"""uvlock re-maps a hand-set uv as Java does (#236, FaceBakery#recomputeUVs).

tests/data/uvlock_java.json holds the per-vertex uvs the MC 1.21.1 and 1.21.8
client jars bake, read by running them in a JVM (see its "about")."""
import json
from pathlib import Path

import pytest

from portkit.converters import models

DATA = json.loads((Path(__file__).parent / "data" / "uvlock_java.json").read_text())
CASES = DATA["cases"]


def _close(a, b):
    return all(abs(p - q) < 1e-2 for pa, pb in zip(a, b) for p, q in zip(pa, pb))


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c['face']}-x{c['x']}y{c['y']}-{c['uv']}-r{c['rotation']}")
def test_the_port_matches_java(case):
    found, why = models.uvlock_uv(case["face"], case["uv"], case["rotation"], case["x"], case["y"])
    agree = _close(case["v1_21_1"], case["v1_21_8"])
    if not agree:
        assert found is None and "differently in MC 1.20.1/1.21.1" in why
        return
    uv, rotation = found
    assert _close(models._uv_vertices(uv, rotation), case["v1_21_1"])


def test_most_plain_uvs_are_taken():
    plain = [c for c in CASES if c["rotation"] == 0 and c["uv"] in ([5, 6, 11, 10], [13, 15, 2, 1])]
    assert plain and all(models.uvlock_uv(c["face"], c["uv"], 0, c["x"], c["y"])[0] for c in plain)


def test_a_mirrored_uv_java_versions_disagree_on_is_refused():
    found, why = models.uvlock_uv("up", [1, 0, 0, 1], 0, 0, 90)
    assert found is None and "MC 1.21.8" in why


def test_a_position_derived_uv_lands_as_the_position_derived_uv_there():
    # Java's own uvlock of an auto uv equals the auto uv where the face lands.
    for x in (0, 90, 180, 270):
        for y in (0, 90, 180, 270):
            for face in models._FACE_NORMAL:
                start, end = [2.0, 3.0, 5.0], [9.0, 12.0, 14.0]
                uv = models.auto_uv(face, start, end)
                (new_uv, rot), _ = models.uvlock_uv(face, uv, 0, x, y)
                moved, _ = models.turn_rigid({"from": start, "to": end, "faces": {face: {"uv": uv}}}, x, y)
                target, turn = models._rigid_face_turn(face, x // 90, y // 90)
                assert models._uv_vertices(new_uv, (rot + turn) % 360) == \
                    models._uv_vertices(models.auto_uv(target, moved["from"], moved["to"]), 0)


def test_a_vanilla_button_face_turns_with_uvlock():
    # minecraft:block/button's up face is uv [5, 6, 11, 10] on a box
    # from [5, 0, 6] to [11, 2, 10]; a wall button turns it x=90.
    element = {"from": [5, 0, 6], "to": [11, 2, 10], "faces": {
        "up": {"uv": [5, 10, 11, 6], "texture": "#t"},
        "north": {"uv": [5, 14, 11, 16], "texture": "#t"}}}
    turned, why = models.turn_locked(element, 90, 0)
    assert why == "" and turned is not None
    assert set(turned["faces"]) == {"north", "down"}
    # Each landed face shows what Java bakes there (the port's own answer).
    for face, spec in (("up", element["faces"]["up"]), ("north", element["faces"]["north"])):
        (uv, rot), _ = models.uvlock_uv(face, spec["uv"], 0, 90, 0)
        target, turn = models._rigid_face_turn(face, 1, 0)
        got = turned["faces"][target]
        assert models._uv_vertices(got["uv"], got.get("rotation", 0)) == \
            models._uv_vertices(uv, (rot + turn) % 360)


def test_a_texture_turned_face_is_still_refused_by_turn_locked():
    element = {"from": [0, 0, 0], "to": [16, 8, 16],
               "faces": {"north": {"texture": "#s", "uv": [0, 0, 4, 4], "rotation": 90}}}
    turned, why = models.turn_locked(element, 0, 90)
    assert turned is None and "turns its texture" in why


def test_turn_y_maps_a_hand_set_uv():
    element = {"from": [0, 0, 7], "to": [16, 16, 9],
               "faces": {"north": {"texture": "#s", "uv": [0, 0, 4, 4], "cullface": "north"}}}
    turned, why = models.turn_y(element, 90, True)
    assert why == "" and turned["faces"]["east"]["uv"] == [0, 0, 4, 4]
    assert turned["faces"]["east"]["cullface"] == "north"  # turn_y leaves cullface as it was
