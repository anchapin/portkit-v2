"""LLMClient for OpenAI-style chat completions.

Also covers anything that speaks the same wire format (OpenRouter, vLLM,
Ollama, LM Studio, Azure-compatible gateways): point ``base_url`` at it.
"""
from __future__ import annotations

import json
from typing import Any

from .budget import Usage
from .http import LLMError, Transport, post_json
from .loop import Message, ToolCall

DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAIClient:
    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        transport: Transport = post_json,
        extra: dict[str, Any] | None = None,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.extra = dict(extra or {})  # temperature, max_tokens, ... passed through

    def complete(self, messages: list[Message], tools: list[dict]) -> Message:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [to_openai_message(m) for m in messages],
            **self.extra,
        }
        if tools:
            body["tools"] = [to_openai_tool(t) for t in tools]
        headers = {"authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        reply = self.transport(f"{self.base_url}/chat/completions", headers, body)
        return from_openai_reply(reply)


def to_openai_tool(schema: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": schema["name"],
            "description": schema.get("description", ""),
            "parameters": schema.get("parameters", {"type": "object", "properties": {}}),
        },
    }


def to_openai_message(m: Message) -> dict:
    if m.role == "tool":
        return {"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content}
    if m.role == "assistant" and m.tool_calls:
        return {
            "role": "assistant",
            "content": m.content or None,
            "tool_calls": [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                }
                for c in m.tool_calls
            ],
        }
    return {"role": m.role, "content": m.content}


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Hand the bad payload to the tool; the loop turns the TypeError into
        # data the model can read and correct, instead of crashing the run.
        return {"_invalid_arguments": raw}
    return parsed if isinstance(parsed, dict) else {"_invalid_arguments": raw}


def from_openai_reply(reply: dict) -> Message:
    try:
        message = reply["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"unexpected OpenAI-style reply: {str(reply)[:300]}") from exc
    calls = [
        ToolCall(
            id=c.get("id", ""),
            name=c["function"]["name"],
            arguments=_parse_arguments(c["function"].get("arguments")),
        )
        for c in message.get("tool_calls") or []
        if c.get("type", "function") == "function"
    ]
    return Message(
        "assistant", message.get("content") or "", tool_calls=calls, usage=_usage(reply)
    )


def _usage(reply: dict) -> Usage | None:
    usage = reply.get("usage")
    if not isinstance(usage, dict):
        return None
    return Usage(int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0))
