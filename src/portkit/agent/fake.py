"""A scripted client so the loop is testable with no API key and no network.

Every agent harness needs one of these on day one. If your loop can only be
exercised against a live model, you will not have tests for it.
"""
from __future__ import annotations

from dataclasses import replace

from .budget import Usage
from .loop import Message, ToolCall


class FakeLLM:
    """Replays a list of Messages, one per complete() call.

    ``usage`` stamps every reply that does not carry its own, so budget tests
    can spend tokens without a provider.
    """

    def __init__(self, script: list[Message], usage: Usage | None = None):
        self.script = list(script)
        self.usage = usage
        self.seen: list[list[Message]] = []

    def complete(self, messages, tools):
        self.seen.append(list(messages))
        reply = self.script.pop(0) if self.script else Message("assistant", "out of script")
        if reply.usage is None and self.usage is not None:
            reply = replace(reply, usage=self.usage)
        return reply


def tool_call(name: str, **arguments) -> Message:
    return Message(
        "assistant",
        tool_calls=[ToolCall(id=f"call_{name}", name=name, arguments=arguments)],
    )
