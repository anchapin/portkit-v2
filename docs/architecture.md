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
                                                            write_output, set_lang_entries,
                                                            lookup_bedrock, validate)
```

## The pipeline (`portkit/pipeline.py`)

`convert(source, out_dir)`:

1. **Ingest** (`ingest.py`) stages a `.jar` or directory onto disk: `assets/`,
   `data/` and loader metadata. Compiled classes and nested jars become residue
   right away. The class files are also kept in memory (`bytecode.ClassIndex`,
   never staged) so the block converter can read a facing block's placement
   rule and shape from them (`blockcode.py`, see below).
2. **Metadata** (`meta.py`) reads `fabric.mod.json`, `mods.toml` and the rest, for
   the pack name, version and the primary namespace.
3. **Converters** run once per namespace (`converters/__init__.py:convert_all`),
   and `merge_namespaces` folds the results. Output that lands on the same path
   twice is combined where Bedrock allows it (`languages.json`, `.lang`, texture
   indexes). Anything else is reported as a `namespace_collision`. Within one
   namespace, a converter may only replace an earlier converter's file when
   both declare the same identifier; any other second write keeps the first
   and is an `output_collision` (`ConversionResult.merge`). Recipes sharing a
   file name in different folders are named by their path (#163). Recipes and
   loot tables whose load conditions don't hold with only this mod loaded
   (another mod's compat content, a config flag off by default) or can't be
   decided are `conditional_recipe` / `conditional_loot_table` residue
   (`conditions.py`, #183). A modded recipe whose JSON holds only its type
   (a "special" recipe built in code), or one of the typed recipes whose
   station or result is code (BetterEnd infusion, BCLib anvil and alloying,
   Mythic Metals smithing variants, Supplementaries suspicious blocks, Silent Gear's
   Salvager), is
   `code_recipe` residue naming the code, and the agent skips it (#180). A recipe that
   melts, alloys, casts or fills with a mod's fluid (Tinkers' smeltery types, Create's
   spout and drain) is `fluid_recipe` residue naming the station, since Bedrock add-ons
   can't define a fluid; the agent skips it too (#174). A recipe that builds, modifies, repairs
   or takes apart a modular tool or its parts (Tinkers' tool station, part builder, worktable,
   modifiers and severing; Silent Gear gear crafting, smithing, gear salvaging) is `modular_tool`
   residue, since those tools' stats are computed in Java per stack; the agent skips it (#175). A recipe that runs in a Mekanism machine (crusher, enrichment chamber, sawmill, chemical machines, energy and chemical conversion) is `machine_recipe` residue naming the machine, and Mekanism's data-keeping `mek_data` crafting is `code_recipe`; the agent skips both (#172). Create's rotation-powered processing recipes (crushing, milling, cutting, pressing, compacting, mixing, fan splashing and haunting, deploying, mechanical crafting, sequenced assembly) are `machine_recipe` too, naming the Create machine, and its hand-used item application and sandpaper polishing are `code_recipe` (#173). Alloy Forgery forging recipes are `machine_recipe` too, their reason carrying the recipe's inputs, tier, fuel and tier overrides, and the forge data Alloy Forgery reads from a mod (forge definitions, tiers, tier bindings, fuels, its recipe tags) is `machine_data` residue saying what it sets (`converters/alloy_forge.py`); the agent skips both (#171). Entities don't convert (a mob's geometry, animations and AI are Java code): a spawn egg item (model parent `item/template_spawn_egg`) and a loot table at `loot_tables/entities/<name>` named after an entity type the bytecode registers are `entity` residue whose reason carries the category, hitbox and egg colours `entities.py` reads; the agent skips it (#176). Mod config flags are decided at their defaults,
   cited in `data/config_flag_defaults.json`, unless the user sets them
   (`portkit convert --config`, recorded in `config-overrides.json`); number
   options a converter reads (Farmer's Delight's `cuttingBoardFortuneBonus`)
   are cited in the same file's `values` with their range and read through
   `LoadContext.config_value` (#190). Items the
   mod's code registers only while a flag is on (a cited `registers` pattern)
   are `conditional_item` residue when it is off. Recipes of a station type
   (Farmer's Delight's `farmersdelight:cutting`) pass the same load-condition
   gate and then go to `converters/stations.py`, which runs after every other
   converter of the namespace (see [Station runtimes](#station-runtimes)).
4. **Unowned files.** Any staged file that no converter `claim`ed becomes an
   `unowned` residue entry, grouped by directory. A file nobody opened is the
   one outcome the pipeline never allows silently.
5. **write_tree** (`pack.py`) splits output into behavior and resource packs by
   path prefix. It writes manifests (the behavior pack depends on the resource
   pack, never the reverse) and derives the engine floor from what was emitted.
   A behavior pack that ships `scripts/portkit/main.js` also gets a `script`
   module running it and a `@minecraft/server` dependency.
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

## Per-mod adapters (`portkit/adapters/`)

The core converts any mod and names none (`tests/test_core_namespace_free.py`,
a ratchet over mod namespace literals in `src/portkit` outside `adapters/`).
Code that serves one mod, or one library many mods share, is an adapter:
`portkit/adapters/<mod>/`, registered in the explicit, ordered `ADAPTERS`
tuple of `portkit/adapters/__init__.py`. An `Adapter` is a frozen dataclass of
optional hooks, and the core asks the registry at a few seams: a load-condition
type it doesn't evaluate itself (`conditions.LoadContext`), a recipe type with
no Bedrock mapping (`recipes.convert`: residue kind and reason), and per-mod
data (`converters.adapter_data`, run after the entity converter). The moves
into adapters follow `docs/adapter-audit-2026-10-15.md` section 7 (#245), each
with md5-identical packs.

## Station runtimes (`converters/stations.py`, `portkit/runtime/`)

Some recipes are data that a block's Java code interprets: Farmer's Delight's
cutting board takes an item, is hit with the right tool, and drops results by
chance. Nothing in Bedrock's recipe JSON can say that, but everything that
varies is in the recipe file, and the interaction is the same code for every
recipe. So it is split the same way (docs/decisions.md, 2026-10-13):

```
recipe JSON ──(stations.py: load conditions, TagResolver, emitted items)──▶ scripts/portkit/data/<ns>_<station>.js   generated, deterministic
                                                                            scripts/portkit/<station>.js            fixed, copied from portkit/runtime/
blockstate + model ──(blocks.py, placement + shape cited)──▶ blocks/<station>.json + custom component <ns>:portkit_<station>
                                                             scripts/portkit/main.js wires table → runtime; manifest gets the script module
```

- **The table** is output like any other file: sorted, diffable, and checked
  against what the namespace emitted. A recipe it can't state exactly is
  `station_recipe` residue with the reason; the agent skips that kind (it
  writes JSON against the validator, not script data).
- **The runtime** is hand-written once per station kind, every behaviour cited
  to the mod's source at a pinned commit, and never generated. Pure logic
  lives in a file with no imports (`*_core.js`) so `tests/js/` runs it under
  node against a stub of `@minecraft/server`; the binding file does storage
  (world dynamic properties, since custom blocks have no inventory), sounds,
  item spawning and tool damage.
- **The block** is the mod's own; a station block's facing-only variants
  convert with the placement rule and `SHAPE` the station spec cites.

## Guide books (`converters/books.py`, `portkit/runtime/book*.js`)

Citadel books (Alex's Mobs' Animal Dictionary, #182) keep their pages as data
in the jar (`assets/<ns>/book/<book>/root.json`, one JSON per page, a text file
per page per locale). The page text, read the way Citadel reads it, goes into
every `texts/<Locale>.lang` the pack ships under `portkit.book.<ns>.<book>.<page>`
(a locale without its own file gets `en_us`, Citadel's fallback); the pages
reachable from `root.json` go into `scripts/portkit/data/<ns>_books.js`; the
fixed viewer shows each page as an `ActionFormData` when the book's item is
used. Which item opens the book is read from bytecode: the `GuiBasicBook`
subclass whose `getRootPage` names it, the item class whose `use` builds that
screen (directly or through a proxy override), and the item's registered name
through `blockcode`'s registration reader; else the item named like the book
directory (DEFAULT, said in the note). Pictures, unreachable pages and
locales Bedrock lacks stay residue (docs/decisions.md, 2026-10-15).

## Facing-only blocks (`blockcode.py`, `bytecode.py`)

A block whose blockstate is exactly `facing=north|east|south|west` (one model,
quarter turns about y) and that is no station converts as decoration: the
model's geometry turned per `minecraft:cardinal_direction` by
`minecraft:transformation` (a uvlocked model gets one bone per facing). Which
way `facing` points when placed and the block's box are its code's, so they are
read from the jar's class files: `bytecode.py` parses class files (JVMS ch. 4)
and `blockcode.py` runs the registration (`DeferredRegister.register`,
`Registry.register`, helpers; a call that passes the block and its item as
several lambdas, like MrCrayfish Framework's `blockWithItem(id, Supplier,
Function)`, registers the one lambda whose dynamicMethodType takes nothing
and returns a block class, and none when that isn't exactly one),
`getStateForPlacement` (the placement context's
`getHorizontalDirection()` is a symbol) and `getShape` once per facing on a
small abstract interpreter, with vanilla `Block.box` / `Shapes.*` /
`Stream.reduce` / enum switch maps / `Map.get` modelled and everything else an
unknown value. A branch on an unknown value runs both ways and counts only when
both agree. Whatever can't be read falls back to a documented default
(placement facing the player, box from the model's element bounds, collision =
selection), and the conversion notes name every value as read (class#method) or
DEFAULT, per block (#87). Jars with Forge SRG or Fabric intermediary member
names are never read by name (a renamed override can't be told from none).
- **Versions.** Script API `@minecraft/server` 2.0.0, the first with custom
  components v2 (Bedrock 1.21.90, also the first block format that reads a
  namespaced component), so a station block is written at 1.21.90 and the pack
  floor follows. A station spec is tied to the mod versions whose code was
  read; any other version stays residue.

- **Stations so far.** Farmer's Delight's cutting board (`stations.py`,
  `cutting_board*.js`) and cooking pot (`cooking_pot.py`, `cooking_pot*.js`,
  a timed station: block `minecraft:tick` + `onTick`, heat read from FD's
  block tags, a facing x `support` blockstate turned by
  `minecraft:transformation`), and the stove (`stove.py`, `stove*.js`), a
  timed station whose recipes are a *shared* type: `minecraft:campfire_cooking`
  recipes still convert as Bedrock campfire recipes and are also handed to the
  stove (`recipes.STATION_SHARED_TYPES`), beside vanilla's own campfire
  recipes from the fetched reference (`portkit/data/recipes.py`); its facing x
  `lit` blockstate is two plain cubes, so Bedrock's `full_block` geometry with
  material instances and light per `lit` value and the facing turn, one
  permutation per (facing, lit). Lit, it is a cooking-pot heat source
  (`stove.HEAT_RULES`). The skillet (`skillet.py`, `skillet*.js`) cooks the
  stove's campfire table (`stove.campfire_table`) as a placed block (facing x
  `support`, the cooking pot's heat rule via `cooking_pot.heat_table`, whose
  JS helpers it imports from `cooking_pot_core.js`) and as a held item: the
  station's first item file (`items/skillet.json`, the block's own item via
  `replace_block_item`, iron-tier weapon numbers cited) and its first
  world-event hooks (`world.beforeEvents.itemUse` for held cooking,
  `world.afterEvents.entityHitEntity` for the hit sound, a
  `system.runInterval` loop over player dynamic properties). The feasts
  (`feasts.py`, `feast*.js`) are six blocks on one component: the blocks FD's
  `farmersdelight:feasts` tag names, facing x an *integer* `servings` state
  (`FacingBlock.int_state`), a box (and the gleaming salad's light) per
  serving count through `value_components`, and the first station to read a
  loot table: `loot.convert` defers a feast's table (`stations.station_loot`)
  and the feast converter turns it into one Bedrock table per distinct drop
  set, set per count with `minecraft:loot` on the permutations; the runtime
  keeps no storage (the state is the count) and clears a block with
  `setblock ... destroy` so it drops through those tables. All of them share
  `station_storage.js` (dynamic property storage, stack describe/rebuild,
  give/drop, sounds); `main.js` imports every station that shipped.

Adding a station (Mekanism single-input machines #172, anvils #180) is a table
writer (in `stations.py` or its own module, dispatched from
`stations.convert`), a runtime file in `portkit/runtime/`, and the block's
cited placement/shape.

## The oracle (`portkit/validate/`)

`validate_tree(tree) -> ValidationReport`, a list of findings, each with a path,
a rule name and a message:

- `rules.py`: structural rules per file type (manifests, recipe bodies,
  identifiers, required fields). Script packs: a `script` module needs
  `language: javascript` and an `entry` file in the pack, a `module_name`
  dependency needs a version string, every `import` in `scripts/` resolves (a
  file in the pack, or a module the manifest depends on), and a block with a
  custom component needs format 1.21.90 or later. A JSON file in a document folder (`items/`,
  `entities/`, `entity/`, `attachables/`, ...) without that folder's document key
  (`minecraft:item`, ...) or with a non-object body is `doc.unknown_shape`.
- `xrefs.py`: cross-file references (a recipe naming an item no pack defines, an
  icon missing from `item_texture.json`).
- `collisions.py`: two files claiming one identifier.
- `schema.py`: shape checks against Mojang's own JSON schemas, vendored per
  snapshot under `validate/schemas/` and picked by `format_version`. An unknown
  `minecraft:` block component is an error, and other shape mismatches are
  warnings. Every finding carries a JSON `pointer`. `schema_upstream.py`
  (`portkit schemas check|refresh`, #155) says when Mojang's stable package for
  a snapshot vendored from a prerelease is out and re-vendors it; steps in
  `validate/schemas/SOURCE.md`.

The validator is deterministic and fast, which is why the agent can call it in a
loop and why CI can gate on it. Making it stricter is always welcome, but a rule
must reflect what Bedrock actually does, cited from Mojang's docs or samples,
never a guess.

## The residue agent (`portkit/agent/`)

- `loop.py`: about 100 lines. Send messages, receive a tool call, run it, append
  the result, repeat until the model stops or a budget runs out.
- `tools.py`: `read_source`, `list_source`, `write_output` (one JSON file, sent
  as JSON text in `content_json`),
  `set_lang_entries` (upserts `key=value` lines into a resource pack `.lang`
  file), `lookup_bedrock` / `list_bedrock_topics` and `validate`, plus the
  system prompt.
- `reference/`: the deterministic Bedrock reference behind `lookup_bedrock`
  (#114). A topic (a block or item component, a recipe type, a pack file such as
  `terrain_texture.json` or `.lang`) maps to the fragment of the vendored Mojang
  schema, a short real example, the docs' property table and a note on what the
  validator checks. No embeddings or ranking: same topic, same bytes, so
  transcripts that use it replay. Answers are capped at 6,000 characters; an
  unknown topic returns the closest names in a fixed order.
  `bedrock_reference.json` is generated by `scripts/build_bedrock_reference.py`
  from pinned commits of Mojang/bedrock-samples and MicrosoftDocs/minecraft-creator
  (CC-BY-4.0; see `reference/NOTICE.md`); `--check` says whether it is current.
- `residue.py`: groups `Unhandled` by `(kind, source)`, builds one task per group
  (the source content plus the exact refusal reason), and runs one session each.
  A group counts as resolved only if the session ends on its own, writes at least
  one file, adds no validator error, every item and tag its recipes name
  exists (`refs.py`: in the pack, in the source mod, or vanilla), every
  gameplay number on its items (damage, durability, ...) is one the source mod
  states for that item (`stats.py`), and every `template` and `addition` it
  puts into a written `minecraft:recipe_smithing_trim` is a vanilla
  `minecraft:` item or tag (`trim.py`; Bedrock add-ons can't apply mod trims).
  Otherwise its writes are rolled back. A session that writes nothing and says why is
  `declined`. The run's `status` (`complete` | `partial` | `failed`) is about the
  agent's work, not about whether the pack validates.
- `budget.py`: step, token and dollar ceilings with per-group accounting. The
  loop stamps every tool result with the steps left, and while three or fewer
  remain with nothing written it adds a nudge to write or decline (#139).
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

## Decisions

The converters' policies (no fabrication, tag resolution, what is fetched rather
than vendored, and the rest) each have an entry in the
[decision log](decisions.md) saying what was decided, why, and what was
rejected. A PR that makes a design decision adds an entry there.
