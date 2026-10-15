"""Mekanism's recipe types that stay residue (#172, #245).

The 26 Mekanism 10.7.19.85 machine recipe types (``machine_recipe``) and
data-keeping ``mek_data`` crafting (``code_recipe``). Moved unchanged from
``converters/recipes.py`` (#245 migration step 4); sources cited beside each.
"""
from __future__ import annotations

from ...converters.recipes import CODE_RECIPE, MACHINE_RECIPE, NO_BEDROCK_MACHINE, NO_BEDROCK_MB


# What Bedrock lacks for Mekanism's chemicals, said in the reasons that use one.
_NO_BEDROCK_CHEMICAL = (
    "Mekanism's chemicals (gases, infuse types, pigments, slurries) have no Bedrock form"
)


def _mek(what: str, *lacks: str) -> str:
    return "; ".join((f"a Mekanism {what}", *lacks, NO_BEDROCK_MACHINE))


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
MACHINE_RECIPES = {
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
        _NO_BEDROCK_CHEMICAL, NO_BEDROCK_MB,
    ),
    "mekanism:separating": _mek(
        "Electrolytic Separator recipe: the fluid `input` splits into `left_chemical_output` and "
        "`right_chemical_output` in mekanism:electrolytic_separator, using energy (ElectrolysisRecipe, "
        "TileEntityElectrolyticSeparator)",
        _NO_BEDROCK_CHEMICAL, NO_BEDROCK_MB,
    ),
    "mekanism:rotary": _mek(
        "Rotary Condensentrator recipe: `chemical_input` condenses into `fluid_output`, or "
        "`fluid_input` decondenses into `chemical_output`, by the mode set on "
        "mekanism:rotary_condensentrator, using energy (RotaryRecipe, "
        "TileEntityRotaryCondensentrator)",
        _NO_BEDROCK_CHEMICAL, NO_BEDROCK_MB,
    ),
    "mekanism:evaporating": _mek(
        "Thermal Evaporation recipe: the fluid `input` evaporates into the fluid `output` in the "
        "thermal evaporation tower (a multiblock run from mekanism:thermal_evaporation_controller) "
        "at a rate set by the tower's heat (FluidToFluidRecipe, EvaporationMultiblockData)",
        NO_BEDROCK_MB,
    ),
    "mekanism:reaction": _mek(
        "Pressurized Reaction Chamber recipe: `item_input`, `fluid_input` and `chemical_input` react "
        "over `duration` ticks, using extra `energy_required`, into `item_output` and "
        "`chemical_output` in mekanism:pressurized_reaction_chamber (PressurizedReactionRecipe, "
        "TileEntityPressurizedReactionChamber)",
        _NO_BEDROCK_CHEMICAL, NO_BEDROCK_MB,
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
}


CODE_RECIPES = {
    # Mekanism 10.7.19.85 (see MACHINE_RECIPES): MekanismRecipeSerializersInternal
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
}


RECIPE_REASONS = {
    **{t: (MACHINE_RECIPE, r) for t, r in MACHINE_RECIPES.items()},
    **{t: (CODE_RECIPE, r) for t, r in CODE_RECIPES.items()},
}
