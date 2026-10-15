# Brainstorm: looking back and scaling out (2026-10-15)

Alex and Hark. This covers the overnight issue campaign of 2026-10-14/15 (PRs #220–#233) and how to make portkit work on *any* Java mod a user submits, not just the corpus.

## 1. Where we are

develop at `afd8e62`. pytest 1582 passed / 14 skipped; node 188.

### Shared-layer work paid off most
Generic fixes lifted many mods at once: facing (#212), light emission (#213), facing+booleans (#215, #219), negative-size elements (#216), waterlogging (#217), 6-way/attach-face (#218), vanilla textures (#220) and connection multiparts (#221). Deco mods (Alex's daughter's favourites):

| Mod | Spike (2026-10-14) | Now |
|---|---|---|
| MOA Decor Toys | 39.9% | 72.3% |
| Night Lights | 83.8%* | 95.7% |
| Plushie Buddies | 38.4% | 71.6% |
| Cluttered | 46.7% | 56.2% |
| Refurbished Furniture | 19.2% | 31.6% |

\* The spike figure was inflated by claimed-but-failed models (see notes in the deco spike).

### The overnight campaign (every open issue gets a PR)
| PR | Issue | Effect |
|---|---|---|
| #221 | #56 | 4-way connection multiparts (panes, bars, hedges, lattice fences): +72 blocks |
| #222 | #155 | `portkit schemas check/refresh`; finish once stable 1.26.60 ships |
| #223 | #190 | numeric `--config` values (FD fortune bonus) |
| #224 | #181 | `separate_transforms` items; held 3D model as an attachable (DEFAULT pose) |
| #225 | #182 | Citadel books: Alex's Mobs Animal Dictionary readable in game (AM 20.3→26.4%) |
| #226 | #179 | 128 deco containers, behind `--experiment upcoming_creator_features` |
| #227 | #180 | `code_recipe` residue (172) |
| #228 | #174 | `fluid_recipe` / `custom_fluid` residue (974) |
| #229 | #175 | `modular_tool` residue (1,094) |
| #230 | #172 | Mekanism `machine_recipe` residue (1,335) |
| #231 | #173 | Create `machine_recipe` residue (294) |
| #232 | #176 | `entity` residue with bytecode facts (AM 116 entities, 89 eggs) |
| #233 | #171 | Alloy Forgery `machine_recipe` / `machine_data` residue (65) |

Not yet PR'd when the campaign paused: #178, #24, #26, #25.

### What didn't work as well
- **Per-issue tech work mostly relabelled.** Mekanism, Create, Tinkers and fluids produced precise residue, not playable content: Bedrock lacks custom fluids, kinetics and ticking machines as data.
- **We measure on ~20 hand-picked mods**, so gains show up where we already looked.
- **Nothing is verified in game.** Nearly every PR ends with "unverified in-game".
- **The residue agent is idle**, waiting on the OpenRouter key, and it's the intended long-tail tool.

### Open calls for Alex (carried from the PRs)
Fence UV/uvlock (#56), BetterEnd anvil/alloying station design (#180), crafting-table stand-ins for machines (#172/#173), the Alloy Forgery controller (#171), the Script API 2.4.0 move after an in-game check (#190), and #129 (decisions.md conflict on rebase).

## 2. Hard vs impossible

**Question (Alex):** is the problem that some conversions are too hard to *automate*, or would they be hard or impossible even for an experienced developer porting by hand?

**Answer:** mostly hard, not impossible. Human porters don't convert; they **re-implement**: remake models in Blockbench, rewrite logic in the Script API, and design a Bedrock-native version of each feature. Popular "Bedrock versions" of big Java mods are lookalike rewrites, not ports.

| Feature | What a human does | Verdict |
|---|---|---|
| Mobs and AI | Entity components + behavior goals, scripts for edge cases | Routine, just labour |
| Machines and GUIs | Script API forms, or block/entity inventories as fake GUIs; energy as stored numbers ticked by scripts | Doable, a rewrite |
| Tool building (Tinkers) | Item data on the stack, forms for the station | Doable, lossy |
| Fluids and tanks | Tank amount as a number on a block; pouring faked with block placement | Fake only; swimmable custom fluids aren't possible for add-ons |
| Create contraptions | Animated entities for spinning parts; moving whole builds is the wall | Very hard, partial |
| Custom dimensions | Far-off regions or structures as stand-ins | Approximation only (to our knowledge) |
| Shaders, custom rendering, client tools (Axiom, minimaps) | None: add-ons run no client code | Impossible |

**Third path:** Geyser + [Hydraulic](https://github.com/GeyserMC/Hydraulic). Keep the mod on a Java server and let Bedrock players join, with Hydraulic translating the mod's content. It's in very early development, targets current versions only, and needs a server.

**Implication for portkit:** for machines, GUIs and mobs, automation is blocked by *design judgment*, not by Bedrock. If Alex approves a small library of workaround templates once, the per-mod long tail becomes fill-in-the-blanks work for the residue agent. A small set stays off-limits for everyone (client rendering/code, real fluids), and the report card should say so plainly.

## 3. Realistic ceiling
- **Deco, building, food and simple items:** high, likely 70–90% with the plan below.
- **Tech and machine mods:** look right, partial function (more with workaround templates).
- **Entity-heavy mods:** need a geometry-from-bytecode spike first.
- **Rendering mods and client tools:** won't convert.

## 4. Plan (issues filed 2026-10-15)
Alex approved this approach.

1. **#234** Random-sample corpus (top ~200 mods) + nightly gap leaderboard. Fix by mods-blocked × kid relevance, not by issue order.
2. **#235** SRG (Forge 1.20.1) and Fabric intermediary mappings for the bytecode reader, which today reads Mojang-named jars only.
3. **#236** Vanilla parent models (~324 known residue: orientable, cross, button, cube_top, fence gate).
4. **#237** Known-superclass behavior table (DoorBlock, TrapDoorBlock, ButtonBlock, LeverBlock, FenceGateBlock, seats, ...).
5. **#238** Automated in-game checks: Bedrock Dedicated Server + GameTest in CI, turning "unverified in-game" into a gate.
6. **#239** Workaround template library (scripted machine, form GUI station, tank block, mob template), one design PR each with Alex's picks.
7. **#240** Per-mod report card for users (what works, what's approximated, what won't and why); feeds #26.
8. **#241** Measure residue agent yield on the sample (blocked on the OpenRouter key).
9. **#242** Spike: entity geometry from bytecode.
10. **#243** Research: Geyser + Hydraulic as a complementary path.

Suggested order: #234 first (it ranks everything else), then #235 and #236 (broad, mechanical), #238 (safety net), #237, then the design-heavy #239 and #242.
