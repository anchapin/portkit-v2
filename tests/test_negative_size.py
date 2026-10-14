"""Negative-size model elements (from > to on some axis), unfolded as Java bakes them.

Java never sorts an element's corners (BlockElement$Deserializer#getFrom/getTo
only bound-check them; FaceBakery#setupShape files from as MIN and to as MAX),
so a face lands where the raw numbers put it and is named by the way its
winding really points (FaceBakery#calculateFacing). models.baked_quad is that
baking, written out from the MC 1.21.1 client jar; these tests hold the
unfolded elements to it corner by corner.
"""
import itertools
import json

import pytest

from portkit.converters import blocks, models
from portkit.model import SourceMod

FACES = ("down", "up", "north", "south", "west", "east")
UV = [1.0, 2.0, 5.0, 7.0]


def _raw(inverted, rotation=0, uv=True, faces=FACES):
    low, high = [1.0, 2.0, 3.0], [9.0, 12.0, 14.0]
    start = [high[i] if inverted[i] else low[i] for i in range(3)]
    end = [low[i] if inverted[i] else high[i] for i in range(3)]
    spec = {"texture": "#t"}
    if uv:
        spec["uv"] = list(UV)
    if rotation:
        spec["rotation"] = rotation
    return {"from": start, "to": end, "faces": {f: dict(spec) for f in faces}}


def _java_quads(element):
    out = []
    for face, spec in element["faces"].items():
        uv = spec.get("uv") or models.auto_uv(face, element["from"], element["to"])
        out.append(models.baked_quad(face, element["from"], element["to"], uv, spec.get("rotation", 0)))
    return out


def test_baking_names_an_ordinary_face_by_its_own_direction():
    """Calibration: calculateFacing on a positive box gives each face its name."""
    for face in FACES:
        quad = models.baked_quad(face, [1, 2, 3], [9, 10, 11], UV, 0)
        assert models.quad_facing(quad) == face


@pytest.mark.parametrize("inverted", [p for p in itertools.product((0, 1), repeat=3) if any(p)])
@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("uv", [True, False])
def test_unfolded_elements_bake_to_the_same_quads(inverted, rotation, uv):
    raw = _raw(inverted, rotation, uv)
    unfolded, why = models.unfold_negative(raw)
    assert why == ""
    for element in unfolded:
        assert all(a <= b for a, b in zip(element["from"], element["to"]))
        assert element[models.NEGATIVE_MARK] is True
        for face, spec in element["faces"].items():
            quad = models.baked_quad(face, element["from"], element["to"], spec["uv"], spec.get("rotation", 0))
            # every unfolded face points the way it is named
            assert models.quad_facing(quad) == face
    expected = _java_quads(raw)
    got = _java_quads({"faces": {}, "from": [0, 0, 0], "to": [0, 0, 0]})
    for element in unfolded:
        got += _java_quads(element)
    assert len(got) == len(expected) == 6
    for quad in expected:
        assert sum(models._same_quad(quad, other) for other in got) == 1


def test_blockbench_inverted_cube_becomes_six_inward_planes():
    """All three axes swapped: each face keeps its name but sits on the
    opposite wall, pointing into the box (an interior), texture half turned."""
    raw = {"from": [10, 10, 10], "to": [6, 6, 6],
           "faces": {f: {"uv": [0, 0, 4, 4], "texture": "#t"} for f in FACES}}
    unfolded, _ = models.unfold_negative(raw)
    assert len(unfolded) == 6
    planes = {next(iter(e["faces"])): (e["from"], e["to"]) for e in unfolded}
    # Java's north face sits on from.z = 10, the south wall, still facing north.
    assert planes["north"] == ([6.0, 6.0, 10.0], [10.0, 10.0, 10.0])
    assert planes["south"] == ([6.0, 6.0, 6.0], [10.0, 10.0, 6.0])
    assert planes["up"] == ([6.0, 6.0, 6.0], [10.0, 6.0, 10.0])
    assert planes["down"] == ([6.0, 10.0, 6.0], [10.0, 10.0, 10.0])
    assert planes["east"] == ([6.0, 6.0, 6.0], [6.0, 10.0, 10.0])
    assert planes["west"] == ([10.0, 6.0, 6.0], [10.0, 10.0, 10.0])
    for element in unfolded:
        (spec,) = element["faces"].values()
        assert spec["uv"] == [0, 0, 4, 4] and spec["rotation"] == 180


def test_two_swapped_axes_stay_one_box_with_textures_half_turned():
    """Two swaps are a half turn: every face still points out of the box."""
    raw = _raw((1, 1, 0))
    unfolded, _ = models.unfold_negative(raw)
    assert len(unfolded) == 1
    box = unfolded[0]
    assert box["from"] == [1.0, 2.0, 3.0] and box["to"] == [9.0, 12.0, 14.0]
    assert set(box["faces"]) == set(FACES)
    # north/south: both in-plane axes (x, y) swapped -> same facing, half turn
    assert box["faces"]["north"] == {"texture": "#t", "uv": UV, "rotation": 180}
    # declared up sits on to.y = 2 (the bottom) wound the other way: it is the down face
    assert box["faces"]["down"]["uv"] == UV


def test_a_face_without_uv_takes_the_uv_of_the_raw_corners():
    """BlockElement#fillUvs runs on the raw from/to, before anything is sorted."""
    raw = {"from": [4, 16, 4], "to": [12, 13, 12], "faces": {"north": {"texture": "#t"}}}
    unfolded, _ = models.unfold_negative(raw)
    (element,) = unfolded
    # y swapped: the north face's winding turns it south, on from.z = 4 (inward)
    assert element["from"] == [4.0, 13.0, 4.0] and element["to"] == [12.0, 16.0, 4.0]
    spec = element["faces"]["south"]
    # Java: north uv = [16 - to.x, 16 - to.y, 16 - from.x, 16 - from.y] = [4, 3, 12, 0]
    assert spec["uv"] == [4.0, 3.0, 12.0, 0.0] and spec["rotation"] == 180


def test_a_positive_element_comes_back_untouched():
    element = {"from": [0, 0, 0], "to": [16, 8, 16], "faces": {"up": {"texture": "#t"}}}
    unfolded, why = models.unfold_negative(element)
    assert why == "" and unfolded == [element] and unfolded[0] is element
    flat = {"from": [0, 8, 0], "to": [16, 8, 16], "faces": {"up": {"texture": "#t"}}}
    assert models.unfold_negative(flat)[0][0] is flat


def test_an_unknown_face_on_a_negative_element_is_refused():
    unfolded, why = models.unfold_negative({"from": [2, 0, 0], "to": [1, 1, 1], "faces": {"top": {}}})
    assert unfolded is None and "unknown 'top' face" in why


def test_geometry_no_longer_refuses_a_negative_element():
    geo, why = models.geometry({"elements": [_raw((0, 1, 0))]}, "geometry.x")
    assert why == ""
    cubes = geo["minecraft:geometry"][0]["bones"][0]["cubes"]
    assert all(min(c["size"]) >= 0 for c in cubes)
    # y swapped alone: all six faces point inward, so six planes
    assert len(cubes) == 6
    assert sum(1 for c in cubes for s in c["size"] if s == 0) == 6


def test_cube_itself_still_refuses_raw_negative_coordinates():
    """cube() is only ever handed unfolded elements; a raw one stays refused."""
    box, why = models.cube(_raw((1, 0, 0)))
    assert box is None and "negative size" in why


def test_uvlocked_turn_of_an_unfolded_element_is_refused():
    (element,) = models.unfold_negative(_raw((1, 1, 0)))[0]
    assert models.turn_y(element, 90, uvlock=True)[0] is None
    assert "negative-size" in models.turn_y(element, 90, uvlock=True)[1]
    assert models.turn_locked(element, 0, 90)[0] is None
    # no turn: nothing to re-map
    assert models.turn_y(element, 0, uvlock=True)[0] is element
    assert models.turn_locked(element, 0, 0)[0] is element
    # without uvlock the textures ride with the box, as for any element
    assert models.turn_rigid(element, 0, 90)[0] is not None
    assert models.turn_y(element, 90, uvlock=False)[0] is not None


def _mod(tmp_path, model):
    assets = tmp_path / "assets" / "examplemod"
    (assets / "blockstates").mkdir(parents=True)
    (assets / "models" / "block").mkdir(parents=True)
    (assets / "textures" / "block").mkdir(parents=True)
    (assets / "blockstates" / "basin.json").write_text(
        json.dumps({"variants": {"": {"model": "examplemod:block/basin"}}}))
    (assets / "models" / "block" / "basin.json").write_text(json.dumps(model))
    (assets / "textures" / "block" / "basin.png").write_bytes(b"png")
    return SourceMod(root=tmp_path, namespace="examplemod")


def test_a_block_with_an_interior_element_converts(tmp_path):
    """A basin: an outer box plus an inverted interior (the Refurbished pattern)."""
    model = {
        "textures": {"texture": "examplemod:block/basin"},
        "elements": [
            {"from": [2, 0, 2], "to": [14, 13, 14],
             "faces": {f: {"uv": [0, 0, 12, 13], "texture": "#texture"} for f in FACES}},
            {"from": [3, 13, 3], "to": [13, 4, 13],
             "faces": {f: {"uv": [0, 0, 10, 9], "texture": "#texture"}
                       for f in ("north", "east", "south", "west", "up")}},
        ],
    }
    result = blocks.convert(_mod(tmp_path, model))
    assert [u.reason for u in result.unhandled] == []
    geo = next(v for k, v in result.files.items() if k.startswith("models/blocks/") or "geometry" in k)
    cubes = geo["minecraft:geometry"][0]["bones"][0]["cubes"]
    assert len(cubes) == 1 + 5
    assert all(min(c["size"]) >= 0 for c in cubes)
    # y swapped alone: the interior's declared up face lies on to.y = 4 still
    # facing up, the floor seen from inside; Bedrock y = Java y.
    floor = [c for c in cubes if c["size"][1] == 0]
    assert len(floor) == 1 and floor[0]["origin"][1] == 4.0 and set(floor[0]["uv"]) == {"up"}
