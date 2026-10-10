"""Java item tags, resolved against what a Bedrock addon of this mod can hold.

A Bedrock addon carries this mod's items and vanilla's, nothing from other
mods. So a tag that only this mod and vanilla can fill often means exactly one
item once it lands on Bedrock, and a recipe that names it can name that item.
Two sources, in order of trust:

1. The mod's own tag file (``data/<ns>/tags/items/<path>.json``, or ``item/``
   since 1.21). Its members are the membership. Other mods' entries are
   dropped because the addon cannot contain them.
2. No tag file: the convention-tag name (``c:ingots/steel``). If exactly one of
   this mod's items carries the conventional name (``steel_ingot``), that is the
   only item the tag can mean on Bedrock.

Anything that still leaves more than one item stays residue, and the reason
lists the members, so the agent starts from the membership instead of the
bare tag name (#88).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..model import SourceMod

_CONVENTION_PREFIXES = ("c:", "forge:", "neoforge:")

# Convention tag folder -> how the member item is usually named.
_CONVENTION_NAMES = {
    "ingots": "{m}_ingot",
    "nuggets": "{m}_nugget",
    "dusts": "{m}_dust",
    "plates": "{m}_plate",
    "gears": "{m}_gear",
    "rods": "{m}_rod",
    "gems": "{m}",
    "storage_blocks": "{m}_block",
    "raw_materials": "raw_{m}",
}


@dataclass
class TagResolution:
    item: str | None = None  # the one item the tag means, when there is one
    reason: str = ""  # why not, when there is not
    note: str = ""  # how it was decided, for the report
    sources: list[str] = field(default_factory=list)  # tag files read, mod-relative


class TagResolver:
    def __init__(self, mod: SourceMod):
        self.mod = mod
        self._items: set[str] | None = None
        self._cache: dict[str, TagResolution] = {}

    # -- what the addon can contain --------------------------------------
    def mod_items(self) -> set[str]:
        """Names of this mod's items and blocks, from their model/blockstate files."""
        if self._items is None:
            names: set[str] = set()
            for sub in ("models/item", "blockstates"):
                folder = self.mod.assets / sub
                if folder.is_dir():
                    names |= {p.stem for p in folder.glob("*.json")}
            self._items = names
        return self._items

    def _available(self, item: str) -> bool:
        ns, _, name = item.partition(":")
        if ns == "minecraft":
            return True
        return ns == self.mod.namespace and name in self.mod_items()

    # -- tag files -------------------------------------------------------
    def _tag_file(self, tag: str) -> Path | None:
        ns, _, path = tag.partition(":")
        if not path:
            return None
        for folder in ("items", "item"):
            candidate = self.mod.root / "data" / ns / "tags" / folder / f"{path}.json"
            if candidate.is_file():
                return candidate
        return None

    def _members(self, tag: str, seen: set[str], sources: list[str]) -> list[str] | None:
        """Every item the tag lists, nested tags expanded; None when unknown.

        A mod's file for a ``minecraft:`` tag only adds to vanilla's own list,
        which is not in the mod, so it says nothing about the full membership
        unless it sets ``"replace": true``. Those count as unknown.
        """
        path = self._tag_file(tag)
        if path is None:
            return None
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            data = {}
        if tag.startswith("minecraft:") and not (isinstance(data, dict) and data.get("replace")):
            return None
        sources.append(str(path.relative_to(self.mod.root)))
        members: list[str] = []
        for entry in data.get("values", []) if isinstance(data, dict) else []:
            ref = entry.get("id") if isinstance(entry, dict) else entry
            if not isinstance(ref, str):
                continue
            if ref.startswith("#"):
                inner = ref[1:]
                if inner in seen:
                    continue
                seen.add(inner)
                nested = self._members(inner, seen, sources)
                members.extend(nested or [])
            elif ref not in members:
                members.append(ref)
        return members

    def _by_convention(self, tag: str) -> str | None:
        for prefix in _CONVENTION_PREFIXES:
            if tag.startswith(prefix):
                kind, _, material = tag[len(prefix):].partition("/")
                pattern = _CONVENTION_NAMES.get(kind)
                if pattern and material and "/" not in material:
                    name = pattern.format(m=material)
                    if name in self.mod_items():
                        return f"{self.mod.namespace}:{name}"
        return None

    def resolved(self) -> dict[str, TagResolution]:
        """Every tag looked up so far."""
        return dict(self._cache)

    # -- the one call recipes make ----------------------------------------
    def resolve(self, tag: str) -> TagResolution:
        if tag not in self._cache:
            self._cache[tag] = self._resolve(tag)
        return self._cache[tag]

    def _resolve(self, tag: str) -> TagResolution:
        sources: list[str] = []
        members = self._members(tag, {tag}, sources)
        if members is not None:
            usable = [m for m in members if self._available(m)]
            dropped = [m for m in members if m not in usable]
            if len(usable) == 1:
                tail = f"; dropped {', '.join(dropped)}, which this addon cannot contain" if dropped else ""
                return TagResolution(
                    item=usable[0],
                    note=f"tag {tag!r} resolved to {usable[0]} from {sources[0]}{tail}",
                    sources=sources,
                )
            if not usable:
                listed = ", ".join(members) or "nothing"
                return TagResolution(
                    reason=f"ingredient uses tag {tag!r}, whose members ({listed}) are none of them in this addon",
                    sources=sources,
                )
            return TagResolution(
                reason=f"ingredient uses tag {tag!r}, which covers {len(usable)} items: {', '.join(usable)}",
                sources=sources,
            )
        item = self._by_convention(tag)
        if item:
            return TagResolution(
                item=item,
                note=(
                    f"tag {tag!r} resolved to {item}: the mod ships no tag file, and {item} "
                    "is the only item in this addon with the conventional name"
                ),
            )
        return TagResolution(
            reason=f"ingredient uses tag {tag!r}, which covers more than one item"
        )
