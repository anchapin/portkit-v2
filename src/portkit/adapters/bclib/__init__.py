"""BCLib (#245): why its recipe types stay residue.

BCLib 21.800.2 anvil and alloying recipes (``code_recipe``, #180): their
station or result is the mod's Java code. BCLib is the library mod BetterEnd
builds on (BetterEnd's recipes use these BCLib types), so this is a library
adapter. Moved unchanged from ``converters/recipes.py`` (#245 migration
step 4); sources cited beside each.
"""
from __future__ import annotations

from ...converters.recipes import CODE_RECIPE
from .. import Adapter


CODE_RECIPES = {
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
}


ADAPTER = Adapter(
    name="bclib",
    namespaces=frozenset({"bclib"}),
    library=True,
    recipe_reasons={
        **{t: (CODE_RECIPE, r) for t, r in CODE_RECIPES.items()},
    },
)
