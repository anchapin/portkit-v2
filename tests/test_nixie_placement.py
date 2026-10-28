"""#296 (pick 1a, Create nixie tubes): a face state of the mod's own read as
attach face, and the shape arithmetic a library's rotation runs on
(Vec3, Mth.sin / cos, Java float rounding, MutableObject, forAllBoxes)."""

import math

from portkit import blockcode as B
from portkit.bytecode import ClassIndex
from portkit.converters import blocks


def _nixie_like(reversed_model="create:block/tube", reversed_y_offset=0):
    variants = {}
    turn = {"north": 180, "east": 270, "south": 0, "west": 90}
    for facing, y in turn.items():
        variants[f"double_face=floor,facing={facing}"] = {"model": "create:block/tube", "y": y}
        variants[f"double_face=ceiling,facing={facing}"] = {"model": "create:block/tube", "x": 180, "y": y}
        variants[f"double_face=wall,facing={facing}"] = {"model": "create:block/tube", "x": 90, "y": y}
        variants[f"double_face=wall_reversed,facing={facing}"] = {
            "model": reversed_model, "x": 90, "y": (y + reversed_y_offset) % 360}
    return {"variants": variants}


def test_face_state_folds_a_value_that_draws_like_wall():
    assert blocks._face_state(_nixie_like()) == ("double_face", {"wall_reversed": "wall"})


def test_face_state_refuses_a_value_drawing_its_own_look():
    assert blocks._face_state(_nixie_like(reversed_y_offset=90)) is None
    assert blocks._face_state(_nixie_like(reversed_model="create:block/other")) is None


def test_vanilla_face_is_not_an_own_face_state():
    bs = {"variants": {f"face={f},facing={d}": {"model": "m"} for f in ("floor", "wall", "ceiling")
                       for d in ("north", "east", "south", "west")}}
    assert blocks._face_state(bs) is None


def test_own_face_state_reads_as_attach_face():
    kind, cells, why = blocks._directional_variants(_nixie_like())
    assert (kind, why) == ("attach", "")
    assert len(cells) == 12
    assert cells[("wall", "north")] == ("create:block/tube", 90, 180, False)


def test_box_number_whole_after_rounding():
    assert blocks._num(6.000000000000001) == 6 and isinstance(blocks._num(6.000000000000001), int)
    assert blocks._num(4.999999999999999) == 5
    assert blocks._num(7.8) == 7.8


def test_java_float_rounding_and_mth_table():
    assert B._f32(0.1) != 0.1 and abs(B._f32(0.1) - 0.1) < 1e-8
    assert B._f2i(float("nan")) == 0 and B._f2i(-2.7) == -2 and B._f2i(1e20) == 2 ** 31 - 1
    m = B.Machine(ClassIndex({}))
    quarter = B._f32(math.pi / 2)
    # Mth.sin(pi/2) = SIN[16384] = 1.0f; Mth.cos(pi/2) = SIN[32768] = (float) sin(pi).
    assert m.call(B._MTH, "sin", "(F)F", [quarter], static=True) == [1.0]
    assert m.call(B._MTH, "cos", "(F)F", [quarter], static=True) == [B._f32(math.sin(math.pi))]


def test_vec3_and_mutable_object():
    m = B.Machine(ClassIndex({}))
    v = B._vec3(1.0, 2.0, 3.0)
    (s,) = m.call(B._VEC3, "scale", "(D)Lnet/minecraft/world/phys/Vec3;", [v, 16.0])
    assert (s.fields["x"], s.fields["y"], s.fields["z"]) == (16.0, 32.0, 48.0)
    (r,) = m.call(B._VEC3, "reverse", "()Lnet/minecraft/world/phys/Vec3;", [v])
    assert r.fields["z"] == -3.0
    (a,) = m.call(B._VEC3, "add", "(Lnet/minecraft/world/phys/Vec3;)Lnet/minecraft/world/phys/Vec3;", [v, r])
    zero = m.get_static(type("R", (), {"owner": B._VEC3, "name": "ZERO"})())
    assert m.call(B._VEC3, "equals", "(Ljava/lang/Object;)Z", [a, zero]) == [1]
    neg = B._vec3(-0.0, 0.0, 0.0)
    assert m.call(B._VEC3, "equals", "(Ljava/lang/Object;)Z", [neg, zero]) == [0]  # Double.compare
    holder = B.Obj(B._MUTABLE_OBJECT)
    m.call(B._MUTABLE_OBJECT, "<init>", "(Ljava/lang/Object;)V", [holder, "a"])
    m.call(B._MUTABLE_OBJECT, "setValue", "(Ljava/lang/Object;)V", [holder, "b"])
    assert m.call(B._MUTABLE_OBJECT, "getValue", "()Ljava/lang/Object;", [holder]) == ["b"]


def test_direction_get_and_plane_order():
    m = B.Machine(ClassIndex({}))
    ad, ax = B._DIRECTION + "$AxisDirection", B._DIRECTION + "$Axis"
    got = m.call(B._DIRECTION, "get", f"(L{ad};L{ax};)L{B._DIRECTION};",
                 [B.Const(ad, "POSITIVE"), B.Const(ax, "Z")], static=True)
    assert got == [B.Dir("south")]
    (it,) = m.call("java/lang/Iterable", "iterator", "()Ljava/util/Iterator;",
                   [B.Const(B._DIRECTION + "$Plane", "HORIZONTAL")])
    assert [d.name for d in it.source.items] == ["north", "east", "south", "west"]
    assert m.call("java/lang/Math", "max", "(II)I", [-1, 0], static=True) == [0]
    assert m.call("java/lang/Math", "min", "(DD)D", [0.0, -0.0], static=True) == [-0.0]
