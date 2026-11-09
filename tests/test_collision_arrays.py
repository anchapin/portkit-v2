"""#296: a block whose collision is read from code and whose Java boxes don't
fill one cuboid collides with those boxes (Bedrock's minecraft:collision_box
as an array, up to 16 boxes, block format 1.26.0) rather than their bounding
box; the selection box stays the bounding box, and only that block moves to
block format 1.26.0 (``converters.blocks._collision_array``,
``_raise_for_arrays``). The readings here are made in the test, not read
from any jar."""
from __future__ import annotations

from pathlib import Path

from portkit import blockcode, pack
from portkit.bytecode import ClassIndex
from portkit.converters import blocks
from portkit.model import ConversionResult, SourceMod

MEMO = Path(__file__).parent / "data" / "memo" / "classes"

# A lever-like plate with two posts: three boxes whose union isn't a cuboid.
POSTS = ((2.0, 0.0, 0.0, 14.0, 12.0, 6.0), (9.0, 12.0, 1.0, 13.0, 16.0, 5.0), (3.0, 12.0, 1.0, 7.0, 16.0, 5.0))


def test_boxes_that_dont_fill_one_cuboid_are_an_array():
    assert blocks._collision_array(POSTS) == sorted(POSTS)
    # The same boxes in another order are the same array.
    assert blocks._collision_array(POSTS[::-1]) == sorted(POSTS)


def test_one_cuboid_is_no_array():
    # Two halves of a slab, a box inside another, a repeated box, one box.
    assert blocks._collision_array(((0, 0, 0, 16, 8, 8), (0, 0, 8, 16, 8, 16))) is None
    assert blocks._collision_array(((0, 0, 0, 16, 8, 16), (2, 2, 2, 4, 4, 4))) is None
    assert blocks._collision_array(((0, 0, 0, 16, 8, 16), (0, 0, 0, 16, 8, 16))) is None
    assert blocks._collision_array(((0, 0, 0, 16, 8, 16),)) is None
    assert blocks._collision_array(()) is None and blocks._collision_array(None) is None


def test_array_is_deduplicated_and_cut_to_the_block():
    got = blocks._collision_array(POSTS + POSTS[:1] + ((4.0, 1.0, 1.0, 5.0, 2.0, 2.0),))
    assert got == sorted(POSTS)
    # A box reaching below the block is cut at its floor; one left with no volume is dropped.
    got = blocks._collision_array(((2.0, -2.0, 2.0, 14.0, 8.0, 14.0), (0.0, 4.0, 0.0, 16.0, 10.0, 16.0),
                                   (0.0, -3.0, 0.0, 16.0, -1.0, 16.0)))
    assert got == [(0.0, 4.0, 0.0, 16.0, 10.0, 16.0), (2.0, 0.0, 2.0, 14.0, 8.0, 14.0)]


def test_array_turns_as_the_bounding_box_does():
    got = blocks._collision_array(POSTS, 90)
    assert got == sorted(tuple(float(v) for v in blocks._java_turn(b, 90)) for b in POSTS)
    assert blocks._bbox(got) == blocks._java_turn(blocks._bbox(POSTS), 90)


def test_more_than_sixteen_boxes_is_no_array():
    # Pixel cubes two apart: none holds another, and together they fill no cuboid.
    cubes = tuple((2.0 * x, 2.0 * y, 2.0 * z, 2.0 * x + 1, 2.0 * y + 1, 2.0 * z + 1)
                  for x in range(3) for y in range(3) for z in range(2))
    assert len(blocks._collision_array(cubes[:16])) == 16
    assert blocks._collision_array(cubes[:17]) is None


def test_collision_value():
    sel = {"origin": [0, 0, 0], "size": [1, 1, 1]}
    assert blocks._collision_value(sel, None, True) is sel
    assert blocks._collision_value(sel, list(POSTS), False) is False
    assert blocks._collision_value(sel, list(POSTS), True) == [blocks._bedrock_box(b) for b in POSTS]


def _reading(name, shapes, collision=True):
    r = blockcode.Reading(name)
    r.shapes, r.shape_from = shapes, f"a.{name.title()}#getShape"
    r.collision, r.collision_from = collision, ""
    r.collision_why = "" if collision is not None else "its Properties aren't read"
    return r


def test_one_look_block_collides_with_its_boxes(monkeypatch):
    readings = {"posts": _reading("posts", POSTS), "guess": _reading("guess", POSTS, collision=None),
                "slab": _reading("slab", ((0.0, 0.0, 0.0, 16.0, 8.0, 8.0), (0.0, 0.0, 8.0, 16.0, 8.0, 16.0)))}
    monkeypatch.setattr(blockcode, "read_stateless_shapes", lambda classes, names, run=None:
                        {n: readings[n] for n in names})
    mod = SourceMod(root=MEMO, namespace="a", classes=ClassIndex.from_source(MEMO))
    result = ConversionResult()
    for name in readings:
        result.files[f"blocks/{name}.json"] = blocks._block_definition("a", name, f"geometry.a.{name}", {})
    blocks._stateless_boxes(mod, result, sorted(readings), lambda: None)

    def comps(name):
        return result.files[f"blocks/{name}.json"]["minecraft:block"]["components"]

    bound = blocks._bedrock_box(blocks._bbox(POSTS))
    assert comps("posts")["minecraft:selection_box"] == bound
    assert comps("posts")["minecraft:collision_box"] == [blocks._bedrock_box(b) for b in sorted(POSTS)]
    # Collision not read from code: the DEFAULT bounding box, as before.
    assert comps("guess")["minecraft:collision_box"] == bound
    assert comps("slab")["minecraft:collision_box"] == comps("slab")["minecraft:selection_box"]

    notes = blocks._raise_for_arrays(result)
    assert result.files["blocks/posts.json"]["format_version"] == "1.26.0"
    for name in ("guess", "slab"):
        assert result.files[f"blocks/{name}.json"]["format_version"] == blocks._BLOCK_FORMAT
    assert len(notes) == 1 and "3 boxes: posts." in notes[0] and "block format 1.26.0" in notes[0]
    assert pack.engine_floor(result.files) >= (1, 26, 0)


def _definition(fmt, components, permutations=()):
    block = {"description": {"identifier": "a:b"}, "components": components}
    if permutations:
        block["permutations"] = [{"condition": "1", "components": c} for c in permutations]
    return {"format_version": fmt, "minecraft:block": block}


def test_raise_keeps_the_old_liquid_clipping_default():
    array = [blocks._bedrock_box(b) for b in POSTS]
    rule = {"liquid_type": "water", "can_contain_liquid": True, "on_liquid_touches": "blocking"}
    result = ConversionResult()
    result.files["blocks/w.json"] = _definition(
        "1.21.60", {"minecraft:geometry": "geometry.a.w", "minecraft:liquid_detection": {"detection_rules": [dict(rule)]}},
        [{"minecraft:collision_box": array}])
    blocks._raise_for_arrays(result)
    definition = result.files["blocks/w.json"]
    assert definition["format_version"] == "1.26.0"
    got = definition["minecraft:block"]["components"]["minecraft:liquid_detection"]["detection_rules"]
    assert got == [{**rule, "use_liquid_clipping": True}]


def test_raise_leaves_newer_and_unarrayed_blocks_alone():
    array = [blocks._bedrock_box(b) for b in POSTS]
    result = ConversionResult()
    result.files["blocks/new.json"] = _definition("1.26.50", {"minecraft:collision_box": array})
    result.files["blocks/plain.json"] = _definition("1.20.20", {"minecraft:collision_box": array[0]})
    before = {k: repr(v) for k, v in result.files.items()}
    assert blocks._raise_for_arrays(result) == []
    assert {k: repr(v) for k, v in result.files.items()} == before


def test_full_block_geometry_keeps_the_bounding_box():
    array = [blocks._bedrock_box(b) for b in POSTS]
    result = ConversionResult()
    result.files["blocks/cube.json"] = _definition(
        "1.20.20", {"minecraft:geometry": "minecraft:geometry.full_block", "minecraft:collision_box": list(array)})
    notes = blocks._raise_for_arrays(result)
    definition = result.files["blocks/cube.json"]
    assert definition["format_version"] == "1.20.20"
    assert definition["minecraft:block"]["components"]["minecraft:collision_box"] == blocks._union(array)
    assert len(notes) == 1 and "full_block" in notes[0] and "cube" in notes[0]
