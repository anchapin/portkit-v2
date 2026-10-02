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
    assert why == ""
    assert geo is not None


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


def test_an_off_centre_pivot_is_mirrored_like_the_cube():
    """Settled in game by the pivot probe (#52): the pivot shares the cube's space."""
    box, why = models.cube(
        {
            "from": [0, 7, 7],
            "to": [16, 9, 9],
            "rotation": {"origin": [0, 3.5, 8], "axis": "z", "angle": -22.5},
        }
    )
    assert why == ""
    assert box["pivot"] == [8.0, 3.5, 0.0]
    assert box["rotation"] == [0.0, 0.0, -22.5]


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


BEAM = {
    "textures": {"end": "examplemod:block/beam_end", "side": "examplemod:block/beam_side"},
    "elements": [
        {
            "from": [0, 6, 6],
            "to": [16, 10, 10],
            "faces": {
                "down": {"texture": "#side"},
                "up": {"texture": "#side"},
                "north": {"texture": "#side"},
                "south": {"texture": "#side"},
                "west": {"texture": "#end"},
                "east": {"texture": "#end"},
            },
        }
    ],
}


def test_each_face_keeps_its_own_texture_key():
    by_face, why = models.element_materials(BEAM)
    assert why == ""
    assert by_face["up"] == "side"
    assert by_face["north"] == "side"


def test_the_x_faces_keep_their_java_names():
    # Read in game (#64): after the box is mirrored, Bedrock's west is Java's west.
    caps = dict(BEAM["elements"][0]["faces"])
    caps["west"] = {"texture": "#end_west"}
    caps["east"] = {"texture": "#end_east"}
    model = {"textures": BEAM["textures"], "elements": [{**BEAM["elements"][0], "faces": caps}]}
    by_face, why = models.element_materials(model)
    assert why == ""
    assert by_face["west"] == "end_west"
    assert by_face["east"] == "end_east"


def test_the_face_rule_follows_the_named_constant(monkeypatch):
    monkeypatch.setattr(models, "FACE_NAMES_FOLLOW_MIRROR", True)
    model = {"elements": [{"from": [0, 0, 0], "to": [16, 16, 16],
                           "faces": {"west": {"texture": "#w"}, "east": {"texture": "#e"}}}]}
    by_face, _ = models.element_materials(model)
    assert by_face == {"east": "w", "west": "e"}


def test_elements_disagreeing_on_one_face_are_refused():
    second = {"from": [0, 0, 0], "to": [16, 4, 16], "faces": {"up": {"texture": "#end"}}}
    model = {"textures": BEAM["textures"], "elements": [BEAM["elements"][0], second]}
    by_face, why = models.element_materials(model)
    assert by_face is None
    assert "disagree about the texture on their up face" in why


def test_a_model_with_no_elements_has_no_materials():
    by_face, why = models.element_materials({"textures": {}})
    assert by_face is None
    assert why == "model has no elements"


def _turned(axis: str, origin: list[float]) -> dict:
    return {
        "from": [0, 0, 0],
        "to": [16, 4, 16],
        "rotation": {"axis": axis, "angle": 22.5, "origin": origin},
        "faces": {"up": {"texture": "#all"}},
    }


def test_a_pivot_slid_along_its_own_axis_is_the_centre_turn():
    # Spinning about y, moving the pivot up or down y changes nothing, and both
    # candidate mappings in #52 agree there, so no probe is needed.
    box, why = models.cube(_turned("y", [8, 0, 8]))
    assert why == ""
    assert box["pivot"] == [0.0, 0.0, 0.0]
    assert box["rotation"][1] == 22.5 * models.ROTATION_SIGN["y"]


def test_the_same_holds_for_x_and_z():
    for axis, origin, expected in (
        ("x", [0, 8, 8], [8.0, 8.0, 0.0]),
        ("z", [8, 8, 15], [0.0, 8.0, 7.0]),
    ):
        box, why = models.cube(_turned(axis, origin))
        assert why == "", axis
        assert box["pivot"] == expected, axis


def test_bonfire_style_pivots_outside_the_block_convert():
    """Decorative Blocks' bonfire logs turn about points beyond the block edge."""
    for axis, origin, expected in (
        ("z", [-3, 0, -8], [11.0, 0.0, -16.0]),
        ("z", [19, 0, -8], [-11.0, 0.0, -16.0]),
        ("x", [-8, 0, 19], [16.0, 0.0, 11.0]),
    ):
        box, why = models.cube(_turned(axis, origin))
        assert why == "", axis
        assert box["pivot"] == expected, axis


def test_the_pivot_mirror_follows_the_named_constant(monkeypatch):
    monkeypatch.setattr(models, "PIVOT_IS_MIRRORED", False)
    box, why = models.cube(_turned("y", [3, 0, 8]))
    assert why == ""
    assert box["pivot"][0] == -5.0



# Faces that disagree about one direction: each names its instance (bonfire).
_BONFIRE_LIKE = {
    "textures": {"texture": "examplemod:block/logs", "cross": "examplemod:block/flame"},
    "elements": [
        {
            "from": [-3, 0, -8],
            "to": [-2.999, 32, 24],
            "rotation": {"origin": [-3, 0, -8], "axis": "z", "angle": -22.5},
            "faces": {"west": {"texture": "#texture", "uv": [0, 0, 16, 16]}},
        },
        {
            "from": [8, 0, -8],
            "to": [8.001, 32, 24],
            "rotation": {"origin": [8, 0, 8], "axis": "y", "angle": 45},
            "faces": {
                "west": {"texture": "#cross", "uv": [0, 0, 16, 16]},
                "east": {"texture": "#cross", "uv": [0, 0, 16, 16]},
            },
        },
    ],
}


def test_disagreeing_faces_get_one_named_instance_per_texture_key():
    by_face, why = models.element_materials(_BONFIRE_LIKE)
    assert by_face is None and "disagree" in why
    names, why = models.tagged_materials(_BONFIRE_LIKE)
    assert why == ""
    assert names == {"cross": "cross", "texture": "texture"}


def test_tagged_geometry_names_the_instance_on_every_face():
    geo, why = models.geometry(_BONFIRE_LIKE, "geometry.examplemod.bonfire", tag_faces=True)
    assert why == ""
    logs, flame = geo["minecraft:geometry"][0]["bones"][0]["cubes"]
    assert logs["uv"]["west"]["material_instance"] == "texture"
    assert {f["material_instance"] for f in flame["uv"].values()} == {"cross"}


def test_untagged_geometry_is_unchanged():
    geo, why = models.geometry(_BONFIRE_LIKE, "geometry.examplemod.bonfire")
    cubes = geo["minecraft:geometry"][0]["bones"][0]["cubes"]
    assert all("material_instance" not in f for c in cubes for f in c["uv"].values())


def test_a_key_named_like_a_built_in_face_is_renamed():
    model = {
        "elements": [
            {"from": [0, 0, 0], "to": [16, 1, 16],
             "faces": {"up": {"texture": "#up", "uv": [0, 0, 16, 16]}}},
            {"from": [0, 1, 0], "to": [16, 2, 16],
             "faces": {"up": {"texture": "#side", "uv": [0, 0, 16, 16]}}},
        ]
    }
    names, _ = models.tagged_materials(model)
    assert names == {"java_up": "up", "side": "side"}


def test_a_tagged_face_without_uv_is_refused():
    model = {"elements": [{"from": [0, 0, 0], "to": [16, 16, 16],
                           "faces": {"up": {"texture": "#top"}}}]}
    geo, why = models.geometry(model, "geometry.examplemod.x", tag_faces=True)
    assert geo is None
    assert "up face has no uv" in why
