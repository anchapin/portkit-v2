"""The random-sample manifest and the gap leaderboard's ranking (#234).

Covers the slice the issue asks for: the sample manifest (pinned url + hash +
licence + source page), the fetch-and-verify path (sha256 pins are checked
when a manifest carries one), and the leaderboard's ranking fields
(mods blocked x kid relevance) with the trend diff.
"""
from __future__ import annotations

import hashlib
import io
import json
import tomllib
from pathlib import Path

import pytest

from portkit import corpus, gaps, sample

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_MANIFEST = ROOT / "fixtures" / "sample" / "mods.toml"

PAYLOAD = b"PK\x05\x06" + b"\x00" * 18  # an empty zip, as far as anyone checks
SHA512 = hashlib.sha512(PAYLOAD).hexdigest()
SHA256 = hashlib.sha256(PAYLOAD).hexdigest()


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _opener(body, calls=None):
    def opener(request, timeout):
        if calls is not None:
            calls.append(request.full_url)
        return _Response(body)
    return opener


# --- the sample manifest ------------------------------------------------------

def test_the_sample_manifest_pins_url_hash_licence_and_source_page():
    mods = corpus.load(SAMPLE_MANIFEST)
    assert len(mods) >= 25
    for mod in mods:
        assert mod.url.startswith("https://cdn.modrinth.com/data/"), mod.name
        assert f"/versions/{mod.version_id}/" in mod.url, mod.name
        assert len(mod.sha512) == 128 and int(mod.sha512, 16) >= 0, mod.name
        assert mod.license, mod.name  # the licence is recorded per entry
        assert mod.source == f"https://modrinth.com/mod/{mod.project}", mod.name
        assert "download rank" in mod.notes, mod.name  # where the entry came from
    assert len({m.sha512 for m in mods}) == len(mods)  # no two entries are the same jar
    assert len({m.name for m in mods}) == len(mods)
    # jars are cached, never committed
    assert not list((ROOT / "fixtures" / "sample").glob("*.jar"))


def test_the_sample_manifest_is_the_corpus_format_and_pins_hashes():
    data = tomllib.loads(SAMPLE_MANIFEST.read_text())
    assert len(data["mod"]) == 50
    for entry in data["mod"]:
        assert set(entry) >= {"name", "project", "version_id", "url", "sha512", "license", "source"}
        assert entry["url"].startswith("https://")
        assert entry["source"].startswith("https://modrinth.com/mod/")


def test_the_builder_records_the_source_page_of_every_entry():
    hit = {"project_id": "id_x", "slug": "x-mod", "downloads": 10,
           "categories": ["decoration", "fabric"], "server_side": "required", "license": "MIT"}
    version = {"id": "v1", "version_number": "1.0", "version_type": "release", "loaders": ["fabric"],
               "game_versions": ["1.21.1"],
               "files": [{"primary": True, "filename": "x.jar", "hashes": {"sha512": "a" * 128},
                          "url": "https://cdn.modrinth.com/data/x/versions/v1/x.jar"}]}

    def opener(request, timeout):
        if "/search" in request.full_url:
            return _Response(json.dumps({"hits": [hit]}).encode())
        return _Response(json.dumps([version]).encode())

    entries, skipped = sample.build(1, opener=opener, today="2026-10-15")
    assert not skipped
    assert entries[0]["source"] == "https://modrinth.com/mod/x-mod"
    assert entries[0]["license"] == "MIT"
    assert entries[0]["sha512"] == "a" * 128
    # and the rendered manifest carries it
    text = sample.render(entries, 1, "all", "2026-10-15")
    assert 'source = "https://modrinth.com/mod/x-mod"' in text


# --- fetch and verify ---------------------------------------------------------

def _mod(**over):
    entry = dict(name="m", project="p", version_id="v", url="https://example.invalid/m.jar",
                 sha512=SHA512, license="MIT")
    entry.update(over)
    return corpus.Mod(**entry)


def test_fetch_verifies_a_sha256_pin_and_refuses_a_mismatch(tmp_path):
    calls = []
    mod = _mod(sha256=SHA256)
    path, downloaded = corpus.fetch(mod, tmp_path, opener=_opener(PAYLOAD, calls))
    assert downloaded and path.is_file() and calls == [mod.url]
    assert corpus.cached(mod, tmp_path) == path

    bad = _mod(sha256="0" * 64)
    with pytest.raises(corpus.CorpusError, match="sha256 mismatch"):
        corpus.fetch(bad, tmp_path, opener=_opener(PAYLOAD))
    assert not list(tmp_path.glob("*.part"))  # the bad download is not kept


def test_a_cached_jar_with_the_wrong_sha256_is_not_cached(tmp_path):
    mod = _mod(sha256="0" * 64)
    mod.path(tmp_path).write_bytes(PAYLOAD)  # in the cache, but not the pinned file
    assert corpus.cached(mod, tmp_path) is None


def test_the_manifest_rejects_a_relevance_score_without_its_source(tmp_path):
    manifest = tmp_path / "mods.toml"
    manifest.write_text(
        '[[mod]]\nname = "a"\nproject = "a"\nversion_id = "v"\n'
        'url = "https://example.invalid/a.jar"\nsha512 = "%s"\nlicense = "MIT"\n'
        'relevance = 0.5\n' % SHA512
    )
    with pytest.raises(corpus.CorpusError, match="relevance_source"):
        corpus.load(manifest)
    manifest.write_text(
        '[[mod]]\nname = "a"\nproject = "a"\nversion_id = "v"\n'
        'url = "https://example.invalid/a.jar"\nsha512 = "%s"\nlicense = "MIT"\n'
        'relevance = 0.5\nrelevance_source = "https://example.invalid/kids"\n' % SHA512
    )
    mods = corpus.load(manifest)
    assert mods[0].relevance == 0.5 and mods[0].relevance_source


# --- the leaderboard's ranking ------------------------------------------------

def _record(coverage, reasons, relevance=None):
    record = {"status": "ok", "namespace": "x", "files": 10, "residue": sum(f for _, _, f in reasons),
              "coverage": coverage, "valid": True, "errors": 0, "seconds": 1.0,
              "reasons": {f"{k}: {r}": {"kind": k, "reason": r, "entries": 1, "files": f,
                                        "examples": [{"source": "s", "reason": r}]}
                          for k, r, f in reasons}}
    if relevance is not None:
        record["relevance"] = relevance
    return record


def _shard(index, mods):
    return {"schema": 1, "kind": "gap-shard", "manifest": "fixtures/sample/mods.toml",
            "shard": index, "generated": "t", "mods": mods}


def test_the_ranking_weighs_mods_blocked_by_kid_relevance():
    shards = [_shard("1/1", {
        "a": _record(50.0, [("block", "model has no parent and no elements", 1)], relevance=1.0),
        "b": _record(50.0, [("block", "model has no parent and no elements", 9)], relevance=1.0),
        "c": _record(50.0, [("block", "model has no parent and no elements", 9)], relevance=1.0),
        "d": _record(50.0, [("loot", "table has N pools", 100)], relevance=0.4),
    })]
    board = gaps.leaderboard(shards)
    reasons = {r["key"]: r for r in board["reasons"]}
    block = reasons["block: model has no parent and no elements"]
    loot = reasons["loot: table has N pools"]
    # 3 mods blocked beat 1 mod blocked, even with 100 files behind it
    assert block["rank"] == 1 and loot["rank"] == 2
    assert (block["mods"], block["relevance"], block["score"]) == (3, 1.0, 3.0)
    assert (loot["mods"], loot["relevance"], loot["score"]) == (1, 0.4, 0.4)
    assert board["ranking"]["sort"] == ["score", "mods", "files", "key"]
    assert "score" in board["ranking"]["fields"]


def test_the_ranking_fields_are_explicit_in_the_json_and_the_markdown():
    board = gaps.leaderboard([_shard("1/1", {
        "a": _record(50.0, [("block", "model has no parent and no elements", 3)], relevance=0.5),
    })])
    reason = board["reasons"][0]
    assert set(reason) >= {"rank", "key", "kind", "reason", "mods", "files", "entries",
                            "relevance", "score", "mod_names"}
    assert board["mods"][0]["relevance"] == 0.5
    md = gaps.render_markdown(board)
    assert "| score |" in md
    assert "| 1 | 1 | 3 | 1 | block | model has no parent and no elements | a | 0.5 |" in md


def test_the_trend_diff_survives_the_new_ranking_fields():
    previous = gaps.leaderboard([_shard("1/1", {
        "a": _record(50.0, [("block", "model has no parent and no elements", 3)], relevance=0.5),
    })])
    now = gaps.leaderboard([_shard("1/1", {
        "a": _record(50.0, [("block", "model has no parent and no elements", 5)], relevance=0.5),
        "b": _record(50.0, [("loot", "table has N pools", 1)]),
    })], previous)
    by_key = {r["key"]: r for r in now["reasons"]}
    assert by_key["block: model has no parent and no elements"]["trend"]["files"] == 2
    assert by_key["loot: table has N pools"]["trend"] == {"new": True}
    assert now["previous"]["gone"] == []
