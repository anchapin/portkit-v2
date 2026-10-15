"""Silent Gear (#245): why its recipe types stay residue.

Silent Gear 2.6.36 gear, part and material recipes (``modular_tool``, #175)
and plain salvaging (``code_recipe``, #180). Moved unchanged from
``converters/recipes.py`` (#245 migration step 4); sources cited beside each.
"""
from __future__ import annotations

from ...converters.recipes import CODE_RECIPE, MODULAR_TOOL, NO_PER_STACK_TOOL
from .. import Adapter


def _sg_gear(what: str) -> str:
    return f"a Silent Gear {what}; {NO_PER_STACK_TOOL}"


# Silent Gear 2.6.36 (SilentChaos512/Silent-Gear 1.16.x @9188137b, committed
# 2021-12-29, the jar's Implementation-Timestamp day): ModRecipes L43-80,
# names from Const L28-46.
MODULAR_TOOL_RECIPES = {
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


CODE_RECIPES = {
    # Silent Gear 2.6.36 (Silent-Gear 1.16.x @9188137b, see MODULAR_TOOL_RECIPES):
    # SalvagerTileEntity L89-153: BASE_WORK_TIME 10 s, each result item lost
    # with a chance between salvagerMinLossRate (0.0) and salvagerMaxLossRate
    # (0.5) by the input's damage (Config L313-320).
    "silentgear:salvaging": (
        "a Silent Gear salvaging recipe: the Salvager block takes the item apart over a work time, "
        "and each result item is lost with a chance that grows with the input's damage "
        "(SalvagerTileEntity#tick and #getLossRate, partLossRate config 0.0 to 0.5); a fixed-result "
        "Bedrock recipe would drop the station, the time and the loss"
    ),
}


ADAPTER = Adapter(
    name="silentgear",
    namespaces=frozenset({"silentgear"}),
    recipe_reasons={
        **{t: (MODULAR_TOOL, r) for t, r in MODULAR_TOOL_RECIPES.items()},
        **{t: (CODE_RECIPE, r) for t, r in CODE_RECIPES.items()},
    },
)
