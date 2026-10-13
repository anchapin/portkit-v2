"""Cross-pack reference checking.

Severity split, deliberately: a texture shortname with no index entry is an
error, because both files are ours and the reference is dangling inside what we
emitted. An item id nothing declares is a warning, because the usual cause is a
definition the converter refused on purpose, which the residue report already
names. Promote it once block and item coverage is wide enough that a missing
definition is always a bug (see the follow-up issue).

Each pack validates fine on its own and the addon is still broken: a block
names a texture shortname the resource pack never defined, a recipe produces an
item nothing declares. Bedrock does not complain about any of it. The block
loads with a missing-texture checkerboard, the recipe silently never appears.

So the references get checked against an index built from both packs at once.
Every finding names the dangling reference AND the file holding it, because
that file is what an agent would have to edit.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .report import ValidationReport

_LANG_NAME = re.compile(r"^(tile|item)\.([a-z0-9_]+:[a-z0-9_/.]+)\.name$")
_VANILLA = "minecraft"


def _load(path: Path):
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None  # the per-pack rules report a broken file themselves


def _obj(value) -> dict:
    """``value`` when it is a JSON object, else ``{}``: a malformed file is the
    per-pack rules' to report (doc.unknown_shape), never a crash here (#141)."""
    return value if isinstance(value, dict) else {}


def _texture_keys(pack: Path, index: str) -> set[str]:
    data = _load(pack / "textures" / index)
    if not isinstance(data, dict):
        return set()
    return set(data.get("texture_data") or {})


def _is_custom(identifier: object) -> bool:
    """A reference we are responsible for. Vanilla ids we take on faith."""
    return isinstance(identifier, str) and ":" in identifier and not identifier.startswith(
        f"{_VANILLA}:"
    )


class Index:
    """Everything the converted addon declares, by kind."""

    def __init__(self, behavior: Path | None, resource: Path | None) -> None:
        self.blocks: dict[str, str] = {}  # identifier -> rel path that declares it
        self.items: dict[str, str] = {}
        self.terrain: set[str] = set()
        self.items_atlas: set[str] = set()
        self.item_tags: set[str] = set()  # every tag an item's minecraft:tags names

        if resource is not None:
            self.terrain = _texture_keys(resource, "terrain_texture.json")
            self.items_atlas = _texture_keys(resource, "item_texture.json")

        if behavior is None:
            return
        prefix = behavior.name
        for path in sorted((behavior / "blocks").glob("*.json")):
            data = _load(path)
            if not isinstance(data, dict):
                continue
            ident = _obj(_obj(data.get("minecraft:block")).get("description")).get("identifier")
            if isinstance(ident, str):
                self.blocks[ident] = f"{prefix}/blocks/{path.name}"
        for path in sorted((behavior / "items").glob("*.json")):
            data = _load(path)
            if not isinstance(data, dict):
                continue
            ident = _obj(_obj(data.get("minecraft:item")).get("description")).get("identifier")
            if isinstance(ident, str):
                self.items[ident] = f"{prefix}/items/{path.name}"
            tags = _obj(_obj(_obj(data.get("minecraft:item")).get("components")).get("minecraft:tags")).get("tags")
            if isinstance(tags, list):
                self.item_tags |= {t for t in tags if isinstance(t, str)}

    @property
    def obtainable(self) -> set[str]:
        """Ids that can appear in an inventory: every block is also its item."""
        return set(self.blocks) | set(self.items)


def _check_block_textures(report: ValidationReport, behavior: Path, index: Index) -> None:
    prefix = behavior.name
    for path in sorted((behavior / "blocks").glob("*.json")):
        rel = f"{prefix}/blocks/{path.name}"
        data = _obj(_load(path))
        components = _obj(_obj(data.get("minecraft:block")).get("components"))
        instances = components.get("minecraft:material_instances")
        if not isinstance(instances, dict):
            continue
        for face, instance in instances.items():
            texture = instance.get("texture") if isinstance(instance, dict) else None
            if not isinstance(texture, str) or texture in index.terrain:
                continue
            report.add(
                rel,
                "xref.texture",
                f"face {face!r} uses texture {texture!r}, which no terrain_texture.json "
                f"entry defines; the block would render untextured",
            )


def _check_item_icons(report: ValidationReport, behavior: Path, index: Index) -> None:
    prefix = behavior.name
    for path in sorted((behavior / "items").glob("*.json")):
        rel = f"{prefix}/items/{path.name}"
        data = _load(path)
        if not isinstance(data, dict):
            continue
        icon = _obj(_obj(data.get("minecraft:item")).get("components")).get("minecraft:icon")
        if isinstance(icon, dict):  # 1.21 shape: {"texture": "..."}
            icon = icon.get("texture")
        if not isinstance(icon, str) or icon in index.items_atlas:
            continue
        report.add(
            rel,
            "xref.texture",
            f"icon {icon!r} is in no item_texture.json entry; the item would render untextured",
        )


def _check_block_placers(report: ValidationReport, behavior: Path, index: Index) -> None:
    """An item that places a block must name one the pack declares (or vanilla's).

    ``replace_block_item`` makes the item the block's own item, which Bedrock
    only accepts when the item's identifier is the block's (learn.microsoft.com,
    Items Documentation - minecraft:block_placer).
    """
    prefix = behavior.name
    for path in sorted((behavior / "items").glob("*.json")):
        rel = f"{prefix}/items/{path.name}"
        item = _obj(_obj(_load(path)).get("minecraft:item"))
        placer = _obj(item.get("components")).get("minecraft:block_placer")
        if not isinstance(placer, dict):
            continue
        block = placer.get("block")
        if _is_custom(block) and block not in index.blocks:
            report.add(rel, "xref.block_placer",
                       f"minecraft:block_placer places {block!r}, which no block definition declares")
        ident = _obj(item.get("description")).get("identifier")
        if placer.get("replace_block_item") is True and isinstance(block, str) and block != ident:
            report.add(rel, "xref.block_placer",
                       f"replace_block_item needs the item's identifier ({ident!r}) to be the "
                       f"block's ({block!r})")


def _recipe_item_refs(body: dict) -> list[tuple[str, object]]:
    """(where, identifier) for every item a recipe names."""
    refs: list[tuple[str, object]] = []
    result = body.get("result")
    for i, entry in enumerate(result if isinstance(result, list) else [result]):
        if isinstance(entry, dict):
            refs.append((f"result[{i}]" if isinstance(result, list) else "result",
                         entry.get("item")))
        elif isinstance(entry, str):
            refs.append(("result", entry))
    for slot, ingredient in (body.get("key") or {}).items():
        if isinstance(ingredient, dict):
            refs.append((f"key[{slot!r}]", ingredient.get("item")))
    ingredients = body.get("ingredients")
    for i, ingredient in enumerate(ingredients if isinstance(ingredients, list) else []):
        if isinstance(ingredient, dict):
            refs.append((f"ingredients[{i}]", ingredient.get("item")))
    for slot in ("input", "output", "reagent"):  # furnace/brewing: a bare id or {"item"}
        value = body.get(slot)
        if isinstance(value, dict):
            refs.append((slot, value.get("item")))
        elif isinstance(value, str):
            refs.append((slot, value))
    for slot in ("template", "base", "addition"):  # smithing: a bare id or {"item"}/{"tag"}
        value = body.get(slot)
        if isinstance(value, str):
            refs.append((slot, value))
        elif isinstance(value, dict) and isinstance(value.get("item"), str):
            refs.append((slot, value["item"]))
    return refs


def _recipe_tag_refs(body: dict) -> list[tuple[str, str]]:
    """(where, tag) for every tag ingredient a recipe names."""
    refs: list[tuple[str, str]] = []
    for slot, ingredient in (body.get("key") or {}).items():
        if isinstance(ingredient, dict) and isinstance(ingredient.get("tag"), str):
            refs.append((f"key[{slot!r}]", ingredient["tag"]))
    ingredients = body.get("ingredients")
    for i, ingredient in enumerate(ingredients if isinstance(ingredients, list) else []):
        if isinstance(ingredient, dict) and isinstance(ingredient.get("tag"), str):
            refs.append((f"ingredients[{i}]", ingredient["tag"]))
    return refs


def _check_recipes(report: ValidationReport, behavior: Path, index: Index) -> None:
    prefix = behavior.name
    obtainable = index.obtainable
    for path in sorted((behavior / "recipes").glob("*.json")):
        rel = f"{prefix}/recipes/{path.name}"
        data = _load(path)
        if not isinstance(data, dict):
            # Earlier rules already flagged a bad file as json.parse; nothing
            # to check here and ``.items()`` would AttributeError on a string.
            continue
        for key, body in data.items():
            if not key.startswith("minecraft:recipe_") or not isinstance(body, dict):
                continue
            for where, ident in _recipe_item_refs(body):
                if isinstance(ident, str) and ident.startswith("#"):
                    # A Java tag string written as an item id (#194): no item
                    # has that name, so the recipe can never be crafted.
                    report.add(
                        rel,
                        "xref.item_tag",
                        f"{where} names {ident!r} as an item; a '#' name is a Java tag, "
                        f"which Bedrock takes as {{\"tag\": \"{ident[1:]}\"}} or not at all",
                    )
                    continue
                if not _is_custom(ident) or ident in obtainable:
                    continue
                report.add(
                    rel,
                    "xref.item",
                    f"{where} names {ident!r}, which no block or item definition declares; "
                    f"the recipe will never appear in game. Usually the definition was "
                    f"refused: check the residue report for that identifier.",
                    severity="warning",
                )
            for where, tag in _recipe_tag_refs(body):
                # A vanilla tag is Bedrock's own; a custom one only matches the
                # pack items whose minecraft:tags name it (#160).
                if not _is_custom(tag) or tag in index.item_tags:
                    continue
                report.add(
                    rel,
                    "xref.tag",
                    f"{where} takes tag {tag!r}, which no item's minecraft:tags names; "
                    f"the recipe can never be crafted.",
                    severity="warning",
                )


def _check_loot(report: ValidationReport, behavior: Path, index: Index) -> None:
    prefix = behavior.name
    obtainable = index.obtainable
    for path in sorted((behavior / "loot_tables").rglob("*.json")):
        rel = f"{prefix}/{path.relative_to(behavior).as_posix()}"
        data = _obj(_load(path))
        pools = data.get("pools")
        for i, pool in enumerate(pools if isinstance(pools, list) else []):
            entries = _obj(pool).get("entries")
            for j, entry in enumerate(entries if isinstance(entries, list) else []):
                name = entry.get("name") if isinstance(entry, dict) else None
                if not _is_custom(name) or name in obtainable:
                    continue
                report.add(
                    rel,
                    "xref.item",
                    f"pools[{i}].entries[{j}] drops {name!r}, which no block or item "
                    f"definition declares; the block will drop nothing. Usually the "
                    f"definition was refused: check the residue report for that identifier.",
                    severity="warning",
                )


def _check_lang(report: ValidationReport, resource: Path, index: Index) -> None:
    """Names are a warning, not an error: a missing one is ugly, not broken."""
    lang = resource / "texts" / "en_US.lang"
    if not lang.is_file():
        return
    rel = f"{resource.name}/texts/en_US.lang"
    obtainable = index.obtainable
    named: set[str] = set()
    for line in lang.read_text().splitlines():
        match = _LANG_NAME.match(line.split("=", 1)[0].strip())
        if not match:
            continue
        ident = match.group(2)
        named.add(ident)
        if _is_custom(ident) and ident not in obtainable:
            report.add(
                rel,
                "xref.lang_orphan",
                f"names {ident!r}, which no block or item definition declares",
                severity="warning",
            )
    for ident, where in sorted({**index.blocks, **index.items}.items()):
        if ident not in named:
            report.add(
                where,
                "xref.lang_missing",
                f"{ident} has no name in en_US.lang and would show as its raw identifier",
                severity="warning",
            )


def check_cross_pack(report: ValidationReport, tree: Path) -> Index:
    """Check every reference that crosses the behavior/resource boundary."""
    behavior = tree / "behavior_pack"
    resource = tree / "resource_pack"
    behavior = behavior if behavior.is_dir() else None
    resource = resource if resource.is_dir() else None
    index = Index(behavior, resource)

    if behavior is not None:
        if resource is not None:
            _check_block_textures(report, behavior, index)
            _check_item_icons(report, behavior, index)
        _check_recipes(report, behavior, index)
        _check_block_placers(report, behavior, index)
        _check_loot(report, behavior, index)
    if resource is not None:
        _check_lang(report, resource, index)
    return index
