"""The agent eval matrix: one row per provider and model (#77).

The code around a model changes its score. The OpenAI-style and
Anthropic-style clients translate tool calls differently, so each provider is
its own small harness, and a default should never be picked from one path's
results. This runs the same fixture residue through each target under the same
budgets and scores it one way:

- **pass**: the group resolved. That means the session ended on its own, wrote
  files, and the validator found nothing new. The validator is the only score.
  There's no credit for producing a file or calling a tool.
- **fail**: the session ran and the validator had its say, but the group didn't
  resolve (declined, rolled back, or out of steps).
- **unscored**: the provider errored, the loop crashed, or the run's ceiling was
  hit before the group started, so the validator never judged it. Unscored
  groups are left out of the pass rate and counted separately.

Groups no tool can work on (bytecode, nested jars, collisions) aren't tasks
and don't appear at all.

Format failures, meaning tool calls that don't fit the toolbox (an unknown tool
or bad arguments), are counted per target. A spike means the translation layer
and the model disagree, not that the model is weaker.
"""
from __future__ import annotations

import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from .budget import Budget
from .loop import LLMClient
from .residue import GroupOutcome, ResidueAgent


def score(outcome: GroupOutcome) -> str | None:
    """pass | fail | unscored, or None for a group that is not a task."""
    if outcome.status == "skipped" and outcome.stopped != "budget":
        return None  # SKIP_KINDS: nothing an agent could work on
    if outcome.status == "resolved":
        return "pass"
    if outcome.stopped == "error" or outcome.status in ("error", "skipped"):
        return "unscored"
    return "fail"


@dataclass
class MatrixRow:
    target: str
    passed: int = 0
    failed: int = 0
    unscored: int = 0
    steps: int = 0
    tool_calls: int = 0
    format_failures: int = 0
    tokens: int = 0
    cost: float | None = None
    stops: dict[str, int] = field(default_factory=dict)  # done | budget | error
    tasks: list[dict] = field(default_factory=list)

    @property
    def scored(self) -> int:
        return self.passed + self.failed

    @property
    def pass_rate(self) -> float | None:
        return self.passed / self.scored if self.scored else None

    @property
    def calls_per_success(self) -> float | None:
        return self.tool_calls / self.passed if self.passed else None

    def add(self, fixture: str, outcome: GroupOutcome) -> None:
        verdict = score(outcome)
        if verdict is None:
            return
        if verdict == "pass":
            self.passed += 1
        elif verdict == "fail":
            self.failed += 1
        else:
            self.unscored += 1
        self.steps += outcome.steps
        self.tool_calls += outcome.tool_calls
        self.format_failures += outcome.format_failures
        self.tokens += outcome.spend.tokens
        if outcome.spend.cost is not None:
            self.cost = (self.cost or 0.0) + outcome.spend.cost
        stop = outcome.stopped or "budget"
        self.stops[stop] = self.stops.get(stop, 0) + 1
        self.tasks.append({"fixture": fixture, "group": outcome.key, "score": verdict,
                           "status": outcome.status, "stopped": outcome.stopped,
                           "format_failures": outcome.format_failures})

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "pass": self.passed,
            "fail": self.failed,
            "unscored": self.unscored,
            "pass_rate": self.pass_rate,
            "steps": self.steps,
            "tool_calls": self.tool_calls,
            "tool_calls_per_success": self.calls_per_success,
            "format_failures": self.format_failures,
            "tokens": self.tokens,
            "cost_usd": self.cost,
            "stops": dict(sorted(self.stops.items())),
            "tasks": self.tasks,
        }


def agent_fixtures(root: Path, names: Iterable[str] = ()) -> list[Path]:
    """Fixtures whose residue the agent works on: ``expect_unhandled`` > 0."""
    wanted = set(names)
    cases = []
    for case in sorted(p for p in root.iterdir() if (p / "case.toml").is_file()):
        if wanted and case.name not in wanted:
            continue
        spec = tomllib.loads((case / "case.toml").read_text())
        if wanted or spec.get("expect_unhandled", 0) > 0:
            cases.append(case)
    return cases


def run_matrix(
    targets: list[tuple[str, Callable[[str], LLMClient]]],
    cases: list[Path],
    budget: Budget,
) -> list[MatrixRow]:
    """``targets`` is (label, factory); the factory gets the fixture name and
    returns a fresh client, so a replay target can pick that fixture's
    transcript. Every target runs under the same ``budget``."""
    from ..pipeline import convert

    rows = []
    for label, factory in targets:
        row = MatrixRow(label)
        for case in cases:
            agent = ResidueAgent(factory(case.name), budget=budget)
            with tempfile.TemporaryDirectory() as tmp:
                result = convert(case / "input", Path(tmp) / "out", emit_addon=False, agent=agent)
            for outcome in (result.agent.outcomes if result.agent else []):
                row.add(case.name, outcome)
        rows.append(row)
    return rows


def render(rows: list[MatrixRow]) -> str:
    def pct(v):
        return "-" if v is None else f"{100 * v:.0f}%"

    def num(v):
        return "-" if v is None else f"{v:.1f}"

    header = ("target", "pass", "fail", "unscored", "pass rate", "steps", "calls/success",
              "format fail", "tokens", "stops")
    body = [
        (r.target, str(r.passed), str(r.failed), str(r.unscored), pct(r.pass_rate), str(r.steps),
         num(r.calls_per_success), str(r.format_failures), str(r.tokens),
         " ".join(f"{k}={v}" for k, v in sorted(r.stops.items())) or "-")
        for r in rows
    ]
    widths = [max(len(x) for x in col) for col in zip(header, *body)]
    lines = ["  ".join(c.ljust(w) for c, w in zip(line, widths)).rstrip() for line in (header, *body)]
    return "\n".join(lines)
