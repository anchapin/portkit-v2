# Real-mod corpus

Real mods from Modrinth, pinned by version id and sha512 in `mods.toml`. The
jars are **downloaded, never committed**: we measure them, we don't
redistribute them.

```bash
portkit corpus fetch        # the default set, into ~/.cache/portkit/mods (PORTKIT_CORPUS_CACHE overrides)
portkit reference fetch     # Bedrock's vanilla sound list, into ~/.cache/portkit/reference (#124)
portkit corpus list         # what's pinned and whether it's cached
portkit eval --corpus       # coverage per mod against coverage-baseline.json
portkit eval --corpus --fetch --fixture betterend   # one mod, downloading if needed
```

These commands cover the **default set** (the first table below). The optional
mods are pinned too but only run when asked for; see [Optional mods](#optional-mods).

A download whose hash doesn't match the pin is refused. A mod that's re-uploaded
or pulled upstream fails loudly instead of quietly changing the numbers.

`coverage-baseline.json` is the same ratchet as the hand-built fixtures, plus a
per-mod validator `errors` count. A real mod is allowed to be invalid today,
but it can't get worse unnoticed. Bank an improvement with
`portkit eval --corpus --update-baseline`.

## A second oracle: Mojang's mct

`portkit eval --corpus --mct` also runs Mojang's
[Minecraft Creator Tools](https://www.npmjs.com/package/@minecraft/creator-tools)
(`mct validate`, Node 22+) over each converted mod and prints its findings by
severity and rule. Our validator is otherwise the only judge; mct is a
differential check that catches what ours misses (#113). It's report-only: mct
findings never fail the run. With `--json PATH` they're written alongside the
coverage rows. Without `mct` on PATH the flag is skipped with a note.

```bash
npm install -g @minecraft/creator-tools@0.20.0
mct eula --accept              # once; Mojang's EULA + privacy statement
portkit eval --corpus --mct --json /tmp/corpus-eval.json
```

Known mct noise on our output, as of mct 0.20.0: `JSON` "string value found,
but a array is required" on `texture_data.*.textures` (vanilla packs use the
string form), `UNLINK` on `minecraft:` items in recipes (mct doesn't index
vanilla items there), and `UNLINK` on recipes and loot naming our own *blocks*
(mct only counts `items/` as item types). `FORMATVER`/`MINENGINEVER`
recommendations say our format versions trail the current release.

CI: `.github/workflows/real-mods.yml` runs the default set nightly and on
demand, with the jars cached on the manifest's hash; a manual dispatch with
`include_optional` ticked adds the optional mods. `pytest -q` skips the
`realmods` tests when the jars aren't cached, so the normal suite stays offline.

## Default set

| name | mod | version | loader | Minecraft | license | source |
| --- | --- | --- | --- | --- | --- | --- |
| `farmers_delight_neoforge` | Farmer's Delight | 1.21.1-1.3.4 | NeoForge | 1.21.1 | MIT | [vectorwing/FarmersDelight](https://github.com/vectorwing/FarmersDelight) |
| `farmers_delight_fabric` | Farmer's Delight Refabricated | 26.1-3.6.28 | Fabric | 26.1 | MIT | [MehVahdJukaar/FarmersDelightRefabricated](https://github.com/MehVahdJukaar/FarmersDelightRefabricated) |
| `betterend` | BetterEnd | 21.800.2 | Fabric | 1.21.8 | MIT | [quiqueck/BetterEnd](https://github.com/quiqueck/BetterEnd) |
| `create` | Create | mc1.20.1-6.0.8 | Forge | 1.20.1 | Create Mod License | [Creators-of-Create/Create](https://github.com/Creators-of-Create/Create) |
| `supplementaries` | Supplementaries | 1.20-3.1.43-forge | Forge | 1.20.1 | Supplementaries Team License | [MehVahdJukaar/Supplementaries](https://github.com/MehVahdJukaar/Supplementaries) |
| `waystones` | Waystones | 21.1.46+neoforge-1.21.1 | NeoForge | 1.21.1 | All Rights Reserved | [TwelveIterations/Waystones](https://github.com/TwelveIterations/Waystones) |
| `mythicmetals` | Mythic Metals | 0.24.6+1.21 | Fabric | 1.21.1 | MIT | [Noaaan/MythicMetals](https://github.com/Noaaan/MythicMetals) |
| `silent_gear_1165` | Silent Gear | 2.6.36 | Forge | 1.16.5 | MIT | [SilentChaos512/Silent-Gear](https://github.com/SilentChaos512/Silent-Gear) |
| `storage_drawers` | Storage Drawers | 1.21.1-13.11.4 | NeoForge | 1.21.1 | MIT | [jaquadro/StorageDrawers](https://github.com/jaquadro/StorageDrawers) |
| `storage_drawers_1122` | Storage Drawers | 1.12-5.5.2 | Forge | 1.12.2 | MIT | [jaquadro/StorageDrawers](https://github.com/jaquadro/StorageDrawers) |
| `veinminer` | VeinMiner | 2.11.2 | NeoForge | 1.21.1 | AGPL-3.0-only | [modrinth.com/mod/veinminer](https://modrinth.com/mod/veinminer) |
| `natures_compass` | Nature's Compass | 1.21.1-3.4.0-neoforge | NeoForge | 1.21.1 | CC-BY-NC-SA-4.0 | [MattCzyr/NaturesCompass](https://github.com/MattCzyr/NaturesCompass) |

The license column is the mod's declared license on Modrinth. Several aren't
open source (Create, Supplementaries, Waystones), and some mods license their
art separately. That's fine here because nothing is redistributed; we only
download from Modrinth's CDN and measure.

Six of the twelve come from PortKit v1's own failure audits (#26): Create,
Supplementaries and Waystones from portkit#971 (4 to 8% coverage), and Silent
Gear and Storage Drawers from portkit#1105 (zero output). The two Storage
Drawers pins and the two Farmer's Delight pins are the same mod across eras
and loaders: Storage Drawers 1.21.1 is the build the top-50 gauntlet measured,
1.12.2 keeps the pre-flattening layout measured. Mythic Metals (since
2026-10-12) brings armor, tools and ores, which the rest of the set lacks. It
publishes only beta builds on Modrinth, so its pin is the newest 1.21.1 beta.

### Pinned on the gauntlet's builds (#289)

These mods were already in the corpus, and are pinned again on the build the
top-50 gauntlet (#278) measured, so both manifests measure the same jar and
their numbers can be compared. The work each needs already landed, so they are
ticked off:

| mod | gauntlet rank | corpus pin | done by |
| --- | ---: | --- | --- |
| `waystones` | 30 | 21.1.46+neoforge-1.21.1 | [#178](https://github.com/anchapin/portkit-v2/issues/178) (the Waystones adapter) |
| `tinkers_construct` | 35 | 3.11.2.166 | [#174](https://github.com/anchapin/portkit-v2/issues/174), [#175](https://github.com/anchapin/portkit-v2/issues/175) (fluids and tool stats) |
| `storage_drawers` | 39 | 1.21.1-13.11.4 | [#179](https://github.com/anchapin/portkit-v2/issues/179) (the drawers convert) |

## Optional mods

Pinned and baselined like the rest, but left out of the default `corpus fetch`,
`eval --corpus` and realmods gate, because they're slow, huge or niche. Their
`coverage-baseline.json` entries are ratcheted whenever they run and ignored
when they're skipped, so re-banking the default set keeps them.

| name | mod | version | loader | Minecraft | license | source | why |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `tinkers_construct` | Tinkers' Construct | 3.11.2.166 | Forge | 1.20.1 | MIT | [SlimeKnights/TinkersConstruct](https://github.com/SlimeKnights/TinkersConstruct) | the top-50 gauntlet's build (#278, rank 35); custom recipe types, fluids (#174, #175). Optional since 2026-10-12: 11,752 generated tool sprites, ~13.5k files (#122) |
| `alexs_mobs` | Alex's Mobs | 1.22.9 | Forge | 1.20.1 | GPL-3.0-only | [AlexModGuy/AlexsMobs](https://github.com/AlexModGuy/AlexsMobs) | entities: models, animations, spawns, loot |
| `mekanism` | Mekanism | 10.7.19.85 | NeoForge | 1.21.1 | MIT | [mekanism/Mekanism](https://github.com/mekanism/Mekanism) | fluids and chemicals, machines, custom recipe types (main jar only) |

```bash
portkit corpus fetch --include-optional                 # every pinned jar
portkit eval --corpus --include-optional                # the default set plus the optional mods
portkit eval --corpus --fetch --fixture mekanism        # any one mod, optional or not
portkit eval --corpus --include-optional --update-baseline   # bank all of them
pytest -m realmods                                      # the optional test runs once they're cached
```

In CI, dispatch `real-mods` by hand with `include_optional` ticked.

## Adding a mod

1. Pick a version on Modrinth and read `https://api.modrinth.com/v2/version/<id>`.
2. Add a `[[mod]]` entry with the primary file's `url` and `hashes.sha512`, plus the license and source.
   Add `optional = true` to keep it out of the default runs.
3. Run `portkit corpus fetch --include-optional && portkit reference fetch && portkit eval --corpus --include-optional --update-baseline` and commit both files.

Mods from v1 failure reports (#26) belong here too: record the report in `notes`.
