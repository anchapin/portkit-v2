"""Farmer's Delight stove: data table + fixed Script API runtime (#177).

The third station on the cutting board's pattern (:mod:`portkit.converters.stations`,
docs/decisions.md). FD's stove is a lit/unlit block with six cooking spots on
top that run vanilla ``minecraft:campfire_cooking`` recipes
(``StoveBlockEntity`` hands ``RecipeType.CAMPFIRE_COOKING`` to
``AbstractStoveBlockEntity``'s recipe lookup). So the table is every campfire
recipe this conversion can state exactly: vanilla's own (fetched reference
data, :mod:`portkit.data.recipes`) and the jar's, whose load conditions passed
(they still convert as Bedrock campfire recipes too). A jar recipe that can't
be stated stays ``station_recipe`` residue with the reason; a vanilla recipe
that can't is a note. Nothing is narrowed or guessed (#87).

The runtime (``portkit/runtime/stove.js`` and its node-tested logic
``stove_core.js``) does what FD's ``AbstractStoveBlock`` /
``AbstractStoveBlockEntity`` do, cited per line there and in the table's
header: lighting it (flint and steel, fire charge), putting it out (an item
that can ``shovel_dig``, a water bucket), placing food on it, cooking while
lit and cooling while not, dropping the food when something covers the top,
burning what stands on it unless it sneaks, the crackle, and the lit state's
light. The food drawn on top is a block-entity renderer in Java; Bedrock custom
blocks have none, so the action bar says what is cooking instead.

The block is the jar's own blockstate (facing x lit, two plain cube models)
converted by :mod:`portkit.converters.blocks` with :data:`STOVE_BLOCKS`. Lit,
it is a heat source for the cooking pot (FD's ``farmersdelight:heat_sources``
tag names it): :data:`HEAT_RULES` is what :mod:`portkit.converters.cooking_pot`
reads.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from ...conditions import LoadContext
from ...data import FETCH_COMMAND
from ...data.recipes import campfire_recipes
from ...model import ConversionResult, SourceMod, Unhandled
from ...converters.recipes import emitted_definitions
from .cutting_board import (
    CAMPFIRE,
    FD_FAB,
    FD_NEO,
    RESIDUE_KIND,
    SCRIPT_FORMAT,
    SCRIPT_MODULE,
    SCRIPT_VERSION,
    FacingBlock,
    _js_module,
    _Refuse,
    _Resolver,
    _recipe_id,
    _RUNTIME_DIR,
    _src,
    _unsupported,
    runtime_source,
)

STATION = "stove"
LIT_STATE = "farmersdelight:lit"
# Same cadence as the cooking pot (approved, #191): the block's minecraft:tick
# interval; the runtime advances Java's per-tick counters by this many ticks.
# Every corpus campfire cookingtime (600) is a multiple of it, so food is done
# on the same tick count as Java.
TICK_INTERVAL = 10
SLOTS = 6  # StoveBlockEntity#getInventorySlotCount


def _blk(repo, line: str) -> str:
    return _src(repo, "common/block/AbstractStoveBlock.java", line)


def _be(repo, line: str) -> str:
    return _src(repo, "common/block/entity/AbstractStoveBlockEntity.java", line)


def _reg(repo, line: str) -> str:
    return _src(repo, "common/registry/ModBlocks.java", line)


# AbstractStoveBlock: FACING and LIT (default north, unlit), placed facing the
# player (getHorizontalDirection().getOpposite(): offset 180) and lit; no
# getShape override, so a full cube. ModBlocks: light 13 while lit
# (litBlockEmission(13)), 0 otherwise.
STOVE_BLOCKS = {
    "neoforge": FacingBlock(
        "stove", 180, {"origin": [-8, 0, -8], "size": [16, 16, 16]},
        (_blk(FD_NEO, "53-L64"), _blk(FD_NEO, "167-L172"), _reg(FD_NEO, "32-L34"), _reg(FD_NEO, "45-L46")),
        java_state="lit", values=("false", "true"), state=LIT_STATE,
        value_components={"true": {"minecraft:light_emission": 13}},
    ),
    "fabric": FacingBlock(
        "stove", 180, {"origin": [-8, 0, -8], "size": [16, 16, 16]},
        (_blk(FD_FAB, "45-L56"), _blk(FD_FAB, "170-L175"), _reg(FD_FAB, "30-L32"), _reg(FD_FAB, "80-L81")),
        java_state="lit", values=("false", "true"), state=LIT_STATE,
        value_components={"true": {"minecraft:light_emission": 13}},
    ),
}

# The cooking pot's heat rule for a converted stove (HeatableBlockEntity#isHeated:
# a heat source with LIT heats only while lit), by Java block id: the Bedrock
# block and the custom state value that says lit.
HEAT_RULES = {"farmersdelight:stove": {"id": "farmersdelight:stove", "lit": {LIT_STATE: "true"}}}

# Vanilla crafting remainders the water-bucket branch needs: Java's
# tryToExtinguish puts the held bucket's crafting remainder in the hand
# (NeoForge getCraftingRemainingItem, Refabricated getCraftingRemainder). The
# water bucket's is the bucket (minecraft.wiki, "Hardcoded item properties
# (Java Edition)", craft remainder table).
WATER_REMAINDERS = {"minecraft:water_bucket": "minecraft:bucket"}

# FD's damage type stove_burn (data/farmersdelight/damage_type/stove_burn.json:
# effects burning, exhaustion 0.1, scaling when_caused_by_living_non_player)
# is vanilla's campfire damage type field for field (misode/mcmeta
# 1.21.1-summary data/damage_type/data.json "campfire") and sits in the same
# vanilla damage tags (is_fire, burn_from_stepping, no_knockback; FD adds
# panic_environmental_causes). Bedrock's cause of the same meaning is
# EntityDamageCause.campfire (@minecraft/server 2.0.0).
BURN = {"amount": 1.0, "cause": "campfire"}


def _sources(loader: str) -> tuple[str, ...]:
    neo = loader == "neoforge"
    repo = FD_NEO if neo else FD_FAB
    block = (
        {"use": "66-L77", "ignite": "79-L103", "extinguish": "105-L125", "place": "127-L138",
         "burn": "174-L186", "remove": "188-L195", "covered": "197-L205"}
        if neo else
        {"use": "65-L76", "ignite": "78-L102", "extinguish": "104-L127", "place": "129-L141",
         "burn": "177-L189", "covered": "191-L199"}
    )
    be = (
        {"tick": "95-L108", "cook": "110-L137", "cool": "139-L150", "place": "157-L179", "slot": "223-L231"}
        if neo else
        {"remove": "91-L97", "tick": "116-L129", "cook": "131-L156", "cool": "158-L169", "place": "178-L200",
         "slot": "244-L252"}
    )
    out = [*(_blk(repo, v) for v in block.values()), *(_be(repo, v) for v in be.values())]
    out.append(_src(repo, "common/block/StoveBlock.java", "280-L287" if neo else "51-L59"))  # crackle
    out.append(_src(repo, "common/block/entity/StoveBlockEntity.java", "16" if neo else "15"))  # CAMPFIRE_COOKING
    out.append(_src(repo, "common/block/entity/StoveBlockEntity.java", "280-L283" if neo else "48-L50"))  # 6 slots
    out.append(_src(repo, "common/utility/ItemUtils.java", "42-L45" if neo else "44-L47"))  # dropItems
    return tuple(out)


SHARED_SOURCES = (
    "https://minecraft.wiki/w/Java_Edition_hardcoded_item_properties (craft remainder: water bucket -> bucket)",
    "https://minecraft.wiki/w/Damage#Invulnerability_timer (10 game ticks after damage)",
    "https://github.com/misode/mcmeta/blob/7cffbcdad5fa36f22acef6bd4b869ecad4ca3fd9/data/damage_type/data.json",
)


def _stack(entry, role: str, resolve: _Resolver) -> dict:
    if isinstance(entry, str):
        entry = {"id": entry}
    if not isinstance(entry, dict):
        raise _Refuse(f"{role} {json.dumps(entry, sort_keys=True)} is not an item stack")
    ident = entry.get("id", entry.get("item"))
    count = entry.get("count", 1)
    extra = set(entry) - {"id", "item", "count"}
    if extra:
        raise _Refuse(f"{role} {ident} carries {', '.join(sorted(extra))}, which the table doesn't hold")
    if not isinstance(ident, str) or not isinstance(count, int) or count < 1:
        raise _Refuse(f"{role} {json.dumps(entry, sort_keys=True)} has no readable id and count")
    return {"item": resolve.item(ident, role), "count": count}


def _entry(ident: str, recipe: dict, resolve: _Resolver) -> dict:
    if recipe.get("type") != CAMPFIRE:
        raise _Refuse(f"not a {CAMPFIRE} recipe")
    if "ingredient" not in recipe:
        raise _Refuse("a campfire recipe has one ingredient (AbstractCookingRecipe)")
    items, _ = resolve.ingredient(recipe["ingredient"], "ingredient")
    result = _stack(recipe.get("result"), "result", resolve)
    cooktime = recipe.get("cookingtime")
    if cooktime is None:
        raise _Refuse("no cookingtime; the default Java fills in is in Minecraft's code, which this "
                      "table doesn't cite")
    if not isinstance(cooktime, int) or cooktime < 1:
        raise _Refuse(f"unreadable cookingtime {cooktime!r}")
    return {"id": ident, "ingredient": sorted(items), "result": result, "cookingtime": cooktime}


def _overlaps(entries: list[dict]) -> dict[str, list[str]]:
    """Recipes that share an ingredient item: Java cooks whichever its recipe
    manager finds first (RecipeManager quickCheck), an order no file states."""
    clash: dict[str, list[str]] = {}
    for i, a in enumerate(entries):
        for b in entries[i + 1:]:
            if set(a["ingredient"]) & set(b["ingredient"]):
                clash.setdefault(a["id"], []).append(b["id"])
                clash.setdefault(b["id"], []).append(a["id"])
    return clash


def _sound(bedrock: str | None, volume: float, pitch: float, **extra) -> dict | None:
    return {"id": bedrock, "volume": volume, "pitch": pitch, **extra} if bedrock else None



@dataclass
class CampfireTable:
    """Every campfire recipe a station can state exactly (the stove's table; the
    skillet cooks the same one): the jar's whose load conditions passed, then
    vanilla's from the fetched reference unless the jar replaces one by id."""

    kept: list[dict]
    jar_kept: int
    residue: list[tuple[str, str]]  # (jar recipe path, why it isn't in the table)
    notes: list[str]
    vanilla: dict | None
    chosen: object


def campfire_table(mod: SourceMod, deferred: list[tuple[str, dict]], files: dict, context: LoadContext,
                   label: str) -> CampfireTable:
    """The campfire recipe table, with notes prefixed by the station ``label``."""
    resolve = _Resolver(mod, context.tags, emitted_definitions(files))
    notes: list[str] = []
    residue: list[tuple[str, str]] = []
    candidates: list[tuple[str | None, str, dict]] = []
    for rel, recipe in sorted(deferred, key=lambda d: d[0]):
        candidates.append((rel, _recipe_id(mod, rel), recipe))
    vanilla, chosen = campfire_recipes(mod.minecraft)
    jar_ids = {ident for _, ident, _ in candidates}
    if vanilla is None:
        notes.append(f"{label}: vanilla's campfire recipes aren't cached (run `{FETCH_COMMAND}`), so the {label} "
                     "cooks only this jar's own campfire recipes")
    else:
        for ident, recipe in sorted(vanilla.items()):
            if ident not in jar_ids:
                candidates.append((None, ident, recipe))

    entries: list[tuple[str | None, dict]] = []
    for rel, ident, recipe in candidates:
        try:
            entries.append((rel, _entry(ident, recipe, resolve)))
        except _Refuse as refusal:
            if rel is None:
                notes.append(f"{label}: vanilla campfire recipe {ident} isn't in the table: {refusal}")
            else:
                residue.append((rel, str(refusal)))
    clash = _overlaps([e for _, e in entries])
    kept = []
    for rel, entry in entries:
        if entry["id"] not in clash:
            kept.append(entry)
            continue
        why = (f"another campfire recipe ({', '.join(sorted(clash[entry['id']]))}) takes the same item; "
               "Java cooks whichever its recipe manager finds first, an order no file states")
        if rel is None:
            notes.append(f"{label}: vanilla campfire recipe {entry['id']} isn't in the table: {why}")
        else:
            residue.append((rel, why))
    jar_kept = sum(1 for e in kept if e["id"] in jar_ids)
    return CampfireTable(kept, jar_kept, residue, notes, vanilla, chosen)


def convert(mod: SourceMod, deferred: list[tuple[str, dict]], files: dict,
            context: LoadContext) -> tuple[ConversionResult, str]:
    """The stove's data table and runtime, when this jar's stove block converted."""
    result = ConversionResult()
    block = STOVE_BLOCKS.get(mod.loader or "")
    if block is None or _unsupported(mod, STATION, STATION) is not None:
        # Not FD, or an FD version the runtime wasn't read from: the stove block
        # stays residue (station_blocks offers nothing), and the jar's campfire
        # recipes convert as plain Bedrock campfire recipes only.
        return result, ""
    block_path = f"blocks/{block.name}.json"
    block_body = files.get(block_path)
    identifier = f"{mod.namespace}:{block.name}"
    if not (isinstance(block_body, dict)
            and block_body.get("minecraft:block", {}).get("description", {}).get("identifier") == identifier):
        why = f"the stove block ({identifier}) did not convert, so there is no station to run on"
        for rel, _ in deferred:
            result.unhandled.append(Unhandled(rel, RESIDUE_KIND, why))
        return result, ""

    emitted = emitted_definitions(files)
    resolve = _Resolver(mod, context.tags, emitted)
    table_ = campfire_table(mod, deferred, files, context, "stove")
    kept, jar_kept, vanilla, chosen = table_.kept, table_.jar_kept, table_.vanilla, table_.chosen
    notes: list[str] = list(table_.notes)
    for rel, why in table_.residue:
        result.unhandled.append(Unhandled(rel, RESIDUE_KIND, why))

    # Lighting and putting out (AbstractStoveBlock#tryToIgnite / #tryToExtinguish).
    try:
        shovel = resolve.tool({"type": "farmersdelight:item_ability", "action": "shovel_dig"})
    except _Refuse as refusal:
        shovel = {"items": [], "tags": []}
        notes.append(f"stove: {refusal}; no shovel puts the stove out")
    water: dict[str, str] = {}
    try:
        buckets = resolve.tag("c:buckets/water", "water bucket")
    except _Refuse as refusal:
        buckets = []
        notes.append(f"stove: {refusal}; a water bucket doesn't put the stove out")
    for item in buckets:
        left = WATER_REMAINDERS.get(item)
        if left is None:
            notes.append(f"stove: {item} is in c:buckets/water, but what it leaves in the hand (its crafting "
                         "remainder) isn't something this table can cite; it doesn't put the stove out")
            continue
        water[item] = resolve.item(left, "water bucket remainder")

    # Sounds, Java event -> Bedrock event with the same audio files (Java
    # misode/mcmeta 1.21.1-assets sounds.json, Bedrock bedrock-samples
    # sound_definitions.json): item.flintandsteel.use = fire.ignite,
    # item.firecharge.use = item.firecharge.use, block.fire.extinguish =
    # random.fizz, block.lantern.place = block.lantern.place; FD's
    # block.stove.crackle is an event that plays block.campfire.crackle
    # (assets/farmersdelight/sounds.json) = block.campfire.crackle. Volumes and
    # pitches from the calls cited; the shovel's level event
    # (SOUND_EXTINGUISH_FIRE) sets them in Minecraft's code, uncited, so
    # Bedrock's defaults.
    sounds = {
        "flint_and_steel": _sound("fire.ignite", 1.0, 1.0, pitch_min=0.8, pitch_max=1.2),
        "fire_charge": _sound("item.firecharge.use", 1.0, 1.0, pitch_spread=0.2),
        "shovel": _sound("random.fizz", 1.0, 1.0),
        "water": _sound("random.fizz", 1.0, 1.0),
        "place": _sound("block.lantern.place", 0.5, 1.0),
        "crackle": _sound("block.campfire.crackle", 1.0, 1.0, chance_per_tick=0.1),
        "break": _sound("random.break", 1.0, 1.0),
    }

    component = f"{mod.namespace}:portkit_stove"
    table = {
        "block": identifier,
        "burn": BURN,
        "component": component,
        "extinguish": {"shovel": shovel, "water": water},
        # FlintAndSteelItem / FireChargeItem: Java checks the item's class;
        # vanilla's items of those classes. A mod item subclassing them isn't
        # recognised (its class isn't data).
        "ignite": {"fire_charge": ["minecraft:fire_charge"], "flint_and_steel": ["minecraft:flint_and_steel"]},
        "lit_state": LIT_STATE,
        "recipes": sorted(kept, key=lambda e: e["id"]),
        "slots": SLOTS,
        "sounds": sounds,
        "tick_interval": TICK_INTERVAL,
    }
    data_path = f"{_RUNTIME_DIR}/data/{mod.namespace}_stove.js"
    vanilla_source = [f"//   {chosen.label}: {chosen.url}\n"] if (vanilla is not None and chosen) else []
    header = (
        f"// Generated by portkit from {mod.namespace}'s and vanilla's {CAMPFIRE} recipes; do not edit.\n"
        f"// Read by the fixed runtime {_RUNTIME_DIR}/stove.js (portkit/runtime). Sources:\n"
        + "".join(f"//   {s}\n" for s in (*_sources(mod.loader), *block.sources, *SHARED_SOURCES))
        + "".join(vanilla_source)
    ).rstrip("\n")
    result.files[data_path] = _js_module(header, table)
    result.files[f"{_RUNTIME_DIR}/stove.js"] = runtime_source("stove.js")
    result.files[f"{_RUNTIME_DIR}/stove_core.js"] = runtime_source("stove_core.js")

    body = json.loads(json.dumps(block_body))
    body["format_version"] = SCRIPT_FORMAT
    components = body["minecraft:block"].setdefault("components", {})
    components[component] = {}
    components["minecraft:tick"] = {"interval_range": [TICK_INTERVAL, TICK_INTERVAL], "looping": True}
    result.files[block_path] = body

    result.stations[CAMPFIRE] = {
        "converted": len(kept),
        "residue": len(deferred) - jar_kept,
        "data": data_path,
        "block": identifier,
        "vanilla": len(kept) - jar_kept,
    }
    result.notes.extend(dict.fromkeys(notes))
    result.notes.append(
        f"{identifier}: cooks {len(kept)} {CAMPFIRE} recipes ({jar_kept} of this jar's {len(deferred)}, "
        f"{len(kept) - jar_kept} of vanilla's) through a Script API runtime ({SCRIPT_MODULE} {SCRIPT_VERSION}, "
        f"{data_path}), as Farmer's Delight's stove does: placed lit; use flint and steel or a fire charge on an "
        "unlit stove to light it, a shovel or a water bucket on a lit one to put it out; use a food a campfire "
        "recipe takes to put one on a free spot (six), unless something covers the top; while lit each item "
        "cooks for its recipe's cookingtime and pops out on top, while unlit it cools; covering the top drops "
        "the food; what stands on a lit stove without sneaking takes 1 fire damage every 10 ticks; lit, it "
        "gives light 13 and heats a cooking pot. The food on top is drawn by a block-entity renderer in Java, "
        "which Bedrock custom blocks don't have: using the stove shows what is cooking in the action bar "
        "instead. Not carried over: the food drawn on top, smoke and flame particles, the stove's own "
        "items when something other than a player destroys it (no break event for that in script API 2.0.0), "
        "what counts as covering the top (Java tests the block above's shape against the grilling area; "
        "scripts can't read shapes, so any block above that isn't air or a liquid covers it), the burn "
        "test's bounding box (an entity standing on the stove, its feet over the stove's own column), "
        "the pathfinding penalty, dispensers and hoppers, mod items that are flint and steel or fire "
        "charges by class, the cooked item's feature-flag check, and the experience a furnace would "
        "give (the stove gives none in Java either). Stored stacks keep their id, name, lore, durability "
        "damage and enchantments only."
    )
    entry = (
        'import { registerStove } from "./stove.js";\n'
        f'import stoveTable from "./data/{mod.namespace}_stove.js";\n'
        "registerStove(stoveTable);\n"
    )
    return result, entry
