"""Supplementaries (#245): why its recipe types stay residue.

Supplementaries 1.20-3.1.43 suspicious-block crafting (``code_recipe``, #180):
their station or result is the mod's Java code. Moved unchanged from
``converters/recipes.py`` (#245 migration step 4); sources cited beside each.
"""
from __future__ import annotations

from ...converters.recipes import CODE_RECIPE
from .. import Adapter


CODE_RECIPES = {
    # Supplementaries 1.20-3.1.43 SusRecipe#assemble (a CustomRecipe): the other
    # grid stack goes into the result's BlockEntityTag "item".
    "supplementaries:sus_crafting": (
        "a Supplementaries suspicious-block recipe: the other item in the grid is stored in the "
        "result's block data as its hidden loot (SusRecipe#assemble, BlockEntityTag.item); a "
        "fixed-result Bedrock recipe would drop the hidden item"
    ),
}


ADAPTER = Adapter(
    name="supplementaries",
    namespaces=frozenset({"supplementaries"}),
    recipe_reasons={
        **{t: (CODE_RECIPE, r) for t, r in CODE_RECIPES.items()},
    },
)
