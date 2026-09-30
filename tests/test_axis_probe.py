"""The probe only helps if the two candidates really do differ."""
import json
import zipfile
from pathlib import Path

import pytest

from portkit.cli import main
from portkit.harness import axis_probe
from portkit.validate import validate_tree

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/asymmetric_model_mod/input"
MODEL = FIXTURE / "assets/examplemod/models/block/probe.json"
TEXTURE = FIXTURE / "assets/examplemod/textures/block/probe.png"


def _cubes(files, candidate):
    geo = files[f"models/blocks/probe_{candidate}.geo.json"]
    return geo["minecraft:geometry"][0]["bones"][0]["cubes"]


def test_the_fixture_model_is_asymmetric_on_x():
    """A symmetric probe would answer nothing, so guard the fixture itself."""
    element = json.loads(MODEL.read_text())["elements"][0]
    assert element["from"][0] != 16 - element["to"][0]


def test_the_two_candidates_disagree_about_where_the_box_goes():
    files = axis_probe.build(MODEL, "examplemod", "examplemod:probe")
    direct = _cubes(files, "direct")[0]["origin"]
    mirrored = _cubes(files, "mirrored")[0]["origin"]
    assert direct[0] != mirrored[0]
    assert direct[1:] == mirrored[1:]


def test_each_candidate_uses_its_own_arithmetic():
    files = axis_probe.build(MODEL, "examplemod", "examplemod:probe")
    element = json.loads(MODEL.read_text())["elements"][0]
    x1, x2 = element["from"][0], element["to"][0]
    assert _cubes(files, "direct")[0]["origin"][0] == x1 - 8
    assert _cubes(files, "mirrored")[0]["origin"][0] == 8 - x2


def test_size_is_the_element_and_z_is_centred():
    files = axis_probe.build(MODEL, "examplemod", "examplemod:probe")
    cube = _cubes(files, "direct")[0]
    assert cube["size"] == [6, 4, 16]
    assert cube["origin"][2] == -8


def test_face_uvs_carry_over_as_offset_and_span():
    files = axis_probe.build(MODEL, "examplemod", "examplemod:probe")
    uv = _cubes(files, "direct")[0]["uv"]
    assert uv["west"]["uv"] == [0, 0]
    assert uv["west"]["uv_size"] == [16, 4]


def test_both_blocks_are_defined_and_named_apart():
    files = axis_probe.build(MODEL, "examplemod", "examplemod:probe")
    for candidate in axis_probe.CANDIDATES:
        body = files[f"blocks/probe_{candidate}.json"]["minecraft:block"]
        assert body["description"]["identifier"] == f"examplemod:probe_{candidate}"
        assert body["components"]["minecraft:geometry"] == f"geometry.examplemod.probe_{candidate}"
    lang = files["texts/en_US.lang"]
    assert "probe_direct.name" in lang and "probe_mirrored.name" in lang


def test_a_model_without_elements_is_refused(tmp_path):
    flat = tmp_path / "flat.json"
    flat.write_text(json.dumps({"parent": "block/cube_all"}))
    with pytest.raises(ValueError):
        axis_probe.build(flat, "examplemod", "examplemod:probe")


def test_the_probe_command_writes_an_installable_pack_that_validates(tmp_path):
    out = tmp_path / "probe"
    code = main(["probe", str(out), "--model", str(MODEL), "--texture", str(TEXTURE)])
    assert code == 0

    report = validate_tree(out)
    assert report.ok, [f.message for f in report.errors]

    addon = out / "axis_probe.mcaddon"
    names = zipfile.ZipFile(addon).namelist()
    assert "behavior_pack/manifest.json" in names
    assert "resource_pack/models/blocks/probe_direct.geo.json" in names
    assert "resource_pack/textures/blocks/probe.png" in names
