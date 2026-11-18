# Research notes: Geyser + Hydraulic as a complementary path for unconvertible mods

Issue: #243 (research only — no code).
Author: portkit worker (issue #243), 2026-11-18.
Status: **notes document**. Nothing here is a portkit policy decision; §6 is a labelled
recommendation, everything else is a cited fact or an explicit `[unverified]` gap.

**How to read the citations.** Every factual statement below carries the URL of the source it
came from, inline. The [Sources](#sources) section at the end lists every URL used. Where a
claim could not be checked against a primary source it is written as `[unverified]` and the
missing source is named, rather than being filled in from memory (repo rule #87, "read, don't
invent" — see `docs/decisions.md`).

**Primary source.** GeyserMC's Hydraulic repository itself
(<https://github.com/GeyserMC/Hydraulic>) is the primary source for everything about
Hydraulic; the Geyser repository (<https://github.com/GeyserMC/Geyser>) is used only for
Geyser's own stated scope and supported versions.

---

## 1. What Hydraulic is, and how it relates to Geyser

- Hydraulic "is a companion to Geyser which allows for Bedrock players to join modded
  Minecraft: Java Edition servers", and it "works alongside Geyser to make this possible"
  (<https://github.com/GeyserMC/Hydraulic/blob/master/README.md>).
- It is "a server-side mod" (README, same URL) and "an open collaboration project by
  CubeCraft Games" (README, same URL).
- The README states: "This project is still in very early development and should not be used
  on production setups!" (README, same URL). The GeyserMC wiki page for Hydraulic repeats the
  same caution verbatim (<https://geysermc.org/wiki/other/hydraulic>).
- Geyser itself is "a proxy, bridging the gap between Minecraft: Bedrock Edition and
  Minecraft: Java Edition servers", and its README warns "due to the nature of Geyser
  translating packets over the network of two different games, *do not expect everything to
  work perfectly!*"
  (<https://github.com/GeyserMC/Geyser/blob/master/README.md>).
- Hydraulic is not archived and was last pushed on 2026-11-11
  (<https://api.github.com/repos/GeyserMC/Hydraulic>), so it is an actively developed
  project — but an early-stage one by its own README.

This matches the in-repo note that introduced this line of work: "Geyser + Hydraulic. Keep the
mod on a Java server and let Bedrock players join, with Hydraulic translating the mod's
content. It's in very early development, targets current versions only, and needs a server."
(`docs/brainstorm-2026-10-15-scaling.md`, §"Third path"). The "targets current versions only"
part is confirmed by the maintainers in §4 below; the rest of that sentence is the brainstorm's
own summary and is **not** a Hydraulic claim.

## 2. What Hydraulic translates today

The Hydraulic README does **not** document a feature matrix. Everything in this section is
therefore read off the repository source tree and the issue tracker, and each claim cites the
file or issue it was read from. The tree listing used for the "what is not there" claims is
<https://api.github.com/repos/GeyserMC/Hydraulic/git/trees/master?recursive=1> (127 blob
files; no path contains `gui`, `container`, `screen`, `menu`, `mob`, `geometry` or `animation`).

### 2a. Blocks — translated

Evidence that Hydraulic converts Java blocks to Bedrock custom blocks:

- `BlockPackModule` registers a listener on Geyser's `GeyserDefineCustomBlocksEvent` and
  builds `NonVanillaCustomBlockData` / `CustomBlockState` /
  `CustomBlockPermutation` objects, i.e. Bedrock custom-block data generated from the Java
  side (<https://github.com/GeyserMC/Hydraulic/blob/master/shared/src/main/java/org/geysermc/hydraulic/block/BlockPackModule.java>).
- The same file reads the Java block's collision shape (`VoxelShape`) into a Bedrock
  `BoxComponent`, the Java model into a Bedrock `GeometryComponent` /
  `TransformationComponent`, and picks a render method from the texture's transparency; it
  also matches block state properties through a `query.block_property(...)` condition string
  (same file).
- Block states are read from the mods' own `blockstates` assets (`StateDefinition`, and the
  `assets(ResourcePack::blockStates)` loop in `BlockPackModule`, same file).
- Item↔block linkage and creative placement are handled by `ItemPackModule`, which registers
  on `GeyserDefineCustomItemsEvent` and creates `NonVanillaCustomItemDefinition` entries with
  a `GeyserBlockPlacer` component (<https://github.com/GeyserMC/Hydraulic/blob/master/shared/src/main/java/org/geysermc/hydraulic/item/ItemPackModule.java>).
- Content is delivered to Bedrock clients as a generated resource pack: `PackManager` reads
  each mod's resource packs and the vanilla pack and drives the pack modules
  (<https://github.com/GeyserMC/Hydraulic/blob/master/shared/src/main/java/org/geysermc/hydraulic/pack/PackManager.java>).

**Limit observed in the tracker:** custom blocks larger than Bedrock's rendering bounds break
in a chunk (<https://github.com/GeyserMC/Hydraulic/issues/11>), and there are open reports of
modded special render types and tint sources dropping an item's model
(<https://github.com/GeyserMC/Hydraulic/issues/116>). Block translation therefore exists but
is not complete.

### 2b. Items — translated

- `ItemPackModule` converts every item in the item registry that has a resolvable model,
  stitches the Java model with `ModelStitcher`, reads the model's texture layers and
  registers the result as a Geyser custom item
  (<https://github.com/GeyserMC/Hydraulic/blob/master/shared/src/main/java/org/geysermc/hydraulic/item/ItemPackModule.java>).
- Bedrock cannot tint item icons, so Hydraulic bakes the tint into the texture instead
  (`itemTints` map and the `handleModel` tint handling, same file).
- Special-cased item kinds exist as separate modules in the tree: `ArmorPackModule` and
  `BowPackModule` (file paths visible in
  <https://api.github.com/repos/GeyserMC/Hydraulic/git/trees/master?recursive=1>); armor
  rendering is known to be imperfect — "armor model does not work when being worn"
  (<https://github.com/GeyserMC/Hydraulic/issues/13>).
- Creative-menu placement of items is driven by `CreativeMappings`, a hand-written table
  that maps Java item/block *classes* and *tags* (e.g. `DoorBlock.class` +
  `BlockTags.DOORS`, `ItemTags.PICKAXES`) to a Bedrock creative group and category
  (<https://github.com/GeyserMC/Hydraulic/blob/master/shared/src/main/java/org/geysermc/hydraulic/item/CreativeMappings.java>).

### 2c. GUIs — no translation found (not stated by the project)

- The Hydraulic source tree contains **no** GUI, container, menu or screen handling: no path
  in the repository tree matches `gui`, `container`, `screen` or `menu`
  (<https://api.github.com/repos/GeyserMC/Hydraulic/git/trees/master?recursive=1>).
- A GitHub issue search over the repository's issues and comments for `gui` returns only two
  hits, neither of which is a GUI-translation feature request
  (<https://api.github.com/search/issues?q=repo:GeyserMC/Hydraulic+gui+in:title,body>).
- User reports show mod GUIs are not reliably usable from Bedrock: blocks such as chairs
  "don't show any GUI or inventory or anything"
  (<https://github.com/GeyserMC/Hydraulic/issues/4>), while other reports describe a Bedrock
  player opening a mod block's GUI at all
  (<https://github.com/GeyserMC/Hydraulic/issues/124>). These are user reports, not
  maintainer statements.
- **Verdict:** Hydraulic does not ship mod-GUI translation in the source we read. Whether a
  mod's own screen can be driven from Bedrock at all is `[unverified]` — no maintainer
  statement on GUI support was found in the README, the wiki page, or the issue tracker.

### 2d. Entities / mobs — not translated on the default branch

- There is no entity, mob, geometry or animation **code** in the repository tree — the only
  paths containing "entity" are three test-mod armour texture files
  (<https://api.github.com/repos/GeyserMC/Hydraulic/git/trees/master?recursive=1>).
- A user reports that modded mobs spawn but are invisible and un-interactable on Bedrock
  (<https://github.com/GeyserMC/Hydraulic/issues/131>); the reply in that thread refers to
  "that branch", i.e. entity support lives outside the default branch (same issue).
- A collaborator wrote in an early issue: "while the project is still in early development,
  we will not be accepting bug report on more broad issues (I.e. entities don't work)"
  (<https://github.com/GeyserMC/Hydraulic/issues/4#issuecomment-1987147893>).

So: **blocks — yes; items — yes; GUIs — not found; entities — not on the default branch.**

## 3. Loaders and Minecraft versions supported

### Loaders

- The repository is a multi-project Gradle build with exactly two platform modules,
  `fabric/` and `neoforge/` (plus `shared/` and a `test/` mod)
  (<https://api.github.com/repos/GeyserMC/Hydraulic/git/trees/master?recursive=1>); the
  platform selection is `loom.platform=fabric` / `loom.platform=neoforge`
  (<https://github.com/GeyserMC/Hydraulic/blob/master/fabric/gradle.properties>,
  <https://github.com/GeyserMC/Hydraulic/blob/master/neoforge/gradle.properties>).
- A maintainer answered a Forge-support request: "Not happening. We don't support Forge."
  and "there's no plans to support older Minecraft versions for Hydraulic"
  (<https://github.com/GeyserMC/Hydraulic/issues/51#issuecomment-3363598303>), and a second
  maintainer added that "forge and older versions are likely to never happen"
  (<https://github.com/GeyserMC/Hydraulic/issues/51#issuecomment-3365041566>).
- Hydraulic therefore runs **alongside** Geyser-Fabric or Geyser-NeoForge, not standalone
  Geyser: the Fabric mod metadata depends on `geyser-fabric` and the NeoForge metadata on
  `geyser_neoforge`
  (<https://github.com/GeyserMC/Hydraulic/blob/master/fabric/src/main/resources/fabric.mod.json>,
  <https://github.com/GeyserMC/Hydraulic/blob/master/neoforge/src/main/resources/META-INF/neoforge.mods.toml>);
  a maintainer made the same point in
  <https://github.com/GeyserMC/Hydraulic/issues/72#issuecomment-4148461521> ("Hydraulic is a
  companion mod for Geyser-Fabric and Geyser-NeoForge").

### Minecraft version

- The build targets `minecraft_version=26.3`
  (<https://github.com/GeyserMC/Hydraulic/blob/master/gradle.properties>); the Fabric mod
  metadata requires `minecraft >= ${minecraft_version}` and `java >=25`
  (<https://github.com/GeyserMC/Hydraulic/blob/master/fabric/src/main/resources/fabric.mod.json>);
  the NeoForge metadata requires `neoforge` in `[26.3.0.0-beta,)` and `minecraft >= 26.3`
  (<https://github.com/GeyserMC/Hydraulic/blob/master/neoforge/src/main/resources/META-INF/neoforge.mods.toml>).
- Pinned dependency versions: `fabric-loader 0.19.5`, `fabric-api 0.162.0+26.3`,
  `neoforge 26.3.0.77`, `geyser 2.12.1-SNAPSHOT`
  (<https://github.com/GeyserMC/Hydraulic/blob/master/gradle/libs.versions.toml>).
- Geyser's own README lists Java **26.3** as its supported Java version and Bedrock
  26.40–26.63 (<https://github.com/GeyserMC/Geyser/blob/master/README.md>), so Hydraulic's
  target version matches Geyser's current Java version.
- Note on the version numbering: the sources above use the `26.x` scheme for current
  Minecraft, while earlier issue threads use `1.21.x` / `1.20.x`. Both appear in the
  tracker; the build files above are the authoritative statement of what the current code
  targets.

### Stated limits and the maintainers' position on older modded versions

- **Hydraulic issue #68** ("Feature Request: Add support for Minecraft 1.21.x",
  <https://github.com/GeyserMC/Hydraulic/issues/68>) asked for long-term 1.21.1 / NeoForge
  21.1.x support. It was closed on 2026-05-21 with these maintainer replies:
  - "We will never support Hybrid software. Since, Hybrid software is usually unstable and
    has a ton of bugs." (<https://github.com/GeyserMC/Hydraulic/issues/68#issuecomment-3920870533>)
  - "Also, there are no plans to support older modded Minecraft versions. Even if we were to
    support older Minecraft versions, that would require Geyser to be able to run on older
    Fabric/NeoForge which currently isn't possible unless you run ViaProxy."
    (<https://github.com/GeyserMC/Hydraulic/issues/68#issuecomment-3920882594>)
  - "Older versions will pretty much never be supported. It's not worth out time to support
    these versions." (<https://github.com/GeyserMC/Hydraulic/issues/68#issuecomment-4510596631>)
- The same position is repeated in later threads:
  - "Hydraulic will likely never be ported to older versions of Minecraft: Java Edition …
    will always be on the latest Minecraft: Java Edition version."
    (<https://github.com/GeyserMC/Hydraulic/issues/82#issuecomment-4539051827>)
  - "Hydraulic will only ever focus on the most recent version of Minecraft, which means we
    don't have any plans to support Minecraft 1.21.1, 1.20.1, or any other version below
    Minecraft 26.1. Hydraulic is a complicated mod, and the technical differences between
    Minecraft 1.20.1, 1.21.1, and 26.1 are huge … Geyser also does not work natively for
    modded platforms on these older versions."
    (<https://github.com/GeyserMC/Hydraulic/issues/82#issuecomment-4541395121>)
  - "We have no interest in supporting older versions due to the time it would take to
    update Hydraulic each time would build up way too much." and "1.20.1 hasn't been
    relevant for quite some time."
    (<https://github.com/GeyserMC/Hydraulic/issues/100#issuecomment-4948135386>,
    <https://github.com/GeyserMC/Hydraulic/issues/100#issuecomment-4948154370>)
  - Backporting "is unfortunately not something we plan to do in the future … Geyser would
    also need to be backported in order to support 1.20.1. This is possible for someone to do
    however." (<https://github.com/GeyserMC/Hydraulic/issues/46#issuecomment-3113048929>)
- Other stated limits: the project "should not be used on production setups" (README,
  <https://github.com/GeyserMC/Hydraulic/blob/master/README.md>) and Geyser's own "do not
  expect everything to work perfectly!" (<https://github.com/GeyserMC/Geyser/blob/master/README.md>).
- Open functional complaints in the tracker that bear on a "will it work for my mod?"
  promise: Bedrock players unable to craft, no recipes in the recipe book
  (<https://github.com/GeyserMC/Hydraulic/issues/69>); modded doors not walkable-through
  (<https://github.com/GeyserMC/Hydraulic/issues/70>); Creative-inventory crashes from some
  block/item models (<https://github.com/GeyserMC/Hydraulic/issues/32>); server crash when a
  Bedrock player interacts with a two-block mod structure
  (<https://github.com/GeyserMC/Hydraulic/issues/124>).

## 4. Could portkit share or learn from Hydraulic's mapping data?

**Licence.** The Hydraulic repository is MIT-licensed: the repository metadata reports
`"license": {"key": "mit", "spdx_id": "MIT"}`
(<https://api.github.com/repos/GeyserMC/Hydraulic>), the README carries an MIT badge
(<https://github.com/GeyserMC/Hydraulic/blob/master/README.md>), and the `LICENSE` file is the
MIT License, "Copyright (c) 2019-2026 GeyserMC. http://geysermc.org"
(<https://github.com/GeyserMC/Hydraulic/blob/master/LICENSE>). The MIT text grants use,
modification and redistribution provided the copyright and permission notice are included
(same file). The `fabric.mod.json` and `neoforge.mods.toml` also declare `"license": "MIT"`
(<https://github.com/GeyserMC/Hydraulic/blob/master/fabric/src/main/resources/fabric.mod.json>,
<https://github.com/GeyserMC/Hydraulic/blob/master/neoforge/src/main/resources/META-INF/neoforge.mods.toml>).
What portkit itself is licensed under is `[unverified]` from this repository: there is no
`LICENSE` file at the repo root and `pyproject.toml` declares no licence field, so MIT-to-MIT
compatibility cannot be asserted from the repo as it stands (checked 2026-11-18). What the
MIT text does grant is use, modification and redistribution provided GeyserMC's copyright and
permission notice are included (same file) — that obligation would follow any copied
Hydraulic code into portkit.

**Submodule.** The repository pulls in one submodule, the Bedrock JSON schemas from
Blockception (`pack-schema/generator/src/main/resources/schema`, url
`https://github.com/Blockception/Minecraft-bedrock-json-schemas`)
(<https://github.com/GeyserMC/Hydraulic/blob/master/.gitmodules>); that upstream repository is
BSD-3-Clause licensed
(<https://api.github.com/repos/Blockception/Minecraft-bedrock-json-schemas>), so its
attribution and disclaimer requirements differ from MIT and would have to be honoured
separately.

**What the "mapping data" actually is.** The only mapping table in the repository is
`CreativeMappings.java`: a hand-written table from Java item/block classes and vanilla tags to
Bedrock creative groups and categories (doors, fences, fences gates, planks, slabs, stairs,
trapdoors, walls, crops, flowers, leaves, logs, spawn eggs, mushrooms, saplings, arrows,
axes, hoes, pickaxes, shovels, swords, …)
(<https://github.com/GeyserMC/Hydraulic/blob/master/shared/src/main/java/org/geysermc/hydraulic/item/CreativeMappings.java>).
It is a *creative-menu placement* table keyed on **vanilla** Java classes/tags — not a general
Java-mod → Bedrock item/block mapping database, and not a mapping of any mod's own ids.

**Assessment (labelled: this is a judgement, not a fact).**

- *Sharing code:* legally fine under MIT with attribution; *practically* low value, because
  the table is short, vanilla-keyed, and covers the creative-tab problem portkit does not
  have.
- *Learning from it:* the more useful takeaway is architectural, not tabular. Hydraulic
  reads the Java side at runtime — the mod's own resource packs, blockstates, models and
  registry entries — and **generates** a Bedrock resource pack plus Geyser custom-block and
  custom-item definitions
  (<https://github.com/GeyserMC/Hydraulic/blob/master/shared/src/main/java/org/geysermc/hydraulic/pack/PackManager.java>,
  <https://github.com/GeyserMC/Hydraulic/blob/master/shared/src/main/java/org/geysermc/hydraulic/block/BlockPackModule.java>,
  <https://github.com/GeyserMC/Hydraulic/blob/master/shared/src/main/java/org/geysermc/hydraulic/item/ItemPackModule.java>).
  portkit's converter reads the same kind of Java artefacts (jars, bytecode, models) but
  *authors* a native Bedrock add-on; the generate-a-pack approach is a plausible alternative
  pipeline for mods whose *content* converts but whose *behaviour* does not.
- *Reusing Hydraulic's item/block mapping data for portkit's own converter:* `[unverified]`
  and probably negative — the data does not exist in a reusable form in this repository. No
  mapping dataset beyond `CreativeMappings` was found in the tree
  (<https://api.github.com/repos/GeyserMC/Hydraulic/git/trees/master?recursive=1>).

## 5. Gaps that stayed open

- `[unverified]` Whether mod GUIs can be operated from Bedrock at all — no maintainer
  statement found in the README, the wiki page, or the issue tracker.
- `[unverified]` Whether Hydraulic supports entity/mob rendering in a released build — the
  default branch has no entity code, and the only thread about it points at "that branch"
  (<https://github.com/GeyserMC/Hydraulic/issues/131>).
- `[unverified]` The exact Bedrock version range Hydraulic is validated against; only Geyser's
  own Bedrock list (26.40–26.63) is published
  (<https://github.com/GeyserMC/Geyser/blob/master/README.md>).
- `[unverified]` Whether a Hydraulic-generated pack can be re-used outside a live Geyser
  session (no statement found); relevant only if portkit ever wanted to ship packs.
- Not fetched (not needed for the questions asked): the GeyserMC download page's per-version
  Hydraulic builds, and the `pack-converter` upstream project.

## 6. Recommendation for portkit's report card (a recommendation, not a fact)

**Recommendation.** Do **not** present "Geyser + Hydraulic" as a general fallback for mods
portkit cannot convert. Present it, if at all, as a short, clearly-caveated *alternative
route for the user to run themselves*, emitted only under the conditions below, and always
labelled as an option outside portkit's output. Rationale, from the facts above:

- **Condition on the mod's target version.** Hydraulic targets the current Java version only
  (`minecraft_version=26.3`, <https://github.com/GeyserMC/Hydraulic/blob/master/gradle.properties>)
  and the maintainers say older modded versions will never be supported
  (<https://github.com/GeyserMC/Hydraulic/issues/68#issuecomment-3920882594>). A mod built
  for 1.20.1 or 1.21.1 therefore cannot use Hydraulic as-is, and the report card must not
  suggest it.
- **Condition on the loader.** Fabric or NeoForge only; Forge is not supported
  (<https://github.com/GeyserMC/Hydraulic/issues/51#issuecomment-3363598303>).
- **Condition on server-side availability.** Hydraulic is a server-side mod that a user runs
  on their own Java server alongside Geyser (README,
  <https://github.com/GeyserMC/Hydraulic/blob/master/README.md>). It is not something portkit
  can deliver as part of a converted pack.
- **Where it genuinely helps — machines.** Hydraulic does translate blocks (states, models,
  collision boxes, render method) and items, and the Java server keeps running the mod's own
  logic while Bedrock clients receive the translated content
  (<https://github.com/GeyserMC/Hydraulic/blob/master/shared/src/main/java/org/geysermc/hydraulic/block/BlockPackModule.java>,
  <https://github.com/GeyserMC/Hydraulic/blob/master/shared/src/main/java/org/geysermc/hydraulic/item/ItemPackModule.java>).
  *That the Java-side logic keeps running is an inference from "Hydraulic is a server-side
  mod that works alongside Geyser" (README) plus Geyser being a proxy
  (<https://github.com/GeyserMC/Geyser/blob/master/README.md>); it is not stated as such by
  the project.* For machine mods, a report-card note saying "the machine's server-side
  behaviour is unchanged; only the client's view of the blocks/items is translated" would
  explain why a Hydraulic route can preserve function that portkit's conversion approximates.
- **Where it does not help — GUIs.** No GUI translation exists in the source we read (§2c), and
  crafting from the Bedrock inventory is reported broken
  (<https://github.com/GeyserMC/Hydraulic/issues/69>). The report card must not promise that a
  mod's machine GUI will work on Bedrock; if it mentions Hydraulic at all for GUI-heavy mods,
  it should say the GUI is `[unverified]`/known-problematic rather than claiming support.
- **Where it does not help — rendering.** Client-side rendering, shaders and other client-only
  mods stay out of scope for a Bedrock client regardless of Hydraulic: Hydraulic translates
  content, and its own tracker still has open rendering-model problems
  (<https://github.com/GeyserMC/Hydraulic/issues/11>,
  <https://github.com/GeyserMC/Hydraulic/issues/116>). The report card's existing "won't
  convert: client rendering" reason should stay as it is; Hydraulic should not be offered as a
  remedy for it.
- **Caveats that must travel with the note.** "Very early development, should not be used on
  production setups" (README), "do not expect everything to work perfectly" (Geyser README),
  no Forge, current Java version only, and the maintainers' explicit statement that they will
  never support older modded versions
  (<https://github.com/GeyserMC/Hydraulic/issues/68#issuecomment-3920882594>).
- **Suggested wording (draft, for review — not a policy decision yet):** *"This mod has
  machine or GUI behaviour that a native Bedrock conversion cannot reproduce. If you run the
  Java server yourself on the current Minecraft version with Fabric or NeoForge, Geyser +
  Hydraulic can give Bedrock players a translated view of the mod's blocks and items while the
  server keeps the mod's own logic. Hydraulic is a separate, early-development project — not
  something this pack includes — and mod GUIs and client-side rendering are not covered."*

**Not recommended:** telling users that portkit output and Hydraulic are interchangeable, or
citing Hydraulic as evidence that a given mod "works on Bedrock" — the sources above support
no such claim.

---

## Sources

All URLs below were fetched on 2026-11-18.

Hydraulic repository and code:

1. Hydraulic README — <https://github.com/GeyserMC/Hydraulic/blob/master/README.md> (raw: <https://raw.githubusercontent.com/GeyserMC/Hydraulic/master/README.md>)
2. Hydraulic repository metadata (licence, description, push date) — <https://api.github.com/repos/GeyserMC/Hydraulic>
3. Hydraulic `LICENSE` (MIT) — <https://github.com/GeyserMC/Hydraulic/blob/master/LICENSE>
4. Hydraulic source tree listing — <https://api.github.com/repos/GeyserMC/Hydraulic/git/trees/master?recursive=1>
5. `BlockPackModule.java` — <https://github.com/GeyserMC/Hydraulic/blob/master/shared/src/main/java/org/geysermc/hydraulic/block/BlockPackModule.java>
6. `ItemPackModule.java` — <https://github.com/GeyserMC/Hydraulic/blob/master/shared/src/main/java/org/geysermc/hydraulic/item/ItemPackModule.java>
7. `CreativeMappings.java` — <https://github.com/GeyserMC/Hydraulic/blob/master/shared/src/main/java/org/geysermc/hydraulic/item/CreativeMappings.java>
8. `PackManager.java` — <https://github.com/GeyserMC/Hydraulic/blob/master/shared/src/main/java/org/geysermc/hydraulic/pack/PackManager.java>
9. `gradle.properties` (`minecraft_version=26.3`) — <https://github.com/GeyserMC/Hydraulic/blob/master/gradle.properties>
10. `gradle/libs.versions.toml` (dependency versions) — <https://github.com/GeyserMC/Hydraulic/blob/master/gradle/libs.versions.toml>
11. `fabric/gradle.properties` — <https://github.com/GeyserMC/Hydraulic/blob/master/fabric/gradle.properties>
12. `neoforge/gradle.properties` — <https://github.com/GeyserMC/Hydraulic/blob/master/neoforge/gradle.properties>
13. `fabric.mod.json` — <https://github.com/GeyserMC/Hydraulic/blob/master/fabric/src/main/resources/fabric.mod.json>
14. `neoforge.mods.toml` — <https://github.com/GeyserMC/Hydraulic/blob/master/neoforge/src/main/resources/META-INF/neoforge.mods.toml>
15. `.gitmodules` (schema submodule) — <https://github.com/GeyserMC/Hydraulic/blob/master/.gitmodules>
16. Blockception schemas repository (BSD-3-Clause) — <https://github.com/Blockception/Minecraft-bedrock-json-schemas>, metadata <https://api.github.com/repos/Blockception/Minecraft-bedrock-json-schemas>

Hydraulic issues and comments:

17. Issue #68 "Feature Request: Add support for Minecraft 1.21.x" — <https://github.com/GeyserMC/Hydraulic/issues/68>
    - <https://github.com/GeyserMC/Hydraulic/issues/68#issuecomment-3920870533>
    - <https://github.com/GeyserMC/Hydraulic/issues/68#issuecomment-3920882594>
    - <https://github.com/GeyserMC/Hydraulic/issues/68#issuecomment-4510596631>
18. Issue #82 "I would like support for 1.21.1" — <https://github.com/GeyserMC/Hydraulic/issues/82>
    - <https://github.com/GeyserMC/Hydraulic/issues/82#issuecomment-4539051827>
    - <https://github.com/GeyserMC/Hydraulic/issues/82#issuecomment-4541395121>
19. Issue #100 "Add support for 1.20.1" — <https://github.com/GeyserMC/Hydraulic/issues/100>
    - <https://github.com/GeyserMC/Hydraulic/issues/100#issuecomment-4948135386>
    - <https://github.com/GeyserMC/Hydraulic/issues/100#issuecomment-4948154370>
20. Issue #51 "(Suggestion) Forge support for older version (1.20.X)" — <https://github.com/GeyserMC/Hydraulic/issues/51>
    - <https://github.com/GeyserMC/Hydraulic/issues/51#issuecomment-3363598303>
    - <https://github.com/GeyserMC/Hydraulic/issues/51#issuecomment-3365041566>
21. Issue #46 "Porting to other versions of Minecraft" — <https://github.com/GeyserMC/Hydraulic/issues/46>
    - <https://github.com/GeyserMC/Hydraulic/issues/46#issuecomment-3113048929>
22. Issue #72 "HydraulicMC (separate project …)" — <https://github.com/GeyserMC/Hydraulic/issues/72>
    - <https://github.com/GeyserMC/Hydraulic/issues/72#issuecomment-4148461521>
23. Issue #4 "the mod works right but …" — <https://github.com/GeyserMC/Hydraulic/issues/4>
    - <https://github.com/GeyserMC/Hydraulic/issues/4#issuecomment-1987147893>
24. Issue #11 "Blocks that are bigger than bedrock's rendering bounds …" — <https://github.com/GeyserMC/Hydraulic/issues/11>
25. Issue #13 "armor model does not work when being worn" — <https://github.com/GeyserMC/Hydraulic/issues/13>
26. Issue #32 "Some block/item models cause a crash in the creative inventory" — <https://github.com/GeyserMC/Hydraulic/issues/32>
27. Issue #69 "Bedrock players are unable to craft" — <https://github.com/GeyserMC/Hydraulic/issues/69>
28. Issue #70 "Bedrock players are unable to walk through modded doors" — <https://github.com/GeyserMC/Hydraulic/issues/70>
29. Issue #116 "Modded special render types and tint sources drop an item's model entirely" — <https://github.com/GeyserMC/Hydraulic/issues/116>
30. Issue #124 "Hydraulic&Kaleidoscope" (crash on Bedrock interaction with a mod block GUI) — <https://github.com/GeyserMC/Hydraulic/issues/124>
31. Issue #131 "Mobs not showing up on bedrock despite their entity existing on java" — <https://github.com/GeyserMC/Hydraulic/issues/131>
32. Issue list (all issues, used to check for GUI-related threads) — <https://api.github.com/repos/GeyserMC/Hydraulic/issues?state=all&per_page=100> and <https://api.github.com/repos/GeyserMC/Hydraulic/issues?state=all&per_page=100&page=2>
33. Issue search for `gui` — <https://api.github.com/search/issues?q=repo:GeyserMC/Hydraulic+gui+in:title,body>

Geyser and GeyserMC:

34. Geyser README (proxy description, supported versions) — <https://github.com/GeyserMC/Geyser/blob/master/README.md> (raw: <https://raw.githubusercontent.com/GeyserMC/Geyser/master/README.md>)
35. Geyser repository metadata (licence MIT) — <https://api.github.com/repos/GeyserMC/Geyser>
36. GeyserMC wiki page "Hydraulic" — <https://geysermc.org/wiki/other/hydraulic>

In-repo:

37. `docs/brainstorm-2026-10-15-scaling.md` (§"Third path") — the note that commissioned this research.
38. `docs/decisions.md` (repo convention for how decisions and unverified items are recorded; rule #87 "read, don't invent").
