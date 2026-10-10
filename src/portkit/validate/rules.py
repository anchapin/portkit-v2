"""The oracle.

Structural rules Bedrock actually enforces. Every rule is cheap, deterministic
and names the file it failed on, because this report is the agent's only
feedback signal and a vague one produces a flailing loop.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from .collisions import check_collisions
from . import schema
from .report import ValidationReport
from .xrefs import check_cross_pack

_IDENTIFIER = re.compile(r"^[a-z0-9_]+:[a-z0-9_/.]+$")
_RECIPE_KEYS = {
    "minecraft:recipe_shaped",
    "minecraft:recipe_shapeless",
    "minecraft:recipe_furnace",
    "minecraft:recipe_brewing_mix",
    "minecraft:recipe_smithing_transform",
    "minecraft:recipe_smithing_trim",
}
# The fields each recipe body needs non-empty. Bedrock loads a recipe with an
# empty one as a silent no-op, so a probe file the agent writes to poke the
# validator would otherwise ship in the addon as if it were a real recipe.
# A tuple entry is a set of alternatives. Furnace recipes name their product
# "output" (#90). Brewing recipes do too; "result" stays accepted there until
# a brewing converter exists to settle it.
_RECIPE_REQUIRED: dict[str, tuple] = {
    "minecraft:recipe_shaped": ("result",),
    "minecraft:recipe_shapeless": ("ingredients", "result"),
    "minecraft:recipe_furnace": ("input", "output"),
    "minecraft:recipe_brewing_mix": ("input", "reagent", ("output", "result")),
    "minecraft:recipe_smithing_transform": ("template", "base", "addition", "result"),
    # A trim keeps its base item, so it names no result.
    "minecraft:recipe_smithing_trim": ("template", "base", "addition"),
}


def _load(report: ValidationReport, path: Path, rel: str):
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        report.add(rel, "json.parse", f"invalid JSON: {exc}")
        return None


def _check_manifest(report: ValidationReport, path: Path, rel: str) -> None:
    data = _load(report, path, rel)
    if data is None:
        return
    if data.get("format_version") != 2:
        report.add(rel, "manifest.format_version", "must be 2")
    header = data.get("header") or {}
    for key in ("name", "uuid", "version", "min_engine_version"):
        if key not in header:
            report.add(rel, "manifest.header", f"missing header.{key}")
    for field_name, value in (("header.uuid", header.get("uuid")),):
        if value is not None:
            try:
                uuid.UUID(str(value))
            except ValueError:
                report.add(rel, "manifest.uuid", f"{field_name} is not a UUID")
    modules = data.get("modules") or []
    if not modules:
        report.add(rel, "manifest.modules", "at least one module is required")
    seen = {header.get("uuid")}
    for i, module in enumerate(modules):
        if module.get("type") not in {"data", "resources", "script"}:
            report.add(rel, "manifest.module_type", f"modules[{i}].type is invalid")
        mid = module.get("uuid")
        if mid in seen:
            report.add(rel, "manifest.uuid_unique", f"modules[{i}].uuid duplicates another UUID")
        seen.add(mid)


def _is_empty(value) -> bool:
    """None, "", [], {} and a list of only empty entries all count as empty."""
    if value is None:
        return True
    if isinstance(value, (str, dict)):
        return not value
    if isinstance(value, list):
        return all(_is_empty(v) for v in value)
    return False


def _check_recipe(report: ValidationReport, path: Path, rel: str) -> None:
    data = _load(report, path, rel)
    if data is None:
        return
    if not isinstance(data, dict):
        report.add(rel, "recipe.shape", "recipe file must be a JSON object")
        return
    if "format_version" not in data:
        report.add(rel, "recipe.format_version", "missing format_version")
    body_keys = [k for k in data if k in _RECIPE_KEYS]
    if len(body_keys) != 1:
        report.add(rel, "recipe.type", "exactly one recipe body key is required")
        return
    body = data[body_keys[0]]
    if not isinstance(body, dict):
        report.add(rel, "recipe.shape", f"{body_keys[0]} must be a JSON object")
        return
    for required in _RECIPE_REQUIRED[body_keys[0]]:
        names = required if isinstance(required, tuple) else (required,)
        if all(_is_empty(body.get(name)) for name in names):
            report.add(rel, "recipe.empty", f"{names[0]} is missing or empty")
    identifier = (body.get("description") or {}).get("identifier")
    if not identifier or not _IDENTIFIER.match(str(identifier)):
        report.add(rel, "recipe.identifier", f"bad identifier {identifier!r}")
    if not body.get("tags"):
        report.add(rel, "recipe.tags", "recipe needs at least one crafting tag")
    if body_keys[0] == "minecraft:recipe_shaped":
        pattern = body.get("pattern") or []
        key = body.get("key") or {}
        if not pattern:
            report.add(rel, "recipe.pattern", "shaped recipe needs a pattern")
        widths = {len(row) for row in pattern}
        if len(widths) > 1:
            report.add(rel, "recipe.pattern", "pattern rows must be the same width")
        used = {c for row in pattern for c in row if c != " "}
        for symbol in sorted(used - set(key)):
            report.add(rel, "recipe.key", f"pattern uses {symbol!r} with no key entry")
        for symbol in sorted(set(key) - used):
            report.add(rel, "recipe.key", f"key defines unused symbol {symbol!r}", "warning")


def _check_texture_index(report: ValidationReport, path: Path, rel: str, pack_root: Path) -> None:
    data = _load(report, path, rel)
    if data is None:
        return
    entries = (data.get("texture_data") or {})
    if not entries:
        report.add(rel, "texture_index.empty", "texture index has no entries")
    for name, entry in entries.items():
        if not _IDENTIFIER.match(name):
            report.add(rel, "texture_index.identifier", f"bad texture key {name!r}")
        target = entry.get("textures")
        if not isinstance(target, str):
            report.add(rel, "texture_index.textures", f"{name}: textures must be a path")
            continue
        if not (pack_root / f"{target}.png").is_file():
            report.add(rel, "texture_index.missing", f"{name}: {target}.png not in pack")


def _check_flipbook(report: ValidationReport, path: Path, rel: str, pack_root: Path) -> None:
    data = _load(report, path, rel)
    if data is None:
        return
    if not isinstance(data, list):
        report.add(rel, "flipbook.shape", "flipbook_textures.json must be a list")
        return

    tiles: set[str] = set()
    for index in ("textures/terrain_texture.json", "textures/item_texture.json"):
        index_path = pack_root / index
        if index_path.is_file():
            try:
                tiles |= set((json.loads(index_path.read_text()).get("texture_data") or {}))
            except json.JSONDecodeError:
                pass  # the index check reports this itself

    for i, entry in enumerate(data):
        target = entry.get("flipbook_texture")
        if not isinstance(target, str):
            report.add(rel, "flipbook.texture", f"[{i}]: flipbook_texture must be a path")
        elif not (pack_root / f"{target}.png").is_file():
            report.add(rel, "flipbook.missing", f"[{i}]: {target}.png not in pack")

        tile = entry.get("atlas_tile")
        if not isinstance(tile, str):
            report.add(rel, "flipbook.atlas_tile", f"[{i}]: atlas_tile must be a texture key")
        elif tile not in tiles:
            report.add(
                rel, "flipbook.atlas_tile", f"[{i}]: atlas_tile {tile!r} is in no texture index"
            )

        ticks = entry.get("ticks_per_frame")
        if not isinstance(ticks, int) or isinstance(ticks, bool) or ticks < 1:
            report.add(rel, "flipbook.ticks", f"[{i}]: ticks_per_frame must be a positive integer")


_MENU_CATEGORIES = {
    "construction", "nature", "equipment", "items", "none",
}


def _check_block(report: ValidationReport, path: Path, rel: str, pack_root: Path) -> None:
    data = _load(report, path, rel)
    if data is None:
        return
    if "format_version" not in data:
        report.add(rel, "block.format_version", "missing format_version")
    body = data.get("minecraft:block")
    if not isinstance(body, dict):
        report.add(rel, "block.body", "missing minecraft:block")
        return
    schema.check_block(report, data, rel)
    description = body.get("description") or {}
    identifier = description.get("identifier")
    if not identifier or not _IDENTIFIER.match(str(identifier)):
        report.add(rel, "block.identifier", f"bad identifier {identifier!r}")
    if str(identifier).startswith("minecraft:"):
        report.add(rel, "block.identifier", "a custom block cannot claim the minecraft namespace")
    category = (description.get("menu_category") or {}).get("category")
    if category is not None and category not in _MENU_CATEGORIES:
        report.add(rel, "block.menu_category", f"unknown creative category {category!r}")

    components = body.get("components") or {}
    if not components:
        report.add(rel, "block.components", "block has no components")
    instances = components.get("minecraft:material_instances")
    if instances is None:
        return
    if not isinstance(instances, dict) or not instances:
        report.add(rel, "block.material_instances", "material_instances must name at least one face")
        return

    for face, instance in instances.items():
        texture = instance.get("texture") if isinstance(instance, dict) else None
        if not isinstance(texture, str):
            report.add(rel, "block.material_instances", f"{face}: texture must be a shortname")
        # Whether that shortname resolves is a cross-pack question: see validate.xrefs.


def _check_lang(report: ValidationReport, path: Path, rel: str) -> None:
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "=" not in line:
            report.add(rel, "lang.syntax", f"line {lineno} has no '='")


_LOOT_FUNCTIONS = {"set_count", "explosion_decay", "set_data", "looting_enchant"}


def _check_loot_table(report: ValidationReport, path: Path, rel: str) -> None:
    """A loot table Bedrock will actually load.

    Bedrock fails quietly on a malformed table: the block simply drops nothing,
    which is exactly the wrong-but-looks-fine outcome this project exists to
    catch, so the shape is checked here rather than in the converter alone.
    """
    data = _load(report, path, rel)
    if data is None:
        return
    pools = data.get("pools")
    if not isinstance(pools, list) or not pools:
        report.add(rel, "loot.pools", "table has no pools")
        return
    for i, pool in enumerate(pools):
        rolls = pool.get("rolls")
        if not isinstance(rolls, (int, float)):
            report.add(rel, "loot.rolls", f"pools[{i}].rolls must be a number")
        entries = pool.get("entries")
        if not isinstance(entries, list) or not entries:
            report.add(rel, "loot.entries", f"pools[{i}] has no entries")
            continue
        for j, entry in enumerate(entries):
            where = f"pools[{i}].entries[{j}]"
            if entry.get("type") != "item":
                report.add(rel, "loot.entry_type", f"{where}.type must be 'item'")
            name = entry.get("name")
            if not isinstance(name, str) or not _IDENTIFIER.match(name):
                report.add(rel, "loot.name", f"{where}.name {name!r} is not an identifier")
            for k, function in enumerate(entry.get("functions") or []):
                fname = function.get("function")
                if fname not in _LOOT_FUNCTIONS:
                    report.add(
                        rel,
                        "loot.function",
                        f"{where}.functions[{k}] uses unsupported function {fname!r}",
                    )
                if fname == "set_count" and not isinstance(function.get("count"), (int, float)):
                    report.add(
                        rel, "loot.set_count", f"{where}.functions[{k}].count must be a number"
                    )


def validate_pack(pack_root: Path) -> ValidationReport:
    """Validate one behavior_pack/ or resource_pack/ directory."""
    report = ValidationReport()
    prefix = pack_root.name

    manifest = pack_root / "manifest.json"
    if not manifest.is_file():
        report.add(f"{prefix}/manifest.json", "manifest.missing", "pack has no manifest.json")
    else:
        _check_manifest(report, manifest, f"{prefix}/manifest.json")

    for path in sorted((pack_root / "recipes").glob("*.json")):
        _check_recipe(report, path, f"{prefix}/recipes/{path.name}")

    for path in sorted((pack_root / "blocks").glob("*.json")):
        _check_block(report, path, f"{prefix}/blocks/{path.name}", pack_root)

    for path in sorted((pack_root / "loot_tables").rglob("*.json")):
        _check_loot_table(report, path, f"{prefix}/{path.relative_to(pack_root).as_posix()}")

    for index in ("textures/terrain_texture.json", "textures/item_texture.json"):
        path = pack_root / index
        if path.is_file():
            _check_texture_index(report, path, f"{prefix}/{index}", pack_root)

    flipbook = pack_root / "textures" / "flipbook_textures.json"
    if flipbook.is_file():
        _check_flipbook(report, flipbook, f"{prefix}/textures/flipbook_textures.json", pack_root)

    lang = pack_root / "texts" / "en_US.lang"
    if lang.is_file():
        _check_lang(report, lang, f"{prefix}/texts/en_US.lang")

    return report


def _check_dependencies(report: ValidationReport, packs: list[Path]) -> None:
    """Every declared dependency has to resolve to a pack in this addon.

    A behavior pack pointing at a UUID that ships nowhere imports as a broken
    half: Bedrock enables it and the player never sees the textures.
    """
    headers: dict[str, str] = {}
    manifests: list[tuple[Path, dict]] = []
    for pack in packs:
        path = pack / "manifest.json"
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue  # the manifest check reports this itself
        manifests.append((pack, data))
        uid = (data.get("header") or {}).get("uuid")
        if uid:
            headers[str(uid)] = pack.name

    for pack, data in manifests:
        rel = f"{pack.name}/manifest.json"
        for i, dep in enumerate(data.get("dependencies") or []):
            uid = str(dep.get("uuid"))
            if uid == str((data.get("header") or {}).get("uuid")):
                report.add(rel, "manifest.dependency", f"dependencies[{i}] points at this pack")
            elif uid not in headers:
                report.add(
                    rel,
                    "manifest.dependency",
                    f"dependencies[{i}] uuid {uid} is not a pack in this addon",
                )
            if not isinstance(dep.get("version"), list):
                report.add(rel, "manifest.dependency", f"dependencies[{i}] needs a version list")


def validate_tree(tree: Path) -> ValidationReport:
    """Validate a converted output tree (behavior_pack/ + resource_pack/)."""
    report = ValidationReport()
    packs = [p for p in (tree / "behavior_pack", tree / "resource_pack") if p.is_dir()]
    if not packs:
        report.add(str(tree), "tree.empty", "no behavior_pack/ or resource_pack/ found")
        return report
    for pack in packs:
        report.findings.extend(validate_pack(pack).findings)
    _check_dependencies(report, packs)
    check_collisions(report, tree)
    check_cross_pack(report, tree)
    return report
