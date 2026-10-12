"""Java item tags, resolved against what a Bedrock addon of this mod can hold.

A Bedrock addon carries this mod's items and vanilla's, nothing from other
mods. So a tag that only this mod and vanilla can fill often means exactly one
item once it lands on Bedrock, and a recipe that names it can name that item.

A tag's membership is the union of everyone who writes to it:

1. The mod's own tag file (``data/<ns>/tags/items/<path>.json``, or ``item/``
   since 1.21). Other mods' entries are dropped because the addon cannot
   contain them.
2. For a tag in a shared namespace (``minecraft:``, ``c:``, ``forge:``,
   ``neoforge:``, ``fabric:``), vanilla's and the loader's shares, from the
   fetched reference data for the jar's loader and game version
   (:mod:`portkit.data.tags`, #160). The mod's file there is only its own share
   (Forge's ``forge:glass/colorless`` is ``minecraft:glass``, which a mod's
   one-line file for the same tag doesn't repeat), so without the reference
   the membership is unknown and the recipe stays residue rather than being
   narrowed to the mod's share. A file that sets ``"replace": true`` is the
   whole tag on its own.
3. No tag file and no known share: the convention-tag name (``c:ingots/steel``).
   If exactly one of this mod's items carries the conventional name
   (``steel_ingot``), that is the only item the tag can mean on Bedrock.

Nested ``#tag`` entries are resolved the same way, recursively. Anything that
still leaves more than one item stays residue for :meth:`TagResolver.resolve`,
and the reason lists the members, so the agent starts from the membership
instead of the bare tag name (#88). :meth:`TagResolver.members` gives the full
membership to the recipe converter, which can express some multi-member tags.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..data import FETCH_COMMAND
from ..data.tags import SHARED_NAMESPACES, TagReference, reference_for
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


@dataclass
class MultiMembers:
    """Every member a tag names, when all of them are known (see TagResolver.members)."""

    tag: str
    members: list[str]  # vanilla ids and ids in the converted namespace, in file order
    dropped: list[str] = field(default_factory=list)  # other mods' ids the addon cannot contain
    sources: list[str] = field(default_factory=list)  # tag files read, mod-relative


@dataclass
class _Membership:
    """A tag's full membership, nested tags expanded."""

    members: list[str]
    sources: list[str]  # the mod's own tag files read
    dropped_tags: list[str]  # other mods' nested tags, whose members the addon can't hold
    reference: bool  # vanilla's or the loader's share came from the reference data


@dataclass
class _NotKnown:
    """Why a tag's full membership isn't known, and the tag files read finding out."""

    reason: str
    sources: list[str]


class _Unknown(Exception):
    """Some part of the membership isn't known; carries why."""


def _is_shared(tag: str) -> bool:
    return tag.partition(":")[0] in SHARED_NAMESPACES


class TagResolver:
    def __init__(self, mod: SourceMod, reference: TagReference | None = None):
        self.mod = mod
        self.reference = reference if reference is not None else reference_for(mod.loader, mod.minecraft)
        self._items: set[str] | None = None
        self._shipped: set[str] | None = None
        self._cache: dict[str, TagResolution] = {}
        self._full_cache: dict[str, _Membership | _NotKnown] = {}

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

    def _shipped_namespaces(self) -> set[str]:
        """Namespaces this jar ships, which the pack may also convert."""
        if self._shipped is None:
            found: set[str] = set()
            for top in ("assets", "data"):
                folder = self.mod.root / top
                if folder.is_dir():
                    found |= {p.name for p in folder.iterdir() if p.is_dir()}
            self._shipped = found
        return self._shipped

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

    def _unknown_shared(self, tag: str) -> str:
        """Why a shared tag's membership is unknown (no reference covers it)."""
        ns = tag.partition(":")[0]
        missing = [s for s in self.reference.missing if ns in s.namespaces]
        if missing:
            return (f"vanilla and the loader add to {ns}: tags, and the {missing[0].label} "
                    f"tag data isn't cached (run `{FETCH_COMMAND}`)")
        if self.mod.loader is None or self.mod.minecraft is None:
            return (f"vanilla and the loader add to {ns}: tags, and the jar doesn't declare "
                    "the loader and game version whose tag data would say what they add")
        return (f"vanilla and the loader add to {ns}: tags, and there is no {ns}: tag data "
                f"for {self.mod.loader} {self.mod.minecraft}")

    def _entries(self, tag: str, sources: list[str]) -> tuple[list, bool]:
        """(raw entries, from reference?) for one tag; raises _Unknown."""
        path = self._tag_file(tag)
        entries: list = []
        replace = False
        if path is not None:
            try:
                data = json.loads(path.read_text())
            except json.JSONDecodeError as exc:
                raise _Unknown(f"its tag file is not valid JSON ({exc})") from exc
            if not isinstance(data, dict):
                raise _Unknown("its tag file is not a JSON object")
            sources.append(str(path.relative_to(self.mod.root)))
            entries.extend(data.get("values") or [])
            replace = data.get("replace") is True
        if not _is_shared(tag) or replace:
            if path is None:
                raise _Unknown("the mod ships no tag file for it")
            return entries, False
        share = self.reference.values(tag)
        if share is None:
            raise _Unknown(self._unknown_shared(tag))
        return entries + share, True

    def _expand(self, tag: str, seen: set[str], sources: list[str],
                dropped_tags: list[str]) -> tuple[list[str], bool]:
        entries, from_ref = self._entries(tag, sources)
        members: list[str] = []
        for entry in entries:
            ref = entry.get("id") if isinstance(entry, dict) else entry
            if not isinstance(ref, str):
                continue
            if not ref.startswith("#"):
                if ref not in members:
                    members.append(ref)
                continue
            inner = ref[1:]
            if inner in seen:
                continue
            seen.add(inner)
            ns = inner.partition(":")[0]
            if not _is_shared(inner) and ns != self.mod.namespace and ns not in self._shipped_namespaces():
                # Another mod's tag: its members are that mod's, which the addon
                # can't hold, same as another mod's item entry.
                dropped_tags.append(ref)
                continue
            try:
                nested, nested_ref = self._expand(inner, seen, sources, dropped_tags)
            except _Unknown as exc:
                raise _Unknown(f"it includes {ref}, whose membership isn't known: {exc}") from exc
            from_ref = from_ref or nested_ref
            members.extend(m for m in nested if m not in members)
        return members, from_ref

    def _full(self, tag: str) -> _Membership | _NotKnown:
        """The tag's full membership, or why it isn't known."""
        if tag not in self._full_cache:
            sources: list[str] = []
            dropped: list[str] = []
            try:
                members, from_ref = self._expand(tag, {tag}, sources, dropped)
                self._full_cache[tag] = _Membership(members, sources, dropped, from_ref)
            except _Unknown as exc:
                self._full_cache[tag] = _NotKnown(str(exc), sources)
        return self._full_cache[tag]

    def own_share(self, tag: str) -> list[str]:
        """This mod's own available items its jar adds to a tag (direct entries)."""
        path = self._tag_file(tag)
        if path is None:
            return []
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            return []
        found = []
        for entry in (data.get("values") or []) if isinstance(data, dict) else []:
            ref = entry.get("id") if isinstance(entry, dict) else entry
            if isinstance(ref, str) and ref.startswith(f"{self.mod.namespace}:") and self._available(ref):
                found.append(ref)
        return found

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

    # -- full membership, for recipes that keep every member (#160) --------
    def members(self, tag: str) -> MultiMembers | None:
        """The full membership of a tag, or None unless all of it is known.

        Stricter than :meth:`resolve`, because here every member ends up in the
        recipe. Members in a namespace this jar ships but that is not the one
        being converted make it unknown too, since the pack may convert them
        under another namespace. Only members from mods this jar does not ship
        are dropped, as :meth:`resolve` does: the addon cannot contain them.
        """
        full = self._full(tag)
        if isinstance(full, _NotKnown):
            return None
        shipped = self._shipped_namespaces()
        kept: list[str] = []
        dropped: list[str] = list(full.dropped_tags)
        for ref in full.members:
            ns, _, name = ref.partition(":")
            if not name:
                return None
            if ns == "minecraft" or ns == self.mod.namespace:
                kept.append(ref)
            elif ns in shipped:
                return None
            else:
                dropped.append(ref)
        return MultiMembers(tag=tag, members=kept, dropped=dropped, sources=list(full.sources))

    def unknown_reason(self, tag: str) -> str | None:
        """Why the tag's full membership is unknown, or None when it is known."""
        full = self._full(tag)
        return full.reason if isinstance(full, _NotKnown) else None

    # -- the one call recipes make ----------------------------------------
    def resolve(self, tag: str) -> TagResolution:
        if tag not in self._cache:
            self._cache[tag] = self._resolve(tag)
        return self._cache[tag]

    def _origin(self, full: _Membership) -> str:
        parts = list(full.sources[:1])
        if full.reference:
            parts.append(f"the {self.reference.describe()} tag data")
        return " and ".join(parts) or "nothing"

    def _resolve(self, tag: str) -> TagResolution:
        full = self._full(tag)
        if isinstance(full, _Membership):
            usable = [m for m in full.members if self._available(m)]
            dropped = [m for m in full.members if m not in usable] + full.dropped_tags
            if len(usable) == 1:
                tail = f"; dropped {', '.join(dropped)}, which this addon cannot contain" if dropped else ""
                return TagResolution(
                    item=usable[0],
                    note=f"tag {tag!r} resolved to {usable[0]} from {self._origin(full)}{tail}",
                    sources=full.sources,
                )
            if len(usable) > 1:
                return TagResolution(
                    reason=f"ingredient uses tag {tag!r}, which covers {len(usable)} items: {', '.join(usable)}",
                    sources=full.sources,
                )
        has_file = self._tag_file(tag) is not None
        item = None if has_file else self._by_convention(tag)
        if item:
            return TagResolution(
                item=item,
                note=(
                    f"tag {tag!r} resolved to {item}: the mod ships no tag file, and {item} "
                    "is the only item in this addon with the conventional name"
                ),
            )
        if isinstance(full, _Membership) and not (full.members or full.dropped_tags):
            return TagResolution(
                reason=(f"ingredient uses tag {tag!r}, which nothing in this addon is in: neither "
                        "this mod, the loader nor vanilla adds a member to it, only other mods"),
                sources=full.sources,
            )
        if isinstance(full, _Membership):
            listed = ", ".join([*full.members, *full.dropped_tags])
            return TagResolution(
                reason=f"ingredient uses tag {tag!r}, whose members ({listed}) are none of them in this addon",
                sources=full.sources,
            )
        if not has_file:
            # Said only when the jar declares its loader and version, so the
            # reason can point at the data that would settle it.
            tail = (f" ({full.reason})"
                    if _is_shared(tag) and self.mod.loader and self.mod.minecraft else "")
            return TagResolution(
                reason=f"ingredient uses tag {tag!r}, which covers more than one item{tail}",
                sources=full.sources,
            )
        return TagResolution(
            reason=(f"ingredient uses tag {tag!r}, whose full membership isn't known (the mod's "
                    f"file is only its own share): {full.reason}") if _is_shared(tag) and "includes #" not in full.reason
            else f"ingredient uses tag {tag!r}, whose full membership isn't known: {full.reason}",
            sources=full.sources,
        )
