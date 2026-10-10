"""LLMClient for the native Gemini ``generateContent`` endpoint.

Companion to :mod:`portkit.agent.openai`. The OpenAI-compatible endpoint at
``/v1beta/openai/chat/completions`` rejects AI Studio **auth keys** with HTTP
400 (``Please pass a valid API key``), so anyone using an AI Studio key after
May 28, 2026 needs this path. Same project, same pricing, different wire
format and a different auth header (``X-goog-api-key`` instead of
``Authorization: Bearer``).

Differences from the OpenAI shape:

- Auth header is ``X-goog-api-key``, no ``Authorization``.
- System prompts are a top-level ``systemInstruction`` object, not a message.
- Messages become ``contents[].role=user|model`` with ``parts[]`` (text,
  ``functionCall``, ``functionResponse``); tool results have to ride inside
  a *user-role* content.
- Tool definitions live under ``tools[].functionDeclarations[]`` (the OpenAI
  JSON Schema field is reused but the container is different).
- ``usageMetadata`` separates candidates and thoughts; we fold both into
  ``output_tokens`` so budget ceilings stay honest (see openai.py:130 for
  the same reasoning against the OpenAI-compat path).
- A ``thoughtSignature`` may sit on a ``functionCall`` part; it's preserved
  on ``ToolCall.extra`` and sent back on the next request verbatim, same
  idea as the OpenAI-compat path's ``extra_content`` (see test_gemini.py).
"""
from __future__ import annotations

from typing import Any

from .budget import Usage
from .http import LLMError, Transport, post_json
from .loop import Message, ToolCall

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiClient:
    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        transport: Transport = post_json,
        extra: dict[str, Any] | None = None,
        base_url: str | None = None,
    ):
        self.model = model
        self.models_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key
        self.transport = transport
        self.extra = dict(extra or {})  # temperature, max_tokens, ...

    @property
    def base_url(self) -> str:
        return f"{self.models_url}/{self.model}:generateContent"

    def complete(self, messages: list[Message], tools: list[dict]) -> Message:
        body: dict[str, Any] = _with_generation_config(self.extra)
        system, contents = to_gemini_messages(messages)
        body["contents"] = contents
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            body["tools"] = [{"functionDeclarations": [to_gemini_tool(t) for t in tools]}]
        headers = {"x-goog-api-key": self.api_key} if self.api_key else {}
        reply = self.transport(self.base_url, headers, body)
        return from_gemini_reply(reply)


# --- request-side translations ------------------------------------------------

# Sampling knobs the rest of portkit names the OpenAI way. The native endpoint
# rejects them at the top level ("Unknown name") and wants them, camelCased,
# under generationConfig.
_GENERATION_KEYS = {
    "temperature": "temperature",
    "top_p": "topP",
    "top_k": "topK",
    "max_tokens": "maxOutputTokens",
    "max_output_tokens": "maxOutputTokens",
    "stop": "stopSequences",
    "seed": "seed",
}


def _with_generation_config(extra: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {}
    config: dict[str, Any] = dict(extra.get("generationConfig") or {})
    for key, value in extra.items():
        if key == "generationConfig":
            continue
        if key in _GENERATION_KEYS:
            if key == "stop" and isinstance(value, str):
                value = [value]
            config[_GENERATION_KEYS[key]] = value
        else:
            body[key] = value
    if config:
        body["generationConfig"] = config
    return body


def to_gemini_tool(schema: dict) -> dict:
    """OpenAI function schema -> native functionDeclarations entry.

    The JSON Schema body is reused verbatim so the model sees the same
    property/required structure. Only the wrapping shape changes.
    """
    return {
        "name": schema["name"],
        "description": schema.get("description", ""),
        "parameters": schema.get("parameters", {"type": "object", "properties": {}}),
    }


def to_gemini_messages(messages: list[Message]) -> tuple[str, list[dict]]:
    """Split out the system prompt (if any), then map turns to ``contents``.

    - ``Message(role='system', ...)`` -> ``systemInstruction.parts[].text``.
    - ``Message(role='user', ...)`` -> ``contents[].role=user``.
    - ``Message(role='assistant', ...)`` -> ``contents[].role=model``. Text
      goes in a text part, each tool call becomes a ``functionCall`` part.
    - ``Message(role='tool', ...)`` -> folded into a preceding user turn as
      a ``functionResponse`` part. If there's no preceding user turn (only
      happens on the very first round if the loop ever opens with a tool,
      which it doesn't), the reply falls back to its own user entry.

    Consecutive same-role entries are merged into a single ``contents``
    entry, mirroring :mod:`portkit.agent.anthropic` (which has the same
    strict-alternation rule).
    """
    system_parts: list[str] = []
    contents: list[dict] = []
    names: dict[str, str] = {}  # local tool-call id -> function name
    for m in messages:
        if m.role == "system":
            if m.content:
                system_parts.append(m.content)
            continue
        role = "user" if m.role in ("user", "tool") else "model"
        parts: list[dict] = []
        if m.role == "tool":
            name = names.get(m.tool_call_id or "") or m.tool_call_id or "tool"
            parts.append({"functionResponse": {"name": name, "response": _parse_tool_payload(m.content)}})
        else:
            if m.content:
                parts.append({"text": m.content})
            for c in m.tool_calls:
                names[c.id] = c.name
                part: dict[str, Any] = {"functionCall": {"name": c.name, "args": c.arguments}}
                if c.extra:
                    part.update(c.extra)  # thoughtSignature and any other provider bookkeeping
                parts.append(part)
        if not parts:
            continue
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"].extend(parts)
        else:
            contents.append({"role": role, "parts": parts})
    return "\n\n".join(system_parts), contents


def _parse_tool_payload(raw: str) -> Any:
    """Tool payloads are JSON-encoded (see AgentSession.run). If the parse
    fails we send the raw string under response.result so the model can at
    least read it back — same tolerance as openai.py's _parse_arguments.
    """
    import json
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {"result": raw}
    # functionResponse.response is a protobuf Struct: it has to be an object.
    return value if isinstance(value, dict) else {"result": value}


# --- reply-side translation ---------------------------------------------------

def from_gemini_reply(reply: dict) -> Message:
    """A native reply -> the provider-neutral Message shape.

    Reply shape (relevant subset):

        {"candidates": [
            {"content": {"role": "model", "parts": [
                {"text": "..."},
                {"functionCall": {"name": "...", "args": {...}}, "thoughtSignature": "..."}
            ]},
             "finishReason": "STOP" | "MAX_TOKENS" | "SAFETY" | "RECITATION" | "OTHER" | ...}]}
    """
    if not isinstance(reply, dict):
        raise LLMError(f"unexpected Gemini reply: {str(reply)[:300]}")
    candidates = reply.get("candidates")
    if not candidates:
        # A blocked prompt comes back with no candidates and a blockReason.
        # Report it as an empty reply with a reason (#85), not a crash.
        feedback = reply.get("promptFeedback") or {}
        if "promptFeedback" in reply or "usageMetadata" in reply:
            return Message(
                "assistant", "", usage=_usage(reply),
                finish_reason=feedback.get("blockReason") or "BLOCKED",
                refusal=feedback.get("blockReasonMessage") or "",
            )
        raise LLMError(f"unexpected Gemini reply: {str(reply)[:300]}")
    candidate = candidates[0] if isinstance(candidates[0], dict) else {}
    # SAFETY / RECITATION / MAX_TOKENS can arrive with no content or no parts.
    parts = (candidate.get("content") or {}).get("parts") or []

    text: list[str] = []
    calls: list[ToolCall] = []
    for n, part in enumerate(parts):
        if part.get("thought"):
            continue  # a thought summary, not reply text
        if "text" in part:
            text.append(part.get("text") or "")
        if "functionCall" in part:
            fc = part["functionCall"]
            extras = {k: v for k, v in part.items() if k != "functionCall"}
            # Use the part index as a stable local id; it's unique within the
            # turn and gets round-tripped via ToolCall.extra so the next
            # request can pair the functionResponse back to the right call.
            calls.append(
                ToolCall(
                    id=f"gemini_call_{n}",
                    name=fc["name"],
                    arguments=fc.get("args") or {},
                    extra=extras,
                )
            )

    return Message(
        "assistant",
        "".join(text),
        tool_calls=calls,
        usage=_usage(reply),
        finish_reason=candidate.get("finishReason"),
    )


def _usage(reply: dict) -> Usage | None:
    """Fold ``thoughtsTokenCount`` into output so token ceilings stay honest
    — a 366-thought-token reply would otherwise look like a 9-token reply.
    Mirrors openai.py's logic for the OpenAI-compat path."""
    meta = reply.get("usageMetadata")
    if not isinstance(meta, dict):
        return None
    prompt = int(meta.get("promptTokenCount") or 0)
    candidates = int(meta.get("candidatesTokenCount") or 0)
    thoughts = int(meta.get("thoughtsTokenCount") or 0)
    return Usage(prompt, candidates + thoughts)
