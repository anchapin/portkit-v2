"""Rigid blockstate x/y turns baked in Java space (Big Chain)."""
from portkit.converters import models

FACES = ("up", "down", "north", "south", "east", "west")


def _element():
    return {"from": [4, 2, 7], "to": [12, 4, 9], "faces": {
        f: {"uv": [0, 0, 4, 4], "texture": "#t"} for f in FACES}}


def test_a_y_turn_agrees_with_the_seat_turn_read_in_game():
    element = _element()
    rigid, why = models.turn_rigid(element, 0, 90)
    assert why == ""
    seat, _ = models.turn_y(element, 90, False)
    assert rigid["from"] == seat["from"] and rigid["to"] == seat["to"]
    for face in FACES:
        assert int(rigid["faces"][face].get("rotation", 0)) == int(seat["faces"][face].get("rotation", 0)), face


def test_x_quarter_turn_lays_a_column_along_z():
    column = {"from": [7, 0, 7], "to": [9, 16, 9], "faces": {
        "north": {"uv": [0, 0, 2, 16], "texture": "#t"}}}
    turned, why = models.turn_rigid(column, 90, 0)
    assert why == ""
    assert turned["from"] == [7.0, 7.0, 0.0] and turned["to"] == [9.0, 9.0, 16.0]
    # x=90 sends north to down (Java dispenser facing=down).
    assert list(turned["faces"]) == ["down"]


def test_x_then_y_lays_a_column_along_x():
    column = {"from": [7, 0, 7], "to": [9, 16, 9], "faces": {}}
    turned, _ = models.turn_rigid(column, 90, 90)
    assert turned["from"] == [0.0, 7.0, 7.0] and turned["to"] == [16.0, 9.0, 9.0]


def test_the_faces_on_the_turn_axis_spin_in_place():
    turned, _ = models.turn_rigid(_element(), 90, 0)
    # Seen from the east, x=90 carries north (right) down: a clockwise quarter.
    assert turned["faces"]["east"]["rotation"] == 90
    assert turned["faces"]["west"]["rotation"] == 270


def test_existing_face_rotation_adds_up_and_cullface_follows():
    element = {"from": [0, 0, 0], "to": [16, 16, 16], "faces": {
        "up": {"uv": [0, 0, 16, 16], "texture": "#t", "rotation": 270, "cullface": "up"}}}
    turned, _ = models.turn_rigid(element, 90, 0)
    assert list(turned["faces"]) == ["north"]
    spec = turned["faces"]["north"]
    assert spec["cullface"] == "north"
    assert spec["rotation"] % 90 == 0


def test_rotated_elements_and_odd_turns_are_refused():
    tilted = {**_element(), "rotation": {"angle": 22.5, "axis": "y", "origin": [8, 8, 8]}}
    assert models.turn_rigid(tilted, 90, 0)[0] is None
    assert models.turn_rigid(_element(), 45, 0)[0] is None
