"""Farmer's Delight skillet: data table + fixed Script API runtime (#177).

The fourth station on the cutting board's pattern (:mod:`portkit.converters.stations`,
docs/decisions.md). FD's skillet is two things at once:

* **A placed block** (``SkilletBlock`` / ``SkilletBlockEntity``) that cooks
  vanilla ``minecraft:campfire_cooking`` recipes over heat: one stack at a
  time, one item after another, each result thrown out to the side. Its heat
  rule is the cooking pot's (``HeatableBlockEntity#isHeated`` over FD's
  ``heat_sources`` / ``heat_conductors`` tags, a converted stove while lit);
  ``support`` (the tray model) follows ``tray_heat_sources`` below.
* **A held item** (``SkilletItem``): an iron-tier weapon that cooks the food in
  the other hand while the player stands near a heat source, places as the
  block only while sneaking, and plays its own hit sound.

The recipe table is the stove's (:func:`portkit.converters.stove.campfire_table`:
the jar's campfire recipes whose load conditions passed and vanilla's from the
fetched reference); recipes the stove can't state are the stove's residue, so
the skillet adds none of its own. Cook times run through FD's skillet rule
(``SkilletBlock#getSkilletCookingTime``) in the runtime, with the skillet's
Fire Aspect level.

The item's numbers come from FD's code and vanilla's iron tier, cited per
field in :func:`_item` (no fabrication, #87). What Bedrock can't express is in
the conversion note and docs/decisions.md.
"""
from __future__ import annotations

import json

from ..conditions import LoadContext
from ..model import ConversionResult, SourceMod
from .cooking_pot import heat_table
from .stations import (
    CAMPFIRE,
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
from .stove import campfire_table

STATION = "skillet"
SUPPORT_STATE = "farmersdelight:support"
# Same cadence as the cooking pot and the stove (approved, #191/#192). Every
# skillet cook time is a whole number of seconds (getSkilletCookingTime rounds
# to multiples of 20 ticks), so a multiple of it.
TICK_INTERVAL = 10
# SkilletBlock: MINIMUM_COOKING_TIME = 60; getSkilletCookingTime's default
# (600 when a recipe has none), its 0.2 reduction and 0.05 per Fire Aspect level.
COOKING = {"default_cooking_time": 600, "fire_aspect_step": 0.05, "min_cooking_time": 60, "reduction": 0.2}
# SkilletBlockEntity#cookAndOutputItems: spawned 0.3 above the block's floor,
# moving 0.08 sideways and 0.25 up.
LAUNCH = {"dy": 0.3, "speed": 0.08, "up": 0.25}
# Item format that reads minecraft:block_placer's replace_block_item
# (learn.microsoft.com, Items Documentation - minecraft:block_placer); the same
# as recipes._BLOCK_ITEM_FORMAT.
ITEM_FORMAT = "1.21.50"


def _blk(repo, line: str) -> str:
    return _src(repo, "common/block/SkilletBlock.java", line)


def _be(repo, line: str) -> str:
    return _src(repo, "common/block/entity/SkilletBlockEntity.java", line)


def _itm(repo, line: str) -> str:
    return _src(repo, "common/item/SkilletItem.java", line)


# SkilletBlock: FACING = context.getHorizontalDirection() (the player's own
# facing, so the placement trait's offset is 0), SUPPORT false/true (false the
# default), SHAPE box(1, 0, 1, 15, 4, 15).
SKILLET_BLOCKS = {
    "neoforge": FacingBlock(
        "skillet", 0, {"origin": [-7, 0, -7], "size": [14, 4, 14]},
        (_blk(FD_NEO, "55-L59"), _blk(FD_NEO, "126-L134")),
        java_state="support", values=("false", "true"), state=SUPPORT_STATE,
    ),
    "fabric": FacingBlock(
        "skillet", 0, {"origin": [-7, 0, -7], "size": [14, 4, 14]},
        (_blk(FD_FAB, "50-L54"), _blk(FD_FAB, "115-L123")),
        java_state="support", values=("false", "true"), state=SUPPORT_STATE,
    ),
}

# Vanilla's iron tier (NeoForge: Tiers.IRON, Refabricated: ToolMaterial.IRON),
# which FD's SkilletItem uses for durability, damage bonus, enchantability and
# repair (minecraft.wiki, "Tiers": iron durability 250, damage bonus 2,
# enchantability 14, repair item iron ingot; the fetched item components agree
# for the iron sword: max_damage 250, enchantable 14 in 26.1).
IRON_TIER = {"durability": 250, "attack_damage_bonus": 2.0, "enchantment_value": 14,
             "repair": "minecraft:iron_ingot"}
TIER_SOURCE = "https://minecraft.wiki/w/Tiers?oldid=3830017 (iron: 250, +2, 14, iron ingot)"
REPAIR_SOURCE = "https://minecraft.wiki/w/Item_repair (unit repair: 25% of maximum durability per unit)"
# ModItems: createAttributes(tier, 5.0F, -3.1F): attack damage 5 + the tier's
# bonus, attack speed -3.1, attack knockback +1 (SkilletItem#createAttributes).
BASE_ATTACK_DAMAGE = 5.0
PLAYER_BASE_DAMAGE = 1.0  # the attack_damage modifier adds to a player's base of 1 (minecraft.wiki, Tiers note a)


def _sources(loader: str) -> tuple[str, ...]:
    neo = loader == "neoforge"
    repo = FD_NEO if neo else FD_FAB
    block = ({"use": "73-L97", "remove": "105-L113", "tray": "136-L145", "sizzle": "162-L173", "time": "199-L216"}
             if neo else {"use": "67-L97", "tray": "125-L142", "sizzle": "158-L170", "time": "196-L213"})
    be = ({"tick": "51-L69", "cook": "94-L109", "place": "152-L156", "add": "158-L179", "take": "181-L183"}
          if neo else {"tick": "52-L71", "cook": "96-L111", "remove": "144-L150", "place": "156-L160",
                       "add": "162-L183", "take": "185-L187"})
    item = ({"near": "128-L139", "duration": "146-L151", "use": "153-L183", "tick": "185-L205",
             "release": "207-L220", "finish": "222-L247", "place": "300-L307", "sound": "88-L111",
             "creative": "113-L116", "hurt": "123-L126", "mine": "292-L298", "tier": "59-L65",
             "attributes": "81-L86"}
            if neo else
            {"near": "97-L108", "duration": "115-L120", "use": "122-L159", "release": "183-L197",
             "finish": "199-L224", "place": "283-L290", "sound": "300-L323", "hurt": "92-L95", "mine": "275-L281",
             "tier": "58-L63", "attributes": "65-L71"})
    out = [*(_blk(repo, v) for v in block.values()), *(_be(repo, v) for v in be.values()),
           *(_itm(repo, v) for v in item.values())]
    out.append(_src(repo, "common/registry/ModItems.java", "64-L65" if neo else "140-L145"))
    out.append(_src(repo, "common/loot/function/CopySkilletFunction.java", "39-L44" if neo else "35-L41"))
    return tuple(out)


def _item(mod: SourceMod, identifier: str, context: LoadContext, notes: list[str]) -> dict:
    """The skillet's Bedrock item: the block's own item (replace_block_item),
    one per stack, an iron-tier weapon, allowed in the off-hand for held
    cooking. Every number cited; attack speed and knockback have no Bedrock
    component and are left out (the note says so)."""
    neo = mod.loader == "neoforge"
    repair = [IRON_TIER["repair"]]
    if not neo:
        # Refabricated: .repairable(ToolMaterial.IRON.repairItems()), the item
        # tag minecraft:iron_tool_materials (fetched vanilla 26.1 tag data).
        found = context.tags.members("minecraft:iron_tool_materials")
        if found is not None and found.members and all(m.startswith("minecraft:") for m in found.members):
            repair = sorted(found.members)
        else:
            notes.append("skillet: minecraft:iron_tool_materials did not resolve; repaired with an iron ingot, "
                         "iron's repair item (minecraft.wiki, Tiers)")
    components = {
        "minecraft:block_placer": {"block": identifier, "replace_block_item": True},
        "minecraft:display_name": {"value": f"tile.{identifier}.name"},
        # ModItems: stacksTo(1).
        "minecraft:max_stack_size": 1,
        "minecraft:hand_equipped": True,
        # Held cooking: the skillet goes in the off-hand (skillet.js header).
        "minecraft:allow_off_hand": {"value": True},
        # properties.durability(IRON uses = 250). Bedrock's own iron tools
        # carry the same number (and, like every Bedrock item, last one use
        # longer: minecraft.wiki, Tiers).
        "minecraft:durability": {"max_durability": IRON_TIER["durability"]},
        # attack_damage modifier 5 + 2 on a player's base 1: 8 per hit.
        "minecraft:damage": {"value": int(PLAYER_BASE_DAMAGE + BASE_ATTACK_DAMAGE + IRON_TIER["attack_damage_bonus"])},
        # getEnchantmentValue = IRON 14; FD puts the skillet in the
        # durability, weapon, sharp_weapon, fire_aspect and sword (NeoForge) /
        # melee_weapon (Refabricated) enchantable tags and refuses sweeping
        # edge: Bedrock's sword slot (no sweeping edge on Bedrock).
        "minecraft:enchantable": {"slot": "sword", "value": IRON_TIER["enchantment_value"]},
        "minecraft:repairable": {"repair_items": [
            {"items": repair, "repair_amount": "query.max_durability * 0.25"},
        ]},
    }
    if neo:
        # NeoForge SkilletItem#canAttackBlock: no block breaking in creative.
        # (Refabricated has no such override.)
        components["minecraft:can_destroy_in_creative"] = {"value": False}
    return {"format_version": ITEM_FORMAT,
            "minecraft:item": {"description": {"identifier": identifier}, "components": components}}


def _sound(java: str, shipped: set, volume: float, **extra) -> dict | None:
    bedrock = VANILLA_SOUNDS.get(java) or (java if java in shipped else None)
    return {"id": bedrock, "volume": volume, **extra} if bedrock else None


def convert(mod: SourceMod, deferred: list[tuple[str, dict]], files: dict,
            context: LoadContext) -> tuple[ConversionResult, str]:
    """The skillet's data table, item, block and runtime, when its block converted."""
    result = ConversionResult()
    block = SKILLET_BLOCKS.get(mod.loader or "")
    if block is None or _unsupported(mod, STATION, STATION) is not None:
        return result, ""
    block_path = f"blocks/{block.name}.json"
    block_body = files.get(block_path)
    identifier = f"{mod.namespace}:{block.name}"
    if not (isinstance(block_body, dict)
            and block_body.get("minecraft:block", {}).get("description", {}).get("identifier") == identifier):
        # The blockstate's residue says why; the campfire recipes are the stove's.
        return result, ""

    notes: list[str] = []
    camp = campfire_table(mod, deferred, files, context, STATION)
    recipes = []
    for entry in camp.kept:
        if entry["cookingtime"] < COOKING["min_cooking_time"]:
            # Mth.clamp(result, 60, cookingtime) with 60 above the recipe's own
            # time: which bound wins is Minecraft's code, not cited here.
            notes.append(f"skillet: campfire recipe {entry['id']} takes {entry['cookingtime']} ticks, under the "
                         "skillet's 60-tick minimum; it cooks on the stove but not in the skillet")
            continue
        recipes.append(entry)

    heat_notes: list[str] = []  # the cooking pot reports the same tag mapping
    heat = heat_table(mod, files, result, heat_notes, unlit_sources=True)

    shipped = _shipped_sounds(files)
    ns = mod.namespace
    sounds = {
        # useItemOn: block.lantern.place at 0.7 / 1.0.
        "place": _sound("minecraft:block.lantern.place", shipped, 0.7, pitch=1.0),
        # addItemToCook: FD's block.skillet.add_food at 0.8 / 1.0.
        "add_food": _sound(f"{ns}:block.skillet.add_food", shipped, 0.8, pitch=1.0),
        # animateTick: block.skillet.sizzle, 1 in 10 client ticks, 0.4, 0.9-1.1.
        "sizzle": _sound(f"{ns}:block.skillet.sizzle", shipped, 0.4, pitch=1.0, pitch_min=0.9, pitch_max=1.1,
                         chance_per_tick=0.1),
        # SkilletItem#onUseTick: the same sizzle, 1 in 50 ticks.
        "held_sizzle": _sound(f"{ns}:block.skillet.sizzle", shipped, 0.4, pitch=1.0, pitch_min=0.9, pitch_max=1.1,
                              chance_per_tick=0.02),
        # playSkilletAttackSound: item.skillet.attack.strong at 1.0, 0.9-1.1.
        "attack": _sound(f"{ns}:item.skillet.attack.strong", shipped, 1.0, pitch=1.0, pitch_min=0.9, pitch_max=1.1),
    }
    for role, sound in sounds.items():
        if sound is None:
            notes.append(f"skillet: the {role.replace('_', ' ')} sound did not convert; it is silent")

    neo = mod.loader == "neoforge"
    messages = {
        # NeoForge's addItemToCook shows it for any item it can't take;
        # Refabricated's block only calls addItemToCook for an empty skillet
        # and a campfire input, so nothing is shown there.
        "invalid_item": _lang_key(mod, f"block.{ns}.skillet.invalid_item") if neo else None,
        "underwater": _lang_key(mod, f"item.{ns}.skillet.underwater"),
        "how_to_cook": _lang_key(mod, f"item.{ns}.skillet.how_to_cook"),
    }

    component = f"{ns}:portkit_skillet"
    table = {
        "block": identifier,
        "component": component,
        "cooking": COOKING,
        "heat": heat,
        "item": identifier,
        "launch": LAUNCH,
        "messages": messages,
        "recipes": sorted(recipes, key=lambda e: e["id"]),
        "sounds": sounds,
        "support_state": SUPPORT_STATE,
        "tick_interval": TICK_INTERVAL,
    }
    data_path = f"{_RUNTIME_DIR}/data/{ns}_skillet.js"
    vanilla_source = [f"//   {camp.chosen.label}: {camp.chosen.url}\n"] if (camp.vanilla is not None and camp.chosen) else []
    header = (
        f"// Generated by portkit from {ns}'s and vanilla's {CAMPFIRE} recipes; do not edit.\n"
        f"// Read by the fixed runtime {_RUNTIME_DIR}/skillet.js (portkit/runtime). Sources:\n"
        + "".join(f"//   {s}\n" for s in (*_sources(mod.loader), *block.sources, TIER_SOURCE, REPAIR_SOURCE))
        + "".join(vanilla_source)
    ).rstrip("\n")
    result.files[data_path] = _js_module(header, table)
    # The heat rule it shares with the cooking pot is the station kit's
    # (station_core.js, shipped by stations.convert), so the pot's core is not needed.
    for name in ("skillet.js", "skillet_core.js"):
        result.files[f"{_RUNTIME_DIR}/{name}"] = runtime_source(name)

    body = json.loads(json.dumps(block_body))
    body["format_version"] = SCRIPT_FORMAT
    components = body["minecraft:block"].setdefault("components", {})
    components[component] = {}
    components["minecraft:tick"] = {"interval_range": [TICK_INTERVAL, TICK_INTERVAL], "looping": True}
    result.files[block_path] = body

    item_path = f"items/{block.name}.json"
    item = _item(mod, identifier, context, notes)
    existing = files.get(item_path)
    if isinstance(existing, dict):
        tags = existing.get("minecraft:item", {}).get("components", {}).get("minecraft:tags")
        if tags:
            item["minecraft:item"]["components"]["minecraft:tags"] = tags
    result.files[item_path] = item

    result.stations[f"{CAMPFIRE} (skillet)"] = {
        "converted": len(recipes),
        "data": data_path,
        "block": identifier,
        "vanilla": len(recipes) - camp.jar_kept,
    }
    result.notes.extend(dict.fromkeys(notes))
    damage = item["minecraft:item"]["components"]["minecraft:damage"]["value"]
    result.notes.append(
        f"{identifier}: cooks {len(recipes)} {CAMPFIRE} recipes (the stove's table) through a Script API runtime "
        f"({SCRIPT_MODULE} {SCRIPT_VERSION}, {data_path}), as Farmer's Delight's skillet does. Placed (sneak to "
        "place it): use a food a campfire recipe takes on an empty skillet to put the whole stack in, an empty "
        "hand to take it out; over heat (the cooking pot's heat sources and conductors, a lit stove) each item "
        "cooks for the skillet's time (a fifth of the recipe's, whole seconds, at least 3 s, shorter with Fire "
        "Aspect on the placed skillet) and is thrown out to the side; off heat the progress cools; the tray "
        "model shows over a tray heat source; using it shows its contents in the action bar. Held: Java cooks "
        "the food in the other hand while the use button is held near a heat source; Bedrock's off-hand takes "
        "no food and a script can't see the use button held, so put the skillet in the off-hand and use a food "
        "in the main hand near heat (or while on fire): one of it cooks instead of being eaten, and the result "
        "goes to the inventory after the skillet's time for as long as the skillet stays in the off-hand "
        "(taken out sooner, the food comes back). Used from the main hand near heat, it says to hold the food "
        "in the other hand. As a weapon: "
        f"{damage} damage a hit, 250 durability, enchantable in Bedrock's sword slot at 14, repaired with iron "
        "(25% a unit), FD's hit sound. Not carried over: attack speed (-3.1) and knockback (+1), which no "
        "Bedrock item component sets; the weak hit sound for an uncharged swing (Bedrock has no attack charge); "
        "the food drawn in the skillet and the flip animation (block-entity and item renderers), steam and "
        "enchanted-hit particles; waterlogging (Bedrock custom blocks can't hold water) and its flooded rules; "
        "the tray's collision slab below the block (a Bedrock box can't reach below its block); the cooking look "
        "of the held item; holding the use button (any off-hand swap ends it instead); eating the food when the "
        "off-hand skillet takes it (Java eats first when hungry, Bedrock always cooks); the food, and the placed "
        "skillet's enchantments, wear and name, when something other than a player destroys it (no break event "
        "for that in script API 2.0.0: the block then drops a plain skillet as its own item; a player's break "
        "swaps that drop for the placed item, as copy_skillet does); hoppers; the advancements. Stored stacks keep their id, count, name, lore, durability damage and "
        "enchantments only."
    )
    entry = (
        'import { registerSkillet } from "./skillet.js";\n'
        f'import skilletTable from "./data/{ns}_skillet.js";\n'
        "registerSkillet(skilletTable);\n"
    )
    return result, entry
