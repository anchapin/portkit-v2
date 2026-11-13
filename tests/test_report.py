"""The report a modder reads when a block is missing."""

import json
from pathlib import Path

from portkit.agent.residue import SKIP_KINDS
from portkit.cli import main
from portkit.pipeline import convert
from portkit.report import Residue, build, render, render_json

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _convert(name: str, tmp_path: Path):
    return convert(FIXTURES / name / "input", tmp_path / "out", "examplemod")


def _tree_with_residue(tmp_path: Path, entries: list[dict]) -> Path:
    """A tree holding the residue the conversion recorded, and nothing else."""
    (tmp_path / "behavior_pack").mkdir(parents=True, exist_ok=True)
    (tmp_path / "unhandled.json").write_text(json.dumps(entries, indent=2))
    return tmp_path


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


def test_the_rotated_fixture_now_converts_whole(tmp_path):
    """Refused until the probe settled the signs; keep it converting."""
    result = _convert("rotated_model_mod", tmp_path)
    text = render(result.tree)
    assert not result.unhandled, [u.reason for u in result.unhandled]
    assert "Everything in the source was converted." in text


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


# --- the report card as JSON (#240) -----------------------------------------


def _markdown_converted(text: str) -> dict[str, int]:
    """The "What converted" table of the Markdown report, as data."""
    rows = {}
    for line in text.splitlines():
        if line.startswith("| ") and not line.startswith("| Content") and not line.startswith("| ---"):
            name, _, count = line.strip().strip("|").partition("|")
            rows[name.strip()] = int(count.strip())
    return rows


def test_the_json_report_carries_the_same_numbers_as_the_markdown(tmp_path):
    result = _convert("recipes_mod", tmp_path)
    doc = json.loads(render_json(result.tree))
    assert doc["schema"] == 1
    assert doc["mod"]["name"] == "examplemod"
    assert doc["converted"] == _markdown_converted(render(result.tree))
    assert doc["coverage"]["converted_files"] == sum(doc["converted"].values())
    assert doc["coverage"]["total_files"] == (
        doc["coverage"]["converted_files"] + doc["coverage"]["residue_files"])
    assert f"{doc['coverage']['percent']:.1f}%" in render(result.tree)


def test_the_json_report_groups_the_unconverted_by_residue_kind(tmp_path):
    result = _convert("loot_mod", tmp_path)
    doc = json.loads(render_json(result.tree))
    groups = doc["unconverted"]
    assert groups, "the fixture leaves residue"
    for group in groups:
        assert group["kind"] and group["files"] >= len(group["items"])
        assert group["explanation"], "every kind says what it means"
        assert group["bedrock"] in ("cannot-be-done-on-bedrock", "partly-cannot-be-done-on-bedrock",
                                    "not-yet-converted")
        for item in group["items"]:
            assert item["source"] and item["reason"]
    assert sum(g["files"] for g in groups) == doc["coverage"]["residue_files"]


def test_the_json_report_names_the_settings_and_the_experiments_the_tree_records(tmp_path):
    tree = _tree_with_residue(tmp_path, [])
    (tree / "config-overrides.json").write_text(json.dumps({"_settings": [{
        "mod": "examplemod", "flag": "doThing", "condition": "examplemod:do_thing",
        "value": True, "cited_default": False, "as_written": "examplemod.doThing",
    }]}))
    blocks = tree / "behavior_pack" / "blocks"
    blocks.mkdir(parents=True)
    (blocks / "chest.json").write_text(json.dumps({
        "format_version": "1.21.80",
        "minecraft:block": {
            "description": {"identifier": "examplemod:chest"},
            "components": {"minecraft:block_entity": {"container": {"slot_count": 9}}},
        },
    }))
    doc = json.loads(render_json(tree))
    assert doc["approximated"]["settings"] == [{
        "mod": "examplemod", "flag": "doThing", "condition": "examplemod:do_thing",
        "value": True, "cited_default": False, "as_written": "examplemod.doThing",
    }]
    assert [e["experiment"] for e in doc["approximated"]["experiments"]] == ["upcoming_creator_features"]


def test_a_tree_with_no_settings_records_none(tmp_path):
    tree = _tree_with_residue(tmp_path, [])
    doc = json.loads(render_json(tree))
    assert doc["approximated"]["settings"] == []
    assert doc["approximated"]["experiments"] == []


def test_the_json_report_says_the_pack_is_not_verified_in_game(tmp_path):
    result = _convert("simple_block_mod", tmp_path)
    doc = json.loads(render_json(result.tree))
    assert doc["unverified_in_game"]["verified"] is False
    assert "in-game" in doc["unverified_in_game"]["note"]


# --- plain-language residue and what cannot be done on Bedrock (#240) --------


def test_each_residue_kind_is_explained_in_plain_language(tmp_path):
    tree = _tree_with_residue(tmp_path, [
        {"kind": "machine_recipe", "source": "data/x/recipes/a.json", "reason": "the machine is a Mekanism one"},
    ])
    text = render(tree)
    assert SKIP_KINDS["machine_recipe"] in text
    doc = json.loads(render_json(tree))
    assert doc["unconverted"][0]["explanation"] == SKIP_KINDS["machine_recipe"].strip()
    assert doc["unconverted"][0]["label"] == "Machine recipe"


def test_what_cannot_be_done_on_bedrock_is_flagged_and_says_why(tmp_path):
    tree = _tree_with_residue(tmp_path, [
        {"kind": "fluid_recipe", "source": "data/x/recipes/a.json", "reason": "it melts at a mod station",
         "count": 2},
        {"kind": "java_only_asset", "source": "assets/x/models/a.json", "reason": "only Java draws it"},
    ])
    doc = json.loads(render_json(tree))
    categories = {card["category"]: card for card in doc["cannot_be_done_on_bedrock"]}
    assert set(categories) == {"real custom fluids", "client rendering and shaders"}
    assert categories["real custom fluids"]["files"] == 2
    assert categories["real custom fluids"]["kinds"] == ["fluid_recipe"]
    assert categories["real custom fluids"]["why"]
    fluids = [g for g in doc["unconverted"] if g["kind"] == "fluid_recipe"][0]
    assert fluids["bedrock"] == "cannot-be-done-on-bedrock"
    text = render(tree)
    assert "## Cannot be done on Bedrock" in text
    assert "real custom fluids" in text
    assert "client rendering and shaders" in text


def test_a_category_the_tree_does_not_hold_is_not_flagged(tmp_path):
    tree = _tree_with_residue(tmp_path, [
        {"kind": "recipe", "source": "data/x/recipes/a.json", "reason": "the tag covers more than one item"},
    ])
    doc = json.loads(render_json(tree))
    assert doc["cannot_be_done_on_bedrock"] == []
    assert doc["unconverted"][0]["bedrock"] == "not-yet-converted"
    text = render(tree)
    assert "Cannot be done on Bedrock" not in text
    assert "real custom fluids" not in text


def test_the_report_command_prints_json_when_asked(tmp_path, capsys):
    result = _convert("recipes_mod", tmp_path)
    assert main(["report", str(result.tree), "--format", "json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["schema"] == 1
    assert doc["converted"] == _markdown_converted(render(result.tree))
    assert main(["report", str(result.tree)]) == 0
    assert "# Conversion report:" in capsys.readouterr().out


def test_the_report_command_writes_json_to_a_file(tmp_path):
    result = _convert("recipes_mod", tmp_path)
    out = tmp_path / "card.json"
    assert main(["report", str(result.tree), "--format", "json", "-o", str(out)]) == 0
    assert json.loads(out.read_text())["schema"] == 1
