"""Blocks whose blockstate draws 6-way ``facing`` (DirectionalBlock) or
``face`` + horizontal ``facing`` (FaceAttachedHorizontalDirectionalBlock),
converted outside station runtimes: the placement rule read from
getStateForPlacement once per clicked face (else a labelled DEFAULT), mapped
onto Bedrock's minecraft:block_face / cardinal_direction / facing_direction
states; Java's x turn baked into the geometry (element rotations carried),
its y turn by minecraft:transformation; a box per variant from getShape.

The class files under tests/data/blockcode/classes are javac 21 output of the
example mod in tests/data/blockcode/src (DirBlocks.java, RodLampBlock,
VentBlock, SconceBlock, PlaqueBlock, StuckBlock, HeightBlock; rebuild with
build.sh): real compiler patterns, no Minecraft code.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from portkit import blockcode
from portkit.bytecode import ClassIndex
from portkit.converters import blocks, models
from portkit.model import SourceMod

from test_facing_boolean import NS, _png

CLASSES = Path(__file__).parent / "data" / "blockcode" / "classes"
SIX = ("down", "up", "north", "south", "west", "east")
KINDS = {"rod_lamp": "facing6", "vent": "facing6", "sconce": "attach", "plaque": "attach",
         "stuck_block": "facing6", "height_block": "facing6"}
# A model pointing up, turned to each facing (vanilla end rod's blockstate).
ROD_TURNS = {"up": (0, 0), "down": (180, 0), "north": (90, 0), "south": (90, 180),
             "west": (90, 270), "east": (90, 90)}
# A floor model, turned per face and facing (vanilla button's blockstate).
ATTACH_TURNS = {(f, d): ({"floor": 0, "wall": 90, "ceiling": 180}[f],
                         ({"north": 0, "east": 90, "south": 180, "west": 270}[d] + (180 if f == "ceiling" else 0)) % 360)
                for f in ("floor", "wall", "ceiling") for d in ("north", "east", "south", "west")}


@pytest.fixture(scope="module")
def readings():
    return blockcode.read_directional(ClassIndex.from_source(CLASSES), KINDS)


# --- reading ------------------------------------------------------------------

def test_clicked_face_rule(readings):
    rod = readings["rod_lamp"]
    assert rod.rule == {c: ("", ("dir", c)) for c in SIX}
    assert rod.rule_from == "com.example.deco.RodLampBlock#getStateForPlacement"
    assert not rod.support_assumed


def test_looking_rule(readings):
    assert readings["vent"].rule == {c: ("", ("look", True)) for c in SIX}


def test_vanilla_attach_rule_leans_on_support(readings):
    sconce = readings["sconce"]
    assert sconce.rule == blockcode.default_rule("attach")
    assert sconce.rule_from.startswith(
        "net.minecraft.world.level.block.FaceAttachedHorizontalDirectionalBlock#getStateForPlacement L39-52")
    assert sconce.support_assumed


def test_own_attach_rule(readings):
    plaque = readings["plaque"].rule
    assert plaque["up"] == ("floor", ("player", 2)) and plaque["down"] == ("ceiling", ("player", 2))
    assert plaque["north"] == ("wall", ("dir", "south"))


def test_conflict_and_unread(readings):
    assert "doesn't set facing" in readings["stuck_block"].rule_conflict
    height = readings["height_block"]
    assert height.rule is None and not height.rule_conflict and "clicking the down face" in height.rule_why


def test_shapes_per_variant(readings):
    rod = readings["rod_lamp"].shapes_by
    assert rod[("", "north")] == ((6.0, 6.0, 4.0, 10.0, 10.0, 16.0),)
    sconce = readings["sconce"].shapes_by
    # getConnectedDirection (vanilla, L64-70): ceiling -> DOWN, wall -> facing.
    assert sconce[("ceiling", "west")] == ((5.0, 8.0, 5.0, 11.0, 16.0, 11.0),)
    assert sconce[("wall", "east")] == ((0.0, 4.0, 5.0, 8.0, 12.0, 11.0),)
    assert readings["vent"].shape_from == "net.minecraft.world.level.block.DirectionalBlock#getShape (vanilla, inherited)"
    assert readings["rod_lamp"].collision is False


# --- blockstates and the Bedrock mapping ----------------------------------------

def _rod_states(model: str = f"{NS}:block/rod", uvlock: bool = False) -> dict:
    return {"variants": {f"facing={d}": {"model": model, **({"x": x} if x else {}), **({"y": y} if y else {}),
                                         **({"uvlock": True} if uvlock else {})}
                         for d, (x, y) in ROD_TURNS.items()}}


def _attach_states(model: str) -> dict:
    return {"variants": {f"face={f},facing={d}": {"model": model, **({"x": x} if x else {}), **({"y": y} if y else {})}
                         for (f, d), (x, y) in ATTACH_TURNS.items()}}


def test_variants_parse():
    kind, cells, why = blocks._directional_variants(_rod_states())
    assert (kind, why) == ("facing6", "") and cells[("", "west")] == (f"{NS}:block/rod", 90, 270, False)
    kind, cells, _ = blocks._directional_variants(_attach_states("m"))
    assert kind == "attach" and cells[("ceiling", "north")] == ("m", 180, 180, False)
    four = {"variants": {f"facing={d}": {"model": "m"} for d in ("north", "east", "south", "west")}}
    assert blocks._directional_variants(four) == (None, None, "")
    odd = _rod_states()
    odd["variants"]["facing=up"]["y"] = 45
    assert blocks._directional_variants(odd)[2] == "6-way facing: facing=up turns a model by other than a quarter turn"


def test_cells_drop_what_the_rule_ignores():
    # One rule for every clicked face: only the player's states matter.
    cells = blocks._bedrock_cells({c: ("", ("look", True)) for c in SIX})
    assert {conds for conds, _ in cells} == {(("minecraft:facing_direction", d),) for d in SIX}
    assert ((("minecraft:facing_direction", "up"),), ("", "down")) in cells
    plaque = blocks._bedrock_cells({**blockcode.default_rule("attach"), "up": ("floor", ("player", 2))})
    assert ((("minecraft:block_face", "up"), ("minecraft:cardinal_direction", "east")), ("floor", "west")) in plaque


def test_molang_collapses_full_faces():
    conds = [(("minecraft:block_face", "down"), ("minecraft:cardinal_direction", d))
             for d in ("north", "east", "south", "west")]
    assert blocks._molang(conds) == "q.block_state('minecraft:block_face') == 'down'"
    assert blocks._molang([(("minecraft:block_face", "up"), ("minecraft:cardinal_direction", "north"))]) == (
        "q.block_state('minecraft:block_face') == 'up' && q.block_state('minecraft:cardinal_direction') == 'north'")


# --- the geometry turn -------------------------------------------------------------

def _corners(element: dict) -> list[tuple]:
    a, b = element["from"], element["to"]
    pts = [(x, y, z) for x in (a[0], b[0]) for y in (a[1], b[1]) for z in (a[2], b[2])]
    rot = element.get("rotation")
    if not rot:
        return pts
    o = rot["origin"]
    t = math.radians(rot["angle"])
    i = "xyz".index(rot["axis"])
    out = []
    for p in pts:
        v = [p[k] - o[k] for k in range(3)]
        j, k = [(1, 2), (2, 0), (0, 1)][i]  # right-hand rule about the axis
        v[j], v[k] = v[j] * math.cos(t) - v[k] * math.sin(t), v[j] * math.sin(t) + v[k] * math.cos(t)
        out.append(tuple(v[m] + o[m] for m in range(3)))
    return out


def _java_turn_point(p, xq, yq):
    c = tuple(v - 8 for v in p)
    return tuple(v + 8 for v in models._turn_vector(c, xq, yq))


@pytest.mark.parametrize("x,y", [(90, 0), (180, 0), (270, 0), (90, 90), (90, 270), (270, 180)])
@pytest.mark.parametrize("axis,angle", [("x", 22.5), ("y", -45), ("z", 45)])
def test_rotated_elements_turn_where_java_puts_them(x, y, axis, angle):
    element = {"from": [3, 1, 5], "to": [9, 12, 7], "rotation": {"origin": [6, 4, 2], "axis": axis, "angle": angle},
               "faces": {"north": {"texture": "#a"}}}
    moved, why = models.turn_rigid(element, x, y, carry_rotation=True)
    assert why == ""
    want = sorted(tuple(round(v, 6) for v in _java_turn_point(p, x // 90, y // 90)) for p in _corners(element))
    got = sorted(tuple(round(v, 6) for v in p) for p in _corners(moved))
    assert got == want
    # Without carry_rotation, as before.
    assert models.turn_rigid(element, x, y)[0] is None


# --- conversion ------------------------------------------------------------------

def _rod_model() -> dict:
    faces = {f: {"texture": "#all"} for f in SIX}
    return {"textures": {"all": f"{NS}:block/wood", "particle": f"{NS}:block/wood"},
            "elements": [{"from": [6, 0, 6], "to": [10, 12, 10], "faces": faces},
                         {"from": [7, 12, 7], "to": [9, 14, 9], "faces": faces,
                          "rotation": {"origin": [8, 13, 8], "axis": "y", "angle": 22.5}}]}


def _sconce_model() -> dict:
    faces = {f: {"texture": "#all"} for f in SIX}
    return {"textures": {"all": f"{NS}:block/wood"},
            "elements": [{"from": [5, 0, 5], "to": [11, 8, 11], "faces": faces}]}


def _mod(tmp_path: Path) -> SourceMod:
    root = tmp_path / "mod"
    for sub in ("textures/block", "models/block", "blockstates"):
        (root / f"assets/{NS}/{sub}").mkdir(parents=True)
    (root / f"assets/{NS}/textures/block/wood.png").write_bytes(_png())
    (root / f"assets/{NS}/models/block/rod.json").write_text(json.dumps(_rod_model()))
    (root / f"assets/{NS}/models/block/sconce.json").write_text(json.dumps(_sconce_model()))
    states = {"rod_lamp": _rod_states(), "vent": _rod_states(), "height_block": _rod_states(),
              "stuck_block": _rod_states(), "sconce": _attach_states(f"{NS}:block/sconce"),
              "plaque": _attach_states(f"{NS}:block/sconce")}
    for name, bs in states.items():
        (root / f"assets/{NS}/blockstates/{name}.json").write_text(json.dumps(bs))
    return SourceMod(root=root, namespace=NS, classes=ClassIndex.from_source(CLASSES))


@pytest.fixture()
def converted(tmp_path):
    return blocks.convert(_mod(tmp_path))


def _block(result, name):
    return result.files[f"blocks/{name}.json"]["minecraft:block"]


def test_rod_lamp_on_block_face(converted):
    rod = _block(converted, "rod_lamp")
    assert rod["description"]["traits"] == {"minecraft:placement_position": {"enabled_states": ["minecraft:block_face"]}}
    vis = rod["components"]["minecraft:geometry"]["bone_visibility"]
    assert vis["m0_x0"] == "q.block_state('minecraft:block_face') == 'up'"
    assert vis["m0_x180"] == "q.block_state('minecraft:block_face') == 'down'"
    perms = {p["condition"]: p["components"] for p in rod["permutations"]}
    west = perms["q.block_state('minecraft:block_face') == 'west'"]
    assert west["minecraft:transformation"] == {"rotation": [0, 90, 0]}
    # No collision (noCollission); getShape in the model's frame equals the
    # x-turned model's bounds at every facing.
    assert west["minecraft:collision_box"] is False
    assert west["minecraft:selection_box"] == {"origin": [-2, 6, -4], "size": [4, 4, 12]}


def test_box_and_geometry_agree(readings):
    model = _rod_model()["elements"][:1]
    for d, (x, y) in ROD_TURNS.items():
        bounds = blocks._element_bounds([models.turn_rigid(e, x, 0, carry_rotation=True)[0] for e in model])
        world = blocks._bbox(readings["rod_lamp"].shapes_by[("", d)])
        assert blocks._java_turn(world, 360 - y) == bounds, d


def test_vent_faces_the_player(converted):
    vent = _block(converted, "vent")
    assert vent["description"]["traits"] == {
        "minecraft:placement_direction": {"enabled_states": ["minecraft:facing_direction"]}}
    vis = vent["components"]["minecraft:geometry"]["bone_visibility"]
    # Looking down places it facing up (the opposite).
    assert vis["m0_x0"] == "q.block_state('minecraft:facing_direction') == 'down'"


def test_sconce_attach(converted):
    sconce = _block(converted, "sconce")
    traits = sconce["description"]["traits"]
    assert traits["minecraft:placement_position"] == {"enabled_states": ["minecraft:block_face"]}
    assert traits["minecraft:placement_direction"] == {"enabled_states": ["minecraft:cardinal_direction"]}
    vis = sconce["components"]["minecraft:geometry"]["bone_visibility"]
    assert set(vis) == {"m0_x0", "m0_x90", "m0_x180"}
    conds = [p["condition"] for p in sconce["permutations"]]
    assert ("q.block_state('minecraft:block_face') == 'up' && "
            "q.block_state('minecraft:cardinal_direction') == 'east'") in conds
    assert "q.block_state('minecraft:block_face') == 'east'" in conds


def test_residue_and_notes(converted):
    reasons = {u.source.rsplit("/", 1)[-1]: u.reason for u in converted.unhandled}
    assert "stuck_block.json" in reasons and "doesn't set facing" in reasons["stuck_block.json"]
    notes = " ".join(converted.notes)
    assert "6-way facing placement DEFAULT" in notes and "height_block" in notes
    assert "Support is not emulated" in notes and "sconce" in notes
    assert "com.example.deco.PlaqueBlock#getStateForPlacement" in notes
    assert "blocks/height_block.json" in converted.files
