"""The whole agent harness. Deliberately this short.

A provider implements one method. The loop sends messages, executes any tool
call, appends the result, and repeats until the model stops calling tools or the
step budget runs out. There is no graph, no router, no planner node. If you find
yourself wanting one, the fix is almost always a better tool or a better
validator message, not more orchestration.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Message:
    role: str  # system | user | assistant | tool
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None


class LLMClient(Protocol):
    """Implement this for OpenAI, Anthropic, OpenRouter, a local model, whatever."""

    def complete(self, messages: list[Message], tools: list[dict]) -> Message: ...


@dataclass
class AgentResult:
    messages: list[Message]
    steps: int
    stopped: str  # done | budget | error


class AgentSession:
    def __init__(
        self,
        client: LLMClient,
        toolbox,
        system: str,
        max_steps: int = 12,
        on_step=None,
    ):
        self.client = client
        self.toolbox = toolbox
        self.max_steps = max_steps
        self.on_step = on_step
        self.messages: list[Message] = [Message("system", system)]

    def run(self, task: str) -> AgentResult:
        self.messages.append(Message("user", task))
        for step in range(1, self.max_steps + 1):
            reply = self.client.complete(self.messages, self.toolbox.schemas())
            self.messages.append(reply)

            if not reply.tool_calls:
                if self.on_step:
                    self.on_step(step, None, reply.content)
                return AgentResult(self.messages, step, "done")

            for call in reply.tool_calls:
                try:
                    output = self.toolbox.invoke(call.name, call.arguments)
                except Exception as exc:  # a tool error is data, not a crash
                    output = {"error": f"{type(exc).__name__}: {exc}"}
                if self.on_step:
                    self.on_step(step, call, output)
                self.messages.append(
                    Message("tool", json.dumps(output, default=str), tool_call_id=call.id)
                )
        return AgentResult(self.messages, self.max_steps, "budget")
