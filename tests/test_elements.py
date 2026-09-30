"""Custom element models, converted under the observed axis convention."""
import json
from pathlib import Path

from portkit.converters import models
from portkit.harness import axis_probe
from portkit.pipeline import convert

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
PROBE_MODEL = FIXTURES / "asymmetric_model_mod/input/assets/examplemod/models/block/probe.json"


def test_x_is_measured_from_the_far_edge():
    """Observed in game: Bedrock's X runs opposite Java's."""
    box, why = models.cube({"from": [0, 0, 0], "to": [6, 4, 16]})
    assert why == ""
    assert box["origin"] == [2.0, 0.0, -8.0]
    assert box["size"] == [6.0, 4.0, 16.0]


def test_the_code_agrees_with_the_probe_candidate_that_was_confirmed():
    """If the constant is ever flipped back, this catches it."""
    element = json.loads(PROBE_MODEL.read_text())["elements"][0]
    ours, _ = models.cube(element)
    probe = axis_probe._cube(element, "mirrored")
    assert ours["origin"] == probe["origin"]
    assert ours["origin"] != axis_probe._cube(element, "direct")["origin"]


def test_a_centred_element_lands_centred():
    box, _ = models.cube({"from": [4, 0, 4], "to": [12, 8, 12]})
    assert box["origin"] == [-4.0, 0.0, -4.0]


def test_uvs_become_offset_and_span():
    box, _ = models.cube(
        {"from": [0, 0, 0], "to": [16, 16, 16], "faces": {"up": {"uv": [0, 0, 8, 4]}}}
    )
    assert box["uv"]["up"] == {"uv": [0.0, 0.0], "uv_size": [8.0, 4.0]}


def test_a_centre_rotation_is_no_longer_refused():
    """Was refused until the signs were read in game on 2026-09-30."""
    box, why = models.cube(
        {"from": [0, 0, 0], "to": [4, 4, 4], "rotation": {"angle": 45, "axis": "y", "origin": [8, 8, 8]}}
    )
    assert why == ""
    assert box["rotation"] == [0.0, -45.0, 0.0]


def test_elements_wearing_different_textures_are_refused():
    key, why = models.element_texture(
        {
            "elements": [
                {"faces": {"up": {"texture": "#top"}, "down": {"texture": "#bottom"}}}
            ]
        }
    )
    assert key is None
    assert "different textures" in why


def test_one_shared_texture_resolves():
    key, why = models.element_texture(
        {"elements": [{"faces": {"up": {"texture": "#all"}, "down": {"texture": "#all"}}}]}
    )
    assert key == "all"
    assert why == ""


def test_geometry_carries_every_element_as_a_cube():
    geo, why = models.geometry(
        {"elements": [{"from": [0, 0, 0], "to": [4, 4, 4]}, {"from": [8, 0, 0], "to": [16, 2, 2]}]},
        "geometry.examplemod.thing",
    )
    assert why == ""
    entry = geo["minecraft:geometry"][0]
    assert entry["description"]["identifier"] == "geometry.examplemod.thing"
    assert len(entry["bones"][0]["cubes"]) == 2


def test_one_bad_element_refuses_the_whole_model():
    geo, why = models.geometry(
        {
            "elements": [
                {"from": [0, 0, 0], "to": [4, 4, 4]},
                {
                    "from": [0, 0, 0],
                    "to": [1, 1, 1],
                    "rotation": {"angle": 22.5, "axis": "x", "origin": [0, 3.5, 8]},
                },
            ]
        },
        "geometry.examplemod.thing",
    )
    assert geo is None
    assert "off the block centre" in why


def test_the_asymmetric_fixture_now_converts_whole(tmp_path):
    out = tmp_path / "out"
    result = convert(FIXTURES / "asymmetric_model_mod/input", out, emit_addon=False)
    assert not result.unhandled, [u.reason for u in result.unhandled]
    assert result.report.ok, [f.message for f in result.report.errors]

    block = json.loads((out / "behavior_pack/blocks/probe.json").read_text())["minecraft:block"]
    assert block["components"]["minecraft:geometry"] == "geometry.examplemod.probe"
    assert block["components"]["minecraft:material_instances"]["*"]["texture"] == "examplemod:probe"

    geo = json.loads((out / "resource_pack/models/blocks/probe.geo.json").read_text())
    cube = geo["minecraft:geometry"][0]["bones"][0]["cubes"][0]
    assert cube["origin"] == [2.0, 0.0, -8.0]


def test_a_centre_rotation_carries_the_observed_sign_per_axis():
    """Observed in game 2026-09-30: x and y negated, z as written."""
    for axis, expected in (("x", -22.5), ("y", -22.5), ("z", 22.5)):
        box, why = models.cube(
            {
                "from": [0, 7, 7],
                "to": [16, 9, 9],
                "rotation": {"origin": [8, 8, 8], "axis": axis, "angle": 22.5},
            }
        )
        assert why == ""
        assert box["pivot"] == [0.0, 8.0, 0.0]
        assert box["rotation"][models._AXIS_INDEX[axis]] == expected
        assert sum(abs(v) for v in box["rotation"]) == abs(expected)


def test_the_sign_table_matches_the_probe_candidates_that_were_confirmed():
    """The converter and the harness must read the same three answers."""
    confirmed = {"x": "negated", "y": "negated", "z": "aswritten"}
    for axis, sign in confirmed.items():
        element = {
            "from": [0, 7, 7],
            "to": [16, 9, 9],
            "rotation": {"origin": [8, 8, 8], "axis": axis, "angle": 22.5},
        }
        ours, _ = models.cube(element)
        theirs = axis_probe.rotated_cube(element, sign)
        assert ours["rotation"] == theirs["rotation"]
        assert ours["pivot"] == theirs["pivot"]


def test_an_off_centre_pivot_is_still_refused_with_the_open_question():
    box, why = models.cube(
        {
            "from": [0, 7, 7],
            "to": [16, 9, 9],
            "rotation": {"origin": [0, 3.5, 8], "axis": "z", "angle": -22.5},
        }
    )
    assert box is None
    assert "off the block centre" in why and "#52" in why


def test_an_angle_java_never_writes_is_refused():
    box, why = models.cube(
        {
            "from": [0, 7, 7],
            "to": [16, 9, 9],
            "rotation": {"origin": [8, 8, 8], "axis": "z", "angle": 30},
        }
    )
    assert box is None
    assert "30" in why


def test_an_unrotated_element_gains_no_rotation_keys():
    box, why = models.cube({"from": [0, 0, 0], "to": [16, 16, 16]})
    assert why == ""
    assert "rotation" not in box and "pivot" not in box
