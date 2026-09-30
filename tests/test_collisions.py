"""Two files, one name. Bedrock picks one and says nothing; we say both."""

import json
from pathlib import Path

from portkit.validate import check_collisions, validate_tree
from portkit.validate.report import ValidationReport


def _definition(kind: str, identifier: str) -> dict:
    return {f"minecraft:{kind}": {"description": {"identifier": identifier}}}


def _tree(root: Path, files: dict[str, dict]) -> Path:
    for rel, data in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))
    return root


def _findings(root: Path) -> list:
    report = ValidationReport()
    check_collisions(report, root)
    return report.findings


def test_a_duplicate_block_identifier_names_both_files(tmp_path):
    _tree(tmp_path, {
        "behavior_pack/blocks/lamp.json": _definition("block", "examplemod:lamp"),
        "behavior_pack/blocks/lamp_copy.json": _definition("block", "examplemod:lamp"),
    })
    (finding,) = [f for f in _findings(tmp_path) if f.rule == "block.identifier_collision"]
    assert finding.severity == "error"
    assert "behavior_pack/blocks/lamp.json" in finding.message
    assert "behavior_pack/blocks/lamp_copy.json" in finding.message
    assert "examplemod:lamp" in finding.message


def test_three_files_one_name_says_three(tmp_path):
    _tree(tmp_path, {
        f"behavior_pack/blocks/lamp_{i}.json": _definition("block", "examplemod:lamp")
        for i in range(3)
    })
    (finding,) = [f for f in _findings(tmp_path) if f.rule.endswith("identifier_collision")]
    assert "declared 3 times" in finding.message


def test_recipes_collide_with_recipes_not_with_blocks(tmp_path):
    _tree(tmp_path, {
        "behavior_pack/blocks/lamp.json": _definition("block", "examplemod:lamp"),
        "behavior_pack/recipes/lamp.json": {
            "minecraft:recipe_shaped": {"description": {"identifier": "examplemod:lamp"}}
        },
    })
    assert not [f for f in _findings(tmp_path) if f.rule.endswith("identifier_collision")]


def test_shadowing_a_vanilla_name_is_an_error(tmp_path):
    _tree(tmp_path, {
        "behavior_pack/blocks/stone.json": _definition("block", "minecraft:stone"),
    })
    (finding,) = [f for f in _findings(tmp_path) if f.rule == "block.vanilla_shadow"]
    assert finding.severity == "error"
    assert "load order" in finding.message


def test_a_block_and_an_item_sharing_a_name_is_a_warning_not_a_failure(tmp_path):
    _tree(tmp_path, {
        "behavior_pack/blocks/lamp.json": _definition("block", "examplemod:lamp"),
        "behavior_pack/items/lamp.json": _definition("item", "examplemod:lamp"),
    })
    findings = _findings(tmp_path)
    (warning,) = [f for f in findings if f.rule == "identifier.block_and_item"]
    assert warning.severity == "warning"
    assert not [f for f in findings if f.severity == "error"]


def test_the_same_name_in_two_packs_still_collides(tmp_path):
    _tree(tmp_path, {
        "behavior_pack/blocks/lamp.json": _definition("block", "examplemod:lamp"),
        "resource_pack/blocks/lamp.json": _definition("block", "examplemod:lamp"),
    })
    (finding,) = [f for f in _findings(tmp_path) if f.rule.endswith("identifier_collision")]
    assert "resource_pack/blocks/lamp.json" in finding.message


def test_a_clean_tree_says_nothing(tmp_path):
    _tree(tmp_path, {
        "behavior_pack/blocks/lamp.json": _definition("block", "examplemod:lamp"),
        "behavior_pack/blocks/chair.json": _definition("block", "examplemod:chair"),
        "behavior_pack/items/wrench.json": _definition("item", "examplemod:wrench"),
    })
    assert _findings(tmp_path) == []


def test_unreadable_json_is_left_to_the_rule_that_owns_it(tmp_path):
    (tmp_path / "behavior_pack/blocks").mkdir(parents=True)
    (tmp_path / "behavior_pack/blocks/broken.json").write_text("{not json")
    assert _findings(tmp_path) == []


def test_the_collision_check_runs_as_part_of_validate_tree(tmp_path):
    _tree(tmp_path, {
        "behavior_pack/blocks/lamp.json": _definition("block", "examplemod:lamp"),
        "behavior_pack/blocks/lamp_copy.json": _definition("block", "examplemod:lamp"),
    })
    report = validate_tree(tmp_path)
    assert [f for f in report.findings if f.rule == "block.identifier_collision"]
    assert not report.ok
