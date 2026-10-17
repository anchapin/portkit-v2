"""Reference tables for converting Java ore features to Bedrock (#281).

Every row is cited; nothing here is a guess (#87). Rows the picks on PR #281's
design PR decide are marked ``(pick N)``; until Alex decides, they are the
recommended defaults and ``docs/decisions.md`` carries the entry as pending.

Sources (short excerpts only, the Mojang texts are under the Minecraft EULA):

* Java vanilla data: misode/mcmeta ``1.20.1-data`` and ``1.21.1-data`` (the
  pinned Minecraft versions the gauntlet reads), files named per row.
* Bedrock biomes: Mojang/bedrock-samples ``behavior_pack/biomes/*.biome.json``,
  each biome's ``minecraft:tags``.
* Bedrock features and feature rules: Mojang/bedrock-samples
  ``documentation/Features.html`` and MicrosoftDocs/minecraft-creator
  ``Reference/Content/FeaturesReference/Examples/FeaturesIntroduction.md`` and
  ``Features/minecraftOre_feature.md``.
"""
from __future__ import annotations

# Java biome tag -> (Bedrock biome filter, dimension).
#
# * ``#minecraft:is_nether`` (mcmeta tags/worldgen/biome/is_nether.json: the
#   five nether biomes nether_wastes, soul_sand_valley, crimson_forest,
#   warped_forest, basalt_deltas) -> biome tag ``nether``: bedrock-samples
#   hell, soulsand_valley, crimson_forest, warped_forest and basalt_deltas are
#   the biomes carrying "nether", the same five. Exact.
# * ``#minecraft:is_overworld`` (every overworld biome, mushroom_fields to
#   deep_dark; no nether or end biome) -> any biome
#   tagged ``overworld`` or ``overworld_generation``: every bedrock-samples
#   biome that is neither nether nor the_end carries one of the two (the
#   mutated variants carry "overworld_generation" instead of "overworld").
#   Bedrock's legacy hills/mutated biomes, which Java folded into others,
#   are included (pick 3).
# * ``#minecraft:is_end`` (the_end, end_highlands, end_midlands,
#   small_end_islands, end_barrens) -> biome tag ``the_end``: bedrock-samples
#   has one end biome, the_end, so the whole End (pick 3).
BIOME_TAGS: dict[str, tuple[list[dict], str]] = {
    "minecraft:is_nether": (
        [{"test": "has_biome_tag", "operator": "==", "value": "nether"}], "nether"),
    "minecraft:is_overworld": (
        [{"any_of": [
            {"test": "has_biome_tag", "operator": "==", "value": "overworld"},
            {"test": "has_biome_tag", "operator": "==", "value": "overworld_generation"},
        ]}], "overworld"),
    "minecraft:is_end": (
        [{"test": "has_biome_tag", "operator": "==", "value": "the_end"}], "the_end"),
}

# Java block tags an ore target may name -> the vanilla blocks in them. Same
# members in 1.20.1 (tags/blocks/) and 1.21.1 (tags/block/), mcmeta. Each id
# is also a Bedrock block id (bedrock-samples resource_pack/blocks.json has
# stone, granite, diorite, andesite, deepslate, tuff, netherrack, basalt and
# blackstone).
BLOCK_TAGS: dict[str, list[str]] = {
    "minecraft:stone_ore_replaceables": ["minecraft:stone", "minecraft:granite", "minecraft:diorite",
                                         "minecraft:andesite"],
    "minecraft:deepslate_ore_replaceables": ["minecraft:deepslate", "minecraft:tuff"],
    "minecraft:base_stone_nether": ["minecraft:netherrack", "minecraft:basalt", "minecraft:blackstone"],
    "minecraft:base_stone_overworld": ["minecraft:stone", "minecraft:granite", "minecraft:diorite",
                                       "minecraft:andesite", "minecraft:tuff", "minecraft:deepslate"],
}

# Vanilla blocks a ``block_match`` target may name, kept to ids that are the
# same on both editions (bedrock-samples resource_pack/blocks.json).
SAME_ID_BLOCKS = frozenset({
    "minecraft:stone", "minecraft:granite", "minecraft:diorite", "minecraft:andesite",
    "minecraft:deepslate", "minecraft:tuff", "minecraft:netherrack", "minecraft:basalt",
    "minecraft:blackstone", "minecraft:end_stone", "minecraft:gravel", "minecraft:sand",
    "minecraft:dirt", "minecraft:clay", "minecraft:soul_sand", "minecraft:soul_soil",
})

# Java generation step (GenerationStep.Decoration) -> Bedrock placement_pass.
# Bedrock's passes, in order: first_pass, before_underground_pass,
# underground_pass, after_underground_pass, before_surface_pass, surface_pass,
# ... (FeaturesIntroduction.md "placement_pass"). Java places ores in
# underground_ores and underground_decoration, both before the surface steps;
# Bedrock's ore pass is underground_pass. Only the two ore steps are read here.
STEPS: dict[str, str] = {
    "underground_ores": "underground_pass",
    "underground_decoration": "underground_pass",
}

# Lowest and highest block y per dimension.
# Java: mcmeta dimension_type/<dim>.json min_y and min_y + height - 1, the same
# in 1.20.1 and 1.21.1 (overworld -64/384, the_nether 0/256, the_end 0/256).
# Bedrock: minecraft.wiki "Altitude" (oldid 3810408): the Overworld builds from
# -64 to 319; the Nether's highest placeable block is at 127 in Bedrock
# (Java 255); the End from 0 to 255 on both.
JAVA_Y = {"overworld": (-64, 319), "nether": (0, 255), "the_end": (0, 255)}
BEDROCK_Y = {"overworld": (-64, 319), "nether": (0, 127), "the_end": (0, 255)}
