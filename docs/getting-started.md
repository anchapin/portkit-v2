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

- **Something Java does in code.** Held tools, multipart blockstates whose
  states the mod's Java sets, and compiled classes. There is no file to translate,
  so that behaviour has to be written by hand or by the agent.
- **A real choice.** A recipe over a tag with several members, or an armour
  trim. portkit won't pick for you.
- **`unowned`.** Files no converter claims yet. These are the best candidates
  for a new converter (see [the converter guide](converter-guide.md)).

`portkit report out/` turns a converted tree into a readable report, and
`portkit validate out/` re-runs the validator after you edit the packs by hand.

## Optional: let an agent work the residue

The agent only ever sees the residue, with the validator as a tool. Pick a
provider and a model, then add `--agent`:

```bash
export PORTKIT_LLM_PROVIDER=anthropic      # openai | anthropic | gemini | gemini_native
export PORTKIT_LLM_MODEL=<model>
export ANTHROPIC_API_KEY=...
portkit convert yourmod.jar out/ --agent --agent-max-cost 0.50
```

The README's agent section covers budgets, transcripts and `--repeat`. A group
the agent can't resolve cleanly is rolled back and stays in `unhandled.json`.

## When the output is wrong

Open an issue with the smallest slice of your mod that reproduces it. Better
still, shrink it into a fixture under `fixtures/` (see `fixtures/README.md`),
since that's how every fix in this repo starts.
