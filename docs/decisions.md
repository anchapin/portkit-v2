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

## 2026-10-15: a `separate_transforms` item converts by its gui view, and a one-texture held 3D model ships as an attachable with a DEFAULT pose

- **Decision:** An item model with `"loader": "forge:separate_transforms"` or
  `"neoforge:separate_transforms"` is read the way Java reads it: `base` for
  every render context, `perspectives[<context>]` where given, keyed by
  `ItemDisplayContext.getSerializedName()` (other keys ignored, as Java does),
  and the outer model's own `overrides` as the item's (a sub-model's are not
  consulted). Sources: `SeparateTransformsModel.Loader.read` and
  `Baked.applyTransform`, Forge 1.20.1 @d13dd32 L147-189 (registered as
  `separate_transforms` in `ClientForgeMod` L35) and NeoForge 1.21.1 @00c6a3f
  L135-169. The **gui** view is the item: it goes through the ordinary icon
  rules (flat parent, one layer, overrides with a resting look), and its
  model files are claimed rather than noted as unregistered variants. Bedrock
  draws the icon for a dropped item and in an item frame, so ground/fixed
  views equal to the gui view are exact. The **held** view (the four
  first/third-person hand contexts) is: the icon, when Java holds the gui view
  too; an **attachable** when all four show one model that draws elements in
  a single texture of the mod's item/block textures:
  `resource_pack/attachables/<item>.json` (format 1.10.0, `entity_alphatest`
  / `entity_alphatest_glint`, texture by path + `textures/misc/enchanted_item_glint`,
  `controller.render.item_default`) and
  `resource_pack/models/entity/<item>.held.geo.json` (the block geometry
  transform; root bone `binding: q.item_slot_to_bone_name(c.item_slot)`), the
  shape of vanilla's trident (bedrock-samples v1.26.50.4
  `attachables/trident.entity.json`, `models/entity/trident.geo.json`).
  **DEFAULT pose:** no animation is written, so Java's held display transforms
  (rotation/translation/scale per hand context) are not carried and the
  elements sit where the block geometry puts them; a note says so per item.
  A held model that can't be carried (two textures, a differing model per hand,
  a non-element model) leaves the item holding its icon, and the held model's
  file is residue naming the item. Ground/fixed/head views that differ from the
  gui view are noted, and their model files are residue naming the view. A gui
  view built by another loader (Mekanism's `meka_tool`: `neoforge:obj`) is
  residue saying so. The attachable is withdrawn with its item, or when its
  texture did not convert (`drop_untextured`); `shorten_paths` renames its
  texture paths; a `models/entity/` geometry counts toward the engine floor.
  Separately, override predicate `dyed` joins the stored-data kind:
  Supplementaries 1.20-3.1.43 registers it on the quiver as
  `DyeableLeatherItem.hasCustomColor(stack) ? 1 : 0` (`ClientRegistry.setup`,
  `lambda$setup$14`, read from the jar's bytecode), so the base is the undyed quiver.
- **Measured** (develop 5973a65 vs this branch, 13 corpus mods + 7 deco mods):
  only Supplementaries changes, +5 files: items `flute` (icon + attachable),
  `quiver` (icon; held model has 2 textures, residue naming the quiver),
  `confetti_popper` (icon; head party-hat view noted); item residue 26 -> 22,
  coverage 28.1 -> 28.2%. The other 19 trees are md5-identical. Mekanism's
  `meka_tool` stays residue (OBJ). Side finding: its `first_person_left_hand` /
  `third_person_left_hand` perspective keys are not `ItemDisplayContext` names,
  so Java ignores them too.
- **Why:** #181's element-drawn in-hand models are source data; this loader is
  the case where the JSON itself says which model shows where, so both the
  inventory icon and the held model are deterministic. Shipping the held model
  keeps the source asset in use instead of dropping it to residue.
- **Rejected:** mapping Java's display transforms onto Bedrock animations now
  (the mapping between Java's held-item origin and Bedrock's item bones is
  unverified in game, and a wrong guess would be stated as fact; DEFAULT until
  checked); stitching two textures into one for the attachable (new art);
  generating icons for 3D-only items such as Create's potato cannon (rendered
  art, not source data); converting the code-selected `*_hand` models of
  Alex's Mobs (Java picks them in code, #176) or the bow/crossbow use states
  (behavior parents, a separate policy).
- **Status:** pending review.
- **Links:** #181, #87, #167, #169.

## 2026-10-15: non-boolean mod config values are cited with their range and set with `--config <mod>.<option>=<number>`; out of range is an error

- **Decision:** A mod config option that a converter reads as a number (not a
  load condition) is cited in the `values` list of
  `src/portkit/data/config_flag_defaults.json`, per mod and exact version:
  type, default, the range the mod's config accepts, file/line/commit URL, what
  Java does with an out-of-range entry, and what reads it. First and only
  entry: Farmer's Delight `cuttingBoardFortuneBonus`, a double, default 0.1,
  range 0.0-1.0, for NeoForge 1.3.4 (`Configuration.java` L84-85 at dd8b9b0,
  `defineInRange`) and Refabricated 26.1-3.6.28 (L84-85 at a8cb49e, mlconfigs
  `define(name, double, min, max)`). `portkit convert --config
  farmersdelight.cuttingBoardFortuneBonus=0.25` (or the same in
  `--config-file`) replaces the default; converters read it through
  `LoadContext.config_value(mod, option)` (the setting, else the cited default
  for the jar's version, else None), and the cutting board's data table
  carries it as `fortune_bonus` (the runtime already multiplied it by the
  tool's Fortune level, as `ChanceResult.rollOutput` does). The setting is
  recorded like a flag (summary `config`, a note, `config-overrides.json` with
  `condition: null` and the range, a `portkit report` row) and reads back with
  `--config-file`. A number outside the cited range, a non-number for a value
  option, or a number for a flag is a `ConfigError` (exit 2, nothing written);
  an unknown name lists the value options with their ranges. A value written
  `1`/`0` is the number for a value option (the written text is kept), still
  true/false for a flag. The default conversion is unchanged byte for byte
  (both FD corpus trees md5-identical; only the conversion note now states the
  bonus and how to change it).
- **Why:** #190 (from the cutting board pilot, 2026-10-13 entry below): the
  bonus is a real gameplay number a Java server sets, and `--config` took
  booleans only, so the conversion could only ship 0.1. Citing the range keeps
  the same rule as flags: the value comes from the mod's source, never a guess.
  Java's own handling of a bad entry differs by loader (NeoForge 1.21.1
  `Range.correct` clamps to the nearer bound, ModConfigSpec.java L1045-1052 at
  00c6a3f; Refabricated's `DoubleConfigValue.loadFromJson` puts the default
  back, L22-40), so neither is "what Java does"; a user typing 1.5 has made a
  mistake, and typos already fail loudly (2026-10-13 config overrides entry).
- **Rejected:** clamping or resetting like one of the loaders (silently gives
  output the user didn't ask for, and the two loaders disagree); a separate
  `--config-value` option (one `--config` namespace, one record file, one
  report table is simpler, and names can't collide: a value option is matched
  before flags and a mismatched type is an error); uncited numeric options
  (nothing would bound or document them); reading a user's real FD
  `farmersdelight-common.toml` (same reason as for flags).
- **Not done from #190:** moving the station runtimes to `@minecraft/server`
  2.4.0 for `BlockCustomComponent.onBreak` (stored items dropped however the
  block is destroyed). 2.4.0 is the first stable package with it (npm
  @minecraft/server 2.4.0, published 2025-12-09: `onBreak?:
  (BlockComponentBlockBreakEvent, ...)` in index.d.ts; 2.3.0 has neither), but
  the 2026-10-13 entry gates the move on the in-game check of the 2.0.0 board,
  which can't be run here. The in-game check itself (interact vs. placement,
  sneak, spawn impulse, `%s` in messages, durability, geometry rotation,
  `y_rotation_offset` 180) is still open, as is the list-ingredient narrowing
  revisit (FD's cabinets are still residue: `minecraft:block/orientable`
  parent).
- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order).
- **Links:** #190, #177, #185, PR #223.

## 2026-10-15: vendored Bedrock schemas are refreshed from the npm package by `portkit schemas`, and 1.26.60 stays on beta.24 until the stable package is out

- **Decision:** `portkit schemas check` compares each row of
  `src/portkit/validate/schemas/SOURCE.md` with the npm registry document of
  `@minecraft/bedrock-schemas` and says per snapshot `current`, `waiting` (no
  stable package for its version; names the latest stable and the newest
  prerelease) or `REFRESH DUE` (exit 1; exit 2 when the registry can't be read).
  A stable release above a snapshot's version is named as a new snapshot to
  add, never folded into the old directory. `portkit schemas refresh` re-vendors
  a snapshot from the package tarball (checked against the registry's sha512):
  `bp/blocks` and `bp/items` mirrored exactly, the `common/` files they `$ref`
  copied when the package ships them, the package `LICENSE`, and the row
  rewritten with the version, the package's `gitHead` and the npm publish
  date; it prints the files and block components added, removed or changed.
  Prereleases only with `--allow-prerelease`. The 1.26.60 snapshot stays on
  1.26.60-beta.24: as of 2026-10-15 the registry's `latest` is 1.26.50 and its
  newest 1.26.60 package is 1.26.60-beta.28 (no stable 1.26.60), and
  Mojang/bedrock-samples' newest non-preview tag is v1.26.50.4 (1.26.60 only
  as v1.26.60.24/.28/.29-preview); the Minecraft Wiki gives 2026-10-27 as the
  planned 26.60 release date. The steps after a refresh (regenerate the agent
  reference, check emitted components, tests, corpus eval) are in SOURCE.md.
- **Why:** #155 asks for the snapshot to move to the stable package once it is
  published; a command makes "is it out?" a one-line check instead of a manual
  registry read, and the tarball path is the one the vendored files came from:
  re-vendoring 1.26.60-beta.24 with it is byte-identical to the committed tree
  (0 added/removed/changed), and its `gitHead` is the recorded fc31f9af.
- **Rejected:** vendoring beta.28 now as an interim step (#155 waits for the
  stable package; a dry run shows beta.28 adds only the experimental
  `minecraft:vibration_properties` block component (portkit doesn't emit it),
  a looser `bone_visibility` (any object; the Molang strings portkit writes
  still pass) and reworded collision-box limit text (a description, not a
  check));
  copying from the GitHub repo (its tags follow Preview builds, e.g.
  v1.26.60.29-preview at 455e6928 has no npm package; the npm package is the
  published unit and carries a registry hash); a scheduled CI job (left out:
  it would need network in CI and an issue-opening token, and the check is
  cheap to run by hand).
- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order).
- **Links:** #155, PR #222.

## 2026-10-14: any multipart keyed only on north/east/south/west booleans converts part for part, each part a bone shown through the connection trait

- **Decision:** A multipart blockstate whose every `when` reads only
  `north`/`east`/`south`/`west` as booleans (`true`, `false`, `true|false`,
  several keys ANDed, `AND`/`OR` lists), with at least one part keyed on one,
  converts after the wall and palisade paths have passed on it: one bone per
  part (`part_<i>`, in blockstate order), its model turned by the part's x/y
  and uvlock as the other shape paths turn them (`models.turn_y`; without
  uvlock an element that is itself rotated turns as a solid, `turn_rigid` with
  its rotation carried; with x, `turn_locked`/`turn_rigid`), and a
  `bone_visibility` Molang test per keyed part over
  `minecraft:connection_<dir>` from the `minecraft:connection` trait
  (`cardinal_connections`), block format 1.26.0 (pack floor follows). An
  unconditional part has no test. Parts whose models give one texture key
  different meanings get that key renamed per part (`<key>_p<i>`), so they share
  one geometry. A part that picks at random between models ships the first,
  the rest named in the note (as `_random_variant` does for variants).
  Collision and selection stay a full block, as on the palisade path. The
  fetched vanilla templates add the glass pane (`template_glass_pane_*`) and
  iron bars (`iron_bars_*`) parents (re-pinned; identical 1.16.5 to 1.21.8 and,
  resolved, in 26.1, which moves bars onto `template_bars_*`). A part that
  can't be turned exactly, or a texture that doesn't resolve, keeps the block
  residue with a reason naming the part (`connection multipart part N
  (model): ...`). Multiparts keyed on anything else (`up`/`down`, `low|tall`,
  `facing`, ages, mod states) keep the general refusal naming their states.
- **Why:** Measured on develop 0ed8556 (13 corpus mods + 7 deco mods, every
  blockstate with a `multipart`): 203 multipart blocks were residue (deco:
  Cluttered 43, Refurbished 29; corpus: Tinkers 47, BetterEnd 39, Create 27,
  Supplementaries 10, Alex's Mobs 3, Farmer's Delight 2+2, Silent Gear 1); the
  largest class, 9-13-part panes, bars, hedges, lattice fences and balustrades
  keyed on the four booleans, matched neither the palisade (5 parts, one side
  model) nor the wall shape. Those four booleans are exactly the states Java's
  CrossCollisionBlock family computes from neighbours and the states Bedrock's
  connection trait reports ("contains information about whether the block
  connects to other blocks, and if so, on what faces", Block Traits:
  connection, learn.microsoft.com; stable without experiments from 1.26.0 per
  the 1.26.0 creator update notes; `minecraft:connection_rule` names fences,
  walls, bars and glass panes as the blocks it governs). `bone_visibility`
  takes a Molang string per bone (vendored 1.26.60 `block_components`
  schema). Bedrock has no other data-driven way to set such states, so
  mapping the part conditions onto the trait's states is the most general
  correct conversion; palisades (#67, checked in game) and walls already use
  it. After: 72 more blocks convert (Cluttered +15 window panes, +3
  balustrades; Refurbished +10 lattice fences, +3 hedges; Create +13 panes and
  bars; Tinkers +24 panes and bars; BetterEnd +2 bars; Farmer's Delight +1
  rope fence per loader), 131 multipart blocks stay residue.
- **Rejected:** Reading which neighbours join from each mod's code (the
  trait's rule is what Bedrock offers; named per block in its note, as for
  palisades and walls); per-permutation collision boxes from the visible
  parts (Java's boxes are code, not the model; the palisade precedent keeps a
  full block); dropping the `false` parts (panes draw their `noside` faces on
  them); a script-set state (no scripts for static blocks); converting
  `up`/`down` six-way connections (no Bedrock trait reports vertical
  connections).
- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order; PR #221).
- **Links:** #56, #67, #220.

## 2026-10-14: a vanilla texture reference names Bedrock's own vanilla texture of the same file name; no art is copied

- **Status:** approved (Alex, 2026-10-14)
- **Decision:** a mod model or item icon that borrows a vanilla texture
  (`minecraft:block/iron_block`, bare `block/stone`, pre-1.13
  `blocks/planks_oak`, `minecraft:item/stick`) points at the texture the
  vanilla Bedrock resource pack already ships, through an index of
  bedrock-samples' vanilla `terrain_texture.json` / `item_texture.json` /
  `flipbook_textures.json` (short names and file paths only) that
  `portkit reference fetch` derives and caches (sha256-pinned, never vendored,
  #24). The pack never carries Mojang art.
  1. **Same file name** (pick 1): Java's `block/<name>` (`item/<name>`) is
     Bedrock's `textures/blocks/<name>` (`textures/items/<name>`). Where a
     plain one-file vanilla short name shows exactly that file, the material
     instance / icon names it (the same-named one if there is one, else the
     flipbook's own tile for an animated file, else the first alphabetically;
     they all show the same file). Bedrock merges a pack's atlases with
     vanilla's, so the name resolves without an entry of ours.
  2. **Renamed textures stay residue** (pick 2): a Java name that is a
     vanilla short name showing a file of another name (`oak_planks` ->
     `textures/blocks/planks_oak`) is not mapped; the residue says which file
     the short name shows. (`models.MAP_RENAMED` flips it.)
  3. **A file only inside a variant set** (pick 3): where no one-file short
     name shows the file (`barrel_top`, `diamond_sword`), the pack's atlas gets
     an entry `<ns>:vanilla/<block|item>/<name>` -> the vanilla file path,
     which the vanilla pack below serves. A mod's own keys flatten `/`, so
     these keys never collide with them. Entries that dress their file (an
     overlay or tint colour) are not named directly; the file gets our entry.
  4. **Animated files** only through vanilla's own flipbook tile; a
     vanilla-animated file with no such short name stays residue (an entry of
     ours would show the whole strip).
  5. **Render method** (pick 4): a vanilla texture on a custom shape gets
     `alpha_test`, the existing "unreadable counts as having holes" rule, since
     the jar holds none of vanilla's pixels. Full cubes keep no render method,
     as for mod textures.
  6. **Version** (pick 5): names are judged against the pinned Bedrock index
     alone, whatever game version the mod targets.
  7. **Tint** (pick 6): a face with `tintindex` keeps today's rule for mod
     textures (no tint applied); vanilla's grayscale textures (leaves, grass)
     will show grey there.
  8. Anything else stays residue, labelled "a vanilla texture: ...": no Bedrock
     file of that name, a short name that is a set of variants, a texture
     outside `block/` and `item/`, or no index cached (run the fetch). Nothing
     is substituted.
  Vanilla parent models (`block/cross`, `block/button`, `block/orientable`,
  ...) are a separate gap and unchanged here.
- **Why:** the file name is the one identity Java and Bedrock share that a
  converter can check; Mojang named Bedrock's files after the same textures.
  Of 564 Java 1.21.1 textures with a same-named one-file Bedrock short name,
  510 are pixel-identical to bedrock-samples' file (the rest are edition art
  differences: cactus, fern, water, grindstone, piston side); checked locally
  against the 1.21.1 client jar, nothing kept. Short names are Bedrock's own
  labels and do not always mean Java's texture: Bedrock's `piston_top` shows
  `piston_inner`, the `command_block_*` short names show `*_mipmap` files of
  another size. Referencing vanilla by short name or path is how packs layer
  on vanilla (bedrock-wiki concepts/overwriting-assets; Mojang's own
  `minecraft:red_shrub` block names the vanilla short name `red_shrub`;
  minecraft:material_instances `texture` and minecraft:icon `textures` name
  atlas keys, MicrosoftDocs minecraft-creator).
- **Rejected:** copying vanilla art (Mojang's, EULA); a hand-written
  Java->Bedrock name table (fabrication, #87); nearest-name or nearest-look
  matching (substitution).
- **Links:** PR #220; #24, #87, #124.

## 2026-10-14: 6-way facing and attach-face blocks with booleans convert, combining the #218 placement with the #215 booleans

- **Status:** approved (Alex, 2026-10-14)
- **Decision:** a blockstate drawing 6-way `facing` or `face` + `facing` and
  one to four booleans (variants naming every combination, or a multipart
  with exactly one part per combination; waterlogged dropped first, #217)
  converts through the #218 converter with #215's boolean half:
  1. **Placement** exactly as #218 (`blockcode.read_directional_states` runs
     `read_directional`'s rule per clicked face; same DEFAULT, same conflicts,
     canSurvive not emulated).
  2. **Booleans** exactly as #215: one Bedrock state `<ns>:<name>` per
     boolean, values `[start, other]`; start = what getStateForPlacement puts
     on every path of the six clicked-face runs (*placed*), else the
     registered default state, else StateDefinition#any's, else labelled
     DEFAULT false. A start that differs between clicked faces falls back
     like any start that differs between paths.
  3. **Box** per (Java variant, booleans) from getShape, else the turned
     model's bounds (DEFAULT); **light** per combination of the booleans from
     Properties.lightLevel with the placement states unknown (#213's
     refusals; a light reading facing/face is refused).
  4. **Toggle** as #215 (useWithoutItem flips exactly one drawn boolean on
     every path, server side, no useItemOn), checked at every (face, facing,
     booleans); it must leave facing/face as they were. The fixed
     `toggle.js` sets the permutation with that one state flipped
     (`permutation.withState`), so the placement states, and the Java
     variant they stand for, stay.
  5. **Vanilla parents:** `FaceAttachedHorizontalDirectionalBlock` counts as
     plain (its placement is the vanilla code #218 supplies, cited L39-52;
     it changes no boolean). `ButtonBlock` and `LeverBlock` flip `powered` in
     vanilla code the jar doesn't hold (use, scheduled tick), so a block
     reaching them stays residue, as #215 does for FenceGateBlock. Where the
     classes can't be read (SRG/intermediary jars, Registrate), the class
     isn't known and the block takes the labelled DEFAULTs, static, as #215.
  6. **Permutations:** a component that follows the placement states alone
     (the y turn) goes in one permutation per Java variant, one that follows
     the booleans alone (light) in one per combination, the rest (a box) per
     (variant, combination). At most block_face (6) x cardinal_direction (4)
     x facing_direction (6) x 2^4 = 2,304 permutations per block, under
     Bedrock's 65,536 per block ("A block cannot have more than 65,536
     permutations", Bedrock-OSS bedrock-wiki docs/blocks/block-permutations.md);
     the world-wide 65,536 is a performance warning (MicrosoftDocs
     minecraft-creator BlockStatesAndPermutations.md, "Unlimited* Power");
     the largest converted pack here (Create) declares 3,041.
  7. **Pack file names (new, pick 1):** Minecraft Creator Tools (mct 0.20.0)
     reads any file named `package.json` (also `package.lock`, `tsconfig`,
     `jsconfig`, `jsdoc`, `docfx`, `.prettierrc`) as a JavaScript tooling
     file wherever it sits, and a pack with scripts and such a file fails its
     SCRIPTMODULE check with an error ("Could not find an package.json
     registration for @minecraft/server"). Refurbished has an item named
     `package`, and its pack now carries the toggle runtime, so mct went from
     0 to 1 error. A block or item definition with such a name is written as
     `blocks/_<name>.json` / `items/_<name>.json` (`pack.write_tree`; Bedrock
     finds definitions by folder; the identifier inside is unchanged), unless
     that name is taken. mct back to 0 errors.
- **Why:** the deco spike's ceiling fans, ceiling lights and light switches
  (MrCrayfish Refurbished) and buttons (Cluttered, BetterEnd) were residue
  only because #218 left booleans out of scope. Every value is read by a
  rule Alex already approved; nothing new is guessed. Deco (not banked):
  Refurbished 230 -> 252 blocks (29.8 -> 30.8%): 20 ceiling fans (placement
  read: facing = clicked face's opposite; lit read as a use toggle; light 15
  at lit+powered, powered set only by the block entity's power network so
  static false) and 2 light switches (vanilla attach placement, enabled read
  as a toggle); boxes DEFAULT (Refurbished builds shapes from a generated
  map). Its pack now carries the toggle runtime (pack floor 1.21.90). The
  2 ceiling lights stay residue (a model with no elements); Cluttered's 10
  buttons stay residue (vanilla ButtonBlock). mct 0 errors.
- **Rejected:** treating vanilla ButtonBlock's press as a toggle (Java
  unpresses it on a scheduled tick; inventing that is #87); one Bedrock
  permutation per cell for every component (correct but bigger); for item 7,
  keeping the file name and accepting mct's false positive.
- **Links:** PR #219; #215, #218, #213, #217, #87.

## 2026-10-14: 6-way facing and attach-face blocks convert, placement read per clicked face onto block_face / cardinal_direction / facing_direction

- **Status:** approved (Alex, 2026-10-14)
- **Decision:** a `variants` blockstate whose only state is `facing` over all
  six directions (Java `DirectionalBlock` / `BlockStateProperties.FACING`), or
  `face` (floor/wall/ceiling) with a horizontal `facing`
  (`FaceAttachedHorizontalDirectionalBlock` / `ATTACH_FACE`), one model per
  variant in quarter x/y turns, converts outside stations (waterlogged dropped
  first, #217). The placement rule is read by `blockcode.read_directional`:
  `getStateForPlacement` runs once per face the player can click, the clicked
  face known (`getClickedFace`; `getNearestLookingDirections` gives its
  opposite first, BlockPlaceContext L76-96), the player's horizontal facing and
  nearest looking direction as symbols; vanilla
  `FaceAttachedHorizontalDirectionalBlock#getStateForPlacement` (L39-52) and
  `#getConnectedDirection` (L64-70) are supplied from the MC 1.21.1 client jar
  (Mojang mappings), `Direction#equals` is identity and `Direction#getAxis` and
  `AttachFace` values/ordinals are known. Each clicked face must give one state:
  the rule is then, per clicked face, the `face` value and `facing` as a fixed
  direction, the player's facing turned by quarters, or the player's looking
  direction (or its opposite). Bedrock maps it with no y_rotation_offset:
  `minecraft:block_face` (placement_position, "the face of another block on
  which this block was placed") for the clicked face,
  `minecraft:cardinal_direction` / `minecraft:facing_direction`
  (placement_direction) for the player's facing; each reachable Java variant is
  one permutation whose condition is exactly the trait states that place it
  (traits only when used; block format 1.20.20, as the docs' examples).
  `canSurvive` is not emulated: where placement asks it, it reads true (the
  clicked face holds the block up), and the notes say so per block. Unread
  rule -> labelled DEFAULT: 6-way = facing is the clicked face (vanilla rods,
  amethyst clusters); attach = vanilla's FaceAttached rule. Read-but-conflicting
  (the player never sets facing; an attach facing from a vertical direction)
  stays residue. Geometry: Java's x turn baked into the model with
  `models.turn_rigid(carry_rotation=True)` (an element rotation goes with the
  turn: axis turned, angle sign flipped when it lands reversed, origin moved),
  one bone per (model, x); Java's y turn by `minecraft:transformation` as #212;
  uvlocked variants turned whole by `turn_locked`, own bone, no transformation.
  So no transformation ever turns about x. Box per Java variant from
  `getShape` (bounding box, in the frame the geometry is drawn in, x flipped as
  `models.X_AXIS_IS_FLIPPED` like #212), else DEFAULT the turned model's
  element bounds; collision as #212. Variants the rule never reaches get no
  permutation and are named. Light from #213's whole-block reading. Booleans
  with 6-way / attach (Refurbished ceiling fans and lights, light switches,
  buttons) stay residue; a later PR.
- **Why:** both Java patterns were residue (#212 and #215 read 4-way facing
  only). Bedrock's traits give exactly the inputs Java's placement reads
  (MicrosoftDocs minecraft-creator `traits/placement_position.md`,
  `traits/placement_direction.md`, `Documents/intro-block-traits.md`, all
  shown at format 1.20.20); running the code per clicked face turns any
  deterministic rule into a table of trait states, so nothing is guessed.
  `minecraft:transformation` documents rotation only as "in increments of 90
  degrees" (`minecraftBlock_transformation.md`), not its x sign or order with
  y, and the repo's turn conventions are already pinned for Java's rigid turn
  (`models._turn_vector`, tested against rotated-element corners), so x stays
  out of transformation. Deco (not banked): Cluttered 635 -> 674 blocks
  (54.2 -> 55.3%), Fairy Lights port 0 -> 1; all 40 read from bytecode
  (placement and box); mct 0 errors. Standard corpus rebanked.
- **Rejected:** transformation [x, y, 0] for every variant (x sign and order
  unverified); y_rotation_offset to express "faces the player" (doesn't turn
  up/down, and the mapping does it anyway); a clicked-face-only reading without
  emulating vanilla FaceAttached (inherited placement is the common case);
  emulating canSurvive (needs the world); booleans in this PR (scope).
- **Links:** PR #218; #212, #213, #215, #217; deco-mods spike gap 8.

## 2026-10-14: a blockstate that draws waterlogged converts without it, and Bedrock holds the water through liquid_detection where getFluidState says the block holds water

- **Status:** approved (Alex, 2026-10-14)
- **Decision:** a `variants` blockstate that draws `waterlogged` with the same
  model at `waterlogged=true` and `=false` for every other combination
  converts with the state dropped, through whichever converter its other
  states fit (a plain block, facing-only (#212), facing plus booleans (#215),
  stairs/slabs...). waterlogged is never a Bedrock state, so it doesn't count
  toward #215's four booleans and adds no permutations. A blockstate whose
  model depends on waterlogged, that leaves it out of some variants or lacks
  one of its values, or a multipart that tests it, stays residue with that
  reason. Stations are left as they were. A converted block gets
  `minecraft:liquid_detection` `{"detection_rules": [{"liquid_type": "water",
  "can_contain_liquid": true, "on_liquid_touches": "blocking"}]}` when its
  code holds water while waterlogged (`blockcode.read_water`: `getFluidState`
  run at waterlogged=true and false gives `Fluids.WATER.getSource(false)` only
  at true), nothing when it never holds a fluid (`getFluidState` is vanilla
  `BlockBehaviour`'s, so Java's state is cosmetic), and the labelled DEFAULT
  `can_contain_liquid: true` when the code isn't read (the blockstate draws a
  waterlogged state). Such a block is written at block format 1.21.60 at least
  (a higher one, such as the toggle's 1.21.90 or the shapes' 1.26.0, is kept),
  and the pack floor follows (`pack.engine_floor`). Notes name each block's
  reading (class#getFluidState) or DEFAULT, and the blocks that aren't a
  `SimpleWaterloggedBlock` in Java (no bucket there).
- **Why:** waterlogged draws nothing in Java. The water is the state's fluid,
  drawn by the fluid renderer, and what makes it water is `getFluidState`:
  vanilla `BlockBehaviour#getFluidState` (L248) returns
  `Fluids.EMPTY.defaultFluidState()`, and a waterloggable block returns
  `Fluids.WATER.getSource(false)` (`FlowingFluid#getSource` L251) when
  WATERLOGGED is true. Java's flowing water doesn't enter a waterloggable block
  (`FlowingFluid#canHoldFluid` L408-411 asks
  `LiquidBlockContainer#canPlaceLiquid`, and `SimpleWaterloggedBlock#canPlaceLiquid`
  L22 accepts only `Fluids.WATER`, the source), which is Bedrock's `blocking`
  (MC 1.21.1 client jar, Mojang mappings, javap). Bedrock keeps water in a
  block position's second layer (Bedrock-OSS bedrock-wiki
  `docs/blocks/block-colocation.md`), and `minecraft:liquid_detection` lets a
  custom block hold it ("Whether this block can contain the liquid. For
  example, if the liquid type is water, this means the block can be
  waterlogged"; "requires a format version of at least 1.21.60",
  MicrosoftDocs/minecraft-creator `minecraftBlock_liquid_detection.md`). It
  left the Upcoming Creator Features experiment for block format 1.21.60 and
  above (Minecraft 1.21.60 Bedrock changelog). `use_liquid_clipping` needs
  1.26.0 and is left out: below 1.26.0 it defaults to true (the water is
  clipped to the block's collision box). Placement in water is the engine's:
  Java sets waterlogged in `getStateForPlacement` from the fluid at the
  clicked position, and nothing is emitted for it.
- **Rejected:** keeping waterlogged as a Bedrock boolean state (it draws
  nothing, doubles the permutations, and Bedrock already has a water layer);
  `liquid_detection` from the blockstate alone (a declared state with a
  vanilla `getFluidState` never holds water in Java); writing waterloggable
  blocks at 1.26.0 so `use_liquid_clipping` can be false (raises the floor of
  every pack with one; Alex's call, pick 6 on PR #217); `on_liquid_touches: no_reaction`
  (Java's flowing water doesn't pass through a waterloggable block).
- **Links:** PR #217; deco-mods spike gap 5; #212, #215.

## 2026-10-14: a negative-size model element (from > to on an axis) converts as the quads Java bakes from it, unfolded into ordinary elements

- **Status:** reproduces Java's renderer; no new policy
- **Decision:** `models.resolve` (and `geometry_bones`, for elements read any
  other way) rewrites every element with `from` > `to` on some axis as
  elements with `from` <= `to` that Java bakes to the same quads, corner for
  corner and uv for uv. A face that points out of the sorted box stays on that
  box, under the name of the way it really faces; a face that points into it
  becomes a zero-thickness element on its plane. A face without a uv first
  takes the uv Java derives from the raw `from`/`to`. The face's texture turn
  is adjusted where the move turns the texture (always 0 or 180 degrees in
  practice: a half turn when two axes are swapped, or on the swapped axis's own
  faces). A uvlocked blockstate turn of such an element stays residue, with a
  reason.
- **Why:** Java never sorts an element's corners. The deserializer only checks
  each coordinate is in [-16, 32] (`BlockElement$Deserializer#getFrom/getTo`
  L147-163). `FaceBakery#setupShape` (L114-121) stores `from` as
  MIN_X/MIN_Y/MIN_Z and `to` as MAX_X/MAX_Y/MAX_Z as written. Each face's
  vertices are read from those six numbers through `FaceInfo` (`<clinit>`
  L7-32), and vertex i takes `BlockFaceUV#getU(i)/getV(i)` (L25-38). Then
  `FaceBakery#bakeQuad` (L49) names the quad by `calculateFacing` (L198-223:
  the normal of (v2 - v1) x (v0 - v1), nearest Direction), which is the side
  the winding draws it on. All of this is from the MC 1.21.1 client jar with
  Mojang mappings. So with an axis swapped, a face keyed to that axis's
  minimum lands on the larger coordinate. A face with one of its in-plane
  axes swapped is wound the other way and faces the opposite direction.
  Blockbench's "inverted" cubes are an example: a basin interior, or Tinkers'
  tank insides. Every face on one of those points inward. Unfolding in Java
  space means everything after it (turns, splits, bounds, materials, the X
  mirror) handles these elements as it already handles any other. The tests
  compare all 7 swap patterns x 4 face rotations, with and without uv,
  against a Java baking written from those methods.
- **Rejected:** sorting `from`/`to` and keeping each face's name. Every
  inverted interior would then turn outward and render over the outside of
  its own block. Leaving the elements residue, as before: 117 Refurbished
  blocks failed on it. Mirroring with a negative uv_size instead of a 180
  texture turn: the face turn was read in game (#68/#71), and a negative
  uv_size on both axes has not been. Carrying uvlock over: uvlock
  (`FaceBakery#recomputeUVs` L61-102) re-maps a face's uv by the face it was
  declared as, not the way it really faces, and that mapping hasn't been
  worked out.
- **Not verified in game:** zero-thickness cubes in Bedrock block geometry.
  Also, which side of a face Bedrock draws depends on its render method:
  `alpha_test` "also disabled backface culling", and so does `double_sided`
  (Microsoft Learn, minecraft:material_instances, Render Method choices). An
  inward face with one of those can also be seen from outside. That was
  already true of every converted face.
- **Links:** #87; deco-mods spike gap 3.

## 2026-10-14: blocks with facing and boolean states convert outside stations, each boolean's start, toggle and light read from bytecode

- **Status:** approved (Alex, 2026-10-14)
- **Decision:** a blockstate that draws `facing` (north/east/south/west) and
  one to four boolean states (`lit`, `open`, `powered`, `on`...), with one
  model per state (a `variants` map naming every combination, or a multipart
  where exactly one part applies at each), converts outside station runtimes
  the way a facing-only block does (#212: placement and box read from
  bytecode, else the labelled DEFAULT), plus:
  1. **States:** one Bedrock state per boolean, `<namespace>:<java name>`,
     values `[start, other]` ("The first item in the values array is used as
     the default", Bedrock-OSS bedrock-wiki docs/blocks/block-states.md).
  2. **Start value** (`blockcode.read_state_blocks`): the value
     `getStateForPlacement` puts in the state it returns on every path
     (*placed*); where that reads the world (a redstone signal, the fluid), the
     registered default state's (`registerDefaultState` in the constructor,
     *registered*); a boolean the code never sets, `StateDefinition#any`'s,
     whose booleans are true (*any*: StateDefinition#any L92 is the first
     state, BooleanProperty's values are `ImmutableSet.of(true, false)`,
     BooleanProperty#<init> L12-14, MC 1.21.1 client jar + Mojang mappings);
     otherwise DEFAULT false, labelled per block. `BlockStateProperties`'
     48 boolean fields are known by the name their `<clinit>` creates them
     with (client jar class `dts`), so `BlockStateProperties.ENABLED` reads as
     `enabled` instead of an unknown property.
  3. **Models:** one geometry with a bone per model drawn (per model and turn
     for a uvlocked variant, turned with `models.turn_y`), each shown by
     `bone_visibility` at the states that draw it; a non-uvlocked model turns
     whole per `minecraft:cardinal_direction` with `minecraft:transformation`,
     as #212. Two models with one texture key and different textures get a
     key each, as station states do.
  4. **Box and light per permutation:** `getShape` run at every (facing,
     booleans) gives each permutation's selection/collision box (else #212's
     DEFAULT: the bounds of the model drawn there); `Properties.lightLevel`
     run at every combination of the booleans (code-only states at their
     placed value) gives `minecraft:light_emission` per permutation, with
     #213's refusals (copied vanilla Properties, `getLightEmission`
     override, shared Properties, outside 0-15). This replaces #213's pick 4
     deferral for these blocks.
  5. **Toggle:** read only when `useWithoutItem` (`use` before 1.20.5), run
     on the server (`Level.isClientSide` false) at every state, calls
     `Level#setBlock` once on every way through it, at the clicked position,
     with exactly that one boolean flipped (`state.cycle(P)`, StateHolder#cycle
     L54 / findNextInCollection L58-69, or `setValue(P, !getValue(P))`), and
     the block's classes don't override `useItemOn`. Such a block carries
     `<namespace>:portkit_toggle` (block format 1.21.90) and the fixed runtime
     `portkit/runtime/toggle.js` flips the state in `onPlayerInteract`
     (@minecraft/server 2.0.0, custom components v2), wired into
     `scripts/portkit/main.js` beside the stations. Sounds and particles in the
     Java method aren't carried.
  6. **Everything else is static** at the start value, named per block in the
     notes with the methods of the block's own classes that change it in
     Java (`+redstone` when that method reads a signal: a Bedrock custom
     block has no redstone input). A use that flips a boolean only sometimes
     (sneaking, a seat, a menu) is not a toggle. No toggle is invented (#87).
  7. **Refused:** a block class reaching a vanilla class with behaviour of its
     own (FenceGateBlock, LanternBlock, JukeboxBlock...) stays residue, since
     its states are vanilla code the jar doesn't hold; a blockstate drawing
     `waterlogged` is left to the other converters (later); a multipart this
     doesn't read is left to `_facing_parts` as before. A block that fails
     claims none of the models it looked at, so residue counts don't move
     when nothing converts.
- **Why:** #214 made 63 more MrCrayfish Refurbished registrations readable and
  most of them carry lit, powered or open; the deco spike counted 197 blocks
  with facing plus a toggled boolean. Reading each boolean from the code that
  sets it keeps the bytecode-first rule (labelled DEFAULT otherwise), and the
  same reader that gives the start value gives the light per state.
- **Rejected:** treating every boolean as a use toggle (invented behaviour);
  picking `false` for every start (wrong for code that places a block lit or
  never sets a boolean); one Bedrock block per combination (the item and
  `/setblock` would need N blocks); converting vanilla-parent blocks at
  DEFAULTs (a fence gate that never opens and has the wrong box).
- **Links:** #212, #213 (pick 4), #214, #87.

## 2026-10-14: a registration that passes several lambdas registers the one that supplies the block, picked by its lambda signature

- **Status:** reader fix under the approved #212/#213 rules (read from bytecode first, labelled DEFAULT otherwise); no new policy
- **Decision:** when one registration call passes the block and its item as
  separate lambdas (MrCrayfish Framework's `RegistryEntry.blockWithItem(id,
  Supplier<T> supplier, Function<T, E> function)`, `T extends Block, E extends
  BlockItem`; Framework multiloader/1.21.1, RegistryEntry.java L156),
  `blockcode` registers the lambda whose `dynamicMethodType` (named
  instantiatedMethodType in older javadoc; the third static argument of
  `LambdaMetafactory.metafactory`, "the signature and return type that should
  be enforced dynamically at invocation time", Java SE 21 javadoc) takes no
  arguments and returns a class that reaches a vanilla block class. Every value in the call must be a lambda and exactly one must qualify;
  otherwise (two block suppliers, a `Supplier<?>` erased to `Object`, a
  non-lambda value) nothing is registered and the block is unread with that
  reason, so its facing, box, collision and light take the labelled DEFAULT or
  stay unconverted as before (#87). Argument order doesn't matter. Calls with
  one lambda are unchanged.
- **Why:** the item function takes the block (`(LampBlock)LampItem`), so it can't
  be what builds it; the signature is in the class file at the call site, so the
  pick is deterministic and citable. Before this, such calls registered nothing
  and 60 Refurbished blocks (lamps, ceiling fans and lights, range hoods, stoves,
  toasters, microwaves, mail boxes, light switches, doorbell, TV) read as "no
  registration found"; 3 more (computer, recycle_bin, workbench) were named only
  by their menu registration. All 63 now read; none of them converts yet (their
  blockstates carry more than `facing`), so converted output is unchanged.
- **Rejected:** picking by position (first or last lambda): registries differ,
  and nothing in the class file says which slot is the block. Running every
  lambda and keeping whichever builds a block: an item function given an
  unknown block may still build something, and two block suppliers would need a
  tie-break we can't cite.
- **Links:** #212, #213 (side finding), #87.

## 2026-10-14: block light emission is read from the jar's bytecode (Properties.lightLevel); a light that can't be read is not emitted

- **Status:** approved (Alex, 2026-10-14)
- **Decision:** every block `converters/blocks.py` writes gets its light from
  its compiled code, through `blockcode.read_light` (the #212 interpreter).
  Java gives each state `properties.lightEmission.applyAsInt(state)`, the
  function being whatever `Properties.lightLevel` was last given, `state -> 0`
  when nothing was (BlockBehaviour$Properties#<init>, MC 1.21.1 client jar +
  Mojang mappings: the default lambda is `iconst_0; ireturn`), and
  `ofFullCopy`/`ofLegacyCopy` copy the copied block's. The function is run on
  abstract states:
  - one value for every state (`state -> 15`, or branches that all agree) ->
    `minecraft:light_emission: N` in the block's components, cited
    class#lambda in the notes; 0 emits nothing;
  - never set -> read as no light (the vanilla default), nothing emitted;
  - the function reads only states the blockstate doesn't draw (code-only
    states, which Bedrock doesn't carry, so the block keeps the state it is
    placed in) -> the value at the state `getStateForPlacement` returns, noted
    as read "at the placed state" (Night Lights: `lit ? brightness : 0`,
    placed lit at 8 or 10);
  - anything else is NOT converted and the block emits no light (Bedrock's
    default), listed per block with the reason: a light that depends on a
    state the converted block carries (one value can't stand for every
    permutation), Properties copied from a vanilla block (the repo holds no
    cited table of vanilla light levels), a NeoForge `getLightEmission`
    override in the block's own classes (it can read the world), a value
    outside Bedrock's 0-15 ("in a range of 0-15", MicrosoftDocs
    minecraftBlock_light_emission.md), a Properties object shared between
    registrations and changed by one of them (what each block gets then
    depends on registration order), or code that can't be followed (Forge
    SRG / Fabric intermediary names included).
  A block another path already lit (a station runtime citing its light, e.g.
  Farmer's Delight's stove) keeps that light. No light value is ever a
  default standing in for one that wasn't read (#87). Shared interpreter
  changes: Properties change in place (a dropped return value counts) and a
  block keeps a copy of them as they were when it was built (Java computes
  each state's light in `BlockStateBase#<init>`, L808-834); every
  registration found is built, so a shared-Properties change is seen
  whichever blocks are asked about; a renamed Properties call makes both
  collision and light unknown instead of being ignored; a vanilla block
  class whose Properties aren't its first argument
  (`DoorBlock(BlockSetType, Properties)`) keeps them.
- **Why:** light is the decoration genre's visible gap (no converted block
  had any). Reading the code is deterministic and citable, as #212 settled for
  placement and boxes; when it can't be read, a dark block is an honest
  shortfall where a guessed light level would be a fabrication.
- **Rejected:** a constant maximum for state-dependent lights (Night Lights
  would glow 13, a level the placed block never has); a default light for
  unread blocks; resolving copied vanilla Properties from PrismarineJS
  minecraft-data (`emitLight` is the default state's only: furnace 0,
  redstone_lamp 0, sea_pickle 6); Decocraft's `lighting.json` now (its own
  schema, and 0 Decocraft blocks convert yet).
- **Links:** PR #213; deco-mods spike (2026-10-14); #212, #87.

## 2026-10-14: facing-only blocks convert outside the station runtimes, placement and box read from the jar's bytecode, else a documented default

- **Status:** approved (Alex, 2026-10-14), all ten of Hark's picks (PR #212).
- **Decision:** a block whose blockstate is exactly `facing=north|east|south|west`
  (one model, a quarter turn about y per facing, no x) and that is no station
  converts. Its geometry is the model as written, turned per
  `minecraft:cardinal_direction` by `minecraft:transformation` (Java turns the
  whole model, rotated elements and textures included, as transformation does;
  the box turns with it, Bedrock-OSS wiki blocks/block-orientation); a
  uvlocked model instead gets one bone per facing through `models.turn_y`,
  which needs unrotated elements. The block's placement rule and box come from
  its compiled code, read by `portkit/bytecode.py` (a class-file reader, JVMS
  ch. 4) and `portkit/blockcode.py` (an abstract interpreter that runs the
  registration, `getStateForPlacement` with the player's horizontal direction
  as a symbol, and `getShape` once per facing; vanilla `Block.box`,
  `Shapes.box/or/join(OR)/block/empty`, `Stream.reduce`, enum switch maps,
  `ImmutableMap`/`Maps.newEnumMap`/`Map.get` and `Properties.noCollission`
  are modelled; anything else is unknown, a branch on an unknown runs both
  ways and counts only when both agree). Vanilla behaviour it relies on is
  read from the 1.21.1 client jar with Mojang's mappings:
  `Block#getStateForPlacement` returns `defaultBlockState()`,
  `BlockBehaviour#getShape` is `Shapes.block()`, `#getCollisionShape` is
  `hasCollision ? getShape : empty`, and `HorizontalDirectionalBlock`,
  `TransparentBlock`, `HalfTransparentBlock`, `BaseEntityBlock` override none
  of the three. Read values map as: facing = `getHorizontalDirection()` ->
  `y_rotation_offset` 0, `.getOpposite()` -> 180; the Bedrock box is the
  bounding box of Java's shape at each facing (one box per block; cut to the
  block's edges), per permutation when it differs in the model's frame;
  `noCollission` -> `minecraft:collision_box: false`. Where a value can't be
  read deterministically (no registration found, unknown calls, Forge SRG or
  Fabric intermediary member names, `Properties.ofFullCopy`), the documented
  DEFAULT stands in: placement faces the player (offset 180), box = the
  model's element bounds (from/to, element rotations ignored), collision = the
  selection box. Code that was read but asks for something the placement trait
  can't give (a quarter turn from the player, or a facing the player never
  sets) stays residue. The conversion notes name every block's placement, box
  and collision as read (`class#method`) or DEFAULT with the reason, never one
  as the other (#87), plus code-declared states the blockstate doesn't draw
  (`waterlogged`, `lit`) and behaviour methods the block overrides, which a
  decoration-only block doesn't carry. Class files are kept in memory at
  ingest (`Ingested.classes`), never staged, and are still residue.
- **Coverage (deco manifest, not banked):** MOA DECOR: TOYS 39.9 -> 72.3%
  (0 -> 177 blocks), Plushie Buddies 38.4 -> 71.1% (0 -> 76), Night Lights
  83.8 -> 95.7% (0 -> 82), Cluttered 46.7 -> 47.5% (353 -> 387), Refurbished
  19.2 -> 20.0% (17 -> 28); Beautify and Seafoam unchanged; mct 0 errors on
  all. Of the 380 blocks, placement is read for 379 (1 default), the box for
  368 (12 default), collision for 297 (83 default). Standard corpus (banked):
  +60 blocks in 7 mods, 59 of them on the defaults (SRG/intermediary jars,
  registries the interpreter doesn't follow), Farmer's Delight NeoForge's
  half tatami mat read.
- **Why:** Alex's decision (2026-10-14): read each block's facing rule and
  hitbox from bytecode first, fall back to a clearly labelled default, keep
  the no-fabrication rule. Decoration mods are mostly facing-only blocks (8 of
  12 measured converted none), and their code follows a handful of compiler
  patterns that read deterministically.
- **Rejected:** a per-mod citation table (doesn't scale to MCreator's one class
  per block); defaulting without reading (Refurbished faces *with* the player,
  offset 0, which a default would get wrong); extending `turn_y` to rotated
  elements (a whole-model transformation is exact for any element rotation);
  a JVM or decompiler dependency (the reader and interpreter are ~1.7k lines of stdlib Python).
- **Links:** PR #212; #87 (no fabrication), #177 (station facing blocks),
  #56 (facing-only blocks counted in the behaviour sweep).

## 2026-10-14: a Java id with a hyphen stays that id on Bedrock; the validator takes "-" in block, item, recipe and loot ids

- **Decision:** the validator's identifier rule (`validate/rules.py`
  `_IDENTIFIER`, used for block ids, recipe ids and loot-entry item names) is
  now `^[a-z0-9_-]+:[a-z0-9_/.-]+$`: Java's identifier characters, with the
  hyphen added on both sides of the colon. The converter keeps mapping a Java
  id to the same Bedrock id (`converters.items.bedrock_identifier` is the
  identity), so `wallpapercraft:woolblue-0` ships as `wallpapercraft:woolblue-0`
  with no rename, no mapping table and no collision handling. The `.lang` name
  check in `validate/xrefs.py` reads the same id shape, so a hyphenated block
  with a `tile.<id>.name` line is no longer reported as unnamed. Texture keys
  (terrain/item atlas) keep the old `[a-z0-9_]` rule as `_TEXTURE_KEY`, since
  the texture converter already maps `-` to `_` there (#168).
- **Why:** every Mojang source that constrains these ids admits a hyphen, and
  none excludes it:
  - Mojang/bedrock-schemas @fc31f9af `schemas/bp/blocks/block_description.schema.json`:
    block `identifier` pattern is `^\S+$` (any non-whitespace); the same file is
    vendored in `src/portkit/validate/schemas/1.26.60/`.
  - Same repo, `schemas/bp/items/item_description.schema.json`, the one
    recipe schema it publishes (`schemas/bp/recipes/brewing_mix_recipe_definition.schema.json`,
    description `identifier`) and `schemas/bp/loot_tables/loot_loot_entry.schema.json`
    (`name`: "The item identifier"): plain strings, no pattern.
  - Same repo, `schemas/bp/biomes/biome_biome_description.schema.json`: the one
    id with its character set spelled out, `^[a-z0-9._%+-]+:[a-z0-9._%+-]+$`.
  - Mojang/bedrock-samples @46ba6ea9 `metadata/json_schemas/server/block/1.26.20/Description.json`
    (block identifier `^\S+$`, flags `ECMAScript,icase`) and
    `server/item/1.26.30/description.json` (no pattern).
  - Microsoft Learn: block description "must include a namespace and must not
    use the Minecraft namespace" with no character rule
    (https://learn.microsoft.com/en-us/minecraft/creator/reference/content/blockreference/examples/blockdescription);
    item `minecraft:item` the same; biome description gives the
    `^[a-z0-9._%+-]+:[a-z0-9._%+-]+$` pattern (MicrosoftDocs/minecraft-creator
    `creator/Reference/Content/BiomesReference/Examples/Components/biome_description.md`,
    https://learn.microsoft.com/en-us/minecraft/creator/reference/content/biomesreference/examples/components/biome_description);
    1.26.20 changelog: "Namespace constraints have been tweaked but everything
    permitted before should still be valid. This affects identifiers used for
    blocks, states, and menu category groups."
  - minecraft.wiki Identifier, Bedrock Edition: "The namespace and the path of
    a namespaced ID can contain all symbols with the exception of slashes and
    colons" (https://minecraft.wiki/w/Identifier). The Bedrock Wiki
    (wiki.bedrock.dev style guide, namespaces) gives naming advice
    (lowercase, snake_case) but no character rule.
  - Microsoft's own validator, Minecraft Creator Tools (`mct validate`
    0.20.0), reports 0 errors on Wallpapercraft's 2300 hyphenated blocks.
  - No vanilla id in bedrock-samples has a hyphen, so there is no in-game
    vanilla precedent either way; that is absence, not a rule.
  Wallpapercraft – Repainted 1.2.0 (NeoForge 1.21.1): validator errors
  2420 -> 0 (2300 `block.identifier` + 120 `recipe.identifier`), valid NO ->
  yes; output tree byte-identical (4911 files, residue 2577, 65.6%, 2302
  block files), mct 0 errors / 2595 warnings unchanged. The 13 corpus mods:
  rows, validity and mct counts unchanged.
- **Rejected:** rename `-` to `_` in the converter with a mapping table and
  collision detection. Nothing documented requires it, it would make Bedrock
  ids differ from the Java ids that `/give`, recipes, loot and the residue
  agent's guards key on, and it adds a collision class (`a-b` vs `a_b`) for
  no evidenced gain. Relaxing the rule to Mojang's literal `^\S+$`: it would
  stop the validator catching ids a Java mod cannot produce (uppercase, a
  missing namespace), which are agent mistakes here, not valid conversions.
  Relaxing texture keys too: no source documents them and #168 already maps
  them.
- **Not verified in-game:** placing, breaking, `/give` and `/setblock` with a
  hyphenated custom block id, and crafting a hyphenated recipe result.
- **Links:** PR #211; deco-mods spike gap 4; #168 (texture keys).

## 2026-10-14: "Return to Portal" is pinned to the top of waystone menus, as in Java, below the player's fleeting memorials

- **Status:** Return to Portal pinned to top as in Java; approved (Alex, 2026-10-14) (PR #210, Part of #178).
- **Decision:** "Return to Portal" (#206) now lists first, not last, in every
  menu that has it: waystone and sharestone menus, the warp scroll's and the
  warp stone's (the portal scroll's never lists it, `getTargetsForPlayer`).
  Java's screen sorts with `pinReturnPortalFirst`
  (`WaystoneSelectionScreenBase` L447-450, from `getSorting` L422-440), whose
  `isReturnPortal` (L246-249) is true for a `WARP_PORTAL` or a
  `FLEETING_MEMORIAL`, so both pin to the top together. Between them the
  player's sort mode decides; the default is MANUAL
  (`PersistentPlayerWaystoneData#getWaystoneSortMode` L257-262), the
  player's sorting index, which `ensureSortingIndex` (L270-290) extends in
  the order the menu's targets arrive, and `PlayerWaystoneManager` adds the
  memorials before the return portal (`getTargetsForWaystone` L313 then
  L318; `getTargetsForItem` L300 via `getTargetsForPlayer` L295, then L302).
  So the runtime lists the memorials (in the order they were made), then
  "Return to Portal", then the other entries.
- **Why:** Java pins it there; #206 appended it last, which #209 noted when
  it pinned the memorials.
- **Rejected:** keeping it last (not Java's order); putting it above the
  memorials (Java's default order adds the memorials first).
- **Not carried over:** the sorting index itself (a player's manual
  reordering, and an index that saw the portal before a memorial keeping it
  above), and the NAME and DISTANCE sort modes, as for the rest of the menu.
- **Links:** #178, #206, #209, PR #210; Waystones
  `WaystoneSelectionScreenBase`, `PlayerWaystoneManager`,
  `PersistentPlayerWaystoneData` at
  https://github.com/TwelveIterations/Waystones/tree/9d280c1ac8d036516a2927e3d2cad8054e491074.

## 2026-10-14: a player who dies with an epitaph leaves a fleeting memorial, listed at the top of their menus through the waystone runtime until a teleport reaches it

- **Status:** approved (Alex, 2026-10-14), all ten of Hark's picks (PR #209, Part of #178).
- **Decision:** Waystones' fleeting memorial (`FleetingMemorialBlock`,
  `ModBlocks` L88) and the epitaph (`ModItems` L49) work through the waystone
  runtime of #198-#208: a `fleeting_memorials` section in the same data
  table, the waystones' own component on the block, and one new event
  (`world.afterEvents.entityDie`). Waystones v21.1.46 @9d280c1a throughout.
  - **Making one** (`EpitaphDeathHandler` L12-31,
    `FleetingMemorialManager#spawnMemorial` L27-54): when a player dies
    carrying an epitaph, a memorial goes at `findMemorialPos` (L105-122): the
    block above their feet, else for each height 0..3 above the feet
    (`SEARCH_HEIGHT` L25) and each radius 1..2 (`SEARCH_RADIUS` L24) the
    square around them in `BlockPos#betweenClosed` order (x fastest, then z:
    Minecraft 1.21.1 `BlockPos$4#computeNext` L600-610, Mojang mappings),
    the first block that is replaceable and inside the world
    (`canPlaceMemorialAt` L124-126). It faces the player
    (`Direction.fromYRot(yaw).getOpposite()`, L35, #206's `portalFacing`).
    Only then is one epitaph used up (`shrink(1)`, L25) and the player hears
    `TOTEM_USE` 1/1 for themselves (`ClientEpitaphActivationHandler`
    L12-15: `forUI`; Java `item.totem.use` = `item/totem/use_totem` =
    Bedrock `random.totem`, misode/mcmeta 1.21.1 vs bedrock-samples
    46ba6ea9). No room: nothing happens, the epitaph stays.
  - **Finding the epitaph on Bedrock (not from Java):** Java looks through
    the inventory before anything drops; `entityDie` comes after Bedrock
    dropped it (unless `keepInventory`). So the runtime looks through the
    inventory (slots 0-35), then the off hand, then the epitaph item
    entities within 2 blocks of where the player died (nearest first), and
    removes the one it uses.
  - **The waystone:** a record of type `waystones:fleeting_memorial`
    (`WaystoneTypes` L13) owned by the player (`initializeWaystone` with the
    player, origin PLAYER), named `block.waystones.fleeting_memorial` (L45;
    shown through its Bedrock key `tile.waystones:fleeting_memorial.name`).
  - **Where it lists** (`FleetingMemorialManager#getTargets` L56-63: the
    owner's memorials): every menu Java builds from `getTargetsForPlayer` or
    `getTargetsForWaystone` (`PlayerWaystoneManager` L292-320): waystone and
    sharestone menus, the portal scroll's, the warp scroll's and the warp
    stone's; not a portstone's (`getTargetsForWaystoneType`), not the return
    scroll's nearest waystone. Pinned to the top
    (`WaystoneSelectionScreenBase#isReturnPortal` L246-249,
    `pinReturnPortalFirst` L447-450), in the order the memorials were made
    (Java's is its manager's hash order). The label is its name and, in
    LIGHT_PURPLE, `gui.waystones.waystone_selection.epitaph_requirement`
    with the epitaph's name (`EpitaphRequirement#appendHoverText` L28-32;
    its `canAfford` is always true and `consume` does nothing).
  - **Cost:** the `warpRequirements` default decided per route with a new
    `to_memorial` flag (`target_is_fleeting_memorial` true,
    `RequirementRegistry` L329-331; ACTIVATION visibility, so
    `target_is_global` false): from each waystone and sharestone menu type,
    the warp portal's teleport, the portal scroll's menu, the warp and bound
    scrolls and the warp stone. `[target_is_fleeting_memorial]
    multiply_xp_cost(0)` makes every one free at the defaults.
  - **Reaching it** (`handleTeleportComplete` L78-97 on every
    `WaystoneTeleportEvent.Complete`, `ModEventHandlers` L19): after a
    teleport that lands at a memorial (a menu, a bound scroll, a warp
    portal, any entity) its block is destroyed without drops (`removeAfterUse`
    L65-76; `setblock ... destroy` gives the break effects, its loot is empty)
    and its waystone forgotten. A memorial whose block is gone says
    "missing" and is forgotten (MissingWaystone -> `removeListing`). A warp
    portal opened to one closes on the next entrant (target invalid,
    `WarpPortalBlockEntity#onEntityInside` L107-119).
  - **Block:** facing alone (`createBlockStateDefinition` L140-142; the
    jar's blockstate), one bone per facing from the jar's model; Java's
    shape differs by facing (`SHAPES` L30-54), so each facing gets its own
    collision and selection box, the bounding box of its three Java boxes
    (new generic `FacingBlock.facing_boxes` -> permutations). The model's
    two elements with a 0-degree rotation now turn like unrotated ones (new
    generic `models.turn_y` rule: an angle of 0 is an identity; no other
    corpus mod changed). Light 6, no loot (`noLootTable`), no item, so in no
    creative tab (`registerBlock`, L88). Using it does nothing
    (`handleEditActions`/`handleActivation` give nothing, L98-102) except
    that a blank scroll binds a bound scroll to it (`WaystoneBlockBase#useItemOn`
    L257-262, `BlankScrollItem#useOn` L20-43); breaking it forgets it
    (`onRemove` L217-237).
  - **Epitaph:** `stacksTo(1)` (L49): `minecraft:max_stack_size` 1 (the item
    converter wrote 64); it stays in the items tab.
  - **Gating:** the memorial ships when a waystone or sharestone works, the
    epitaph item converted and the jar has the requirement text and the two
    names; otherwise its blockstate stays residue with the reason.
  - **Coverage:** Waystones 30.7 -> 30.9 (324 -> 326 files, residue 732 ->
    730), banked; no other mod changed.
- **Why:** the memorial is a waystone record like the warp portal's (#206):
  placed by the runtime, never by an item, a target in other menus, gone
  after use. So it reuses the records, `menu()`, `land()`, the item
  teleport and the portal, with a single `arrived()` hook standing in for
  Java's teleport-complete handler, and every number read from the classes,
  the config defaults and Minecraft's own `betweenClosed`.
- **Rejected:** scanning every player's inventory each tick to remember who
  carries an epitaph (a cost on every tick for a rare event; the dropped
  items are still there when `entityDie` arrives); requiring the epitaph to
  still be in the inventory (only true with `keepInventory`); listing
  memorials after the other entries (Java pins them first); a cost line or
  no requirement line (Java shows the epitaph requirement); Java's
  replaceable-block test (scripts can't read it: only air and liquid count,
  as for every Waystones placement here); mapping strength 2 / 6 (no
  Waystones block maps Java's hardness).
- **Not carried over:** the memorial's bobbing and the owner's name a Java
  client draws on it (`FleetingMemorialRenderer`), its ash particles
  (`animateTick` L77-91), the epitaph's activation animation, waterlogging,
  pistons not moving it, not being pathfindable, the menu's sorting and
  search, config changes.
- **Links:** #178, PR #209; Waystones `FleetingMemorialManager`,
  `FleetingMemorialBlock`, `EpitaphDeathHandler`, `EpitaphRequirement` at
  https://github.com/TwelveIterations/Waystones/tree/9d280c1ac8d036516a2927e3d2cad8054e491074.

## 2026-10-14: the warp stone opens the warp scroll's menu through the waystone runtime after its own hold, and each teleport from it costs one of its 128 durability

- **Status:** approved (Alex, 2026-10-14), all ten of Hark's picks (PR #208, Part of #178).
- **Decision:** Waystones' warp stone (`WarpStoneItem`, `ModItems` L42) works
  through the waystone runtime of #198-#207: a `warp_stones` section in the
  same data table, no new block or component.
  - **Item:** `properties.durability(128)` (`WarpStoneItem` L33-35), which in
    Minecraft 1.21.1 also makes it one per stack (`Item$Properties#durability`
    L144-147: max damage, max stack size 1, damage 0; Mojang's mappings for
    the 1.21.1 client jar): `minecraft:durability` 128 and
    `minecraft:max_stack_size` 1 (the item converter wrote 64 and no
    durability). Always drawn with the enchantment glint (`isFoil` L152-155:
    `minecraft:glint`). It stays in the items tab (registered with the mod's
    tab, L42).
  - **Use:** held for `general.warpStoneUseTime` ticks (32,
    `WaystonesConfigData` L71; `getUseDuration` L37-40) on #206's script
    timer: `world.afterEvents.itemUse` starts it with `PORTAL_TRIGGER` 0.1 / 2
    (`use` L137-150, the scroll's sound), switching away from the stone or
    taking damage stops it (an `IResetUseOnDamage`, L29;
    `WarpDamageResetHandler` L10-15).
  - **Menu** (`finishUsingItem` L120-135): `withTargetsForItem` ->
    `getTargetsForItem` (`PlayerWaystoneManager` L299-304): the player's
    activated waystones and, while it stands, "Return to Portal"; no source
    waystone (no "Current Location", nothing left out, no range check),
    titled `container.waystones.waystone_selection`. The builder gets no
    `withHand`, so `SelectWaystoneMessage` L60-67 (and
    `WaystoneTeleportManager#isWarpItemStillPresent` L547-558) never check
    that the stone is still held: a choice teleports either way, unlike the
    warp scroll.
  - **Cost:** the `warpRequirements` default decided per target type (and the
    return portal with `target_is_warp_portal`), no source waystone, with the
    warp item's conditions read from the jar's item tags: new fixed condition
    `source_is_warp_stone` (`RequirementRegistry` L316, tag
    `waystones:warp_stones`), false elsewhere; the stone is in no
    `waystones:*scrolls` tag. The defaults have no warp stone rule, so it
    pays the distance cost (`scaled_add_xp_cost(distance, 0.01)` in the same
    dimension, 27 between dimensions, at most 27), as in Java. Errors (can't
    pay, block gone) on the action bar in DARK_RED (L80-81); a waystone that
    no longer exists does nothing (`InvalidWaystone`'s empty message).
  - **Wear** (post-teleport handler L126-130, with
    `teleports.enableDurability`, true, `WaystonesConfigData` L97):
    `ItemStack#hurtAndBreak(1)` (L442-470): no damage for a player with
    infinite materials (creative); a stack whose new damage reaches 128
    breaks (128 teleports), with the item break sound
    (`LivingEntity#onEquippedItemBroken` L3571-3572 -> `breakItem`
    L1368-1374: `ITEM_BREAK` 0.8, pitch 0.8 + random x 0.4; Java
    `random/break` = Bedrock `random.break`). Java wears the very stack
    used, wherever it went; here the warp stone in the slot it was used
    from, if one is still there.
  - **Gating:** the stone ships when a waystone block works (no new text: the
    menu's are the waystone's); otherwise a note says why and it stays a
    plain icon.
- **Why:** the warp stone is the warp scroll's menu with durability instead
  of a stack to use up (`WarpStoneItem` vs `WarpScrollItem`), so it reuses
  #206/#207's timer, #207's menu (`requirementsFor`, `back`) and the scroll
  teleport (now a shared `itemTeleport`), with every number read from the
  item class, the config defaults and Minecraft's own `hurtAndBreak`.
- **Rejected:** checking the stone is still in hand at the choice (Java's
  warp stone menu has no warp hand; that check is the warp scroll's); keeping
  the stack size 64 (Java's durability items don't stack); breaking one use later
  as Bedrock's own tools do (Java breaks at damage 128); `minecraft:enchantable`
  for Unbreaking and Mending (no Bedrock enchantable slot is
  "durability only"; the stone would take other enchantments too).
- **Not carried over (conversion note):** letting go of the use button, the
  bow pose, slowed walking and the particles while it is used, using it from
  the off hand, enchanting it (Java's `enchantable/durability` tag lets an
  anvil put Unbreaking and Mending on it), repairing it by combining two,
  wearing a stone that left its slot while the menu was open, pets and
  leashed mobs travelling along, third-party waystones, fleeting memorials
  and twinbound feather players in its menu (not converted), the menu's
  sorting and search, the warp stone Java's sharestone and portstone
  renderers draw, config changes (cited defaults).
- **Coverage:** Waystones 30.7 -> 30.7 (324 files, residue 732): the warp
  stone already shipped as a plain icon; this adds its behaviour, durability,
  stack size and glint. No other corpus mod changed.
- **Links:** #178, PR #198 (waystones), PR #201 (sharestones), PR #202
  (portstones), PR #203/#204 (runes), PR #205 (warp plates), PR #206 (warp
  portal and portal scroll), PR #207 (scrolls), #87 (no fabrication), PR #208.

## 2026-10-14: the warp, return and bound scrolls teleport through the waystone runtime after the portal scroll's hold; a blank scroll binds a bound scroll, which keeps its waystone as item data

- **Status:** approved (Alex, 2026-10-14), all ten of Hark's picks (PR #207, Part of #178).
- **Decision:** Waystones' warp scroll (`WarpScrollItem`), return scroll
  (`ReturnScrollItem`) and bound scroll (`BoundScrollItem`), with the blank
  scroll (`BlankScrollItem`) that makes a bound scroll (`ModItems` L37-40),
  work through the waystone runtime of #198-#206: a `scrolls` section in the
  same data table, no new block or component.
  - **Use:** each is used for `general.scrollUseTime` ticks (32,
    `WaystonesConfigData` L83; `getUseDuration` in each class) on #206's
    script timer: `world.afterEvents.itemUse` starts it with `PORTAL_TRIGGER`
    0.1 / 2 (`ScrollItemBase#use` L37-49), switching away from the scroll or
    taking damage stops it (all three are `IResetUseOnDamage`,
    `WarpDamageResetHandler` L10-15). The timer is now shared by every scroll.
  - **Warp scroll** (`finishUsingItem` L25-36): the menu of
    `getTargetsForItem` (`PlayerWaystoneManager` L299-304): the player's
    activated waystones and, while it stands, "Return to Portal"; no source
    waystone (no "Current Location", nothing left out, no range check), titled
    `container.waystones.waystone_selection`. A choice teleports when the
    scroll is still in hand (`SelectWaystoneMessage` L60-66: else
    `chat.waystones.source_item_missing`, DARK_RED, on the action bar) and
    uses one scroll up after the teleport (`withPostTeleportHandler`
    `consume`: not in creative).
  - **Return scroll** (`ReturnScrollItem` L19-22): the return portal while it
    stands, else the nearest of the player's activated waystones in their
    dimension (`getNearestWaystone` L104-117: `distanceToSqr` to the block
    centre; the first of equals in activation order); none does nothing. A
    teleport with no menu, then one scroll used up.
  - **Bound scroll** (`BoundScrollItem` L37-65): a teleport to the waystone
    it is bound to (a waystone or sharestone, any dimension, activated or
    not), then one scroll used up; a player who can't pay or whose waystone's
    block is gone is told on the action bar in DARK_RED (L49-50); a waystone
    that no longer exists fails with `InvalidWaystone`, whose message is empty,
    so nothing shows; an unbound bound scroll does nothing.
  - **Binding** (`BlankScrollItem#useOn` L20-43): a blank scroll in the main
    hand used on a waystone or sharestone (either half, sneaking or not:
    `WaystoneBlockBase#useItemOn` L257-262 skips the block's own use, so
    nothing is activated and no menu opens) gives a bound scroll bound to its
    waystone, when the inventory has a free slot or, outside creative, it is
    the last blank scroll (L29-31); one blank scroll is used up (not in
    creative) and the bound scroll goes into the inventory, or is dropped at
    the player. On a portstone nothing happens (no `WaystoneBlockEntityBase`);
    on a warp plate neither (`WarpPlateBlock#useItemOn` passes to
    `useWithoutItem`, which takes the click).
  - **The bound waystone** (Java: the `waystones:bound_scroll` component,
    `BoundScrollComponent` {id, name}) is kept as an item dynamic property
    (`waystones:portkit_bound_waystone`, its uid). Bedrock allows those only on
    items that don't stack, so the bound scroll's stack size becomes 1 (Java
    64). Its lore is the waystone's name at binding time in AQUA
    (`appendHoverText` L79-96 without its translated "Bound to:" label: lore
    is plain text); an unnamed waystone gives no lore.
  - **Cost:** the `warpRequirements` default decided per scroll and per target
    type (each waystone type, and the return portal with
    `target_is_warp_portal`), with no source waystone and the
    `source_is_*scroll` conditions read from the jar's `waystones:*scrolls`
    item tags (`RequirementRegistry` L311-315; new fixed conditions
    `source_is_bound_scroll`, `_return_`, `_warp_`, `_portal_scroll`, false
    elsewhere): `[source_is_scroll] multiply_xp_cost(0)` makes every scroll
    teleport free at the defaults, as in Java. The portal scroll's menu now
    reads the same tags (unchanged for the real jar, which lists it).
  - **Items:** the return and bound scrolls get `minecraft:glint`
    (`BoundScrollItem#isFoil` L98-101, which `ReturnScrollItem` inherits); the
    warp scroll does not (no `isFoil`). The bound scroll is in no creative tab
    (`ModItems` L39 registers it with a null tab: Balm 1.21.1
    `BalmItems#registerItem`).
  - **Gating:** the scrolls ship only when a waystone block works and the
    jar's `chat.waystones.source_item_missing` exists; the bound scroll only
    when the blank scroll converted (nothing else makes one); otherwise a
    note says why (the items stay plain icons, as before).
- **Why:** the three scrolls are the same `ScrollItemBase` hold as the portal
  scroll and end in the same teleport (`createUncheckedDefaultTeleportContext`
  with the scroll as the warp item), so they reuse #206's timer and #198's
  records, landing and cost parser; each step is read line by line from the
  item classes, `PlayerWaystoneManager`, `SelectWaystoneMessage` and
  `WaystoneTeleportManager`.
- **Rejected:** a bound scroll that stacks with its binding in lore (a
  visible uid, or names, which aren't unique) or in a world table (two bound
  scrolls could not be told apart); an English "Bound to:" label in the lore
  (every locale would read English); leaving out the blank scroll (the bound
  scroll could never be made: no recipe, no creative tab); converting the
  bound scroll's binding as an activation (Java needs none).
- **Not carried over (conversion note):** letting go of the use button, the
  bow pose, the bound scroll's field-of-view change, slowed walking and the
  particles while a scroll is used, using a scroll (or binding) from the off
  hand, item tooltips (the blank scroll's, the return scroll's nearest
  waystone), pets and leashed mobs travelling along, third-party waystones,
  fleeting memorials and twinbound feather players in the warp scroll's menu
  (not converted), the menu's sorting and search, the bound scroll stacking,
  dropping the bound scroll the way `Player#drop` throws it, config changes
  (cited defaults).
- **Coverage:** Waystones 30.7 -> 30.7 (324 files, residue 732): the scroll
  items already shipped as plain icons; this adds their behaviour (and one
  runtime text). No other corpus mod changed.
- **Links:** #178, PR #198 (waystones), PR #201 (sharestones), PR #202
  (portstones), PR #203/#204 (runes), PR #205 (warp plates), PR #206 (warp
  portal and portal scroll), #87 (no fabrication), PR #207.

## 2026-10-14: the portal scroll opens a warp portal through the waystone runtime; the portal sends what enters it to the chosen waystone and closes after its lifetime

- **Status:** approved (Alex, 2026-10-14), all ten of Hark's picks (PR #206, Part of #178).
- **Decision:** Waystones' warp portal (`WarpPortalBlock`, registered by name
  with no item, `ModBlocks` L87) converts with the one thing that makes one,
  the portal scroll (`PortalScrollItem`, `ModItems` L41), through the waystone
  runtime of #198-#205: a component of its own
  (`waystones:portkit_warp_portal`: `onTick` every tick through
  `minecraft:tick` [1, 1]) and a `warp_portals` section in the same data
  table. A portal is a record of type `waystones:warp_portal`
  (`WaystoneTypes` L12) holding its target's uid and its age.
  - **Scroll:** a use starts with `PORTAL_TRIGGER` 0.1 / 2 at the player
    (`ScrollItemBase#use` L37-49; Bedrock `portal.trigger`, the same audio)
    and finishes after `general.scrollUseTime` ticks (32,
    `WaystonesConfigData` L83, now in the cited defaults): a script timer
    started by `world.afterEvents.itemUse`, stopped when the player selects
    another slot or the slot stops holding the scroll, or takes damage
    (`WarpDamageResetHandler` L10-15, `world.afterEvents.entityHurt`). Then
    (`PortalScrollItem#finishUsingItem` L33-53): no place for a portal says
    `chat.waystones.warp_portal_no_space` in chat, DARK_RED; otherwise the
    menu of the player's activated waystones (`withTargetsForPlayer`), titled
    `container.waystones.waystone_selection`, its costs decided with
    `source_is_scroll` true (so none shows at the defaults, as in Java).
  - **Opening:** the choice (`SelectWaystoneMessage` L52-58, no teleport)
    runs `WarpPortalManager#spawnPortal` L39-62: the place is found again
    (`findPortalPos` L72-92: along the horizontal look, 3 then 4 blocks out,
    from two blocks above the feet down five, the first block with solid
    ground below and room for the two halves and one more block; scripts
    read neither Java test, so anything but air or liquid is solid and only
    air or liquid is room), both halves are set facing the player
    (`Direction.fromYRot(yaw).getOpposite()`), `PORTAL_TRAVEL` 0.25 / 1.4
    plays there, and one scroll is used up (`ItemStack#consume`: not in
    creative).
  - **Block:** facing x a custom `waystones:half` (lower, upper), Java's
    models as one plane per half; no collision and no selection box (both
    shapes empty, L57-64), `minecraft:light_emission` 10 (L87), not mined
    and not blown up (`strength(-1, 3600000)`), no loot (`noLootTable`), no
    creative item (`menu_category` none). Drawn translucent
    (`ModRenderers` L35: `render_method` blend) from the jar's animation
    strip (16 x 32 frames, frametime 3), which the models draw in halves:
    each half gets its own 16 x 16-frame strip cut from it, as a flipbook at
    3 ticks a frame. New generic `DerivedTexture.frame` / `ticks_per_frame`
    (textures) and `FacingBlock.slices` / `material` (blocks): the strip
    itself is no longer shipped nor residue.
  - **Going through:** every tick, each entity whose position is in either
    half (`entityInside` L66-74), at most once every 20 ticks per entity
    (`canUsePortal` L101-109, in memory as Java's unsaved map), not the
    deny list (`minecraft:wither`) and, here, not riders: a portal whose
    waystone is gone tells a player `chat.waystones.warp_portal_attunement_lost`
    and closes (`onEntityInside` L107-119); otherwise the entity lands beside
    the waystone on its first free side for the `warpRequirements` default
    decided for a portal teleport (`fixed_conditions(WARP_PORTAL_TYPE)`: no
    source waystone of a known kind, no warp item, the target a waystone:
    distance x 0.01, 27 across dimensions, at most 27), which only a player
    pays (`consumeRequirements`), told on the action bar in DARK_RED when they
    can't or when the waystone's block is gone.
  - **Closing:** after `LIFETIME_TICKS` (6000, L38) ticks of the lower half
    ticking (kept in memory, saved on the record every 20 ticks), or when
    its target is gone: `FIRE_EXTINGUISH` 0.5 / 1.2 (`removePortal`
    L127-137; Bedrock `random.fizz`, the same audio), both halves air, the
    record forgotten. A portal placed by command has no target (Java's block
    entity defaults), so the first entity in it closes it.
  - **Return to Portal:** a player who went through keeps the portal's uid
    (player dynamic property; `setReturnPortal` L128-135) and, while the
    portal stands, finds "Return to Portal" (its name,
    `gui.waystones.waystone_selection.return_to_portal`) at the end of every
    waystone and sharestone menu (`getTargetsForWaystone` L318; not
    portstones, which use `getTargetsForWaystoneType`), costing the default
    decided for that menu's type with `target_is_warp_portal` true; it lands
    beside the portal on its facing side first.
    Its place at the end is superseded by the 2026-10-14 entry "Return to
    Portal is pinned to the top of waystone menus": it lists first, as in
    Java.
  - **Item:** the portal scroll gets `minecraft:glint` (`isFoil` L27-30).
  - **Gating:** the portal ships only when the jar's texts for it exist, the
    portal scroll converted, a waystone block works, and the strip is the
    16 x 32-frame one its models halve; otherwise its blockstate is residue
    with the reason.
- **Why:** the portal is a block with no way in but the scroll, so the
  scroll is the slice; it is built on the same waystone records, teleport
  rules and cost parser, and each step is read line by line from
  `WarpPortalManager`, `WarpPortalBlockEntity` and `PortalScrollItem`.
- **Rejected:** converting the block alone (nothing could ever open it);
  `minecraft:use_modifiers` with `itemCompleteUse` for the hold (documented
  only with food, shooter or throwable, as #198 found; if it doesn't fire on
  a plain item the scroll does nothing) or an instant use (drops Java's
  32-tick hold); one 16 x 32 flipbook (Bedrock would cut 16 x 16 frames and
  show top and bottom halves in turn); the scroll's other targets (third-party
  waystones, fleeting memorials: not converted); a cooldown in entity dynamic
  properties (it would survive a reload, Java's doesn't).
- **Not carried over (conversion note):** letting go of the use button (a
  script can't see it), the bow pose, slowed walking and the particles while
  it is used, using it from the off hand, the portal's idle and burst
  particles, pets, leashed mobs and mounts travelling along, Java's solid and
  replaceable tests, an entity counting as inside by its position (Java: its
  bounding box), up to 19 ticks of a portal's age across a reload, "Return
  to Portal" in the warp stone's and scrolls' menus (not converted), config
  changes (cited defaults).
- **Coverage:** Waystones 30.2 -> 30.7 (319 -> 324 files, residue 736 ->
  732); no other corpus mod changed.
- **Links:** #178, PR #198 (waystones), PR #201 (sharestones), PR #202
  (portstones), PR #203/#204 (runes), PR #205 (warp plates), #87 (no
  fabrication), PR #206.

## 2026-10-14: warp plates attune a dormant shard and warp what stands on them through the waystone runtime; the shard keeps its plate as item data

- **Status:** approved (Alex, 2026-10-14), all ten of Hark's picks (PR #205, Part of #178).
- **Decision:** Waystones' warp plate (`WarpPlateBlock`, registered by name,
  `ModBlocks` L86) runs through the waystone runtime of #198-#204 with a
  component of its own (`waystones:portkit_warp_plate`: `onTick` every tick
  through `minecraft:tick` [1, 1], `onPlayerInteract`, `onPlayerBreak`) and a
  `warp_plates` section in the same data table. A plate is a record of type
  `waystones:warp_plate` (`WaystoneTypes` L11), owned by its placer, never in
  any menu, holding one shard (`{id, attunement}`: Java's container slot 0).
  - **Block:** no facing; a custom `waystones:status` state with Java's seven
    `WarpPlateStatus` values in enum order, `empty` first (L61-68, default
    L87-89); one bone per Java model (`warp_plate_empty`, `warp_plate`,
    `warp_plate_locked`) shown for the statuses the jar's blockstate maps to
    it; collision and selection box = the bounding box of `SHAPE` (L78-81),
    16 x 2 x 16 px. New generic `FacingBlock.facing=False` (a station block
    whose blockstate is one state alone) and `drop_tinted` in `blocks.py`.
  - **Attuning:** placing a plate (or the first tick of one placed by command,
    origin UNKNOWN, no owner) gives it a dormant shard
    (`WarpPlateBlockEntity#initializeWaystone` L67-80); a dormant shard
    attunes after 30 ticks (`getMaxAttunementTicks` L377-379) into an attuned
    shard bound to that plate, which pops out at the plate's centre the next
    tick with `CHICKEN_EGG` 1/1 (L345-376; Bedrock `mob.chicken.plop`, the same
    audio: mcmeta 1.21.1 `entity.chicken.egg` = `mob/chicken/plop`,
    bedrock-samples `mob.chicken.plop`). The status follows `getIdleState`
    (L145-157).
  - **Shards:** using a plate with a shard of the jar's `waystones:warp_shards`
    item tag in the main hand puts one in when it holds none, creative keeping
    the item (`WarpPlateBlock#useItemOn` L163-176); sneak-using with empty
    hands pops it out (`useWithoutItem` L184-194); sneaking with anything in
    either hand does nothing (vanilla's rule for using a block). The attuned
    shard keeps its plate's uid as an item dynamic property, which Bedrock
    allows only on non-stackable items; the attuned shard's stack size becomes
    1 and the crumbling one's 4, from their classes (`AttunedShardItem` L6,
    `CrumblingAttunedShardItem` L17; the item converter had written 64).
  - **Warping:** each tick, the entities whose position is in the plate's
    block: an IDLE plate whose shard can name a target turns WARPING (or
    WARPING_INVALID when that plate is gone or a player can't pay)
    (`onEntityCollision` L115-142); while warping, each entity counts ticks
    and after more than `warpPlateUseTime` (15, `WaystonesConfigData` L75;
    `getWarpPlateUseTime` L236-249 with no modifiers) is teleported to the
    target plate's centre facing north (no side offset for a warp plate,
    `WaystoneTeleportManager` L245-247, L275-284); players are told on the
    action bar, in DARK_RED, when the shard has no attunement or its plate is
    gone (L208-220) or when they can't pay (L284-290). Mobs and items go too;
    riders and `teleports.entityDenyList` (`minecraft:wither`, L114) do not.
    An arrival is marked on the target plate and may not use it again until
    it has been off it for `warpPlateCooldownTime` (20, L79), kept per entity
    in memory as Java keeps it unsaved on the entity (`EntityMixin` L17-28,
    `tickEntityWarpPlateState` L385-405).
  - **Cost:** the `warpRequirements` default decided for a plate-to-plate
    teleport (`fixed_conditions(WARP_PLATE_TYPE)`: `source_is_warp_plate` and
    `target_is_warp_plate` true, the waystone ones false, `target_is_global`
    false as a plate's visibility is SHARD_ONLY): `multiply_xp_cost(0)`
    applies to every plate teleport, so it is free at the defaults; the rest
    is still evaluated per teleport, creative players always go.
  - **Breaking:** the jar's loot table (one pool, `survives_explosion`; its
    silk-touch `copy_components` and `copy_name` are not carried) and,
    outside creative, the held shard (`WaystoneBlockBase#playerWillDestroy`
    L128-133); the plate is forgotten.
  - **Gating:** a plate ships only when the jar's texts for it exist, its
    `warp_shards` tag is readable and the dormant and attuned shard items
    converted; otherwise it stays residue with the reason.
- **Why:** the warp plate is built on `WaystoneBlockBase` and the same
  teleport manager, so it shares the runtime's storage and cost parser; the
  per-tick behaviour is read line by line from `WarpPlateBlockEntity`, and an
  item dynamic property is the one place Bedrock lets a single stack carry
  which plate it was attuned to.
- **Rejected:** a three-value state (empty/plate/locked) with the status kept
  elsewhere (loses Java's one-to-one blockstate); drawing the tinted rune mark
  untinted (white, wrong) or baking its twelve `ChatFormatting` colours now
  (a follow-up, as runes were for #201/#202: it needs a UUID-shaped uid and
  Java's `String#hashCode` of the galactic name); keeping the attunement in
  lore or a name tag (visible and editable) or in a world table (two attuned
  shards could not be told apart); `onStepOn` (fires once; Java counts ticks
  while standing); players only (Java warps any entity); a cooldown in entity
  dynamic properties (it would survive a reload, Java's doesn't); a rename
  form on plain use (nothing shows a plate's name here, and Java names plates
  from a word-list generator that isn't carried).
- **Not carried over (conversion note):** the rune mark tinted by the plate's
  galactic name and the item's tinted runes (`0xC456BD`; the item shows the
  empty plate, the block's default state, where Java's item model is the
  whole plate), the settings
  screen (name, visibility, the four modifier slots and every warp modifier:
  status effects, amethyst/slime use time, quartz round-robin, spider eye,
  redstone torch, so REDSTONE_DISABLED never shows), the generated name,
  each status's particles and the eject effect, shard tooltips and glint,
  pets and leashed mobs travelling along, a crumbling shard's attunement (a
  stackable item can't hold script data, so it warps nowhere), several
  shards picked at random, a silk-touched plate keeping its identity, an
  entity counting as on the plate by its position (Java: its bounding box),
  config changes (cited defaults).
- **Coverage:** Waystones 29.9 -> 30.2 (316 -> 319 files, residue 741 ->
  736); no other corpus mod changed.
- **Links:** #178, PR #198 (waystones), PR #201 (sharestones), PR #202
  (portstones), PR #203/#204 (runes), #87 (no fabrication), PR #205.

## 2026-10-13: waystone and portstone runes reuse the sharestone overlay; a waystone's show once any player activates it

- **Status:** approved (Alex, 2026-10-14), all ten of Hark's picks (PR #204, Part of #178).
- **Decision:** the `stations.Overlay` / `DerivedTexture` pieces from the
  sharestone runes (entry below) now carry the other two rune renderers in
  Waystones 21.1.46:
  - **Portstones (16):** `PortstoneRenderer` (L26-47) draws
    `block/portstone_runes` from the lower half, turned by `toYRot()`, in the
    colour's `DyeColor#getTextureDiffuseColor()` (L43); the item model
    `item/portstone` has the same runes with `tintindex 0`, tinted by the item
    colour handler with `getTextColor()` (`ModRenderers` L31-32). Exactly the
    sharestone treatment: bones in the lower half (the band lies wholly in
    it), a baked block texture and a baked item texture per colour (white
    included: `F9FFFE` / `FFFFFF`), `minecraft:item_visual` for the item. The
    jar's `portstone_runes.png` is grey+alpha; it is decoded to RGBA before
    the multiply.
  - **Waystones (10):** `WaystoneRenderer` (L26-51) draws
    `block/waystone_runes` in the block's `WaystoneStyle` rune colour
    (`WaystoneStyles` L19 blackstone `0xFF993333`, L21 end stone
    `0xFF7200FF`; every other style keeps `WaystoneStyle`'s default
    `0xFFFFFFFF`, L11), only while the client's own player has activated that
    waystone (L33-37, `PlayerWaystoneManager#isWaystoneActivated`, a
    per-player list). The item model `item/waystone` has no runes.
    - **Colour:** white multiplies the texture by 1, so the eight white styles
      use the jar's own `waystone_runes.png` (already shipped under
      `waystones:waystone_runes`); blackstone and end stone get a baked
      texture. No item texture.
    - **Activation:** a boolean block state `waystones:runes` (default false)
      that the overlay bones also require in `bone_visibility`. The waystone
      runtime turns it on for both halves when a player activates the
      waystone (placing it activates it for the placer, as in Java; first use
      activates it for the user), and turns it back on when a player who has
      it activated uses it and finds it off. It never turns off: the runtime
      has no "forget waystone" action. Table keys `rune_state` /
      `rune_blocks` (only waystones whose block really has the state).
    - **Geometry:** the band runs from 12 to 21.5 px, across into the upper
      block. It is cut at 16 (`models.split_y`): the side faces' v range is
      split linearly where y = 16 falls (north `3.5-13` becomes upper
      `3.5-9`, lower `9-13`), the up face goes with the top part and the down
      face with the bottom one. Only an unrotated element (or one with a
      0-degree rotation, which Java leaves as it is; the jar's element has
      one) with unrotated side faces is cut; anything else still means no
      runes with the reason in the note (this replaces the sharestone
      entry's "an element across two blocks means no runes" for such boxes).
      Same facing rule as the sharestones
      (180 degrees at north/south in the stone's frame), computed from each
      blockstate.
- **Why:** the runes are the only thing that tells a portstone's colour
  apart and the visible sign that a waystone is activated. A Bedrock block
  looks the same to every player, so a per-player overlay cannot exist. A
  world-level state driven by the runtime that already tracks activation is
  exact in single player (the common case) and on a server shows runes
  once anyone has activated the waystone.
- **Rejected:**
  - Waystone runes never shown (matches only players who never activated
    it; loses the activation cue entirely); always shown (wrong for every
    waystone nobody has activated, including freshly generated ones).
  - A per-player view through a client-side entity or particles (no
    per-player block rendering in Bedrock; an entity per waystone for this
    is heavy and drifts from the block).
  - Baking white copies of the waystone texture (identical to the jar's own).
  - Refusing the waystone band because it crosses blocks (the cut is exact
    for an unrotated box).
  - A separate overlay block on top (Bedrock has no mechanism that draws
    over a custom block).
- **Not carried over (conversion note):** per-player rune visibility (once
  any player activates a waystone, everyone sees its runes); the runes'
  full-brightness glow and the `disableTextGlow` client option; the
  portstone's tilted warp stone on top; the portstone item's upper half.
- **Links:** #178, PR #204; builds on PR #203 (sharestone runes) and PR
  #202 (portstones).

## 2026-10-13: a sharestone's runes are part of its block, in textures tinted at convert time with the colour's DyeColor values

- **Status:** approved (Alex, 2026-10-13), all ten of Hark's picks (PR #203).
- **Decision:** Waystones' `SharestoneRenderer` (L31-53) draws the
  `block/sharestone_runes` model (`ModModels` L11-17) from the lower half's
  block entity, turned by `FACING.toYRot()`, through `RuneRenderUtil`
  (L12-20): cutout, the colour's `DyeColor#getTextureDiffuseColor()`
  multiplied into the tinted faces, full brightness unless the client config
  `disableTextGlow` is set (default false). The item model tints the same
  runes with `DyeColor#getTextColor()` (`ModRenderers` L27-28; the block
  colour handler next to it has no effect, since the block models have no
  tinted face). Bedrock now gets:
  - **Block:** the rune model's elements as extra bones of the sharestone's
    own geometry, each in the block it lies in (the top band moves 16 down
    into the upper half), with a material instance `runes` on a texture baked
    at convert time: the jar's `sharestone_runes.png` with every pixel's RGB
    multiplied by the colour's texture diffuse colour, alpha kept (Java's
    shader multiplies texture by vertex colour). `alpha_test`,
    `face_dimming: false`, `ambient_occlusion: false` (Java puts these quads
    with brightness 1: no face shade, no AO).
  - **Facing:** the renderer turns the runes anticlockwise by `toYRot()`
    (south 0, west 90, north 180, east 270) and the blockstate turns the stone
    clockwise by its `y` (north 0 ... west 270), so in the stone's frame the
    runes are turned 180 degrees at north and south and not at east and west.
    Two rune bones per half (turn 0 / 180), picked by `bone_visibility`;
    the facing's own turn stays the permutation's.
  - **Item:** `minecraft:item_visual` (block format 1.21.60) with the same
    geometry showing the lower half and its unturned runes, the runes on a
    second baked texture in the colour's text colour.
  - **Colours:** `waystones.DYE_COLORS`, the constructor arguments of
    `net.minecraft.world.item.DyeColor`'s static initializer in the
    Minecraft 1.21.1 client jar (sha1 30c73b1c5da7..., read with Mojang's
    mappings), the game Waystones 21.1.46 is built for; the diffuse colours
    match the minecraft.wiki Dye table. Thirty numbers, stored inline with
    the citation (not fetched): they are facts, not Mojang assets.
  - **Mechanism:** a station `FacingBlock` may carry an `Overlay` (model,
    texture, per-value offsets, per-facing turns, block and item textures);
    the block converter adds its bones, and the textures converter bakes the
    `DerivedTexture`s the station asks for (`stations.station_textures`), so
    `terrain_texture.json` stays one converter's output. A rune model that is
    missing, draws more than one texture, has an element across two blocks,
    or a derived texture key the jar already uses means no runes (the old
    look, with the reason in the note), never a guess.
- **Why:** the colour is the sharestone's identity (it decides the network),
  and Bedrock has no arbitrary per-block tint: `tint_method` takes only biome
  tints (MicrosoftDocs minecraftBlock_material_instances.md), so a baked
  texture per colour is the one faithful way; the inputs are the user's own
  jar texture and the exact numbers Java multiplies by.
- **Rejected:** a block entity (Bedrock has none for custom blocks; an entity
  per sharestone to draw runes is heavy and drifts from the block);
  `tint_method` (biome tints only); recolouring the stone texture (Java's
  stone is untinted); a flat item icon texture (loses the 3D item Java
  shows); the item in the block colour (Java's item uses the text colour);
  both halves in the item (the two halves are separate bones in one block
  space and would overlap; a separate item geometry would be over Bedrock's
  30-pixel block geometry limit); fetching the DyeColor values with
  `portkit reference fetch` (thirty cited numbers do not need a download);
  emissive glow via `minecraft:light_emission` (lights the whole block and
  its surroundings, which Java's runes do not).
- **Not carried over (conversion note):** the runes' full-brightness glow
  (no emissive block material), the floating, spinning warp stone above the
  sharestone (an animated item render), the `disableTextGlow` client option,
  and the upper half in the item icon (as for waystones).
- **Coverage:** Waystones 20.8 -> 23.1 (204 -> 234 files: 30 baked
  textures; residue 778 -> 777, the rune model now read); no other corpus mod
  changed. With the portstones (PR #202) merged in: 25.3 -> 27.5 (252 -> 282
  files, residue 744 -> 743).
- **Links:** #178, PR #201 (sharestones, decision pick 6), #87 (no
  fabrication), PR #203.

## 2026-10-13: portstones open their colour's sharestone network (white: the player's waystones) from anywhere; a portstone is no waystone

- **Status:** approved (Alex, 2026-10-13), all ten of Hark's picks (PR #202).
- **Decision:** Waystones' sixteen portstones (the `waystones:portstones`
  block tag intersected with the colours `ModBlocks` registers a
  `PortstoneBlock` for, L16-33 / L90-94: every dye colour, white included)
  run through the waystone runtime of #198/#201. A portstone is no waystone:
  its block entity is a plain `PortstoneBlockEntity`, so `setPlacedBy`
  (L299) makes nothing beyond the upper half (no record, owner, name or
  activation) and nothing ever lists it (its tooltip: "Can not be teleported
  to."). Using one, sneaking or not, opens a menu of the network
  `PortstoneBlock#getTargetWaystoneType` (L145-147) names: its colour's
  sharestones (every one in the world, any dimension, placement order), or,
  for white (`WaystoneTypes.getSharestone` has no white sharestone), the
  waystones the player activated (activation order;
  `getTargetsForWaystoneType` L323-333). The menu has no waystone in use
  (`WaystoneSelectionListBuilder` L69-72), so nothing is left out, there is
  no "Current Location" header (`WaystoneSelectionScreenBase` L333-337), and
  no distance is checked: `WaystoneSelectionMenu#stillValid` (L79-86) and
  `isSourceWaystoneInRange` (L523-528) pass without a source waystone, so the
  player can walk away before choosing. The title is the jar's
  `container.waystones.<colour>_portstone` (L140); an empty list shows the
  sharestone or the waystone text by target kind (L349-360). The table gains
  `portstones` (block -> `target` type, `title`, `requirements`); portstones
  are in `blocks` (placement and breaking) but not `block_types` (never a
  target).
- **Cost:** the `warpRequirements` default is parsed once per target type
  with a portstone's conditions decided (`fixed_conditions(kind,
  portstone=True)`): `source_is_portstone` true (the menu's PORTSTONE flag,
  ModMenus L27); `source_is_waystone`, `source_is_sharestone` and every
  `source_is_<colour>_sharestone` false (no source waystone); the target's
  conditions as for its network. The defaults have no portstone line, so a
  portstone teleport costs what a waystone's does, from where the player
  stands (distance x 0.01 points, 27 across dimensions, at most 27).
- **Block:** facing x `waystones:half`; the lower box is full (north
  `LOWER_SHAPES` spans 0-16), the upper is the bounding box of north
  `UPPER_SHAPES` (x 3-13, y 0-7, z 7-13), turned per facing by the same
  `minecraft:transformation` as the geometry (which turns collision and
  selection boxes, Bedrock-OSS wiki blocks/block-orientation). The jar's loot
  table drops from the lower half; there is nothing for silk touch to copy.
- **Gating:** a portstone ships only when the jar has its title and its
  empty-list text and its target network converted (a coloured portstone
  needs its colour's sharestone, the white one a waystone); otherwise it
  stays residue with the reason.
- **Why:** Java builds the portstone on `WaystoneBlockBase` and the same
  selection menu and teleport manager, so one runtime keeps one copy; the
  target rule, the missing range check and the conditions are read straight
  from the code paths a portstone takes.
- **Rejected:** storing a record for portstones (they would become targets,
  which Java's are not); the 8-block range rule from the portstone (Java has
  no source waystone to measure from); reusing each network's requirement
  list (wrong as soon as a config line names `source_is_portstone` or
  `source_is_sharestone`); a "select your destination" title (Java shows the
  portstone's own name); one centred upper box for every facing (10x7x10,
  larger than any facing's shape) or a collision box array; shipping a
  portstone whose network did not convert (an always-empty menu); drawing the
  runes (code-rendered by `PortstoneRenderer`, as for sharestones).
- **Not carried over (conversion note):** the coloured runes and the
  floating warp stone (`PortstoneRenderer`), the item tooltip and the 3D item
  model, global and team waystones in the white portstone's list (visibility
  is not carried), the menu's sorting, search and deleting, and what #198
  lists for waystones (pets and leashed mobs, waterlogging, the free-space
  tests, an unloaded target's room check, explosions taking one half, config
  changes).
- **Coverage:** Waystones 20.8 -> 25.3 (204 -> 252 files, residue 778 ->
  744); no other corpus mod changed.
- **Links:** #178, PR #198 (waystones), PR #201 (sharestones), #87 (no
  fabrication), PR #202.

## 2026-10-13: sharestones share one network per colour through the waystone runtime; the cost is the same cited default, decided per waystone type

- **Status:** approved (Alex, 2026-10-13), all ten of Hark's picks (PR #201).
- **Decision:** Waystones' fifteen coloured sharestones (the
  `waystones:sharestones` block tag intersected with the colours `ModBlocks`
  registers a `SharestoneBlock` for, L35-51 / L96-100: every dye colour but
  white) run through the waystone runtime of #198 rather than a second one.
  The data table now maps each block to its Java waystone type
  (`block_types`: every waystone variant is `waystones:waystone`, a
  sharestone is `waystones:<colour>_sharestone`, `WaystoneTypes`) and each
  type to a network (`networks`: `shared`, the name and empty-list texts, its
  own requirement modifiers). A sharestone places, names, breaks and
  teleports like a waystone, but has nothing to activate: using one opens a
  menu of every other sharestone of its colour in the world, any dimension
  (`SharestoneBlock#handleActivation` L74-82,
  `PlayerWaystoneManager#getTargetsForWaystoneType` L325-326 ->
  `WaystoneManagerImpl#getWaystonesByType`), in placement order; placing
  one makes the placer its owner (the rename rule is the waystone's) but
  adds nothing to the player's activated list (`activateWaystone` L60 records
  only `WAYSTONE`). The block is facing x `waystones:half` with a full box per
  half (both Java shapes span 0-16) and the jar's loot table on the lower
  half; silk touch drops a plain sharestone, which is Java's behaviour too
  (`canSilkTouch` is false for sharestones). The settings form's title is now
  Java's "Edit %s" with the block entity's name ("Edit Waystone" / "Edit
  Sharestone", `getSettingsMenuProvider` L297 + `getName`), for waystones too
  (#198 showed the waystone's own name there).
- **Cost:** the `warpRequirements` default is parsed once per waystone type
  with that type's conditions decided (`waystones.fixed_conditions`): from a
  sharestone, `source_is_sharestone`/`target_is_sharestone` and its own
  colour's `source_is_<colour>_sharestone`/`target_is_<colour>_sharestone`
  are true, every other colour and `*_is_waystone` false, and
  `target_is_global` false (a sharestone's visibility is its colour's,
  `WaystoneVisibility#fromWaystoneType` L38-57). The defaults have no
  sharestone line, so a sharestone pays what a waystone does (distance x
  0.01 points, 27 across dimensions, at most 27); a config line with a
  per-colour condition (`source_is_orange_sharestone`) now resolves instead
  of refusing the runtime.
- **Storage:** records gain `type` and `order` (a world placement counter,
  the menu's order); a record without a type
  (written by #198's runtime) is a waystone (`default_type`), so existing
  worlds keep working; a record whose type is not the block's at its spot is
  stale and replaced by a fresh one (no owner), as Java's block entity would
  be. A teleport also checks the target's stored type and its block's type.
- **Texts:** `container.waystones.waystone` joins the runtime's keys;
  `container.waystones.sharestone` and
  `gui.waystones.waystone_selection.no_sharestones_available` ship only with
  sharestones, and a jar missing either keeps its sharestones residue (the
  waystones still work).
- **Why:** a sharestone is a waystone with a different target list (Java
  shares `WaystoneBlockBase`, the teleport manager and the requirement
  rules), so one runtime keeps one copy of placement, teleport, breaking and
  storage; typing the networks keeps each value traceable to a line of
  source.
- **Rejected:** a separate sharestone runtime and table (a second copy of
  the teleport code); per-player activation of sharestones (Java has none);
  Java's menu order (its manager's `ConcurrentHashMap` order appended to each
  player's sorting index: unspecified, so a per-player index would store a
  list per player for no rule to reproduce) or name order (Java's default
  sort is MANUAL); one shared requirement list for every type (a config line
  naming sharestones would be wrong for one of them); drawing the coloured
  runes (Java's `SharestoneRenderer` tints the `sharestone_runes` model with
  `DyeColor#getTextureDiffuseColor` in code: Bedrock block geometry has no
  arbitrary tint, so it would need generated per-colour textures, a later
  slice) or keeping sharestones residue until then (the network works without
  them; the colour is in the item's name); portstones in this slice.
- **Not carried over (conversion note):** the coloured runes and the
  floating warp stone (code-rendered; every colour looks the same), the
  item tooltip, the menu's sorting, search and deleting (creative deletion
  removes a sharestone from its network in Java), and what #198 lists for
  waystones (pets and leashed mobs, waterlogging, particles, comparator and
  observers, Java's free-space tests, an unloaded target's room check,
  explosions taking one half, config changes, operator edit permission).
- **Coverage:** Waystones 16.4 -> 20.8 (159 -> 204 files, residue 810 ->
  778); no other corpus mod changed.
- **Links:** #178, PR #198 (waystones), #87 (no fabrication), PR (this).

## 2026-10-13: waystones activate, list and teleport through a scripted block; the experience cost is the cited warpRequirements default, parsed and decided per runtime

- **Status:** approved (Alex, 2026-10-13), all ten of Hark's picks (PR #198).
- **Decision:** Waystones' ten `WaystoneBlock` blocks (waystone, mossy,
  sandy, deepslate, blackstone, end stone, red nether bricks, purpur,
  prismarine, mud bricks) take the station split of #177: a generated table
  (`scripts/portkit/data/waystones_waystone.js`: the blocks, the warp
  requirement modifiers that can apply here, texts, sounds, the edit rule,
  name length, range) read by a fixed runtime (`portkit/runtime/waystone.js`
  + `waystone_core.js`, `@minecraft/server` 2.0.0 plus
  `@minecraft/server-ui` 2.0.0 for the forms). The block is facing x a custom
  `waystones:half` state (lower first, Java's default), one box per half from
  Java's shapes. Placing one needs a free block above, sets the upper half,
  makes a waystone owned by the placer, activates it for them and asks for a
  name (Java opens the settings screen on placement); using it activates it
  (chat "Activated Waystone: %s", level-up sound 0.2/1) or, once activated,
  opens an `ActionFormData` menu of the player's activated waystones in
  activation order (Java's default MANUAL sort over its sorting index), the
  one in use left out and named as "Current Location"; choosing one checks
  the player is still within 8 blocks of the waystone used, that the target
  still exists, and that they can pay (creative always can), takes the
  points (Java's consume runs in creative too) and teleports them to the
  first free side of the target (its facing, then east, west, south, north;
  its own block when none), turned to that side, with the portal-travel
  sounds 0.01/0.05. Sneak-use renames (`ModalFormData`, 128 characters, a
  blank name becomes "Untitled Waystone"), only by the owner while PLAYER is
  restricted. Breaking either half removes both and the waystone; only the
  lower half drops (its loot table), so breaking the upper half outside
  creative destroys the lower one with its drops.
- **Where each value comes from (no fabrication):** which blocks: the
  `waystones:waystones` block tag (data) intersected with the blocks
  `ModBlocks` registers as `WaystoneBlock` (L70-85); facing/half/placement/
  breaking: `WaystoneBlockBase`/`WaystoneBlock`; drops: the jar's loot table
  (one pool, `half=lower`, `survives_explosion` -> `explosion_decay`); the
  cost: `teleports.warpRequirements`, `enableCosts`, `enableCooldowns`,
  `restrictedWaystones`, `defaultVisibility` from `WaystonesConfigData` at
  v21.1.46 (9d280c1a), in `portkit/data/waystones_config_defaults.json` with
  a citation per value. The converter parses each requirement line as
  `RequirementModifierParser` does and decides each condition for this
  runtime (`waystones.FIXED_CONDITIONS`: the source is always a waystone,
  the target always a waystone with ACTIVATION visibility); what is left
  (`is_interdimensional`) is evaluated per teleport, with Java's float
  arithmetic and int truncation. At the defaults: distance x 0.01 points in
  one dimension, 27 between dimensions, clamped to 0..27; the scroll, warp
  plate, global, memorial and inventory-button lines can't apply and are
  listed in the table's header. A condition, function or variable without a
  runtime, or a cooldown that would apply, means no runtime (blocks place,
  do nothing; loot tables residue), never a guess. Texts: the jar's own lang
  keys, shipped under their Java key in every locale
  (`lang.convert(runtime_keys=...)`), shown with rawtext `translate`/`with`.
  Sounds: `random.levelup` and `portal.travel` play the same files as Java's
  `entity.player.levelup` and `block.portal.travel` (mcmeta 1.21.1 assets,
  bedrock-samples sound_definitions).
- **Storage:** one world dynamic property per waystone, keyed by dimension
  and lower-half position (JSON: uid, dimension, pos, facing, name, owner,
  origin); a player dynamic property holds the uids they activated, in
  order. A waystone placed by a player replaces whatever was stored at its
  spot; one without a record (placed by command or structure) gets one on
  first use, with no owner and origin UNKNOWN (Java's block entity default).
- **Why:** the same reason as the FD stations: the data says what varies
  (blocks, drops, the cost rules), the behaviour is one fixed script, and the
  cost is the mod's own rule language read from its own default, so a value
  in the pack can be traced to a line of source.
- **Rejected:** hard-coding "distance x 0.01, max 27" in the script (the
  number would have no source in the table, and a different default would
  be silently wrong); one registry property for all waystones (dynamic
  property strings are size-capped); teleporting anywhere for free or
  without the menu (#87, a gameplay change); the warp stone and scrolls in
  this slice (their charge-up is `warpStoneUseTime`/`scrollUseTime` 32 ticks,
  and `minecraft:use_modifiers` is documented only with food, shooter or
  throwable; an instant `onUse` would drop it); listing the waystone in use
  as a button that does nothing (`ActionFormData` can't disable one).
- **Not carried over (conversion note):** visibility (every waystone is
  visible upon activation), modifier slots and warp modifiers, groups,
  aliases, favourites, menu sorting/search/deleting, pets and leashed mobs
  travelling along, waterlogging, particles, comparator and observers, a
  silk-touched waystone keeping its identity (it drops a plain waystone),
  operator edit permission, the room test for a target in an unloaded chunk
  (the player lands on its front side), Java's replaceable and suffocation
  tests (placing needs air or liquid above, and only air or liquid count as
  room beside a target; scripts can't read either), the other half going when
  one is removed by anything but a player (an explosion), the player's reach in the
  range test (the non-player 8-block rule, L531), config changes (cited
  defaults), the item icon (Bedrock draws the lower half), village and wild
  generation, sharestones, portstones, warp plates/portals, fleeting
  memorials, and the warp stone, scrolls, shards and feather. Another
  Waystones version gets no runtime.
- **Coverage:** Waystones 12.7 -> 16.4 (124 -> 159 files, residue 851 -> 810);
  no other corpus mod changed.
- **Links:** #178, #177 (station pattern), #87 (no fabrication), PR (this).

## 2026-10-13: feasts serve portions through a scripted block; serving counts and leftovers come from the blockstate and loot table, the serving item and container from cited FD code

- **Status:** approved (Alex, 2026-10-13), all ten of Hark's picks (PR
  #196): the numbered picks below, and the code/data cross-check under
  "Where each value comes from" (pick 10).
- **Decision:** Farmer's Delight's six feasts (roast chicken, stuffed
  pumpkin, honey glazed ham, shepherd's pie, gleaming salad, rice roll
  medley) take the station split: a generated table
  (`scripts/portkit/data/<ns>_feast.js`: per feast block, its serving item
  per serving count, the container the player must hold, whether it lingers
  at 0, its top count; sounds; FD's `use_container` message) read by a fixed
  runtime (`portkit/runtime/feast.js` + `feast_core.js`, Script API
  `@minecraft/server` 2.0.0 unchanged, one custom component on every feast
  block, `onPlayerInteract` only, no tick, no stored data). Behaviour is
  `FeastBlock#takeServing` at the pinned commits (NeoForge dd8b9b0 L103-138,
  Refabricated a8cb49e L110-144): the right container in the main hand gives
  one serving (inventory, else dropped at the player), counts `servings`
  down and is used up (not in creative); a serving with no container (the
  medley's rolls) serves to any hand; the wrong item shows "You need a %s to
  eat this." with the container's Bedrock name; at 0 a feast with leftovers
  is cleared by one more use (wood break 0.8/0.8) and drops its loot; one
  without leftovers (stuffed pumpkin) goes with its last serving. The
  take-portion sound is `armor.equip_generic` 1.0/1.0 on both loaders
  (NeoForge's FD event plays that vanilla event per FD's sounds.json).
- **Where each value comes from (no fabrication):** which blocks: FD's own
  `farmersdelight:feasts` block tag, intersected with the six feasts whose
  code was read (`feasts.FEASTS`); serving counts: the blockstate's
  `servings` values (0-4, the medley 0-8), the top one Java's default state;
  leftovers and break drops: the jar's loot table (pools gated on `servings`
  = full or its inversion), decided per count. Only in Java code, cited
  narrowly per loader: the serving item and `hasLeftovers` (`ModBlocks`
  constructor arguments), the container (`ModItems.bowlFoodItem`:
  `craftRemainder(Items.BOWL)`; the rolls are `foodItem`, none), the
  medley's per-count rolls (`RiceRollMedleyBlock.riceRollServings`), shapes
  (`FeastBlock.SHAPES`, `BlockShapes`, `GleamingSaladBlock.SHAPE`,
  `RiceRollMedleyBlock` shapes) and the salad's light (`servings * 3`). Code
  and data are cross-checked: a feast whose loot drops something at 0 must be
  a lingering one and vice versa, every serving item and loot drop must be an
  emitted or vanilla item; any miss leaves that feast's loot table as `feast`
  residue and the block placeable but not serving (a note says so).
- **1. Feast set (pick: FD's feasts tag x the code-read specs).**
  *Rejected:* every block with a `servings` state (a guess from a state
  name; the tag is the mod's own word for "feast", and FD's pies are another
  class with `bites`, not part of this).
- **2. Serving state (pick: Bedrock integer state `farmersdelight:servings`,
  values top..0, full first).** Bedrock's default is the list's first value,
  so a placed feast is full as in Java; integer states are what Microsoft's
  own custom-component example uses for a counting block (`starter:crop_age`
  0-4 with per-permutation `minecraft:loot`, learn.microsoft.com "Building
  with Custom Components"), and vanilla's cake has an integer
  `bite_counter`.
  `blocks.py` gains `FacingBlock.int_state` (unquoted Molang tests).
  *Rejected:* strings like the pot's `support` / stove's `lit` (a count is a
  number; scripts would parse it).
- **3. Drops (pick: the jar's loot table per serving count, `minecraft:loot`
  per permutation; the runtime clears with `setblock ... destroy`).** One
  Bedrock table per distinct drop set (`<name>.json` for the full feast,
  `<name>_servings_<lo>_to_<hi>.json` for the rest, vanilla's
  `loot_tables/empty.json` for none), so breaking, clearing the leftovers and
  the stuffed pumpkin vanishing all drop through the same data, as Java's
  `destroyBlock(pos, true)` does. First station to read a loot table:
  `loot.convert` hands a feast's table to the station
  (`stations.station_loot`) instead of refusing it ("table has 3 pools").
  *Rejected:* spawning drops in script (a second path; a player's break would
  still drop the block); swapping the self-drop on `onPlayerBreak` like the
  skillet (misses explosions and the clear).
- **4. Box (pick: per serving count, the box that holds Java's shape at every
  facing).** Bedrock's box is one cuboid and the block turns by
  `minecraft:transformation`, so each count gets the facing-independent
  bounds of its Java shape (tray 14x2 at 0, chicken to 8 px; stuffed pumpkin
  2, 2, 4, 6, 8 px tall). *Rejected:* one box for all counts (an eaten feast
  as tall as a full one); exact per-facing boxes (how a permutation's box and
  its transformation combine is not verified).
- **5. Support (pick: `minecraft:placement_filter` on the top face).**
  `FeastBlock#canSurvive`/`updateShape`: a feast needs a block below and
  breaks, with drops, when it goes; the filter does both. It accepts any
  block's top face, not just a rigid one (noted). *Rejected:* nothing
  (floating feasts); a per-tick script check (no neighbour hook in 2.0.0).
- **6. Hands (pick: main hand only).** Java tries the off-hand when the main
  hand can't serve; Bedrock's block use is the main hand's. *Rejected:*
  reading the off-hand in script (the off-hand takes no bowl on Bedrock).
- **7. Per-stage textures (pick: a value that draws a different texture under
  the same key gets its own key, `<key>_servings_<n>`).** The stuffed
  pumpkin's eaten top and every feast's per-stage `particle` made the station
  geometry path refuse ("models disagree"); keys no face draws (particle) are
  ignored, and a drawn one is re-keyed for that value only (stations with
  agreeing textures are unchanged). *Rejected:* residue (all six blocks
  would stay residue).
- **8. Item (pick: the block's own item, `replace_block_item`, stack 1, the
  flat icon).** `ModItems`: `PlaceableItem`, `basicItem().stacksTo(1)`;
  before this the item shipped as a plain stack-64 item that placed nothing.
- **9. Geometry (pick: one geometry, a bone per serving count shown by the
  state).** mct reports its >50-cubes performance warning on three feasts.
  *Rejected:* one geometry per count via permutation `minecraft:geometry`
  (more files, same cubes drawn).
- **Not carried over:** the off-hand try, serving particles and the salad's
  sparkles, the comparator signal, the item-used statistic and the
  place-feast advancement, exact Java shapes, the rigid-support test, piston
  popping (`PushReaction.DESTROY`), Java's `isSameItem` beyond the item id.
- **Coverage:** both FD jars convert all six feasts and their loot tables.
  Banked: FD NeoForge 37.0 → 38.5 (814 → 840 files, residue 1388 → 1343), FD
  Fabric 32.7 → 34.0 (835 → 861, 1715 → 1670; on top of the #194 bare-tag
  fix, the feasts add the same +26 files / -45 residue as before it); no other
  mod changed. mct 0 errors on both.
- **Links:** #177; PRs #189, #191, #192, #193 (the station pattern), #196.

## 2026-10-13: a bare "#tag" recipe ingredient is the tag; a "#" item id is a validator error

- **Decision:** A 1.21.2+ bare-string ingredient starting with `#` (`"#c:crops/wheat"`)
  converts exactly as `{"tag": "c:crops/wheat"}` does (pass-through Bedrock tag,
  one-member resolve, native tag, per-member recipes, residue with the same
  reason), in crafting keys and ingredient lists, furnace inputs and smithing
  slots; any other string is the item. Lists get the same per-entry reading, so a
  list holding a tag stays residue as it does in object form. The validator gains
  `xref.item_tag`: an `item` (or furnace/smithing slot) naming a `#...` id is an
  **error**, unlike `xref.item`, which stays a warning.
- **Why:** `{"item": "#..."}` names no item on Bedrock in any pack, so the recipe
  can never be crafted (99 dead recipes, 66 FD Refabricated + 33 BetterEnd, plus 3
  FD furnace and 4 BetterEnd smithing recipes). `xref.item` warns because an
  unknown id is usually a definition that was refused on purpose; a `#` id is
  never that, only a converter bug, so it should fail the run.
- **Rejected:** a warning (these 106 recipes already shipped under the `xref.item` warning);
  letting the agent or a fallback pick one member for a multi-member tag in a
  slot Bedrock can't express (#87: residue, not a guess).
- **Links:** #194.

## 2026-10-13: an item named like a block that did not convert ships as a plain item; its block placing is left out

- **Decision:** the item converter skips an item model named like a
  blockstate only when that block was emitted (Bedrock then makes the
  block's item). When the block is residue, Bedrock has no item at all, so
  the item converts as a plain item (icon, stack 64) when (1) its model is a
  flat icon the converter already accepts (generated/handheld chain, no
  elements, resting-state overrides) and (2) the source evidences an *item*:
  an `item.<ns>.<name>` lang key, or a recipe, item tag or loot entry naming
  it (`registry.registered_ids(items_only=True)`). A blockstate, a `block.`
  lang key, a block loot table's file name or an item model alone don't
  count: BCLib writes item models for every block (BetterEnd
  `end_portal_block` has one and no item). An item with no `item.` key but a
  `block.` one gets `minecraft:display_name` = the block's `tile.` line, as
  Java's `BlockItem#getDescriptionId` names it (FD Refabricated sets this
  explicitly: `registerBlockWithTab` calls `useBlockDescriptionPrefix()`,
  ModItems.java L61-66 @a8cb49e, used for `wild_rice` at L346; NeoForge's
  `DoubleHighBlockItem` inherits it from `BlockItem`). One note per mod
  lists the items and says what is left out: whatever the Java item does in
  code, most often placing the block (seed, sign, door, sapling); in Bedrock
  it places nothing. A block-model item (`parent: <ns>:block/...`) still stays
  with its block's residue.
- **Why:** Farmer's Delight registers its rice seed under the crop block's id
  (`registerWithTab("rice", () -> new RiceItem(ModBlocks.RICE_CROP.get(), ...))`,
  NeoForge ModItems.java L276 @dd8b9b0; `BLOCKS.register("rice", ...)`
  ModBlocks.java L323), and the 8-state crop block is residue, so the rule
  "a block's item is Bedrock's to make" left `farmersdelight:rice` with no
  definition anywhere: 5 cooking-pot recipes (`c:crops/rice`) and the
  rice_panicle cutting recipe were residue for want of it. The item itself
  is fully stated by the source (registered, named, iconed); only its code is
  missing, the same partial conversion held items take (2026-10-12 entry).
  Across the corpus the same gap had left ~290 already-emitted recipes and
  ~250 block loot tables naming items no file declared (validator `xref.item`
  warnings, now gone with no new warning on any mod).
- **Rejected:** an FD special case for rice (the gap is generic: signs,
  doors, saplings, pies, wild crops); a `minecraft:block_placer` pointing at
  the residue block (no such block exists in the pack: invented behaviour);
  treating the blockstate as item evidence (ships items Java never registers,
  e.g. portals); leaving the items out until their blocks convert (keeps ~400 items
  and the recipes and drops that need them dead).
- **Links:** #177; PR #195. Found alongside: #194 (bare `"#tag"`
  recipe ingredients written as items).

## 2026-10-13: the skillet cooks the stove's campfire table placed and held; held cooking takes the skillet in the off-hand; the item is an iron-tier weapon from cited numbers

- **Status:** approved (Alex, 2026-10-13): all six of Hark's picks from PR
  #193 (decisions 1–5 below; 6: durability loss left to Bedrock's
  `minecraft:durability`, in the note below).
- **Decision:** Farmer's Delight's skillet takes the station split with the
  approved patterns: a generated table (`scripts/portkit/data/<ns>_skillet.js`:
  the stove's campfire recipes, `stove.campfire_table`, so vanilla's fetched
  ones plus the jar's; the skillet's cook-time rule; the cooking pot's heat
  rules; sounds; FD's messages) read by a fixed runtime
  (`portkit/runtime/skillet.js` + `skillet_core.js`, Script API
  `@minecraft/server` 2.0.0 unchanged, `minecraft:tick` every 10 ticks,
  `station_storage.js` and `cooking_pot_core.js`'s heat helpers reused), every
  behaviour cited to FD's `SkilletBlock` / `SkilletBlockEntity` /
  `SkilletItem` / `CopySkilletFunction` at the pinned commits. No list
  narrowing; ids plus `minecraft:is_*` tags are not needed (no tool test).
- **Recipes:** the stove's table exactly (16 per corpus jar: 7 of the jar's,
  9 of vanilla's), so a recipe the stove can't state is the stove's
  `station_recipe` residue and the skillet adds none. A recipe under 60
  ticks would stay off the skillet with a note (`Mth.clamp` with min above
  max is Minecraft's code); no corpus recipe is. Cook time:
  `getSkilletCookingTime` (a fifth of the recipe's time in whole seconds, 5
  points less per Fire Aspect level, at least 60 ticks, float maths as Java),
  so 600 → 120 / 80 / 60 ticks at Fire Aspect 0 / I / II. No experience (FD's
  skillet awards none).
- **Placed:** Java's gestures. Sneak to place (`SkilletItem#place`; a
  non-sneaking place is cancelled in `beforeOnPlayerPlace` and treated as a
  main-hand use). Using a campfire input on an empty skillet puts the whole
  stack in (up to 64 or the item's stack size; creative keeps it), lantern
  place sound 0.7/1.0, FD's add_food 0.8/1.0 when heated; an empty hand takes
  the stack out (creative: removed, not given, as Java). Anything else:
  NeoForge shows `block.farmersdelight.skillet.invalid_item`, Refabricated
  does nothing (its block only calls `addItemToCook` for an empty skillet and
  a campfire input). Heated by the cooking pot's rule (`heat_sources` lit,
  `heat_conductors`, a lit stove), it cooks one item per cook time and throws
  the result clockwise of its facing (0.08 sideways, 0.25 up, from 0.3 above
  the floor); off heat the counter falls 2 a tick. The sizzle 1 in 10 ticks
  while cooking. `support` → custom state `farmersdelight:support`
  (`"false"`/`"true"`) from `tray_heat_sources` below, at placement and on
  every tick (no neighbour hook in 2.0.0). Facing is the player's own
  (`getHorizontalDirection()`, placement offset 0). The placed skillet
  remembers the item it came from (`setSkilletItem`): its Fire Aspect sets the
  cook time, and a player's break swaps the block's plain self-drop for that
  item (copy_skillet), found as an item entity the tick after.
- **Held (decision 1, pick: off-hand skillet):** Java cooks with the skillet
  in either hand and the food in the *other* hand while the use button is held
  (`use` / `releaseUsing` / `finishUsingItem`). Bedrock's off-hand takes only a
  few vanilla items (never food), and a right click always uses the main-hand
  item. So: skillet in the off-hand (`minecraft:allow_off_hand`), food in the
  main hand; `world.beforeEvents.itemUse` on a campfire input, near heat
  (`isPlayerNearHeatSource`: on fire, or a `heat_sources` block in the 3×3×3
  around the player, the tag alone, so an unlit campfire counts), cancels the
  eat and moves one item into a cooking session (player dynamic property).
  Underwater (head block is water): FD's underwater message. The skillet
  used from the main hand near heat shows FD's `how_to_cook` message.
  *Rejected:* skillet in the main hand taking the food from a hotbar slot
  (invented, not discoverable); leaving held cooking out (FD's headline
  feature, and the off-hand mapping keeps "the food in the other hand").
- **Held (decision 2, pick: keep it in the off-hand):** a script can't see the
  use button held on an item with no use animation (Microsoft's item docs
  describe `minecraft:use_modifiers` as timing use "in combination with
  components such as Shooter, Throwable, or Food"), so "hold to cook" becomes "keep
  the skillet in the off-hand": a `system.runInterval` loop every 10 ticks
  advances the session, gives the result after the skillet's cook time (Fire
  Aspect of the off-hand skillet; inventory, else at the feet), and gives the
  food back if the skillet leaves the off-hand first (`releaseUsing`). FD's
  sizzle 1 in 50 ticks; action-bar progress. *Rejected:* a fixed
  `use_duration` (one length for every recipe and Fire Aspect level, and
  whether its start/stop events fire on a non-food item is unverified).
- **Weapon (decision 3, pick: cited numbers on the item JSON):** the skillet
  item (`items/skillet.json`, format 1.21.50, the block's own item via
  `replace_block_item`, the shelf_mushroom pattern): `max_stack_size` 1
  (`stacksTo(1)`); `durability` 250 (iron tier uses); `damage` 8 (FD's
  `createAttributes(tier, 5.0F, -3.1F)`: attack_damage modifier 5 + iron's 2
  on a player's base 1; the agent stat guard's same base-1 rule);
  `enchantable` slot `sword`, value 14 (iron's enchantability; FD tags it
  durability/weapon/sharp_weapon/fire_aspect/sword enchantable and refuses
  sweeping edge, which Bedrock's sword slot doesn't have);
  `repairable` iron ingot (NeoForge: iron's repair item; Refabricated:
  `minecraft:iron_tool_materials` from fetched 26.1 tags) at 25% a unit
  (minecraft.wiki, Item repair); `can_destroy_in_creative` false on NeoForge
  only (`canAttackBlock`; Refabricated has no override); `hand_equipped`.
  Iron's numbers are Minecraft code, cited to minecraft.wiki "Tiers"
  (oldid 3830017) and consistent with the fetched item components (iron
  sword: max_damage 250, enchantable 14). Attack speed −3.1 and knockback +1
  have no Bedrock item component: left out, in the note. *Rejected:* no stats
  (#167's held-item rule) — those items had no stats in any file; here FD's
  code states them, so leaving them out would drop sourced gameplay.
- **Hit sound (decision 4, pick: always the strong sound):**
  `world.afterEvents.entityHitEntity` with the skillet in a player's main hand
  plays FD's `item.skillet.attack.strong` at 1.0, pitch 0.9–1.1. Java plays the
  weak sound for an under-charged player swing; Bedrock has no attack charge.
  Fires on every hit, not only damaging ones (Java: `LivingDamageEvent.Pre`).
- **Drop (decision 5, pick: swap the self-drop):** keep Bedrock's default
  self-drop (a plain skillet; so explosions still drop one, close to
  `survives_explosion`) and swap it for the remembered item on a player's
  break. *Rejected:* an empty block loot table with a scripted drop (every
  non-player destruction would lose the skillet); no swap (enchantments and
  wear reset on every pick-up, a free repair).
- **Not carried over (conversion note):** attack speed and knockback; the weak
  hit sound; the food drawn in the skillet, the flip animation and the
  cooking item model (renderers); steam and enchanted-hit particles;
  waterlogging and its flooded rules (custom blocks can't hold water); the
  tray's collision slab below the block (a box can't reach below its block)
  and the tray model's parts in the block below (blocks.py note); holding the
  use button; eating first when hungry (Java tries the main-hand food first);
  the placed skillet's data and food on non-player destruction; hoppers;
  advancements. Durability loss per hit and per mined block is Bedrock's own
  handling of `minecraft:durability` (not scripted, to avoid double damage),
  unverified in game.
- **Scope:** the FD versions read (NeoForge 1.3.4 @dd8b9b0, Refabricated
  26.1-3.6.28 @a8cb49e); other versions keep the skillet block as residue.
- **Links:** #177 (feasts remain), #193, #192 (campfire table), #191 (heat
  rule), #87.

## 2026-10-13: the stove is a scripted station cooking vanilla's and the jar's campfire recipes; lit, it heats the cooking pot

- **Decision:** Farmer's Delight's stove takes the station split (cutting
  board and cooking pot entries below): a generated table
  (`scripts/portkit/data/<ns>_stove.js`: every `minecraft:campfire_cooking`
  recipe as ingredient item ids, result and cookingtime; the items that light
  it and put it out; sounds; the burn) read by a fixed runtime
  (`portkit/runtime/stove.js` + `stove_core.js`, Script API
  `@minecraft/server` 2.0.0, unchanged, `minecraft:tick` every 10 ticks,
  `station_storage.js` reused), every behaviour cited to FD's
  `AbstractStoveBlock` / `AbstractStoveBlockEntity` / `StoveBlock` /
  `StoveBlockEntity` at the pinned commits.
- **Recipes:** `StoveBlockEntity` runs `RecipeType.CAMPFIRE_COOKING`, so the
  table is vanilla's own campfire recipes, fetched like the other Mojang
  reference data (`portkit reference fetch`: misode/mcmeta `<mc>-summary`
  `data/recipe/data.json` for 1.21.1 and 26.1 at the commits the vanilla tag
  sets pin, campfire recipes only, sha256-pinned, never vendored; the set
  nearest the jar's game version), plus the jar's campfire recipes whose load
  conditions pass. The jar's recipes are a *shared* station type: they still
  convert as Bedrock campfire recipes (`recipes.STATION_SHARED_TYPES`) and the
  stove reads them too; a jar recipe with a vanilla recipe's id replaces it.
  Refused (a jar recipe: `station_recipe` residue; a vanilla one: a note):
  unconverted items, no `cookingtime` (Java's default is Minecraft's code),
  recipes that share an ingredient item (Java's recipe-manager order). No
  experience: the stove gives none in Java either.
- **Interaction:** Java's own gestures, nothing invented. A lit stove is put
  out by an item that can `shovel_dig` (read as `#minecraft:shovels` plus
  Bedrock's `minecraft:is_shovel`, as the cutting board reads abilities; 1
  durability, with Unbreaking) or a `c:buckets/water` item (the hand then
  holds its crafting remainder: water bucket → bucket, minecraft.wiki
  "Hardcoded item properties (Java Edition)"; a member without a citable
  remainder is left out, with a note). An unlit one is lit by flint and steel
  (1 durability) or a fire charge (used up): vanilla's items of those Java
  classes. A food a campfire recipe takes goes, one item at a time, onto the
  first of six free spots unless the top is covered or all six are taken
  (creative keeps the stack). Placed lit. While lit each spot cooks for its
  recipe's cookingtime (exact in 10-tick runs for every corpus recipe, 600)
  and pops the result out on top with FD's velocity; unlit, progress falls by
  2 a tick. Covering the top drops the food. A living entity standing on a lit
  stove without sneaking takes 1 damage every 10 ticks, Bedrock cause
  `campfire` (FD's `stove_burn` is vanilla's campfire damage type field for
  field and sits in the same damage tags; Java's every-tick stepOn deals one
  hit per 10 ticks under the 10-tick invulnerability timer). The crackle (FD's
  event plays `block.campfire.crackle`) at Java's 1 in 10 per tick. Light 13
  while lit. No way to take food back off: Java has none.
- **Item display:** Java draws the food with a block-entity renderer.
  Bedrock custom blocks have none, and without entities the honest
  substitute is text: every use of the stove (any hand) shows lit or unlit,
  each item's cook %, free spots and "top covered" in the action bar.
- **Block:** facing × `lit` → custom state `farmersdelight:lit` (`"false"`,
  `"true"`: Java's default first, player placement sets `"true"`); the two
  plain `orientable_with_bottom` cubes → Bedrock's `full_block` geometry with
  material instances per lit value, light per value, the cube turned by
  `minecraft:transformation` per cardinal direction (uvlock off), one
  permutation per (facing, lit). Lit, the stove is a cooking-pot heat source
  (`{"id": "farmersdelight:stove", "states": {"farmersdelight:lit": "true"}}`,
  only when the emitted block has that state).
- **Why:** The same split as the other stations. Every rule that doesn't need
  a renderer or a block shape is Java's own; the two that do are stated
  approximations. "Covered" is any block above that isn't air or a liquid
  (scripts can't read shapes; Java tests the shape against a 10×1×10 px
  grilling area, so a top slab, an open or top trapdoor, a ladder, wall
  torch or button on a side, or the light block covers it on Bedrock but not
  in Java). The burn reads the feet over the stove's column on the ground
  (Java also needs the entity's box to overlap the grilling area, which every
  entity at least 6 px wide standing there does). String state values rather
  than Bedrock booleans keep the Molang conditions in the form the pot uses.
- **Rejected:** *Item display entities* (floating item entities or a display
  entity per spot): entities to keep in sync with a dynamic property, with
  pickup and despawn rules to fight. *An empty-hand "take back"*: Java has no
  such action. *Vendoring vanilla's nine campfire recipes*: Mojang's data,
  fetched and pinned like the rest. *Moving the jar's campfire recipes into
  the table only*: they are real Bedrock campfire recipes too. *Flame and
  smoke particles*: cosmetic, left out for now.
- **Not carried over (conversion note):** the food drawn on top, smoke and
  flame particles, the items when something other than a player destroys the
  stove, the exact covered and burn shapes (above), the pathfinding penalty,
  dispensers and hoppers, mod flint-and-steel or fire-charge subclasses, the
  result's feature-flag check, the shovel level event's own volume and pitch
  (Bedrock's defaults).
- **Scope:** the FD versions read (NeoForge 1.3.4 @dd8b9b0, Refabricated
  26.1-3.6.28 @a8cb49e); other versions keep the stove block as residue, and
  their campfire recipes convert as plain Bedrock campfire recipes.
- **Links:** #177 (skillet and feasts remain), #191 (its decision 7: the stove
  as a heat source once it converts), #87.

## 2026-10-13: the cooking pot is a scripted station worked by hand (no container UI); heat from FD's own block tags

- **Decision:** `farmersdelight:cooking` recipes (28 per FD jar) take the
  cutting board's split (entry below): a generated table
  (`scripts/portkit/data/<ns>_cooking_pot.js`: per recipe the ingredient slots
  as resolved item ids, result, serving container, cookingtime, experience; the
  ingredient remainders; the heat rules; `farmersdelight:serving_containers`)
  read by a fixed runtime (`portkit/runtime/cooking_pot.js` +
  `cooking_pot_core.js`, Script API `@minecraft/server` 2.0.0, unchanged), with
  every behaviour cited to FD's `CookingPotBlockEntity` / `CookingPotBlock` /
  `CookingPotMenu` / `CookingPotRecipe` at the pinned commits. Storage and
  give/drop/sound helpers are shared with the cutting board
  (`station_storage.js`). **Interaction model** (Bedrock custom blocks have no
  container screen): sneak + empty hand toggles the handle (Java's own);
  using the meal's container on a pot with a meal serves one portion (Java's
  own, `useHeldItemOnMeal`, container used up in creative too); any other held
  item goes in, a serving container (or the meal's container) to the container
  slot as `quickMoveStack` routes it, anything else whole into the first empty
  ingredient slot, onto the same item only when no slot is empty; an empty
  hand takes out the output (paying the experience owed, as the result slot
  does), else the last ingredient stack, else the containers; the action bar
  shows the contents as plain text (item ids, cook %, heated or not). Cooking
  runs in a block `minecraft:tick` every 10 ticks, advancing Java's per-tick
  counters by 10 (exact for cookingtime multiples of 10: every corpus recipe
  is 100/200/400), cooling by 2 a tick off the heat, one cook per run, meals
  without a container to the output, meals with one served into stored
  containers, ingredient remainders ejected at FD's offset and velocity.
- **Heat:** read from the jar's own `farmersdelight:heat_sources`,
  `heat_conductors` and `tray_heat_sources` block tags (both builds: magma
  block, lava cauldron, stove, `#tray_heat_sources` = lava, `#minecraft:campfires`,
  `#minecraft:fire`; conductor hopper and optional `create:chute`), rule from
  `HeatableBlockEntity#isHeated` (a source with `lit` counts only lit; a
  conductor counts with a source under it) and `CookingPotBlock#getTrayState`
  (tray over a tray source, lit or not). Java blocks map to Bedrock blocks and
  states of the same meaning from bedrock-samples `mojang-blocks.json`
  (magma_block → magma; lava → lava + flowing_lava; lava_cauldron → cauldron
  with `cauldron_liquid` lava and `fill_level` > 0; campfire lit →
  `extinguished` false); vanilla block tags from misode/mcmeta summaries
  (1.21.1, 26.1). The stove doesn't convert (its blockstate is residue), so it
  doesn't heat the pot, with a note; `create:chute` is optional and absent.
  *Update (the stove entry above, 2026-10-13):* the stove now converts with
  a `farmersdelight:lit` state, and a lit stove is a heat source rule like a
  lit campfire; the note says so.
- **Remainders and containers:** the serving container is the recipe's
  `container`, else the result's crafting remainder from FD's ModItems
  (`bowlFoodItem`/`drinkItem`/explicit `craftRemainder`, every FD item listed
  per loader, so an unlisted FD item has none), and on Refabricated also
  `INGREDIENT_REMAINDER_OVERRIDES` (its `CookingPotRecipe.container()`). An
  ingredient's remainder is its crafting remainder (FD's, or the milk bucket's
  bucket, minecraft.wiki "Cake") else the overrides map. A recipe whose
  vanilla result has no `container` and no cited remainder, or whose
  ingredients include a vanilla item that may carry an uncited remainder
  (water/lava bucket, honey bottle, dragon's breath), stays residue.
- **Block:** the pot's facing × `support` (none/handle/tray) blockstate converts
  for station blocks only: one bone per support value, a custom state
  `farmersdelight:support` (Java's default `none` first), turned per
  `minecraft:cardinal_direction` by `minecraft:transformation` (uvlock is off,
  so Java turns the textures with the model, as transformation does; rotated
  elements like the spoon stay as they are), placement offset 180
  (`getHorizontalDirection().getOpposite()`), box from `SHAPE`. Handle when
  placed against a ceiling (`beforeOnPlayerPlace` face Down), tray/none from
  the block below on placement and every tick unless on the handle.
- **Why:** Same as the cutting board: the recipe data is complete, the
  behaviour is one piece of code read once. The hand model keeps every Java
  rule that doesn't need a screen (heat, timing, matching, stacking limits,
  containers, remainders, experience), and where a screen action has to be
  replaced it takes the menu's own routing. First-empty-slot insertion (not
  shift-click's merge-first) because otherwise recipes that need the same item
  in two slots (apple cider, hot cocoa, tomato sauce, onion soup, beetroot
  soup) could never be filled by hand.
- **Rejected:** *A `@minecraft/server-ui` form as the menu*: a second module
  dependency for what the action bar and three hand gestures cover, and forms
  can't show item icons or take drag-and-drop. *Shift-click insertion*: makes
  duplicate-ingredient recipes unreachable. *system.runInterval over a list
  of pots*: needs a registry of pot positions that breaks when chunks unload;
  `minecraft:tick` runs only where the block is ticking, as Java's block
  entity does. *Per-(support, facing) bones*: `turn_y` can't turn the
  rotated spoon, and turned textures are what Java does without uvlock.
  *Drawing the tray legs*: they sit wholly in the block below and push the
  model past Bedrock's 30-pixel geometry limit (learn.microsoft.com, Advanced
  Block Visuals), so the tray bone drops them (and the grate at y -0.001),
  with a note. *Heat from a hand-typed block list*: FD's tags are the source.
- **Not carried over (conversion note):** the menu and recipe book, hoppers and
  other automation (no block inventory), the meal kept inside the dropped pot
  item (`copy_components`; the meal drops as items instead), the contents
  when something other than a player destroys the pot, experience orbs
  (paid straight to the player who takes the output or breaks the pot; lost
  when the pot is destroyed otherwise), bubble/steam particles, comparator
  signal, waterlogging, the tray's collision slab and legs, pick-block of a
  filled pot, custom names, recipe unlocking. Boil sounds play with the
  chance that 1 in 10 per tick gives over 10 ticks. Stored stacks keep id,
  count, name, lore, durability damage, enchantments.
- **Scope:** the FD versions read (NeoForge 1.3.4 @dd8b9b0, Refabricated
  26.1-3.6.28 @a8cb49e); other versions stay residue. `food_serving` and
  `dough` are other recipe types (crafting specials), not part of this.
- **Links:** #177 (skillet, stove, feasts remain), #87, #190.

## 2026-10-13: station recipes become a generated data table run by a fixed Script API runtime (cutting board pilot)

- **Decision:** A recipe type whose behaviour is a block's Java code (pilot:
  Farmer's Delight's `farmersdelight:cutting`) is converted in three parts.
  (1) **Data table, generated:** every recipe of the type that passes its load
  conditions and can be stated exactly becomes one entry in a JavaScript data
  module, `behavior_pack/scripts/portkit/data/<ns>_cutting_board.js`, written
  deterministically (sorted, `json.dumps`) by `converters/stations.py`. Items
  and tags resolve through the existing machinery (`TagResolver` with the
  fetched loader/vanilla tag data; unions as `neoforge:compound` /
  `fabric:any` / JSON lists); a recipe naming an item this conversion didn't
  emit, an unknown ingredient type, or the same item + tool as another recipe
  is `station_recipe` residue with the reason (never narrowed, #87). (2)
  **Runtime, fixed:** a hand-written script checked into the package
  (`src/portkit/runtime/cutting_board.js` + `cutting_board_core.js`, copied
  verbatim) registers a block custom component (`<ns>:portkit_cutting_board`)
  that does what FD's code does, each behaviour cited to FD's source at the
  pinned commits; a generated two-line `scripts/portkit/main.js` wires table to
  runtime. (3) **Block, from the jar:** the station block's facing-only
  variants convert (one bone per facing, `minecraft:placement_direction`) only
  for station blocks, with the placement rule and shape read from the block's
  code (`y_rotation_offset` 180 because FD faces the board toward the player;
  collision/selection box from `SHAPE`), and it carries the custom component.
  The behavior pack gets a `script` module and a `@minecraft/server` 2.0.0
  dependency only when it ships `scripts/portkit/main.js`; that version shipped
  with Bedrock 1.21.90, which is also the first block format that reads a
  namespaced custom component, so the block is written at 1.21.90 and the
  engine floor rises with it.
- **Tool abilities:** FD's `item_ability` reads as one Java tag per ability,
  as Farmer's Delight Refabricated defines it (ItemAbility.java L37-45):
  axe_dig/axe_strip → `#minecraft:axes`, hoe_dig → `#minecraft:hoes`,
  pickaxe_dig → `#minecraft:pickaxes`, shovel_dig → `#minecraft:shovels`,
  sword_dig → `#minecraft:swords`, shears_* → `#c:tools/shear`, knife_* →
  `#c:tools/knife`. On NeoForge the ability is code (`canPerformAction`); its
  vanilla holders are the classes NeoForge gives `DEFAULT_*_ACTIONS`
  (ItemAbilities.java L152-157) and FD's own are its knives (KnifeItem
  KNIFE_ACTIONS), the same members as those tags with only this mod loaded,
  and every NeoForge recipe lists the tag beside the ability anyway. Except
  on NeoForge `sword_dig` and `shears_carve`: FD's knives perform those too
  (KNIFE_ACTIONS), so there they are more than the tag and stay residue (no
  NeoForge 1.3.4 recipe uses either). The table
  holds the resolved item ids; where the Java tag has a Bedrock tag of the
  same meaning (learn.microsoft.com Vanilla Item Tags: `minecraft:is_axe`,
  `is_hoe`, `is_pickaxe`, `is_shovel`, `is_sword`, `is_shears`) that tag is
  accepted too, as Java accepts any mod's axe in `minecraft:axes`. Any other
  ability or ingredient type is residue (`farmersdelight:tool_action` is not
  registered by FD 1.21, so Java never loads such a recipe).
- **Sounds:** a recipe's Java vanilla sound maps to the Bedrock vanilla event
  that plays exactly the same audio files (Java: misode/mcmeta 1.21.1-assets
  sounds.json; Bedrock: bedrock-samples sound_definitions.json; ties broken by
  verb): item.axe.strip → use.wood, block.metal.break → dig.stone, and FD's
  defaults (sheep shear, wood break/place/hit, item break). A recipe sound with
  no such event is played as silence, with a note, rather than the tool's
  default (which Java would not play).
- **Why:** The recipe JSON already carries every number that varies; the
  interaction is the same code for every recipe, so it is written once, read
  from the mod's source, and reviewed once. A data table keeps the converter
  deterministic and testable (the table is diffable output; the runtime is
  unit-tested offline with node against a stub of `@minecraft/server`), and the
  same split serves Mekanism single-input machines (#172) and anvil-style
  stations (#180): a new station is a table writer plus one runtime file.
- **Rejected:** *Generating script code per recipe or per mod*: 105-114
  near-identical functions per jar, no single place to review behaviour against
  the mod's source, and generated code is far harder to test than generated
  data. *Leaving it to the residue agent*: the agent writes JSON files against
  the validator; a scripted behaviour can't be checked by the oracle, would be
  re-invented differently run to run, and the agent has no way to read the
  Java code the behaviour lives in (#87). *A `minecraft:crafting_table`
  stand-in*: drops the tool requirement and the chance outputs, a gameplay
  change (#177 issue body).
- **Not carried over (said in the conversion note):** the item drawn on the
  board, sneak-placing a tool, cutting particles, comparator output,
  waterlogging, dispenser use, the advancement/statistic, the stored item when
  something other than a player destroys the board (`onBreak` needs script API
  2.4.0), the block break sound for a stored block item with no recipe sound
  (scripts can't read a block's sound type), and `cuttingBoardFortuneBonus`
  overrides (a double; `--config` takes boolean flags only, so the cited
  default 0.1 is used). *(Superseded in part by the 2026-10-15
  config values entry above: `--config
  farmersdelight.cuttingBoardFortuneBonus=<0..1>` now sets it.)* Stored stacks keep id, count, name, lore, durability
  damage and enchantments; other item data is not kept while on the board.
- **Scope:** runs only for the FD versions whose code was read (NeoForge 1.3.4
  @dd8b9b0, Refabricated 26.1-3.6.28 @a8cb49e); another version's cutting
  recipes stay residue and its board keeps its facing residue. Supplementaries'
  three FD cutting recipes are compat gated on Farmer's Delight
  (`conditional_recipe`, #183) and have no board in their jar either.
- **Links:** #177 (pilot; the cooking pot stays open), #172, #180, #87, #183.

## 2026-10-13: the residue agent follows the conversion's mod config; gated-off items' assets keep shipping

- **Decision:** the residue agent's guards decide config-gated items with the
  same `LoadContext` the converters use (cited flag defaults replaced by
  `--config` / `--config-file`): `pipeline.convert` hands `ResidueAgent.run`
  that context (built by the shared `SourceMod.from_metadata`), and the agent
  asks `LoadContext.gated_item`, the code the item converter uses, so there is
  one rule and one config. Run without a context, the agent builds one from
  the mod's metadata at the cited defaults. While a flag is off, an item it
  gates (a cited `registers` pattern, e.g. `mythicmetals:*_dust`) may not be
  defined by the agent (`agent.unknown_item`, message "item gated off by
  config flag mythicmetals:dust_enabled (disabled by default config: ...);
  enable with --config mythicmetals.enableDusts=true") nor named anywhere in a
  file the session writes: recipe inputs and outputs, loot entries, any JSON
  id, a `.lang` key (`agent.gated_item`, outcome field `gated_items`). Either
  rolls the group back. With the flag on, both pass. An id the pack already
  defines outside the session, or that the file held before the session,
  isn't the session's. No other agent guard reads the registered set: the
  stat, state, trim and namespace guards don't decide whether an item exists,
  and the recipe ref guard (`agent.unresolved_ref`) is covered by the new
  rule. Gated-off items' textures, `item_texture.json` entries and lang lines
  keep shipping (Mythic Metals: 27 dust textures, their atlas keys, and their
  lang lines, 28 in en_US).
- **Why:** since #186 the converter leaves gated items out, but the agent's
  registered set still held them (a lang key or a gated recipe names them),
  so a session on any other residue group could write back content Java
  doesn't register. Assets: Alex's keep-source-assets rule (2026-10-11, the
  unused Tinkers textures, #122); an unreferenced texture, atlas key or lang
  line has no effect in game, and keeping them makes the resource pack the
  same for every config, so a `--config` run differs only in behaviour files
  and default output stays byte-identical.
- **Rejected:** a second gating check in the agent (two rules that can drift);
  removing gated ids from `registry.registered_ids` (it reads the source, not
  a config, and has no context); dropping the dust textures/atlas/lang lines
  when gated off (against the asset policy, and churns every baseline for no
  in-game change).
- **Links:** #187.

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
- **Links:** #185, #186; builds on #183 / #184.

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
