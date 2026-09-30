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

from .report import ValidationReport

_IDENTIFIER = re.compile(r"^[a-z0-9_]+:[a-z0-9_/.]+$")
_RECIPE_KEYS = {
    "minecraft:recipe_shaped",
    "minecraft:recipe_shapeless",
    "minecraft:recipe_furnace",
    "minecraft:recipe_brewing_mix",
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


def _check_recipe(report: ValidationReport, path: Path, rel: str) -> None:
    data = _load(report, path, rel)
    if data is None:
        return
    if "format_version" not in data:
        report.add(rel, "recipe.format_version", "missing format_version")
    body_keys = [k for k in data if k in _RECIPE_KEYS]
    if len(body_keys) != 1:
        report.add(rel, "recipe.type", "exactly one recipe body key is required")
        return
    body = data[body_keys[0]]
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


def _check_lang(report: ValidationReport, path: Path, rel: str) -> None:
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "=" not in line:
            report.add(rel, "lang.syntax", f"line {lineno} has no '='")


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


def validate_tree(tree: Path) -> ValidationReport:
    """Validate a converted output tree (behavior_pack/ + resource_pack/)."""
    report = ValidationReport()
    packs = [p for p in (tree / "behavior_pack", tree / "resource_pack") if p.is_dir()]
    if not packs:
        report.add(str(tree), "tree.empty", "no behavior_pack/ or resource_pack/ found")
        return report
    for pack in packs:
        report.findings.extend(validate_pack(pack).findings)
    return report
