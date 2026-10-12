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
