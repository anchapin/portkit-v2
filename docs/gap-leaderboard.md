# The gap leaderboard (#234)

The real-mod corpus (`fixtures/real/`) measures about 20 hand-picked mods, so
gains show up where we already looked. The gap leaderboard measures a
**sample of popular mods** instead and ranks *why* they don't convert: which
residue reason blocks the most mods. Use it to choose the next converter work
by how many mods it unblocks, not by issue order.

It is report-only. It never fails a build and never changes a conversion.

## The pieces

| Piece | What it is |
|---|---|
| `fixtures/sample/mods.toml` | The sample: Modrinth mods pinned by version id, primary file url and sha512, in the corpus manifest format. Generated, not hand-edited. |
| `portkit sample build` | Rebuilds the sample from Modrinth's API (`src/portkit/sample.py`). |
| `portkit gaps run` | Fetches (sha512-checked, cached) and converts one shard of the sample, each mod in a child process with a timeout, and writes a shard file (`src/portkit/gaps.py`). |
| `portkit gaps board` | Merges shard files into the leaderboard JSON + markdown, with a trend against a previous leaderboard. |
| `.github/workflows/gap-leaderboard.yml` | Nightly and on demand: four shard jobs, then the board job, which uploads the `gap-leaderboard` artifact (kept 90 days) and writes the markdown to the run summary. |

The jars are downloaded from Modrinth's CDN, measured and discarded. Nothing
from a jar is committed or redistributed, the same as the corpus.

## Running it

In CI: Actions, **gap-leaderboard**, Run workflow (tick or untick mct). The
leaderboard is the run's summary page and its `gap-leaderboard` artifact.

Locally (one shard at a time keeps memory down):

```bash
portkit reference fetch                      # vanilla tags and model templates, as CI has them
portkit gaps run --shard 1/4 --out s1.json   # ... and 2/4, 3/4, 4/4
portkit gaps run --fixture farmers_delight --out fd.json   # just one mod
portkit gaps board s*.json --previous last/gap-leaderboard.json \
    --json gap-leaderboard.json --md gap-leaderboard.md
```

Without `portkit reference fetch`, recipes on shared tags and blocks built
from vanilla templates stay residue and the numbers differ from CI's.

## Reading it

Each row is one **normalized reason**: a residue entry's kind plus its reason
text with the specifics blanked, so the same gap in two mods is one row.

| Blanked | Becomes | Example |
|---|---|---|
| quoted names | `'…'` | unrecognised translation key `'…'` |
| namespaced ids, and lists of them | `<id>`, `<ids>` | ingredient `<id>` is not converted |
| paths and file names | `<path>`, `<file>` | |
| Java class names | `<class>` | |
| blockstate lists `(age=0, age=1)` | `(<states>)` | |
| numbers | `N` | `N` file(s) no converter claims yet |
| "e.g." lists | `(e.g. …)` | |
| the other mod in a compat condition | `<mod>` | compat for `<mod>`: loads only when `<mod>` is installed |

Files no converter claims (`unowned`) all share one reason text, so their key
also carries the directory shape, such as `[data/<ns>/advancement/]`.

Columns:

- **mods**: how many sample mods have at least one entry with this reason.
  The ranking is by this, then by files.
- **files**: source files the entries stand for (an entry grouping 200
  unclaimed models counts 200).
- **entries**: residue entries.
- **e.g.**: the mod this reason covers most; the JSON lists up to 25 mods and
  three raw examples per reason.
- **trend**: against the previous successful run on the same branch: change
  in mods and files, or `new`. Reasons that disappeared are listed under
  "Gone since the previous run". The mods table shows each mod's coverage
  change.

With mct (on the nightly schedule, and on a manual run unless unticked) the
mods table also gives Mojang's validator's error and warning counts per mod,
report-only as in the corpus. In the first runs every mod at 0% coverage
showed exactly one mct error; which rule that is hasn't been looked at yet.

A mod that never produced residue still shows up: a crash, a timeout or a jar
portkit can't ingest (no `assets/` or `data/` tree, such as a pure-code mod)
becomes a `conversion` row. A jar that fails to download or verify is listed
as `fetch_failed` in the mods table.

What to expect at the top: `java_code` is in every mod with classes (the
behaviour in bytecode), and lang and unclaimed-tag rows are in most. They are
true but not where the next win is; read past them to the first row a
converter could take on.

The leaderboard doesn't weigh "kid relevance" yet (#234 proposes mods blocked
× kid relevance); there is no sourced relevance score to multiply by.

## Adding or changing mods

Don't hand-edit `fixtures/sample/mods.toml`; regenerate it:

```bash
portkit sample build --count 50 --licences all   # the default
```

It asks `api.modrinth.com/v2/search?index=downloads` for mods, keeps the
first `--count` that look like content (a content category such as
decoration, food, mobs, worldgen or technology; not a library; not
client-only), and pins each one's newest release build with a
Fabric/Forge/NeoForge/Quilt `.jar` (a project with only betas gets its newest
beta). Every field comes from the API; the notes record the download rank and
count on the build date. `--licences open` drops `LicenseRef-*` licences (All
Rights Reserved and custom ones).

A one-off mod you want measured belongs in the corpus manifest
(`fixtures/real/mods.toml`, see its README), not here: the sample is the
download ranking, and a new build replaces it.

When the sample changes, the next run's trend compares different mods, and
reasons can move because the mods did. The mods table says which mods are
new (no coverage delta).

## Limits of this first slice

- The sample is Modrinth only. (The gauntlet, below, has two CurseForge-only mods, fetched only through CurseForge's official API with a key.)
- Fifty mods, not ~200; the workflow's shard count would need to grow with it.
- The ranking is by mods blocked, not weighted by relevance.
- Normalization is pattern-based and tuned on the first run's 447 reasons; a
  reason text that keeps a mod-specific word unblanked will split into
  several rows until a rule covers it.

## The top-50 gauntlet

The same machinery runs #277's gauntlet: the 50 most popular Java mods,
pinned in `fixtures/real/gauntlet.toml` (#278). The board is
[`docs/gauntlet.md`](gauntlet.md).

| Piece | What it is |
|---|---|
| `fixtures/real/gauntlet.toml` | #277's 50 in its order, one jar each, corpus format plus `rank`, `title`, `host`, `rule`, `redistribution`, `listed_lib` and, for a jar that can't be fetched, `unfetchable` with the reason. Generated by `portkit gauntlet pin`. |
| `portkit gauntlet pin` | Resolves each mod by the version rule (below) from Modrinth's API, or for a mod not on Modrinth from CurseForge's official API when `CURSEFORGE_API_KEY` is set (otherwise its previous pin is kept), and writes the manifest. |
| `portkit gauntlet run` | `portkit gaps run` over the gauntlet, plus a profile of each jar: file counts by kind (assets, data, blockstates, models, textures, recipes, loot tables, lang, sounds, tags, worldgen, structures, classes, nested jars), mixin configs and mixin counts, entrypoints, environment and declared dependencies, and a class read from those (`portkit.gauntlet.classify`). |
| `portkit gauntlet board` | Merges the shards into `gauntlet-board.json` and `docs/gauntlet.md`: per mod class, coverage, residue by reason class, validate and mct status and #277's done flag; the cross-mod reason-class roll-up; the class evidence; and the gap leaderboard's normalized reasons for the same 50. `--bank PATH` also writes the baseline. |
| `fixtures/real/gauntlet-baseline.json` | The banked gauntlet baseline, apart from the 13-mod corpus's `coverage-baseline.json`: the PR gate never runs the 50. The board shows each mod's coverage change against it. |

Run it: Actions, **gap-leaderboard**, Run workflow, set `gauntlet`. It also
runs weekly (Mondays 09:17 UTC). The board is the run summary and the
`gauntlet-board` artifact (kept 90 days, with the shards). To update the
committed board or bank the baseline, download the artifact and run
`portkit gauntlet board shards/*.json --md docs/gauntlet.md --bank
fixtures/real/gauntlet-baseline.json` in a PR.

**Version rule.** The newest build for Minecraft 1.21.1, else 1.20.1,
releases before pre-releases (so a 1.20.1 release beats a 1.21.1 beta), on
the loader the converter reads best for that version: for 1.21.1 NeoForge
(Mojang names, the neoforge-1.21.1 tag set), Fabric, Forge, Quilt; for 1.20.1
Forge (SRG, the forge-1.20.1 tag set), Fabric, NeoForge, Quilt. A mod with
neither version gets its newest release, marked `off-rule` (Chisel: 1.12.2).

**CurseForge.** Twilight Forest and Chisel are not on Modrinth (#278 pick 2,
Alex 2026-10-16). Overwolf treats downloading from CurseForge's CDN outside
its official API as scraping, and an Actions cache on a public repository is
readable by anyone who opens a PR, so:

- The manifest marks both `unfetchable` ("CurseForge-only; awaiting official
  CurseForge API key (allowModDistribution must be true)"), with their
  CurseForge project id (`cf_mod_id`), file id (`version_id`) and sha512
  kept as metadata. Nothing builds a CDN url.
- With `CURSEFORGE_API_KEY` set (the repository's Actions secret of that
  name), `portkit gauntlet run` asks the official API
  (`api.curseforge.com/v1`, `x-api-key` header) for each one's
  `allowModDistribution`. False (or missing): the mod stays `unfetchable`
  with that reason. True: the pinned file's `downloadUrl` from
  `/v1/mods/{id}/files/{fileId}` is fetched, sha512-checked against the pin,
  into a temporary directory that is deleted after the run: re-fetched every
  run, never in the Actions cache, never committed.
- The workflow passes the secret only to the gauntlet's convert step on this
  repository's own scheduled or manual runs, never to `pull_request` runs,
  and portkit never prints it. Each shard records what the API said under
  `curseforge_allow_mod_distribution`.
- Their licences are read from the mods' source repositories (TF: LGPL-2.1
  code, CC-BY-NC-SA-4.0 assets; Chisel: GPL-2.0).

**Classes.** One per jar, the first rule that holds, from its own files
(never its description): **content** (blockstates, item definitions,
recipes, loot tables, worldgen or structures); **library** (a language
adapter, Mod Menu's "library" badge, a bundle of 5+ nested jars with at most
10 classes of its own, most classes in an `api` package, or code only: 100+
classes with no textures, lang or sounds and few mixins); **client-only**
(declared: Fabric environment `client`, NeoForge `clientSideOnly`, a
minecraft dependency on side `CLIENT`, or `displayTest="IGNORE_ALL_VERSION"`);
**performance/mixin-only** (mixins are 10%+ of its classes, at most 10 lang
files and 8 textures, no sounds or shaders); **UI/info** (the rest). The
board's evidence table shows why, next to #277's `[lib]` mark.

**Reason classes and done.** A reason class is a residue kind; files no
converter claims (`unowned`) are split by directory (`unowned
[data/<ns>/worldgen/]`). Kinds the residue agent skips with a documented
reason (`SKIP_KINDS`: `java_code`, `entity`, `machine_recipe`, ...) are
marked explained. A mod is **done** (#277 rule 6) when it converted, the
validator reports no errors, and every residue entry is of an explained
kind. The "next general work" list is the roll-up without explained kinds.
