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


def test_java_lean_is_recorded_for_every_axis():
    assert set(axis_probe.EXPECTED_LEAN) == set(axis_probe.AXES)
    assert all(lean.strip() for lean in axis_probe.EXPECTED_LEAN.values())


def test_both_candidates_for_an_axis_carry_the_same_java_expectation():
    files = axis_probe.rotation_pack_files(MODELS, TEXTURE, "probe")
    lines = dict(
        line.split("=", 1) for line in files["texts/en_US.lang"].splitlines() if "=" in line
    )
    for axis in axis_probe.AXES:
        lean = axis_probe.EXPECTED_LEAN[axis]
        written = lines[f"tile.probe:rot_{axis}_aswritten.name"]
        negated = lines[f"tile.probe:rot_{axis}_negated.name"]
        assert lean in written and lean in negated
        assert "as written" in written and "negated" in negated


def test_the_java_convention_is_recorded_next_to_the_axis_constant():
    from portkit.converters import models

    assert models.JAVA_ROTATION_IS_RIGHT_HANDED is True


def test_the_derivation_is_written_down_where_it_can_be_checked():
    doc = Path(__file__).resolve().parents[1] / "docs/rotation-convention.md"
    text = doc.read_text()
    assert "template_torch_wall" in text
    for lean in axis_probe.EXPECTED_LEAN.values():
        head = lean.split(" swings")[0].split(" end")[0]
        assert head in text


def test_the_two_pivot_candidates_land_on_opposite_sides():
    """Off centre, the mappings disagree, which is the whole point of the probe."""
    element = {
        "from": [6, 6, 6],
        "to": [10, 10, 10],
        "rotation": {"angle": 45, "axis": "z", "origin": [0, 8, 8]},
    }
    mirrored = axis_probe.pivot_cube(element, "mirrored")
    unmirrored = axis_probe.pivot_cube(element, "unmirrored")

    assert mirrored["pivot"] == [8, 8, 0]
    assert unmirrored["pivot"] == [-8, 8, 0]
    # Same cube, same turn: the pivot is the only disagreement.
    assert mirrored["origin"] == unmirrored["origin"]
    assert mirrored["rotation"] == unmirrored["rotation"] == [0, 0, 45]


def test_a_centre_pivot_probes_nothing(tmp_path):
    """Both candidates agree at the centre, so the harness refuses to pretend."""
    model = tmp_path / "centre.json"
    model.write_text(
        json.dumps(
            {
                "elements": [
                    {
                        "from": [6, 6, 6],
                        "to": [10, 10, 10],
                        "rotation": {"angle": 45, "axis": "z", "origin": [8, 8, 8]},
                    }
                ]
            }
        )
    )
    texture = tmp_path / "probe.png"
    texture.write_bytes(b"png")

    with pytest.raises(ValueError, match="probes nothing"):
        axis_probe.pivot_pack_files(model, texture, "examplemod")


def test_the_pivot_pack_carries_both_blocks(tmp_path):
    model = tmp_path / "pivot_z.json"
    model.write_text(
        json.dumps(
            {
                "elements": [
                    {
                        "from": [6, 6, 6],
                        "to": [10, 10, 10],
                        "rotation": {"angle": 45, "axis": "z", "origin": [0, 8, 8]},
                    }
                ]
            }
        )
    )
    texture = tmp_path / "probe.png"
    texture.write_bytes(b"png")

    files = axis_probe.pivot_pack_files(model, texture, "examplemod")

    assert "blocks/pivot_mirrored.json" in files
    assert "blocks/pivot_unmirrored.json" in files
    assert axis_probe.PIVOT_EXPECTED in files["texts/en_US.lang"]
