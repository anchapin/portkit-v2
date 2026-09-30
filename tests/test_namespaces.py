"""Mods that ship more than one namespace."""
import json

from portkit.pipeline import convert, merge_namespaces
from portkit.model import ConversionResult


def result(files, consumed=()):
    return ConversionResult(files=dict(files), consumed=set(consumed))


def test_both_namespaces_convert(tmp_path, fixtures_dir):
    out = convert(fixtures_dir / "two_namespace_mod" / "input", tmp_path / "out")
    assert out.unhandled == [], [u.reason for u in out.unhandled]
    assert out.report.ok, out.report.to_dict()
    assert set(out.namespaces) == {"examplemod", "compatmod"}
    assert all(count > 0 for count in out.namespaces.values())


def test_no_identifier_leaks_between_namespaces(tmp_path, fixtures_dir):
    out = convert(fixtures_dir / "two_namespace_mod" / "input", tmp_path / "out")
    index = json.loads(
        (out.tree / "resource_pack" / "textures" / "terrain_texture.json").read_text()
    )["texture_data"]
    assert set(index) == {"examplemod:steel_block", "compatmod:brass_block"}
    for key, entry in index.items():
        ns = key.split(":")[0]
        other = "compatmod" if ns == "examplemod" else "examplemod"
        assert other not in json.dumps(entry)


def test_the_primary_namespace_is_the_first_one(tmp_path, fixtures_dir):
    out = convert(fixtures_dir / "two_namespace_mod" / "input", tmp_path / "out")
    assert out.namespace == "examplemod"
    assert list(out.namespaces)[0] == "examplemod"


def test_naming_a_namespace_still_converts_only_that_one(tmp_path, fixtures_dir):
    out = convert(
        fixtures_dir / "two_namespace_mod" / "input",
        tmp_path / "out",
        namespace="compatmod",
    )
    assert list(out.namespaces) == ["compatmod"]
    index = json.loads(
        (out.tree / "resource_pack" / "textures" / "terrain_texture.json").read_text()
    )["texture_data"]
    assert set(index) == {"compatmod:brass_block"}


def test_texture_indexes_are_merged_not_overwritten():
    merged = merge_namespaces({
        "a": result({"textures/terrain_texture.json": {
            "resource_pack_name": "x", "texture_data": {"a:one": {"textures": "t/one"}}}}),
        "b": result({"textures/terrain_texture.json": {
            "resource_pack_name": "x", "texture_data": {"b:two": {"textures": "t/two"}}}}),
    })
    data = merged.files["textures/terrain_texture.json"]["texture_data"]
    assert set(data) == {"a:one", "b:two"}
    assert merged.unhandled == []


def test_locale_files_are_merged_line_wise():
    merged = merge_namespaces({
        "a": result({"texts/en_US.lang": "tile.a:one.name=One\n",
                     "texts/languages.json": ["en_US"]}),
        "b": result({"texts/en_US.lang": "tile.b:two.name=Two\n",
                     "texts/languages.json": ["en_US", "fr_FR"]}),
    })
    assert merged.files["texts/en_US.lang"] == "tile.a:one.name=One\ntile.b:two.name=Two\n"
    assert merged.files["texts/languages.json"] == ["en_US", "fr_FR"]
    assert merged.unhandled == []


def test_a_real_collision_is_reported_rather_than_silently_kept():
    merged = merge_namespaces({
        "a": result({"recipes/thing.json": {"minecraft:recipe_shaped": {"id": "a"}}}),
        "b": result({"recipes/thing.json": {"minecraft:recipe_shaped": {"id": "b"}}}),
    })
    assert merged.files["recipes/thing.json"]["minecraft:recipe_shaped"]["id"] == "a"
    (entry,) = merged.unhandled
    assert entry.kind == "namespace_collision"
    assert "recipes/thing.json" in entry.reason


def test_identical_output_from_two_namespaces_is_not_a_collision():
    same = {"textures/blocks/x.png": b"png"}
    merged = merge_namespaces({"a": result(same), "b": result(same)})
    assert merged.unhandled == []


def test_summary_reports_per_namespace_counts(tmp_path, fixtures_dir):
    out = convert(fixtures_dir / "two_namespace_mod" / "input", tmp_path / "out")
    summary = out.summary()
    assert set(summary["namespaces"]) == {"examplemod", "compatmod"}
