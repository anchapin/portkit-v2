"""Record agent sessions to a transcript, and replay them with no network.

A transcript is JSON Lines, one completion per line, in call order:

    {"v": 1, "session": 0, "step": 1, "request": "<sha256>", "last": {...}, "reply": {...}}

``request`` is a digest of exactly what the client was sent (every message plus
the tool names); ``last`` is the newest message in that request, kept readable
so a mismatch can say what changed; ``reply`` is the provider's answer in the
provider-neutral ``Message`` shape, usage included, so budgets replay too.

:class:`ReplayClient` hands the recorded replies back in order and, by default,
checks each request against its digest. If a prompt, a tool's output or the
validator's findings drift, the replay stops at the first step that differs
and names it. That is what turns "the agent did something odd last week" into
a failing test.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .budget import Usage
from .loop import LLMClient, Message, ToolCall

VERSION = 1


def message_to_dict(m: Message) -> dict[str, Any]:
    out: dict[str, Any] = {"role": m.role, "content": m.content}
    if m.tool_calls:
        out["tool_calls"] = [
            {"id": c.id, "name": c.name, "arguments": c.arguments} for c in m.tool_calls
        ]
    if m.tool_call_id is not None:
        out["tool_call_id"] = m.tool_call_id
    if m.usage is not None:
        out["usage"] = {"input_tokens": m.usage.input_tokens, "output_tokens": m.usage.output_tokens}
    return out


def message_from_dict(d: dict[str, Any]) -> Message:
    usage = d.get("usage")
    return Message(
        role=d["role"],
        content=d.get("content", ""),
        tool_calls=[
            ToolCall(id=c["id"], name=c["name"], arguments=c.get("arguments") or {})
            for c in d.get("tool_calls") or []
        ],
        tool_call_id=d.get("tool_call_id"),
        usage=Usage(usage["input_tokens"], usage["output_tokens"]) if usage else None,
    )


def request_digest(messages: list[Message], tools: list[dict]) -> str:
    """What the model was asked, as one stable hash. Usage is not part of it."""
    payload = {
        "messages": [
            {k: v for k, v in message_to_dict(m).items() if k != "usage"} for m in messages
        ],
        "tools": sorted(t["name"] for t in tools),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_session_start(messages: list[Message]) -> bool:
    # Every session opens with its system prompt and one task message.
    return len(messages) <= 2


class RecordingClient:
    """Wraps any LLMClient and appends every completion to a transcript file.

    The file is truncated when the recorder is created, so one recorder is one
    run. Lines are flushed as they happen, so a run that dies midway still
    leaves everything up to the failure on disk.
    """

    def __init__(self, inner: LLMClient, path: Path):
        self.inner = inner
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("")
        self.session = -1
        self.step = 0

    def complete(self, messages: list[Message], tools: list[dict]) -> Message:
        if _is_session_start(messages) or self.session < 0:
            self.session += 1
            self.step = 0
        self.step += 1
        digest = request_digest(messages, tools)
        reply = self.inner.complete(messages, tools)
        line = {
            "v": VERSION,
            "session": self.session,
            "step": self.step,
            "request": digest,
            "last": _summarise(messages[-1]) if messages else None,
            "reply": message_to_dict(reply),
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, sort_keys=True) + "\n")
        return reply


class ReplayMismatch(AssertionError):
    """The run asked the model something the transcript never recorded."""


class ReplayClient:
    """Feeds a transcript's replies back, in order, with no network and no key."""

    def __init__(self, path: Path, strict: bool = True):
        self.path = Path(path)
        self.strict = strict
        self.entries = load(self.path)
        self.position = 0

    @property
    def remaining(self) -> int:
        """Recorded completions not yet asked for. Zero after a faithful replay."""
        return len(self.entries) - self.position

    def complete(self, messages: list[Message], tools: list[dict]) -> Message:
        if self.position >= len(self.entries):
            raise ReplayMismatch(
                f"{self.path.name}: the run asked for completion {self.position + 1}, "
                f"but only {len(self.entries)} were recorded"
            )
        entry = self.entries[self.position]
        self.position += 1
        if self.strict and request_digest(messages, tools) != entry["request"]:
            raise ReplayMismatch(
                f"{self.path.name}: session {entry['session']} step {entry['step']} "
                f"diverged from the recording. Recorded last message: "
                f"{json.dumps(entry.get('last'))[:300]}; this run sent: "
                f"{json.dumps(_summarise(messages[-1]))[:300]}. If the change is "
                f"intended, re-record with --agent-record."
            )
        return message_from_dict(entry["reply"])


def load(path: Path) -> list[dict[str, Any]]:
    entries = []
    for n, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: line {n} is not JSON: {exc}") from exc
        if entry.get("v") != VERSION:
            raise ValueError(f"{path}: line {n} has transcript version {entry.get('v')!r}, expected {VERSION}")
        for key in ("request", "reply"):
            if key not in entry:
                raise ValueError(f"{path}: line {n} has no {key!r}")
        entries.append(entry)
    return entries


def _summarise(m: Message) -> dict[str, Any]:
    d = message_to_dict(m)
    d.pop("usage", None)
    if len(d.get("content", "")) > 500:
        d["content"] = d["content"][:500] + "..."
    return d
