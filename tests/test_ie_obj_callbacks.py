"""#296: the rest of Immersive Engineering's ``ie_obj`` callbacks. A callback
that also overrides ``getRenderColor`` or ``modifyQuads`` (IE's
``PipeCallbacks``) is run on the key its block entity gives placed alone,
and must hand back the colour and quads it is given; one ``layers`` name is
the model's ``render_type``. The machine pieces this needs (int/long bit
operations, ``dup2_x1`` on a double, ``EnumMap`` iteration by ordinal,
``Direction#get3DDataValue``, a ``Transformation`` made from a JOML
``Matrix4f``) are read generically. Class files are assembled here, and
the model fixture is ``tests/data/ieobj`` (written for the tests, not from
a jar)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from test_ie_obj_models import _model, mod  # noqa: F401  (fixture)
from test_key_alone import _class, _u2

from portkit import blockcode
from portkit.adapters.immersiveengineering import ieobj
from portkit.blockcode import UNKNOWN, Dir, Machine, Obj
from portkit.bytecode import ClassIndex, Ref

_D = "net/minecraft/core/Direction"


@pytest.mark.parametrize("op, a, b, want", [
    (0x78, 1, 5, 32),                      # ishl
    (0x78, 1, 31, -2147483648),            # ishl wraps to a signed int
    (0x78, 1, 33, 2),                      # an int shift uses the low 5 bits
    (0x79, 1, 63, -9223372036854775808),   # lshl
    (0x7A, -16, 2, -4),                    # ishr keeps the sign
    (0x7C, -1, 28, 15),                    # iushr
    (0x7D, -1, 60, 15),                    # lushr
    (0x7E, 0b1100, 0b0101, 0b0100),        # iand
    (0x80, 0b1100, 0b0011, 0b1111),        # ior
    (0x82, -1, 0x0F, -16),                 # ixor
    (0x81, 1 << 40, 1, (1 << 40) | 1),     # lor
])
def test_bit_operations_are_java_s(op, a, b, want):
    assert blockcode._bitwise(op, a, b) == want


def test_a_float_bit_operand_is_unknown():
    assert blockcode._bitwise(0x7E, 1.0, 1) is UNKNOWN


def test_get3d_data_value_is_the_declared_order():
    m = Machine(ClassIndex({}))
    got = [m.call(_D, "get3DDataValue", "()I", [Dir(d)])[0]
           for d in ("down", "up", "north", "south", "west", "east")]
    assert got == [0, 1, 2, 3, 4, 5]


def test_an_enum_map_iterates_by_ordinal():
    m = Machine(ClassIndex({}))
    em = m._new("java/util/EnumMap")
    assert em.kind == "enum"
    for d in ("east", "down", "north"):
        m._map_call(em, "put", "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;", [Dir(d), 1])
    assert m._map_view(em, "keySet") is not None
    assert list(em.items) == [Dir("down"), Dir("north"), Dir("east")]
    # A key whose ordinal isn't known leaves the order unknown.
    m._map_call(em, "put", "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;", [Obj("x/Unread"), 1])
    assert m._map_view(em, "keySet") is None
    # A HashMap's order stays unknown.
    hm = m._new("java/util/HashMap")
    m._map_call(hm, "put", "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;", [Dir("up"), 1])
    assert m._map_view(hm, "keySet") is None


def _run(cls: bytes, name: str, desc: str, args: list):
    ci = ClassIndex({"a/T": cls})
    m = Machine(ci)
    cf = ci.get("a/T")
    return m, m.run(cf, cf.method(name, desc), args)


def test_dup2_x1_under_a_double_and_a_matrix_transformation():
    mat = "org/joml/Matrix4f"
    tr = "com/mojang/math/Transformation"

    def chain(p):
        # this.x = 1.0 (aload_0; dconst_1; dup2_x1; putfield x; dreturn)
        return b"\x2a\x0f\x5d\xb5" + _u2(p.ref(9, "a/T", "x", "D")) + b"\xaf"

    def ident(p, entries):
        # new Transformation(new Matrix4f(16 floats))
        code = b"\xbb" + _u2(p.cls(tr)) + b"\x59" + b"\xbb" + _u2(p.cls(mat)) + b"\x59"
        code += b"".join(b"\x0c" if v else b"\x0b" for v in entries)  # fconst_1 / fconst_0
        code += b"\xb7" + _u2(p.ref(10, mat, "<init>", "(" + "F" * 16 + ")V"))
        code += b"\xb7" + _u2(p.ref(10, tr, "<init>", f"(L{mat};)V")) + b"\xb0"
        return code

    one = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    turned = [0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    cls = _class("a/T", "java/lang/Object", [("x", "D")], [
        ("chain", "()D", chain),
        ("ident", f"()L{tr};", lambda p: ident(p, one)),
        ("turned", f"()L{tr};", lambda p: ident(p, turned)),
    ])
    this = Obj("a/T")
    this._uninit = False
    _m, got = _run(cls, "chain", "()D", [this])
    assert got == [1.0] and this.fields["x"] == 1.0
    _m, got = _run(cls, "ident", f"()L{tr};", [this])
    assert len(got) == 1 and blockcode.is_identity_transform(got[0])
    _m, got = _run(cls, "turned", f"()L{tr};", [this])
    assert len(got) == 1 and not blockcode.is_identity_transform(got[0])
    assert blockcode.is_identity_transform(blockcode.Const(tr, "IDENTITY"))


def test_dup2_x1_on_a_value_of_unknown_width_is_not_guessed():
    def code(p):  # aload_0; iconst_1; iconst_2; dup2_x1; ...
        return b"\x2a\x04\x05\x5d\x57\x57\x57\x57\x57\xb1"

    cls = _class("a/T", "java/lang/Object", [], [("f", "()V", code)])
    this = Obj("a/T")
    this._uninit = False
    with pytest.raises(blockcode.Unreadable):
        _run(cls, "f", "()V", [this])


def test_ask_key_hands_back_what_the_method_returns():
    quads = "(Ljava/lang/Object;Ljava/util/List;)Ljava/util/List;"
    cls = _class("a/T", "java/lang/Object", [], [
        ("same", quads, lambda p: b"\x2c\xb0"),  # aload_2; areturn
        ("fresh", quads, lambda p: b"\xbb" + _u2(p.cls("java/util/ArrayList")) + b"\x59\xb7"
         + _u2(p.ref(10, "java/util/ArrayList", "<init>", "()V")) + b"\xb0"),
    ])
    m = Machine(ClassIndex({"a/T": cls}))
    marker = Obj("java/util/List")
    got, why = blockcode.ask_key(m, "a/T", ("same", quads), [Obj("a/Key"), marker])
    assert why == "" and got[0] is marker
    got, why = blockcode.ask_key(m, "a/T", ("fresh", quads), [Obj("a/Key"), marker])
    assert why == "" and got[0] is not marker
    got, why = blockcode.ask_key(m, "a/T", ("absent", quads), [Obj("a/Key"), marker])
    assert got is None and "isn't found" in why


def test_one_layer_is_the_render_type(mod):  # noqa: F811
    out, _files, why = ieobj.read(mod, _model(mod, "tube_layers"))
    assert why == "" and out["render_type"] == "minecraft:cutout"
    assert ieobj._one_layer(["minecraft:translucent"]) == "minecraft:translucent"
    assert ieobj._one_layer(["mymod:glow"]) is None
    assert ieobj._one_layer(["solid", "cutout"]) is None


def _alone(monkeypatch, answers):
    """_read_alone with the block's entity found and the key read; ``answers``
    maps a method name to what ask_key gives."""
    from portkit.adapters import immersiveengineering as ie
    run = (None, {"b": ([SimpleNamespace(cls="x/Block", _made_in=("x/Reg", "m", "()V"))], "")})
    monkeypatch.setattr(ie, "_chain", lambda classes, cls: [ie._ENTITY_BLOCK])
    monkeypatch.setattr(ie, "_declaring", lambda *a: (SimpleNamespace(name=ie._ENTITY_BLOCK), None))
    monkeypatch.setattr(ie, "_type_field", lambda *a: (Ref("x/Types", "BE", "Lx/T;"), ""))
    monkeypatch.setattr(ie, "_entity_of", lambda *a: ("x/Be", ""))
    monkeypatch.setattr(blockcode, "read_key_alone", lambda *a, **k: (["key"], ""))
    state = Obj(ieobj._OBJ_STATE)
    vis = Obj(ieobj._VISIBILITY)

    def call(self, owner, name, desc, args, **k):
        if name == "transform":
            return [blockcode.Const("com/mojang/math/Transformation", "IDENTITY")]
        if name == "visibility":
            return [vis]
        if name == "isVisible":
            return [1 if args[1] == "shown" else 0]
        raise AssertionError(name)

    monkeypatch.setattr(blockcode.Machine, "call", call)

    def ask(machine, cb, method, args):
        if method[0] == "getIEOBJState":
            return [state], ""
        return answers[method[0]](args)

    monkeypatch.setattr(blockcode, "ask_key", ask)
    return lambda also: ieobj._read_alone(object(), "b", run, "x/Cb", ["shown", "hidden"], also)


def test_colour_and_quads_handed_back_draw_the_shown_groups(monkeypatch):
    read = _alone(monkeypatch, {"getRenderColor": lambda a: ([a[-1]], ""), "modifyQuads": lambda a: ([a[-1]], "")})
    assert read(("getRenderColor", "modifyQuads")) == ({"shown": True, "hidden": False}, "")


def test_a_recolour_or_new_quads_are_named(monkeypatch):
    read = _alone(monkeypatch, {"getRenderColor": lambda a: ([Obj(ieobj._COLOR4)], ""),
                                "modifyQuads": lambda a: ([a[-1]], "")})
    shown, why = read(("getRenderColor",))
    assert shown is None and why == "Cb#getRenderColor recolours the group 'shown'"
    read = _alone(monkeypatch, {"modifyQuads": lambda a: (None, "x#modifyQuads can't be followed (y)")})
    shown, why = read(("modifyQuads",))
    assert shown is None and why == "Cb#modifyQuads changes the quads (x#modifyQuads can't be followed (y))"
