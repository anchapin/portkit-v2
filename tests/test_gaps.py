"""The gap leaderboard (#234): reason normalization, shards, ranking, trend."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from portkit import corpus, gaps
from portkit.cli import main

ROOT = Path(__file__).resolve().parents[1]


# --- normalization: real reasons from Farmer's Delight 1.21.1-1.3.4 ---------

@pytest.mark.parametrize("raw, expected", [
    ("ingredient farmersdelight:birch_cabinet is not converted",
     "ingredient <id> is not converted"),
    ("unrecognised translation key 'tag.block.farmersdelight.survives.rich_soil'",
     "unrecognised translation key '…'"),
    ("222 file(s) no converter claims yet", "N file(s) no converter claims yet"),
    ("compat for immersiveengineering: loads only when immersiveengineering is installed, and "
     "this conversion holds only this mod (fabric:all_mods_loaded immersiveengineering)",
     "compat for <mod>: loads only when <mod> is installed, and this conversion holds only "
     "this mod (<id> …)"),
    ("100 string(s) belong to mod code with no Bedrock text surface (e.g. advancements.a.b, "
     "advancements.c.d, advancements.farmersdelight.eat_",
     "N string(s) belong to mod code with no Bedrock text surface (e.g. …)"),
    ("block has 8 blockstate variant(s) (age=0, age=1, age=2); Bedrock needs explicit block "
     "states and permutations",
     "block has N blockstate variant(s) (<states>); Bedrock needs explicit block states and "
     "permutations"),
    ("facing and booleans: vectorwing.farmersdelight.common.block.RopeFenceGateBlock is a vanilla "
     "FenceGateBlock", "facing and booleans: <class> is a vanilla FenceGateBlock"),
    ("12 key(s) present in de_de but not in en_us went untranslated (e.g. x.y",
     "N key(s) present in <locale> but not in <locale> went untranslated (e.g. …)"),
    ("model extends 'minecraft:block/orientable', whose boxes are in vanilla's model, and the "
     "vanilla model templates aren't cached (run 'portkit reference fetch')",
     "model extends '…', whose boxes are in vanilla's model, and the vanilla model templates "
     "aren't cached (run '…')"),
    ("the drop copies block components (minecraft:copy_components)",
     "the drop copies block components (<id>)"),
    ("texture assets/x/textures/block/a.png is missing", "texture <path> is missing"),
    ("chunky-ffcbedca6a0b.jar has no assets/<namespace> or data/<namespace> tree; nothing to convert",
     "<file> has no <path><namespace> or <path><namespace> tree; nothing to convert"),
    ("unknown load condition forge:mod_loaded, forge:not", "unknown load condition <ids>"),
    ("but this jar adds to c:a, c:b, c:d and 3 more, which", "but this jar adds to <ids>, which"),
    ("blockstate covers only ['x', 'z'] of the three axes (missing ['y'])",
     "blockstate covers only […] of the three axes (missing […])"),
])
def test_normalize_blanks_specifics(raw, expected):
    assert gaps.normalize(raw) == expected


def test_reason_key_keeps_the_source_shape_for_unowned_only():
    assert gaps.reason_key("unowned", "218 file(s) no converter claims yet",
                           "data/farmersdelight/advancement/") == \
        "unowned: N file(s) no converter claims yet [data/<ns>/advancement/]"
    assert gaps.reason_key("lang", "unrecognised translation key 'a.b'", "assets/x/lang/en_us.json") == \
        "lang: unrecognised translation key '…'"


def test_group_residue_totals_and_examples():
    entries = [{"kind": "station_recipe", "source": f"data/fd/recipe/{i}.json",
                "reason": f"ingredient fd:thing_{i} is not converted", "count": 1} for i in range(5)]
    entries.append({"kind": "unowned", "source": "data/fd/tags/", "reason": "160 file(s) no converter claims yet",
                    "count": 160})
    grouped = gaps.group_residue(entries)
    slot = grouped["station_recipe: ingredient <id> is not converted"]
    assert (slot["entries"], slot["files"], len(slot["examples"])) == (5, 5, 3)
    assert slot["examples"][0]["reason"] == "ingredient fd:thing_0 is not converted"
    assert grouped["unowned: N file(s) no converter claims yet [data/<ns>/tags/]"]["files"] == 160


# --- shards ------------------------------------------------------------------

def test_parse_and_split_shards():
    assert gaps.parse_shard(None) == (1, 1)
    assert gaps.parse_shard("2/4") == (2, 4)
    for bad in ("0/4", "5/4", "x", "1/0"):
        with pytest.raises(ValueError):
            gaps.parse_shard(bad)
    items = list(range(10))
    parts = [gaps.shard_of(items, i, 3) for i in (1, 2, 3)]
    assert parts == [[0, 3, 6, 9], [1, 4, 7], [2, 5, 8]]
    assert sorted(sum(parts, [])) == items


def _mod(name, **kw):
    base = dict(name=name, project=name, version_id="v", url="https://cdn.modrinth.com/x.jar",
                sha512="0" * 128, license="MIT", loader="fabric", minecraft="1.21.1", version="1")
    base.update(kw)
    return corpus.Mod(**base)


def _record(coverage, reasons):
    return {"status": "ok", "namespace": "x", "files": 10, "residue": sum(r[2] for r in reasons),
            "coverage": coverage, "valid": True, "errors": 0, "seconds": 1.0,
            "reasons": {f"{k}: {r}": {"kind": k, "reason": r, "entries": 1, "files": f,
                                      "examples": [{"source": "s", "reason": r}]}
                        for k, r, f in reasons}}


def test_run_shard_records_fetch_failures_crashes_and_timeouts():
    mods = [_mod("a"), _mod("b"), _mod("c"), _mod("d")]

    def fetch(mod):
        if mod.name == "b":
            raise corpus.CorpusError("b: sha512 mismatch")
        return Path(f"/jars/{mod.name}.jar")

    def convert(jar, work, timeout):
        assert work.is_dir()
        name = jar.stem
        if name == "c":
            return {"status": "crashed", "detail": "KeyError: 'model'", "seconds": 0.1}
        if name == "d":
            return {"status": "timeout", "detail": "conversion took longer than 5s", "seconds": 5}
        return _record(50.0, [("block", "model has no parent and no elements", 3)])

    doc = gaps.run_shard(mods, shard="1/1", manifest="m.toml", fetch=fetch, convert=convert,
                         timeout=5, log=lambda *_: None)
    assert doc["kind"] == "gap-shard" and doc["shard"] == "1/1"
    assert {n: r["status"] for n, r in doc["mods"].items()} == \
        {"a": "ok", "b": "fetch_failed", "c": "crashed", "d": "timeout"}
    assert doc["mods"]["a"]["license"] == "MIT"


def test_convert_one_runs_a_real_child(tmp_path):
    record = gaps.convert_one(ROOT / "fixtures" / "residue_mod" / "input", tmp_path, timeout=120)
    assert record["status"] == "ok"
    assert record["files"] > 0 and 0 <= record["coverage"] < 100
    assert record["reasons"] and sum(r["files"] for r in record["reasons"].values()) == record["residue"]
    assert (tmp_path / "out").is_dir()  # left for mct


def test_convert_one_reports_a_jar_with_nothing_to_convert(tmp_path):
    import zipfile

    empty = tmp_path / "empty-1234.jar"
    with zipfile.ZipFile(empty, "w") as zf:
        zf.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
    work = tmp_path / "work"
    work.mkdir()
    record = gaps.convert_one(empty, work, timeout=120)
    assert record["status"] == "ingest_error", record
    board = gaps.leaderboard([_shard("1/1", {"empty": record})])
    assert board["reasons"][0]["key"].startswith("conversion: cannot ingest: ")
    assert "1234" not in board["reasons"][0]["key"]


def test_convert_one_reports_a_crash_and_a_timeout(tmp_path):
    def crash(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, "", "Traceback...\nKeyError: 'model'\n")

    rec = gaps.convert_one(Path("x.jar"), tmp_path, runner=crash)
    assert rec["status"] == "crashed" and rec["detail"] == "KeyError: 'model'"

    def hang(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])

    rec = gaps.convert_one(Path("x.jar"), tmp_path, timeout=3, runner=hang)
    assert rec["status"] == "timeout"


# --- the leaderboard -----------------------------------------------------------

def _shard(index, mods):
    return {"schema": 1, "kind": "gap-shard", "manifest": "fixtures/sample/mods.toml",
            "shard": index, "generated": "t", "mods": mods}


def _two_shards():
    return [
        _shard("1/2", {
            "a": {**_record(40.0, [("block", "model has no parent and no elements", 5),
                                   ("loot", "table has N pools", 2)]), "license": "MIT"},
            "b": {**_record(60.0, [("block", "model has no parent and no elements", 1)]), "license": "ARR"},
        }),
        _shard("2/2", {
            "c": {**_record(80.0, [("loot", "table has N pools", 9)])},
            "d": {"status": "crashed", "detail": "KeyError: 'model'", "seconds": 0.2},
        }),
    ]


def test_leaderboard_ranks_by_mods_then_files():
    board = gaps.leaderboard(_two_shards())
    keys = [r["key"] for r in board["reasons"]]
    assert keys[:2] == ["loot: table has N pools", "block: model has no parent and no elements"]
    top = board["reasons"][0]
    assert (top["mods"], top["files"], top["mod_names"]) == (2, 11, ["c", "a"])  # most files first
    crash = next(r for r in board["reasons"] if r["kind"] == "conversion")
    assert crash["reason"] == "conversion crashed: KeyError: '…'" and crash["mods"] == 1
    assert board["statuses"] == {"crashed": 1, "ok": 3}
    assert board["mean_coverage"] == 60.0
    assert "trend" not in top and "previous" not in board


def test_leaderboard_refuses_a_mod_in_two_shards_and_foreign_documents():
    s = _two_shards()
    s[1]["mods"]["a"] = s[0]["mods"]["a"]
    with pytest.raises(ValueError):
        gaps.leaderboard(s)
    with pytest.raises(ValueError):
        gaps.leaderboard([{"kind": "gap-leaderboard"}])


def test_trend_against_the_previous_leaderboard():
    previous = gaps.leaderboard(_two_shards())
    now = _two_shards()
    now[0]["mods"]["a"] = _record(45.0, [("loot", "table has N pools", 2), ("sound", "new thing", 1)])
    board = gaps.leaderboard(now, previous)
    by_key = {r["key"]: r for r in board["reasons"]}
    assert by_key["sound: new thing"]["trend"] == {"new": True}
    assert by_key["block: model has no parent and no elements"]["trend"] == {"mods": -1, "files": -5, "rank": 0}
    assert by_key["loot: table has N pools"]["trend"]["mods"] == 0
    assert board["previous"]["gone"] == []
    a = next(m for m in board["mods"] if m["name"] == "a")
    assert a["coverage_delta"] == 5.0
    # a reason fixed everywhere shows as gone
    now[0]["mods"]["b"] = _record(70.0, [])
    board = gaps.leaderboard(now, previous)
    assert board["previous"]["gone"] == ["block: model has no parent and no elements"]


def test_markdown_has_the_ranked_table_trend_and_mods():
    previous = gaps.leaderboard(_two_shards())
    md = gaps.render_markdown(gaps.leaderboard(_two_shards(), previous))
    assert md.startswith("# Gap leaderboard")
    assert "| 1 | 2 | 11 | 2 | loot | table has N pools | c | +0 mods, +0 files |" in md
    assert "| d | crashed: KeyError: 'model' |" in md
    assert "## Mods" in md and "mct" not in md
    shards = _two_shards()
    shards[0]["mods"]["a"]["mct"] = {"error": 1, "warning": 7, "recommendation": 0}
    md = gaps.render_markdown(gaps.leaderboard(shards))
    assert "mct errors / warnings |" in md and "| 1 / 7 |" in md


def test_cli_board_writes_json_and_markdown(tmp_path, capsys):
    paths = []
    for i, doc in enumerate(_two_shards()):
        p = tmp_path / f"s{i}.json"
        p.write_text(json.dumps(doc))
        paths.append(str(p))
    out_json, out_md = tmp_path / "b.json", tmp_path / "b.md"
    assert main(["gaps", "board", *paths, "--previous", str(tmp_path / "missing.json"),
                 "--json", str(out_json), "--md", str(out_md)]) == 0
    assert "no previous leaderboard" in capsys.readouterr().out
    board = json.loads(out_json.read_text())
    assert board["kind"] == "gap-leaderboard" and board["mods_total"] == 4
    assert out_md.read_text().startswith("# Gap leaderboard")
    # and again with that board as the previous one: the trend column appears
    assert main(["gaps", "board", *paths, "--previous", str(out_json),
                 "--json", str(tmp_path / "c.json"), "--md", str(out_md)]) == 0
    assert "trend |" in out_md.read_text()


def test_cli_run_with_a_bad_shard_is_a_usage_error(capsys):
    assert main(["gaps", "run", "--shard", "3/2"]) == 2


# --- the committed sample manifest ----------------------------------------------

def test_sample_manifest_loads_in_the_corpus_format():
    mods = corpus.load(ROOT / "fixtures" / "sample" / "mods.toml")
    assert len(mods) >= 20
    for m in mods:
        assert m.url.startswith("https://cdn.modrinth.com/data/"), m.name
        assert f"/versions/{m.version_id}/" in m.url, m.name
        assert m.license and m.loader in ("fabric", "forge", "neoforge", "quilt"), m.name
        assert "download rank" in m.notes, m.name
    # sha512 pins are unique (no two entries are the same file)
    assert len({m.sha512 for m in mods}) == len(mods)
