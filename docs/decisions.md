# Decision log

The design decisions that shape portkit's output, and why they were made. Read
this before changing a converter's policy; the reasoning behind a rule usually
lives in an issue thread, and this page is the index into those threads.

**When a PR makes a design decision** (a policy for what the converter emits or
refuses, a precedence rule, what is or isn't stored in the repo), add an entry
here in the same PR.

## Format

Newest first. One entry per decision:

```
## YYYY-MM-DD: the decision, as one line

- **Decision:** what we do now.
- **Why:** the reason that settled it.
- **Rejected:** the alternatives considered, and why not.
- **Links:** issues and PRs.
```

The date is when the decision was settled (usually the merge date of the PR
that implemented it). If a later decision replaces an entry, add the new one
on top and mark the old one "superseded by" with its date; don't rewrite it.

---

## 2026-10-12: agent-written block properties and map colours need a source

- **Decision:** the fabricated-stat guard (#135) now covers agent-written
  blocks, over base components and every permutation's: `light_emission`,
  `light_dampening`, `friction`, `destructible_by_mining.seconds_to_destroy`,
  `destructible_by_explosion.explosion_resistance`, `flammable`'s two
  modifiers (and the legacy bare `destroy_time`, `explosion_resistance`,
  `block_light_emission`, `block_light_filter`) must be numbers the source
  states for that block, by the same file rule as item stats (outside
  `assets/` and recipe-like data, in a file that names the block). A
  `minecraft:map_color` (hex, `[r, g, b]` or `{"color": ...}`) must appear in
  such a file as hex or as its decimal RGB integer. `seconds_to_destroy` may
  also be a stated hardness x 1.5. Bedrock's omitted-component defaults (light
  0, dampening 15, friction 0.4) and `true`/`false` forms pass. Otherwise
  `agent.fabricated_stat` and rollback, as for items. The system prompt and
  task prompt's no-guessing line names block properties and map colour; the
  `residue_mod` transcript was re-recorded with its replies kept.
- **Why:** GLM 5.3 wrote `minecraft:map_color` on storage drawers and
  waystones blocks; Java sets map colour, hardness, blast resistance, light and
  friction in code, so the converter never has them (see the converters/blocks.py
  docstring) and the agent can't either. No deterministic output in the 21
  fixtures or 10 corpus mods carries any of these components.
- **Rejected:** deriving a map colour from the texture's average (Java's map
  colour is chosen in code, not computed from the texture); stripping the
  component instead of rolling back (same reasoning as #135); checking boolean
  forms such as `flammable: true` (no number to trace; a separate policy if
  wanted).
- **Links:** #152, #86 ([real-mod report](https://github.com/anchapin/portkit-v2/issues/86#issuecomment-6122960840)), #135, #147, #149.

## 2026-10-12: agent-written block states must be the Java blockstate's

- **Decision:** when a residue session writes a `minecraft:block` whose Java
  blockstate exists (`assets/<ns>/blockstates/<name>.json`, matched by id),
  every custom state in `description.states` and every
  `q.block_state('<custom>')` in the file must be a state that blockstate keys
  on (variant keys, multipart `when` incl. `OR`/`AND`/`a|b`, Forge
  `forge_marker` variants), and every value (declared, or compared with
  `==`/`!=`) one it lists, compared as Java spells it. Integers pass only where
  Java uses integers; a boolean state accepts both `true` and `false` even if a
  multipart only tests one. Vanilla trait states (`minecraft:cardinal_direction`,
  `block_face`, `facing_direction`, `vertical_half`, `connection_*`) are
  accepted with their own value sets, other `minecraft:` states on faith.
  Otherwise `validate` reports `agent.invented_state` and the group rolls back,
  listed in `invented_states`.
- **Why:** on real-mod residue GLM 5.3 wrote `facing` as an invented `0/1/2`
  enum and state values the Java blockstate doesn't have; no guard read block
  states. Trait states are how `converters/blocks.py` already maps facing,
  axis and connections, so the guard accepts exactly that mapping. A
  synthetic faithful block for each of the 1,525 stateful blockstates in the
  10 corpus mods (plus the fixtures) passes, as does every deterministic block.
- **Rejected:** requiring trait states to correspond to a Java state (a
  separate question: a trait with no Java basis is an addition, not an
  encoding); guarding omitted states (waystones portstones' WATERLOGGED/ORIGIN
  were dropped, which loses fidelity but invents nothing); matching per-variant
  blocks (`basicdrawers_oak`) to a shorter blockstate by prefix (could compare
  a slab against its full block's states).
- **Links:** #149, #86 ([real-mod report](https://github.com/anchapin/portkit-v2/issues/86#issuecomment-6122960840)), #147.

## 2026-10-12: agent-written ids must be in a namespace the mod has

- **Decision:** every namespaced id in a JSON or `.lang` file a residue session
  writes (string values, object keys, ids quoted in Molang, `tag:` components,
  `tile.`/`item.` lang keys) must be `minecraft`, the conversion's namespace,
  or a namespace the mod has a folder for under `assets/` or `data/`. An exact
  id the source names in an item position (`source_items`) and an id the file
  held before the session are exempt. Otherwise `validate` reports
  `agent.unknown_namespace` (naming the id and the valid namespaces) and a
  group that ends with one is rolled back, listed in `unknown_namespaces`.
  A recipe id the #132 check already reports is not reported twice.
- **Why:** on real-mod residue GLM 5.3 wrote `sd:` ids for storage drawers
  (namespace `storagedrawers`) and passed every guard; the #132 check only
  reads recipes. Run against every file the deterministic converter emits for
  the 21 fixtures and 10 corpus mods, the check flags nothing in the packs.
- **Rejected:** checking that each id *exists* (needs a full vanilla list,
  which is Mojang data, and the agent may legitimately define new ids in the
  mod's namespace); only checking recipes and item references (the typos were
  in block identifiers and loot/state names too); flagging any non-vanilla
  namespace in the source's own data (compat recipes name other mods' items).
- **Links:** #147, #86 ([real-mod report](https://github.com/anchapin/portkit-v2/issues/86#issuecomment-6122960840)), #132.

## 2026-10-11: `--agent-max-total-cost` caps a `--repeat` sweep

- **Decision:** `--agent-max-total-cost USD` bounds the dollars spent across
  all `--repeat` runs. Before each run, its ceiling becomes the smaller of
  `--agent-max-cost` and what the sweep has left; once nothing is left, the
  remaining runs don't start and are listed in `repeat-summary.json` under
  `skipped_runs` (with `max_total_cost_usd`, `total_cost_usd`,
  `runs_requested`). Without `--repeat` it acts as a run ceiling. It needs the
  same prices as `--agent-max-cost`.
- **Why:** `--agent-max-cost` is per run, so a three-run sweep could spend three
  times it; Alex's Gemini 3.8 Flash `--repeat 3` spent $0.544 with nothing
  landing. Tightening the last run to the remainder keeps the overshoot to the
  one completion in flight, as for every other ceiling.
- **Rejected:** Only stopping between runs (the last run could still spend a
  full per-run ceiling past the cap); changing `--agent-max-cost` to mean the
  sweep (existing commands would silently change meaning).
- **Links:** #143.

## 2026-10-11: write_output takes the file as JSON text, for every provider

- **Decision:** `write_output` advertises `path` and `content_json` (a string:
  the whole file as JSON text), both required, for every provider. No tool
  schema has a free-form object any more (a test enforces it). A parse error
  comes back as a tool error with `line`, `column` and the text `near` it;
  JSON text that isn't an object is refused. The old `content` object is still
  taken, though no longer advertised, and is not counted as a format failure
  (recorded transcripts and models that ignore the schema send it); exactly
  one of the two is required. A file with a bare `minecraft` key gets a note
  that it is usually a `minecraft:...` key cut at the colon.
- **Why:** Gemini 3.8 Flash, via OpenRouter, sent only stubs
  (`{"format_version": ..., "minecraft": null | "item" | true}`) for
  `content: {"type": "object"}`. Gemini's function declarations take "a select
  subset of an OpenAPI 3.0 schema object" with no `additionalProperties`
  (https://ai.google.dev/api/generate-content#v1beta.Schema); free-form objects
  have been rejected or ignored, and the workaround Google's forum gives is a
  JSON string (https://discuss.ai.google.dev/t/gemini-api-2-0-flash-exp-requires-non-empty-properties-for-open-ended-object-parameters/64086). One tool surface for all
  providers keeps the eval matrix comparing like with like.
- **Rejected:** Advertising both params (Gemini would still see, and could
  still pick, the free-form object; OpenAPI-subset `required` can't say
  "exactly one"); a Gemini-only schema (two tool surfaces, and OpenRouter model
  names don't reliably say which backend serves them); sending
  `parametersJsonSchema` on the native endpoint (doesn't reach the OpenRouter
  path, and `additionalProperties` there has drawn `MALFORMED_FUNCTION_CALL`).
- **Links:** #142, #141.

## 2026-10-11: A file that is not the document its folder holds is an error

- **Decision:** `doc.unknown_shape` (error) for a `.json` file in a document
  folder with none of that folder's top-level document keys, or with one whose
  body is not an object: BP `items/` (`minecraft:item`), `entities/`,
  `spawn_rules/`, `biomes/`, `feature_rules/`, `dimensions/`, `animations/`,
  `animation_controllers/`; RP `items/`, `entity/` (`minecraft:client_entity`),
  `attachables/`, `fogs/`, `particles/` (`particle_effect`), `animations/`,
  `animation_controllers/`, `render_controllers/`. Also for a JSON `null` file
  anywhere, and a non-object top level in `blocks/` and `loot_tables/`
  (`blocks/` and `recipes/` keep their own body checks). Folders not listed are
  not shape-checked. A bare `minecraft` key gets a hint that it is usually a
  `minecraft:...` key cut at the colon.
- **Why:** Gemini 3.8 Flash's stubs (`{"format_version": ..., "minecraft":
  "item"}`) passed as `valid: true` and scored `partial`; Bedrock loads them as
  nothing. As an error it rolls the agent group back (the residue agent already
  rolls back any group that adds validator errors, and its note now names them).
  No converter output in the fixtures or the 10-mod corpus trips it.
- **Rejected:** A warning (the run would still report a stub as work done);
  checking every folder (unknown folders would false-positive).
- **Links:** #141.

## 2026-10-11: The agent sees its step budget, and is nudged before it runs out

- **Decision:** Every tool result the loop hands back carries
  `steps_left: "steps left: N of M"`. While 0 < N <= 3 and the session has not
  written a file successfully, it also carries a `nudge` to write the best
  supported answer and validate it, or decline in one sentence. A
  `write_output` to a path already written in the session with no `validate`
  since gets a `note` saying so. The system prompt says steps are limited and
  shown. All of it depends only on the step count and the toolbox's own write
  record, so replays stay exact.
- **Why:** In Alex's Gemini 3.8 Flash spot-check steel_sword hit the 12-step
  ceiling in 3/3 runs on research alone (no identical-call loops), and
  alloy_block rewrote one file five times without validating, then rolled
  back. The model had no way to know how close the ceiling was.
- **Rejected:** A separate system message per step (breaks Anthropic's strict
  role alternation and doubles the turns); cutting research tools off near the
  end (a model mid-fix may still need a lookup); forcing a validate after each
  write (more steps, and a model may write two files before validating on
  purpose); a token or cost countdown (only steps are per session).
- **Links:** #139.

## 2026-10-11: Provider clients retry transient failures inside complete()

- **Decision:** All three clients send through `http.complete_with_retry`:
  HTTP 429/500/502/503/504/529, timeouts and connection failures (and an
  OpenRouter 200 whose `error` body carries one of those codes) are retried up
  to 2 times with exponential backoff (1 s, 2 s, capped at 20 s), honouring
  `Retry-After` up to 60 s. An empty reply with `finish_reason=error` is
  retried once. `PORTKIT_LLM_MAX_RETRIES` overrides the count; 0 turns all of
  it off. Tokens billed for a discarded empty reply are added to the final
  reply's usage.
- **Why:** In Alex's Gemini 3.8 Flash spot-check an OpenRouter 504 ended a
  group as `error` and an empty `finish_reason=error` reply (175 billed output
  tokens) ended another; both are transient. Retrying inside one `complete()`
  call keeps transcripts exact: the request digest is unchanged and only the
  final reply is recorded, so replays and spend replay as before.
- **Rejected:** Retrying in the agent loop (a retried step would show in the
  transcript and the step count); recording every attempt (replay would need
  to know about failures); retrying 4xx client errors or any empty reply (a
  `length` cutoff or a refusal won't change on resend).
- **Links:** #137.

## 2026-10-11: Agent-written items may only carry gameplay numbers the source states

- **Decision:** A stat on an item the residue agent writes (`minecraft:damage`,
  `durability.max_durability`, `digger` speeds, `wearable`/`armor`
  protection, `food` nutrition and saturation, `cooldown`, `enchantable.value`,
  `fuel`, use duration) must equal a number in a source-mod text file that
  names the item, outside `assets/` and outside recipes, tags, advancements and
  loot tables. One derivation: Bedrock damage n is supported by a Java
  `attack_damage` of n - 1. Otherwise `validate` reports
  `agent.fabricated_stat`, and if any remain when the session ends the group is
  **rolled back** (not stripped), listed in `fabricated_stats` and in the note.
  The prompt says unknown stats are omitted, not guessed, and named in the
  final message. Descriptive components (icon, name, `hand_equipped`,
  `max_stack_size`, tags, `repairable`, the enchantable slot) are not checked.
- **Why:** After #132, DeepSeek wrote agent_mod's steel sword with damage 5,
  durability 250 and an enchantability value; the fixture states no stats at
  all. That breaks the no-fabrication policy (2026-10-09), and the recipe ref
  check doesn't look at items.
- **Rejected:** Stripping the stats and keeping the item (rewrites the agent's
  file after the fact with no validate pass over the result, and the existing
  ref check already rolls back, so one rule is simpler); counting numbers from
  `assets/` (item models are full of display rotations and scales that would
  excuse an invented stat) or from files that don't name the item (a
  per-material stats file is missed; that errs toward omitting, never
  inventing); checking repair amounts and block hardness (out of scope here).
- **Links:** #135, #87, #86.

## 2026-10-11: OpenRouter's reasoning_details go back to the model unmodified

- **Decision:** The OpenAI-style client keeps a reply's message-level
  `reasoning_details` on `Message.extra` and sends it back on that assistant
  turn in later requests; transcripts record it and it is part of the request
  digest. The plain-text `reasoning` field is not echoed.
- **Why:** OpenRouter returns reasoning there (for Gemini, the encrypted thought
  signatures) and documents passing it back unmodified so the model can
  continue its reasoning across tool calls. We dropped it, which is one
  candidate explanation for Gemini 3.8 Flash looping to the step ceiling on
  every group in #86 (not proven; needs a live re-run).
- **Rejected:** Echoing every unknown message field (could send providers
  fields they reject); echoing `reasoning` text as well (redundant with the
  details, and bigger).
- **Links:** #86; https://openrouter.ai/docs/guides/best-practices/reasoning-tokens

## 2026-10-11: The default agent model is deepseek/deepseek-v4.1-flash via OpenRouter

- **Decision:** Recommend `deepseek/deepseek-v4.1-flash` through OpenRouter
  (`PORTKIT_LLM_PROVIDER=openai`, base URL `https://openrouter.ai/api/v1`) as
  the default for the residue agent, in the README's agent section.
- **Why:** Alex's #86 sweep (6 models × 3 runs on `fixtures/agent_mod`, develop
  @0252190, 12 steps per group, $0.50 per run, after a fabrication check):
  DeepSeek V4.1 Flash 6/9 for $0.094, Claude Sonnet 5.5 6/9 for $0.574, Claude
  Opus 5.5 6/9 for $1.046, GPT-6.1 Sol 4/9 for $0.353, Qwen 3.8 Max Prime 4/9
  for $1.509 (one fabricated ingredient; hit the cost ceiling on steel_trim
  every run), Gemini 3.8 Flash 0/9 for $0.188 (step ceiling on every group).
  Same top score as the Claude models at a fraction of the cost. steel_trim
  was 0/3 for every model, which is the expected answer (see the next entry).
- **Rejected:** Sonnet or Opus as default (no more groups resolved, 6–11× the
  cost); Gemini 3.8 Flash, the README's earlier "cheap setup" (0/9 via
  OpenRouter).
- **Links:** #86.

## 2026-10-11: "Declined" is its own outcome, and agent status is separate from pack validity

- **Decision:** A residue session that ends on its own having written nothing
  but saying why is `declined`, not `unresolved`; it stays residue and scores
  as a fail in the eval matrix, but is counted separately everywhere
  (summary, `--repeat` summary, matrix rows). The agent run gets its own
  `status` (`complete` | `partial` | `failed`), and the `--repeat` per-run
  row's old `ok` (which was pack validity) is now `valid`, beside
  `agent_status`. The exit code stays about the pack.
- **Why:** In #86 Gemini Flash rolled back every group and its runs still said
  `ok: true`, and steel_trim went 0/3 for every model when writing nothing is
  the answer the task asks for (a mod item can't be a Bedrock trim material,
  and the fixture ships no trim_material even for Java). Both read as the
  wrong thing.
- **Rejected:** Scoring a decline as a pass (the harness can't tell a correct
  decline from a lazy one, so it stays a fail and is shown); failing the exit
  code when the agent resolves nothing (the pack is still valid and
  installable; scripts gate on `agent.status` instead).
- **Links:** #86.

## 2026-10-11: Agent-written recipes may only name items and tags that exist

- **Decision:** In the residue agent, every item a recipe written in the
  session names must be defined by the output pack, defined or named as an item
  by the source mod, or be a `minecraft:` id; every non-vanilla tag must be
  declared by a pack item (`minecraft:tags`) or block (`tag:` component). An
  unresolved reference is an error in the `validate` tool's answer
  (`agent.unresolved_ref`) and rolls the group back, listed in its
  `unresolved_refs`. Vanilla ids and tags are taken on faith.
- **Why:** In the #86 sweep a model wrote `examplemod:alloy_ingots` (the Java
  tag's name) as an ingredient and the group counted as resolved, because the
  validator's `xref.item` only warns. A recipe that matches nothing is a silent
  no-op in game.
- **Rejected:** Promoting `xref.item` to an error for all output (the
  deterministic path leaves undeclared ids on purpose when a definition was
  refused); checking vanilla names against a list (a full item list is Mojang
  data we don't vendor, and the reference's tag list is partial, so real names
  would be rejected).
- **Links:** #86.

## 2026-10-11: Tinkers tool icons are pre-baked from Tinkers' own preset rule (route A)

- **Decision:** For Tinkers' Construct, portkit composites one icon per tool
  per visible material, following the rule Tinkers uses for its creative tab
  (`ToolBuildHandler.addVariants`), read entirely from the jar's JSON. The 21
  materials that load only when another mod is present are left out, with a
  note.
- **Why:** Bedrock's `minecraft:icon` takes a single texture; nothing composes
  layers for the inventory UI. Pre-baking is deterministic and data-driven.
- **Rejected:** Route B, layering part sprites at runtime with render
  controllers or attachables: it can't produce inventory icons and still needs
  one Bedrock item per tool/material combination. Possible later for held
  models only.
- **Links:** #128, #122, PR #129 (under review).

## 2026-10-11: Keep Tinkers' part × material textures instead of dropping them

- **Decision:** The ~11.7k shipped `textures/item/tool/**` sprites keep
  converting, even though only 160 were referenced by a converted item, and
  the work is to make them useful (#128) rather than to prune them.
- **Why:** The goal is maximum coverage of what the mod ships (Alex,
  2026-10-11). PACKFILECOUNT is a Marketplace guideline, not a load failure.
- **Rejected:** Shipping only referenced textures and reporting the rest as
  residue: it shrinks the pack, but discards real assets and changes coverage
  accounting.
- **Links:** #122, #128.

## 2026-10-11: Mojang/EULA material is fetched on demand, not vendored

- **Decision:** Data derived from Mojang/bedrock-samples ((c) Mojang AB, all
  rights reserved) is not stored in the repo or the wheel. The Bedrock vanilla
  sound list is downloaded by `portkit reference fetch` at a pinned commit,
  checked against a pinned sha256, and cached. Without the cache, vanilla
  sound refs are dropped with a note saying to run the fetch. The one
  exception is the few-hundred-byte format examples in
  `agent/reference/bedrock_reference.json` (see its `NOTICE.md`); revisit those
  before publishing to PyPI (#24).
- **Why:** Mojang's samples are all-rights-reserved under the Minecraft EULA;
  MicrosoftDocs material (CC-BY-4.0 / MIT) can ship with attribution.
- **Rejected:** Vendoring the derived list (what #121 first did).
- **Links:** #124 (PR #125), #114 (PR #119), #121.

## 2026-10-10: Missing sounds are dropped with a note; vanilla refs are kept only if Bedrock has the path

- **Decision:** `sound_definitions.json` never names audio the player won't
  have. An un-namespaced or `minecraft:` sound is vanilla, kept only when
  Bedrock's vanilla pack has a file at the same path. Mod audio the jar doesn't
  ship is dropped. Dropping is per sound, with a note; an event left with no
  sound becomes residue.
- **Why:** A dangling reference is a silent sound in game, and Java→Bedrock
  vanilla sound paths have no reliable mapping table.
- **Rejected:** Guessing a Java→Bedrock path mapping; treating bare names as
  the mod's own files (the old behaviour).
- **Links:** #116 (PR #121).

## 2026-10-10: Long pack paths are shortened deterministically

- **Decision:** Any pack path over 100 characters or 9 segments (pack-relative,
  as `mct` measures) is renamed: keep the directory and as much of the leaf as
  fits, then `_<8 hex of sha256(original path)>`. References in the texture,
  flipbook and sound indexes move with the file; index keys don't change. The
  validator errors on any path over the limit.
- **Why:** Long paths may not load on consoles and mobile. Same mod in, same
  names out.
- **Rejected:** Leaving them (mct PATHLENGTH error); non-deterministic names.
- **Links:** #117 (PR #123).

## 2026-10-10: Real mods are downloaded and pinned, never committed

- **Decision:** Real-mod jars live in `fixtures/real/mods.toml`, pinned by
  Modrinth version id, URL and sha512, fetched into a content-addressed cache.
  The hand-built fixtures stay the PR gate (`portkit eval`); the real-mod corpus
  (`portkit eval --corpus`) runs nightly, ratcheting coverage, files and
  validator errors per mod.
- **Why:** Alex's call: third-party mods aren't stored in the repo. Pinning by
  hash keeps the runs reproducible, and PR CI stays offline and fast (the
  `realmods` test skips when the jars aren't cached).
- **Rejected:** Committing trimmed copies of the mods.
- **Links:** #21 (PRs #107, #110).

## 2026-10-10: Per-provider base URLs take precedence over the global one

- **Decision:** `resolve_base_url` checks, in order: `config["base_url"]`;
  `PORTKIT_LLM_<PROVIDER>_BASE_URL`; the provider's built-in endpoint (gemini,
  gemini_native); and only then the global `PORTKIT_LLM_BASE_URL`, which applies
  only to providers without a built-in endpoint (openai, anthropic).
- **Why:** A gateway URL saved for OpenAI silently captured Gemini requests
  (401/400 from the wrong host).
- **Rejected:** A single global base URL for every provider.
- **Links:** #95 (PR #98).

## 2026-10-10: Furnace-family recipes emit `input`/`output` as bare ids

- **Decision:** Smelting, blasting, smoking and campfire recipes become
  `minecraft:recipe_furnace` with bare-id `input` and `output`. A result count
  other than 1 is dropped with a note; a tag input is residue. The validator
  requires `output` (no `result` alternative).
- **Why:** That is the shape Microsoft Learn's `recipe_furnace` reference
  documents; `result` may not load in game.
- **Rejected:** Keeping `result` / `{"item": ...}` objects; writing tag inputs
  Bedrock's furnace can't read.
- **Links:** #90 (PR #99).

## 2026-10-09: Item tags resolve from the mod's tag file, then the convention name, then residue

- **Decision:** A Java item tag in a recipe resolves to one item when the
  addon can only mean one: first from the mod's own tag file (nested tags
  expanded, other mods' entries dropped), then from the convention name
  (`c:ingots/steel` → the mod's one `steel_ingot`). Otherwise it is residue,
  and the reason lists the members. A mod's file for a `minecraft:` tag counts
  only with `"replace": true`, since otherwise it just adds to vanilla's list.
- **Why:** A Bedrock addon holds only this mod's items plus vanilla's, so many
  tags have exactly one possible member; the rest need the agent, with the
  membership in hand.
- **Rejected:** Refusing every tag; emitting Bedrock tags the addon can't fill.
- **Links:** #88 (PR #94).

## 2026-10-09: No fabrication: smithing recipes never get invented inputs

- **Decision:** A complete `smithing_transform` (template, base, addition)
  becomes `minecraft:recipe_smithing_transform`. An incomplete one becomes
  `minecraft:recipe_shapeless` from the inputs it does name, plus a report note.
  A multi-item tag in any slot is residue. The agent must not invent inputs.
- **Why:** The validator checks structure, not intent, so invented inputs
  always pass; and models fabricate differently run to run (#86). This is the
  general rule: when the source doesn't say, portkit doesn't guess.
- **Rejected:** Filling missing slots with the base item (a no-op upgrade);
  leaving every incomplete recipe to the agent.
- **Links:** #87 (PR #93).
