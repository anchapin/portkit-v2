"""The rotation probe: six blocks that answer three sign questions."""

import json
from pathlib import Path

import pytest

from portkit.harness import axis_probe

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/rotated_model_mod/input"
MODELS = FIXTURE / "assets/examplemod/models/block"
TEXTURE = FIXTURE / "assets/examplemod/textures/block/probe.png"


def test_every_axis_has_a_model_to_probe_with():
    for axis in axis_probe.AXES:
        model = json.loads((MODELS / f"rot_{axis}.json").read_text())
        rotation = model["elements"][0]["rotation"]
        assert rotation["axis"] == axis
        assert rotation["angle"] == 22.5
        assert rotation["origin"] == [8, 8, 8], "a non-centre pivot is a separate question"


def test_the_bar_is_asymmetric_enough_to_read_a_lean_from():
    for axis in axis_probe.AXES:
        element = json.loads((MODELS / f"rot_{axis}.json").read_text())["elements"][0]
        size = [t - f for f, t in zip(element["from"], element["to"])]
        assert max(size) == 16 and sorted(size)[1] <= 2, size


def test_the_two_signs_disagree_and_only_about_the_sign():
    element = json.loads((MODELS / "rot_y.json").read_text())["elements"][0]
    a = axis_probe.rotated_cube(element, "aswritten")
    b = axis_probe.rotated_cube(element, "negated")
    assert a["rotation"] == [0, 22.5, 0]
    assert b["rotation"] == [0, -22.5, 0]
    assert a["origin"] == b["origin"] and a["size"] == b["size"]
    assert a["pivot"] == b["pivot"]


def test_the_angle_lands_on_the_axis_java_named():
    for axis, index in (("x", 0), ("y", 1), ("z", 2)):
        element = json.loads((MODELS / f"rot_{axis}.json").read_text())["elements"][0]
        degrees = axis_probe.rotated_cube(element, "aswritten")["rotation"]
        assert degrees[index] == 22.5
        assert [d for i, d in enumerate(degrees) if i != index] == [0.0, 0.0]


def test_a_centre_pivot_survives_the_mirror_unchanged():
    element = json.loads((MODELS / "rot_z.json").read_text())["elements"][0]
    assert axis_probe.rotated_cube(element, "aswritten")["pivot"] == [0, 8, 0]


def test_the_cube_itself_still_follows_the_confirmed_x_flip():
    element = json.loads((MODELS / "rot_y.json").read_text())["elements"][0]
    cube = axis_probe.rotated_cube(element, "aswritten")
    assert cube["origin"][0] == 8 - element["to"][0]


def test_the_pack_carries_six_blocks_and_six_geometries():
    files = axis_probe.rotation_pack_files(MODELS, TEXTURE, "probe")
    blocks = [k for k in files if k.startswith("blocks/")]
    geometries = [k for k in files if k.endswith(".geo.json")]
    assert len(blocks) == 6 and len(geometries) == 6
    assert sorted(blocks) == sorted(
        f"blocks/rot_{a}_{s}.json" for a in axis_probe.AXES for s in axis_probe.SIGNS
    )


def test_every_block_is_named_in_the_lang_file_so_you_can_tell_them_apart():
    files = axis_probe.rotation_pack_files(MODELS, TEXTURE, "probe")
    lang = files["texts/en_US.lang"]
    for axis in axis_probe.AXES:
        for sign in axis_probe.SIGNS:
            assert f"tile.probe:rot_{axis}_{sign}.name=" in lang


def test_each_block_points_at_its_own_geometry():
    files = axis_probe.rotation_pack_files(MODELS, TEXTURE, "probe")
    for axis in axis_probe.AXES:
        for sign in axis_probe.SIGNS:
            block = files[f"blocks/rot_{axis}_{sign}.json"]
            components = block["minecraft:block"]["components"]
            assert components["minecraft:geometry"] == f"geometry.probe.rot_{axis}_{sign}"


def test_a_model_with_nothing_to_rotate_is_refused_not_guessed(tmp_path):
    for axis in axis_probe.AXES:
        (tmp_path / f"rot_{axis}.json").write_text(json.dumps({"elements": []}))
    with pytest.raises(ValueError, match="no elements"):
        axis_probe.rotation_pack_files(tmp_path, TEXTURE, "probe")
