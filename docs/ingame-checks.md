# In-game checks (Bedrock Dedicated Server)

mct and the schemas check a converted pack's structure. These checks load it
in Mojang's own server and look at what the game does with it (#238).

## What runs

`portkit ingame run` copies an unpacked Bedrock Dedicated Server (BDS), installs
the converted behavior and resource packs plus a generated check behavior pack
(`portkit.ingame.testpack`), starts a flat creative world nobody joins, and
reads the server output. The check pack's script (`src/portkit/ingame/runtime/`,
stable `@minecraft/server` 2.0.0, no experiments needed) runs once the world
loads:

| check | what passes |
| --- | --- |
| `place` | every block the pack defines resolves and sets in the world, and reads back with its id |
| `item`, `block_item` | every item, and every block's item, builds as an `ItemStack` and spawns as an item entity carrying the same id |
| `container` | a block the converter made a container (#226, `--experiment upcoming_creator_features`) has a `minecraft:inventory` of the slot count it wrote |
| `connection` | a block on the `minecraft:connection` trait (#221 multiparts, palisades, walls) reports all four `minecraft:connection_<dir>` states: joined to its own kind (east), not to air (south, west); north is stone, reported only |
| `ore_generate` | each converted ore rule (#281): fresh chunks of its dimension (the Overworld only with `--world default`) hold at least one of its ore blocks in its height range; skipped when the range holds none of the blocks it may replace |
| `geode_generate` | each converted geode rule (#281 slice 3): the check pack carries a test-only copy of the rule (`portkit_check:<rule>`, no `scatter_chance`), so the converted geode feature is placed in every chunk; fresh chunks of its dimension (the Overworld only with `--world default`) hold at least one of its inner or alternate inner layer blocks. The `minecraft:block_face` of each inner placement block found is reported, not asserted |

A run fails when a check fails, the script never finishes, or the server logs a
content-log ERROR. `report.json` holds the counts, every failure, the
connection states read, and every content-log error and warning;
`server.log` is the whole server output and `content-log/` the server's own
content-log file.

What it can't see: anything only the client does. Geometry, textures, bone
visibility, render methods and UI are resource-pack work the server doesn't
load; the connection check proves the states a pack's `bone_visibility`
reads, not the bones drawn.

## Running it

```
portkit ingame fetch-server --dir bds --accept-eula   # x86-64 Linux only
portkit convert some-mod.jar tree/some-mod --no-addon
portkit ingame run --server bds --tree tree/some-mod --out ingame/some-mod \
    [--experiment upcoming_creator_features]
```

`--experiment` toggles the experiment in the world's `level.dat` (a first boot
writes the world, `portkit.ingame.nbt` edits it). `portkit ingame pack` writes
only the check pack, to install by hand.

BDS is downloaded from minecraft.net, sha256-checked against the pin in
`src/portkit/ingame/server.py`, and never committed, cached or uploaded.
Downloading it means agreeing to the Minecraft End User License Agreement
(minecraft.net/eula) and the Microsoft Privacy Statement: the download page
gates its button behind "I agree to the Minecraft End User License Agreement
and Privacy Policy". `fetch-server` refuses without `--accept-eula`.

The workflow is `.github/workflows/ingame.yml` (manual dispatch, report-only;
see docs/decisions.md 2026-10-15 for the open choices).

BDS stops at a recipe's first problem. Until converted crafting recipes carried
`unlock` (#260) every one stopped there ("1.20+ Recipes require unlock data"),
so ingredient and result ids Bedrock doesn't know only show up once the unlock
is in place (#261).
