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

Unknown namespaces (#147)
-------------------------
The recipe check only reads recipes. On real-mod residue GLM 5.3 wrote blocks
and items naming ``sd:`` ids, a typo for storage drawers' ``storagedrawers``
namespace, and nothing caught them. So every identifier in *any* JSON file the
session writes (a string value or object key of the form ``ns:path``, an id
quoted inside a Molang string, a ``tag:ns:path`` component, a ``tile.ns:path``
lang key) must have a namespace that is:

- ``minecraft``;
- one the mod has a folder for under ``assets/`` or ``data/``; or
- the conversion's own namespace (the pack's identity).

Two exceptions keep it from flagging what the agent did not invent: an exact
id the source mod names in an item position (``source_items``, which covers a
compat recipe naming another mod's item), and an id the file already held
before the session touched it.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from ..registry import _ID, _bare, _java_item_specs, _load, _walk_loot_names

_VANILLA = "minecraft"


@dataclass(frozen=True)
class Ref:
    path: str  # the pack file that names it, relative to the output tree
    where: str  # e.g. "key['#']", "ingredients[0]", "addition"
    kind: str  # item | tag
    ident: str

    def describe(self) -> str:
        return f"{self.path} {self.where}: {self.kind} {self.ident!r}"


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


# -- unknown namespaces (#147) -------------------------------------------

# Ids quoted inside a Molang expression: q.block_state('sd:facing').
_QUOTED_ID = re.compile(r"'([a-z0-9_.\-]+:[a-z0-9_./\-]+)'")
# Bedrock lang keys that carry an id: tile.ns:name.name, item.ns:name, entity.ns:name.name
_LANG_ID = re.compile(r"^(?:tile|item|entity|block)\.([a-z0-9_.\-]+:[a-z0-9_./\-]+?)(?:\.name)?$")


def _id_like(text: str) -> bool:
    """``ns:path`` with a real-looking namespace: not a time, ratio or URL."""
    if not _ID.match(text):
        return False
    ns, path = text.split(":", 1)
    return any(c.isalpha() for c in ns) and not path.startswith("/")


def _string_ids(text: str) -> Iterator[str]:
    if text.startswith("tag:"):
        text = text[len("tag:"):]
    lang = _LANG_ID.match(text)  # a translation key: item.ns:name.name
    if lang:
        text = lang.group(1)
    bare = _bare(text)
    if _id_like(bare):
        yield bare
        return
    for match in _QUOTED_ID.finditer(text):
        if _id_like(match.group(1)):
            yield match.group(1)


def document_ids(node, where: str = "") -> Iterator[tuple[str, str]]:
    """(where, id) for every namespaced identifier a JSON document names."""
    if isinstance(node, str):
        for ident in _string_ids(node):
            yield where or "(value)", ident
    elif isinstance(node, dict):
        for key, value in node.items():
            here = f"{where}.{key}" if where else str(key)
            if isinstance(key, str):
                for ident in _string_ids(key):
                    yield f"{here} (key)", ident
            yield from document_ids(value, here)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from document_ids(value, f"{where}[{i}]")


def lang_ids(text: str) -> Iterator[tuple[str, str]]:
    """(where, id) for every id-bearing key in a .lang file."""
    for line in text.splitlines():
        key = line.split("=", 1)[0].strip()
        if "=" not in line or key.startswith("#"):
            continue
        match = _LANG_ID.match(key)
        if match and _id_like(match.group(1)):
            yield f"lang key {key!r}", match.group(1)


def _file_ids(rel: str, raw: bytes | str | None) -> list[tuple[str, str]]:
    if raw is None:
        return []
    text = raw.decode("utf-8-sig", errors="replace") if isinstance(raw, bytes) else raw
    if rel.endswith(".lang"):
        return list(lang_ids(text))
    if not rel.endswith(".json"):
        return []
    try:
        data = json.loads(text.lstrip("\ufeff"))
    except json.JSONDecodeError:
        return []  # a broken file is the validator's to report
    return list(document_ids(data))


def source_namespaces(source_root: Path) -> set[str]:
    """Namespaces the mod has a folder for under ``assets/`` or ``data/``."""
    found: set[str] = set()
    for top in ("assets", "data"):
        base = source_root / top
        if base.is_dir():
            found.update(p.name for p in base.iterdir() if p.is_dir())
    return found


def valid_namespaces(source_root: Path, namespace: str | None = None) -> set[str]:
    found = {_VANILLA, *source_namespaces(source_root)}
    if namespace:
        found.add(namespace)
    return found


def unknown_namespace_refs(
    out_tree: Path,
    written: list[str],
    source_root: Path,
    namespace: str | None = None,
    originals: dict[str, bytes | None] | None = None,
    *,
    _source_ids: set[str] | None = None,
) -> list[Ref]:
    """Ids in the files listed in ``written`` whose namespace this mod does not have.

    ``originals`` maps a written path to what it held before the session (None
    for a new file): ids already there are not the session's to answer for.
    """
    valid = valid_namespaces(source_root, namespace)
    originals = {k.replace("\\", "/"): v for k, v in (originals or {}).items()}
    known_ids = _source_ids
    bad: list[Ref] = []
    for rel in sorted({r.replace("\\", "/") for r in written}):
        target = out_tree / rel
        if not rel.startswith(("behavior_pack/", "resource_pack/")) or not target.is_file():
            continue
        before = {ident for _, ident in _file_ids(rel, originals.get(rel))}
        seen: set[tuple[str, str]] = set()
        for where, ident in _file_ids(rel, target.read_bytes()):
            ns = ident.split(":", 1)[0]
            if ns in valid or ident in before or (where, ident) in seen:
                continue
            if known_ids is None:
                known_ids = source_items(source_root)
            if ident in known_ids:
                continue
            seen.add((where, ident))
            bad.append(Ref(rel, where, "id", ident))
    return bad


def namespace_finding(ref: Ref, valid: set[str]) -> dict:
    """The validate-tool finding for one id in a namespace the mod does not have."""
    ns = ref.ident.split(":", 1)[0]
    listed = ", ".join(sorted(valid, key=lambda n: (n != _VANILLA, n)))
    message = (
        f"{ref.where} names {ref.ident!r}, but namespace {ns!r} is neither vanilla nor one this "
        f"mod has. Valid namespaces: {listed}. Use the id the source mod actually uses (check "
        "its assets/ and data/ folders), a vanilla minecraft: id, or leave the reference out; "
        "never invent a namespace."
    )
    return {"path": ref.path, "rule": "agent.unknown_namespace", "message": message, "severity": "error"}


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
