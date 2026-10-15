"""Farmer's Delight feasts: data table + fixed Script API runtime (#177).

The last piece of #177 on the cutting board's pattern
(:mod:`portkit.converters.stations`, docs/decisions.md). A feast is a placed
meal (roast chicken, stuffed pumpkin, honey glazed ham, shepherd's pie,
gleaming salad, rice roll medley) that serves portions: using it with the
serving's container (a bowl) gives one serving and counts the ``servings``
block state down; a feast with leftovers lingers at 0 servings and is cleared
by one more use, dropping what its loot table says; one without vanishes with
its last serving.

Where each value comes from (no fabrication, #87):

* **Which blocks, and how many servings**: the jar's blockstates. A feast is
  a block in FD's own ``farmersdelight:feasts`` block tag whose blockstate is
  ``facing`` x ``servings``; the serving count is the blockstate's highest
  ``servings`` value (4, or 8 for the rice roll medley), Java's default state.
* **What is left at the end, and what breaking drops**: the jar's loot table,
  pool by pool, decided for each ``servings`` value (FD's tables gate pools on
  ``servings`` = full or not). It becomes one Bedrock loot table per distinct
  drop set, set per serving count with ``minecraft:loot`` on the block's
  permutations; the runtime clears a block with ``setblock ... destroy``, so
  using up a feast drops through the same tables.
* **The serving item, its container, and whether the block lingers**: only in
  FD's Java code (``ModBlocks`` passes the serving item and ``hasLeftovers`` to
  ``FeastBlock``; ``ModItems`` gives bowl foods ``craftRemainder(Items.BOWL)``;
  ``RiceRollMedleyBlock#getServingItem`` picks a roll per serving count).
  They are cited per line in :data:`FEASTS` and checked against the jar where
  data can check them: the leftover model and loot pool exist only for a feast
  that lingers, and every serving item must be an item the conversion emitted.
* **Shapes and light**: FD's code (``FeastBlock.SHAPES``, ``BlockShapes``,
  ``GleamingSaladBlock.SHAPE``, ``RiceRollMedleyBlock`` shapes,
  ``ModBlocks.glowingFeastBlockEmission``), cited in :func:`_boxes`.

What Bedrock can't express is in the conversion note and docs/decisions.md.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from ...conditions import LoadContext
from ...model import ConversionResult, SourceMod, Unhandled
from ...converters import models
from ...converters.recipes import emitted_definitions
from .cutting_board import (
    FD_FAB,
    FD_NEO,
    SCRIPT_FORMAT,
    SCRIPT_MODULE,
    SCRIPT_VERSION,
    VANILLA_SOUNDS,
    FacingBlock,
    _js_module,
    _lang_key,
    _RUNTIME_DIR,
    _shipped_sounds,
    _src,
    _unsupported,
    runtime_source,
)

STATION = "feast"
RESIDUE_KIND = "feast"
SERVINGS_STATE = "farmersdelight:servings"
FEAST_TAG = "feasts"  # data/<ns>/tags/block/feasts.json
# Item format that reads minecraft:block_placer's replace_block_item (as the skillet's).
ITEM_FORMAT = "1.21.50"
# Vanilla Bedrock's empty loot table (Mojang/bedrock-samples 46ba6ea9,
# behavior_pack/loot_tables/empty.json), for a serving count that drops nothing.
EMPTY_LOOT = "loot_tables/empty.json"
EMPTY_LOOT_SOURCE = ("https://github.com/Mojang/bedrock-samples/blob/46ba6ea985fb5a92d79a9419198f10dda14c199d/"
                     "behavior_pack/loot_tables/empty.json")
# The Bedrock lang key of a vanilla container's name, for FD's
# "You need a %s to eat this." (Mojang/bedrock-samples 46ba6ea9,
# resource_pack/texts/en_US.lang L5229 item.bowl.name=Bowl).
VANILLA_NAMES = {"minecraft:bowl": "item.bowl.name"}
NAMES_SOURCE = ("https://github.com/Mojang/bedrock-samples/blob/46ba6ea985fb5a92d79a9419198f10dda14c199d/"
                "resource_pack/texts/en_US.lang#L5229")


def _blk(repo, path: str, line: str) -> str:
    return _src(repo, f"common/block/{path}", line)


def _reg(repo, path: str, line: str) -> str:
    return _src(repo, f"common/registry/{path}", line)


@dataclass(frozen=True)
class Feast:
    """One feast block as FD's code builds it.

    ``serving`` is the serving item's path, or for the rice roll medley one
    path per serving count (``serving[n - 1]`` at ``servings`` = n,
    ``RiceRollMedleyBlock#getServingItem``). ``container`` is the serving's
    crafting remainder (the item the player must hold), None when it has none.
    ``shape`` names its Java shape family in :func:`_boxes`. ``light`` is the
    light per serving (``glowingFeastBlockEmission``: servings x 3), else None.
    """

    name: str
    serving: str | tuple[str, ...]
    leftovers: bool
    container: str | None
    shape: str
    sources: tuple[str, ...]
    light: int | None = None
    particles: bool = True


def _feasts(loader: str) -> dict[str, Feast]:
    neo = loader == "neoforge"
    repo = FD_NEO if neo else FD_FAB
    # ModBlocks registrations (serving item, hasLeftovers) and the serving
    # items' properties in ModItems (bowlFoodItem: craftRemainder(Items.BOWL);
    # foodItem: none).
    blocks = _reg(repo, "ModBlocks.java", "328-L340" if neo else "302-L314")
    bowl = _reg(repo, "ModItems.java", "51-L53" if neo else "114-L123")
    plain = _reg(repo, "ModItems.java", "47-L49" if neo else "105-L112")
    meals = _reg(repo, "ModItems.java", "464-L491" if neo else "563-L595")
    rolls = _reg(repo, "ModItems.java", "409-L416" if neo else "486-L493")
    medley = _blk(repo, "RiceRollMedleyBlock.java", "23-L62" if neo else "22-L61")
    salad = _blk(repo, "GleamingSaladBlock.java", "19-L45" if neo else "21-L51")
    light = _reg(repo, "ModBlocks.java", "36-L38" if neo else "34-L36")
    plated = (_blk(repo, "RotatedFeastBlock.java", "27-L30" if neo else "28-L36"),
              _src(repo, "common/BlockShapes.java", "10-L34"),
              _src(repo, "common/utility/ShapeUtils.java", "75-L135"))
    feast = _blk(repo, "FeastBlock.java", "40-L53" if neo else "39-L52")
    return {
        "roast_chicken_block": Feast("roast_chicken_block", "roast_chicken", True, "minecraft:bowl", "roast_chicken",
                                     (blocks, meals, bowl, *plated)),
        "stuffed_pumpkin_block": Feast("stuffed_pumpkin_block", "stuffed_pumpkin", False, "minecraft:bowl", "feast",
                                       (blocks, meals, bowl, feast)),
        "honey_glazed_ham_block": Feast("honey_glazed_ham_block", "honey_glazed_ham", True, "minecraft:bowl",
                                        "honey_glazed_ham", (blocks, meals, bowl, *plated)),
        "shepherds_pie_block": Feast("shepherds_pie_block", "shepherds_pie", True, "minecraft:bowl", "shepherds_pie",
                                     (blocks, meals, bowl, *plated)),
        "gleaming_salad_block": Feast("gleaming_salad_block", "gleaming_salad", True, "minecraft:bowl", "gleaming_salad",
                                      (blocks, meals, bowl, salad, light), light=3),
        # RiceRollMedleyBlock: super(properties, SALMON_ROLL, true, false),
        # riceRollServings cod, cod, salmon x3, kelp slice x3 by servings - 1;
        # the rolls are foodItem (no crafting remainder).
        "rice_roll_medley_block": Feast("rice_roll_medley_block",
                                        ("cod_roll", "cod_roll", "salmon_roll", "salmon_roll", "salmon_roll",
                                         "kelp_roll_slice", "kelp_roll_slice", "kelp_roll_slice"),
                                        True, None, "rice_roll_medley", (blocks, medley, rolls, plain),
                                        particles=False),
    }


FEASTS = {loader: _feasts(loader) for loader in ("neoforge", "fabric")}

# -- shapes ----------------------------------------------------------------------
# Java boxes in pixels (x0, y0, z0, x1, y1, z1), transcribed from FD's code.
# FeastBlock.SHAPES, by servings 0..4.
_FEAST_SHAPES = [(2, 0, 2, 14, 2, 14), (2, 0, 2, 14, 2, 14), (2, 0, 2, 14, 4, 14), (2, 0, 2, 14, 6, 14),
                 (2, 0, 2, 14, 8, 14)]
# BlockShapes: TRAY_SHAPE = TRAY_OUTER_SHAPE minus TRAY_INNER_SHAPE (its
# bounding box is the outer one); the dish shapes, facing north, by servings
# 1..4 (ShapeUtils.buildPlatedFoodShapes: servings 0 is the tray alone,
# servings n the tray or'd with dish n - 1 turned to the facing).
_TRAY = (1, 0, 1, 15, 2, 15)
_DISHES = {
    "roast_chicken": [[(4, 1, 10, 12, 8, 12)], [(4, 1, 8, 12, 8, 12)], [(4, 1, 6, 12, 8, 12)],
                      [(4, 1, 4, 12, 8, 12)]],
    "honey_glazed_ham": [[(4, 1, 3, 12, 3, 11)], [(4, 1, 6, 12, 9, 10)], [(4, 2, 4, 12, 10, 10)],
                         [(4, 2, 2, 12, 10, 10)]],
    "shepherds_pie": [[(2, 1, 8, 8, 8, 14)], [(2, 1, 8, 14, 8, 14)], [(8, 1, 2, 14, 8, 8), (2, 1, 8, 14, 8, 14)],
                      [(2, 1, 2, 14, 8, 14)]],
}
# GleamingSaladBlock.SHAPE, every serving count.
_SALAD = [(3, 0, 3, 13, 2, 13), (2, 2, 2, 14, 6, 14)]
# RiceRollMedleyBlock SHAPE_NORTH_SOUTH (facing on the x axis) and
# SHAPE_EAST_WEST, every serving count.
_MEDLEY = [(2, 1, 1, 14, 3, 15), (2, 0, 3, 14, 2, 5), (2, 0, 11, 14, 2, 13),
           (1, 1, 2, 15, 3, 14), (3, 0, 2, 5, 2, 14), (11, 0, 2, 13, 2, 14)]


def _turned_bounds(boxes: list[tuple]) -> tuple[int, int, int, int]:
    """(low, high, y0, y1) of ``boxes`` turned to all four facings about the
    block's centre: one box that holds the shape whichever way it faces."""
    low = min(min(b[0], b[2], 16 - b[3], 16 - b[5]) for b in boxes)
    y0 = min(b[1] for b in boxes)
    y1 = max(b[4] for b in boxes)
    return low, 16 - low, y0, y1


def _bedrock_box(boxes: list[tuple]) -> dict:
    low, high, y0, y1 = _turned_bounds(boxes)
    return {"origin": [low - 8, y0, low - 8], "size": [high - low, y1 - y0, high - low]}


def _boxes(feast: Feast, top: int) -> dict[int, dict]:
    """The collision/selection box per serving count: the Java shape of that
    count, as the box holding it at every facing (Bedrock's box is one cuboid
    and the block turns by permutation)."""
    if feast.shape == "feast":
        return {n: _bedrock_box([_FEAST_SHAPES[n]]) for n in range(top + 1)}
    if feast.shape in _DISHES:
        dishes = _DISHES[feast.shape]
        return {n: _bedrock_box([_TRAY, *(dishes[n - 1] if n else [])]) for n in range(top + 1)}
    whole = _SALAD if feast.shape == "gleaming_salad" else _MEDLEY
    return {n: _bedrock_box(whole) for n in range(top + 1)}


def _top(feast: Feast) -> int:
    return len(feast.serving) if isinstance(feast.serving, tuple) else 4


def _block(feast: Feast, loader: str) -> FacingBlock:
    """The feast as a station block: facing (getHorizontalDirection().getOpposite():
    offset 180) x an integer ``servings`` state, Java's default (full) first;
    a box per serving count, and the salad's light."""
    top = _top(feast)
    boxes = _boxes(feast, top)
    values = tuple(str(n) for n in range(top, -1, -1))
    components = {}
    for n in range(top + 1):
        comps = {"minecraft:collision_box": boxes[n], "minecraft:selection_box": boxes[n]}
        if feast.light is not None:
            comps["minecraft:light_emission"] = n * feast.light
        components[str(n)] = comps
    repo = FD_NEO if loader == "neoforge" else FD_FAB
    neo = loader == "neoforge"
    return FacingBlock(
        feast.name, 180, boxes[top],
        (_blk(repo, "FeastBlock.java", "141-L143" if neo else "147-L149"), *feast.sources),
        java_state="servings", values=values, state=SERVINGS_STATE, value_components=components, int_state=True,
    )


def _tagged(mod: SourceMod) -> set[str]:
    """The jar's ``farmersdelight:feasts`` block tag, as block names in this namespace."""
    for folder in ("block", "blocks"):
        path = mod.data / "tags" / folder / f"{FEAST_TAG}.json"
        if path.is_file():
            try:
                values = json.loads(path.read_text()).get("values") or []
            except (OSError, json.JSONDecodeError, AttributeError):
                return set()
            prefix = f"{mod.namespace}:"
            return {v[len(prefix):] for v in values if isinstance(v, str) and v.startswith(prefix)}
    return set()


def feast_blocks(mod: SourceMod) -> dict[str, FacingBlock]:
    """The feasts of ``mod`` a runtime makes work, by blockstate name: FD's
    feasts at a version whose code was read, that the jar tags as feasts."""
    if _unsupported(mod, STATION, "feast") is not None:
        return {}
    tagged = _tagged(mod)
    return {name: _block(feast, mod.loader) for name, feast in FEASTS[mod.loader].items() if name in tagged}


def loot_names(mod: SourceMod) -> set[str]:
    """Block loot tables (by name under loot_table/blocks/) the feast converter reads."""
    return set(feast_blocks(mod))


# -- loot --------------------------------------------------------------------------


class _Refuse(Exception):
    pass


def _servings_test(condition: dict, block_id: str) -> tuple[str, bool]:
    """(value, wanted) for FD's pool condition ``servings`` = value, or its
    inversion (wanted False)."""
    inverted = condition.get("condition") == "minecraft:inverted"
    if inverted:
        condition = condition.get("term")
        if not isinstance(condition, dict):
            raise _Refuse("an inverted condition has no term")
    if condition.get("condition") != "minecraft:block_state_property":
        raise _Refuse(f"pool condition {condition.get('condition')!r} is not a servings test")
    if condition.get("block") != block_id:
        raise _Refuse(f"pool tests the state of {condition.get('block')!r}, not this feast")
    props = condition.get("properties")
    if not isinstance(props, dict) or set(props) != {"servings"}:
        raise _Refuse("pool tests a block state other than servings alone")
    value = props["servings"]
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise _Refuse("pool tests servings against a range, not one value")
    return str(value), not inverted


def _drops(table: dict, block_id: str, top: int) -> dict[int, list[str]]:
    """The items dropped at each serving count, read pool by pool."""
    pools = table.get("pools")
    if not isinstance(pools, list):
        raise _Refuse("table has no pools")
    if table.get("functions"):
        raise _Refuse("table-level functions")
    drops: dict[int, list[str]] = {n: [] for n in range(top + 1)}
    for i, pool in enumerate(pools):
        if not isinstance(pool, dict):
            raise _Refuse(f"pools[{i}] is not an object")
        rolls = pool.get("rolls", 1)
        if not isinstance(rolls, (int, float)) or rolls != 1 or pool.get("bonus_rolls", 0) not in (0, 0.0):
            raise _Refuse(f"pools[{i}] does not roll exactly once")
        if pool.get("functions"):
            raise _Refuse(f"pools[{i}] has functions")
        entries = pool.get("entries")
        if not isinstance(entries, list) or len(entries) != 1:
            raise _Refuse(f"pools[{i}] has {len(entries) if isinstance(entries, list) else 'no'} entries, not one")
        entry = entries[0]
        if not isinstance(entry, dict) or entry.get("type") not in ("minecraft:item", "item"):
            raise _Refuse(f"pools[{i}] entry is not an item")
        if set(entry) - {"type", "name"}:
            raise _Refuse(f"pools[{i}] entry carries {', '.join(sorted(set(entry) - {'type', 'name'}))}")
        name = entry.get("name")
        if not isinstance(name, str) or ":" not in name:
            raise _Refuse(f"pools[{i}] entry names {name!r}")
        tests = [_servings_test(c, block_id) for c in pool.get("conditions") or []]
        for n in range(top + 1):
            if all((str(n) == value) == wanted for value, wanted in tests):
                drops[n].append(name)
    return drops


def _loot_files(name: str, drops: dict[int, list[str]], top: int) -> tuple[dict[str, dict], dict[int, str]]:
    """Bedrock loot tables, one per distinct drop set, and the path each serving
    count uses. The full feast's set keeps the Java table's name; an empty set
    is vanilla's empty table."""
    groups: dict[tuple, list[int]] = {}
    for n in range(top, -1, -1):
        groups.setdefault(tuple(drops[n]), []).append(n)
    files: dict[str, dict] = {}
    paths: dict[int, str] = {}
    for items, counts in groups.items():
        if not items:
            path = EMPTY_LOOT
        else:
            low, high = min(counts), max(counts)
            if top in counts:
                stem = name
            elif low == high:
                stem = f"{name}_servings_{low}"
            elif sorted(counts) == list(range(low, high + 1)):
                stem = f"{name}_servings_{low}_to_{high}"
            else:
                stem = f"{name}_servings_{'_'.join(str(c) for c in sorted(counts))}"
            path = f"loot_tables/blocks/{stem}.json"
            files[path] = {"pools": [{"rolls": 1, "entries": [{"type": "item", "name": item, "weight": 1}]}
                                     for item in items]}
        for n in counts:
            paths[n] = path
    return files, paths


# -- the converter -------------------------------------------------------------------


def _icon(mod: SourceMod, name: str, files: dict) -> str | None:
    """The item's flat icon key when its Java item model is one and the texture
    shipped, else None (Bedrock then draws the block)."""
    path = mod.assets / "models" / "item" / f"{name}.json"
    try:
        model = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(model, dict) or model.get("parent") not in ("minecraft:item/generated", "item/generated"):
        return None
    layers = model.get("textures") or {}
    if set(layers) != {"layer0"} or not isinstance(layers["layer0"], str):
        return None
    icon, _ = models.texture_shortname(layers["layer0"], mod.namespace)
    index = (files.get("textures/item_texture.json") or {}).get("texture_data") or {}
    return icon if icon in index else None


def _item(mod: SourceMod, feast: Feast, identifier: str, files: dict) -> dict:
    """The feast's item: the block's own (replace_block_item), one per stack
    (ModItems: PlaceableItem, basicItem().stacksTo(1)), its flat icon."""
    components = {
        "minecraft:block_placer": {"block": identifier, "replace_block_item": True},
        "minecraft:display_name": {"value": f"tile.{identifier}.name"},
        "minecraft:max_stack_size": 1,
    }
    icon = _icon(mod, feast.name, files)
    if icon:
        components["minecraft:icon"] = icon
    return {"format_version": ITEM_FORMAT,
            "minecraft:item": {"description": {"identifier": identifier}, "components": components}}


def _servings_value(condition: str) -> int | None:
    marker = f"q.block_state('{SERVINGS_STATE}') == "
    if marker not in condition:
        return None
    try:
        return int(condition.split(marker, 1)[1].split()[0])
    except (ValueError, IndexError):
        return None


def convert(mod: SourceMod, deferred: list[tuple[str, dict]], files: dict,
            context: LoadContext) -> tuple[ConversionResult, str]:
    """Each feast's runtime entry, loot tables, item and block component.

    ``deferred`` is (source path, table) for the feasts' block loot tables,
    which the loot converter left to this one (:func:`loot_names`).
    """
    result = ConversionResult()
    blocks = feast_blocks(mod)
    tables = {rel.rsplit("/", 1)[-1][:-len(".json")]: (rel, table) for rel, table in deferred}
    if not blocks:
        for rel, _ in deferred:
            result.unhandled.append(Unhandled(rel, RESIDUE_KIND, "no feast runtime for this jar"))
        return result, ""

    ns = mod.namespace
    component = f"{ns}:portkit_feast"
    emitted = emitted_definitions(files)
    shipped = _shipped_sounds(files)
    notes: list[str] = []
    table_feasts: dict[str, dict] = {}
    kept: list[str] = []
    for name, station in sorted(blocks.items()):
        feast = FEASTS[mod.loader][name]
        identifier = f"{ns}:{name}"
        block_path = f"blocks/{name}.json"
        body = files.get(block_path)
        loot = tables.get(name)
        why = None
        if not (isinstance(body, dict)
                and body.get("minecraft:block", {}).get("description", {}).get("identifier") == identifier):
            why = f"the feast block {identifier} did not convert, so there is nothing to serve from"
        top = _top(feast)
        servings = list(feast.serving) if isinstance(feast.serving, tuple) else [feast.serving] * top
        missing = sorted({f"{ns}:{s}" for s in servings if f"{ns}:{s}" not in emitted})
        if why is None and missing:
            why = f"serving item(s) {', '.join(missing)} not converted"
        if why is None and feast.container and not feast.container.startswith("minecraft:") \
                and feast.container not in emitted:
            why = f"container {feast.container} not converted"
        drops = None
        if why is None:
            if loot is None:
                why = f"no loot table for {identifier} in the jar, so what it leaves is unknown"
            else:
                try:
                    drops = _drops(loot[1], identifier, top)
                except _Refuse as refusal:
                    why = f"loot table {loot[0]}: {refusal}"
        if why is None:
            unknown = sorted({d for ds in drops.values() for d in ds
                              if not d.startswith("minecraft:") and d not in emitted and d != identifier})
            if unknown:
                why = f"the loot table drops {', '.join(unknown)}, not converted"
        if why is None:
            # The data's own word on hasLeftovers: a lingering feast drops
            # something at 0 servings (the plate); one that vanishes with its
            # last serving drops nothing there (destroyBlock at 0).
            lingers = bool(drops[0])
            if lingers != feast.leftovers:
                why = (f"FD's code says hasLeftovers={str(feast.leftovers).lower()} but the loot table "
                       f"{'drops' if lingers else 'drops nothing'} at servings 0")
        if why is not None:
            if loot is not None:
                result.unhandled.append(Unhandled(loot[0], RESIDUE_KIND, why))
            notes.append(f"{identifier}: places but does not serve ({why})")
            continue

        loot_files, loot_paths = _loot_files(name, drops, top)
        result.files.update(loot_files)
        result.consumed.add(loot[0])

        new = json.loads(json.dumps(body))
        new["format_version"] = SCRIPT_FORMAT
        block = new["minecraft:block"]
        block.setdefault("components", {})[component] = {}
        # FeastBlock#canSurvive / updateShape: it needs a block below and
        # breaks (with drops) when that goes. Bedrock's placement_filter on
        # the top face does both (learn.microsoft.com, minecraft:placement_filter).
        block["components"]["minecraft:placement_filter"] = {"conditions": [{"allowed_faces": ["up"]}]}
        block["components"]["minecraft:loot"] = loot_paths[top]
        for permutation in block.get("permutations") or []:
            value = _servings_value(permutation.get("condition", ""))
            if value is not None:
                permutation.setdefault("components", {})["minecraft:loot"] = loot_paths[value]
        result.files[block_path] = new
        result.files[f"items/{name}.json"] = _item(mod, feast, identifier, files)

        entry = {
            "container": feast.container,
            "container_name": VANILLA_NAMES.get(feast.container) if feast.container else None,
            "leftovers": feast.leftovers,
            "max_servings": top,
            # servings[n - 1] is served at servings = n.
            "servings": [f"{ns}:{s}" for s in servings],
        }
        if feast.container and entry["container_name"] is None:
            notes.append(f"{identifier}: the container's name has no Bedrock key here; the message names its id")
        table_feasts[identifier] = entry
        kept.append(identifier)

    if not kept:
        result.notes.extend(notes)
        return result, ""

    def sound(java: str, volume: float, pitch: float) -> dict | None:
        bedrock = VANILLA_SOUNDS.get(java) or (java if java in shipped else None)
        return {"id": bedrock, "volume": volume, "pitch": pitch} if bedrock else None

    neo = mod.loader == "neoforge"
    sounds = {
        # takeServing: block.food.take_portion (NeoForge, FD's event, which
        # assets/farmersdelight/sounds.json plays as item.armor.equip_generic)
        # / item.armor.equip_generic (Refabricated), 1.0 / 1.0.
        "serve": sound("minecraft:item.armor.equip_generic", 1.0, 1.0),
        # servings == 0: SoundEvents.WOOD_BREAK at 0.8 / 0.8.
        "clear": sound("minecraft:block.wood.break", 0.8, 0.8),
    }
    message = _lang_key(mod, f"block.{ns}.feast.use_container")
    table = {
        "component": component,
        "feasts": table_feasts,
        "messages": {"use_container": message},
        "servings_state": SERVINGS_STATE,
        "sounds": sounds,
    }
    data_path = f"{_RUNTIME_DIR}/data/{ns}_feast.js"
    repo = FD_NEO if neo else FD_FAB
    sources = [
        _blk(repo, "FeastBlock.java", "103-L138" if neo else "110-L144"),
        _blk(repo, "FeastBlock.java", "145-L153" if neo else "151-L167"),
        *dict.fromkeys(s for name in sorted(blocks) for s in blocks[name].sources),
        EMPTY_LOOT_SOURCE,
        NAMES_SOURCE,
    ]
    header = (
        f"// Generated by portkit from {ns}'s feast blocks, loot tables and Java code; do not edit.\n"
        f"// Read by the fixed runtime {_RUNTIME_DIR}/feast.js (portkit/runtime). Sources:\n"
        + "".join(f"//   {s}\n" for s in sources)
    ).rstrip("\n")
    result.files[data_path] = _js_module(header, table)
    for name in ("feast.js", "feast_core.js"):
        result.files[f"{_RUNTIME_DIR}/{name}"] = runtime_source(name)
    result.stations[f"{ns}:feasts"] = {
        "converted": len(kept),
        "residue": len(blocks) - len(kept),
        "data": data_path,
        "block": ", ".join(kept),
    }
    result.notes.extend(dict.fromkeys(notes))
    result.notes.append(
        f"{ns}: {len(kept)} feast(s) serve through a Script API runtime ({SCRIPT_MODULE} {SCRIPT_VERSION}, "
        f"{data_path}): {', '.join(kept)}. Using a feast with its container (a bowl) in the main hand gives "
        "one serving and counts the servings state down (the container is used up except in creative); a "
        "feast whose servings need no container serves to any hand; with the wrong item the action bar says "
        "which container it needs; at 0 servings a feast with leftovers is cleared by one more use and drops "
        "what its loot table says, and one without leftovers vanishes with its last serving. Breaking drops "
        "per serving count from the jar's loot table (minecraft:loot per permutation). Not carried over: "
        "trying the off-hand when the main hand can't serve (Bedrock's block use is the main hand's), the "
        "serving particles and the gleaming salad's sparkles, the comparator signal, the item-used statistic "
        "and the place-feast advancement, the exact Java shapes (each serving count gets the one box that "
        "holds its shape at every facing), the rigid-support test (any block's top face holds a feast), and "
        "piston popping."
    )
    entry = (
        'import { registerFeasts } from "./feast.js";\n'
        f'import feastTable from "./data/{ns}_feast.js";\n'
        "registerFeasts(feastTable);\n"
    )
    return result, entry
