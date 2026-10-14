"""Facing-only blocks outside the station runtimes: placement and box read
from the jar's bytecode (portkit.blockcode), else a documented default.

The class files under tests/data/blockcode/classes are javac 21 output of the
example mod in tests/data/blockcode/src (rebuild with build.sh): real
compiler patterns, no Minecraft code.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from portkit import blockcode
from portkit.bytecode import ClassIndex, instructions, parse
from portkit.converters import blocks, models
from portkit.model import SourceMod

CLASSES = Path(__file__).parent / "data" / "blockcode" / "classes"
CARDINALS = ("north", "east", "south", "west")


@pytest.fixture(scope="module")
def index() -> ClassIndex:
    return ClassIndex.from_source(CLASSES)


@pytest.fixture(scope="module")
def readings(index):
    return blockcode.read_blocks(index, ["lamp", "statue", "vase", "odd", "fan", "ghost"])


# --- the class-file reader ---------------------------------------------------

def test_parses_javac_output(index):
    cf = index.get("com/example/deco/LampBlock")
    assert cf.super_name == "net/minecraft/world/level/block/HorizontalDirectionalBlock"
    shape = cf.method("getShape")
    ops = [i.name for i in instructions(cf, shape.code)]
    assert "tableswitch" in ops or "lookupswitch" in ops
    assert ops[-1] == "areturn"


def test_rejects_non_class_bytes():
    with pytest.raises(Exception):
        parse(b"not a class file at all")


# --- reading the code ---------------------------------------------------------

def test_lambda_registration_switch_shape_no_collision(readings):
    lamp = readings["lamp"]
    assert lamp.cls == "com.example.deco.LampBlock"
    # defaultBlockState().setValue(FACING, ctx.getHorizontalDirection().getOpposite())
    assert lamp.placement == 180
    assert lamp.placement_from == "com.example.deco.LampBlock#getStateForPlacement"
    # The enum switch, through its synthetic $SwitchMap class; default arm is north.
    assert lamp.shapes["east"] == ((0.0, 0.0, 4.0, 6.0, 12.0, 12.0),)
    assert lamp.shapes["north"] == ((4.0, 0.0, 10.0, 12.0, 4.0, 16.0), (5.0, 4.0, 11.0, 11.0, 12.0, 15.0))
    # Properties.of().noCollission()
    assert lamp.collision is False
    assert lamp.states == ("facing",)


def test_constructor_reference_stream_fold_and_undecided_branch(readings):
    statue = readings["statue"]
    # ctx.getHorizontalDirection() as is, behind a waterlogged branch on the
    # fluid that can't be decided: both ways agree, so it counts.
    assert statue.placement == 0
    shape = ((2.0, 0.0, 2.0, 14.0, 2.0, 14.0), (5.0, 2.0, 5.0, 11.0, 20.0, 11.0))
    assert all(statue.shapes[d] == shape for d in CARDINALS)
    assert statue.collision is True
    assert statue.states == ("facing", "waterlogged")


def test_static_enum_map_and_copied_properties(readings):
    vase = readings["vase"]
    assert vase.placement == 180
    assert vase.shapes["east"] == ((0.0, 0.0, 0.0, 8.0, 16.0, 16.0),)
    # Properties.ofFullCopy(Blocks.STONE): whether it collides is stone's.
    assert vase.collision is None and "copy a vanilla block" in vase.collision_why


def test_unknown_code_is_unread_with_a_reason(readings):
    odd = readings["odd"]
    assert odd.shapes is None and "not built from boxes" in odd.shape_why
    # No getStateForPlacement of its own: facing stays the default, which
    # Bedrock's placement trait can't give -> a conflict, not a default.
    assert odd.placement is None and odd.placement_conflict
    fan = readings["fan"]
    assert fan.placement is None and "quarter turn" in fan.placement_conflict
    ghost = readings["ghost"]
    assert ghost.cls is None and "no registration" in ghost.placement_why


def test_no_classes_means_unread():
    readings = blockcode.read_blocks(ClassIndex({}), ["lamp"])
    assert readings["lamp"].placement is None
    assert readings["lamp"].placement_why == "the mod ships no class files"


# --- converting ----------------------------------------------------------------

def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body) if not isinstance(body, str) else body)


def _mod(tmp_path: Path, classes: bool = True) -> SourceMod:
    root = tmp_path / "mod"
    ns = "examplemod"
    tex = {"all": f"{ns}:block/wood", "particle": f"{ns}:block/wood"}
    (root / f"assets/{ns}/textures/block").mkdir(parents=True)
    (root / f"assets/{ns}/textures/block/wood.png").write_bytes(_solid_png())
    plain = {"textures": tex, "elements": [
        {"from": [4, 0, 10], "to": [12, 4, 16],
         "faces": {f: {"texture": "#all"} for f in ("north", "south", "east", "west", "up", "down")}},
        {"from": [5, 4, 11], "to": [11, 12, 15],
         "faces": {f: {"texture": "#all"} for f in ("north", "south", "east", "west", "up", "down")}},
    ]}
    rotated = {"textures": tex, "elements": [
        {"from": [2, 0, 2], "to": [14, 2, 14],
         "faces": {f: {"texture": "#all"} for f in ("north", "south", "east", "west", "up", "down")}},
        {"from": [6, 2, 3], "to": [10, 12, 7], "rotation": {"angle": 22.5, "axis": "x", "origin": [8, 2, 5]},
         "faces": {f: {"texture": "#all"} for f in ("north", "south", "east", "west", "up", "down")}},
    ]}
    for name, model in (("lamp", plain), ("statue", rotated), ("vase", plain), ("odd", plain),
                        ("fan", plain), ("ghost", rotated)):
        _write(root, f"assets/{ns}/models/block/{name}.json", model)
    def states(name, turns=(0, 90, 180, 270), uvlock=False):
        out = {}
        for d, t in zip(CARDINALS, turns):
            out[f"facing={d}"] = {"model": f"{ns}:block/{name}", **({"y": t} if t else {}),
                                  **({"uvlock": True} if uvlock else {})}
        return out

    _write(root, f"assets/{ns}/blockstates/lamp.json", {"variants": states("lamp")})
    # The model faces south: Java turns it 180 more at every facing.
    _write(root, f"assets/{ns}/blockstates/statue.json", {"variants": states("statue", (180, 270, 0, 90))})
    _write(root, f"assets/{ns}/blockstates/vase.json", {"variants": states("vase", uvlock=True)})
    for name in ("odd", "fan", "ghost"):
        _write(root, f"assets/{ns}/blockstates/{name}.json", {"variants": states(name)})
    return SourceMod(root=root, namespace=ns, classes=ClassIndex.from_source(CLASSES) if classes else None)


def _solid_png() -> bytes:
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    raw = b"".join(b"\x00" + b"\x80\x60\x40\xff" * 16 for _ in range(16))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


@pytest.fixture
def converted(tmp_path):
    mod = _mod(tmp_path)
    return mod, blocks.convert(mod)


def _block(result, name):
    return result.files[f"blocks/{name}.json"]["minecraft:block"]


def _perm(block, facing):
    for p in block.get("permutations", []):
        if p["condition"] == f"q.block_state('minecraft:cardinal_direction') == '{facing}'":
            return p["components"]
    return {}


def test_read_placement_and_boxes_land_in_the_definition(converted):
    _, result = converted
    lamp = _block(result, "lamp")
    trait = lamp["description"]["traits"]["minecraft:placement_direction"]
    assert trait == {"enabled_states": ["minecraft:cardinal_direction"], "y_rotation_offset": 180}
    # Java's north shape bounds x 4-12, z 10-16; the model is the north one,
    # so every facing's box is that box in the model's frame: one box.
    expected = blocks._bedrock_box((4.0, 0.0, 10.0, 12.0, 12.0, 16.0))
    assert lamp["components"]["minecraft:selection_box"] == expected
    assert lamp["components"]["minecraft:collision_box"] is False  # noCollission
    assert _perm(lamp, "east")["minecraft:transformation"] == {"rotation": [0, -90, 0]}
    assert "minecraft:transformation" not in _perm(lamp, "north")


def test_player_facing_rule_gets_offset_zero(converted):
    _, result = converted
    statue = _block(result, "statue")
    trait = statue["description"]["traits"]["minecraft:placement_direction"]
    assert "y_rotation_offset" not in trait
    # Java's shape is the same in the world at every facing (and reaches y 20,
    # cut to the block). In the turned model's frame that is one box again,
    # since the shape is centred.
    box = statue["components"]["minecraft:selection_box"]
    assert box == blocks._bedrock_box((2.0, 0.0, 2.0, 14.0, 16.0, 14.0))


def test_uvlocked_model_gets_bones_and_world_boxes(converted):
    _, result = converted
    vase = _block(result, "vase")
    geometry = vase["components"]["minecraft:geometry"]
    assert set(geometry["bone_visibility"]) == {f"facing_{d}" for d in CARDINALS}
    assert not any("minecraft:transformation" in p["components"] for p in vase.get("permutations", []))
    # Shape per facing from the static map; no transformation, so world boxes.
    assert _perm(vase, "east")["minecraft:selection_box"] == blocks._bedrock_box((0, 0, 0, 8, 16, 16))
    assert _perm(vase, "north")["minecraft:selection_box"] == blocks._bedrock_box((0, 0, 8, 16, 16, 16))


def test_conflicting_placement_stays_residue(converted):
    _, result = converted
    assert "blocks/fan.json" not in result.files
    assert "blocks/odd.json" not in result.files
    reasons = {u.source.rsplit("/", 1)[-1]: u.reason for u in result.unhandled}
    assert "quarter turn" in reasons["fan.json"]
    assert "default facing" in reasons["odd.json"]


def test_unregistered_block_takes_every_default_and_says_so(converted):
    _, result = converted
    ghost = _block(result, "ghost")
    assert ghost["description"]["traits"]["minecraft:placement_direction"]["y_rotation_offset"] == 180
    # Default box: the model's element bounds, rotation ignored (x 2-14, y 0-12, z 2-14).
    assert ghost["components"]["minecraft:selection_box"] == blocks._bedrock_box((2, 0, 2, 14, 12, 14))
    assert ghost["components"]["minecraft:collision_box"] == ghost["components"]["minecraft:selection_box"]
    notes = "\n".join(result.notes)
    assert "Facing placement DEFAULT, not read from code" in notes
    assert "no registration of this block was found in the mod's classes: ghost" in notes
    assert "Facing box DEFAULT" in notes and "Facing collision DEFAULT" in notes


def test_notes_cite_class_and_method_for_read_values(converted):
    _, result = converted
    notes = "\n".join(result.notes)
    assert "com.example.deco.LampBlock#getStateForPlacement (y_rotation_offset 180): lamp" in notes
    assert "com.example.deco.StatueBlock#getStateForPlacement (y_rotation_offset 0): statue" in notes
    assert "com.example.deco.LampBlock#getShape: lamp" in notes
    assert "No collision, read from bytecode" in notes and "lamp" in notes
    assert "waterlogged" in notes  # a code state the blockstate doesn't draw
    assert "reaches outside the block" in notes and "statue" in notes


def test_without_classes_every_block_is_default(tmp_path):
    result = blocks.convert(_mod(tmp_path, classes=False))
    for name in ("lamp", "statue", "vase", "odd", "fan", "ghost"):
        assert f"blocks/{name}.json" in result.files
    notes = "\n".join(result.notes)
    assert "the mod ships no class files" in notes
    assert "read from bytecode" not in notes


def test_station_blocks_keep_their_own_path(tmp_path):
    from portkit.converters.stations import FacingBlock
    mod = _mod(tmp_path)
    station = FacingBlock("lamp", 180, {"origin": [-8, 0, -8], "size": [16, 16, 16]}, ("cited",))
    result = blocks.convert(mod, stations={"lamp": station})
    lamp = _block(result, "lamp")
    assert "bone_visibility" in lamp["components"]["minecraft:geometry"]
    assert not any("cutting_board" in n for n in result.notes)
    assert all(": lamp" not in n for n in result.notes if "Facing" in n)


# --- geometry, checked numerically --------------------------------------------
#
# Java places facing d by turning the whole model (every element, its own
# rotation included) clockwise by the variant's y. Bedrock draws the one
# geometry turned by the permutation's minecraft:transformation. With the
# repo's conventions (models.X_AXIS_IS_FLIPPED, PIVOT_IS_MIRRORED,
# ROTATION_SIGN: a geometry cube decodes back to the Java element it came
# from) and transformation's y rotation as a right-handed turn about +y in
# world space (x east, z south; -90 takes north to east, _BEDROCK_Y_TURN),
# both must put every corner of every element in the same place.

def _corners(frm, to):
    return [(x, y, z) for x in (frm[0], to[0]) for y in (frm[1], to[1]) for z in (frm[2], to[2])]


def _rotate_axis(point, axis, degrees, origin):
    a = math.radians(degrees)
    p = [point[i] - origin[i] for i in range(3)]
    i, j = {"x": (1, 2), "y": (2, 0), "z": (0, 1)}[axis]
    pi, pj = p[i], p[j]
    p[i], p[j] = pi * math.cos(a) - pj * math.sin(a), pi * math.sin(a) + pj * math.cos(a)
    return tuple(p[k] + origin[k] for k in range(3))


def _java_world(element, y_turn):
    pts = _corners(element["from"], element["to"])
    rot = element.get("rotation")
    if rot:
        pts = [_rotate_axis(p, rot["axis"], rot["angle"], rot["origin"]) for p in pts]
    # Blockstate y: clockwise from above, about the block centre: (x, z) -> (16 - z, x).
    for _ in range((y_turn // 90) % 4):
        pts = [(16 - z, y, x) for x, y, z in pts]
    return sorted((round(x, 6), round(y, 6), round(z, 6)) for x, y, z in pts)


def _decode(cube):
    """The Java element a geometry cube was written from (inverse of models.cube)."""
    ox, oy, oz = cube["origin"]
    sx, sy, sz = cube["size"]
    x2 = 8 - ox if models.X_AXIS_IS_FLIPPED else ox + sx + 8
    element = {"from": [x2 - sx, oy, oz + 8], "to": [x2, oy + sy, oz + sz + 8]}
    if any(cube.get("rotation") or ()):
        axis = next(a for a, v in zip("xyz", cube["rotation"]) if v)
        angle = cube["rotation"]["xyz".index(axis)] / models.ROTATION_SIGN[axis]
        px, py, pz = cube["pivot"]
        element["rotation"] = {"axis": axis, "angle": angle,
                               "origin": [8 - px if models.PIVOT_IS_MIRRORED else px + 8, py, pz + 8]}
    return element


def _bedrock_world(element, transformation_y):
    pts = _java_world(element, 0)
    a = math.radians(transformation_y)
    out = []
    for x, y, z in pts:
        u, w = x - 8, z - 8
        out.append((u * math.cos(a) + w * math.sin(a) + 8, y, -u * math.sin(a) + w * math.cos(a) + 8))
    return sorted((round(x, 6), round(y, 6), round(z, 6)) for x, y, z in out)


def test_transformation_places_rotated_elements_where_java_does(converted):
    mod, result = converted
    model = json.loads((mod.assets / "models/block/statue.json").read_text())
    turns = dict(zip(CARDINALS, (180, 270, 0, 90)))
    geo = result.files["models/blocks/statue.geo.json"]["minecraft:geometry"][0]
    cubes = [c for bone in geo["bones"] for c in bone["cubes"]]
    statue = _block(result, "statue")
    for facing in CARDINALS:
        rotation = (_perm(statue, facing).get("minecraft:transformation") or {"rotation": [0, 0, 0]})["rotation"][1]
        java = sorted(p for e in model["elements"] for p in _java_world(e, turns[facing]))
        bedrock = sorted(p for c in cubes for p in _bedrock_world(_decode(c), rotation))
        assert java == bedrock, facing


def test_boxes_turn_back_to_java_world_boxes():
    # A box per facing in the model's frame, turned by the facing's
    # transformation, is Java's world box again.
    world = {"north": (4, 0, 10, 12, 12, 16), "east": (0, 0, 4, 6, 12, 12),
             "south": (4, 0, 0, 12, 12, 6), "west": (10, 0, 4, 16, 12, 12)}
    for facing, turn in zip(CARDINALS, (0, 90, 180, 270)):
        model_frame = blocks._java_turn(world[facing], 360 - turn)
        assert blocks._java_turn(model_frame, turn) == world[facing]
        assert model_frame == world["north"]
