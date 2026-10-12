# portkit v2 skeleton

A from-scratch layout for the Java -> Bedrock converter. Three ideas:

1. **The deterministic core is a library, not a service.** Textures, recipes, lang
   files, sounds are schema-to-schema mapping. They run offline, with no API key,
   no Postgres, no Docker. `portkit convert <mod> <out>` works on a laptop with
   stdlib Python.

2. **The validator is a hard oracle, not another model.** `portkit.validate`
   checks generated packs against Bedrock's actual structural rules and returns a
   machine-readable report. Nothing in the loop asks an LLM whether the output is
   good.

3. **The agent is a plain loop.** `portkit.agent.loop` is ~100 lines: send
   messages, get a tool call, run it, append the result, repeat. It is given the
   validator as a tool so it iterates against real signal. Swap providers by
   implementing one method. No graph framework.

## Run it

```bash
pip install -e ".[dev]"
pytest -q                      # unit tests + golden-fixture parity
portkit convert fixtures/simple_block_mod/input /tmp/out
portkit validate /tmp/out
portkit eval                   # run every fixture, print a coverage table, fail if any fixture drops below fixtures/coverage-baseline.json
portkit eval --update-baseline # bank an improvement (or a deliberate step down) in the baseline
```

One step needs the network, once: `portkit reference fetch` caches reference
data that isn't in the repo under `~/.cache/portkit/reference/`, each piece
checked against a pinned sha256:

- Bedrock's vanilla sound list (Mojang's data). With it, a mod sound that names
  vanilla audio Bedrock also has (`random/bow`) is kept; without it, those
  references are dropped with a note saying to run the fetch.
- The item tags Forge 1.20.1, NeoForge 1.21.1, Fabric's convention tags and
  vanilla define (#160). A mod's `c:`/`forge:`/`neoforge:`/`minecraft:` tag file
  is only its own share; the loader and vanilla add the rest
  (`forge:glass/colorless` is `minecraft:glass` plus whatever the mod adds). The
  data for the loader and game version the jar declares completes those tags;
  without it, recipes using them stay residue rather than being narrowed.
  `portkit reference fetch --mod your.jar` fetches only what that jar needs.
- A handful of vanilla block model templates (Mojang's data): stairs, slabs,
  walls, fences and the cube shapes. A mod's stairs model only names
  `minecraft:block/stairs`; the boxes are vanilla's. With them, stairs, slabs,
  walls and turned pillars convert; without them they stay residue, saying to
  run the fetch.

Tests and the fixtures don't need it.

## Where the LLM goes

Nowhere, until a converter says it cannot handle something. Each converter
returns `Unhandled` items with the source file and a reason. Those, and only
those, get handed to the agent loop with the validator attached. If the
deterministic converters grow to cover a case, the agent stops seeing it. That
is the direction you want the ratchet to run.

Pick a provider with `make_client()` from `portkit.agent`. It reads explicit
arguments, then a config mapping, then the environment:

```bash
export PORTKIT_LLM_PROVIDER=anthropic   # or openai, or gemini
export PORTKIT_LLM_MODEL=<model name>
export ANTHROPIC_API_KEY=...            # or OPENAI_API_KEY, or GEMINI_API_KEY
export PORTKIT_LLM_BASE_URL=...         # optional: OpenRouter, a local server, a gateway (openai/anthropic only;
                                        # gemini keeps Google's endpoint unless PORTKIT_LLM_GEMINI_BASE_URL is set)
export PORTKIT_LLM_TEMPERATURE=...      # optional: sampling temperature
export PORTKIT_LLM_MAX_RETRIES=2        # optional: retries on 429/5xx/timeouts (default 2; 0 = off)
```

Transient provider failures are retried inside the client: HTTP 429, 500, 502,
503, 504 and 529, timeouts and dropped connections, with exponential backoff
that honours `Retry-After`; and, once, an empty reply with
`finish_reason=error`. A retry is invisible to transcripts (same request, only
the final reply recorded), and tokens billed for a discarded empty reply still
count toward spend.

Both clients are stdlib HTTP (no SDK dependency) and translate tool calls both
ways, so the same `AgentSession` runs against either one unchanged.

**Recommended default: `deepseek/deepseek-v4.1-flash` through OpenRouter.** In
the #86 sweep (6 models × 3 runs on `fixtures/agent_mod`, 12 steps per group,
$0.50 per run) it tied Claude Sonnet 5.5 and Opus 5.5 for the most groups
resolved, 6 of 9, at about a sixth of Sonnet's cost and a tenth of Opus's
($0.094 for all three runs). Gemini 3.8 Flash through the same OpenRouter
setup resolved none.

```bash
export PORTKIT_LLM_PROVIDER=openai
export PORTKIT_LLM_BASE_URL=https://openrouter.ai/api/v1
export PORTKIT_LLM_MODEL=deepseek/deepseek-v4.1-flash
export OPENAI_API_KEY=...               # your OpenRouter key
export PORTKIT_LLM_INPUT_PRICE=... PORTKIT_LLM_OUTPUT_PRICE=...   # from the model's OpenRouter page, for --agent-max-cost
```

A sweep is a sample, not a guarantee: rerun `--repeat 3` on `fixtures/agent_mod`
when a new model or a prompt change might move the ranking (see
docs/decisions.md).

`gemini` is the OpenAI client aimed at Google's OpenAI-compatible endpoint, so
no base URL is needed. A cheap setup for trying the agent (note that Gemini 3.8
Flash went 0 of 9 through OpenRouter in #86, looping until the step ceiling; it
has not been re-swept through this endpoint):

```bash
export PORTKIT_LLM_PROVIDER=gemini
export PORTKIT_LLM_MODEL=gemini-3.8-flash
export GEMINI_API_KEY=...               # from Google AI Studio
export PORTKIT_LLM_INPUT_PRICE=0.75 PORTKIT_LLM_OUTPUT_PRICE=3.75   # list price through 2026-12-31
```

Gemini 3 attaches a thought signature to each tool call and refuses the next
turn without it. The OpenAI client keeps any extra fields on a tool call and
sends them back unchanged, and transcripts record them, so replay still matches.
Through OpenRouter the reasoning (Gemini's signatures included) comes as a
message-level `reasoning_details` array instead; the client keeps that too and
echoes it on the next request, as OpenRouter asks.

Then send the residue through it:

```bash
portkit convert path/to/mod.jar /tmp/out --agent   # --agent-max-steps N per group, default 12
```

`portkit.agent.residue` groups the `Unhandled` items by kind and source file and
runs one session per group. Each task carries the source content and the exact
reason the deterministic path refused it. A group counts as resolved only when
its session ends on its own, it wrote at least one file, and the validator finds
no new error; a group that breaks the tree is rolled back. A session that writes
nothing and says why is `declined`: the right answer when the Java behaviour has
no faithful Bedrock form, and still residue. One that stops without a reason is
`unresolved`. So is a group whose
recipes name an item or tag that exists nowhere: every item must be defined by
the pack or the source mod or be vanilla, and every non-vanilla tag must be one
a pack item declares in `minecraft:tags` (Bedrock does not read Java tag files).
The `validate` tool reports these as `agent.unresolved_ref` so the model can fix
them, and the group's `unresolved_refs` lists any left. The same goes for
gameplay numbers on an item the agent writes (damage, durability, mining speed,
armor, food, cooldowns, enchantability, fuel): each must be a value the source
mod states for that item, never a guess. An unknown stat is omitted and the
agent's final note says so; one left in is reported as `agent.fabricated_stat`
and rolls the group back, listed in `fabricated_stats`. Blocks get the same
rule for their properties (light emission and dampening, friction, seconds to
destroy, explosion resistance, flammability) and for `minecraft:map_color`:
Java sets all of these in code, so unless the source states the value for that
block (a stated hardness x 1.5 counts for seconds to destroy), the agent must
leave the component out. Writing Bedrock's own default (light 0, dampening 15,
friction 0.4) claims nothing and passes. Every namespaced id in
a file the agent writes must be `minecraft:`, the conversion's namespace or one
the mod has an `assets/` or `data/` folder for (an id the source itself names,
or one the file already held, is fine too); anything else, such as an `sd:`
typo for `storagedrawers:`, is `agent.unknown_namespace` and rolls the group
back, listed in `unknown_namespaces`. A block the agent writes whose Java
blockstate exists may only declare and test (`q.block_state(...)`) the states
that blockstate keys on, with the values it lists, spelled as Java spells them:
`facing` as `0..3` when Java says `north`/`east`/... is `agent.invented_state`
and rolls the group back, listed in `invented_states`. Bedrock's own trait
states (`minecraft:cardinal_direction`, `minecraft:block_face`, ...), which the
deterministic converter maps Java's facing and axis onto, are accepted with
their own values. The same goes for `minecraft:recipe_smithing_trim`: every
`template` and `addition` slot must name a vanilla `minecraft:` item or tag.
A Bedrock add-on can't apply a mod's trim pattern or material, so a trim
slot naming any other id applies nothing in game; a written recipe there is
`agent.unresolved_trim` and rolls the group back, listed in
`unresolved_trims`. An item the agent defines in the mod's or the conversion's
namespace must be one the Java source registers (a blockstate, a lang key, an
item a recipe, item tag or loot table names), under the converter's own id
mapping; an item model file alone is not a registration. A per-variant item
such as `storagedrawers:basicdrawers_full2_jungle`, where Java registers one
`basicdrawers` and keeps the variant in block state or NBT, is
`agent.unknown_item` (the finding names the closest real Java id) and rolls the
group back, listed in `unknown_items`. The deterministic item converter holds
itself to the same test (#158): it writes no item for an item model alone (a
1.12 per-metadata model or a modern override model), explains the skip in the
summary's `notes`, and leaves the variant's texture to ship like any other
texture. Anything unresolved
stays in `unhandled.json`, and the summary's `agent` block says what each group
did. Its `status` is `complete` (every group resolved), `partial` or `failed`
(none did). That is separate from `valid` and from the exit code, which are
about the pack: a run whose every group was rolled back leaves a valid pack and
a `failed` agent run. Bytecode, nested jars and namespace collisions are skipped, since no tool
can read them.

Budgets: `--agent-max-steps` bounds each group's session, and the model sees it:
every tool result says how many steps are left, and with three or fewer left and
nothing written yet it is told to write its best supported answer or decline.
Rewriting a file without validating in between is pointed out too. `--agent-max-tokens`
and `--agent-max-cost` bound the whole run, shared across groups. The run stops
before the next model call once a ceiling is reached, keeps whatever it wrote
that still validates (the group shows as `partial`, its residue stands), and
skips the remaining groups with the ceiling named. Spend is reported per group
and in total. Dollars come from your prices, never from the provider:

```bash
export PORTKIT_LLM_INPUT_PRICE=3     # USD per million input tokens
export PORTKIT_LLM_OUTPUT_PRICE=15   # USD per million output tokens
portkit convert mod.jar /tmp/out --agent --agent-max-tokens 200000 --agent-max-cost 0.50
```

Transcripts: `--agent-record run.jsonl` writes every completion of a run to a
JSON Lines transcript; `--agent-replay run.jsonl` runs the agent from one with
no provider, key or network. Replay checks each request against the recording
and fails at the first step that differs, so an agent regression is an ordinary
failing test. Committed transcripts live in `fixtures/transcripts/` and replay
in CI (`tests/test_transcripts.py`).

Variance: one run is one sample. `--repeat 3` converts into `OUT/run-1..3`,
records `run-1..3.jsonl` when `--agent-record run.jsonl` is set, and prints the
mean, stdev and range of resolved and declined groups, steps, tokens and cost,
how many runs resolved or declined each group, and each run's `agent_status`
beside `valid`. The same numbers land in `OUT/repeat-summary.json`.

`--agent-max-cost` caps each run; `--agent-max-total-cost` caps the sweep. Each
run's dollar ceiling is tightened to what the sweep has left, and once it is
spent no further run starts: those runs are listed under `skipped_runs` in
`repeat-summary.json`, beside `total_cost_usd`.

```bash
portkit convert fixtures/agent_mod/input /tmp/var --agent --repeat 3 \
  --agent-max-cost 0.25 --agent-max-total-cost 0.50 --agent-record /tmp/var/run.jsonl
```

## Comparing providers

`portkit eval --agent` runs the fixture residue (every fixture with
`expect_unhandled > 0`, or `--fixture NAME`) through each provider and model
under the same budgets, and prints one row per target:

```bash
portkit eval --agent --target anthropic:<model> --target gemini_native:<model> --json /tmp/matrix.json
portkit eval --agent --agent-replay fixtures/transcripts   # the offline row CI replays
```

A target can name its own endpoint with `@BASE_URL`, so one run can mix
gateways without touching the environment:

```bash
portkit eval --agent --fixture agent_mod \
  --target openai:anthropic/claude-haiku-4.5@https://openrouter.ai/api/v1 \
  --target gemini_native:gemini-flash-latest
```

Each task scores **pass** (resolved: the validator is the only judge), **fail**,
or **unscored** (a provider error, or a ceiling hit before the validator ran).
Unscored tasks stay out of the pass rate. **Format failures** count tool calls
that don't fit the toolbox, such as an unknown tool name or bad arguments. A spike
there points at the provider's tool-call translation, not the model. Each row
also reports steps, tool calls per success, tokens, and stop reasons.

## Real mods

The hand-built fixtures pin behaviour; the real-mod corpus shows where it breaks.
Real mods are pinned by Modrinth version and sha512 in `fixtures/real/mods.toml`.
They're downloaded, never committed:

```bash
portkit corpus fetch
portkit reference fetch
portkit eval --corpus
```

See [fixtures/real/README.md](fixtures/real/README.md). A nightly workflow runs
the corpus against its own baseline.

`portkit eval --corpus --mct` adds Mojang's own validator (`mct validate` from
`@minecraft/creator-tools`, Node 22+) as a second, report-only oracle: its
findings are summarised by severity and rule, and written to `--json PATH`.
It's skipped with a note when `mct` isn't installed.

## Docs

- [Getting started](docs/getting-started.md): convert your own mod and read the residue.
- [Architecture](docs/architecture.md): the deterministic core, the oracle, the residue loop, and why there's no graph framework.
- [Writing a converter](docs/converter-guide.md): a worked example, end to end.
- [Decision log](docs/decisions.md): the design decisions behind the converters' policies, and why. If your PR makes one, add an entry there.

## Layout

```
src/portkit/
  converters/      one module per content type, all pure functions
  validate/        the oracle: structural checks, returns ValidationReport
  agent/           plain tool loop + tool definitions + fake client for tests
  pack.py          assemble behavior/resource packs into an .mcaddon
  cli.py
fixtures/          golden corpus: input/ java mod, expected/ bedrock output
tests/             unit tests + fixture parity harness
```
