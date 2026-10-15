# Reference data: sources

## Bedrock vanilla sound list (#124)

Nothing from Mojang/bedrock-samples is stored here or shipped in the package
(#124). The sounds converter and validator read a list of the audio paths named
in Bedrock's vanilla `resource_pack/sounds/sound_definitions.json`, from
[Mojang/bedrock-samples](https://github.com/Mojang/bedrock-samples) at
`46ba6ea985fb5a92d79a9419198f10dda14c199d` (the commit pinned for the agent
reference, see `portkit/agent/reference/NOTICE.md`). That data is (c) Mojang AB,
all rights reserved; use is subject to the
[Minecraft EULA](https://www.minecraft.net/en-us/eula).

`portkit reference fetch` downloads the file at that commit, derives the path
list (paths only: no audio and no definitions), checks it against the sha256
pinned in `portkit/data/__init__.py` and caches it under
`~/.cache/portkit/reference/` (`$XDG_CACHE_HOME`, or `$PORTKIT_REFERENCE_CACHE`
to move it). Without it, vanilla sound references are dropped with a note
saying to run the fetch. `python scripts/build_vanilla_sounds.py` prints the
sha256 to pin after bumping the commit (`--check` says whether the pin is
current).

## Bedrock vanilla texture atlases

Nothing from these is stored here or shipped in the package either, and no
texture art is fetched at all. `portkit reference fetch` downloads Bedrock's
vanilla `resource_pack/textures/terrain_texture.json`, `item_texture.json` and
`flipbook_textures.json` from
[Mojang/bedrock-samples](https://github.com/Mojang/bedrock-samples) at the same
pinned commit as the sound list, keeps only each short name and the file paths it
points at (plus which files vanilla animates), checks the result against the
sha256 pinned in `portkit/data/vanilla_textures.py` and caches it. That data is
(c) Mojang AB, all rights reserved; use is subject to the
[Minecraft EULA](https://www.minecraft.net/en-us/eula) (#24). The converter uses
it to point a mod's vanilla texture references at the textures the vanilla
resource pack already ships (`python -m portkit.data.vanilla_textures --pin`
prints the sha256 to pin after bumping the commit). Without it, vanilla texture
references stay residue with a note saying to run the fetch.

## Loader and vanilla item tags (#160)

Nothing from these is stored here or shipped in the package either.
`portkit reference fetch` downloads each pinned artifact below, keeps only its
item tag membership (tag id -> the `values` list), checks the result against the
sha256 pinned in `portkit/data/tags.py` and caches it in the same reference
cache. The tag resolver reads the set nearest the loader and game version the
mod's jar declares; without it, recipes on shared tags stay residue.

| set | source (pinned) | licence |
|---|---|---|
| forge-1.20.1 | `data/forge/tags/items/**` in `net.minecraftforge:forge:1.20.1-47.4.26:universal` (maven.minecraftforge.net); source [MinecraftForge/MinecraftForge](https://github.com/MinecraftForge/MinecraftForge) | LGPL-2.1 |
| neoforge-1.21.1 | `data/c/tags/item/**` and `data/neoforge/tags/item/**` in `net.neoforged:neoforge:21.1.259:universal` (maven.neoforged.net); source [neoforged/NeoForge](https://github.com/neoforged/NeoForge) | LGPL-2.1 |
| fabric-1.20.1 | `data/c/tags/items/**` in `net.fabricmc.fabric-api:fabric-convention-tags-v1:1.5.6+1802ada577` (Fabric API 0.92.12+1.20.1, maven.fabricmc.net); source [FabricMC/fabric](https://github.com/FabricMC/fabric) | Apache-2.0 |
| fabric-1.21.1 | `data/c/tags/item/**` in `fabric-convention-tags-v2:2.12.0+c3656daa19` (Fabric API 0.116.17+1.21.1) | Apache-2.0 |
| fabric-1.21.8 | `data/c/tags/item/**` in `fabric-convention-tags-v2:2.15.6+eb5df52f2c` (Fabric API 0.136.1+1.21.8) | Apache-2.0 |
| fabric-26.1 | `data/c/tags/item/**` in `fabric-convention-tags-v2:4.3.2+c37e6e5f47` (Fabric API 0.145.1+26.1) | Apache-2.0 |
| vanilla-VERSION | `data/tag/item/data.json` of [misode/mcmeta](https://github.com/misode/mcmeta) `VERSION-summary` at a pinned commit, for 1.16.5, 1.19.2, 1.20.1, 1.21.1, 1.21.8 and 26.1 | generated from Minecraft: (c) Mojang AB, subject to the [Minecraft EULA](https://www.minecraft.net/en-us/eula) |

The tests use a few hand-written entries in `tests/data/tag_reference/`, not
copies of these files. `python -m portkit.data.tags --pins` downloads every set
and prints the sha256 to pin after bumping a version.

## Vanilla block model templates (stairs, slabs, walls)

Nothing from these is stored here or shipped either. The block converter needs
the elements of a few vanilla parent models (`block/stairs`, `inner_stairs`,
`outer_stairs`, `slab`, `slab_top`, `template_wall_post`, `template_wall_side`,
`template_wall_side_tall`, `fence_post`, `fence_side`, `cube`, `cube_all`,
`cube_column`, `cube_column_horizontal`, and their parent `block/block`).
`portkit reference fetch` downloads `assets/model/data.json` of
[misode/mcmeta](https://github.com/misode/mcmeta) `1.20.1-summary` at
`15f05b54846b0cc5adebe63b245c7045ba105709` (the commit the vanilla-1.20.1 tag
set pins), keeps only those models' `parent`, `textures` and `elements`, checks
the result against the sha256 pinned in `portkit/data/models.py` and caches it
as `models-vanilla-1.20.1-<sha12>.json`. Generated from Minecraft: (c) Mojang AB,
subject to the [Minecraft EULA](https://www.minecraft.net/en-us/eula). The same
derivation is identical for the 1.16.5, 1.19.2, 1.21.1, 1.21.8 and 26.1
summaries, so one set serves every mod. The tests use hand-written shapes in
`tests/data/model_templates.json`, not copies. `python -m portkit.data.models
--pin` prints the sha256 to pin after bumping the commit.

## Vanilla campfire recipes (#177, the Farmer's Delight stove)

Nothing from these is stored here or shipped in the package either. `portkit
reference fetch` downloads `data/recipe/data.json` of
[misode/mcmeta](https://github.com/misode/mcmeta) `1.21.1-summary` at
`7cffbcdad5fa36f22acef6bd4b869ecad4ca3fd9` and `26.1-summary` at
`e7068326fb23dcdff9fff17c7eabcd59f46e7460` (the commits the vanilla tag sets
pin), keeps only the `minecraft:campfire_cooking` recipes, checks the result
against the sha256 pinned in `portkit/data/recipes.py` and caches it in the
same reference cache. Generated from Minecraft: (c) Mojang AB, subject to the
[Minecraft EULA](https://www.minecraft.net/en-us/eula). Without it, the stove's
table holds only the jar's own campfire recipes, with a note saying to run the
fetch.
