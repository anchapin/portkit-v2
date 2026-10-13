"""Farmer's Delight cooking pot: data table + fixed Script API runtime (#177).

The second station on the cutting board's pattern (:mod:`portkit.converters.stations`,
docs/decisions.md): every ``farmersdelight:cooking`` recipe becomes one entry in
a generated data module (``scripts/portkit/data/<namespace>_cooking_pot.js``),
read by a hand-written runtime (``portkit/runtime/cooking_pot.js`` and its
node-tested logic ``cooking_pot_core.js``) that does what FD's
``CookingPotBlockEntity`` does, cited per line there. Nothing here is guessed:
an ingredient, result or container this conversion can't state exactly leaves
its recipe as ``station_recipe`` residue with the reason.

What the table carries beyond the recipe JSON, each read from FD's source at the
pinned commits (:data:`stations.FD_NEO`, :data:`stations.FD_FAB`):

* the meal's serving container: the recipe's ``container``, else the result's
  crafting remainder (FD's ModItems, :data:`FD_CRAFT_REMAINDERS`), and on
  Refabricated also the result's entry in INGREDIENT_REMAINDER_OVERRIDES
  (CookingPotRecipe.container());
* each ingredient's remainder, ejected when it is used up
  (processCooking: crafting remainder, else INGREDIENT_REMAINDER_OVERRIDES);
* the heat rule: FD's own ``farmersdelight:heat_sources``,
  ``heat_conductors`` and ``tray_heat_sources`` block tags, read from the jar
  (HeatableBlockEntity#isHeated; CookingPotBlock#getTrayState), each Java
  block mapped to the Bedrock block and state of the same meaning
  (:data:`BEDROCK_BLOCKS`; a converted stove by its lit state,
  :data:`portkit.converters.stove.HEAT_RULES`);
* ``farmersdelight:serving_containers``, the item tag that routes a held
  container to the container slot (CookingPotMenu#quickMoveStack).
"""
from __future__ import annotations

import json

from ..conditions import LoadContext
from ..model import ConversionResult, SourceMod, Unhandled
from .recipes import emitted_definitions
from .stations import (
    COOKING,
    FD_FAB,
    FD_NEO,
    RESIDUE_KIND,
    SCRIPT_FORMAT,
    SCRIPT_MODULE,
    SCRIPT_VERSION,
    VANILLA_SOUNDS,
    FacingBlock,
    _js_module,
    _Refuse,
    _Resolver,
    _recipe_id,
    _RUNTIME_DIR,
    _shipped_sounds,
    _src,
    _unsupported,
    runtime_source,
)

STATION = "cooking-pot"
SUPPORT_STATE = "farmersdelight:support"
# Ticks between two runs of the pot's tick (the block's minecraft:tick
# interval). Java ticks the block entity every game tick; the runtime advances
# the same counters by this many ticks at once, so every cookingtime that is a
# multiple of it (all corpus recipes: 100, 200, 400) finishes on the same tick
# count as Java.
TICK_INTERVAL = 10


def _blk(repo, line: str) -> str:
    return _src(repo, "common/block/CookingPotBlock.java", line)


def _be(repo, line: str) -> str:
    return _src(repo, "common/block/entity/CookingPotBlockEntity.java", line)


# CookingPotBlock: FACING = getHorizontalDirection().getOpposite() (faces the
# player, so the placement trait's offset is 180 as for the cutting board),
# SUPPORT none/handle/tray with NONE the default, SHAPE box(2, 0, 2, 14, 10, 14).
COOKING_POT_BLOCKS = {
    "neoforge": FacingBlock(
        "cooking_pot", 180, {"origin": [-6, 0, -6], "size": [12, 10, 12]},
        (_blk(FD_NEO, "117"), _blk(FD_NEO, "55"), _blk(FD_NEO, "58"), _blk(FD_NEO, "63")),
        java_state="support", values=("none", "handle", "tray"), state=SUPPORT_STATE,
    ),
    "fabric": FacingBlock(
        "cooking_pot", 180, {"origin": [-6, 0, -6], "size": [12, 10, 12]},
        (_blk(FD_FAB, "110"), _blk(FD_FAB, "48"), _blk(FD_FAB, "51"), _blk(FD_FAB, "56")),
        java_state="support", values=("none", "handle", "tray"), state=SUPPORT_STATE,
    ),
}

# Crafting remainders FD gives its own items (common/registry/ModItems.java,
# the registration line; bowlFoodItem / drinkItem add craftRemainder(BOWL /
# GLASS_BOTTLE): NeoForge L51-57, Refabricated L114-133). Every FD item
# registered with a remainder is listed, so an FD item that isn't has none.
FD_CRAFT_REMAINDERS = {
    "neoforge": {
        "farmersdelight:milk_bottle": ("minecraft:glass_bottle", 309),
        "farmersdelight:hot_cocoa": ("minecraft:glass_bottle", 311),
        "farmersdelight:apple_cider": ("minecraft:glass_bottle", 313),
        "farmersdelight:melon_juice": ("minecraft:glass_bottle", 315),
        "farmersdelight:tomato_sauce": ("minecraft:bowl", 317),
        "farmersdelight:glow_berry_custard": ("minecraft:glass_bottle", 381),
        "farmersdelight:fruit_salad": ("minecraft:bowl", 383),
        "farmersdelight:mixed_salad": ("minecraft:bowl", 387),
        "farmersdelight:nether_salad": ("minecraft:bowl", 389),
        "farmersdelight:cooked_rice": ("minecraft:bowl", 419),
        "farmersdelight:bone_broth": ("minecraft:bowl", 421),
        "farmersdelight:beef_stew": ("minecraft:bowl", 423),
        "farmersdelight:chicken_soup": ("minecraft:bowl", 425),
        "farmersdelight:vegetable_soup": ("minecraft:bowl", 427),
        "farmersdelight:fish_stew": ("minecraft:bowl", 429),
        "farmersdelight:fried_rice": ("minecraft:bowl", 431),
        "farmersdelight:pumpkin_soup": ("minecraft:bowl", 433),
        "farmersdelight:baked_cod_stew": ("minecraft:bowl", 435),
        "farmersdelight:noodle_soup": ("minecraft:bowl", 437),
        "farmersdelight:onion_soup": ("minecraft:bowl", 439),
        "farmersdelight:bacon_and_eggs": ("minecraft:bowl", 443),
        "farmersdelight:pasta_with_meatballs": ("minecraft:bowl", 445),
        "farmersdelight:pasta_with_mutton_chop": ("minecraft:bowl", 447),
        "farmersdelight:mushroom_rice": ("minecraft:bowl", 449),
        "farmersdelight:roasted_mutton_chops": ("minecraft:bowl", 451),
        "farmersdelight:vegetable_noodles": ("minecraft:bowl", 453),
        "farmersdelight:steak_and_potatoes": ("minecraft:bowl", 455),
        "farmersdelight:ratatouille": ("minecraft:bowl", 457),
        "farmersdelight:squid_ink_pasta": ("minecraft:bowl", 459),
        "farmersdelight:grilled_salmon": ("minecraft:bowl", 461),
        "farmersdelight:roast_chicken": ("minecraft:bowl", 467),
        "farmersdelight:stuffed_pumpkin": ("minecraft:bowl", 472),
        "farmersdelight:honey_glazed_ham": ("minecraft:bowl", 477),
        "farmersdelight:shepherds_pie": ("minecraft:bowl", 482),
        "farmersdelight:gleaming_salad": ("minecraft:bowl", 487),
        "farmersdelight:dog_food": ("minecraft:bowl", 494),
    },
    "fabric": {
        "farmersdelight:milk_bottle": ("minecraft:glass_bottle", 381),
        "farmersdelight:hot_cocoa": ("minecraft:glass_bottle", 383),
        "farmersdelight:apple_cider": ("minecraft:glass_bottle", 385),
        "farmersdelight:melon_juice": ("minecraft:glass_bottle", 388),
        "farmersdelight:tomato_sauce": ("minecraft:bowl", 390),
        "farmersdelight:glow_berry_custard": ("minecraft:glass_bottle", 454),
        "farmersdelight:fruit_salad": ("minecraft:bowl", 457),
        "farmersdelight:mixed_salad": ("minecraft:bowl", 462),
        "farmersdelight:nether_salad": ("minecraft:bowl", 465),
        "farmersdelight:cooked_rice": ("minecraft:bowl", 496),
        "farmersdelight:bone_broth": ("minecraft:bowl", 499),
        "farmersdelight:beef_stew": ("minecraft:bowl", 502),
        "farmersdelight:chicken_soup": ("minecraft:bowl", 505),
        "farmersdelight:vegetable_soup": ("minecraft:bowl", 508),
        "farmersdelight:fish_stew": ("minecraft:bowl", 511),
        "farmersdelight:fried_rice": ("minecraft:bowl", 514),
        "farmersdelight:pumpkin_soup": ("minecraft:bowl", 517),
        "farmersdelight:baked_cod_stew": ("minecraft:bowl", 520),
        "farmersdelight:noodle_soup": ("minecraft:bowl", 523),
        "farmersdelight:onion_soup": ("minecraft:bowl", 526),
        "farmersdelight:bacon_and_eggs": ("minecraft:bowl", 532),
        "farmersdelight:pasta_with_meatballs": ("minecraft:bowl", 535),
        "farmersdelight:pasta_with_mutton_chop": ("minecraft:bowl", 538),
        "farmersdelight:mushroom_rice": ("minecraft:bowl", 541),
        "farmersdelight:roasted_mutton_chops": ("minecraft:bowl", 544),
        "farmersdelight:vegetable_noodles": ("minecraft:bowl", 547),
        "farmersdelight:steak_and_potatoes": ("minecraft:bowl", 550),
        "farmersdelight:ratatouille": ("minecraft:bowl", 553),
        "farmersdelight:squid_ink_pasta": ("minecraft:bowl", 556),
        "farmersdelight:grilled_salmon": ("minecraft:bowl", 559),
        "farmersdelight:roast_chicken": ("minecraft:bowl", 566),
        "farmersdelight:stuffed_pumpkin": ("minecraft:bowl", 572),
        "farmersdelight:honey_glazed_ham": ("minecraft:bowl", 578),
        "farmersdelight:shepherds_pie": ("minecraft:bowl", 584),
        "farmersdelight:gleaming_salad": ("minecraft:bowl", 590),
        "farmersdelight:dog_food": ("minecraft:bowl", 598),
    },
}

# Vanilla crafting remainders this table can cite. The milk bucket leaves its
# bucket in the crafting grid on Java (minecraft.wiki, "Cake", crafting:
# "the empty buckets remain in the crafting grid in Java Edition").
VANILLA_CRAFT_REMAINDERS = {"minecraft:milk_bucket": "minecraft:bucket"}
# Vanilla items that may carry a crafting remainder in Minecraft's own item
# code, which this table doesn't cite; a recipe taking one stays residue
# rather than ejecting a guessed remainder (or none).
_UNCITED_VANILLA_REMAINDERS = frozenset({
    "minecraft:water_bucket", "minecraft:lava_bucket", "minecraft:honey_bottle", "minecraft:dragon_breath",
})
# CookingPotBlockEntity.INGREDIENT_REMAINDER_OVERRIDES (NeoForge L69-84,
# Refabricated L80-95; the same map): items whose leftover FD sets itself.
INGREDIENT_REMAINDER_OVERRIDES = {
    "minecraft:powder_snow_bucket": "minecraft:bucket",
    "minecraft:axolotl_bucket": "minecraft:bucket",
    "minecraft:cod_bucket": "minecraft:bucket",
    "minecraft:pufferfish_bucket": "minecraft:bucket",
    "minecraft:salmon_bucket": "minecraft:bucket",
    "minecraft:tropical_fish_bucket": "minecraft:bucket",
    "minecraft:suspicious_stew": "minecraft:bowl",
    "minecraft:mushroom_stew": "minecraft:bowl",
    "minecraft:rabbit_stew": "minecraft:bowl",
    "minecraft:beetroot_soup": "minecraft:bowl",
    "minecraft:potion": "minecraft:glass_bottle",
    "minecraft:splash_potion": "minecraft:glass_bottle",
    "minecraft:lingering_potion": "minecraft:glass_bottle",
    "minecraft:experience_bottle": "minecraft:glass_bottle",
}

# Java block -> the Bedrock blocks of the same meaning, each with the states it
# must have to count. Java's rule (HeatableBlockEntity#isHeated): a heat source
# with a LIT property gives heat only while lit. Bedrock ids and states from
# Mojang/bedrock-samples 46ba6ea9 metadata/vanilladata_modules/mojang-blocks.json:
# magma_block is minecraft:magma; Java's single lava block (every level) is
# Bedrock's lava and flowing_lava; Java's lava_cauldron is a cauldron with
# cauldron_liquid "lava" and fill_level above 0; a campfire's lit is the
# inverse of Bedrock's "extinguished". Fire, soul fire, campfires and hopper
# keep their ids.
BEDROCK_BLOCKS = {
    "minecraft:magma_block": [{"id": "minecraft:magma"}],
    "minecraft:lava": [{"id": "minecraft:lava"}, {"id": "minecraft:flowing_lava"}],
    "minecraft:lava_cauldron": [{"id": "minecraft:cauldron", "states": {"cauldron_liquid": "lava"},
                                 "not": {"fill_level": 0}}],
    "minecraft:campfire": [{"id": "minecraft:campfire", "lit": {"extinguished": False}}],
    "minecraft:soul_campfire": [{"id": "minecraft:soul_campfire", "lit": {"extinguished": False}}],
    "minecraft:fire": [{"id": "minecraft:fire"}],
    "minecraft:soul_fire": [{"id": "minecraft:soul_fire"}],
    "minecraft:hopper": [{"id": "minecraft:hopper"}],
}
# Vanilla block tags FD's heat tags name, from misode/mcmeta summary
# data/tag/block/data.json (1.21.1 @7cffbcda and 26.1 @e7068326 agree).
VANILLA_BLOCK_TAGS = {
    "minecraft:campfires": ["minecraft:campfire", "minecraft:soul_campfire"],
    "minecraft:fire": ["minecraft:fire", "minecraft:soul_fire"],
}
HEAT_SOURCES = (
    _src(FD_NEO, "common/block/entity/HeatableBlockEntity.java", "19-L38"),
    _blk(FD_NEO, "137-L142"),
    "https://github.com/vectorwing/FarmersDelight/blob/dd8b9b0bfec916a2da88a6d64e3a37f4a02c3259/"
    "src/generated/resources/data/farmersdelight/tags/block/heat_sources.json",
    "https://github.com/Mojang/bedrock-samples/blob/46ba6ea9/metadata/vanilladata_modules/mojang-blocks.json",
)


def _sources(loader: str) -> tuple[str, ...]:
    neo = loader == "neoforge"
    repo = FD_NEO if neo else FD_FAB
    lines = (
        {"use": "72-L93", "tick": "209-L238", "can": "279-L301", "cook": "303-L334", "eject": "336-L343",
         "xp": "379-L387", "move": "412-L422", "stored": "424-L441", "serve": "443-L450", "valid": "452-L460",
         "limit": "524-L529"}
        if neo else
        {"use": "65-L86", "tick": "228-L257", "can": "302-L322", "cook": "324-L358", "eject": "360-L367",
         "xp": "405-L413", "move": "437-L447", "stored": "449-L466", "serve": "468-L474", "valid": "476-L484",
         "limit": "556-L561"}
    )
    return (
        _blk(repo, lines["use"]),
        *(_be(repo, lines[k]) for k in ("tick", "can", "cook", "eject", "xp", "move", "stored", "serve",
                                        "valid", "limit")),
        _src(repo, "common/crafting/CookingPotRecipe.java", "100-L112" if neo else "147-L149"),  # matches
        _src(repo, "common/crafting/CookingPotRecipe.java", "45-L51" if neo else "67-L79"),  # container
        _src(repo, "common/block/entity/container/CookingPotMenu.java", "114-L151" if neo else "116-L153"),
    )


def _read_tag(mod: SourceMod, kind: str, name: str) -> list | None:
    path = mod.data / "tags" / kind / f"{name}.json"
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    values = body.get("values")
    return values if isinstance(values, list) else None


def _heat_blocks(mod: SourceMod, name: str, emitted_blocks: set, notes: list, seen=None) -> list[str] | None:
    """The Java block ids FD's block tag ``farmersdelight:<name>`` names, from
    the jar; ``required: false`` entries for mods not in this jar drop out as
    Java drops them, and blocks that don't exist here are noted."""
    values = _read_tag(mod, "block", name)
    if values is None:
        return None
    seen = set() if seen is None else seen
    out: list[str] = []
    for value in values:
        required = True
        if isinstance(value, dict):
            required = value.get("required", True)
            value = value.get("id")
        if not isinstance(value, str):
            continue
        if value.startswith("#"):
            tag = value[1:]
            if tag in VANILLA_BLOCK_TAGS:
                out += VANILLA_BLOCK_TAGS[tag]
            elif tag.startswith(f"{mod.namespace}:") and tag not in seen:
                seen.add(tag)
                inner = _heat_blocks(mod, tag.split(":", 1)[1], emitted_blocks, notes, seen)
                out += inner or []
            else:
                notes.append(f"cooking pot: heat tag entry #{tag} is not a tag this conversion can read; left out")
            continue
        namespace = value.split(":", 1)[0]
        if namespace not in ("minecraft", mod.namespace) and not required:
            continue  # an optional entry for a mod not in this jar (Create's chute)
        out.append(value)
    return list(dict.fromkeys(out))


def _station_rules(files: dict) -> dict[str, list[dict]]:
    """Heat rules for converted station blocks that carry a lit state (the
    stove, :data:`portkit.converters.stove.HEAT_RULES`), when the emitted block
    really has that state."""
    from .stove import HEAT_RULES

    rules: dict[str, list[dict]] = {}
    for java, rule in HEAT_RULES.items():
        body = files.get(f"blocks/{java.split(':', 1)[1]}.json")
        block = body.get("minecraft:block", {}) if isinstance(body, dict) else {}
        if block.get("description", {}).get("identifier") != rule["id"]:
            continue
        states = block.get("description", {}).get("states") or {}
        if all(value in (states.get(name) or []) for name, value in rule["lit"].items()):
            rules[java] = [dict(rule)]
    return rules


def _bedrock_rules(java_ids: list[str], emitted_blocks: set, notes: list, role: str,
                   with_lit: bool, station_rules: dict | None = None) -> list[dict]:
    rules: list[dict] = []
    for java in java_ids:
        mapped = BEDROCK_BLOCKS.get(java) or (station_rules or {}).get(java)
        if mapped is None and java in emitted_blocks:
            notes.append(f"cooking pot: {role} {java} is a converted block, but its Java lit state has no "
                         "Bedrock state this conversion can read; left out")
            continue
        if mapped is None:
            notes.append(f"cooking pot: {role} {java} did not convert (or has no Bedrock block of the same "
                         "meaning); it does not heat the pot on Bedrock")
            continue
        for rule in mapped:
            rule = dict(rule)
            lit = rule.pop("lit", None)
            if with_lit and lit:
                rule["states"] = {**rule.get("states", {}), **lit}
            rules.append(rule)
    return rules



def heat_table(mod: SourceMod, files: dict, result: ConversionResult, notes: list,
               unlit_sources: bool = False) -> dict:
    """FD's heat rules as Bedrock block rules: ``sources`` (lit, where a source
    can be unlit), ``conductors`` and ``tray`` from this jar's block tags
    (HeatableBlockEntity#isHeated, getTrayState); with ``unlit_sources`` also
    ``nearby``, the heat sources without the lit test (SkilletItem's
    isPlayerNearHeatSource tests the tag only). The tag files are claimed on
    ``result``; notes say what didn't map."""
    emitted_blocks = {
        body["minecraft:block"]["description"]["identifier"]
        for path, body in files.items()
        if path.startswith("blocks/") and isinstance(body, dict) and "minecraft:block" in body
    }
    station_rules = _station_rules(files)
    heat = {}
    roles = [("sources", "heat_sources", True), ("conductors", "heat_conductors", False),
             ("tray", "tray_heat_sources", False)]
    if unlit_sources:
        roles.append(("nearby", "heat_sources", False))
    for role, tag, lit in roles:
        java = _heat_blocks(mod, tag, emitted_blocks, notes)
        if java is None:
            notes.append(f"cooking pot: {mod.namespace}:{tag} is not in this jar; no {role}")
            heat[role] = []
            continue
        path = mod.data / "tags" / "block" / f"{tag}.json"
        result.claim(mod, path)
        kind = {"sources": "source", "conductors": "conductor", "tray": "tray", "nearby": "source"}[role]
        heat[role] = _bedrock_rules(java, emitted_blocks, notes, f"heat {kind} block", lit, station_rules)
    return heat


def _remainder(item: str, loader: str) -> str | None:
    """The leftover processCooking ejects when ``item`` is used up."""
    fd = FD_CRAFT_REMAINDERS[loader].get(item)
    if fd is not None:
        return fd[0]
    if item in VANILLA_CRAFT_REMAINDERS:
        return VANILLA_CRAFT_REMAINDERS[item]
    return INGREDIENT_REMAINDER_OVERRIDES.get(item)


def _stack(entry, role: str, resolve: _Resolver) -> dict:
    """An ItemStack field ({"id", "count"} or the older {"item", "count"}) as {item, count}."""
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


def _entry(mod: SourceMod, rel: str, recipe: dict, resolve: _Resolver, remainders: dict) -> dict:
    ingredients = recipe.get("ingredients")
    if not isinstance(ingredients, list) or not 1 <= len(ingredients) <= 6:
        raise _Refuse("a cooking recipe takes one to six ingredients (CookingPotRecipe.INPUT_SLOTS)")
    slots = []
    for spec in ingredients:
        items, _ = resolve.ingredient(spec, "ingredient")
        uncited = sorted(set(items) & _UNCITED_VANILLA_REMAINDERS)
        if uncited:
            raise _Refuse(f"ingredient {', '.join(uncited)} may leave a crafting remainder (Minecraft's item "
                          "code) that this table can't cite")
        for item in items:
            left = _remainder(item, mod.loader)
            if left is not None:
                remainders[item] = resolve.item(left, "ingredient remainder")
        slots.append(sorted(items))
    result = _stack(recipe.get("result"), "result", resolve)
    if "container" in recipe:
        container = _stack(recipe["container"], "container", resolve)["item"]
    else:
        container = None
        fd = FD_CRAFT_REMAINDERS[mod.loader].get(result["item"])
        if fd is not None:
            container = fd[0]
        elif result["item"].startswith(f"{mod.namespace}:"):
            container = None  # FD registers no remainder for it (ModItems)
        elif mod.loader == "fabric" and result["item"] in INGREDIENT_REMAINDER_OVERRIDES:
            container = INGREDIENT_REMAINDER_OVERRIDES[result["item"]]
        else:
            raise _Refuse(f"result {result['item']} has no container in the recipe, and whether it has a "
                          "crafting remainder (Minecraft's item code) is not something this table can cite")
        if container is not None:
            container = resolve.item(container, "container")
    cooktime = recipe.get("cookingtime", 200)
    experience = recipe.get("experience", 0.0)
    if not isinstance(cooktime, int) or cooktime < 1:
        raise _Refuse(f"unreadable cookingtime {cooktime!r}")
    if not isinstance(experience, (int, float)) or experience < 0:
        raise _Refuse(f"unreadable experience {experience!r}")
    return {
        "id": _recipe_id(mod, rel),
        "ingredients": slots,
        "result": result,
        "container": container,
        "cookingtime": cooktime,
        "experience": float(experience),
    }


def _perfect_match(a: list[list[str]], b: list[list[str]]) -> bool:
    """Whether every slot of ``a`` pairs with its own slot of ``b`` sharing an item."""
    if len(a) != len(b):
        return False
    pair: dict[int, int] = {}

    def augment(i: int, seen: set) -> bool:
        for j, slot in enumerate(b):
            if j in seen or not set(a[i]) & set(slot):
                continue
            seen.add(j)
            if j not in pair or augment(pair[j], seen):
                pair[j] = i
                return True
        return False

    return all(augment(i, set()) for i in range(len(a)))


def _overlaps(entries: list[dict]) -> dict[str, list[str]]:
    """Recipes another recipe also matches: some pot contents fill both.

    Java takes the first match its recipe manager finds (RecipeManager
    quickCheck), an order no file states, so neither recipe of such a pair is
    written.
    """
    clash: dict[str, list[str]] = {}
    for i, a in enumerate(entries):
        for b in entries[i + 1:]:
            if _perfect_match(a["ingredients"], b["ingredients"]):
                clash.setdefault(a["id"], []).append(b["id"])
                clash.setdefault(b["id"], []).append(a["id"])
    return clash


def _sound(java: str, shipped: set) -> dict | None:
    """A Java sound event as the Bedrock event the pack can play, or None."""
    bedrock = VANILLA_SOUNDS.get(java) or (java if java in shipped else None)
    return {"id": bedrock} if bedrock else None


def convert(mod: SourceMod, deferred: list[tuple[str, dict]], files: dict,
            context: LoadContext) -> tuple[ConversionResult, str]:
    """The cooking pot's data table and runtime for the ``farmersdelight:cooking`` recipes."""
    result = ConversionResult()
    if not deferred:
        return result, ""
    why = _unsupported(mod, STATION, "cooking pot")
    block = COOKING_POT_BLOCKS.get(mod.loader or "")
    block_path = f"blocks/{block.name}.json" if block else None
    block_body = files.get(block_path) if block_path else None
    identifier = f"{mod.namespace}:{block.name}" if block else None
    if why is None and not (isinstance(block_body, dict)
                            and block_body.get("minecraft:block", {}).get("description", {})
                            .get("identifier") == identifier):
        why = f"the cooking pot block ({identifier}) did not convert, so there is no station to run on"
    if why is not None:
        for rel, _ in deferred:
            result.unhandled.append(Unhandled(rel, RESIDUE_KIND, why))
        return result, ""

    emitted = emitted_definitions(files)
    resolve = _Resolver(mod, context.tags, emitted)
    notes: list[str] = []
    remainders: dict[str, str] = {}
    entries: list[tuple[str, dict]] = []
    for rel, recipe in sorted(deferred, key=lambda d: d[0]):
        try:
            entries.append((rel, _entry(mod, rel, recipe, resolve, remainders)))
        except _Refuse as refusal:
            result.unhandled.append(Unhandled(rel, RESIDUE_KIND, str(refusal)))
    clash = _overlaps([e for _, e in entries])
    kept = []
    for rel, entry in entries:
        if entry["id"] in clash:
            result.unhandled.append(Unhandled(rel, RESIDUE_KIND, (
                f"another cooking recipe ({', '.join(sorted(clash[entry['id']]))}) can match the same pot "
                "contents; Java cooks whichever its recipe manager finds first, an order no file states")))
        else:
            kept.append(entry)
    # Remainders only for items a written recipe can consume.
    used = {item for e in kept for slot in e["ingredients"] for item in slot}
    remainders = {k: v for k, v in sorted(remainders.items()) if k in used}

    # Heat: FD's block tags from this jar; a converted stove heats while lit.
    station_rules = _station_rules(files)
    heat = heat_table(mod, files, result, notes)
    notes = list(dict.fromkeys(notes))

    serving = context.tags.members(f"{mod.namespace}:serving_containers")
    serving_items = sorted(m for m in (serving.members if serving is not None else [])
                           if m.startswith("minecraft:") or m in emitted)
    if serving is None:
        notes.append("cooking pot: farmersdelight:serving_containers did not resolve; held containers go to "
                     "the ingredient slots")

    shipped = _shipped_sounds(files)
    # useItemOn: serving plays FD's block.food.take_portion on NeoForge, which
    # FD's sounds.json defines as the vanilla event item.armor.equip_generic,
    # and item.armor.equip_generic itself on Refabricated; the handle toggle
    # plays block.lantern.place at 0.7 / 1.0. animateTick: boil (empty pot) or
    # boil_soup (a meal inside), 1 in 10 client ticks, volume 0.5, pitch 0.9-1.1.
    sounds = {
        "serve": {**(_sound("minecraft:item.armor.equip_generic", shipped) or {}), "volume": 1.0, "pitch": 1.0},
        "handle": {**(_sound("minecraft:block.lantern.place", shipped) or {}), "volume": 0.7, "pitch": 1.0},
        "boil": _sound(f"{mod.namespace}:block.cooking_pot.boil", shipped),
        "boil_soup": _sound(f"{mod.namespace}:block.cooking_pot.boil_soup", shipped),
    }
    for role in ("boil", "boil_soup"):
        if sounds[role] is None:
            notes.append(f"cooking pot: {mod.namespace}:block.cooking_pot.{role} did not convert; the pot "
                         "boils silently")
        else:
            sounds[role].update({"volume": 0.5, "pitch_min": 0.9, "pitch_max": 1.1, "chance_per_tick": 0.1})
    for role in ("serve", "handle"):
        if "id" not in sounds[role]:
            sounds[role] = None

    component = f"{mod.namespace}:portkit_cooking_pot"
    table = {
        "block": identifier,
        "component": component,
        "heat": heat,
        "max_slot_meal": 64,
        "recipes": sorted(kept, key=lambda e: e["id"]),
        "remainders": remainders,
        "serving_containers": serving_items,
        "sounds": sounds,
        "support_state": SUPPORT_STATE,
        "tick_interval": TICK_INTERVAL,
    }
    data_path = f"{_RUNTIME_DIR}/data/{mod.namespace}_cooking_pot.js"
    header = (
        f"// Generated by portkit from {mod.namespace}'s {COOKING} recipes; do not edit.\n"
        f"// Read by the fixed runtime {_RUNTIME_DIR}/cooking_pot.js (portkit/runtime). Sources:\n"
        + "".join(f"//   {s}\n" for s in (*_sources(mod.loader), *block.sources, *HEAT_SOURCES))
    ).rstrip("\n")
    result.files[data_path] = _js_module(header, table)
    result.files[f"{_RUNTIME_DIR}/cooking_pot.js"] = runtime_source("cooking_pot.js")
    result.files[f"{_RUNTIME_DIR}/cooking_pot_core.js"] = runtime_source("cooking_pot_core.js")

    body = json.loads(json.dumps(block_body))
    body["format_version"] = SCRIPT_FORMAT
    components = body["minecraft:block"].setdefault("components", {})
    components[component] = {}
    # The pot's tick (custom component onTick needs minecraft:tick).
    components["minecraft:tick"] = {"interval_range": [TICK_INTERVAL, TICK_INTERVAL], "looping": True}
    result.files[block_path] = body

    for rel, _ in deferred:
        result.consumed.add(rel)
    result.stations[COOKING] = {
        "converted": len(kept),
        "residue": len(deferred) - len(kept),
        "data": data_path,
        "block": identifier,
    }
    result.notes.extend(notes)
    result.notes.append(
        f"{identifier}: {len(kept)} of {len(deferred)} {COOKING} recipes cook in the pot through a Script API "
        f"runtime ({SCRIPT_MODULE} {SCRIPT_VERSION}, {data_path}). Bedrock custom blocks have no container "
        "screen, so the pot is worked by hand: use an item on it to put it in (a serving container goes to "
        "the container slot as shift-clicking it into FD's menu would; anything else goes whole into the "
        "first empty ingredient slot, so a recipe needing one item twice takes two uses), use the meal's container on it to serve one portion, use an empty hand to take out "
        "the finished output (else the last ingredient stack, else the containers), sneak with an empty "
        "hand to hang it on or off its handle; the action bar shows what is inside. Not carried over: the "
        "menu itself and its recipe book, hoppers and other automation (Bedrock custom blocks have no "
        "inventory), the meal kept inside the dropped pot item (the meal drops as items instead), the "
        "contents when something other than a player destroys the pot (no break event for that in script API "
        "2.0.0), the experience orbs (awarded straight to the player who takes the output or breaks the pot), the "
        "bubble and steam particles, the comparator signal, waterlogging, the heating tray's collision "
        "slab and legs, pick-block of a filled pot, a custom name, and recipe unlocking. Stored stacks keep "
        "their id, count, name, lore, durability damage and enchantments only."
    )
    for java in sorted(station_rules):
        result.notes.append(
            f"{identifier}: a lit {java} under the pot heats it, as Java's farmersdelight:heat_sources tag says "
            f"(read from the stove's {', '.join(station_rules[java][0]['lit'])} state, which the stove runtime "
            "sets when it is lit or put out)")
    entry = (
        'import { registerCookingPot } from "./cooking_pot.js";\n'
        f'import cookingPotTable from "./data/{mod.namespace}_cooking_pot.js";\n'
        "registerCookingPot(cookingPotTable);\n"
    )
    return result, entry
