"""Create (#245): why its recipe types stay residue; its smithing bases' durability (#268).

Create mc1.20.1-6.0.8 rotation-powered processing recipes (``machine_recipe``,
#173), spout filling and drain emptying (``fluid_recipe``, #174), and the
hand-used item application and sandpaper polishing (``code_recipe``, #180).
Moved unchanged from ``converters/recipes.py`` (#245 migration step 4);
sources cited beside each.
"""
from __future__ import annotations

from ...converters.recipes import CODE_RECIPE, FLUID_RECIPE, MACHINE_RECIPE, NO_BEDROCK_FLUID
from .. import Adapter
from .armor import item_armor
from .durability import item_durability


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


# Create mc1.20.1-6.0.8 (Creators-of-Create/Create @1a1a9a28): AllRecipeTypes
# L61-62 FILLING/EMPTYING; FillingRecipe#getRequiredFluid (a FluidIngredient
# with an amount), run by FillingBySpout (the Spout); EmptyingRecipe
# #getResultingFluid, run by GenericItemEmptying (the Item Drain,
# ItemDrainBlockEntity L200-234).
FLUID_RECIPES = {
    "create:filling": (
        f"a Create filling recipe: the Spout pours the fluid ingredient's amount (mB) onto the item "
        f"below it to make the result (FillingRecipe#getRequiredFluid, FillingBySpout); {NO_BEDROCK_FLUID}"
    ),
    "create:emptying": (
        f"a Create emptying recipe: the Item Drain empties the item into its fluid result (mB) and "
        f"keeps the emptied item (EmptyingRecipe#getResultingFluid, GenericItemEmptying); "
        f"{NO_BEDROCK_FLUID}"
    ),
}


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
# code_recipe (used by hand, see CODE_RECIPES); TOOLBOX_DYEING and
# ITEM_COPYING are data-free special recipes (code_recipe, #180).
MACHINE_RECIPES = {
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


CODE_RECIPES = {
    # Create mc1.20.1-6.0.8 (@1a1a9a28, see MACHINE_RECIPES):
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
}


ADAPTER = Adapter(
    name="create",
    namespaces=frozenset({"create"}),
    recipe_reasons={
        **{t: (FLUID_RECIPE, r) for t, r in FLUID_RECIPES.items()},
        **{t: (MACHINE_RECIPE, r) for t, r in MACHINE_RECIPES.items()},
        **{t: (CODE_RECIPE, r) for t, r in CODE_RECIPES.items()},
    },
    # The copper diving gear's durability, the netherite upgrade's base (#268).
    item_durability=item_durability,
    item_armor=item_armor,
)
