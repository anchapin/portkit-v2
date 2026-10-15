"""BetterEnd (#245): why its recipe types stay residue.

BetterEnd 21.800.2 infusion rituals (``code_recipe``, #180): their station or
result is the mod's Java code. Moved unchanged from ``converters/recipes.py``
(#245 migration step 4); sources cited beside each.
"""
from __future__ import annotations

from ...converters.recipes import CODE_RECIPE
from .. import Adapter


CODE_RECIPES = {
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
}


ADAPTER = Adapter(
    name="betterend",
    namespaces=frozenset({"betterend"}),
    recipe_reasons={
        **{t: (CODE_RECIPE, r) for t, r in CODE_RECIPES.items()},
    },
)
