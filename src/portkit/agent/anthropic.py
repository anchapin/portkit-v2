"""LLMClient for Anthropic-style Messages APIs.

Differences from the OpenAI shape that this module absorbs:
- system prompts are a top-level field, not a message;
- tool calls are ``tool_use`` content blocks with a parsed ``input`` object;
- tool results go back as ``tool_result`` blocks inside a *user* message, and
  every result for one assistant turn must sit in that single message.
"""
from __future__ import annotations

from typing import Any

from .budget import Usage
from .http import LLMError, Transport, post_json
from .loop import Message, ToolCall

DEFAULT_BASE_URL = "https://api.anthropic.com"
API_VERSION = "2023-06-01"


class AnthropicClient:
    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        max_tokens: int = 4096,
        transport: Transport = post_json,
        extra: dict[str, Any] | None = None,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.max_tokens = max_tokens
        self.transport = transport
        self.extra = dict(extra or {})

    def complete(self, messages: list[Message], tools: list[dict]) -> Message:
        system, turns = to_anthropic_messages(messages)
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": turns,
            **self.extra,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [to_anthropic_tool(t) for t in tools]
        headers = {"anthropic-version": API_VERSION}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        reply = self.transport(f"{self.base_url}/v1/messages", headers, body)
        return from_anthropic_reply(reply)


def to_anthropic_tool(schema: dict) -> dict:
    return {
        "name": schema["name"],
        "description": schema.get("description", ""),
        "input_schema": schema.get("parameters", {"type": "object", "properties": {}}),
    }


def _blocks(m: Message) -> list[dict]:
    if m.role == "tool":
        return [{"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}]
    blocks: list[dict] = [{"type": "text", "text": m.content}] if m.content else []
    for c in m.tool_calls:
        blocks.append({"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments})
    return blocks


def to_anthropic_messages(messages: list[Message]) -> tuple[str, list[dict]]:
    system = "\n\n".join(m.content for m in messages if m.role == "system" and m.content)
    turns: list[dict] = []
    for m in messages:
        if m.role == "system":
            continue
        role = "assistant" if m.role == "assistant" else "user"  # tool results ride as user
        blocks = _blocks(m)
        if not blocks:
            continue
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"].extend(blocks)  # the API wants strictly alternating roles
        else:
            turns.append({"role": role, "content": blocks})
    return system, turns


def from_anthropic_reply(reply: dict) -> Message:
    if not isinstance(reply, dict) or not isinstance(reply.get("content"), list):
        raise LLMError(f"unexpected Anthropic-style reply: {str(reply)[:300]}")
    text: list[str] = []
    calls: list[ToolCall] = []
    for block in reply["content"]:
        if block.get("type") == "text":
            text.append(block.get("text", ""))
        elif block.get("type") == "tool_use":
            calls.append(ToolCall(id=block["id"], name=block["name"], arguments=block.get("input") or {}))
    return Message(
        "assistant",
        "".join(text),
        tool_calls=calls,
        usage=_usage(reply),
        finish_reason=reply.get("stop_reason"),
    )


def _usage(reply: dict) -> Usage | None:
    usage = reply.get("usage")
    if not isinstance(usage, dict):
        return None
    # Cache reads and writes are input the account pays for, at whatever rate;
    # counting them as input keeps a token ceiling honest.
    inputs = sum(
        int(usage.get(k) or 0)
        for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    )
    return Usage(inputs, int(usage.get("output_tokens") or 0))
