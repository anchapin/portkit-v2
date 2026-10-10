"""Turn ``Unhandled`` items into agent tasks and run one session per group.

The deterministic converters say exactly what they refused and why. This module
is the bridge from that list to the loop:

1. :func:`group_residue` folds the items by kind and source file, so a
   ``sounds.json`` refused for two different events is one task, not two.
2. :func:`build_task` writes the task prompt: the source content and the
   specific reasons the deterministic path gave, never a generic "convert this".
3. :class:`ResidueAgent` runs one :class:`AgentSession` per group against the
   output tree and keeps a group's writes only if the validator finds no error
   the session introduced. A group that breaks the tree is rolled back, so one
   bad session can never cost the player the installable addon.

A group counts as resolved only when its session ended on its own, it wrote at
least one file, and the validator found no new error. Declaring victory in prose
is not enough, and neither is a session that wrote nothing because the Java behaviour
has no Bedrock form: that one stays residue, with the agent's reason attached.

Every group's spend (steps, tokens, dollars when priced) is reported. Token and
dollar ceilings are per run: once one is reached, the session in flight stops
before its next call, keeping whatever it wrote that still validates, and the
groups after it are skipped with the ceiling named.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..meta import ModMetadata
from ..model import Unhandled
from ..pack import ENGINE_FLOOR, manifest
from ..validate import validate_tree
from .budget import Budget, Spend
from .loop import AgentSession, LLMClient
from .tools import SYSTEM_PROMPT, ToolBox

# Kinds no session can make progress on with the tools it has: bytecode is not
# readable text, a nested jar is not unpacked, and a namespace collision is a
# decision about the pack, not a file to convert. They stay residue, skipped
# with a reason rather than burning a session.
SKIP_KINDS = {
    "java_code": "compiled bytecode; the agent's tools read text files only",
    "nested_jar": "nested jars are not unpacked, so there is nothing to read",
    "namespace_collision": "a collision is a packaging decision, not a file to convert",
}

# Where Bedrock keeps each kind of content. A hint, not a constraint: the
# validator is still the only thing that decides whether the result is right.
_OUTPUT_HINTS = {
    "recipe": "Bedrock recipes go in behavior_pack/recipes/<name>.json.",
    "loot": "Bedrock loot tables go in behavior_pack/loot_tables/<path>.json.",
    "block": (
        "Bedrock blocks go in behavior_pack/blocks/<name>.json, geometry in "
        "resource_pack/models/blocks/<name>.geo.json."
    ),
    "item": "Bedrock items go in behavior_pack/items/<name>.json.",
    "sound": "Bedrock sounds are declared in resource_pack/sounds/sound_definitions.json.",
    "texture": "Bedrock textures live under resource_pack/textures/.",
    "texture_animation": "Bedrock flipbooks go in resource_pack/textures/flipbook_textures.json.",
}

_BINARY_SUFFIXES = {".png", ".ogg", ".wav", ".class", ".jar", ".nbt"}
_MAX_INLINE_CHARS = 16_000
_MAX_LISTED_FILES = 100


@dataclass
class ResidueGroup:
    """Every Unhandled item that shares a kind and a source."""

    kind: str
    source: str
    items: list[Unhandled] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.source}"

    @property
    def reasons(self) -> list[str]:
        seen: list[str] = []
        for item in self.items:
            if item.reason not in seen:
                seen.append(item.reason)
        return seen

    @property
    def count(self) -> int:
        """Source files this group stands for (an entry per file, not per reason)."""
        return max((item.count for item in self.items), default=0)


def group_residue(unhandled: list[Unhandled]) -> list[ResidueGroup]:
    """Fold residue by (kind, source), keeping first-seen order."""
    groups: dict[tuple[str, str], ResidueGroup] = {}
    for item in unhandled:
        key = (item.kind, item.source)
        if key not in groups:
            groups[key] = ResidueGroup(item.kind, item.source)
        groups[key].items.append(item)
    return list(groups.values())


def _source_block(source_root: Path, source: str) -> str:
    """The source the deterministic path refused, as the task prompt shows it."""
    path = (source_root / source.rstrip("/")).resolve()
    root = source_root.resolve()
    if path != root and root not in path.parents:
        return f"(source {source!r} is not a path inside the mod)"
    if path.is_dir():
        files = sorted(str(p.relative_to(source_root)) for p in path.rglob("*") if p.is_file())
        shown = files[:_MAX_LISTED_FILES]
        more = f"\n... and {len(files) - len(shown)} more" if len(files) > len(shown) else ""
        listing = "\n".join(f"- {f}" for f in shown) or "(empty)"
        return f"Directory {source} holds {len(files)} file(s); read them with read_source:\n{listing}{more}"
    if not path.is_file():
        return f"(no file at {source}; use list_source to look around)"
    if path.suffix.lower() in _BINARY_SUFFIXES:
        return f"{source} is a binary file ({path.stat().st_size:,} bytes); its content is not shown."
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > _MAX_INLINE_CHARS:
        text = text[:_MAX_INLINE_CHARS] + f"\n... (truncated; {len(text):,} chars in total, read_source has the rest)"
    return f"Source file {source}:\n```\n{text}\n```"


def _tree_listing(out_tree: Path) -> str:
    files = sorted(
        str(p.relative_to(out_tree))
        for pack in ("behavior_pack", "resource_pack")
        if (out_tree / pack).is_dir()
        for p in (out_tree / pack).rglob("*")
        if p.is_file()
    )
    shown = files[:_MAX_LISTED_FILES]
    more = f"\n... and {len(files) - len(shown)} more" if len(files) > len(shown) else ""
    return "\n".join(f"- {f}" for f in shown) + more if shown else "(empty)"


def build_task(group: ResidueGroup, source_root: Path, out_tree: Path, namespace: str) -> str:
    """The user message for one session: what was refused, why, and the source."""
    reasons = "\n".join(f"- {r}" for r in group.reasons)
    hint = _OUTPUT_HINTS.get(group.kind, "")
    parts = [
        f"Convert one piece of residue from the Java mod (namespace {namespace!r}) to Bedrock.",
        f"Kind: {group.kind}\nSource: {group.source}",
        f"The deterministic converter refused it because:\n{reasons}",
        _source_block(source_root, group.source),
        f"The output tree already holds:\n{_tree_listing(out_tree)}",
        (
            "Write only the files this residue needs, with paths starting "
            "behavior_pack/ or resource_pack/. Do not rewrite manifests. "
            + hint
        ).strip(),
        (
            "Call validate after writing and fix every finding it names. If this "
            "has no faithful Bedrock equivalent, write nothing and say why in one "
            "sentence; that is a correct answer, not a failure."
        ),
    ]
    return "\n\n".join(parts)


class _TrackingToolBox(ToolBox):
    """A ToolBox that remembers what each write replaced, so a group can roll back."""

    def __init__(self, source: Path, out_tree: Path):
        super().__init__(source, out_tree)
        self.originals: dict[str, bytes | None] = {}

    def write_output(self, path: str, content: dict) -> dict:
        target = self._resolve(self.out_tree, path)
        rel = str(target.relative_to(self.out_tree.resolve()))
        if rel not in self.originals:
            self.originals[rel] = target.read_bytes() if target.is_file() else None
        return super().write_output(path, content)

    def rollback(self) -> None:
        for rel, original in self.originals.items():
            target = self.out_tree / rel
            if original is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(original)


@dataclass
class GroupOutcome:
    key: str
    kind: str
    source: str
    status: str  # resolved | partial | unresolved | rolled_back | skipped | error
    stopped: str = ""  # the session's own stop reason: done | budget | error
    steps: int = 0
    written: list[str] = field(default_factory=list)
    note: str = ""
    limit: str | None = None  # the ceiling that stopped it: steps | tokens | cost
    spend: Spend = field(default_factory=Spend)
    tool_calls: int = 0
    format_failures: int = 0  # tool calls that didn't fit the toolbox (#77)

    def to_dict(self) -> dict[str, Any]:
        return {
            "group": self.key,
            "status": self.status,
            "stopped": self.stopped,
            "limit": self.limit,
            "steps": self.steps,
            "written": self.written,
            "spend": self.spend.to_dict(),
            "tool_calls": self.tool_calls,
            "format_failures": self.format_failures,
            "note": self.note,
        }


@dataclass
class ResidueRun:
    outcomes: list[GroupOutcome]
    remaining: list[Unhandled]
    spend: Spend = field(default_factory=Spend)
    budget: Budget = field(default_factory=Budget)

    @property
    def limit(self) -> str | None:
        """The run ceiling that cut work short, if one did: tokens | cost.

        Read off the outcomes rather than the totals: a run whose last group
        finished exactly at the ceiling lost nothing, and should not say it did.
        """
        for outcome in self.outcomes:
            if outcome.limit in ("tokens", "cost"):
                return outcome.limit
        return None

    @property
    def resolved(self) -> list[GroupOutcome]:
        return [o for o in self.outcomes if o.status == "resolved"]

    @property
    def files_written(self) -> int:
        """Files from resolved groups: the ones that count as converted."""
        return sum(len(o.written) for o in self.outcomes if o.status == "resolved")

    @property
    def partial_files(self) -> int:
        """Files kept from groups that did not resolve (out of budget, or a
        provider error after valid writes); their residue stands."""
        return sum(len(o.written) for o in self.outcomes if o.status != "resolved")

    def summary(self) -> dict[str, Any]:
        return {
            "groups": len(self.outcomes),
            "resolved": len(self.resolved),
            "files_written": self.files_written,
            "partial_files": self.partial_files,
            "spend": self.spend.to_dict(),
            "budget": {
                "max_steps_per_group": self.budget.max_steps,
                "max_tokens": self.budget.max_tokens,
                "max_cost_usd": self.budget.max_cost,
            },
            "stopped_by": self.limit,
            "outcomes": [o.to_dict() for o in self.outcomes],
        }


def _final_text(messages) -> str:
    for message in reversed(messages):
        if message.role == "assistant" and message.content and not message.tool_calls:
            return message.content.strip()
    return ""


def _empty_reply_note(messages) -> str:
    """Say why a session ended on a reply with no text and no tool calls.

    Without this the group's note is just "", which reads like a silent
    refusal (#85). The finish reason tells a token cutoff ("length") from a
    content filter or an explicit refusal, and the output token count shows
    whether the model spent its budget thinking without answering.
    """
    last = next((m for m in reversed(messages) if m.role == "assistant"), None)
    if last is None:
        return ""
    if last.refusal:
        return f"model refused: {last.refusal.strip()}"
    details = [f"finish_reason={last.finish_reason or 'unknown'}"]
    if last.usage is not None:
        details.append(f"{last.usage.output_tokens} output tokens")
    return f"model ended with an empty reply ({', '.join(details)})"


class ResidueAgent:
    """Runs the residue through the loop, one session per group."""

    def __init__(
        self,
        client: LLMClient,
        max_steps: int = 12,
        system: str = SYSTEM_PROMPT,
        budget: Budget | None = None,
    ):
        self.client = client
        self.budget = budget or Budget(max_steps=max_steps)
        self.system = system

    def run(
        self,
        source_root: Path,
        out_tree: Path,
        unhandled: list[Unhandled],
        namespace: str,
        meta: ModMetadata | None = None,
    ) -> ResidueRun:
        scaffolded = _scaffold_manifests(out_tree, namespace, meta or ModMetadata())
        outcomes: list[GroupOutcome] = []
        remaining: list[Unhandled] = []
        spent = Spend()
        try:
            for group in group_residue(unhandled):
                outcome = self._run_group(group, source_root, out_tree, namespace, spent)
                outcomes.append(outcome)
                if outcome.status != "resolved":
                    remaining.extend(group.items)
        finally:
            _remove_empty_scaffolds(out_tree, scaffolded)
        return ResidueRun(outcomes, remaining, spent, self.budget)

    def _run_group(
        self,
        group: ResidueGroup,
        source_root: Path,
        out_tree: Path,
        namespace: str,
        spent: Spend,
    ) -> GroupOutcome:
        outcome = GroupOutcome(group.key, group.kind, group.source, "skipped")
        if group.kind in SKIP_KINDS:
            outcome.note = SKIP_KINDS[group.kind]
            return outcome
        limit = self.budget.exhausted(spent)
        if limit:
            outcome.stopped, outcome.limit = "budget", limit
            outcome.note = f"the run's {limit} ceiling was reached before this group started"
            return outcome

        before = _error_set(out_tree)
        box = _TrackingToolBox(source_root, out_tree)
        session = AgentSession(
            self.client, box, self.system, budget=self.budget, run_spend=spent
        )
        task = build_task(group, source_root, out_tree, namespace)
        try:
            result = session.run(task)
            outcome.stopped, outcome.steps, outcome.limit = result.stopped, result.steps, result.limit
            outcome.tool_calls, outcome.format_failures = result.tool_calls, result.format_failures
            outcome.note = _final_text(result.messages)
            if result.stopped == "done" and not outcome.note:
                outcome.note = _empty_reply_note(result.messages)
            if result.stopped == "budget" and not outcome.note:
                outcome.note = f"stopped at the {result.limit} ceiling"
        except Exception as exc:  # a provider failure ends this group, not the run
            outcome.stopped = "error"
            outcome.steps = session.spend.steps
            outcome.tool_calls, outcome.format_failures = session.tool_calls, session.format_failures
            outcome.note = f"{type(exc).__name__}: {exc}"
        outcome.spend = session.spend

        outcome.written = sorted(box.originals)
        # Judged against the tree as the session found it: a group is rolled back
        # for errors it introduced, never for ones the deterministic path left.
        if box.originals and _error_set(out_tree) - before:
            box.rollback()
            outcome.status = "rolled_back"
            outcome.written = []
        elif outcome.stopped == "done" and box.originals:
            outcome.status = "resolved"
        elif outcome.stopped == "budget" and box.originals:
            # Out of budget mid-task: what it wrote validates, so it stays on
            # disk for the next run or a human, but the residue is not cleared.
            outcome.status = "partial"
        elif outcome.stopped == "error":
            outcome.status = "error"
        else:
            outcome.status = "unresolved"
        return outcome


def _error_set(out_tree: Path) -> set[tuple[str, str, str]]:
    return {(f.path, f.rule, f.message) for f in validate_tree(out_tree).errors}


def _scaffold_manifests(out_tree: Path, namespace: str, meta: ModMetadata) -> list[Path]:
    """Give the agent both packs to write into without letting it author manifests.

    Manifest UUIDs are derived deterministically from the mod; a model inventing
    one would break pack updates. A scaffold that ends up holding nothing but
    its manifest is removed again afterwards.
    """
    floor = ENGINE_FLOOR
    for pack in ("resource_pack", "behavior_pack"):
        existing = out_tree / pack / "manifest.json"
        if existing.is_file():
            try:
                version = json.loads(existing.read_text())["header"]["min_engine_version"]
                floor = max(floor, tuple(int(v) for v in version))
            except (KeyError, TypeError, ValueError):
                pass
    had_resource = (out_tree / "resource_pack" / "manifest.json").is_file()
    created: list[Path] = []
    for pack, kind in (("resource_pack", "resource"), ("behavior_pack", "behavior")):
        base = out_tree / pack
        if (base / "manifest.json").is_file():
            continue
        # Only depend on a resource pack that will still be there afterwards.
        depends = ("resource",) if kind == "behavior" and had_resource else ()
        base.mkdir(parents=True, exist_ok=True)
        (base / "manifest.json").write_text(
            json.dumps(manifest(namespace, kind, meta, depends, floor), indent=2) + "\n"
        )
        created.append(base)
    return created


def _remove_empty_scaffolds(out_tree: Path, scaffolded: list[Path]) -> None:
    for base in scaffolded:
        contents = [p for p in base.rglob("*") if p.is_file()]
        if all(p.name == "manifest.json" and p.parent == base for p in contents):
            shutil.rmtree(base)
