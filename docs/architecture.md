# Architecture

portkit has three parts, in this order of authority:

1. **A deterministic core** that converts everything with a definite Bedrock
   equivalent.
2. **A validator** that acts as the only judge of whether output is acceptable.
3. **A plain agent loop** that sees only what the core refused, and works
   against the validator.

Nothing downstream is allowed to overrule anything upstream. The agent can't
edit what the core produced and still count it as resolved, and nothing asks a
model whether output is good.

```
mod.jar ─▶ ingest ─▶ converters (per namespace) ─▶ write_tree ─▶ validate ─▶ .mcaddon
                          │                              ▲
                          └─ Unhandled ─▶ residue agent ─┘ (optional; tools: read_source,
                                                            write_output, validate)
```

## The pipeline (`portkit/pipeline.py`)

`convert(source, out_dir)`:

1. **Ingest** (`ingest.py`) stages a `.jar` or directory onto disk: `assets/`,
   `data/` and loader metadata. Compiled classes and nested jars become residue
   right away.
2. **Metadata** (`meta.py`) reads `fabric.mod.json`, `mods.toml` and the rest, for
   the pack name, version and the primary namespace.
3. **Converters** run once per namespace (`converters/__init__.py:convert_all`),
   and `merge_namespaces` folds the results. Output that lands on the same path
   twice is combined where Bedrock allows it (`languages.json`, `.lang`, texture
   indexes). Anything else is reported as a `namespace_collision`.
4. **Unowned files.** Any staged file that no converter `claim`ed becomes an
   `unowned` residue entry, grouped by directory. A file nobody opened is the
   one outcome the pipeline never allows silently.
5. **write_tree** (`pack.py`) splits output into behavior and resource packs by
   path prefix. It writes manifests (the behavior pack depends on the resource
   pack, never the reverse) and derives the engine floor from what was emitted.
6. **The agent** (optional) works the residue in the written tree.
7. **validate_tree** runs on the final tree. The `.mcaddon` is written only when
   it's clean.

## The core: converters as pure functions

Every converter is `SourceMod -> ConversionResult`, with no network, model, or
global state. A `ConversionResult` has four fields:

| field | meaning |
| --- | --- |
| `files` | output relpath → JSON-able value, `str` (text files like `.lang`), or `bytes` |
| `unhandled` | `Unhandled(source, kind, reason, count)`: refused, with the specific reason |
| `consumed` | every source file the converter looked at, converted or refused |
| `notes` | converted, but with a stated loss (a dropped count, a random variant pinned) |

The rule that shapes the whole codebase: **a converter only translates the
unambiguous.** When a mapping needs a guess (which tag member, which state Java
computes in code, which way an undocumented rotation leans), the converter
refuses with a reason precise enough that a human or the agent can act on it.
Residue isn't failure. It's the honest boundary of what has been worked out,
and every converter that shrinks it moves that boundary.

Where a fact can be settled without guessing, it's settled once and written
down. `docs/rotation-convention.md` is the model for that, and `portkit probe`
builds in-game probe packs for the questions only the game can answer.

## The oracle (`portkit/validate/`)

`validate_tree(tree) -> ValidationReport`, a list of findings, each with a path,
a rule name and a message:

- `rules.py`: structural rules per file type (manifests, recipe bodies,
  identifiers, required fields).
- `xrefs.py`: cross-file references (a recipe naming an item no pack defines, an
  icon missing from `item_texture.json`).
- `collisions.py`: two files claiming one identifier.

The validator is deterministic and fast, which is why the agent can call it in a
loop and why CI can gate on it. Making it stricter is always welcome, but a rule
must reflect what Bedrock actually does, cited from Mojang's docs or samples,
never a guess.

## The residue agent (`portkit/agent/`)

- `loop.py`: about 100 lines. Send messages, receive a tool call, run it, append
  the result, repeat until the model stops or a budget runs out.
- `tools.py`: `read_source`, `list_source`, `write_output` and `validate`, plus
  the system prompt.
- `residue.py`: groups `Unhandled` by `(kind, source)`, builds one task per group
  (the source content plus the exact refusal reason), and runs one session each.
  A group counts as resolved only if the session ends on its own, writes at least
  one file, and adds no validator error. Otherwise its writes are rolled back.
- `budget.py`: step, token and dollar ceilings with per-group accounting.
- `transcript.py`: record a run to JSONL and replay it offline. Replay checks
  every request against the recording, so an agent regression is an ordinary
  failing test (`fixtures/transcripts/`).
- Providers (`openai.py`, `anthropic.py`, `gemini.py`, `factory.py`) are stdlib
  HTTP clients. Adding one means implementing `complete(messages, tools) -> Message`.

### Why there is no graph framework

The control flow is one loop. Every decision about what the agent works on is
already made by the time the loop starts: the core decides what's residue, and
the validator decides what's resolved. A graph or orchestration framework would
add state machines, retries and abstractions around a problem with none of that
shape, and it would hide the one thing that matters: exactly what the model saw
and what it changed. A plain loop keeps every request recordable and replayable,
every provider swappable by one method, and the whole agent readable in a
sitting.

## The ratchet

`portkit eval` converts every fixture and compares coverage against
`fixtures/coverage-baseline.json`. CI fails if any fixture loses coverage or
converted files. Coverage only moves one way, and every step down has to show
up as a reviewed baseline diff.
