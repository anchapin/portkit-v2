"""Tinkers' Construct (#245): why its recipe types stay residue.

Tinkers' Construct 3.12.1.231 recipe types that have no Bedrock form: fluid
recipes (melting, casting, alloying, fuels; ``fluid_recipe``, #174), modular
tool recipes (tool building, modifiers, part builder, severing;
``modular_tool``, #175) and molding (``code_recipe``, #180). Moved unchanged
from ``converters/recipes.py`` (#245 migration step 4); each reason is read
from Tinkers' own code at the corpus pin, cited beside it. Its load-condition
types are Mantle's (:mod:`portkit.adapters.mantle`).
"""
from __future__ import annotations

from ...converters.recipes import (
    CODE_RECIPE, FLUID_RECIPE, MODULAR_TOOL, NO_BEDROCK_FLUID, NO_PER_STACK_TOOL,
)
from .. import Adapter


def _tinkers(what: str) -> str:
    return f"a Tinkers' Construct {what}; {NO_BEDROCK_FLUID}"


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


def _tc_tool(what: str) -> str:
    return f"a Tinkers' Construct {what}; {NO_PER_STACK_TOOL}"


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
# every type below is registered in TinkerSmeltery L408-444
# (RECIPE_SERIALIZERS.register), the smeltery module. Field names from each
# recipe's LOADER: MeltingRecipe L32-38 (ingredient, result, temperature, time,
# byproducts), ItemCastingRecipe L26-31 (fluid, result, cooling_time),
# AlloyRecipe L29-33 (inputs list of >= 2, result, temperature), MeltingFuel
# L27-32 (fluid, duration, temperature, rate), EntityMeltingRecipe L29-33
# (entity, result, damage), MaterialFluidRecipe L30-36 (fluid, temperature).
FLUID_RECIPES = {
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
}


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
MODULAR_TOOL_RECIPES = {
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
}


CODE_RECIPES = {
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
}


ADAPTER = Adapter(
    name="tconstruct",
    namespaces=frozenset({"tconstruct"}),
    recipe_reasons={
        **{t: (FLUID_RECIPE, r) for t, r in FLUID_RECIPES.items()},
        **{t: (MODULAR_TOOL, r) for t, r in MODULAR_TOOL_RECIPES.items()},
        **{t: (CODE_RECIPE, r) for t, r in CODE_RECIPES.items()},
    },
)
