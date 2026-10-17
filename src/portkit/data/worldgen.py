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
    # Java 1.17+ blocks, in blocks.json as "calcite" and "smooth_basalt"
    # (Mythic Metals' starrite and orichalcum veins replace them, #281).
    "minecraft:calcite", "minecraft:smooth_basalt",
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

# Loader convention biome tags whose pinned definition is exactly one vanilla
# dimension tag, keyed by the loader tag set (portkit.data.tags.select).
#
# * ``fabric-1.21.1``: fabric-convention-tags-v2 2.12.0+c3656daa19 (Fabric API
#   0.116.17+1.21.1, Apache-2.0; the jar portkit.data.tags pins),
#   ``data/c/tags/worldgen/biome/is_overworld.json`` is
#   ``{"values": [{"id": "#minecraft:is_overworld", "required": false},
#   {"id": "#c:in_the_overworld", "required": false}]}``; ``is_nether.json``
#   the same with ``#minecraft:is_nether`` and ``#c:in_nether``;
#   ``is_end.json`` with ``#minecraft:is_end`` and ``#c:in_the_end``. The
#   legacy ``c:in_*`` tags are optional and defined nowhere in that Fabric API
#   (its pom lists fabric-convention-tags-v2 only, and the v2 jar has no
#   ``in_*`` biome tag), so each tag is exactly its vanilla tag.
#
# Other convention biome tags (``c:is_aquatic``, ``c:is_mountain``...) are
# biome lists, which have no Bedrock map here (pick 3), so they are not rows.
CONVENTION_BIOME_TAGS: dict[str, dict[str, str]] = {
    "fabric-1.21.1": {
        "c:is_overworld": "minecraft:is_overworld",
        "c:is_nether": "minecraft:is_nether",
        "c:is_end": "minecraft:is_end",
    },
}


def convention_biome_tags(loader: str | None, minecraft: str | None) -> dict[str, str]:
    from . import tags as tag_data
    for tag_set in tag_data.select(loader, minecraft):
        if tag_set.family != "vanilla":
            return dict(CONVENTION_BIOME_TAGS.get(tag_set.id, {}))
    return {}


# -- geodes and patches (#281, third slice) ---------------------------------------

# Java generation steps a geode's biome modifier may name -> Bedrock
# placement_pass. Java runs the steps in GenerationStep.Decoration order
# (raw_generation, lakes, local_modifications, underground_structures,
# surface_structures, strongholds, underground_ores, ...: the enum's
# declaration order in Mojang's 1.20.1 client mappings,
# net.minecraft.world.level.levelgen.GenerationStep$Decoration). Bedrock: "Earlier passes in the list are
# guaranteed to occur before later passes" (bedrock-samples
# documentation/Features.html, Feature Rule Conditions, placement_pass), and
# its list puts before_underground_pass ahead of underground_pass, where the
# ores go (STEPS). So local_modifications, Java's step before the ores, is
# before_underground_pass: the order kept, not an exact engine match (pick 3).
GEODE_STEPS: dict[str, str] = {
    "local_modifications": "before_underground_pass",
    **STEPS,
}

# Vanilla blocks a geode layer or inner placement may name, kept to ids that
# are the same on both editions: bedrock-samples resource_pack/blocks.json
# lists air, calcite, clay, smooth_basalt, amethyst_block, budding_amethyst,
# end_stone, obsidian and netherrack (and the SAME_ID_BLOCKS above).
GEODE_VANILLA_BLOCKS = SAME_ID_BLOCKS | frozenset({
    "minecraft:air", "minecraft:amethyst_block", "minecraft:budding_amethyst", "minecraft:obsidian",
})

# Bedrock minecraft:geode_feature integer ranges (bedrock-samples
# documentation/Features.html and MicrosoftDocs/minecraft-creator
# Features/minecraftGeode_feature.md): min_outer_wall_distance <1-10>,
# max_outer_wall_distance <1-20>, min_distribution_points <1-10>,
# max_distribution_points <1-20>, min_point_offset and max_point_offset
# <0-10>, crack_point_offset <0-10>; base_crack_size 0..5 and the chances 0..1.
GEODE_RANGES: dict[str, tuple[float, float]] = {
    "min_outer_wall_distance": (1, 10), "max_outer_wall_distance": (1, 20),
    "min_distribution_points": (1, 10), "max_distribution_points": (1, 20),
    "min_point_offset": (0, 10), "max_point_offset": (0, 10),
    "crack_point_offset": (0, 10), "base_crack_size": (0, 5),
    "generate_crack_chance": (0, 1), "use_potential_placements_chance": (0, 1),
    "use_alternate_layer0_chance": (0, 1),
}

# Java geode fields with no Bedrock geode_feature field (pick 1). Their Java
# defaults, minecraft.wiki "Amethyst Geode" (oldid 3811952), Config: layers
# filling 1.7, inner_layer 2.2, middle_layer 3.2, outer_layer 4.2;
# min_gen_offset -16, max_gen_offset 16 ("Chebyshev distance between the
# block and the center"); cannot_replace #minecraft:features_cannot_replace
# and invalid_blocks #minecraft:geode_invalid_blocks in vanilla geodes.
JAVA_GEODE_DEFAULTS = {
    "layers": {"filling": 1.7, "inner_layer": 2.2, "middle_layer": 3.2, "outer_layer": 4.2},
    "min_gen_offset": -16, "max_gen_offset": 16,
    "cannot_replace": "#minecraft:features_cannot_replace",
    "invalid_blocks": "#minecraft:geode_invalid_blocks",
}

# Java configured feature types of the plant patch family (minecraft.wiki
# "Configured feature": random_patch, flower and no_bonemeal_flower take a
# RandomPatchConfiguration (tries, xz_spread, y_spread, feature);
# simple_block places one block state; random_selector and
# simple_random_selector pick one of their placed features).
PATCH_TYPES = frozenset({"minecraft:random_patch", "minecraft:flower", "minecraft:no_bonemeal_flower",
                         "minecraft:simple_block"})
SELECTOR_TYPES = frozenset({"minecraft:random_selector", "minecraft:simple_random_selector"})
