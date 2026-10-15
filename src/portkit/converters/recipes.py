"""Crafting recipes.

Java recipe JSON and Bedrock recipe JSON are both declarative, so this is a
mapping table, not an inference problem. Anything not in the table becomes an
Unhandled item rather than a plausible-looking guess.

Output names (#163): a recipe is written to ``recipes/<name>.json`` with the
identifier ``<namespace>:<name>``. ``<name>`` is the file's stem when no other
recipe file of the namespace shares it; when several do (Tinkers'
``world/wood/{greenheart,skyroot}/planks.json``), every one of them is named by
its whole path under ``recipes/``, folders joined with ``_``
(``world_wood_greenheart_planks``). See :func:`recipe_names`. No output is
ever written twice: a name another recipe already holds sends the later recipe
to residue saying which one holds it.

Ingredients that are tags with several members (#160) convert only when the
tag's whole membership is known (see :mod:`portkit.converters.tags`: a shared
``c:``/``forge:``/``neoforge:``/``fabric:``/``minecraft:`` tag needs the fetched
loader and vanilla data) and every member is either vanilla or a block or item
this conversion emits (``emitted``, filled by
:func:`portkit.converters.convert_all`). Three forms, in order:

1. Bedrock vanilla tag. When the membership is exactly that of one of the
   vanilla tags Bedrock's own recipes take under the same name and meaning
   (:data:`_BEDROCK_VANILLA_TAGS`, membership from the vanilla reference data),
   the recipe takes that tag. When the Java tag *is* one of those and the mod
   adds its own members to it (Silent Gear's netherwood planks in
   ``minecraft:planks``), the recipe takes Bedrock's tag and each of the mod's
   members carries it: an item in its ``minecraft:tags``, a block through an
   item that replaces the block's own item and carries the tag (see
   :func:`_block_item`). If one of them can't (a block that already has an
   item file), a single-slot ingredient keeps the tag recipe and gets one more
   recipe per mod member beside it (``<recipe>__<member>.json``); anything
   else stays residue. Bedrock's tag on its own would drop the mod's members.
2. Native tag. When the mod's members are items or blocks this conversion
   emits, the recipe keeps ``{"tag": "<java tag id>"}``: each member item gets
   the tag in its ``minecraft:tags`` component, and each member block gets an
   item form carrying it (see :func:`_block_item`; a block's own
   ``minecraft:tags`` are block tags, which recipes don't read). A vanilla item
   can't be given a tag by an add-on, nor can a block with its own item file;
   when the tag holds such members and at least two of the mod's own, a
   single-slot ingredient keeps the tag recipe and gets one recipe per such
   member beside it (``<recipe>__<member>.json``, at most
   :data:`EXPANSION_CAP`). Create's ``stone_types`` tags (14 blocks and one
   vanilla stone) take this form.
3. One recipe per member. Otherwise, when the recipe has exactly one such
   ingredient left, it fills exactly one grid slot, and the tag has at most
   :data:`EXPANSION_CAP` members, each member gets its own recipe. One slot
   only, because a tag filling several slots lets the player mix members, and
   per-member recipes would forbid that. Furnace recipes always take this
   form, since Bedrock's furnace input is one item id.

An ingredient written as a JSON list of items (Java's "any of these"; Mythic
Metals' ``[{"item": "...:deepslate_adamantite_ore"}, {"item":
"...:adamantite_ore"}]``) is a membership the recipe states outright, so it
takes form 3 under the same conditions: every listed item vanilla or emitted,
the only such ingredient, one slot, at most :data:`EXPANSION_CAP` items. A list
gets no tag of its own (the mod declared none). Vanilla Bedrock writes its
"armour piece -> nugget" furnace recipes the same way, one per piece
(bedrock-samples ``behavior_pack/recipes/furnace_iron_helmet.json``). A list
holding a tag, or anything but plain item ids, stays residue.

Anything else stays residue, and the reason names any members this conversion
did not emit. A recipe is never narrowed to part of a tag.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import PurePosixPath

from ..conditions import CONDITIONAL_TYPES, LoadContext, condition_keys
from ..model import ConversionResult, SourceMod, Unhandled
from ..data import FETCH_COMMAND
from .tags import MultiMembers, TagResolver

# Recipe types a station runtime writes into a data table (stations.RECIPE_TYPES;
# kept here as a literal so this module doesn't import the station converter).
STATION_TYPES = frozenset({"farmersdelight:cutting", "farmersdelight:cooking"})
# Recipe types a station also reads while they convert as usual (stations.SHARED_TYPES):
# the Farmer's Delight stove cooks campfire recipes, which still become
# Bedrock campfire recipes of their own.
STATION_SHARED_TYPES = frozenset({"minecraft:campfire_cooking"})

# Most members a single-slot tag ingredient is expanded into, one recipe each.
# 16 covers a full dye-colour set; a bigger tag is a family (every drawer, every
# cast) whose recipe would flood the recipe book, so it stays residue.
EXPANSION_CAP = 16

# minecraft:tags on an item needs item format_version 1.20.50 or later
# (learn.microsoft.com, Items Documentation - minecraft:tags).
_ITEM_TAGS_FORMAT = "1.20.50"
# minecraft:block_placer's replace_block_item needs item format_version 1.21.50
# or later (learn.microsoft.com, Items Documentation - minecraft:block_placer).
_BLOCK_ITEM_FORMAT = "1.21.50"

# Java type -> (Bedrock body key, crafting tags).
# Bedrock has no separate stonecutter recipe type: a stonecutter recipe is a
# shapeless one tagged for that block, which is also how the vanilla packs do it.
_SUPPORTED = {
    "minecraft:crafting_shaped": ("minecraft:recipe_shaped", ["crafting_table"]),
    "minecraft:crafting_shapeless": ("minecraft:recipe_shapeless", ["crafting_table"]),
    "minecraft:smelting": ("minecraft:recipe_furnace", ["furnace"]),
    "minecraft:blasting": ("minecraft:recipe_furnace", ["blast_furnace"]),
    "minecraft:smoking": ("minecraft:recipe_furnace", ["smoker"]),
    "minecraft:campfire_cooking": ("minecraft:recipe_furnace", ["campfire", "soul_campfire"]),
    "minecraft:stonecutting": ("minecraft:recipe_shapeless", ["stonecutter"]),
}

_FURNACE_TYPES = {
    "minecraft:smelting",
    "minecraft:blasting",
    "minecraft:smoking",
    "minecraft:campfire_cooking",
}

# Types with a real Bedrock equivalent we deliberately do not attempt yet, so the
# residue says why instead of "unsupported".
_KNOWN_UNSUPPORTED = {
    "minecraft:smithing_trim": (
        "an armour trim; Bedrock has minecraft:recipe_smithing_trim, but its slots only "
        "accept items carrying the trim_templates, trimmable_armors and trim_materials "
        "tags, and a custom item tagged trim_materials has no effect, so whether this "
        "trim can work on Bedrock is a judgment call"
    ),
    "minecraft:crafting_transmute": "transmute recipes have no Bedrock equivalent",
    # wisp-forest/alloy-forgery 1.21.1 (48e309f), RawAlloyForgeRecipe: up to 10
    # counted inputs, min_forge_tier, fuel_per_tick, tier-range output overrides.
    # The forge (controller block, multiblock, fuels, tiers) is Alloy Forgery's,
    # not the recipe mod's; a crafting-table or furnace stand-in would drop the
    # fuel and tier gates and the tier bonus, and a made-up forge block is
    # fabrication (#87). See docs/decisions.md, 2026-10-12.
    "alloy_forgery:forging": (
        "an Alloy Forgery forge recipe (counted inputs, minimum forge tier, fuel per tick, "
        "tier-dependent output); it runs only in a forge the Alloy Forgery mod defines, which "
        "is not in this jar, so there is no station on Bedrock to tag it for, and a crafting "
        "table or furnace stand-in would drop the fuel and tier rules"
    ),
}

# A recipe whose result Java computes in code, or that runs only at a station
# that is Java code, is residue of its own kind (#180): nothing in its JSON
# can become a fixed-result Bedrock recipe without inventing or dropping part
# of what it does (#87), so the residue agent skips it (agent/residue.py
# SKIP_KINDS) instead of writing a stand-in. docs/decisions.md, 2026-10-15.
CODE_RECIPE = "code_recipe"

# Keys any recipe may carry that say nothing about what it takes or makes:
# vanilla's recipe-book fields (group, category, show_notification) and the
# mod's loader's load-condition keys (conditions.condition_keys; decided
# before this point). A
# modded recipe type whose JSON holds nothing else is a "special" recipe: its
# serializer reads no ingredients and no result, so what it matches and what
# it builds are the mod's Java code (vanilla's SimpleCraftingRecipeSerializer
# reads "category" only; Supplementaries 1.20-3.1.43 ModRecipes registers its
# 13 such types through it, Alex's Mobs 1.22.9 AMRecipeRegistry its 2, both
# CustomRecipe subclasses, bytecode).
_NO_DATA_KEYS = frozenset({"type", "group", "category", "show_notification"})

# Modded types that do carry data, but whose station or result is code. Each
# reason is read from the mod's own code at the corpus pin (sources in the
# comments; docs/decisions.md, 2026-10-15). Bedrock side: its recipe types
# are shaped, shapeless, furnace (one input), brewing and smithing (agent
# reference topics, MicrosoftDocs/minecraft-creator @4186dc4), and the only
# block components that open a screen are minecraft:crafting_table and the
# experimental minecraft:block_entity container (vendored
# @minecraft/bedrock-schemas 1.26.60 bp/blocks), so a GUI station has no
# Bedrock screen to land in.
_CODE_RECIPES = {
    # BetterEnd 21.800.2 (quiqueck/BetterEnd @9c449fb7): InfusionRecipe codec
    # L351-357 (input, result, catalysts, time default 1, group); InfusionRitual PEDESTALS_MAP
    # L42-51 (eight pedestals 3 out), tick L128-172 (time ticks, then the
    # result replaces the input); PedestalBlock#useItemOn L116-148 (one stack
    # per pedestal), getStateForPlacement/updateShape L180-275 (shape follows
    # the blocks above and below).
    "betterend:infusion": (
        "a BetterEnd infusion ritual: the input sits on betterend:infusion_pedestal, the eight "
        "catalysts on pedestals three blocks out, and after `time` ticks the result replaces the "
        "input (InfusionRitual#tick); the pedestals' item storage, neighbour-driven shapes and the "
        "ritual are block-entity code, so there is no station on Bedrock to run it yet, and a "
        "crafting stand-in would drop the pedestal layout and the time"
    ),
    # BCLib 21.800.2 (quiqueck/BCLib @80a081d4): AnvilMenuMixin#bcl_updateOutput
    # L138-158 (vanilla anvil screen, anvil crafting level >= anvilLevel),
    # AnvilRecipe#matches L182-195 (hammer in allowedTools), #craft L160-170
    # (the hammer takes `damage`).
    "bclib:smithing": (
        "a BCLib anvil recipe: worked in the vanilla anvil screen with a hammer from "
        "`allowedTools`, on an anvil whose crafting level is at least `anvilLevel`, the hammer "
        "taking `damage` (AnvilMenuMixin#bcl_updateOutput, AnvilRecipe#craft); Bedrock has no anvil "
        "recipe type and no block component that opens an anvil screen, so a Bedrock station "
        "would be a new interaction (a decision, #180), and a crafting stand-in would drop the "
        "hammer, level and damage"
    ),
    # BCLib AlloyingRecipe codec L228-238 (two ingredients, result, experience
    # default 0, smelttime default 350); BetterEnd EndStoneSmelter#useWithoutItem L55-72 opens
    # EndStoneSmelterBlockEntity's menu (two ingredient slots and fuel,
    # createMenu L399).
    "bclib:alloying": (
        "a BCLib alloying recipe: two ingredients smelted with fuel in BetterEnd's End Stone "
        "Smelter screen (EndStoneSmelter#useWithoutItem, EndStoneSmelterBlockEntity), with its "
        "experience and smelt time; Bedrock's furnace recipes take one input and no block "
        "component opens a furnace screen, so a Bedrock station would be a new interaction (a decision, "
        "#180), and a furnace or crafting stand-in would drop the second input, fuel and time"
    ),
    # Mythic Metals 0.24.6+1.21 (jar bytecode, intermediary names):
    # TidesingerCoralRecipe#craft copies the base onto the result item and sets
    # MythicDataComponents.TIDESINGER from TidesingerPatternComponent.fromStack
    # (the addition).
    "mythicmetals:tidesinger_smithing_transform": (
        "a Mythic Metals Tidesinger smithing recipe: the result keeps the base armour's data and "
        "takes a coral pattern read from the coral addition (TidesingerCoralRecipe#craft, "
        "MythicDataComponents.TIDESINGER); a Bedrock smithing_transform has no pattern to carry, "
        "so the armour would lose what the coral decides"
    ),
    # MidasFoldingRecipe#matches/#craft: GOLD_FOLDED (GoldFoldedComponent)
    # count on the sword, item switched to GILDED/ROYAL_MIDAS_GOLD_SWORD by it.
    "mythicmetals:fold_midas_sword": (
        "a Mythic Metals Midas folding recipe: each fold adds to a folded-gold count kept on the "
        "sword (MythicDataComponents.GOLD_FOLDED), and that count decides whether it matches and "
        "which sword comes out (MidasFoldingRecipe#matches/#craft); the JSON result is only the "
        "item, the count is code"
    ),
    # UpgradeSmithingRecipe#matches (UpgradeComponent.hasUpgrade/hasFreeSlots),
    # #craft (UpgradeComponent.addItem onto a copy of the base).
    "mythicmetals:upgrading": (
        "a Mythic Metals upgrade recipe: the addition is stored in the base item's upgrade slots "
        "(UpgradeSmithingRecipe#craft, UpgradeComponent.addItem) and matches only while a slot is "
        "free and that upgrade isn't there yet; a Bedrock smithing_transform would drop the stored "
        "upgrade"
    ),
    # Tinkers' Construct 3.12.1.231 TinkerSmeltery L433-434 (molding_basin /
    # molding_table, MoldingRecipe LOADER L23-29: material, pattern,
    # pattern_consumed, result): the material sits on a casting table or basin
    # and using the pattern on it presses it into the result
    # (CastingBlockEntity L152-181: moldingInventory.setPattern(held)).
    **dict.fromkeys(("tconstruct:molding_table", "tconstruct:molding_basin"), (
        "a Tinkers' Construct molding recipe: the `material` placed on a casting table or basin is "
        "pressed into the result by using the `pattern` on it, which may be kept or consumed "
        "(MoldingRecipe, run by CastingBlockEntity L152-181); Bedrock has no casting block to press "
        "on, and a crafting stand-in would turn a block interaction into a grid recipe"
    )),
    # Silent Gear 2.6.36 (Silent-Gear 1.16.x @9188137b, see _MODULAR_TOOL_RECIPES):
    # SalvagerTileEntity L89-153: BASE_WORK_TIME 10 s, each result item lost
    # with a chance between salvagerMinLossRate (0.0) and salvagerMaxLossRate
    # (0.5) by the input's damage (Config L313-320).
    "silentgear:salvaging": (
        "a Silent Gear salvaging recipe: the Salvager block takes the item apart over a work time, "
        "and each result item is lost with a chance that grows with the input's damage "
        "(SalvagerTileEntity#tick and #getLossRate, partLossRate config 0.0 to 0.5); a fixed-result "
        "Bedrock recipe would drop the station, the time and the loss"
    ),
    # Mekanism 10.7.19.85 (see _MACHINE_RECIPES): MekanismRecipeSerializersInternal
    # L102 registers mek_data as MekanismRecipeSerializer.wrapped(MekanismShapedRecipe::new);
    # MekanismShapedRecipe#assemble L31-79 merges each ingredient's
    # RecipeUpgradeData (energy, stored items, fluids, chemicals, upgrades,
    # security, sorting, QIO and lock data) into the result.
    "mekanism:mek_data": (
        "a Mekanism data-keeping shaped recipe: the grid's ingredients pass what they store (energy, "
        "items, fluids, chemicals, installed upgrades, owner and security, and other machine data) on "
        "to the result, as when an energy cube is upgraded a tier (MekanismShapedRecipe#assemble, "
        "RecipeUpgradeData); a Bedrock shaped recipe makes a fresh item, so the stored contents would "
        "be lost"
    ),
    # Create mc1.20.1-6.0.8 (@1a1a9a28, see _CREATE_MACHINE_RECIPES):
    # ManualApplicationRecipe#manualApplicationRecipesApplyInWorld L40-80 (a
    # RightClickBlock handler: the block matching ingredient 0 is replaced by
    # the result block, the held ingredient 1 used up unless keepHeldItem,
    # ItemApplicationRecipe L57); a create:deployer runs the same recipes
    # (DeployerBlockEntity L573).
    "create:item_application": (
        "a Create item application recipe: using the second ingredient on a placed block that matches "
        "the first turns that block into the result block in the world, the held item used up unless "
        "`keepHeldItem` is true (ManualApplicationRecipe#manualApplicationRecipesApplyInWorld, a "
        "right-click-block handler; a create:deployer can do it too); the ingredients are a block in "
        "the world and an item in hand, not a crafting grid, so a Bedrock recipe would turn a block "
        "interaction into a grid recipe, and a Bedrock version needs a script on item use (#173)"
    ),
    # SandPaperItem#use L55-75 (the item in the other hand goes into the
    # sandpaper's "Polishing" tag), getUseDuration L241-242 (32 ticks),
    # #finishUsingItem L118-145 (SandPaperPolishingRecipe#applyPolish, the
    # sandpaper takes 1 damage); a deployer holding sandpaper polishes too
    # (DeployerBlockEntity L559).
    "create:sandpaper_polishing": (
        "a Create sandpaper polishing recipe: holding sandpaper and using it for 32 ticks polishes the "
        "item in the other hand into the result, the sandpaper taking 1 damage (SandPaperItem#use, "
        "#finishUsingItem, SandPaperPolishingRecipe#applyPolish; a create:deployer holding sandpaper "
        "does it too); it is an item use, not a crafting grid, so a Bedrock recipe would drop the "
        "sandpaper's wear and the hold-to-use step"
    ),
    # Supplementaries 1.20-3.1.43 SusRecipe#assemble (a CustomRecipe): the other
    # grid stack goes into the result's BlockEntityTag "item".
    "supplementaries:sus_crafting": (
        "a Supplementaries suspicious-block recipe: the other item in the grid is stored in the "
        "result's block data as its hidden loot (SusRecipe#assemble, BlockEntityTag.item); a "
        "fixed-result Bedrock recipe would drop the hidden item"
    ),
}


# A recipe that melts items into a mod's fluid, alloys fluids, or casts or
# fills items from a fluid (mostly the mod's own; a few take vanilla lava or
# water, still by the millibucket at a mod station) is residue of its own kind
# (#174). Bedrock add-ons
# can't define a fluid: the custom block component list has no fluid component
# (learn.microsoft.com, Block Components Documentation, updated 2026-08-25),
# and the Script API's only fluid surface is the cauldron-style
# BlockFluidContainerComponent ("used with blocks like cauldrons") whose
# FluidType enumeration is fixed to Water, Lava, PowderSnow and Potion
# (learn.microsoft.com scriptapi/minecraft/server/blockfluidcontainercomponent,
# .../fluidtype). So the molten metals, slimes and soups these recipes make or
# take, measured in millibuckets, have no Bedrock form, and the stations that
# run them (multiblock tanks, faucets, casting blocks, spouts) are block-entity
# code. An item-only stand-in (say, ingot in, cast part out) would drop the
# fluid amounts, temperatures and cooling times and invent an item step the mod
# doesn't have (#87). The residue agent skips the kind (agent/residue.py
# SKIP_KINDS). docs/decisions.md, 2026-10-15.
FLUID_RECIPE = "fluid_recipe"

# What Bedrock lacks, said once at the end of every fluid recipe's reason.
_NO_BEDROCK_FLUID = (
    "Bedrock add-ons can't define a fluid or store a measured amount of one (no fluid block "
    "component; the script fluid container holds only water, lava, powder snow or potion, as a "
    "cauldron does), so a mod's fluid has no Bedrock form and the station that measures fluid in mB "
    "has nothing to build on; an item-only stand-in would drop the fluid amounts and invent a step"
)


def _tinkers(what: str) -> str:
    return f"a Tinkers' Construct {what}; {_NO_BEDROCK_FLUID}"


_TC_MELTING = _tinkers(
    "melting recipe: the ingredient melts into `result` (a fluid amount in mB, plus any byproducts) "
    "once the melter, smeltery or foundry reaches `temperature`, over `time` (MeltingRecipe LOADER "
    "L32-38, run by the melting block entities)"
)
_TC_CASTING = _tinkers(
    "casting recipe: fluid poured from a faucet into a casting table or basin (optionally over a "
    "cast) cools into the result over a cooling time (ItemCastingRecipe LOADER L26-31: fluid, "
    "result, cooling_time; the material, composite, tool, part-swap, potion, tipping and "
    "duplication variants work the same way; run by CastingBlockEntity)"
)
_TC_FILLING = _tinkers(
    "container filling recipe: poured fluid fills `fluid_amount` mB into the `container` item on a "
    "casting table or basin (ContainerFillingRecipe LOADER L39-42, run by CastingBlockEntity)"
)

# Tinkers' Construct 3.12.1.231 (SlimeKnights/TinkersConstruct @a5a03249):
# every type below is registered in TinkerSmeltery L408-444
# (RECIPE_SERIALIZERS.register), the smeltery module. Field names from each
# recipe's LOADER: MeltingRecipe L32-38 (ingredient, result, temperature, time,
# byproducts), ItemCastingRecipe L26-31 (fluid, result, cooling_time),
# AlloyRecipe L29-33 (inputs list of >= 2, result, temperature), MeltingFuel
# L27-32 (fluid, duration, temperature, rate), EntityMeltingRecipe L29-33
# (entity, result, damage), MaterialFluidRecipe L30-36 (fluid, temperature).
# Create mc1.20.1-6.0.8 (Creators-of-Create/Create @1a1a9a28): AllRecipeTypes
# L61-62 FILLING/EMPTYING; FillingRecipe#getRequiredFluid (a FluidIngredient
# with an amount), run by FillingBySpout (the Spout); EmptyingRecipe
# #getResultingFluid, run by GenericItemEmptying (the Item Drain,
# ItemDrainBlockEntity L200-234).
_FLUID_RECIPES = {
    **dict.fromkeys((
        "tconstruct:melting", "tconstruct:ore_melting", "tconstruct:damagable_melting",
        "tconstruct:material_melting",
    ), _TC_MELTING),
    "tconstruct:entity_melting": _tinkers(
        "entity melting recipe: a living `entity` inside a smeltery or foundry takes `damage` and yields "
        "`result` fluid (EntityMeltingRecipe LOADER L29-33)"
    ),
    "tconstruct:melting_fuel": _tinkers(
        "melting fuel: the `fluid` burned from a fuel tank for `duration` gives a melter, smeltery or "
        "foundry its `temperature` and melting `rate` (MeltingFuel LOADER L27-32)"
    ),
    "tconstruct:alloy": _tinkers(
        "alloying recipe: two or more fluids in the smeltery, foundry or alloyer tank combine by "
        "amount into `result` above `temperature` (AlloyRecipe LOADER L29-33)"
    ),
    "tconstruct:material_fluid": _tinkers(
        "material fluid: which `fluid` (and amount) casts a tool material, at what `temperature`, "
        "when tool parts are cast (MaterialFluidRecipe LOADER L30-36)"
    ),
    **dict.fromkeys((
        "tconstruct:casting_table", "tconstruct:casting_basin",
        "tconstruct:table_duplication", "tconstruct:basin_duplication",
        "tconstruct:casting_table_potion", "tconstruct:casting_basin_potion",
        "tconstruct:casting_table_tipping", "tconstruct:casting_basin_tipping",
        "tconstruct:casting_table_tipped_clearing", "tconstruct:casting_basin_tipped_clearing",
        "tconstruct:retextured_casting_table", "tconstruct:retextured_casting_basin",
        "tconstruct:table_casting_material", "tconstruct:basin_casting_material",
        "tconstruct:table_casting_composite", "tconstruct:basin_casting_composite",
        "tconstruct:table_tool_casting", "tconstruct:basin_tool_casting",
        "tconstruct:table_casting_part_swapping", "tconstruct:basin_casting_part_swapping",
    ), _TC_CASTING),
    **dict.fromkeys(("tconstruct:table_filling", "tconstruct:basin_filling"), _TC_FILLING),
    "create:filling": (
        f"a Create filling recipe: the Spout pours the fluid ingredient's amount (mB) onto the item "
        f"below it to make the result (FillingRecipe#getRequiredFluid, FillingBySpout); {_NO_BEDROCK_FLUID}"
    ),
    "create:emptying": (
        f"a Create emptying recipe: the Item Drain empties the item into its fluid result (mB) and "
        f"keeps the emptied item (EmptyingRecipe#getResultingFluid, GenericItemEmptying); "
        f"{_NO_BEDROCK_FLUID}"
    ),
}


def fluid_recipe_reason(java_type: object) -> str | None:
    """Why a recipe of this type makes, takes or moves a mod's fluid (#174),
    or None if it isn't one this module knows: a type in :data:`_FLUID_RECIPES`."""
    return _FLUID_RECIPES.get(java_type) if isinstance(java_type, str) else None


# A recipe that builds, modifies, repairs or takes apart a modular tool, or
# makes a part or material whose identity is stored on the stack, is residue
# of its own kind (#175). In Tinkers' Construct and Silent Gear a tool's
# numbers (durability, mining speed, attack, traits) are computed in Java at
# craft time from the materials of the parts it was built from, plus its
# modifiers, and stored per stack (NBT). A Bedrock item's components are fixed
# per item type in its JSON, so one Bedrock item can't be an iron-headed pick
# and a cobalt-headed pick at once; per-stack stats would need a scripted
# station and runtime (#175's large option), which doesn't exist. A stand-in
# with fixed stats is fabrication (#87, #135). The residue agent skips the
# kind (agent/residue.py SKIP_KINDS). docs/decisions.md, 2026-10-15.
MODULAR_TOOL = "modular_tool"

# What Bedrock lacks, said once at the end of every modular tool reason.
_NO_PER_STACK_TOOL = (
    "a Bedrock item's components are fixed per item type, so a tool or part whose materials, stats "
    "and modifiers are computed in Java and stored on each stack has no single Bedrock item to write, "
    "and a stand-in with fixed numbers would invent them"
)


def _tc_tool(what: str) -> str:
    return f"a Tinkers' Construct {what}; {_NO_PER_STACK_TOOL}"


def _sg_gear(what: str) -> str:
    return f"a Silent Gear {what}; {_NO_PER_STACK_TOOL}"


_TC_STATION_EDIT = _tc_tool(
    "Tinker Station recipe that changes a built tool (adds or levels a modifier, fills overslime, "
    "swaps a part or material, repairs or damages it); the tool's modifiers, slots, materials and "
    "stats live in its stack data and are recomputed by ToolStack"
)
_TC_CRAFTING_EDIT = _tc_tool(
    "crafting-table recipe that edits a built tool's stack data (overslime or a modifier's repair "
    "material), run by a CustomRecipe subclass rather than a fixed result"
)
_TC_WORKTABLE = _tc_tool(
    "Modifier Worktable recipe (an AbstractWorktableRecipe: removing, extracting, sorting or "
    "toggling a tool's modifiers, or converting enchanted books into modifier crystals); the "
    "worktable is a block-entity screen and its results are written into the tool's stack data"
)
_TC_PART_BUILDER = _tc_tool(
    "Part Builder recipe: a pattern plus enough material value (from `tconstruct:material` "
    "recipes) makes a tool part carrying that material on the stack, or recycles a tool back into "
    "parts (PartRecipe/ItemPartRecipe/PartBuilderRecycle/PartBuilderToolRecycle); the Part Builder "
    "is a block-entity screen"
)
_TC_SEVERING = _tc_tool(
    "severing recipe: when a tool with the severing modifier kills the `entity`, the "
    "`result` may drop with a chance per modifier level (SeveringRecipe LOADER L32-36, run by "
    "SeveringModule#processLoot L42-56); the drop belongs to the modifier on the tool, not to a recipe"
)

# Tinkers' Construct 3.12.1.231 (SlimeKnights/TinkersConstruct @a5a03249):
# TinkerTables L149-165 and TinkerModifiers L741-779 (RECIPE_SERIALIZERS
# .register). The data-free CustomRecipe types (tinker_station_repair,
# crafting_table_repair, armor_dyeing_modifier, armor_trim_modifier) stay
# special code_recipe residue. ToolBuildingRecipe#requiresAnvil L230-232 (4 or
# more parts and extra requirements need the Tinker's Anvil); #assemble L200-202
# (ToolStack.createTool from the parts' MaterialNBT). MaterialRecipe LOADER
# L35-43 (ingredient, value, needed, material, leftover). ModifierSalvage
# LOADER L30-38 (tools, modifier, level, slots), read by ModifierRemovalRecipe
# L122 through ModifierRecipeLookup#getSalvage. ShapedMaterialsRecipe L118-148
# and ShapelessMaterialsRecipe set the result's MaterialNBT from the grid.
# Silent Gear 2.6.36 (SilentChaos512/Silent-Gear 1.16.x @9188137b, committed
# 2021-12-29, the jar's Implementation-Timestamp day): ModRecipes L43-80,
# names from Const L28-46.
_MODULAR_TOOL_RECIPES = {
    "tconstruct:tool_building": _tc_tool(
        "tool building recipe: the parts placed in the Tinker Station (or the Tinker's Anvil when "
        "parts and extra requirements number four or more) build the `result` tool, and its stats "
        "come from each part's material (ToolBuildingRecipe#assemble, ToolStack.createTool with "
        "the parts' materials)"
    ),
    "tconstruct:tipped_tool_transform": _tc_tool(
        "tool building recipe that turns tipped arrows into a tipped tool (TippedToolTransformRecipe, "
        "a ToolBuildingRecipe)"
    ),
    **dict.fromkeys((
        "tconstruct:modifier", "tconstruct:incremental_modifier", "tconstruct:swappable_modifier",
        "tconstruct:multilevel_modifier", "tconstruct:multilevel_incremental_modifier",
        "tconstruct:overslime_modifier", "tconstruct:banner_modifier", "tconstruct:modifier_repair",
        "tconstruct:tinker_station_part_swapping", "tconstruct:tinker_station_damaging",
        "tconstruct:fixed_material_swapping", "tconstruct:material_value_swapping",
        "tconstruct:tool_material_swapping", "tconstruct:part_swapping_override",
    ), _TC_STATION_EDIT),
    **dict.fromkeys(("tconstruct:crafting_overslime_modifier", "tconstruct:crafting_modifier_repair"),
                    _TC_CRAFTING_EDIT),
    **dict.fromkeys((
        "tconstruct:remove_modifier", "tconstruct:extract_modifier", "tconstruct:modifier_sorting",
        "tconstruct:modifier_set_worktable", "tconstruct:enchantment_converting",
        "tconstruct:toggle_interaction",
    ), _TC_WORKTABLE),
    "tconstruct:modifier_salvage": _tc_tool(
        "modifier salvage entry: which modifier slots come back to a tool when `modifier` is removed "
        "from it at the worktable (ModifierSalvage LOADER L30-38, read by ModifierRemovalRecipe "
        "through ModifierRecipeLookup#getSalvage); it is data for the tool's slot bookkeeping, not a "
        "recipe with an output"
    ),
    "tconstruct:material": _tc_tool(
        "material recipe: it says how much of the tool `material` the `ingredient` is worth (`value` "
        "per `needed`, with any `leftover`) to the Part Builder and the other recipes that count "
        "material value (MaterialRecipe LOADER L35-43); it makes nothing by itself"
    ),
    **dict.fromkeys((
        "tconstruct:part_builder", "tconstruct:item_part_builder", "tconstruct:part_builder_recycling",
        "tconstruct:part_builder_tool_recycling",
    ), _TC_PART_BUILDER),
    **dict.fromkeys((
        "tconstruct:crafting_shaped_material", "tconstruct:crafting_shaped_materials",
        "tconstruct:crafting_shapeless_materials",
    ), _tc_tool(
        "crafting-table recipe whose result stores the tool materials of its grid ingredients on "
        "the stack (ShapedMaterialsRecipe/ShapelessMaterialsRecipe set the result's MaterialNBT; "
        "such as traveler's armour, or the Tinker's Anvil and forge whose metal the grid chooses)"
    )),
    **dict.fromkeys((
        "tconstruct:severing", "tconstruct:ageable_severing", "tconstruct:player_beheading",
        "tconstruct:snow_golem_beheading", "tconstruct:mooshroom_demushrooming",
        "tconstruct:sheep_shearing",
    ), _TC_SEVERING),
    # ShapelessGearRecipe/ShapedGearRecipe#assemble: item.construct(getParts(inv)),
    # matches only while each part allows crafting that gear type.
    **dict.fromkeys(("silentgear:gear_crafting", "silentgear:shaped_gear_crafting"), _sg_gear(
        "gear crafting recipe: the parts in the grid build the gear item, and its stats and traits "
        "come from the parts' materials (ShapelessGearRecipe/ShapedGearRecipe#assemble, "
        "ICoreItem#construct)"
    )),
    # ShapelessCompoundPartRecipe#assemble: item.create(getMaterials(inv), count).
    "silentgear:compound_part": _sg_gear(
        "compound part recipe: the materials in the grid make a part that stores them on the stack "
        "(ShapelessCompoundPartRecipe#assemble, CompoundPartItem#create)"
    ),
    # ConversionRecipe#assemble L95-106: construct from result.materials, copy
    # damage and enchantments from the input tool; config allowConversionRecipes.
    "silentgear:conversion": _sg_gear(
        "conversion recipe: an ordinary tool becomes a gear item built from the `result.materials` "
        "it lists, keeping the input's damage and enchantments (ConversionRecipe#assemble), when the "
        "allowConversionRecipes config is on"
    ),
    # Coating/UpgradeSmithingRecipe#applyUpgrade: GearData.addOrReplacePart /
    # addPart, then GearData.recalculateStats.
    "silentgear:smithing/coating": _sg_gear(
        "smithing coating recipe: the material in the smithing table becomes the gear's coating "
        "part and its stats are recalculated (CoatingSmithingRecipe#applyUpgrade)"
    ),
    "silentgear:smithing/upgrade": _sg_gear(
        "smithing upgrade recipe: the upgrade part is added to the gear's parts and its stats are "
        "recalculated (UpgradeSmithingRecipe#applyUpgrade)"
    ),
    **dict.fromkeys(("silentgear:salvaging/gear", "silentgear:salvaging/compound_part"), _sg_gear(
        "salvaging recipe: the Salvager takes a gear item or compound part back into the parts and "
        "materials stored on that stack, each lost with a damage-based chance "
        "(GearSalvagingRecipe#getPossibleResults, SalvagerTileEntity#getLossRate)"
    )),
    # MaterialPressingRecipe#assemble: CraftedMaterialItem#create(material of input).
    "silentgear:pressing/material": _sg_gear(
        "material pressing recipe: the Metal Press turns a material into a crafted material item "
        "that carries the input's material on the stack (MaterialPressingRecipe#assemble)"
    ),
}


def modular_tool_reason(java_type: object) -> str | None:
    """Why a recipe of this type builds, changes or takes apart a modular tool
    (#175), or None if it isn't one this module knows: a type in
    :data:`_MODULAR_TOOL_RECIPES`."""
    return _MODULAR_TOOL_RECIPES.get(java_type) if isinstance(java_type, str) else None


# A recipe that runs in one of Mekanism's machines (#172) or Create's
# rotation-powered machines (#173) is residue of its own kind. The JSON names
# the inputs and outputs, but the machine is the mod's block-entity code. A
# Mekanism machine holds the inputs, outputs, energy and any chemical or
# fluid in its own slots and tanks, and works the recipe over ticks, faster or
# cheaper with upgrades (TileEntityProgressMachine L73-74 via
# MekanismUtils#getTicks; TileEntityRecipeMachine). A Bedrock custom block has
# no ticking inventory, tank or energy store, and Mekanism's chemicals (gases,
# infuse types, pigments, slurries) have no Bedrock form, so there is no
# Bedrock station to tag these for. A crafting stand-in at the machine block
# would be a gameplay change (instant, free, chance outputs dropped), which #172
# leaves to a decision; a scripted machine runtime doesn't exist yet. The
# residue agent skips the kind (agent/residue.py SKIP_KINDS).
# docs/decisions.md, 2026-10-15. Create's machines turn only while a
# rotational network (shafts and cogwheels from a power source) gives them
# speed, and work faster with more of it; see _CREATE_MACHINE_RECIPES.
MACHINE_RECIPE = "machine_recipe"

# What Bedrock lacks, said once at the end of every machine recipe's reason.
_NO_BEDROCK_MACHINE = (
    "a Bedrock custom block has no ticking inventory, tank or energy store, so there is no Bedrock "
    "station to run it (that needs a scripted machine runtime, #172), and an instant crafting "
    "stand-in at the machine block would drop the processing time and what the machine consumes"
)
_NO_BEDROCK_CHEMICAL = (
    "Mekanism's chemicals (gases, infuse types, pigments, slurries) have no Bedrock form"
)
_NO_BEDROCK_MB = "Bedrock can't store a measured amount of fluid (#174)"


def _mek(what: str, *lacks: str) -> str:
    return "; ".join((f"a Mekanism {what}", *lacks, _NO_BEDROCK_MACHINE))


# What Bedrock lacks for a Create machine, said once at the end of each reason.
_NO_BEDROCK_KINETICS = (
    "the machine works only while Create's rotational network (shafts and cogwheels carrying speed "
    "and stress from a source such as a water wheel, windmill or steam engine) turns it, faster at "
    "higher speed, and a Bedrock custom block has no rotational network and no ticking inventory, "
    "so there is no Bedrock station to run it (that needs a scripted kinetic runtime, #173), and an instant "
    "crafting stand-in would drop the rotation and the processing time"
)
_NO_BEDROCK_BASIN_FLUID = (
    "a fluid ingredient or result (an `amount` in mB) can't be carried, since Bedrock can't store a "
    "measured amount of fluid (#174)"
)
_NO_BEDROCK_CHANCE = (
    "a Bedrock recipe result has no chance field, so `results` entries with a `chance` below 1 "
    "can't be carried"
)


def _create(what: str, *lacks: str) -> str:
    return "; ".join((f"a Create {what}", *lacks, _NO_BEDROCK_KINETICS))


# Create mc1.20.1-6.0.8 for Forge 1.20.1 (Creators-of-Create/Create
# @1a1a9a28; the jar's Implementation-Version 6.0.8): types registered in
# AllRecipeTypes L49-66; processing recipe fields from
# ProcessingRecipeSerializer L41-85 (ingredients, results, processingTime,
# heatRequirement) and ProcessingOutput L85 (a result's `chance`, default 1).
# The machine that runs each type is where Java looks the type up:
# CRUSHING in CrushingWheelControllerBlockEntity L321 (which falls back to
# MILLING at L323), MILLING in MillstoneBlockEntity L103, CUTTING in
# SawBlockEntity L380-386, PRESSING and COMPACTING in
# MechanicalPressBlockEntity L185-204 (compacting over a basin), MIXING in
# MechanicalMixerBlockEntity L259-260 over a basin whose heat
# BasinRecipe#apply L75-77 tests, SPLASHING and HAUNTING in
# AllFanProcessingTypes L423 / L232 (the encased fan's air through the
# fan_processing_catalysts tags: water for splashing; lit blaze burner, soul
# fire and soul campfire for haunting, jar data/create/tags), DEPLOYING in
# DeployerBlockEntity L571-572, MECHANICAL_CRAFTING in RecipeGridHandler
# L152 (a grid of mechanical crafters; ShapedRecipe.setCraftingSize(9, 9) in
# AllRecipeTypes#register, acceptMirrored at MechanicalCraftingRecipe L91),
# SEQUENCED_ASSEMBLY in SequencedAssemblyRecipe#getRecipe/#advance L61-120
# (a transitional item stepped through the sequence `loops` times by the
# machines whose recipes implement IAssemblyRecipe: deploying, pressing,
# filling, cutting; the final result rolled by weight, #rollResult L143-150).
# Each machine idles at speed 0 (for example MillstoneBlockEntity L64,
# SawBlockEntity L137, DeployerBlockEntity L161). FILLING and EMPTYING are
# fluid_recipe (#174); ITEM_APPLICATION and SANDPAPER_POLISHING are
# code_recipe (used by hand, see _CODE_RECIPES); TOOLBOX_DYEING and
# ITEM_COPYING are data-free special recipes (code_recipe, #180).
_CREATE_MACHINE_RECIPES = {
    "create:crushing": _create(
        "crushing recipe: the `ingredients` dropped between two spinning create:crushing_wheel blocks "
        "are crushed into the `results` over `processingTime` "
        "(CrushingRecipe, CrushingWheelControllerBlockEntity)",
        _NO_BEDROCK_CHANCE,
    ),
    "create:milling": _create(
        "milling recipe: the `ingredients` put in a create:millstone (or dropped between crushing wheels "
        "when no crushing recipe matches) are ground into the `results` over `processingTime` "
        "(MillingRecipe, MillstoneBlockEntity, CrushingWheelControllerBlockEntity)",
        _NO_BEDROCK_CHANCE,
    ),
    "create:cutting": _create(
        "cutting recipe: the create:mechanical_saw cuts the item fed to it (on a belt or dropped onto "
        "it) into the `results` over `processingTime` (CuttingRecipe, SawBlockEntity)",
        _NO_BEDROCK_CHANCE,
    ),
    "create:pressing": _create(
        "pressing recipe: the create:mechanical_press stamps the item below it (on a belt, depot or "
        "the ground) into the `results` (PressingRecipe, MechanicalPressBlockEntity)",
        _NO_BEDROCK_CHANCE,
    ),
    "create:compacting": _create(
        "compacting recipe: the create:mechanical_press packs the `ingredients` held in a create:basin "
        "below it into the `results`, heated by a blaze burner when `heatRequirement` says so "
        "(CompactingRecipe, MechanicalPressBlockEntity, BasinRecipe)",
        _NO_BEDROCK_CHANCE, _NO_BEDROCK_BASIN_FLUID,
    ),
    "create:mixing": _create(
        "mixing recipe: the create:mechanical_mixer stirs the `ingredients` held in a create:basin "
        "below it into the `results`, heated by a blaze burner when `heatRequirement` says so "
        "(MixingRecipe, MechanicalMixerBlockEntity, BasinRecipe)",
        _NO_BEDROCK_CHANCE, _NO_BEDROCK_BASIN_FLUID,
    ),
    "create:splashing": _create(
        "splashing (bulk washing) recipe: items caught in a create:encased_fan's air stream after it "
        "passes through water become the `results` (SplashingRecipe, AllFanProcessingTypes "
        "SplashingType)",
        _NO_BEDROCK_CHANCE,
    ),
    "create:haunting": _create(
        "haunting recipe: items caught in a create:encased_fan's air stream after it passes through "
        "soul fire, a lit soul campfire or a soul-flame blaze burner become the `results` "
        "(HauntingRecipe, AllFanProcessingTypes HauntingType)",
        _NO_BEDROCK_CHANCE,
    ),
    "create:deploying": _create(
        "deploying recipe: a create:deployer holding the second ingredient uses it on the first (an "
        "item on a belt or depot in front of it) to make the `results`, using the held item up "
        "unless `keepHeldItem` is true (DeployerApplicationRecipe, DeployerBlockEntity)",
        _NO_BEDROCK_CHANCE,
    ),
    "create:mechanical_crafting": _create(
        "mechanical crafting recipe: a shaped `pattern` (up to 9x9) laid out across a grid of "
        "create:mechanical_crafter blocks, mirrored too unless `acceptMirrored` is false "
        "(MechanicalCraftingRecipe, RecipeGridHandler)",
        "Bedrock shaped recipes are at most 3x3, so most patterns don't fit a crafting table either",
    ),
    "create:sequenced_assembly": _create(
        "sequenced assembly recipe: the `ingredient` becomes the `transitionalItem` and is passed "
        "through the `sequence` of deploying, pressing, filling or cutting steps by those machines, "
        "`loops` times, before one of the `results` is picked by weight (SequencedAssemblyRecipe "
        "#advance and #rollResult)",
        "a Bedrock recipe makes one fixed result in one step, so the steps, the loops and the weighted "
        "pick can't be carried",
    ),
}

# Mekanism 10.7.19.85 for NeoForge 1.21.1 (mekanism/Mekanism tag
# v1.21.1-10.7.19.85 @a00109e4; the jar's Implementation-Version 10.7.19):
# serializers registered in MekanismRecipeSerializersInternal L54-98, recipe
# field names from SerializationConstants. The machine each type runs in is
# the recipe class's own getToastSymbol (the block Java shows for it):
# Basic{Crushing,Enriching,Smelting}Recipe L36, BasicChemicalInfuserRecipe L39,
# BasicPigmentMixingRecipe L39, BasicPigmentExtractingRecipe L36,
# Basic{Activating,Centrifuging,ChemicalOxidizer,Compressing,Injecting,
# MetallurgicInfuser,Painting,Purifying}Recipe L37, BasicWashingRecipe L60,
# CombinerRecipe L120, ElectrolysisRecipe L93, FluidToFluidRecipe L89,
# ChemicalCrystallizerRecipe L116, ChemicalDissolutionRecipe L30,
# NucleosynthesizingRecipe L43, PressurizedReactionRecipe L125, RotaryRecipe
# L160, SawmillRecipe L104. The two conversion types have no machine of their
# own: Java reads them from every energy slot (EnergyInventorySlot L33/L131)
# and every chemical slot that fills or converts (ChemicalInventorySlot
# L34/L223). Base processing times are the tile classes'
# BASE_TICKS_REQUIRED; the Solar Neutron Activator needs sky
# (TileEntitySolarNeutronActivator#canSeeSun L178-186) and the evaporation
# tower is a heat-driven multiblock (EvaporationMultiblockData).
_MACHINE_RECIPES = {
    "mekanism:crushing": _mek(
        "Crusher recipe: `input` becomes `output` in mekanism:crusher (or a crushing factory) over "
        "time, using energy (BasicCrushingRecipe, TileEntityElectricMachine)"
    ),
    "mekanism:enriching": _mek(
        "Enrichment Chamber recipe: `input` becomes `output` in mekanism:enrichment_chamber (or an "
        "enriching factory) over time, using energy (BasicEnrichingRecipe, TileEntityElectricMachine)"
    ),
    "mekanism:smelting": _mek(
        "Energized Smelter recipe: `input` becomes `output` in mekanism:energized_smelter (or a "
        "smelting factory) over time, using energy (BasicSmeltingRecipe, TileEntityElectricMachine)"
    ),
    "mekanism:sawing": _mek(
        "Precision Sawmill recipe: `input` becomes `main_output` in mekanism:precision_sawmill (or a "
        "sawing factory) over time, using energy, with any `secondary_output` produced "
        "at `secondary_chance` (SawmillRecipe, TileEntityPrecisionSawmill)",
        "a Bedrock recipe result has no chance field, so a `secondary_chance` below 1 can't be carried",
    ),
    "mekanism:combining": _mek(
        "Combiner recipe: `main_input` and `extra_input` become `output` in mekanism:combiner (or a "
        "combining factory) over time, using energy (CombinerRecipe, TileEntityCombiner)"
    ),
    **{t: _mek(
        f"{machine} recipe: `item_input` becomes `output` in mekanism:{block} (or a {factory} factory) "
        f"over time, using energy and drawing `chemical_input` from the machine's chemical tank (each "
        f"tick when `per_tick_usage` is true, else once; {cls}, TileEntity{tile})",
        _NO_BEDROCK_CHEMICAL,
    ) for t, machine, block, factory, cls, tile in (
        ("mekanism:compressing", "Osmium Compressor", "osmium_compressor", "compressing",
         "BasicCompressingRecipe", "OsmiumCompressor"),
        ("mekanism:purifying", "Purification Chamber", "purification_chamber", "purifying",
         "BasicPurifyingRecipe", "PurificationChamber"),
        ("mekanism:injecting", "Chemical Injection Chamber", "chemical_injection_chamber", "injecting",
         "BasicInjectingRecipe", "ChemicalInjectionChamber"),
        ("mekanism:metallurgic_infusing", "Metallurgic Infuser", "metallurgic_infuser", "infusing",
         "BasicMetallurgicInfuserRecipe", "MetallurgicInfuser"),
    )},
    "mekanism:painting": _mek(
        "Painting Machine recipe: `item_input` is painted into `output` in mekanism:painting_machine "
        "over time, using energy and drawing pigment `chemical_input` from its tank (each tick when "
        "`per_tick_usage` is true, else once; BasicPaintingRecipe, TileEntityPaintingMachine)",
        _NO_BEDROCK_CHEMICAL,
    ),
    "mekanism:nucleosynthesizing": _mek(
        "Antiprotonic Nucleosynthesizer recipe: `item_input` becomes `output` in "
        "mekanism:antiprotonic_nucleosynthesizer over `duration` ticks, using energy and drawing "
        "`chemical_input` (antimatter) from its tank, each tick when `per_tick_usage` is true "
        "(NucleosynthesizingRecipe, "
        "TileEntityAntiprotonicNucleosynthesizer)",
        _NO_BEDROCK_CHEMICAL,
    ),
    "mekanism:dissolution": _mek(
        "Chemical Dissolution Chamber recipe: `item_input` dissolves with `chemical_input` into the "
        "chemical `output` in mekanism:chemical_dissolution_chamber over time, using energy, the "
        "chemical drawn each tick when `per_tick_usage` is true (ChemicalDissolutionRecipe, "
        "TileEntityChemicalDissolutionChamber)",
        _NO_BEDROCK_CHEMICAL,
    ),
    "mekanism:oxidizing": _mek(
        "Chemical Oxidizer recipe: `input` is turned into the chemical `output` in "
        "mekanism:chemical_oxidizer over time, using energy (BasicChemicalOxidizerRecipe, "
        "TileEntityChemicalOxidizer)",
        _NO_BEDROCK_CHEMICAL,
    ),
    "mekanism:pigment_extracting": _mek(
        "Pigment Extractor recipe: `input` is turned into the pigment `output` in "
        "mekanism:pigment_extractor over time, using energy (BasicPigmentExtractingRecipe, "
        "TileEntityPigmentExtractor)",
        _NO_BEDROCK_CHEMICAL,
    ),
    "mekanism:chemical_infusing": _mek(
        "Chemical Infuser recipe: the chemicals `left_input` and `right_input` combine into `output` "
        "in mekanism:chemical_infuser, using energy (BasicChemicalInfuserRecipe, "
        "TileEntityChemicalInfuser)",
        _NO_BEDROCK_CHEMICAL,
    ),
    "mekanism:pigment_mixing": _mek(
        "Pigment Mixer recipe: the pigments `left_input` and `right_input` mix into `output` in "
        "mekanism:pigment_mixer, using energy (BasicPigmentMixingRecipe, TileEntityPigmentMixer)",
        _NO_BEDROCK_CHEMICAL,
    ),
    "mekanism:centrifuging": _mek(
        "Isotopic Centrifuge recipe: the chemical `input` becomes the chemical `output` in "
        "mekanism:isotopic_centrifuge, using energy (BasicCentrifugingRecipe, "
        "TileEntityIsotopicCentrifuge)",
        _NO_BEDROCK_CHEMICAL,
    ),
    "mekanism:activating": _mek(
        "Solar Neutron Activator recipe: the chemical `input` becomes the chemical `output` in "
        "mekanism:solar_neutron_activator, only while it can see the sky (BasicActivatingRecipe, "
        "TileEntitySolarNeutronActivator#canSeeSun)",
        _NO_BEDROCK_CHEMICAL,
    ),
    "mekanism:crystallizing": _mek(
        "Chemical Crystallizer recipe: the chemical `input` crystallizes into the item `output` in "
        "mekanism:chemical_crystallizer over time, using energy (ChemicalCrystallizerRecipe, "
        "TileEntityChemicalCrystallizer)",
        _NO_BEDROCK_CHEMICAL,
    ),
    "mekanism:washing": _mek(
        "Chemical Washer recipe: `fluid_input` washes the slurry `chemical_input` into `output` in "
        "mekanism:chemical_washer, using energy (BasicWashingRecipe, TileEntityChemicalWasher)",
        _NO_BEDROCK_CHEMICAL, _NO_BEDROCK_MB,
    ),
    "mekanism:separating": _mek(
        "Electrolytic Separator recipe: the fluid `input` splits into `left_chemical_output` and "
        "`right_chemical_output` in mekanism:electrolytic_separator, using energy (ElectrolysisRecipe, "
        "TileEntityElectrolyticSeparator)",
        _NO_BEDROCK_CHEMICAL, _NO_BEDROCK_MB,
    ),
    "mekanism:rotary": _mek(
        "Rotary Condensentrator recipe: `chemical_input` condenses into `fluid_output`, or "
        "`fluid_input` decondenses into `chemical_output`, by the mode set on "
        "mekanism:rotary_condensentrator, using energy (RotaryRecipe, "
        "TileEntityRotaryCondensentrator)",
        _NO_BEDROCK_CHEMICAL, _NO_BEDROCK_MB,
    ),
    "mekanism:evaporating": _mek(
        "Thermal Evaporation recipe: the fluid `input` evaporates into the fluid `output` in the "
        "thermal evaporation tower (a multiblock run from mekanism:thermal_evaporation_controller) "
        "at a rate set by the tower's heat (FluidToFluidRecipe, EvaporationMultiblockData)",
        _NO_BEDROCK_MB,
    ),
    "mekanism:reaction": _mek(
        "Pressurized Reaction Chamber recipe: `item_input`, `fluid_input` and `chemical_input` react "
        "over `duration` ticks, using extra `energy_required`, into `item_output` and "
        "`chemical_output` in mekanism:pressurized_reaction_chamber (PressurizedReactionRecipe, "
        "TileEntityPressurizedReactionChamber)",
        _NO_BEDROCK_CHEMICAL, _NO_BEDROCK_MB,
    ),
    "mekanism:energy_conversion": _mek(
        "energy conversion: `input` placed in a Mekanism machine's or energy cube's energy slot is "
        "used up for `output` energy (ItemStackToEnergyRecipe, EnergyInventorySlot#fillOrConvert); "
        "there is no "
        "crafted result, and Bedrock has no energy store to add to"
    ),
    "mekanism:chemical_conversion": _mek(
        "chemical conversion: `input` placed in a Mekanism machine's chemical slot is used up for "
        "the chemical `output` in its tank (BasicChemicalConversionRecipe, "
        "ChemicalInventorySlot#fillOrConvert); there "
        "is no crafted result",
        _NO_BEDROCK_CHEMICAL,
    ),
    **_CREATE_MACHINE_RECIPES,
}


def machine_recipe_reason(java_type: object) -> str | None:
    """Why a recipe of this type runs in a Mekanism (#172) or Create (#173)
    machine, or None if it isn't one this module knows: a type in
    :data:`_MACHINE_RECIPES`."""
    return _MACHINE_RECIPES.get(java_type) if isinstance(java_type, str) else None


def code_recipe_reason(java_type: object, recipe: dict, loader: str | None = None) -> str | None:
    """Why a recipe of this modded type is code (#180), or None if it isn't
    one this module knows to be: a type in :data:`_CODE_RECIPES`, or a
    non-vanilla type whose JSON carries nothing but recipe-book fields and
    ``loader``'s load conditions (a "special" recipe)."""
    if not isinstance(java_type, str):
        return None
    if java_type in _CODE_RECIPES:
        return _CODE_RECIPES[java_type]
    if java_type.startswith("minecraft:"):
        return None
    if set(recipe) - _NO_DATA_KEYS - set(condition_keys(loader)):
        return None
    return (
        f"a special recipe ({java_type!r}): its JSON holds no ingredient and no result, only its type, "
        "so what it takes and what it makes are the mod's Java code; a Bedrock recipe would have to "
        "invent both"
    )

# Convention tags that name exactly one vanilla item. Both loaders ship these
# (Forge under forge:, Fabric and NeoForge under c:) and a mod using one means
# the single vanilla item in practice. Anything not here stays residue: a tag
# covering several items is a choice, and guessing which one is how you ship a
# recipe that crafts the wrong thing.
_SINGLE_ITEM_TAGS = {
    "ingots/iron": "minecraft:iron_ingot",
    "ingots/gold": "minecraft:gold_ingot",
    "ingots/copper": "minecraft:copper_ingot",
    "ingots/netherite": "minecraft:netherite_ingot",
    "ingots/brick": "minecraft:brick",
    "gems/diamond": "minecraft:diamond",
    "gems/emerald": "minecraft:emerald",
    "gems/lapis": "minecraft:lapis_lazuli",
    "gems/quartz": "minecraft:quartz",
    "gems/amethyst": "minecraft:amethyst_shard",
    "gems/prismarine": "minecraft:prismarine_shard",
    "dusts/redstone": "minecraft:redstone",
    "dusts/glowstone": "minecraft:glowstone_dust",
    "rods/wooden": "minecraft:stick",
    "rods/blaze": "minecraft:blaze_rod",
    "nuggets/iron": "minecraft:iron_nugget",
    "nuggets/gold": "minecraft:gold_nugget",
    "leather": "minecraft:leather",
    "string": "minecraft:string",
    "gunpowder": "minecraft:gunpowder",
    "obsidian": "minecraft:obsidian",
    "ender_pearls": "minecraft:ender_pearl",
    "slimeballs": "minecraft:slime_ball",
    "feathers": "minecraft:feather",
    "bones": "minecraft:bone",
    "eggs": "minecraft:egg",
    "netherrack": "minecraft:netherrack",
    "glowstone": "minecraft:glowstone",
}
_TAG_NAMESPACES = ("forge:", "c:", "neoforge:")

# Vanilla tags Bedrock's own recipes take as ingredients, under the same name
# and meaning as Java's. Read from Mojang/bedrock-samples behavior_pack/recipes
# on 2026-10-02 (e.g. torch and campfire take {"tag": "minecraft:coals"}, soul
# campfire takes minecraft:soul_fire_base_blocks). These pass through as tags,
# so the recipe accepts the same set of items it does in Java. Bedrock tags with
# no Java twin of the same name (is_pickaxe, mushrooms_for_stew, metal_nuggets,
# trim_*) are left out on purpose.
_BEDROCK_VANILLA_TAGS = frozenset({
    "minecraft:coals",
    "minecraft:logs",
    "minecraft:logs_that_burn",
    "minecraft:planks",
    "minecraft:soul_fire_base_blocks",
    "minecraft:stone_crafting_materials",
    "minecraft:stone_tool_materials",
    "minecraft:wooden_slabs",
    "minecraft:wool",
})


def resolve_tag(tag: str) -> str | None:
    """A convention tag that unambiguously means one vanilla item, or None."""
    for prefix in _TAG_NAMESPACES:
        if tag.startswith(prefix):
            return _SINGLE_ITEM_TAGS.get(tag[len(prefix):])
    return None


def _ingredient(spec):
    """A 1.21.2+ bare-string ingredient in the older object form (#194).

    Since Minecraft 1.21.2 an ingredient may be a bare string: ``"#ns:path"``
    names a tag, any other string an item. A tag string becomes ``{"tag":
    "ns:path"}`` so it takes the same path as the object form (pass-through,
    single-member resolve, membership, residue reason); an item string stays as
    it is, which :func:`_item` and :func:`_listed_items` already read as the
    item. List entries are normalized the same way.
    """
    if isinstance(spec, str) and spec.startswith("#"):
        return {"tag": spec[1:]}
    if isinstance(spec, list):
        return [_ingredient(entry) for entry in spec]
    return spec


def _result_item(spec, tags: TagResolver | None = None) -> dict | None:
    """A recipe's result as ``{"item": id}``, or None when it isn't one item.

    A result is always an item in Java; a ``#`` name there is a malformed recipe
    Java refuses to load, so it is never read as a tag (or resolved to a member).
    """
    ident = spec.get("id", spec.get("item")) if isinstance(spec, dict) else spec
    if isinstance(ident, str) and ident.startswith("#"):
        return None
    return _item(spec, tags)


def _item(spec, tags: TagResolver | None = None) -> dict | None:
    """Java item specs come in several shapes. Only translate the unambiguous ones."""
    if isinstance(spec, str) and spec.startswith("#"):
        return _item(_ingredient(spec), tags)  # a tag, never an item id (#194)
    if isinstance(spec, str):
        return {"item": spec}
    listed = _listed_items(spec)
    if listed is not None and len(listed) == 1:
        return {"item": listed[0]}  # "any of [x]" is x
    if isinstance(spec, dict):
        if "item" in spec:
            return {"item": spec["item"]}
        if "id" in spec:
            return {"item": spec["id"]}
        if "tag" in spec:
            if _passes_through(str(spec["tag"]), tags):
                return {"tag": str(spec["tag"])}
            resolved = resolve_tag(str(spec["tag"]))
            if resolved and not (tags is not None and tags.own_share(str(spec["tag"]))):
                # The table names the loader's one vanilla member; a mod that adds
                # its own item to the tag goes through the full membership instead,
                # so the recipe doesn't lose that item (#160).
                return {"item": resolved}
            if tags is not None:
                found = tags.resolve(str(spec["tag"])).item
                return {"item": found} if found else None
            return None
    # multi-item tags and weighted lists have no clean 1:1 Bedrock form
    return None


def _passes_through(tag: str, tags: TagResolver | None) -> bool:
    """Whether Bedrock's own tag of this name is the whole Java tag.

    True for a :data:`_BEDROCK_VANILLA_TAGS` tag the mod adds nothing to. When
    the mod adds its own members (Silent Gear's netherwood planks in
    ``minecraft:planks``), Bedrock's tag alone would drop them, so the recipe
    goes through the full membership instead (see :func:`convert`).
    """
    if tag not in _BEDROCK_VANILLA_TAGS:
        return False
    return tags is None or tags.mod_additions(tag) == []


def _tag_reason(spec, tags: TagResolver | None = None) -> str:
    if isinstance(spec, dict) and "tag" in spec and tags is not None:
        tag = str(spec["tag"])
        nested = tags.unknown_nested(tag) if tag in _BEDROCK_VANILLA_TAGS else []
        if nested and tags.mod_additions(tag) is None:
            # Bedrock has this tag, but without the vanilla tag data it can't be
            # told whether the jar's own share of a nested tag belongs in it.
            shown = ", ".join(nested[:3]) + (f" and {len(nested) - 3} more" if len(nested) > 3 else "")
            return (
                f"ingredient uses tag {tag!r}, which Bedrock also has, but this jar adds to "
                f"{shown}, which vanilla may nest in it, and without the vanilla tag data "
                f"(run `{FETCH_COMMAND}`) Bedrock's tag alone could drop those members"
            )
        return tags.resolve(tag).reason
    if isinstance(spec, dict) and "tag" in spec:
        return f"ingredient uses tag {spec['tag']!r}, which covers more than one item"
    listed = _listed_items(spec)
    if listed is not None:
        return (f"ingredient is a list of {len(listed)} items ({', '.join(listed)}); it converts "
                f"as one recipe per item only when every item is converted, it is the "
                f"recipe's only such ingredient, it fills one grid slot, and it has at most "
                f"{EXPANSION_CAP} items")
    if isinstance(spec, list):
        return "ingredient is a list holding a tag or a non-item entry"
    return "ingredient uses a tag or item list"


def _smithing_item(spec, tags: TagResolver | None = None) -> str | None:
    """Bedrock smithing slots take a bare item id; a multi-item tag has no form."""
    mapped = _item(spec, tags)
    return mapped.get("item") if mapped else None


def _smithing(recipe: dict, identifier: str, rel: str, result: ConversionResult, tags=None):
    """A Java smithing_transform, as Bedrock's smithing or (when incomplete) crafting.

    Complete (template, base and addition all name an item): Bedrock has the
    same recipe, ``minecraft:recipe_smithing_transform`` on the smithing table.

    Incomplete (template or addition missing): Bedrock's smithing recipe needs
    all three, and inventing the missing ones changes what the player has to
    gather (#87). So it becomes a shapeless crafting recipe from the inputs the
    source does name to its result, and the downgrade is said in the notes.
    Returns (body key, body) or None when the recipe went to residue.
    """
    slots = {}
    for slot in ("template", "base", "addition"):
        spec = _ingredient(recipe.get(slot))
        if spec in (None, "", {}, []):
            continue
        item = _smithing_item(spec, tags)
        if item is None:
            result.unhandled.append(Unhandled(rel, "recipe", f"smithing {slot}: {_tag_reason(spec, tags)}"))
            return None
        slots[slot] = item
    mapped_out = _result_item(recipe.get("result"), tags)
    out = mapped_out.get("item") if mapped_out else None
    if out is None or "base" not in slots:
        result.unhandled.append(
            Unhandled(rel, "recipe", "smithing recipe has no readable base or result item")
        )
        return None
    description = {"identifier": identifier}
    if len(slots) == 3:
        return "minecraft:recipe_smithing_transform", {
            "description": description,
            "tags": ["smithing_table"],
            "template": slots["template"],
            "base": slots["base"],
            "addition": slots["addition"],
            "result": out,
        }
    missing = [s for s in ("template", "addition") if s not in slots]
    result.notes.append(
        f"{rel}: smithing recipe has no {' or '.join(missing)}, which Bedrock's smithing "
        "table requires; converted to a shapeless crafting recipe from the inputs it names"
    )
    return "minecraft:recipe_shapeless", {
        "description": description,
        "tags": ["crafting_table"],
        "ingredients": [{"item": slots[s]} for s in ("template", "base", "addition") if s in slots],
        "result": {"item": out},
    }


def emitted_definitions(files: dict) -> dict[str, tuple[str, str, dict]]:
    """identifier -> (kind, path, body) for every block and item definition in ``files``.

    kind is ``"item"``, ``"block"``, or ``"block_and_item"`` for a block that
    also has its own item file (path and body are then the first one seen).
    """
    found: dict[str, tuple[str, str, dict]] = {}
    for path, body in files.items():
        if not isinstance(body, dict):
            continue
        for key, kind in (("minecraft:item", "item"), ("minecraft:block", "block")):
            root = body.get(key)
            ident = ((root or {}).get("description") or {}).get("identifier") if isinstance(root, dict) else None
            if not isinstance(ident, str):
                continue
            if ident in found and found[ident][0] != kind:
                # A block with its own item file: which one a recipe slot sees
                # depends on how the player got it, so neither can be tagged alone.
                found[ident] = ("block_and_item", *found[ident][1:])
            else:
                found.setdefault(ident, (kind, path, body))
    return found


@dataclass
class _Multi:
    """A tag ingredient whose every member this addon holds."""

    spec: dict
    found: MultiMembers
    # Every member of this mod can carry the Java tag as a native tag: an
    # emitted item in its minecraft:tags, an emitted block through a replacing
    # block_placer item (see _block_item). Members that can't (vanilla items,
    # a block that has its own item file) are in ``extras``.
    taggable: bool
    vanilla_tag: str | None = None  # a Bedrock vanilla tag with the same membership
    # A Bedrock vanilla tag of the same name whose every member this mod adds
    # can carry it: an emitted item, or an emitted block given an item form.
    bedrock_tag: bool = False
    # Members a native tag can't hold, each needing its own recipe beside the
    # tag recipe: vanilla items, and blocks that already have an item file.
    extras: list = None  # type: ignore[assignment]
    # The ingredient is a JSON list of items, not a tag: it can only be written
    # once per member (form 3), and ``found.tag`` is a label, not a tag id.
    listed: bool = False


def _bedrock_equivalent(found: MultiMembers, tags: TagResolver) -> str | None:
    """A Bedrock vanilla tag whose Java twin has exactly this membership, or None.

    Only the tags in :data:`_BEDROCK_VANILLA_TAGS`, whose Bedrock meaning matches
    Java's, and only when the vanilla reference data gives the twin's full
    membership: then ``{"tag": "minecraft:planks"}`` accepts the same items the
    Java tag does.
    """
    wanted = set(found.members)
    for candidate in sorted(_BEDROCK_VANILLA_TAGS):
        if candidate == found.tag:
            continue
        twin = tags.members(candidate)
        if (twin is not None and not twin.dropped and set(twin.members) == wanted
                and all(m.startswith("minecraft:") for m in twin.members)):
            # Bedrock's own tag holds only vanilla items, so a twin the mod
            # adds to is not the same set on Bedrock.
            return candidate
    return None


def _listed_items(spec) -> list[str] | None:
    """The item ids of a list ingredient made only of plain items, else None.

    Accepts ``{"item": id}`` entries and bare id strings (the 1.21.2+ form); a
    tag entry (``{"tag": ...}``, ``"#..."``) or anything else gives None.
    """
    if not isinstance(spec, list) or not spec:
        return None
    ids: list[str] = []
    for entry in spec:
        if isinstance(entry, dict) and set(entry) == {"item"} and isinstance(entry["item"], str):
            ids.append(entry["item"])
        elif isinstance(entry, str) and not entry.startswith("#"):
            ids.append(entry)
        else:
            return None
    return [i if ":" in i else f"minecraft:{i}" for i in dict.fromkeys(ids)]


def _list_label(ids: list[str]) -> str:
    return "[" + ", ".join(ids) + "]"


def _list_reason(multi: _Multi, slots: int, others: int) -> str:
    """Why a fully converted item-list ingredient still can't be written."""
    ids = multi.found.members
    head = f"ingredient is a list of {len(ids)} items ({', '.join(ids)})"
    if slots != 1:
        return (f"{head} filling {slots} grid slots; the player may mix items across them, "
                "which one recipe per item would forbid, and the mod declares no tag to take")
    if others > 1:
        return f"{head}, beside another multi-item ingredient; one recipe per item covers only one"
    return f"{head}, more than the {EXPANSION_CAP} recipes one per item is capped at"


def _multi_list(spec, emitted: dict | None) -> _Multi | None:
    """A list-of-items ingredient whose every item this addon holds, or None."""
    ids = _listed_items(spec)
    if emitted is None or ids is None:
        return None
    if any(not i.startswith("minecraft:") and i not in emitted for i in ids):
        return None
    if len(ids) == 1:
        return None  # _item reads a one-entry list as its lone member
    return _Multi(spec=spec, found=MultiMembers(tag=_list_label(ids), members=ids),
                  taggable=False, extras=[], listed=True)


def _multi_tag(spec, tags: TagResolver, emitted: dict | None) -> _Multi | None:
    """The tag (or item-list) ingredient as a known, fully emitted membership, or None."""
    if isinstance(spec, list):
        return _multi_list(spec, emitted)
    if emitted is None or not isinstance(spec, dict) or not isinstance(spec.get("tag"), str):
        return None
    found = tags.members(spec["tag"])
    if found is None or len(found.members) < 2:
        return None
    kinds = []
    for member in found.members:
        if member.startswith("minecraft:"):
            kinds.append("vanilla")
        elif member in emitted:
            kinds.append(emitted[member][0])
        else:
            return None  # a member this conversion did not emit: not ours to drop
    own = [k for k in kinds if k != "vanilla"]
    taggable = (not found.tag.startswith("minecraft:")
                and any(k in ("item", "block") for k in own))
    extras = [m for m, k in zip(found.members, kinds) if k in ("vanilla", "block_and_item")]
    # Bedrock's tag holds vanilla's whole share, so only when the jar's file
    # doesn't replace the tag (mod_additions is None then).
    bedrock_tag = (found.tag in _BEDROCK_VANILLA_TAGS and tags.mod_additions(found.tag) is not None
                   and all(k in ("vanilla", "item", "block") for k in kinds))
    return _Multi(spec=spec, found=found, taggable=taggable, vanilla_tag=_bedrock_equivalent(found, tags),
                  bedrock_tag=bedrock_tag, extras=extras)


def _not_emitted(spec, tags: TagResolver, emitted: dict | None) -> list[str]:
    """Members of a known tag ingredient that this conversion did not emit."""
    listed = _listed_items(spec)
    if listed is not None:
        if emitted is None:
            return []
        return [m for m in listed if not m.startswith("minecraft:") and m not in emitted]
    if emitted is None or not isinstance(spec, dict) or not isinstance(spec.get("tag"), str):
        return []
    found = tags.members(spec["tag"])
    if found is None:
        return []
    return [m for m in found.members if not m.startswith("minecraft:") and m not in emitted]


def _max_format(current, minimum: str) -> str:
    """The later of two dotted format versions."""
    def parse(text):
        try:
            return tuple(int(p) for p in str(text).split("."))
        except ValueError:
            return ()
    return current if isinstance(current, str) and parse(current) >= parse(minimum) else minimum


def _block_item(identifier: str, block_path: str) -> tuple[str, dict]:
    """(path, body) of an item standing in as a block's own item, to carry tags.

    A block's ``minecraft:tags`` are block tags; recipes match item tags. Since
    format 1.21.50 an item whose identifier is the block's and whose
    ``minecraft:block_placer`` sets ``replace_block_item`` becomes the block's
    item (what breaking or picking the block gives), and that item can carry
    ``minecraft:tags``. Vanilla does exactly this: bedrock-samples'
    ``items/shelf_mushroom.json`` replaces the block's item and tags it
    ``minecraft:mushrooms_for_stew``, which ``recipes/mushroom_stew.json`` takes
    as a tag (learn.microsoft.com, Items Documentation - minecraft:block_placer).
    No icon: a block placer without ``minecraft:icon`` renders the block. The
    display name is the block's lang key, as the vanilla samples do.
    """
    stem = block_path.rsplit("/", 1)[-1]
    return f"items/{stem}", {
        "format_version": _BLOCK_ITEM_FORMAT,
        "minecraft:item": {
            "description": {"identifier": identifier},
            "components": {
                "minecraft:block_placer": {"block": identifier, "replace_block_item": True},
                "minecraft:display_name": {"value": f"tile.{identifier}.name"},
            },
        },
    }


def _qualified(rel: PurePosixPath) -> str:
    """A recipe's whole path under ``recipes/``, folders joined by ``_``."""
    return "_".join(rel.with_suffix("").parts)


def recipe_names(rels: list[PurePosixPath]) -> tuple[dict[PurePosixPath, str], dict[PurePosixPath, str]]:
    """Output name per recipe file (paths relative to ``recipes/``), and the refused ones.

    A stem no other file shares is kept as it is, so a recipe that never
    collided keeps the name (and identifier) it always had. A stem several
    files share is qualified for every one of them by its whole path: none of
    them is picked to keep the bare name, so the outcome depends only on which
    files exist, never on the order they are read in. A qualified name can
    still meet an unshared stem (``x/planks`` and ``x_planks``) or another
    qualified name; the unshared stem keeps its name, and every qualified file
    that lands on a taken name is refused, mapped to the file(s) it met.
    """
    by_stem: dict[str, list[PurePosixPath]] = {}
    for rel in rels:
        by_stem.setdefault(rel.stem, []).append(rel)
    names: dict[PurePosixPath, str] = {}
    for stem, group in by_stem.items():
        if len(group) == 1:
            names[group[0]] = stem
    bare = {name: rel for rel, name in names.items()}
    qualified: dict[str, list[PurePosixPath]] = {}
    for stem, group in by_stem.items():
        if len(group) > 1:
            for rel in group:
                qualified.setdefault(_qualified(rel), []).append(rel)
    refused: dict[PurePosixPath, str] = {}
    for name, group in qualified.items():
        if name in bare or len(group) > 1:
            for rel in group:
                others = sorted({*(r.as_posix() for r in group if r != rel),
                                 *([bare[name].as_posix()] if name in bare else [])})
                refused[rel] = (
                    f"recipe output name {name!r} (its path, because its file name is shared) "
                    f"is also the name of {', '.join(others)}; refused rather than overwrite"
                )
        else:
            names[group[0]] = name
    return names, refused


def _member_suffix(member: str) -> str:
    return member.replace(":", "_").replace("/", "_")


def convert(mod: SourceMod, emitted: dict | None = None,
            context: LoadContext | None = None,
            deferred: list | None = None) -> ConversionResult:
    """Convert the mod's recipes.

    ``emitted`` maps identifier -> (kind, path, body) for the blocks and items the
    earlier converters wrote (see :func:`emitted_definitions`). Without it a
    multi-member tag ingredient stays residue, as before #160.

    A recipe whose load conditions are false or undecidable in this conversion
    is ``conditional_recipe`` residue, and a ``forge:conditional`` wrapper
    converts the entry Java would load (see :mod:`portkit.conditions`, #183).
    ``context`` is shared with the other converters of the namespace; without
    one the recipes get their own, and the config-flag note with it.

    With a ``deferred`` list, a recipe of a station type
    (:data:`portkit.converters.stations.RECIPE_TYPES`) whose load conditions
    pass is appended to it as (source path, recipe) instead of being refused:
    the station converter writes it into its data table (#177). A recipe of a
    :data:`STATION_SHARED_TYPES` type is appended too, and still converts.
    """
    result = ConversionResult()
    for lane in ("recipes", "recipe"):
        src = mod.data / lane
        if src.is_dir():
            break
    else:
        return result

    own_context = context is None
    if context is None:
        context = LoadContext(mod, tags=TagResolver(mod))
    tag_resolver = context.tags
    item_tags: dict[str, set[str]] = {}  # emitted item id -> native tags it must carry
    multi_used: dict[str, MultiMembers] = {}  # tags a converted recipe kept or expanded
    sources = sorted(src.rglob("*.json"))
    names, refused = recipe_names([PurePosixPath(p.relative_to(src).as_posix()) for p in sources])
    reserved = set(names.values())
    owners: dict[str, str] = {}  # output path -> the source recipe that wrote it
    identifiers: dict[str, str] = {}  # recipe identifier -> the source recipe that declared it

    def taken(rel: str, outputs: list[tuple[str, str]]) -> str | None:
        """Why one of ``outputs`` ((path, identifier)) can't be written, if one can't."""
        for out_path, ident in outputs:
            holder = owners.get(out_path) or identifiers.get(ident)
            if holder is not None and holder != rel:
                return (f"output {out_path} ({ident}) was already written by {holder}; "
                        "refused rather than overwrite")
        return None

    def write(rel: str, out_path: str, ident: str, value: dict) -> None:
        owners[out_path] = rel
        identifiers[ident] = rel
        result.files[out_path] = value

    for path in sources:
        rel = result.claim(mod, path)
        key = PurePosixPath(path.relative_to(src).as_posix())
        if key in refused:
            result.unhandled.append(Unhandled(rel, "recipe", refused[key]))
            continue
        name = names[key]
        try:
            recipe = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            result.unhandled.append(Unhandled(rel, "recipe", f"invalid JSON: {exc}"))
            continue
        if not isinstance(recipe, dict):
            result.unhandled.append(Unhandled(rel, "recipe", "recipe file is not a JSON object"))
            continue

        # Java loads the recipe only when its load conditions hold (#183).
        verdict = context.gate(recipe)
        if verdict.passes is not True:
            result.unhandled.append(Unhandled(rel, "conditional_recipe", verdict.reason()))
            continue
        if recipe.get("type") in CONDITIONAL_TYPES:
            chosen, verdict = context.choose(recipe)
            if chosen is None:
                result.unhandled.append(Unhandled(rel, "conditional_recipe", verdict.reason()))
                continue
            result.notes.append(
                f"{rel}: {recipe['type']} wrapper; converted the entry Java loads with only this "
                f"mod ({verdict.why})"
            )
            recipe = chosen

        java_type = recipe.get("type")
        if deferred is not None and java_type in STATION_TYPES:
            deferred.append((rel, recipe))
            continue
        if deferred is not None and java_type in STATION_SHARED_TYPES:
            deferred.append((rel, recipe))  # and convert it below as well
        if java_type == "minecraft:smithing_transform":
            converted = _smithing(recipe, f"{mod.namespace}:{name}", rel, result, tag_resolver)
            if converted is not None:
                body_key, body = converted
                out_path, ident = f"recipes/{name}.json", f"{mod.namespace}:{name}"
                clash = taken(rel, [(out_path, ident)])
                if clash:
                    result.unhandled.append(Unhandled(rel, "recipe", clash))
                    continue
                write(rel, out_path, ident, {"format_version": "1.20.10", body_key: body})
            continue
        mapping = _SUPPORTED.get(java_type)
        if mapping is None:
            fluid = fluid_recipe_reason(java_type)
            if fluid is not None:
                result.unhandled.append(Unhandled(rel, FLUID_RECIPE, fluid))
                continue
            tool = modular_tool_reason(java_type)
            if tool is not None:
                result.unhandled.append(Unhandled(rel, MODULAR_TOOL, tool))
                continue
            machine = machine_recipe_reason(java_type)
            if machine is not None:
                result.unhandled.append(Unhandled(rel, MACHINE_RECIPE, machine))
                continue
            code = code_recipe_reason(java_type, recipe, mod.loader)
            if code is not None:
                result.unhandled.append(Unhandled(rel, CODE_RECIPE, code))
                continue
            why = _KNOWN_UNSUPPORTED.get(
                java_type, f"unsupported recipe type {java_type!r}"
            )
            result.unhandled.append(Unhandled(rel, "recipe", why))
            continue
        bedrock_type, tags = mapping

        identifier = f"{mod.namespace}:{name}"
        body: dict = {
            "description": {"identifier": identifier},
            "tags": list(tags),
        }

        # Ingredient positions as (spec, grid slots it fills). A shaped key
        # entry fills one slot per use in the pattern; everything else one.
        if java_type == "minecraft:crafting_shaped":
            pattern = recipe.get("pattern", [])
            used = "".join(row for row in pattern if isinstance(row, str))
            key_specs = list((recipe.get("key") or {}).items())
            positions = [(_ingredient(spec), used.count(symbol)) for symbol, spec in key_specs]
        elif java_type == "minecraft:crafting_shapeless":
            positions = [(_ingredient(spec), 1) for spec in recipe.get("ingredients", [])]
        else:  # stonecutting and the furnace family: one input
            positions = [(_ingredient(recipe.get("ingredient")), 1)]
        furnace = java_type in _FURNACE_TYPES

        mapped = [_item(spec, tag_resolver) for spec, _ in positions]
        failing = [i for i, m in enumerate(mapped) if m is None]
        multis = {i: _multi_tag(positions[i][0], tag_resolver, emitted) for i in failing}
        variants: list[tuple[str, list]] = [("", mapped)]  # (file suffix, ingredients)
        native: set[int] = set()  # ingredients written as this addon's own tag
        partly: list[int] = []  # native-tag candidates with members that can't carry it
        with_extras: int | None = None  # the native tag ingredient with extra recipes
        expanded: int | None = None  # the ingredient written once per member
        rest: list[int] = []  # tag ingredients only a per-member expansion could write
        if failing and all(multis.values()):
            ingredients = list(mapped)
            for i in failing:
                multi = multis[i]
                if not furnace and multi.vanilla_tag:
                    ingredients[i] = {"tag": multi.vanilla_tag}
                elif not furnace and multi.bedrock_tag:
                    # Bedrock's own tag, with this mod's members tagged into it.
                    ingredients[i] = {"tag": multi.found.tag}
                    native.add(i)
                elif not furnace and multi.taggable and not multi.extras:
                    ingredients[i] = {"tag": multi.found.tag}
                    native.add(i)
                elif not furnace and multi.taggable and len(multi.found.members) - len(multi.extras) >= 2:
                    # Worth it only when it writes fewer recipes than one per
                    # member: two or more of the mod's members share the tag.
                    partly.append(i)
                else:
                    rest.append(i)
            if (
                len(partly) == 1
                and not rest
                and positions[partly[0]][1] == 1
                and len(multis[partly[0]].extras) <= EXPANSION_CAP
            ):
                # The mod's members carry the tag; each member that can't (a
                # vanilla item, a block with its own item) gets its own recipe
                # beside the tag recipe. One slot only, as for every expansion.
                with_extras = partly[0]
                ingredients[with_extras] = {"tag": multis[with_extras].found.tag}
                native.add(with_extras)
            else:
                rest.extend(partly)
            own = ([m for m in multis[rest[0]].found.members if not m.startswith("minecraft:")]
                   if len(rest) == 1 else [])
            if not rest and with_extras is not None:
                variants = [("", ingredients)]
                for member in multis[with_extras].extras:
                    one = list(ingredients)
                    one[with_extras] = {"item": member}
                    variants.append((f"__{_member_suffix(member)}", one))
            elif not rest:
                variants = [("", ingredients)]
            elif (
                not furnace
                and len(rest) == 1
                and multis[rest[0]].found.tag in _BEDROCK_VANILLA_TAGS
                and tag_resolver.mod_additions(multis[rest[0]].found.tag) is not None
                and positions[rest[0]][1] == 1
                and len(own) <= EXPANSION_CAP
            ):
                # Bedrock's tag keeps the vanilla members; a member of this mod
                # that can't carry the tag gets its own recipe beside it.
                expanded = rest[0]
                ingredients[expanded] = {"tag": multis[expanded].found.tag}
                variants = [("", ingredients)]
                for member in own:
                    one = list(ingredients)
                    one[expanded] = {"item": member}
                    variants.append((f"__{_member_suffix(member)}", one))
            elif (
                len(rest) == 1
                and positions[rest[0]][1] == 1
                and len(multis[rest[0]].found.members) <= EXPANSION_CAP
            ):
                expanded = rest[0]
                variants = []
                for member in multis[expanded].found.members:
                    one = list(ingredients)
                    one[expanded] = {"item": member}
                    variants.append((f"__{_member_suffix(member)}", one))
            else:
                native = set()
        if any(m is None for _, ms in variants for m in ms):
            # Not expressible (or not fully known): the reason is the one the
            # first failing ingredient always had, plus which members this
            # conversion didn't emit when that is what blocks it.
            # A tag this conversion could have written isn't what blocks it.
            bad_i = next((i for i in failing if multis[i] is None), (rest or failing)[0])
            bad = positions[bad_i][0]
            reason = _tag_reason(bad, tag_resolver)
            if multis.get(bad_i) is not None and multis[bad_i].listed:
                reason = _list_reason(multis[bad_i], positions[bad_i][1], len(rest))
            missing = _not_emitted(bad, tag_resolver, emitted)
            if missing:
                reason += f"; not converted: {', '.join(missing)}"
            result.unhandled.append(Unhandled(rel, "recipe", reason))
            continue

        if furnace:
            first = variants[0][1][0]
            if "item" not in first:
                # Bedrock's furnace input is one item id; a tag has no place there.
                result.unhandled.append(Unhandled(
                    rel, "recipe",
                    f"furnace input is tag {first.get('tag')!r}; Bedrock's furnace "
                    "recipe takes a single item id, not a tag",
                ))
                continue

        out = _result_item(recipe.get("result"), tag_resolver)
        if out is None:
            result.unhandled.append(Unhandled(rel, "recipe", "unreadable result item"))
            continue
        count = 1
        if isinstance(recipe.get("result"), dict):
            count = recipe["result"].get("count", 1)
        elif "count" in recipe:
            # stonecutting keeps the count beside the result, not inside it
            count = recipe["count"]
        if bedrock_type == "minecraft:recipe_furnace":
            # Bedrock names the product "output", a bare item id with no count
            # (learn.microsoft.com recipe_furnace reference). See #90.
            if "item" not in out:
                result.unhandled.append(Unhandled(rel, "recipe", "furnace result is a tag, not an item"))
                continue
            body["output"] = out["item"]
            if count != 1:
                result.notes.append(
                    f"{rel}: furnace result count {count} dropped; Bedrock's furnace "
                    "recipe output is a single item id and always yields one"
                )
        else:
            body["result"] = {**out, "count": count} if count != 1 else out

        outputs = [(f"recipes/{name}{suffix}.json", f"{identifier}{suffix}") for suffix, _ in variants]
        if any(suffix for suffix, _ in variants) and any(
            path_ in result.files or (suffix and f"{name}{suffix}" in reserved)
            for (path_, _), (suffix, _) in zip(outputs, variants)
        ):
            # A per-member file name another recipe already took or will take:
            # refuse rather than overwrite either one.
            result.unhandled.append(Unhandled(rel, "recipe", _tag_reason(positions[failing[0]][0], tag_resolver)))
            continue
        clash = taken(rel, outputs)
        if clash:
            # Not reached on the corpus (names are unique by construction); the
            # guard that keeps a future change from overwriting a recipe (#163).
            result.unhandled.append(Unhandled(rel, "recipe", clash))
            continue

        for suffix, ingredients in variants:
            variant = copy.deepcopy(body)
            variant["description"]["identifier"] = f"{identifier}{suffix}"
            if java_type == "minecraft:crafting_shaped":
                variant["pattern"] = recipe.get("pattern", [])
                variant["key"] = {symbol: ing for (symbol, _), ing in zip(key_specs, ingredients)}
                # keep the field order the single-recipe form always had
                variant["result"] = variant.pop("result")
            elif furnace:
                variant["input"] = ingredients[0]["item"]
                variant["output"] = variant.pop("output")
            else:
                variant["ingredients"] = ingredients
                variant["result"] = variant.pop("result")
            write(rel, f"recipes/{name}{suffix}.json", f"{identifier}{suffix}", {
                "format_version": "1.20.10",
                bedrock_type: variant,
            })
        for i, multi in multis.items():
            if multi is None or multi.listed:
                continue
            multi_used[multi.found.tag] = multi.found
            if i in native:
                for member in multi.found.members:
                    if not member.startswith("minecraft:") and member not in (multi.extras or []):
                        item_tags.setdefault(member, set()).add(multi.found.tag)
                if multi.found.tag in _BEDROCK_VANILLA_TAGS:
                    own = [m for m in multi.found.members if not m.startswith("minecraft:")]
                    result.notes.append(
                        f"{rel}: tag {multi.found.tag!r} also holds {', '.join(own)} from this mod, "
                        "so they carry Bedrock's tag of that name and the recipe takes it"
                    )
            elif multi.vanilla_tag and i != expanded:
                result.notes.append(
                    f"{rel}: tag {multi.found.tag!r} has the same members as Bedrock's "
                    f"{multi.vanilla_tag!r}, so the recipe takes that tag"
                )
        if with_extras is not None and with_extras in native:
            multi = multis[with_extras]
            result.notes.append(
                f"{rel}: tag {multi.found.tag!r} is carried by this mod's members, and "
                f"{', '.join(multi.extras)} (which can't carry it) got their own recipe "
                f"({name}__<member>) beside the one taking the tag"
            )
        if expanded is not None and variants[0][0] == "":
            member_tag = multis[expanded].found.tag
            result.notes.append(
                f"{rel}: tag {member_tag!r} also holds {len(variants) - 1} of this mod's members "
                f"that can't carry Bedrock's tag of that name, so each got its own recipe "
                f"({name}__<member>) beside the one taking the tag"
            )
        elif expanded is not None and multis[expanded].listed:
            result.notes.append(
                f"{rel}: ingredient lists {len(variants)} items, which Bedrock can't group "
                f"without a tag the mod never declared, so the recipe was written once per item "
                f"({name}__<item>)"
            )
        elif expanded is not None:
            member_tag = multis[expanded].found.tag
            result.notes.append(
                f"{rel}: tag {member_tag!r} has {len(variants)} members, which Bedrock "
                f"can't group under one tag here, so the recipe was written once per member "
                f"({name}__<member>)"
            )

    for member, member_tags in sorted(item_tags.items()):
        kind, item_path, source_body = emitted[member]
        if kind == "block":
            item_path, item = _block_item(member, item_path)
            item["minecraft:item"]["components"]["minecraft:tags"] = {"tags": sorted(member_tags)}
            result.files[item_path] = item
            continue
        item = copy.deepcopy(source_body)
        components = item["minecraft:item"].setdefault("components", {})
        existing = components.get("minecraft:tags") or {}
        merged_tags = sorted(set(existing.get("tags") or []) | member_tags)
        components["minecraft:tags"] = {"tags": merged_tags}
        item["format_version"] = _max_format(item.get("format_version"), _ITEM_TAGS_FORMAT)
        result.files[item_path] = item
    for tag, found in sorted(multi_used.items()):
        for source in found.sources:
            result.consumed.add(source)
        if found.dropped:
            result.notes.append(
                f"tag {tag!r}: dropped {', '.join(found.dropped)}, which this addon cannot contain"
            )
    for tag, found in sorted(tag_resolver.resolved().items()):
        for source in found.sources:
            result.consumed.add(source)  # the tag files were read, so they are owned
        if found.note:
            result.notes.append(found.note)
    note = context.note() if own_context else None
    if note:
        result.notes.append(note)
    return result
