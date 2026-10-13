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

## 2026-10-13: users can override mod config flags at conversion time; flag-gated items follow the flag

- **Decision:** `portkit convert --config <mod>.<flag>=<true|false>`
  (repeatable) and `--config-file <path>` (JSON or TOML, nested
  `{mod: {flag: bool}}` or flat `{"mod.flag": bool}`; `--config` wins over the
  file, later settings win) set a mod config flag for the conversion, the
  stand-in for a Java player or server editing the mod's config file. A
  setting replaces the cited default wherever a load condition reads the flag,
  both ways: on converts what the default left out (Mythic Metals
  `enableDusts=true`: 37 dust recipes), off sends what it gates to residue as
  "disabled by user config: <flag>". A flag is named as the conditions spell it
  (`dust_enabled`, `flax`, `force_integration_materials`) or by the option's
  own config key where `config_flag_defaults.json` cites it (`config_key`:
  Mythic Metals `enableDusts`/`enableNuggets`/`enableAnvils`, Farmer's
  Delight `enableVanillaCropCrates`, Tinkers' Config.java keys, where
  `glassRecipeFix` sets both `glass_recipe_fix` and `slime_recipe_fix` as in
  Java). Flags with no cited default can be set when the jar's own recipes or
  loot tables use them ("set by user config"). An unknown mod or flag is an
  error, exit 2 before anything is written, listing the valid flags. The
  settings go into the summary (`config`), the notes, `portkit report`, and
  `config-overrides.json` next to the tree, which `--config-file` reads back to
  reproduce the run. Items the mod's code registers only while a flag is on
  are recorded as a cited `registers` pattern on the flag; the item converter
  makes them `conditional_item` residue (the agent skips it) when the flag is
  off, by default or by the user. Cited so far: Mythic Metals 0.24.6+1.21
  `*_dust` (ItemSet L64/CopperSet L29, `enableDusts`) and `*_nugget` (ItemSet
  L61/CopperSet L26, `enableNuggets`). `eval` and `corpus` take no `--config`:
  they check the default conversion against its baseline.
- **Why:** Java has the config and Bedrock doesn't, so content a pack can
  switch on in Java had no way into a conversion once flags were decided at
  their defaults (2026-10-13 entry below). Typos must fail loudly, since a
  silently ignored setting gives the default output while the user believes
  otherwise. Mythic Metals registers its dust items only with `enableDusts`, so
  shipping them by default was the same "content the mod doesn't have" problem
  the dust recipes had; default output drops the 27 dust items (1726 -> 1699
  files, 46.8% -> 46.1%), and `--config mythicmetals.enableDusts=true` gives
  1763 files, 37 recipes and 27 items more, mct 0 errors. No other mod's
  default output changes.
- **Rejected:** a per-mod config-file parser reading the user's real
  `config/*.toml`/`json5` (each mod's format and nesting differ; a named flag
  covers it); silently ignoring unknown names; refusing uncited flags (the
  user's explicit choice decides them); Supplementaries config-path aliases
  (its toggles nest under categories whose parents AND into children, and
  `globe_sepia`/`key` are computed, so the TOML path isn't a one-to-one name for
  a condition flag; its condition flag names are accepted); gating Mythic
  Metals' anvil blocks under `enableAnvils` (on by default, and the anvil
  blocks are residue regardless, so it changes nothing today).
- **Links:** #185, PR (this one); builds on #183 / #184.

## 2026-10-13: load conditions are decided against the conversion; mod config flags at their defaults cited from source

- **Decision:** a recipe or block loot table whose load conditions
  (`conditions` on Forge, `neoforge:conditions`, `fabric:load_conditions`)
  don't hold with only this mod loaded is `conditional_recipe` /
  `conditional_loot_table` residue (`src/portkit/conditions.py`). The context is
  the mods the jar's metadata declares, its required dependencies, and the
  platform; every other mod is absent. `mod_loaded`, `not`/`and`/`or`,
  `tag_empty`, `item_exists`, Fabric `all_mods_loaded`/`any_mods_loaded`/
  `tags_populated`/`registry_contains`, Mantle `tag_filled`/
  `tag_combination_filled` and `mekanism:mod_version_loaded` are evaluated; a
  tag counts as filled from the jar's tag files plus the fetched loader and
  vanilla data, and anything undecidable (unknown membership, a non-item
  registry, whether this mod's code registers an item) is residue. A mod's own
  config flag (`supplementaries:flag`, `mythicmetals:{nuggets,dust,anvils}_enabled`,
  `farmersdelight:vanilla_crates_enabled`, `tconstruct:config`) is decided at
  its default, read from the mod's source at the version its metadata
  declares and recorded with file, line and commit URL in
  `src/portkit/data/config_flag_defaults.json`: a cited `true` passes (one
  note per mod lists the flags assumed), a cited `false` is residue "disabled
  by default config: <flag>", and a flag or mod version with no citation is
  residue "unknown load condition <type>/<flag>". A `forge:conditional`
  wrapper converts the first entry whose conditions hold. Residue that rests
  on an absent mod says "compat for <mod>". `conditions` inside loot pools and
  entries, loot modifiers (`moonlight:iconditions`) and Silent Gear trait data
  are loot predicates or the mod's own logic, not load conditions.
- **Why:** Java doesn't load these files with the mod on its own, so shipping
  them is content the mod doesn't have (Create's 42 and Supplementaries' 18
  compat recipes for absent mods, Supplementaries' 18 "flax off" alternatives,
  Mythic Metals' 37 dust recipes with `enableDusts = false`). Defaults are the
  config a player gets, and citing them from the pinned source keeps the call
  checkable: Supplementaries 1.20-3.1.43 (100 flags, all `true`:
  `CommonConfigs.isEnabled` at c095e871, unregistered keys default `true`),
  Mythic Metals 0.24.6+1.21 (`enableDusts` false, nuggets and anvils true),
  Farmer's Delight 1.3.4 and 3.6.28 refabricated (`enableVanillaCropCrates`
  true), Tinkers 3.12.1.231 (6 true, `forceIntegrationMaterials` false).
- **Rejected:** (A) every mod-specific flag as residue: drops 350 recipes Java
  loads under the default config (Supplementaries 232, Mythic Metals 109,
  Farmer's Delight 3+3, Tinkers 3) and Mythic Metals' 24 anvil loot tables,
  while the blocks and items the same flags gate still ship, so the pack would
  contradict itself. (B) treat the mod's
  own flags as "on, as shipped" without reading them: wrong for Mythic
  Metals' `dust_enabled` (off by default) and Tinkers'
  `force_integration_materials`, and a guess the decision log couldn't defend.
- **Links:** #183; #171 (multi-jar conversion would add other mods to the
  context).

## 2026-10-12: item-list ingredients convert one recipe per item; Alloy Forgery forging recipes stay residue

- **Decision:** an ingredient written as a JSON list of items (Java's "any of
  these", e.g. Mythic Metals' `[{"item": "mythicmetals:deepslate_adamantite_ore"},
  {"item": "mythicmetals:adamantite_ore"}]`, or bare id strings) is a membership
  the recipe states outright, so it takes the multi-member tag rule's form 3:
  one recipe per item (`<recipe>__<item>.json`), when every listed item is
  vanilla or emitted by this conversion, it is the recipe's only multi-item
  ingredient, it fills one grid slot, and it has at most `EXPANSION_CAP` (16)
  items. A one-entry list is its item. A list gets no tag of its own, since the
  mod declared none. Anything else stays residue with a reason naming the
  failed condition (slots, a second multi ingredient, the cap, unconverted
  members, or a tag/non-item entry in the list). `alloy_forgery:forging`
  recipes stay residue, now with a reason that names the missing forge.
- **Why:** a list is exactly as known as a fully resolved tag, and vanilla
  Bedrock writes its armour -> nugget furnace recipes the same way, one per
  piece (Mojang/bedrock-samples `behavior_pack/recipes/furnace_iron_helmet.json`);
  Bedrock's furnace input is one item id (learn.microsoft.com, Furnace Recipe).
  Corpus: Mythic Metals 42 furnace recipes (ore and armour lists, every one of
  the 42 "tag or item list" residues), Mekanism 8, Tinkers 3, BetterEnd,
  Create, Farmer's Delight (both), Supplementaries 1 each. The forging format
  (wisp-forest/alloy-forgery 1.21.1 @ 48e309f, `RawAlloyForgeRecipe`) is up to
  10 counted inputs, `min_forge_tier`, `fuel_per_tick` and tier-range output
  overrides (`"3+": 3`), run in a multiblock forge whose controller blocks,
  tiers and fuels Alloy Forgery's own jar defines (`data/alloy_forgery/alloy_forge/`);
  no corpus jar ships them (Mythic Metals carries only stray assets for an
  `alloy_forgery:adamantite_block_forge_controller`, with no definition).
- **Rejected:** forging as crafting-table or furnace recipes (drops the fuel
  and tier gates and the tier bonus, so cheaper than Java: a gameplay change);
  an invented "alloy forge" block with `minecraft:crafting_table`
  `crafting_tags` (no source jar defines it: fabrication, #87); a synthetic
  native tag for a list (the mod declared no tag); multi-jar conversion of
  Alloy Forgery itself (a large feature, and a crafting-table station still
  could not express fuel, tiers or counted inputs above 1 per slot): left for
  Alex to choose.
- **Links:** #87, #160, #161.

## 2026-10-12: a flat item icon with `overrides` converts as its base icon when every predicate has a resting state

- **Decision:** an item model whose chain is a flat icon (`item/generated` or
  the held parents, no `elements`) and that has its own `overrides` now
  converts like one without them: the base icon, which is the look Java draws
  when no override matches. This holds when every predicate key, read by its
  name without the namespace (`mythicmetals:funny_day` -> `funny_day`), is one
  of five known kinds whose no-match state is the item at rest:
  *occasion* (`funny_day`, `silly`, `wrapping`: an easter egg or a special
  day), *use* (`pull`, `pulling`, `charged`, `firework`, `cast`, `throwing`,
  `blocking`, `tooting`, `brushing`, `cooldown`, `using`, `active`,
  `is_active`: not in use), *wear* (`broken`, `damage`, `damaged`: intact),
  *state* (`custom_model_data`, `trim_type`, `filled`, `dye`,
  `encoded`, `invalid`, `mode`, `clipboard_type`, `midas_gold_count`,
  `is_primed`: no special stored data) and *context* (`lefthanded`,
  `in_world`: the ordinary inventory/right-hand look). The names are vanilla
  1.21.1's item properties plus the mod-specific ones the corpus uses. One
  note per mod lists each converted item, its predicate keys, the alternate
  looks dropped, and what those looks showed (so a bow-like item's draw
  animation is named as lost); nothing is written for the behavior (#87).
  Still residue: a *readout* predicate (`time`, `angle`, `radiation`, `speed`,
  `in_chunk`: a clock, compass, gauge or locator whose look is the reading,
  where one frozen frame would show a false reading), any predicate not in the
  table (no way to know its resting state), malformed overrides, overrides on
  a model with `elements` (now said as such), and every non-flat base (Tinkers'
  `forge:item/default` loader models, `block/block` presents, shields on
  `builtin/entity`, vanilla `item/bow`). An empty `overrides` list is no
  overrides. Override target models and their textures are handled exactly as
  before (unregistered variant models get their note, textures ship).
- **Why:** `durasteel_ingot` (Mythic Metals) is a plain ingot whose only
  override swaps in the `dura-chan` easter-egg sprite when
  `mythicmetals:funny_day` is set, and refusing the ingot left 15 recipe
  warnings that the ingot is missing. Survey of all 13 corpus mods
  (`corpus fetch --include-optional`): 119 item models have `overrides` (9
  mods); 30 have a flat base: 26 convert under this rule (occasion 5, use 5,
  wear 2, state 13, context+state 1) and 4 are readouts kept as residue
  (`mythicmetals:platinum_watch` time, `mekanism:geiger_counter` radiation,
  `supplementaries:speedometer` speed, `alexsmobs:pupfish_locator`
  in_chunk); the other 89 have no flat base and stay residue on that ground.
  Of the 26, `create:clipboard` is a block item (the block converter owns
  it) and three Mythic Metals items (`legendary_banglum_pickaxe`,
  `legendary_banglum_shovel`, `unobtainium`) are withdrawn by
  `drop_untextured` because their base textures are animated with per-frame
  timings; 22 new item definitions ship. Recipes no longer warning about a
  missing item: Mythic Metals 41 (mostly osmium_ingot and durasteel_ingot),
  Supplementaries 35 (bunting), Mekanism 5, Create 4, Alex's Mobs 2,
  Waystones 1. Bedrock has no stable way to carry most of these:
  `minecraft:icon` is a static texture map per item (`default`, plus armor
  trim textures and palettes)
  (https://learn.microsoft.com/en-us/minecraft/creator/reference/content/itemreference/examples/itemcomponents/minecraft_icon),
  with no Molang or state selection. Two partial mechanisms exist and are
  follow-ups, not built here: an attachable with a render controller can
  switch the *held* model on `query.main_hand_item_use_duration`, as
  Microsoft's custom bow tutorial does
  (https://learn.microsoft.com/en-us/minecraft/creator/documents/custom_projectiles,
  "Create a custom bow and arrow"; reference
  https://learn.microsoft.com/en-us/minecraft/creator/reference/content/attachablereference/examples/attachabledefinitions/attachable),
  which could carry the *use* kind in hand (not the inventory icon); and the
  icon map's armor-trim keys might carry `trim_type` (Create's cardboard
  armor), unverified for custom items.
- **Rejected:** keep refusing every model with overrides (loses items whose
  JSON fully states their ordinary look, and every recipe that uses them);
  convert any flat base regardless of predicate (a watch or gauge would ship
  a frozen, false reading, and an unknown predicate may have no resting
  state); emit the alternate looks as extra items (they are not registered
  items, #158); build attachables or trim icons now (each needs geometry or
  per-item verification; follow-ups).
- **Links:** #87, #158, #167, #168.

## 2026-10-12: held items (`item/handheld`, `_rod`, `_mace`) convert as flat icons with `minecraft:hand_equipped`

- **Superseded in part by** the 2026-10-12 `overrides` entry above: a flat
  icon with its own `overrides` now converts when every predicate has a
  resting state.
- **Decision:** an item model whose parent chain ends in vanilla
  `item/handheld`, `item/handheld_rod` or `item/handheld_mace` converts like an
  `item/generated` one: the same single-layer icon through
  `item_texture.json`, plus `"minecraft:hand_equipped": true` so Bedrock
  draws it in the hand like a tool, at item `format_version` 1.20.30 (the
  minimum that component needs; plain icons stay at 1.20.10). No damage,
  durability, digger speed, tool tier or enchantable slot is written (#87):
  the model states none of them, so one note per mod lists the held items
  and says their behavior is Java code that is not converted. The parent
  chain is now followed through the mod's own intermediate models (as the
  block converter already did) for generated icons too; the leaf's textures
  win over a parent's, and intermediate files are claimed only when the item
  converts. Still residue, with their own reasons: `item/template_bow`; a
  model with its own `overrides` (Java reads overrides from the item's own
  model only, so a parent's do not count); any model in the chain with
  `elements` (a 3D shape, now said as such instead of "not a flat icon");
  two or more `layerN` textures (same as generated icons, no compositing);
  a chain that leaves the mod's namespace or its folder. An empty
  `"elements": []` counts as none (Java inherits the parent's), and `#name`
  texture variables resolve through the merged map. `pack.engine_floor` now
  reads item definitions too, so a pack with a held item declares
  `min_engine_version` 1.20.30 (Mythic Metals, Waystones, both Storage
  Drawers), and Mekanism's tagged items (1.20.50) lift its floor from
  1.20.20, a gap that predates this change. The agent_mod fixture's steel
  sword gained a one-box `elements` list so it stays the agent's
  stat-fabrication probe; item_defs_mod's pickaxe gained a lang key so it is
  a registered item, and it now converts.
- **Why:** the icon and the held pose are fully stated in the JSON; refusing
  the whole item over code-side behavior left 212 handheld models in the
  corpus as residue (Mythic Metals alone 129), when the honest partial answer
  is the item as Java draws it, with the missing behavior named in a note.
  `minecraft:hand_equipped` is documented in Microsoft's item reference
  (https://learn.microsoft.com/en-us/minecraft/creator/reference/content/itemreference/examples/itemcomponents/minecraft_hand_equipped:
  boolean, "rendered like a tool while it is in a player's hand", format
  1.20.30+; vanilla `breeze_rod.json` in Mojang/bedrock-samples uses it), and
  in the fetched lookup reference (`item:minecraft:hand_equipped`, docs pin
  4186dc4ec84c). The vendored 1.26.60 item schema leaves `components` an open
  object, so it neither confirms nor rejects it. Corpus: 188 of 212 handheld
  models convert (Mythic Metals 117 of 129), 13 stay residue (overrides 9,
  vanilla `minecraft:item/stick` icon 3, a foreign-namespace texture 1), 11
  are unregistered variants (notes); mct 0 errors on every changed mod.
- **Rejected:** keep refusing held tools (loses icons the JSON fully
  states); write tool components with guessed numbers (fabrication, #87);
  composite multi-layer icons (no such path exists for generated icons
  either); resolve `overrides` (bows, pulling) here (out of scope, they stay
  residue).
- **Links:** #87, #158, #135.

## 2026-10-12: Tinkers' Construct is an optional corpus mod; Mythic Metals takes its default slot

- **Decision:** `fixtures/real/mods.toml` entries can be `optional = true`:
  pinned and baselined, but left out of the default `portkit corpus fetch`,
  `portkit eval --corpus` and the realmods gate, and run with
  `--include-optional` (or `--fixture <name>` for any one mod). A skipped
  optional mod's baseline entry is neither "missing" nor dropped on re-bank.
  Tinkers' Construct moves to optional. Mythic Metals (Fabric 1.21.1) joins the
  default set; Alex's Mobs (entities) and Mekanism (fluids, machines, custom
  recipe types) join as optional.
- **Why:** Tinkers' 11,752 generated tool sprites make it a file-count outlier
  (13,512 of the corpus's files, 87% of them sprites; #122), so it dominates
  run time and pack-size numbers without exercising anything new. Silent Gear
  already covers material-built tools. Mythic Metals adds armor, tool and ore
  (worldgen) content the default set lacked. Mythic Metals publishes only beta
  builds on Modrinth, so its pin is the newest 1.21.1 beta rather than a release.
- **Rejected:** dropping Tinkers entirely (it is still the corpus's v1 zero-output
  case with custom recipe types and fluids, and keeping the pin keeps its numbers
  ratcheted whenever someone runs it).
- **Links:** #122, #21.

## 2026-10-12: recipes that share a file name are named by their path; no output is written twice

- **Decision:** A Java recipe is written to `recipes/<name>.json` with the
  identifier `<namespace>:<name>`. `<name>` is the file's stem when no other
  recipe file of the namespace has that stem (counting every recipe file in
  the jar, converted or not), so those keep the name they always had. When
  several files share a stem, *every* one of them is named by its whole path
  under `recipes/`, folders joined with `_`
  (`smeltery/casting/planks` -> `smeltery_casting_planks`); a file at the root
  of `recipes/` keeps its stem, which is its whole path. Per-member recipes
  (#161/#162/#164) append `__<member>` to that name. If a path-qualified name
  lands on an unshared stem (`x/planks` vs `x_planks`) or two qualified names
  meet (`a/b/c` vs `a_b/c`), the unshared stem keeps its name and each
  qualified file that met it is residue naming the other file; a per-member
  name that is another recipe's name sends the expanding recipe to residue.
  Guards: inside the recipe converter, a second write to an output path or a
  second recipe declaring an identifier is residue (`refused rather than
  overwrite`), never an overwrite; and `ConversionResult.merge` (one
  converter after another) lets a later converter replace a file only when
  both declare the same identifier (recipes adding `minecraft:tags` to an
  item); anything else keeps the first file and is `output_collision`
  residue. The validator's existing `recipe.identifier_collision` still
  catches duplicate identifiers in the written tree.
- **Why:** Every recipe used to go to `recipes/<stem>.json`, so recipes with
  the same file name in different folders overwrote each other: only the last
  shipped, nothing went to residue, and the lost ones counted as converted.
  On the corpus that was 102 converted recipes lost (create 28, supplementaries
  7, tinkers_construct 67, including Tinkers' four wood `planks`). Qualifying
  the whole colliding group means the result depends only on which files
  exist, not the order a jar or the filesystem yields them, and no member is
  arbitrarily the "real" one; keeping unshared stems leaves every other
  recipe's file and identifier unchanged.
- **Rejected:** Path-qualifying every recipe (renames ~3,000 corpus recipes
  and every existing identifier for no gain); keeping the bare name for the
  first file in sort order and qualifying the rest (picks a winner by
  character order, so adding a folder can rename an unrelated recipe);
  numbering duplicates (`planks_2`: order-dependent and meaningless to a
  reader); raising on a collision (a mod's own file names can cause one, and a
  converter refusing a file is residue, not a crash).
- **Links:** #163, #161, #162, #164.

## 2026-10-12: stairs, slabs, walls and turned pillars convert from vanilla's templates; tags of mostly-block members ride on block items

- **Decision:** Blocks whose blockstate has exactly vanilla's stairs state set
  (`facing` x `half` x `shape`, all 40), slab set (`type=bottom|top|double`) or
  wall multipart (post on `up=true`, low and tall sides per direction), and
  whose models extend vanilla's `block/stairs`/`inner_stairs`/`outer_stairs`,
  `slab`/`slab_top` or `template_wall_post`/`_side`/`_side_tall`, convert at
  block format 1.26.0. Detection is structural plus the parent; names are never
  read. The boxes come from those vanilla templates, fetched by
  `portkit reference fetch` from misode/mcmeta's 1.20.1 model summary (pinned,
  sha256-checked, never vendored; identical for 1.16.5 to 26.1). Every Java
  variant keeps its own model, x/y turn and uvlock (a new `turn_locked` for
  uvlock with x turns; position-derived uvs only, else residue):
  stairs get one geometry per variant, picked per permutation by
  `minecraft:cardinal_direction` (= Java `facing`), `minecraft:vertical_half`
  (= `half`) and `minecraft:corner` (= `shape`, `straight` = `none`) from the
  `placement_direction` trait's `corner_and_cardinal_direction` plus
  `placement_position`; they corner with anything tagged
  `minecraft:cornerable_stairs` (they carry the tag), get
  `minecraft:support` `stair` and a collision box per variant equal to its
  boxes. Slabs get bottom/top bones on `vertical_half` with half-height
  collision and selection boxes; Java's `type=double` has no data-driven
  Bedrock form, so it is read, set aside and named in a note. Walls get a post
  and four low sides on the connection trait, the post shown by Java's own rule
  with nothing above (raised unless exactly one opposite pair joins); tall sides
  and the above-block post are not reachable and are named in a note, and
  collision stays a full block. A blockstate that turns a plain cube (pillars
  and logs lying on their side, `axis=x|z` with x/y and no uvlock) now takes the
  template's box and turns it with `turn_rigid`. Models that only name a
  vanilla template also feed the palisade and facing paths. Without the
  templates cached, all of these stay residue saying to run the fetch.
  Recipes: a tag whose mod members are emitted items or blocks keeps the Java
  tag as a native item tag on them (blocks through the #162 replacing
  block_placer item); members that can't carry it (vanilla items, blocks with
  their own item file) get one recipe each beside the tag recipe, for a
  single-slot ingredient, when at least two of the mod's members share the tag
  (otherwise the #161 one-recipe-per-member form stays). Also: offline (no
  vanilla tag data), a Bedrock vanilla tag such as `minecraft:logs` no longer
  passes through when the jar ships other `minecraft:` item tag files (its own
  `minecraft:oak_logs` may feed `minecraft:logs`); the recipe stays residue
  naming them.
- **Why:** 120 stairs, 123 slabs, 88 walls and ~80 turned pillars were block
  residue across the corpus, and Create's stairs, walls and pillars kept all
  266 `create:stone_types/*` stonecutting recipes residue. Bedrock has the
  states these blocks need as stable traits since 1.26.0: the connection trait,
  `corner_and_cardinal_direction` ("can now be used without the Beta APIs
  toggle", inner corners fixed in 1.26.10), `minecraft:support`, array
  collision boxes (learn.microsoft.com 1.26.0 / 1.26.10 creator update notes;
  Block Traits: placement_direction; Block Traits; minecraft:support; vendored
  1.26.60 schemas `block_placement_direction`, `block_placement_position`,
  `block_connection`, `block_support`, `block_components`). Java facing and
  Bedrock `cardinal_direction` are both the player's facing at placement
  (y_rotation_offset 0). Corpus: stairs 117/120, slabs 120/123, walls 86/88
  and 79 more turned pillars convert; all 266 stone_types recipes (278 in all)
  leave residue, and with native tags Create ships 3,904 files instead of the
  7,790 one recipe per member would have written.
- **Rejected:** Straight stairs only (Bedrock has stable corner states);
  `minecraft:transformation` to turn one geometry (turns textures too, which
  Java's uvlock doesn't); one geometry with 40 bones (mct GEOMETRY warning, ~100
  cubes in one model); vendoring vanilla's template JSON (Mojang's data, #124
  policy); hand-typed box tables (the fetched models are the source); a scripted
  double slab (no scripts in packs); wall collision from Java code (24 high,
  not in the JSON); one recipe per member for stone_types (~4,000 files);
  passing an offline vanilla tag through when the jar adds to other vanilla tags
  (could drop the mod's members, #87).
- **Links:** #87, #161, #162.

## 2026-10-12: a mod's own members of a Bedrock vanilla tag carry that tag; Bedrock's tag alone never stands in for them

- **Decision:** A Java recipe ingredient naming one of the vanilla tags
  Bedrock also has under the same name (`_BEDROCK_VANILLA_TAGS`:
  `minecraft:planks`, `minecraft:wooden_slabs`, `minecraft:logs`, ...) passes
  through as Bedrock's tag only when the mod adds nothing to it: no tag file
  in the jar, or a merged membership (#160 rules, nested tags included) whose
  every kept member is vanilla. When the mod adds its own members, the recipe
  still takes Bedrock's tag, and each of those members carries it: an emitted
  item gets it in `minecraft:tags` (format 1.20.50); an emitted block gets an
  item form, `items/<block>.json` with the block's identifier,
  `minecraft:block_placer` `{"block": <id>, "replace_block_item": true}`,
  `minecraft:display_name` = the block's `tile.<id>.name` key, and
  `minecraft:tags` (format 1.21.50). Only members the Java data puts in the
  tag are tagged; nothing is added by name. A member that can't carry it (a
  block that already has its own item file, now marked `block_and_item` by
  `emitted_definitions`) falls back, for a single-slot ingredient, to the tag
  recipe plus one recipe per mod member (`<recipe>__<member>.json`, at most
  16); a multi-slot one, a member this conversion didn't emit, a jar file that
  sets `"replace": true` (it may drop vanilla members) or an unknown
  membership (no reference data) stays residue with the reason. When a block
  is withdrawn later for a texture that didn't convert, its item form goes
  with it. The validator gains `xref.block_placer` (error: a block placer
  naming a block the pack doesn't declare, or `replace_block_item` on an item
  whose identifier isn't the block's) and no longer warns
  `identifier.block_and_item` for a block whose item form says so through
  `replace_block_item`.
- **Why:** Bedrock's `minecraft:planks` holds vanilla planks only, so passing
  the tag through dropped the planks the mod adds (#87 in the narrowing
  direction). Bedrock lets a block's item carry item tags that recipes match:
  `replace_block_item` "registers the item as the item for this block"
  (learn.microsoft.com, Items Documentation - minecraft:block_placer, format
  1.21.50; Customizing the Item for a Block), and vanilla does exactly this:
  Mojang/bedrock-samples `behavior_pack/items/shelf_mushroom.json` replaces
  the shelf mushroom block's item and tags it `minecraft:mushrooms_for_stew`,
  which `recipes/mushroom_stew.json` takes as a tag (main @ 46ba6ea). Corpus:
  5 recipes now keep the mod's members instead of narrowing (Silent Gear
  `refabricator`, `upgrade_base`; Tinkers `pattern`, `part_chest`,
  `tinkers_chest`), with 5 new item forms (Silent Gear netherwood planks,
  Tinkers greenheart/skyroot/bloodshroom/enderbark planks).
- **Rejected:** Passing the tag through and dropping the mod's members (the
  #161 behaviour, a silent narrowing); making these recipes residue (they have
  a faithful form); one recipe per member for every tag (needs one slot and
  forbids mixing members, so only the fallback); block tags (`tag:minecraft:planks`
  block components are block tags, which recipes don't read); tagging blocks
  by name (`*_planks`) without the Java tag saying so (fabrication).
- **Links:** #161, #160, #87.

## 2026-10-12: shared tags take their full membership from fetched loader and vanilla data, and fully known multi-member tags convert

- **Decision:** A tag in the `minecraft:`, `c:`, `forge:`, `neoforge:` or
  `fabric:` namespace read from a mod jar is incomplete unless its file sets
  `"replace": true`. Its full membership is the jar's members, plus the
  loader's and vanilla's shares from reference data, nested `#tag` entries
  resolved the same way. `portkit reference fetch` downloads that data on
  demand from pinned artifacts and caches it beside the vanilla sound list,
  sha256-checked: Forge 1.20.1-47.4.26's and NeoForge 21.1.259's universal
  jars (LGPL-2.1), Fabric API's `fabric-convention-tags-v1`/`-v2` module jars
  for 1.20.1, 1.21.1, 1.21.8 and 26.1 (Apache-2.0), and misode/mcmeta's vanilla
  item tag summaries for 1.16.5, 1.19.2, 1.20.1, 1.21.1, 1.21.8 and 26.1
  (Mojang's data, Minecraft EULA). Only tag id -> `values` is kept; nothing is
  committed (`src/portkit/data/NOTICE.md`). The loader and game version come
  from the jar's `mods.toml` / `neoforge.mods.toml` / `fabric.mod.json`
  (`ModMetadata.minecraft`) and map to the nearest pinned set (Forge and
  pre-1.20.5 NeoForge to Forge 1.20.1; Fabric before 1.20.5 to convention
  tags v1). A namespace the loader never writes (Forge 1.20.1 ships no `c:`
  tags, NeoForge 1.21 dropped `forge:`) holds only mods' entries there, so the
  jar's share is all the addon can hold. When the data isn't cached, or the
  jar doesn't say its loader and version, the recipe stays residue and the
  reason says why; a recipe is never narrowed to the jar's share. The
  built-in single-vanilla-item table (`rods/wooden` -> stick) no longer
  applies when the mod adds its own item to that tag.
  With the membership known, the recipe converter (the #160 prototype) also
  writes multi-member tags whose every member is vanilla or emitted by this
  conversion: a Bedrock vanilla tag when the membership is exactly that of one
  of `_BEDROCK_VANILLA_TAGS`; else the Java tag as a native tag, with
  `minecraft:tags` added to the emitted member items, when every member is an
  emitted item; else one recipe per member (`<recipe>__<member>.json`) when the
  tag fills one grid slot and has at most 16 members. Anything else stays
  residue, and the reason names members this conversion didn't emit. The
  validator accepts tag ingredients, still flags unknown items, and warns
  (`xref.tag`) on a custom tag no pack item carries. `fixtures/agent_mod`'s
  `alloy_ingots` tag gains `examplemod:tin_ingot`, which the jar has no model
  for, so that group still needs the agent (its 2-member form would now
  convert deterministically); its
  scripted agent tests keep their outcomes and the residue_mod transcript
  replays unchanged.
- **Why:** A mod's file for a shared tag lists only its own additions (Forge's
  `forge:glass/colorless` is `minecraft:glass`; Tinkers' file adds its clear
  glass), so treating it as the whole tag made recipes accept only the mod's
  item, a fabrication in the other direction (#87). Corpus (10 mods): 243
  recipes convert that didn't (230 of the 354 blocked only by convention
  tags), and 46 recipes that converted narrowed are residue now (Tinkers' glass
  11, Silent Gear's `forge:rods/wooden`/`forge:string` 33, Farmers Delight's
  `c:drinks/milk` 2).
- **Rejected:** Vendoring the loaders' tag files (licence and size; fetched
  like #124 instead); trusting the jar's share when the data is missing (the
  #160 bug); dropping vanilla members to fit a native tag (narrows); splitting a
  tag that fills several slots into per-member recipes (forbids mixing
  members); expanding big families (cap 16) that would flood the recipe book.
- **Links:** #160 (PR #161), #88 (PR #94), #94, #87. Supersedes in part the
  2026-10-09 entry "Item tags resolve from the mod's tag file, then the
  convention name, then residue" for shared namespaces.

## 2026-10-12: the item converter emits only items the Java source registers

- **Decision:** the deterministic item converter writes a Bedrock item only
  when its id passes the same registration test as the agent's
  `agent.unknown_item` guard: `portkit.registry.registered_ids` (blockstate,
  JSON or 1.12 `.lang` key, recipe, item tag or loot table), under
  `converters.items.bedrock_identifier`. That test moved out of
  `agent/items.py` into `src/portkit/registry.py` so the converter and the
  guard share one copy. An item id whose only evidence is its item model file
  (a 1.12 per-metadata model such as `upgrade_storage_obsidian`, a modern
  override model such as `twinbound_feather_brushing_0`) is claimed, not
  emitted and not sent to the residue, and a note names it and the registered
  item it is a variant of. Its texture is not dropped: the textures converter
  ships it like every other texture (or lists it in the residue with its
  reason), and the note records it as a variant texture of the parent item
  when the parent's own model does not already use it. Nothing in the pack
  switches to it; that choice is Java code. Because the converter no longer
  defines these ids, the guard's "deterministic output already defines it"
  allowance no longer lets the agent write them. Real-mod corpus baseline:
  39 such item files left the packs (storage_drawers_1122 16, supplementaries
  9, create 3, waystones 3, tinkers_construct 3, betterend 2,
  storage_drawers_1192 2, farmers_delight_neoforge 1), and 10 more
  supplementaries models (`speedometer_1`..`_9`, `flint_shard`) that had been
  withdrawn to the residue for an unconverted texture are no longer residue.
  Every one was checked to have no registration (examples:
  `storagedrawers:keybutton_drawer`, `storagedrawers:upgrade_storage_iron`,
  `create:clipboard_0`, `betterend:elytra_armored_broken`). Fixture baselines
  are unchanged.
- **Why:** Java registers one item and carries the variant in metadata, NBT
  or a model override, so these files were items no Java player can hold, the
  same fabrication #157 stopped the agent from writing. Keeping the converter
  and the guard on one test keeps them from disagreeing. The textures stay
  because of the project rule (2026-10-11) to keep source assets and find
  ways to use them.
- **Rejected:** keep emitting them (the pack keeps items Java never
  registers, and the guard keeps an exemption for them); drop the variants'
  textures with the items (loses source assets a later override mapping could
  use); invent a Bedrock icon switch for them (Bedrock behaviour with nothing
  in the source to check it against).
- **Links:** #158, #157, #87.

## 2026-10-12: agent-written items must be ones the Java source registers

- **Decision:** every `minecraft:item` the residue agent writes (either pack)
  whose identifier is in a source-mod namespace or the conversion's namespace
  must be the Bedrock id, under the converter's own mapping
  (`converters.items.bedrock_identifier`, also applied with the conversion
  namespace), of an id the Java source registers: a blockstate (block and its
  block item), a lang key (JSON `item.`/`block.` keys; 1.12 `.lang`
  `item.`/`tile.` keys, lower- or snake-cased), or an item a recipe, item tag
  or loot table names, or a block loot table. An id an item or block the
  deterministic output already defines, or that the file held before the
  session, passes too. Anything else makes `validate` report
  `agent.unknown_item`, naming the closest registered Java id, and a group
  that ends with one is rolled back, listed in `unknown_items` and in the
  note. An item model file alone is not a registration. `minecraft:` ids are
  out of scope, and a namespace the mod does not have stays
  `agent.unknown_namespace`'s.
- **Why:** on real-mod residue GLM 5.3 wrote per-variant item duplicates that
  no guard caught: `items/basicdrawers_full2_jungle.json` and its siblings in
  storage_drawers_1122 (22 copies) and nine per-variant items in waystones.
  Java registers one item there and keeps the variant in block state,
  metadata or NBT; the per-variant names come from 1.12 per-metadata item
  models and modern override models (`twinbound_feather_brushing_0`), so the
  files validated while the pack gained items no Java player can hold.
- **Rejected:** a block/item id-collision rule (reject an item only when it
  duplicates a block or another item): too narrow, it misses every
  per-variant id that collides with nothing. Also rejected: counting
  `models/item` files as registrations (`refs.source_items` does, which is
  right for "does this ingredient exist" but is exactly where the invented
  per-variant names come from).
- **Links:** #86, #87.

## 2026-10-12: a `<prefix>_<state>` rename with Java's exact values counts as that Java state

- **Decision:** the `agent.invented_state` guard accepts a declared custom
  state named `<prefix>_<javastate>` (`waystones:portstone_half` for Java's
  `half`) as that Java state when its suffix matches exactly one Java state
  and the values it declares are exactly that state's values: the same set,
  spelled as Java names them, and no integers (so a numeric Java state such
  as `level` is never aliased). `q.block_state()` may then use the alias, with
  its compared values checked against the Java state's. Still rejected: a name
  with no Java suffix match, a suffix match with invented, missing or integer
  values, a name that suffix-matches two Java states, and an alias used in
  Molang without being declared. The finding tells the agent the rename's
  condition and to prefer the Java name.
- **Why:** an offline check of DeepSeek residue output found 13 hits on
  waystones `black_portstone`/`cyan_portstone`/`cyan_sharestone` that renamed
  Java's `half` to `<block>_half` with the real `lower`/`upper` values. A
  rename isn't fabrication, and our principle (#87) is no invented data, not
  Java's exact spelling; strict names rolled that work back.
- **Rejected:** strict Java names only (the #151 behaviour; rolls back real
  DeepSeek work that invents nothing); accepting any suffix match whatever its
  values (lets an integer enum or invented values through under a new name);
  picking one of several suffix matches (guessing which state was meant).
- **Links:** #151, #86, #87.

## 2026-10-12: agent-written armour-trim recipes may only name vanilla trim slots

- **Decision:** a written `minecraft:recipe_smithing_trim` may only name a
  `template` and an `addition` that are vanilla `minecraft:` items or tags.
  Any other id in either slot, item or tag, in the mod's namespace or any
  other, makes `validate` report `agent.unresolved_trim`, and a group that
  ends with any is rolled back, listed in `unresolved_trims` and in the note;
  the agent is told to write nothing and decline. Vanilla ids and tags are
  taken on faith, as `refs.py` does (a complete vanilla list is Mojang data we
  don't vendor). `base` is not gated: Bedrock's recipe matcher accepts a
  trimmable armour, vanilla or modded, so only the two slots that decide
  whether the trim applies anything are checked.
- **Why:** in the #86 sweep mistral-large-4-0 wrote agent_mod's steel_trim as
  a Bedrock `recipe_smithing_trim` whose addition was `examplemod:steel_ingot`.
  The structural oracle only checks the three slots are non-empty, so the
  recipe validated and the group counted as resolved, but Bedrock add-ons
  can't register trim materials or patterns, so a mod item in either slot
  applies nothing in game.
- **Rejected:** an escape hatch accepting a mod id when the source ships
  `data/<ns>/trim_material/<id>.json` or `trim_pattern/<id>.json` with `<id>`
  equal to the item id (PR #150's first version): Java keys those files by
  material or pattern name (`steel.json`) with the item in its `ingredient`
  (`template_item` for patterns) field, so the match was wrong, and Bedrock
  can't use the definition anyway. Also rejected: stripping the recipe and
  keeping the residue as declined (rewrites the agent's file behind its back
  after the validator already named the slot, like the recipe ref check);
  checking `base` against vanilla (a trimmable mod armour is the point of a
  modded trim, and Bedrock accepts it); accepting any mod `addition` as "the
  mod's call" (the sweep finding is why this guard exists).
- **Links:** #86, supersedes #150.

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
- **Superseded in part by** 2026-10-12 (#160): a shared-namespace (`c:`,
  `forge:`, `neoforge:`, `fabric:`, `minecraft:`) tag file is only the mod's
  share; the loader's and vanilla's shares come from fetched reference data.

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
