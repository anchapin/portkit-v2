"""Mythic Metals (#245): why its recipe types stay residue.

Mythic Metals 0.24.6 Tidesinger smithing, Midas folding and upgrade recipes
(``code_recipe``, #180): their station or result is the mod's Java code. Moved
unchanged from ``converters/recipes.py`` (#245 migration step 4); sources
cited beside each.
"""
from __future__ import annotations

from ...converters.recipes import CODE_RECIPE
from .. import Adapter


CODE_RECIPES = {
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
}


ADAPTER = Adapter(
    name="mythicmetals",
    namespaces=frozenset({"mythicmetals"}),
    recipe_reasons={
        **{t: (CODE_RECIPE, r) for t, r in CODE_RECIPES.items()},
    },
)
