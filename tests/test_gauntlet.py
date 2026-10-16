"""The top-50 gauntlet harness (#278): pin rule, jar profile/class, run, board."""
from __future__ import annotations

import io
import json
import tomllib
import urllib.parse
import zipfile
from pathlib import Path

import pytest

from portkit import corpus, gaps, gauntlet
from portkit.cli import main

ROOT = Path(__file__).resolve().parents[1]


# --- the version rule ------------------------------------------------------------

def _b(id_, type_, loaders, games, date):
    return {"id": id_, "type": type_, "loaders": loaders, "game_versions": games, "date": date}


def test_rule_prefers_1211_on_the_best_loader_then_1201():
    builds = [
        _b("fab", "release", ["fabric"], ["1.21.1"], "2026-09"),
        _b("neo", "release", ["neoforge"], ["1.21", "1.21.1"], "2026-08"),
        _b("forge20", "release", ["forge"], ["1.20.1"], "2026-10"),
    ]
    chosen, rule = gauntlet.pick(builds)
    assert chosen["id"] == "neo" and rule == "1.21.1 neoforge release"
    chosen, rule = gauntlet.pick(builds[:1] + builds[2:])
    assert chosen["id"] == "fab" and rule == "1.21.1 fabric release"
    chosen, rule = gauntlet.pick(builds[2:])
    assert chosen["id"] == "forge20" and rule == "1.20.1 forge release"


def test_rule_takes_releases_before_pre_releases_and_the_newest_in_a_slot():
    builds = [
        _b("beta211", "beta", ["neoforge"], ["1.21.1"], "2026-10"),
        _b("old201", "release", ["forge"], ["1.20.1"], "2025-01"),
        _b("new201", "release", ["forge"], ["1.20.1"], "2026-01"),
    ]
    chosen, rule = gauntlet.pick(builds)
    assert chosen["id"] == "new201" and rule == "1.20.1 forge release"
    chosen, rule = gauntlet.pick(builds[:1])
    assert chosen["id"] == "beta211" and rule == "1.21.1 neoforge pre-release"


def test_off_rule_when_neither_version_exists():
    builds = [_b("a165", "alpha", ["forge"], ["1.16.5"], "2021"),
              _b("r1122", "release", ["forge"], ["1.12.2"], "2020")]
    assert gauntlet.pick(builds) is None
    chosen, rule = gauntlet.pick_off_rule(builds)
    assert chosen["id"] == "r1122" and rule.startswith("off-rule")
    assert gauntlet._slot_of(chosen, rule) == ("1.12.2", "forge")
    assert gauntlet.pick_off_rule([_b("x", "release", ["bukkit"], ["1.21.1"], "2026")]) is None


def test_forgecdn_url_splits_the_file_id():
    assert gauntlet.forgecdn_url(7797302, "twilightforest-1.21.1-4.8.3345-universal.jar") == \
        "https://mediafilez.forgecdn.net/files/7797/302/twilightforest-1.21.1-4.8.3345-universal.jar"
    assert gauntlet.forgecdn_url(4865011, "a b+c.jar").endswith("/4865/11/a%20b%2Bc.jar")


def _modrinth_opener(project, versions):
    def opener(request, timeout):
        path = urllib.parse.urlparse(request.full_url).path
        body = versions if path.endswith("/version") else project
        return io.BytesIO(json.dumps(body).encode())
    return opener


def _mr_version(id_, type_, loaders, games, date, sha):
    return {"id": id_, "version_number": id_, "version_type": type_, "loaders": loaders,
            "game_versions": games, "date_published": date,
            "files": [{"primary": True, "filename": f"{id_}.jar", "url": f"https://cdn.modrinth.com/{id_}.jar",
                       "hashes": {"sha512": sha}}]}


def test_pin_modrinth_from_api_data():
    project = {"id": "P1", "license": {"id": "MIT"}, "downloads": 5}
    versions = [_mr_version("fab", "release", ["fabric", "quilt"], ["1.21.1"], "2026-10-02", "1" * 128),
                _mr_version("neo", "release", ["neoforge"], ["1.21.1"], "2026-09-01", "2" * 128),
                {"id": "zip", "version_type": "release", "loaders": ["neoforge"], "game_versions": ["1.21.1"],
                 "date_published": "2026-10-09", "files": [{"primary": True, "filename": "x.zip", "url": "u",
                                                            "hashes": {"sha512": "3" * 128}}]}]
    item = gauntlet.Listed(9, "thing", "Thing", "thing")
    entry = gauntlet.pin_modrinth(item, _modrinth_opener(project, versions))
    assert (entry["version_id"], entry["loader"], entry["minecraft"], entry["sha512"]) == \
        ("neo", "neoforge", "1.21.1", "2" * 128)
    assert entry["host"] == "modrinth" and entry["license"] == "MIT" and entry["rank"] == 9


def test_pin_curseforge_pins_the_cdn_jar_or_records_why_not():
    files = {"id": 1, "files": [
        {"id": 7797302, "name": "tf-1.21.1.jar", "type": "release", "display": "TF 1.21.1",
         "versions": ["1.21.1", "NeoForge", "Client"], "uploaded_at": "whenever"},
        {"id": 9091040, "name": "tf-fabric.jar", "type": "beta", "display": "TF fabric",
         "versions": ["1.21.1", "Fabric"], "uploaded_at": "later"},
    ]}

    def opener(request, timeout):
        return io.BytesIO(json.dumps(files).encode())

    item = gauntlet.Listed(34, "twilight_forest", "TF", curseforge="the-twilight-forest", licence="LGPL",
                           redistribution="r")
    seen = []
    entry = gauntlet.pin_curseforge(item, opener, download=lambda url, op: seen.append(url) or "a" * 128)
    assert entry["version_id"] == "7797302" and entry["rule"] == "1.21.1 neoforge release"
    assert seen == ["https://mediafilez.forgecdn.net/files/7797/302/tf-1.21.1.jar"]
    assert entry["sha512"] == "a" * 128 and entry["host"] == "curseforge" and entry["license"] == "LGPL"

    def refuse(url, op):
        raise gauntlet.PinError("HTTP Error 403: Forbidden")

    entry = gauntlet.pin_curseforge(item, opener, download=refuse)
    assert entry["unfetchable"].startswith("CurseForge CDN refused the jar without an API key")
    assert "url" not in entry


def test_rendered_manifest_round_trips_with_an_unfetchable_entry(tmp_path):
    good = {"name": "a", "rank": 1, "title": "A", "project": "a", "host": "modrinth", "version_id": "v",
            "version": "1", "loader": "neoforge", "minecraft": "1.21.1", "rule": "1.21.1 neoforge release",
            "license": "MIT", "redistribution": "r", "url": "https://cdn.modrinth.com/a.jar",
            "sha512": "0" * 128, "listed_lib": True, "notes": "n"}
    bad = gauntlet._unfetchable(gauntlet.Listed(2, "b", "B", curseforge="b"), "curseforge", "needs a key")
    text = gauntlet.render_manifest([good, bad], "2026-10-16")
    assert tomllib.loads(text)["mod"][1]["unfetchable"] == "needs a key"
    path = tmp_path / "g.toml"
    path.write_text(text)
    mods = corpus.load(path)
    assert mods[0].listed_lib is True and mods[0].rank == 1
    assert mods[1].unfetchable == "needs a key" and mods[1].url == ""
    with pytest.raises(corpus.CorpusError, match="unfetchable: needs a key"):
        corpus.fetch(mods[1], tmp_path)


def test_corpus_load_still_requires_pins_for_fetchable_entries(tmp_path):
    path = tmp_path / "g.toml"
    path.write_text('[[mod]]\nname = "a"\nproject = "a"\nlicense = "MIT"\n')
    with pytest.raises(corpus.CorpusError, match="missing version_id, url, sha512"):
        corpus.load(path)
    path.write_text('[[mod]]\nname = "a"\nproject = "a"\nlicense = "MIT"\nunfetchable = "x"\nrank = "1"\n')
    with pytest.raises(corpus.CorpusError, match="rank must be an integer"):
        corpus.load(path)


# --- profiling and classifying jars ------------------------------------------------

def _jar(tmp_path, name, files: dict) -> Path:
    path = tmp_path / f"{name}.jar"
    with zipfile.ZipFile(path, "w") as zf:
        for n, body in files.items():
            zf.writestr(n, body if isinstance(body, (str, bytes)) else json.dumps(body))
    return path


def _classes(n, prefix="com/x/", mixin=0):
    out = {f"{prefix}C{i}.class": b"\xca\xfe" for i in range(n)}
    out.update({f"{prefix}mixin/M{i}.class": b"\xca\xfe" for i in range(mixin)})
    return out


NEO = '''modLoader="javafml"
loaderVersion="[4,)"
license="MIT"
[[mods]]
modId="thing"
{extra}
[[dependencies.thing]]
modId="minecraft"
type="required"
{side}
[[dependencies.thing]]
modId="balm"
type="required"
[[dependencies.thing]]
modId="jei"
type="optional"
[[mixins]]
config="thing.mixins.json"
'''


def test_profile_counts_kinds_and_reads_neoforge_metadata(tmp_path):
    jar = _jar(tmp_path, "content", {
        "META-INF/neoforge.mods.toml": NEO.format(extra="", side=""),
        "thing.mixins.json": {"mixins": ["A", "B"], "client": ["C"]},
        "assets/thing/blockstates/a.json": {}, "assets/thing/models/block/a.json": {},
        "assets/thing/models/item/a.json": {}, "assets/thing/textures/block/a.png": b"",
        "assets/thing/textures/gui/g.png": b"", "assets/thing/lang/en_us.json": {},
        "assets/thing/sounds.json": {}, "assets/thing/sounds/a.ogg": b"",
        "data/thing/recipe/a.json": {}, "data/thing/loot_table/blocks/a.json": {},
        "data/thing/tags/item/a.json": {}, "data/thing/worldgen/biome/a.json": {},
        **_classes(3),
    })
    prof = gauntlet.profile(jar)
    c = prof["counts"]
    assert (c["blockstates"], c["block_models"], c["item_models"], c["textures"], c["gui_textures"]) == (1, 1, 1, 2, 1)
    assert (c["lang"], c["sounds"], c["recipes"], c["loot_tables"], c["tags"], c["worldgen"]) == (1, 2, 1, 1, 1, 1)
    assert prof["loaders"] == ["neoforge"] and prof["mod_ids"] == ["thing"]
    assert prof["dependencies"] == ["balm"]  # required only; minecraft/neoforge left out
    assert prof["mixin_configs"] == ["thing.mixins.json"]
    assert prof["mixin_classes"] == {"common": 2, "client": 1, "server": 0}
    assert prof["environment"] == "*" and prof["namespaces"] == ["thing"]
    assert gauntlet.classify(prof)[0] == "content"


def _fabric(env="*", **extra):
    return {"schemaVersion": 1, "id": "thing", "environment": env,
            "entrypoints": {"main": ["a"], "client": ["b"]}, "mixins": ["thing.mixins.json"],
            "depends": {"fabricloader": "*", "minecraft": "*", "fabric-api": "*"}, **extra}


@pytest.mark.parametrize("files, expected, evidence", [
    # a language adapter is a library whatever else it holds
    ({"fabric.mod.json": _fabric(languageAdapters={"kotlin": "x"})}, "library", "language adapter"),
    # a bundle of nested module jars with almost no code of its own
    ({"fabric.mod.json": _fabric(), **{f"META-INF/jars/m{i}.jar": b"" for i in range(6)}},
     "library", "bundles 6 nested jars"),
    # most classes in an api package
    ({"fabric.mod.json": _fabric(), **_classes(6, "com/x/api/"), **_classes(2)}, "library", "api classes 6/8"),
    # code only: lots of classes, nothing user-facing, few mixins
    ({"META-INF/neoforge.mods.toml": NEO.format(extra="", side=""), **_classes(120)}, "library", "code only"),
    # declared client-only
    ({"fabric.mod.json": _fabric(env="client"), "assets/thing/lang/en_us.json": {}}, "client-only", "declares"),
    ({"META-INF/neoforge.mods.toml": NEO.format(extra='displayTest="IGNORE_ALL_VERSION"', side=""),
      "assets/thing/lang/en_us.json": {}}, "client-only", "IGNORE_ALL_VERSION"),
    ({"META-INF/neoforge.mods.toml": NEO.format(extra="", side='side="CLIENT"'),
      "assets/thing/lang/en_us.json": {}}, "client-only", "declares"),
    # mixin-heavy, nothing user-facing
    ({"fabric.mod.json": _fabric(), "thing.mixins.json": {"mixins": [f"M{i}" for i in range(4)]},
      **_classes(10, mixin=4)}, "performance/mixin-only", "4 mixin(s) in 14 classes"),
    # mixins but a lot of lang: a tooltip/UI mod, not a performance one
    ({"fabric.mod.json": _fabric(), "thing.mixins.json": {"mixins": ["A", "B"]}, **_classes(5, mixin=2),
      **{f"assets/thing/lang/l{i}.json": {} for i in range(12)}}, "UI/info", "lang 12"),
])
def test_classify_from_contents(tmp_path, files, expected, evidence):
    got, why = gauntlet.classify(gauntlet.profile(_jar(tmp_path, "j", files)))
    assert got == expected
    assert any(evidence in e for e in why), why


def test_profile_and_classify_adds_class_and_evidence(tmp_path):
    jar = _jar(tmp_path, "c", {"fabric.mod.json": _fabric(), "data/thing/recipes/a.json": {}})
    out = gauntlet.profile_and_classify(jar)
    assert out["class"] == "content" and out["evidence"] == ["recipes 1"]
    assert out["dependencies"] == ["fabric-api"] and out["entrypoints"] == ["client", "main"]


# --- running a shard with profiles and unfetchable mods -------------------------------

def _mod(name, **kw):
    base = dict(name=name, project=name, version_id="v", url="https://cdn.modrinth.com/x.jar",
                sha512="0" * 128, license="MIT", loader="neoforge", minecraft="1.21.1", version="1")
    base.update(kw)
    return corpus.Mod(**base)


def _record(coverage, reasons, errors=0):
    return {"status": "ok", "namespace": "x", "files": 10, "residue": sum(r[2] for r in reasons),
            "coverage": coverage, "valid": not errors, "errors": errors, "seconds": 1.0,
            "reasons": {(f"{k}: {r}" + (f" [{src}]" if src else "")):
                        {"kind": k, "reason": r, "entries": 1, "files": f, "examples": []}
                        for k, r, f, *rest in reasons for src in [rest[0] if rest else ""]}}


def test_run_shard_profiles_jars_and_records_unfetchable_mods():
    mods = [_mod("a", rank=1, title="A", listed_lib=True),
            _mod("b", rank=2, url="", sha512="", version_id="", unfetchable="needs an API key")]
    fetched = []

    def fetch(mod):
        fetched.append(mod.name)
        return Path(f"/jars/{mod.name}.jar")

    doc = gaps.run_shard(mods, fetch=fetch, convert=lambda jar, work, t: _record(50.0, []),
                         profile=lambda jar: {"class": "content", "evidence": ["recipes 1"]},
                         log=lambda *_: None)
    assert fetched == ["a"]
    a, b = doc["mods"]["a"], doc["mods"]["b"]
    assert a["profile"]["class"] == "content" and a["rank"] == 1 and a["title"] == "A" and a["listed_lib"]
    assert (b["status"], b["detail"]) == ("unfetchable", "needs an API key")


def test_run_shard_survives_a_profile_that_fails():
    def boom(jar):
        raise zipfile.BadZipFile("not a zip")

    doc = gaps.run_shard([_mod("a")], fetch=lambda m: Path("/x.jar"),
                         convert=lambda jar, work, t: _record(1.0, []), profile=boom, log=lambda *_: None)
    assert doc["mods"]["a"]["profile"]["class"] == "?"
    assert "profile failed" in doc["mods"]["a"]["profile"]["evidence"][0]


# --- the board ---------------------------------------------------------------------

def _shard(mods):
    return {"schema": 1, "kind": "gap-shard", "manifest": "fixtures/real/gauntlet.toml", "shard": "1/1",
            "generated": "t", "mods": mods}


def _shards():
    content = {"class": "content", "evidence": ["blockstates 3"]}
    return [_shard({
        "quark": {**_record(30.0, [("unowned", "N file(s) no converter claims yet", 40,
                                    "data/<ns>/worldgen/biome/"),
                                   ("java_code", "compiled classes", 900),
                                   ("model", "model has no parent", 5)]),
                  "rank": 32, "title": "Quark", "profile": content},
        "botania": {**_record(20.0, [("unowned", "N file(s) no converter claims yet", 10,
                                      "data/<ns>/worldgen/configured_feature/"),
                                     ("java_code", "compiled classes", 500)]),
                    "rank": 38, "title": "Botania", "profile": content},
        "clumps": {**_record(0.0, [("java_code", "compiled classes", 15)]), "rank": 44, "title": "Clumps",
                   "profile": {"class": "performance/mixin-only", "evidence": ["2 mixin(s)"]}},
        "lithium": {"status": "ingest_error", "detail": "lithium.jar has no assets/<namespace> tree",
                    "rank": 9, "title": "Lithium",
                    "profile": {"class": "performance/mixin-only", "evidence": ["240 mixin(s)"]}},
        "chisel": {"status": "unfetchable", "detail": "needs a key", "rank": 50, "title": "Chisel"},
        "bad": {**_record(10.0, [("java_code", "compiled classes", 1)], errors=3), "rank": 49,
                "profile": content},
    })]


def test_board_rolls_reason_classes_up_across_mods():
    b = gauntlet.board(_shards())
    roll = {r["reason_class"]: r for r in b["rollup"]}
    assert roll["java_code"]["mods"] == 4 and roll["java_code"]["explained"] is True
    assert b["rollup"][0]["reason_class"] == "java_code"
    # unowned files are split by directory, three levels deep
    assert roll["unowned [data/<ns>/worldgen/]"]["mods"] == 2
    assert roll["unowned [data/<ns>/worldgen/]"]["files"] == 50
    assert roll["unowned [data/<ns>/worldgen/]"]["mod_names"] == ["quark", "botania"]
    assert roll["model"]["explained"] is False
    # the ingest failure and the unfetchable jar are statuses, not reason classes
    assert "conversion" not in roll and "fetch" not in roll


def test_board_mods_carry_class_status_and_the_done_flag():
    b = gauntlet.board(_shards())
    by = {m["name"]: m for m in b["mods"]}
    assert [m["name"] for m in b["mods"]] == ["lithium", "quark", "botania", "clumps", "bad", "chisel"]
    assert by["clumps"]["done"] is True  # validator clean, only explained residue
    assert by["quark"]["done"] is False and "unowned" in by["quark"]["done_why"]
    assert by["bad"]["done"] is False and by["bad"]["done_why"] == "3 validator error(s)"
    assert by["lithium"]["done"] is False and by["lithium"]["class"] == "performance/mixin-only"
    assert by["chisel"]["class"] == "unfetched"
    assert b["classes"] == {"content": 3, "performance/mixin-only": 2, "unfetched": 1}
    assert b["done"] == 1 and b["mean_coverage"] == 15.0
    assert list(by["quark"]["reason_classes"]) == ["java_code", "unowned [data/<ns>/worldgen/]", "model"]


def test_board_trend_and_baseline():
    first = gauntlet.board(_shards())
    base = gauntlet.baseline_of(first)
    assert base["kind"] == "gauntlet-baseline" and base["mods"]["quark"]["coverage"] == 30.0
    shards = _shards()
    shards[0]["mods"]["quark"]["coverage"] = 35.5
    del shards[0]["mods"]["quark"]["reasons"]["model: model has no parent"]
    again = gauntlet.board(shards, previous=first, baseline=base)
    by = {m["name"]: m for m in again["mods"]}
    assert by["quark"]["coverage_vs_baseline"] == 5.5
    roll = {r["reason_class"]: r for r in again["rollup"]}
    assert roll["java_code"]["trend"] == {"mods": 0, "files": 0}
    assert "model" not in roll


def test_markdown_has_the_rollup_mods_and_evidence():
    md = gauntlet.render_markdown(gauntlet.board(_shards()))
    assert md.startswith("# Top-50 gauntlet board")
    assert "## Cross-mod reason classes (#277 rule 4)" in md
    assert "| 1 | java_code | 4 |" in md
    assert "1. `unowned [data/<ns>/worldgen/]`: 2 mods, 50 files" in md  # next work skips explained kinds
    assert "| 50 | Chisel | unfetched |" in md and "unfetchable: needs a key" in md
    assert "| 44 | Clumps | performance/mixin-only |" in md and "| clean |  | yes |" in md
    assert "## Class evidence" in md and "## Top normalized reasons" in md


def test_cli_board_banks_a_baseline(tmp_path, capsys):
    shard = tmp_path / "s.json"
    shard.write_text(json.dumps(_shards()[0]))
    out_json, out_md, bank = tmp_path / "b.json", tmp_path / "docs" / "g.md", tmp_path / "base.json"
    assert main(["gauntlet", "board", str(shard), "--manifest", str(tmp_path / "none.toml"),
                 "--baseline", str(tmp_path / "missing.json"),
                 "--json", str(out_json), "--md", str(out_md), "--bank", str(bank)]) == 0
    assert "no gauntlet baseline" in capsys.readouterr().out
    assert json.loads(out_json.read_text())["kind"] == "gauntlet-board"
    assert out_md.read_text().startswith("# Top-50 gauntlet board")
    assert json.loads(bank.read_text())["mods"]["clumps"]["done"] is True


def test_cli_run_with_a_bad_shard_is_a_usage_error():
    assert main(["gauntlet", "run", "--shard", "0/2"]) == 2


# --- the committed manifest and baseline -----------------------------------------------

def test_the_committed_gauntlet_pins_all_50_in_order():
    mods = corpus.load(ROOT / "fixtures" / "real" / "gauntlet.toml")
    assert [m.rank for m in mods] == list(range(1, 51))
    assert [m.name for m in mods] == [x.name for x in gauntlet.THE_50]
    for m in mods:
        assert m.license and m.host in ("modrinth", "curseforge"), m.name
        if m.unfetchable:
            continue
        assert len(m.sha512) == 128 and m.version_id and m.rule, m.name
        if m.host == "modrinth":
            assert m.url.startswith("https://cdn.modrinth.com/data/") and f"/versions/{m.version_id}/" in m.url
        else:
            assert m.url.startswith("https://mediafilez.forgecdn.net/files/") and m.redistribution
        if not m.rule.startswith("off-rule"):
            assert m.minecraft in gauntlet.RULE_VERSIONS and m.loader in gauntlet.LOADER_PREFERENCE[m.minecraft]
    assert len({m.sha512 for m in mods if m.sha512}) == len([m for m in mods if m.sha512])
    assert {m.name for m in mods if m.listed_lib} == {x.name for x in gauntlet.THE_50 if x.listed_lib}


def test_the_banked_baseline_matches_the_manifest():
    path = ROOT / "fixtures" / "real" / "gauntlet-baseline.json"
    if not path.is_file():
        pytest.skip("no gauntlet baseline banked yet")
    base = json.loads(path.read_text())
    names = {m.name for m in corpus.load(ROOT / "fixtures" / "real" / "gauntlet.toml")}
    assert base["kind"] == "gauntlet-baseline" and set(base["mods"]) == names
