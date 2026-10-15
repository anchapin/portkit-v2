"""Building the random-sample manifest (#234) from Modrinth API data (offline)."""
from __future__ import annotations

import io
import json
import tomllib
import urllib.parse

import pytest

from portkit import corpus, sample


def _hit(slug, rank_downloads, cats, server="required", licence="MIT"):
    return {"project_id": f"id_{slug}", "slug": slug, "downloads": rank_downloads,
            "categories": cats, "server_side": server, "license": licence}


SEARCH = [
    _hit("fabric-api", 900, ["fabric", "library"], server="optional", licence="Apache-2.0"),
    _hit("sodium", 800, ["fabric", "optimization"], server="unsupported"),
    _hit("farmers-delight", 700, ["decoration", "food", "neoforge"]),
    _hit("waystones", 600, ["adventure", "fabric", "magic"], licence="LicenseRef-All-Rights-Reserved"),
    _hit("geckolib", 500, ["fabric", "library", "mobs"]),
    _hit("betaonly", 400, ["equipment", "fabric"]),
    _hit("datapack-only", 300, ["worldgen"]),
]


def _file(name, sha="a" * 128):
    return {"primary": True, "filename": name, "url": f"https://cdn.modrinth.com/data/x/versions/v/{name}",
            "hashes": {"sha512": sha, "sha1": "b" * 40}}


VERSIONS = {
    "id_farmers-delight": [
        {"id": "beta1", "version_number": "1.4-beta", "version_type": "beta", "loaders": ["neoforge"],
         "game_versions": ["1.21.1"], "files": [_file("fd-beta.jar", "1" * 128)]},
        {"id": "XTVZDOol", "version_number": "1.21.1-1.3.4", "version_type": "release",
         "loaders": ["neoforge"], "game_versions": ["1.21", "1.21.1"], "files": [_file("fd.jar", "2" * 128)]},
    ],
    "id_waystones": [
        {"id": "w1", "version_number": "21.1.46", "version_type": "release", "loaders": ["fabric"],
         "game_versions": ["1.21.1"], "files": [_file("waystones.jar", "3" * 128)]},
    ],
    "id_betaonly": [
        {"id": "b2", "version_number": "0.2", "version_type": "beta", "loaders": ["fabric"],
         "game_versions": ["1.21"], "files": [_file("b.jar", "4" * 128)]},
    ],
    "id_datapack-only": [
        {"id": "d1", "version_number": "1", "version_type": "release", "loaders": ["datapack"],
         "game_versions": ["1.21"], "files": [_file("d.zip", "5" * 128)]},
    ],
}


def _opener(calls):
    def opener(request, timeout):
        url = request.full_url
        calls.append(url)
        parsed = urllib.parse.urlparse(url)
        if parsed.path.endswith("/search"):
            q = urllib.parse.parse_qs(parsed.query)
            off, lim = int(q["offset"][0]), int(q["limit"][0])
            body = {"hits": SEARCH[off:off + lim]}
        else:
            pid = parsed.path.split("/")[-2]
            body = VERSIONS[pid]
        return io.BytesIO(json.dumps(body).encode())
    return opener


def test_content_filter():
    assert not sample.is_content(SEARCH[0])  # library
    assert not sample.is_content(SEARCH[1])  # client-only
    assert sample.is_content(SEARCH[2])
    assert not sample.is_content(SEARCH[4])  # a library, even with a content category


def test_licence_policies():
    assert sample.licence_allowed("LicenseRef-All-Rights-Reserved", "all")
    assert not sample.licence_allowed("LicenseRef-All-Rights-Reserved", "open")
    assert sample.licence_allowed("MIT", "open")
    assert not sample.licence_allowed("", "open")
    with pytest.raises(ValueError):
        sample.licence_allowed("MIT", "some")


def test_build_pins_releases_from_api_data_and_skips_non_jars():
    calls = []
    entries, skipped = sample.build(10, "all", opener=_opener(calls), today="2026-10-15")
    names = [e["name"] for e in entries]
    assert names == ["farmers_delight", "waystones", "betaonly"]
    fd = entries[0]
    assert (fd["version_id"], fd["sha512"], fd["minecraft"], fd["loader"]) == \
        ("XTVZDOol", "2" * 128, "1.21.1", "neoforge")  # the release, not the newer beta
    assert entries[2]["version_id"] == "b2"  # beta-only project: its newest beta
    assert "download rank 3 on Modrinth (700 downloads, 2026-10-15)" in fd["notes"]
    assert skipped == ["datapack-only: no version with a Java-loader .jar"]
    assert "project_type%3Amod" in calls[0] and "index=downloads" in calls[0]


def test_open_policy_drops_licenceref():
    entries, _ = sample.build(10, "open", opener=_opener([]), today="2026-10-15")
    assert "waystones" not in [e["name"] for e in entries]


def test_rendered_manifest_round_trips_through_corpus_load(tmp_path):
    entries, _ = sample.build(2, "all", opener=_opener([]), today="2026-10-15")
    text = sample.render(entries, 2, "all", "2026-10-15")
    assert tomllib.loads(text)["mod"][0]["project"] == "farmers-delight"
    path = tmp_path / "mods.toml"
    path.write_text(text)
    mods = corpus.load(path)
    assert [m.name for m in mods] == ["farmers_delight", "waystones"]
    assert mods[1].license == "LicenseRef-All-Rights-Reserved"
