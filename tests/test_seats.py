"""Seat-shaped multiparts, textures that turn with the box, and face rotation (#68)."""
from portkit import pack
from portkit.converters import blocks, models

SEAT = {
    "from": [0, 4, 4],
    "to": [16, 7, 12],
    "faces": {
        "up": {"uv": [0, 0, 16, 8], "texture": "#texture"},
        "down": {"uv": [0, 0, 16, 8], "texture": "#texture"},
        "north": {"uv": [0, 9, 16, 12], "texture": "#texture"},
        "west": {"uv": [4, 9, 12, 12], "texture": "#texture"},
    },
}


def _seat_state():
    parts = [
        {"apply": {"model": "m:seat", **({"y": y} if y else {})}, "when": {"facing": d}}
        for d, y in (("north", 0), ("east", 90), ("south", 180), ("west", 270))
    ]
    parts += [
        {"apply": {"model": "m:seat_post"}, "when": {"attached": "true"}},
        {"apply": {"model": "m:seat_top_post"}, "when": {"post": "true"}},
    ]
    return {"multipart": parts}


def test_a_turn_without_uvlock_carries_the_textures_round():
    turned, why = models.turn_y(SEAT, 90, uvlock=False)
    assert why == ""
    assert turned["from"] == [4, 4, 0] and turned["to"] == [12, 7, 16]
    # The north face's own uv now sits on the east face, unchanged.
    assert turned["faces"]["east"]["uv"] == [0, 9, 16, 12]
    # Top clockwise seen from above; bottom the same turn, seen from below.
    assert turned["faces"]["up"]["rotation"] == 90
    assert turned["faces"]["down"]["rotation"] == 270


def test_top_and_bottom_rotation_reach_bedrock_as_uv_rotation():
    element = {"from": [0, 0, 0], "to": [16, 1, 16], "faces": {
        "up": {"uv": [0, 0, 16, 16], "texture": "#t", "rotation": 90},
        "down": {"uv": [0, 0, 16, 16], "texture": "#t", "rotation": 270},
    }}
    box, why = models.cube(element)
    assert why == ""
    assert box["uv"]["up"]["uv_rotation"] == 90
    assert box["uv"]["down"]["uv_rotation"] == 270


def test_a_side_face_rotation_is_refused_not_dropped():
    element = {"from": [0, 0, 0], "to": [16, 16, 16], "faces": {
        "north": {"uv": [0, 0, 16, 16], "texture": "#t", "rotation": 90}}}
    box, why = models.cube(element)
    assert box is None and "side face" in why


def test_turned_geometry_moves_to_the_newer_format_and_lifts_the_floor():
    geo, _ = models.geometry_bones([("a", [models.turn_y(SEAT, 90, False)[0]])], "geometry.t")
    assert geo["format_version"] == "1.21.0"
    plain, _ = models.geometry_bones([("a", [SEAT])], "geometry.t")
    assert plain["format_version"] == "1.16.0"
    assert pack.engine_floor({"models/blocks/t.geo.json": geo}) == (1, 21, 0)


def test_the_seat_shape_is_recognised_and_its_extras_named():
    model, uvlock, dropped = blocks._facing_parts(_seat_state())
    assert model == "m:seat" and uvlock is False
    assert dropped == [("attached", "m:seat_post"), ("post", "m:seat_top_post")]


def test_an_extra_gated_on_anything_but_true_is_not_a_seat():
    state = _seat_state()
    state["multipart"][-1]["when"] = {"post": "false"}
    assert blocks._facing_parts(state)[0] is None
