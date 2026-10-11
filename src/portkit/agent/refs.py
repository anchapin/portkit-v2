"""Do the items and tags an agent-written recipe names actually exist? (#86)

The validator's ``xref.item`` rule only warns about an item id nothing
declares, because the usual cause is a definition the deterministic path
refused on purpose. That is the right call for the deterministic output, but it
let a live model write ``examplemod:alloy_ingots`` as a recipe ingredient (the
Java *tag* name, used as if it were an item) and still count the group as
resolved.

So the residue agent holds what it writes to a stricter, deterministic rule.
Every item a recipe written in the session names must resolve to one of:

- an item or block the output pack defines;
- an item the source mod defines or names as an item (an item model, a
  blockstate, a lang key, a recipe result or ingredient, a tag-file member, a
  block loot table);
- a vanilla ``minecraft:`` id.

Every tag it names must be a vanilla ``minecraft:`` tag or one an item or block
in the pack declares (``minecraft:tags`` on an item, a ``tag:`` component on a
block). A Java tag file does not carry over to Bedrock: a Bedrock recipe that
names ``examplemod:alloy_ingots`` matches nothing unless a pack item carries
that tag.

Vanilla ids and tags are taken on faith. A full vanilla item list is Mojang
data (see docs/decisions.md on EULA material), and the tag list the agent
reference has is partial, so rejecting an unlisted ``minecraft:`` name would
reject real ones. The check is aimed at what a model can actually invent: ids
in the mod's own namespace, or any other non-vanilla namespace.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

_VANILLA = "minecraft"
_ID = re.compile(r"^[a-z0-9_.\-]+:[a-z0-9_./\-]+$")
# Bedrock still accepts a legacy aux value on an item id: "minecraft:dye:4".
_AUX = re.compile(r"^([^:]+:[^:]+):\d+$")


@dataclass(frozen=True)
class Ref:
    path: str  # the pack file that names it, relative to the output tree
    where: str  # e.g. "key['#']", "ingredients[0]", "addition"
    kind: str  # item | tag
    ident: str

    def describe(self) -> str:
        return f"{self.path} {self.where}: {self.kind} {self.ident!r}"


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _bare(ident: str) -> str:
    match = _AUX.match(ident)
    return match.group(1) if match else ident


# -- what a recipe names -------------------------------------------------

def _spec_refs(where: str, spec) -> Iterator[tuple[str, str, str]]:
    """(where, kind, id) for one ingredient or result spec in any Bedrock shape."""
    if isinstance(spec, str):
        yield where, "item", spec
    elif isinstance(spec, dict):
        if isinstance(spec.get("item"), str):
            yield where, "item", spec["item"]
        if isinstance(spec.get("tag"), str):
            yield where, "tag", spec["tag"]
    elif isinstance(spec, list):
        for i, entry in enumerate(spec):
            yield from _spec_refs(f"{where}[{i}]", entry)


def recipe_refs(body: dict) -> Iterator[tuple[str, str, str]]:
    """Every item and tag one ``minecraft:recipe_*`` body names."""
    key = body.get("key")
    if isinstance(key, dict):
        for slot, spec in key.items():
            yield from _spec_refs(f"key[{slot!r}]", spec)
    for slot in ("ingredients", "result", "input", "output", "reagent", "template", "base", "addition"):
        if slot in body:
            yield from _spec_refs(slot, body[slot])


def pack_recipe_refs(out_tree: Path, rel: str) -> list[Ref]:
    data = _load(out_tree / rel)
    if not isinstance(data, dict):
        return []  # a broken file is the validator's to report
    refs: list[Ref] = []
    for top, body in data.items():
        if top.startswith("minecraft:recipe_") and isinstance(body, dict):
            refs.extend(Ref(rel, where, kind, ident) for where, kind, ident in recipe_refs(body))
    return refs


# -- what exists -------------------------------------------------------

@dataclass
class Known:
    items: set[str]
    tags: set[str]


def pack_known(out_tree: Path) -> Known:
    """Items, blocks and declared tags in the output tree's behavior pack."""
    items: set[str] = set()
    tags: set[str] = set()
    bp = out_tree / "behavior_pack"
    for kind, folder in (("minecraft:item", "items"), ("minecraft:block", "blocks")):
        for path in sorted((bp / folder).rglob("*.json")) if (bp / folder).is_dir() else []:
            data = _load(path)
            if not isinstance(data, dict) or not isinstance(data.get(kind), dict):
                continue
            body = data[kind]
            ident = (body.get("description") or {}).get("identifier")
            if isinstance(ident, str):
                items.add(ident)
            components = body.get("components") or {}
            if not isinstance(components, dict):
                continue
            declared = (components.get("minecraft:tags") or {})
            if isinstance(declared, dict) and isinstance(declared.get("tags"), list):
                tags.update(t for t in declared["tags"] if isinstance(t, str))
            tags.update(name[len("tag:"):] for name in components if name.startswith("tag:"))
    return Known(items, tags)


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


def source_items(source_root: Path) -> set[str]:
    """Item ids the Java mod defines, or names in an item position of its own data."""
    found: set[str] = set()
    assets = source_root / "assets"
    for ns_dir in sorted(p for p in assets.iterdir() if p.is_dir()) if assets.is_dir() else []:
        ns = ns_dir.name
        for sub in ("models/item", "blockstates"):
            base = ns_dir / sub
            if base.is_dir():
                found.update(f"{ns}:{p.relative_to(base).with_suffix('').as_posix()}" for p in base.rglob("*.json"))
        lang = ns_dir / "lang"
        for path in sorted(lang.glob("*.json")) if lang.is_dir() else []:
            data = _load(path)
            for key in data if isinstance(data, dict) else []:
                parts = key.split(".")
                if len(parts) == 3 and parts[0] in ("item", "block") and parts[1] == ns:
                    found.add(f"{ns}:{parts[2]}")
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
            if blocks.is_dir():
                found.update(f"{ns}:{p.relative_to(blocks).with_suffix('').as_posix()}" for p in blocks.rglob("*.json"))
            for path in sorted(base.rglob("*.json")):
                found.update(_walk_loot_names(_load(path)))
    return {_bare(i) for i in found if isinstance(i, str) and _ID.match(_bare(i))}


# -- the check ---------------------------------------------------------

def _is_recipe(rel: str) -> bool:
    return rel.startswith("behavior_pack/recipes/") and rel.endswith(".json")


def unresolved_refs(out_tree: Path, written: list[str], source_root: Path) -> list[Ref]:
    """Refs in the recipes listed in ``written`` that resolve to nothing."""
    normalised = sorted({rel.replace("\\", "/") for rel in written})
    recipes = [rel for rel in normalised if _is_recipe(rel) and (out_tree / rel).is_file()]
    if not recipes:
        return []
    pack = pack_known(out_tree)
    mod_items = source_items(source_root)
    bad: list[Ref] = []
    for rel in recipes:
        for ref in pack_recipe_refs(out_tree, rel):
            ident = _bare(ref.ident) if ref.kind == "item" else ref.ident
            if ident.split(":", 1)[0] == _VANILLA:
                continue  # taken on faith; see the module docstring
            if ref.kind == "item" and (ident in pack.items or ident in mod_items):
                continue
            if ref.kind == "tag" and ident in pack.tags:
                continue
            bad.append(ref)
    return bad


def finding(ref: Ref) -> dict:
    """The validate-tool finding for one unresolved ref, as the agent sees it."""
    if ref.kind == "tag":
        message = (
            f"{ref.where} names tag {ref.ident!r}, which no item or block in the pack declares "
            "and which is not a vanilla tag. Bedrock does not read Java tag files: either give "
            "each member item that tag in its minecraft:tags component, or name the items "
            "explicitly (one recipe per item if needed)."
        )
    else:
        message = (
            f"{ref.where} names item {ref.ident!r}, which neither the pack nor the source mod "
            "defines and which is not vanilla. Use an item that exists; a tag name is not an item."
        )
    return {"path": ref.path, "rule": "agent.unresolved_ref", "message": message, "severity": "error"}
