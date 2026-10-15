# Getting started: convert your own mod

This guide is for a modder with a Java mod who wants a Bedrock add-on out of it.
You need Python 3.11 or newer. You don't need Minecraft, Java, a server, or an
API key.

## Install

```bash
git clone https://github.com/anchapin/portkit-v2
cd portkit-v2
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Then fetch Bedrock's vanilla sound list, once (it's Mojang's data, so it is
downloaded rather than shipped, and cached under `~/.cache/portkit/reference/`):

```bash
portkit reference fetch
```

It lets portkit keep a sound your mod borrows from vanilla (`random/bow`,
`minecraft:mob/slime/big1`) when Bedrock has the same file. Skip it and those
sounds are dropped, each with a note saying to run the fetch.

The same command fetches the item tags your loader and vanilla define (Forge
1.20.1, NeoForge 1.21.1, Fabric convention tags, vanilla per game version).
Your mod's own `c:`/`forge:`/`minecraft:` tag files only list what it adds;
without the loader's share a recipe like "any colorless glass" stays residue
instead of quietly becoming "only my glass". Add `--mod yourmod.jar` to fetch
only the data your jar's loader and game version need.

It also fetches a few vanilla block model templates (stairs, slabs, walls,
fences, the cube shapes). Your stairs model names `minecraft:block/stairs` and
its textures; the boxes come from vanilla's model, so without the templates
stairs, slabs, walls and pillars that lie on their side stay residue.

## Convert

Point `portkit convert` at your mod's `.jar`, or at an unpacked directory that
holds `assets/` and `data/`:

```bash
portkit convert path/to/yourmod-1.0.jar out/
```

You get:

| path | what it is |
| --- | --- |
| `out/behavior_pack/` | blocks, items, recipes, loot tables |
| `out/resource_pack/` | textures, geometry, sounds, translations |
| `out/<mod>.mcaddon` | the installable add-on (written only when the packs validate) |
| `out/unhandled.json` | everything portkit refused to guess at, with a reason for each (written only when there is any) |

The command also prints a JSON summary: files converted, residue count,
coverage, the mod metadata it found, and the `notes`. Notes list things that
converted but lost a detail Bedrock can't carry, such as a furnace result count
or a random model variant.

To install, open the `.mcaddon` on a device with Minecraft Bedrock, or copy the
two pack folders into `development_behavior_packs/` and
`development_resource_packs/`.

## Read the residue

portkit converts what has a definite Bedrock equivalent and refuses the rest.
Each refusal is an `Unhandled` entry in `unhandled.json`:

```json
{"source": "data/yourmod/recipes/alloy_block.json", "kind": "recipe",
 "reason": "ingredient uses tag 'yourmod:alloy_ingots', which covers 2 items: ...", "count": 1}
```

There are three common kinds:

- **Something Java does in code.** Bows and items that swap their look on
  item properties, multipart blockstates whose states the mod's Java sets,
  and compiled classes. There is no file to translate, so that behaviour has
  to be written by hand or by the agent. (A held tool converts as its icon,
  held like a tool; a note says its mining, attack and durability behaviour
  was not converted.)
- **A real choice.** A recipe over a tag with several members, or an armour
  trim. portkit won't pick for you.
- **`unowned`.** Files no converter claims yet. These are the best candidates
  for a new converter (see [the converter guide](converter-guide.md)).

`portkit report out/` turns a converted tree into a readable report, and
`portkit validate out/` re-runs the validator after you edit the packs by hand.

## Bedrock experiments

Some Bedrock features a converted block could use are still behind one of the
world's experiment toggles. portkit leaves them out unless you say your world
runs that experiment, since a pack that needs an experiment the world doesn't
have fails to load the blocks that use it.

```bash
portkit convert refurbished_furniture.jar out/ --experiment upcoming_creator_features
```

`upcoming_creator_features` (the world's *Upcoming Creator Features* toggle)
turns blocks that hold items behind a plain chest-style menu in Java (Refurbished
Furniture's drawers and fridges, Cluttered's cabinets and side tables) into
Bedrock containers with the slot count their code gives
(`minecraft:block_entity` `container`, block format 1.26.50). Without it they
convert as decoration and the conversion notes list what was read. The notes
name every block made a container and what of its Java behaviour isn't carried.

## Mod config options

Some content only exists when an option in the mod's config file is on. In Java
a player or server edits that file; a Bedrock add-on has no such file, so the
choice is made when you convert. By default portkit uses each option's default,
read from the mod's own source (`src/portkit/data/config_flag_defaults.json`):
Mythic Metals' dusts, for example, are off, so its 37 dust recipes and 27 dust
items are residue saying `disabled by default config: mythicmetals:dust_enabled`.

Set an option with `--config <mod>.<option>=<true|false>` (repeatable):

```bash
portkit convert mythicmetals-0.24.6+1.21.jar out/ --config mythicmetals.enableDusts=true
portkit convert tinkers.jar out/ --config tconstruct.forceIntegrationMaterials=true
portkit convert supplementaries.jar out/ --config supplementaries.flax=false
```

The option is the flag as the mod's load conditions name it (`dust_enabled`,
`flax`, `force_integration_materials`) or, where the data file cites it, the
option's own name in the mod's config file (`enableDusts`,
`forceIntegrationMaterials`). It works both ways: turning a default-on option
off sends what it gates to residue as `disabled by user config: <flag>`. An
option portkit has no cited default for can still be set when the jar's files
use it, since your choice decides it. A misspelt option or an unknown mod is an
error that lists the valid options; nothing is silently ignored.

A few options are numbers a converted behaviour reads rather than switches.
These are cited with their default and the range the mod's config accepts, and
take a number in that range:

```bash
portkit convert farmersdelight.jar out/ --config farmersdelight.cuttingBoardFortuneBonus=0.25
```

(on Farmer's Delight 1.3.4 or Refabricated 3.6.28, each Fortune level on the
cutting board's tool adds 0.25 to every chance result instead of the default
0.1). A number outside the range is an error; Java would quietly clamp it or
put the default back, depending on the loader.

Several options can go in a file, JSON or TOML, passed with
`--config-file` (settings given with `--config` win over it):

```toml
[mythicmetals]
enableDusts = true
enableAnvils = false
```

Every run with settings writes `out/config-overrides.json`, lists the settings
in the summary's `config` and `notes`, and adds a table to `portkit report`.
Pass `config-overrides.json` back with `--config-file` to reproduce the output.
Without any setting the output is the default-config conversion.

## Optional: let an agent work the residue

The agent only ever sees the residue, with the validator as a tool. Pick a
provider and a model, then add `--agent`:

```bash
export PORTKIT_LLM_PROVIDER=anthropic      # openai | anthropic | gemini | gemini_native
export PORTKIT_LLM_MODEL=<model>
export ANTHROPIC_API_KEY=...
portkit convert yourmod.jar out/ --agent --agent-max-cost 0.50
```

The README's agent section covers budgets, transcripts, `--repeat` and the
recommended default model (DeepSeek V4.1 Flash through OpenRouter). A group the
agent can't resolve cleanly is rolled back and stays in `unhandled.json`.

## When the output is wrong

Open an issue with the smallest slice of your mod that reproduces it. Better
still, shrink it into a fixture under `fixtures/` (see `fixtures/README.md`),
since that's how every fix in this repo starts.
