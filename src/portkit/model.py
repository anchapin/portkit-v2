"""Shared types. Deliberately tiny and stdlib-only."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SourceMod:
    """A parsed Java mod on disk."""

    root: Path
    namespace: str

    @property
    def assets(self) -> Path:
        return self.root / "assets" / self.namespace

    @property
    def data(self) -> Path:
        return self.root / "data" / self.namespace


@dataclass
class Unhandled:
    """Something a deterministic converter refused to guess at.

    This is the ONLY input the agent loop is allowed to work on.

    ``count`` is how many source files the entry stands for. It is 1 for a
    single refused file and N for a grouped entry, so coverage arithmetic can
    weigh one entry covering 300 models against one covering a single recipe.
    """

    source: str
    kind: str
    reason: str
    count: int = 1


@dataclass
class ConversionResult:
    """What one converter produced."""

    files: dict[str, Any] = field(default_factory=dict)  # relpath -> json-able or bytes
    unhandled: list[Unhandled] = field(default_factory=list)
    # Source paths (relative to the mod root) this converter looked at, whether
    # it converted them or refused them. Anything left over at the end of the
    # run was seen by nobody, which is the one outcome we never allow silently.
    consumed: set[str] = field(default_factory=set)

    def claim(self, mod: "SourceMod", path: Path) -> str:
        """Record a source file as looked at and return its relative path."""
        rel = str(path.relative_to(mod.root))
        self.consumed.add(rel)
        return rel

    def merge(self, other: "ConversionResult") -> "ConversionResult":
        merged = ConversionResult(dict(self.files), list(self.unhandled), set(self.consumed))
        merged.files.update(other.files)
        merged.unhandled.extend(other.unhandled)
        merged.consumed |= other.consumed
        return merged

    @property
    def residue_count(self) -> int:
        """How many source files the residue stands for."""
        return sum(u.count for u in self.unhandled)
