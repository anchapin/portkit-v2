"""The whole agent harness. Deliberately this short.

A provider implements one method. The loop sends messages, executes any tool
call, appends the result, and repeats until the model stops calling tools or a
budget runs out: steps per session, and optionally tokens or dollars shared
across a whole run (see ``budget.py``). There is no graph, no router, no
planner node. If you find yourself wanting one, the fix is almost always a better tool or a better
validator message, not more orchestration.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .budget import Budget, Spend, Usage


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    # Opaque provider fields that must go back on the next request unchanged,
    # e.g. Gemini's thought signature (``extra_content``). Empty for most.
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    role: str  # system | user | assistant | tool
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    # Tokens the completion that produced this message cost, when the provider
    # says. Only assistant messages carry it.
    usage: Usage | None = None
    # Why the provider stopped generating ("stop", "length", "tool_calls",
    # "content_filter", Anthropic's "end_turn"/"max_tokens", ...), and any
    # refusal text it put beside the content. Diagnostics only: an empty final
    # reply means nothing on its own, these say whether it was a cutoff, a
    # filter or a refusal. Never sent back to the model.
    finish_reason: str | None = None
    refusal: str = ""


@runtime_checkable
class LLMClient(Protocol):
    """Implement this for OpenAI, Anthropic, OpenRouter, a local model, whatever."""

    def complete(self, messages: list[Message], tools: list[dict]) -> Message: ...


@dataclass
class AgentResult:
    messages: list[Message]
    steps: int
    stopped: str  # done | budget | error
    # Which ceiling stopped a budget run: steps | tokens | cost.
    limit: str | None = None
    spend: Spend = field(default_factory=Spend)


class AgentSession:
    def __init__(
        self,
        client: LLMClient,
        toolbox,
        system: str,
        max_steps: int = 12,
        on_step=None,
        budget: Budget | None = None,
        run_spend: Spend | None = None,
    ):
        """``budget`` adds token and dollar ceilings; its max_steps wins over
        ``max_steps``. ``run_spend`` is the running total for the whole run,
        shared between sessions, which the ceilings are checked against."""
        self.client = client
        self.toolbox = toolbox
        self.budget = budget
        self.max_steps = budget.max_steps if budget else max_steps
        self.on_step = on_step
        self.messages: list[Message] = [Message("system", system)]
        self.spend = Spend()
        self.run_spend = run_spend

    def _record(self, usage: Usage | None) -> None:
        pricing = self.budget.pricing if self.budget else None
        self.spend.record(usage, pricing)
        if self.run_spend is not None:
            self.run_spend.record(usage, pricing)

    def run(self, task: str) -> AgentResult:
        self.messages.append(Message("user", task))
        for step in range(1, self.max_steps + 1):
            # Checked before every call, never mid-reply: whatever the last
            # reply asked for has already run, so its writes are kept.
            if self.budget:
                limit = self.budget.exhausted(
                    self.run_spend if self.run_spend is not None else self.spend
                )
                if limit:
                    return AgentResult(self.messages, step - 1, "budget", limit, self.spend)
            reply = self.client.complete(self.messages, self.toolbox.schemas())
            self._record(reply.usage)
            self.messages.append(reply)

            if not reply.tool_calls:
                if self.on_step:
                    self.on_step(step, None, reply.content)
                return AgentResult(self.messages, step, "done", None, self.spend)

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
        return AgentResult(self.messages, self.max_steps, "budget", "steps", self.spend)
