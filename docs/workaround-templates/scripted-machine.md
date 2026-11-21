# Workaround template 1: the scripted machine

**Status:** design only. No template code, no converter change and no test ships with
this document. Issue #239's rule is that *a template ships only after Alex approves its
design*, so the picks in [Decisions for Alex](#decisions-for-alex) are the deliverable
here. Nothing in this repository runs a machine until those picks are made and the
implementation PR that follows them lands.

There is deliberately **no entry in `docs/decisions.md`** yet: that file records
*settled* decisions ("When a PR makes a design decision ... add an entry here in the
same PR", `docs/decisions.md:8-9`), and this design settles nothing until Alex picks.
The entry comes with the PR that implements the approved design.

This is the first of the #239 template library (the brainstorm lists the set as
"scripted machine, form GUI station, tank block, mob template", one design PR each with
Alex's picks: `docs/brainstorm-2026-10-15-scaling.md:84`). Only the scripted machine is
designed here.

---

## 1. Purpose

A Java mod machine is a block entity: it holds an inventory (and tanks, and an energy
store, and sometimes a fuel store), it *works over ticks*, and it consumes something
while it works. Bedrock has none of that on a custom block, so the converter refuses
these recipes and leaves them as residue, and the residue agent is told to skip them.

The template turns such a recipe into a playable Bedrock machine:

* a custom block that **ticks** (Script API `onTick`),
* **item input/output slots** in a custom block container (`#226`),
* **progress** (how far the current recipe has run) kept in **dynamic properties**.

Its scope is deliberately small: item in, item out, over time. It carries no energy,
no chemicals, no fluid, no rotation and no multiblock. Every one of those is a
documented non-goal ([§8](#8-non-goals)), because Bedrock cannot carry them and because
the residue does not state them ([§7](#7-what-the-agent-may-fill-in-per-mod-and-what-stays-a-labelled-default)).

The template is a *pattern*, not a converter feature: the machine block, its data table
and its runtime are produced per mod (by the residue agent, or by a hand-written
adapter), from the residue the deterministic converter already emits. The template
supplies the fixed runtime script and the shape of the data table.

### How it relates to the existing station kit

This template is not a new idea in this repository: it is the "generic recipe-table
pattern (data table written from recipe JSON + fixed runtime + `main.js` entry)" that the
adapter audit already names as the core of a #239 "scripted machine" template
(`docs/adapter-audit-2026-10-15.md:100-102`), and it reuses the parts the audit lists as
reusable (`docs/adapter-audit-2026-10-15.md:172-182`):

| Piece | Today in | What the template takes from it |
|---|---|---|
| Data table + fixed runtime + `main.js` entry (`runtime_source`, `js_module`, `ENTRY`, `SCRIPT_*`) | `src/portkit/converters/station_kit.py:34-51`, `203-211` | the table shape and the entry script |
| `storageKey` / `storagePrefix` | `src/portkit/runtime/station_core.js:16-23` | the dynamic-property key shape |
| `station_storage.js` (`loadStored`/`saveStored`, `describe`/`rebuild`, `give`, `dropStored`) | `src/portkit/runtime/station_storage.js:16-36`, `39-69`, `90-104` | storing stacks, giving and dropping them |
| Recipe resolver (`_Resolver`: items/tags/tool abilities -> Bedrock) | `src/portkit/adapters/farmersdelight/cutting_board.py:243-268` | resolving an ingredient to ids the pack holds |
| World dynamic-property record store | `src/portkit/adapters/waystones/runtime/waystone.js:150` | the "state lives in a world property" pattern |

---

## 2. The residue this template consumes

### 2.1 What the converter emits

A refusal is one `Unhandled` record (`src/portkit/model.py:67-81`):

```
source   the file the converter refused, relative to the mod root
kind     the residue kind ("machine_recipe")
reason   why it was refused, and what the file sets
count    how many source files the entry stands for
```

Those four fields are what lands in `unhandled.json` next to the packs
(`src/portkit/pipeline.py:705-707` writes `u.__dict__` for every remaining record), so
they are the whole contract between the converter and any template.

The kind this template consumes is `machine_recipe`:

* the kind constant: `MACHINE_RECIPE = "machine_recipe"` (`src/portkit/converters/recipes.py:318`);
* the hook that asks an adapter for the reason: `machine_recipe_reason()`
  (`src/portkit/converters/recipes.py:329-334`), called from the recipe converter when a
  recipe's type has no supported vanilla mapping (`src/portkit/converters/recipes.py:2003-2007`,
  `Unhandled(rel, *found)`);
* the kind's skip entry, which is why the residue agent never touches these today:
  `SKIP_KINDS["machine_recipe"]` (`src/portkit/agent/residue.py:133-138`);
* the report's label for the kind, "Machine recipe"
  (`src/portkit/report.py:86-88`).

The reason always ends with the same statement of what Bedrock lacks
(`NO_BEDROCK_MACHINE`, `src/portkit/converters/recipes.py:321-325`): "a Bedrock custom
block has no ticking inventory, tank or energy store, so there is no Bedrock station to
run it (that needs a scripted machine runtime, #172), and an instant crafting stand-in
at the machine block would drop the processing time and what the machine consumes".

### 2.2 What each mod's reason carries

The reason is per mod, and it is where the machine's *identity* and *shape* live:

| Mod / issue | Reason source | What the reason states |
|---|---|---|
| Mekanism (#172) | `src/portkit/adapters/mekanism/recipes.py:41-...` (26 types) | the machine block (`mekanism:crusher`, `mekanism:enrichment_chamber`, ...), the input field (`input`, `main_input` + `extra_input`, `item_input`, `fluid_input`), the output field (`output`, `main_output` + `secondary_output` at `secondary_chance`), and that it works "over time, using energy" |
| Mekanism, per-tick chemicals | `src/portkit/adapters/mekanism/recipes.py:64-77` | `chemical_input`, `per_tick_usage` ("each tick when `per_tick_usage` is true, else once"), and that chemicals have no Bedrock form (`src/portkit/adapters/mekanism/recipes.py:13-15`) |
| Mekanism, a duration | `src/portkit/adapters/mekanism/recipes.py:85-91` | "over `duration` ticks" (the nucleosynthesizer) |
| Create (#173) | `src/portkit/adapters/create/__init__.py:84-...` (11 types) | the machine, the `ingredients` / `results` fields, "over `processingTime`", and that a result's `chance` has no Bedrock field (`src/portkit/adapters/create/__init__.py:29-32`) |
| Create, heat | `src/portkit/adapters/create/__init__.py:109`, `115` | "heated by a blaze burner when `heatRequirement` says so" (compacting, mixing) |
| Alloy Forgery (#171) | `src/portkit/adapters/alloy_forgery/forge.py:146-194` | the inputs and the output ("forges 2 x item into 1 x item"), `min_forge_tier` ("needs a forge of tier 2 or higher"), `fuel_per_tick` ("burns N fuel per tick"), the tier `overrides`, and the forge's controller block |

The reasons carry **field names and machine identity, not gameplay numbers** (no energy
amount, no tick count for most machines, no rotation speed, no fuel item id). The
numbers that do exist live in the refused file itself: the residue agent's task prompt
carries the source file's content (`_source_block`, `src/portkit/agent/residue.py:385-404`,
put into the prompt at `src/portkit/agent/residue.py:428`), so an ingredient id, a count
and a `processingTime` are *in the prompt* and in the source jar, while an energy cost
is nowhere.

That split is the whole basis of [§7](#7-what-the-agent-may-fill-in-per-mod-and-what-stays-a-labelled-default):
the template may use what the residue *and its source file* state, and nothing else.

### 2.3 Residue kinds this template does not consume

* `machine_data` (Alloy Forgery's forge definitions, tiers, tier bindings, fuels and its
  recipe tags) — a separate kind (`src/portkit/agent/residue.py:140-142`), read at
  runtime by Java code; it is not a recipe and this template has no use for it.
* `code_recipe` (Mekanism's `mek_data` crafting, Create's hand-used item application,
  Alloy Forgery's ...) — used by hand, not by a machine (`src/portkit/agent/residue.py:125-128`).
* `fluid_recipe` — Bedrock cannot store a measured amount of fluid
  (`NO_BEDROCK_MB`, `src/portkit/converters/recipes.py:326`).
* `custom_fluid`, `modular_tool`, `entity`, `java_code` — not machine recipes
  (`src/portkit/agent/residue.py:138-149`).

---

## 3. The block, the container and the tick

Everything below is behaviour this repository already uses, or is flagged as
unverified. Nothing is invented.

### 3.1 The block

A machine is a custom block with two components:

* **`minecraft:tick`** — the block's own tick. The repository writes it as
  `{"interval_range": [N, N], "looping": True}`: the cooking pot
  (`src/portkit/adapters/farmersdelight/cooking_pot.py:598-599`), the skillet
  (`src/portkit/adapters/farmersdelight/skillet.py:281`), the stove
  (`src/portkit/adapters/farmersdelight/stove.py:359`), the Waystones' blocks
  (`src/portkit/adapters/waystones/convert.py:1831`, `1860`). The comment in the
  runtime states the rule: "The block carries minecraft:tick at the table's
  tick_interval, so onTick runs while its chunk is ticking"
  (`src/portkit/adapters/farmersdelight/runtime/cooking_pot.js:9-10`).
* **`minecraft:block_entity`** with `{"container": {"slot_count": N}}` — the #226
  container. The converter writes exactly this
  (`src/portkit/converters/blocks.py:6735`) and documents the component's limits: slot
  count 1-54, interacting opens Bedrock's own container screen, contents drop when the
  block is destroyed, and "other access such as hoppers is not supported"
  (`src/portkit/converters/blocks.py:6660-6669`).

Both components need the **Upcoming Creator Features** experiment, which is why the
container is written only when the user converts with
`--experiment upcoming_creator_features` (`src/portkit/converters/blocks.py:6666-6669`,
`6744-6746`; the note the player reads,
`src/portkit/converters/blocks.py:6758-6762`). The scripted machine has the same
precondition, and it is a hard one: see [§9](#9-failure-modes).

The block's other properties (facing, collision box, textures) come from the mod's own
converted block, read by the usual converter path; the template adds nothing to them.

### 3.2 The Script API side

The template's runtime is a custom-component binding like the existing station
runtimes. The repository uses, in `src/portkit/adapters/farmersdelight/runtime/cooking_pot.js:8-10`
and `221-224`:

* `BlockCustomComponent` with `onPlayerInteract`, **`onTick`**, `onPlayerBreak`,
  `onPlace`, `beforeOnPlayerPlace`;
* `@minecraft/server` **2.0.0**, custom components v2, Bedrock 1.21.90 — the pins the
  station kit holds (`src/portkit/converters/station_kit.py:34-38`) and the reason the
  kit's blocks need block format 1.21.90 or later.

The template needs the same set minus the placement hooks: `onTick` (the machine works),
`onPlayerInteract` (open/take out), `onPlayerBreak` (drop the contents, clear the
progress record).

Storage helpers are the shared ones, not new code: `loadStored`/`saveStored` for the
progress record (`src/portkit/runtime/station_storage.js:16-36`), `describe`/`rebuild`
for a stack that has to survive a save/load (`src/portkit/runtime/station_storage.js:39-69`),
`give`/`dropStored` for handing items back
(`src/portkit/runtime/station_storage.js:90-104`).

### 3.3 APIs this design names that the repository does **not** use

These are flagged, per the rule that every API a template names is either cited to
existing repo usage or explicitly unverified:

| API | Status |
|---|---|
| `block.getComponent("minecraft:inventory")?.container` | **Cited for reading** `.size`: `src/portkit/ingame/runtime/ingame.js:348`, with the verdict helper `src/portkit/ingame/runtime/ingame_core.js:270-274` |
| `container.getItem(i)` / `container.setItem(i, stack)` on a **block** container | **Unverified — needs Alex/desktop check.** The repository only reads `.size` on a block container (`src/portkit/ingame/runtime/ingame.js:348`); `getItem`/`addItem` are cited for *player* inventories only (`src/portkit/runtime/station_storage.js:90-95` `give`, `137-143` `heldAt`) |
| `world.setDynamicProperty` / `world.getDynamicProperty` | **Cited**: `src/portkit/runtime/station_storage.js:16-36`, `src/portkit/adapters/waystones/runtime/waystone.js:150` |
| `block.setDynamicProperty` (a property on the block itself) | **Unverified — needs Alex/desktop check.** No block-level dynamic property is used anywhere in this repository; the grep for `setDynamicProperty` finds only world, player, entity and item stacks (`src/portkit/runtime/station_storage.js:34`, `src/portkit/adapters/farmersdelight/runtime/skillet.js:257`, `src/portkit/adapters/waystones/runtime/waystone.js:123`, `150`, `597`, `1071`, `1354`) |
| `system.runInterval` | **Not used by this design.** The stations tick through the block's own `minecraft:tick` (`src/portkit/adapters/farmersdelight/runtime/cooking_pot.js:9-10`); `system.run`/`system.runTimeout` are used elsewhere in the repo (`src/portkit/runtime/*.js`) but not for a machine's progress |

---

## 4. The progress schema

Progress is **not** an item and **not** a block state: it is a dynamic property, keyed
by where the machine is.

**Key.** `<template component>|<dimension id>|<x>,<y>,<z>`, the shape
`storageKey` already builds for every station
(`src/portkit/runtime/station_core.js:16-18`, `storagePrefix` at `21-23`):

```
portkit|machine|overworld|128,64,-317
```

**Value.** One JSON object, stored with `saveStored`
(`src/portkit/runtime/station_storage.js:34-36`):

```json
{
  "recipe": "portkit:mekanism/crushing/<source file stem>",
  "ticks": 37,
  "total": 140
}
```

| Field | Meaning | Where it comes from |
|---|---|---|
| `recipe` | the template row the machine is running | the residue row the agent wrote |
| `ticks` | ticks already worked | the runtime's own count |
| `total` | the recipe's full duration | **only** a duration the residue states ([§7](#7-what-the-agent-may-fill-in-per-mod-and-what-stays-a-labelled-default)) |

Rules:

* the property is written **only while it changes**, so an idle machine costs nothing
  (the cooking pot does the same: "Only write the dynamic property when the pot
  changed", `src/portkit/adapters/farmersdelight/runtime/cooking_pot.js:188`);
* it is **cleared** (written as `undefined`, which is how `saveStored` clears a value,
  `src/portkit/runtime/station_storage.js:34-36`) when the machine finishes, when the
  output is taken, or when the block is broken;
* the key is **position-keyed, not machine-keyed**: two machines of the same kind at
  different positions have different records, and a machine that is broken and replaced
  starts fresh (its old record is removed by the break handler);
* `total` is never a guess. If the residue states no duration, there is no `total` and
  the machine does not start that recipe ([Decision 4](#decisions-for-alex)).

A machine's *inventory* is not in the dynamic property: it is in the block's container
([§5](#5-slot-semantics)). The dynamic property holds the machine's *work*, nothing else.

---

## 5. Slot semantics

The container's slots are the machine's inventory, laid out by the template:

| Slot | Holds |
|---|---|
| `0 .. n-1` | the **input** slots (one per ingredient the residue names: `input`; `main_input` + `extra_input`; `item_input`; Create's `ingredients` list) |
| `n` | the **output** slot |

* `n` is fixed by the recipe row the agent wrote; `slot_count` is `n + 1` and must be
  between 1 and 54 (`src/portkit/converters/blocks.py:6663`).
* A machine with more than 54 ingredients cannot be a container; the row is refused
  (see [§9](#9-failure-modes)).
* The **output slot is write-only by the player**: the player can take from it and put
  into it, but the runtime owns the result. A stack a player puts in the output slot
  is not consumed by a recipe (Java's output slot is the machine's, not the player's).
* The input slots are the machine's: a player putting an item in is the machine's
  "put the ingredient in" step; the runtime removes the ingredients when the recipe
  completes, exactly once, and only if they are still there.
* Items are matched by id and count. A **tag** ingredient (Java's `#tag`) is resolved
  to the ids the pack holds at convert time (the `_Resolver` pattern,
  `src/portkit/adapters/farmersdelight/cutting_board.py:243-268`); at run time a stack
  matches if its id is one of those ids.
* **Chance results** (Mekanism's `secondary_output` at `secondary_chance`, Create's
  `results` with a `chance`) are **not** carried: "a Bedrock recipe result has no chance
  field, so a `secondary_chance` below 1 can't be carried"
  (`src/portkit/adapters/mekanism/recipes.py:58`, `src/portkit/adapters/create/__init__.py:29-32`).
  Such a row is written as a labelled DEFAULT and the secondary output is dropped, not
  approximated.
* What the player can reach is what Bedrock's container gives: "Interacting from any face
  opens Bedrock's own container screen; its contents drop when the block is destroyed;
  hoppers and other blocks don't reach it"
  (`src/portkit/converters/blocks.py:6758-6762`). The template does not add a GUI, a
  menu layout, or automation.

---

## 6. The data table the runtime reads

One generated module per machine kind, in the shape `js_module` already writes
(`src/portkit/converters/station_kit.py:208-211`), read by the fixed runtime at
`scripts/portkit/main.js` (`ENTRY`, `src/portkit/converters/station_kit.py:40`):

```json
{
  "component": "portkit|machine",
  "block": "portkit:mekanism_crusher",
  "tick_interval": 1,
  "slots": { "input": 1, "output": 1 },
  "recipes": [
    {
      "id": "portkit:mekanism/crushing/<source file stem>",
      "inputs":  [{ "id": "mod:raw_ore", "count": 1 }],
      "outputs": [{ "id": "mod:crushed_ore", "count": 2 }],
      "ticks": 140,
      "defaults": ["energy per tick"]
    }
  ]
}
```

Every field above is either copied from the residue's source file (ids, counts,
`ticks`) or is a structural constant of the template (block id, slot layout, tick
interval). The `defaults` list names the things the residue did **not** state, in the
repo's labelled-DEFAULT wording, so a reader of the pack can see what was dropped.

---

## 7. What the agent may fill in per mod, and what stays a labelled DEFAULT

The residue agent's task prompt already gives it the refused file's content and the
reason (`src/portkit/agent/residue.py:420-448`), and the repo's rule for it is explicit:
gameplay numbers "come only from the source mod: if it does not state one, omit that
component rather than guess" (`src/portkit/agent/residue.py:435-441`). The template
inherits that rule.

### 7.1 The agent may fill in (from residue data only)

| Field | Evidence it exists |
|---|---|
| the machine's block id | the reason names it: "in `mekanism:crusher`" (`src/portkit/adapters/mekanism/recipes.py:42-45`), "in `mekanism:enrichment_chamber`" (`:46-49`), Create's machines (`src/portkit/adapters/create/__init__.py:85-...`), Alloy Forgery's controller (`src/portkit/adapters/alloy_forgery/forge.py:186-190`) |
| input item ids and counts | the refused file's own fields (`input`, `main_input`, `extra_input`, `item_input`, `ingredients`), which the prompt carries (`src/portkit/agent/residue.py:385-404`) |
| output item id and count | the refused file's `output` / `main_output` / `results`; for Alloy Forgery the reason states it in words ("forges 2 x item into 1 x item", `src/portkit/adapters/alloy_forgery/forge.py:158-162`) |
| the duration, **when the residue names one** | Create's `processingTime` (`src/portkit/adapters/create/__init__.py:87`), Mekanism's `duration` ticks (`src/portkit/adapters/mekanism/recipes.py:85-91`) |
| the tier gate, for Alloy Forging | `min_forge_tier` ("needs a forge of tier 2 or higher", `src/portkit/adapters/alloy_forgery/forge.py:163-166`) |
| the fuel cost, for Alloy Forging | `fuel_per_tick` ("burns N fuel per tick", `src/portkit/adapters/alloy_forgery/forge.py:167-171`) |
| the tier overrides, for Alloy Forging | `overrides` ("makes ... instead", `src/portkit/adapters/alloy_forgery/forge.py:172-182`) |

The last three are **facts the residue states**, so the table may record them. Whether the
machine can *enforce* them is a separate question: a tier gate needs the forge's tier
data, which is `machine_data` residue, a different kind this template does not consume
(`src/portkit/agent/residue.py:140-142`), and a fuel needs a fuel item id the residue
does not carry. So a recorded tier gate is an **enforced-nothing DEFAULT**: the table
says which tier the Java recipe needed, and the machine runs without the gate.

### 7.2 What stays a labelled DEFAULT (never invented)

| Thing | Why it is a DEFAULT | Evidence |
|---|---|---|
| energy per tick, energy capacity | in Mekanism's Java code, not in the recipe file; the reason says only "using energy" | `src/portkit/adapters/mekanism/recipes.py:42-45` |
| chemicals (gases, infuse types, pigments, slurries) | "Mekanism's chemicals ... have no Bedrock form" | `src/portkit/adapters/mekanism/recipes.py:13-15` |
| fluid amounts in mB | "Bedrock can't store a measured amount of fluid (#174)" | `src/portkit/converters/recipes.py:326` |
| rotational speed and stress | the machine "works only while Create's rotational network ... turns it"; no number is in the recipe file | `src/portkit/adapters/create/__init__.py:18-24` |
| the heat source (blaze burner) | the reason names the requirement but not its shape | `src/portkit/adapters/create/__init__.py:109`, `115` |
| the forge's multiblock (material around the controller) | the reason names the controller block, not the structure | `src/portkit/adapters/alloy_forgery/forge.py:186-190` |
| the fuel item ids | the fuels are `machine_data` residue, a different kind | `src/portkit/agent/residue.py:140-142` |
| chance results | Bedrock's recipe result has no chance field | `src/portkit/adapters/mekanism/recipes.py:58` |
| machine upgrades | Java-side only; nothing in the residue | `src/portkit/converters/recipes.py:300-317` (the converter's own account of what the machine does) |

A DEFAULT is **labelled**, in the repo's own wording, so a reader of the pack can see
what was dropped: the pattern the converter uses is "Collision DEFAULT, not read from
code" (`src/portkit/converters/blocks.py:2246`) and "a labelled **DEFAULT**"
(`src/portkit/adapters/ae2/__init__.py:45`). In the template's table each DEFAULT is a
string in the row's `defaults` list ([§6](#6-the-data-table-the-runtime-reads)), and the
conversion notes say the same in words.

**The rule the template enforces:** a row with a DEFAULT is still playable (the machine
runs the recipe, it just costs nothing to run); a row *without* a duration is not
started at all ([Decision 4](#decisions-for-alex)).

---

## 8. Non-goals

1. **Energy, chemicals, fluid.** No energy store, no chemical tank, no fluid amount.
   Bedrock has none of them (`src/portkit/converters/recipes.py:321-325`), and the
   residue does not state the numbers.
2. **Rotation / stress** (Create). A machine runs on its own tick, not on a kinetic
   network (`src/portkit/adapters/create/__init__.py:18-24`).
3. **Multiblocks** (Alloy Forgery's forge: a controller plus a shell of forge material).
   The reason names the controller, not the shape (`src/portkit/adapters/alloy_forgery/forge.py:186-190`).
4. **Menus, GUIs, recipe books, the machine's own Java screen.** The template uses
   Bedrock's own container screen; it does not reproduce Java's menu layout (the
   converter's own note for containers lists "Java's menu layout, any face or sneak rule
   on opening, open/close sounds and animation" as not carried,
   `src/portkit/converters/blocks.py:6758-6762`).
5. **Automation.** "hoppers and other blocks don't reach it"
   (`src/portkit/converters/blocks.py:6758-6762`).
6. **The machine block's own conversion** (its block entity, its loot, its behaviour
   overrides). The template adds a tick and a container to a block the ordinary
   converter path already produced; it does not convert the machine's Java code.
7. **A converter feature.** This template is a pattern the residue agent (or a
   hand-written adapter) fills in; it is not a new residue kind and not a new refusal.
8. **The other #239 templates** (form GUI station, tank block, mob template) and the
   `machine_data` kind.

---

## 9. Failure modes

| Failure | What happens | Evidence |
|---|---|---|
| the world's blocks are not the mod's machine block (it is residue itself, or was never converted) | the agent writes nothing and says why; the row stays residue | the agent's own rule: "If this has no faithful Bedrock equivalent, write nothing and say why in one sentence" (`src/portkit/agent/residue.py:442-446`) |
| the world runs without the Upcoming Creator Features experiment | the container is not written, so the machine has no slots; the machine must not silently run with no inventory | `src/portkit/converters/blocks.py:6666-6669`, `6744-6746` |
| the chunk is unloaded | `onTick` does not fire, so the machine does not progress (it resumes when the chunk ticks again) | "onTick runs while its chunk is ticking" (`src/portkit/adapters/farmersdelight/runtime/cooking_pot.js:9-10`) |
| more than 54 slots are needed | the container's slot count is 1-54; the row is refused | `src/portkit/converters/blocks.py:6663` |
| an ingredient is an item the pack does not hold | the row is refused, not approximated: "not converted" / "tag ... has no member this addon can hold" | `src/portkit/adapters/farmersdelight/cutting_board.py:251-268` |
| a result has a chance | the chance is dropped and labelled DEFAULT | `src/portkit/adapters/mekanism/recipes.py:58` |
| the block is broken | the container's contents drop (Bedrock's rule), and the progress record is cleared | "its contents drop when the block is destroyed" (`src/portkit/converters/blocks.py:6665-6666`) |
| the machine's Java code had a special case (a machine that works only in the rain, a solar machine that needs the sky) | not carried; the reason names it, the template ignores it and the row's DEFAULT says so | e.g. "only while it can see the sky" (`src/portkit/adapters/mekanism/recipes.py:131-132`) |
| the template's runtime is broken | every machine in the pack is affected; the in-game check (`src/portkit/ingame/runtime/ingame.js`) is the only place that catches it | `src/portkit/ingame/runtime/ingame.js:334-355` (the container check the in-game pack runs) |

---

## 10. Decisions for Alex

Five picks. Each one is a choice the design cannot make on its own; the template ships
only after they are made.

**Pick 1 — where the slots live.**
(a) the #226 custom block container (`minecraft:block_entity` + `container.slot_count`),
the subject of this title, which needs the Upcoming Creator Features experiment;
(b) the repository's existing station pattern: the inventory in a world dynamic
property (`src/portkit/runtime/station_storage.js:16-71`), which needs no experiment but
gives the player no container screen.
*Recommendation: (a), with (b) as the documented fallback for a world without the
experiment, and never a silent mix of the two.*

**Pick 2 — which block is the machine.**
(a) the mod's own converted block, with `minecraft:tick` and the container added to it
(the player sees the mod's own machine);
(b) a new block in a portkit namespace, used when the mod's machine block is residue.
*Recommendation: (a); (b) only when (a) is impossible, and then the reason is named.*

**Pick 3 — where progress lives.**
(a) a world dynamic property keyed by dimension and position, the shape `storageKey`
already builds (`src/portkit/runtime/station_core.js:16-18`);
(b) a dynamic property on the block itself (a cleaner key, but no usage of
`block.setDynamicProperty` exists in this repository — unverified, needs a desktop
check).
*Recommendation: (a).*

**Pick 4 — a recipe with no stated duration.**
(a) the machine runs it with a **labelled DEFAULT** duration;
(b) the machine does not start it, and the row is labelled DEFAULT ("no duration in the
residue"), so no number is ever invented.
*Recommendation: (b) — the repo's rule is to omit rather than guess
(`src/portkit/agent/residue.py:435-441`).*

**Pick 5 — what happens to `machine_recipe` in `SKIP_KINDS`.**
(a) the kind stays skipped and the template is used by hand (or by a dedicated adapter
per mod);
(b) the kind leaves `SKIP_KINDS` (`src/portkit/agent/residue.py:133-138`) so the residue
agent fills the template in automatically, for the rows it can state exactly.
*Recommendation: (b), but only for rows with no labelled DEFAULT that changes the
gameplay (no duration, no chemical, no fluid) — otherwise the agent would ship a
machine that does not behave like the mod's.*

---

## Appendix: evidence index

| Claim | Where |
|---|---|
| the residue record's four fields | `src/portkit/model.py:67-81` |
| `unhandled.json` holds those records | `src/portkit/pipeline.py:705-707` |
| the kind `machine_recipe` | `src/portkit/converters/recipes.py:318`, `src/portkit/agent/residue.py:133-138` |
| the reason hook | `src/portkit/converters/recipes.py:329-334`, called at `2003-2007` |
| what Bedrock lacks, said once | `src/portkit/converters/recipes.py:321-326` |
| Mekanism's reasons | `src/portkit/adapters/mekanism/recipes.py:41-...` |
| Create's reasons | `src/portkit/adapters/create/__init__.py:84-...` |
| Alloy Forging's reasons | `src/portkit/adapters/alloy_forgery/forge.py:146-194` |
| the agent's prompt carries the refused file | `src/portkit/agent/residue.py:385-404`, `420-448` |
| the tick component | `src/portkit/adapters/farmersdelight/cooking_pot.py:598-599` and the runtime's note `src/portkit/adapters/farmersdelight/runtime/cooking_pot.js:9-10` |
| the container component | `src/portkit/converters/blocks.py:6660-6669`, `6735` |
| the container read from script | `src/portkit/ingame/runtime/ingame.js:348` |
| the shared storage helpers | `src/portkit/runtime/station_storage.js:16-104`, `src/portkit/runtime/station_core.js:16-23` |
| the Script API pins and the entry script | `src/portkit/converters/station_kit.py:34-51`, `203-211` |
| the reusable-pieces audit for #239 | `docs/adapter-audit-2026-10-15.md:172-182` |
| the template list and the one-design-PR-each rule | `docs/brainstorm-2026-10-15-scaling.md:84` |
