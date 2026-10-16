"""Shared types. Deliberately tiny and stdlib-only."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Files several converters of one namespace may each contribute to; merge adds
# them up instead of treating the second write as a collision (#129).
_TEXTURE_INDEXES = ("textures/item_texture.json", "textures/terrain_texture.json")
_LANGUAGES = "texts/languages.json"


def _is_lang(path: str) -> bool:
    return path.startswith("texts/") and path.endswith(".lang")


@dataclass
class SourceMod:
    """A parsed Java mod on disk."""

    root: Path
    namespace: str
    # What the jar's metadata declares, when known: which loader's and which
    # game version's tag data completes its shared tags (#160).
    loader: str | None = None
    minecraft: str | None = None
    # Every mod id the jar's metadata declares, with its version, and the mods
    # it declares as required (Java can't load it without them); None without
    # metadata. Load conditions are decided against them (#183).
    mods: dict[str, str] | None = None
    requires: frozenset[str] | None = None
    # The jar's compiled classes (portkit.bytecode.ClassIndex), or None when
    # the source has none to offer: what a block's code says is then unknown.
    classes: Any = field(default=None, compare=False, repr=False)

    @classmethod
    def from_metadata(cls, root: Path, namespace: str, meta, classes=None) -> "SourceMod":
        """The mod one namespace of a staged jar stands for, under its metadata.

        One construction for the converters (``pipeline.convert``) and the
        residue agent's guards, so both decide load conditions and config
        gating against the same declared mods (#183, #185).
        """
        requires = getattr(meta, "requires", None)
        return cls(root=root, namespace=namespace, loader=getattr(meta, "loader", None),
                   minecraft=getattr(meta, "minecraft", None), mods=getattr(meta, "mods", None),
                   requires=frozenset(requires) if requires is not None else None, classes=classes)

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


def _declared(value: Any) -> str | None:
    """The identifier a definition file declares (``{"minecraft:item": {"description": ...}}``)."""
    if not isinstance(value, dict):
        return None
    for body in value.values():
        description = body.get("description") if isinstance(body, dict) else None
        if isinstance(description, dict) and isinstance(description.get("identifier"), str):
            return description["identifier"]
    return None


@dataclass
class ConversionResult:
    """What one converter produced."""

    files: dict[str, Any] = field(default_factory=dict)  # relpath -> json-able or bytes
    unhandled: list[Unhandled] = field(default_factory=list)
    # Source paths (relative to the mod root) this converter looked at, whether
    # it converted them or refused them. Anything left over at the end of the
    # run was seen by nobody, which is the one outcome we never allow silently.
    consumed: set[str] = field(default_factory=set)
    # Reductions: something converted, but with a detail Bedrock cannot carry.
    # Deliberately not residue. Residue is a file an agent can go and work on;
    # a note is a file that shipped with something lost, and it still cannot go
    # unsaid.
    notes: list[str] = field(default_factory=list)
    # Station runtimes (#177): recipe type -> what its data table holds
    # ({"converted": n, "residue": m, "data": path, "block": id}).
    stations: dict[str, dict] = field(default_factory=dict)
    # Recipe output path -> the source recipe it was written from (#261), so a
    # recipe withdrawn after every namespace converted goes back to residue
    # under its own source.
    recipe_sources: dict[str, str] = field(default_factory=dict)

    def claim(self, mod: "SourceMod", path: Path) -> str:
        """Record a source file as looked at and return its relative path."""
        rel = str(path.relative_to(mod.root))
        self.consumed.add(rel)
        return rel

    def merge(self, other: "ConversionResult") -> "ConversionResult":
        """This result followed by ``other`` (a later converter of the same namespace).

        A later converter may rewrite an earlier one's definition (recipes give
        an item its ``minecraft:tags``), so a path both write is taken from
        ``other`` when both declare the same identifier. Any other second
        write to one path keeps the first and is residue (#163): one output
        silently replacing another is the failure this project refuses.
        """
        merged = ConversionResult(dict(self.files), list(self.unhandled), set(self.consumed))
        for path, value in other.files.items():
            first = merged.files.get(path)
            if path in _TEXTURE_INDEXES and isinstance(first, dict) and isinstance(value, dict):
                # Two converters adding keys to one texture index (the textures
                # converter and an adapter's pre-baked icons, #129) add up. A key
                # both define keeps the first: nothing re-points a texture.
                combined = dict(first)
                combined["texture_data"] = {
                    **(value.get("texture_data") or {}),
                    **(first.get("texture_data") or {}),
                }
                merged.files[path] = combined
                continue
            if _is_lang(path) and isinstance(first, str) and isinstance(value, str):
                # Two converters naming things in one locale (the lang converter
                # and an adapter's item names, #129): one file, every line,
                # sorted as the lang converter sorts. A key both define keeps
                # the first converter's line.
                lines = {}
                for text in (value, first):
                    for line in text.splitlines():
                        key, sep, _ = line.partition("=")
                        if sep:
                            lines[key] = line
                merged.files[path] = "".join(f"{line}\n" for line in sorted(lines.values()))
                continue
            if path == _LANGUAGES and isinstance(first, list) and isinstance(value, list):
                both = set(first) | set(value)
                merged.files[path] = (["en_US"] if "en_US" in both else []) + sorted(both - {"en_US"})
                continue
            if path in merged.files and first != value:
                was, now = _declared(first), _declared(value)
                if was is None or was != now:
                    merged.unhandled.append(Unhandled(
                        path, "output_collision",
                        f"two converters wrote {path} ({was or 'no identifier'} and "
                        f"{now or 'no identifier'}); kept the first",
                    ))
                    continue
            merged.files[path] = value
        merged.unhandled.extend(other.unhandled)
        merged.consumed |= other.consumed
        merged.notes = [*self.notes, *other.notes]
        merged.stations = {**self.stations, **other.stations}
        merged.recipe_sources = {**other.recipe_sources, **self.recipe_sources}
        return merged

    @property
    def residue_count(self) -> int:
        """How many source files the residue stands for."""
        return sum(u.count for u in self.unhandled)
