# Single-mod code audit (#245 step 1), 2026-10-15

Audit of `src/portkit` (Python and the fixed runtime JavaScript) at develop
`6e1fc1d` for code that names one mod's namespace or only serves one mod,
toward #245's goal: per-mod adapters and a namespace-free core. This is step 1
(the audit) plus step 4's lint in allowlist mode
(`tests/test_core_namespace_free.py`, `tests/data/core_namespace_allowlist.json`).
**No code moves in this PR**, and the adapter interface (section 6) is a sketch
with open picks for Alex.

## 1. Summary

- `src/portkit` is **37,132 lines** of `.py` + `.js`. About **10,300 lines
  (28%)** serve a single mod or library:

  | Family | Lines | Corpus / deco mods it serves |
  |---|---:|---|
  | Waystones (converter + runtime) | 4,573 | `waystones` (BetterEnd's `data/waystones/tags` compat folder is refused by the version check) |
  | Farmer's Delight stations (cutting board, cooking pot, stove, skillet, feasts) | ~4,580 | `farmers_delight_neoforge`, `farmers_delight_fabric` (Refurbished Furniture and Supplementaries ship only `data/farmersdelight/tags` compat folders) |
  | Per-mod recipe residue tables in `recipes.py` | ~766 | Tinkers, Silent Gear, Mekanism, Create, BetterEnd/BCLib, Mythic Metals, Supplementaries |
  | Alloy Forgery | 351 | `mythicmetals` (its forging recipes and forge data) |
  | Mod-specific load conditions in `conditions.py` | ~60 | `mekanism`, `tinkers_construct` (Mantle) |

  Citadel books (`books.py` + `book*.js`, 698 lines) are a **library** format
  (any Citadel mod; the corpus has one: `alexs_mobs`), so they count as a
  library adapter, not single-mod code.
- **Lint baseline: 313 mod namespace literals** in 11 core files (section 5).
  `recipes.py` (166) and `cooking_pot.py` (76) carry most of them. The runtime
  JS has **0** literals: every runtime gets its namespace from its data table,
  but four runtimes are still single-mod by behaviour.
- The seams already exist. Every single-mod converter reaches the core through
  a few hooks: `stations.station_blocks/station_loot/station_textures/
  station_lang_keys/convert`, `CONVERTERS` in `converters/__init__.py`,
  `recipes.py`'s per-type reason lookups, `conditions.py`'s condition-type
  `if` chain, and the residue kinds in `agent/residue.py` `SKIP_KINDS`. An
  adapter registry can replace those hooks one at a time without changing pack
  output.

How this was measured: the lint's rule (code string literals; section 5); a
broad case-insensitive scan for mod words in code, identifiers, comments and
docstrings; and reading every hit. Line counts are `wc -l` at `6e1fc1d`.
"Mods that use it" comes from the 2026-10-14/15 measurements in
`docs/decisions.md` and `notes/history`: which corpus (13) and deco (7 with
conversions) packs change when the code changes.

## 2. Inventory by module

Classes: **A** = adapter-only (moves into `adapters/<mod>/`), **D** = per-mod
data file (a table that can leave code), **P** = reusable piece to promote
toward #239's templates (stays in core, made generic).

### 2.1 Waystones: `waystones` only (A)

| Module | Lines | What | Class |
|---|---:|---|---|
| `converters/waystones.py` | 2,480 | Whole module. `NS = "waystones"` and 41 literals (tags `data/waystones/tags/...`, `waystones:*` state/component names). Block lists with citations (`WAYSTONE_BLOCKS`, `SHARESTONE_*`, `PORTSTONE_*`, `WARP_PLATE_*`, `WARP_PORTAL_*`, `FLEETING_MEMORIAL_*`), scroll/warp stone/memorial tables, `MESSAGES`, `SOUNDS`, `FIXED_CONDITIONS` + `requirements()` (the warp-requirements parser), rune overlays (`_runes`, `_rune_overlay`, `derived_textures`, `DYE_COLORS`), `waystone_blocks`, `loot_names`, `lang_keys`, `convert` | A (tables D) |
| `runtime/waystone.js` | 1,620 | Records, activation, menus, teleport, warp plate, portal, scrolls, warp stone, memorials, `registerWaystones` | A |
| `runtime/waystone_core.js` | 473 | Pure logic (cost, targets, attune, portalPos, memorialPos, nearestWaystone, wearBreaks) | A (see P below) |
| `data/waystones_config_defaults.json` | 3.3 KB | Cited config defaults per version | D (moves with the adapter) |
| Core hooks | | `stations.station_blocks` (falls back to `waystone_blocks`), `station_loot`, `station_textures`, `station_lang_keys`, `stations.convert` (splits loot by `waystones.loot_names`); residue kind `waystone` in `agent/residue.py` | hooks |

Tests: `tests/test_waystones.py` (1,827), `tests/js/{waystone,memorial,scrolls,warp_portal,warp_plate,warp_stone}.test.mjs` (3,455).

Reusable inside it (P): the form helper `show(form, player, retries)` with the
`UserBusy` retry (also copied in `book.js`), the item-use **hold timer**
(`scrollUsed`/`scrollTicks`/`heldAt`: start on itemUse, stop on slot switch or
`entityHurt`), `land()` (safe landing beside a block), `destroyCommand` (also
in `feast_core.js`), per-entity cooldown tracking, the "records in world
dynamic properties" store (`recordKey`/`orderKey`), and the
`requirements()` cost-expression evaluator. These are the parts a #239
"scripted machine" or "form GUI station" template would reuse.

### 2.2 Farmer's Delight stations: `farmers_delight_neoforge`, `farmers_delight_fabric` (A)

| Module | Lines | What | Class |
|---|---:|---|---|
| `converters/stations.py` | 834 (~523 FD) | **FD part:** `CUTTING`/`COOKING` types, `FD_NEO`/`FD_FAB` pins, `_src` (hardcodes `vectorwing/farmersdelight/`), `CUTTING_BOARD_BLOCKS`, `FORTUNE_OPTION`, `_FD_VERSIONS`, `ABILITY_TAGS`/`NEOFORGE_KNIFE_SHARED`/`ABILITY_SOURCES`/`_ABILITY_TYPES`, `CuttingBoardSpec`/`_cutting_spec`, `_unsupported` (checks `namespace == "farmersdelight"`), `_cutting_entry`, `_overlaps`, `_component`, `_convert_cutting`. **Generic part:** module docstring, `SCRIPT_*`, `ENTRY`, `Overlay`, `DerivedTexture`, `FacingBlock`, `BEDROCK_TOOL_TAGS`, `VANILLA_SOUNDS`, `_Resolver` (its two FD literals are the ability-type branch), `_recipe_id`, `runtime_source`, `_js_module`, `_lang_key`, `convert` (the `main.js` wiring), `_shipped_sounds` | split: A (FD) / P (generic) |
| `converters/cooking_pot.py` | 637 | 76 literals: `FD_CRAFT_REMAINDERS` (72 `farmersdelight:*` items, cited `ModItems`), `HEAT_SOURCES`, `SUPPORT_STATE`, `COOKING_POT_BLOCKS`; `heat_table` (shared with the skillet), `_entry`, `convert` | A (`FD_CRAFT_REMAINDERS` D) |
| `converters/stove.py` | 395 | `STOVE_BLOCKS`, `LIT_STATE`, `HEAT_RULES`, `campfire_table` (shared with the skillet), `convert` | A |
| `converters/skillet.py` | 331 | `SKILLET_BLOCKS`, `_item` (iron-tier numbers, cited), `convert` | A |
| `converters/feasts.py` | 568 | `FEASTS` (serving items, leftovers, cited), `_FEAST_SHAPES`, `feast_blocks`, `loot_names`, `convert`; residue kind `feast` | A (`FEASTS` D) |
| `runtime/cutting_board{,_core}.js` | 161 + 113 | cutting board | A |
| `runtime/cooking_pot{,_core}.js` | 243 + 414 | cooking pot | A |
| `runtime/stove{,_core}.js` | 259 + 193 | stove | A |
| `runtime/skillet{,_core}.js` | 410 + 206 | skillet block + held item | A |
| `runtime/feast{,_core}.js` | 73 + 57 | feasts | A |
| `data/recipes.py` | 183 | vanilla campfire recipes fetched for the stove's table (vanilla data, used only by FD's stove) | P (vanilla data fetcher; stays core) |
| `data/config_flag_defaults.json` `values` | | `farmersdelight.cuttingBoardFortuneBonus` (2 entries) | D (already data) |
| Core hooks | | `recipes.STATION_TYPES` (two `farmersdelight:` literals), `recipes.STATION_SHARED_TYPES` (campfire), `stations.station_blocks`/`station_loot`/`convert`, `loot.convert(station_tables=)`, residue kinds `station_recipe` (generic name) and `feast`; `cli.py` `reference fetch` help mentions the stove | hooks |

Tests: `tests/test_{stations,cooking_pot,stove,skillet,feasts}.py` (1,338),
`tests/js/{cutting_board,cooking_pot,stove,skillet,feast}.test.mjs` (1,308).

Reusable inside it (P): `station_storage.js` (94 lines, already shared:
`loadStored/saveStored/describe/rebuild/give/dropStored/play/centre`), plus
copies that should become shared helpers: `storageKey` (4 copies in the
`*_core.js` files), `COUNTER_CLOCKWISE`/`STEP` + `ejectOffset`/`spawnOffset`
(3 copies), `keyOf/load/save/view/facingOf` (repeated in each runtime),
`enchantLevel` (cutting board, stove), and the heat rule (`isHeated`,
`trayState`, `blockMatches`; cooking pot, skillet). The generic recipe-table
pattern (data table written from recipe JSON + fixed runtime + `main.js`
entry) is the core of a #239 "scripted machine" template.

### 2.3 Per-mod recipe residue tables in `converters/recipes.py` (D)

Lines 138–903 of 1,790 (~766 lines, most of the 166 literals):

| Table | Lines | Mods | Literals |
|---|---:|---|---|
| `_CODE_RECIPES` (+ the generic special-recipe rule in `code_recipe_reason`) | 161–290 (130) | BetterEnd, BCLib, Mythic Metals, Tinkers, Silent Gear, Mekanism, Create, Supplementaries | 16 |
| `_FLUID_RECIPES` + `_tinkers`, `_TC_*` | 310–416 | Tinkers (30 types), Create (2) | 32 |
| `_MODULAR_TOOL_RECIPES` + `_tc_tool`, `_sg_gear`, `_TC_*` | 417–593 | Tinkers (39), Silent Gear (9) | 49 |
| `_CREATE_MACHINE_RECIPES` + `_create`, `_NO_BEDROCK_KINETICS/BASIN_FLUID/CHANCE` | 613–748 | Create (21) | 21 |
| `_MACHINE_RECIPES` + `_mek`, `_NO_BEDROCK_MACHINE/CHEMICAL/MB` | 594–612, 749–903 | Mekanism (46); the Create table is merged in | 46 |
| `STATION_TYPES` | 81 | Farmer's Delight | 2 |
| `_KNOWN_UNSUPPORTED` comment / `FORGING` import | 76, 121–131 | Alloy Forgery | 0 |

The `*_reason()` lookups (`fluid_recipe_reason`, `modular_tool_reason`,
`machine_recipe_reason`, `code_recipe_reason`) and the residue kinds they feed
(`fluid_recipe`, `modular_tool`, `machine_recipe`, `code_recipe`) are
**generic** and stay in core; only the tables move. Each table is pure data
(type -> reason string built from shared "Bedrock lacks X" phrases), so it can
live in its mod's adapter as a dict or a JSON file (pick 5).

Tests: `tests/test_{code_recipes,fluids,modular_tools,mekanism_machines,create_machines}.py` (921).

### 2.4 Alloy Forgery: `mythicmetals` (A)

| Module | Lines | What | Class |
|---|---:|---|---|
| `converters/alloy_forge.py` | 351 | `FORGING = "alloy_forgery:forging"`, forge data dirs, `forging_reason`, `forge_names`, `_forge_reason`, `convert` (claims `machine_data`) | A |
| Core hooks | | `CONVERTERS` entry; `recipes.py` imports `FORGING, forge_names, forging_reason` and calls them inside `convert` (L1512); residue kind `machine_data` (generic name, Alloy Forgery text) | hooks |

Tests: `tests/test_alloy_forge.py` (189).

### 2.5 Citadel books: `alexs_mobs` today, any Citadel mod (library adapter)

| Module | Lines | What | Class |
|---|---:|---|---|
| `converters/books.py` | 590 | `CITADEL`, `SOURCES` (4 Citadel URLs), `SCREEN = ".../citadel/client/gui/GuiBasicBook"` (bytecode superclass match), `page_text` (Citadel's `readInPageText`), `read_book`, `book_screens`, `plan`, `convert` | library adapter `citadel` (format reader) |
| `runtime/book.js`, `book_core.js` | 65 + 43 | form-based page viewer; namespace-free | P (form viewer for #239's "form GUI" template) |
| Core hooks | | `converters/__init__.py` calls `books.plan/lang_text/convert`; `lang.convert(book_text=)`; `stations.convert(extra_entries=)`; residue kind `book` | hooks |

Tests: `tests/test_books.py` (248), `tests/js/book.test.mjs` (77).

### 2.6 Mod-specific code inside generic modules

| Module | Where | What | Class |
|---|---|---|---|
| `conditions.py` (1,016) | `LoadContext._one` L409–415, L424–427, `_combination` L456–485 | `mekanism:mod_version_loaded` (Mekanism), `mantle:tag_filled` / `mantle:tag_combination_filled` (Mantle = Tinkers' library) | A (condition handlers; Mantle as a library adapter) |
| `conditions.py` | config flags | `supplementaries:flag`, `mythicmetals:*_enabled`, `farmersdelight:vanilla_crates_enabled`, `tconstruct:config` are generic flag conditions read from `data/config_flag_defaults.json` (7 cited entries: Mythic Metals 3, FD 2, Supplementaries 1, Tinkers 1; plus 2 FD `values`) | D (already data; keep) |
| `converters/items.py` (901) | `_OVERRIDE_KINDS` L149–169, `_READOUT_PREDICATES` L174 | override predicate names include mod ones without namespaces (`encoded`, `midas_gold_count`, `clipboard_type`, `tooting`, `dyed`, `is_primed`; readouts such as `radiation`), cited per mod | D (a known-predicates table; the lint can't see it, no namespace) |
| `converters/items.py` | `fluid_container_reason` | generic (`*:fluid_container` loader); Tinkers only in the comment | core |
| `agent/residue.py` (760) | `SKIP_KINDS` | kinds `feast`, `waystone` are single-mod; `machine_data`'s text names Alloy Forgery | A (adapter-registered kinds) |
| `converters/__init__.py` (97) | imports + `convert_all` | imports `alloy_forge`, `books`, `stations`; special-cases `books` and station hooks | hooks |
| `converters/blocks.py` (4,168) | station parameters | generic: `stations=` (`FacingBlock`), overlays, `toggle.js`; mods appear in comments only | core |
| `cli.py` (1,189) | help text | `--config` examples `mythicmetals.enableDusts`, `farmersdelight.cuttingBoardFortuneBonus`; `reference fetch` names the FD stove | core (prose) |
| `blockcode.py`, `entities.py`, `paths.py`, `models.py`, `lang.py`, `loot.py`, `textures.py`, `pack.py`, `icon.py`, `meta.py`, `agent/*.py` | comments/docstrings | mods named as the motivating example or measurement (e.g. "Waystones' fleeting memorial", Mantle's register helper shape) | core (no action) |

### 2.7 Shared runtime JS (already generic)

| File | Lines | Used by | Class |
|---|---:|---|---|
| `runtime/station_storage.js` | 94 | all FD stations + Waystones | P (already shared) |
| `runtime/toggle.js` | 39 | any mod (`blocks.py` facing+boolean toggles, #215/#219) | core |
| `runtime/book.js` / `book_core.js` | 108 | Citadel books | P |

## 3. Reusable pieces to promote toward #239

| Piece | Today in | Template it feeds |
|---|---|---|
| Data table + fixed runtime + `main.js` entry (`runtime_source`, `_js_module`, `ENTRY`, `SCRIPT_*`) | `stations.py` | all scripted templates |
| `FacingBlock` (station block spec), `Overlay` + `DerivedTexture` (baked tinted overlays) | `stations.py` | scripted machine (block shell) |
| `station_storage.js` (+ `storageKey`, eject offsets, `enchantLevel`) | runtime | scripted machine (inventory) |
| Heat rule (`isHeated`, `trayState`, `blockMatches`, `heat_table`) | cooking pot / skillet / stove | scripted machine ("needs a heat source") |
| Form helper with busy retry + menu builder (`menu()`), rename form | `waystone.js`, `book.js` | form GUI station |
| Book viewer (`book.js`/`book_core.js`) | runtime | form GUI (read-only pages) |
| Item hold timer (itemUse start, slot switch / hurt stop) | `waystone.js` | held-item actions |
| World dynamic-property record store (`recordKey`, order, per-player lists) | `waystone*.js` | any template with world state |
| Recipe resolver (`_Resolver`: items/tags/tool abilities -> Bedrock) | `stations.py` | every recipe-driven template |
| Cost expression evaluator (`requirements()` + `cost()`) | Waystones | machine energy/XP costs |
| `toggle.js` | runtime | already a template |

## 4. What the scan does not see

- **Identifiers and f-strings.** `waystones.py` builds most ids as
  `f"{NS}:..."`, so its 41 literals understate a 2,480-line module. The lint
  ratchets literals; the audit above is the full picture.
- **Namespace-free single-mod data**: `_OVERRIDE_KINDS` / `_READOUT_PREDICATES` predicate names, FD's
  `ABILITY_TAGS` keys, Waystones' message keys built from parts.
- **JSON data** (`src/portkit/data/*.json`) is not scanned (per-mod data by
  design).
- **Runtime behaviour**: four runtimes are single-mod with 0 literals.

## 5. The lint (step 4, allowlist mode)

`tests/test_core_namespace_free.py` scans every `*.py` and `*.js` under
`src/portkit` except `src/portkit/adapters/` and fails on any mod namespace
literal not in `tests/data/core_namespace_allowlist.json`. The rule, documented
in the test:

- Only code string literals count: Python constants other than docstrings
  (f-string text included); JS `'…'`, `"…"`, `` `…` `` outside comments.
- A literal names namespace `ns` (once per literal) when: **A** it contains
  `ns:` + a path character, `ns` a known mod namespace; **B** the whole literal
  is `ns:path` with `ns` not a platform namespace (`minecraft`, `c`, `forge`,
  `neoforge`, `fabric`, `portkit`), which catches mods not on the list;
  **C** it is exactly a known mod namespace; **D** a known namespace is a
  `/`- or `.`-delimited segment (`data/waystones/...`,
  `block.farmersdelight.x`, `.../citadel/client/...`). C and D skip namespaces
  that are also words (`create`, ...).
- Known namespaces = every `assets/<ns>`/`data/<ns>` folder in the 13 corpus
  and 13 deco-set jars, plus `citadel`.

Ratchet: a count above the allowlist fails (with file, line and literal), and
a count below it fails too until the allowlist is lowered, so the total
only shrinks. Baseline **313**:

| File | Namespace: count |
|---|---|
| `converters/recipes.py` | tconstruct 72, mekanism 47, create 27, silentgear 10, mythicmetals 3, bclib 2, betterend 2, farmersdelight 2, supplementaries 1 (166) |
| `converters/cooking_pot.py` | farmersdelight 76 |
| `converters/waystones.py` | waystones 41 |
| `converters/stations.py` | farmersdelight 13 |
| `converters/books.py` | citadel 5 |
| `converters/stove.py` | farmersdelight 4 |
| `conditions.py` | mantle 3, mekanism 1 |
| `converters/alloy_forge.py` | alloy_forgery 2 |
| `converters/feasts.py` | farmersdelight 1 |
| `converters/skillet.py` | farmersdelight 1 |

When a mod joins the corpus or deco set, add its namespaces to
`MOD_NAMESPACES` in the test.

Until the moves land, a PR that has to extend single-mod code in place
(for example more Waystones or FD work) raises that file's count in the
allowlist in the same diff, where review sees it. The better fix is to put
the new code in an adapter once step 1 of section 7 exists.

## 6. Proposed adapter interface (sketch; picks open for Alex)

```python
# src/portkit/adapters/__init__.py
@dataclass(frozen=True)
class Adapter:
    name: str                                  # "waystones", "farmersdelight", "mantle", ...
    namespaces: frozenset[str]                 # Java namespaces it serves
    library: bool = False                      # Mantle, Citadel: serve other mods' jars
    # Refusal: None when this jar/version is supported, else the reason
    # (today's waystones._unsupported / stations._unsupported).
    supports: Callable[[SourceMod], str | None] = lambda mod: None
    # Station seams (today's stations.station_*):
    blocks: Callable[[SourceMod], dict[str, FacingBlock]] | None = None
    loot_names: Callable[[SourceMod], set[str]] | None = None
    derived_textures: Callable[[SourceMod], list[DerivedTexture]] | None = None
    lang_keys: Callable[[SourceMod], set[str]] | None = None
    station_recipe_types: frozenset[str] = frozenset()   # deferred to convert()
    convert: Callable[..., tuple[ConversionResult, str]] | None = None  # (result, main.js entry)
    # Residue seams:
    recipe_reasons: Mapping[str, tuple[str, str]] = {}   # java type -> (kind, reason)
    claim: Callable[[SourceMod], ConversionResult] | None = None  # e.g. Alloy Forgery data
    residue_kinds: Mapping[str, str] = {}                # kind -> SKIP_KINDS text
    # Load conditions:
    conditions: Mapping[str, Callable] = {}              # "mantle:tag_filled" -> handler

ADAPTERS: tuple[Adapter, ...] = (...)        # explicit, ordered (pick 3)
```

The core asks the registry at each existing seam (`stations.station_blocks`
becomes "union of `a.blocks(mod)` over adapters that support `mod`", etc.), in
registry order, so output order and bytes stay as today. Pure logic stays
pure; adapters get the same inputs the station converters get now.

**Picks for Alex** (recommendation first):

1. **Where adapters live.** (a) `src/portkit/adapters/<name>/` packages
   (`__init__.py` with the `Adapter`, `convert.py`, `runtime/*.js`,
   `data/*.json`), shipped in the same wheel. (b) Separate installable
   packages (`portkit-adapter-waystones`) found via entry points. Recommend
   (a) now; (b) only if third parties ever write adapters.
2. **What an adapter is keyed by.** (a) One adapter per Java mod id, plus
   library adapters for code many mods share (`mantle`, `citadel`) with
   `library=True`. (b) Mod ids only, with Mantle/Citadel left in core as
   "generic formats". Recommend (a): Mantle conditions and Citadel books are
   exactly the "known library" pattern #235/#237 will grow.
3. **How adapters register.** (a) An explicit ordered tuple in
   `adapters/__init__.py`. (b) Entry points. (c) Auto-discovery by scanning
   the package. Recommend (a): deterministic order (needed for byte-identical
   output), greppable, no import magic.
4. **Interface shape.** (a) A frozen dataclass of optional hooks (above)
   matching today's seams. (b) An abstract base class with methods.
   Recommend (a): most adapters fill one or two hooks (the recipe-table
   adapters only `recipe_reasons`).
5. **Per-mod tables: Python or JSON.** (a) Move the tables as Python dicts in
   the adapter first (pure cut/paste, md5 trivially identical), and extract to
   `adapters/<mod>/data/*.json` later where a #239 template wants to read them.
   (b) Go straight to JSON (the reason strings are built from shared "Bedrock
   lacks X" phrases, so JSON needs phrase keys). Recommend (a).
6. **Runtime JS bundling.** (a) Adapter JS lives in `adapters/<name>/runtime/`
   but ships at today's output paths (`scripts/portkit/<file>.js`), importing
   the shared core helpers (`./station_storage.js`, a new `./forms.js`) by
   relative path; `runtime_source` takes `(package, name)`. (b) Ship under
   `scripts/portkit/adapters/<name>/`. Recommend (a): (b) changes every pack's
   bytes and paths for no user gain.
7. **How tests move.** (a) `tests/adapters/<name>/test_*.py` and
   `tests/js/adapters/<name>/*.test.mjs`, with the node command widened to
   `tests/js/**/*.test.mjs` and the pytest node wrappers updated. (b) Tests
   stay where they are and only imports change. Recommend (a), moved in the
   same PR as the code each one covers.
8. **Promotion before or with the move.** (a) Extract the generic station
   kit (`FacingBlock`, `Overlay`, `DerivedTexture`, `_Resolver`,
   `runtime_source`/`_js_module`, `VANILLA_SOUNDS`, `BEDROCK_TOOL_TAGS`,
   duplicated JS helpers) into core modules first, as its own byte-identical
   PR, then move FD/Waystones on top. (b) Move first, deduplicate later.
   Recommend (a): the FD move is otherwise one huge diff through `stations.py`.
9. **`config_flag_defaults.json`.** (a) Keep it a single core registry of
   cited config defaults (it is data, read generically by `conditions.py`),
   and move only `waystones_config_defaults.json` into the Waystones adapter.
   (b) Split it per mod into the adapters. Recommend (a).
10. **Mod names in core comments and docstrings.** (a) Allowed: they cite the
    case that motivated generic code, and the lint ignores them. (b) Scrub
    them too. Recommend (a).

## 7. Migration order (smallest risk first)

Each step is its own PR with the same gate: pytest, node, `portkit eval`,
and **md5-identical pack trees** for the 13 corpus and 7 deco conversions
(plus `--mct` where a src file changes), and the allowlist lowered in the same
PR.

1. **Registry skeleton**: `src/portkit/adapters/__init__.py` with the
   `Adapter` type and an empty `ADAPTERS`; core seams consult it (no adapter
   yet). No output change. Lint scope already excludes `adapters/`.
2. **Load conditions** (~60 lines): `mekanism:mod_version_loaded` ->
   `adapters/mekanism`, `mantle:*` -> `adapters/mantle`. Allowlist -4.
3. **Alloy Forgery** (351 lines): self-contained; `recipes.py` asks the
   registry for `alloy_forgery:forging` instead of importing it. -2.
4. **Recipe residue tables** (~766 lines), one PR or one commit per mod:
   Mekanism, Create, Tinkers, Silent Gear, BetterEnd/BCLib, Mythic Metals,
   Supplementaries. Residue reasons only, so md5 is easy. -164.
5. **Generic station kit** (pick 8a): extract from `stations.py` and dedupe
   the JS helpers (`storageKey`, eject offsets, `enchantLevel`, form `show`,
   `destroyCommand`). Byte-identical runtime output requires care: helper
   moves change the shipped JS bytes, so either keep each runtime's text
   identical (re-export) or accept a reviewed, behaviour-identical JS diff
   (a pick for that PR).
6. **Citadel books** -> `adapters/citadel` (library); viewer JS stays core. -5.
7. **Waystones** (4,573 lines): already behind the four station hooks + its
   residue kind. -41.
8. **Farmer's Delight** (~4,580 lines): cutting board out of `stations.py`,
   then cooking pot, stove, skillet, feasts (`heat_table` and
   `campfire_table` move together). -97.
9. **Close-out**: empty allowlist, delete it, the test then asserts zero;
   `SKIP_KINDS` composed from core + adapter kinds. #245 done.

## 8. Not decided here

The adapter interface picks above; whether helper moves may change shipped
JS bytes (step 5); and whether `_OVERRIDE_KINDS`' mod predicate names become
data. None of this PR changes behaviour: it adds this document, the lint and
its allowlist.
