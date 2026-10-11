"""The one place the agent touches the network. Stdlib only.

Every provider client takes a ``transport``: a callable that POSTs a JSON body
and returns the decoded JSON reply. The default is :func:`post_json`. Tests pass
their own, so no client test needs an API key or a socket.

Every client sends through :func:`complete_with_retry`, which retries what is
worth retrying (#137):

- HTTP 429, 500, 502, 503, 504 and 529, a connection failure or a timeout, up to
  ``max_retries`` times (default 2) with bounded exponential backoff. A
  ``Retry-After`` header is honoured, capped at :data:`MAX_RETRY_AFTER`
  seconds. OpenRouter sometimes answers HTTP 200 with an ``error`` object
  carrying one of those codes; that counts too.
- A reply with no text, no tool calls and ``finish_reason`` "error" (OpenRouter
  relaying a provider that died mid-generation), once.

``PORTKIT_LLM_MAX_RETRIES`` overrides the count; 0 turns every retry off,
including the empty-reply one. A retry happens inside one ``complete()`` call,
so it is invisible to transcripts: the request digest is the same, and only the
final reply is recorded. Tokens a discarded empty reply was billed for are
added to the final reply's usage, so budgets and spend still see them.
"""
from __future__ import annotations

import email.utils
import http.client
import json
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping

from .budget import Usage
from .loop import Message

Transport = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]

# 529 is Anthropic's "overloaded".
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504, 529})
DEFAULT_MAX_RETRIES = 2
MAX_RETRY_AFTER = 60.0


class LLMError(RuntimeError):
    """A provider answered with something other than a usable completion."""

    def __init__(
        self,
        message: str,
        status: int | None = None,
        body: str = "",
        retry_after: float | None = None,
        transient: bool = False,
    ):
        super().__init__(message)
        self.status = status
        self.body = body
        # Seconds the provider asked us to wait (Retry-After), when it said.
        self.retry_after = retry_after
        # A connection failure or timeout: no answer at all, worth another try.
        self.transient = transient

    @property
    def retryable(self) -> bool:
        return self.transient or self.status in RETRY_STATUSES


def _retry_after(headers) -> float | None:
    raw = headers.get("Retry-After") if headers is not None else None
    if not raw:
        return None
    raw = str(raw).strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    return max(0.0, when.timestamp() - time.time())


def post_json(url: str, headers: dict[str, str], body: dict[str, Any], timeout: float = 120.0) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, method="POST", headers={"content-type": "application/json", **headers}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise LLMError(
            f"HTTP {exc.code} from {url}: {detail[:500]}",
            status=exc.code,
            body=detail,
            retry_after=_retry_after(exc.headers),
        ) from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"could not reach {url}: {exc.reason}", transient=True) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise LLMError(f"timed out waiting for {url}", transient=True) from exc
    except (ConnectionError, http.client.HTTPException) as exc:
        raise LLMError(f"connection to {url} failed: {type(exc).__name__}: {exc}", transient=True) from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMError(f"non-JSON reply from {url}: {raw[:200]}", body=raw) from exc


@dataclass(frozen=True)
class RetryPolicy:
    """How hard to try. ``sleep`` is injectable so tests never wait."""

    max_retries: int = DEFAULT_MAX_RETRIES
    base_delay: float = 1.0
    max_delay: float = 20.0
    sleep: Callable[[float], None] = field(default=time.sleep, compare=False)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "RetryPolicy":
        env = os.environ if env is None else env
        raw = env.get("PORTKIT_LLM_MAX_RETRIES")
        if raw in (None, ""):
            return cls()
        try:
            count = int(raw)
        except ValueError:
            raise ValueError(f"PORTKIT_LLM_MAX_RETRIES must be a whole number, got {raw!r}") from None
        if count < 0:
            raise ValueError("PORTKIT_LLM_MAX_RETRIES must be 0 or more")
        return cls(max_retries=count)

    def delay(self, attempt: int, error: LLMError) -> float:
        """Seconds before retry number ``attempt`` (1-based)."""
        if error.retry_after is not None:
            return min(error.retry_after, MAX_RETRY_AFTER)
        return min(self.base_delay * (2 ** (attempt - 1)), self.max_delay)


def body_error(reply: Any) -> LLMError | None:
    """An error object a gateway put in a 200 reply instead of a completion.

    OpenRouter does this when the upstream provider fails after the response
    has started: ``{"error": {"code": 502, "message": ...}}`` with no choices.
    """
    if not isinstance(reply, dict) or reply.get("choices") or not isinstance(reply.get("error"), dict):
        return None
    err = reply["error"]
    code = err.get("code")
    try:
        status = int(code) if code is not None else None
    except (TypeError, ValueError):
        status = None
    return LLMError(f"provider error in reply: {str(err)[:300]}", status=status, body=json.dumps(reply)[:2000])


def _empty_error(message: Message) -> bool:
    return (
        not message.content
        and not message.tool_calls
        and not message.refusal
        and (message.finish_reason or "").lower() == "error"
    )


def complete_with_retry(
    transport: Transport,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    parse: Callable[[dict[str, Any]], Message],
    policy: RetryPolicy | None = None,
) -> Message:
    """POST ``body`` and parse the reply, retrying what is worth retrying.

    The same body is sent on every attempt. See the module docstring.
    """
    policy = policy or RetryPolicy.from_env()
    attempt = 0  # retries spent on transport errors
    empty_left = min(1, policy.max_retries)
    billed: Usage | None = None  # usage of discarded empty replies
    while True:
        try:
            reply = transport(url, headers, body)
            error = body_error(reply)
            if error is not None:
                raise error
        except LLMError as exc:
            if not exc.retryable or attempt >= policy.max_retries:
                raise
            attempt += 1
            policy.sleep(policy.delay(attempt, exc))
            continue
        message = parse(reply)
        if _empty_error(message) and empty_left > 0:
            empty_left -= 1
            if message.usage is not None:
                billed = _add(billed, message.usage)
            policy.sleep(policy.base_delay)
            continue
        if billed is not None:
            message = replace(message, usage=_add(billed, message.usage))
        return message


def _add(a: Usage | None, b: Usage | None) -> Usage | None:
    if a is None:
        return b
    if b is None:
        return a
    return Usage(a.input_tokens + b.input_tokens, a.output_tokens + b.output_tokens)
