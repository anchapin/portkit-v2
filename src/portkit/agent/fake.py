"""A scripted client so the loop is testable with no API key and no network.

Every agent harness needs one of these on day one. If your loop can only be
exercised against a live model, you will not have tests for it.
"""
from __future__ import annotations

from .loop import Message, ToolCall


class FakeLLM:
    """Replays a list of Messages, one per complete() call."""

    def __init__(self, script: list[Message]):
        self.script = list(script)
        self.seen: list[list[Message]] = []

    def complete(self, messages, tools):
        self.seen.append(list(messages))
        if not self.script:
            return Message("assistant", "out of script")
        return self.script.pop(0)


def tool_call(name: str, **arguments) -> Message:
    return Message(
        "assistant",
        tool_calls=[ToolCall(id=f"call_{name}", name=name, arguments=arguments)],
    )
