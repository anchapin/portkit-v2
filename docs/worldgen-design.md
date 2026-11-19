# Worldgen design (issue #281)

**Status: design spike.** This document answers issue #281's design questions
with concrete picks. **No production code is built in this PR** — the only file
this PR adds is this document. Every "recommended first slice" below is a
*recommendation*, not a commitment; the picks are written so a reviewer can
accept, change or reject each one independently.

Every claim about what this repository already does is cited to a
`path:line` in this worktree. Every claim about an external source is
attributed to the source *as this repository cites it*, with the citation's own
`path:line`; see "Sources and their reachability" for what could and could not
be verified from this VM.

---

## 1. What the repository already does with worldgen

Worldgen touches this codebase in five places. They are listed here so the
picks below are grounded in what exists, not in a fresh design.

| Touchpoint | What it does today |
|---|---|
| `src/portkit/converters/features.py` | The only converter that *writes* worldgen. Reads Java `worldgen/configured_feature` + `worldgen/placed_feature` + Forge/NeoForge `biome_modifier` files and writes Bedrock `features/<name>.json` (`minecraft:ore_feature`, `minecraft:geode_feature`) and `feature_rules/<name>.json` (`minecraft:feature_rules`) — `src/portkit/converters/features.py:1-14`, `:71-79`, `:539-608`. |
| `src/portkit/data/worldgen.py` | The cited reference tables the converter reads: Java biome tag → Bedrock biome filter, Java block tag → vanilla blocks, Java generation step → Bedrock placement pass, per-dimension y bounds, geode field ranges, the plant-patch feature family (`:37-47`, `:54-61`, `:81-84`, `:92-93`, `:141-144`, `:160-167`, `:187-189`). |
| `src/portkit/biomecode.py` | Reads Fabric's `BiomeModifications` attachments out of the jar's bytecode and hands them to `converters/features.py` as modifier-shaped rows (`src/portkit/biomecode.py:1-58`, `:667-712`, `:747-784`). |
| `src/portkit/worldgen.py` | Files *leftover* worldgen as residue: `code_worldgen` for a file typed with the mod's own Java class, `other_mod_data` for data only another mod reads (`src/portkit/worldgen.py:1-41`, `:48-50`, `:87-89`, `:223-253`, `:375-414`). |
| `src/portkit/agent/residue.py` | The residue reason classes: `worldgen_feature` (`:123-124`), `code_worldgen` (`:233-236`), `other_mod_data` (`:237-241`). |

The pipeline wires them in this order: Fabric bytecode attachments are read and
decided (`src/portkit/pipeline.py:588-601`), `converters/features.convert` runs
over the data files (`:602-608`), leftovers become `unowned`
(`src/portkit/pipeline.py:51-78`, `:627`) and are then re-filed by
`portkit.worldgen.refine` (`:669-672`).

### Is worldgen "currently reported as `unowned`"?

The issue's premise is only partly true of this tree, and the doc repeats the
corrected version:

* **What is converted today.** A Java ore that a Forge/NeoForge biome modifier
  adds, or that a Fabric mod attaches in code, becomes a Bedrock ore feature
  plus a feature rule (`src/portkit/converters/features.py:539-608`). A geode
  becomes a Bedrock geode feature (`src/portkit/converters/features.py:421-520`).
  The configured and placed feature files such a feature reads are *consumed*
  (`src/portkit/converters/features.py:609`), so they are no longer
  `unowned`.
* **What is still `unowned`.** Everything under `data/<ns>/worldgen/` that no
  converter claimed: worldgen built only from `minecraft:` types (the core
  residue rule says exactly this: "Worldgen built from `minecraft:` types only
  stays `unowned` (a real #281 gap)", `src/portkit/worldgen.py:18-20`), and
  placed features with only vanilla placements even when the feature they place
  is code (`src/portkit/worldgen.py:19-20`). The board reports this class as
  `unowned [data/<ns>/worldgen/]`: 6 mods, 631 files
  (`docs/gauntlet.md:39`, `:219`).
* **The "50 files" figure.** The issue's example, `data/mythicmetals/worldgen/`,
  cannot be verified from this VM: the Mythic Metals jar is not in the worktree
  (no `*.jar` under `fixtures/`) and there is no network access (see §7). What
  the repository does record about that mod is the *measured* conversion result
  of its ore slice: "Measured on Mythic Metals 0.24.6+1.21: 22 of 25 ores
  convert (17 Overworld, 4 Nether, 1 End); aquarium, osmium and prometheum are
  4a residue" (`docs/decisions.md:1645-1647`), and the manifest pins that mod
  as Fabric 1.21.1 (`fixtures/real/mods.toml:104-114`) — the loader whose
  attachments are read from bytecode (`src/portkit/biomecode.py:1-58`). So the
  number this design uses for Mythic Metals is *ores converted*, not files
  `unowned`.

### How residue is reported today

* A converter that understood a file and refused it files it with an explained
  kind and a reason naming what could not be stated exactly — the pattern is
  `worldgen_feature` (`src/portkit/agent/residue.py:123-124`,
  `src/portkit/converters/features.py:642-643` refusing with the reason, and
  `:705-706` filing the refusal).
* A file no converter opened is grouped by directory as `unowned`
  (`src/portkit/pipeline.py:51-78`), and the board splits `unowned` by
  directory to make a reason class per directory
  (`docs/gap-leaderboard.md:225-229`, `docs/gauntlet.md:14`).
* A reason class only counts as *explained* when it is in the agent's
  `SKIP_KINDS` (`docs/gap-leaderboard.md:225-229`,
  `src/portkit/agent/residue.py:95-325`).

---

## 2. Question A — what Bedrock can express

### A.1 Feature rules and features

Bedrock's worldgen model as this repository uses it is two documents: a
*feature* (`features/<name>.json`) and a *feature rule*
(`feature_rules/<name>.json`) that attaches the feature to biomes with a
placement pass and a scatter distribution. The repository's own citation of
Mojang's text is in the converter's module docstring:

> "Bedrock builds the same thing from two: a `features/<name>.json`
> `minecraft:ore_feature` and a `feature_rules/<name>.json` that attaches it to
> biomes with a placement pass and a scatter distribution (Mojang/bedrock-samples
> documentation/Features.html, 'Attaching features': 'Features must be attached
> to at least one biome in order to show up in the world ... via a feature rule
> definition')" — `src/portkit/converters/features.py:8-13`.

The set of feature documents Bedrock accepts is listed in this repository's
validator, which says it is "Every feature type Mojang/bedrock-samples
documentation/Features.html lists (#281)"
(`src/portkit/validate/rules.py:87-88`), enumerated at
`src/portkit/validate/rules.py:69-78`:

`aggregate_feature`, `beards_and_shavers`, `cave_carver_feature`,
`conditional_list`, `fossil_feature`, `geode_feature`,
`growing_plant_feature`, `height_difference_filter_feature`,
`horizontal_tree_decoration_feature`, `multi_block_feature`,
`multiface_feature`, `multipart_block_column_feature`,
`nether_cave_carver_feature`, `ore_feature`, `partially_exposed_blob_feature`,
`rect_layout`, `scan_surface`, `scatter_feature`, `sculk_patch_feature`,
`search_feature`, `sequence_feature`, `single_block_feature`,
`snap_to_surface_feature`, `structure_template_feature`,
`surface_relative_threshold_feature`, `tree_feature`,
`underwater_cave_carver_feature`, `vegetation_patch_feature`,
`weighted_random_feature`.

**Pick A.1 — the expressible set is exactly this list.** The design targets
the feature types in that list and nothing else; a Java feature with no
Bedrock counterpart is residue, not a guess.

*Alternatives rejected:*
- *Convert any feature type and let the validator judge* — rejected: the
  validator only checks shape and cross-references
  (`src/portkit/validate/rules.py:63-68`), so a shape-valid document can still
  be semantically wrong; #87 forbids guessing.
- *Restrict to the two types this repository already writes* (`ore_feature`,
  `geode_feature`) — rejected as too narrow: it would leave `scatter_feature`,
  `single_block_feature` and `structure_template_feature` — the three types
  issue #281's first-slice suggestion names — permanently unaddressed.

### A.2 The four feature families the issue names

| Java | Bedrock | Pick |
|---|---|---|
| ore | `minecraft:ore_feature` | **Pick A.2a — convert.** Bedrock has a first-class ore feature; the repository already writes it (`src/portkit/converters/features.py:649-660`) and the validator cross-checks its `replace_rules` blocks (`src/portkit/validate/xrefs.py:310-315`). |
| scatter | `minecraft:scatter_feature` | **Pick A.3a — convert, but not in the first slice.** Java's scatter family is the plant patch family (`random_patch`, `flower`, `no_bonemeal_flower`, `simple_block`, plus the `random_selector`/`simple_random_selector` choosers) — the table `src/portkit/data/worldgen.py:187-189` names exactly these. The repository's own decision on it is "5a patches stay residue with reasons until a corpus mod's patch clears the biome/removal/code gates; then the tries/xz_spread scatter mapping (Java's `nextInt(s+1)-nextInt(s+1)` offsets vs Bedrock's `triangle`) is decided on that case" (`docs/decisions.md:1582-1585`). Pick A.3a adopts that: the mapping is decided on a real corpus case, not on fixtures. |
| single-block | `minecraft:single_block_feature` | **Pick A.4a — treat as a scatter-family member, i.e. covered by the A.3a gate.** `minecraft:simple_block` is already listed as part of the plant patch family in this repository's tables (`src/portkit/data/worldgen.py:187-188`), so it is not a separate design problem. |
| structure-template feature | `minecraft:structure_template_feature` | **Pick A.5a — do not convert Java `.nbt` templates in this design.** Java's structure templates are `.nbt` files under `data/<ns>/structure[s]/`; this repository files them as residue and never rewrites them (`src/portkit/worldgen.py:88-89`, `:322-355`, `:411-414`), and its decision record rejects "shipping the templates as standalone `.mcstructure` features (Java never spawns them outside a village)" (`docs/decisions.md:1762-1764`). |

### A.3 Custom biomes and their limits

*Bedrock's biome document* is a supported pack document here — the validator
lists `"biomes": ("minecraft:biome",)` among the behavior-pack document keys
(`src/portkit/validate/rules.py:85`), and `src/portkit/converters/features.py`
uses Bedrock biome *tags* to filter a rule's biomes
(`src/portkit/data/worldgen.py:37-47`).

**Pick A.6a — a Java biome is not converted, but a Java biome *tag* may be,
when it resolves to a vanilla dimension tag.** The limits this design accepts:

1. Only the three vanilla dimension tags have a Bedrock map today:
   `minecraft:is_nether` → tag `nether`, `minecraft:is_overworld` → tag
   `overworld` or `overworld_generation`, `minecraft:is_end` → tag `the_end`
   (`src/portkit/data/worldgen.py:37-47`, with the per-tag evidence in the
   comments at `:20-36`).
2. A loader convention tag counts only when its pinned definition is exactly
   one vanilla dimension tag — today `c:is_overworld`, `c:is_nether`,
   `c:is_end` for the Fabric 1.21.1 tag set
   (`src/portkit/data/worldgen.py:95-117`).
3. Any other biome set is refused with the reason "only vanilla biome tags
   with a Bedrock biome tag map" (`src/portkit/converters/features.py:330-337`)
   and "other biome sets have no Bedrock biome map here"
   (`src/portkit/biomecode.py:703-704`).
4. A Java biome *id* (not a tag) has no Bedrock map in this design — refused
   at `src/portkit/biomecode.py:702-704`.

**Alternatives rejected:**
- *Write a Bedrock biome per Java biome tag* — rejected: a Bedrock biome file
  is terrain, and the repository states it converts nothing of the worldgen
  biome registry today (`docs/gauntlet.md:209`).
- *Guess a biome tag from a tag's name* — rejected: the decision record rejects
  "converting Fabric ores by the `<ore>_ore_biomes` tag naming convention (a
  guess, #87)" (`docs/decisions.md:1703-1704`), and the code refuses a tag
  that is "not the jar's own, a vanilla dimension tag, or a loader convention
  tag whose pinned definition is exactly one" (`src/portkit/biomecode.py:685-687`).

### A.4 Structures (`.mcstructure`) and dimensions

* **Structures.** Java ships structures as `.nbt` templates under
  `data/<ns>/structure[s]/` (`src/portkit/worldgen.py:88-89`); Bedrock's
  structure format is `.mcstructure`, which this repository does not write
  anywhere. **Pick A.7a — structures stay residue.** A template goes with the
  residue that names it, or stays `unowned` when nothing names it
  (`src/portkit/worldgen.py:22-33`, `:322-355`, `:411-414`). The template pool
  that places a structure is Java's own machinery: a pool whose
  `element_type` is the mod's own class is `code_worldgen`
  (`src/portkit/worldgen.py:14-16`, `:248-251`).
* **Dimensions.** Bedrock has a dimension document in the accepted document
  keys (`src/portkit/validate/rules.py:89`), but Java's dimension type is a
  *noise and height* definition, and this repository's mapping stops at the
  per-dimension y bounds (`src/portkit/data/worldgen.py:86-93`) used to refuse
  heights that reach outside the dimension. **Pick A.8a — a Java
  `dimension_type` is not converted** (see §5.2, D.1, for the reason class).

---

## 3. Question B — the Java → Bedrock mapping

The mapping this design proposes is the one this repository already implements
for the ore slice, plus the geode and patch rows already in its tables. It is
stated here as a design, with the code that carries it cited, so that a
reviewer can change a row without touching the prose elsewhere.

### B.1 The three Java files → the two Bedrock files

| Java | Bedrock | Where |
|---|---|---|
| `worldgen/configured_feature/<x>.json` of type `minecraft:ore` | `features/<x>.json` with `minecraft:ore_feature` | `src/portkit/converters/features.py:655-660` |
| `worldgen/placed_feature/<x>.json` | the *distribution* of `feature_rules/<x>_feature_rules.json` | `src/portkit/converters/features.py:290-325`, `:669-678` |
| `data/<ns>/{forge,neoforge}/biome_modifier/<x>.json` of type `<loader>:add_features` | `feature_rules/<x>_feature_rules.json`: `conditions.placement_pass`, `conditions.minecraft:biome_filter`, `distribution` | `src/portkit/converters/features.py:75-76`, `:626-630`, `:669-676` |

The mod's own placement (how many veins per chunk, where) has no Java
"biome modifier" equivalent on Bedrock's side: Bedrock's rule *is* the
attachment, so the placed feature's placements fold into the rule's
distribution, and the modifier's biome list and step become the rule's
conditions. The repository's module docstring states this pairing
(`src/portkit/converters/features.py:3-13`).

### B.2 Field-level rows

| Java | Bedrock | Note / citation |
|---|---|---|
| `config.size` | `count` | "The number of blocks to be placed" (`src/portkit/converters/features.py:27-29`) |
| `config.discard_chance_on_air_exposure` | same field name | "Chance of discarding placement if neighboring block is Air", 0..1 (`:31-32`) |
| each `config.targets` entry, in order | one `replace_rules` entry, in order | both editions try targets in order (`:33-36`); `state.Name` → `places_block`, `block_match` → `may_replace`, `tag_match` → the tag's members (`:36-41`, `:347-382`) |
| `minecraft:count` | `distribution.iterations` | (`:37`, `:298-300`) |
| `minecraft:in_square` | `x`,`z` uniform over `[0,15]` | (`:38-40`) |
| `minecraft:height_range` (`uniform`) | `y` uniform over `[min,max]` | (`:41-45`, `:265-287`) |
| `minecraft:height_range` (`trapezoid`, no plateau) | `y` triangle over `[min,max]` | "Bedrock's distributions have no plateau" (`:285`) |
| `minecraft:height_range` anchors `absolute` / `above_bottom` / `below_top` | the same y, per dimension bounds | Java and Bedrock bounds per dimension (`:241-259`, `src/portkit/data/worldgen.py:92-93`) |
| `minecraft:rarity_filter` | `distribution.scatter_chance` 1/N | "The 'scatter_chance' check happens once" (`:46-48`) |
| `minecraft:biome` placement | nothing extra (the rule's biome filter is the biome set) | (`:49-50`) |
| modifier `biomes` | `minecraft:biome_filter` | (`:51-52`, `src/portkit/data/worldgen.py:37-47`) |
| modifier `step` | `conditions.placement_pass` | `underground_ores`, `underground_decoration` → `underground_pass` (`src/portkit/data/worldgen.py:75-84`) |
| configured feature of type `minecraft:geode` | `features/<x>.json` with `minecraft:geode_feature` | field map at `src/portkit/converters/features.py:421-520`; the Java fields Bedrock has no field for are named in the note (`:653-654`) |
| configured feature of the plant patch family | **no row yet** | the mapping is deferred to a corpus case (`:621-626`, `docs/decisions.md:1582-1585`) |

### B.3 Rows the design refuses (each with the reason already in the code)

| Java shape | Why refused | Citation |
|---|---|---|
| `below_top` in the Nether | Java's top is y=255, Bedrock's is 127 | `src/portkit/converters/features.py:254-258`, `src/portkit/data/worldgen.py:92-93` |
| a trapezoid height with a plateau | Bedrock's distributions have no plateau | `src/portkit/converters/features.py:283-286` |
| a biome tag with no Bedrock biome tag map | only vanilla dimension tags map | `src/portkit/converters/features.py:330-337` |
| a feature some `remove_features` modifier names | "a Bedrock feature rule can't subtract" the biomes it names | `src/portkit/converters/features.py:590-596`, `:613-615`, `:712-715` |
| a rarity filter after a count above 1 | Bedrock checks the chance once for all iterations | `src/portkit/converters/features.py:307-314` |
| a feature placed by the mod's own placement type | that is the mod's code | `src/portkit/converters/features.py:149-156`, `:618-620` |
| a scatter/patch feature | the tries/xz_spread mapping is not decided | `src/portkit/converters/features.py:621-626` |
| a `.nbt` structure template | Java never spawns it outside a village | `docs/decisions.md:1762-1764`, `src/portkit/worldgen.py:22-33` |

### B.4 Rows the design does not cover at all (no code, no row)

* **Noise settings / density functions** (Java `worldgen/noise_settings/`,
  `density_function/`) — no reader in this repository. Not addressed further in
  §5.2.
* **Java biome definitions** (`worldgen/biome/`) and their placement
  (multi-noise biome source) — no reader; the biome registry is untouched
  (`docs/gauntlet.md:209`).
* **Template pools** that place vanilla structures — Java's pool machinery
  (selection, jigsaw placement) has no Bedrock equivalent in this design; a
  pool typed with the mod's own class is `code_worldgen`
  (`src/portkit/worldgen.py:14-16`).

---

## 4. Question C — the recommended first slice

### The issue's suggestion

The issue suggests **ore and simple scatter features from data files** as the
first slice.

### Pick C.1 — first slice = **ore features from data files**, and the scatter
half of the suggestion is **deferred** to a second slice.

**Why the ore half is confirmed:**

1. *It is the only family with a mechanical, fully cited mapping.* Every row
   in §B.2 above exists in code with its reason string
   (`src/portkit/converters/features.py:265-382`, `src/portkit/data/worldgen.py:20-117`).
   Nothing in the ore path needs a value that is not in the jar.
2. *It is the family with a measured result.* On the pinned Mythic Metals
   0.24.6+1.21, 22 of 25 ores convert (17 Overworld, 4 Nether, 1 End), the
   remaining three being residue for a stated reason
   (`docs/decisions.md:1645-1647`). On the geode side, Tinkers' Construct's
   earth geode converts (3 files) while 24 files of Botania flowers and
   Supplementaries' wild flax move from `unowned` to explained
   `worldgen_feature` residue (`docs/decisions.md:1586-1589`). Those are the
   numbers this design is judged against.
3. *Its attachment mechanism is known on both loaders.* Forge/NeoForge attach
   with a `biome_modifier` JSON (`src/portkit/converters/features.py:75-76`);
   Fabric attaches in code and is read from the bytecode
   (`src/portkit/biomecode.py:1-58`, `src/portkit/pipeline.py:588-601`).

**Why the scatter half is deferred (rejected for the first slice):**

* The scatter family is not one mapping but several: `random_patch` carries
  `tries`, `xz_spread`, `y_spread` and a per-block condition, while
  `simple_block` places one block state, and the two selectors pick one of
  their placed features (`src/portkit/data/worldgen.py:182-189`). The
  repository's own decision is to decide the scatter mapping "on that case",
  a real corpus patch, and not to build it on fixtures
  (`docs/decisions.md:1582-1585`).
* The repository refuses patches today, with the reason
  "Java scatters `tries` placements with xz_spread/y_spread offsets and
  per-block conditions, which no corpus mod's patch has reached a Bedrock
  mapping for yet" (`src/portkit/converters/features.py:621-626`).
* The gates that a patch must clear before it is even eligible are already
  written down: the biome tag must map (`src/portkit/converters/features.py:630`),
  no `remove_features` modifier may name it (`:613-615`), and no nested
  feature or placement may be the mod's own type (`:618-620`).

**Alternatives rejected for the first slice:**

* *Simple scatter (plant patch) first* — rejected: the scatter mapping is not
  decided, and the repository's own recorded preference is to decide it on a
  corpus case (`docs/decisions.md:1582-1585`); building it on fixtures would
  pre-empt that decision with a guess.
* *Structure templates (`.nbt` → `.mcstructure`) first* — rejected: the
  repository has rejected shipping templates as standalone `.mcstructure`
  features, because Java never spawns them outside a village
  (`docs/decisions.md:1762-1764`); a first slice built on it would ship
  structures Java does not place.
* *Custom biomes first* — rejected: nothing in the worldgen biome registry is
  converted (`docs/gauntlet.md:209`), and only three vanilla dimension tags
  have a Bedrock map (`src/portkit/data/worldgen.py:37-47`), so the first
  slice would be a one-row table.

**Second slice (recommendation, not a commitment):** the scatter/patch family,
once one corpus patch clears the gates above — the mapping decided on that
case, exactly as `docs/decisions.md:1582-1585` already prescribes.

---

## 5. Question D — what stays residue, and with which reason class

The repository's convention: a residue *kind* is the reason class; `unowned`
is split by directory into one class per directory
(`docs/gap-leaderboard.md:225-229`, `docs/gauntlet.md:14`); a kind counts as
*explained* only when it is in the agent's `SKIP_KINDS`
(`src/portkit/agent/residue.py:95-325`, `docs/gap-leaderboard.md:225-229`).

### 5.1 Already-filed residue (no new class needed)

| What | Kind | Reason class today |
|---|---|---|
| An ore/geode/patch the converter read but could not state exactly | `worldgen_feature` | `src/portkit/agent/residue.py:123-124`; filed at `src/portkit/converters/features.py:705-706` |
| A `remove_features` modifier over features Bedrock rules can't subtract | `worldgen_feature` | `src/portkit/converters/features.py:712-715` |
| A worldgen file typed with the mod's own Java class | `code_worldgen` | `src/portkit/agent/residue.py:233-236`; `src/portkit/worldgen.py:223-253` |
| Data only another mod reads | `other_mod_data` | `src/portkit/agent/residue.py:237-241`; `src/portkit/worldgen.py:255-320` |
| A `.nbt` template named only by such residue | `code_worldgen` / `other_mod_data` | `src/portkit/worldgen.py:322-355`, `:411-414` |
| Worldgen built only from `minecraft:` types, and vanilla-placed features of a code feature | `unowned` (`unowned [data/<ns>/worldgen/]`) | `src/portkit/worldgen.py:18-20`; board row `docs/gauntlet.md:39`, `:219` |

### 5.2 What stays residue under this design — proposed reason classes

These three are **proposed** classes for the gap this design does not close.
They are not in `SKIP_KINDS` today, so under the repository's rule 6 they
would *not* yet count as explained; adding them to `SKIP_KINDS` is part of
the follow-up implementation, not of this document.

| # | What stays residue | Proposed kind | Why it cannot be converted (reason class body) |
|---|---|---|---|
| D.1 | **Custom dimensions** — Java `data/<ns>/dimension_type/*.json` and `dimension/*.json`, with their generator settings and the dimension's biome source | `worldgen_dimension` | Bedrock's dimension document is a different object from Java's dimension type: Java's file is a height/noise/generator-settings definition (`src/portkit/data/worldgen.py:86-93` reads only its `min_y`/height bounds, and nothing else of it), and the generator settings it names (noise, biome source) have no mapping in this design (§B.4). A dimension file converted to a Bedrock dimension would invent terrain that Java never generates — the same rule the repository applies to a code-typed feature (`src/portkit/agent/residue.py:233-236`: "a Bedrock feature or feature rule would invent it"). |
| D.2 | **Noise-based terrain** — Java `worldgen/noise_settings/`, `density_function/`, and the noise settings a dimension type names | `worldgen_noise` | The repository reads no noise or density file at all: the only worldgen directories it recognises are `configured_feature`, `placed_feature` and `template_pool` (`src/portkit/worldgen.py:87-89`), so these files are outside every reader. Java's noise graph (densities, spline thresholds, final density) has no counterpart in the Bedrock feature/rule model this design uses (`src/portkit/validate/rules.py:69-78`); a converted file would be a terrain claim the pack cannot honour. |
| D.3 | **Biome placement** — Java biome definitions (`worldgen/biome/`) and the biome source that places them (multi-noise, fixed, or the per-dimension biome list) | `worldgen_biome` | Java's biome placement decides *which* biome a column gets from noise; Bedrock decides biomes by the terrain generator, not from a data-driven biome source. The repository converts nothing of the worldgen biome registry (`docs/gauntlet.md:209`), and its biome handling is limited to *tags used as a rule filter* (`src/portkit/data/worldgen.py:37-47`, `src/portkit/converters/features.py:328-344`). A biome file converted on its own would claim a biome the pack's terrain never produces. |

Naming follows the repository's convention (lowercase `snake_case` kind, one
sentence saying what Bedrock cannot carry, the way `worldgen_feature`,
`code_worldgen` and `other_mod_data` read — `src/portkit/agent/residue.py:123-124`,
`:233-241`).

**Rejected alternatives for these three:**
- *Leave them `unowned`* — rejected: `unowned` is "no converter claims yet"
  (`src/portkit/pipeline.py:74-77`), which says nothing about *why* Bedrock
  cannot hold them, and the board counts `unowned` per directory as a general
  work item (`docs/gauntlet.md:219`, `:52`), not as an explained class.
- *Convert a dimension's y bounds only* — rejected: the bounds alone are not
  a dimension; they are read today only to refuse an ore whose height leaves
  the Bedrock dimension (`src/portkit/converters/features.py:639-641`).

### 5.3 The in-game check this design inherits

A converted rule is checked in a real Bedrock server: `ore_generate` reads
fresh chunks of the rule's dimension and asserts one of the ore's blocks
appears in its height range, skipping a rule whose range holds none of the
blocks it may replace; `geode_generate` carries a test-only copy of the geode
rule so the geode is placed in every chunk (`docs/ingame-checks.md:22-23`).
Any first slice built from this design should be checked the same way; the
check list is generated from the converted `feature_rules/`
(`src/portkit/ingame/testpack.py:569-593`).

---

## 6. Verdict

* **This is a design spike.** No code is built in this PR: the only file it
  adds is `docs/worldgen-design.md`. Nothing in the picks above is wired in.
* **The picks, in one line each.**
  * A.1 — Bedrock's expressible feature set is the validator's feature-type
    list (`src/portkit/validate/rules.py:69-78`).
  * A.2a — ore features convert; A.3a — scatter converts, deferred to slice
    two; A.4a — single-block is part of the scatter family; A.5a — Java
    `.nbt` templates do not convert; A.6a — biome *tags* convert only when
    they resolve to a vanilla dimension tag; A.7a — structures stay residue;
    A.8a — Java dimension types do not convert.
  * B.1–B.3 — the Java→Bedrock row set and the refusal rows, each cited to the
    code that already carries it.
  * C.1 — **recommended first slice: ore features from data files** (Java
    `configured_feature` + `placed_feature` + `biome_modifier`, or the Fabric
    code attachment), with the scatter half of the issue's suggestion deferred
    to a second slice. This is a recommendation, not a commitment.
  * D.1–D.3 — custom dimensions, noise-based terrain and biome placement stay
    residue, with the proposed reason classes `worldgen_dimension`,
    `worldgen_noise` and `worldgen_biome`.
* **What this design does not answer.** The scatter (patch) mapping, in
  detail: it is decided on a real corpus case, not here
  (`docs/decisions.md:1582-1585`). No in-game result is claimed anywhere in
  this document: none was run for this PR, and the in-game numbers quoted
  above are the repository's recorded measurements, cited as such.

---

## 7. Sources and their reachability

* **External sources could not be fetched from this VM.** Attempts to reach
  `raw.githubusercontent.com`, `learn.microsoft.com`, `minecraft.wiki` and
  `github.com` over HTTPS and HTTP all failed at the transport layer (no HTTP
  response), so this document asserts nothing about the *current* content of
  those pages.
* Therefore every external claim here is stated as *"this repository's
  citation of <source> says X"*, with the `path:line` of the citation:
  * Mojang/bedrock-samples `documentation/Features.html` — cited by this
    repository at `src/portkit/converters/features.py:8-13` (features must be
    attached to at least one biome via a feature rule), `:47-48` (the
    `scatter_chance` check happens once), `:425-426` (the geode field map),
    `src/portkit/data/worldgen.py:136-137` ("Earlier passes in the list are
    guaranteed to occur before later passes"), `:154-159` (the geode field
    ranges), `src/portkit/validate/rules.py:87-88` (the list of feature types
    the page lists).
  * MicrosoftDocs/minecraft-creator `FeaturesIntroduction.md` and
    `Features/minecraftOre_feature.md` — cited at
    `src/portkit/data/worldgen.py:13-16`, `:75-80`.
  * Mojang/bedrock-samples `behavior_pack/biomes/*.biome.json` — cited at
    `src/portkit/data/worldgen.py:11-12`, `:22-36`.
  * misode/mcmeta `1.20.1-data` / `1.21.1-data` (the pinned vanilla versions) —
    cited at `src/portkit/data/worldgen.py:9-10`, `:22-36`, `:49-53`, `:86-93`.
  * minecraft.wiki "Configured feature" and "Amethyst Geode" (oldid 3811952) —
    cited at `src/portkit/data/worldgen.py:169-180`, `:182-186`,
    `src/portkit/converters/features.py:425-426`.
  * Fabric API `fabric-convention-tags-v2` 2.12.0+c3656daa19 and
    `BiomeSelectors.java` — cited at `src/portkit/data/worldgen.py:95-107`,
    `src/portkit/biomecode.py:44-46`.
* **Repository records used as measurements** (they are the project's own
  recorded runs, not runs made for this PR): the ore and geode measurements at
  `docs/decisions.md:1586-1589` and `:1645-1647`; the board row at
  `docs/gauntlet.md:39`, `:219`; the decision entries at
  `docs/decisions.md:1550-1596`, `:1598-1650`, `:1660-1707`, `:1709-1765`.
