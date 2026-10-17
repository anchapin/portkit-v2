"""Java vanilla texture names Bedrock files under another name, checked pixel by pixel (#296).

Java's ``block/oak_planks`` has no ``textures/blocks/oak_planks`` in Bedrock's
vanilla pack, but Bedrock's terrain atlas has a short name ``oak_planks`` showing
``textures/blocks/planks_oak``. Pick 2 of #220 left such names residue, because
a short name that shares the Java name doesn't promise the same picture: some
show a different texture (``piston_top`` is ``piston_inner``). This table is
the approved way through (Alex, 2026-10-17; docs/decisions.md): a pair maps
only when a pixel check showed the Bedrock file looks exactly like the Java
texture.

Where the names come from: every pair is a short name and its one file in
Mojang/bedrock-samples ``resource_pack/textures/terrain_texture.json`` and
``item_texture.json`` at the commit pinned in :data:`portkit.data.COMMIT`
(:data:`BEDROCK_COMMIT`, the same atlases :mod:`portkit.data.vanilla_textures`
indexes). Nothing is hand-written: a Java name gets a pair only when Bedrock's
own atlas files a short name of exactly that name. Java names with no Bedrock
short name of the same name (``bricks``, ``sandstone``, ``prismarine``) have no
cited pairing and stay residue.

The method (``scripts/check_vanilla_texture_aliases.py``, needs the jar and
Pillow): the candidates are every atlas short name showing exactly one file
where Bedrock has no file of that name (top level or one folder down) and the
Java client jar has the texture; both images are decoded to RGBA; a pair is
kept when width, height and every pixel's alpha match and every visible pixel
(alpha > 0) has the same colour. Colours under fully transparent pixels are
ignored. Java side: Minecraft 1.21.11 client jar, sha1 :data:`JAVA_CLIENT_SHA1`
(piston-meta.mojang.com launcher manifest). Nothing from the jar is kept here,
only the names. Result: 203 pairs look the same (:data:`ALIASES`), 28 differ
(:data:`DIFFERS`: the stained glass pane tops, ``piston_top``, the coral blocks,
``short_grass``, ``spruce_planks`` by one pixel, lilac, two glazed terracottas,
the command block mipmaps, ``conduit``) and stay residue.

Both tables are tied to the pinned atlases: bump :data:`portkit.data.COMMIT`
and the check must be re-run (a test holds them together). The converter still
applies its usual rules to the file a pair names (a plain short name showing
just that file is named, else a pack entry; vanilla-animated files stay residue).
"""
from __future__ import annotations

BEDROCK_COMMIT = "46ba6ea985fb5a92d79a9419198f10dda14c199d"
JAVA_VERSION = "1.21.11"
JAVA_CLIENT_SHA1 = "ba2df812c2d12e0219c489c4cd9a5e1f0760f5bd"

# atlas ("terrain" / "item") -> Java texture name -> the Bedrock file that looks the same
ALIASES: dict[str, dict[str, str]] = {
    "item": {
        "acacia_door": "textures/items/door_acacia",
        "birch_door": "textures/items/door_birch",
        "cooked_salmon": "textures/items/fish_salmon_cooked",
        "dark_oak_door": "textures/items/door_dark_oak",
        "dragon_breath": "textures/items/dragons_breath",
        "heart_of_the_sea": "textures/items/heartofthesea_closed",
        "iron_door": "textures/items/door_iron",
        "jungle_door": "textures/items/door_jungle",
        "nautilus_shell": "textures/items/nautilus",
        "pufferfish": "textures/items/fish_pufferfish_raw",
        "rabbit": "textures/items/rabbit_raw",
        "salmon": "textures/items/fish_salmon_raw",
        "spruce_door": "textures/items/door_spruce",
    },
    "terrain": {
        "acacia_log_top": "textures/blocks/log_acacia_top",
        "acacia_planks": "textures/blocks/planks_acacia",
        "acacia_sapling": "textures/blocks/sapling_acacia",
        "allium": "textures/blocks/flower_allium",
        "andesite": "textures/blocks/stone_andesite",
        "azure_bluet": "textures/blocks/flower_houstonia",
        "birch_log_top": "textures/blocks/log_birch_top",
        "birch_planks": "textures/blocks/planks_birch",
        "birch_sapling": "textures/blocks/sapling_birch",
        "black_concrete": "textures/blocks/concrete_black",
        "black_concrete_powder": "textures/blocks/concrete_powder_black",
        "black_glazed_terracotta": "textures/blocks/glazed_terracotta_black",
        "black_shulker_box": "textures/blocks/shulker_top_black",
        "black_stained_glass": "textures/blocks/glass_black",
        "black_terracotta": "textures/blocks/hardened_clay_stained_black",
        "blue_concrete": "textures/blocks/concrete_blue",
        "blue_concrete_powder": "textures/blocks/concrete_powder_blue",
        "blue_glazed_terracotta": "textures/blocks/glazed_terracotta_blue",
        "blue_orchid": "textures/blocks/flower_blue_orchid",
        "blue_shulker_box": "textures/blocks/shulker_top_blue",
        "blue_stained_glass": "textures/blocks/glass_blue",
        "blue_terracotta": "textures/blocks/hardened_clay_stained_blue",
        "brain_coral": "textures/blocks/coral_plant_pink",
        "brain_coral_block": "textures/blocks/coral_pink",
        "brain_coral_fan": "textures/blocks/coral_fan_pink",
        "brown_concrete": "textures/blocks/concrete_brown",
        "brown_concrete_powder": "textures/blocks/concrete_powder_brown",
        "brown_glazed_terracotta": "textures/blocks/glazed_terracotta_brown",
        "brown_shulker_box": "textures/blocks/shulker_top_brown",
        "brown_stained_glass": "textures/blocks/glass_brown",
        "brown_terracotta": "textures/blocks/hardened_clay_stained_brown",
        "bubble_coral": "textures/blocks/coral_plant_purple",
        "bubble_coral_fan": "textures/blocks/coral_fan_purple",
        "campfire_fire": "textures/blocks/campfire",
        "chipped_anvil_top": "textures/blocks/anvil_top_damaged_1",
        "chiseled_quartz_block_top": "textures/blocks/quartz_block_chiseled_top",
        "chiseled_red_sandstone": "textures/blocks/red_sandstone_carved",
        "chiseled_sandstone": "textures/blocks/sandstone_carved",
        "chiseled_stone_bricks": "textures/blocks/stonebrick_carved",
        "closed_eyeblossom": "textures/blocks/eyeblossom_dormant",
        "cornflower": "textures/blocks/flower_cornflower",
        "cracked_stone_bricks": "textures/blocks/stonebrick_cracked",
        "cut_red_sandstone": "textures/blocks/red_sandstone_smooth",
        "cut_sandstone": "textures/blocks/sandstone_smooth",
        "cyan_concrete": "textures/blocks/concrete_cyan",
        "cyan_concrete_powder": "textures/blocks/concrete_powder_cyan",
        "cyan_glazed_terracotta": "textures/blocks/glazed_terracotta_cyan",
        "cyan_shulker_box": "textures/blocks/shulker_top_cyan",
        "cyan_stained_glass": "textures/blocks/glass_cyan",
        "cyan_terracotta": "textures/blocks/hardened_clay_stained_cyan",
        "damaged_anvil_top": "textures/blocks/anvil_top_damaged_2",
        "dandelion": "textures/blocks/flower_dandelion",
        "dark_oak_log_top": "textures/blocks/log_big_oak_top",
        "dark_oak_planks": "textures/blocks/planks_big_oak",
        "dark_oak_sapling": "textures/blocks/sapling_roofed_oak",
        "dark_prismarine": "textures/blocks/prismarine_dark",
        "dead_brain_coral": "textures/blocks/coral_plant_pink_dead",
        "dead_brain_coral_block": "textures/blocks/coral_pink_dead",
        "dead_brain_coral_fan": "textures/blocks/coral_fan_pink_dead",
        "dead_bubble_coral": "textures/blocks/coral_plant_purple_dead",
        "dead_bubble_coral_block": "textures/blocks/coral_purple_dead",
        "dead_bubble_coral_fan": "textures/blocks/coral_fan_purple_dead",
        "dead_fire_coral": "textures/blocks/coral_plant_red_dead",
        "dead_fire_coral_block": "textures/blocks/coral_red_dead",
        "dead_fire_coral_fan": "textures/blocks/coral_fan_red_dead",
        "dead_horn_coral": "textures/blocks/coral_plant_yellow_dead",
        "dead_horn_coral_block": "textures/blocks/coral_yellow_dead",
        "dead_horn_coral_fan": "textures/blocks/coral_fan_yellow_dead",
        "dead_tube_coral": "textures/blocks/coral_plant_blue_dead",
        "dead_tube_coral_block": "textures/blocks/coral_blue_dead",
        "dead_tube_coral_fan": "textures/blocks/coral_fan_blue_dead",
        "diorite": "textures/blocks/stone_diorite",
        "fire_coral": "textures/blocks/coral_plant_red",
        "fire_coral_fan": "textures/blocks/coral_fan_red",
        "fletching_table_top": "textures/blocks/fletcher_table_top",
        "granite": "textures/blocks/stone_granite",
        "gray_concrete": "textures/blocks/concrete_gray",
        "gray_concrete_powder": "textures/blocks/concrete_powder_gray",
        "gray_glazed_terracotta": "textures/blocks/glazed_terracotta_gray",
        "gray_shulker_box": "textures/blocks/shulker_top_gray",
        "gray_stained_glass": "textures/blocks/glass_gray",
        "gray_terracotta": "textures/blocks/hardened_clay_stained_gray",
        "green_concrete": "textures/blocks/concrete_green",
        "green_concrete_powder": "textures/blocks/concrete_powder_green",
        "green_glazed_terracotta": "textures/blocks/glazed_terracotta_green",
        "green_shulker_box": "textures/blocks/shulker_top_green",
        "green_stained_glass": "textures/blocks/glass_green",
        "green_terracotta": "textures/blocks/hardened_clay_stained_green",
        "honeycomb_block": "textures/blocks/honeycomb",
        "horn_coral": "textures/blocks/coral_plant_yellow",
        "horn_coral_block": "textures/blocks/coral_yellow",
        "horn_coral_fan": "textures/blocks/coral_fan_yellow",
        "jungle_log_top": "textures/blocks/log_jungle_top",
        "jungle_planks": "textures/blocks/planks_jungle",
        "jungle_sapling": "textures/blocks/sapling_jungle",
        "large_fern_bottom": "textures/blocks/double_plant_fern_bottom",
        "large_fern_top": "textures/blocks/double_plant_fern_top",
        "light_blue_concrete": "textures/blocks/concrete_light_blue",
        "light_blue_concrete_powder": "textures/blocks/concrete_powder_light_blue",
        "light_blue_glazed_terracotta": "textures/blocks/glazed_terracotta_light_blue",
        "light_blue_shulker_box": "textures/blocks/shulker_top_light_blue",
        "light_blue_stained_glass": "textures/blocks/glass_light_blue",
        "light_blue_terracotta": "textures/blocks/hardened_clay_stained_light_blue",
        "light_gray_concrete": "textures/blocks/concrete_silver",
        "light_gray_concrete_powder": "textures/blocks/concrete_powder_silver",
        "light_gray_shulker_box": "textures/blocks/shulker_top_silver",
        "light_gray_stained_glass": "textures/blocks/glass_silver",
        "light_gray_terracotta": "textures/blocks/hardened_clay_stained_silver",
        "lily_of_the_valley": "textures/blocks/flower_lily_of_the_valley",
        "lime_concrete": "textures/blocks/concrete_lime",
        "lime_concrete_powder": "textures/blocks/concrete_powder_lime",
        "lime_glazed_terracotta": "textures/blocks/glazed_terracotta_lime",
        "lime_shulker_box": "textures/blocks/shulker_top_lime",
        "lime_stained_glass": "textures/blocks/glass_lime",
        "lime_terracotta": "textures/blocks/hardened_clay_stained_lime",
        "magenta_concrete": "textures/blocks/concrete_magenta",
        "magenta_concrete_powder": "textures/blocks/concrete_powder_magenta",
        "magenta_glazed_terracotta": "textures/blocks/glazed_terracotta_magenta",
        "magenta_shulker_box": "textures/blocks/shulker_top_magenta",
        "magenta_stained_glass": "textures/blocks/glass_magenta",
        "magenta_terracotta": "textures/blocks/hardened_clay_stained_magenta",
        "mossy_stone_bricks": "textures/blocks/stonebrick_mossy",
        "oak_log_top": "textures/blocks/log_oak_top",
        "oak_planks": "textures/blocks/planks_oak",
        "oak_sapling": "textures/blocks/sapling_oak",
        "orange_concrete": "textures/blocks/concrete_orange",
        "orange_concrete_powder": "textures/blocks/concrete_powder_orange",
        "orange_glazed_terracotta": "textures/blocks/glazed_terracotta_orange",
        "orange_shulker_box": "textures/blocks/shulker_top_orange",
        "orange_stained_glass": "textures/blocks/glass_orange",
        "orange_terracotta": "textures/blocks/hardened_clay_stained_orange",
        "orange_tulip": "textures/blocks/flower_tulip_orange",
        "oxeye_daisy": "textures/blocks/flower_oxeye_daisy",
        "peony_bottom": "textures/blocks/double_plant_paeonia_bottom",
        "peony_top": "textures/blocks/double_plant_paeonia_top",
        "pink_concrete": "textures/blocks/concrete_pink",
        "pink_concrete_powder": "textures/blocks/concrete_powder_pink",
        "pink_glazed_terracotta": "textures/blocks/glazed_terracotta_pink",
        "pink_shulker_box": "textures/blocks/shulker_top_pink",
        "pink_stained_glass": "textures/blocks/glass_pink",
        "pink_terracotta": "textures/blocks/hardened_clay_stained_pink",
        "pink_tulip": "textures/blocks/flower_tulip_pink",
        "polished_andesite": "textures/blocks/stone_andesite_smooth",
        "polished_diorite": "textures/blocks/stone_diorite_smooth",
        "polished_granite": "textures/blocks/stone_granite_smooth",
        "poppy": "textures/blocks/flower_rose",
        "purple_concrete": "textures/blocks/concrete_purple",
        "purple_concrete_powder": "textures/blocks/concrete_powder_purple",
        "purple_shulker_box": "textures/blocks/shulker_top_purple",
        "purple_stained_glass": "textures/blocks/glass_purple",
        "purple_terracotta": "textures/blocks/hardened_clay_stained_purple",
        "quartz_pillar_top": "textures/blocks/quartz_block_lines_top",
        "red_concrete": "textures/blocks/concrete_red",
        "red_concrete_powder": "textures/blocks/concrete_powder_red",
        "red_glazed_terracotta": "textures/blocks/glazed_terracotta_red",
        "red_shulker_box": "textures/blocks/shulker_top_red",
        "red_stained_glass": "textures/blocks/glass_red",
        "red_terracotta": "textures/blocks/hardened_clay_stained_red",
        "red_tulip": "textures/blocks/flower_tulip_red",
        "rose_bush_bottom": "textures/blocks/double_plant_rose_bottom",
        "rose_bush_top": "textures/blocks/double_plant_rose_top",
        "slime_block": "textures/blocks/slime",
        "smooth_stone": "textures/blocks/stone_slab_top",
        "smooth_stone_slab_side": "textures/blocks/stone_slab_side",
        "soul_campfire_fire": "textures/blocks/soul_campfire",
        "spruce_log_top": "textures/blocks/log_spruce_top",
        "spruce_sapling": "textures/blocks/sapling_spruce",
        "stone_bricks": "textures/blocks/stonebrick",
        "sunflower_bottom": "textures/blocks/double_plant_sunflower_bottom",
        "sunflower_top": "textures/blocks/double_plant_sunflower_top",
        "tall_grass_bottom": "textures/blocks/double_plant_grass_bottom",
        "tall_grass_top": "textures/blocks/double_plant_grass_top",
        "tube_coral": "textures/blocks/coral_plant_blue",
        "tube_coral_block": "textures/blocks/coral_blue",
        "tube_coral_fan": "textures/blocks/coral_fan_blue",
        "wet_sponge": "textures/blocks/sponge_wet",
        "white_concrete": "textures/blocks/concrete_white",
        "white_concrete_powder": "textures/blocks/concrete_powder_white",
        "white_glazed_terracotta": "textures/blocks/glazed_terracotta_white",
        "white_shulker_box": "textures/blocks/shulker_top_white",
        "white_stained_glass": "textures/blocks/glass_white",
        "white_terracotta": "textures/blocks/hardened_clay_stained_white",
        "white_tulip": "textures/blocks/flower_tulip_white",
        "wither_rose": "textures/blocks/flower_wither_rose",
        "yellow_concrete": "textures/blocks/concrete_yellow",
        "yellow_concrete_powder": "textures/blocks/concrete_powder_yellow",
        "yellow_glazed_terracotta": "textures/blocks/glazed_terracotta_yellow",
        "yellow_shulker_box": "textures/blocks/shulker_top_yellow",
        "yellow_stained_glass": "textures/blocks/glass_yellow",
        "yellow_terracotta": "textures/blocks/hardened_clay_stained_yellow",
    },
}

# atlas -> Java texture name -> the Bedrock file its same-named short name shows,
# which does not look like the Java texture (kept so the residue can say so)
DIFFERS: dict[str, dict[str, str]] = {
    "item": {
    },
    "terrain": {
        "black_stained_glass_pane_top": "textures/blocks/glass_pane_top_black",
        "blue_stained_glass_pane_top": "textures/blocks/glass_pane_top_blue",
        "brown_stained_glass_pane_top": "textures/blocks/glass_pane_top_brown",
        "bubble_coral_block": "textures/blocks/coral_purple",
        "command_block_back": "textures/blocks/command_block_back_mipmap",
        "command_block_front": "textures/blocks/command_block_front_mipmap",
        "command_block_side": "textures/blocks/command_block_side_mipmap",
        "conduit": "textures/blocks/conduit_base",
        "cyan_stained_glass_pane_top": "textures/blocks/glass_pane_top_cyan",
        "fire_coral_block": "textures/blocks/coral_red",
        "gray_stained_glass_pane_top": "textures/blocks/glass_pane_top_gray",
        "green_stained_glass_pane_top": "textures/blocks/glass_pane_top_green",
        "light_blue_stained_glass_pane_top": "textures/blocks/glass_pane_top_light_blue",
        "light_gray_stained_glass_pane_top": "textures/blocks/glass_pane_top_silver",
        "lilac_bottom": "textures/blocks/double_plant_syringa_bottom",
        "lilac_top": "textures/blocks/double_plant_syringa_top",
        "lime_stained_glass_pane_top": "textures/blocks/glass_pane_top_lime",
        "magenta_stained_glass_pane_top": "textures/blocks/glass_pane_top_magenta",
        "orange_stained_glass_pane_top": "textures/blocks/glass_pane_top_orange",
        "pink_stained_glass_pane_top": "textures/blocks/glass_pane_top_pink",
        "piston_top": "textures/blocks/piston_inner",
        "purple_glazed_terracotta": "textures/blocks/glazed_terracotta_purple",
        "purple_stained_glass_pane_top": "textures/blocks/glass_pane_top_purple",
        "red_stained_glass_pane_top": "textures/blocks/glass_pane_top_red",
        "short_grass": "textures/blocks/tallgrass",
        "spruce_planks": "textures/blocks/planks_spruce",
        "white_stained_glass_pane_top": "textures/blocks/glass_pane_top_white",
        "yellow_stained_glass_pane_top": "textures/blocks/glass_pane_top_yellow",
    },
}


def verified(atlas: str, name: str, file: str) -> bool:
    """Whether Java's ``name`` is known to look exactly like Bedrock's ``file``."""
    return ALIASES.get(atlas, {}).get(name) == file


def differs(atlas: str, name: str, file: str) -> bool:
    """Whether the pixel check found Bedrock's ``file`` is not Java's ``name``."""
    return DIFFERS.get(atlas, {}).get(name) == file
