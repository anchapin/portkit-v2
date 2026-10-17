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

from ..data import FETCH_COMMAND, bedrock_vanilla_sounds
from ..data import trim_items
from ..data.smithing_bases import addon_slot_refusal, vanilla_base_refusal, vanilla_slot_refusal
from ..paths import MAX_PATH, MAX_SEGMENTS, too_long
from ..png import dimensions
from .collisions import check_collisions
from . import schema
from .report import ValidationReport
from .xrefs import check_cross_pack

_ICON_SIZES = {2, 4, 8, 16, 32, 64, 128, 256}
# A namespaced id of a block, item, recipe or loot entry. Bedrock's schemas take
# a hyphen here (checked against the schemas, not in game): Mojang's block
# description schema only asks for no whitespace (bedrock-schemas
# bp/blocks/block_description.schema.json, "^\\S+$"), the item, recipe and
# loot-entry schemas put no pattern on the id, and the biome schema spells the
# set out as "^[a-z0-9._%+-]+:[a-z0-9._%+-]+$". Java ids are [a-z0-9_.-] with
# "/" in the path, so a converted id keeps its hyphen and its Java spelling
# (Wallpapercraft's wallpapercraft:woolblue-0). See docs/decisions.md.
_IDENTIFIER = re.compile(r"^[a-z0-9_-]+:[a-z0-9_/.-]+$")
# A terrain/item texture key. No published schema constrains these, and the
# texture converter maps a Java path's "-" to "_" (#168), so the key check
# stays as strict as it was.
_TEXTURE_KEY = re.compile(r"^[a-z0-9_]+:[a-z0-9_/.]+$")
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


# Directories where every .json file is one Bedrock document, and the top-level
# key(s) that name that document (#141). A file there with none of them, or with
# one whose body is not an object, loads as nothing: Bedrock skips it, and an
# agent's stub such as {"format_version": "1.20.80", "minecraft": "item"} would
# otherwise pass as a valid pack. blocks/, recipes/ and loot_tables/ have their
# own, stricter checks below. Directories not listed are not shape-checked.
FEATURE_TYPES: tuple[str, ...] = tuple(f"minecraft:{t}" for t in (
    "aggregate_feature", "beards_and_shavers", "cave_carver_feature", "conditional_list", "fossil_feature",
    "geode_feature", "growing_plant_feature", "height_difference_filter_feature",
    "horizontal_tree_decoration_feature", "multi_block_feature", "multiface_feature",
    "multipart_block_column_feature", "nether_cave_carver_feature", "ore_feature",
    "partially_exposed_blob_feature", "rect_layout", "scan_surface", "scatter_feature", "sculk_patch_feature",
    "search_feature", "sequence_feature", "single_block_feature", "snap_to_surface_feature",
    "structure_template_feature", "surface_relative_threshold_feature", "tree_feature",
    "underwater_cave_carver_feature", "vegetation_patch_feature", "weighted_random_feature",
))

_DOCUMENT_KEYS: dict[str, dict[str, tuple[str, ...]]] = {
    "behavior_pack": {
        "items": ("minecraft:item",),
        "entities": ("minecraft:entity",),
        "spawn_rules": ("minecraft:spawn_rules",),
        "biomes": ("minecraft:biome",),
        "feature_rules": ("minecraft:feature_rules",),
        # Every feature type Mojang/bedrock-samples documentation/Features.html lists (#281).
        "features": FEATURE_TYPES,
        "dimensions": ("minecraft:dimension",),
        "animations": ("animations",),
        "animation_controllers": ("animation_controllers",),
    },
    "resource_pack": {
        "items": ("minecraft:item",),
        "entity": ("minecraft:client_entity",),
        "attachables": ("minecraft:attachable",),
        "fogs": ("minecraft:fog_settings",),
        "particles": ("particle_effect",),
        "animations": ("animations",),
        "animation_controllers": ("animation_controllers",),
        "render_controllers": ("render_controllers",),
    },
}


def _shape_error(report: ValidationReport, rel: str, data, expected: tuple[str, ...]) -> bool:
    """Report a file that is not the Bedrock document its directory holds.

    True when it reported, so a caller with its own checks can stop there.
    """
    want = " or ".join(expected)
    if not isinstance(data, dict):
        report.add(rel, "doc.unknown_shape",
                   f"file must be a JSON object with {want}, got a {type(data).__name__}")
        return True
    present = [k for k in expected if k in data]
    if not present:
        found = ", ".join(sorted(map(str, data))) or "none"
        message = f"no Bedrock document key: needs {want}; found keys: {found}"
        if any(str(k) == "minecraft" for k in data):
            message += " (a bare 'minecraft' key is usually a 'minecraft:...' key cut at the colon)"
        report.add(rel, "doc.unknown_shape", message)
        return True
    body = data[present[0]]
    if not isinstance(body, dict):
        report.add(rel, "doc.unknown_shape",
                   f"{present[0]} must be a JSON object, got {json.dumps(body)[:40]}")
        return True
    return False


def _check_document(report: ValidationReport, path: Path, rel: str, expected: tuple[str, ...]) -> None:
    data = _load(report, path, rel)
    if data is not None:
        _shape_error(report, rel, data, expected)


def _load(report: ValidationReport, path: Path, rel: str):
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        report.add(rel, "json.parse", f"invalid JSON: {exc}")
        return None
    if data is None:
        # A literal ``null`` parses, then every check would skip it as unreadable.
        report.add(rel, "doc.unknown_shape", "file is JSON null, not a Bedrock document")
    return data


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
        if module.get("type") == "script":
            _check_script_module(report, rel, i, module, path.parent)
    for i, dep in enumerate(data.get("dependencies") or []):
        if isinstance(dep, dict) and "module_name" in dep:
            _check_module_dependency(report, rel, i, dep)


# Script modules (#177). learn.microsoft.com, Pack Manifest: a "script" module
# says its language ("the only supported value is javascript") and names the
# file Bedrock runs ("entry"); a dependency on a built-in script module names
# it by "module_name" (e.g. @minecraft/server) with a version string.
_SEMVER = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$")
_SCRIPT_IMPORT = re.compile(r"""^\s*import\b[^'"]*?(?:from\s*)?['"]([^'"]+)['"]""", re.M)
# Block JSON reads a namespaced custom component key from format 1.21.90
# (minecraft.net, "Minecraft 1.21.90 Bedrock Changelog": "Custom components v2
# is available in JSON versions 1.21.90 and higher").
_CUSTOM_COMPONENT_FORMAT = (1, 21, 90)


def _check_script_module(report: ValidationReport, rel: str, i: int, module: dict, pack_root: Path) -> None:
    if module.get("language") != "javascript":
        report.add(rel, "manifest.script", f"modules[{i}] is a script module without language \"javascript\"")
    entry = module.get("entry")
    if not isinstance(entry, str) or not entry.endswith(".js"):
        report.add(rel, "manifest.script", f"modules[{i}] needs an entry naming a .js file")
    elif not (pack_root / entry).is_file():
        report.add(rel, "manifest.script", f"modules[{i}].entry {entry!r} is not a file in this pack")


def _check_module_dependency(report: ValidationReport, rel: str, i: int, dep: dict) -> None:
    name, version = dep.get("module_name"), dep.get("version")
    if not isinstance(name, str) or not name.startswith("@minecraft/"):
        report.add(rel, "manifest.dependency", f"dependencies[{i}].module_name {name!r} is not a built-in script module")
    if not isinstance(version, str) or not _SEMVER.match(version):
        report.add(rel, "manifest.dependency", f"dependencies[{i}] needs a version string like \"2.0.0\"")


def _check_scripts(report: ValidationReport, pack_root: Path, prefix: str) -> None:
    """Every import in the pack's scripts resolves: a relative path to a file in
    the pack, or a built-in module the manifest declares a dependency on."""
    scripts = sorted((pack_root / "scripts").rglob("*.js"))
    if not scripts:
        return
    declared: set[str] = set()
    has_script_module = False
    try:
        manifest = json.loads((pack_root / "manifest.json").read_text())
        declared = {d.get("module_name") for d in manifest.get("dependencies") or [] if isinstance(d, dict)}
        has_script_module = any(isinstance(m, dict) and m.get("type") == "script" for m in manifest.get("modules") or [])
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    if not has_script_module:
        report.add(f"{prefix}/manifest.json", "manifest.script",
                   "the pack ships scripts/ but has no script module, so Bedrock never runs them", "warning")
    for path in scripts:
        rel = f"{prefix}/{path.relative_to(pack_root).as_posix()}"
        for target in _SCRIPT_IMPORT.findall(path.read_text(encoding="utf-8", errors="replace")):
            if target.startswith("."):
                if not (path.parent / target).resolve().is_file():
                    report.add(rel, "script.import", f"imports {target!r}, which is not a file in this pack")
            elif target not in declared:
                report.add(rel, "script.import",
                           f"imports {target!r}, which the manifest declares no dependency on")


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
        if not _TEXTURE_KEY.match(name):
            report.add(rel, "texture_index.identifier", f"bad texture key {name!r}")
        target = entry.get("textures")
        if not isinstance(target, str):
            report.add(rel, "texture_index.textures", f"{name}: textures must be a path")
            continue
        if not (pack_root / f"{target}.png").is_file() and target not in _vanilla_files():
            report.add(rel, "texture_index.missing", f"{name}: {target}.png not in pack")


def _vanilla_files() -> frozenset[str]:
    """Texture files the vanilla resource pack below every pack serves (the
    fetched atlas index, portkit.data.vanilla_textures), or none without it."""
    from ..data import vanilla_textures

    index = vanilla_textures.index()
    return index.all_files() if index is not None else frozenset()


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


def _format_tuple(value) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in str(value).split("."))
    except ValueError:
        return ()


# Vanilla Bedrock loot tables a pack's block may name without shipping them:
# the vanilla behavior pack's own (Mojang/bedrock-samples@46ba6ea9
# behavior_pack/loot_tables/empty.json, the drop-nothing table station
# adapters already name).
_VANILLA_LOOT_TABLES = frozenset({"loot_tables/empty.json"})


def _check_block(report: ValidationReport, path: Path, rel: str, pack_root: Path) -> None:
    data = _load(report, path, rel)
    if data is None:
        return
    if not isinstance(data, dict):
        _shape_error(report, rel, data, ("minecraft:block",))
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
    # minecraft:loot is a path relative to the behavior pack, at most 256
    # characters (learn.microsoft.com, Block Components Documentation -
    # minecraft:loot). A table that isn't there leaves the block dropping
    # nothing, so a missing file is an error (#299).
    for where, comps in [("components", components)] + [
            (f"permutations[{i}].components", p.get("components") or {})
            for i, p in enumerate(body.get("permutations") or []) if isinstance(p, dict)]:
        loot = comps.get("minecraft:loot") if isinstance(comps, dict) else None
        if loot is None:
            continue
        if not isinstance(loot, str) or not loot or len(loot) > 256:
            report.add(rel, "block.loot", f"{where}.minecraft:loot must be a pack path of at most 256 characters")
        elif loot not in _VANILLA_LOOT_TABLES and not (pack_root / loot).is_file():
            report.add(rel, "block.loot", f"{where}.minecraft:loot names {loot}, which the pack doesn't ship; "
                       "the block would drop nothing")
    # A tag:<name> component adds a block tag; it isn't a custom component
    # (learn.microsoft.com, Block Documentation - tag:). Block format 1.26.20
    # removed it (bedrock.dev Block Format History) (#293).
    custom = [c for c in components if ":" in c and not c.startswith(("minecraft:", "tag:"))]
    tagged = [c for c in components if c.startswith("tag:")]
    if tagged and _format_tuple(data.get("format_version")) >= (1, 26, 20):
        report.add(rel, "block.tag_component",
                   f"component {tagged[0]!r}: block format 1.26.20 removed tag:* components")
    if custom and _format_tuple(data.get("format_version")) < _CUSTOM_COMPONENT_FORMAT:
        report.add(rel, "block.custom_component",
                   f"custom component {custom[0]!r} needs block format_version 1.21.90 or later")
    _check_render_methods(report, rel, body)
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


def _check_render_methods(report: ValidationReport, rel: str, body: dict) -> None:
    """One render method per material_instances object (#262).

    Mojang's block docs (bedrock-samples documentation/Blocks.html,
    minecraft:material_instances): render_method "must be the same for each".
    BDS 1.26.52.3 logs "MaterialInstances can't mix and match opaque and
    transparent materials" as an error and warns on any other mix. Checked on
    the block's components, each permutation's, and their item_visual; an
    instance without render_method is opaque (the documented default)."""
    places = [("components", body.get("components"))]
    places += [(f"permutations[{i}]", p.get("components")) for i, p in enumerate(body.get("permutations") or [])
               if isinstance(p, dict)]
    for where, components in places:
        if not isinstance(components, dict):
            continue
        visual = components.get("minecraft:item_visual")
        for label, instances in (
            ("minecraft:material_instances", components.get("minecraft:material_instances")),
            ("minecraft:item_visual", visual.get("material_instances") if isinstance(visual, dict) else None),
        ):
            if not isinstance(instances, dict):
                continue
            methods = sorted({str(spec.get("render_method", "opaque")) for spec in instances.values()
                              if isinstance(spec, dict)})
            if len(methods) > 1:
                report.add(rel, "block.render_method",
                           f"{where} {label}: instances mix render methods {methods}; Bedrock needs one "
                           "render_method for every instance of a block")


_AUDIO_EXTENSIONS = (".ogg", ".fsb", ".wav")


def _check_sound_definitions(report: ValidationReport, path: Path, rel: str, pack_root: Path) -> None:
    """Every sound a definition names has audio the player will have.

    Bedrock loads a definition pointing at nothing and the sound is silent in
    game, so this is a warning (mct reports it as UNLINK). A name resolves when
    the pack ships it as .ogg/.fsb/.wav or Bedrock's vanilla pack has it. With
    the vanilla list not cached (``portkit reference fetch``), only the pack's
    own audio resolves and the warning says so.
    """
    data = _load(report, path, rel)
    if data is None:
        return
    definitions = data.get("sound_definitions") if isinstance(data, dict) else None
    if not isinstance(definitions, dict):
        report.add(rel, "sound.shape", "sound_definitions.json needs a sound_definitions object")
        return
    vanilla = bedrock_vanilla_sounds()
    for event, body in definitions.items():
        sounds = body.get("sounds") if isinstance(body, dict) else None
        for i, sound in enumerate(sounds if isinstance(sounds, list) else []):
            name = sound.get("name") if isinstance(sound, dict) else sound
            if not isinstance(name, str):
                report.add(rel, "sound.name", f"{event}: sounds[{i}] has no name")
                continue
            if (vanilla is not None and name in vanilla) or any(
                (pack_root / f"{name}{ext}").is_file() for ext in _AUDIO_EXTENSIONS
            ):
                continue
            if vanilla is None:
                message = (
                    f"{event}: sounds[{i}] {name!r} is not in the pack, and Bedrock's vanilla "
                    f"sound list isn't cached to check it (run `{FETCH_COMMAND}`)"
                )
            else:
                message = f"{event}: sounds[{i}] {name!r} is not in the pack or Bedrock's vanilla audio"
            report.add(rel, "sound.missing", message, "warning")


def _check_lang(report: ValidationReport, path: Path, rel: str) -> None:
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "=" not in line:
            report.add(rel, "lang.syntax", f"line {lineno} has no '='")


_LOOT_FUNCTIONS = {"set_count", "explosion_decay", "set_data", "looting_enchant"}
# The entry conditions the converter writes (#299): Bedrock's match_tool with
# item-tag filters (learn.microsoft.com, Loot and Trade Table Conditions,
# match_tool: count, durability, enchantments, item and the three
# minecraft:match_tool_filter_* tag lists).
_MATCH_TOOL_KEYS = {"condition", "count", "durability", "enchantments", "item",
                    "minecraft:match_tool_filter_any", "minecraft:match_tool_filter_all",
                    "minecraft:match_tool_filter_none"}
_MATCH_TOOL_FILTERS = ("minecraft:match_tool_filter_any", "minecraft:match_tool_filter_all",
                       "minecraft:match_tool_filter_none")


def _check_loot_conditions(report: ValidationReport, rel: str, where: str, conditions) -> None:
    if conditions is None:
        return
    if not isinstance(conditions, list):
        report.add(rel, "loot.condition", f"{where}.conditions must be a list")
        return
    for k, condition in enumerate(conditions):
        at = f"{where}.conditions[{k}]"
        if not isinstance(condition, dict) or condition.get("condition") != "match_tool":
            report.add(rel, "loot.condition", f"{at} must be a match_tool condition")
            continue
        unknown = sorted(set(condition) - _MATCH_TOOL_KEYS)
        if unknown:
            report.add(rel, "loot.condition", f"{at} has fields match_tool doesn't take: {', '.join(unknown)}")
        filters = [f for f in _MATCH_TOOL_FILTERS if f in condition]
        if not filters and "item" not in condition and "enchantments" not in condition:
            report.add(rel, "loot.condition", f"{at} tests nothing")
        for f in filters:
            tags = condition[f]
            if not isinstance(tags, list) or not tags or not all(
                    isinstance(t, str) and _IDENTIFIER.match(t) for t in tags):
                report.add(rel, "loot.condition", f"{at}.{f} must be a non-empty list of item tag identifiers")


def _check_loot_table(report: ValidationReport, path: Path, rel: str) -> None:
    """A loot table Bedrock will actually load.

    Bedrock fails quietly on a malformed table: the block simply drops nothing,
    which is exactly the wrong-but-looks-fine outcome this project exists to
    catch, so the shape is checked here rather than in the converter alone.
    """
    data = _load(report, path, rel)
    if data is None:
        return
    if not isinstance(data, dict):
        _shape_error(report, rel, data, ("pools",))
        return
    pools = data.get("pools")
    if not isinstance(pools, list) or not pools:
        report.add(rel, "loot.pools", "table has no pools")
        return
    for i, pool in enumerate(pools):
        if not isinstance(pool, dict):
            report.add(rel, "loot.pools", f"pools[{i}] must be a JSON object")
            continue
        rolls = pool.get("rolls")
        if not isinstance(rolls, (int, float)):
            report.add(rel, "loot.rolls", f"pools[{i}].rolls must be a number")
        entries = pool.get("entries")
        if not isinstance(entries, list) or not entries:
            report.add(rel, "loot.entries", f"pools[{i}] has no entries")
            continue
        for j, entry in enumerate(entries):
            where = f"pools[{i}].entries[{j}]"
            if not isinstance(entry, dict):
                report.add(rel, "loot.entries", f"{where} must be a JSON object")
                continue
            if entry.get("type") != "item":
                report.add(rel, "loot.entry_type", f"{where}.type must be 'item'")
            name = entry.get("name")
            if not isinstance(name, str) or not _IDENTIFIER.match(name):
                report.add(rel, "loot.name", f"{where}.name {name!r} is not an identifier")
            _check_loot_conditions(report, rel, where, entry.get("conditions"))
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

    # Bedrock loads a pack without an icon and shows a placeholder; Mojang's
    # validator (mct CPACKICON) rejects it for distribution. A warning here, so
    # our own oracle sees what theirs does without failing a loadable pack.
    icon = pack_root / "pack_icon.png"
    if not icon.is_file():
        report.add(
            f"{prefix}/pack_icon.png",
            "pack.icon",
            "pack has no pack_icon.png; Bedrock shows a placeholder in the pack list",
            "warning",
        )
    else:
        size = dimensions(icon.read_bytes())
        if size is None or size[0] != size[1] or size[0] not in _ICON_SIZES:
            found = "not a PNG" if size is None else f"{size[0]}x{size[1]}"
            report.add(
                f"{prefix}/pack_icon.png",
                "pack.icon",
                f"pack_icon.png must be a square PNG of 2-256 px, a power of two; found {found}",
                "warning",
            )

    # Some devices (consoles, mobile) cannot load a file whose pack-relative
    # path is over 100 characters or more than eight directories deep; mct
    # PATHLENGTH is an error for both, and so is this.
    for path in sorted(pack_root.rglob("*")):
        rel = path.relative_to(pack_root).as_posix()
        if path.is_file() and too_long(rel):
            report.add(
                f"{prefix}/{rel}",
                "pack.path_length",
                f"path inside the pack is {len(rel)} characters / {len(rel.split('/'))} segments; "
                f"keep it to {MAX_PATH} characters and {MAX_SEGMENTS} segments",
            )

    for path in sorted((pack_root / "recipes").glob("*.json")):
        _check_recipe(report, path, f"{prefix}/recipes/{path.name}")

    _check_scripts(report, pack_root, prefix)
    _check_smithing_bases(report, pack_root, prefix)
    _check_smithing_trims(report, pack_root, prefix)

    for path in sorted((pack_root / "blocks").glob("*.json")):
        _check_block(report, path, f"{prefix}/blocks/{path.name}", pack_root)

    for path in sorted((pack_root / "loot_tables").rglob("*.json")):
        _check_loot_table(report, path, f"{prefix}/{path.relative_to(pack_root).as_posix()}")

    for folder, expected in _DOCUMENT_KEYS.get(prefix, {}).items():
        for path in sorted((pack_root / folder).rglob("*.json")):
            _check_document(report, path, f"{prefix}/{path.relative_to(pack_root).as_posix()}", expected)

    for index in ("textures/terrain_texture.json", "textures/item_texture.json"):
        path = pack_root / index
        if path.is_file():
            _check_texture_index(report, path, f"{prefix}/{index}", pack_root)

    flipbook = pack_root / "textures" / "flipbook_textures.json"
    if flipbook.is_file():
        _check_flipbook(report, flipbook, f"{prefix}/textures/flipbook_textures.json", pack_root)

    sound_definitions = pack_root / "sounds" / "sound_definitions.json"
    if sound_definitions.is_file():
        _check_sound_definitions(
            report, sound_definitions, f"{prefix}/sounds/sound_definitions.json", pack_root
        )

    lang = pack_root / "texts" / "en_US.lang"
    if lang.is_file():
        _check_lang(report, lang, f"{prefix}/texts/en_US.lang")

    return report


def _definitions(pack_root: Path, folder: str, key: str) -> dict[str, dict]:
    """identifier -> components of each definition under ``folder`` (unreadable ones skipped)."""
    found = {}
    for path in sorted((pack_root / folder).rglob("*.json")):
        try:
            body = json.loads(path.read_text(encoding="utf-8")).get(key)
        except (ValueError, OSError, AttributeError):
            continue
        if isinstance(body, dict):
            description = body.get("description")
            ident = description.get("identifier") if isinstance(description, dict) else None
            if isinstance(ident, str):
                found[ident] = body.get("components") if isinstance(body.get("components"), dict) else {}
    return found


def _check_smithing_bases(report: ValidationReport, pack_root: Path, prefix: str) -> None:
    """A smithing recipe's base from this pack is armor or a tool (#268).

    Mojang bedrock-samples documentation/Recipes.html, recipe_smithing_transform:
    the base's "only accepted items are armor and tools"; BDS 1.26.52.3 refuses
    a base without minecraft:durability ("base item is not a piece of armor or
    equipment", #263). Checked for bases the pack defines (a block, or an item
    without durability) and for vanilla bases, against Bedrock's vanilla data
    (portkit.data.smithing_bases, #270: minecraft:stick is not armor or a
    tool); other ids the pack doesn't define are other rules' business.

    ``recipe.smithing_slot`` (#305): the template and addition must carry
    ``minecraft:transform_templates`` / ``minecraft:transform_materials``
    (learn.microsoft.com, Recipe Documentation - Smithing Transform Recipe;
    BDS 1.26.52.3 refuses the recipe otherwise): a vanilla item must be
    Bedrock's own member (portkit.data.smithing_bases), the pack's item must
    carry the tag, and the pack's block (no item definition) can't."""
    recipes = sorted((pack_root / "recipes").glob("*.json"))
    if not recipes:
        return
    items = blocks = None
    for path in recipes:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        body = data.get("minecraft:recipe_smithing_transform") if isinstance(data, dict) else None
        if isinstance(body, dict):
            for slot in ("template", "addition"):
                ident = body.get(slot)
                if not isinstance(ident, str) or ":" not in ident:
                    continue
                if ident.startswith("minecraft:"):
                    refusal = vanilla_slot_refusal(slot, ident)
                else:
                    if items is None:
                        items = _definitions(pack_root, "items", "minecraft:item")
                        blocks = _definitions(pack_root, "blocks", "minecraft:block")
                    if ident in items:
                        refusal = addon_slot_refusal(slot, ident, "item", items[ident])
                    elif ident in blocks:
                        refusal = addon_slot_refusal(slot, ident, "block", None)
                    else:
                        refusal = None  # not this pack's: other rules' business
                if refusal:
                    report.add(f"{prefix}/recipes/{path.name}", "recipe.smithing_slot", f"smithing {refusal}")
        base = body.get("base") if isinstance(body, dict) else None
        if not isinstance(base, str):
            continue
        if base.startswith("minecraft:"):
            refusal = vanilla_base_refusal(base)
            if refusal:
                report.add(f"{prefix}/recipes/{path.name}", "recipe.smithing_base",
                           f"smithing base {refusal}; Bedrock's smithing table takes only armor and tools "
                           "as the base")
            continue
        if items is None:
            items = _definitions(pack_root, "items", "minecraft:item")
            blocks = _definitions(pack_root, "blocks", "minecraft:block")
        rel = f"{prefix}/recipes/{path.name}"
        if base in items:
            if not isinstance(items[base].get("minecraft:durability"), dict):
                report.add(rel, "recipe.smithing_base",
                           f"smithing base {base} has no minecraft:durability; Bedrock's smithing table takes "
                           "only armor and tools as the base")
        elif base in blocks:
            report.add(rel, "recipe.smithing_base",
                       f"smithing base {base} is a block; Bedrock's smithing table takes only armor and tools "
                       "as the base")


_TRIM_KEY = "minecraft:recipe_smithing_trim"


def _check_smithing_trims(report: ValidationReport, pack_root: Path, prefix: str) -> None:
    """Every trim recipe's slots are ones Bedrock takes, and no item's trim tag
    puts an item Bedrock refuses into Mojang's own trim recipe (#272,
    :mod:`portkit.data.trim_items`).

    ``recipe.smithing_trim``: a slot's tag must be that slot's Bedrock tag; a
    vanilla item must be in it (minecraft.wiki's Bedrock item tag lists); the
    pack's own item can't be a template or an addition (an add-on can't
    register a trim pattern or material; BDS 1.26.52.3 refuses it), and as the
    base it must be wearable and carry ``minecraft:trimmable_armors``. Ids the
    pack doesn't define are other rules' business.

    ``item.trim_tag``: an item of the pack carrying ``minecraft:trim_templates``
    or ``minecraft:trim_materials``, or ``minecraft:trimmable_armors`` without
    ``minecraft:wearable``, puts an item Bedrock refuses into Mojang's own
    ``minecraft:smithing_armor_trim``, which BDS then reports as an error.
    """
    items = _definitions(pack_root, "items", "minecraft:item")
    for path in sorted((pack_root / "items").rglob("*.json")):
        try:
            body = json.loads(path.read_text(encoding="utf-8")).get("minecraft:item")
        except (ValueError, OSError, AttributeError):
            continue
        description = body.get("description") if isinstance(body, dict) else None
        ident = description.get("identifier") if isinstance(description, dict) else None
        components = body.get("components") if isinstance(body, dict) else None
        if not isinstance(ident, str) or ident.startswith("minecraft:") or not isinstance(components, dict):
            continue
        refusal = trim_items.item_tag_refusal(ident, components)
        if refusal:
            report.add(f"{prefix}/{path.relative_to(pack_root).as_posix()}", "item.trim_tag", refusal)
    blocks = None
    for path in sorted((pack_root / "recipes").glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        body = data.get(_TRIM_KEY) if isinstance(data, dict) else None
        if not isinstance(body, dict):
            continue
        rel = f"{prefix}/recipes/{path.name}"
        for slot in ("template", "base", "addition"):
            found = trim_items.slot_value(body.get(slot))
            if found is None:
                continue  # an empty slot is _check_recipe's
            kind, ident = found
            if kind == "tag" or ident.startswith("minecraft:"):
                refusal = trim_items.vanilla_refusal(slot, kind, ident)
            else:
                if blocks is None:
                    blocks = _definitions(pack_root, "blocks", "minecraft:block")
                if ident not in items and ident not in blocks:
                    refusal = None  # not this pack's: other rules' business
                elif slot != "base":
                    refusal = trim_items.addon_refusal(slot, ident)
                else:
                    refusal = trim_items.addon_base_refusal(ident, items.get(ident))
            if refusal:
                report.add(rel, "recipe.smithing_trim", f"trim {refusal}")


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
            if isinstance(dep, dict) and "module_name" in dep:
                continue  # a built-in script module, checked with the manifest
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
        # A mod with nothing Bedrock can hold is reported, not packed (#279):
        # a tree holding a well-formed explained-empty.json and no packs is
        # that outcome, not an empty conversion.
        from ..codeonly import REPORT_NAME, read_report

        explained = read_report(tree)
        if explained is not None:
            report.add(str(tree / REPORT_NAME), "tree.explained_empty",
                       "explained-empty: no pack, nothing converts (" + ", ".join(
                           r["class"] for r in explained["reason_classes"]) + ")", severity="info")
            return report
        report.add(str(tree), "tree.empty", "no behavior_pack/ or resource_pack/ found")
        return report
    for pack in packs:
        report.findings.extend(validate_pack(pack).findings)
    _check_dependencies(report, packs)
    check_collisions(report, tree)
    check_cross_pack(report, tree)
    return report
