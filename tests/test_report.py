"""The report a modder reads when a block is missing."""

import json
from pathlib import Path

from portkit.pipeline import convert
from portkit.report import Residue, render

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _convert(name: str, tmp_path: Path):
    return convert(FIXTURES / name / "input", tmp_path / "out", "examplemod")


def test_a_clean_mod_reports_full_coverage_and_no_gaps(tmp_path):
    result = _convert("simple_block_mod", tmp_path)
    text = render(result.tree)
    assert "100.0%" in text
    assert "Everything in the source was converted." in text
    assert "passed" in text


def test_every_residue_item_names_its_source_file_and_reason(tmp_path):
    result = _convert("loot_mod", tmp_path)
    text = render(result.tree)
    assert result.unhandled, "fixture is supposed to leave residue"
    for item in result.unhandled:
        assert item.source in text
        assert item.reason in text


def test_the_refused_rotation_shows_up_with_its_reason(tmp_path):
    result = _convert("rotated_model_mod", tmp_path)
    text = render(result.tree)
    assert "## What did not, and why" in text
    assert any(item.source in text for item in result.unhandled)


def test_coverage_in_the_report_matches_what_the_pipeline_counted(tmp_path):
    result = _convert("block_defs_mod", tmp_path)
    text = render(result.tree)
    assert f"{result.coverage:.1f}%" in text


def test_converted_files_are_grouped_by_content_type(tmp_path):
    result = _convert("recipes_mod", tmp_path)
    text = render(result.tree)
    assert "| Content | Files |" in text
    assert "recipes" in text


def test_the_mod_name_comes_from_the_manifest_not_the_directory(tmp_path):
    result = _convert("simple_block_mod", tmp_path)
    text = render(result.tree)
    assert text.startswith("# Conversion report: ")
    assert "(behavior)" not in text.splitlines()[0]


def test_findings_are_grouped_with_errors_before_warnings(tmp_path):
    result = _convert("block_defs_mod", tmp_path)
    tree = result.tree
    # Two blocks, one name: an error the validator will find.
    blocks = tree / "behavior_pack/blocks"
    existing = sorted(blocks.glob("*.json"))[0]
    (blocks / "collide.json").write_text(existing.read_text())
    text = render(tree)
    assert "### Errors" in text
    assert "identifier_collision" in text
    if "### Warnings" in text:
        assert text.index("### Errors") < text.index("### Warnings")


def test_residue_survives_a_missing_or_unreadable_manifest_of_its_own(tmp_path):
    (tmp_path / "behavior_pack/blocks").mkdir(parents=True)
    assert Residue.load(tmp_path) == []
    (tmp_path / "unhandled.json").write_text("{not json")
    assert Residue.load(tmp_path) == []


def test_residue_counts_files_not_entries(tmp_path):
    (tmp_path / "unhandled.json").write_text(json.dumps([
        {"kind": "textures", "source": "assets/x", "reason": "nope", "count": 7}
    ]))
    (tmp_path / "behavior_pack").mkdir()
    text = render(tmp_path)
    assert "7 file(s) in 1 item(s)" in text
    assert "(7 files)" in text


def test_an_empty_tree_says_so_instead_of_dividing_by_zero(tmp_path):
    (tmp_path / "behavior_pack").mkdir()
    text = render(tmp_path)
    assert "100.0%" in text
    assert "Nothing. The tree holds no pack files." in text
