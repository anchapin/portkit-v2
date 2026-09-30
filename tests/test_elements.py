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


def test_a_rotated_element_is_still_refused():
    box, why = models.cube(
        {"from": [0, 0, 0], "to": [4, 4, 4], "rotation": {"angle": 45, "axis": "y", "origin": [8, 8, 8]}}
    )
    assert box is None
    assert "rotated" in why


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
        {"elements": [{"from": [0, 0, 0], "to": [4, 4, 4]}, {"from": [0, 0, 0], "to": [1, 1, 1], "rotation": {"angle": 22.5, "axis": "x"}}]},
        "geometry.examplemod.thing",
    )
    assert geo is None
    assert "rotated" in why


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
