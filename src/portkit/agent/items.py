"""Is every item the agent defines one the Java mod registers? (#86)

On real-mod residue GLM 5.3 wrote per-variant item definitions: storage
drawers 1.12.2 got ``items/basicdrawers_full2_jungle.json`` and its siblings,
and waystones got nine per-variant items. Java registers *one* item for those
(``storagedrawers:basicdrawers``) and carries the variant (wood, size, colour)
in block state, metadata or NBT. The per-variant names come from item *model*
files (a 1.12 mod ships one model per metadata variant; a modern mod ships
override models such as ``twinbound_feather_brushing_0``), which are not
registrations. The files validated, so the group counted as resolved while the
pack gained items no Java player can hold. None of the other guards look at a
definition's own identifier.

So the residue agent holds the items it defines to a deterministic rule, in
the spirit of :mod:`portkit.agent.refs`, :mod:`portkit.agent.states` and
:mod:`portkit.agent.trim`. Every ``minecraft:item`` the session writes (either
pack) whose ``description.identifier`` is in a source-mod namespace or the
conversion's namespace must be the Bedrock id, under the converter's own
mapping (:func:`portkit.converters.items.bedrock_identifier`), of a Java id the
source *registers*. The registered set is what the deterministic core already
reads, minus item models (:func:`portkit.registry.registered_ids`, which the
item converter applies to its own output too since #158):

- a blockstate (a block, and the block item Java gives it);
- a lang key (``item.<ns>.<name>`` / ``block.<ns>.<name>`` in a JSON lang
  file; in a 1.12 ``.lang`` file, ``item.<ns>.<key>.name`` /
  ``tile.<ns>.<key>.name`` with the camelCase key in lower or snake case);
- an item a recipe, an item tag or a loot table names, or a block loot table.

A Bedrock id may also be the conversion namespace with a registered Java path
(the converter's mapping under the pack's namespace), and an id an item or
block the deterministic output already defines (outside the session's files)
passes too. ``minecraft:`` ids are out of scope, and a namespace the mod does
not have is :func:`portkit.agent.refs.unknown_namespace_refs`' to report. An
identifier the file already held before the session is not the session's.

If a written item violates the rule, :func:`finding` produces an
``agent.unknown_item`` validate error naming the closest real Java id, and
:func:`unknown_items` is the list the residue agent rolls the group back for.

Config-gated items (#187)
-------------------------
Some ids the source names are registered by the mod's code only while a config
flag is on: a cited ``registers`` pattern in
``portkit/data/config_flag_defaults.json``, such as Mythic Metals'
``mythicmetals:*_dust`` under ``enableDusts`` (default off). The item converter
leaves those out (``conditional_item`` residue) under the conversion's
effective config: each flag's cited default, replaced by the user's
``portkit convert --config`` setting. The agent is held to the same config,
decided by the same code (:meth:`portkit.conditions.LoadContext.gated_item`,
passed in as ``gate``): :func:`gated_ids` maps every gated-off Java id to its
Bedrock id, an item defined under one is ``agent.unknown_item`` with a message
naming the flag and the setting that turns it on, and :func:`gated_refs` finds
any other mention of one (a recipe input or output, a loot entry, any id in a
written JSON file or lang key), which :func:`gated_finding` reports as
``agent.gated_item``. With the flag on (by default or by ``--config``) the
items are registered and pass.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ..conditions import Verdict
from ..converters.items import bedrock_identifier
from ..registry import _load, closest_id, registered_ids
from .refs import _VANILLA, Ref, _file_ids, valid_namespaces

__all__ = [
    "GatedItem",
    "UnknownItem",
    "bedrock_ids",
    "closest_id",
    "finding",
    "gated_finding",
    "gated_ids",
    "gated_refs",
    "registered_ids",
    "unknown_items",
]


# Whether the mod's code registers a Java id, when a config flag decides it:
# LoadContext.gated_item (None when no cited pattern names the id).
Gate = Callable[[str], Optional[Verdict]]


@dataclass(frozen=True)
class GatedItem:
    """A Java id the mod registers only under a config flag that is off here."""

    java: str  # the Java id, e.g. mythicmetals:tin_dust
    flag: str  # the deciding flag, "<condition>" or "<condition>/<flag>"
    reason: str  # the verdict's reason: "disabled by default config: ..." or "... user config ..."
    enable: str  # the --config setting that turns it on, e.g. mythicmetals.enableDusts=true

    def explain(self) -> str:
        return (f"item gated off by config flag {self.flag} ({self.reason}); "
                f"enable with --config {self.enable}")


@dataclass(frozen=True)
class UnknownItem:
    path: str  # the pack file that defines it, relative to the output tree
    ident: str  # the identifier the file gives the item
    closest: str | None  # the nearest id the Java source registers, if any
    gated: GatedItem | None = None  # set when Java registers it only under a flag that is off

    def describe(self) -> str:
        if self.gated is not None:
            return f"{self.path}: item {self.ident!r} ({self.gated.explain()})"
        hint = f" (closest Java id {self.closest!r})" if self.closest else ""
        return f"{self.path}: item {self.ident!r}{hint}"


# -- what Java registers: portkit.registry, shared with the converter ---


def bedrock_ids(java_ids: set[str], namespace: str | None) -> set[str]:
    """The Bedrock ids the converter's mapping gives the registered Java ids."""
    out: set[str] = set()
    for ident in java_ids:
        ns, path = ident.split(":", 1)
        out.add(bedrock_identifier(ns, path))
        if namespace:
            out.add(bedrock_identifier(namespace, path))
    return out


def gated_ids(java_ids: set[str], gate: Gate | None, namespace: str | None) -> dict[str, GatedItem]:
    """Bedrock id -> :class:`GatedItem` for every Java id the config gates off.

    ``gate`` is the conversion's :meth:`LoadContext.gated_item`, so the agent
    and the item converter decide gating with one piece of code and one config.
    """
    if gate is None:
        return {}
    out: dict[str, GatedItem] = {}
    for ident in sorted(java_ids):
        if ":" not in ident:
            continue
        verdict = gate(ident)
        if verdict is None or verdict.passes is True:
            continue
        flag = verdict.gate or next(iter(verdict.user_disabled or verdict.disabled or verdict.unknown), "")
        item = GatedItem(ident, flag, verdict.reason(), verdict.enable)
        ns, path = ident.split(":", 1)
        out.setdefault(bedrock_identifier(ns, path), item)
        if namespace:
            out.setdefault(bedrock_identifier(namespace, path), item)
    return out


# -- what the session wrote ----------------------------------------------

def _item_identifier(data) -> str | None:
    if not isinstance(data, dict) or not isinstance(data.get("minecraft:item"), dict):
        return None
    desc = data["minecraft:item"].get("description")
    ident = desc.get("identifier") if isinstance(desc, dict) else None
    return ident if isinstance(ident, str) else None


def _parse(raw: bytes | None):
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8-sig", errors="replace"))
    except json.JSONDecodeError:
        return None


def _pack_defined(out_tree: Path, exclude: set[str]) -> set[str]:
    """Items and blocks the pack defines in files the session did not write."""
    found: set[str] = set()
    for pack in ("behavior_pack", "resource_pack"):
        for folder, kind in (("items", "minecraft:item"), ("blocks", "minecraft:block")):
            base = out_tree / pack / folder
            for path in sorted(base.rglob("*.json")) if base.is_dir() else []:
                rel = path.relative_to(out_tree).as_posix()
                if rel in exclude:
                    continue
                data = _load(path)
                if isinstance(data, dict) and isinstance(data.get(kind), dict):
                    ident = (data[kind].get("description") or {}).get("identifier")
                    if isinstance(ident, str):
                        found.add(ident)
    return found


def unknown_items(
    out_tree: Path,
    written: list[str],
    source_root: Path,
    namespace: str | None = None,
    originals: dict[str, bytes | None] | None = None,
    *,
    gated: dict[str, GatedItem] | None = None,
    _registered: set[str] | None = None,
) -> list[UnknownItem]:
    """Items the session defined whose id the Java source never registers.

    ``gated`` is :func:`gated_ids` under the conversion's config: those ids
    are not registered here even though the source names them (#187).
    ``_registered`` is :func:`registered_ids` for ``source_root`` when the
    caller already has it (the source does not change mid-session).
    """
    gated = gated or {}
    normalised = sorted({rel.replace("\\", "/") for rel in written})
    targets = [
        rel for rel in normalised
        if rel.startswith(("behavior_pack/", "resource_pack/")) and rel.endswith(".json")
        and (out_tree / rel).is_file()
    ]
    if not targets:
        return []
    originals = {k.replace("\\", "/"): v for k, v in (originals or {}).items()}
    checked = valid_namespaces(source_root, namespace) - {_VANILLA}
    java = _registered
    allowed: set[str] | None = None  # built on the first item that needs it
    defined: set[str] = set()  # ...and what the pack defines outside the session
    bad: list[UnknownItem] = []
    for rel in targets:
        ident = _item_identifier(_load(out_tree / rel))
        if ident is None or ":" not in ident:
            continue
        if ident.split(":", 1)[0] not in checked:
            continue  # vanilla is out of scope; a foreign namespace is refs.py's
        if ident == _item_identifier(_parse(originals.get(rel))):
            continue  # the file already defined it before the session
        if allowed is None:
            if java is None:
                java = registered_ids(source_root)
            off = {g.java for g in gated.values()}
            defined = _pack_defined(out_tree, set(normalised))
            allowed = bedrock_ids(java - off, namespace) | defined
        if ident in gated and ident not in defined:
            # Checked first: another namespace's id with the same path (mapped
            # under the conversion namespace) must not let a gated one through.
            bad.append(UnknownItem(rel, ident, gated[ident].java, gated[ident]))
            continue
        if ident in allowed:
            continue
        bad.append(UnknownItem(rel, ident, closest_id(ident, java)))
    return bad


def gated_refs(
    out_tree: Path,
    written: list[str],
    gated: dict[str, GatedItem],
    originals: dict[str, bytes | None] | None = None,
    exclude: set[tuple[str, str]] = frozenset(),
) -> list[Ref]:
    """Mentions of a gated-off item in the files the session wrote (#187).

    Every id in a written JSON file (a recipe input or output, a loot entry, a
    component) or ``.lang`` key counts, unless the pack itself defines the item
    outside the session's files, the file held it before the session, or
    ``exclude`` has its ``(path, id)`` (an item definition
    :func:`unknown_items` already reports).
    """
    if not gated:
        return []
    normalised = sorted({rel.replace("\\", "/") for rel in written})
    originals = {k.replace("\\", "/"): v for k, v in (originals or {}).items()}
    defined: set[str] | None = None
    bad: list[Ref] = []
    for rel in normalised:
        target = out_tree / rel
        if not rel.startswith(("behavior_pack/", "resource_pack/")) or not target.is_file():
            continue
        before = {ident for _, ident in _file_ids(rel, originals.get(rel))}
        seen: set[str] = set()
        for where, ident in _file_ids(rel, target.read_bytes()):
            if ident not in gated or ident in before or ident in seen or (rel, ident) in exclude:
                continue
            if defined is None:
                defined = _pack_defined(out_tree, set(normalised))
            if ident in defined:
                continue
            seen.add(ident)
            bad.append(Ref(rel, where, "gated_item", ident))
    return bad


def gated_finding(ref: Ref, gated: dict[str, GatedItem]) -> dict:
    """The validate-tool finding for one mention of a gated-off item."""
    item = gated.get(ref.ident)
    why = item.explain() if item else "item gated off by a mod config flag"
    message = (
        f"{ref.where} names {ref.ident!r}: {why}. Java doesn't register this item with the mod "
        "config this conversion holds, so the pack must not define, craft, drop or name it. "
        "Leave it out (drop the recipe, entry or line that needs it), or write nothing and decline."
    )
    return {"path": ref.path, "rule": "agent.gated_item", "message": message, "severity": "error"}


def finding(item: UnknownItem) -> dict:
    """The validate-tool finding for one invented item, as the agent sees it."""
    if item.gated is not None:
        message = (
            f"defines item {item.ident!r}: {item.gated.explain()}. Java doesn't register this "
            "item with the mod config this conversion holds, so defining it would ship content "
            "the mod doesn't have. Write nothing for it and decline."
        )
        return {"path": item.path, "rule": "agent.unknown_item", "message": message, "severity": "error"}
    closest = (
        f" The closest id the Java mod registers is {item.closest!r}."
        if item.closest else ""
    )
    message = (
        f"defines item {item.ident!r}, but the Java mod registers no item or block with "
        "that id (checked: blockstates, lang keys, recipes, item tags, loot tables; an "
        "item model file alone is not a registration). Java registers one item and "
        "carries variants (wood, colour, size) in block state, metadata or NBT, so a "
        f"per-variant item is an invented id.{closest} Define the item under a real id, "
        "or write nothing and decline."
    )
    return {"path": item.path, "rule": "agent.unknown_item", "message": message, "severity": "error"}
