"""Structural validation against Mojang's vendored Bedrock schemas (#15)."""
import json
from pathlib import Path

from portkit.validate import schema, validate_tree
from portkit.validate.report import ValidationReport

ROOT = Path(__file__).resolve().parents[1]


def _block(components, permutations=None, fmt="1.21.40"):
    body = {"description": {"identifier": "m:x"}, "components": components}
    if permutations is not None:
        body["permutations"] = permutations
    return {"format_version": fmt, "minecraft:block": body}


def _check(data):
    report = ValidationReport()
    schema.check_block(report, data, "behavior_pack/blocks/x.json")
    return report


def test_unknown_component_is_an_error_with_rule_and_pointer():
    report = _check(_block({"minecraft:geometry": "minecraft:geometry.full_block", "minecraft:frobnicate": {}}))
    [finding] = report.errors
    assert finding.rule == "schema.unknown_component"
    assert finding.pointer == "/minecraft:block/components/minecraft:frobnicate"
    assert finding.pointer in finding.message
    assert report.to_dict()["findings"][0]["pointer"] == finding.pointer


def test_unknown_component_in_a_permutation_is_caught():
    report = _check(_block({}, [{"condition": "q.block_state('a')", "components": {"minecraft:glow": 1}}]))
    assert [f.pointer for f in report.errors] == ["/minecraft:block/permutations/0/components/minecraft:glow"]


def test_custom_namespace_components_are_left_alone():
    assert _check(_block({"examplemod:on_use": {}, "minecraft:light_emission": 7})).findings == []


def test_shape_mismatches_warn_with_a_pointer():
    report = _check(_block({"minecraft:light_emission": "bright"}))
    assert report.ok
    [warning] = report.findings
    assert (warning.rule, warning.severity) == ("schema.type", "warning")
    assert warning.pointer == "/minecraft:block/components/minecraft:light_emission"
    missing = _check({"minecraft:block": {"description": {}}})
    assert {(f.rule, f.pointer) for f in missing.findings} == {
        ("schema.required", "/"),
        ("schema.required", "/minecraft:block/description"),
    }


def test_pointer_escapes_tilde_and_slash():
    assert schema.pointer(["a/b", "c~d", 0]) == "/a~1b/c~0d/0"


def test_snapshot_choice_falls_back_to_the_newest():
    newest = ".".join(map(str, schema.SNAPSHOTS[-1]))
    assert schema.snapshot_for("1.20.20").name == newest  # oldest snapshot at or above
    assert schema.snapshot_for("99.0.0").name == newest
    assert schema.snapshot_for("not a version").name == newest
    assert "minecraft:geometry" in schema.known_block_components(schema.snapshot_for("1.21.0"))


def test_validate_tree_runs_the_schema_on_block_files(tmp_path):
    bp = tmp_path / "behavior_pack"
    (bp / "blocks").mkdir(parents=True)
    (bp / "manifest.json").write_text(json.dumps({
        "format_version": 2,
        "header": {"name": "t", "description": "", "uuid": "11111111-1111-4111-8111-111111111111",
                   "version": [1, 0, 0], "min_engine_version": [1, 20, 20]},
        "modules": [{"type": "data", "uuid": "22222222-2222-4222-8222-222222222222", "version": [1, 0, 0]}],
    }))
    (bp / "blocks" / "x.json").write_text(json.dumps(_block({"minecraft:frobnicate": {}})))
    assert any(f.rule == "schema.unknown_component" for f in validate_tree(tmp_path).errors)


def test_the_vendored_corpus_is_packaged_and_sourced():
    snap = schema.snapshot_for(None)
    assert (snap / "LICENSE").is_file() and (snap / "bp" / "blocks" / "index.schema.json").is_file()
    assert snap.name in (schema.SCHEMA_ROOT / "SOURCE.md").read_text()
