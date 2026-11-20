# Spike: entity geometry from bytecode (portkit-v2 #242)

**Deliverable:** feasibility notes only. No production code, test, baseline or
fixture was changed; the diff is this file.

**Question the spike answers:** can portkit's existing bytecode readers read a
Java entity's *geometry* out of a mod's class files (vanilla `ModelPart` /
`LayerDefinition` builders and Citadel `AdvancedModelBox` constructors), and
bind the entity's *texture* through the renderer's bytecode rather than
through file names?

**Rule applied throughout (repo rule #87, no fabrication):** only *constant*
arguments count as readable. Every non-constant argument is reported as
**unread**; nothing is guessed, defaulted or filled in. No AI / mob-behaviour
work is in scope.

---

## 1. Verdict

**Conditional Go.**

*Feasible and measured:* the vanilla model-builder call shapes that carry
geometry are constants in the bytecode and are readable with the machinery the
repo already has (`src/portkit/bytecode.py` for decoding + resolving call
refs, the abstract-interpreter pattern of `src/portkit/blockcode.py` for
telling a constant from an unknown, and the constant-argument precedent of
`src/portkit/entities.py` from #232). On the fallback corpus, **100 % of the
box sizes and positions, 100 % of the part poses, 97 % of the UV origins and
93 % of the texture sizes** were constant arguments; the rest were reported
unread.

*Not measured here:* the two shapes the issue names that are **not** in the
fallback corpus — the vanilla **1.20.1** API (`CubeListBuilder.addBox(IIIIIIIII)`,
`TextureSize.<init>(II)`, `LayerDefinition.create(TextureSize, ModelPart)`) and
**Citadel's `AdvancedModelBox`** — and Alex's Mobs itself. See §2.

So: go, but only as a **follow-up implementation issue** that is explicitly
scoped to (a) the shapes measured in §4, and (b) an explicit "unread" report
for everything else, and whose first task is to obtain the Alex's Mobs jar and
the Citadel library so the two unmeasured shapes can be measured on the mod
the whole question is about.

---

## 2. What was measured, and what could not be measured

### 2.1 Alex's Mobs: one fetch attempt through the repo's own pinned mechanism, and it failed

`fixtures/real/mods.toml` pins `alexs_mobs` 1.22.9 (Modrinth version id
`XoIASRVU`, url `https://cdn.modrinth.com/data/2cMuAZAp/versions/XoIASRVU/alexsmobs-1.22.9.jar`,
sha512 `b50280057926d750f9ffbf6a8df36deb37529356895f6bf59f25d272ecf69afccec65ec1a5c3a8bfad24f9475c15b93c5ec4666447b1fce26a90c41445bbfb04`,
`optional = true`). The repo's own fetch path is `portkit corpus fetch`, which
is `portkit.corpus.fetch()` (`src/portkit/corpus.py`). One attempt, through
that mechanism only:

```
$ cd /home/hatch/workspace/fixtrees/portkit-v2-worker-242
$ PYTHONPATH=src python3 -c "
from portkit import corpus
m = next(x for x in corpus.load() if x.name=='alexs_mobs')
print('pin', m.url, m.sha512[:12])
try:
    path, downloaded = corpus.fetch(m)
    print('FETCHED', path, downloaded)
except Exception as e:
    print('FETCH_FAILED', type(e).__name__, e)
"
pin https://cdn.modrinth.com/data/2cMuAZAp/versions/XoIASRVU/alexsmobs-1.22.9.jar b50280057926
FETCH_FAILED CorpusError alexs_mobs: download failed: <urlopen error [SSL: WRONG_VERSION_NUMBER] wrong version number (_ssl.c:1000)>
```

The jar is not committed to this repository and this environment has no
outbound HTTPS, so **Alex's Mobs coverage is unmeasured**. No second attempt
was made and no other source was tried.

### 2.2 The fallback corpus (all numbers below are fallback numbers, not Alex's Mobs numbers)

The fallback is the set of mod jars the repo's own corpus mechanism had
already fetched into the corpus cache (`~/.cache/portkit/mods`, filled by
`portkit corpus fetch`; the pins live in `fixtures/real/gauntlet.toml`).
Five of them carry entity/model code and were analysed:

| mod | jar in the corpus cache | loader / MC |
|---|---|---|
| botania | `botania-43b82e3e101b.jar` | forge / 1.20.1 |
| iron_chests | `iron_chests-5d41daa11bbc.jar` | forge / 1.20.1 |
| biomes_o_plenty | `biomes_o_plenty-cc8aab089379.jar` | forge / 1.20.1 |
| comforts | `comforts-e9de2952545e.jar` | neoforge / 1.21.1 |
| tinkers_construct | `tinkers_construct-69da7399162b.jar` | forge / 1.20.1 |

Every number in §4–§6 comes from these five jars and is labelled *fallback*.

### 2.3 Which model API the fallback corpus actually contains

The issue names the **1.20.1** API and **Citadel**. A byte-level scan of
every class file of every cached jar (looking for the exact descriptors and
class names) says the fallback corpus contains **neither**:

```
$ python3 - <<'EOF'
import zipfile
from pathlib import Path
cache=Path.home()/".cache/portkit/mods"
needles={
 "1.20.1 addBox(IIIIIIIII)": b"(IIIIIIII)Lnet/minecraft/client/model/geom/CubeListBuilder;",
 "TextureSize": b"net/minecraft/client/renderer/texture/TextureSize",
 "LayerDefinition.create(TextureSize,ModelPart)": b"(Lnet/minecraft/client/renderer/texture/TextureSize;Lnet/minecraft/client/model/ModelPart;)",
 "TextureAtlasLocation": b"net/minecraft/client/renderer/texture/TextureAtlasLocation",
 "citadel": b"citadel",
 "AdvancedModelBox": b"AdvancedModelBox",
 "1.21 addBox(FFFFFF)": b"(FFFFFF)Lnet/minecraft/client/model/geom/builders/CubeListBuilder;",
}
print("jar: " + " | ".join(needles))
for jar in sorted(cache.glob("*.jar")):
    zf=zipfile.ZipFile(jar); hits={k:0 for k in needles}
    for info in zf.infolist():
        if info.filename.endswith(".class"):
            raw=zf.read(info)
            for k,n in needles.items():
                if n in raw: hits[k]+=1
    print(f"{jar.name}: " + ", ".join(f"{k}={v}" for k,v in hits.items()))
EOF
jar: 1.20.1 addBox(IIIIIIIII) | TextureSize | LayerDefinition.create(TextureSize,ModelPart) | TextureAtlasLocation | citadel | AdvancedModelBox | 1.21 addBox(FFFFFF)
biomes_o_plenty-cc8aab089379.jar: 1.20.1 addBox(IIIIIIIII)=0, TextureSize=0, LayerDefinition.create(TextureSize,ModelPart)=0, TextureAtlasLocation=0, citadel=0, AdvancedModelBox=0, 1.21 addBox(FFFFFF)=0
botania-43b82e3e101b.jar: 1.20.1 addBox(IIIIIIIII)=0, TextureSize=0, LayerDefinition.create(TextureSize,ModelPart)=0, TextureAtlasLocation=0, citadel=0, AdvancedModelBox=0, 1.21 addBox(FFFFFF)=14
comforts-e9de2952545e.jar: 1.20.1 addBox(IIIIIIIII)=0, TextureSize=0, LayerDefinition.create(TextureSize,ModelPart)=0, TextureAtlasLocation=0, citadel=0, AdvancedModelBox=0, 1.21 addBox(FFFFFF)=2
cooking_for_blockheads-bec8bb71b954.jar: 1.20.1 addBox(IIIIIIIII)=0, TextureSize=0, LayerDefinition.create(TextureSize,ModelPart)=0, TextureAtlasLocation=0, citadel=0, AdvancedModelBox=0, 1.21 addBox(FFFFFF)=0
iron_chests-5d41daa11bbc.jar: 1.20.1 addBox(IIIIIIIII)=0, TextureSize=0, LayerDefinition.create(TextureSize,ModelPart)=0, TextureAtlasLocation=0, citadel=0, AdvancedModelBox=0, 1.21 addBox(FFFFFF)=1
mantle-9851a78342f4.jar: 1.20.1 addBox(IIIIIIIII)=0, TextureSize=0, LayerDefinition.create(TextureSize,ModelPart)=0, TextureAtlasLocation=0, citadel=0, AdvancedModelBox=0, 1.21 addBox(FFFFFF)=0
natures_compass-5314b536bcb9.jar: 1.20.1 addBox(IIIIIIIII)=0, TextureSize=0, LayerDefinition.create(TextureSize,ModelPart)=0, TextureAtlasLocation=0, citadel=0, AdvancedModelBox=0, 1.21 addBox(FFFFFF)=0
storage_drawers-df97b8b5053a.jar: 1.20.1 addBox(IIIIIIIII)=0, TextureSize=0, LayerDefinition.create(TextureSize,ModelPart)=0, TextureAtlasLocation=0, citadel=0, AdvancedModelBox=0, 1.21 addBox(FFFFFF)=0
tinkers_construct-69da7399162b.jar: 1.20.1 addBox(IIIIIIIII)=0, TextureSize=0, LayerDefinition.create(TextureSize,ModelPart)=0, TextureAtlasLocation=0, citadel=0, AdvancedModelBox=0, 1.21 addBox(FFFFFF)=1
veinminer-195fdfe9f135.jar: 1.20.1 addBox(IIIIIIIII)=0, TextureSize=0, LayerDefinition.create(TextureSize,ModelPart)=0, TextureAtlasLocation=0, citadel=0, AdvancedModelBox=0, 1.21 addBox(FFFFFF)=0
waystones-ca90b58d884d.jar: 1.20.1 addBox(IIIIIIIII)=0, TextureSize=0, LayerDefinition.create(TextureSize,ModelPart)=0, TextureAtlasLocation=0, citadel=0, AdvancedModelBox=0, 1.21 addBox(FFFFFF)=0
```

Consequences, stated plainly:

* **The 1.20.1 vanilla shapes are unmeasured** (0 occurrences in every cached
  jar). The fallback corpus's model code is the **1.21.2+ model API**
  (`net/minecraft/client/model/geom/builders/*`, `addBox(FFFFFF)`,
  `LayerDefinition.create(MeshDefinition, II)`).
* **Citadel is unmeasured**: no Citadel library jar is in the corpus cache and
  no class file mentions `citadel` or `AdvancedModelBox` (the scan above:
  `citadel=0`, `AdvancedModelBox=0` for all eleven cached jars).
* The 1.20.1 shapes are nevertheless *known to exist* and their geometry is
  documented inside this repository: `docs/decisions.md:2087` and
  `src/portkit/converters/armor.py:112` both describe Java 1.20.1's
  `HumanoidArmorModel.createBodyLayer` building the armour layers on a 64x32
  texture (`head texOffs(0,0) 8x8x8, hat (32,0) 8x8x8, body (16,16) 8x12x4,
  arms (40,16) 4x12x4, legs (0,16) 4x12x4`). That is the repo's own citation
  of the 1.20.1 shape; the spike did not measure it.

---

## 3. Feasibility with the repo's existing readers

What the repo already has, and what the spike used:

| repo piece | what it gives | used for |
|---|---|---|
| `src/portkit/bytecode.py` — `ClassIndex.from_source(jar)`, `instructions(cf, code)`, `Ref` | a jar's class files, decoded instructions, resolved call refs (owner/name/descriptor) | finding the call shapes and their arguments |
| `src/portkit/data/mappings.py` — `attach(classes, loader, minecraft)` | Forge SRG / Fabric intermediary names → Mojang names (the tables were cached in `~/.cache/portkit/reference`, so this worked offline) | the shapes above are named in Mojang's names |
| `src/portkit/blockcode.py` — the `Machine` abstract interpreter | the repo's existing pattern for "this value is a constant / this value is an unknown", with unknown branches running both ways and only agreeing answers counting | the model of the const-vs-unread split this spike needs |
| `src/portkit/entities.py` (#232) — `_int_const()`, `_float_const()`, descriptor-matched call patterns | the repo already reads *constant* arguments out of a mod's bytecode (MobCategory, `sized(w, h)`, spawn-egg colours) and calls everything else unread | the precedent that a constant-argument geometry reader is in line with repo practice |

The spike added **no** production reader: the constant-tracking used for the
measurement was a throwaway abstract stack interpreter (Appendix A) modelled on
`blockcode.py`'s `Machine`, and it was deliberately conservative — a method
whose instruction stream could not be followed end to end was reported as
unread, never guessed.

What does **not** exist yet (grep over `src/`, quoted):

```
$ grep -rn "ModelPart\|CubeListBuilder\|PartPose\|LayerDefinition\|AdvancedModelBox" src/
src/portkit/converters/armor.py:112:    "Java: 1.20.1, 1.21.1 and 1.21.4 LayerDefinitions build the armor layers as HumanoidArmorModel.createBodyLayer"
src/portkit/entities.py:3:A Java mob is code: its geometry is built by ModelPart or Citadel calls in a
```

i.e. no geometry reader and no entity-texture reader exist; the only mentions
are prose. A follow-up implementation would add one (most likely a new
`src/portkit/geometry.py` next to `entities.py`, reading through
`portkit.bytecode`).

---

## 4. The call shapes examined

These are the **exact** bytecode call shapes the spike looked for and found.
Owner / name / descriptor are as they appear in the class files (after the
repo's own SRG/intermediary → Mojang remapping). Counts are fallback-corpus
counts (§2.2); "constant args" is per argument position, e.g. `arg0=85` means
"argument 0 was a constant at 85 of the 85 call sites".

| # | call shape (owner.name + descriptor) | sites | constant args (per position) | classes | verdict |
|---|---|---|---|---|---|
| 1 | `net/minecraft/client/model/geom/builders/CubeListBuilder.create()` | 214 | (no arguments) | 21 | readable — the builder object itself |
| 2 | `net/minecraft/client/model/geom/builders/CubeListBuilder.texOffs(II)` | 159 | `arg0=157 arg1=157` | 20 | **readable** (157/159) — UV origin |
| 3 | `net/minecraft/client/model/geom/builders/CubeListBuilder.addBox(FFFFFF)` | 85 | `arg0=85 arg1=85 arg2=85 arg3=85 arg4=85 arg5=85` | 18 | **readable** (85/85) — box position + size |
| 4 | `net/minecraft/client/model/geom/builders/CubeListBuilder.addBox(FFFFFF, CubeDeformation)` | 108 | `arg0..arg5=108` each, `arg6=0` | 6 | **readable** for the box (108/108); the deformation object is not a constant, but its own constructor `CubeDeformation.<init>(F)` has a constant float (10 sites) |
| 5 | `net/minecraft/client/model/geom/builders/CubeListBuilder.mirror()` | 46 | (no arguments) | 6 | readable — the mirror flag |
| 6 | `net/minecraft/client/model/geom/PartPose.offset(FFF)` | 66 | `arg0=66 arg1=66 arg2=66` | 14 | **readable** (66/66) — part offset |
| 7 | `net/minecraft/client/model/geom/PartPose.offsetAndRotation(FFFFFF)` | 57 | `arg0..arg5=57` each | 11 | **readable** (57/57) — part offset + rotation |
| 8 | `net/minecraft/client/model/geom/PartPose.rotation(FFF)` | 6 | `arg0=6 arg1=6 arg2=6` | 3 | **readable** (6/6) — part rotation |
| 9 | `net/minecraft/client/model/geom/builders/PartDefinition.addOrReplaceChild(String, CubeListBuilder, PartPose)` | 215 | `arg0=215` (the child name), `arg1=0 arg2=0` | 21 | child **name** readable (215/215); the builder and the pose are objects — readable only through the calls that made them (shapes 2–8) |
| 10 | `net/minecraft/client/model/geom/builders/MeshDefinition.getRoot()` | 28 | (no arguments) | 21 | readable — the root part |
| 11 | `net/minecraft/client/model/geom/builders/LayerDefinition.create(MeshDefinition, II)` | 29 | `arg1=27 arg2=27` (texture width/height), `arg0=0` (the mesh) | 8 | **texture size readable** (27/29) |
| 12 | `net/minecraft/client/model/geom/ModelLayerLocation.<init>(ResourceLocation, String)` | 8 | `arg1=6` (the layer name), `arg0=0` (the namespace) | 5 | layer **name** readable (6/8); the namespace is not a constant |
| 13 | `net/minecraft/client/model/geom/EntityModelSet.bakeLayer(ModelLayerLocation)` | 7 | `arg0=0` | 6 | unread as an argument — the layer is found by the constant name of shape 12, not by the object |

Where the shapes were found (one example each; the full per-shape table with
counts is in §5):

```
215  net/minecraft/client/model/geom/builders/PartDefinition.addOrReplaceChild(Ljava/lang/String;Lnet/minecraft/client/model/geom/builders/CubeListBuilder;Lnet/minecraft/client/model/geom/PartPose;)Lnet/minecraft/client/model/geom/builders/PartDefinition;   [botania vazkii/botania/client/model/AvatarModel#createMesh]
214  net/minecraft/client/model/geom/builders/CubeListBuilder.create()Lnet/minecraft/client/model/geom/builders/CubeListBuilder;   [botania vazkii/botania/client/model/AvatarModel#createMesh]
159  net/minecraft/client/model/geom/builders/CubeListBuilder.texOffs(II)Lnet/minecraft/client/model/geom/builders/CubeListBuilder;   [botania vazkii/botania/client/model/AvatarModel#createMesh]
108  net/minecraft/client/model/geom/builders/CubeListBuilder.addBox(FFFFFFLnet/minecraft/client/model/geom/builders/CubeDeformation;)Lnet/minecraft/client/model/geom/builders/CubeListBuilder;   [botania vazkii/botania/client/model/CloakModel#createMesh]
 85  net/minecraft/client/model/geom/builders/CubeListBuilder.addBox(FFFFFF)Lnet/minecraft/client/model/geom/builders/CubeListBuilder;   [botania vazkii/botania/client/model/AvatarModel#createMesh]
 76  net/minecraft/client/model/geom/ModelPart.getChild(Ljava/lang/String;)Lnet/minecraft/client/model/geom/ModelPart;   [botania vazkii/botania/client/model/AvatarModel#<init>]
 66  net/minecraft/client/model/geom/PartPose.offset(FFF)Lnet/minecraft/client/model/geom/PartPose;   [botania vazkii/botania/client/model/AvatarModel#createMesh]
 57  net/minecraft/client/model/geom/PartPose.offsetAndRotation(FFFFFF)Lnet/minecraft/client/model/geom/PartPose;   [botania vazkii/botania/client/model/AvatarModel#createMesh]
 46  net/minecraft/client/model/geom/builders/CubeListBuilder.mirror()Lnet/minecraft/client/model/geom/builders/CubeListBuilder;   [botania vazkii/botania/client/model/AvatarModel#createMesh]
 38  net/minecraft/client/model/geom/ModelPart.render(Lcom/mojang/blaze3d/vertex/PoseStack;Lcom/mojang/blaze3d/vertex/VertexConsumer;II)V   [botania vazkii/botania/client/model/GaiaPylonModel#renderCrystal]
 29  net/minecraft/client/model/geom/builders/LayerDefinition.create(Lnet/minecraft/client/model/geom/builders/MeshDefinition;II)Lnet/minecraft/client/model/geom/builders/LayerDefinition;   [botania vazkii/botania/client/model/BotaniaBookModel#createBodyLayer]
 28  net/minecraft/client/model/geom/builders/MeshDefinition.getRoot()Lnet/minecraft/client/model/geom/builders/PartDefinition;   [botania vazkii/botania/client/model/AvatarModel#createMesh]
 27  net/minecraft/client/model/geom/builders/MeshDefinition.<init>()V   [botania vazkii/botania/client/model/AvatarModel#createMesh]
 22  net/minecraft/client/model/geom/ModelPart.render(Lcom/mojang/blaze3d/vertex/PoseStack;Lcom/mojang/blaze3d/vertex/VertexConsumer;IIFFFF)V   [botania vazkii/botania/client/model/AvatarModel#renderToBuffer]
 10  net/minecraft/client/model/geom/builders/CubeDeformation.<init>(F)V   [botania vazkii/botania/client/model/CloakModel#createMesh]
  8  net/minecraft/client/model/geom/ModelLayerLocation.<init>(Lnet/minecraft/resources/ResourceLocation;Ljava/lang/String;)V   [botania vazkii/botania/client/model/BotaniaModelLayers#make]
  7  net/minecraft/client/model/geom/EntityModelSet.bakeLayer(Lnet/minecraft/client/model/geom/ModelLayerLocation;)Lnet/minecraft/client/model/geom/ModelPart;   [botania vazkii/botania/client/core/handler/RenderLexicon#getModel]
  6  net/minecraft/client/model/geom/PartPose.rotation(FFF)Lnet/minecraft/client/model/geom/PartPose;   [botania vazkii/botania/client/model/BotaniaBookModel#createBodyLayer]
  4  net/minecraft/client/model/geom/ModelPart.translateAndRotate(Lcom/mojang/blaze3d/vertex/PoseStack;)V   [botania vazkii/botania/client/render/entity/ContributorFancinessHandler#renderGoldfish]
  3  net/minecraft/client/model/geom/ModelPart.setPos(FFF)V   [botania vazkii/botania/client/model/armor/ArmorModel#setupAnim]
  1  net/minecraft/client/model/geom/builders/LayerDefinition.bakeRoot()Lnet/minecraft/client/model/geom/ModelPart;   [botania vazkii/botania/client/render/block_entity/RunicAltarBlockEntityRenderer#<init>]
  1  net/minecraft/client/model/geom/builders/PartDefinition.getChild(Ljava/lang/String;)Lnet/minecraft/client/model/geom/builders/PartDefinition;   [tinkers_construct slimeknights/tconstruct/world/client/SkullModelHelper#createHeadHatLayer]
```

A worked example of what "readable" buys, taken from
`vazkii/botania/client/model/AvatarModel#createMesh` (Botania, fallback
corpus): the box call reads as
`addBox(-3.0, -6.0, -3.0, 6.0, 6.0, 6.0)`, the UV origin as
`texOffs(0, 12)`, the pose as
`PartPose.offsetAndRotation(3.0, 15.0, -1.0, 0.0, -0.0, -0.08730000257492065)`,
and the child as `addOrReplaceChild("head", …)` — a box, its UV origin, its
offset and its rotation, all as constants, which is exactly what a Bedrock
geometry needs.

### 4.1 The shapes the issue names that are *not* in the fallback corpus

| shape named in the issue | measured? | note |
|---|---|---|
| vanilla 1.20.1 `CubeListBuilder.addBox(IIIIIIIII)` (x, y, z, w, h, d, texOffU, texOffV) | **no** — 0 occurrences in every cached jar (§2.3) | same argument kind as shape 3/4 (all int constants in the 1.21 form); feasible by the same reader, but *unmeasured* |
| vanilla 1.20.1 `TextureSize.<init>(II)` / `LayerDefinition.create(TextureSize, ModelPart)` | **no** — 0 occurrences (§2.3) | the texture size is the same idea as shape 11 (two int constants); *unmeasured* |
| Citadel `AdvancedModelBox` constructors | **no** — no Citadel jar, 0 mentions of `citadel` / `AdvancedModelBox` in the cache (§2.3) | *unmeasured*; its constructor takes a parent `ModelPart` plus integer offsets/size, so it would be read by the same machinery as shapes 3/4, but that is an argument, not a measurement |

These three rows are the reason the verdict is *Conditional* and not *Go*.

---

## 5. Coverage counts (fallback corpus)

```
$ python3 /tmp/spike242/report.py
== fallback corpus jars ==
  botania            botania-43b82e3e101b.jar               forge/1.20.1
  iron_chests        iron_chests-5d41daa11bbc.jar           forge/1.20.1
  biomes_o_plenty    biomes_o_plenty-cc8aab089379.jar       forge/1.20.1
  comforts           comforts-e9de2952545e.jar              neoforge/1.21.1
  tinkers_construct  tinkers_construct-69da7399162b.jar     forge/1.20.1

== per shape: call sites, constant arguments per position, classes ==
  CubeListBuilder.create()                                   sites= 214   classes= 21
  CubeListBuilder.texOffs(II)                                sites= 159 arg0=157 arg1=157  classes= 20
  CubeListBuilder.addBox(FFFFFF)                             sites=  85 arg0=85 arg1=85 arg2=85 arg3=85 arg4=85 arg5=85  classes= 18
  CubeListBuilder.addBox(FFFFFF,CubeDeformation)             sites= 108 arg0=108 arg1=108 arg2=108 arg3=108 arg4=108 arg5=108 arg6=0  classes=  6
  CubeListBuilder.mirror()                                   sites=  46   classes=  6
  PartPose.offset(FFF)                                       sites=  66 arg0=66 arg1=66 arg2=66  classes= 14
  PartPose.offsetAndRotation(FFFFFF)                         sites=  57 arg0=57 arg1=57 arg2=57 arg3=57 arg4=57 arg5=57  classes= 11
  PartPose.rotation(FFF)                                     sites=   6 arg0=6 arg1=6 arg2=6  classes=  3
  PartDefinition.addOrReplaceChild(String,CubeListBuilder,PartPose) sites= 215 arg0=215 arg1=0 arg2=0  classes= 21
  MeshDefinition.getRoot()                                   sites=  28   classes= 21
  LayerDefinition.create(MeshDefinition,II)                  sites=  29 arg0=0 arg1=27 arg2=27  classes=  8
  ModelLayerLocation.<init>(ResourceLocation,String)         sites=   8 arg0=0 arg1=6  classes=  5
  EntityModelSet.bakeLayer(ModelLayerLocation)               sites=   7 arg0=0  classes=  6

== per mod ==
  botania            classes touching a geometry owner= 27 shape call sites= 1128
  iron_chests        classes touching a geometry owner=  2 shape call sites=   21
  biomes_o_plenty    classes touching a geometry owner=  1 shape call sites=    1
  comforts           classes touching a geometry owner=  3 shape call sites=   40
  tinkers_construct  classes touching a geometry owner=  4 shape call sites=   21
  TOTAL jar classes=4178 methods=28857 unfollowable=4931 model classes=37 of which partly unfollowable=15

== texture sizes read from LayerDefinition.create ==
   (64, 64) 10
   (64, 128) 8
   (64, 32) 5
   (32, 32) 2
   (None, None) 2
   (32, 16) 1
   (16, 16) 1

== renderer getTextureLocation: constant strings ==
   ('botania', 'vazkii/botania/client/render/entity/PixieRenderer', 'getTextureLocation', 'botania:textures/model/pixie_halloween.png', 'net/minecraft/resources/ResourceLocation.<init>')
   ('botania', 'vazkii/botania/client/render/entity/PixieRenderer', 'getTextureLocation', 'botania:textures/model/pixie.png', 'net/minecraft/resources/ResourceLocation.<init>')
```

Reading of the numbers:

* **Classes examined:** 4 178 classes in the five fallback jars; 37 of them
  call a geometry owner (model classes); 15 of those 37 have at least one
  method the conservative interpreter could not follow end to end, so part of
  their geometry is **unmeasured** (and would be reported unread).
* **Methods:** 28 857 methods with code; 4 931 (17 %) could not be followed
  and were therefore read as unread rather than guessed.
* **Per shape:** see §4. Readable geometry per shape: boxes 85/85 and 108/108,
  UV origins 157/159, part offsets 66/66, part poses 57/57, part rotations
  6/6, texture sizes 27/29, child names 215/215, layer names 6/8.
* **Texture sizes** actually read: 64x64 (10), 64x128 (8), 64x32 (5), 32x32
  (2), 32x16 (1), 16x16 (1), and 2 sites whose size was **not** a constant
  (reported `(None, None)` — unread, not guessed; both in
  `slimeknights/tconstruct/world/client/SkullModelHelper#createHeadLayer` and
  `#createHeadHatLayer`).

---

## 6. Binding an entity's texture through renderer bytecode (not file names)

#232 rejected "matching entity textures to entities by file name (a guess;
textures/entity/ also holds block-entity art), left for a renderer-bytecode
read" (`docs/decisions.md:3015`). The fallback corpus shows how that read
would work:

* **The renderer names the texture.** Botania's
  `vazkii/botania/client/render/entity/PixieRenderer#getTextureLocation`
  holds two constant strings, each passed straight to
  `net/minecraft/resources/ResourceLocation.<init>(Ljava/lang/String;)V`:
  `botania:textures/model/pixie.png` and
  `botania:textures/model/pixie_halloween.png` (quoted above). The
  disassembly of that method (decoded by `portkit.bytecode.instructions`) is:

  ```
  0 getstatic  vazkii/botania/client/core/proxy/ClientProxy.dootDoot : Z
  3 ifeq       18
  6 new        net/minecraft/resources/ResourceLocation
  9 dup
  10 ldc       botania:textures/model/pixie_halloween.png
  12 invokespecial net/minecraft/resources/ResourceLocation.<init>(Ljava/lang/String;)V
  15 goto      27
  18 new       net/minecraft/resources/ResourceLocation
  21 dup
  22 ldc       botania:textures/model/pixie.png
  24 invokespecial net/minecraft/resources/ResourceLocation.<init>(Ljava/lang/String;)V
  27 areturn
  ```

  The texture path is a **constant string in the renderer's bytecode**; no
  file-name matching is involved. (The 1.20.1 form of this call is
  `TextureAtlasLocation.<init>(Ljava/lang/String;)V`; that class is 0
  occurrences in the fallback corpus, §2.3, so the 1.20.1 spelling is
  unmeasured.)
* **The geometry layer is named by a constant too.**
  `ModelLayerLocation.<init>(ResourceLocation, String)` has a constant layer
  name at 6 of 8 sites (shape 12); the renderer then asks
  `EntityModelSet.bakeLayer(ModelLayerLocation)` (7 sites) for the baked
  `ModelPart` (shape 13).
* **The namespace is the weak point.** The `ResourceLocation` argument of
  `ModelLayerLocation.<init>` was a constant at 0 of 8 sites (§4, shape 12) —
  it comes from a field or a helper, not from a literal. A follow-up reader
  would have to resolve it (the mod's own id, or a `static final` field) or
  report the layer as unread. This is exactly the "unread, never guessed"
  boundary.

So the binding chain a follow-up would read is:

```
renderer class --getTextureLocation()--> constant "ns:textures/...png"   (texture)
renderer class --ModelLayerLocation("layer-name", ns)--> constant name    (which layer)
model class --createBodyLayer/createMesh--> boxes, UV origins, poses      (geometry)
model class --LayerDefinition.create(mesh, w, h)--> constant w, h         (texture size)
```

Textures would then be bound to the geometry **by what the renderer code
says**, not by what a file is called.

---

## 7. What a follow-up must not do

* No fabrication (#87): a non-constant argument stays unread. In the fallback
  corpus that means 2 of 29 texture sizes and 2 of 159 UV origins would ship
  as *unread*, not as 0.
* No defaults for geometry: a box that cannot be read is not a box of size 0.
* No AI / animation / mob-behaviour reading in the same issue (out of scope
  here, and #176's own no-fabrication section applies).
* Do not resurrect file-name matching of entity textures (rejected in #232).

---

## 8. Recommendation

**Conditional Go** — open a follow-up implementation issue with this scope:

1. **A geometry reader** (a new `src/portkit/geometry.py`, next to
   `entities.py`, reading through `portkit.bytecode`): read
   `CubeListBuilder.create/texOffs/addBox/mirror`, `PartPose.offset /
   offsetAndRotation / rotation`, `PartDefinition.addOrReplaceChild`,
   `MeshDefinition.getRoot`, `LayerDefinition.create` and the **1.20.1
   spellings** (`addBox(IIIIIIIII)`, `TextureSize`, `LayerDefinition.create`),
   plus **Citadel `AdvancedModelBox`** constructors — with the *constant*
   arguments only, and every other argument reported unread. The fallback
   numbers in §5 are the expected coverage of that reader on the fallback
   corpus (boxes 193/193, poses 129/129, UV origins 157/159, texture sizes
   27/29, child names 215/215).
2. **A texture binding read** through the renderer's `getTextureLocation`
   (constant string) and the model's layer name (constant string), never
   through file names; unresolved namespaces are unread.
3. **Preconditions before the numbers are believed:**
   * obtain the Alex's Mobs 1.22.9 jar through the repo's corpus mechanism
     (`portkit corpus fetch --include-optional` / `corpus.fetch`) so the
     entity corpus this issue is really about can be measured, and
   * pin and fetch the **Citadel** library jar so `AdvancedModelBox` can be
     measured at all.
   Until then the 1.20.1 and Citadel rows of §4.1 stay *unmeasured*.
4. **Not in the same issue:** emitting a Bedrock client entity / behaviour
   entity, animations, AI goals or stats. This spike only establishes that
   the *geometry and texture binding* are readable; what a Bedrock entity
   still needs beyond that (components, spawn rules, AI) is #176's open
   question, not this issue's.

**No-go** for the two unmeasured shapes until they are measured: a
`AdvancedModelBox` reader or a 1.20.1 `addBox(IIIIIIIII)` reader would be
written against a guess about a jar nobody in this repository has.

---

## 9. Limits of this spike

* Alex's Mobs: **unmeasured** (jar unavailable, §2.1).
* Vanilla 1.20.1 model API: **unmeasured** on bytecode (0 occurrences in the
  fallback corpus); known only from the repo's own citations
  (`docs/decisions.md:2087`, `src/portkit/converters/armor.py:112`).
* Citadel `AdvancedModelBox`: **unmeasured** (no Citadel jar in the cache).
* The constant-tracking was a throwaway interpreter, not a production
  reader; its 17 % unfollowable-method rate means some model methods in the
  fallback corpus were not read at all. A production reader (which can use
  `blockcode.py`'s `Machine`, with branches and merges) should do better
  than the numbers above, and the follow-up issue should re-measure rather
  than assume these counts.
* The numbers are fallback-corpus numbers. Any statement about Alex's Mobs'
  own models in this document would be a guess, and there is none.

---

## Appendix A — the measurement scripts (throwaway, not part of the diff)

The two scripts below are the ones that produced §4–§6. They were written
under `/tmp` for this spike and are **not** committed (the diff is this file
only). Save them side by side in one directory and run
`python3 report.py` with `PYTHONPATH` pointing at the repo's `src/`.

### A.1 `measure.py` — the constant-vs-unread classifier

```python
"""Spike measurement (throwaway): read entity-model geometry call shapes from
the corpus jars the repo's own fetch mechanism already cached, and classify
each call argument as constant (readable) or not (unread).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/hatch/workspace/fixtrees/portkit-v2-worker-242/src")

from portkit.bytecode import ClassIndex, Ref, instructions  # noqa: E402
from portkit.data import mappings  # noqa: E402

CACHE = Path.home() / ".cache" / "portkit" / "mods"

SHAPE_OWNERS = (
    "net/minecraft/client/model/ModelPart",
    "net/minecraft/client/model/geom/",
    "net/minecraft/client/renderer/texture/TextureSize",
    "net/minecraft/client/renderer/texture/TextureAtlasLocation",
)
CITADEL = "citadel"


def desc_args(desc):
    out = []
    i = desc.index("(") + 1
    while desc[i] != ")":
        c = desc[i]
        if c == "L":
            i = desc.index(";", i) + 1
            out.append("L")
        elif c == "[":
            i += 1
            while desc[i] == "[":
                i += 1
            if desc[i] == "L":
                i = desc.index(";", i) + 1
            else:
                i += 1
            out.append("L")
        else:
            out.append(c)
            i += 1
    return out


def desc_ret(desc):
    return desc[desc.index(")") + 1:]


class Fail(Exception):
    pass


class Sim:
    def __init__(self):
        self.stack = []
        self.locals = {}

    def push(self, kind, value=None):
        self.stack.append((kind, value))
        if kind in ("long", "double"):
            self.stack.append(("wide2", None))

    def pop(self):
        if not self.stack:
            raise Fail("stack underflow")
        top = self.stack.pop()
        if top[0] == "wide2":
            if not self.stack:
                raise Fail("wide underflow")
            wide = self.stack.pop()
            return ("wide", wide[1])
        return top

    def peek(self):
        if not self.stack:
            raise Fail("stack underflow")
        return self.stack[-1]


def _binop(sim, kind):
    b = sim.pop()
    a = sim.pop()
    if a[0] == kind and b[0] == kind and isinstance(a[1], (int, float)) and isinstance(b[1], (int, float)):
        if kind == "int":
            sim.push("int", (a[1] + b[1]) & 0xFFFFFFFF)
        else:
            sim.push("float", a[1] + b[1])
    else:
        sim.push("unknown", None)


def analyze(cf, method):
    insns = instructions(cf, method.code)
    sim = Sim()
    calls = []
    for insn in insns:
        op = insn.op
        arg = insn.arg
        if op == 0x00:
            pass
        elif 0x01 <= op <= 0x0D:
            if op == 0x01:
                sim.push("ref", None)
            elif 0x02 <= op <= 0x08:
                sim.push("int", op - 0x03)
            elif op in (0x09, 0x0A):
                sim.push("long", 0 if op == 0x09 else 1)
            else:
                sim.push("float", float(op - 0x0B))
        elif op in (0x10, 0x11):
            sim.push("int", arg)
        elif op in (0x12, 0x13):
            if isinstance(arg, bool):
                sim.push("int", int(arg))
            elif isinstance(arg, int):
                sim.push("int", arg)
            elif isinstance(arg, float):
                sim.push("float", arg)
            elif isinstance(arg, str):
                sim.push("str", arg)
            else:
                sim.push("unknown", None)
        elif op == 0x14:
            sim.push("unknown", None)
        elif 0x15 <= op <= 0x19:
            kind = {0x15: "int", 0x16: "long", 0x17: "float", 0x18: "double", 0x19: "ref"}[op]
            val = sim.locals.get(arg)
            sim.push(kind if val is not None else "unknown", val)
        elif 0x1A <= op <= 0x2D:
            base = op - (op - 0x1A) % 4
            kind = {0x1A: "int", 0x1E: "long", 0x22: "float", 0x26: "double", 0x2A: "ref"}[base]
            idx = (op - 0x1A) % 4
            val = sim.locals.get(idx)
            sim.push(kind if val is not None else "unknown", val)
        elif 0x36 <= op <= 0x3A:
            sim.locals[arg] = sim.pop()[1]
        elif 0x3B <= op <= 0x4E:
            idx = (op - 0x3B) % 4
            sim.locals[idx] = sim.pop()[1]
        elif 0x4F <= op <= 0x56:
            sim.pop(); sim.pop(); sim.pop()
        elif op == 0x57:
            sim.pop()
        elif op == 0x58:
            sim.pop(); sim.pop()
        elif op == 0x59:
            v = sim.peek()
            if v[0] == "wide2":
                raise Fail("dup of a wide value")
            sim.push(v[0], v[1])
        elif op == 0x5A:
            v1 = sim.pop(); v2 = sim.pop()
            sim.push(v1[0], v1[1]); sim.push(v2[0], v2[1]); sim.push(v1[0], v1[1])
        elif op == 0x5B:
            v1 = sim.pop(); v2 = sim.pop(); v3 = sim.pop()
            sim.push(v1[0], v1[1]); sim.push(v3[0], v3[1]); sim.push(v2[0], v2[1]); sim.push(v1[0], v1[1])
        elif op == 0x5C:
            v1 = sim.pop()
            if v1[0] == "wide":
                sim.push("wide", v1[1]); sim.push("wide2", None)
            else:
                v2 = sim.pop()
                sim.push(v2[0], v2[1]); sim.push(v1[0], v1[1])
        elif op == 0x5F:
            v1 = sim.pop(); v2 = sim.pop()
            sim.push(v1[0], v1[1]); sim.push(v2[0], v2[1])
        elif 0x60 <= op <= 0x83:
            kind = {0x60: "int", 0x61: "long", 0x62: "float", 0x63: "double"}.get(op)
            if op in (0x74, 0x75, 0x78, 0x79):
                v = sim.pop()
                if v[0] == kind and isinstance(v[1], (int, float)):
                    sim.push(kind, -v[1])
                else:
                    sim.push("unknown", None)
            elif op in (0x7C, 0x7D, 0x7E, 0x7F):
                sim.pop(); sim.pop(); sim.push("unknown", None)
            else:
                _binop(sim, kind)
        elif op == 0x84:
            pass
        elif 0x85 <= op <= 0x93:
            sim.pop()
            sim.push("unknown", None)
        elif 0x94 <= op <= 0x98:
            sim.pop(); sim.pop(); sim.push("int", 0)
        elif 0x99 <= op <= 0xA6:
            sim.pop()
        elif op == 0xA7:
            pass
        elif op == 0xA8:
            sim.push("ref", None)
        elif op == 0xA9:
            pass
        elif op in (0xAA, 0xAB):
            sim.pop()
        elif op in (0xAC, 0xAD, 0xAE, 0xAF, 0xB0, 0xB1):
            want = {0xAC: 1, 0xAD: 2, 0xAE: 2, 0xAF: 1, 0xB0: 1, 0xB1: 0}[op]
            if len(sim.stack) != want:
                raise Fail("stack not as expected at return (%d, want %d)" % (len(sim.stack), want))
            if op in (0xAC, 0xAD, 0xAE, 0xAF, 0xB0):
                sim.pop()
        elif op == 0xB2:
            sim.push("unknown", None)
        elif op == 0xB3:
            sim.pop()
        elif op == 0xB4:
            sim.pop(); sim.push("unknown", None)
        elif op == 0xB5:
            sim.pop(); sim.pop()
        elif op in (0xB6, 0xB7, 0xB8, 0xB9):
            if not isinstance(arg, Ref):
                sim.push("unknown", None)
                continue
            ref = arg
            args = desc_args(ref.desc)
            values = []
            for t in reversed(args):
                if t in ("J", "D"):
                    v = sim.pop()
                    values.append(("wide", v[1]))
                else:
                    values.append(sim.pop())
            values.reverse()
            if op in (0xB6, 0xB7, 0xB9):
                sim.pop()
            calls.append((insn.offset, ref, values))
            ret = desc_ret(ref.desc)
            if ret != "V":
                sim.push("unknown", None)
        elif op == 0xBA:
            d = arg.desc if hasattr(arg, "desc") else "()V"
            for t in reversed(desc_args(d)):
                sim.pop()
            ret = desc_ret(d)
            if ret != "V":
                sim.push("unknown", None)
        elif op == 0xBB:
            sim.push("new", arg if isinstance(arg, str) else None)
        elif op in (0xBC, 0xBD):
            sim.pop()
            sim.push("ref", None)
        elif op == 0xBE:
            sim.pop(); sim.push("int", 0)
        elif op == 0xBF:
            raise Fail("athrow")
        elif op == 0xC0:
            sim.pop(); sim.push("unknown", None)
        elif op == 0xC1:
            sim.pop(); sim.push("int", 0)
        elif op in (0xC2, 0xC3):
            sim.pop()
        elif op == 0xC5:
            sim.pop(); sim.push("ref", None)
        elif op in (0xC6, 0xC7):
            sim.pop()
        elif op == 0xC8:
            pass
        elif op == 0xC9:
            sim.push("ref", None)
        else:
            raise Fail("unknown opcode %02x" % op)
    return calls


def classify(values):
    out = []
    for v in values:
        if v[0] == "wide":
            out.append("wide")
        elif v[0] in ("int", "float", "str") and v[1] is not None:
            out.append("const")
        else:
            out.append("unknown")
    return out


def scan_jar(path, loader, minecraft):
    classes = ClassIndex.from_source(path)
    note = mappings.attach(classes, loader, minecraft)
    results = []
    unread_methods = 0
    analysed_methods = 0
    for name in classes.names():
        cf = classes.get(name)
        if cf is None:
            continue
        for m in cf.methods:
            if m.code is None:
                continue
            try:
                calls = analyze(cf, m)
            except Fail:
                unread_methods += 1
                continue
            analysed_methods += 1
            for offset, ref, values in calls:
                owner = ref.owner
                if not any(owner.startswith(o) for o in SHAPE_OWNERS) and CITADEL not in owner:
                    continue
                results.append({
                    "class": name, "method": m.name, "offset": offset,
                    "owner": owner, "name": ref.name, "desc": ref.desc,
                    "args": classify(values),
                    "values": [v[1] if v[0] in ("int", "float", "str") else None for v in values],
                })
    return {"classes": len(classes), "note": note, "analysed_methods": analysed_methods,
            "unread_methods": unread_methods, "calls": results}


CORPUS = [
    ("botania", "botania-43b82e3e101b.jar", "forge", "1.20.1"),
    ("iron_chests", "iron_chests-5d41daa11bbc.jar", "forge", "1.20.1"),
    ("biomes_o_plenty", "biomes_o_plenty-cc8aab089379.jar", "forge", "1.20.1"),
    ("comforts", "comforts-e9de2952545e.jar", "neoforge", "1.21.1"),
    ("tinkers_construct", "tinkers_construct-69da7399162b.jar", "forge", "1.20.1"),
]

if __name__ == "__main__":
    out = {}
    for name, jar, loader, mc in CORPUS:
        path = CACHE / jar
        if not path.is_file():
            print("missing", path)
            continue
        out[name] = scan_jar(path, loader, mc)
        print(name, "classes", out[name]["classes"], "note", out[name]["note"],
              "calls", len(out[name]["calls"]))
    Path("/tmp/spike242/calls.json").write_text(json.dumps(out, indent=1))
```

### A.2 `report.py` — the driver that prints §4–§6

```python
"""Driver: the numbers this spike quotes. Run after measure.py."""
import collections, sys
sys.path.insert(0, "/tmp/spike242")
from measure import scan_jar, CACHE, CORPUS, Fail, analyze, SHAPE_OWNERS
from portkit.bytecode import ClassIndex
from portkit.data import mappings

SHAPES = [
    ("CubeListBuilder.create()", lambda c: c["owner"].endswith("CubeListBuilder") and c["name"] == "create"),
    ("CubeListBuilder.texOffs(II)", lambda c: c["owner"].endswith("CubeListBuilder") and c["name"] == "texOffs"),
    ("CubeListBuilder.addBox(FFFFFF)", lambda c: c["owner"].endswith("CubeListBuilder") and c["name"] == "addBox" and len(c["args"]) == 6),
    ("CubeListBuilder.addBox(FFFFFF,CubeDeformation)", lambda c: c["owner"].endswith("CubeListBuilder") and c["name"] == "addBox" and len(c["args"]) == 7),
    ("CubeListBuilder.mirror()", lambda c: c["owner"].endswith("CubeListBuilder") and c["name"] == "mirror"),
    ("PartPose.offset(FFF)", lambda c: c["owner"].endswith("PartPose") and c["name"] == "offset"),
    ("PartPose.offsetAndRotation(FFFFFF)", lambda c: c["owner"].endswith("PartPose") and c["name"] == "offsetAndRotation"),
    ("PartPose.rotation(FFF)", lambda c: c["owner"].endswith("PartPose") and c["name"] == "rotation"),
    ("PartDefinition.addOrReplaceChild(String,CubeListBuilder,PartPose)", lambda c: c["owner"].endswith("PartDefinition") and c["name"] == "addOrReplaceChild"),
    ("MeshDefinition.getRoot()", lambda c: c["owner"].endswith("MeshDefinition") and c["name"] == "getRoot"),
    ("LayerDefinition.create(MeshDefinition,II)", lambda c: c["owner"].endswith("LayerDefinition") and c["name"] in ("create", "createMeshDefinition")),
    ("ModelLayerLocation.<init>(ResourceLocation,String)", lambda c: c["owner"].endswith("ModelLayerLocation") and c["name"] == "<init>"),
    ("EntityModelSet.bakeLayer(ModelLayerLocation)", lambda c: c["owner"].endswith("EntityModelSet") and c["name"] == "bakeLayer"),
    ("ModelPart.addOrReplaceChild(String,ModelPart)", lambda c: c["owner"].endswith("ModelPart") and c["name"] == "addOrReplaceChild"),
]

sites = collections.Counter(); consts = collections.defaultdict(collections.Counter)
classes = collections.defaultdict(set); modclasses = collections.Counter()
sizes = collections.Counter(); per_mod = collections.Counter()
n_model_classes = 0; n_unfollowable = 0; n_methods = 0; n_classes = 0; n_partly = 0
tex = []
for name, jar, loader, mc in CORPUS:
    path = CACHE / jar
    if not path.is_file():
        continue
    info = scan_jar(path, loader, mc)
    for c in info["calls"]:
        for shape, test in SHAPES:
            if not test(c):
                continue
            sites[shape] += 1
            classes[shape].add((name, c["class"]))
            for i, a in enumerate(c["args"]):
                consts[shape][f"arg{i}"] += (a == "const")
            if shape == "LayerDefinition.create(MeshDefinition,II)":
                sizes[(c["values"][1], c["values"][2])] += 1
    # classes and followability
    idx = ClassIndex.from_source(path); mappings.attach(idx, loader, mc)
    model = set(); partly = set(); unfollow = 0; methods = 0
    for cn in idx.names():
        cf = idx.get(cn)
        if cf is None:
            continue
        for m in cf.methods:
            if m.code is None:
                continue
            methods += 1
            try:
                calls = analyze(cf, m)
            except Fail:
                unfollow += 1; partly.add(cn); continue
            for off, ref, vals in calls:
                if any(ref.owner.startswith(o) for o in SHAPE_OWNERS) or "citadel" in ref.owner:
                    model.add(cn)
    n_model_classes += len(model); n_partly += len(partly & model)
    n_unfollowable += unfollow; n_methods += methods; n_classes += len(idx)
    modclasses[name] = len(model)
    per_mod[name] = len(info["calls"])
    # texture binding: the constant strings inside renderer getTextureLocation
    # methods (an ldc of a string next to a ResourceLocation/TextureAtlasLocation
    # constructor call), read from the decoded instructions, not the stack.
    from portkit.bytecode import instructions
    for cn in idx.names():
        cf = idx.get(cn)
        if cf is None:
            continue
        for m in cf.methods:
            if m.name != "getTextureLocation" or m.code is None:
                continue
            insns = instructions(cf, m.code)
            for k, insn in enumerate(insns):
                if insn.op in (0x12, 0x13) and isinstance(insn.arg, str):
                    nxt = insns[k + 1] if k + 1 < len(insns) else None
                    tex.append((name, cn, m.name, insn.arg,
                                nxt.arg.owner + "." + nxt.arg.name if nxt is not None and hasattr(nxt.arg, "owner") else "?"))

print("== fallback corpus jars ==")
for name, jar, loader, mc in CORPUS:
    print(f"  {name:18s} {jar:38s} {loader}/{mc}")
print()
print("== per shape: call sites, constant arguments per position, classes ==")
for shape, _ in SHAPES:
    if not sites[shape]:
        continue
    n = sites[shape]
    parts = " ".join(f"{k}={consts[shape][k]}" for k in sorted(consts[shape], key=lambda x: int(x[3:])))
    print(f"  {shape:58s} sites={n:4d} {parts}  classes={len(classes[shape]):3d}")
print()
print("== per mod ==")
for name, _, _, _ in CORPUS:
    print(f"  {name:18s} classes touching a geometry owner={modclasses[name]:3d} shape call sites={per_mod[name]:5d}")
print(f"  TOTAL jar classes={n_classes} methods={n_methods} unfollowable={n_unfollowable} "
      f"model classes={n_model_classes} of which partly unfollowable={n_partly}")
print()
print("== texture sizes read from LayerDefinition.create ==")
for k, v in sorted(sizes.items(), key=lambda kv: -kv[1]):
    print("  ", k, v)
print()
print("== renderer getTextureLocation: constant strings ==")
for t in tex:
    print("  ", t)
```

---

## 11. Sources

* `fixtures/real/mods.toml` — the `alexs_mobs` pin (1.22.9, Modrinth
  `XoIASRVU`) and the corpus's rules; `fixtures/real/gauntlet.toml` — the pins
  of the fallback jars.
* `src/portkit/corpus.py` — `fetch()` / `cached()`: the only sanctioned way
  to get a corpus jar.
* `src/portkit/bytecode.py` — `ClassIndex.from_source`, `instructions`,
  `Ref`: the decoding and call-ref resolution used here.
* `src/portkit/data/mappings.py` — `attach()`: the SRG / intermediary →
  Mojang remapping used here.
* `src/portkit/blockcode.py` — the `Machine` abstract interpreter: the repo's
  existing "constant vs unknown" machinery, the pattern a production
  geometry reader would follow.
* `src/portkit/entities.py` (#232) — `_int_const` / `_float_const` and the
  descriptor-matched call patterns: the repo's precedent for reading constant
  arguments out of a mod's bytecode.
* `docs/decisions.md:3015` — #232's decision, including the rejection of
  matching entity textures to entities by file name.
* `docs/decisions.md:2087` and `src/portkit/converters/armor.py:112` — the
  repo's own description of the 1.20.1 `LayerDefinition` / `createBodyLayer`
  shapes (not measured here).
