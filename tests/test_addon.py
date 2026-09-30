"""The two packs have to install as one addon."""
import json
import zipfile

import pytest

from portkit.pack import addon_name, manifest
from portkit.meta import ModMetadata
from portkit.pipeline import convert
from portkit.validate import validate_tree


def read(tree, kind):
    return json.loads((tree / f"{kind}_pack" / "manifest.json").read_text())


@pytest.fixture
def converted(tmp_path, fixtures_dir):
    return convert(fixtures_dir / "simple_block_mod" / "input", tmp_path / "out")


def test_behavior_pack_depends_on_the_resource_pack(converted):
    bp = read(converted.tree, "behavior")
    rp = read(converted.tree, "resource")
    assert [d["uuid"] for d in bp["dependencies"]] == [rp["header"]["uuid"]]
    assert bp["dependencies"][0]["version"] == rp["header"]["version"]


def test_the_resource_pack_does_not_point_back(converted):
    # Bedrock rejects a circular dependency, so only one direction is declared.
    assert "dependencies" not in read(converted.tree, "resource")


def test_a_resource_only_mod_declares_no_dependency(tmp_path, fixtures_dir):
    result = convert(fixtures_dir / "animated_block_mod" / "input", tmp_path / "out")
    assert not (result.tree / "behavior_pack").exists()
    assert "dependencies" not in read(result.tree, "resource")
    assert result.report.ok


def test_addon_holds_only_the_packs(converted, tmp_path):
    (tmp_path / "out" / "stray.txt").write_text("not part of the addon")
    from portkit.pack import write_mcaddon

    addon = write_mcaddon(converted.tree, tmp_path / "out" / "again.mcaddon")
    with zipfile.ZipFile(addon) as zf:
        assert not [n for n in zf.namelist() if "stray" in n or n.endswith(".mcaddon")]


def test_addon_is_written_and_contains_both_packs(converted):
    assert converted.addon is not None
    assert converted.addon.name == "examplemod.mcaddon"  # the declared mod id, not the folder
    with zipfile.ZipFile(converted.addon) as zf:
        names = zf.namelist()
    assert "behavior_pack/manifest.json" in names
    assert "resource_pack/manifest.json" in names
    # every entry sits under a pack folder, which is what Bedrock imports
    assert all(n.startswith(("behavior_pack/", "resource_pack/")) for n in names)


def test_addon_manifests_survive_the_zip(converted):
    with zipfile.ZipFile(converted.addon) as zf:
        bp = json.loads(zf.read("behavior_pack/manifest.json"))
    assert bp["dependencies"]
    assert bp["format_version"] == 2


def test_no_addon_flag_leaves_the_tree_alone(tmp_path, fixtures_dir):
    result = convert(
        fixtures_dir / "simple_block_mod" / "input", tmp_path / "out", emit_addon=False
    )
    assert result.addon is None
    assert not list((tmp_path / "out").glob("*.mcaddon"))
    assert result.summary()["mcaddon"] is None


def test_addon_is_named_after_the_declared_mod_id():
    assert addon_name("examplemod", ModMetadata(mod_id="cool_mod")) == "cool_mod.mcaddon"
    assert addon_name("examplemod") == "examplemod.mcaddon"
    assert addon_name("ns", ModMetadata(mod_id="Cool Mod!")) == "Cool_Mod.mcaddon"


def test_validator_rejects_a_dependency_on_a_pack_that_is_not_here(converted):
    path = converted.tree / "behavior_pack" / "manifest.json"
    data = json.loads(path.read_text())
    data["dependencies"] = [{"uuid": "00000000-0000-0000-0000-000000000000", "version": [1, 0, 0]}]
    path.write_text(json.dumps(data))
    report = validate_tree(converted.tree)
    assert not report.ok
    assert any(f.rule == "manifest.dependency" for f in report.errors)


def test_validator_rejects_a_pack_depending_on_itself(converted):
    path = converted.tree / "behavior_pack" / "manifest.json"
    data = json.loads(path.read_text())
    data["dependencies"] = [{"uuid": data["header"]["uuid"], "version": [1, 0, 0]}]
    path.write_text(json.dumps(data))
    report = validate_tree(converted.tree)
    assert any("points at this pack" in f.message for f in report.errors)


def test_dependency_uuids_are_stable_across_runs(tmp_path, fixtures_dir):
    first = convert(fixtures_dir / "simple_block_mod" / "input", tmp_path / "a")
    second = convert(fixtures_dir / "simple_block_mod" / "input", tmp_path / "b")
    assert read(first.tree, "behavior")["dependencies"] == (
        read(second.tree, "behavior")["dependencies"]
    )


def test_manifest_dependency_version_follows_the_mod_version():
    meta = ModMetadata(mod_id="x", version=(4, 2, 1))
    data = manifest("x", "behavior", meta, depends_on=("resource",))
    assert data["dependencies"][0]["version"] == [4, 2, 1]
    assert data["header"]["version"] == [4, 2, 1]
