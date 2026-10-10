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
```

Both clients are stdlib HTTP (no SDK dependency) and translate tool calls both
ways, so the same `AgentSession` runs against either one unchanged.

`gemini` is the OpenAI client aimed at Google's OpenAI-compatible endpoint, so
no base URL is needed. A cheap setup for trying the agent:

```bash
export PORTKIT_LLM_PROVIDER=gemini
export PORTKIT_LLM_MODEL=gemini-3.8-flash
export GEMINI_API_KEY=...               # from Google AI Studio
export PORTKIT_LLM_INPUT_PRICE=0.75 PORTKIT_LLM_OUTPUT_PRICE=3.75   # list price through 2026-12-31
```

Gemini 3 attaches a thought signature to each tool call and refuses the next
turn without it. The OpenAI client keeps any extra fields on a tool call and
sends them back unchanged, and transcripts record them, so replay still matches.

Then send the residue through it:

```bash
portkit convert path/to/mod.jar /tmp/out --agent   # --agent-max-steps N per group, default 12
```

`portkit.agent.residue` groups the `Unhandled` items by kind and source file and
runs one session per group. Each task carries the source content and the exact
reason the deterministic path refused it. A group counts as resolved only when
its session ends on its own, it wrote at least one file, and the validator finds
no new error; a group that breaks the tree is rolled back. Anything unresolved
stays in `unhandled.json`, and the summary's `agent` block says what each group
did. Bytecode, nested jars and namespace collisions are skipped, since no tool
can read them.

Budgets: `--agent-max-steps` bounds each group's session; `--agent-max-tokens`
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
mean, stdev and range of resolved groups, steps, tokens and cost, plus how many
runs resolved each group. The same numbers land in `OUT/repeat-summary.json`.

```bash
portkit convert fixtures/agent_mod/input /tmp/var --agent --repeat 3 \
  --agent-max-cost 0.25 --agent-record /tmp/var/run.jsonl
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
portkit eval --corpus
```

See [fixtures/real/README.md](fixtures/real/README.md). A nightly workflow runs
the corpus against its own baseline.

## Docs

- [Getting started](docs/getting-started.md): convert your own mod and read the residue.
- [Architecture](docs/architecture.md): the deterministic core, the oracle, the residue loop, and why there's no graph framework.
- [Writing a converter](docs/converter-guide.md): a worked example, end to end.

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
