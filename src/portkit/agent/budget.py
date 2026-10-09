"""Step, token and dollar ceilings, and the accounting behind them.

``max_steps`` bounds one session. Tokens and dollars bound a whole run: every
residue group draws from the same allowance, so a mod with forty hard groups
cannot spend forty times what you said it could.

Dollars are derived, never reported by a provider: tokens times the prices you
configure. With no prices there is no dollar figure, and asking for a dollar
ceiling without prices is a configuration error rather than a silent no-op.

Ceilings are checked before each model call, so a run can overshoot one by at
most the single completion that crossed it. Nothing is cut off mid-reply, and
the tool calls that reply asked for still run, so their output is kept.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class Usage:
    """Tokens one completion consumed, as the provider reported them."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class Pricing:
    """USD per million tokens."""

    input_per_mtok: float
    output_per_mtok: float

    def cost(self, usage: Usage) -> float:
        return (
            usage.input_tokens * self.input_per_mtok
            + usage.output_tokens * self.output_per_mtok
        ) / 1_000_000

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Pricing | None":
        """PORTKIT_LLM_INPUT_PRICE / PORTKIT_LLM_OUTPUT_PRICE, USD per million tokens."""
        env = os.environ if env is None else env
        raw_in, raw_out = env.get("PORTKIT_LLM_INPUT_PRICE"), env.get("PORTKIT_LLM_OUTPUT_PRICE")
        if not raw_in and not raw_out:
            return None
        try:
            return cls(float(raw_in or 0), float(raw_out or 0))
        except ValueError as exc:
            raise ValueError(f"LLM prices must be numbers (USD per million tokens): {exc}") from exc


@dataclass
class Spend:
    """What was used. One per session, and one summed over the run."""

    steps: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float | None = None  # None when no pricing is configured
    # Completions that came back without a usage block. Counted so a ceiling
    # that never tripped because the provider reported nothing is visible.
    unreported: int = 0

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def record(self, usage: Usage | None, pricing: Pricing | None) -> None:
        self.steps += 1
        if usage is None:
            self.unreported += 1
            return
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        if pricing is not None:
            self.cost = (self.cost or 0.0) + pricing.cost(usage)

    def add(self, other: "Spend") -> None:
        self.steps += other.steps
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.unreported += other.unreported
        if other.cost is not None:
            self.cost = (self.cost or 0.0) + other.cost

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "steps": self.steps,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": None if self.cost is None else round(self.cost, 6),
        }
        if self.unreported:
            out["unreported_completions"] = self.unreported
        return out

    def describe(self) -> str:
        text = f"{self.steps} step(s), {self.tokens:,} tokens"
        if self.cost is not None:
            text += f", ${self.cost:.4f}"
        return text


@dataclass(frozen=True)
class Budget:
    """Ceilings for one run. ``None`` means unbounded on that axis."""

    max_steps: int = 12  # per session
    max_tokens: int | None = None  # per run, input plus output
    max_cost: float | None = None  # per run, USD
    pricing: Pricing | None = None

    def __post_init__(self):
        if self.max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        if self.max_tokens is not None and self.max_tokens < 1:
            raise ValueError("max_tokens must be at least 1")
        if self.max_cost is not None and self.max_cost <= 0:
            raise ValueError("max_cost must be more than 0")
        if self.max_cost is not None and self.pricing is None:
            raise ValueError(
                "a dollar ceiling needs prices: set PORTKIT_LLM_INPUT_PRICE and "
                "PORTKIT_LLM_OUTPUT_PRICE (USD per million tokens)"
            )

    def exhausted(self, spent: Spend) -> str | None:
        """Which run ceiling ``spent`` has reached, if any: tokens | cost."""
        if self.max_tokens is not None and spent.tokens >= self.max_tokens:
            return "tokens"
        if self.max_cost is not None and (spent.cost or 0.0) >= self.max_cost:
            return "cost"
        return None
