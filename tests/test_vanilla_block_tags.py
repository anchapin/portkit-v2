"""#298: vanilla's own block tags say what vanilla's tool tags nest."""
import io
import json
from pathlib import Path

import pytest

from portkit import cli, data
from portkit.data import vanilla_block_tags

# Vanilla's own block tags of one game version, as the reference gives them:
# mineable/axe holds #minecraft:logs, and logs holds #minecraft:logs_that_burn.
VANILLA = {
    "minecraft:mineable/axe": ["#minecraft:logs", "#minecraft:planks"],
    "minecraft:mineable/pickaxe": ["minecraft:stone_ore"],
    "minecraft:logs": ["minecraft:oak_log", "#minecraft:logs_that_burn"],
    "minecraft:logs_that_burn": ["minecraft:oak_log"],
    "minecraft:planks": ["minecraft:oak_planks"],
    "minecraft:needs_iron_tool": ["minecraft:iron_ore"],
}


@pytest.fixture
def vanilla(tmp_path, monkeypatch):
    """The cached vanilla block tags of one version, read from the override file."""
    path = tmp_path / "vanilla-block-tags.json"
    path.write_text(json.dumps({"tags": VANILLA}))
    monkeypatch.setenv("PORTKIT_VANILLA_BLOCK_TAGS", str(path))
    return path


def _opener(payload, calls=None, url="https://example.invalid/x"):
    def opener(request, timeout):
        if calls is not None:
            calls.append(request.full_url)
        return io.BytesIO(payload)
    return opener


def _offline_fetches(tmp_path, monkeypatch):
    """Every reference fetch returns a file, so the CLI runs without a network."""
    from portkit.data import (forge_versions, java_items, java_sounds, mappings, models,
                              recipes, tags, vanilla_block_collision, vanilla_block_tools,
                              vanilla_blocks, vanilla_items, vanilla_textures)

    def fake(*args, **kwargs):
        return (tmp_path / "fake.json", False)

    for module in (forge_versions, models, vanilla_textures, vanilla_items, java_items,
                   vanilla_blocks, vanilla_block_tools, vanilla_block_collision):
        monkeypatch.setattr(module, "fetch", fake)
    for module in (recipes, java_sounds, mappings, tags, vanilla_block_tags):
        monkeypatch.setattr(module, "fetch", lambda s, cache=None, **kwargs:
                            (tmp_path / "fake.json", False))
    monkeypatch.setattr(data, "fetch_sounds", fake)


# -- the pinned sets ----------------------------------------------------------
def test_the_sets_are_the_pinned_vanilla_game_versions():
    assert {s.minecraft for s in vanilla_block_tags.SETS} == {
        "1.16.5", "1.19.2", "1.20.1", "1.21.1", "1.21.8", "26.1"}
    for tag_set in vanilla_block_tags.SETS:
        assert tag_set.commit in tag_set.url
        assert tag_set.url.startswith("https://raw.githubusercontent.com/misode/mcmeta/")
        assert "data/minecraft/tags" in tag_set.tree_url or tag_set.tree_url.endswith("?recursive=1")


def test_nothing_of_the_vanilla_tags_is_vendored():
    folder = Path(data.__file__).parent
    assert not [p for p in folder.iterdir()
                if p.suffix in (".json", ".txt", ".gz") and "block_tag" in p.name]
    for path in folder.rglob("*"):
        if path.is_file() and path.suffix in (".json", ".txt"):
            assert "mineable/axe" not in path.read_text(encoding="utf-8", errors="ignore")


def test_the_nearest_version_is_chosen():
    assert vanilla_block_tags.select("1.20.1").minecraft == "1.20.1"
    assert vanilla_block_tags.select("1.20.4").minecraft == "1.20.1"
    assert vanilla_block_tags.select("1.21.2").minecraft == "1.21.1"
    assert vanilla_block_tags.select(None) is None
    assert vanilla_block_tags.select("nonsense") is None


def test_derive_keeps_the_values_as_written():
    summary = json.dumps({
        "mineable/axe": {"values": ["#minecraft:logs", {"id": "minecraft:oak_log", "required": False}]},
        "logs": {"values": ["minecraft:oak_log"]},
    }).encode()
    derived = json.loads(vanilla_block_tags.derive(vanilla_block_tags.SETS[0], summary))
    assert derived["tags"]["minecraft:mineable/axe"] == [
        "#minecraft:logs", {"id": "minecraft:oak_log", "required": False}]
    assert derived["tags"]["minecraft:logs"] == ["minecraft:oak_log"]


def test_derive_reads_vanillas_own_tag_files():
    files = {
        "data/minecraft/tags/blocks/mineable/axe.json": json.dumps(
            {"values": ["#minecraft:logs"]}).encode(),
        "data/minecraft/tags/blocks/logs.json": json.dumps(
            {"values": ["minecraft:oak_log"]}).encode(),
        "data/minecraft/tags/items/planks.json": json.dumps(
            {"values": ["minecraft:oak_planks"]}).encode(),
    }
    derived = json.loads(vanilla_block_tags.derive_raw(vanilla_block_tags.SETS[0], files, "x"))
    assert derived["tags"] == {"minecraft:mineable/axe": ["#minecraft:logs"],
                                "minecraft:logs": ["minecraft:oak_log"]}


def test_fetch_caches_and_is_then_read(tmp_path, monkeypatch):
    monkeypatch.delenv("PORTKIT_VANILLA_BLOCK_TAGS", raising=False)
    monkeypatch.setenv("PORTKIT_REFERENCE_CACHE", str(tmp_path))
    tag_set = vanilla_block_tags.SETS[0]
    summary = json.dumps({"logs": {"values": ["minecraft:oak_log"]}}).encode()
    calls = []
    path, downloaded = vanilla_block_tags.fetch(tag_set, opener=_opener(summary, calls))
    assert downloaded and path.parent == tmp_path
    assert calls == [tag_set.url]
    assert vanilla_block_tags.cached(tag_set) == path
    assert vanilla_block_tags.fetch(tag_set, opener=_opener(summary, calls)) == (path, False)
    assert len(calls) == 1
    assert vanilla_block_tags.vanilla_tags(tag_set.minecraft) == {
        "minecraft:logs": ["minecraft:oak_log"]}


def test_a_download_failure_is_named(tmp_path, monkeypatch):
    monkeypatch.delenv("PORTKIT_VANILLA_BLOCK_TAGS", raising=False)
    monkeypatch.setenv("PORTKIT_REFERENCE_CACHE", str(tmp_path))

    def opener(request, timeout):
        raise OSError("no network")

    with pytest.raises(data.ReferenceDataError, match="download failed"):
        vanilla_block_tags.fetch(vanilla_block_tags.SETS[0], opener=opener)
    assert vanilla_block_tags.vanilla_tags("1.20.1") is None


def test_the_cli_lists_and_fetches_the_vanilla_block_tags(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PORTKIT_REFERENCE_CACHE", str(tmp_path))
    monkeypatch.delenv("PORTKIT_VANILLA_BLOCK_TAGS", raising=False)
    assert cli.main(["reference", "list"]) == 0
    out = capsys.readouterr().out
    assert "vanilla-block-tags-1.20.1" in out and "missing" in out
    _offline_fetches(tmp_path, monkeypatch)
    assert cli.main(["reference", "fetch"]) == 0
    assert "vanilla-block-tags-1.20.1" in capsys.readouterr().out
