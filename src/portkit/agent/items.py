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
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..converters.items import bedrock_identifier
from ..registry import _load, closest_id, registered_ids
from .refs import _VANILLA, valid_namespaces

__all__ = [
    "UnknownItem",
    "bedrock_ids",
    "closest_id",
    "finding",
    "registered_ids",
    "unknown_items",
]


@dataclass(frozen=True)
class UnknownItem:
    path: str  # the pack file that defines it, relative to the output tree
    ident: str  # the identifier the file gives the item
    closest: str | None  # the nearest id the Java source registers, if any

    def describe(self) -> str:
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
    _registered: set[str] | None = None,
) -> list[UnknownItem]:
    """Items the session defined whose id the Java source never registers.

    ``_registered`` is :func:`registered_ids` for ``source_root`` when the
    caller already has it (the source does not change mid-session).
    """
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
            allowed = bedrock_ids(java, namespace) | _pack_defined(out_tree, set(normalised))
        if ident in allowed:
            continue
        bad.append(UnknownItem(rel, ident, closest_id(ident, java)))
    return bad


def finding(item: UnknownItem) -> dict:
    """The validate-tool finding for one invented item, as the agent sees it."""
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
