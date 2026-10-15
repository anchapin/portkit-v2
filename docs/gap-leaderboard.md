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

- Modrinth only. CurseForge's API needs a key and its terms differ.
- Fifty mods, not ~200; the workflow's shard count would need to grow with it.
- The ranking is by mods blocked, not weighted by relevance.
- Normalization is pattern-based and tuned on the first run's 447 reasons; a
  reason text that keeps a mod-specific word unblanked will split into
  several rows until a rule covers it.
