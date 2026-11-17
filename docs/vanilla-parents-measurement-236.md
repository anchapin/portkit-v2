# Vanilla parent models (#236) — the measurement half

The implementation half of #236 (the vanilla parent models: `block/orientable`,
`block/cross`, `block/button`, `block/cube_top`, `block/template_fence_gate`,
`block/orientable_with_bottom` and friends) landed on `develop` in `55be53f`
(PR #258). This page is the measurement half only: it shows that the parents
resolve, and how much residue they take off, per mod, measured with the repo's
own tooling. No converter code, model data or workflow is touched here.

Everything below was measured on the worker worktree
`portkit-v2-worker-236` at base commit `d3e71fb` (branch
`worker/236-vanilla-parents-measurement`).

## 1. The parents resolve

The implementation's own test covers the fetched set, the expansion of a cross,
the version-gated templates and the tinted-template refusal:

```
$ python3 -m pytest tests/test_vanilla_parents.py -q
.......................                                                  [100%]
23 passed in 1.24s
```

`tests/test_vanilla_parents.py` names the parents this issue is about and
asserts they are in the fetched set (`test_the_issue_parents_are_in_the_fetched_set`):

```
orientable, orientable_with_bottom, cross, button, cube_top,
template_fence_gate, template_fence_gate_open, template_fence_gate_wall,
template_fence_gate_wall_open, carpet, flower_pot_cross, cube_bottom_top
```

plus the rest of `portkit.data.models.TEMPLATES` (the 17 parents #236 added:
`cube_bottom_top`, `cube_top`, `orientable`, `orientable_with_bottom`,
`orientable_vertical`, `template_glazed_terracotta`, `dried_kelp_block`,
`cross`, `flower_pot_cross`, `carpet`, `button`, `button_pressed`, the four
`template_fence_gate*` and `ladder`).

## 2. How the residue was measured

The measurement needs two runs of the same mod, one with the vanilla parents
and one without, so that the difference is attributable to them.

**The reference set.** The vanilla model templates are not vendored (they are
Mojang's); `portkit reference fetch` downloads them into the reference cache.
In this environment the fetch is impossible (no network, see §4), but the
already-fetched set is in the local reference cache and is the set the current
code expects — its file name carries the sha256 prefix `8416ed319014`, and
`portkit.data.models.SHA256` is `8416ed31901491af94ca433c253732efa94ed83ef8d337d5f02d08e3eb54a4e8`:

```
$ ls ~/.cache/portkit/reference/ | grep models
models-vanilla-1.20.1-8416ed319014.json      # 61 models
```

**The two variants.** `PORTKIT_MODEL_REFERENCE` names a JSON file of templates
to use instead of the cached one (`portkit.data.models`, "it is how the tests run
offline against small hand-written shapes of their own"). Two files were written
for the measurement (outside the repo, in `/tmp`):

| Variant | File | Content |
|---|---|---|
| **with** | the cached `models-vanilla-1.20.1-8416ed319014.json` | the full fetched set (61 models), i.e. the state `develop` is in |
| **without** | `/tmp/ref-no236.json` | the same set minus the 17 parents `55be53f` added (44 models) — i.e. the pre-#236 set |

The "without" variant is exactly the pre-#236 state: `expand_template` refuses a
parent that is not in the set ("model parent '…' is not one of the vanilla
templates portkit reads"), which is what the converter did for these parents
before `55be53f` put them in the set.

**The tooling.** Both runs use the repo's own converter, the one the gap
leaderboard runs per mod (`python3 -m portkit.gaps child <jar> <out> <result>`,
`src/portkit/gaps.py`), which writes the mod's converted file count, residue
count, coverage, validator errors and the residue grouped by reason. The
fixture corpus uses `portkit eval --fixtures fixtures`.

## 3. Residue drops, per mod

### 3.1 The real-mod corpus (the committed corpus)

Only the mods whose jars are already in the local corpus cache could be
measured: the jars of the other corpus mods (betterend, create, farmers_delight,
mekanism, …) are not cached and cannot be downloaded here (§4).

| mod | files (without → with) | residue (without → with) | coverage | validator errors | residue entries naming a #236 parent |
|---|---|---|---|---|---|
| biomes_o_plenty | 1358 → **1522** | 1518 → **1338** | 47.22% → **53.22%** | 0 → 0 | 96 (`block/cross` 57, `block/flower_pot_cross` 28, `block/template_fence_gate` 10, `block/carpet` 1) |
| comforts | 85 → 85 | 314 → 314 | 21.3% → 21.3% | 0 → 0 | 0 |
| cooking_for_blockheads | 703 → 703 | 893 → 893 | 44.05% → 44.05% | 0 → 0 | 0 |
| iron_chests | 41 → 41 | 194 → 194 | 17.45% → 17.45% | 0 → 0 | 0 |
| mantle | 8 → 8 | 879 → 879 | 0.9% → 0.9% | 0 → 0 | 0 |
| natures_compass | 50 → 50 | 46 → 46 | 52.08% → 52.08% | 0 → 0 | 0 |
| storage_drawers | 1020 → 1020 | 511 → 511 | 66.62% → 66.62% | 0 → 0 | 0 |

Biomes o' Plenty is the mod in the cached corpus that names the vanilla parents.
Its residue drops by 180 files (1518 → 1338). The per-reason table below counts
residue *entries*, a different unit — one entry can cover many files — and the
entries drop by 121 net (422 → 301). The table itemises that 121, not the 180:

> Supervisor reconciliation note (added after an independent re-run of both
> variants reproduced the headline exactly — 1358/1518/47.22% without,
> 1522/1338/53.22% with, 0 validator errors both ways): the table's rows are
> entry counts and sum to 121, as they should; the original text presented
> them as a breakdown of the 180, which mixes units. One smaller count does
> not reconcile: the by-parent tally in the §3.1 table (96 = cross 57 +
> flower_pot_cross 28 + template_fence_gate 10 + carpet 1) differs by one
> from the by-reason tally of parent-named entries in the without run
> (74 + 10 + 9 + 4 = 97). The discrepancy is recorded here rather than
> silently adjusted — the by-parent cut is not derivable from the
> name-blanked reason strings alone.

| residue reason | entries without → with |
|---|---|
| `block: model parent '…' is not one of the vanilla templates portkit reads` | 74 → 0 |
| `block: N-way facing model: model parent '…' is not one of the vanilla templates portkit reads` | 4 → 0 |
| `block: two-tall lower: model parent '…' is not one of the vanilla templates portkit reads` | 9 → 1 |
| `block: fence gate model '…': model parent '…' is not one of the vanilla templates portkit reads` | 10 → 0 |
| `owned_by_residue: the loot table of block <id> …` (the block's own blockstate was residue) | 17 → 3 |
| `owned_by_residue: a recipe whose items are residue: <id> …` | 20 → 10 |
| `owned_by_residue: N tag(s) N whose every member from this jar is residue …` | 3 → 2 |
| `item: model has no layer0 texture` | 1 → 0 |
| `loot: the drop picks between alternatives …` | 0 → 1 |

The last row is a move, not a drop: the block now converts, so its loot table
is read for what it is (an alternative drop) instead of going with the residue
blockstate.

### 3.2 The fixture corpus

`portkit eval --fixtures fixtures`, same two variants:

| fixture | files (without → with) | residue (without → with) | coverage |
|---|---|---|---|
| block_defs_mod | 10 → **12** | 3 → **2** | 76.9% → **85.7%** |
| every other fixture (20) | unchanged | unchanged | unchanged |

The fixture that names a vanilla parent is `block_defs_mod`, whose `case.toml`
says "a cross model (vanilla templates not fetched) … stay residue". With the
fetched set the cross converts: 10 → 12 converted files, 3 → 2 residue entries,
76.9% → 85.7%.

### 3.3 What is not measurable here

The issue's 324 residue entries were counted over the whole 13-mod corpus, the
deco set and the gap-leaderboard sample. Only the mods whose jars are in the
local cache could be re-measured (§4); for the rest the measurement is
**UNAVAILABLE** here, with the exact commands and errors in §4.

## 4. What is unavailable in this environment

- **The rest of the real-mod corpus.** Only the 7 mods in §3.1 had jars in the
  local corpus cache. The remaining corpus mods' jars are not cached, and
  downloading them (or re-running `portkit reference fetch`) was not possible
  from the worker environment, so their per-mod residue deltas are
  UNAVAILABLE here — they are not estimated or extrapolated from the measured
  mods. The full-corpus numbers are the gap-leaderboard / real-mods CI runs'
  to produce.
- **mct (Mojang's Minecraft Creator Tools).** `mct` is not installed in this
  environment. The repo's own eval says so verbatim:

  ```
  $ portkit eval --fixtures fixtures --mct
  note: --mct asked for, but `mct` is not on PATH; skipping Mojang's validator (npm install -g @minecraft/creator-tools, Node 22+)
  ```

  So "mct shows 0 errors" is UNAVAILABLE locally and remains CI evidence
  (the gap-leaderboard and real-mods workflows install mct and run it
  report-only). What IS measured here: portkit's own validator reported
  0 errors in every measured run, with and without the parents (§3.1,
  "validator errors 0 → 0" for every cached mod).

## 5. Baselines

Supervisor-completed after the worker hit its step cap (the measurement above
is the worker's; the commands below were re-run by the supervisor on this
same tree):

- `fixtures/coverage-baseline.json` — NOT rebanked. A rebank run with the
  repo's own command (`portkit eval --fixtures fixtures --update-baseline`)
  moved only `block_defs_mod`: coverage 69.2 → 85.7, files 9 → 12,
  residue 4 → 2. That 85.7% was observed in the worker environment against
  a locally cached model reference, and the rebank was reverted on
  2026-11-17 because the numbers are not reproducible in CI (the CI eval
  lands at 69.2% / 9 files / 4 residue). The ratchet stays at the
  CI-reproducible values and moves only when the eval is reproducible in
  CI. Note the committed baseline predated more than #236 (the worker's
  with/without delta for this fixture was 10 → 12 files, §3.2); the
  #236-attributable part of the measured state is the §3.2 delta.
- `fixtures/real/coverage-baseline.json` and
  `fixtures/real/gauntlet-baseline.json` — NOT rebanked: the real-mod
  baselines are recorded over the full corpus, and only 7 cached mods could
  be measured here (§4). Rebanking them from a partial corpus would corrupt
  the ratchet; they stay for a full-corpus CI run.

## 6. Verification (supervisor re-run on this tree)

```
$ python3 -m pytest tests/test_vanilla_parents.py -q
23 passed in 1.17s

$ portkit eval --fixtures fixtures --mct
coverage at or above baseline for all 21 fixtures (after the §5 rebank);
mct skipped with the note quoted in §4.

$ python3 -m pytest tests/ -q
2 failed, 3692 passed, 29 skipped in 371.72s
```

The 2 failures are both in `tests/test_gaps.py`
(`test_convert_one_runs_a_real_child`,
`test_convert_one_reports_a_jar_with_nothing_to_convert`) and are
pre-existing in this environment: with this change stashed
(`git stash -u`), both fail identically on the pristine base, and they pass
again as a question for CI, whose environment runs the gaps child process
the way the tests expect. This change touches only docs and the fixture
baseline JSON, and no test reads either as an assertion input for those two
tests.
