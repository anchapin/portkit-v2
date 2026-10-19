"""LinkedHashMap iteration, record map keys and the system property setters
(#280, WorldWeaver ``BlockSet`` material sets; portkit.blockcode).

``BlockSet#buildAndRegister`` loops over a ``SlotMap`` (a ``LinkedHashMap``
keyed by ``SlotType`` records) and ``MaterialManager.register`` tests
``ModCore.isDatagen()`` (``System.getProperty("fabric-api.datagen")``); these
tests pin each JVM shape on its own, with class files assembled here.
"""
from __future__ import annotations

import struct

import pytest

from portkit.blockcode import UNKNOWN, IterV, Machine, MapV, MapView, Obj, Unreadable
from portkit.bytecode import ClassIndex


def _assemble(name: str, super_name: str = "java/lang/Object", refs=(), strings=(), fields=(),
              equals: str | None = None) -> bytes:
    """A class file: ``refs`` are (owner, method, desc) Methodrefs, ``strings``
    String constants, ``fields`` (name, desc) private final fields; ``equals``
    "record" gives it javac's record ``equals`` (``invokedynamic`` of
    ``ObjectMethods.bootstrap`` naming ``fields``), "custom" one that returns
    false."""
    pool: list[bytes] = []
    index: dict[tuple, int] = {}

    def add(key, raw: bytes) -> int:
        if key not in index:
            pool.append(raw)
            index[key] = len(pool)
        return index[key]

    def utf(text: str) -> int:
        data = text.encode()
        return add(("utf", text), b"\x01" + struct.pack(">H", len(data)) + data)

    def cls(text: str) -> int:
        return add(("class", text), b"\x07" + struct.pack(">H", utf(text)))

    def nat(n: str, d: str) -> int:
        return add(("nat", n, d), b"\x0c" + struct.pack(">HH", utf(n), utf(d)))

    def mref(owner: str, n: str, d: str) -> int:
        return add(("mref", owner, n, d), b"\x0a" + struct.pack(">HH", cls(owner), nat(n, d)))

    def string(text: str) -> int:
        return add(("str", text), b"\x08" + struct.pack(">H", utf(text)))

    this, sup = cls(name), cls(super_name)
    for owner, n, d in refs:
        mref(owner, n, d)
    for text in strings:
        string(text)
    methods = b""
    count = 0
    bootstrap = b""
    if equals:
        if equals == "record":
            bsm_ref = mref("java/lang/runtime/ObjectMethods", "bootstrap",
                           "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/TypeDescriptor;"
                           "Ljava/lang/Class;Ljava/lang/String;[Ljava/lang/invoke/MethodHandle;)Ljava/lang/Object;")
            bsm = add(("mh", bsm_ref), b"\x0f\x06" + struct.pack(">H", bsm_ref))
            getters = []
            for fname, fdesc in fields:
                fref = add(("fref", fname), b"\x09" + struct.pack(">HH", this, nat(fname, fdesc)))
                getters.append(add(("mhf", fname), b"\x0f\x01" + struct.pack(">H", fref)))
            args = [this, string(";".join(f for f, _ in fields)), *getters]
            bootstrap = struct.pack(">HH", bsm, len(args)) + b"".join(struct.pack(">H", a) for a in args)
            indy = add(("indy",), b"\x12" + struct.pack(">HH", 0, nat("equals", f"(L{name};Ljava/lang/Object;)Z")))
            code = b"\x2a\x2b\xba" + struct.pack(">H", indy) + b"\x00\x00\xac"
        else:
            code = b"\x03\xac"  # iconst_0; ireturn
        body = struct.pack(">HHI", 2, 2, len(code)) + code + struct.pack(">HH", 0, 0)
        methods += struct.pack(">HHHH", 0x11, utf("equals"), utf("(Ljava/lang/Object;)Z"), 1)
        methods += struct.pack(">HI", utf("Code"), len(body)) + body
        count += 1
    field_bytes = b"".join(struct.pack(">HHHH", 0x12, utf(f), utf(d), 0) for f, d in fields)
    attrs = b""
    nattrs = 0
    if bootstrap:
        attrs = struct.pack(">HIH", utf("BootstrapMethods"), 2 + len(bootstrap), 1) + bootstrap
        nattrs = 1
    out = b"\xca\xfe\xba\xbe" + struct.pack(">HHH", 0, 61, len(pool) + 1) + b"".join(pool)
    out += struct.pack(">HHH", 0x31, this, sup) + struct.pack(">H", 0)
    out += struct.pack(">H", len(fields)) + field_bytes
    out += struct.pack(">H", count) + methods
    return out + struct.pack(">H", nattrs) + attrs


SLOT = "com/example/sets/SlotType"


def _machine(extra: dict | None = None) -> Machine:
    classes = {SLOT: _assemble(SLOT, "java/lang/Record", fields=[("suffix", "Ljava/lang/String;")],
                               equals="record")}
    classes.update(extra or {})
    return Machine(ClassIndex(classes))


def _v(m: Machine, owner: str, name: str, desc: str, args: list):
    return m.vanilla(owner, name, desc, args, False)


def _slot(suffix) -> Obj:
    o = Obj(SLOT, {"suffix": suffix})
    o._defaults = True  # built by ``new`` here, constructor followed to the end
    return o


def _linked(m: Machine) -> MapV:
    mp = m._new("java/util/LinkedHashMap")
    m._invoke_on(0xB7, _ref("java/util/LinkedHashMap", "<init>", "()V"), _frame([mp]))
    return mp


def _ref(owner, name, desc):
    from portkit.bytecode import Ref
    return Ref(owner, name, desc)


def _frame(stack):
    from portkit.blockcode import Frame
    return Frame(0, [], list(stack))


PUT = "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;"
GET = "(Ljava/lang/Object;)Ljava/lang/Object;"


def _put(m, mp, k, v):
    return _v(m, "java/util/Map", "put", PUT, [mp, k, v])


def _iterate(m, view) -> list:
    it = _v(m, "java/util/Collection", "iterator", "()Ljava/util/Iterator;", [view])[0]
    assert isinstance(it, IterV)
    out = []
    while _v(m, "java/util/Iterator", "hasNext", "()Z", [it]) == [1]:
        out.append(_v(m, "java/util/Iterator", "next", "()Ljava/lang/Object;", [it])[0])
    return out


# -- LinkedHashMap ---------------------------------------------------------------

def test_a_linked_hash_map_iterates_in_insertion_order():
    m = _machine()
    m._top = 1
    mp = _linked(m)
    mp.run = 1
    a, b, c = _slot("a"), _slot("b"), _slot("c")
    for k, v in ((b, "B"), (a, "A"), (c, "C")):
        assert _put(m, mp, k, v) == [None]
    # Re-inserting a key keeps its place (LinkedHashMap, Java SE 21).
    assert _put(m, mp, a, "A2") == ["A"]
    view = _v(m, "java/util/Map", "values", "()Ljava/util/Collection;", [mp])[0]
    assert isinstance(view, MapView)
    assert _iterate(m, view) == ["B", "A2", "C"]
    keys = _v(m, "java/util/Map", "keySet", "()Ljava/util/Set;", [mp])[0]
    assert _iterate(m, keys) == [b, a, c]


def test_a_hash_map_is_not_iterated_and_a_view_of_it_leaves_it_unknown():
    m = _machine()
    mp = m._new("java/util/HashMap")
    _put(m, mp, "x", 1)
    assert _v(m, "java/util/Map", "values", "()Ljava/util/Collection;", [mp]) == [UNKNOWN]
    assert mp.havoc
    assert _v(m, "java/util/Map", "get", GET, [mp, "x"]) == [UNKNOWN]


def test_a_map_changed_while_iterated_fails_fast():
    m = _machine()
    mp = _linked(m)
    _put(m, mp, "x", 1)
    view = _v(m, "java/util/Map", "values", "()Ljava/util/Collection;", [mp])[0]
    it = _v(m, "java/util/Collection", "iterator", "()Ljava/util/Iterator;", [view])[0]
    _put(m, mp, "y", 2)
    with pytest.raises(Unreadable):
        _v(m, "java/util/Iterator", "next", "()Ljava/lang/Object;", [it])


def test_replacing_a_value_while_iterating_is_not_a_structural_change():
    m = _machine()
    mp = _linked(m)
    _put(m, mp, "x", 1)
    view = _v(m, "java/util/Map", "values", "()Ljava/util/Collection;", [mp])[0]
    it = _v(m, "java/util/Collection", "iterator", "()Ljava/util/Iterator;", [view])[0]
    _put(m, mp, "x", 2)
    assert _v(m, "java/util/Iterator", "next", "()Ljava/lang/Object;", [it]) == [2]


def test_a_map_changed_past_an_undecided_branch_is_not_iterated():
    m = _machine()
    mp = _linked(m)
    m._fork_floor = mp._serial  # a frame on the stack forked after the map was made
    _put(m, mp, "x", 1)
    m._fork_floor = -1
    assert _v(m, "java/util/Map", "values", "()Ljava/util/Collection;", [mp]) == [UNKNOWN]


def test_a_map_made_by_an_earlier_top_level_run_is_not_iterated():
    m = _machine()
    mp = _linked(m)
    _put(m, mp, "x", 1)
    m._top += 1
    assert _v(m, "java/util/Map", "values", "()Ljava/util/Collection;", [mp]) == [UNKNOWN]


@pytest.mark.parametrize("desc", ["(IFZ)V", "(Ljava/util/Map;)V"])
def test_other_constructors_leave_the_map_unknown(desc):
    m = _machine()
    mp = m._new("java/util/LinkedHashMap")
    args = [mp] + [UNKNOWN] * (len(desc) - 3 if desc == "(IFZ)V" else 1)
    m._invoke_on(0xB7, _ref("java/util/LinkedHashMap", "<init>", desc), _frame(args))
    assert mp.havoc and mp.kind is None


def test_remove_and_clear_are_modelled_and_other_changes_leave_the_map_unknown():
    m = _machine()
    mp = _linked(m)
    _put(m, mp, "x", 1)
    _put(m, mp, "y", 2)
    assert _v(m, "java/util/Map", "remove", GET, [mp, "x"]) == [1]
    assert _v(m, "java/util/Map", "get", GET, [mp, "x"]) == [None]
    view = _v(m, "java/util/Map", "values", "()Ljava/util/Collection;", [mp])[0]
    assert _iterate(m, view) == [2]
    _v(m, "java/util/Map", "clear", "()V", [mp])
    assert _v(m, "java/util/Map", "size", "()I", [mp]) == [0]
    _v(m, "java/util/Map", "putAll", "(Ljava/util/Map;)V", [mp, UNKNOWN])
    assert mp.havoc
    assert _v(m, "java/util/Map", "get", GET, [mp, "x"]) == [UNKNOWN]


# -- record keys -------------------------------------------------------------------

def test_equal_records_are_one_key():
    m = _machine()
    mp = _linked(m)
    first, again = _slot("slab"), _slot("slab")
    _put(m, mp, first, "one")
    assert _v(m, "java/util/Map", "get", GET, [mp, again]) == ["one"]
    assert _put(m, mp, again, "two") == ["one"]
    assert list(mp.items) == [first]  # the map keeps the key it already held
    assert _v(m, "java/util/Map", "get", GET, [mp, _slot("stairs")]) == [None]


def test_a_record_with_an_unknown_component_is_not_a_known_key():
    m = _machine()
    mp = _linked(m)
    _put(m, mp, _slot(UNKNOWN), "x")
    assert not mp.exact
    assert _v(m, "java/util/Map", "get", GET, [mp, _slot("a")]) == [UNKNOWN]
    assert _v(m, "java/util/Map", "values", "()Ljava/util/Collection;", [mp]) == [UNKNOWN]


def test_a_key_whose_class_writes_its_own_equals_is_not_a_known_key():
    own = "com/example/sets/OwnKey"
    m = _machine({own: _assemble(own, "java/lang/Record", fields=[("suffix", "Ljava/lang/String;")],
                                 equals="custom")})
    key = Obj(own, {"suffix": "a"})
    key._defaults = True
    mp = _linked(m)
    _put(m, mp, key, 1)
    assert not mp.exact
    assert _v(m, "java/util/Map", "get", GET, [mp, Obj(own, {"suffix": "a"})]) == [UNKNOWN]


def test_a_record_handed_to_code_that_isn_t_followed_still_compares_by_its_components():
    # #280: WorldWeaver's ``SlotType`` keys are shared statics; one material
    # set hands them to a library call the machine can't follow (havoc), and
    # the next set keys its own map by them. A record's components are its
    # only instance fields, private final, and Field#set refuses a record's
    # final field (Java SE 21), so nothing can have changed them.
    m = _machine()
    shared = _slot("bark")
    m._havoc([shared], "a library call the machine can't follow")
    assert shared._defaults is False and shared.fields == {"suffix": "bark"}
    mp = _linked(m)
    _put(m, mp, shared, "one")
    assert mp.exact
    assert _v(m, "java/util/Map", "get", GET, [mp, _slot("bark")]) == ["one"]
    assert isinstance(_v(m, "java/util/Map", "values", "()Ljava/util/Collection;", [mp])[0], MapView)


def test_a_record_whose_constructor_wasn_t_followed_to_the_end_is_not_a_known_key():
    m = _machine()
    for key in (Obj(SLOT, {"suffix": "bark", "__partial": "its constructor can't be followed to the end"}),
                Obj(SLOT, {})):  # partial, or a component never stored
        mp = _linked(m)
        _put(m, mp, key, 1)
        assert not mp.exact
    unbuilt = Obj(SLOT, {"suffix": "bark"})
    unbuilt._uninit = True  # ``new`` ran, its constructor hasn't
    mp = _linked(m)
    _put(m, mp, unbuilt, 1)
    assert not mp.exact


def test_an_object_that_isn_t_a_record_is_still_compared_by_identity_only():
    # Havoc doesn't make a class that writes its own ``equals`` a known key.
    own = "com/example/sets/OwnKey2"
    m = _machine({own: _assemble(own, "java/lang/Record", fields=[("suffix", "Ljava/lang/String;")],
                                 equals="custom")})
    key = Obj(own, {"suffix": "a"})
    m._havoc([key], "x")
    mp = _linked(m)
    _put(m, mp, key, 1)
    assert not mp.exact


def test_a_record_s_components_are_read_from_its_generated_equals():
    m = _machine()
    assert m._record_components(SLOT) == ["suffix"]


# -- system property setters ---------------------------------------------------------

def _props(extra: dict) -> Machine:
    return Machine(ClassIndex(extra))


@pytest.mark.parametrize("refs, strings, sets", [
    ([("java/lang/System", "setProperty", "(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;")], [], True),
    ([("java/lang/System", "getProperties", "()Ljava/util/Properties;")], [], True),
    ([("java/lang/System", "clearProperty", "(Ljava/lang/String;)Ljava/lang/String;")], [], True),
    ([], ["setProperty"], True),  # a reflective lookup by name
    ([("java/util/Properties", "setProperty", "(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Object;")], [], False),
    ([("com/example/Builder", "setProperties", "(Ljava/lang/Object;)Lcom/example/Builder;")], [], False),
])
def test_only_java_lang_system_s_setters_can_set_a_system_property(refs, strings, sets):
    m = _props({"com/example/A": _assemble("com/example/A", refs=refs, strings=strings)})
    assert m._system_property("fabric-api.datagen") is (UNKNOWN if sets else None)


def test_a_class_that_mentions_a_setter_but_can_t_be_parsed_counts_as_setting():
    m = _props({"com/example/Bad": b"\xca\xfe\xba\xbe...java/lang/System...setProperty..."})
    assert m._system_property("fabric-api.datagen") is UNKNOWN
