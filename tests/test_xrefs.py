"""Cross-pack references: the breakage that survives per-pack validation."""
from __future__ import annotations

import json

from portkit.pipeline import convert
from portkit.validate import check_cross_pack, validate_tree
from portkit.validate.report import ValidationReport

FIXTURES = __import__("pathlib").Path(__file__).resolve().parents[1] / "fixtures"


def _convert(tmp_path, name):
    out = tmp_path / "out"
    convert(FIXTURES / name / "input", out)
    return out


def test_deleting_a_texture_entry_breaks_the_pack(tmp_path):
    """The done-when for #13, spelled out."""
    tree = _convert(tmp_path, "block_defs_mod")
    assert validate_tree(tree).ok

    index_path = tree / "resource_pack" / "textures" / "terrain_texture.json"
    index = json.loads(index_path.read_text())
    dropped = sorted(index["texture_data"])[0]
    del index["texture_data"][dropped]
    index_path.write_text(json.dumps(index, indent=2))

    report = validate_tree(tree)
    assert not report.ok
    dangling = [f for f in report.errors if f.rule == "xref.texture"]
    assert dangling, report.to_dict()
    assert all(dropped in f.message for f in dangling)
    assert all(f.path.startswith("behavior_pack/blocks/") for f in dangling)


def test_a_missing_item_icon_is_an_error(tmp_path):
    tree = _convert(tmp_path, "item_defs_mod")
    assert validate_tree(tree).ok

    index_path = tree / "resource_pack" / "textures" / "item_texture.json"
    index = json.loads(index_path.read_text())
    index["texture_data"] = {}
    index_path.write_text(json.dumps(index, indent=2))

    errors = [f for f in validate_tree(tree).errors if f.rule == "xref.texture"]
    assert errors
    assert all("item_texture.json" in f.message for f in errors)


def test_an_undeclared_recipe_result_is_a_warning_not_an_error(tmp_path):
    """A refused definition is already on the residue list: don't fail twice."""
    tree = _convert(tmp_path, "recipes_mod")
    report = validate_tree(tree)
    assert report.ok
    warnings = [f for f in report.findings if f.rule == "xref.item"]
    assert warnings
    assert all(f.severity == "warning" for f in warnings)
    assert any("residue report" in f.message for f in warnings)


def test_an_undeclared_loot_drop_is_reported(tmp_path):
    tree = _convert(tmp_path, "loot_mod")
    findings = [f for f in validate_tree(tree).findings if f.rule == "xref.item"]
    assert any("drop nothing" in f.message for f in findings)
    assert all(f.path.startswith("behavior_pack/loot_tables/") for f in findings)


def test_a_block_is_also_its_own_item(tmp_path):
    """examplemod:steel_block in a recipe resolves to the block definition."""
    tree = _convert(tmp_path, "block_defs_mod")
    index = check_cross_pack(ValidationReport(), tree)
    assert index.blocks
    assert set(index.blocks) <= index.obtainable


def test_a_lang_name_for_nothing_is_a_warning(tmp_path):
    tree = _convert(tmp_path, "block_defs_mod")
    lang = tree / "resource_pack" / "texts" / "en_US.lang"
    lang.write_text(lang.read_text() + "\ntile.examplemod:ghost.name=Ghost\n")

    report = validate_tree(tree)
    assert report.ok
    orphans = [f for f in report.findings if f.rule == "xref.lang_orphan"]
    assert len(orphans) == 1
    assert "examplemod:ghost" in orphans[0].message


def test_vanilla_references_are_taken_on_faith(tmp_path):
    tree = _convert(tmp_path, "simple_block_mod")
    findings = [f for f in validate_tree(tree).findings if f.rule == "xref.item"]
    assert not any("minecraft:" in f.message for f in findings)


def test_a_tree_with_one_pack_still_checks_what_it_can(tmp_path):
    tree = _convert(tmp_path, "loot_mod")
    __import__("shutil").rmtree(tree / "resource_pack")
    report = validate_tree(tree)
    assert [f for f in report.findings if f.rule == "xref.texture"] == []
    assert [f for f in report.findings if f.rule == "xref.item"]
