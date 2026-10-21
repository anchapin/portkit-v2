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

## 2026-10-21 (pending Alex: picks 1a–3a, PR #PRNUM): a recipe whose type the mod's own code registers is the explained `mod_recipe_type`; a crafting-like variant converts only when its recipe class is plain vanilla

- **Decision (pick 1a, the kind):** a recipe with a non-`minecraft:` type that no adapter claims (fluid, modular tool, machine, code tables) and that isn't a special recipe is `mod_recipe_type` residue when the jar's bytecode is read registering it, or its namespace is the mod's own (Java has no data-driven recipe types, so only code registers one). The reason names the type and what the bytecode reads (`portkit.recipetypes`, no list of mods or types, #220): the registering class (a class of the mod naming `RecipeSerializer`/`RecipeType` that puts the type's path on the stack as a registry name: built into the full `ResourceLocation`, directly or through a namespace helper, or passed as the `String` of a `register`/`accept` call for a type in the mod's own namespace), the serializer class handed over (constructor reference, lambda constructing it, `new`, static `INSTANCE`) and the recipe class the serializer's generic signature names. Another mod's unregistered type stays `recipe` ("unsupported"). The kind is in `SKIP_KINDS`, so it counts as explained on the board. Each entry counts its 1 file (it is a real source file left unconverted), unlike #354's count-0 `renderer_drawn_parts`.
- **Decision (pick 2a, the split):** a recipe is *crafting-like* when its JSON has the vanilla shaped (`pattern`+`key`+`result`), shapeless (`ingredients`+`result`) or stonecutting (`ingredient`+`result`) shape, or wraps a vanilla recipe object. It converts, as that vanilla type, only when (i) its recipe class is read from bytecode, (ii) that class's superclass chain reaches vanilla `ShapedRecipe`/`ShapelessRecipe`/`StonecutterRecipe` matching the JSON shape, (iii) no class of the mod in that chain (or an interface default method) overrides `matches`, `assemble` or `getRemainingItems`, and (iv) the JSON holds nothing beyond the shape, recipe-book fields and load conditions, with only `minecraft:` ingredient types. Then Java does exactly what the vanilla recipe does, so nothing is invented or dropped (#87). Wrappers never convert (the wrapper class is code).
- **Decision (pick 3a, extras):** anything beyond the vanilla shape keeps the recipe residue and the reason names it: extra keys (`quarter_turn`, `nbt`, `copy_nbt`), non-vanilla ingredient types (IE `fluid_stack` creosote/water), and each overriding `Class#method`. No approximation ships: a fluid ingredient isn't replaced by a bucket, an NBT result isn't shipped bare, a tool that Java damages isn't consumed.
- **Why:** the 951 gauntlet entries were `recipe` "unsupported recipe type", which reads as a converter gap; they are a Bedrock limit (recipe types are a fixed list an add-on can't extend: shaped, shapeless, furnace, brewing, smithing). On the gauntlet jars every crafting-like variant read does more than its shape in code (IE `shaped_fluid`/`shapeless_fluid` through `IFluidAwareRecipe` defaults and fluid ingredients, `turn_and_copy` overriding `assemble` + `quarter_turn`, `no_container_item` through `INoContainersRecipe`; AE2 `quartz_cutting`'s `QuartzCuttingRecipe` overriding all three; Botania wrappers), so converting them would drop behaviour.
- **Measured:** see PR #PRNUM's runs comment (real-mods include_optional, gap-leaderboard on the gauntlet set, ingame).
- **Rejected:** a hand table of crafting-like types (#220); converting crafting-like variants by dropping their extras with a label (3b: still a recipe that gives what Java doesn't, or takes what Java gives back); explaining only types whose registering class is read (1b: a type in the mod's own namespace can't come from anywhere but its code, and the reason says the class wasn't read).

## 2026-10-21 (approved (Hark, high confidence under Alex's 2026-10-14 campaign order), PR #357): a sound event that plays another event inlines the target's sounds, resolved as Java's SoundManager does; `weight` is carried

- **Decision:** a Java sounds.json entry `{"name": "<event>", "type": "event"}` is replaced by the target event's sounds, recursively. Each flattened sound keeps its own weight within the target, its volume and pitch are the products down the chain, and stream is set when any link sets it; preload/attenuation stay unconverted as before. Targets are the mod's own events, or vanilla events read from vanilla's own sounds.json for the jar's game version (misode/mcmeta `sounds/data.json` at the six summary commits the vanilla tag sets pin, nearest version, sha256-pinned, fetched by `portkit reference fetch`, never vendored; `portkit.data.java_sounds`). Vanilla files then take the existing same-path rule (#116/#124). Another mod's event refuses the event, named (its sounds.json isn't in the jar). A loop refuses the event, naming the loop. A target no sounds.json defines, or one listing no sounds, drops only that entry. Java's per-sound `weight` is now written on every Bedrock sound when it isn't 1 (Bedrock's sound_definitions uses the same relative weight; 323 of its own vanilla entries carry one).
- **Why:** this is a faithful reproduction, not a policy pick. `SoundManager.Preparations#handleRegistration`'s `SOUND_EVENT` case wraps the target in a Weighted whose `getWeight()` is the target event's total weight and whose `getSound()` returns the target's pick with volume and pitch multiplied by the referencing entry's (`MultipliedFloats` from 1.19), stream OR-ed, preload and attenuation from the target; identical in the 1.16.5, 1.18.1 and 1.21.11 decompiled client sources (nectcon-source/minecraft-sourse, jacobo-mc/mc_1.18.1_src, dawalishi0396/mc-1.21.11-). So W_B/W_A x w/W_B = w/W_A: a flattened sound with its own weight is chosen exactly as often as in Java. An undefined target has weight 0 in Java (never picked). Reading vanilla's own sounds.json and keeping the same-path rule means no hand table (#220) and no guessed Bedrock path (#87).
- **Measured (local, old vs new converter on every Modrinth mod of the corpus and gauntlet, same Bedrock list and Java sets):** Botania sound residue 47 -> 5 entries (+42 events), Create 48 -> 16 (+32), Farmer's Delight NeoForge and Fabric 13 -> 4 each (+9), Supplementaries 5 -> 4 (+1); Biomes O' Plenty's 5 nether music events gain their weights (4:1:1:1:1). Every other mod's sound_definitions is byte-identical. Files are unchanged everywhere: these residue entries were count 0 (#354 counts them as 0 files), and sound_definitions.json was already one file, so coverage, the board and the mean don't move. Gauntlet (gap-leaderboard 39643163309 on 0bb4cb1, jar metadata as declared): sound 238 -> 74 entries, 2 files both; Twilight Forest 179 -> 16, Botania 47 -> 46 (its mods.toml declares no minecraft dependency, so no vanilla set is chosen and its 46 vanilla targets drop, saying so; with 1.20.1 known it is 47 -> 5), Quark 5, Biomes O' Plenty 1, Tinkers 5, Immersive Engineering 1 unchanged; board 40/50, mean 11.31%, every coverage unchanged.
- **Left:** a jar that declares no game version (Botania) gets no vanilla set; choosing one from other evidence (pack.mcmeta pack_format, the Forge major) would need a sourced table, so it is left for a follow-up. The remaining sound residue is mostly vanilla files Bedrock files under another path (armor equip, item frame, netherite, leash knot); mapping them needs a sourced Java-path -> Bedrock-path table (Bedrock's own event for the same sound), not a guess. Attenuation distance and preload are still not converted. Bedrock's clamping of out-of-range products (Botania writes pitch 0.001 and volume 20) is unverified in game.
- **Rejected:** keeping event references as residue (224 gauntlet entries of sound Bedrock can play); emitting the referencing entry's own weight (Java ignores it); one vanilla sounds.json for every game version (events differ between versions; the nearest-version rule is the tag sets' own).
- **Links:** #356, PR #357, #277, #116, #124, #354.

## 2026-10-21 (approved (Alex, 2026-10-21), PR #354): a block whose Java render shape is ENTITYBLOCK_ANIMATED or INVISIBLE for every state is `code_drawn_block`; a shipped MODEL block whose block entity a renderer of the jar accepts is flagged `renderer_drawn_parts` (0 files)

- **Status:** approved (Alex, 2026-10-21): picks 1a 2a 3a 4a 5a, the defaults (#352, part of #277, DESIGN PR #354, picks comment 6315425423). Measurements: see **Measured** (filled from the branch runs).
- **What Java does** (read, not assumed): `BlockBehaviour#getRenderShape(BlockState)` returns `RenderShape.MODEL`, `ENTITYBLOCK_ANIMATED` or `INVISIBLE`, and the client bakes a block's blockstate model into the world only for `MODEL` (1.21.1 `SectionCompiler#compile`, 1.20.1 `BlockRenderDispatcher#renderBatched`: `getstatic RenderShape.MODEL` / `if_acmpne`). Vanilla's own answers, read with `portkit.bytecode` from Mojang's client jars through client.txt (every class whose `getRenderShape` has code, resolved down the vanilla hierarchy): 1.19.2 (jar sha1 055b30d8…), 1.20.1 (0c3ec587…) and 1.21.1 (30c73b1c…) return `INVISIBLE` from `BaseEntityBlock` and its subclasses that don't override it (signs, skulls, banners, `MovingPistonBlock`, `EndPortalBlock`, …, plus `AirBlock`, `LiquidBlock`, `LightBlock`, `BarrierBlock`, `BubbleColumnBlock`, `StructureVoidBlock`) and `ENTITYBLOCK_ANIMATED` from `BedBlock`, `ChestBlock`, `TrappedChestBlock`, `EnderChestBlock`, `ConduitBlock`, `ShulkerBoxBlock`; every other vanilla block resolves to `BlockBehaviour`'s `MODEL`. 1.21.8 (a19d9bad…) has no `ENTITYBLOCK_ANIMATED` constant and `BaseEntityBlock` no longer overrides it (9 `INVISIBLE` classes). Tables in `portkit.rendershape.VANILLA`; full sha1s there.
- **Decision** (`src/portkit/rendershape.py`, `src/portkit/converters/blocks.py`, `src/portkit/pipeline.py`; no mod names, #220):
  1. **Read the shape** per registered block off the shared registration run: the first class up the chain that declares a method with `getRenderShape`'s descriptor (any name: Mojang, SRG/intermediary, 1.14–1.16 and 1.12 MCP class names) decides; it is run on the registered object (constructor fields known, state unknown), else read from its constants when it returns exactly one and calls nothing; a vanilla superclass's answer comes from the table for exactly the mod's game version. Anything else is unread and changes nothing. A block refused by the registration reader only for SRG/intermediary member names is read too (the method is found by descriptor).
  2. **Code-drawn shape** (`ENTITYBLOCK_ANIMATED` or `INVISIBLE` on every path): the blockstate is the explained `code_drawn_block` (the #296 kind), its models and their in-mod parents claimed; the reason names the shape and the class#method that returns it.
  3. **Mixed or unread shape:** unchanged (ships as before).
  4. **`MODEL` with a renderer:** the block ships its static model, and a count-0 entry of the new explained kind `renderer_drawn_parts` names the renderer. The block's block entities are the ones its `BlockEntity`-returning methods construct or its generic signature names; a non-abstract renderer class (implements `BlockEntityRenderer`, 1.15–1.16 `TileEntityRenderer`, 1.12 `TileEntitySpecialRenderer`) accepts one when it is a subtype of a concrete type argument in the renderer's own signature or of every bound of one of its own type parameters (the vanilla block entity base class itself as argument or bound counts for nothing), and some other class of the jar names the renderer. Read from class signatures, not from the registration call: it says a renderer can draw the block entity. Known limit: a generic renderer bound to a mod's own block-entity base class still over-matches every block entity under that base.
  5. **Withdrawn geometry:** a block `drop_untextured` withdraws for a texture that didn't convert takes its `models/blocks/*.geo.json` with it once no block left names a geometry the file defines (the orphan geometry #351 noted for Mekanism and Tinkers).
- **Why:** #352 / #277: since #351 blocks Java never draws as a model (Botania's mana spreaders, fabulous pool, cocoon, …) shipped their blockstate model as a static block; and bearings, basins and pools whose moving parts or contents a block-entity renderer draws shipped with nothing saying so.
- **Rejected:** see the picks comment on PR #354 (keep every static model with a flag only; refuse every renderer-drawn block; read the renderer registration call instead of signatures).
- **Measured** (branch head 9a7457e code = 41e3282):
  - Top-50 gauntlet (gap-leaderboard 39593087205 on 41e3282, banked in `docs/gauntlet.md`): done 40/50 before and after; mean coverage of converted mods 11.32% → 11.31%. Botania 47.6 → 47.4% (files 3675 → 3655), AE2 19.2 → 19.0% (811 → 801), Twilight Forest 25.2 → 25.1% (2320 → 2313), Quark 53.3 → 53.3% (3630 → 3628), Tinkers' Construct 53.2 → 53.2% (15382 → 15379); every other mod unchanged. `code_drawn_block` 8 mods / 324 files → 9 / 439; `block` 1174 → 1073 files. `sound` reads 2 files instead of 238 because its entries are count 0 (the 0-count rule of this PR in `gaps.py`).
  - Real corpus (real-mods 39594786990 with optional mods, rebanked in `fixtures/real/coverage-baseline.json` from files and residue, `round(100*files/(files+residue), 1)`): create 41.7 → 41.8% (files 4083 → 4077, residue 5697 → 5665), supplementaries 29.6 → 29.6% (1520 → 1518), tinkers_construct 52.5 → 52.5% (16683 → 16680), silent_gear_1165 37.1 → 37.0% (1116 → 1115), mekanism 16.1 → 16.0% (1251 → 1240); the other 8 mods unchanged. mct 0 errors.
  - Pack bytes, develop 5476b10 vs branch: create −6 files (hand_crank and turntable: block, recipe, geometry); supplementaries −2 orphan geometry (drawers, soul_jar); mekanism −11 orphan geometry (the induction cells and providers ×4 tiers each, teleporter, teleporter_frame, thermal_evaporation_controller) and 5 `renderer_drawn_parts` entries (the bins, `RenderBin`); tinkers_construct −3 orphan geometry (blazewood fence, slab, stairs); silent_gear_1165 −1 orphan geometry (refabricator); betterend and farmers_delight_neoforge change `unhandled.json` only; farmers_delight_fabric, waystones, alexs_mobs, mythicmetals, storage_drawers_1122 and storage_drawers_1192 byte-identical.
- **Not checked in game:** none of the refused or flagged blocks.
- **Links:** #352, #277, #351, #296, #87, #220.

## 2026-10-21 (approved (Hark, high confidence under Alex's 2026-10-14 campaign order), PR #351): texture variables resolve through the whole parent chain, a tagged face without a uv takes Java's derived uv, and the models an emitted block's item model reads go with the block

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order) (#350, part of #277, PR #351). A converter fix that follows Java's own model loading; no policy pick.
- **What Java does** (read, not assumed): a texture variable is resolved against the whole flattened model, child entries over parents', and a `#name` value is looked up again from the top until it reaches a location (1.21.1 `BlockModel#findTextureEntry`/`getMaterial`; 1.21.4+ `TextureSlots.Resolver`); an unresolvable or cyclic one is the missing texture. A face with no `uv` gets one from the element's position (1.21.1 `BlockElement#uvsByFace`, already `models.auto_uv`). Storage Drawers 1.21.1-13.11.4: `<wood>_full_drawers_N` sets `top`/`front`/`side`/`trim`, its parent `full_drawers_orientable` maps `down`/`up` to `#top`, `north` to `#front`, the sides to `#side`, and the grandparent `full_drawers` has the boxes, whose `up`/`north`/... faces name no `uv`.
- **Decision** (`src/portkit/converters/models.py`, `src/portkit/converters/items.py`, `src/portkit/ownership.py`; no mod names, #220):
  1. **Variables.** `models.resolve` resolves `#var` values in the merged map recursively (`models.resolve_variables`), with cycle detection. An unfilled variable keeps the last `#` reference (still residue, the reason names it); a cycle keeps the values as written. A variable only a vanilla template fills is left for `expand_template`, as before.
  2. **Derived uv on tagged faces.** When a block's elements disagree per face direction and every face names its material in the geometry, a face without a `uv` gets `auto_uv` instead of refusing the block. Untagged geometry is unchanged (a face without a `uv` still writes none).
  3. **Bookkeeping.** An emitted block's item model is claimed with the block already; the models it reads outside `models/item/` (its parent chain and its `overrides` models with their parents) are now claimed with it too, instead of turning `unowned` once the block ships. And a model's `textures` map names textures only: `portkit.ownership` no longer counts a texture value as a user of a same-named model (Botania's `*_spreader_core` models, loaded by its block-entity renderer, share their path with a texture), so such a model is `java_only_asset`, not `unowned`.
- **Why:** #277: Storage Drawers' biggest unexplained class (74 blocks, closing analysis 2026-10-20 item 11). The same two gaps refused blocks in other mods.
- **Measured:** gap-leaderboard 39556349927 on ad3d26a, all 50 mods (ok 50), against the 2026-10-20 board: Storage Drawers 38.1% → 63.3% (files 457 → 1026, residue entries 742 → 594, `block` 112 → 38; mct clean, 0/1280); Botania 46.9 → 47.6, The Twilight Forest 24.7 → 25.2, Quark 52.9 → 53.3, Biomes O' Plenty 50.0 → 50.3, Tinkers' Construct 53.2 (+0.1), Immersive Engineering 25.9 (+0.0); no mod went down. Cross-mod: `block` 1297 → 1174 files, `owned_by_residue` 6849 → 6700, `unowned [assets/<ns>/models/]` (223 files) leaves the top 25. Board: done 40/50 (unchanged), mean coverage of converted mods 10.77% → 11.32%; docs/gauntlet.md banked from that run. Corpus (real-mods 39556364874 on ad3d26a, include_optional; mct 0 errors on all 13 trees): storage_drawers_1192 41.3 → 73.2% (files 268 → 723, residue 381 → 265), create 41.4 → 41.7 (+22 files), mekanism 15.7 → 16.1 (+28), tinkers_construct 52.4 → 52.5 (+16), betterend 39.0 → 39.1 (+4), alexs_mobs 28.9 → 29.0 (files unchanged; its 2-file `unowned [assets/alexsmobs/models/]` entry goes: models an emitted block's item model reads, now claimed with it); farmers_delight (both), supplementaries and silent_gear_1165 lose 1–4 residue entries the same way with files and coverage unchanged; waystones, mythicmetals and storage_drawers_1122 unchanged. Rebanked in `fixtures/real/coverage-baseline.json`.
- **Pack bytes:** Local, whole tree, develop a8290f7 vs branch, `portkit convert --no-addon`: **create** +22 files, nothing removed or changed but `unhandled.json`: `clockwork_bearing`, `mechanical_bearing`, `windmill_bearing` (each `#side` filled two parents up) and `creative_crate` (`#crate`) gain block and geometry, plus 14 recipes (`clockwork_bearing`, `mechanical_bearing`, 12 `windmill_bearing__<stone>`). Java draws a bearing's turning top with a block-entity renderer; the static body is what ships. **tinkers_construct** +16 files, same shape: `ichor_slime`, `seared_`/`scorched_basin`, `scorched_table`, `seared_`/`scorched_fluid_cannon` (each refused before for a face without a uv) gain block and geometry, plus 4 recipes. **mekanism** +28 files: 13 machines whose `#front` is filled by a child (`crusher`, `combiner`, `enrichment_chamber`, `osmium_compressor`, `purification_chamber`, `chemical_injection_chamber`, `energized_smelter`, `precision_sawmill`, `pigment_extractor`, `painting_machine`, `fuelwood_heater`, `formulaic_assemblicator`, `oredictionificator`) gain block and geometry, plus the `module_color_modulation_unit` recipe; `thermal_evaporation_controller` now resolves its `#sides` and is refused for its CTM texture instead (still residue), which leaves its geometry file in the pack with no block naming it, as develop already does for 10 Mekanism and 3 Tinkers blocks refused over a texture (pre-existing; mct reports no error). **storage_drawers_1192** +455 files (the drawer blocks, their items and recipes); its `min_engine_version` moves 1.21.0 → 1.21.50 because the block items carry item tags. **betterend**: 4 chandelier blocks gain block and geometry, their 4 standalone item files go (a converted block's item is its block's), and 2 loot tables gain the `match_tool` gate a converted block's table carries. **alexs_mobs**: only `unhandled.json`.
- **`c:obsidians` (checked, no change):** Storage Drawers' `void_upgrade` puts the 2-member tag in 8 grid slots, 2^8 = 256 combinations, over the #302 cap of 16, so it is the explained `recipe_over_cap` (#343), not a bug. The closing analysis's "1 slot" was wrong.
- **Not checked in game:** blocks whose Java block returns `RenderShape.ENTITYBLOCK_ANIMATED` (Botania's mana spreaders and pools) now ship their blockstate model as a static block, as Botania's cocoon already does on develop; Java draws them through a block-entity renderer (a spreader turns toward its aim). Not verified in game. Reading `getRenderShape` is the follow-up (the refinement the 2026-10-16 `code_drawn_block` entry left open; #352).
- **Rejected:** keeping the refusal for faces without a `uv` (Java fills it, so it was a converter gap, not a rule); resolving variables only one hop (Storage Drawers' chain is two); a substitute texture for an unfilled variable (#87).
- **Links:** #350, #277, #87, #220, #302, #343, #352.

## 2026-10-20 (approved (Alex, 2026-10-21): picks 1a–6a, PR #349): a texture sidecar with a Connected Textures Mod `"ctm"` section and no animation is the explained `connected_texture` (not converted); texture keys from pre-1.13 paths are lowercased and sanitised

- **Status:** approved (Alex, 2026-10-21): picks 1a–6a (#348, part of #277, PR #349; picks comment https://github.com/anchapin/portkit-v2/pull/349#issuecomment-6307434303). The branch implements every "a" pick. docs/gauntlet.md is banked from gap-leaderboard 39538703718, approved with the picks.
- **What the jar holds** (read from Chisel-Team/Chisel `1.12/dev` sources, a0df104, GPL-2.0; the CurseForge jar itself is only read in CI, #278 pick 2): Chisel 1.12.2-1.0.2.45 ships `.png.mcmeta` sidecars whose only section is `"ctm"` (857 in the jar per gap-leaderboard 39529691385; 866 in the source tree), 22 (source tree) with both `"ctm"` and `"animation"`, and 4 that aren't valid JSON (`animations/strobe` misses a comma; `technical/malfunctionfan-side`, `technical/new/oldetimeyserveranim` and `technical/new/tapedrive` end `frames` with a trailing comma); none of the 4 has a `"ctm"` section. CTM types in the source tree's ctm-only sidecars: `ctm` 398, none (NORMAL: only a render `layer`) 157, `pattern` 134, `random`/`r` 91, `ar` 42, `pillar` 26, `ctmh` 15, `sctm` 3. Seven block textures have keys the validator refuses: `dirt/bricks+dirt2-ctmv.png`, `hexPlating/{hexbase,hexnew}.png`, `redstoneLamp/{redstone_lamp_off,redstone_lamp_on,square-off,square-on}.png` (before 1.13, Minecraft did not restrict resource paths to [a-z0-9/._-]).
- **Decision** (`src/portkit/converters/textures.py`, `src/portkit/agent/residue.py`; no mod names, #220):
  1. **The kind (1a).** A sidecar that parses as a JSON object with a `"ctm"` key and no `"animation"` key is `connected_texture` residue instead of `texture_animation`, whatever its CTM `type`. `"ctm"` is the metadata section the Connected Textures Mod reads (`team.chisel.ctm.client.texture.IMetadataSectionCTM.SECTION_NAME`, Chisel-Team/ConnectedTexturesMod `1.12/dev` and `1.21/dev`), not Minecraft; CTM draws the texture per block from its neighbours (`ctm`, `ctmh`, `ctmv`, `pillar`, `sctm`, `edges`), from the block's position (`pattern`, `random`/`r`, `ar`, through `TextureTypeMap`) or only sets its render layer (no type = NORMAL). A Bedrock block texture is fixed per face (`minecraft:material_instances`, `terrain_texture.json`), with no neighbour lookup. The reason names the CTM type. Generic: any mod's CTM sidecars.
  2. **Invalid JSON stays `texture_animation` (2a).** The 4 aren't known to be CTM's (none has a `"ctm"` section; all 4 are animation sidecars). Java may still read 3 of them: Gson's `JsonParser.parse(Reader)` sets its reader lenient (gson 2.8.0 `JsonParser.java` line 82), and a lenient reader takes `,]` as a trailing null element (`JsonReader.java` line 558); whether 1.12's resource metadata reader goes through it, and what its animation parser does with the null, is not checked. Left open.
  3. **Not converted (3a).** The texture goes with its sidecar, as for every unmapped sidecar today: a `pattern` texture is an N×N sheet and a connected texture's look depends on CTM, so a static png would draw it wrong (#87). Pack bytes unchanged by the kind.
  4. **Animation beside a `"ctm"` section is unchanged (4a):** it still converts as a flipbook, the CTM layout dropped as today. Refusing those changes pack bytes and is a separate call.
  5. **The residue agent skips the kind (5a)** (`SKIP_KINDS`): its tools write static textures and flipbooks, neither of which can follow CTM either.
  6. **Keys (6a), converter fix:** `textures.shortname` lowercases the path and maps every character outside `[a-z0-9_.]` to `_`, as `/` and `-` already were; a legal Java path (`[a-z0-9/._-]`) gives the same key as before. Only the key changes: the file keeps its path, which the index entry names (`chisel:hexplating_hexbase` → `textures/blocks/hexPlating/hexbase`), and models resolve through the same function. Two textures that land on one key are both `texture` residue (existing clash rule). Measured: no clash in Chisel's source tree.
- **Why:** #277: Chisel's 7 validator errors and its biggest explainable residue class (closing analysis 2026-10-20, items 8–9).
- **Measured** (gap-leaderboard 39538703718 on bf9ce78, all 50 mods, against #347's board 39529691385): Chisel mct errors 7 → 0 (valid), `texture_animation` 861 → 4 files (the 4 invalid-JSON sidecars), `connected_texture` 857; Chisel files 2653, residue 1763 and coverage 60.08% unchanged; the other 49 mods' records identical. Chisel stays open (unexplained: `block`, `texture_animation`, `unowned`). Board: done 40/50, mean coverage 10.77%, both unchanged. docs/gauntlet.md banked from that run's shards with the trend against 39529691385, approved with the picks. Pack bytes: only Chisel's, and only the 7 renamed keys in `terrain_texture.json` and what names them (`flipbook_textures.json` `atlas_tile` for the animated `hexPlating/hexnew`); a legal Java path gives the same key as before, so no other mod's bytes can move (real-mods: see the runs comment).
- **Rejected:** 1b, only neighbour-connected types (leaves `pattern`/`random`/NORMAL as `texture_animation`, which reads as converter work); 1c, any section vanilla doesn't read (no second case on the gauntlet to check it against). 2b, a separate explained `invalid_mcmeta` kind (Java may read 3 of the 4, so "invalid" would be wrong for them); 2c, reading leniently now (the 1.12 path above is unchecked). 3b, shipping the base png as a labelled DEFAULT (a pattern sheet squashed onto one block). 6b, also lowercasing the file path (no need: the index names the path, and mct accepts it).
- **Left:** CTM `random`/`r` could map to Bedrock `terrain_texture.json` `variations` (weighted per-position choice) after an in-game check; NORMAL-type sidecars (render layer only) could ship as static textures with the layer as `render_method`; lenient reading of the 3 trailing-comma animation sidecars; 1.12 `.lang` files; Chisel's 1.12 `forge_marker` blocks.
- **Links:** #348, #277, #288, #87, #220, #278.

## 2026-10-20 (approved (Alex, 2026-10-20): picks 1a–7a, PR #347): an `assets/<ns>/` folder Minecraft's client doesn't read, all JSON, that no class of the jar names is `other_mod_data`; a block whose model borrows a vanilla texture outside block/ and item/ is the explained `vanilla_texture_outside_atlas` (still not converted)

- **Status:** approved (Alex, 2026-10-20): picks 1a–7a (#346, part of #277, PR #347; picks comment https://github.com/anchapin/portkit-v2/pull/347#issuecomment-6306062465). The branch implements every "a" pick. docs/gauntlet.md is banked from gap-leaderboard 39529691385 (trend against #345's board 39517100055), approved with the picks.
- **What the jar holds** (read, not assumed): Comforts 9.0.5+1.21.1 (NeoForge) ships `assets/comforts/seamless_rules/{hammock,sleeping_bag}_{head,foot}.json`, JSON objects naming only `#comforts:` tags (`blocks`, `blockstates`, `directions`, `connecting_blocks`, `connecting_blockstates`); none of its 64 classes holds `seamless` in a string and its `neoforge.mods.toml` declares no dependency beyond NeoForge and Minecraft. Its block `rope_and_nail` has two models (`rope_and_nail`, `rope_and_nail_s`) that take 18 and 30 faces from `minecraft:entity/lead_knot`.
- **Decision** (`src/portkit/worldgen.py`, `src/portkit/converters/blocks.py`, `src/portkit/converters/models.py`, `src/portkit/agent/residue.py`; no mod names, no list of mods' folders, #220):
  1. **Asset folders (1a).** `other_mod_data` (#316) also covers an unowned `assets/<ns>/<dir>/` when `<dir>` is not a folder Minecraft's client reads, every file in it is a JSON object, and no class of the jar holds `<dir>` anywhere inside a string constant (so the mod's own code can't be building its path). The reason names the folder and says the evidence; it can't name the reader, since nothing in the jar does. Without the jar's classes nothing is re-filed. The data/ rule is unchanged (it still needs a foreign `type`/`target_*`).
  2. **Vanilla textures outside block/ and item/ (2a).** A `block` entry refused because a model names a vanilla texture in a Java folder other than `block/` and `item/` (`entity/`, `misc/`, ...) is re-filed as the explained `vanilla_texture_outside_atlas`, keeping the converter's reason. Not converted: the converter names vanilla textures only through Bedrock's terrain and item atlases (portkit.data.vanilla_textures, bedrock-samples 46ba6ea9), which list no such file, and the pack can't carry Mojang's art (#24). Checked for the one case on the gauntlet: bedrock-samples 46ba6ea9 does have `resource_pack/textures/entity/lead_knot.png` (32×32, the `minecraft:leash_knot` client entity's skin), but a pixel check against Java's `assets/minecraft/textures/entity/lead_knot.png` (1.21.1 client jar sha1 30c73b1c5da787909b2f73340419fdf13b9def88 and 1.21.11 ba2df812c2d12e0219c489c4cd9a5e1f0760f5bd) differs in 70 of 334 visible pixels: the knot's box area (rows 0–13) is identical, but Java's rows 19–25 are transparent in Bedrock's copy, and 10 of rope_and_nail's 48 lead_knot faces (Box3 down/up, north/south) sample them. Naming Bedrock's file would draw those faces wrong (#87), the rule #296 set for a different-name pair.
  3. **Guide book folders count (3a).** Botania's `assets/botania/patchouli_books/` (265 files, read by Patchouli) meets 1a and is re-filed. A reader for it (#182) would claim the files first, and they'd leave this kind then.
  4. **Items unchanged (4a).** An item icon refused for the same kind of texture keeps `item`: measured 0 on the gauntlet, so there is no case to check a rule against.
  5. **The client's folders (5a)** are read from the jars, not hand-written: every `assets/minecraft/` folder in the 1.21.1 client jar (atlases, blockstates, font, lang, models, particles, shaders, texts, textures) and the 1.21.11 one (adds equipment, items, post_effect, waypoint_style), `sounds/` (the asset index), and the data folders 1.12 still read from `assets/` (recipes, advancements, loot_tables, structures, functions).
  6. **"Names the folder" is a substring test (6a):** any string constant containing `<dir>`, so a class building `"<dir>/" + name` or a resource location with it keeps the folder `unowned`. Conservative: a short common folder name (`book`) stays unowned.
  7. **The residue agent skips both (7a)** (`SKIP_KINDS`).
- **Why:** #277: these were Comforts' last unexplained residue (after #341), and the same two cases are general: data another jar reads, and art Bedrock has no checked copy of.
- **Measured** (gap-leaderboard 39529691385 and 39527765485 on the branch, identical, against #345's board 39517100055, all 50 mods): unowned → `other_mod_data` 318 files in 4 mods: Comforts 4 (`seamless_rules`), Botania 265 (`patchouli_books`), Immersive Engineering 44 (`transformations`), Quark 5 (`train_hat_info`); none of the three other folders is named by a class of its jar. `block` → `vanilla_texture_outside_atlas`: Comforts 1 (`rope_and_nail`); `block` 11 mods/1298 files → 10/1297. Files, residue counts, coverage and pack bytes unchanged for every mod (re-filing only; Comforts' packs md5-identical locally). Board: done 39 → 40/50 (Comforts), mean coverage 10.77% unchanged.
- **Rejected:** 1b, a separate kind for asset data: the same fact as #316's (no reader in Minecraft, the loader or this jar). 1c, requiring a foreign namespace as data/ does: none of the four folders has one, so Comforts stays unexplained. 2b, converting with Bedrock's `textures/entity/lead_knot` through a pack atlas entry: the pixel check above. 2c, keeping `block`: it reads as converter work there's no way to do without Mojang's art. 3b, excluding book folders: needs a list of readers' folder names (#220).
- **Left:** a pixel-checked pairing table for `entity/` textures (like #296's aliases) would let a block whose sampled pixels match convert; the one case on the gauntlet doesn't.
- **Links:** #346, #277, #316, #296, #24, #87, #182, #220, #341.

## 2026-10-20 (approved (Alex, 2026-10-20): picks 1a–6a, PR #345): an item whose model overrides switch on an item property the mod's own code registers is the explained `live_item_property` residue (still not converted; #169 stands)

- **Status:** approved (Alex, 2026-10-20): picks 1a–6a (#344, part of #277, PR #345; picks comment https://github.com/anchapin/portkit-v2/pull/345#issuecomment-6304455925). The branch implements every "a" pick. docs/gauntlet.md is banked from gap-leaderboard 39517100055 (trend against #343's board 39499922058), approved with the picks.
- **What Java does** (read, not assumed): Nature's Compass 1.21.1-3.4.0's only item model with overrides, `assets/naturescompass/models/item/naturescompass.json`, picks one of 32 needle frames on `naturescompass:angle`, registered in `NaturesCompassClient#lambda$clientInit$0` as `ItemProperties.register(NaturesCompass.naturesCompass, ResourceLocation.fromNamespaceAndPath("naturescompass", "angle"), new NaturesCompassClient$1())`. `NaturesCompassClient$1#unclampedCall` computes the angle every frame from the holder (or item frame) toward the found biome (`getFoundBiomeX/Z` when the state is FOUND), else toward the world spawn (`getSharedSpawnPos`), with a `wobble`; with no holder it returns 0, the 0.0 override, which is the base look (`naturescompass_16`).
- **Decision** (`src/portkit/itemprops.py`, `src/portkit/converters/items.py`, `src/portkit/agent/residue.py`; no mod names, no list of properties, #220):
  1. **The kind (1a).** A flat-icon item model whose `overrides` the base-icon rule (2026-10-12, #169) refuses, where every predicate without a known resting look (a readout or an unknown name) is a mod-namespaced property the mod's own code registers, is `live_item_property` residue instead of `item`. Predicates with a resting look beside them don't matter. The item is **not converted**: #169 ("a frozen frame would show a false reading; an unknown predicate may not have a resting state") stands, and this only explains it. The reason names each property and the class that builds it. Owned recipes and advancements follow it unchanged (#343, #341).
  2. **Vanilla names are never counted (2a).** A `minecraft:` key, bare (`time`, `angle`, `pull`, `pulling`) or namespaced, keeps today's handling (resting kinds convert; readouts and unknown names stay `item`), even when the mod's code builds that name: a mod may build vanilla's name only to read vanilla's own property, so the name alone isn't evidence of the mod's registration. Measured: 0 items move either way on the gauntlet: the only vanilla names a mod's code registers there (Botania's `minecraft:pull`/`pulling` on its two bows, Waystones' `minecraft:brushing` on the twinbound feather) are resting kinds, and those items already convert as their base icon.
  3. **No static stand-in (3a).** A Bedrock item's `minecraft:icon` is a static map of textures (`default`, plus armor trim textures and palettes; learn.microsoft.com, "Items Documentation - minecraft:icon", https://learn.microsoft.com/en-us/minecraft/creator/reference/content/itemreference/examples/itemcomponents/minecraft_icon): nothing in it selects a texture by a value. Nature's Compass' base frame is a needle Java shows only with no holder, so shipping it would freeze a direction (a false reading), and the jar has no needle-free frame.
  4. **1.21.4+ item model definitions (4a).** The reader also knows the 1.21.4 property interfaces (`RangeSelectItemModelProperty`, `SelectItemModelProperty`, `ConditionalItemModelProperty`; mappings.dev 1.21.4, `net.minecraft.client.renderer.item.properties.*`), but the item converter doesn't read `assets/<ns>/items/` yet, so there is no residue entry to re-kind; it follows when it does (#181). No gauntlet mod ships one (all are ≤ 1.21.1).
  5. **The residue agent skips the kind (5a)** (`SKIP_KINDS`): its tools write static item JSON, which can't follow the property either.
  6. **Evidence (6a).** A property counts as registered in code when a class whose code names one of Java's item property function types (`ItemPropertyFunction`, `ClampedItemPropertyFunction`, or the 1.21.4 interfaces above) builds that exact name as a `ResourceLocation` from string constants: `fromNamespaceAndPath`/`tryBuild`/the two-string constructor, `parse`/`tryParse`/the one-string constructor, `withDefaultNamespace`, or a static mod helper (`ldc ns; aload_0; <factory>; areturn`, followed two calls deep: Quark's `Quark.asResource`, Botania's `ResourceLocationHelper.prefix`, Tinkers' `TConstruct.getResource`), including a static field the same class initialises. This reads all six registration paths on the gauntlet: direct `ItemProperties.register` (Nature's Compass, Quark, AE2, Tinkers' Construct), a mixin accessor of it (Waystones `ItemPropertiesAccessor.callRegister`) and a consumer handed `ItemProperties::register` (Botania `BotaniaItemProperties.init(TriConsumer)`). A name built any other way is not read, and the item stays `item`.
- **Why:** #277: Nature's Compass' last unexplained residue was this one item (its recipe is already owned by it, #343). Keeping it as plain `item` made "kept on purpose" (#169) indistinguishable from "not handled yet".
- **Measured** (local, develop c72908e → branch, pinned gauntlet jars; confirmed for all 50 by gap-leaderboard 39517100055, which also ran Twilight Forest and Chisel: 0 there, and Tinkers' Construct 0): `item` → `live_item_property`, 27 files in 3 mods: Nature's Compass 1 → 0 (`naturescompass`), Quark 6 (abacus `quark:count`, backpack `quark:has_items`, crab_bucket `quark:variant`, pathfinders_quill `quark:has_biome`, seed_pouch `quark:pouch_items`, slime_in_a_bucket `quark:shiny`+`quark:excited`), Botania 20 (wands, horns, armor `botania:holiday`, brews, mana bottle/cookie, lexicon, terra pick, spawner mover, bauble box, sword, shears, infinite fruit). AE2, Waystones, Immersive Engineering unchanged (their override items convert already or are residue for another reason). Files, residue counts, coverage and pack bytes unchanged for every mod; only `unhandled.json` kinds and reasons. Board: done 38 → 39/50 (Nature's Compass).
- **Rejected:** 1b, only readout-named properties (`time`, `angle`, `radiation`, `speed`, `in_chunk`): Nature's Compass only, but it keys the kind on #169's name list instead of the code (#220), and Quark's and Botania's unknown-property items stay residue for the same #169 reason with no explanation. Shipping the base icon as a labelled DEFAULT (3b): a frozen needle states a false direction, the reason #169 kept these. Counting vanilla names the mod builds (2b): reading vanilla's own property builds the same name. Requiring the literal `ItemProperties.register` call (6b): misses Botania's and Waystones' registrations.
- **Left:** reading a property function's no-holder value, which could later convert items whose base look is their resting look (Botania's name easter eggs, Quark's empty backpack); 1.21.4+ item definitions (4a).
- **Links:** #344, #277, #169, #181, #220, #343, #341, #87.

## 2026-10-20 (approved (Alex, 2026-10-20): picks 1a–8a, PR #343): a refused recipe whose result is residue is `owned_by_residue`; a recipe refused only for the #302 expansion cap is the explained `recipe_over_cap` (still not converted)

- **Status:** approved (Alex, 2026-10-20): picks 1a–8a (#342, part of #277, PR #343; picks comment https://github.com/anchapin/portkit-v2/pull/343#issuecomment-6301949983). The branch implements every "a" pick.
- **Decision** (`src/portkit/converters/recipes.py`, `src/portkit/agent/residue.py`; keyed on the recipe's own JSON and the residue entries, never a mod's name):
  1. **Result is residue → `owned_by_residue` (1a).** The recipe converter records every recipe's result (`ConversionResult.recipe_results`: `result.item`, `result.id` or a bare id; a bare path is `minecraft:`; a `#` name is none). After the ownership pass, `recipes.refine_owned` re-files a `recipe` or `recipe_over_cap` entry whose result is a mod item the pack doesn't ship under that id and that has a residue entry of its own (its blockstate, item model or item definition, any kind but `unowned`/`recipe`/`recipe_over_cap`, the #303 rule) as `owned_by_residue`, whatever else refused it. The reason names the result, its entry and kind, and keeps the recipe's own kind and reason. A `minecraft:` result never counts. Bedrock refuses a recipe whose result it doesn't know ("Recipe result malformed", #238), so the recipe can't ship before its result does; when the result converts, the recipe converter reads the recipe again and its own refusal (if any) comes back.
  2. **Recipes refused only for the cap are `recipe_over_cap` (2a),** an explained kind in the residue agent's `SKIP_KINDS`. Only when every refused ingredient's membership is fully known, every member is vanilla or emitted by this conversion, every vanilla member has a Bedrock id (`bedrock_item`), and one of the two capped forms fits but for its size: one tag or item list in one slot (one recipe per member, n) or #302 pick 1's vanilla-only tags over several slots (one recipe per combination, nᵏ multiplied over the tags; never a furnace). The reason names each tag or list, its member count, the slots it fills (nᵏ) and the total, and keeps the ingredient's own reason. **The recipe is still not converted**: #302's cap ("still residue") stands; this only explains it.
  3. **The owner may be any residue kind (3a),** as #303: an unexplained owner (Nature's Compass' live-readout compass, `item`) still owns its recipe; the owner itself stays open.
  4. **Item lists over several slots stay `recipe` (4a).** #302 pick 1 writes combinations of vanilla-only *tags*, not lists, so a list over several slots has no capped form for the cap to be the only reason (Iron Chests' dirt chest is owned by its result instead).
  5. **Result ownership wins over `recipe_over_cap` (5a):** a recipe that is both is `owned_by_residue` (its reason keeps `recipe_over_cap: ...`).
  6. **Advancements follow unchanged (6a):** #341 pick 1a already owns a recipe advancement whose recipes all have residue entries of any kind but `unowned`, so the advancements of these recipes stay `owned_by_residue`; nothing new.
  7. **The residue agent skips `recipe_over_cap` (7a):** writing a narrowed recipe would break #302's "a recipe is never narrowed to part of a tag".
  8. **Every `recipe` refusal counts for 1, unsupported types included (8a):** a recipe of a type the converter doesn't support (`unsupported recipe type ...`, kind `recipe`) whose result is residue is owned too (24 files on the gauntlet: AE2 8, Immersive Engineering 13, Botania 3), for the same reason. Types an adapter or the code-recipe table explains (`machine_recipe`, `code_recipe`, ...) keep their own kinds; `conditional_recipe` (Java doesn't load it) is never touched.
- **Why:** #277: Iron Chests' last unexplained residue was 8 recipe files (4 chest recipes whose result chests are `code_drawn_block`, 4 upgrade recipes over the cap with `forge:glass`, 18 members), and Nature's Compass' recipe names its residue compass.
- **Measured** (gauntlet, gap-leaderboard 39499922058 on 0f23246 vs develop's board 39485986978): done 37 → 38/50 (Iron Chests), mean 10.77% unchanged; files, residue, coverage and validator errors identical for all 50 mods (no pack byte changes; only `unhandled.json` kinds and reasons). `recipe` 1288 → 1130 files (11 → 9 mods); `owned_by_residue` +145; `recipe_over_cap` 13 files in 6 mods (Iron Chests 4, Immersive Engineering 3, AE2 2, Tinkers 2, Storage Drawers 1, Twilight Forest 1); 17 more over-cap recipes are owned by their result (5a). Per mod `recipe` before → after: Iron Chests 8 → 0, Nature's Compass 1 → 0 (item still open), Quark 157 → 115, AE2 126 → 104, Immersive Engineering 505 → 450, Botania 309 → 300, Twilight Forest 70 → 59, Tinkers 34 → 28, Cooking for Blockheads 69 → 66, Storage Drawers 2 → 1 (`c:obsidians` is 2 members over 8 slots, 2^8 = 256, so over the cap, not under it).
- **Rejected:** raising or dropping the cap for these recipes (#302 decided against flooding the recipe book); narrowing a tag to some members (#302, #160); owning only when the other refusal is itself explained (1b: leaves the dirt chest and Nature's Compass' recipe open for a reason that can't matter until the result ships); counting a result the pack ships under its id (Bedrock knows it).
- **Links:** #342, #277, #302, #303, #341, #296, #169, #181, #238.

## 2026-10-20 (approved (Alex, 2026-10-20): picks 1a–6a, PR #341): leftover advancements are `owned_by_residue` when their recipes are residue, else the explained `no_bedrock_advancement` (story advancements, furnace-recipe and undefined-recipe advancements); nothing is granted

- **Status:** approved (Alex, 2026-10-20): picks 1a–6a (#340, part of #277, PR #341; picks comment https://github.com/anchapin/portkit-v2/pull/341#issuecomment-6297977154). The branch implements every "a" pick.
- **Decision** (`src/portkit/advancements.py`, run after `worldgen.refine`; keyed on the advancement's own JSON, never a mod's name):
  1. **Recipe advancements of residue recipes are `owned_by_residue` (1a).** A recipe advancement (`rewards.recipes`) every one of whose recipes is a recipe file of the jar (`data/<ns>/recipe[s]/`) with a residue entry of its own (any kind but `unowned`) goes with those recipes, the #299 / #302 pattern. Its one effect is unlocking them in Java's recipe book; when a recipe converts, #260 already reads its advancement for the crafting recipe's Bedrock `unlock` (`inventory_changed` items/tags read exactly, else `AlwaysUnlocked`, labelled) and claims it. No change to #260's rule.
  2. **Story and challenge advancements are `no_bedrock_advancement` (2a).** An advancement with no recipe reward: Bedrock has no data-driven advancements. Its achievements are a fixed list tracked per account, and external behaviour packs turn them off for a world (minecraft.wiki, "Achievement", https://minecraft.wiki/w/Achievement); the add-on JSON reference defines no advancement or achievement (learn.microsoft.com, Bedrock reference). Nothing in a pack can track or show one.
  3. **Rewards are not given (3a).** A story advancement's `experience`, `loot` or `function` rewards are named in the reason and not given. A pack never gives more than Java. Giving them some other way (a script on the same criteria) would be inventing the trigger.
  4. **Furnace-recipe advancements are `no_bedrock_advancement` (4a).** A recipe advancement whose recipes all ship as `minecraft:recipe_furnace` (Java smelting, blasting, smoking, campfire cooking): Bedrock's furnace recipe has no `unlock` field (learn.microsoft.com, "minecraft:recipe_furnace", https://learn.microsoft.com/en-us/minecraft/creator/reference/content/recipereference/examples/recipedefinitions/recipe_furnace; unlock data is a crafting-recipe field, "Recipe Introduction - Recipe Unlocking"), so the shipped recipe needs nothing from it.
  5. **Advancements naming recipes the jar doesn't define are `no_bedrock_advancement` (5a).** Every recipe it rewards is a recipe id no data file of the jar defines (Cooking for Blockheads' datagen rewards `minecraft:dye_*`, while its recipes are `cookingforblockheads:dye_*`; Storage Drawers' `balance_fill_upgrade` vs the recipe `balanced_fill_upgrade`). There is no converted recipe whose `unlock` could carry it.
  6. **Everything else stays `unowned` (6a).** Not a JSON object, `criteria` not a non-empty object, `rewards` with a key Java's `AdvancementRewards` doesn't have (experience, loot, recipes, function: minecraft.wiki, "Advancement definition"), a recipe reward next to other rewards, or recipes that are a mix of the cases above.
- **Why:** #277: `unowned [data/<ns>/advancement/]` was 796 files over 8 mods on the gauntlet board, and one of the last unexplained classes for Iron Chests, Comforts and Nature's Compass.
- **Measured** (local, develop 77439c4 -> branch, pinned gauntlet jars, Twilight Forest is CurseForge-only and measured in CI): unowned advancement files -> 0 in every mod measured: Comforts 66 (66 owned), Iron Chests 8 (`advancements/`, 8 owned), Nature's Compass 3 (3 owned), Quark 193 (163 owned, 30 story), Immersive Engineering 226 (80 owned, 81 furnace, 65 story), Cooking for Blockheads 123 (3 owned, 1 furnace, 119 undefined recipe), Storage Drawers 9 (7 owned, 2 undefined recipe). Pack bytes, files and residue counts unchanged.
- **Rejected:** converting story advancements to anything Bedrock has (there is no data-driven achievement); scripting rewards on the same criteria (invents a trigger, can give more than Java); claiming furnace-recipe advancements as converted (they carry nothing the pack holds); treating a mistyped recipe id as the recipe it probably means (#87).
- **Links:** #340, #277, #260, #299, #302, #279, #316, #87.

## 2026-10-20 (approved (Alex, 2026-10-20): picks 1a–6a, PR #339): a NeoForge `neoforge:add_table` loot modifier that adds to a vanilla block's table converts as a drop a fixed runtime adds on a player's break of that Bedrock vanilla block; additions to any other vanilla table, and modifiers the jar doesn't list, stay residue

- **Status:** approved (Alex, 2026-10-20): picks 1a–6a (#280, PR #339 "Part of #280: Quark loot injection tables"; picks comment https://github.com/anchapin/portkit-v2/pull/339#issuecomment-6296584853). Every "a" below is implemented, 6a included.
- **What Java does** (read, not assumed): Quark 4.1-487's 18 `data/quark/loot_table/inject/**` tables are not added by code but by NeoForge global loot modifiers: `data/quark/loot_modifiers/inject/**.json`, each `{"type": "neoforge:add_table", "conditions": [{"condition": "neoforge:loot_table_id", "loot_table_id": "minecraft:blocks/glass"}], "table": "quark:inject/blocks/glass"}`, and `data/neoforge/loot_modifiers/global_loot_modifiers.json` lists 17 of the 18 (glass and the 16 stained glasses). NeoForge 1.21.1 (github.com/neoforged/NeoForge, branch 1.21.1): `LootModifierManager#prepare` loads only modifiers that list names; `AddTableLootModifier#doApply` rolls the table with the broken block's loot context (`getRandomItemsRaw`) and adds its items. Each table is gated on `zeta:flag` `glass_shard` (on by default, PR #338's reader) and gives 2-4 shards (`set_count` uniform), Fortune `uniform_bonus_count` x1, `limit_count` 1-4, `explosion_decay`, never with Silk Touch. The 18th, `inject/gameplay/sniffer_digging` (ancient sapling into `minecraft:gameplay/sniffer_digging`), is unlisted, so NeoForge never loads it; Quark's sniffer sapling comes from code instead (`AncientWoodModule#onLootTableLoad` adds an `ancient_sapling` entry to the vanilla table's `main` pool through Zeta's `ZLootTableLoad`, as `ColorRunesModule`, `AncientTomesModule` and `EndermoshMusicDiscModule` add runes, tomes and a disc to vanilla chest tables).
- **Decision** (`src/portkit/converters/loot_modifiers.py`, loader-level and namespace-free; runtime `portkit/runtime/block_drops.js` on `block_drops_core.js`):
  1. **Route (pick 1a).** Bedrock has no loot injection and its vanilla glass has no loot table file to override (Mojang/bedrock-samples@46ba6ea9 `behavior_pack/loot_tables/blocks/` holds only concrete/wool slabs and stairs, `red_shrub` and `shelf_mushroom_growth_*`). A listed `neoforge:add_table` whose one condition is `neoforge:loot_table_id` naming `minecraft:blocks/<name>` becomes rows in `scripts/portkit/data/<ns>_block_drops.js`, read by a fixed runtime subscribed to `world.afterEvents.playerBreakBlock` that spawns the added drop at the broken Bedrock vanilla block (id from GeyserMC's item mapping, checked against Bedrock's vanilla item list; every one of the 17 is a Bedrock block id in Mojang/bedrock-samples@46ba6ea9 `metadata/vanilladata_modules/mojang-blocks.json`, e.g. `minecraft:red_stained_glass`). No vanilla file is shipped or overridden, so nothing clashes with other packs.
  2. **What it rolls (pick 2a).** Only tables whose every pool is one roll of one `minecraft:item` entry; entry conditions none, `survives_explosion` (always true for a player's break) or `inverted(match_tool silk_touch >= 1)`; functions `set_count` (constant or integer `uniform`, not `add`), `apply_bonus` Fortune `uniform_bonus_count`, `limit_count`, `explosion_decay` (acts only on explosions). Applied in Java's order, entry functions then pool functions. Not in Creative, not with `doTileDrops` off. Anything else is `loot` residue naming what defeated it. Labelled per table (`approximated loot (#280)`): explosions and other non-player breaks add nothing on Bedrock, so never more than Java. The added item must ship in the pack (or be a Bedrock vanilla item of the same id).
  3. **Other targets (pick 3a).** An addition to a vanilla chest, gameplay or entity table is `loot` residue: carrying it means overriding Bedrock's vanilla table with its pools plus the added one (a vanilla-behaviour change, clashes with other packs, and needs Mojang's EULA-bound table); left for its own decision. Code injections (`ZLootTableLoad`/`LootTableLoadEvent` handlers) are unchanged (no file to claim).
  4. **Unlisted modifiers (pick 4a).** A modifier file the jar's `global_loot_modifiers.json` doesn't list, and the table only it names, are `loot` residue "NeoForge never loads it", not silently dropped, so the reason stays visible.
  6. **Blocks that need the right tool (pick 6a, implemented).** Java generates a block's loot, and so its modifiers, only when the player may harvest it: `ServerPlayerGameMode#destroyBlock` calls `Block#playerDestroy` only when `Player#hasCorrectToolForDrops(state)`, i.e. `!state.requiresCorrectToolForDrops() || tool.isCorrectToolForDrops(state)` (NeoForge's `canHarvestBlock`/`EventHooks#doPlayerHarvestCheck` start from the same check). The runtime can't see Java's tool rules, so a target block that needs the correct tool, or whose flag isn't read, is `loot` residue naming the block and pick 6a (never a drop from a bare hand, more than Java). The flag is read, not tabled (#220, #87): `src/portkit/data/vanilla_block_tools.py` derives `vanilla-block-tools-<version>` from the same sha1-pinned Mojang client.jar + client.txt as `vanilla-blocks-<version>` (#324), at `portkit reference fetch` time, sha256-pinned, never vendored. Each `BlockBehaviour$Properties` method is classified from its own bytecode (sets the flag: `iconst_1; putfield requiresCorrectToolForDrops`; copies it: `getfield`/`putfield` of it, as `ofLegacyCopy`/`ofFullCopy`/1.20 `copy`; anything else touching it is unread), then each `Blocks#<clinit>` registration (and the `Blocks` helpers it calls, e.g. `stainedGlass(DyeColor)`) is read for a call that sets it or a copy of a block already read. A copy of a helper's parameter (`legacyStair(Block)`) or a `Properties` value from elsewhere is unread, so refused. Read for 1.21.1: 1011 blocks (356 need a tool, e.g. stone, ores, obsidian, cobweb, snow), 49 unread (the legacy stairs); glass and all 16 stained glasses read as not needing one, matching minecraft.wiki/w/Glass and minecraft.wiki/w/Stained_Glass ("Tool: Any tool"). The version is the mod's declared Minecraft, else its loader's (Quark declares only NeoForge 21.1, so 1.21.1). Quark: 0 of its 17 targets refused, so its numbers don't move. Rejected 6b (gate the runtime on Bedrock's tool tier as #299 does for mod blocks): a second rule to keep in step with Java for no current target.
  5. **Load conditions.** The modifier's and the added table's own `neoforge:conditions` go through the load-condition gate (`zeta:flag` via PR #338); false or undecided is `conditional_loot_table` residue.
- **Why:** #280 lists the 18 inject tables as unowned; 17 of them are Quark's glass shards, a visible gameplay feature (break glass, get shards to craft back), and the drop is carried exactly for a player's break without touching any vanilla file.
- **Measured** (local, develop 77439c4 -> branch, `portkit convert` of Quark 4.1-487 with Zeta 1.1-40): 17 of 18 inject tables (17 pools) convert into one runtime table (17 vanilla blocks); 1 (sniffer) is `loot` residue "never loads it" with its modifier; unowned files 364 -> 327 (the 18 tables, 18 modifiers and the global list are now claimed), `loot` residue 29 -> 31; 3 files added (`block_drops.js`, `block_drops_core.js`, `data/quark_block_drops.js`) and one `main.js` entry. Other mods ship no loot modifiers and are unchanged.
- **Rejected:** overriding Bedrock's vanilla glass (it has no table file; its drops are built in); overriding vanilla chest/sniffer tables in this slice (pick 3b); giving the drop with Silk Touch or on explosions (more than Java, or a guess at Bedrock's explosion context); a hand table of Quark's injections (#220).
- **Links:** #280, #299 (loot approximations), #338 (zeta:flag), #183 (load conditions).

## 2026-10-20 (approved (Hark, high confidence under Alex's 2026-10-14 campaign order), PR #338): Zeta's `zeta:flag` load condition is decided at the flag's default read from the mod's and Zeta's bytecode (module `@ZetaLoadModule` defaults, `@Config(flag)` field initialisers, `ZGatherAdditionalFlags` handlers), so Quark recipes gated on a flag on by default convert

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order) (#280, PR #338, "Part of #280: Zeta flag conditions from @ZetaLoadModule defaults").
- **Decision** (`src/portkit/adapters/zeta/`, a library adapter; generic class-file reading in `portkit.bytecode`):
  1. **What a flag is, from Zeta 1.1-40's code.** `FlagCondition#test` answers `extraCondition (default true) && ConfigFlagManager#getFlag(flag)`; `putFlag(module, flag, value)` stores `value && module.isEnabled()`. Flags come from each module (`putModuleFlag`: its lowerCaseName, `TentativeModule#from` naming), each `@Config(flag = ...)` boolean field of a module (`ConfigObjectMapper#readInto`: the field's value is the option's default) and each `@LoadEvent` handler of `ZGatherAdditionalFlags` (its `putFlag(this, "<name>", <constant or field>)` calls). Client replacements add none.
  2. **Defaults read, never tabled (#220).** A module is enabled by default when its `enabledByDefault` (the class's `@ZetaLoadModule` element, else the annotation class's AnnotationDefault) is true, its category's option defaults on (read from `ConfigManager`'s option builder), its category's required mod (`new ZetaCategory(name, icon, requiredMod)` in the mod's code) is loaded, and none of its `antiOverlap` mods is loaded. A config field's default is the constant its initialiser stores (`<clinit>` for a static field, the no-argument `<init>` for an instance one), false when it stores none (JVMS 2.3).
  3. **Verdicts, as the cited config flags (2026-10-13).** On by default passes and the conversion note names it ("read from the bytecode of the mod and its library jars"); off by default fails, residue "disabled by default config: zeta:flag/<flag>"; a category whose required mod is absent fails as compat for that mod (as `mod_loaded`). `portkit convert --config zeta.<flag>=true|false` decides the flag both ways (2026-10-13 config overrides); a module flag the user sets also decides the module's other flags (Java's `value && module.isEnabled()`).
  4. **Undecided stays residue ("unknown load condition").** No Zeta library jar or a Zeta whose naming or option builders this reader doesn't know; a flag no module of the jar registers (Java logs "Non-existent flag" and passes it; portkit does not, since the flag may come from code it didn't read); a value that isn't a constant or a field's initial value; a category whose required mod is chosen at run time (Quark's `oddities`: `ODDITIES_ID` is `quarkoddities` or `quark` by `Zeta.isProduction`); an anti-overlap mod that is (or may be) loaded; a flag registered twice with different values; a flag holding `%` (Java throws).
- **Why:** #280: Quark's 1490 recipes all carry `zeta:flag` (vertical_slabs, shingles, ...), so they were residue "unknown load condition" though the modules they test are on in a default Quark install. The defaults are in the bytecode the converter already reads, and the load-condition policy for on/off defaults and user config was settled on 2026-10-13; this applies it to one more condition type without a new rule.
- **Measured** (local, develop 3310ec2 -> branch, `portkit convert` of Quark 4.1-487 with Zeta 1.1-40): recipe residue 1491 -> 371 (1120 recipes convert; behaviour-pack recipe files 30 -> 1155); of the 30 recipes still residue on a load condition, 17 test a flag off or false by default (`neoforge:not` of a flag on by default, `iron_rod_pre_end`, `hammer`), 12 rest on the run-time `oddities` category (backpack, crate, magnets, pipes, tiny potato), 1 is compat for cyclic. The 18 `zeta:flag` loot tables (`loot_table/inject/`) are still unclaimed by any converter, so loot output is unchanged. No other residue source appears; other mods carry no `zeta:flag` and are unchanged.
- **Rejected:** a hand table of Quark flag defaults (#220); passing a flag no module registers because Java does (it may be a flag of code not read); deciding the `oddities` category from the development-or-production switch (a run-time value); treating a loaded anti-overlap mod as disabling the module without reading its "Ignore Anti Overlap" option.
- **Links:** #280, #183/#184 (load conditions), #185/#186 (config overrides), #220, #245 (adapters), #337.

## 2026-10-20 (approved (Alex, 2026-10-20): picks 1a-4a, PR #337): a per-object map in a final instance field, read through an object the reader can't pin, stands for what every object's map of that field holds together, so Quark's 62 own vertical slabs (and thatch_vertical_slab) are read (Quark 699 -> 762/809)

- **Status:** approved (Alex, 2026-10-20): picks 1a-4a (#280, PR #337). The branch implements every "a" below.
- **Decision** (keyed on JVM shapes, never a mod's or library's name; `blockcode.Machine._site_map`, `_site_field`, `_shared_map`, `_site_complete`, `_map_read_only`):
  1. **Allocation-site reading of a per-object map (1a; `_site_map`, `_site_field`).** In the registration runs (not in class initializers, not in the census), a `getfield C.f` on an object the run can't pin (unknown: a library event hands it over, or the reader can't tell which of several objects it is) reads one map per (C, f) shared by every top-level run, when `f` is a final instance field (JVMS 4.5 ACC_FINAL, not ACC_STATIC) of a class of the mod or its libraries and every constructor of C either delegates to another of its own or writes `f` exactly once with `new java/util/LinkedHashMap; dup; invokespecial <init>()V; putfield` (each object holds its own map, empty when built, in insertion order, Java SE 21). The map stands for what the maps of all of C's objects hold together. **What this claims (DEFAULT, labelled here):** an element read from it was surely put into *some* object's map of that field, not necessarily the one the code reads; a block named from it counts only for a name the mod ships a blockstate for (every reading is keyed on the jar's blockstate names, so nothing is named that the mod's data doesn't name). For Quark: `NewStoneTypesModule` and the other modules fill `event.getVariantRegistry().slabs` (`ForgeZRegister` hands over its `Zeta`'s registry), and `VerticalSlabsModule#postRegister` reads `Quark.ZETA.variantRegistry.slabs`; the game holds two `ForgeZeta`, each with its own `VariantRegistry` (#332 pick 5a), and which one an event carries is Zeta's event routing (`ForgeZeta#registerHighest` fires `new ForgeZRegister(this)` on `this.loadBus`; the modules subscribe through `ZetaEventBus#subscribe`, by reflection), which stays unmodelled (#220). 1b keeps today's reading (the slabs stay unread, #332 5a as approved). 1c would model the event bus (subscription by annotation scan and reflective dispatch; not implemented, its own design).
  2. **Two passes, as a shared list (2a; `_shared_map`, `_site_complete`).** First pass: a `put` is kept (a pair whose key isn't known is left out and the map stops being exact; any other change makes it unknown); a read in the mod's own code stops the run, which runs again in the second pass; a read in a dependency jar's code answers unknown, as before this change (a library's code is followed for what it registers, not waited on). Second pass: a read sees the map when every method of the mod and its libraries that loads the field either only reads it there (`_map_read_only`: a `Map` reading call on it, with only constants, local loads, getstatic, getfield, checkcast and calls above it in between) or ran to the end in the first pass; else it answers unknown. A put of a key it already holds to the same value changes nothing; any other second-pass change stops the run. Same assumption as #331 pick 2a: every put comes before any read in the game (registration before post-registration).
  3. **`Iterable#forEach` on a known map view (3a).** `values()` / `keySet()` of a map whose iteration is known now run `forEach(action)` element by element in the map's order (Java SE 21; a change to the map meanwhile fails fast, `HashMap$Values#forEach`); before, it made the map unknown. Iterating a per-class map's view gives the elements surely put, in the order the runs put them.
  4. **What reading more changes (4a).** Newly read blocks are judged by the rules already approved for read blocks (#307 vertical slabs, #321 pick 5a, facing and boxes from bytecode first); nothing new is emitted or refused by a new rule.
- **Why:** #280 / #332 left Quark's 62 own-slab vertical slabs unread: the registry their base slabs go into and the registry `VerticalSlabsModule` reads can't be proven one object, and #332's census can't stand in (two `ForgeZeta`, and every class is open under its pick 4a because Quark and Zeta reflect). Alex's 2026-10-20 order asked the reader to follow the data flow across instances without mod names in core. Reading the field by allocation site follows the data (what `addSlab` puts is what the loop gets) without deciding which object an event carries.
- **Measured** (local, develop 3bd1644 -> branch, blockstates whose registration is read, Quark 4.1-487 with Zeta 1.1-40 and the 1.21.1 vanilla table): Quark 699/809 -> 762/809; vertical slabs 59/122 -> 122/122. The 63 newly read are the 62 vertical slabs of Quark's own slabs (andesite/calcite/diorite/granite/jasper/limestone/myalite/shale/dripstone bricks and polished stones, the 17 shingles, the soul sandstones, raw metal bricks, ancient/azalea/blossom planks, duskbound, midori, iron plates, permafrost, netherrack/blue nether/cobblestone/mossy cobblestone/dirt/blackstone/sandstone/red sandstone bricks) and thatch_vertical_slab, all as `QuarkVerticalSlabBlock`; no block read before changes class or is lost. Converted (local `portkit convert` with Zeta): Quark 2492 files both, every file byte-identical, residue identical (the vertical slab converter takes nothing more from a partial `QuarkVerticalSlabBlock` reading than its DEFAULT gave, as for the 51 read in #324: placement stays the labelled DEFAULT because Quark's `VerticalSlabType` enum names aren't evaluated, and boxes are the turned model's element bounds). 113 of Quark's 122 vertical slabs already convert on develop (block, geometry, loot); the other 9 stay residue for their vanilla texture names (#296 sub-reason 5), unchanged. Other mods: see the PR's runs comment (real-mods include_optional vs coverage-baseline.json, gap-leaderboard board).
- **Rejected:** a Zeta- or Quark-specific adapter naming the registry (a mod name where a JVM shape does it); a hand table of Zeta's event routing (#220); treating the two `ForgeZeta` as one object (they are two objects, #332); reading the union for a field set from a constructor argument, a non-final field or a `HashMap` (another object's map, a later write, or an unknown order).
- **Left:** recipes for vertical slabs stay residue on Zeta's `zeta:flag/vertical_slabs` load condition (a module-enabled flag; its default is the module's `@ZetaLoadModule` annotation, not read yet). The `type=double` state stays set aside (#307 pick 2). Quark's 9 vertical slabs on vanilla textures without a Bedrock name. The same allocation-site reading for lists and sets in instance fields (not needed here).
- **Links:** #280, #277, #332, #331, #324, #307, #220, #87.

## 2026-10-20 (approved (Alex, 2026-10-20): picks 1a-7a): vanilla ButtonBlock converts with a button runtime (press, scheduled release, redstone power, arrows) when its press time and set type are read from code and agree on every way its registration can take; the attach-face/6-way reader with booleans reads off the shared registration run

- **Status:** approved (Alex, 2026-10-20): picks 1a-7a (#280, PR #336). The branch implements every "a" below.
- **Decision** (keyed on vanilla `ButtonBlock`'s and `BlockSetType`'s shapes, never a mod's or library's name; `converters/buttons.py`, `runtime/button.js` + `button_core.js`, `blockcode.read_directional_states(run=)`, `blocks._SharedRun`, `data/block_set_types.py`):
  1. **What a button is.** An attach-face blockstate (`face` + `facing`) drawing exactly one boolean, `powered`, whose registration is followed to vanilla `ButtonBlock` with no mod class in between overriding `blockcode.BUTTON_BEHAVIOUR` (use/useWithoutItem, press, playSound, getSound, onRemove, getSignal, getDirectSignal, isSignalSource, tick, entityInside, checkPressed, updateNeighbours, onExplosionHit, getShape and BlockBehaviour's other hooks). Its placement, shape and textures are the attach-face converter's (#218); `vanilla_parent` stays set and #321 pick 5a still holds for every other vanilla parent.
  2. **What is read** (Mojang's 1.21.1 client jar sha1 30c73b1c through client.txt 2244b6f0, `ButtonBlock` = `dgi`, `BlockSetType` = `dtr`; checked against 1.20.1 jar 0c3ec587 / client.txt 6c48521e, `cpw` / `dcq`; read 2026-10-20). From the vanilla constructor call: 1.21 `ButtonBlock(BlockSetType, int ticksToStayPressed, Properties)`, 1.20 `ButtonBlock(Properties, BlockSetType, int, boolean arrowsCanPress)`; the press time must be an int literal (codec range 1..1024). From the set type: `BUTTON_TYPES` (from `BlockSetType#<clinit>`: IRON, COPPER, GOLD, STONE, POLISHED_BLACKSTONE arrows false with STONE_BUTTON_CLICK_*; CHERRY, CRIMSON, WARPED, BAMBOO arrows true with their family's; the one-argument constructor arrows true with WOODEN_BUTTON_CLICK_*), or a set type built in code read by position (`BUTTON_CTORS`: 1.21 arrows 4th, buttonClickOff/On 13th/14th; 1.20.1 clicks 10th/11th), each argument a literal, a `SoundEvents.<family>_BUTTON_CLICK_*` field or a `Part` of a constant (`canButtonBeActivatedByArrows` joins `canOpenByHand` as a readable boolean component). **Every way must agree:** a registration the reader can't decide builds one object per way; the button converts only when press time, arrows and clicks are the same on all of them, else residue naming the values. No DEFAULT press time or set type (#87).
  3. **Redstone (pick 1a).** `minecraft:redstone_producer` (block format >= 1.21.120 per Microsoft Learn; MCPE-229570 fixed in 1.21.130): power 0 in the base components, power 15 on the powered permutations with `strongly_powered_face` the face touching the block it hangs on (Java `getDirectSignal` into `getConnectedDirection`: floor -> down, ceiling -> up, wall facing north -> south ...), every face connected (Java `getSignal` 15 on every side).
  4. **Press and release (pick 2a).** Java's `ticksToStayPressed` as Bedrock game ticks (both 20 per second): a player's use (custom component `onPlayerInteract`) presses an unpowered button (a powered one does nothing, Java's CONSUME), plays the set type's click on, and `system.runTimeout(ticks)` runs Java's `checkPressed`: released with the click off unless an arrow holds it. A world reload drops the timer; the block's `minecraft:tick` (interval = the press time) releases a powered button with none pending. Clicks: the bedrock-samples `block_sounds` `button.click_on/off` events of the same family (46ba6ea9: wood `random.wood_click` 0.6/0.5, stone `random.stone_click`, cherry/nether/bamboo `click_on./click_off.<family>_button`).
  5. **Arrows (pick 3a).** `world.afterEvents.projectileHitBlock` (stable): an arrow or trident (Java's `AbstractArrow`) hitting an unpowered button whose set type lets arrows press it presses it; at release, one still in the block cell (0.1 margin) keeps it pressed for another press time. Java presses when the arrow enters the button's shape; here on the hit.
  6. **Engine (pick 4a).** Block format 1.21.130 and `@minecraft/server` 2.0.0 (custom components v2, `system.runTimeout`, `projectileHitBlock`, `scriptEventReceive`), the pressure plates' line: no `onRedstoneUpdate`, so the doors' 1.26.40 / 2.5.0 isn't needed.
  7. **A press entry point (pick 5a).** The runtime presses the button at `x y z` on `/scriptevent portkit:button_press <x> <y> <z>`, the same path a use takes: usable by command blocks and functions, and how the in-game check presses a button on a server with no player.
  8. **One registration run (pick 6a).** The attach-face / 6-way reader with booleans ran the registration code on its own names, which misses names a library's material set builds by concatenation (#334 side finding: BetterEnd's wood buttons were "no registration found" there and read as `ButtonBlock` on the shared run). It now reads off the same run over every blockstate as the paired reader (`blocks._SharedRun`, made once). Newly read blocks are judged by the approved rules (#321 pick 5a).
- **Why:** #321 pick 5a / #334 left every vanilla `ButtonBlock` residue (or, unread, a static DEFAULT that never presses) until press, release and power were ported.
- **Measured** (head 3ebdcab; real-mods 39368455342 include_optional, gap-leaderboard 39368229814 gauntlet, ingame 39368227006, ci 39368200436): Buttons that convert: Cluttered (fixtures/ingame, NeoForge 1.21.1) 10 of 10 (`new ButtonBlock(BlockSetType.OAK, 30, ...)`: hand or arrow, 30 ticks, wooden clicks); in game on BDS, both Cluttered runs: button_place, idle, press, press_redstone (lamp lit), hold, release, release_redstone, drop 10/10 each, 0 failed, no content-log errors (all 18 ingame jobs green). Buttons that stay residue, with what was read: BetterEnd 17 of 17 (16 undecided ways, press time 8/20/30), Quark 5 (its ZetaWoodenButtonBlock / MetalButtonBlock override getSound), Biomes O' Plenty 10 (its BlockSetType isn't read). BetterEnd local convert, develop 9a0b859 -> branch: 3474 -> 3414 files, 61 paths differ: its 10 wood buttons and 10 wood barrels (now read on the shared run as vanilla ButtonBlock / BarrelBlock) move from static DEFAULT to residue, each losing block, recipe and geometry (60 files), and `unhandled.json`. Corpus: BetterEnd 39.8% -> 39.0%, files 3469 -> 3409, residue 5258 -> 5338 (rebanked in `fixtures/real/coverage-baseline.json`); the other 12 corpus rows equal their baseline exactly; mct errors 0. Gauntlet board: every mod's coverage equals the banked baseline, done 37/50, mean 10.36%.
- **Rejected:** a DEFAULT press time by set type (20 stone / 30 wood) when unread or disagreeing (#87); a hand table of BetterEnd's or WorldWeaver's buttons (#220); script-only power (scripts can't emit a redstone signal); a hidden redstone block; polling on `minecraft:tick` every few ticks (the press is an event; only the reload safety net ticks).
- **Left:** explosions pressing a button (1.21 `onExplosionHit`); Java's support rule (a button pops when its block goes); game events; BetterEnd's 17 buttons (residue: WorldWeaver's `Button` picks 8, 20 or 30 ticks by `hasTrait(STONE_BLOCK / WOOD_BLOCK)`, which the reader can't decide); a reader model of WorldWeaver-style trait lists would let them convert.
- **Links:** #280, #277, #219, #296, #313, #314, #321, #322, #328, #333, #334, #220, #87.

## 2026-10-19 (approved (Hark, high confidence under Alex's 2026-10-14 campaign order)): a door's or trapdoor's BlockSetType built in code is read from its constructor arguments, and paired blocks are read on one registration run over every blockstate, so BetterEnd's metal doors and trapdoors convert; PALE_OAK joins the set type tables

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order) (#280, PR #334). No new emit or refuse rule: the doors and trapdoors are judged by #296's approved rules (doors pick 6a, trapdoors pick 7a: a set type that a hand can't open opens only by redstone) with the values read here.
- **Decision** (keyed on vanilla `BlockSetType`'s shape, never a mod's or library's name; `doors._set_type_door`, `blockcode.Part`, `blocks._read_paired`, `data/block_set_types.py`):
  1. **A door's or trapdoor's set type built in code (`doors._set_type_door`).** As #333 does for plates: a door or trapdoor whose `BlockSetType` is `new BlockSetType(...)` reads whether a hand opens it and its sounds from the constructor's arguments, by position in the canonical constructor (`DOOR_CTORS`: 1.21.1/1.21.4/1.21.8 canOpenByHand 2nd, doorClose/doorOpen 7th/8th, trapdoorClose/trapdoorOpen 9th/10th; 1.20.1 canOpenByHand 2nd, the four sounds 4th-7th; client.txt 1.21.1, 1.21.8, 1.20.1 as #333 cites). canOpenByHand must be a literal 0/1 or `BlockSetType.<constant>.canOpenByHand()`; each sound a vanilla `SoundEvents.<family>_DOOR_CLOSE/_OPEN` (`_TRAPDOOR_CLOSE/_OPEN` for a trapdoor) of a family in `SOUNDS` / `TRAPDOOR_SOUNDS` (all twelve fields in 1.21.8 client.txt `SoundEvents`) or that component of a constant in `DOOR_TYPES`; both sounds one family. The one-argument constructor is a hand-opened wooden door (`ONE_ARG_DOOR`, its 1.21.1/1.21.8 bytecode). Anything else keeps #322 pick 7 (wooden DEFAULT only if the jar's wooden tag lists it, else residue).
  2. **`canOpenByHand()` on a vanilla constant is a `Part`.** #333 left boolean components unknown; `BlockSetTypeBuilder.copyOf` copies `canOpenByHand`, so it reads as which constant's component. A boolean `Part` decides no branch and is no number (`_branch` and `_arith` take it as unknown, as before); `canOpenByWindCharge`, `canButtonBeActivatedByArrows` and `name()` stay unknown.
  3. **One registration run for paired blocks.** `_read_paired` ran the registration code once per kind on that kind's names alone. WorldWeaver's material sets build `terminite_door` and the wood doors by concatenation that a doors-only run never reaches (their door names were "no registration found", the wood doors took the tag DEFAULT and the 2 metal doors and 2 metal trapdoors were residue), while the plates' run happened to reach them. It now runs once on every blockstate of the mod, as the other block readers do, and reads doors, trapdoors, two-tall blocks and plates off that run (`doors.read_code(..., run=)`).
  4. **`PALE_OAK`** (1.21.4+) is `register(new BlockSetType("pale_oak"))`, the one-argument constructor, in Mojang's 1.21.4 (client jar sha1 a7e5a602, client.txt 0cf2a0b7) and 1.21.8 (a19d9bad, bdeb624c) `BlockSetType#<clinit>`, read 2026-10-19: hand-opened wooden door and trapdoor, everything presses the plate, wooden clicks, in `DOOR_TYPES` and `PLATE_TYPES`.
- **Why:** #333 left BetterEnd's doors and trapdoors on the wooden DEFAULT through the jar's tags and its 2 metal doors and 2 metal trapdoors as residue, though the same Fabric API set types it read for the plates say what they are.
- **Measured:** local, develop 5960230 -> branch, each jar with its pinned libraries and mappings. BetterEnd 21.800.2: blockstates whose registration is read 654/722 unchanged (the general reader); paired readings: the 12 doors and 12 trapdoors now read from code (before: none, "no registration found"): the 10 wood sets' copy `BlockSetType.OAK` (hand, wooden sounds, the values of the wooden DEFAULT they converted with through the jar's tags), terminite and thallasium copy `BlockSetType.IRON` (redstone only, iron door and iron trapdoor sounds); the 19 plates read as in #333. Converted: 3464 -> 3474 files, 19 paths differ: terminite and thallasium door and trapdoor each gain block and geometry (8 files), the 2 trapdoors gain their recipe and the 2 doors their loot table (4), the 2 doors' item files go (2: a converted door's item is its block's), the 2 trapdoor loot tables gain the iron-tier pickaxe `match_tool` gate a converted block's table carries, `betterend_doors.js` and `betterend_trapdoors.js` gain the 4 rows (`hand: false`, iron sounds), `unhandled.json` loses the 4 blocks, 2 recipes and 2 loot tables and moves the roll-ups (models owned by residue 820 -> 800, unowned 217 -> 215). Corpus (`portkit eval --corpus --fixture betterend`): 39.5% -> 39.8%, files 3459 -> 3469, residue 5288 -> 5258; rebanked in `fixtures/real/coverage-baseline.json`. Byte-identical (whole tree, develop vs branch): corpus Farmer's Delight (NeoForge, Fabric), Supplementaries, Waystones, Mythic Metals, Silent Gear, Storage Drawers (1.19.2, 1.12.2), Alex's Mobs, Mekanism, Create, Tinkers; gauntlet Quark (with Zeta; its new BlockSetType(String) doors and trapdoors now read from code, the wooden values they had), Biomes O' Plenty, Immersive Engineering, Botania, Tinkers. The other 43 gauntlet jars have no door, trapdoor, two-tall or plate blockstate (scanned; Twilight Forest and Chisel are CurseForge-only and weren't fetched), so nothing here reaches them.
- **Not done (buttons):** BetterEnd's 7 stone buttons read their set type soundly (`ButtonBlock(BlockSetType, int ticksToStayPressed, Properties)` with the copied STONE set type and a literal press time) but stay residue: #219 / #321 pick 5a keep a block read as vanilla `ButtonBlock` residue because its press and scheduled release are vanilla code that isn't ported, and porting them (a button runtime, a redstone source on Bedrock, the press time) is its own design. Reading the set type changes nothing until then.
- **Rejected:** a hand table of BetterEnd's or WorldWeaver's set types (#220); reading the doors with the plates' names added to their run (it happens to reach the material sets in BetterEnd and wouldn't in a mod without plates); a run per kind on every blockstate (four runs where one serves); converting the stone buttons as the static DEFAULT they had before #328 (pick 5a).
- **Left:** a button converter (press, scheduled release, redstone power, `canButtonBeActivatedByArrows`, the button clicks and press time read here); BetterEnd's 10 wood buttons still convert as the static DEFAULT; a run on every blockstate reads them as vanilla `ButtonBlock` (which pick 5a makes residue), so the attach-face reader's own run apparently doesn't reach the wood set (side finding, not changed here).
- **Links:** #280, #277, #296, #313, #314, #321, #322, #328, #333, #220, #87.

## 2026-10-19 (approved (Hark, high confidence under Alex's 2026-10-14 campaign order)): a plate's BlockSetType built in code is read from its constructor arguments, and Fabric API is pinned for BetterEnd, so BetterEnd's 9 stone and metal pressure plates convert

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order) (#280, PR #333). No new emit or refuse rule: the plates are judged by #296's approved rules (picks 3a, 6a) with the values read here.
- **Decision** (keyed on vanilla `BlockSetType`'s shape, never a mod's or library's name; `blockcode.Part`, `Machine.vanilla`, `doors._set_type_plate`, `data/block_set_types.py`):
  1. **`BlockSetType.register` returns its argument.** It files the set type under its name and returns it: `aload_0; areturn` in Mojang's 1.20.1 (sha1 0c3ec587), 1.21.1 (30c73b1c) and 1.21.8 (a19d9bad) client jars, read through client.txt. It was an unknown call before, so any set type a mod or library registered was unknown.
  2. **A vanilla constant's set type components are `Part(constant, component)`.** A record accessor called on a vanilla `BlockSetType` constant (`BlockSetType.STONE.pressurePlateSensitivity()`, the sound accessors, `soundType()`) reads as which constant's which component; its value isn't modelled in the reader. Boolean components and `name()` stay unknown. This is what Fabric API's `BlockSetTypeBuilder.copyOf(BlockSetType)` copies (fabric-object-builder-api-v1 21.1.10, in Fabric API 0.136.1+1.21.8).
  3. **A set type built in code (`doors._set_type_plate`).** A plate whose set type is `new BlockSetType(...)` reads what presses it and its clicks from the constructor's arguments, by position in the canonical constructor (record components in declaration order, client.txt 1.21.1/1.21.8: sensitivity 5th, `pressurePlateClickOff`/`On` 11th/12th; 1.20.1: no sensitivity, clicks 8th/9th, the sensitivity from the plate's own `PressurePlateBlock$Sensitivity`). Each argument must be a vanilla constant (`PressurePlateSensitivity.MOBS`, `SoundEvents.<family>_PRESSURE_PLATE_CLICK_OFF/_ON` for a family of `PLATE_SOUNDS`) or a `Part` of a constant in `PLATE_TYPES`; both clicks must be one family. The one-argument constructor `BlockSetType(String)` is EVERYTHING with the wooden clicks (its 1.21.1 and 1.21.8 bytecode). Anything else stays "a BlockSetType that isn't a vanilla constant read here" (#322 pick 7: wooden DEFAULT only if the jar's wooden tag lists it, else residue).
  4. **Fabric API pinned for BetterEnd** (`fixtures/real/libraries.toml`, #321 pick 2a: the newest Modrinth release on the mod's loader and game version inside its declared range, pinned because it changes what the readers find): 0.136.1+1.21.8 (Modrinth version g58ofrov, Apache-2.0, sha512-checked, fetched like the other pins and never committed). BetterEnd asks `fabric-api >=0.100.0`. Its 43 module jars are nested under `META-INF/jars/` and read with it (#321's one-level nesting). WorldWeaver's `BlockSet`, `MetalBlockSet` and `WoodenBlockSet#createSetType` build each set's type as `BlockSetTypeBuilder.copyOf(BlockSetType.STONE / IRON / OAK)[.soundGroup(..)].register(id)`.
- **Why:** #328 read BetterEnd's 9 stone and metal plates as vanilla `PressurePlateBlock`, but their `BlockSetType` came from Fabric API's builder, which wasn't pinned, so what presses them wasn't known and they stayed residue (#322 pick 7).
- **Measured** (local, develop 37ebfdc with BetterEnd's 3 pins -> branch with 4): BetterEnd 21.800.2 blockstates read 654 -> 654/722, every per-blockstate reading identical. All 19 BetterEnd plates read their set type: the 7 stone sets' plates (azure_jadestone, flavolite, sandy_jadestone, sulphuric_rock, umbralith, violecite, virid_jadestone) MOBS with stone clicks (`BlockSetType.STONE`'s), terminite and thallasium EVERYTHING with metal clicks (`BlockSetType.IRON`'s), the 10 wood plates EVERYTHING with wooden clicks (`BlockSetType.OAK`'s; before, the labelled wooden DEFAULT through the jar's tag, the same values). Converted: BetterEnd 3437 -> 3464 files, 31 differ: the 9 plates each gain block, recipe and geometry (27 files); `betterend_pressure_plates.js` gains their 9 rows; terminite and thallasium plate loot tables gain the iron-tier pickaxe `match_tool` gate a converted block's table carries (`converters/loot.py`); `unhandled.json` loses the 9 plates and their 9 recipes. Corpus (`portkit eval --corpus --fixture betterend`, local): BetterEnd 39.2% -> 39.5%, files 3432 -> 3459, residue 5324 -> 5288; rebanked in `fixtures/real/coverage-baseline.json`. Unchanged, block for block (same per-blockstate reading) and byte-identical (local `portkit convert`, develop vs branch): Quark 699/809 (its ancient, azalea and blossom plates now read `new BlockSetType(String)`, EVERYTHING with wooden clicks, the values of the wooden DEFAULT they converted with; obsidian stays its own class), Waystones (Fabric, NeoForge) 44/44, Farmer's Delight (Fabric 0/133, NeoForge 132/132), Mythic Metals 0/119, BOP 229/345, Comforts 33/33, Iron Chests 14/14, Cooking for Blockheads 140/140, Storage Drawers (1.12.2 0/6, 1.19.2 69/70, NeoForge 143/144), Silent Gear 0/59, Alex's Mobs 4/37, AE2 102/102, Immersive Engineering 175/390, Botania 174/678, Mekanism 147/201, Supplementaries 7/234. The pin is read only for BetterEnd (`for = ["betterend"]`), so no other Fabric mod is converted with Fabric API. Create and Tinkers were not converted locally; CI covers them (see the PR's runs comment).
- **Rejected:** a hand table of BetterEnd's or WorldWeaver's set types (#220); special-casing Fabric API's builder class (a library name in core: the builder is followed as code); modelling every vanilla constant's record components in the reader (the converter resolves the plate's three from `PLATE_TYPES`, the table #296 read from the client jar); vendoring Fabric API.
- **Left:** BetterEnd's doors and trapdoors built with the same set types still take the wooden DEFAULT through the jar's tags (their reading only looks at vanilla constants; a later slice can read them the same way); `PALE_OAK` (1.21.4+) isn't in `PLATE_TYPES`; buttons don't read their set type yet.
- **Links:** #280, #277, #296, #321, #322, #328, #220, #87.

## 2026-10-19 (approved (Alex, 2026-10-19): picks 1a–5a): the loader's entry classes are part of the closed world, and a class the closed world provably makes exactly one object of stands in for an unknown call result of that class; Quark's own vertical slabs stay residue (its two variant registries are separate objects)

- **Status:** approved (Alex, 2026-10-19): picks 1a–5a (#280, PR #332). The branch implements every "a" below.
- **Decision** (keyed on loader metadata and JVM shapes, never a mod's or library's name; `portkit.entrypoints`, `blockcode._census`, `Machine.closed_why`, `Machine.sole_instance`):
  1. **Entry classes (1a; `entrypoints.entry_classes`, `_census`).** Every loader constructs each entry class it declares itself: NeoForge/Forge construct each `@Mod` class whose value is a mod id of the jar's `[[mods]]` (`META-INF/neoforge.mods.toml` / `META-INF/mods.toml`, language loader `javafml`) once (NeoForge docs "Mod Files / javafml and @Mod", https://docs.neoforged.net/docs/gettingstarted/modfiles#javafml-and-mod; FancyModLoader df8b0a5 `FMLModContainer#constructMod`, one `constructor.newInstance` per entry class; MinecraftForge 1.20.1 `FMLModContainer#constructMod`, one `modInstance`). Fabric makes "a new instance of the class" per class (or instance-method) reference, memoized per entrypoint name and type, `main` on both sides, `client`/`server` on one side, other names on request (Fabric wiki "Entrypoints", https://wiki.fabricmc.net/documentation:entrypoint). Quilt's `init` (same JVM notation, Quilt RFC 0002) is taken as Fabric's `main` (DEFAULT). The mod's and each library jar's metadata (and their `META-INF/jars/` jars') are read. Each entry class constructed exactly once on every side (an `@Mod` with no `dist`, or a single `main`/`init` reference) has its class initialized and its one public constructor (Fabric/Quilt: the public no-argument one) run once on a new object of exactly its class with unknown arguments, after the wanted classes' initializers and before the registration runs; what it writes stays (statics, registrations); a list other runs add to (#331 pick 2a) is used as in the first registration pass (appends kept, a read stops the run and makes what it appended unknown). A constructor that stops part way puts the statics back. An entry class constructed on one side only or on request isn't run. 1b runs none of them (the census below only counts class initializers). 1c treats Quilt `init` as on request.
  2. **One object stands in (2a; `closed_why`, `sole_instance`, the fallback of `Machine.call`).** The census is every object `new` made while the class initializers and entry constructors above ran. The objects of class C (and its subclasses and implementors) are all the program ever makes when every `new` of them in the mod and its libraries sits in a class initializer the census ran whole (JVMS 5.5: once), in a census-completed entry class's constructor (rule 1), or in a constructor of a class itself closed this way (an `<init>` runs only on an object `new` just made of that class or a subclass, JVMS 2.9.1 / 6.5, so it ran, for each such object, in the census); a `new` anywhere else (a method the game may call any number of times), a constructor reference (`C::new`), an entry class that wasn't run, or a Cloneable class leaves C open. When C is closed and the census holds exactly one object of it, an unknown result of a call declared to return C, in the registration runs, is that object (the same object the static field holding it gives). Two or more objects, or an open C, leave the result unknown, as today. 2b keeps every such result unknown (the census only reported).
  3. **Not null (3a, DEFAULT).** The stand-in is the object; a call declared to return C may return null instead, which the code dereferencing it would throw on. 3b doesn't stand in at all unless the call can be shown not to return null (no such proof is implemented; equivalent to 2b today).
  4. **Reflection (4a).** Any method of the mod or its libraries that calls an API making an object of a class it is handed (`Class#newInstance`, `Constructor#newInstance`, `Unsafe#allocateInstance`, `MethodHandles.Lookup#findConstructor`, `ObjectInputStream#readObject`/`readUnshared`, `ServiceLoader`) leaves every class open: such a call may make an object of any class. 4b would look at what class each such call is handed (not implemented; would need its own measurement).
  5. **Quark's vertical slabs (5a).** They stay residue, as the reader shows: Zeta's variant registry is built in `Zeta`'s constructor (offset 17, before any branch), and `ForgeZeta` is made unconditionally in two places the census runs, `Quark`'s class initializer (offset 8) and `ZetaModForge`'s constructor (offset 1, `@Mod("zeta")`, run as an entry class under 1a), so the game holds at least two separate variant registries and which one a module's `ZRegister` event carries is only Zeta's event routing (not modelled, #220). The census counts 2 `ForgeZeta` objects; `VariantRegistry` is also open under 4a (6 reflective methods in Quark and Zeta: emote instantiation, `Zeta#createProxy`, `ConfigObjectMapper#restrict`, `ZetaModuleManager#construct`, two `ForgeEventsRemapper` wrapper lambdas) and because `Quark`'s class initializer stops at the one branch it has (`ZETA.isProduction`, "writes to memory after a branch it can't decide"), so neither registry stands in. 5b keeps the slabs on #280 for a later, generic reading of the event object (a `ForgeZRegister` is made with `this` in a method reached only through a method reference bound in `start()`), with no change now.
- **Why:** #331 left Quark's 62 own-slab vertical slabs unread because `ZetaModForge`, which the loader constructs by reflection, builds a second `ForgeZeta`, so the reader couldn't tell whether the variant registry map is one object. Alex (2026-10-19) chose to treat loader-created entry classes as part of the closed world and let the reader decide, not to model Zeta's event routing (#220).
- **Measured** (local, develop 7bb31d2 -> branch, blockstates whose registration is read): Quark 699/809 -> 699/809, every per-name reading identical; 0 of the 62 vertical slabs convert. Census for Quark + Zeta 1.1-40: entry classes `Quark` (once; its constructor stops part way, "writes to memory after a branch it can't decide", statics put back) and `ZetaModForge` (once; completed). Other mods: see the PR's runs comment (real-mods, gap-leaderboard).
- **Rejected:** a hand table of a library's event routing (#220); treating an entry class's constructor as running any number of times (leaves every class it makes open, the state today); running one-side or on-request entry classes (whether they run isn't known); counting objects by allocation site without the census (a site in a loop or a method the game calls many times makes many).
- **Left:** Quark's 62 own vertical slabs (+ thatch_vertical_slab): residue under 5a. A reflective-instantiation reading by class operand (4b). Objects counted twice when a constructor forks before a `new` (the census counts each way's object; conservative).
- **Links:** #280, #277, #220, #87, #331.

## 2026-10-19 (approved (Alex, 2026-10-19): picks 1a–3a): a block constructor that names its own block stands in for its registration, and a static final list its class initializer builds is shared across top-level runs in two passes (Quark 686 -> 699/809)

- **Status:** approved (Alex, 2026-10-19): picks 1a–3a (#280, PR #331). The branch implements every "a" below.
- **Decision** (keyed on JVM shapes, never a mod's or library's name; `blockcode.Machine`, `_constructed`, `_run_method`, `_run_pass`):
  1. **Own-name constructors (1a; `_constructed`, `Machine.has_subclass`).** A block constructor that loads its own whole name (`super("sturdy_stone", module, ..)`), run on its own, gets a fresh object of exactly its class, but only when the class is concrete, nothing in the jar or its libraries extends it (JVMS: `<init>` runs only on an object `new` made of that class or a subclass), and no other run registers the name. A module run that calls such a constructor is run too (thatch, then its slab and stairs). 1b leaves these blocks unread.
  2. **Two-pass shared lists (2a; `_mark_shared`, `_shared_list`, `_escape_shared`, `_shared_complete`, `_reads_only`).** A list a static final field holds after its class initializer built it is shared across top-level runs. Pass 1 keeps every append and queues a run that reads the list. Pass 2 reruns the queued readers, which see the full list only when every method that loads the field only reads it or ran to the end, and the list wasn't stored anywhere else; otherwise the list is unknown. This assumes every add happens before any read in the game (mod construction before registration). Class initializers use such a list as before: without that rule AE2 fell from 102 to 1. 2b keeps today's order-dependent behaviour (a later run iterates the list with only the elements of the runs that happened to run first); 2c never reads a list another run fills.
  3. **Newly read blocks (3a).** Judged by the rules already approved for read blocks; no new emit or refuse rule. Under #321 pick 5a, iron_rod moves from DEFAULT to residue (`IronRodBlock` extends vanilla `EndRodBlock`). 3b keeps its DEFAULT conversion.
- **Why:** Quark's 123 unread blockstates included blocks whose only registration is their own constructor naming them (sturdy_stone, iron_rod, grate, cut_vine, matrix_enchanter, thatch and its slab and stairs), and blocks added to a module's static list in one run and registered from it in another (the 5 blossom hedges).
- **Measured** (blockstates whose registration is read, local, develop db94984 -> branch): Quark 686 -> 699/809. The 13 newly read: 5 blossom hedges, thatch, thatch_slab, thatch_stairs, sturdy_stone, iron_rod, grate, cut_vine, matrix_enchanter. Quark converted output 2494 -> 2492 files, 4 differ: iron_rod's block and geo files removed; its loot table loses the pickaxe/stone-tier `match_tool` gate (an unconverted block gets a standalone ungated table, `converters/loot.py`); `unhandled.json` gains iron_rod. Roll-ups: tag_unread 21 -> 20, owned_by_residue models 312 -> 314, all-residue tags 6 -> 7 (breaks_toretoise_ore). Byte-identical: BetterEnd, Comforts, Iron Chests, Cooking for Blockheads, Waystones, Storage Drawers, Farmer's Delight, Silent Gear, Mythic Metals, Alex's Mobs. Gauntlet (gap-leaderboard 39292888468): only Quark moves, 2489 -> 2487 files, 5167 -> 5170 residue, 32.51 -> 32.48%; board done 37/50, mean 10.36%; baseline rebanked.
- **Rejected:** 1b and 2c (leave blocks unread); 2b (a reader's view depends on run order); sharing class-initializer reads of the list (AE2 102 -> 1); a constructor's run for a subclassable or abstract class (the object may be a subclass); special-casing Zeta's or Quark's classes (a mod name in core).
- **Left:** 62 vertical slabs of Quark's own slabs (+ thatch_vertical_slab): Zeta's `variantRegistry` can't be proven one object, since `ZetaModForge` is created by reflection by the loader and builds a second `ForgeZeta`. Follow-up question: model a library's event routing, or treat loader-created classes as part of the closed world. 34 Lootr chests (registered only when Lootr is installed). 12 tuff/crafter assets no class names.
- **Links:** #280, #277, #321, #327, #328, #329, #330.

## 2026-10-19 (approved (Alex, 2026-10-19): picks 1a–4a): unmodifiable `Map.of`/`Map.ofEntries` maps, `Object#getClass` of a built object, per-way iterator copies and a 2,000,000-step run, so BetterEnd's planks, bookshelves and signs are read (BetterEnd 613 -> 654/722)

- **Status:** approved (Alex, 2026-10-19): picks 1a–4a (#280, PR #330). The branch implements every "a" below.
- **Decision** (keyed on JVM shapes, never a mod's or library's name; `blockcode.Machine`):
  1. **Fixed maps (1a; `_fixed_map`, `_MAP_CHANGES`).** `Map.entry(k, v)`, `Map.ofEntries(..)`, `Map.of(..)` and Guava `ImmutableMap.of(..)` build an exact unmodifiable map (Java SE 21, Guava 33): keys compare as `_map_key` compares them (a record by its components), a null key or value throws `NullPointerException`, a duplicate key throws `IllegalArgumentException`, any change (`put`, `remove`, `clear`, `compute*`, `merge`, `replace*` ...) throws `UnsupportedOperationException`. Its order isn't modelled (`Map.of`'s is unspecified), so it is never iterated; only looked up. 1b leaves these maps unknown: the 41 blocks below stay unread (BetterEnd 613/722).
  2. **`getClass` (2a; `Machine.vanilla`).** `Object#getClass()` (final) reads as the class only for an object the run built with `new` of a class in the jar or its libraries, fully initialised; anything else is unknown. 2b keeps it unknown: a javac-style `equals` that compares `getClass()` (WorldWeaver's `BlockTraitKey`) can't decide, and 21 wall signs read today are lost.
  3. **Per-way iterators (3a; `_own_iterators`, `IterV.home`, `IterV.escaped`).** At a branch the run can't decide, each way gets its own copy of an iterator that the frame's own `iterator()`/`listIterator()` call returned and that hasn't escaped (stored in a field, static or array, passed to any call but its own `hasNext`/`next`/`remove`, captured by a lambda, or returned). In the game each way is its own run, so its position is its own. 3b keeps one iterator shared across ways: one way's `next()` advances the other's loop, and the same 21 wall signs are lost.
  4. **Step budget (4a; `_MAX_STEPS`).** 2,000,000 steps per top-level run, up from 1,000,000 (#328 pick 2a). `EndWoodBlocks`, with its planks, bookshelves and signs followed, needs about 934k on top of the 159k its caller used (about 1.09M in one nested pass). 4b keeps 1M: `lucernia_gate` moves from residue back to DEFAULT.
  5. **Newly read blocks.** Judged by the rules already approved for read blocks; no new emit or refuse rule, and no DEFAULT -> residue moves: converted output is byte-identical.
- **Why:** WorldWeaver's `WoodenBlockSet.FUEL_TICKS = Map.ofEntries(Map.entry(..), ..)` wasn't modelled, so a block's fuel trait was unknown and `BlockDefinition#build` forked past 16 paths. Past that, `BlockTraitKey#equals` compares `getClass()`, and a loop's iterator was shared between the ways of a fork, so the wall signs were lost.
- **Measured** (blockstates whose registration is read, local, develop e9e0dd0 -> branch): BetterEnd 613 -> 654/722. The 41 newly read are the blocks the #329 entry left unread through `defineDefaultBlock(name)`: the 10 wood sets' planks, bookshelves, signs and hanging signs, and lucernia_jellyshroom_hanging_sign. BetterEnd converted output byte-identical (3437 files). Byte-identical with unchanged per-name readings: Quark, Comforts, Iron Chests, Cooking for Blockheads, Waystones, Storage Drawers (all three), Farmer's Delight (both), Silent Gear, Mythic Metals, Alex's Mobs. AE2 readings unchanged (not converted locally). Immersive Engineering, BOP, Botania, Mekanism, Supplementaries, Create and Tinkers were not measured locally; CI covers them: gap-leaderboard 39272842752 (gauntlet, 015a1f0) shows AE2, IE, BOP, Botania and Tinkers with coverage, files and residue equal to `gauntlet-baseline.json` (no mod changed; done 37/50, mean 10.36%); real-mods (include_optional) checks Create, Supplementaries, Mekanism and Tinkers against `coverage-baseline.json` (see PR #330 for the run). ingame 39272838193 succeeded on 015a1f0. Local gates on the branch: pytest 2917 passed / 31 skipped, `portkit eval` 21/21, node 238/238.
- **Rejected:** 1b, 2b, 3b (each leaves blocks unread or loses read ones); iterating a fixed map (`Map.of` order is unspecified); `getClass` of any object (one the run didn't build may be a subclass); copying an escaped iterator (another holder sees one object); 4b (`lucernia_gate` back to DEFAULT); special-casing WorldWeaver's classes (a mod name in core).
- **Left:** hydralux petal blocks and bulb lanterns (Guava `Maps.newLinkedHashMap()` filled from `DyeColor.values()`), custom chorus flower and plant, ivis vine; anvils and alloying blocks (residue by Alex's call); the plates' `BlockSetType` (Fabric API, not pinned).
- **Links:** #280, #277, #321, #322, #327, #328, #329, #87.

## 2026-10-19 (approved (Alex, 2026-10-19): picks 1a–2a): a record map key keeps comparing by its components after a call the machine can't follow, so BetterEnd's other 9 WorldWeaver wood sets are read (BetterEnd 393 -> 613/722)

- **Status:** approved (Alex, 2026-10-19): picks 1a–2a (#280, PR #329). The branch implements every "a" in the PR's picks comment.
- **Decision** (keyed on JVM shapes, never a mod's or library's name; `blockcode.Machine._map_key`):
  1. **Record keys after havoc (1a).** #328 pick 3a lets a record key a `LinkedHashMap` by its components only on an object whose unwritten fields still read as defaults (`_defaults`), which a call the machine can't follow clears (#327 pick 4a havoc). A record's key now holds after such a call too: a record's only instance fields are its components, each `private final` (JLS 8.10.3), and nothing can write them later, reflection included (`Field#set` refuses a final field of a record class, Java SE 21), so havoc already keeps them (it keeps final fields) and they are what `Record#equals` compares. The record's constructor must still have been followed to the end (not `__partial`, not uninitialised) and have stored every component; a class with its own `equals` is unchanged (identity only). 1b keeps #328's test; BetterEnd stays at 393/722.
  2. **Newly read blocks (2a).** They are judged by the rules already approved for read blocks (#320 plates, #296 doors and trapdoors, #307, #321 pick 5a, #328 pick 4a); no new emit or refuse rule. Under #321 pick 5a, 9 blocks move from DEFAULT to residue: the 9 wood fence gates (dragon_tree, end_lotus, helix_tree, jellyshroom, lacugrove, lucernia, pythadendron, tenanea, umbrella_tree `_gate`; vanilla `FenceGateBlock`), exactly as mossy_glowshroom_gate did under #328 pick 4a. 2b keeps their DEFAULT conversion.
- **Why:** `EndWoodBlocks.<clinit>` builds 10 `EndWoodenComplexMaterial` sets. Each set's `createDefaultDefinitions` fills its `SlotMap` from the shared `WoodSlots.*` statics, keyed by their `SlotType` records. The first set (mossy glowshroom) hands those slots to library calls the machine can't follow (`BlockDefinition#build` forks on the unknown size of its `propertySetters` list once a trait argument is unknown), and havoc cleared each shared record's `_defaults`. So from the second set on, `SlotMap.add` made its map inexact, `BlockSet#buildAndRegister` couldn't iterate it and registered nothing. The record's components were never touched (they are final).
- **Measured** (blockstates whose registration is read, local, develop d16d893 -> branch, each jar with its mapping table, pinned libraries and vanilla block table): BetterEnd 21.800.2 393 -> 613/722, none lost, none reread as a different class. The 220 newly read are the 9 wood sets' bark, logs and stripped variants (36 `RotatedPillarBlock`), barrels, buttons, chests, chiseled bookshelves, composters, crafting tables, doors, fences, gates, ladders, pressure plates, slabs, stairs, trapdoors, walls, wall signs (9 each), wall hanging signs, bar stools, chairs and taburets (10 each, with lucernia's jellyshroom furniture). Unchanged, block for block (same per-blockstate reading): Quark 686/809, Comforts 33/33, Iron Chests 14/14, Cooking for Blockheads 140/140, Waystones (Fabric, NeoForge) 44/44, Storage Drawers (1.12.2 0/6, 1.19.2 69/70, NeoForge 143/144), Farmer's Delight (NeoForge 132/132, Fabric 0/133), Silent Gear 0/59, Mythic Metals 0/119, Alex's Mobs 4/37, AE2 102/102, Immersive Engineering 175/390, BOP 229/345, Botania 174/678, Mekanism 99/201, Supplementaries 7/234, Create 319/643, Tinkers (3.12.1.231 and 3.11.2.166) 0/435. Converted (local `portkit convert`, develop vs branch): BetterEnd 3464 -> 3437 files, 28 differ: the 9 gates each lose block, recipe and geometry (27 files), and `unhandled.json` gains their 9 block entries and 9 recipe entries and moves the roll-ups (models owned by residue 802 -> 829, unowned models 217 -> 226, `fence_gates` joins the all-residue block and item tags). The other 211 newly read blocks convert byte-identically: they were already residue for reasons the reading doesn't touch (state-driven or multipart blockstates, `bclib:block/*` parents, quadless sign models; the 9 plates stay residue under #322 pick 7, their `BlockSetType` coming from the unpinned Fabric API) or convert as their DEFAULT did. Byte-identical: Quark, Comforts, Iron Chests, Cooking for Blockheads, Waystones (both), Storage Drawers (all three), Farmer's Delight (both), Silent Gear, Mythic Metals, Alex's Mobs, AE2, Immersive Engineering, BOP, Botania, Supplementaries, Mekanism. Create and Tinkers were not converted locally (sandbox time limit); CI covers them: on head c0cebdb, ci 39254234106 and real-mods 39254240200 (include_optional; corpus coverage equal to `coverage-baseline.json` with BetterEnd rebanked, corpus tests passed) succeeded; ingame 39253392547 (18 pack jobs, BetterEnd, Create and both Tinkers included, no content-log errors) and gap-leaderboard 39253395509 (gauntlet board) succeeded on 1c0b151, whose code is head's (head only rebanks the baseline). Local gates: pytest 2901 passed / 29 skipped, `portkit eval` 21/21, node 238/238. Corpus (`portkit eval --corpus --fixture betterend`, local): BetterEnd 39.6% -> 39.2%, files 3459 -> 3432, residue 5270 -> 5324; rebanked in `fixtures/real/coverage-baseline.json` in this PR.
- **Rejected:** 1b (leaves 9 of BetterEnd's 10 wood sets unread); keeping a havocked object's defaults in general (a non-final field may have been written by the code that wasn't followed); special-casing WorldWeaver's slot statics (a mod name in core).
- **Left:** BetterEnd's planks, bookshelves, signs and hanging signs of all 10 wood sets and lucernia_jellyshroom_hanging_sign (41; their slots build through `defineDefaultBlock(name)` with no factory handed over, so only `BlockDefinition#build`, which forks on its unknown `propertySetters` list, would show the block); hydralux petal blocks and the 64 bulb lanterns (`ColoredMaterial` iterates a Guava `Maps.newLinkedHashMap()` static filled from `DyeColor.values()` and `MapColor.col` in another class's initializer: a vanilla dye table and a map from an earlier top-level run, neither modelled); custom chorus flower and plant, ivis vine; anvils and alloying blocks (Alex's call, residue); the plates' `BlockSetType` (Fabric API, not pinned).
- **Links:** #280, #277, #296, #307, #320, #321, #322, #327, #328, #87.

## 2026-10-18 (approved (Alex, 2026-10-19): picks 1a–4a): WorldWeaver's `BlockSet` material sets are read: only `java.lang.System`'s own setters make a system property settable, a run gets 1,000,000 steps, and a `LinkedHashMap` built in the run is iterated in insertion order (BetterEnd 199 -> 393/722)

- **Status:** approved (Alex, 2026-10-19): picks 1a–4a (#280, PR #328). The branch implements every "a" in the PR's picks comment.
- **Decision** (keyed on JVM shapes, never a mod's or library's name; `blockcode.Machine`):
  1. **Who can set a system property (1a; `_can_set_properties`, `_SYSTEM_SETTERS`).** #327's rule reads an unset non-reserved property as null only when no class can set one. A class now counts as a setter only when its constant pool holds a method reference to `java/lang/System` `setProperty`, `setProperties`, `clearProperty` or `getProperties` (the one way to the mutable system Properties object, Java SE 21), or one of those names as a string constant (a reflective lookup). A class that can't be parsed counts as a setter. A method of another class with the same name (a `server.properties` `Properties#setProperty` in a mixin, a builder's `setProperties`) no longer does. 1b keeps #327's byte test, under which BetterEnd stays at 242/722 with the rest of this slice.
  2. **Step budget (2a; `_MAX_STEPS`).** 1,000,000 steps per top-level run, up from 400,000. `EndBlockEntities` needs about 548k and `EndWaterPlantBlocks` about 554k once the sets are followed; at 400k, 22 blocks read today are lost. 2b keeps 400k.
  3. **Maps (3a; `_map_call`, `_map_view`, `_map_key`, `_record_components`).** `values()` and `keySet()` of a `LinkedHashMap` built in the same run are iterated in insertion order, failing fast (as `ConcurrentModificationException` would) on a structural change during iteration. This holds only when every change to the map was modelled, none happened on a forked way, and every key compares exactly; a record compares by its components (`Record#equals`, JLS 8.10.3). Any map call outside the model makes the map unknown. 3b doesn't iterate maps.
  4. **Newly read blocks (4a).** They are judged by the rules already approved for read blocks; no new emit or refuse rule. Under #321 pick 5a, 8 blocks move from DEFAULT to residue: 7 stone buttons (azure, sandy and virid jadestone, flavolite, sulphuric rock, umbralith, violecite; vanilla `ButtonBlock`) and mossy_glowshroom_gate (`FenceGateBlock`). 4b keeps their DEFAULT conversion.
- **Why:** `MaterialManager.register` tests `System.getProperty("fabric-api.datagen")`; #327's byte test matched WorldWeaver's `DedicatedServerPropertiesMixin` and a `setProperties` builder method, so the read forked. Past it, `BlockSet#buildAndRegister` iterates a `SlotMap` (a `LinkedHashMap` keyed by `SlotType` records) that the reader couldn't follow.
- **Measured** (blockstates whose registration is read, local, develop 10ba83d -> branch): BetterEnd 199 -> 393/722, none lost, none reread as a different class (7 stone sets, 119 blockstates; end-stone variants, pedestals and lanterns; the terminite and thallasium metal sets; chandeliers; end_portal_block; the mossy glowshroom wood set). Its 9 plates read as `PressurePlateBlock` and stay residue under #322 pick 7 (their `BlockSetType` comes from the unpinned Fabric API `BlockSetTypeBuilder`); anvils are read and stay residue. Unchanged and byte-identical: Quark 686/809, Comforts, Iron Chests, Cooking for Blockheads, Waystones, Storage Drawers, Farmer's Delight, Silent Gear, Mythic Metals, Alex's Mobs, AE2, Immersive Engineering, BOP, Botania, Mekanism, Supplementaries, Create. Converted BetterEnd: 3488 -> 3464 files, 25 differ (the 8 moved blocks each lose block, recipe and geometry; `unhandled.json` reasons change for the plates and 8 furnaces, and roll-up counts move 785 -> 802 and 216 -> 217). Tinkers (3.12.1.231 and 3.11.2.166) byte-identical (local convert, 16672 and 15371 files). CI on 5db186f: real-mods 39197084920 (include_optional) moved only BetterEnd against `coverage-baseline.json` (39.9% -> 39.6%, files 3483 -> 3459, residue 5236 -> 5270; rebanked in this PR), every other corpus mod equal; ingame 39197087331 18/18 green, 0 content-log errors; gauntlet board unchanged (gap-leaderboard 39197089269: done 37/50, mean 10.36%, no coverage deltas; banked).
- **Rejected:** 1b (keeps the fork on a property nothing can set); 2b (loses 22 read blocks); 3b (no set is reached); iterating any `Map` (a `HashMap`'s order isn't specified); special-casing WorldWeaver's classes (a mod name in core).
- **Left:** the other 9 BetterEnd wood sets (`BlockDefinition#build` writes after a fork); hydralux and chorus blocks (329 still unread); the plates' `BlockSetType` (needs Fabric API pinned).
- **Links:** #280, #321, #322, #327, #87.

## 2026-10-18 (approved (Alex, 2026-10-18): picks 1a–5a): builders a mod reaches through its libraries are read through deterministic models of system properties, `java.util` collections, trait Properties and havoc, and BetterEnd's BCLib-family libraries are pinned (BetterEnd 86 -> 199/722, Quark 498 -> 686/809)

- **Status:** approved (Alex, 2026-10-18): picks 1a–5a (#280, PR #327). The defaults below ("a" in the PR's picks comment) are what the branch implements.
- **Decision** (keyed on JVM shapes, never a mod's or library's name; `blockcode.Machine`):
  1. **System properties** (`_system_property`, `_RESERVED_PROPERTIES`). `System.getProperty(key)` for a constant key outside the JVM's and the game launchers' namespaces (`java.`, `os.`, `user.`, `fabric.`, `fml.`, `mixin.`, `minecraft.` and the rest of the list) reads null, as in a player's game started without `-D<key>`, unless any class of the mod or its libraries mentions `setProperty`, `setProperties`, `clearProperty` or `getProperties()`; then, and for any reserved or non-constant key, it is unknown. `Class.desiredAssertionStatus()` reads false (assertions are off unless the JVM is started with `-ea`).
  2. **`java.util` collections.** `ArrayList`/`LinkedList` built here, their iterators, `stream()` (a deterministic subset of `Stream`), `Optional`, and a subset of `Map` are modelled exactly; any method outside the model makes the collection unknown, and a loop over an unknown list stops that way instead of guessing a count. A library's registration code gets up to 16 ways (`_MAX_LIBRARY_PATHS`).
  3. **Trait Properties.** A `Properties` object passed into a library's trait/helper code is followed through that code; a lambda counts only as its functional interface, not as any other type.
  4. **Havoc (4a).** A library call the machine can't follow makes unknown everything its receiver and arguments reach (non-final fields, array elements, map contents, list items, builder text, a Properties' collision and light); statics are kept. 4b (also dropping every non-final static and havocking what the finals reach, `_HAVOC_STATICS`) was measured: Quark loses 145 blocks, BetterEnd is unchanged.
  5. **Library pins.** A library is pinned for a mod in `fixtures/real/libraries.toml` only when the reading with it is at or above the no-library baseline: BCLib, WorldWeaver and WunderLib 21.800.3 for BetterEnd (199 with them vs 86 without).
- **Soundness assumptions** (named so a later case can test them):
  - 4a does not havoc statics: an unfollowed library call that writes a static the run already holds is not seen.
  - A field nothing wrote is read as its JVM default (null, 0, 0.0; `_field_default`) only on an object made by `new` in this run, whose constructor was followed to the end, and that hasn't been handed to code the machine couldn't follow.
- **Why:** the builders BetterEnd registers through live in BCLib/WorldWeaver code that reads system properties, builds `java.util` lists and streams, and hands Properties through trait code, which the machine could not follow before. Each model returns what the JVM does in a player's game, or unknown; it never guesses.
- **Measured** (local, develop b04e368 -> branch): BetterEnd 86 -> 199/722 (7 of 3488 output files differ: 4 FurBlock blocks and smaragdant_crystal_shard get per-facing boxes from `getShape` because BCLib `BaseAttachedBlock` now resolves; filalux_wings's boxes come from `FilaluxWingsBlock.BOUNDING_SHAPES`; `unhandled.json`'s feature reasons cite `BiomeIslandFeature` instead of `BlueVineFeature` as the example `Feature` subclass `EndFeatures` names, because `BiomeIslandFeature extends bclib DefaultFeature extends Feature` now resolves and sorts first); Quark 498 -> 686/809, byte-identical output; Comforts 1 -> 33/33; the other small mods measured are unchanged and byte-identical.
- **Rejected:** 4b (measured worse, above); pinning libraries regardless of the reading (BCLib 21.800.3 alone read 16/722 before these models).
- **Links:** #280.

## 2026-10-18: a lazy-initialisation guard's test of a static that only such guards write is read as finding null, so a registration made through a lazily fetched registry is read (BetterEnd's `getBlockRegistry()`)

- **Decision** (keyed on JVM shapes, never a mod's or library's name; `Machine._lazy_guard`, `_lazy_field`, `_lazy_guarded`):
  1. **The guard.** A `getstatic F` directly followed by `ifnonnull L`, where the code it skips ends `putstatic F` immediately before `L` and nothing outside that stretch jumps into it, nothing in it jumps out except to `L`, returns or throws, and nothing in it reads a local variable it didn't first write (javac's `if (F == null) F = <expr>;` computing from no argument), is taken as finding null when the run doesn't hold a known non-null value for `F`, so the run goes on through the guard's computation instead of forking. This holds only for a field `F` that is a private, non-final reference static without a ConstantValue (only its own nest's classes can write it, JVMS 5.4.4; a static holds null from preparation until written, JVMS 2.3, 5.4.2) and whose nest (the top-level class and its `$` classes, the static initializer included) has exactly one `putstatic F`, inside such a guard; the test read this way is that guard's own `ifnonnull`, not an outer test around it (code between two tests runs in the game only while `F` is null). Why it is exact: a guarded read that finds `F` set finds what an earlier run of the same guard computed (one write, so no other guard could have computed a different value first, and no argument feeds the computation); one that finds it null computes it now; either way the value the guard leaves is the guard's computation (the computation is taken to yield the same value each time, as BetterEnd's `BlockRegistry.forMod(C)` and its `computeIfAbsent` do). Any other read of `F` is unchanged (unknown until written in the run). (Narrowed in review of PR #326, 2026-10-18: one write rather than every write guarded, no local reads, no return or throw, the guard's own test; BetterEnd's reading is the same 86 blocks, class for class.)
  2. **Field flags.** `ClassFile.field_access` keeps each field's access flags (plus 0x10000 for a ConstantValue); `ClassIndex.nest(name)` lists the classes compiled from the same top-level class, the mod's and the libraries'.
  3. **Libraries.** BCLib, WorldWeaver and WunderLib 21.800.3 (the newest 1.21.8 Fabric releases on Modrinth inside BetterEnd's declared 21.800.x) are measured, not pinned: with them BetterEnd reads 16/722, alone 86/722 (their builder code, once followed, forks on `System.getProperty("fabric-api.datagen")` and iterates trait lists the reader doesn't model, so each static initializer stops at its first block); pinning them would lower what the readers find (#321 pick 2a pins only what improves the reading). Recorded in `fixtures/real/libraries.toml`.
  4. **What reading more changes.** Newly read blocks are judged by the rules already approved for read blocks (#321 pick 5a, #320/#296 plates, #307, facing and boxes from bytecode first, light from `Properties.lightLevel`); nothing new is emitted or refused by a new rule, and no block moves from DEFAULT to residue.
- **Measured** (blockstates whose registration is read, local, 2026-10-18, each corpus and gauntlet jar with its mapping table, pinned libraries and vanilla block table; develop 2c17521 -> this branch): BetterEnd 21.800.2 0/722 -> 86/722 (the first-class blocks its `End*Blocks` static initializers register through `EndBlocks.defineBlock(name, Foo::new)`: `registry.defineDefaultBlock(name, factory)` is a call into code that isn't there handing one name and one block factory, the #321 pick 4a registration; e.g. aeternium_block `AeterniumBlock`, the 11 `EndPathBlock` paths, 6 `TintedParticleLeavesBlock` leaves, dragon bone, neon cactus and smaragdant crystal slabs, stairs, walls and pillars, respawn_obelisk, eternal and infusion pedestals). Their Properties are unknown (the builder's `getProperties()` result isn't read), so no light, sound or strength is taken from them. Every other corpus and gauntlet mod unchanged, block for block: AE2 102/102, Alex's Mobs 4/37, BOP 229/345, Botania 174/678, Comforts 1/33, Cooking for Blockheads 140/140, Create 318/643, Farmer's Delight (NeoForge 132/132, Fabric 0/133), Immersive Engineering 175/390, Iron Chests 14/14, Mekanism 99/201, Mythic Metals 0/118, Quark 498/809, Silent Gear 0/59, Storage Drawers (NeoForge 143/144, 1.19.2 69/70, 1.12.2 0/6), Supplementaries 7/231, Tinkers 0/435, Waystones 44/44; the other 37 fetchable jars have no blockstates; Twilight Forest and Chisel (CurseForge, no pinned URL) unmeasured. Converted: BetterEnd byte-identical (local `portkit convert`, 3488 files both, every file identical): 35 of the 86 newly read blocks are residue for reasons the reading doesn't touch (state-driven blockstates, multipart, `bclib:block/path` parents, stair and wall models off the vanilla template), and the other 51 (cubes, leaves, pillars, slabs, stairs, walls) convert exactly as their DEFAULT did: their converters take nothing more from the reading, and with unknown Properties no light is read. BetterEnd's 9 stone and metal plates are not among them (registered through WorldWeaver's `BlockSet` builders) and stay residue. Gauntlet board unchanged (gap-leaderboard 39168344469: done 37/50, mean 10.36%; banked). ingame 39168342280: 18/18 green, 0 content-log errors.
- **Why:** #280: BetterEnd read 0/722 because `EndBlocks.getBlockRegistry()` is a lazy singleton: its null test forked and the write after it stopped every static initializer before its first registration.
- **Rejected:** reading every unwritten static as its default (another method may have set it first in the game; not exact); following WorldWeaver's builders by special-casing their classes (a mod name in core); pinning the three libraries (lowers the reading, see 3); taking `System.getProperty` of a property the JVM doesn't define as null (a new assumption about the player's JVM; left for a design pick).
- **Left:** WorldWeaver's `BlockDefinition` builders, read with the library: `System.getProperty("fabric-api.datagen")` forks (a policy pick: is an unset non-standard property null in a player's game?), mutable `java.util` lists and their iterators, streams and `removeIf` (the builder's trait and property-setter lists), and trait objects applying Properties; the registration method then needs a way past a call it can't follow (treat it as code that isn't there, with what it may have written unknown). BCLib's base classes resolve only with the library (35 BetterEnd blocks are "registered as org.betterx.bclib.blocks.Base*" without it). BetterEnd's `BlockSet` material sets (stones, metals, woods: its 9 plates), anvil and alloying blocks (pending Alex's calls, residue); Registrate, Balm, owo, Mantle, Moonlight jars.
- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order).
- **Links:** #280, #277, #296, #307, #320, #321, #87, PR #326.

## 2026-10-18: a constructor's ways after a branch it can't decide are joined where it returns (each way writes its own copy of the object it builds), and an object whose `new` comes before such a branch is built once per way

- **Decision** (keyed on JVM shapes, never a mod's or library's name):
  1. **The join** (`Machine._run_code`, `_join_fields`). While a constructor runs, each way after a branch it can't decide keeps its own copy of the receiver's fields (`Frame.recv_fields`), so a write to the object under construction (a `putfield` on `this`, or the super or `this(..)` constructor called on it) no longer stops the run. Where the constructor returns, the copies of the ways that returned are joined: a field every way left the same (the same object, or an equal value: a string, a number, a vanilla constant, an equal Properties copy) keeps it; a field the ways left differently, or that one way didn't set, is unknown and the object is marked partial ("its constructor's ways after a branch it can't decide leave <field> different"), so no reader takes anything from it, as a constructor that stops is read today. A way that throws is not joined (that object is never built). Writes to anything else after such a branch still stop the run (statics; objects allocated before the branch, other than the receiver), as before.
  2. **`new` before the branch, the constructor after it** (`Machine._invoke`). Until its constructor is called an object can only sit on its frame's operand stack and locals (JVMS 4.10.1.9: an uninitialized reference can't be stored in a field or array or passed to a method), so every way of a branch taken between `new` and `<init>` holds the same reference; each way now builds its own copy of it instead of stopping at the constructor (exactly one way runs in the JVM).
  3. **Smaller fidelity pieces the same shapes need.** `String#replaceAll` / `replaceFirst` with a regex holding no `java.util.regex` metacharacter and a replacement holding no `\` or `$` is the plain left-to-right replacement (Pattern, Matcher#appendReplacement, Java SE 21); any other regex or replacement is unknown. Apache Commons Lang `Pair.of` / `ImmutablePair.of` keep both elements and `getLeft`/`getKey`, `getRight`/`getValue` return them (commons-lang3, which Minecraft ships). Choosing what to run (#322 pick 1) also takes a method loading a format string whose only specifiers are `%s` and whose filled slots match a whole blockstate name (`"hollow_%s"`), and its callers; as before, a name counts only as the machine evaluates it.
  4. **What reading more changes.** Newly read blocks are judged by the rules already approved for read blocks (#307 vertical slabs, #321 pick 5a, #324 pick 5a, facing and boxes from bytecode first, light from `Properties.lightLevel` and copied Properties); nothing new is emitted or refused by a new rule, and no block moves from DEFAULT to residue.
- **Measured** (blockstates whose registration is read, local, 2026-10-18, each corpus and gauntlet jar with its mapping table, pinned libraries and vanilla block table; develop ec728a3 -> this branch): Quark 4.1-487 (with Zeta 1.1-40) 425/809 -> 498/809: 22 wooden posts (`WoodPostBlock`, vanilla woods, plain and stripped), 13 hollow logs (`HollowLogBlock`, `"hollow_%s"`: the 10 vanilla logs and stems, and Quark's ancient, azalea and blossom logs), 10 leaf carpets (`LeafCarpetBlock`, vanilla leaves, `path.replaceAll("_leaves", "_leaf_carpet")`), 11 panes (`ZetaInheritedPaneBlock`: 9 corundum panes, dirty and framed glass panes), 9 corundum clusters (`CorundumClusterBlock`, named from their corundum by Zeta's `inheritQuark` before the super constructor; their constructor then writes to the corundum block, an object built before the fork, so their reading stays partial for boxes), 4 copper vertical slabs (`WeatheringCopperVerticalSlabBlock`, `Pair#getLeft`) and their 4 waxed vertical slabs (`QuarkVerticalSlabBlock`, `Pair#getRight`); the 51 vertical slabs read in #324 now read whole (their constructor's ways all write the same module and condition). No block read before is read as a different class or lost. Every other corpus and gauntlet mod unchanged: AE2 102/102, Alex's Mobs 4/37, BetterEnd 0/722, BOP 229/345, Botania 174/678, Comforts 1/33, Cooking for Blockheads 140/140, Create 318/643, Farmer's Delight (NeoForge 132/132, Fabric 0/133), Immersive Engineering 175/390, Iron Chests 14/14, Mekanism 99/201, Mythic Metals 0/119, Silent Gear 0/59, Storage Drawers (NeoForge 143/144, 1.19.2 69/70, 1.12.2 0/6), Supplementaries 7/234, Tinkers (both) 0/435, Waystones (both) 44/44; the other fetchable jars have no blockstates. Converted: Quark byte-identical except the 9 corundum panes, which gain `minecraft:light_emission` 11, because `Properties.ofFullCopy` copies the parent `CorundumBlock`'s light 11; every other corpus and gauntlet mod byte-identical: Tinkers' Construct corpus 16667 files / 15137 residue and every other corpus mod's files and residue identical to coverage-baseline.json (real-mods 39160089592, include_optional, mct errors 0), gauntlet board unchanged (gap-leaderboard 39158219789: done 37/50, mean 10.36%, block 11/1297). ingame 39160238768: 18/18 green, 0 content-log errors.
- **Why:** #280: Quark builds its posts, hollow logs, leaf carpets and panes from vanilla parent blocks, and Zeta's name lookup forks before their super constructor runs, so no way of the fork could build the block and every reader fell back to DEFAULTs (#324 left 76 such blockstates unread); the #324 vertical slabs' constructor reading was partial for the same reason. #87: what a way stores is kept only when every way stores the same thing.
- **Rejected:** a classic join of whole frames at every merge point (it would make the looked-up name unknown on every way and lose the registration); letting forked ways write the shared object in turn (the last way's writes would win: nondeterministic in meaning, not exact); keeping the first way's field when ways differ (a guess).
- **Left:** map iteration as a loop source (`VariantRegistry.slabs.values().forEach(..)`: the 60-odd vertical slabs of Quark's own slabs; the map is filled by other modules' registration runs in Zeta's registry, which #323 chose not to model, so its contents and order aren't known in one run); Quark-wood posts and leaf carpets, blossom hedges and framed glass panes (built from Quark blocks whose own names aren't read yet); Quark's stones built by `NewStoneTypesModule#makeStone`; BOP and Botania have no pinned table for their declared versions; WorldWeaver/BCLib builders (BetterEnd); Registrate, Balm, owo, Mantle, Moonlight jars. A nested call on a forked way can still write shared state (a library's static map) unguarded, as before this change (the write guard is per method).
- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order).
- **Links:** #280, #277, #307, #321, #322, #323, #324, #87, PR #325.

## 2026-10-18: a vanilla block's registered name is read from Mojang's client jar at `portkit reference fetch` (a `Blocks` field -> id table per pinned game version, never vendored), so variants named from vanilla parents are read; `java.util.Map#put` is not a registration

- **Decision** (PR #324 for #280; picks numbered, each "a" the default, all approved):
  1. **Where the table comes from.** a) `portkit reference fetch` downloads Mojang's client jar and `client.txt` for each pinned game version (piston-data.mojang.com, each pinned by the sha1 Mojang's version manifest gives; `client.txt` is the same file and pin the #235 name mappings use), derives `Blocks` field -> id from `net.minecraft.world.level.block.Blocks#<clinit>` with the existing bytecode reader (`portkit.data.vanilla_blocks.derive`: each block field's `putstatic` follows an `invokestatic` of a `Blocks` method whose first argument is the id, a string constant or a 1.21+ `ResourceKey` constant built from one; a block field assigned another way is listed under `unmatched`, not guessed), checks the derived table's sha256 pin and caches it; like the joined name mappings and Geyser's item map it carries Mojang's names, so it is never vendored (no jar, no table in the repo or wheel). b) commit the generated tables (with jar version, sha1s and the method recorded) and check them with a test. c) take a field's lower-cased name as its id (rejected in #323: `POTTED_AZALEA` is `potted_azalea_bush` in every pinned version).
  2. **Which version's table.** a) Exactly the game version the mod declares (1.19.2, 1.20, 1.20.1, 1.21, 1.21.1, 1.21.8: the versions the name mappings pin); a NeoForge jar that names no `minecraft` dependency takes the version its required `neoforge` dependency's lower bound names under NeoForge's versioning ("the major version is Minecraft's minor version, the minor version is Minecraft's patch version", docs.neoforged.net Getting Started > Versioning; majors 20-25 only), for this table only (`ModMetadata.loader_minecraft`; `minecraft` and every other reference set stay as declared). Any other version: no table, variants of vanilla blocks stay unread as before. b) also use the nearest pinned version.
  3. **What the reader does with it** (keyed on bytecode, never a mod's name). a) The block registry's `getKey(Blocks.X)` answers `minecraft:<id>` from the table (a looked-up key, registering nothing, as #323 pick 1); a vanilla `Blocks` constant the table lists is no instance of a jar class or interface (#323 pick 3's rule, applied to a vanilla object); Guava `ImmutableList.of` / `ImmutableSet.of` and `java.util.List.of` / `Set.of` of known elements are evaluated (varargs flattened; an ImmutableSet keeps the first of equal elements in order; `Set.of`, whose iteration order is unspecified, only when it holds at most one element) and `Iterable#forEach(Consumer)` over one runs the consumer per element in order; the caller search for name-building methods goes up to 4 levels and counts an `invokedynamic` naming a method as a call to it; while registrations are collected, a way of a fork that stops at a write after the fork no longer keeps its sibling ways from running for the registrations they make (the run still stops when they are done, so nothing it returns or writes is taken as known). b) model nothing new in the interpreter and read only `getKey` of constants handed straight to a registration.
  4. **`java.util.Map#put` / `putIfAbsent` (Map and its java.util implementations) is not a registration.** a) A call storing a block and a string in a map registers nothing. Measured: the one blockstate it changes in the whole corpus and gauntlet is Quark's myalite stone, which no longer reads as the myalite crystal's class, so its converted block drops the crystal's `minecraft:light_emission` 14 (DEFAULT, as its other stones). b) leave the misread.
  5. **What reading more changes.** a) Newly read blocks are judged by the rules already approved for read blocks (#307 vertical slabs, #321 pick 5a, facing and boxes from bytecode first, light from `Properties.lightLevel`); nothing new is emitted or refused by a new rule, and no block moves from DEFAULT to residue.
- **Measured** (blockstates whose registration is read, local, 2026-10-18, each corpus and gauntlet jar with its mapping table, pinned libraries and, on this branch, its vanilla block table; develop ac979b9 -> this branch): Quark 4.1-487 (NeoForge, `neoforge` [21.1.252,) -> table 1.21.1) 375/809 -> 425/809: the 51 vertical slabs of vanilla slabs (`ImmutableSet.of(Blocks.ACACIA_SLAB, ..).forEach(..)`, named `<vanilla id>_vertical_slab` via `RegistryUtil#inherit`) are read as `QuarkVerticalSlabBlock`, and myalite is no longer misread (pick 4). Every other mod unchanged, and no block read before is read as a different class: AE2 102/102, Alex's Mobs 4/37, BetterEnd 0/722, BOP 229/345, Botania 174/678, Comforts 1/33, Cooking for Blockheads 140/140, Create 318/643, Farmer's Delight (NeoForge 132/132, Fabric 0/133), Immersive Engineering 175/390, Iron Chests 14/14, Mekanism 99/201, Mythic Metals 0/119, Silent Gear 0/59, Storage Drawers (NeoForge 143/144, 1.19.2 69/70, 1.12.2 0/6), Supplementaries 7/234, Tinkers 0/435, Waystones 44/44; the other 39 fetchable jars have no blockstates. The derived tables: 1.19.2 933 blocks, 1.20 and 1.20.1 1003, 1.21 and 1.21.1 1060, 1.21.8 1105; every block field matched (`unmatched` empty) and every id has a blockstate file in its jar; ids that differ from the lower-cased field name: `POTTED_AZALEA` -> `potted_azalea_bush`, `POTTED_FLOWERING_AZALEA` -> `potted_flowering_azalea_bush` (all six versions). Converted (local `portkit convert` of Quark with Zeta, develop vs branch): 2493 files both, residue entries unchanged, one file differs: `blocks/myalite.json` loses `minecraft:light_emission` 14. The 51 newly read vertical slabs convert byte-identically: their constructor writes a field after Zeta's name lookup forks, so the reading is partial ("its constructor can't be followed to the end") and the vertical slab converter takes nothing more from it than the DEFAULT gave.
- **Why:** #280: Quark builds its vertical slabs, posts, hollow logs, leaf carpets, hedges and panes from vanilla parent blocks, and nothing could name a variant of a vanilla block without the vanilla `Blocks` field -> id table (#323 left it). #87: the id is read from the game's own code, not guessed.
- **Rejected:** a hand-written table (#220, #87); the lower-cased field name (not exact, see pick 1c); the nearest pinned version for an unpinned game version (fields are renamed between patch releases: 1.20.3 renamed `GRASS` to `SHORT_GRASS`); stopping counting every `java.*` call as a registration (broader than the misread found; not measured).
- **Left:** Quark's posts, hollow logs, leaf carpets, hedges and panes of vanilla woods and glass (their constructors call the super constructor on `this` after Zeta's lookup forks, so no way of the fork may build the block; 76 still unread), its copper vertical slabs (`Pair#getLeft` in a lambda) and the vertical slabs of its own slabs (`VariantRegistry.slabs.values()`, map iteration); the newly read vertical slabs' partial constructor (a join of the ways of a fork at a constructor's end would make them whole); Quark's stones built by `NewStoneTypesModule#makeStone`; BOP and Botania have no pinned table for their declared versions; WorldWeaver/BCLib builders (BetterEnd); Registrate, Balm, owo, Mantle, Moonlight jars. Runtime unobfuscated (26.1+) jars need no `client.txt`; not pinned yet.
- **Status:** approved (Alex, 2026-10-18, picks 1a-5a): picks 1a 2a 3a 4a 5a, the defaults (PR #324).
- **Links:** #280, #277, #235, #261, #307, #321, #323, #87, #220, PR #324.

## 2026-10-18: a registration name derived from another block's registered name is evaluated from the bytecode (the block registry's key of a block this run registered, a location whose namespace is unknown but whose path is known); a parent whose registered name isn't read leaves the variant unread

- **Decision:**
  1. **The registered name of a block** (`Machine._registry_key`). The block registry's `getKey(block)` (`BuiltInRegistries.BLOCK`, vanilla `Registry#getKey(Object)`) answers, for a block object this run recorded as registered (`_record`) under exactly one valid resource name, that name; anything else stays unknown. A key that was looked up names a registration already made, so handing it on with another block (Zeta's potted plant filed under its plant's key) registers nothing. A vanilla parent (`Blocks.STONE`) has no recorded registration, so a variant of it stays unread: the vanilla `Blocks` field -> registry id table isn't modelled (no fabricated vanilla ids, #87).
  2. **A location whose namespace isn't known** (`Tail`). `String.format("%s:%s", <unknown modid>, "%s_slab")`, a concatenation or a `StringBuilder` with an unknown piece followed by a known `":"`, and `ResourceLocation.fromNamespaceAndPath(<unknown>, path)` keep the text after the last `":"` exactly, which is all a registration name is matched by (`_record` drops the namespace). Formatting such a string formats its known text only when that text's `%s` take exactly the arguments given (no specifier can span the `":"`, and one the unknown start used would leave the text's `%s` short, which throws; java.util.Formatter, Java SE 21). `ResourceLocation#getPath` / `getNamespace` / `toString` are evaluated for a location known here.
  3. **Interpreter fidelity the JVM shape needs** (keyed on bytecode, never a mod's or library's name): an interface's default method is run when neither the jar's classes in the receiver's chain nor what the machine models of vanilla answer the call (JVMS 5.4.6, maximally-specific superinterface method; Zeta's `IZetaBlock#setCreativeTab` returns the block); `instanceof` is exact for null and for an object of a jar class whose type is a jar class or interface (a vanilla class can't extend or implement one), else unknown; a branch whose one way only builds and throws a `java.lang` exception (`if (module == null) throw new IllegalArgumentException(..)`) is not a fork (that way registers and returns nothing); a write after an undecided branch to an object or array that way allocated since (its allocation number is above the branch's) is allowed, every other such write still stops the run. `ClassFile.access` now holds the class's flags (it held the last method's).
  4. **What reading more changes.** Newly read blocks are judged by the rules already approved for read blocks (#307 vertical slabs, #321 pick 5a, facing and boxes from bytecode first, light from `Properties.lightLevel`); nothing new is emitted or refused by a new rule.
- **Measured** (blockstates whose registration is read, local, 2026-10-18, each corpus and gauntlet jar with its mapping table and pinned libraries, base acf340b -> this branch): Quark 4.1-487 (with Zeta 1.1-40) 296/809 -> 375/809 (33 slabs, 33 stairs, 12 walls named `<parent>_slab|_stairs|_wall` by Zeta's `VariantRegistry` + `RegistryUtil#inherit`, and ancient_hedge); Applied Energistics 2 0/102 -> 102/102 (its registration helpers' null guards and fresh arrays no longer stop the run); Storage Drawers (NeoForge) 66/144 -> 143/144 (66 standard drawers, 11 trims); Immersive Engineering 174 -> 175/390 (coke_oven). Unchanged: Farmer's Delight (NeoForge 132/132, Fabric 0/133), BetterEnd 0/722, Create 318/643, Supplementaries 7/234, Waystones 44/44, Tinkers (both) 0/435, Mythic Metals 0/119, Silent Gear 0/59, Storage Drawers 1.19.2 69/70 and 1.12.2 0/6, Alex's Mobs 4/37, Mekanism 99/201, BOP 229/345, Botania 174/678, Iron Chests 14/14, Comforts 1/33, Cooking for Blockheads 140/140; the other 36 gauntlet jars have no blockstates; Twilight Forest and Chisel (CurseForge, no pinned URL) were measured only by the board. No block read before is read as a different class. Converted (gap-leaderboard 39098074880): Quark 2489 files / 5167 residue unchanged (the 78 newly read slabs, stairs and walls and ancient_hedge convert byte-identically to their DEFAULT output: the slab, stair and wall converters take nothing more from a reading than the DEFAULT gave); AE2 814 -> 811 files, 3399 -> 3404 residue, 19.3 -> 19.2%: its 3 quartz buds and quartz cluster take the per-facing boxes read from `CertusQuartzClusterBlock#getShape` instead of the DEFAULT full cube, and crystal_resonance_generator, growth_accelerator and spatial_anchor, already residue (textures that don't convert), now name the reason read from code ("the player doesn't set facing", the approved 6-way rule), so their 3 geometry files no longer ship alone; every other gauntlet mod unchanged; done 37/50, mean 10.37 -> 10.36%.
- **Why:** #280: most of Quark's still-unread blockstates are variants Zeta names from the parent block's registered name (`inherit(parent, "%s_slab")`), so every bytecode reader fell back to DEFAULTs for them; the guards and helper shapes that stopped those runs also stopped AE2's and Storage Drawers' registration code.
- **Rejected:** a model of the library registry's own map (needs every unknown receiver of a registry class to be one object, which a mod with a block and an item `DeferredRegister` breaks); matching `<name>_slab` to a slab by pattern (a guess); a vanilla `Blocks` field name as its registry id (not exact for every field, and no pinned table); treating every write after a branch as unknown instead of stopping (a static written on one way would read as unknown on the next run of a later method, which lost 119 of Quark's wood-set reads when measured).
- **Left:** variants of vanilla blocks (Quark's 122 vertical slabs are built from vanilla slabs and from `VariantRegistry.slabs.values()`; posts, hollow logs, leaf carpets, hedges and panes of vanilla woods and glass: Quark 434/809 still unread), a vanilla `Blocks` -> id table; map and list iteration as loop sources; Quark's stones built by `NewStoneTypesModule#makeStone` (jasper, limestone, shale, myalite and their bricks: it stops at a static written after a config branch); a pre-existing misread found here and left as it was: Quark's `myalite` stone reads as the myalite crystal's class and takes its light 14, because Zeta's `blocksToColorProviderName.put(crystal, "myalite")` (a call into code that isn't there handing a block and a name) is taken as a registration (base acf340b does the same; a follow-up should stop counting `java.util.Map#put` as one, measured); WorldWeaver/BCLib builders (BetterEnd); Registrate (Create's other 325), Balm, owo, Mantle, Moonlight jars. PR #322 review nits not addressed: piece runs still share state in class order, short name pieces still pull in many methods, and the caller search is still one level.
- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order).
- **Links:** #280, #277, #296, #307, #321, #322, #87, PR #323.

## 2026-10-17: registration names built by concatenation are evaluated from the bytecode (string pieces, enum and array constants, static finals, simple loops); a name that can't be evaluated stays unread

- **Decision:**
  1. **What runs** (`blockcode._piece_methods`). Besides the static initializers and methods that load a whole blockstate name (#280 slice 1), every method of the mod's own classes (never a library's) that may build a name runs once on unknown arguments, its class initialized first: one that loads (`ldc`) a whole-word piece of a name (`"azalea"`, `"_shingles"`: a run of `_`-separated words short of the whole name), one whose `makeConcatWithConstants` recipe matches a whole name (`"\x01_pressure_plate"`), and, one level up, a method calling one of those (a module looping `DyeColor.values()` into `new StoolBlock(this, dye)`). Choosing what to run decides nothing: a name counts only as the machine evaluates it, exactly, and only when it equals a blockstate's name. The JVM shapes are keyed on, never a mod's or library's name.
  2. **What evaluates.** `StringConcatFactory` recipes and `StringBuilder` (including `new StringBuilder(String)`) with each argument printed as Java's `String.valueOf` would by its descriptor type (`char`, `boolean`, `int`/`long`; a `float`/`double` is unknown, since Java's float text isn't Python's); `String.format` with only `%s`/`%%`; `String#concat`, `replace`, `toString`, `toLowerCase`/`toUpperCase` (no locale or a `java.util.Locale` constant, ASCII text); a mod enum's `name()`/`ordinal()`/`toString()` (unless overridden) from `java.lang.Enum(String, int)`, `values()` through `$VALUES.clone()`; vanilla `DyeColor.values()`, `getName()`/`getSerializedName()`, `ordinal()`/`getId()` (its 16 constants and their names, MC 1.21.1 Mojang mappings; the 0-15 ids on minecraft.wiki "Dye#Data values"); static finals from the class's own static initializer; `for` loops over arrays and int counters whose bounds are known. Anything else (a call into code that isn't there, an `Iterator`, a float) is unknown, and a name built from an unknown is not a name: the block stays unread with the reason it had ("no registration of this block was found").
  3. **A run that stops part way** (`Unreadable`) puts the statics it wrote back to what they were before it, for every registration method run, the slice-1 ones included: a library's half-done state (Zeta's `CreativeTabManager` chain started and never ended) otherwise made every later run branch on it and stop too. Registrations it recorded before stopping stay.
  4. **A concatenated name handed with a non-block** (a config builder, a recipe builder) is not a registration and is never given as the reason a block went unread.
  5. **What reading more changes.** Newly read blocks are judged by the rules already approved for read blocks (facing and boxes read from bytecode first, #321 pick 5a for vanilla classes whose state changes aren't ported, light from `Properties.lightLevel`); nothing new is emitted or refused by a new rule.
  6. Library jars nested under `META-INF/jars/` larger than 64 MiB are skipped rather than read whole (PR #321 review).
  7. A pressure plate, door or trapdoor read as its vanilla class but built with a `BlockSetType` that isn't a vanilla constant read here takes the wooden DEFAULT only when the jar's own `minecraft:wooden_pressure_plates` / `wooden_doors` / `wooden_trapdoors` tag lists it, the same check an unread one gets (#296 pick 3a); otherwise it is residue with that reason (PR #322 review).
- **Measured** (blockstates whose registration is read, local, 2026-10-17, read with the mod's mapping table and pinned libraries): Quark 4.1-487 (with Zeta 1.1-40) 77/809 -> 296/809 (wood sets: logs, wood, planks, fences, gates, doors, trapdoors, plates, buttons; dye-colour stools, framed glass, shingles; corundum; chests; ladders, bookshelves, posts' kin built in loops); Create 6.0.8 208 -> 318/643 (16-colour postboxes, seats, table cloths, toolboxes, valve handles, nixie tubes, sails); Mekanism 2 -> 99/201; Immersive Engineering 116 -> 174/390; Cooking for Blockheads 12 -> 140/140; Waystones (Fabric and NeoForge) 13 -> 44/44. Unchanged: Farmer's Delight (NeoForge 132/132, Fabric 0/133), BetterEnd 0/722, Supplementaries 7/234, Tinkers (both) 0/435, Mythic Metals 0/119, Silent Gear 0/59, Storage Drawers (1.19.2 69/70, 1.12.2 0/6, NeoForge 66/144), Alex's Mobs 4/37, AE2 0/102, BOP 229/345, Botania 174/678, Iron Chests 14/14, Comforts 1/33; the other 36 gauntlet jars have no blockstates; Twilight Forest and Chisel (CurseForge jars) were measured only by the board. No block read before is read differently. Converted: Quark 2499 -> 2489 files, 5145 -> 5167 residue, 32.69 -> 32.51% (gap-leaderboard 39093001497): 3 wood fence gates and 2 furnaces now read as vanilla `FenceGateBlock` / `FurnaceBlock` move from DEFAULT to residue (#321 pick 5a), and 22 blocks gain `minecraft:light_emission` read from code (18 corundum 11, glow_shroom 10, glow_lichen_growth 8, potted_cave_vines 14, potted_sea_pickle 3). Create's 15 dyed sails take the placement read from code that its white sail and sail frame already had (`minecraft:facing_direction` instead of the DEFAULT `minecraft:block_face`); Immersive Engineering's 23 warning signs take facing = the player's facing read from `WarningSignBlock#getStateForPlacement` (the DEFAULT's 180-degree offset dropped). File and residue counts of every corpus mod at baseline (real-mods 39092999769, include_optional, mct errors 0); every other gauntlet mod unchanged; block residue 11 mods/1292 -> 11/1297; done 37/50, mean 10.37%. Quark's wood-set pressure plates, doors and trapdoors are now read as vanilla classes, but built with Quark's own `new BlockSetType("quark:<wood>")`, which isn't a vanilla constant, so they convert as the labelled wooden DEFAULT exactly as before, because the jar's wooden_* tags list all 9 (pick 7; Quark output byte-identical with and without it, 2494 files). ingame 39093517689: 18/18 green.
- **Why:** #280: Quark's wood and colour sets, and every colour-looped block in Create, Mekanism, IE, Cooking for Blockheads and Waystones, are registered under names javac builds at run time; reading only whole-name constants left them unread, so every bytecode reader fell back to DEFAULTs or residue for them.
- **Rejected:** matching names by pattern without running the code (a guess: `"\x01_planks"` says nothing about which woods); taking a name from one branch when paths disagree; treating every enum-like `Const` as an enum (a record's `name()` isn't its field name); following Zeta's `RegistryUtil#inherit` / `ZetaRegistry#getRegistryName` (names derived from another block's registered name need a model of the registry's own map; a later slice).
- **Left:** names derived from another block's registered name (Zeta's slabs 66, stairs 65, vertical slabs 122, walls 32, posts 28, panes, hollow logs, vertical planks, leaf carpets, hedges: Quark 513/809 still unread); lists and iterators as loop sources; float and double text; Quark's 1-arg `BlockSetType(String)` (its plates, doors and trapdoors stay the wooden DEFAULT); WorldWeaver/BCLib builders (BetterEnd); Registrate (Create's other 325), Balm, owo, Mantle, Moonlight jars.
- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order).
- **Links:** #280, #277, #235, #296, #321, #87, PR #322.

## 2026-10-17: a mod is read with its pinned dependency jars, read-only: library classes resolve base classes and registering constructors; registrations made in methods are read too

- **Decision:**
  1. **Input** (pick 1a). `portkit convert --library JAR` (repeatable), and for corpus and gauntlet mods a hand-pinned `fixtures/real/libraries.toml` (`[[library]]`: name, project, version_id, version, url, sha512, license, `for` = the manifest mods it is read with), fetched and sha512-checked like the corpus jars, cached, never committed or vendored. `portkit corpus fetch`, `eval --corpus`, `gauntlet run` and `ingame.yml` read a mod with its pinned libraries; a gauntlet shard record names them. Jars a library nests in `META-INF/jars/` (Fabric jar-in-jar) are read as part of it; the mod's own nested jars are not (#171 stays open for that).
  2. **What is pinned** (pick 2a, DEFAULT). The newest Modrinth release of the library on the mod's loader and game version inside the mod's own declared range, pinned only when measured to change what the readers find. Pinned: Zeta 1.1-40 for Quark 4.1-487 (Quark's `neoforge.mods.toml` requires `zeta [1,1.2)`). Not pinned: BCLib, WorldWeaver and WunderLib 21.800.2 for BetterEnd 21.800.2 (0 of 722 registrations found with or without them, see Measured).
  3. **Read-only** (pick 3a). Library classes go into the mod's `ClassIndex` as library classes: found by a lookup by name (a superclass chain, a constructor, a static), never listed, counted, scanned or converted as the mod's (`names()`, `raw()`, `len()` are the mod's own, so `java_code` counts, worldgen/biome/item scans and every reason are unchanged). The mod's own class wins a name clash, then the earlier library. No library asset, data, tag, lang or model is read, and nothing of a library ships. A library jar is remapped with the mod's table (#235).
  4. **Registrations** (pick 4a). (i) A call into a library's code that hands one name and a block (`ZetaRegistry#registerBlock(this, name, ...)` from a library constructor) is a registration, exactly as a call into code that isn't there already was, and is then followed. (ii) Besides static initializers, every method of a class whose constant pool names a blockstate, and that loads the name itself (`ldc`), runs once on unknown arguments (a module's `register(event)`, an initializer's `onInitialize()`), with or without libraries. The same object handed on through a library's own registry methods is one registration. Names built by concatenation (Quark's wood sets, `name + "_pressure_plate"`) are not looked for yet.
  5. **What reading more changes** (pick 5a). A block whose registration is now read is judged by the rules already approved for read blocks: a facing+booleans block read as a vanilla class whose state changes aren't ported (`FenceGateBlock`, `ButtonBlock`) is residue naming that class, where it took the labelled DEFAULT while unread. That moves 12 fence gates (BOP 10, Botania 2) from DEFAULT conversions that never open to residue (pick 5b: keep converting such a block as the DEFAULT it got while unread).
- **Measured** (registrations read, of all blockstates; local, 2026-10-17): Quark 4.1-487 0/809 -> 7/809 (methods, no library) -> 77/809 with Zeta (Block 55, FenceBlock 10, RotatedPillarBlock 4, ButtonBlock 2, FlowerPotBlock 2, PressurePlateBlock 1, FenceGateBlock, IronBarsBlock, PinkPetalsBlock 1 each). BetterEnd 21.800.2 0/722 with and without its three libraries: its `End*Blocks` static initializers build through WorldWeaver's `BlockSet` / `BlockDefinition` builders, whose lazily created registries are written after branches the reader can't decide. Converted Quark (`--library zeta`): 10 blocks gain `minecraft:light_emission` read from code (blaze_lantern, duskbound_lantern, paper_lantern, paper_lantern_sakura, stone_lamp, stone_brick_lamp 15; glowberry_sack, myalite, myalite_crystal 14; magnet 0 unpowered, 3 powered), none had one before; 4 residue reasons name what was read instead of "no registration" (obsidian_pressure_plate: `ObsidianPressurePlateBlock#getSignalStrength` overrides vanilla, players only; gold/iron_button and nether_brick_fence_gate: vanilla `ButtonBlock`/`FenceGateBlock` state changes not read); files 2499, residue 5145, 32.7% unchanged. Without a library, Quark's output is byte-identical to develop. Corpus (real-mods 39089361714 on b47df90, include_optional): all 13 mods at baseline, mct errors 0. Gauntlet board (gap-leaderboard 39089363055 on b47df90): BOP 1487 -> 1457 files, 1395 -> 1455 residue, 51.6 -> 50.03%; Botania 3619 -> 3613, 4080 -> 4092, 47.01 -> 46.89%; block residue 11 mods/1280 -> 11/1292; every other mod unchanged; done 37/50, mean 10.37%.
- **Why:** #280: mods that register through a library read as "no registration found" or "leaves the jar at the library's class", so every bytecode reader (facing, boxes, light, booleans, doors, trapdoors, plates) fell back to DEFAULTs or residue. Reading the library's classes, without converting them, is the shared part #280, #171 and #235's helper leftovers all need.
- **Rejected:** merging a library into the mod (would convert and ship its content); resolving dependencies from the mod's metadata at conversion time (a network fetch inside `convert`; pins keep runs reproducible); pinning every declared dependency (BetterEnd's three change nothing yet); following WorldWeaver's builders by special-casing its classes (a mod name in core); reading the 1-arg `BlockSetType(String)` constructor Quark's wood sets build their plates with (its registration isn't read yet; a later slice).
- **Left:** names built by concatenation (Quark's wood sets and variants, 677 of its 809 blockstates still unread); lazy singletons and builders (WorldWeaver/BCLib, so BetterEnd's 9 stone/metal plates stay residue); Balm, owo, Mantle, Registrate, Moonlight jars (not pinned or measured here); Quark's obsidian plate (players-only `getSignalStrength`, its own code; would need a "players" sensitivity read from bytecode); library tags, lang and model parents (#280 scope bullet 1); the mod's own jar-in-jar (#171).
- **Status:** approved (Alex, 2026-10-17): picks 1a 2a 3a 4a 5a, the defaults (PR #321, picks comment 6244701124).
- **Links:** #280, #277, #171, #235, #296, #320, #87, PR #321.

## 2026-10-17: pressure plates convert to one block with a `minecraft:redstone_producer` on its powered permutation, pressed and released by a polling script ported from vanilla `PressurePlateBlock` (approved (Alex, 2026-10-17))

- **Decision:**
  1. **Shape.** A `variants` blockstate drawing exactly `powered` (false/true), each one model reaching vanilla's `block/pressure_plate_up` (unpowered) and `block/pressure_plate_down` (powered) templates unturned, is a **pressure plate**. The two templates (and their parent `thin_block`) are added to the fetched model templates; they are identical in mcmeta's 1.16.5, 1.18.2, 1.19.2, 1.20.1, 1.21.1, 1.21.8 and 26.1 summaries. The block has the up model's geometry and selection box, the down model's on the powered permutation, and no collision (Java: `noCollission`).
  2. **Which convert** (pick 3a, the doors' pick 6a rule): a plate converts when its code is read as vanilla `PressurePlateBlock` or a subclass overriding none of its behaviour (`getSignalStrength`, `getPressedTime`, `checkPressed`, `entityInside`, `tick`, `getSignal`, `getDirectSignal` and BlockBehaviour's other hooks). What presses it and its clicks come from its constructor's constants: `BlockSetType.X` (1.21: `pressurePlateSensitivity`, `pressurePlateClickOn/Off`) and, in 1.20.1, the `PressurePlateBlock$Sensitivity` argument. If the registration isn't read (#280), it converts as the labelled DEFAULT wooden plate (everything presses it, wooden clicks) only when the jar's own `minecraft:wooden_pressure_plates` tag lists it. Anything else is residue naming why: a stone or metal plate whose code isn't read, a mod's own plate class, `WeightedPressurePlateBlock` (its `power` state isn't this shape).
  3. **Detection** (pick 1a). Bedrock's `onStepOn` needs a collision box taller than 3.2 pixels and a plate has none, so the block has `minecraft:tick` every 2 ticks (DEFAULT) and the fixed `pressure_plate.js` reads `Dimension.getEntities` in Java's `TOUCH_AABB` (x/z 1/16..15/16, y 0..4/16). Sensitivity EVERYTHING: any entity; MOBS (Java `LivingEntity`, pick 6a): a player or an entity in Bedrock's `mob` family (armor stands included, as in Java). Never a spectator (`EntitySelector.NO_SPECTATORS`). An entity counts when its position is in the box; Java counts its bounding box meeting it.
  4. **Timing.** `checkPressed`'s rules, ported in `pressure_plate_core.js`: an unpressed plate presses at once (`entityInside`), plays `pressurePlateClickOn`, and re-checks `getPressedTime()` = 20 ticks later (1.20.1, 1.21.1 and 1.21.8 `BasePressurePlateBlock`); a re-check that finds someone holds another 20, one that finds nobody releases it with `pressurePlateClickOff`.
  5. **Redstone** (pick 2a). `minecraft:redstone_producer` `power` 0 on the block and 15 on the powered permutation, `strongly_powered_face` down (Java: `getSignal` on every side, `getDirectSignal` only to the block below). No script workaround: MCPE-229570 (a producer toggled by permutation didn't update its signal) is fixed in 1.21.130, and the in-game check shows a lamp beside the plate lighting and going out. Block format 1.21.130 (pick 4a) and `@minecraft/server` 2.0.0 (`onTick`), so plates raise no pack floor above what they need.
  6. **Placement** (pick 5a). `minecraft:placement_filter` `allowed_faces` ["up"], as Farmer's Delight's feasts already ship: placed on top of a block only. Java's finer support rule (`canSupportRigidBlock` or `canSupportCenter` below) is not carried.
  7. **Sound.** The Bedrock sound vanilla Bedrock plays for the same family (bedrock-samples `block_sounds` `pressure_plate.click_on/off`: `click_on.wooden_pressure_plate`, stone, cherry wood, nether wood, bamboo wood); Bedrock's metal family has no plate events, so a metal plate plays its `power.on/off` (`random.click`, pitch 0.6/0.5). No metal plate converts today.
  Picks (approved by Alex 2026-10-17: 1a 2a 3a 4a 5a 6a, the defaults; this entry is pick 7b of the doors entry below):
  1a `minecraft:tick` every 2 ticks reading the entities in Java's touch box (1b every tick, twice the queries; 1c a 4-pixel collision box so `onStepOn` fires);
  2a the block's own `minecraft:redstone_producer`, power 15 on the powered permutation and strong power down, no script workaround (2b also the bug report's air-swap workaround);
  3a the doors' rule: code read as vanilla `PressurePlateBlock`, else the labelled DEFAULT wooden plate only when the jar's `minecraft:wooden_pressure_plates` tag lists it, else residue; 37/47 convert (3b also convert an untagged `minecraft:pressure_plates` plate as a DEFAULT stone plate);
  4a block format 1.21.130 and `@minecraft/server` 2.0.0 (4b 1.26.0 like trapdoors);
  5a `minecraft:placement_filter` `allowed_faces` ["up"] (5b no filter);
  6a MOBS is a player or an entity in Bedrock's `mob` family (6b any entity with `minecraft:health`).
- **In-game (BDS 1.26.52.3, ingame run 39086356973 on 6f76f55):** all 37 converted plates (Cluttered 10, BOP 10, BetterEnd 10, Tinkers 4, Quark 3) placed on stone beside a redstone lamp: idle unpowered and lamp off; an armor stand spawned on it presses it within 8 ticks and lights the lamp; removing the stand releases it after the re-check and the lamp goes out; a stick dropped on it presses it; broken, it drops exactly one plate. 0 content-log errors in every run. Not exercised in game: a mobs-only plate (none converts; node tests cover it) and a player's own placement.
- **Why:** pressure plates are the next sub-class of the #296 `block` residue (47 blockstates in the corpus, deco and gauntlet sets: BetterEnd 19, BOP 10, Cluttered 10, Quark 4, Tinkers 4). Without the runtime a plate would look right and do nothing.
- **Rejected:** a 4-pixel collision box so `onStepOn` fires (pick 1c: changes how the plate walks, and Java plates have no collision); a tick every tick (pick 1b: twice the queries for at most a tick of latency); the bug report's air-swap workaround (not needed after 1.21.130); a `minecraft:health` test for MOBS (counts XP orbs and end crystals); defaulting an untagged plate to a stone plate (BetterEnd's terminite and thallasium plates are metal, Quark's obsidian plate is players-only code: guessing would invent a detection rule).
- **Sources:** Mojang's 1.21.1 client jar and client.txt (`BasePressurePlateBlock` TOUCH_AABB, getPressedTime, checkPressed, entityInside, tick, getDirectSignal; `PressurePlateBlock#getSignalStrength`; `BlockSetType#<clinit>`), 1.20.1 (client sha1 0c3ec587af28e5a785c0b4a7b8a30f9a8f78f838: `PressurePlateBlock(Sensitivity, Properties, BlockSetType)`) and 1.21.8 (a19d9badbea944a4369fd0059e53bf7286597576: `getPressedTime` 20), read 2026-10-17; learn.microsoft.com minecraft:redstone_producer ("requires a format version of at least 1.21.120"), https://learn.microsoft.com/en-us/minecraft/creator/reference/content/blockreference/examples/blockcomponents/minecraftblock_redstone_producer ; learn.microsoft.com minecraft:tick, https://learn.microsoft.com/en-us/minecraft/creator/reference/content/blockreference/examples/blockcomponents/minecraftblock_tick ; Bedrock Wiki Block Events (step events need a collision box taller than 3.2 pixels), https://wiki.bedrock.dev/blocks/block-events ; MCPE-229570 (Fix Versions 1.21.130), https://mojira.dev/MCPE-229570 ; minecraft.wiki Block components (`redstone_producer` in a permutation needs it on the block too from format 1.26.20), https://minecraft.wiki/w/Block_components ; Mojang/bedrock-samples@46ba6ea9 resource_pack/sounds.json `block_sounds` and behavior_pack/entities (`type_family`); misode/mcmeta `*-summary` model data.
- **Status:** approved (Alex, 2026-10-17): picks 1a 2a 3a 4a 5a 6a, the defaults (PR #320, picks comment 6244244536).
- **Links:** #296, #277, #280, PR #320.

## 2026-10-17: geodes a biome modifier adds convert to `minecraft:geode_feature`; plant patches are explained residue (approved (Alex, 2026-10-17))

- **Decision:** `converters/features.py` (no mod names) reads every Forge/NeoForge
  add/remove biome modifier, and every Fabric code row (#318), whose features
  are wholly ores, vanilla `minecraft:geode`s or the plant patch family
  (`random_patch`, `flower`, `no_bonemeal_flower`, `simple_block`, and
  `random_selector`/`simple_random_selector` of them), with Minecraft's own
  placement types on the placed feature. A geode becomes a Bedrock
  `minecraft:geode_feature` (format 1.13.0) plus a feature rule under the
  approved ore rules (dimension tags, `rarity_filter` -> `scatter_chance`,
  `height_range`, Nether `below_top` and biome lists/exclusions residue,
  removals residue). Exact fields: the five single-block providers ->
  `filler`/`inner_layer`/`alternate_inner_layer`/`middle_layer`/`outer_layer`
  (a block the pack ships or a same-id vanilla block); `outer_wall_distance`,
  `distribution_points`, `point_offset` -> `min_`/`max_`; `crack.*`,
  `noise_multiplier`, the two chances, `placements_require_layer0_alternate`,
  `invalid_blocks_threshold` -> the same names, checked against Bedrock's
  ranges (Java: minecraft.wiki "Amethyst Geode" oldid 3811952; Bedrock:
  bedrock-samples `documentation/Features.html`, MicrosoftDocs
  `Features/minecraftGeode_feature.md`). A geode leaving any field to Java's
  defaults is residue. A patch is `worldgen_feature` residue with the first
  reason that applies (a removal, the mod's own nested feature/placement types,
  an unmapped biome tag, else pick 5); a remove modifier over such features is
  residue of its own. The validator's `xref.feature` checks a geode's blocks.
  In-game `geode_generate`: the check pack carries a test-only copy of each
  geode rule without `scatter_chance` (pick 4) and asserts the crystal blocks
  appear in fresh chunks.
  Picks (approved by Alex 2026-10-17: 1a 2a 3a 4a 5a, the defaults):
  1a convert a geode, dropping the Java fields Bedrock has no field for:
  `layers` (shell thickness; Java defaults 1.7/2.2/3.2/4.2), `cannot_replace`
  and `invalid_blocks` (block tags), and `min_gen_offset`/`max_gen_offset`
  -m/m (a Chebyshev cutoff about the start) written as `max_radius` m;
  asymmetric offsets residue; each geode gets an "approximated geode" note
  naming every dropped field and value (1b convert only when those fields equal
  vanilla's, which no corpus geode does; 1c every geode residue);
  2a inner placements by block name only: Java's `GeodeFeature.place` sets
  FACING to the side each bud grows on and WATERLOGGED from the fluid there
  (1.20.1 client jar, class `dku` through Mojang's client mappings), Bedrock's
  `inner_placements` carry one fixed state and its docs don't say whether the
  engine turns them; the in-game check reports the `block_face` found (2b write
  Java's literal `facing=up` as `block_face=up`; 2c residue);
  3a Java's `local_modifications` step -> `before_underground_pass` (the
  enum's order puts it before `underground_ores`; Bedrock "Earlier passes in
  the list are guaranteed to occur before later passes"), ores staying in
  `underground_pass` (3b `underground_pass` with the ores);
  4a the in-game geode check uses a test-only every-chunk copy of the rule in
  the check pack, since 1-in-256 geodes don't show in a 3x3-chunk scan (4b
  scan more chunks with the real rule; 4c report-only);
  5a patches stay residue with reasons until a corpus mod's patch clears the
  biome/removal/code gates; then the tries/xz_spread scatter mapping
  (Java's `nextInt(s+1)-nextInt(s+1)` offsets vs Bedrock's `triangle`) is
  decided on that case (5b build the mapping now on fixtures only).
  Measured: Tinkers' Construct earth geode converts (3 files); ichor, ender
  and sky geodes, Botania's mystical flowers and mushrooms (24 files) and
  Supplementaries' wild flax (3 files) move from `unowned` to explained
  `worldgen_feature` residue.
- **Why:** Bedrock's geode feature is the same algorithm family with fewer
  knobs; converting with every dropped field named keeps the geode in the
  world without hiding what changed, the #299 "approximated loot" pattern.
- **Rejected:** guessing Bedrock's built-in shell thickness as an exact match
  (undocumented); a Tinkers adapter (the reader is generic).
- **Status:** approved (Alex, 2026-10-17): picks 1a 2a 3a 4a 5a, the defaults (PR #319, picks comment 6241942660).
- **Links:** #281, #277, PR #319, PR #317, PR #318.

## 2026-10-17: ores a Fabric mod attaches in code are read from its bytecode and converted like modifier ores (approved (Alex, 2026-10-17))

- **Decision:** new core module `src/portkit/biomecode.py` (no mod names)
  reads Fabric API `BiomeModifications.addFeature(selector, step, key)` and
  `BiomeModifications.create(id).add(phase, selector, (sel, ctx) ->
  ctx.getGenerationSettings().addFeature/removeFeature(step, key))` from the
  jar's classes (Mojang names; Fabric intermediary through the #235 mapping),
  starting at the `fabric.mod.json` `main` (Quilt `init`) entrypoints and
  following only mod methods that reach `net.fabricmc.fabric.api.biome.v1`.
  Each method runs once over its control-flow graph with values joined where
  paths meet; a call's guards are the undecided branches it is control
  dependent on (Ferrante-Ottenstein-Warren), in its method and every caller.
  A branch on a mod's own undecided no-argument boolean method is a named
  gate (`MythicMetalsConfig.adamantite()`). Each attachment becomes a
  modifier-shaped row for `converters/features.py`, which converts it under
  the approved ore rules (1a-6a) or files `worldgen_feature` residue with the
  reason. Selectors read: `BiomeSelectors.tag`, `foundInOverworld`,
  `foundInTheNether`, `foundInTheEnd`; anything else (`all`, `includeByKey`,
  `Predicate.and/or/negate`) is residue. A biome tag resolves through the
  jar's own tag files only down to vanilla dimension tags; a biome id or any
  other tag is residue (never a guess from a tag's name, 5b rejected). A
  biome call no entrypoint reaches is only noted (its ore stays `unowned`).
  `SAME_ID_BLOCKS` gains `minecraft:calcite` and `minecraft:smooth_basalt`
  (bedrock-samples blocks.json `calcite`, `smooth_basalt`).
  Picks (approved by Alex 2026-10-17: 1a 2a 3a 4a 5a, the defaults):
  1a a config-gated attachment is decided at the gate's cited default: a
  `code_gate` entry in `config_flag_defaults.json` maps the config class's
  `<option>()Z` methods to flags (Mythic Metals 0.24.6+1.21: 25 owo-config
  options, `MythicConfigModel.java` L13-61 at 7332378b, all `true`), the same
  rule as recipe load conditions (#183 option C), noted, `--config
  mythicmetals.<option>=false` turns one off; an uncited gate is residue
  (1b: every gated attachment residue);
  2a Fabric's `c:is_overworld`, `c:is_nether`, `c:is_end` are their vanilla
  tags (fabric-convention-tags-v2 2.12.0+c3656daa19: `#minecraft:is_*` plus
  an optional legacy `#c:in_*` defined nowhere in Fabric API 0.116.17+1.21.1),
  table `CONVENTION_BIOME_TAGS` keyed by the pinned loader tag set (2b residue);
  3a `foundInOverworld/TheNether/TheEnd` ("all biomes that would normally spawn
  in" that dimension, BiomeSelectors.java L61-84) map like the vanilla
  dimension tags; biomes other mods add to a dimension are not covered, as for
  tags (3b residue);
  4a biome-list tags (`c:is_aquatic`, `c:is_mountain`/`c:is_hill`,
  `c:is_jungle` + `minecraft:lush_caves`) stay residue until a cited Java to
  Bedrock biome table exists (4b build that table now);
  5a the in-game check gets `portkit ingame run --world default` (BDS
  `level-type=DEFAULT`, ore checks only) so Overworld ores are counted in fresh
  chunks; a rule whose scanned range holds none of the blocks it may replace
  is reported as skipped, not failed (5b no Overworld check).
  Measured on Mythic Metals 0.24.6+1.21: 22 of 25 ores convert (17 Overworld,
  4 Nether, 1 End); aquarium, osmium and prometheum are 4a residue. The code,
  not the option names, decides the gate: `banglum()` gates both banglum ores,
  `kyber()` calcite kyber, `runite()` deepslate runite (the options
  `netherBanglum`, `calciteKyber`, `deepslateRunite` gate nothing here).
- **Why:** Fabric has no biome-modifier JSON; the attachment exists only as
  code, and reading it from the bytecode (Alex's pick 5a on PR #317) gives the
  exact selector, step and key instead of a naming guess.
- **Rejected:** converting by the `<ore>_ore_biomes` tag naming convention
  (5b, a guess); a mod-specific adapter for Mythic Metals (the reader is
  generic); path enumeration (2^n paths for n sequential config ifs).
- **Status:** approved (Alex, 2026-10-17): picks 1a 2a 3a 4a 5a, the defaults (PR #318, picks comment 6240982325).
- **Links:** #281, #277, PR #318, PR #317 picks comment 6239348623.

## 2026-10-17: ores a Forge/NeoForge biome modifier adds convert to a Bedrock `minecraft:ore_feature` plus a feature rule (approved (Alex, 2026-10-17))

- **Decision:** `converters/features.py` (#281, first slice) reads
  the `data/<ns>/{forge,neoforge}/biome_modifier/` files of type
  `<loader>:add_features` whose every feature is a vanilla `minecraft:ore`
  placed with vanilla placements (`count`, `in_square`, `height_range`,
  `rarity_filter`, `biome`). Each placed feature becomes
  `features/<configured>.json` (`minecraft:ore_feature`, format 1.13.0 as in
  Mojang's examples) and `feature_rules/<placed>_feature_rules.json`
  (`placement_pass`, `minecraft:biome_filter`, scatter `distribution`), or
  residue kind `worldgen_feature` (explained, agent `SKIP_KINDS`) naming why.
  A modifier holding anything else is left for the other passes
  (`code_worldgen`, `unowned`). Cited tables: `src/portkit/data/worldgen.py`.
  Exact mappings: `discard_chance_on_air_exposure` (same field on Bedrock),
  targets in order to `replace_rules` (`block_match` of a same-id vanilla
  block, `tag_match` of `stone_ore_replaceables`, `deepslate_ore_replaceables`,
  `base_stone_nether`, `base_stone_overworld`), constant `count` ->
  `iterations`, `in_square` -> x/z uniform `[0, 15]`, `uniform` heights ->
  `uniform` extents (both inclusive), anchors against each edition's
  dimension bounds, `rarity_filter` -> `scatter_chance` only before any count
  above 1, `underground_ores`/`underground_decoration` -> `underground_pass`,
  `#minecraft:is_nether` -> biome tag `nether` (the same five biomes).
  Alex's picks (PR #317, picks comment 6239348623), the defaults:
  1a Java `size` -> Bedrock `count`; 2a a trapezoid with no plateau ->
  `triangle`, with a plateau residue; 3a `#minecraft:is_overworld` -> tag
  `overworld` or `overworld_generation` (Bedrock's legacy hills/mutated
  biomes included), `#minecraft:is_end` -> `the_end`; 4a `below_top` in the
  Nether (Java's top 255, Bedrock's 127) is residue; 5a Fabric ores, attached
  in code, stay `unowned` (a bytecode reader for `BiomeModifications` is a
  follow-up); 6a a feature some `remove_features` modifier names is residue.
  Validator: `features/` documents must carry a feature type key, and
  `xref.feature` (identifier = file name, rule -> a declared feature, ore ->
  a declared block). In-game (#238): `ore_generate` loads fresh chunks of the
  rule's dimension (not the flat Overworld) and counts the ore it generated.
  Measured: Tinkers' Construct cobalt_ore_large converts (gauntlet ingame run
  39060971192: 82 `tconstruct:cobalt_ore` generated in y 8..32 of a 48x48
  Nether area, 0 content-log errors); cobalt_ore_small is 4a residue.
- **Why:** ores are the one worldgen every content mod has, and Bedrock's ore
  feature and feature rules carry Java's vein, targets and per-chunk scatter.
  The 14-jar survey (gauntlet + corpus) found few data-attached vanilla ores:
  Create, IE and Mekanism ores use their own placement or feature types
  (`code_worldgen`), Mythic Metals' are Fabric (code-attached), BOP's sits only
  in its own biomes. Where Bedrock can't state Java's numbers exactly, the
  feature stays residue (picks 2a, 4a, 6a).
- **Rejected:** converting Fabric ores by the `<ore>_ore_biomes` tag naming
  convention (a guess, #87); a Bedrock biome for each Java biome tag.
- **Status:** approved (Alex, 2026-10-17): picks 1a 2a 3a 4a 5a 6a, the defaults (PR #317, picks comment 6239348623).
- **Links:** #281, #277, PR #317.

## 2026-10-17: worldgen typed with the mod's own classes is `code_worldgen`; data only another mod reads is `other_mod_data` (approved (Alex, 2026-10-17))

- **Decision:** two new explained residue kinds (agent `SKIP_KINDS`), filed from
  leftover `unowned` data by `portkit.worldgen.refine` after the data-tag pass.
  Core and generic, no mod names:
  - `code_worldgen`: a `worldgen/configured_feature/` file whose `type`, a
    `worldgen/placed_feature/` file with a `placement` modifier whose `type`, or
    a `worldgen/template_pool/` file with an `element_type`, in one of the jar's
    own namespaces. Those types are registry entries only code registers, so the
    file is the mod's Java code. The reason names the type and the jar's classes
    whose constant pool holds its path, the one that also names the jar's own
    subclass of Minecraft's `Feature` / `PlacementModifier` / pool element first
    (#87). Worldgen built only from `minecraft:` types stays `unowned` (#281); so
    does a placed feature with only vanilla placements, even of a code feature.
  - `other_mod_data`: `data/<ns>/<dir>/` where `<dir>` is not a folder Minecraft
    (1.16-1.21.x) or a loader reads, and every file is a JSON object whose
    top-level `type` or `target_*` names a namespace that is not the jar's own,
    vanilla's, `c` or a loader's. One entry per folder; the reason names the
    other mod's namespace and the jar's classes that name it.
  - A structure template (`structure[s]/<path>.nbt`) every data file naming it
    is residue of these kinds goes with them: `code_worldgen` when one is, else
    `other_mod_data`. A template named by nothing, or by a file still `unowned`,
    stays `unowned`.
  - The Waystones adapter (`adapters/waystones/worldgen.py`, its new `convert`
    hook) files the 5 village pools `worldgen/template_pool/village/<biome>/waystones.json`
    as `code_worldgen` (nothing in the data names them;
    `mixin/JigsawPlacementPlacerMixin#forceWaystonePool` turns a `.../houses`
    pool into `waystones:.../waystones` by config `worldGen.spawnInVillages`) and
    `unbreakables/generated_waystones.json` as `other_mod_data`
    (`compat/UnbreakablesIntegration` registers its conditions through
    `net/blay09/mods/unbreakables/api/UnbreakablesAPI`). Each claim checks that
    the jar's classes hold the cited class and strings, else the file stays
    `unowned`. The reasons say only what the jar shows; whether a Bedrock add-on
    can add pieces to vanilla villages was not checked.
  - Waystones 21.1.46 (NeoForge and Fabric): 20 features/placements, 5 pools and
    2 templates `code_worldgen`; `lithostitched/` 5, `rs_pieces_spawn_counts/` 12,
    `rs_pool_additions/` 22, `unbreakables/` 1 and the template
    `village/common/waystone_waterlogged.nbt` (named only by the Repurposed
    Structures files, so not "with its pools" as the picks comment said)
    `other_mod_data`. Waystones has no `unowned` left and is done (gauntlet
    run 39056824522: done 36 -> 37/50).
  - Other gauntlet mods, same rule, no coverage change: `code_worldgen` Twilight
    Forest 164, Biomes O' Plenty 107, Immersive Engineering 13, Tinkers 7 files;
    `other_mod_data` Immersive Engineering 36 (its Repurposed Structures
    `rs_*` data and the 12 engineer-house templates only those name).
    `unowned [data/<ns>/worldgen/]` 8 mods/979 -> 7/663 files.
  - Pack bytes are unchanged: explained entries add no converted files, so
    coverage and mean coverage don't move.
- **Why:** Alex's picks 1a, 2a and 3a on PR #316 (comment 6237827326): what the
  files generate, and where, is Java code or another mod's, and converting
  them would invent it; but they are not a portkit gap either, so Waystones can
  count as done (#277 rule 6).
- **Rejected:** 1b converting the wild waystones to Bedrock features
  (needs the spawn rate from WaystonePlacement's bytecode and world-generated
  waystone naming, its own issue); 2b shipping the templates as standalone
  `.mcstructure` features (Java never spawns them outside a village); 3b all
  other-mod data in the Waystones adapter only; 1c/3c leaving them `unowned`.
- **Links:** #277, #281, #87, PR #316.

## 2026-10-17: an item-model template only emitted block items inherit is claimed with them

- **Decision:** a `models/item/` file in the parent chain of an emitted block's
  item model is claimed with it when no item is registered under the
  template's name (`registered_ids(items_only=True)`). A registered template,
  or one whose child blocks did not convert, keeps its `item` residue.
- **Why:** such a template is a display parent, not an item (Waystones'
  portstone/sharestone, BOP `rose_quartz_bud`, CfB `oven`); it ships with its
  children.
- **Rejected:** reporting it as an item that failed to convert.
- **Links:** #277, PR #316.

## 2026-10-17: trapdoors convert as one block on `placement_position` (vertical_half) + `placement_direction`, opened by hand and redstone through the door's rules

- **Status:** approved (Hark, high confidence under Alex's 2026-10-17 pick 7a of the doors entry below, whose detection rule, runtime and sources it reuses unchanged; Alex's 2026-10-14 campaign order).
- **Decision:**
  1. **Shape.** A `variants` blockstate that draws exactly `facing`, `half` (bottom/top) and `open`, with all 16 variants on vanilla's six trapdoor templates turned by quarter turns, is a **trapdoor**. Java's `powered` and `waterlogged` draw nothing and are dropped. The templates are `block/template_trapdoor_{bottom,top,open}` and `block/template_orientable_trapdoor_*`, added to the fetched model templates; they are identical in mcmeta's 1.16.5, 1.18.2, 1.19.2, 1.20.1, 1.21.1, 1.21.8 and 26.1 summaries. An orientable trapdoor's open top half is `x` 180.
  2. **Which convert** (pick 6a's rule): convert when the code is read as vanilla `TrapDoorBlock`, or a subclass overriding none of its behaviour (`useWithoutItem`, `toggle`, `playSound`, `neighborChanged`, `getStateForPlacement`, `updateShape`, `getShape`, `onExplosionHit` and BlockBehaviour's other hooks). Whether a hand opens it, and its sounds, come from the `BlockSetType` constant it was built with. If the registration isn't read (#280), convert as a labelled DEFAULT wooden trapdoor only when the jar's own `minecraft:wooden_trapdoors` tag lists it. Anything else is residue that names what was found.
  3. **Placement.** One block, no multi_block. `minecraft:placement_position` sets `minecraft:vertical_half` and `minecraft:placement_direction` sets `minecraft:cardinal_direction`. Java `half` is `vertical_half`. Java `facing` F is `cardinal_direction` == opposite(F): `TrapDoorBlock#getStateForPlacement` takes the opposite of the player's direction on a top or bottom face, and the clicked side face otherwise, which is the same whenever the player faces that side. The approximation is a side face clicked at a slant, and the notes say so. There are 16 permutations on facing, half and the custom `open` state (geometry and boxes only).
  4. **Behaviour.** The fixed `trapdoor.js` runs on `door_core.js`, because `TrapDoorBlock#useWithoutItem` and `#neighborChanged` are `DoorBlock`'s for one block. `onPlayerInteract` toggles open when the `BlockSetType` allows a hand. `onRedstoneUpdate` with `minecraft:redstone_consumer` (min_power 0) sets open = powered on a change of power, with a sound when open changes. `onPlace` opens a trapdoor that is placed already powered. Block format 1.26.0 (redstone_consumer with no experiment) and `@minecraft/server` 2.5.0 (onRedstoneUpdate), as for doors.
  5. **Look and sound.** Vanilla trapdoor geometry comes from the templates. Sounds are vanilla Bedrock's trapdoor sounds for the family (`open.wooden_trapdoor` / `close.wooden_trapdoor`, iron, cherry, nether wood, bamboo; copper plays `open_trapdoor.copper` for both, as vanilla Bedrock's copper block_sounds do). The 1.21.1 `BlockSetType` passes each family's `*_TRAPDOOR_*` events, so the trapdoor family is the door's.
- **Why:** trapdoors are the next sub-class of the #296 `block` residue (48 blockstates in the corpus and deco sets). Bedrock has the trait for exactly this ("placement_position ... vertical_half ... blocks that behave like slabs or trapdoors"). The door's rules already carry use and redstone.
- **Not carried** (named in each block's note): waterlogging, a wind charge opening it (`onExplosionHit`), mob pathing.
- **Rejected:** a static trapdoor (looks like one, never opens); adding `block_face` so a slanted side click matches Java (96 state combinations for an edge case; Bedrock Wiki Custom Trapdoors uses cardinal_direction only); per-mod adapters (no mod in core).
- **Sources:** learn.microsoft.com Using Block Traits ("By using the `minecraft:placement_position` trait to set the `minecraft:block_face` ... and `minecraft:vertical_half` ... you can easily create blocks that behave like slabs or trapdoors"; placement_direction "contains information about the direction the player is facing when the block is placed"), https://learn.microsoft.com/en-us/minecraft/creator/reference/content/blockreference/examples/blocktraits ; learn.microsoft.com placement_position, https://learn.microsoft.com/en-us/minecraft/creator/reference/content/blockreference/examples/traits/placement_position ; learn.microsoft.com minecraft:redstone_consumer, https://learn.microsoft.com/en-us/minecraft/creator/reference/content/blockreference/examples/blockcomponents/minecraftblock_redstone_consumer ; learn.microsoft.com BlockCustomComponent (`onPlace`, `onPlayerInteract`, `onRedstoneUpdate`), https://learn.microsoft.com/en-us/minecraft/creator/scriptapi/minecraft/server/blockcustomcomponent ; Bedrock Wiki Custom Trapdoors, https://wiki.bedrock.dev/blocks/custom-trapdoors ; Mojang/bedrock-samples@46ba6ea9 resource_pack/sounds.json `block_sounds` (`trapdoor.open` / `trapdoor.close`); Mojang's 1.21.1 client jar and client.txt (`TrapDoorBlock`, `BlockSetType#<clinit>`), read 2026-10-17.
- **Links:** #296, #277, #280, #87.

## 2026-10-17: doors and plain two-tall blocks convert on Bedrock's `minecraft:multi_block` trait; a door's hinge, hand use and redstone are a fixed script ported from vanilla `DoorBlock`

- **Status:** approved (Alex, 2026-10-17): picks 1a 2a 3a 4a 5a 6a 7a, the defaults (PR #313, picks comment 6235234464).
- **Decision:**
  1. **Shapes.** A `variants` blockstate drawing exactly `facing`, `half` (lower/upper), `hinge`, `open` (Java's `powered` draws nothing and is dropped) with all 32 variants on vanilla's eight door templates (`block/door_{bottom,top}_{left,right}[_open]`, added to the fetched model templates; identical in mcmeta's 1.19 through 26.1 summaries) is a **door**. A `variants` blockstate drawing only `half` (one model per half, no turn) is a **plain two-tall block** (tall flowers and grasses).
  2. **Both halves are one block** (pick 2): `minecraft:multi_block` (`direction` up, 2 parts), block `format_version` 1.26.40, the first with no experiment for vertical multi-blocks (pick 5: the pack's engine floor follows). Bedrock places part 1 above part 0, breaks both together and drops only the broken part's loot. A door also uses `placement_direction` (`cardinal_direction`, the one other trait allowed), `minecraft:movable` popped, 32 permutations on part, facing, hinge and open (geometry and boxes only).
  3. **Which code** (pick 6): a door converts when its registration is followed (`blockcode`) to vanilla `DoorBlock` or a subclass overriding none of the door's behaviour methods, taking whether a hand opens it and its sounds from the `BlockSetType` constant it was built with (`data/block_set_types.py`, read from the 1.21.1 client jar); when the registration isn't followed (#280), the labelled DEFAULT (opens by hand, wooden sounds) only if the jar's own `minecraft:wooden_doors` tag lists it; otherwise residue naming why. A class overriding door behaviour stays residue. Two-tall blocks: vanilla `DoublePlantBlock` / `TallFlowerBlock` with no override, or unread (DEFAULT, labelled). No mod is named in core.
  4. **Behaviour** (pick 1, scripted): `portkit/runtime/door.js` + `door_core.js`, a port of `DoorBlock#getHinge`, `useWithoutItem` and `neighborChanged`, as one custom component per namespace (`beforeOnPlayerPlace`, `onPlace`, `onPlayerInteract`, `onRedstoneUpdate`) and `minecraft:redstone_consumer` `min_power` 0 (pick 3: every power change reaches the script). Every state change is written to both parts. The runtime needs `onRedstoneUpdate`, first in the stable `@minecraft/server` 2.5.0 typings (Bedrock 1.26.0), so a pack shipping it declares 2.5.0 (`// portkit-requires:` line, `pack.script_version`). Sounds are the Bedrock sound definitions vanilla plays for the same family (bedrock-samples `sounds.json`); no open/close animation; the item is the block's own (shows the lower half, pick 4).
  5. **Loot** (#299): Java runs the lower half's table whichever half is broken, so a `block_state_property` `{half: lower}` test on a paired block is read as holding (`loot.fold_paired_half`); Bedrock drops the broken part's loot once.
  6. **Not carried, said per block in the notes:** villagers opening doors, the sturdy-block-below rule, waterlogging, a plant's survival rules and bone meal, collision for plants (none, the DEFAULT).
- **In-game (BDS 1.26.52.3, ingame run 39040957501 and the rerun on the PR head):** Cluttered's 19 doors, Quark's 3 and BOP's 10 doors and 8 two-tall plants, Botania's 16: both parts placed by script read back as one block; a redstone block beside the lower half opens both halves and removing it closes both (so `onRedstoneUpdate` does fire when power drops to 0); after the script's per-part writes the halves stay paired; breaking the upper part removes the lower and leaves exactly one item. Script `setPermutation` of part 0 alone places only the lower half (the `setblock` command places both); a player's placement is Bedrock's own multi-block placement, which BDS can't exercise headless, so hinge choice and hand use are covered by node tests (`tests/js/door_core.test.mjs`), not in-game. First run: BOP's 20 content-log errors were redstone updates arriving for a door a command had just replaced with air; the runtime now ignores an event whose block is no longer that door.
- **Why:** doors are the largest sub-class of the #296 `block` residue (59 blockstates in the corpus and deco sets; 46 convert: Cluttered 19, BOP 10, BetterEnd 10, Tinkers 4, Quark 3; the gauntlet's Twilight Forest adds 7, its sorting door stays residue: its models have no vanilla parent). Two-tall: 25 convert (Botania 16 double flowers, BOP 8, Farmer's Delight Fabric's wild rice 1, all DEFAULT: their registrations aren't read) and Bedrock now has the vanilla door's own mechanism for custom blocks. Without the script a door would be a two-tall block that never opens.
- **Rejected:** a static door (no use, no redstone: looks like a door, isn't one); pairing two single blocks by script (breaking, piston and placement edge cases the trait handles natively); a redstone tick poll (cost on every door, every tick; the event exists); per-mod door adapters (no mod in core, and the tag rule already covers unread wooden doors); a static fallback below 1.26.40 (needs the experiment, or loses the pairing).
- **Sources:** learn.microsoft.com Block Traits: multi-block ("requires Bedrock Edition 1.26.10 or higher. For vertical directions if the block format_version is less than 1.26.40 then it requires that the Upcoming Creator Features experimental toggle is set on"; only `placement_direction` with `cardinal_direction` alongside; `minecraft:movable` popped or immovable), https://learn.microsoft.com/en-us/minecraft/creator/reference/content/blockreference/examples/traits/multi_block ; learn.microsoft.com minecraft:redstone_consumer (format 1.21.130+, no experiment from block format 1.26.0, `min_power` 0 "meaning event is always emitted", not on permutations), https://learn.microsoft.com/en-us/minecraft/creator/reference/content/blockreference/examples/blockcomponents/minecraftblock_redstone_consumer ; learn.microsoft.com BlockCustomComponent (`beforeOnPlayerPlace`, `onPlace`, `onPlayerInteract`, `onRedstoneUpdate`), https://learn.microsoft.com/en-us/minecraft/creator/scriptapi/minecraft/server/blockcustomcomponent ; Bedrock Wiki Multi-Blocks (only the broken part drops loot; `beforeOnPlayerPlace` only for part 0; states other than the part must be equal and are written to every part; the block item shows part 0), https://wiki.bedrock.dev/blocks/multi-blocks ; MCPE-229570 (a custom `redstone_producer` toggled by permutation didn't update its signal; fixed in 1.21.130), https://mojira.dev/MCPE-229570 , relevant to pressure plates next, not to doors (consumers only).
- **Links:** #296, #277, #299, #280, #218.

## 2026-10-17: a smithing transform's template and addition carry their Bedrock slot tag, a block's on its item form; otherwise the recipe goes to residue

- **Decision:** every `recipe_smithing_transform` portkit writes has a template carrying `minecraft:transform_templates` and an addition carrying `minecraft:transform_materials` (learn.microsoft.com, Recipe Documentation - Smithing Transform Recipe: items "must have" the tag "to be accepted into the respective UI slot"; BDS 1.26.52.3 refuses the recipe otherwise, ingame run 38996897674).
  1. The pack's own item in either slot gets the tag (as since #263). The pack's own **block** in either slot now gets it on its item form: its own item file if it has one, else an item replacing the block's item through `minecraft:block_placer` `replace_block_item` (the #293 mechanism, `recipes._block_item`). The Java recipe is the evidence the item goes in that slot. Not the base: that must be armor or a tool (#268), which a block isn't.
  2. A vanilla item must be Bedrock's own member of the tag: `minecraft:netherite_upgrade_smithing_template` (template) and `minecraft:netherite_ingot` (addition), the only members minecraft.wiki's Item tag (Bedrock Edition) lists (oldid=3758407; MS Learn: the addition's "only accepted item is minecraft:netherite_ingot"). A vanilla item can't be given a tag, so any other vanilla template or addition sends the recipe to the residue with the reason, in the withdraw pass (`withdraw_unequipped_smithing`) and the new validator rule `recipe.smithing_slot` alike. A pack item or block that ends up without the tag is refused the same way.
  3. When a withdrawn recipe was the only reason an item form was written for a block, that item form is removed again (the block keeps its own item).
- **Why:** Create's `netherite_backtank_from_netherite` takes `create:copper_backtank` as the addition; the backtank ships as a block, so the recipe shipped without the tag and was Create's one content-log error, keeping it out of the in-game matrix. Tagging the block's item form is what Java does (the backtank item goes in the slot) and uses the item-form mechanism vanilla itself uses (bedrock-samples `items/shelf_mushroom.json`).
- **Rejected:** withdrawing every recipe whose slot item ships as a block (loses a recipe Bedrock can take); tagging vanilla items (an add-on can't); rewriting as a crafting recipe (drops the smithing table and what the upgrade carries over, Alex 2026-10-16, #268).
- **Links:** #305, #263, #268, #270, #293.

## 2026-10-17: a renamed vanilla texture (`oak_planks` -> `planks_oak`) maps through a pinned, pixel-checked per-name table; pairs that look different stay residue

- **Status:** approved (Alex, 2026-10-17). Extends #220 (pick 2) and the 2026-10-17 subfolder entry below (#308), whose "call for Alex" this settles.
- **Decision:** a Java vanilla texture name with no Bedrock file of that name, whose Bedrock atlas short name of exactly that name shows one file of another name, maps to that file only when the pair is in `src/portkit/data/vanilla_texture_aliases.py` (`ALIASES`). The converter then applies #220's rules to that file unchanged: a plain one-file short name is named directly (`oak_planks`), a dressed one (tint, overlay) gets a pack entry naming the file (`<ns>:vanilla/block/double_plant_grass_top`), vanilla-animated files stay residue. Pairs the check found different (`DIFFERS`) stay residue with that reason; a pair whose pinned atlas no longer shows the table's file stays residue. `MAP_RENAMED` is removed.
- **Source of the names:** Mojang/bedrock-samples `resource_pack/textures/terrain_texture.json` and `item_texture.json` at the pinned commit (`portkit.data.COMMIT` 46ba6ea9, held equal to the table's `BEDROCK_COMMIT` by a test). A pair exists only where Bedrock's own atlas files a short name of exactly the Java name; nothing is hand-written. Java names with no such short name (`bricks`, `sandstone`, `red_sandstone`, `mossy_cobblestone`, `nether_bricks`, `red_nether_bricks`, `end_stone_bricks`, `prismarine`, a set of 3) have no cited pairing and stay residue.
- **Pixel-check method** (`scripts/check_vanilla_texture_aliases.py --jar <client.jar> [--check]`, maintenance only, needs Pillow): candidates are every atlas short name showing exactly one file where Bedrock has no file of that name (top level or one folder down) and the Java client jar has `textures/block/<name>.png` (`item/` for the item atlas). Java side: Minecraft 1.21.11 client jar, sha1 `ba2df812c2d12e0219c489c4cd9a5e1f0760f5bd` (Mojang launcher manifest); Bedrock side: `resource_pack/<file>.png` (else `.tga`) at the pinned commit. Both decoded to RGBA; a pair is kept when width, height and every pixel's alpha match and every pixel with alpha > 0 has the same colour (colour under fully transparent pixels is ignored). Nothing from the jar or the Bedrock art is kept in the repo, only the name pairs.
- **Result:** 231 candidates (terrain 218, item 13); 203 look the same (181 byte-for-byte equal pixels, 22 equal in every visible pixel) and are in `ALIASES`; 28 differ and are in `DIFFERS`: the 16 `*_stained_glass_pane_top`, `piston_top` (`piston_inner`), `bubble_coral_block`, `fire_coral_block`, `purple_glazed_terracotta`, `short_grass`, `spruce_planks` (one pixel), `lilac_bottom`/`lilac_top`, the 3 `command_block_*` mipmaps (size) and `conduit` (size). (The #308 entry's 26 of 225 was the same check over the terrain lane without the 2 lilac textures, whose Bedrock files are RLE TGAs; the committed script reads them.)
- **Why:** the short name sharing Java's name is a cited Bedrock fact, but not a promise of the same picture; the pixel check is what makes each pair true, and pinning both sides makes it repeatable. Measured (Quark 4.1-487): 17 vertical slabs (oak, birch, jungle, acacia, dark oak, andesite, diorite, granite and their polished forms, stone brick, mossy stone brick, smooth stone, cut sandstone, cut red sandstone, dark prismarine), 5 bookshelves, 5 vertical planks and the stone brick lamp convert, with their 17 slab loot tables; validator 0 errors. Spruce vertical slab stays residue (`spruce_planks` differs by one pixel) and so do the 8 slabs with no Bedrock name.
- **Rejected:** turning every same-named short name on (28 of 231 wrong); a hand-written Java -> Bedrock name table for the names Bedrock lacks (#87, #220); the nearest-named file; keeping Java pixels or hashes of them in the repo.
- **Links:** #296, #220, #308, #277, #87.

## 2026-10-17: a vanilla texture Bedrock files one folder down (`textures/blocks/deepslate/<name>`) is the same file name; renamed short names still stay residue

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order): it extends #220 pick 1 (same file name) and leaves pick 2 (renamed short names) as it was.
- **Decision:** where Bedrock has no `textures/blocks/<name>` (`textures/items/<name>`), the one file named `<name>` in a folder below it is Java's `block/<name>` (`item/<name>`), and then #220's rules apply unchanged: a plain one-file short name showing it is named directly (`cobbled_deepslate`, `crimson_planks`), a file only inside a variant set gets a pack entry whose key keeps the folder (`<ns>:vanilla/block/huge_fungus/<name>` -> `textures/blocks/huge_fungus/<name>`), animated files only through vanilla's flipbook tile. Two or more files of that name below the folder stay residue, naming them. The pinned index has 67 such terrain files (`candles/`, `deepslate/`, `huge_fungus/`) and 117 item files (`harness/`, `nautilus_armor/`, `spawn_eggs/`, `spear/`), with no name in two places and none clashing with a top-level file.
- **Why:** the file name is the identity #220 settled on, and a subfolder doesn't change it. Checked locally against the Java 1.21.11 client jar (nothing kept): of the 184 nested files, 69 share a name with a Java texture, and all 69 are pixel-identical to it (52 byte-identical, 17 identical in every visible pixel; the 16 coloured candles and `candle` differ only in the colour of fully transparent pixels). Measured (Quark 4.1-487): 6 vertical slabs (cobbled deepslate, deepslate brick, deepslate tile, polished deepslate, crimson, warped) and 4 other blocks (crimson and warped bookshelves, vertical crimson and warped planks) convert; validator 0 errors.
- **Not changed (pick 2 of #220 stands):** a Java name that is a Bedrock short name showing a file of another name (`oak_planks` -> `planks_oak`) still stays residue. The same check found 26 of those 225 short names are not Java's texture (`piston_top` shows `piston_inner`, the 16 `*_stained_glass_pane_top`, `short_grass`, `bubble_coral_block`, `fire_coral_block`, `purple_glazed_terracotta`, `spruce_planks` by one pixel, the 3 `command_block_*` mipmaps, `conduit`), so turning `MAP_RENAMED` on would ship wrong textures. Mapping them needs a cited per-name table, which is a call for Alex.
- **Rejected:** turning `MAP_RENAMED` on (26 wrong of 225, above); a hand-written Java -> Bedrock name table (#87, #220); the nearest-named file.
- **Links:** #296, #220, #277, #87.

## 2026-10-17: vertical slabs (`type` = north|east|south|west|double) convert on the 6-way placement mapping; a clicked top or bottom face places the half nearest the player

- **Status:** approved (Alex, 2026-10-17): picks 1a 2a 3a 4a, the defaults (PR #307, picks comment 6229544923).
- **Decision:** a `variants` blockstate whose only state is `type` with exactly the values `north`, `east`, `south`, `west`, `double` (vertical slabs; Quark's 122, the biggest state set in the #296 "generic variant states" sub-reason) converts through the 6-way / attach-face path (#218, `_convert_directional`) as a new kind `vslab`: each of the four sides is a Java variant whose model, quarter y turn and uvlock are kept (one bone per side through `models.turn_locked`, no `minecraft:transformation`), picked by bone_visibility and permutations on `minecraft:block_face` (placement_position, "the face of another block on which this block was placed") and `minecraft:cardinal_direction` (placement_direction, the player's facing, no y_rotation_offset as #164 and #218). **Placement rule (pick 1):** read from bytecode where the code can be read; otherwise the labelled DEFAULT: a clicked side face gives type = that face (the slab stands against the block it was placed on, as vanilla `SlabBlock#getStateForPlacement` puts a slab against the face clicked); a clicked top or bottom face gives type = the player's facing, the half nearest the player. The value is the mod's own enum (no vanilla class has this state set), whose serialized names `blockcode` doesn't evaluate, so for now every vertical slab takes the DEFAULT, labelled per block in the notes with the reason (Quark: "no registration of this block was found", its Zeta registration isn't followed, #280). **Double (pick 2):** `type=double` (a second slab placed into the first) has no data-driven Bedrock form; it is set aside and named in a note, exactly as the horizontal slab's double is (#164), and recorded as unreachable in `ConversionResult.java_states` so a loot `set_count 2` conditioned on it never applies (#299/#301). **Box (pick 3):** getShape isn't read (same enum), so each side's collision and selection box is the DEFAULT turned model's element bounds, labelled. Loot: Quark's tables convert with count 1.
- **Why:** Quark's code (read by hand from `org/violetmoon/quark/content/building/block/VerticalSlabBlock.class`, Quark 4.1-461 neoforge 1.21.1: `getStateForPlacement` -> `getDirectionForPlacement` -> `VerticalSlabType.fromDirection`) gives type = the clicked face for a side click, and for a top or bottom click the direction from the block's centre to the point clicked (`getClickLocation`, `Math.atan2`, `Direction.fromYRot(..).getOpposite()`), i.e. the half the player clicked. Bedrock's placement traits expose the clicked face and the player's facing but no horizontal click point (learn.microsoft.com Block Traits: `placement_position` gives `block_face` and `vertical_half` only; `placement_direction` gives `cardinal_direction` / `facing_direction`), and neither does the Script API's place event (`BlockComponentPlayerPlaceBeforeEvent`: `cancel`, `face`, `permutationToPlace`, `player`; learn.microsoft.com @minecraft/server stable). The player's facing matches Java whenever the player clicks the near half of a top face, the usual case. Side clicks, the four shapes and the uvlocked textures are exact. Measured (local, Quark 4.1-461): 122 vertical slab blockstates were `block` residue; 90 now convert (270 files: block, geometry, loot table), 32 stay residue for an existing, separate reason (their model names a vanilla texture Bedrock doesn't have under that name, #296 sub-reason 5). Validator 0 errors.
- **Rejected:** keeping vertical slabs residue until Bedrock exposes a click point (loses 90 blocks for the top/bottom case only); a fixed type for top/bottom clicks (north; wrong for three of four facings); `y_rotation_offset` on cardinal_direction (doesn't change which half is nearest); a scripted double slab (no scripts for plain decoration blocks, #164); matching the block to its class by state set when the registration isn't read (a new inference; left for #280).
- **Links:** #296, #277, #218, #164, #299, #301, #280, #87.

## 2026-10-16: multi-item tag ingredients: vanilla-only tags over several slots are written once per combination (≤16), a block's own item file carries the tag, and a tag none of whose members converted is `owned_by_residue` (approved (Alex, 2026-10-16))

- **Decision:** (Alex's picks 1–3 on #302, comment 6228435148.) **(1) Combinations.** A recipe ingredient that is a tag whose members are all vanilla items (an add-on can't put a tag on a vanilla item, and no Bedrock vanilla tag has the same members) and that, alone or with other such tags, fills several grid slots is written once per combination of members the player can put in those slots, only when there are at most `EXPANSION_CAP` (16) of them: nᵏ for n members over k slots, multiplied over the tags (`recipes._combinations`). In a shaped recipe each slot set to a different member gets its own key symbol (Bedrock: "The key used in the pattern may be any single character except the 'space' character"; a slot group holding one member keeps the Java symbol), named `<recipe>__<member path>__<member path>...` (one per slot, namespace left out since every member is `minecraft:`). A grid that is another's mirror image is written once, since Bedrock's `assume_symmetry` defaults to true ("Used to automatically assume a symmetrical recipe should return the same result"; learn.microsoft.com, Recipe Documentation - Shaped Recipe) as Java matches shaped recipes mirrored; a shapeless combination is written once whatever order its members are in. Forge/Common `chests/wooden` (chest, trapped chest) over two slots is 3 recipes. Each such recipe gets a report note. **(2) Item files.** A mod block that also has its own item file (`block_and_item`) carries a recipe's native tag, and Bedrock's vanilla item tags (#293), in that item file's `minecraft:tags` (item format ≥ 1.20.50; learn.microsoft.com, Items Documentation - minecraft:tags), instead of getting one recipe of its own beside the tag recipe (or none, for a tag over several slots). `emitted_definitions` now gives the item file's path and body for such a block. **(3) All-residue tags.** A recipe refused only for tag ingredients none of whose members converted (every member a mod item this conversion didn't emit, membership fully known) records those members, with any other unemitted mod item it names, in `ConversionResult.unshipped_names`; the pipeline's `recipes.refine_owned` (#303) re-files it `owned_by_residue`, keeping the original reason, when every one of them has a residue entry of its own. A tag with any vanilla or converted member, or a recipe refused for anything else too, stays `recipe`.
- **Why:** each turns a refusal into Java's own behaviour where Bedrock can express it, or into an explanation from the jar where it can't yet. (1) is exact: every mix Java accepts is a recipe, and nothing Java refuses is one; the cap keeps a large tag (17–18 glass members) from flooding the recipe book, so those stay residue. (2) a recipe slot sees the item the player holds, and the mod's own item file is that item. (3) a tag none of whose members exist on Bedrock matches nothing until they convert, the same reason #303 owns recipes naming residue items. This supersedes the "owning tag ingredients whose members didn't convert" rejection in the bare-type entry below.
- **Rejected:** one recipe per member with every slot the same member (forbids mixing, so not Java's recipe); combinations over the cap (recipe-book flood; still residue); owning a recipe whose tag has some converted or vanilla members (it is narrowed, not waiting on its members: left as `recipe`).
- **Links:** #302, #303, #299, #277, #160, #293.

## 2026-10-16: block loot approximates Silk Touch, shears and tool tier with Bedrock `match_tool`, labelled; a block that drops nothing names Bedrock's `loot_tables/empty.json` (approved (Alex, 2026-10-16))

- **Decision:** (Alex's picks 1 and 2 on #299, comment 6228193615.) **(1) Approximate, don't refuse.** Bedrock never reads a block's `minecraft:loot` when it is broken with Silk Touch: the block drops itself (wiki.bedrock.dev, Tool-Based Destruction, "It is impossible to prevent a block from dropping itself when mined using an item with the Silk Touch enchantment"; Ore Loot Tables). So the converted table only ever runs without Silk Touch: a Java Silk Touch `match_tool` is false there and its `inverted` form true, and `alternatives` whose Silk Touch child comes first reduce to the next child. Shears (`minecraft:shears`, `forge:shears`, `c:shears`, `c:tools/shear(s)`, Forge/NeoForge `shears_*` tool abilities) and tool tags (`minecraft:pickaxes`, `axes`, `shovels`, `hoes`, `swords`) become an entry condition `{"condition": "match_tool", "minecraft:match_tool_filter_any": ["minecraft:is_shears"]}` etc. (learn.microsoft.com, Loot and Trade Table Conditions, match_tool; Vanilla Item Tags, Tool tags). `any_of` of tool tests is one `filter_any`; a tool-specific `alternatives` child with another child after it, or a negated tool test, is still refused (Bedrock can't test that a tool is absent). **Tool tier:** a block in Java's `needs_stone_tool` / `needs_iron_tool` / `needs_diamond_tool` / `forge:needs_netherite_tool` (the jar's own block tags, #293's reader) gets, on every drop entry, `match_tool` with `minecraft:match_tool_filter_all: ["minecraft:is_tool", "minecraft:is_<tool>"]` for each of its `mineable/*` tools (one entry per tool) and `minecraft:match_tool_filter_any` the Bedrock tier tags of that tier or better (the wiki's Tool-Based Destruction pattern). Conservative, never more than Java: golden and copper tiers, mod tools and explosions get nothing. A table that is the self-drop is wired anyway when it is gated. A tier-tagged block in no mineable tag is `loot` residue. **Labelled:** every approximated table gets its own report note `<table>: approximated loot (#299): <why>` (a Java tool tag that also takes mod tools; Silk Touch giving the block itself where Java gives something else, read from the table; the tier gate and what it leaves out), plus a count note. **(2) Empty Java tables, `minecraft:air` drops, and tables that drop only under Silk Touch** put `minecraft:loot: loot_tables/empty.json` (Bedrock's vanilla drop-nothing table, Mojang/bedrock-samples@46ba6ea9) on their converted block; with no converted block they are `loot` residue (re-filed `owned_by_residue` when the block is residue), no longer a loose table naming `minecraft:air`. Validator: `loot.condition` (entry conditions must be `match_tool` with known fields and tag lists). In-game: blocks with `match_tool` tables are checked per tool (bare hand, shears, the lowest allowed tier and the one below) through `LootTableManager.generateLootFromBlockPermutation` (stable since @minecraft/server 2.2.0; the check pack now depends on 2.2.0), and setblock-destroy (no tool) must leave nothing.
- **Why:** Alex, 2026-10-16: "from the user perspective having something that is mostly right is better than not at all right." A refused table leaves the block dropping itself, which is further from Java than any of these approximations. Labelling each one keeps the difference visible. An empty table is exactly Java's "drops nothing".
- **Rejected:** keeping the refusals (the old default); `minecraft:match_tool_filter_none` for "not shears" (no corpus table needs it after Silk Touch is removed, and whether a bare hand passes it is unverified); counting copper or golden tiers (could give more than Java); reading `requiresCorrectToolForDrops` from bytecode in this slice (a block in a tier tag that doesn't require the tool drops by hand in Java and gets nothing here: less, never more); mapping `minecraft:cluster_max_harvestables` (no cited Bedrock tag; those tables also use `apply_bonus`).
- **Links:** #299, #301, #277, #293.

## 2026-10-16: a bare recipe `type` is `minecraft:`; a recipe withdrawn for naming items that are residue of their own is `owned_by_residue`

- **Decision:** (1) A recipe `type` with no namespace is read as `minecraft:<type>` before anything else looks at it (`recipes.with_namespaced_type`), so Biomes O' Plenty's `"type": "crafting_shaped"` converts as `minecraft:crafting_shaped`. A bare type that isn't vanilla is refused under its Java name (`'minecraft:sawmill'`). (2) After the ownership pass, a `recipe` entry that `drop_unshipped_recipes` withdrew because it names (as result or ingredient) mod items the pack doesn't ship is re-filed as `owned_by_residue` (`recipes.refine_owned`) when **every** such item has a residue entry of its own: its blockstate `assets/<ns>/blockstates/<path>.json`, item model `assets/<ns>/models/item/<path>.json` or 1.21.4 item definition `assets/<ns>/items/<path>.json`, of an explaining kind (not `unowned`). The reason names each item with its entry and kind, and keeps the original reason. An item with no entry of its own (another mod's, or one the jar never defines) keeps the recipe `recipe`. `ConversionResult.unshipped_names` carries the full item list, since the reason shortens it.
- **Why:** both are the cheapest sub-reasons of the gauntlet's `recipe` class (#302, breakdown on #299): 131 files in 2 mods are bare types, and 751 in 8 mods name items that are residue. Java reads a ResourceLocation without `:` as `minecraft:` (minecraft.wiki, Identifier, "Conversion from string"), the same default `bedrock_item` already applies to item ids. A recipe whose items didn't convert has nothing wrong with it: it goes with its items, the same explain-from-the-jar rule loot tables of refused blocks (#299) and their models and textures (#292) follow. (1) ships recipes; (2) changes no pack bytes.
- **Rejected:** (1) a per-mod hook for Biomes O' Plenty (the default is Java's own, for every mod); (2) owning a recipe whose items only partly have residue entries (the rest are a real gap); owning tag ingredients whose members didn't convert (a tag is any-of, so one member isn't required; left with the multi-item tag sub-reason on #302; since decided for tags none of whose members converted, see the 2026-10-16 multi-item tag entry above).
- **Links:** #302, #299, #277.

## 2026-10-16: a converted block loot table goes on its block with `minecraft:loot` when it isn't the self-drop; function conditions are decided per Bedrock state or refused

- **Decision:** A block loot table whose block converted is put on that block with `minecraft:loot` unless it is Bedrock's default (one of the block itself), which stays implicit. A function's own `conditions` are translated only when they are `block_state_property` tests on the table's block, decided per Bedrock state the block converter recorded (`ConversionResult.java_states`; a slab's `type=double` is unreachable, so its `set_count 2` never applies). When reachable states give different tables, each gets its own table on a permutation. Any other function condition refuses the table; nothing is applied unconditionally. Vanilla drop ids are written as Bedrock's (`set_data` where needed). A table that drops `minecraft:air`, or an item the pack doesn't define, is not wired and goes to residue. The validator's `block.loot` errors on a `minecraft:loot` naming a table the pack doesn't ship (Bedrock's vanilla `loot_tables/empty.json` aside). The in-game check breaks every wired block on BDS and counts its drops.
- **Why:** an unwired table is a file Bedrock never reads: every custom block dropped itself, so Botania's root, AE2's flawless budding quartz and Create's dyed sails dropped the wrong thing. Applying a state-conditioned `set_count` unconditionally wrote slab tables that said 2 for a single slab, and candle-holder tables that said 4 for one candle. A missing `minecraft:loot` drops itself (learn.microsoft.com, minecraft:loot; MicrosoftDocs/minecraft-creator@4186dc4e).
- **Rejected:** wiring every table, including self-drops (byte churn, same drop); applying an undecidable function condition unconditionally, or dropping it silently (a wrong count); wiring an air drop to an empty table (open as a pick on #299; since decided, see the 2026-10-16 `match_tool` entry above); approximating silk touch, shears or tool tier with Bedrock `match_tool` (open as a pick on #299, since decided the same way; Bedrock ignores `minecraft:loot` under Silk Touch, so those blocks drop themselves there whatever the table says).
- **Links:** #299, #301, #277.

## 2026-10-16: a refused block loot table whose block is residue is `owned_by_residue`, explained from the jar

- **Decision:** after the ownership pass, a `loot` entry for `data/<ns>/loot_table[s]/blocks/<path>.json` is re-filed as `owned_by_residue` (`loot.refine_owned`) when the pack ships no block `<ns>:<path>` and the blockstate `assets/<ns>/blockstates/<path>.json` has a residue entry of its own (`block`, `code_drawn_block`, a station's, ...). Only the pack's blocks count as shipped: a Java block's item shares its id and may ship without the block. The new reason names the block, its blockstate's residue kind, and keeps why the table itself was refused. A table whose block shipped, or that has no blockstate, stays `loot`. Nothing ships differently: pack bytes are unchanged, and the entries still count as residue for coverage.
- **Why:** this is the biggest sub-reason of the gauntlet's `loot` class (#277, breakdown in #299): 363 of the 688 refused block tables in the 11 content mods read locally (10 mods) belong to blocks that are already residue, so the table has no block to drop from and goes with its block when that converts. It is the same explain-from-the-jar rule `owned_by_residue` already applies to a refused block's models and textures (#292).
- **Rejected:**
  - Converting the tables anyway: a loot table with no block is dead weight, and most of these use functions Bedrock lacks (copy_name, copy_components, block-state drops).
  - A new kind (`loot_owner_residue`): `owned_by_residue` already means "ships with its owner, which has its own entry", and the agent already skips it.
  - Counting the block as shipped when its item ships: the item is not the block, and nothing drops from it.
- **Found on the way (not changed here):** converted block loot tables are written to `loot_tables/blocks/` but no block names them in `minecraft:loot`, and a Bedrock custom block without that component drops itself (learn.microsoft.com, Block Components: minecraft:loot). For a table that drops the block itself that is the same drop; for one that drops something else or a set count it is not. Wiring the tables, and then converting tables of several plain pools (164 files, 4 mods), is the next slice; both change what players get, so they need the in-game check.
- **Links:** #277, #299, #292, #296, #87.


## 2026-10-16: a block whose every model bakes no quads is `code_drawn_block` residue, explained from the jar's models

- **Decision:** a blockstate is `code_drawn_block` residue, an explained kind in the residue agent's `SKIP_KINDS`, when every model it names (all variants, random lists and multipart applies) bakes no quads. Such a model has no `elements`, no `loader`, and no vanilla (`minecraft:`) parent anywhere up its chain inside the mod, and has no texture except `particle`. The reason names the particle textures. A chain that leaves the mod (another namespace's parent, a missing file) is not read as drawing nothing, so the block stays on its old path. One drawing model keeps the whole block on its old path too. Station blocks are skipped (their adapters decide). The models are claimed the way the refusing single-model path claimed them before, so the change moves entries from `block` to `code_drawn_block`. The one other count change is in AE2: a parent model that was `owned_by_residue` is now claimed with its block (-1 residue file). No pack byte changes.
- **Why:** this is the biggest cross-mod sub-reason of the `block` class (#296: 9 of the 13 content mods, 338 files: chests, signs and hanging signs, beds, hammocks and sleeping bags, mod fluid blocks). Java's block model renderer bakes a model's elements, or its parent's, so a particle-only model draws nothing. The player sees the mod's code instead: a block-entity renderer, the fluid renderer, or a baked model swapped in at runtime. A Bedrock block definition has no renderer to hand that to, and a stand-in geometry would invent the look (#87). This follows the explain-from-the-jar rule of #279/#292/#293.
- **Rejected:**
  - A box or chest-shaped stand-in geometry: invented.
  - Converting the block as an invisible block: it would ship a block the player can't see, where Java shows one.
  - Not claiming the models: honest about the files, but 4 Botania models a shipped item also names would turn `unowned`, and coverage would drop with no change in game.
  - Naming the renderer from bytecode (BlockEntityRenderer registration, LiquidBlock, `getRenderShape`): more specific, but the model alone already proves Java's model renderer draws nothing. It is a possible refinement.
- **Links:** #296, #277, #87, #279, #292, #293.

## 2026-10-16: leftover data tags become Bedrock block and item tags where Bedrock reads them, else they are explained from the jar

- **Decision:** A Java tag file no converter read (#293) goes one of four ways, decided from the jar's own files (`portkit.datatags`):
  - (1) **Tool and tier block tags** become Bedrock vanilla block tags on the blocks the pack ships, as `tag:<name>` components: `minecraft:mineable/{pickaxe,axe,shovel,hoe}` -> `minecraft:is_{pickaxe,axe,shovel,hoe}_item_destructible`; `minecraft:needs_{stone,iron,diamond}_tool` -> `minecraft:{stone,iron,diamond}_tier_destructible`; Forge's `forge:needs_netherite_tool` -> `minecraft:netherite_tier_destructible`. Membership is the jar's own share (nested tags through the jar's files). A block at block format 1.26.20 or later (no `tag:*` components) is left untagged with a note. The validator no longer counts `tag:*` as a custom component, and flags it at 1.26.20+ (`block.tag_component`).
  - (2) **Bedrock vanilla item tags** (`_BEDROCK_VANILLA_TAGS`: planks, logs, wool, coals, ...) are carried by the mod's emitted members even when no recipe of the mod names the tag, so Bedrock's own recipes (sticks, crafting table, torches) take them as Java's do. Blocks carry it through a replacing item (`_block_item`); a block with its own item file can't and is named in a note (since #302 pick 2, it carries the tag on its item file).
  - (3) **Explained kinds** (all in `SKIP_KINDS`):
    - `tag_unshipped_registry`: a registry portkit converts nothing of (fluid, worldgen biome/structure, enchantment, damage_type, banner_pattern, entity_type, point_of_interest_type, menu, potion, ...). An entity-type tag stays `unowned` when the pack ships entities.
    - `owned_by_residue`: a residue data file names the tag (a machine recipe, a loot table), or every member from this jar is residue.
    - `tag_unread`: members ship but no data file of the jar reads it (only Java code or other mods would) and Bedrock has no tag of the name its systems read; or it names only vanilla entries (an add-on can't re-tag vanilla items) and other mods' entries.
  - (4) A tag a **shipped** file names (other than a recipe advancement read for its unlock) that is still unclaimed stays `unowned`: a converter gap.
  - **Forge/NeoForge `remove`** is now applied by the tag resolver (`TagResolver`) and by `jar_members`: on forge/neoforge jars the listed ids and `#tags` leave the merged tag; on fabric/quilt the key is ignored (Fabric's loader doesn't read it); on a jar with no declared loader a removing file makes the membership unknown.
- **Why:** 2178 tag files in 13 gauntlet content mods were reported as "no converter claims yet". Java says which tool mines a block and which tier it needs only through tags, and Bedrock has vanilla tags for the same thing (learn.microsoft.com Vanilla Block Tags and `tag:`; stable since Bedrock 1.21.50 per feedback.minecraft.net). Java's vanilla recipes accept a mod's planks through `#minecraft:planks`, and Bedrock's take the same tag. Everything else has no Bedrock reader, and saying which (registry, residue owner, or nobody reads it) turns noise into reasons. `remove` is a Forge extension (docs.minecraftforge.net 1.20.x Tags) NeoForge keeps (docs.neoforged.net Tags); ignoring it gave wrong memberships (Mekanism's `trimmable_armor` removes all 8 of its entries).
- **Rejected:**
  - Bedrock's shears and sword block tags (`is_shears_item_destructible`, `is_sword_item_destructible`): they don't work (wiki.bedrock.dev Tool-Based Destruction, MCPE-189586).
  - Forge's `needs_wood_tool` / `needs_gold_tool`: Bedrock removed `wood_tier_destructible` and `gold_tier_destructible` in 1.21.50.
  - Mod tool types (`<mod>:mineable/hammer`) as custom Bedrock block tags: no Bedrock item reads them (the pack's items carry no `minecraft:digger`), so they are `tag_unread`.
  - Java tool item tags (`minecraft:pickaxes`) -> Bedrock `minecraft:is_pickaxe`: different names and meaning, and Bedrock reads them for digging and loot, which the pack's items don't do yet.
  - Vanilla's own nesting of block tags (`#minecraft:logs` inside `mineable/axe`) is not read: no vanilla block tag data is fetched yet, so a mod log only in `#minecraft:logs` gets no axe tag (under-tagged, never over-tagged).
  - Writing tags for unconverted registries, or tags nobody reads, onto items: it would change nothing in game.
- **Links:** #293, #277, #292 (same explain-from-the-jar rule), #272 (Mekanism `remove` side note).

## 2026-10-16: .lang carries lines for what ships; lang and leftover assets are explained from the jar's own references

- **Decision:** These are three rules for the content mods' two biggest unexplained reason classes (#277 rule 4).
  - (1) **.lang**: a `tile.`/`item.`/`entity.`/`itemGroup.name.` line ships when the final pack defines its identifier or names its key (`lang.settle`, run after the withdraw passes). A line for one of the jar's own blocks, items or entities that didn't ship is kept, so the name is there when its owner converts; the owner's own residue already says why it didn't ship. Lines for creative tabs, other mods' entries and sub-keys (`block.<ns>.x.tooltip`) are dropped. Source text is never changed.
  - (2) **Lang keys** with no line are explained with one entry per file and kind:
    - `lang_code_string`: no block, item, entity, creative tab or registry entry owns the key, so only Java code shows it.
    - `lang_unshipped`: a registry portkit converts none of (effect, enchantment, biome, fluid, attribute, trim, painting, structure, ...), a vanilla-namespaced extension, a creative tab, or another mod's content.
    - `lang_locale`: no Bedrock slot.
    - `lang_unreadable`: Gson rejects the file too. Only `,,` / `,}` inside an object is claimed, per `JsonReader.doPeek` in gson 2.10.1.
    
    Lang files are read as `utf-8-sig` (Gson skips a BOM). Locales are read en_us first.
  - (3) **Unowned models, textures and atlases** (`portkit.ownership`) are traced back through blockstates, item definitions, model parents/textures/overrides/loader parts, OBJ `mtllib` and particle definitions:
    - `owned_by_residue` when every user is residue with its own entry, including a refused block's item model;
    - `java_only_asset` when no JSON names the file, only Java-only models do, or it is an atlas;
    - left `unowned` when a shipped user names it (a converter gap).
    
    All six kinds are explained (`SKIP_KINDS`), and they still count as residue for coverage. Explained-empty mods (#279) keep `code_only`.
- **Why:** Almost all of the 6872 `lang` entries were keys no Bedrock line can carry, reported one by one as "unrecognised". Almost all unowned models belonged to blocks already refused for their own reasons, and almost all unowned textures are drawn only by Java code (GUI, entity renderers, effect icons, armor layers). Saying which, with the owner named, turns noise into reasons. The leftovers are the real gaps: block-item inventory models and modular-tool parts. Alex prefers keeping source assets: nothing is deleted, and an owned file ships when its owner does.
- **Rejected:**
  - Writing lines for everything (keys that name nothing, and bogus `tile.x.tooltip.name` keys).
  - Dropping the jar's own unshipped-content lines. The agent would lose the name, and the owner is already residue.
  - Inventing locale mappings (es_ar to es_MX).
  - Parsing JSON leniently beyond what Gson is shown to do.
  - Mod-specific GUI/texture lists. The answer comes from the jar's own references.
- **Links:** #292 (PR #294), #277, #279. Data tags: #293.

## 2026-10-16: a mod with nothing Bedrock can hold is explained-empty: no pack, a report of reason classes read from the jar

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order); pick 1 is
  the default Alex suggested (no pack, an explained-empty report). PR #291 for #279.
- **Decision:** when a conversion ships no file, every residue entry is of an
  explained kind (`SKIP_KINDS`) or a leftover only the mod's code reads, and
  the jar's own facts name at least one reason class, the outcome is
  **explained-empty** (`portkit.codeonly`). Picks:
  1. **No pack.** No behavior/resource pack and no `.mcaddon` are written;
     `explained-empty.json` (outcome, reason classes with evidence and why
     Bedrock can't carry each, residue by kind, the facts) goes where the
     packs would have. `validate_tree` reports a tree holding a well-formed
     report and no packs as `tree.explained_empty` (severity info), not
     `tree.empty`; mct is skipped for it. A later run that ships a pack
     deletes a stale report.
  2. **Leftovers.** For an explained-empty mod, lang residue (per-key
     `lang` and `lang_code_string` lines, folded to one entry per file),
     `unowned` assets outside `blockstates/`, `items/` and `sounds`, and
     `unowned` loader data (`data/<ns>/neoforge|forge|fabric|quilt/`) whose
     every file is typed with the mod's own namespace become `code_only`
     residue, a new explained kind. A leftover blockstate, item definition,
     sound or any other `data/` file keeps the mod out of explained-empty
     (a converter gap, not an explanation), and so does any unexplained
     residue kind.
  3. **Reason classes**, from jar facts only (mixin configs; superclasses
     and constant-pool references in Mojang names through the #235 table;
     string constants and file paths for resource formats; nested jars):
     `mixin_patch`, `client_rendering` (10+ classes calling
     `net/minecraft/client/renderer/`, shader files, OptiFine CTM, CEM/EMF
     `.jem`/`.jpm`, random/emissive entity textures, built-in resource
     packs), `gui_screen`, `hud_overlay`, `config_screen`, `keybind`,
     `networking`, `commands`, `gameplay_hooks`, `library_api`,
     `nested_modules`, and `java_code` for code with none of these shapes
     ("N classes of Java code with no content files").
  4. **Ingest.** A jar with no `assets/` or `data/` tree ingests when it
     carries loader metadata (fabric.mod.json, quilt.mod.json, mods.toml,
     neoforge.mods.toml, mcmod.info); its pack identity is its declared mod
     id. A jar with neither is still refused ("not a mod").
  5. **Gauntlet classes** (amends #278 pick 5): library also when the jar
     defines an event API (10+ `*Event(s)` classes in 100+, no textures) or
     is passive (50+ classes, mixins under 5%, no game, input, screen or HUD
     event, no keybind registration, not client-only); the code-only library
     rule no longer fires on a jar that hooks gameplay events; a one-sided
     jar whose code is screens (a screen class, under 10 classes calling the
     world renderer) is UI/info, not client-only; a new class **gameplay
     code** for code hooking block/player/living events with no screen, HUD
     or renderer code. Done (#277 rule 6) is unchanged: an explained-empty
     mod is done because it is validator-clean and all its residue kinds are
     explained.
- **Why:** half of #277's 50 ship no convertible content; an empty pack the
  validator rejects told the user nothing, and their leftovers read as
  converter gaps. A pack of only lang text would be keys no Bedrock screen
  shows (the text belongs to Java screens, tooltips and config), so shipping
  it would install something that does nothing. Deciding from jar facts
  keeps the rule general (no mod names in core).
- **Rejected:** a lang-only (or icon-only) pack: installs dead text, and
  needs the validator to accept a content-free pack; leaving `tree.empty`
  as an error: counts every code-only mod as failing; deciding from the
  mod's description or a list of names: not general, and the core lint
  forbids mod names.
- **Links:** #279, #277, #278.

## 2026-10-16: the top-50 gauntlet pins one jar per mod by a version rule, classifies it from its own files, and is boarded weekly apart from the PR gate

- **Status:** approved. Pick 2 decided by Alex (2026-10-16); picks 1 and
  3-5 as proposed by Hark. PR #290 for #278.
- **Decision:** #277's 50 mods are pinned in `fixtures/real/gauntlet.toml`
  (corpus format; `portkit gauntlet pin`), run by the #234 gap-leaderboard
  workflow (`set: gauntlet`, same shards, normalized reasons, trend, mct),
  each jar profiled and classified from its own contents, and boarded in
  `docs/gauntlet.md` with a cross-mod reason-class roll-up. The gauntlet
  baseline is `fixtures/real/gauntlet-baseline.json`, separate from the
  13-mod corpus baseline; the PR gate never runs the 50. Picks:
  1. **Version rule:** the newest build for Minecraft 1.21.1, else 1.20.1,
     releases before pre-releases, on the loader the converter reads best:
     1.21.1 NeoForge, Fabric, Forge, Quilt; 1.20.1 Forge, Fabric, NeoForge,
     Quilt. A mod with neither gets its newest release, marked off-rule.
     Result: 44 on 1.21.1 (40 NeoForge, 4 Fabric), 5 on 1.20.1 Forge
     (Tinkers', BOP, Botania, Iron Chests, Better Advancements), JER on a
     1.21.1 NeoForge beta (it publishes no releases), Chisel off-rule on
     1.12.2 (its newest build is a 1.16.5 alpha; no 1.20.1/1.21.1 exists).
  2. **CurseForge fetch policy (decided, Alex 2026-10-16):** Modrinth first
     (48 of 50 are there). Twilight Forest and Chisel are CurseForge-only and
     stay `unfetchable` in the manifest ("CurseForge-only; awaiting official
     CurseForge API key (allowModDistribution must be true)"), their
     CurseForge project id, pinned file id and sha512 kept as metadata only.
     They are fetched only through the official API (`api.curseforge.com/v1`,
     `x-api-key`) when `CURSEFORGE_API_KEY` is set (the repository's Actions
     secret), and only when the mod's `allowModDistribution` is true;
     otherwise they stay unfetchable with that reason. CurseForge jars are
     re-fetched each run into a temporary directory, never put in an Actions
     cache, never committed. The secret goes only to the gauntlet's convert
     step on this repository's scheduled and manual runs, never to
     `pull_request` runs (so never to forks), and is never printed. Licences
     from their source repositories (TF: LGPL-2.1 code, CC-BY-NC-SA-4.0
     assets; Chisel: GPL-2.0).
  3. **Board format:** one row per mod (rank, class, loader/MC, status,
     coverage, files, residue, top three reason classes, validate, mct,
     done), the roll-up ranked by mods then files with explained kinds
     marked, a "next general work" list without them, class evidence beside
     #277's [lib] mark, and the leaderboard's normalized reasons.
     Reason class = residue kind; `unowned` split by directory three levels
     deep. Done (#277 rule 6) = converted, no validator errors, every residue
     kind in the residue agent's `SKIP_KINDS`.
  4. **Cadence:** weekly (Mondays 09:17 UTC) and on demand; the sample
     stays nightly. The committed board and baseline are updated by hand in
     a PR from the run's artifact.
  5. **Classes:** content, library, client-only, performance/mixin-only,
     UI/info, first rule that holds, thresholds in `gauntlet.classify`.
- **Why:** #277 needs one shared, reproducible view of all 50 so each
  sub-issue is chosen by how many mods a gap blocks (rule 4). The loader
  order follows what the converter has: NeoForge 1.21.1 jars need no
  remapping and have their tag set; Forge 1.20.1 has SRG (no ambiguous ids)
  and its tag set; Fabric needs intermediary (8-10 ambiguous ids per
  version); Forge 1.21+ has neither (decisions 2026-10-15 #235, 2026-10-12
  #160). A weekly board is enough for sub-issues that land a few times a
  week, and the 50 include the heaviest jars we run.
- **Rejected:** fetching the two CurseForge jars from cfwidget and
  CurseForge's public CDN without a key (the first draft of pick 2): Overwolf
  treats downloading from CurseForge's CDN outside its official API as
  scraping, and an Actions cache on a public repository is readable by
  anyone who opens a PR, so the jars must not sit in one; dropping
  the two CurseForge mods (rule 4 needs Twilight Forest's worldgen); each
  mod's newest build on any version (#234's rule: 26.x builds the converter
  has no tag set or name table for); classifying from Modrinth categories
  or descriptions (#278 says from the jar); a sixth "code-only gameplay"
  class (VeinMiner reads as library; #279 treats both the same); running the
  50 in the PR gate (slow; the 13-mod corpus stays the ratchet).
- **Links:** #277, #278, #234 (PR #255), #235, #279.

## 2026-10-16: wearable mod armor is drawn when worn: an attachable on vanilla armor geometry wearing the mod's own layer texture, found from the mod's code

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order). PR #276, merged 5e37982.
- **Decision:** a wearable mod armor piece (#275) gets a Bedrock attachable when the mod's code says which texture Java draws it with, and that texture is one 64x32 png in the jar (#274). No texture is drawn, recoloured or guessed (#87).
  1. **Shape** (Mojang bedrock-samples@46ba6ea9 `resource_pack/attachables/diamond_helmet.json`, `_chestplate`, `_leggings`, `_boots`): format 1.8.0, materials `armor` / `armor_enchanted`, textures `<the mod's layer>` + `textures/misc/enchanted_actor_glint`, geometry `geometry.humanoid.armor.helmet` / `chestplate` / `leggings` / `boots`, `parent_setup` `variable.<helmet|chest|leg|boot>_layer_visible = 0.0;`, `controller.render.armor`. Only vanilla ids are referenced; no Mojang file is copied. Vanilla's second, player-only attachable (`<id>.player`, `geometry.player.armor.*` with an offset animation) is not written: the issue scoped the humanoid geometry, and one attachable per item is what the held-model path does too.
  2. **Texture, from the mod's code** (`portkit.armorlook`, generic readers; the adapters say which applies):
     - 1.21.1 `ArmorMaterial` record: its `layers` list, with the mod's static helpers followed (`MythicArmorMaterials.layer(name)` -> `new ArmorMaterial.Layer(RegistryHelper.id(name))` -> `ResourceLocation.fromNamespaceAndPath("mythicmetals", name)`). Vanilla 1.21.1: `Layer(id)` = `Layer(id, "", false)`, texture `id.withPath("textures/models/armor/" + path + "_layer_" + (inner ? 2 : 1) + suffix + ".png")`, inner = legs (client jar sha1 30c73b1c).
     - Forge 1.20.1: an item's `getArmorTexture` wins (`ForgeHooksClient.getArmorTexture`, Forge @d13dd327). One body is read: Forge's own format `"%s:textures/models/armor/%s_layer_%d%s.png"` on a `ResourceLocation` field, with the field's value followed through the constructor chain (Create's `BaseArmorItem.textureLoc` = `Create.asResource("cardboard")` / `"copper_diving"`). With no override, the material's `getName()` split at `:` (Forge's `getArmorResource`); vanilla 1.20.1 reads the whole name as a path in `minecraft` (client jar sha1 0c3ec587).
     - 1.21.2+ equipment assets (`assets/<ns>/equipment/<id>.json`, `models/equipment/` in 1.21.2-1.21.3; `layers.humanoid` / `humanoid_leggings` -> `textures/entity/equipment/<layer>/<path>.png`, minecraft.wiki Equipment oldid 3837905) are resolved by the core when an adapter answers with one; no corpus mod reaches it yet (no 1.21.2+ armor reader).
     - **DEFAULT:** when no reader can say, `<material constant lowercased>_layer_<n>.png` in the item's namespace is used only if that file is in the jar, and the notes label it DEFAULT. No corpus piece uses it.
  3. **Not drawn (a note per reason; the piece stays wearable):** pieces the mod draws its own way: a Fabric `ArmorRenderer` registration (Fabric API @83c07162 `ArmorFeatureRendererMixin` cancels the vanilla draw; the items are read from the filter lambda's `instanceof`, and an unreadable registration refuses the mod's armor), Forge `IClientItemExtensions#getHumanoidArmorModel`/`getGenericArmorModel` handed over in `initializeClient`, any other `getArmorTexture` body; a dyeable (tinted) or multi-layer material; a texture that isn't in the jar or isn't 64x32 (another size isn't checked to map the same way); an item that already has a held-model attachable. Trim overlays on worn armor aren't written: Java's trim atlases aren't carried, and whether Bedrock's own trim path in `controller.render.armor` (`variable.has_trim ? variable.trim_path`) applies to an add-on's attachable is unverified.
  4. **UV layout verified:** Java's armor layers are `HumanoidArmorModel.createBodyLayer` (outer deformation 1.0, inner 0.5) on a 64x32 texture in 1.20.1, 1.21.1 and 1.21.4 (`LayerDefinitions`, client jars sha1 0c3ec587, 30c73b1c, a7e5a602): head texOffs(0,0) 8x8x8, hat (32,0), body (16,16) 8x12x4, arms (40,16) 4x12x4, legs (0,16) 4x12x4, left limbs mirrored. Bedrock's `geometry.humanoid.armor.*` (`models/mobs.json` on `geometry.humanoid.armor1`/`armor2` on `geometry.zombie`, `models/entity/zombie.v1.0.geo.json`, texture 64x32) has the same boxes and uv offsets with the same mirroring, and the same parts per slot as Java's `setPartVisibility` (helmet head+hat, chestplate body+arms, leggings body+legs, boots legs). Only the inflation differs slightly (Bedrock body 1.01, inner legs 0.49; Java legs 0.9/0.4), which changes size, not UVs. So the texture is copied unchanged to `textures/models/armor/<ns>/`, and its source counts as consumed.
- **Measured (corpus):** Mythic Metals 89 attachables of 96 wearable (7 drawn by Mythic Metals' own `ArmorRenderer` for `HallowedArmor` and subclasses: hallowed, metallurgium and runite helmets, all 4 tidesinger pieces; the legendary banglum pieces don't ship, as before), files 1736 -> 1871, residue 1933 -> 1885, coverage 47.3% -> 49.8%. Create 6 of 6 (cardboard set, copper diving helmet and boots), files 4012 -> 4021, residue 8337 -> 8334, 32.5%. Baseline rebanked. mct 0 errors on both.
- **Unverified:** the look in game. BDS is a server and doesn't load resource packs, so nothing here is checked by the in-game run beyond the pack loading.
- **Rejected:** guessing `<material>_layer_N.png` without a reader or without the file (#87); recolouring or flattening dyeable and multi-layer looks; approximating a mod's custom armor model with the vanilla geometry; copying Mojang's attachable files (EULA: ids only); writing the `.player` variant without a source saying a mod item needs it.
- **Links:** #274, PR #275, #272 / PR #273, #87.

## 2026-10-16: mod armor is wearable when the mod's code states its slot and numbers, else it stays a plain item and is residue

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order). PR #275, merged 7aee0f0.
- **Decision:** a mod armor item gets Bedrock `minecraft:wearable` when its slot, armor points, toughness, knockback resistance, durability and enchantability are all read from the mod's own bytecode, each with a citation (#274, follow-up to #272/#273). No number is invented (#87), and the policy for anything unreadable is Alex's 2026-10-16 decision on #268.
  1. **Read, don't invent.** New shared readers in `portkit.itemcode`: a 1.20-style `ArmorMaterial` enum's getters (`getDefenseForType` = `array[type.ordinal()]`, `getEnchantmentValue`/`getToughness`/`getKnockbackResistance` = a constructor field or a constant, durability as #268 reads it); a 1.21 `new ArmorMaterial(Map.of(...), enchantability, sound, repair, layers, toughness, knockback)` record built in a static initializer; a registration lambda's `new` and the `Item.Properties` calls on the way; and an item class followed up its constructors to vanilla `ArmorItem` (branches on two known statics are followed, any other branch stops it). An item class that overrides a method deciding its numbers in code (`getDefense`, `getToughness`, `get(Default)AttributeModifiers`, `getEnchantmentValue`, `isEnchantable`, `getEquipmentSlot`, `getMaterial`, `getType`, `getMaxDamage`, `isDamageable`, `canBeDepleted`) is not read, and neither is a piece whose `Item.Properties` get `durability`, `attributes` or a vanilla `component` outside the material. Vanilla's side is read from Mojang's client jars with client.txt: 1.20.1 `ArmorItem` takes defense, toughness, knockback resistance, durability and enchantability from the material (client jar sha1 0c3ec587); 1.21.1 `ArmorItem.getDefense()`/`getEnchantmentValue()` read the material record and it adds no durability (sha1 30c73b1c).
  2. **Adapters** (new `item_armor` hook, `(mod, names) -> {name: ArmorPiece | reason}`):
     - **Mythic Metals** 0.24.6+1.21: all 25 `MythicArmor` sets, 100 pieces: `new ArmorSet(material, multiplier)` or a set subclass whose `makeItem` builds its own class for the helmet (Hallowed, Banglum, Celestium, Metallurgium, Runite, Tidesinger), durability `BASE_DURABILITY[type] * multiplier` (the #268 numbers, test-checked equal), defense/enchantability/toughness/knockback from `MythicArmorMaterials`. Mod data components a set or class adds (tidesinger pattern, prometheum) and `ArmorItemMixin`'s attribute bonuses on some materials are named in a note as not carried.
     - **Create** mc1.20.1-6.0.8: cardboard helmet/chestplate/leggings/boots (`AllArmorMaterials.CARDBOARD`) and copper diving helmet/boots (`COPPER`). Netherite diving gear is built on vanilla's `ArmorMaterials.NETHERITE`, whose numbers aren't in Create's jar, so it is residue; the backtanks override `canBeDepleted`/`isEnchantable` (and ship as blocks).
  3. **Bedrock components** (MicrosoftDocs/minecraft-creator@4186dc4e `minecraft_wearable.md`, `minecraft_enchantable.md`, `minecraft_durability.md`, the pin of the agent reference; bedrock-samples@46ba6ea9 has no item component docs, and its `diamond_spear.json` shows `max_stack_size` 1 with `durability` and `enchantable`): `minecraft:wearable` `{slot, protection}` with HELMET/CHESTPLATE/LEGGINGS/BOOTS -> `slot.armor.head`/`chest`/`legs`/`feet` and protection = the Java armor points; `minecraft:durability` `{max_durability}` = Java max damage; `minecraft:enchantable` `{slot, value}` with `armor_head`/`armor_torso`/`armor_legs`/`armor_feet` and value = Java enchantability; `minecraft:max_stack_size` 1; item format raised to 1.20.30 (wearable and enchantable need it). Applied right after the item converter, so the recipe converter sees which items are wearable.
  4. **Toughness and knockback resistance** must be read like the rest (unreadable: residue), but Bedrock has no item component for either, so they are named in a note per item and not approximated (the issue's scope: read toughness, emit slot and protection; the skillet precedent left attack speed and knockback out in a note). Vanilla 1.20.1 `ArmorItem` adds its knockback-resistance modifier only for `ArmorMaterials.NETHERITE` anyway (client jar sha1 0c3ec587).
  5. **Else residue.** A mod item Java's own data marks as armor (`#minecraft:head_armor`, `chest_armor`, `leg_armor`, `foot_armor`, `trimmable_armor`), or one an adapter knows is armor, that can't be read stays the plain item it converted to and is residue of the new kind `armor` with the reason (the agent skips it: its tools can't read bytecode, and writing wearable without the numbers would invent them).
  6. **Trims.** Nothing new: #273's path tags every wearable Java `#minecraft:trimmable_armor` member `minecraft:trimmable_armors` (verified: Mythic Metals 96 of 96 shipped pieces, Create 4 cardboard pieces).
- **Measured (corpus):** wearable items: Mythic Metals 0 -> 96 (all trimmable-tagged; the 4 legendary banglum pieces don't ship, their animated texture doesn't convert), Create 0 -> 6 (4 trimmable-tagged), BetterEnd 0 (16 residue: Wover-built, numbers not in the jar, as in #268), Mekanism 0 (4 hazmat pieces residue: material registered through a DeferredRegister lambda and the class overrides `isEnchantable`). Coverage: Mythic Metals 47.3% (residue 1938 -> 1933: the trim tag files now count as consumed), Create 32.5% (8336 -> 8337), Mekanism 12.0% (8996 -> 9000), BetterEnd 37.2% -> 37.1% (5591 -> 5607); baseline rebanked.
- **Left (second slice):** worn rendering. A wearable item without an attachable doesn't show on the player; the armor layer textures (`textures/models/armor`, equipment assets) stay as they are. Vanilla-material armor (Create's netherite diving gear) needs vanilla's material table. A Wover library adapter (BetterEnd) and a Mekanism reader. What the mods' code adds beyond the numbers (Create's diving behavior, Mythic Metals' bonuses and components, enchantment rules a class decides in code) is not carried.
- **Rejected:** writing `minecraft:wearable` with protection only, or guessing toughness-less defaults for unreadable pieces (#87); approximating toughness by raising protection (invents a number Java doesn't have); dropping an item that can't be read (it still converts as a plain item, and recipes and loot keep it); vanilla `ArmorMaterials` numbers from minecraft.wiki for Create's netherite diving gear in this slice (vanilla code, not the mod's; can be a later, cited table); mod names in the core (lint): the readers are generic and the mod wiring is in the Create and Mythic Metals adapters.
- **Links:** #274, #272 / PR #273, #268 / PR #269, #263, #87.

## 2026-10-16: a smithing trim recipe converts only when Bedrock takes every slot, else it is residue; mod armor gets minecraft:trimmable_armors only when it is wearable

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order; the policy is Alex's 2026-10-16 decision on #268). PR #273, merged e66ac37.
- **Decision:** Java `minecraft:smithing_trim` converts to Bedrock `minecraft:recipe_smithing_trim` when Bedrock takes each of its three slots, checked against cited Bedrock data (`portkit.data.trim_items`, #272). Until now it was residue as "a judgment call". Any slot that fails sends the recipe to the residue under its source with the cited reason. It is never rewritten as a crafting recipe, and no slot is invented.
  1. **Tags.** Java's slot tags `#minecraft:trim_templates`, `#minecraft:trimmable_armor` and `#minecraft:trim_materials` become Bedrock's `minecraft:trim_templates`, `minecraft:trimmable_armors` and `minecraft:trim_materials`. Any other tag that means more than one item is refused. When the mod adds its own items to Java's template or material tag, a note says those items can't be a trim pattern or material on Bedrock.
  2. **Vanilla items** must be in Bedrock's tag for their slot, per minecraft.wiki [Item tag (Bedrock Edition)](https://minecraft.wiki/w/Item_tag_(Bedrock_Edition)?oldid=3758407): 18 templates, 25 trimmable armors and 10 materials, plus resin brick ([Resin Brick](https://minecraft.wiki/w/Resin_Brick?oldid=3734929)). All 54 ids are checked against bedrock-samples' `mojang-items.json` (test, `-m realmods`). Copper armor and the elytra aren't in the list, so they are refused, even though BDS loads a recipe naming them.
  3. **A mod item** can't be a template or an addition, because an add-on can't register a trim pattern or material. A mod base must have `minecraft:wearable` and carry `minecraft:trimmable_armors`. It gets the tag when the Java recipe names it as the base (as for transform slot tags, #263), and the base is checked on the final pack (`withdraw_unacceptable_trims`, after #268's pass).
  4. **A fixed Java 1.21.5+ `pattern`** converts only when it is the vanilla template's own pattern. Bedrock's trim recipe has no pattern field.
  5. **Java trimmable armor.** A mod item in Java's `#minecraft:trimmable_armor` gets `minecraft:trimmable_armors` only when it is wearable in the pack. Membership comes from the jar's file plus vanilla's 1.21 `#head/chest/leg/foot_armor` nesting from the reference data, cited in a note, and the tag files count as consumed only when an item was tagged. The other items are counted in a note.
  6. **Validator.** Rule `recipe.smithing_trim` checks every slot of every trim recipe in the pack, the agent's included. Rule `item.trim_tag` flags any pack item carrying `minecraft:trim_templates` or `minecraft:trim_materials`, or carrying `minecraft:trimmable_armors` without `minecraft:wearable`.
- **Why:** Mojang bedrock-samples@46ba6ea9 `documentation/Recipes.html`, Smithing Trim Recipe: the base's "only accepted items are armors", and each slot's items "must have" `minecraft:trimmable_armors` / `trim_templates` / `trim_materials` "to be accepted into the respective UI slot". Mojang's `smithing_armor_trim.json` takes those three tags. A BDS 1.26.52.3 probe on a throwaway branch (ingame runs 38936397375, 38937251687) confirmed it with content-log ERRORs:
  - a base that isn't armor is refused ("should be an armor, but isn't"): stick, netherite sword, wolf armor, diamond horse armor, carved pumpkin, a tag of planks, and an add-on item without `minecraft:wearable` even when it carries `minecraft:trimmable_armors`;
  - an add-on item is refused as a template or addition even with the tag ("Did you register it in the Trim Pattern Registry?");
  - an add-on item tagged `trim_templates`, or tagged `trimmable_armors` without being wearable, makes BDS refuse Mojang's own `minecraft:smithing_armor_trim`. That is why the converter never writes those tags on such items.
  - A wearable add-on item, tagged or not, loads clean.
- **Measured (corpus + deco):** no `smithing_trim` recipes in the 13 corpus mods or the 13 deco jars (seafoam_dyeable included). Java trimmable-armor members: Mythic Metals 96 (direct), Create 4 (cardboard armor, direct), BetterEnd 16 and Mekanism 8 (via the 1.21 nesting). Tinkers' Construct adds 16 items to Java `trim_materials` and ships 17 `trim_material` files. The converter writes no `minecraft:wearable`, so no item is tagged today. The change is a guard: packs are unchanged and the reports gain the note above.
- **Supersedes in part:** the 2026-10-12 agent-trim entry's "`base` is not gated". The agent gate (`agent.unresolved_trim`) still checks only template and addition, and the base is now checked by `recipe.smithing_trim`, because BDS refuses a base that isn't armor.
- **Rejected:**
  - Keeping trims as residue: a validated trim on vanilla or wearable armor works on Bedrock.
  - Tagging every Java trimmable member: on non-wearable items the tag breaks Mojang's own trim recipe in BDS.
  - Tagging mod items `trim_materials` from Java's tag (Tinkers): an add-on can't register a material, and BDS refuses such items.
  - Accepting copper armor or elytra on BDS load alone: load acceptance only shows "is armor", not that the item is in the slot's tag.
  - Writing `minecraft:wearable` for mod armor: that needs a cited slot and protection, which is armor conversion's job.
  - A crafting downgrade (Alex, 2026-10-16, #268).
- **Links:** #272, #270 / PR #271, #268 / PR #269, #263, #86.

## 2026-10-16: a vanilla smithing base must be armor or a tool in Bedrock's vanilla data, else its recipe is residue

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order; the policy is Alex's 2026-10-16 decision on #268). PR #271, merged e169ba3.
- **Decision:** a converted `recipe_smithing_transform` whose base is a vanilla item ships only when Bedrock's vanilla data shows that item is armor or a tool (#270, follow-up to #268). A vanilla item can't be given durability, so there is nothing to equip: the recipe either ships as it is or goes back to the residue under its source recipe with the reason, like a mod base with no readable durability. No crafting-table downgrade and no invented stats. The list is `portkit.data.smithing_bases` (86 Bedrock ids, each with its source):
  1. **Mojang's own data** (bedrock-samples@46ba6ea9): the 12 bases of Mojang's vanilla smithing transform recipes (`behavior_pack/recipes/smithing_netherite_*.json`: diamond tools, armor and spear, and diamond horse and nautilus armor, which have no durability at all) and the 7 spears, whose vanilla definitions in `behavior_pack/items` carry `minecraft:durability`.
  2. **Bedrock armor and tools with durability** per minecraft.wiki's Durability page (oldid 3790798): turtle shell and the leather, golden, copper, chainmail, iron, diamond and netherite armor; wooden to netherite swords, pickaxes, axes, shovels and hoes; flint and steel, brush, fishing rod, carrot and warped fungus on a stick, shears, shield, bow, trident, elytra, crossbow, mace and wolf armor. Bedrock hard-codes these, so bedrock-samples has no definition for them. Every id is checked against bedrock-samples' `mojang-items.json` (test, `-m realmods`).
  3. Any other vanilla base (`minecraft:stick`) is refused, in the withdraw pass and in the validator rule `recipe.smithing_base` alike.
- **Measured (corpus + deco):** vanilla smithing bases in the pinned jars are `minecraft:stick` (BetterEnd `terminite_sword_handle`, `thallasium_sword_handle`), `elytra` (BetterEnd `armored_elytra`, Mythic Metals `celestium_elytra`), chainmail armor (Mythic Metals 4), diamond tools and armor (Mythic Metals 9) and netherite tools and armor (Mythic Metals 9, Create 3). Only the two stick recipes are withdrawn: BetterEnd 3315 -> 3313 files, residue 5589 -> 5591, coverage 37.2% unchanged (baseline rebanked); the terminite and thallasium ingots and upgrade templates lose the slot tags only those recipes used. Mythic Metals, Create, Farmer's Delight (both) md5-identical; no other corpus or deco jar has a smithing recipe with a vanilla base.
- **Why:** Mojang bedrock-samples `documentation/Recipes.html`, recipe_smithing_transform: the base's "only accepted items are armor and tools". A stick is neither. Bedrock's own recipes take horse armor, which has no durability, so for vanilla items the test is armor-or-tool in Bedrock's data, not the `minecraft:durability` component a mod item needs (#263).
- **Rejected:** a crafting-table downgrade and invented durability (Alex, 2026-10-16, #268). Only Mojang's 12 recipe bases (would withdraw chainmail, netherite and elytra upgrades that Bedrock takes). Java's vanilla tags or item components (Java data; `enchantable/durability` doesn't exist in 1.20.1). Fetching the list on demand like the other vanilla data: the check would then change with the cache, and the list is 86 item ids with no file content (`portkit/data/NOTICE.md`).
- **Links:** #270, #268 / PR #269, #263 / PR #267.

## 2026-10-16: a smithing base's durability is read from the mod's code, else its recipe is residue

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order; the policy is Alex's 2026-10-16 decision on #268).
- **Decision:** a converted `recipe_smithing_transform` whose base is a mod item ships only when that item is armor or a tool to Bedrock, i.e. has `minecraft:durability` (#268, follow-up to #263):
  1. **Read, don't invent.** The durability comes from the mod's own code, read from its bytecode at conversion time. The generic readers live in the shared layer (`portkit.itemcode`): a tier enum's `getUses()` per constant, a 1.20-style `ArmorMaterial` enum's `ARRAY[type.ordinal()] * field` per constant and piece, a static initializer's values, and a name-plus-lambda registration. Which item is built on which tier or material is read by the mod's adapter (new `item_durability` hook). The base also gets a stack of one (Java can't stack an item with max_damage, minecraft.wiki Data component format, 24w12a). The core applies the durability on the merged pack after `drop_unshipped_recipes`, so only recipes that ship count. Sources:
     - **Create** mc1.20.1-6.0.8: `copper_diving_helmet` 77, `copper_diving_boots` 91. `AllItems.<clinit>` registers them as `DivingHelmetItem`/`DivingBootsItem(AllArmorMaterials.COPPER, ...)`, with `TYPE` HELMET/BOOTS. `AllArmorMaterials.getDurabilityForType` = `MAX_DAMAGE_ARRAY{11,16,15,13}[ordinal] * maxDamageFactor` (COPPER 7). Vanilla 1.20.1 `ArmorItem` takes `defaultDurability(material.getDurabilityForType(type))` (client jar sha1 0c3ec587, Mojang client.txt).
     - **Mythic Metals** 0.24.6+1.21, 15 bases. Tools use `MythicTools.<X> = new ToolSet(MythicToolMaterials.<X>)` with `getUses()` KYBER 889, BANGLUM 260, MYTHRIL 1564, PALLADIUM 1234, HALLOWED 1984. Vanilla 1.21.1 `TieredItem` sets `durability(tier.getUses())` (client jar sha1 30c73b1c). Armor uses `MythicArmor.KYBER = new ArmorSet(KYBER, 21)` and `ArmorSet.baseArmorItem` = `durability(BASE_DURABILITY[type] * 21)`, with BASE_DURABILITY HELMET 12, CHESTPLATE 16, LEGGINGS 15, BOOTS 13. That gives helmet 252, chestplate 336, leggings 315, boots 273. 1.21.1 `ArmorItem` adds none of its own.
  2. **Else residue.** When no durability can be read (and FD's knives already carry theirs, #263), the recipe goes back to the residue under its source recipe. The same happens when the base is a mod block. The reason names the base and Bedrock's rule. The smithing slot tags an item carried only for withdrawn recipes are taken off again, including recipes `drop_unshipped_recipes` withdrew. This covers BetterEnd 21.800.2: its tool heads, sword blades, `leather_wrapped_stick`, `diamond_hammer` and terminite armor (24 recipes). Their numbers are set through the Wover library's builders (`ToolTiers.DIAMOND_TOOL`, `ArmorTier`, `CustomArmorMaterial.Builder#durability`). Wover's code isn't in BetterEnd's jar, and the heads/blades are plain items with no durability in Java at all. It also covers Create's `copper_backtank`, which is shipped as a block (1 recipe).
  3. **No crafting-table downgrade** for these recipes.
- **Why:** Mojang bedrock-samples@46ba6ea9 `documentation/Recipes.html`: the smithing base's "only accepted items are armor and tools". The #263 in-game experiments showed a tag alone is refused (38858468149), while tag + durability + stack 1 passes (38858470689). A durability is a gameplay number, so it is read and cited, never invented (#87).
- **Rejected:** a crafting-table downgrade (it loses the smithing table and the carry-over of enchantments and damage; Alex, 2026-10-16). Vanilla-tier guesses for BetterEnd's Wover-built items: the number Wover applies isn't in the jar. Mod-name code in the core (lint): the readers are generic, and the mod-specific wiring is in the Create and Mythic Metals adapters.
- **Left:** vanilla smithing bases aren't checked (BetterEnd's sword handles take `minecraft:stick`, which Bedrock likely refuses too). A Wover library adapter could read BetterEnd's numbers if Wover's jar were read. Attack damage, mining speed, armor points, enchantability and repair aren't written. None of the affected mods is in the in-game set.
- **Links:** #268, #263, #267, #238.

## 2026-10-16: smithing-slot item tags from the recipe; Farmer's Delight knives carry their tier's durability

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order).
- **Decision:** two changes so a converted smithing upgrade is one Bedrock accepts (#263):
  1. **Slot tags (core, recipes).** A mod item that a converted
     `recipe_smithing_transform` names as template, base or addition carries
     that slot's item tag: `minecraft:transform_templates`,
     `minecraft:transformable_items`, `minecraft:transform_materials` (item
     format raised to 1.20.50 for `minecraft:tags`, as for other recipe tags).
     This applies only to item definitions. A block in a slot is left as it is.
  2. **FD knives (adapter).** Farmer's Delight's knife items (NeoForge 1.3.4 and
     Refabricated 26.1-3.6.28, the versions the FD adapter reads) get their tool
     tier's durability and a stack of one: flint 131 (FD's own tier), iron 250,
     golden 32, diamond 1561, netherite 2031 (minecraft.wiki Tiers, the skillet's
     revision), from FD's ModItems (`KnifeItem(Tier)` / `.durability(material.durability())`).
     Java can't have max_damage with a stack above one (minecraft.wiki Data
     component format, 24w12a). Refabricated's copper knife is left as it was,
     because the cited table doesn't state copper's durability unambiguously.
     Damage, mining speed, enchantability and repair aren't written yet.
- **Why:** Mojang bedrock-samples@46ba6ea9 `documentation/Recipes.html`,
  recipe_smithing_transform: the base's "only accepted items are armor and
  tools", and each slot's items "must have" its tag "to be accepted into the
  respective UI slot". BDS 1.26.52.3 rejected FD's netherite knife upgrade ("base
  item is not a piece of armor or equipment"). Experiment ingame runs on
  throwaway branches showed that the tag alone still fails (38858468149), while
  tag + durability + stack 1 passes (38858470689). So the base needs durability,
  which is a gameplay number: only an adapter with a cited source writes it (the
  skillet precedent, #87).
- **Rejected:** downgrading the recipe to shapeless crafting (it loses the
  smithing table and the carry-over of enchantments and damage). Leaving it as
  residue (the knife upgrade would vanish when the numbers are citable). Writing
  durability in the core for every smithing base (no cited number for an
  arbitrary mod's item).
- **Left:** other mods' custom smithing bases still lack durability, so BDS
  would still reject them. That's BetterEnd's tool heads and hammers, Mythic
  Metals' custom tools, and Create's copper diving gear. They aren't in the
  in-game set. How to handle them (residue, crafting downgrade, or per-mod stats)
  is an open policy call.
- **Links:** #263, #238.

## 2026-10-16: a block's material instances share one render method, from the Java render_type or else the textures' alpha

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order).
- **Decision:** when the faces of one converted block want different
  `render_method`s (a holey texture gets `alpha_test`, an opaque one none), every
  material instance of that `minecraft:material_instances` object (the block's,
  each permutation's, and `item_visual`'s) gets the same one (#262):
  1. **The Java render type**, when every model the block resolved names the same
     one (NeoForge/Forge `render_type`, inherited from the nearest parent that
     names it, as `BlockGeometryBakingContext#getRenderTypeHint` does; unprefixed
     names are `minecraft:`). `solid` -> `opaque`, `cutout`/`cutout_mipped`/
     `cutout_mipped_all` -> `alpha_test`, `translucent` -> `blend`: the Bedrock
     method the Mojang docs describe for that kind of texture ("without an alpha
     layer"; "only fully opaque or fully transparent"; "like stained glass ...
     translucency"). `tripwire`, mod-registered names, two models naming
     different types, or a model naming none (its layer is set in mod code) are
     unread and fall through.
  2. **Otherwise the textures' alpha:** the one transparent method a face asked
     for (`alpha_test` for a texture with holes; alpha_test on the opaque faces
     draws them the same); `alpha_test` + `blend` together -> `blend`. Any other
     mix (e.g. `double_sided` + `alpha_test`) is left alone with a note, and the
     validator rejects it.
  Blocks whose faces already agree are untouched, even when the model names a
  render_type (reading render_type for every block is a separate change). The
  validator gains `block.render_method`: an error for any mix in one
  material_instances object (an unset method counts as `opaque`, the default).
- **Why:** Mojang's block docs say render_method "must be the same for each"
  (bedrock-samples@46ba6ea9 `documentation/Blocks.html`, minecraft:material_instances),
  and BDS 1.26.52.3 logs "MaterialInstances can't mix and match opaque and
  transparent materials" as a content-log ERROR (29 on the in-game check: FD 6,
  Supplementaries 22, Waystones warp plate 1). Java also draws a whole model in
  one block layer, so one method per block is the faithful reading. Nothing is
  invented: the method is the Java model's own render type or the one a face's
  texture already asked for.
- **Rejected:** splitting the transparent part into its own block (changes the
  block count and placement for a rendering detail); always `blend` (draws
  cutout textures with sorting artefacts and half render distance for no reason);
  dropping alpha_test to opaque (holes render as their RGB, often black).
- **Links:** #262, #238 (in-game check that found it).

## 2026-10-16: recipes are written in Bedrock's vanilla ids (GeyserMC/mappings), and a recipe naming an item the pack doesn't ship is residue

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order).
- **Decision:** two rules for the item ids a converted recipe names (#261).
  1. **Vanilla ids as Bedrock spells them.** A Java id becomes Bedrock's through
     GeyserMC/mappings `items.json` (pinned commit `81700ab5`, generated for Java
     26.3 / Bedrock 1.26.50; `portkit.data.java_items`): `minecraft:bricks` ->
     `minecraft:brick_block`, `lily_pad` -> `waterlily`, `oak_button` ->
     `wooden_button`, `terracotta` -> `hardened_clay`, `magma_block` -> `magma`,
     `oak_trapdoor` -> `trapdoor`, `red_nether_bricks` -> `red_nether_brick`,
     `end_stone_bricks` -> `end_bricks`, `nether_brick` (the item) -> `netherbrick`.
     When one Bedrock id stands for several Java items (beds, banners) the
     recipe slot carries Geyser's data value, written as vanilla Bedrock writes
     it (`{"item": "minecraft:bed", "data": 14}`; bedrock-samples
     `behavior_pack/recipes/chest_boat.json` writes `"data": 0` the same way).
     The rewrite is used only when the target is in Bedrock's own item list
     (bedrock-samples `mojang-items.json`). Covers crafting keys, ingredients and
     results, furnace input/output, smithing slots, and unlock entries. A bare
     Java id (`"black_dye"`) is Java's `minecraft:` one.
  2. **Only shipped items.** After every namespace converted and blocks whose
     textures didn't convert were withdrawn, a recipe naming a mod item the pack
     doesn't ship is removed and goes back to residue under its source recipe
     (`kind: recipe`, "names X, which the pack doesn't ship ..."); every file
     written from that source goes with it. An unlock entry naming such an item
     is dropped (AlwaysUnlocked, labelled, if none is left).
- **Why:** Bedrock Dedicated Server refuses both kinds ("The Item: X is missing
  or invalid, can't make the recipe" / "Recipe result malformed", in-game runs
  #238/#260), so a broken recipe ships nothing for the player and hides the gap
  from the residue. Residue names the missing item, which the agent can act on
  once that item converts. Geyser's table is the Java -> Bedrock map a
  production proxy uses, from a generator that reads both games; no id is
  guessed.
- **Not mapped (stay residue, with the reason):** a Java id whose Bedrock id
  *and* data another Java item shares (`tipped_arrow` and `spectral_arrow` are
  plain `arrow`; every explorer map is `filled_map`; `knowledge_book`,
  `debug_stick`, `furnace_minecart`), since writing it would make or take the
  other item; a target missing from Bedrock's item list (`light` ->
  `light_block`); a data value in a slot that holds a bare id (furnace,
  smithing).
- **Kept as written, with a note:** a vanilla id neither Bedrock's list nor the
  table knows. Today that is Java 1.21.1's `minecraft:chain` (Java 1.21.9 renamed
  it `iron_chain`, so Geyser's 26.3 table has no entry); BDS 1.26.52.3 loaded
  those recipes without an error in the #260 runs, so dropping them would lose
  working recipes.
- **Licence:** GeyserMC/mappings is MIT, and says it doesn't relicense
  Minecraft's own data; like Mojang's lists it is fetched by `portkit reference
  fetch`, sha256-pinned, cached, never vendored (`src/portkit/data/NOTICE.md`).
- **Rejected:** keeping a recipe whose items are missing (BDS drops it with two
  errors); rewriting it to a different emitted id (no source says which);
  narrowing a tag expansion to the members that ship (a recipe is never
  narrowed, #160); mapping with a hand-written table (unsourced); checking mod
  items at recipe time only (another namespace of the jar, or a converter that
  runs later, can ship an item; a block withdrawn for its texture afterwards,
  like `tconstruct:blazewood`, can't).
- **Fixtures:** recipes_mod, simple_block_mod, smithing_mod and
  two_namespace_mod named items they never declared, so their recipes would have
  failed in game; each now ships those items (item/generated or cube_all models),
  and two_namespace_mod's ingots are `steel_ingot` / `brass_ingot` (two
  namespaces' `items/ingot.json` would collide). agent_mod's sword recipe is a
  fourth residue group, waiting for the sword.
- **Links:** #261, #260, #238.

## 2026-10-15: converted crafting recipes carry `unlock` read from the Java recipe advancement; AlwaysUnlocked is the labelled fallback

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order).
- **Decision:** every `minecraft:recipe_shaped` and `minecraft:recipe_shapeless`
  the converter writes gets an `unlock` (`portkit.converters.recipe_unlock`).
  Its entries come from the jar's own recipe advancements
  (`data/*/advancement[s]/**` whose `rewards.recipes` names the recipe): in a
  single OR requirement group, each `minecraft:inventory_changed` criterion with
  exactly one plain item predicate (`items` / `item` / `tag`) gives its items or
  tag; `recipe_unlocked` criteria are skipped. An item is written only when this
  conversion ships it or Bedrock has it as a vanilla id (Mojang's item list,
  bedrock-samples `metadata/vanilladata_modules/mojang-items.json`, fetched by
  `portkit reference fetch` and sha256-pinned, never vendored); a tag only when
  the converted recipe takes that same tag. Every recipe written from one Java
  recipe (per-member expansions too) takes the same entries. When no
  advancement rewards the recipe, or nothing survives, the recipe gets
  `{"context": "AlwaysUnlocked"}` (an object, as vanilla writes every context),
  with a note. Furnace and smithing recipes are left as they were. The
  advancement files read for a shipped recipe count as consumed.
- **Why:** Bedrock Dedicated Server 1.26.52.3 logged "1.20+ Recipes require
  unlock data" for all 2,408 crafting recipes over the five in-game packs (#238
  run 38841956046), and not for furnace or smithing recipes. Java states what
  unlocks a recipe in the recipe book in data (its `has_<item>` advancement),
  and vanilla Bedrock's own recipes take the same items (bedrock-samples
  `behavior_pack/recipes`: 1,706 `item` and 19 `tag` unlock entries), so the
  item rule is the source's own, not a guess. A criterion Bedrock can't say (an
  AND of criteria, a count or component condition, another trigger) is dropped,
  which only narrows the unlock. Item ids are checked because BDS refuses the
  whole recipe for an unlock item it doesn't know ("has an invalid unlock
  ingredient"), and many Java vanilla ids aren't Bedrock's
  (`minecraft:oak_trapdoor` is `minecraft:trapdoor`). `unlock` decides when
  the recipe book lists the recipe; only with the `dolimitedcrafting` gamerule
  on ("Determines whether players should be able to craft only those recipes
  that they've unlocked first", learn.microsoft.com /gamerule) does it also
  gate crafting, as Java's `doLimitedCrafting` does with the same advancement.
  Recipe-book and crafting behaviour were not observed in game (the Script API
  can't list recipes).
- **Fallback:** AlwaysUnlocked, the vanilla crafting table's own unlock, for
  recipes Java gives no expressible advancement (Night Lights, Mekanism, Alex's
  Mobs and Mythic Metals' crafting recipes ship none). The recipe book lists
  them from the start.
- **Rejected:** AlwaysUnlocked for every recipe (drops what the mod says about
  progression, unlike vanilla Bedrock); `{"context": "None"}` for recipes without
  an advancement (Java's book doesn't list them until crafted, but whether
  Bedrock ever lists a `None` recipe is unverified, so the recipe could stay
  out of the book for good); `unlock` written as a list holding a context (BDS
  reads each list entry as an item and refuses it, branch run 38842744549);
  Java vanilla ids unchecked (refused by BDS, see above); `unlock` on furnace
  and smithing recipes (BDS doesn't ask for it; left for a recipe-book pass).
- **Measured:** in-game (ingame.yml on the branch, runs 38843367960 and
  38844281443, vs develop 38841956046): the
  unlock errors go 2,408 -> 0 on all six runs; every check still passes. With
  the unlock in place BDS validates further and reports ingredient and result
  ids the recipes already named that Bedrock doesn't have (Java vanilla ids such
  as `minecraft:lily_pad`, `minecraft:terracotta`, `minecraft:bricks`, and
  unshipped mod items), which it skipped before: those are #261. Corpus and
  deco set (20 mods): 3,860 crafting recipes take derived entries, 2,502
  AlwaysUnlocked;
  the advancement files read now count as consumed (corpus residue -2,546,
  sample -2,796, mean coverage 12.56% -> 12.94%); only `recipes/*.json` gain
  `unlock`, every other pack file md5-identical; mct 0 errors.
- **Links:** #260, #238 (pick 3), #261.

## 2026-10-15: converted packs are checked in Mojang's Bedrock Dedicated Server by a generated Script API pack; downloading the server is an EULA acceptance, made explicitly

- **Status:** approved (Alex, 2026-10-15). All six DEFAULT picks on PR #259
  were chosen: (1) CI passes `--accept-eula` and the workflow runs only on
  manual dispatch; (2) one BDS release is pinned by URL + sha256 and bumped by
  hand; (3) report-only until converted recipes carry unlock data, then a
  known-errors baseline and a PR gate; (4) dispatch-only now, nightly once
  picks 1 and 3 settle; (5) no cache of the server zip; (6) a browser-like
  User-Agent for the minecraft.net download.
- **Decision:** `portkit ingame` fetches a pinned Bedrock Dedicated
  Server (1.26.52.3 Linux zip, sha256 `f6348d84...71c6`, from minecraft.net)
  only with `--accept-eula`, installs a converted tree and a generated check
  behavior pack (`portkit.ingame.testpack`; stable `@minecraft/server` 2.0.0)
  into a flat creative world, and reads the server output: every block places
  and reads back, every item and block item spawns, a converted container
  (#226) has the slot count the converter wrote, a connection block (#221) has
  its four cardinal states joined to its own kind and not to air. Any failed
  check, an unfinished script, or a content-log ERROR fails the run; the
  report, server output and content log are uploaded, never the server.
  `.github/workflows/ingame.yml` runs it on x86-64 Ubuntu 24.04 for Farmer's
  Delight (NeoForge), Waystones, Supplementaries, Cluttered (with and without
  `upcoming_creator_features`) and Night Lights (`fixtures/ingame/mods.toml`
  pins the two deco jars), manual dispatch only, report-only.
- **Terms (read 2026-10-15):** the download page
  (minecraft.net/en-us/download/server/bedrock) gates DOWNLOAD behind "I agree
  to the Minecraft End User License Agreement and Privacy Policy", linking
  minecraft.net/eula and the Microsoft Privacy Statement. The EULA: "If you
  buy, download, or use any of our Services ... that means you agree to this
  Minecraft EULA and the Microsoft Services Agreement"; "you must not
  distribute anything we've made unless we specifically agree to it", which
  includes to "give copies of our game software or content to anyone else".
  Hence: the CI download is an acceptance on the repo owner's behalf (pick 1),
  and the zip is neither committed, cached nor put in an artifact.
- **Found on the first runs (develop 9c44ef0 converter, Actions run
  38838745295):** every check passes on all six runs (five packs, Cluttered
  counted once below: place 1,018, items 385, block items 1,018, containers
  74/74 at the converted slot counts, connection 37/37), and every run fails on content-log errors: (a) every
  converted recipe is logged "1.20+ Recipes require unlock data" (format
  1.20.10 without `unlock`; 2,408 recipes over the five packs); (b) 301 recipes
  name an item the pack doesn't ship ("missing or invalid" + "Recipe result
  malformed": Cluttered 262 over 199 ids, Supplementaries 36, Farmer's Delight
  3), including two vanilla ids with different Bedrock names
  (`minecraft:bricks`, `minecraft:white_bed`); (c) blocks mixing opaque and
  transparent `material_instances`, 29 errors (Supplementaries 22, Farmer's Delight 6,
  Waystones' warp plate); (d) Farmer's Delight's netherite knife smithing
  recipe: "base item is not a piece of armor or equipment".
- **Why:** almost every converter PR ended "unverified in game"; the server
  is the oracle for what the game accepts. Scripted checks, not GameTest
  structures: `@minecraft/server-gametest` needs the Beta APIs experiment and
  structure files per test, while a stable-API script on world load needs
  neither and covers generated per-pack checks.
- **Rejected:** GameTest framework (experiment toggle, per-test structures);
  caching the server zip (a stored copy outside Mojang's distribution);
  running on the PR gate now (every pack is red on (a) until recipes carry
  `unlock`); tracking the newest BDS release (moves checks unannounced).
- **Unverified:** whether the server still registers a recipe it logs (a) for
  (the log is ERROR; Script API can't list recipes); anything client-side
  (geometry, textures, bone visibility, render methods, container UI).
- **Links:** #238, PR #259, #221, #226, #87.

## 2026-10-15: uvlock re-maps a hand-set uv as Java does, by the game version the mod declares

- **Decision:** A blockstate turn with `"uvlock": true` no longer refuses a
  face with a hand-set uv. `models.uvlock_uv` ports Java's uvlock: one matrix
  per face, `GLOBAL_TO_LOCAL[face] * R^-1 * LOCAL_TO_GLOBAL[face']` about the
  texture centre (BlockModelRotation `rotateYXZ(-y, -x, 0)`, BlockMath's
  per-face table), in exact integers. Before MC 1.21.5 Java applies it
  through `FaceBakery#recomputeUVs` (two uv corners, per-axis sign kept,
  rotation `floorMod(-round(atan2/90)*90, 360)`); from 1.21.5 it maps each
  vertex's uv (`ModelState#inverseFaceTransformation`). The generation is read
  from the mod's declared version (`SourceMod.minecraft`, set for one block
  conversion through `models.UVLOCK_GAME`); a mod declaring none gets a face
  only where both generations bake the same uv at every vertex, else residue
  naming the split. The face's (uv, rotation) is then carried by the rigid
  turn as before; a face whose uv is position-derived keeps landing on the
  position-derived uv where it lands (unchanged, and checked equal to Java's
  recompute for every non-degenerate box and all 16 turns). Texture-rotated
  faces stay refused in `turn_locked` (Java's recompute flips 90/270 even
  for an unturned uvlocked model before 1.21.5, which portkit does not model).
- **Why:** #236's second slice. Buttons, fence gates, palisade fences and
  attach-face blocks (BetterEnd, Tinkers, Supplementaries, Silent Gear,
  Storage Drawers, Cluttered, Biomes O' Plenty, Cataclysm, Quark, ...) stopped
  only at this refusal. Grounding: the MC 1.21.1 and 1.21.8 client jars run
  in a JVM over 3,840 cases (16 turns x 6 faces x 4 rotations x 10 uvs) match
  the port exactly (tests/data/uvlock_java.json keeps 576 of them as numbers);
  1.16.5, 1.19.2 and 1.20.1 decompile to the same recomputeUVs body and
  table; the 1.21.4/1.21.5 cut is where Mojang's mappings move from
  `recomputeUVs`/`getUVLockTransform` to `faceTransformation`/
  `getFaceTransformation`.
- **Rejected:** taking only faces both generations agree on for every mod
  (leaves Cataclysm's 1.20.1 murals as residue although their Java is known);
  porting one generation for all mods (wrong for the other); keeping the
  refusal.
- **Links:** #236, PR #258, #257 (first slice).
- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order; PR #258).

## 2026-10-15: the vanilla parents random mods name most (orientable, cross, carpet, button, fence gate, cube_top and friends) are read from the fetched templates

- **Decision:** The fetched vanilla template set (`portkit reference fetch`,
  misode/mcmeta 1.20.1-summary at the same commit, re-pinned) adds
  `cube_bottom_top`, `cube_top`, `orientable`, `orientable_with_bottom`,
  `orientable_vertical`, `template_glazed_terracotta`, `dried_kelp_block`,
  `cross`, `flower_pot_cross`, `carpet`, `button`, `button_pressed`,
  `template_fence_gate`, `_open`, `_wall`, `_wall_open` and `ladder` (with
  `thin_block`). `cube_top` and `orientable_vertical` join the full-cube face
  table (Bedrock's `full_block`, as `cube_all` and `orientable` already map).
  A plain (stateless or coded-facing) block whose model only names a fetched
  template that isn't a full cube now takes the template's boxes as a custom
  shape, through the same parent-chain and `#texture` resolution the stairs,
  walls and panes use; a parent outside the set keeps its refusal. Java's
  `rescale` on a template element's rotation (the cross and flower-pot planes)
  is folded into the box: stretched about the rotation origin by 1/cos(angle)
  on the two turned axes. Two templates changed their boxes between versions
  and are read only for mods declaring the version they match or later
  (`SINCE`): the button (top-face uv turned in 1.20) and the ladder (back-face
  uv mirrored in 1.17); an older or undeclared mod keeps such a block as
  residue saying so. Tinted templates (`tinted_cross`, `leaves`, `lily_pad`)
  are not fetched, and a template face with a `tintindex` is refused.
- **Why:** These parents were the largest vanilla-parent residue in the
  measured data (corpus, deco set and the 50-mod gap-leaderboard sample, raw
  reasons ranked by parent on develop d0ae602): 1,251 entries named them
  (carpet 435, cross 320, glazed terracotta 185, flower-pot cross 74,
  orientable 55, cube_bottom_top 52, button 42, fence gate 36, ...). The
  boxes are Mojang's data, read from the fetched summary (never vendored), so
  converting them is a lookup, not an inference. Compared on the fields the
  converter reads (from, to, rotation, faces) across mcmeta's 1.16.5, 1.17.1,
  1.18.2, 1.19.2, 1.19.3, 1.19.4, 1.20, 1.20.1, 1.21.1, 1.21.8, 26.1 and 26.3
  summaries they are identical except the button and ladder above. No 26.x
  release moves them (unlike bars in 26.1, #221); 26.3 only swaps `shade:
  false` for `shade_direction_override` on the cross, flower pot and ladder
  planes, lighting hints the converter doesn't read. The rescale fold is
  exact: FaceBakery scales each rotated vertex about the origin by a factor
  that is the same on both turned axes, so it commutes with the rotation;
  uvs are Java's explicit ones either way. After (CI real-mods 38829976227,
  gap-leaderboard 38829978831): 1,143 of the 1,251 entries convert; corpus
  residue -239 (Farmer's Delight -54/-58, BetterEnd -65, Tinkers -49,
  Supplementaries -5, Mekanism -3, Silent Gear -2, Alex's Mobs -2, Mythic
  Metals -1; Create, Waystones, Storage Drawers md5-identical); deco -147
  (Wallpapercraft -115 carpets, Cluttered -32; the other 10 md5-identical);
  sample -1,038, mean coverage 12.24% -> 12.47% (Chipped -709, Biomes O' Plenty
  -90, Farmer's Delight -54/-52, Quark -51, Cobblemon -42, BetterEnd -22,
  Deeper Darker -13, Supplementaries -5; the other 39 unchanged). mct 0 errors
  on every tree. The 108 left fail later and say why: buttons (37) and fence
  gates (36) are turned with uvlock while vanilla's template sets its own uvs
  (the existing "hand-set uv" refusal), ladders (20) reach outside the block
  at some facing, 8 furnaces extend a model in another namespace, 5 Quark
  buttons declare no game version.
- **Rejected:** Bedrock's built-in `minecraft:geometry.cross` for the cross
  (one more special case, and it only serves the plain cross; the template
  route covers the cross, the potted cross and 6-way-facing crosses alike);
  vendoring the models (Mojang's EULA; the fetch is the existing path);
  one template set per game version (two templates differ, and only for old
  versions; refusing them there is honest and cheap); converting tinted
  templates (their colour is code: a biome or colour handler, #87); reading
  `rescale` on a mod's own elements (it would change packs of mods this
  decision doesn't touch; left as a follow-up).
- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order; PR #257).
- **Links:** #236, #221, #56, #87, #257.

## 2026-10-15: Forge SRG and Fabric intermediary jars are read in Mojang's names (fetched, pinned name tables)

- **Decision:** the bytecode readers (facing/boxes #212, booleans #215/#219,
  light #213, containers #226, entities #232) keep matching Minecraft by its
  Mojang names, and a renamed jar is put into those names before they run.
  `portkit reference fetch` downloads, per pinned game version, Mojang's
  `client.txt` (sha1 from Mojang's version manifest) and MCPConfig's
  `joined.tsrg` (Forge, sha256) or FabricMC/intermediary's `<version>.tiny`
  at commit 91686875 (Fabric/Quilt, sha256), joins them on the obfuscated
  names into one SRG/intermediary -> Mojang table, checks the table's sha256
  and caches it (`src/portkit/data/mappings.py`). Pinned: SRG 1.19.2, 1.20,
  1.20.1; intermediary 1.19.2, 1.20, 1.20.1, 1.21, 1.21.1, 1.21.8. The table
  is chosen by the loader and the exact Minecraft version the mod declares
  (the lower bound of a range): Forge and NeoForge 1.20.1 -> SRG,
  Fabric/Quilt -> intermediary; NeoForge 1.20.5+ and 26.1+ jars hold Mojang
  names and get none. `ClassIndex.set_remapper` rewrites class names, member
  names and descriptors in each class's constant pool and declarations as it
  is parsed; String constants are never touched, and only names shaped like
  `m_N_`/`f_N_`/`method_N`/`field_N`/`comp_N`/`net/minecraft/class_N` change,
  so a Mojang-named jar parses exactly as before. An id that maps to two
  Mojang names (none in SRG; 8-10 per intermediary version) stays unmapped.
  Without the table a renamed jar reads as before and the conversion notes say
  to run the fetch. 1.20.1's `Properties.copy` (ofFullCopy's earlier name; it
  copies lightEmission, client jar `dca$d.a(dca)` bytecode 57-60) is read like
  ofFullCopy.
- **Why:** most of the standard corpus (Forge 1.20.1, Fabric) got nothing
  from the readers (#235). Same facts on every build of one mod: Handcrafted
  4.0.3 Fabric 1.21.1 (intermediary) vs NeoForge 1.21.1 (Mojang), and 3.0.6
  Forge 1.20.1 (SRG) vs Fabric 1.20.1 (intermediary): every reading of all
  267 blockstates (placement, boxes, collision, light, booleans, containers)
  and both entities identical, and the converted packs byte-identical apart
  from the class-file count.
- **Licences:** Mojang's mappings may be used "for development purposes" but
  not redistributed "complete and unmodified"; MCPConfig is zlib-style (Forge
  Development LLC), intermediary CC0. The joined table carries Mojang's names,
  so it is handled like Mojang's file: fetched at runtime, never vendored
  (data/NOTICE.md). Nothing is vendored, so no redistribution choice is made.
- **Rejected:** vendoring the tables (Mojang's notice); matching SRG names
  one by one in each reader (#232 did two; unbounded); one table for every
  version (Mojang names move between versions; ids don't, so the declared
  version's table is exact); guessing a version for a jar that declares none
  (Alex's Mobs) or that no table is pinned for (Forge 1.16.5's MCP names).
- **Measured (reader counts, all blockstates, off -> on):** Create
  registered 23 -> 201, placement 0 -> 5, shape 17 -> 88, boolean starts
  0 -> 38; Supplementaries registered 0 -> 7, shape 0 -> 6; Storage Drawers
  1.19.2 registered 9 -> 69, placement 0 -> 56, shape 9 -> 38, collision 0 ->
  69, light 0 -> 69; Fairy Lights 1.20.1 (deco) registered 0 -> 21, collision
  0 -> 21, light 0 -> 1; Handcrafted Fabric 1.21.1 0 -> 267 registered, 166
  placement, 192 shape, 77 containers. Unchanged: Waystones (Balm),
  Mythic Metals (owo field names), BetterEnd (BCLib), Tinkers (Mantle),
  Alex's Mobs (no declared version): their registrations, not their names,
  are what the reader can't follow. Converted output: Create 6 blocks and
  Supplementaries 3 blocks change (read placement/boxes replace DEFAULTs);
  coverage, file and residue counts unchanged everywhere, so no rebank; all
  Mojang-named corpus jars and the 7 deco fixtures md5-identical.
- **Left:** registration patterns the reader can't follow on these jars
  (Registrate, Balm, owo, BCLib, Moonlight's RegHelper), 1.20.1 vocabulary
  the readers still lack beyond `Properties.copy`, Forge 1.21+ / MCP-era
  (1.16.5) names, versions not pinned yet.
- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order), PR #256.
- **Links:** #235, PR #256, #212, #213, #215, #219, #226, #232.

## 2026-10-15: A random sample of popular Modrinth mods, ranked by residue reason (gap leaderboard)

- **Status:** approved (Alex, 2026-10-15). All six DEFAULT picks chosen on
  PR #255 (https://github.com/anchapin/portkit-v2/pull/255#issuecomment-6201666043):
  (1) measure every licence, ARR included, jars never committed; (2) 50 mods
  now, ~200 after clean nightlies; (3) content mods only; (4) nightly, with
  mct; (5) each mod's newest release; (6) sample rebuilt by hand in a PR.
- **Decision:** besides the hand-picked corpus, portkit measures a sample of
  popular mods built from Modrinth's download ranking
  (`fixtures/sample/mods.toml`, generated by `portkit sample build`, pinned by
  version id + sha512, jars never committed) and publishes a "gap
  leaderboard": residue reasons normalized (ids, paths, quoted names, numbers
  blanked) and ranked by how many sample mods each blocks, with a trend
  against the previous run. Report-only; it never gates a merge. Picks
  (all DEFAULTs, approved): every licence is measured, as the corpus already does
  (pick 1); 50 mods to start (pick 2); content mods only - a content
  category, not a library, not client-only (pick 3); nightly (pick 4); each
  project's newest release, any game version (pick 5); the sample is rebuilt
  by hand in a PR (pick 6).
- **Why:** gains on ~20 hand-picked mods only find gaps where we already
  looked (2026-10-15 scaling brainstorm). The raw download ranking is mostly
  libraries and client-side mods with nothing to convert (Fabric API, Sodium,
  Iris lead it), so a content filter is needed for the sample to say anything.
  Measuring a jar downloaded from Modrinth's CDN, without committing or
  redistributing it, is how the corpus already handles All Rights Reserved and
  custom-licensed mods (Waystones, Create, Supplementaries).
- **Rejected:** hand-picking more mods (the bias this fixes); CurseForge in
  this slice (needs an API key and separate terms); weighting by kid
  relevance now (no sourced score to weigh by); failing CI on leaderboard
  movement (the sample changes when mods update; the corpus ratchet is the
  gate).
- **Links:** #234; docs/gap-leaderboard.md; docs/brainstorm-2026-10-15-scaling.md.

## 2026-10-15: Display-only items are allowed when the visual is real and the behavior isn't portable

- **Status:** approved (Alex, 2026-10-15); item policy approved by Alex in #128 on 2026-10-11.
- **Decision:** portkit may ship an item that only looks right, when its
  look comes from the mod's own assets and its behavior is Java code with no
  Bedrock mapping. Such an item carries its icon, its name from the mod's lang
  and an honest stack size, and nothing else (no mining speed, damage,
  durability or enchantability), and the report says it is display-only and
  that the behavior stays in Java. First use: the 1,160 baked Tinkers preset
  tools; Tinkers' part items ship as plain inert items, like ingots.
- **Why:** The visual is real data, and leaving it out loses coverage
  without making anything more correct. Inventing stats would break the
  no-fabrication rule (2026-10-09); saying "display-only" doesn't.
- **Rejected:** Icons only, with no item (the first prototype): the art
  ships but nothing in the game shows it. Functional tools: would need
  Tinkers' stat formula, i.e. fabrication.
- **Names (Alex, 2026-10-15):** every preset tool is named the way Tinkers
  names that stack, read from source rather than kept plain. The tool
  definition's display-name modules run in JSON list order, each given the
  previous name (`ToolNameHook.ComposeMerger` L86-99; `ModuleHookMap.createMap`
  L32-47, a `LinkedHashMultimap`): `material_name` (filter `all` /
  `repairable`), `stat_types_name`, `fixed_material_name`,
  `unique_material_name` (the item's own `.material.<ns>.<m>` key, ignoring
  the incoming name) and `custom_material_name` (`material.<ns>.<m>.<suffix>`,
  else the material name, in `item.<ns>.tool.format`), module names as
  `TinkerTools#registerRecipeSerializers` registers them. A tool with no name
  module gets the hook default (`ToolHooks` L134): the materials whose slot
  stat type `canRepair`, which is `defaultStats instanceof
  IRepairableMaterialStats` (`MaterialStatType` L35/L45), read per stat id
  from the jar's stats classes (`adapters/tconstruct/stat_types.py`; Tinkers
  3.12.1.231 @a5a03249). No hardcoded table. The 16 tools that had kept the
  plain name (battlesign, broad_axe, cleaver, javelin, longbow, mattock,
  melting_pan, minotaur_axe, pickadze, sledge_hammer, slime_boots,
  slime_helmet, slime_leggings, slime_wings, vein_hammer, war_pick) now read
  e.g. "Iron Broad Axe", "Cobalt Longbow", "Skeleton Slimeskull", "Magma
  Elytra"; 435 of their 438 presets change, the other 3 are Slimelytra in
  Java too. A rule the jar doesn't answer (no classes, an undeclared stat
  type, an unknown module) still keeps the plain name and says why in the
  report; none in Tinkers 3.12.1.231.
- **Links:** #128 (Alex approved, 2026-10-11), PR #129.

## 2026-10-15: Farmer's Delight stations move into an adapter; the core names no mod

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order), PR #254.
- **Decision:** step 8 of the #245 migration, the last. The cutting board
  (the Farmer's Delight part of `converters/stations.py`, now
  `adapters/farmersdelight/cutting_board.py`: pinned sources, versions,
  tool-ability tags, the recipe resolver, `_convert_cutting` as `convert`),
  `cooking_pot.py`, `stove.py`, `skillet.py` and `feasts.py` move unchanged to
  `adapters/farmersdelight/`, their runtimes to
  `adapters/farmersdelight/runtime/` (pick 6a: still shipped at
  `scripts/portkit/`). `StationHooks` gains `recipe_types` and
  `shared_types`, and its `convert` takes the deferred recipes of those
  types; `recipes.convert` asks `stations.station_recipe_types()` instead of
  its two `farmersdelight:` literals. `converters/stations.py` keeps only the
  seams (each asks every hook in registry order), `_loot_name`, `_lang_key`,
  `_shipped_sounds`, the kit re-exports and the `main.js` entry. Tests move
  with the code (pick 7a). Core namespace allowlist 97 -> 0.
- **Why:** audit section 7 step 8 and picks 1-10 (approved by Alex,
  2026-10-15). Farmer's Delight registers before Waystones (alphabetical), and
  its hook runs its five stations in the old order and joins their entry
  lines, so pack trees are md5-identical (all 13 corpus jars but Tinkers and
  Mekanism checked locally; those on GitHub).
- **Rejected:** keeping the cutting board in the core as the "reference"
  station (it names `farmersdelight` 13 times); a re-export shim at the old
  module paths (the core would still import an adapter).
- **Links:** #245, #177, PRs #253, #254; `docs/adapter-audit-2026-10-15.md` section 7.

## 2026-10-15: Waystones move into an adapter behind a `station` hook

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order), PR #253.
- **Decision:** step 7 of the #245 migration. `converters/waystones.py`
  (#178) moves unchanged to `adapters/waystones/convert.py`, its runtime
  (`waystone.js`, `waystone_core.js`) to `adapters/waystones/runtime/` and
  its cited config defaults to `adapters/waystones/data/` (picks 6a, 9a; the
  runtime still ships at `scripts/portkit/` beside the kit files it imports).
  A new optional hook, `Adapter.station` (`StationHooks`: `blocks`,
  `loot_names`, `derived_textures`, `lang_keys`, `convert`), is asked by every
  seam of `converters/stations.py` in registry order after the core's own
  Farmer's Delight stations; loot tables an adapter names go to it, the rest
  to the feasts, as before. Tests move with the code (pick 7a:
  `tests/adapters/waystones/`, `tests/js/adapters/waystones/`); the node test
  loader resolves an adapter runtime's missing `./` imports to
  `src/portkit/runtime/`, as they resolve in a pack. Core namespace allowlist
  138 -> 97.
- **Why:** audit section 7 step 7 and picks 1-10 (approved by Alex,
  2026-10-15). With one station adapter the hook gives the old calls in the
  old order (Waystones' converter ran last), so pack trees are md5-identical
  (Waystones, Farmer's Delight fabric and neoforge, Alex's Mobs checked
  locally; the corpus gate on GitHub).
- **Rejected:** a re-export shim at `converters/waystones.py` (the core would
  still import an adapter); shipping the runtime under
  `scripts/portkit/adapters/waystones/` (pick 6b: every pack's paths change
  for no player-visible gain).
- **Links:** #245, #178, PR #252; `docs/adapter-audit-2026-10-15.md` section 7.

## 2026-10-15: Citadel books move into a library adapter behind a `books` hook

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order), PR #252.
- **Decision:** step 6 of the #245 migration. `converters/books.py` (the
  Citadel guide-book reader, #182) moves unchanged to
  `adapters/citadel/books.py`; `adapters/citadel` registers it as a library
  adapter (`library=True`, namespace `citadel`) through a new optional hook,
  `Adapter.books` (a `BookReader` of `plan`, `lang_text`, `convert`).
  `convert_all` asks every reader in registry order (plans once the items
  have converted, page text merged into the lang converter's `book_text`,
  files merged and each non-empty entry line passed to `stations.convert`).
  The viewer JS (`book.js`, `book_core.js`, `forms.js`) stays core. Tests move
  with the code (`tests/adapters/citadel/`, pick 7a); new tests pin the
  registration and the hook's order. Core namespace allowlist 143 -> 138.
- **Why:** audit section 7 step 6 and picks 1-4 (approved by Alex,
  2026-10-15). With one reader the hook gives exactly the old calls in the
  old order, so pack trees are md5-identical (Alex's Mobs, Waystones,
  Farmer's Delight fabric, Storage Drawers 1.19.2 and Night Lights checked
  locally; the corpus gate on GitHub).
- **Rejected:** keeping a re-export shim at `converters/books.py` (the core
  would still import an adapter directly); folding books into the generic
  `convert` hook (books need the converted items first and return a main.js
  entry, which that hook can't carry).
- **Links:** #245, PR #251; `docs/adapter-audit-2026-10-15.md` section 7.

## 2026-10-15: the generic station kit; shipped runtime bytes may change when behaviour is identical

- **Status:** pick 8 (sub-question) **approved (Alex, 2026-10-15)**: "Yes, as long as behaviour is identical that's all that matters. Basically as long as the user in bedrock gets the same or similar enough experience, that's all we care about." The kit itself: approved (Hark, high confidence under Alex's 2026-10-14 campaign order), PR #251.
- **Decision:** step 5 of the #245 migration. The parts of the scripted
  station pattern that name no mod move into a kit any adapter can build on
  (#239's templates start here). Python: `converters/station_kit.py` holds the
  Script API pins and entry path, `FacingBlock`/`Overlay`/`DerivedTexture`,
  `BEDROCK_TOOL_TAGS`, `VANILLA_SOUNDS`, `runtime_source`, `js_module`, moved
  unchanged (still importable from `stations`). Runtime JS: helpers that were
  copied between mods' runtimes are now one copy each: new
  `station_core.js` (pure: `storageKey` from four `*_core.js` copies,
  `storagePrefix`, the counter-clockwise side step from the cooking pot and
  cutting board, the heat rule from `cooking_pot_core.js`, `destroyCommand`
  from feasts and Waystones, `HoldTimer` from Waystones' scroll timer), new
  `forms.js` (`show` with the UserBusy retry, from `waystone.js` and
  `book.js`), and `station_storage.js` gains `loadAll`, `enchantLevel`,
  `blockView`, `blockBelow`, `facingOf`, `heldAt`. `KIT_FILES`
  (`station_core.js`, `station_storage.js`) ship beside every station
  runtime and `forms.js` with Waystones and the book viewer. Conversion now
  fails (RuntimeError) if a shipped script imports a `./` file the pack does
  not ship (`station_kit.unresolved_imports`).
- **Why:** pick 8a (the station kit) with Alex's answer above: shipped bytes
  may change; player-facing behaviour may not. Every moved function is the
  same code (same arguments, same strings, same order of checks); only where
  it lives and how it is imported changed. The md5 diff over the 13 corpus and
  7 deco trees lists every changed file in the PR; node runtime tests pass
  with the old tests kept (calls to moved helpers ported to `station_core.js`)
  and new `tests/js/station_core.test.mjs`.
- **Rejected:** keeping every runtime's text identical (the kit would then be
  a Python-only move and the copies would stay); changing any helper's
  behaviour while moving it (a player could notice; any such change is a
  separate pick for Alex); shipping the kit in every pack with scripts
  (toggle-only packs need none of it, and their bytes stay identical).
- **Links:** #245, PR #246, PR #250; `docs/adapter-audit-2026-10-15.md`
  (section 5, promote to #239).

## 2026-10-15: the per-mod recipe residue tables live in their mods' adapters

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order), PR #250.
- **Decision:** step 4 of the #245 migration (pick 5: Python first). The
  tables in `converters/recipes.py` that give a mod's recipe types their
  residue kind and reason move unchanged into one adapter per mod, as
  `recipe_reasons`: `tconstruct` (30 `fluid_recipe`, 39 `modular_tool`, 2
  `code_recipe`), `silentgear` (9 `modular_tool`, 1 `code_recipe`), `create`
  (2 `fluid_recipe`, 11 `machine_recipe`, 2 `code_recipe`), `mekanism` (26
  `machine_recipe`, 1 `code_recipe`; in `adapters/mekanism/recipes.py`),
  `betterend` (1), `bclib` (2, a library adapter: BetterEnd's recipes use
  BCLib's types), `mythicmetals` (3) and `supplementaries` (1), each with the
  source citations that were beside it. Phrases only one mod uses (Create's
  kinetics/basin/chance, Mekanism's chemicals) move with it; the generic
  "Bedrock lacks X" phrases stay in core under public names
  (`NO_BEDROCK_FLUID`, `NO_PER_STACK_TOOL`, `NO_BEDROCK_MACHINE`,
  `NO_BEDROCK_MB`). `fluid_recipe_reason`, `modular_tool_reason`,
  `machine_recipe_reason` and `code_recipe_reason` keep their signatures and
  answer from the registry; `recipes.convert` asks the registry seam once
  and drops its three per-kind lookups (the tables are disjoint, which
  `check()` enforces, so precedence is unchanged). Every reason string is
  identical (all 130 types compared before and after). The allowlist drops
  by 164 (307 -> 143; `recipes.py` keeps only Farmer's Delight's 2 station
  types, which move with the FD adapter). The Mekanism and Create machine
  tests move to `tests/adapters/<mod>/`; the fluid, modular-tool and
  code-recipe tests cover several mods and stay in `tests/`. All 13 corpus
  and 7 deco conversions are md5-identical to develop.
- **Why:** the tables were the bulk of the core's mod namespace literals
  (164 of 313); each is per-mod data with per-mod citations.
- **Rejected:** JSON tables now (pick 5b: the reasons are built from shared
  phrases, so JSON needs phrase keys; later, where a #239 template wants to
  read them); one "recipe tables" adapter for all mods (pick 2a is per mod).
- **Links:** #245, #172, #173, #174, #175, #180,
  `docs/adapter-audit-2026-10-15.md` section 7 step 4.

## 2026-10-15: Alloy Forgery's forge recipes and forge data live in its adapter

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order), PR #249.
- **Decision:** step 3 of the #245 migration. `converters/alloy_forge.py`
  moves unchanged to `src/portkit/adapters/alloy_forgery/forge.py`, and
  `adapters/alloy_forgery/__init__.py` registers it: `recipe_reasons` maps
  `alloy_forgery:forging` to `machine_recipe` with a computed reason
  (`forging_reason(recipe, forge_names(mod))`, the reason the 2026-10-15
  #171 entry describes), and `convert` claims the forge data as
  `machine_data`. `recipes.py` no longer imports Alloy Forgery and drops its
  `FORGING` branch; `alloy_forge.convert` leaves `CONVERTERS`, and
  `adapter_data` runs the adapter's `convert` in the same place (right after
  the entity converter). `forge_names` is now read per forging recipe instead
  of once per namespace (same value; Mythic Metals has 62 such recipes and
  one forge file). `ADAPTERS` is `(alloy_forgery, mantle, mekanism)`. The
  allowlist drops by the 2 literals that moved (309 -> 307). The tests move
  to `tests/adapters/alloy_forgery/`. All 13 corpus and 7 deco conversions are
  md5-identical to develop.
- **Why:** Alloy Forgery is a separate mod only Mythic Metals' data uses in
  the corpus; it was the last converter module importing into `recipes.py`.
- **Rejected:** caching `forge_names` per mod inside the adapter (state in a
  pure converter for no measurable gain).
- **Links:** #245, #171, `docs/adapter-audit-2026-10-15.md` section 7 step 3.

## 2026-10-15: Mantle's and Mekanism's load-condition types live in their adapters

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order), PR #248.
- **Decision:** step 2 of the #245 migration. `mantle:tag_filled` and
  `mantle:tag_combination_filled` move from `conditions.py` to
  `src/portkit/adapters/mantle` (a library adapter, `library=True`: Mantle is
  the library Tinkers' Construct's data uses), and
  `mekanism:mod_version_loaded` to `src/portkit/adapters/mekanism`, each as a
  `conditions` hook evaluated through the registry seam in
  `LoadContext._one`. The handlers are the old code, unchanged; they use the
  core's helpers (`LoadContext.tag_filled`, `loaded`, `tags`, and `present`,
  renamed from `_present` because an adapter now calls it; `ITEM_REGISTRY`
  is the public name of the item-registry values). `ADAPTERS` is
  `(mantle, mekanism)`, alphabetical. `referenced_flags` is untouched (it
  still lists these types as candidate flags, as before). The core namespace
  allowlist drops by the 4 literals that moved (313 -> 309; `conditions.py`
  leaves it). The Mantle tests move to `tests/adapters/mantle/`; Mekanism's
  condition had no test and gets one in `tests/adapters/mekanism/`. All 13
  corpus and 7 deco conversions are md5-identical to develop.
- **Why:** these are the only mod-defined condition types the core evaluated
  by name; every other mod condition is a cited config flag
  (`config_flag_defaults.json`, which stays in core per pick 9).
- **Rejected:** keeping Mantle in core as a "generic format" (pick 2b).
- **Links:** #245, `docs/adapter-audit-2026-10-15.md` section 7 step 2.

## 2026-10-15: single-mod code reaches the core only through an explicit, ordered adapter registry

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order), PR #247; built to Alex's approved picks 1-4 (2026-10-15).
- **Decision:** step 1 of the #245 migration (`docs/adapter-audit-2026-10-15.md`
  section 7). `src/portkit/adapters/__init__.py` defines `Adapter`, a frozen
  dataclass of optional hooks (`name`, `namespaces`, `library`, and the hooks
  `conditions` (load-condition type -> handler), `recipe_reasons` (Java recipe
  type -> residue kind and a fixed or computed reason) and `convert` (a
  per-mod data converter)), and `ADAPTERS`, an explicit ordered tuple, empty
  in this PR. `check()` refuses two adapters with one name, a condition or
  recipe type claimed twice, and a claim outside the adapter's namespaces, so
  registry order never decides between adapters. The core asks the registry
  at three seams: `LoadContext._one` for a non-builtin condition type, before
  the config-flag fallback; `recipes.convert` for a recipe type with no
  Bedrock mapping, before the per-kind tables and the "special recipe" rule;
  `convert_all` through `converters.adapter_data`, placed right after the
  entity converter (where `alloy_forge.convert` runs). The core imports the
  registry lazily inside those functions, so an adapter may import core
  modules. Station hooks (blocks, loot, textures, lang, runtime) come with the
  station moves (steps 5-8). With no adapter registered the output is
  unchanged: all 13 corpus and 7 deco conversions are md5-identical to
  develop.
- **Why:** the moves that follow (load conditions, Alloy Forgery, recipe
  tables) each need one of these seams; landing the seams first, empty, keeps
  each move a cut-and-paste with an md5 gate.
- **Rejected:** entry points or package scanning (pick 3: order would follow
  installation or import order, and byte-identical output needs a fixed
  order); an abstract base class (pick 4); adding every station hook now
  (unused hooks would be guesses about the station moves' shape).
- **Links:** #245, PR #246, PR #247; `docs/adapter-audit-2026-10-15.md`.

## 2026-10-15: the core may not gain mod namespace literals (ratchet lint, allowlist mode); the adapter interface stays open

- **Status:** lint and audit approved (Hark, high confidence under Alex's 2026-10-14 campaign order), PR #246; adapter interface picks 1-10 in `docs/adapter-audit-2026-10-15.md` section 6 **approved (Alex, 2026-10-15)**, each as recommended (1a, 2a, 3a, 4a, 5a, 6a, 7a, 8a, 9a, 10a). Pick 8's sub-question (may the station-kit extraction change shipped runtime JS bytes?) **approved (Alex, 2026-10-15)**: yes, when player-facing behaviour is identical; see the 2026-10-15 station kit entry above.
- **Decision:** first slice of #245 (step 1 + step 4 in allowlist mode), no
  code moves and no behaviour change. (1) `docs/adapter-audit-2026-10-15.md`
  lists the single-mod code in `src/portkit`: about 10,300 of 37,132 lines
  (Waystones 4,573; Farmer's Delight stations ~4,580; per-mod recipe residue
  tables in `recipes.py` ~766; Alloy Forgery 351; Mekanism/Mantle load
  conditions ~60; Citadel books 698 counted as a library), classified as
  adapter-only, per-mod data, or reusable pieces for #239, with a migration
  order. (2) `tests/test_core_namespace_free.py` scans code string literals
  (not comments or docstrings) in every `src/portkit` `.py`/`.js` outside
  `src/portkit/adapters/` for mod namespaces: a known namespace as `ns:`, a
  whole-literal `ns:path` of any non-platform namespace, a bare known
  namespace, or a `/`/`.`-delimited segment; the known list is every
  `assets/`/`data/` namespace of the 13 corpus and 13 deco-set jars plus
  `citadel`. Today's 313 hits are frozen per (file, namespace) in
  `tests/data/core_namespace_allowlist.json`; a new or higher count fails, and
  a lower count fails until the allowlist is lowered, so it only shrinks.
- **Why:** portkit has to scale to arbitrary mods
  (`docs/brainstorm-2026-10-15-scaling.md`); single-mod code in shared modules
  makes every core change touch Waystones/FD paths and hides how much of the
  converter is generic. A ratchet stops the share growing while the moves
  happen one adapter at a time with md5-identical packs as the gate.
- **Rejected:** a lint over every word in the file (comments and docstrings
  cite the mods that motivated generic code; scrubbing them loses the
  citations); a fixed list without rule B (a new mod's hard-coded ids would
  slip past); an allowlist that only caps counts (removed references could
  come back unnoticed); moving code in the same PR (the interface needs
  Alex's picks first).
- **Links:** #245, PR #246, #239, #234; `docs/adapter-audit-2026-10-15.md`.

## 2026-10-15: Alloy Forgery forging recipes are `machine_recipe` residue carrying the recipe's rules; forge definitions, tiers, fuels and its recipe tags are `machine_data`

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order), PR #233.
- **Decision:** first slice of #171, precise residue only; no pack output
  changes. (1) An `alloy_forgery:forging` recipe is `machine_recipe` residue
  (the kind the residue agent already skips, #172/#173) instead of `recipe`,
  and its reason is built from the recipe file by `converters/alloy_forge.py`
  `forging_reason`: the counted inputs (`N x item` / `N x #tag`, count
  default 1 as `CountedIngredient`; "N different inputs" past five), the
  output, `min_forge_tier` (`ForgeControllerBlockEntity#canSmelt` L317),
  `fuel_per_tick` times the tier's speed multiplier (`#tick` L279-288), and
  each tier override read as `AlloyForgeRecipe$OverrideRange#fromString` does
  (`"3+"` tier 3 and up, `"1 to 3"`, `"2"`; `#getResult`). The forge is
  described from `ForgeRegistry#registerDefinition` L40-50 (controller
  `alloy_forgery:<material path>_forge_controller`, block and item) and
  `ForgeControllerBlockEntity#verifyMultiblock` L420-430 (a multiblock of
  the material), and the forges the recipe's own namespace defines are
  named. A field not in the shape
  Alloy Forgery reads is left out of the reason, never guessed. (2) The forge
  data Alloy Forgery reads from other mods is claimed as a new skipped kind,
  `machine_data`, with what each file sets: forge definitions in
  `alloy_forges/` (the pre-2.5 format) and `alloy_forge/forge/`, forge tiers
  (`alloy_forge/tier/`), tier bindings (`alloy_forge/tier_binding/`), fuels
  (`alloy_forge_fuels/`, each item with its fuel and return item), and, in
  the `alloy_forgery` namespace, its two recipe tags
  `blacklisted_blasting_recipes` / `blacklisted_increased_blasting_outputs`
  (under `tags/recipe/`, where `RecipeTagLoader` L29 reads them).
  A forge definition outside the jar's declared mod ids says Java never loads
  it (owo-lib `ModDataLoader#load` reads `data/<mod id>/<subdir>` under each
  mod's own id only).
- **Why:** the 62 forging recipes were agent-workable `recipe` residue,
  inviting the crafting stand-in 2026-10-12 rejected, and their reason said
  nothing about the recipe. Mythic Metals' forge data was unowned with "no
  converter claims yet". Correction to 2026-10-12: Mythic Metals 0.24.6 does
  define a forge, `mythicmetals:adamantite_forge` (material
  `mythicmetals:adamantite_block`, `tier` 3, `speed_multiplier` 3.0,
  `fuel_capacity` 192000, the pre-2.5 format) and fuels (morkite 750,
  morkite block 8000), plus the controller's blockstate, models, textures
  and loot table under `alloy_forgery`. Which tier that forge runs at depends
  on the Alloy Forgery version, so the reason states both: 2.4.1 (tag
  `2.4.1+1.21` @ed938ab, the minimum Mythic Metals' fabric.mod.json requires)
  reads tier/speed/capacity from the file (`ForgeDefinition#loadAndEnqueue`
  L68-88, folder from `ForgeRegistry$Loader` L87); 2.5.0 (branch `1.21.1`
  @48e309f) still loads `alloy_forges/` but builds the `ForgeTier` and drops
  it (`ForgeDefinition#loadAndEnqueue` L44-58), so an unbound forge runs at
  `ForgeTier.DEFAULT` (tier 1, speed 1, capacity 48000;
  `ForgeControllerBlockEntity#forgeTier` L88-94, `ForgeTier` L10). The two
  recipe tags only steer Alloy Forgery's copying of blasting recipes into its
  forges (`BlastFurnaceRecipeAdapter#addRecipes` L50, L66-71); vanilla blast
  furnaces still run those recipes, so on Bedrock they change nothing.
- **Measured:** Mythic Metals `recipe` 69 -> 7, `machine_recipe` 0 -> 62,
  `unowned` 977 -> 974 files, `machine_data` 0 -> 3; agent-workable residue
  -65. Pack trees md5-identical on all 13 corpus mods and the 7 deco mods;
  coverage, residue totals and the baseline unchanged; mct 0 errors on the 13.
- **Rejected / left for Alex (#171):** converting the controller block
  (`alloy_forgery:adamantite_block_forge_controller`, facing x lit, still
  `block` residue for its `block/orientable` parent) as a decorative shell
  (a forge that can't forge; #172's display-shell precedent); multi-jar
  conversion of Alloy Forgery's own jar (its 6 forges, 4 tiers, fuels and its
  own forge recipes); a scripted forge runtime (fuel, tier, multiblock check,
  overrides); a crafting-table or furnace stand-in (2026-10-12). Each needs
  Alex's call.
- **Links:** #171, #87, #170, #172, #173.

## 2026-10-15: entities don't convert; spawn eggs and entity loot tables are `entity` residue carrying what the bytecode reads

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order), PR #232.
- **Decision:** a mod's entities still don't convert (#176). The two kinds of
  file that only work with an entity become `entity` residue (a new kind in
  the residue agent's `SKIP_KINDS`) instead of misleading item residue or
  unowned files: an item model whose parent chain reaches
  `minecraft:item/template_spawn_egg` (`converters/items.py`), and a loot
  table at `loot_tables/entities/<name>.json` (`loot_table/` from 1.21) named
  after an entity type the mod's bytecode registers (`converters/entities.py`;
  Java's default entity table is `entities/<path>` of the entity id,
  `EntityType#getDefaultLootTable`; tables in a jar's `minecraft/` namespace
  override vanilla mobs and are left alone). The reasons record what
  `portkit.entities` reads from the jar's bytecode, for later entity work:
  each registration `register("name", lambda)` whose lambda returns
  `EntityType` or `EntityType.Builder`, with the `MobCategory` and the
  `sized(w, h)` hitbox when both are constants (Mojang names and Forge
  1.20.1's SRG `m_20704_`/`m_20699_`, matched with their descriptors); and
  each spawn egg built in a registered lambda as `new
  ForgeSpawnEggItem|DeferredSpawnEggItem|SpawnEggItem(ENTITY, primary,
  secondary, ...)`, with the entity resolved through the static field a
  registration stored and both colours read only when they are integer
  constants (written as Bedrock's `#RRGGBB`). Anything not matched is said
  to be unread; nothing is filled in. Tables under `entities/` named after no
  registered entity (Alex's Mobs' 15 variant tables such as
  `catfish_large`) stay unowned. No pack output changes.
- **Why:** a Java mob's geometry (ModelPart/Citadel calls), animations and AI
  goals are code, and no corpus jar ships readable entity model data (no
  GeckoLib/Blockbench/Tabula entity models), so a Bedrock entity would have
  to invent its geometry, components and stats (#87, #135). On Bedrock a
  spawn egg is the `spawn_egg` entry of its entity's client definition and an
  entity loot table is named by the entity's `minecraft:loot` component, so
  neither can ship before the entity does. As item residue the eggs invited
  the agent to draw a flat icon that spawns nothing (a wrong-but-valid item,
  #56's reasoning); as `entity` residue they are skipped and their reason
  carries the colours and hitbox an entity converter will need, cited to the
  class and method they were read from.
- **Rejected:** behavior-pack entities with no AI or default stats as
  stand-ins (fabrication, #176's own no-fabrication section); stand-in
  vanilla mobs with the mod's textures (a gameplay change); converting the
  loot tables and eggs ahead of the entity (dead files, or eggs with nothing
  to spawn); matching entity textures to entities by file name (a guess;
  textures/entity/ also holds block-entity art), left for a renderer-bytecode
  read.
- **Links:** #176, PR #232, #181, #87, #135, #56.

## 2026-10-15: Create's rotation-powered processing recipes are `machine_recipe` residue naming the machine; hand-used item application and sandpaper polishing are `code_recipe`

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order), PR #231.
- **Decision:** a recipe of one of Create's 11 rotation-powered processing
  types (crushing, milling, cutting, pressing, compacting, mixing, splashing,
  haunting, deploying, mechanical_crafting, sequenced_assembly) is
  `machine_recipe` residue (the kind #172 added; agent `SKIP_KINDS`) with a
  reason naming the Create machine and the Java it was read from
  (`converters/recipes.py` `_CREATE_MACHINE_RECIPES`, merged into
  `_MACHINE_RECIPES`). Source: Create mc1.20.1-6.0.8 for Forge 1.20.1
  (Creators-of-Create/Create @1a1a9a28; jar Implementation-Version 6.0.8),
  types in `AllRecipeTypes` L49-66; the machine is where Java looks each type
  up (`CrushingWheelControllerBlockEntity` L321-323, which also falls back to
  milling; `MillstoneBlockEntity` L103; `SawBlockEntity` L380-386;
  `MechanicalPressBlockEntity` L185-204 for pressing and compacting over a
  basin; `MechanicalMixerBlockEntity` L259-260 with `BasinRecipe#apply`
  L75-77 testing blaze-burner heat; `AllFanProcessingTypes` L232/L423 with
  the jar's `fan_processing_catalysts` tags; `DeployerBlockEntity` L571-572;
  `RecipeGridHandler` L152; `SequencedAssemblyRecipe#advance`/`#rollResult`
  L107-150). Each reason adds what Bedrock can't hold: a result `chance`
  below 1 (`ProcessingOutput` L85) for the processing types, a fluid amount
  in mB for basin recipes (#174), heat via `heatRequirement`, patterns up to
  9x9 for mechanical crafting, steps/loops/weighted pick for sequenced
  assembly, and always the rotational network. `create:item_application`
  (`ManualApplicationRecipe#manualApplicationRecipesApplyInWorld` L40-80, a
  right-click-block handler that replaces the placed block) and
  `create:sandpaper_polishing` (`SandPaperItem#use`/`#finishUsingItem`, a
  32-tick item use that wears the sandpaper) join `code_recipe`: they are
  used by hand, not in a machine (a deployer can also run them). Filling and
  emptying stay `fluid_recipe` (#174), `toolbox_dyeing`/`item_copying` stay
  special `code_recipe` (#180), and compat recipes gated on an absent mod
  (Create's own 442, plus Farmer's Delight and Supplementaries' `create:*`
  files) stay `conditional_recipe` (#183), which already covered #173's
  "separate reason for the compat recipes". `create:basin` and
  `create:conversion` ship no recipe files and get no reason.
- **Why:** each machine is block-entity code that idles at speed 0 (for
  example `MillstoneBlockEntity` L64, `SawBlockEntity` L137,
  `DeployerBlockEntity` L161) and works faster with more speed; speed and
  stress come from Create's kinetic network (shafts, cogwheels, a power
  source). A Bedrock custom block has no rotational network and no ticking
  inventory, so there is no Bedrock station to tag these recipes for. Naming
  the machine makes the residue say where the work is and stops the agent
  spending sessions on files no tool can convert.
- **Rejected:** shapeless crafting stand-ins for milling/crushing (#173's own
  "gameplay change, needs a decision": drops rotation, stress, time and
  chance outputs); not made here, as #171/#172 did not. A scripted kinetic
  runtime (months, #173). Converting Create's machine blocks to display
  blocks: a machine shell that does nothing is a wrong-but-valid block
  (#172, #56). Treating item application as a crafting recipe: its first
  ingredient is a block placed in the world, not an item in a grid.
- **Links:** #173, PR #231, #172, #174, #180, #183, #171, #87, #135.

## 2026-10-15: Mekanism machine recipes are `machine_recipe` residue naming the machine; `mek_data` crafting is `code_recipe`; the residue agent skips both

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order), PR #230.
- **Decision:** a recipe of one of Mekanism's 26 machine types is
  `machine_recipe` residue with a reason naming the machine block that runs it
  and the Java it was read from (`converters/recipes.py` `_MACHINE_RECIPES`,
  checked after `modular_tool` and before `code_recipe`; the kind is in the
  residue agent's `SKIP_KINDS`). Source: Mekanism 10.7.19.85 for NeoForge
  1.21.1 (mekanism/Mekanism tag v1.21.1-10.7.19.85 @a00109e4), serializers in
  `MekanismRecipeSerializersInternal` L54-98; the machine is each recipe
  class's own `getToastSymbol` (for example `BasicCrushingRecipe` L36 ->
  `mekanism:crusher`, `SawmillRecipe` L104 -> `mekanism:precision_sawmill`,
  `FluidToFluidRecipe` L89 -> the thermal evaporation controller). The two
  conversion types have no machine: Java reads `energy_conversion` from every
  energy slot (`EnergyInventorySlot#fillOrConvert`) and `chemical_conversion`
  from chemical slots (`ChemicalInventorySlot#fillOrConvert`), and the reasons
  say so. Each reason adds what Bedrock can't hold: chemicals (gases, infuse
  types, pigments, slurries) where the recipe uses one, measured fluid where it
  uses one (#174), the sawmill's `secondary_chance`, and always the ticking,
  energy-holding machine. `mekanism:mek_data` (L102,
  `MekanismShapedRecipe#assemble` L31-79 merges the ingredients' stored energy,
  items, fluids, chemicals, upgrades, security and other data into the
  result) joins `code_recipe`. Compat recipes gated on an absent mod stay
  `conditional_recipe` (#183), which already covered #172's second residue
  reason.
- **Why:** the machine is block-entity code: it holds its inputs, outputs,
  energy and any chemical or fluid in its own slots and tanks and works the
  recipe over ticks, faster or cheaper with upgrades
  (`TileEntityProgressMachine` L73-74, `MekanismUtils#getTicks`). A Bedrock
  custom block has no ticking inventory, tank or energy store, and no
  chemicals, so there is no Bedrock station to tag these recipes for. Naming
  the machine makes the residue say where the work is and stops the agent
  spending sessions on files no tool can convert.
- **Rejected:** a crafting-table stand-in at the machine block for the
  item-only types (crushing, enriching, smelting, sawing, combining): it turns
  a timed, energy-using machine into instant free crafting and drops chance
  outputs, a gameplay change #172 leaves to an explicit decision, as #171 did;
  not made here. A scripted machine runtime (weeks; agent/runtime territory).
  Converting `mek_data` as plain shaped crafting: the result would lose what
  the ingredients stored, and most of its results are machines that don't
  convert yet. Converting the machine blocks to display blocks: a shell that
  looks like a machine and does nothing is a wrong-but-valid block (#56's
  reasoning), as #172's own no-fabrication section says.
- **Links:** #172, PR #230, #171, #174, #175, #180, #183, #87, #135.

## 2026-10-15: modular tool recipes (Tinkers' Construct, Silent Gear) are `modular_tool` residue naming the code; the residue agent skips them

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order), PR #229.
- **Decision:** a recipe that builds, modifies, repairs or takes apart a
  modular tool, or makes a part or material that stores its material on the
  stack, is `modular_tool` residue with a reason naming the station and the
  Java that runs it (`converters/recipes.py` `_MODULAR_TOOL_RECIPES`, checked
  after `fluid_recipe` and before `code_recipe`; the kind is in the residue
  agent's `SKIP_KINDS`). Covered: Tinkers' Construct 3.12.1.231's table and
  modifier serializers (SlimeKnights/TinkersConstruct @a5a03249, TinkerTables
  L149-165, TinkerModifiers L741-779): tool building and tipped-tool
  transform, the Tinker Station modifier/overslime/banner/repair/part- and
  material-swapping/damaging types, the crafting-table overslime and
  modifier-repair types, the six Modifier Worktable types, modifier salvage,
  material values, the four Part Builder types, the materials crafting types,
  and the six severing types; Silent Gear 2.6.36's (Silent-Gear 1.16.x
  @9188137b, ModRecipes L43-80) gear crafting (shaped and shapeless),
  compound part, conversion, smithing coating/upgrade, gear and compound-part
  salvaging, and material pressing. Plain `silentgear:salvaging` (a vanilla
  item taken apart at the Salvager, SalvagerTileEntity L89-153, losing each
  result item with a damage-based chance, partLossRate 0.0-0.5) isn't a
  modular tool recipe, so it joins `code_recipe` with its own reason. Each reason cites the class or LOADER
  it was read from. The data-free Tinkers types (`tinker_station_repair`,
  `crafting_table_repair`, armour dyeing and trim) stay `code_recipe`.
- **Why:** these tools' numbers (durability, mining speed, attack, traits)
  are computed in Java at craft time from the materials of the parts they
  were built from, plus modifiers, and stored per stack. A Bedrock item's
  components are fixed per item type in its JSON, so there is no single
  Bedrock item to write for "a pickaxe", and per-stack stats would need a
  scripted station and runtime (#175's large option) that doesn't exist yet.
  A stand-in with fixed stats is fabrication (#87, #135). Naming the code
  keeps the residue honest and stops the agent spending a session per recipe.
- **Rejected:** crafting-table stand-ins producing fixed tools (gameplay
  change and invented stats, the issue's third option); a material stat table
  in the pack with no runtime to read it (dead weight until a scripted
  station exists, and the same call #174 made for smeltery data); folding the
  plain-result Silent Gear `damage_item` hammer recipes and the Metal Alloyer
  / Recrystallizer `compounding/*` recipes in here (they aren't modular tool
  recipes; they stay ordinary `recipe` residue for now).
- **Not touched:** PR #129's display-only preset and part items (route A of
  #128) live in `converters/tinkers.py` and `items.py`; this change is
  recipe residue only and doesn't overlap them.
- **Measured** (20 corpus + deco trees, develop 2e18398 vs this branch): every
  pack file md5-identical; Tinkers 837 `recipe` -> 37 `recipe` + 800
  `modular_tool`; Silent Gear 357 `recipe` + 6 `code_recipe` -> 63 `recipe` +
  59 `code_recipe` (54 salvaging) + 241 `modular_tool`
  (`salvaging/compound_part` moves from the special-recipe reason to its
  own); agent-workable residue -1,094.
- **Links:** #175, #87, #128, #129, #135, #174, #180.

## 2026-10-15: a mod's own fluids have no Bedrock form: fluid recipes are `fluid_recipe` residue and fluid-container buckets are `custom_fluid` residue; the residue agent skips both

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order), PR #228.
- **Decision:** Bedrock add-ons can't define a fluid. The custom block
  component list has no fluid component
  ([Block Components Documentation](https://learn.microsoft.com/en-us/minecraft/creator/reference/content/blockreference/examples/blockcomponents/blockcomponentslist),
  updated 2026-08-25), and the Script API's only fluid surface is
  [BlockFluidContainerComponent](https://learn.microsoft.com/en-us/minecraft/creator/scriptapi/minecraft/server/blockfluidcontainercomponent)
  ("used with blocks like cauldrons"), whose
  [FluidType](https://learn.microsoft.com/en-us/minecraft/creator/scriptapi/minecraft/server/fluidtype)
  is fixed to Water, Lava, PowderSnow and Potion. So:
  (1) in `converters/recipes.py`, a recipe that melts items into a mod's
  fluid, alloys fluids, burns a fluid as fuel, or casts or fills items from
  one is `fluid_recipe` residue with a reason naming its station and fields
  (`_FLUID_RECIPES`, checked before `code_recipe`): the 30 fluid types of the
  32 smeltery recipe types
  Tinkers' Construct 3.12.1.231 registers in TinkerSmeltery L408-444
  (SlimeKnights/TinkersConstruct @a5a03249; melting/ore/damagable/material/
  entity melting, melting_fuel, alloy, material_fluid, table and basin
  casting incl. material/composite/tool/part-swap/potion/tipping/duplication/
  retextured, table/basin filling; fields from each recipe's LOADER), and
  Create mc1.20.1-6.0.8's `create:filling` (Spout, FillingBySpout) and
  `create:emptying` (Item Drain, GenericItemEmptying) (AllRecipeTypes
  L61-62 @1a1a9a28). Tinkers' `molding_table`/`molding_basin` hold no fluid
  (a pattern pressed into sand on a casting block, CastingBlockEntity
  L152-181), so they are `code_recipe` with their own reason.
  (2) In `converters/items.py`, an item model whose `loader` ends in
  `:fluid_container` and which names a non-`minecraft:` `fluid` is
  `custom_fluid` residue:
  Forge's and NeoForge's DynamicFluidContainerModel (Forge 1.20.x
  ClientForgeMod L32 @243490d7, NeoForge 1.21.x ClientNeoForgeMod L278
  @0753a6a7) and Tinkers' FluidContainerModel (FluidClientEvents L43-44) draw
  the icon at runtime from the fluid's client texture and tint masked into a
  bucket; neither the masks nor the vanilla bucket are in the jar, and the
  pack must not carry Mojang's art (#24). A flat bucket icon the mod ships
  (Create's chocolate/honey buckets, Supplementaries' lumisene bucket) still
  converts as an ordinary item. Both kinds are in the residue agent's
  `SKIP_KINDS`.
- **Why:** every one of these recipes takes or makes a millibucket amount of
  fluid, mostly the mod's own (a few take vanilla lava or water, which
  Bedrock has but can't store as an amount outside a cauldron), at a station
  that is block-entity code (multiblock tank, faucet, casting block, spout,
  drain).
  An item-only stand-in (ingot in, cast part out) would drop amounts,
  temperatures and cooling times and invent a step the mod doesn't have
  (#87); an icon for a bucket would be invented the same way. Naming the
  station keeps the residue honest and stops the agent spending a session
  per recipe on a conversion that can only fabricate.
- **Rejected:** fluid source blocks shipped as solid blocks (wrong-but-valid:
  you'd walk on molten iron; the issue already calls this wrong); bucket
  items with a vanilla `bucket_empty` icon (every molten bucket would look
  empty and do nothing; a choice for when a scripted tank exists); a
  composited bucket icon (needs Forge's LGPL masks and Mojang's bucket art);
  a melting/casting data table in the pack with no runtime to read it (dead
  weight until a scripted smeltery exists, issue's "very large" option);
  a crafting/furnace stand-in for casting (fabrication, #87, #135).
- **Measured** (20 corpus + deco trees, develop 725f72b vs this branch):
  every pack file md5-identical; residue moves only between kinds:
  Tinkers 874 `recipe` -> 824 `fluid_recipe` + 50 `code_recipe` (molding),
  70 `item` -> `custom_fluid`; Mekanism 18 `item` -> `custom_fluid`; Create
  12 `recipe` -> `fluid_recipe`. Agent-workable residue -974 (886 recipe, 88
  item). Coverage and the baseline are unchanged. Tinkers' 1,016
  `conditional_recipe` (817 `mantle:tag_filled`, 147 compat `mod_loaded`, 52
  other) are untouched: load conditions are decided first.
- **Left (#174):** the 73 Tinkers fluid blocks (`molten_*_fluid`, model
  `tconstruct:block/fluid` with no elements) and Mekanism/Create fluid
  blocks still read as model residue; a precise `custom_fluid` reason for
  them needs the block's LiquidBlock class read from bytecode. The 45
  smeltery/foundry blocks, a scripted tank (custom component + tick +
  dynamic properties) and any runtime for these recipes; Supplementaries
  `moonlight/soft_fluids` (103 files); Tinkers fluid lang lines.
- **Links:** #174, #87, #135, #24, #180 (code_recipe), #172, #173, #175.

## 2026-10-15: a recipe whose result or station is Java code is `code_recipe` residue naming the code; the residue agent skips it

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order), PR #227.
- **Decision:** In `converters/recipes.py`, a recipe whose type has no
  converter is `code_recipe` residue (not `recipe`) when either holds:
  (1) **special recipe:** its type is not `minecraft:` and its JSON holds
  nothing but recipe-book fields (`type`, `group`, `category`,
  `show_notification`) and the mod loader's load-condition keys
  (`conditions.condition_keys`: on Fabric only `fabric:load_conditions`;
  already decided, so a recipe Java doesn't load stays
  `conditional_recipe`). Such a serializer reads no
  ingredient and no result, so what the recipe matches and builds is the
  mod's code: vanilla's `SimpleCraftingRecipeSerializer` reads `category`
  only, and Supplementaries 1.20-3.1.43 (`ModRecipes`, 13 types) and Alex's
  Mobs 1.22.9 (`AMRecipeRegistry`, 2 types) register theirs through it,
  each a `CustomRecipe` subclass (jar bytecode). (2) **typed code recipe:**
  one of seven types read from the mod's code at the corpus pin, each with
  a reason naming the station or the code and what a stand-in would drop:
  `betterend:infusion` (BetterEnd 21.800.2 @9c449fb7: InfusionRitual
  PEDESTALS_MAP L42-51 and tick L128-172, PedestalBlock useItemOn L116-148
  and the neighbour-driven shape L180-275), `bclib:smithing` (BCLib
  21.800.2 @80a081d4: worked in the vanilla anvil screen, AnvilMenuMixin
  L138-158, hammer from `allowedTools` taking `damage`, AnvilRecipe L160-195,
  anvil level >= `anvilLevel`), `bclib:alloying` (two ingredients + fuel in
  the End Stone Smelter screen, EndStoneSmelter#useWithoutItem L55-72,
  AlloyingRecipe codec L228-238), `mythicmetals:tidesinger_smithing_transform`
  (coral pattern component from the addition), `mythicmetals:fold_midas_sword`
  (folded-gold count decides match and result),
  `mythicmetals:upgrading` (addition stored in upgrade slots) (Mythic Metals
  0.24.6+1.21 bytecode: TidesingerCoralRecipe/MidasFoldingRecipe/
  UpgradeSmithingRecipe#craft), `supplementaries:sus_crafting` (the other
  grid stack stored as the result's `BlockEntityTag.item`, SusRecipe#assemble).
  `code_recipe` is in the residue agent's `SKIP_KINDS`. Vanilla
  `minecraft:` special types and modded types that carry data keep the
  `unsupported recipe type` residue.
- **Why:** A fixed-result Bedrock recipe for any of these invents a result or
  drops part of what Java does (the hammer, the anvil level, the second
  smelter input, the ritual layout and time, the stored item or component),
  which #87 rules out; left as `recipe` residue the agent was offered them
  with no reason and could only write such a stand-in. The type-only rule
  is read from the data (nothing to convert is in the file), so it needs no
  per-mod list and can't claim a recipe that carries data.
- **Measured:** 172 recipes move from `recipe` to `code_recipe` across the
  13 corpus + 7 deco jars (BetterEnd 78, Mythic Metals 27, Fairy Lights port
  27, Supplementaries 16, Silent Gear 6, Tinkers 4, Mekanism 3, Alex's Mobs,
  Create, both Farmer's Delight and Storage Drawers 1192 2 each, Refurbished
  1); every pack file is md5-identical (only `unhandled.json` kinds and
  reasons move); agent-workable `recipe` residue 4,799 -> 4,627.
- **Rejected:** *Stations in this slice.* The anvil and the smelter are
  GUI stations: Bedrock has no anvil recipe type, its furnace recipes take one
  input, and the only block components that open a screen are
  `minecraft:crafting_table` and the experimental `minecraft:block_entity`
  container (vendored bedrock-schemas 1.26.60 bp/blocks; recipe topics from
  MicrosoftDocs/minecraft-creator @4186dc4), so any Bedrock version is a
  new interaction (a decision for Alex). Infusion is in-world but needs
  BetterEnd's pedestals first (six neighbour-driven shapes, one stored stack
  each; all 15 pedestal blocks are residue today), which is its own slice.
  *A per-type list for the special recipes:* the data already says it.
  *Claiming `minecraft:` special types:* those are Bedrock's own crafting.
- **Left:** the infusion ritual (pedestal blocks, then a data table + runtime
  as the cutting board), anvil and alloying stations (policy), per-serializer
  scripts for the special recipes (low value each), Alex's Mobs capsid
  recipes (`capsid_recipes/` data files, not recipes).
- **Links:** #180, PR #227, #87, #177 (station pattern), #171.

## 2026-10-15: a block that holds items behind a vanilla grid menu ships as a Bedrock container, slot count read from bytecode, only under `--experiment upcoming_creator_features`

- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order), PR #226.
- **Decision:** A converted block is read as storage
  (`portkit.blockcode.read_containers`) when its compiled code says all of:
  `newBlockEntity` builds one block entity of the mod's (directly, or through
  a registered `BlockEntityType`: a `DeferredRegister#register(id,
  supplier)` holder runs its supplier, `BlockEntityType$Builder.of(factory,
  ..)`/`build` keep the factory and `BlockEntityType#create(pos, state)`
  calls it, as MC 1.21.1 does), built on `BaseContainerBlockEntity` or
  `RandomizableContainerBlockEntity` (vanilla chests, barrels, furnaces and
  hoppers add behaviour of their own and don't count); its
  `getContainerSize` gives one constant, 1 to 54, on every path (the entity
  run through its constructor); its `createMenu` builds only a vanilla grid
  menu (`ChestMenu` and `ChestMenu.oneRow..sixRows`, `ShulkerBoxMenu`,
  `DispenserMenu`, `HopperMenu`), not a mod menu or one made where the reader
  doesn't follow; the block's use method (`useWithoutItem`/`useItemOn`/`use`,
  nearest declaration, mod calls 3 deep) reaches `Player#openMenu` or
  `NetworkHooks.openScreen`; and the block doesn't override `getTicker`.
  With `portkit convert --experiment upcoming_creator_features` such a block
  gets `"minecraft:block_entity": {"container": {"slot_count": N}}` in its
  root components and block format 1.26.50 (a liquid_detection rule moved
  past 1.26.0 keeps `use_liquid_clipping: true`, its old default; a block
  whose JSON 1.26.x would read differently, `tag:*` components, boolean
  `ambient_occlusion` or `geometry.full_block` below 1.26.0, isn't moved and
  says so). Without the experiment nothing in the packs changes; the notes
  list each block's slot count, menu and opening as read, and how to turn it
  on. Every block read but not converted (no menu, a mod menu, a ticker, the
  format) is named with its reason; nothing is a default. Unknown experiment
  names are an error.
- **Bedrock sources:** `minecraft:block_entity` `container.slot_count` 1-54
  (learn.microsoft.com minecraftblock_block_entity, updated 2026-08-25;
  `@minecraft/bedrock-schemas` 1.26.50 `block_container.schema.json`, also in
  the vendored 1.26.60 snapshot); `container` added in 1.26.50 behind
  Upcoming Creator Features, opened by interacting, contents dropped when the
  block is destroyed, no hopper access, exclusive with `crafting_table`
  (bedrock.dev Block Format History 1.26.50; still experimental in 1.26.60,
  which adds `title`); Minecraft Preview 26.70.20 adds
  `show_ui_on_interaction` (default true) and chest permissions.
- **Measured (deco manifest, with the experiment):** 128 blocks become
  containers: Refurbished Furniture 54 (drawers 10 x 9 slots, kitchen
  drawers 26 x 9, coolers 16 x 9, fridges 2 x 27), Cluttered 74 (21 x 9 slots,
  e.g. side and end tables; 25 x 18, e.g. kitchen cabinets and the filing
  box; 27 x 27, e.g. counters and briefcases; the safe, 36; all 74 hold
  water, so their liquid_detection keeps `use_liquid_clipping: true`). Read but left
  decoration: Refurbished cutting boards, storage jars, plate, toasters, post
  box (no menu), microwaves, electricity generators, recycle bin (mod menus or
  ticking). Without the experiment all 20 corpus and deco trees are
  md5-identical to develop; mct 0 errors with and without it.
- **Why:** Bedrock now has a real custom-block container, so a Java chest-like
  block can be one without a script or an entity, and its slot count, menu
  and opening are in the jar, so nothing is invented (#87). The experiment is
  the user's call: a pack that uses an experimental field in a world without
  the toggle loses the block, so the default output must not need it.
- **Rejected:** shipping the container by default (breaks the block for
  worlds without the experiment); an entity-backed inventory or a
  script/form storage (more moving parts than the engine's own container,
  and the issue's options predate it); reading slots from a menu alone or a
  Forge `ItemStackHandler` (a handler isn't always player-facing; next slice);
  a vanilla chest stand-in (loses the block's look and identity).
- **Left:** SRG/intermediary jars (most of the standard corpus: the reader
  finds methods by Mojang name), blocks that don't convert yet (Farmer's
  Delight cabinets, Refurbished crates and storage cabinets read 27 slots
  but stay residue for their models), Cluttered multi-block storage, Storage
  Drawers' drawers (script interaction, not a menu), Forge item handlers,
  turning it on by default once `container` leaves the experiment.
- **Unverified in game:** the container screen for each slot count, opening
  from every face, drops on break, and a toggle/state block also being a
  container.
- **Links:** #179, PR #226, #87.

## 2026-10-15: a Citadel guide book ships as a form viewer: page text verbatim in .lang, pages from the jar, opened by the item read from bytecode

- **Decision:** A directory `assets/<ns>/book/<book>/` whose `root.json` is a
  Citadel `BookPage` (keys `parent`/`text`/`title`/`linked_page_buttons`/
  `entity_buttons`) converts to (`portkit.converters.books`):
  **text** — each reachable page's text file, per Java locale folder, read as
  Citadel's `GuiBasicBook.readInPageText` does (every line split on `" "` into
  one run of words, so a line break in the file is a space; the word
  `<NEWLINE>` exactly ends the line and leaves a blank one; a glued
  `word<NEWLINE>` is printed as written, as in Java), written as one `.lang`
  entry `portkit.book.<ns>.<book>.<page>` with `~LINEBREAK~` line breaks. The
  words are untouched; the layout is the form's: a run of `<NEWLINE>`
  (Citadel's room around pictures) is one blank line, empty words (double
  spaces) are dropped, and the text is trimmed. Every Bedrock locale the pack
  ships, plus every one a book folder maps to (`lang._LOCALES`), gets every
  page: its own folder's text, else `en_us` (Citadel's `refreshSpacing`
  fallback when the game language has no file);
  **pages** — `scripts/portkit/data/<ns>_books.js`: every page reachable from
  `root.json` through its buttons and parents, with its title key, text key,
  parent and buttons in the order Java creates them (`linked_page_buttons`,
  then `entity_buttons`, file order), labels by their own keys (`text` /
  `hover_text`); a Java key goes through the lang converter's mapping when
  the jar's `en_us` defines it, else stays the Java key (what Java's I18n
  shows for a missing key);
  **viewer** — fixed `portkit/runtime/book.js` + `book_core.js`
  (`@minecraft/server` 2.0.0 `world.afterEvents.itemUse`,
  `@minecraft/server-ui` 2.0.0 `ActionFormData`, UserBusy retried): using the
  book's item opens the root page; a page shows title, text as body, one
  button per link and, except on the root, a back button to the page's parent
  (Citadel's previous-page arrow on a page's first sheet,
  `onSwitchPage`), labelled with vanilla Bedrock's `gui.back` ("Back",
  bedrock-samples v1.26.50.4 `texts/en_US.lang`), not invented text;
  **item** — read from bytecode: a class extending
  `com/github/alexthe666/citadel/client/gui/GuiBasicBook` names its book in
  `getRootPage` (one string, or a static field set from one string in
  `<clinit>`); an item class whose `use(Level, Player, InteractionHand)`
  builds that screen with its `(ItemStack)` constructor (the root page),
  directly or by invoking a method whose override in a subclass of the
  invoked owner does (Alex's Mobs: `ItemAnimalDictionary#m_7203_ ->
  ClientProxy#openBookGUI`), bound to its registered name through
  `blockcode`'s registration reader. Without an answer from the classes, the
  item named like the book directory, labelled **DEFAULT** in the note; with
  neither, the whole book directory is `book` residue and no text ships.
  Sources: Citadel 1.20 @8c09dce GuiBasicBook.java (refreshSpacing
  L311-331, readInPageText L605-690, onSwitchPage L262-280) and BookPage.java
  (Deserializer L101-136).
- **Residue / reductions:** a locale folder Bedrock has no locale for
  (Alex's Mobs `es_ar`, `vi_vn`) is `book` residue counting its files; a page
  no button or parent reaches (Alex's Mobs `sea_bear.json`) is residue with
  its text files; any other file in the book directory (pictures, a stray
  text file) is residue. Noted per book, not carried: pictures (images, item,
  entity and Tabula renders, recipe grids), entity pictures and hover
  tooltips on index buttons, the two-page spread and pagination (a form
  scrolls), and the rest of the item's Java use (statistics, the
  ConsumeItem advancement trigger, opening a mob's page when used on it); a
  button naming a page that isn't in the jar is left out and named in the
  note.
- **Measured (Alex's Mobs 1.22.9):** bound from bytecode to
  `alexsmobs:animal_dictionary`; 90 pages, 15 locale folders; `book/`
  unowned 1,439 files -> converted (1,244 files) + `book` residue 195 (es_ar 90,
  vi_vn 88, sea_bear 16, a stray `pl_pl/devil's_hole_pupfish.txt`); pack +5
  files (main.js, book.js, book_core.js, data table, sv_SE.lang, which the
  mod's own strings didn't produce); behaviour pack engine floor 1.21.90 (the
  script module). Every other corpus mod unchanged.
- **Why:** the content is data and can be carried exactly; only the screen is
  Java, so the same split as the station runtimes (generated table, fixed
  script) applies. `.lang` text keeps the pack's file count flat (no file per
  page; #122) and lets Bedrock show the player's own language. Reading the
  item from bytecode follows Alex's rule (bytecode first, labelled DEFAULT
  fallback).
- **Rejected:** a JS module holding every locale's text (one large script
  file, and the player's language would have to be guessed by script);
  item custom components (`onUse`) — they need the item rewritten at format
  1.21.90 for a viewer that `world.afterEvents.itemUse` gives without
  touching the item; mapping `es_ar` to `es_MX` (a different locale, not
  Citadel's fallback); rendering pictures as text placeholders (invented
  content, #87).
- **Not done (rest of #182):** Tinkers' Mantle books (`assets/tconstruct/book/**`,
  5,494 files, many page types); Create Ponder (won't fix: animated scenes);
  BetterEnd / Silent Gear book assets; pictures in the viewer (item icons as
  button icons are possible later); opening a mob's page when the book is
  used on it (needs #176 entities).
- **Unverified in game:** `~LINEBREAK~` inside a form body, long `.lang`
  values, the form opening from `itemUse` on every platform.
- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order).
- **Links:** #182, #87, #122, #176, PR #225.

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
- **Status:** approved (Hark, high confidence under Alex's 2026-10-14 campaign order).
- **Links:** #181, #87, #167, #169, PR #224.

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

- **Corrected 2026-10-15** (Alloy Forgery forge data entry): Mythic Metals does
  ship a forge definition (`data/mythicmetals/alloy_forges/adamantite_forge.json`)
  and forge fuels; forging recipes are now `machine_recipe` residue.
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
- **Superseded in part by:** 2026-10-16 (#272): `base` is now checked by the
  validator rule `recipe.smithing_trim` (BDS refuses a base that isn't
  wearable armor carrying `minecraft:trimmable_armors`); this agent gate is
  unchanged.

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
