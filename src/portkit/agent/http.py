"""The one place the agent touches the network. Stdlib only.

Every provider client takes a ``transport``: a callable that POSTs a JSON body
and returns the decoded JSON reply. The default is :func:`post_json`. Tests pass
their own, so no client test needs an API key or a socket.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable

Transport = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]


class LLMError(RuntimeError):
    """A provider answered with something other than a usable completion."""

    def __init__(self, message: str, status: int | None = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


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
        raise LLMError(f"HTTP {exc.code} from {url}: {detail[:500]}", status=exc.code, body=detail) from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"could not reach {url}: {exc.reason}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMError(f"non-JSON reply from {url}: {raw[:200]}", body=raw) from exc
