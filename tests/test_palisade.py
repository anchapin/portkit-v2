"""Fence-shaped multiparts and the per-pack engine floor."""
import pytest

from portkit import pack
from portkit.converters import blocks, models

SIDE = {
    "from": [5, 0, 0],
    "to": [11, 16, 5],
    "faces": {f: {"texture": "#side"} for f in ("down", "up", "north", "south", "west", "east")},
}


def _palisade(**overrides):
    parts = [{"apply": {"model": "m:post"}}]
    for d, y in (("north", 0), ("east", 90), ("south", 180), ("west", 270)):
        parts.append({"apply": {"model": "m:side", "y": y, "uvlock": True}, "when": {d: "true"}})
    return {"multipart": parts, **overrides}


def test_a_quarter_turn_sends_the_north_side_east():
    turned, why = models.turn_y(SIDE, 90, uvlock=True)
    assert why == ""
    assert turned["from"] == [11, 0, 5] and turned["to"] == [16, 16, 11]
    # The face that pointed north now points east, and wears the uv of where it landed.
    assert turned["faces"]["east"]["uv"] == models.auto_uv("east", [11, 0, 5], [16, 16, 11])


def test_four_quarter_turns_come_home():
    element = SIDE
    for _ in range(4):
        element, _ = models.turn_y(element, 90, uvlock=True)
    assert element["from"] == SIDE["from"] and element["to"] == SIDE["to"]


@pytest.mark.parametrize("change, phrase", [
    ({"rotation": {"angle": 22.5, "axis": "y", "origin": [8, 8, 8]}}, "themselves rotated"),
    ({"faces": {"up": {"uv": [1, 0, 0, 1], "texture": "#side"}}}, "differently before MC 1.21.5"),
])
def test_turns_we_cannot_state_exactly_are_refused(change, phrase):
    turned, why = models.turn_y({**SIDE, **change}, 90, uvlock=True)
    assert turned is None and phrase in why


def test_the_palisade_shape_is_recognised():
    assert blocks._palisade_parts(_palisade()) == ("m:post", "m:side", True)


def test_a_side_turned_the_wrong_way_is_not_a_palisade():
    state = _palisade()
    state["multipart"][1]["apply"]["y"] = 180
    assert blocks._palisade_parts(state)[0] is None


def test_other_multiparts_are_refused_naming_their_states():
    seat = {"multipart": [
        {"apply": {"model": "m:seat"}, "when": {"facing": "north"}},
        {"apply": {"model": "m:post"}, "when": {"attached": "true"}},
    ]}
    reason = blocks._multipart_reason(seat)
    # The states are named with the values they take, not only by name (#56).
    assert "2 part(s) keyed on attached=true, facing=north" in reason


def _seat_multipart():
    """A seat-shaped multipart: a model per facing, plus an attached part."""
    parts = []
    for d, y in (("north", 0), ("east", 90), ("south", 180), ("west", 270)):
        parts.append({"apply": {"model": "m:seat", "y": y}, "when": {"facing": d}})
    parts.append({"apply": {"model": "m:post"}, "when": {"attached": "true"}})
    return {"multipart": parts}


def _wall_multipart():
    """A vanilla-wall-shaped multipart: a post, and a low and tall side per direction."""
    parts = [{"apply": {"model": "m:post"}, "when": {"up": "true"}}]
    for d, y in (("north", 0), ("east", 90), ("south", 180), ("west", 270)):
        for height in ("low", "tall"):
            parts.append({"apply": {"model": f"m:side-{height}", "y": y}, "when": {d: height}})
    return {"multipart": parts}


def _pane_multipart():
    """A connection-shaped multipart: a post, and a side per direction."""
    parts = [{"apply": {"model": "m:post"}}]
    for d, y in (("north", 0), ("east", 90), ("south", 180), ("west", 270)):
        parts.append({"apply": {"model": "m:side", "y": y}, "when": {d: "true"}})
        parts.append({"apply": {"model": "m:noside", "y": y}, "when": {d: "false"}})
    return {"multipart": parts}


def test_a_seat_shaped_multipart_is_refused_naming_its_shape_and_values():
    reason = blocks._multipart_reason(_seat_multipart())
    assert "shape: seat-shaped" in reason
    assert "keyed on attached=true, facing=east|north|south|west" in reason


def test_a_fence_shaped_multipart_is_refused_naming_its_shape_and_values():
    reason = blocks._multipart_reason(_palisade())
    assert "shape: fence-shaped" in reason
    assert "keyed on east=true, north=true, south=true, west=true" in reason


def test_a_wall_shaped_multipart_is_refused_naming_its_shape_and_values():
    reason = blocks._multipart_reason(_wall_multipart())
    assert "shape: wall-shaped" in reason
    assert "keyed on east=low|tall, north=low|tall, south=low|tall, up=true, west=low|tall" in reason


def test_a_connection_shaped_multipart_is_refused_naming_its_shape_and_values():
    reason = blocks._multipart_reason(_pane_multipart())
    assert "shape: connection-shaped" in reason
    assert "keyed on east=false|true, north=false|true, south=false|true, west=false|true" in reason


def test_a_multipart_no_detector_reads_says_so():
    state = {"multipart": [
        {"apply": {"model": "m:a"}, "when": {"lit": "true"}},
        {"apply": {"model": "m:b"}, "when": {"facing": "north"}},
    ]}
    reason = blocks._multipart_reason(state)
    assert "shape: unrecognised shape" in reason
    assert "keyed on facing=north, lit=true" in reason


def test_a_connection_multipart_that_names_no_model_says_which_shape_it_is():
    state = {"multipart": [
        {"apply": {"model": "m:a"}},
        {"apply": {"y": 90}, "when": {"north": "true"}},
    ]}
    parts, why = blocks._connection_parts(state)
    assert parts is None
    assert "connection multipart: a part names no model" in why
    assert "shape: connection-shaped" in why
    assert "keyed on north=true" in why


def test_the_floor_stays_low_without_a_newer_block():
    files = {"blocks/a.json": {"format_version": "1.20.20"}, "textures/x.png": b""}
    assert pack.engine_floor(files) == (1, 20, 20)


def test_one_newer_block_lifts_the_whole_pack():
    files = {"blocks/a.json": {"format_version": "1.20.20"},
             "blocks/p.json": {"format_version": "1.26.0"}}
    assert pack.engine_floor(files) == (1, 26, 0)
