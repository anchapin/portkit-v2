"""What does the Java source register? (#86, #158)

One deterministic answer, shared by the item converter
(:mod:`portkit.converters.items`, which emits only registered items) and the
residue agent's item guard (:mod:`portkit.agent.items`, which holds the agent
to the same set). It lives outside both packages so neither has to import the
other's.

The registered set is what the deterministic core already reads, minus item
models:

- a blockstate (a block, and the block item Java gives it);
- a lang key (``item.<ns>.<name>`` / ``block.<ns>.<name>`` in a JSON lang
  file; in a 1.12 ``.lang`` file, ``item.<ns>.<key>.name`` /
  ``tile.<ns>.<key>.name`` with the camelCase key in lower or snake case);
- an item a recipe, an item tag or a loot table names, or a block loot table.

An item *model* file is not a registration: a 1.12 mod ships one model per
metadata variant, and a modern mod ships override models such as
``twinbound_feather_brushing_0``, while Java registers one item and keeps the
variant in metadata, NBT or a model override.
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Iterator

_ID = re.compile(r"^[a-z0-9_.\-]+:[a-z0-9_./\-]+$")
# Bedrock still accepts a legacy aux value on an item id: "minecraft:dye:4".
_AUX = re.compile(r"^([^:]+:[^:]+):\d+$")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _bare(ident: str) -> str:
    match = _AUX.match(ident)
    return match.group(1) if match else ident


def _java_item_specs(spec) -> Iterator[str]:
    if isinstance(spec, str):
        if not spec.startswith("#"):
            yield spec
    elif isinstance(spec, dict):
        for key in ("item", "id"):
            if isinstance(spec.get(key), str):
                yield spec[key]
    elif isinstance(spec, list):
        for entry in spec:
            yield from _java_item_specs(entry)


def _walk_loot_names(node) -> Iterator[str]:
    if isinstance(node, dict):
        if node.get("type") in ("minecraft:item", "item") and isinstance(node.get("name"), str):
            yield node["name"]
        for value in node.values():
            yield from _walk_loot_names(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_loot_names(value)


def _legacy_lang_ids(ns: str, path: Path, kinds=("item", "tile")) -> set[str]:
    """Ids a 1.12 ``.lang`` file's ``item.<ns>.<key>.name`` keys stand for."""
    found: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return found
    for line in text.splitlines():
        key = line.split("=", 1)[0].strip()
        parts = key.split(".")
        if "=" not in line or len(parts) < 4 or parts[-1] != "name":
            continue
        if parts[0] not in kinds or parts[1] != ns:
            continue
        base = parts[2]
        found.add(f"{ns}:{base.lower()}")
        found.add(f"{ns}:{_CAMEL.sub('_', base).lower()}")
    return found


def registered_ids(source_root: Path, items_only: bool = False) -> set[str]:
    """Item and block ids the Java source registers (item models excluded).

    ``items_only`` keeps only the evidence that names an *item*: an item lang
    key, and items that recipes, item tags and loot entries name. A blockstate,
    a block lang key and a block loot table's file name say a block exists,
    not that Java gives it an item (a portal, a crop, a wall sign has none),
    which is what an item named like a block that did not convert must show
    before it is written on its own (:mod:`portkit.converters.items`).
    """
    found: set[str] = set()
    lang_kinds = ("item",) if items_only else ("item", "block")
    assets = source_root / "assets"
    for ns_dir in sorted(p for p in assets.iterdir() if p.is_dir()) if assets.is_dir() else []:
        ns = ns_dir.name
        states = ns_dir / "blockstates"
        if states.is_dir() and not items_only:
            found.update(f"{ns}:{p.relative_to(states).with_suffix('').as_posix()}" for p in states.rglob("*.json"))
        lang = ns_dir / "lang"
        for path in sorted(lang.glob("*.json")) if lang.is_dir() else []:
            data = _load(path)
            for key in data if isinstance(data, dict) else []:
                parts = key.split(".")
                if len(parts) == 3 and parts[0] in lang_kinds and parts[1] == ns:
                    found.add(f"{ns}:{parts[2]}")
        for path in sorted(lang.glob("*.lang")) if lang.is_dir() else []:
            found |= _legacy_lang_ids(ns, path, ("item",) if items_only else ("item", "tile"))
    data_root = source_root / "data"
    for ns_dir in sorted(p for p in data_root.iterdir() if p.is_dir()) if data_root.is_dir() else []:
        ns = ns_dir.name
        for folder in ("recipes", "recipe"):
            for path in sorted((ns_dir / folder).rglob("*.json")) if (ns_dir / folder).is_dir() else []:
                recipe = _load(path)
                if not isinstance(recipe, dict):
                    continue
                for slot in ("result", "ingredient", "ingredients", "template", "base", "addition"):
                    found.update(_java_item_specs(recipe.get(slot)))
                if isinstance(recipe.get("key"), dict):
                    for spec in recipe["key"].values():
                        found.update(_java_item_specs(spec))
        for folder in ("tags/items", "tags/item"):
            for path in sorted((ns_dir / folder).rglob("*.json")) if (ns_dir / folder).is_dir() else []:
                tag = _load(path)
                if isinstance(tag, dict):
                    found.update(_java_item_specs(tag.get("values")))
        for folder in ("loot_tables", "loot_table"):
            base = ns_dir / folder
            if not base.is_dir():
                continue
            blocks = base / "blocks"
            if blocks.is_dir() and not items_only:
                found.update(f"{ns}:{p.relative_to(blocks).with_suffix('').as_posix()}" for p in blocks.rglob("*.json"))
            for path in sorted(base.rglob("*.json")):
                found.update(_walk_loot_names(_load(path)))
    # 1.12 recipes live under assets/<ns>/recipes.
    for ns_dir in sorted(p for p in assets.iterdir() if p.is_dir()) if assets.is_dir() else []:
        recipes = ns_dir / "recipes"
        for path in sorted(recipes.rglob("*.json")) if recipes.is_dir() else []:
            recipe = _load(path)
            if not isinstance(recipe, dict):
                continue
            found.update(_java_item_specs(recipe.get("result")))
            for slot in ("ingredient", "ingredients"):
                found.update(_java_item_specs(recipe.get(slot)))
            if isinstance(recipe.get("key"), dict):
                for spec in recipe["key"].values():
                    found.update(_java_item_specs(spec))
    return {_bare(i) for i in found if isinstance(i, str) and _ID.match(_bare(i))}


def variant_of(ident: str, java_ids: set[str]) -> str | None:
    """The registered id an unregistered one extends with a ``_suffix``, if any.

    ``basicdrawers_full2_jungle`` is a variant of ``basicdrawers``; the longest
    registered path in the same namespace wins.
    """
    ns, path = ident.split(":", 1)
    stems = [
        i for i in java_ids
        if i.split(":", 1)[0] == ns and path.startswith(i.split(":", 1)[1] + "_")
    ]
    return max(stems, key=lambda i: (len(i), i)) if stems else None


def closest_id(ident: str, java_ids: set[str]) -> str | None:
    """The registered Java id nearest an unregistered one.

    A per-variant id is usually a real id plus a suffix
    (``basicdrawers_full2_jungle`` for ``basicdrawers``), so the longest
    registered path the variant extends wins; otherwise the nearest by
    edit similarity, preferring the same namespace.
    """
    if not java_ids:
        return None
    ns, path = ident.split(":", 1)
    same = sorted(i for i in java_ids if i.split(":", 1)[0] == ns) or sorted(java_ids)
    stems = [i for i in same if path.startswith(i.split(":", 1)[1] + "_")]
    if stems:
        return max(stems, key=lambda i: (len(i), i))
    paths = {i.split(":", 1)[1]: i for i in same}
    match = difflib.get_close_matches(path, list(paths), n=1, cutoff=0.0)
    return paths[match[0]] if match else same[0]
