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
    """

    source: str
    kind: str
    reason: str


@dataclass
class ConversionResult:
    """What one converter produced."""

    files: dict[str, Any] = field(default_factory=dict)  # relpath -> json-able or bytes
    unhandled: list[Unhandled] = field(default_factory=list)

    def merge(self, other: "ConversionResult") -> "ConversionResult":
        merged = ConversionResult(dict(self.files), list(self.unhandled))
        merged.files.update(other.files)
        merged.unhandled.extend(other.unhandled)
        return merged
