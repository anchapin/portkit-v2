"""#296: collision read where it was a DEFAULT before - a copy of a vanilla
block's Properties, a getCollisionShape box of the block's own, and a block
registered twice whose readings disagree only on collision.

tests/data/collread/classes are javac 21 output (build.sh): an example mod whose
blocks copy ``Blocks.WHEAT`` (no collision), ``Blocks.STONE`` (collides) and
``Blocks.GLOWSTONE`` (not in the table), ``peel`` is Alex's Mobs
BlockBananaPeel's shapes (a 4 px peel to select, a 9 px slab to collide with),
``post`` collides above its block, and ``twice`` is registered twice, once on a
copy of WHEAT and once on a copy of GLOWSTONE. The ``super_*`` blocks (``CSuper``)
override getCollisionShape and hand the call back to vanilla (Immersive
Engineering's IEEntityBlock does so for a block entity without collision
bounds).
"""
from __future__ import annotations

from pathlib import Path

from portkit import blockcode
from portkit.bytecode import ClassIndex
from portkit.converters.blocks import _no_collision_notes

DATA = Path(__file__).parent / "data" / "collread" / "classes"
COPIES = ["wheatish", "wheatish_old", "stony", "stony_off", "glowy"]


def _index(table: bool = True) -> ClassIndex:
    classes = ClassIndex({p.relative_to(DATA).as_posix()[:-6]: p.read_bytes() for p in DATA.rglob("*.class")})
    classes.vanilla_blocks = {"WHEAT": "wheat", "STONE": "stone", "GLOWSTONE": "glowstone"}
    if table:
        classes.vanilla_collision = {"wheat": False, "stone": True}
    return classes


def _copies(table: bool = True) -> dict:
    return blockcode.read_state_blocks(_index(table), {n: ("lit",) for n in COPIES}, facingless=frozenset(COPIES))


def test_a_copy_of_a_vanilla_blocks_properties_takes_its_collision():
    r = _copies()
    for name in ("wheatish", "wheatish_old"):  # ofFullCopy (1.21.1), copy (1.20.1)
        assert r[name].collision is False and r[name].collision_copied == "Blocks.WHEAT"
        assert r[name].collision_from == ""
    assert r["stony"].collision is True and r["stony"].collision_copied == ""


def test_the_mods_own_no_collision_after_a_copy_is_its_own():
    r = _copies()
    assert r["stony_off"].collision is False and r["stony_off"].collision_copied == ""


def test_a_copy_the_table_doesnt_read_stays_unknown():
    r = _copies()
    assert r["glowy"].collision is None
    assert "copy a vanilla block's" in r["glowy"].collision_why
    # Without the table (not fetched), every copy stays a labelled DEFAULT, as before.
    bare = _copies(table=False)
    for name in ("wheatish", "wheatish_old", "stony", "glowy"):
        assert bare[name].collision is None and bare[name].collision_copied == "", name
    assert bare["stony_off"].collision is False


def test_a_plant_on_a_copy_of_wheat_has_no_collision_with_its_shape_read():
    r = blockcode.read_stateless_shapes(_index(), ["shrub"])["shrub"]
    assert r.shapes == ((2.0, 0.0, 2.0, 14.0, 13.0, 14.0),)
    assert r.collision is False and r.collision_copied == "Blocks.WHEAT"


def test_a_box_of_its_own_inside_the_block_is_read_for_every_entity():
    r = blockcode.read_stateless_shapes(_index(), ["peel"])["peel"]
    assert r.shapes == ((2.0, 0.0, 2.0, 14.0, 4.0, 14.0),)  # the selection box stays getShape's
    assert r.collision is True
    assert r.collision_boxes == ((0.0, 0.0, 0.0, 16.0, 9.0, 16.0),)
    assert r.collision_from == "com.example.cmod.CPeel#getCollisionShape"
    assert r.collision_for == ""


def test_a_box_of_its_own_beyond_the_block_keeps_the_default():
    r = blockcode.read_stateless_shapes(_index(), ["post"])["post"]
    assert r.shapes == ((6.0, 0.0, 6.0, 10.0, 16.0, 10.0),)
    assert r.collision is None and r.collision_boxes is None
    assert "a box of its own" in r.collision_why


def test_in_block():
    assert blockcode._in_block([(0, 0, 0, 16, 9, 16), (2, 0, 2, 14, 16, 14)])
    assert not blockcode._in_block([(6, 0, 6, 10, 24, 10)])
    assert not blockcode._in_block([(-1, 0, 0, 16, 1, 16)])
    assert not blockcode._in_block([(0, 0, 0, 0, 1, 16)])  # empty


def test_registered_twice_disagreeing_only_on_collision_keeps_the_rest():
    r = blockcode.read_stateless_shapes(_index(), ["twice"])["twice"]
    assert r.shapes == ((2.0, 0.0, 2.0, 14.0, 13.0, 14.0),)  # what both agree on is kept
    assert r.collision is None and r.collision_copied == ""
    assert r.collision_why == "registered twice with different settings"


def test_settle_collision():
    a, b = blockcode.Reading("x"), blockcode.Reading("x")
    a.collision, a.collision_copied, b.collision = False, "Blocks.WHEAT", None
    blockcode._settle_collision(a, b)
    for x in (a, b):
        assert x.collision is None and x.collision_copied == "" and x.collision_from == ""
        assert x.collision_why == "registered twice with different settings"
    c, d = blockcode.Reading("y"), blockcode.Reading("y")
    c.collision = d.collision = True
    c.collision_why = "kept"
    blockcode._settle_collision(c, d)  # they agree: nothing changes
    assert c.collision is True and c.collision_why == "kept"


def test_notes_name_the_copied_vanilla_block():
    notes = _no_collision_notes([
        {"name": "a", "collision": False, "collision_from": ""},
        {"name": "rice", "collision": False, "collision_from": "", "collision_copied": "Blocks.WHEAT"},
    ])
    assert notes[0].endswith(": a.")
    assert notes[1].startswith("No collision, read from bytecode (the block's Properties copy a vanilla block's")
    assert "Blocks.WHEAT: rice." in notes[1]


def test_block_files_get_the_peels_own_box_and_the_shrubs_no_collision(monkeypatch):
    from portkit.converters import blocks
    from portkit.model import ConversionResult, SourceMod
    classes = _index()
    readings = blockcode.read_stateless_shapes(classes, ["peel", "shrub"])
    monkeypatch.setattr(blockcode, "read_stateless_shapes", lambda c, names, run=None:
                        {n: readings[n] for n in names})
    mod = SourceMod(root=DATA, namespace="cmod", classes=classes)
    result = ConversionResult()
    for name in ("peel", "shrub"):
        result.files[f"blocks/{name}.json"] = blocks._block_definition("cmod", name, f"geometry.cmod.{name}", {})
    notes = blocks._stateless_boxes(mod, result, ["peel", "shrub"], lambda: None)
    peel = result.files["blocks/peel.json"]["minecraft:block"]["components"]
    assert peel["minecraft:collision_box"] == {"origin": [-8, 0, -8], "size": [16, 9, 16]}
    assert peel["minecraft:selection_box"] == {"origin": [-6, 0, -6], "size": [12, 4, 12]}
    shrub = result.files["blocks/shrub.json"]["minecraft:block"]["components"]
    assert shrub["minecraft:collision_box"] is False
    own = [n for n in notes if "gives boxes of its own" in n]
    assert len(own) == 1 and own[0].endswith("com.example.cmod.CPeel#getCollisionShape: peel.")
    copied = [n for n in notes if "copy a vanilla block's" in n]
    assert len(copied) == 1 and copied[0].endswith("Blocks.WHEAT: shrub.")
    assert blocks._raise_for_arrays(result) == []


def test_a_super_call_runs_vanillas_get_collision_shape():
    # BlockBehaviour#getCollisionShape (1.21.1 client jar dtb#b): hasCollision ?
    # state.getShape(level, pos) : Shapes.empty(); the state's getShape is the
    # block's own (dtb$a#j -> #a -> getBlock().getShape).
    r = blockcode.read_stateless_shapes(_index(), ["super_box", "super_cube", "super_off", "super_open"])
    box = r["super_box"]
    assert box.shapes == ((4.0, 0.0, 4.0, 12.0, 10.0, 12.0),)
    assert box.collision is True and box.collision_boxes is None  # the selection box
    assert box.collision_from == "com.example.cmod.CSuper#getCollisionShape"
    cube = r["super_cube"]  # getShape is vanilla's too: Shapes.block()
    assert cube.shapes == ((0.0, 0.0, 0.0, 16.0, 16.0, 16.0),) and cube.collision is True
    off = r["super_off"]  # noCollission: Shapes.empty()
    assert off.collision is False and off.collision_from == "com.example.cmod.CSuper#getCollisionShape"


def test_a_super_call_on_one_path_only_keeps_the_default():
    r = blockcode.read_stateless_shapes(_index(), ["super_open"])["super_open"]
    assert r.collision is None and r.collision_boxes is None
    assert "depends on more than the drawn states" in r.collision_why


def test_a_super_call_reads_has_collision_from_the_blocks_own_properties():
    from portkit.blockcode import Machine, Obj, Props, State, UNKNOWN
    machine = Machine(_index())
    block = Obj("com/example/cmod/CSuper")
    block.fields["__props"] = Props(has_collision=UNKNOWN)
    block.fields["own"] = 1
    args = [block, State(), UNKNOWN, UNKNOWN, UNKNOWN]

    def call():
        return machine.call("net/minecraft/world/level/block/Block", "getCollisionShape",
                            blockcode._GET_SHAPE_DESC, args, special=True)
    assert call() == [UNKNOWN]
    block.fields["__props"] = Props(has_collision=False)
    assert call() == [blockcode.Shape(())]
    block.fields["__props"] = Props(has_collision=True)
    assert call() == [blockcode.Shape(((4.0, 0.0, 4.0, 12.0, 10.0, 12.0),))]
