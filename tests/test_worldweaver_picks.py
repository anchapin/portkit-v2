"""The interpreter pieces WorldWeaver's block builders need (#280, picks 1, 2
and 4 of the WorldWeaver design PR; portkit.blockcode).

Built on the example library of tests/data/inheritcode (javac 21 output):
``ILib`` and ``IModule`` are plain classes with non-final fields, ``IRegistry``
has a final field, ``IEmissive`` and ``IVariantBlock`` are interfaces.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from portkit import blockcode
from portkit.blockcode import (UNKNOWN, Arr, Coll, IterV, Lam, ListV, MapV, Machine, Obj, RKey, RL, Strm,
                               Unreadable)
from portkit.bytecode import ClassIndex, Handle, Ref

LIB = Path(__file__).parent / "data" / "inheritcode" / "library"


def _entries(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix()[:-6]: p.read_bytes() for p in root.rglob("*.class")}


def _machine(extra: dict | None = None) -> Machine:
    return Machine(ClassIndex(dict(extra or {}), _entries(LIB)))


def _v(m: Machine, owner: str, name: str, desc: str, args: list, static: bool = False):
    return m.vanilla(owner, name, desc, args, static)


# -- pick 1: a system property nothing defines ----------------------------------

def test_an_undefined_property_reads_null():
    m = _machine()
    assert _v(m, "java/lang/System", "getProperty", "(Ljava/lang/String;)Ljava/lang/String;",
              ["fabric-api.datagen"], static=True) == [None]


@pytest.mark.parametrize("key", ["java.version", "user.home", "os.name", "fabric.development",
                                 "fml.modLoader", "neoforge.enableForgeLogging", "mixin.debug"])
def test_a_property_the_jvm_or_a_launcher_defines_is_unknown(key):
    m = _machine()
    assert _v(m, "java/lang/System", "getProperty", "(Ljava/lang/String;)Ljava/lang/String;",
              [key], static=True) == [UNKNOWN]


def test_a_property_is_unknown_when_any_class_can_set_one():
    m = _machine({"com/example/Setter": b"\xca\xfe\xba\xbe...java/lang/System...setProperty..."})
    assert m._system_property("fabric-api.datagen") is UNKNOWN


def test_an_unknown_key_is_unknown():
    assert _machine()._system_property(UNKNOWN) is UNKNOWN


def test_assertions_are_off():
    m = _machine()
    assert _v(m, "java/lang/Class", "desiredAssertionStatus", "()Z",
              [blockcode.ClassLit("com/example/ilib/ILib")]) == [0]


# -- pick 2: mutable java.util lists, iterators, streams -------------------------

def test_a_new_arraylist_is_a_modelled_list():
    m = _machine()
    assert isinstance(m._new("java/util/ArrayList"), ListV)
    assert isinstance(m._new("java/util/LinkedList"), ListV)


def test_list_add_get_size_and_iterate():
    m = _machine()
    lst = ListV([])
    assert _v(m, "java/util/List", "add", "(Ljava/lang/Object;)Z", [lst, "a"]) == [1]
    assert _v(m, "java/util/List", "add", "(Ljava/lang/Object;)Z", [lst, "b"]) == [1]
    assert _v(m, "java/util/List", "size", "()I", [lst]) == [2]
    assert _v(m, "java/util/List", "isEmpty", "()Z", [lst]) == [0]
    assert _v(m, "java/util/List", "get", "(I)Ljava/lang/Object;", [lst, 1]) == ["b"]
    assert _v(m, "java/util/List", "get", "(I)Ljava/lang/Object;", [lst, 2]) == []  # throws
    it = _v(m, "java/util/List", "iterator", "()Ljava/util/Iterator;", [lst])[0]
    seen = []
    while _v(m, "java/util/Iterator", "hasNext", "()Z", [it]) == [1]:
        seen += _v(m, "java/util/Iterator", "next", "()Ljava/lang/Object;", [it])
    assert seen == ["a", "b"]


def test_a_list_changed_while_iterated_fails_fast():
    m = _machine()
    lst = ListV(["a"])
    it = _v(m, "java/util/List", "iterator", "()Ljava/util/Iterator;", [lst])[0]
    _v(m, "java/util/List", "add", "(Ljava/lang/Object;)Z", [lst, "b"])
    with pytest.raises(Unreadable, match="ConcurrentModification"):
        _v(m, "java/util/Iterator", "next", "()Ljava/lang/Object;", [it])


def test_a_call_not_modelled_leaves_the_list_unknown_and_a_loop_over_it_stops():
    m = _machine()
    lst = ListV(["a"])
    _v(m, "java/util/List", "replaceAll", "(Ljava/util/function/UnaryOperator;)V", [lst, UNKNOWN])
    assert lst.havoc
    assert _v(m, "java/util/List", "size", "()I", [lst]) == [UNKNOWN]
    it = _v(m, "java/util/List", "iterator", "()Ljava/util/Iterator;", [lst])[0]
    with pytest.raises(Unreadable, match="contents aren't known"):
        _v(m, "java/util/Iterator", "hasNext", "()Z", [it])


def test_a_list_handed_to_code_that_isnt_there_is_unknown():
    m = _machine()
    lst = ListV(["a"])
    m.call("com/example/Missing", "fill", "(Ljava/util/List;)V", [lst], static=True)
    assert lst.havoc


def test_arraylist_of_a_collection_copies_it():
    m = _machine()
    frame = blockcode.Frame(0, [], [])
    lst = m._new("java/util/ArrayList")
    frame.stack += [lst, Coll(("x", "y"))]
    m._invoke(0xB7, Ref("java/util/ArrayList", "<init>", "(Ljava/util/Collection;)V"), frame)
    assert lst.items == ["x", "y"] and not lst.havoc


def test_streams_of_known_elements():
    m = _machine()
    s = Strm(("a", "b", "c"))
    assert m._stream(s, "count", "()J", []) == [3]
    assert m._stream(s, "toList", "()Ljava/util/List;", []) == [Coll(("a", "b", "c"))]
    assert m._stream(s, "findFirst", "()Ljava/util/Optional;", []) == [blockcode.Opt("a")]
    # findAny of several: one of them, which isn't known; that there is one is.
    found = m._stream(s, "findAny", "()Ljava/util/Optional;", [])[0]
    assert _v(m, "java/util/Optional", "isPresent", "()Z", [found]) == [1]
    empty = m._stream(Strm(()), "findAny", "()Ljava/util/Optional;", [])[0]
    assert _v(m, "java/util/Optional", "isPresent", "()Z", [empty]) == [0]
    collected = m._stream(s, "collect", "(Ljava/util/stream/Collector;)Ljava/lang/Object;",
                          [blockcode.CollectorV("toList")])[0]
    assert isinstance(collected, ListV) and collected.items == ["a", "b", "c"]


def test_a_list_write_after_an_undecided_branch_makes_it_unknown():
    m = _machine()
    m.registrations = []
    lst = ListV(["a"])
    frame = blockcode.Frame(0, [], [], forked=True)
    frame.fork_serial = lst._serial  # the list was allocated before the branch
    m._frame = frame
    assert _v(m, "java/util/List", "add", "(Ljava/lang/Object;)Z", [lst, "b"]) == [UNKNOWN]
    assert lst.havoc


def test_map_compute_if_absent_and_size():
    m = _machine()
    mp = MapV({})
    lam = Lam(Handle(6, Ref("com/example/Missing", "make", "(Ljava/lang/Object;)Ljava/lang/Object;")))
    # A function the machine can't call: the map is unknown from then on.
    assert _v(m, "java/util/Map", "computeIfAbsent",
              "(Ljava/lang/Object;Ljava/util/function/Function;)Ljava/lang/Object;", [mp, "k", lam]) == [UNKNOWN]
    assert mp.havoc
    assert _v(m, "java/util/Map", "get", "(Ljava/lang/Object;)Ljava/lang/Object;", [mp, "k"]) == [UNKNOWN]
    known = MapV({"k": "v"})
    assert _v(m, "java/util/Map", "computeIfAbsent",
              "(Ljava/lang/Object;Ljava/util/function/Function;)Ljava/lang/Object;", [known, "k", lam]) == ["v"]
    assert _v(m, "java/util/Map", "size", "()I", [known]) == [1]


def test_an_object_key_whose_class_declares_no_equals_compares_by_identity():
    m = _machine()
    assert m._key_ok(Obj("com/example/ilib/ILib"))
    assert not m._key_ok(UNKNOWN)
    assert not m._key_ok(Obj("net/minecraft/world/level/block/Block"))  # a vanilla class may override equals


# -- trait objects: a lambda's type ---------------------------------------------

def test_a_lambda_is_an_instance_of_its_interface_only():
    m = _machine()
    lam = Lam(Handle(6, Ref("x", "y", "()V")), (), None, "com/example/ilib/IEmissive")
    assert m.instance_of(lam, "com/example/ilib/IEmissive") == 1
    assert m.instance_of(lam, "com/example/ilib/IVariantBlock") == 0
    assert m.instance_of(lam, "com/example/ilib/ILib") == 0  # a class: lambdas extend Object
    plain = Lam(Handle(6, Ref("x", "y", "()V")))
    assert m.instance_of(plain, "com/example/ilib/IEmissive") is UNKNOWN


# -- fields hold their defaults until written -------------------------------------

def test_a_new_object_s_unwritten_field_reads_its_default():
    m = _machine()
    obj = m._new("com/example/ilib/ILib")
    obj._uninit = False
    assert m._field_default(obj, "registry") is None
    assert m._field_default(obj, "nothing_declared") is UNKNOWN
    obj.fields["__partial"] = "stopped"
    assert m._field_default(obj, "registry") is UNKNOWN


def test_an_object_handed_to_code_that_isnt_there_loses_its_defaults():
    m = _machine()
    obj = m._new("com/example/ilib/ILib")
    m.call("com/example/Missing", "inject", "(Ljava/lang/Object;)V", [obj], static=True)
    assert m._field_default(obj, "registry") is UNKNOWN


# -- pick 4: havoc ------------------------------------------------------------

def test_havoc_makes_what_the_arguments_reach_unknown_and_keeps_final_fields():
    m = _machine()
    inner = ListV(["a"])
    arr = Arr(["x"])
    mp = MapV({"k": "v"})
    reg = Obj("com/example/ilib/IRegistry", {"internalNames": mp, "z": "lib"})
    lib = Obj("com/example/ilib/ILib", {"modid": "mod", "registry": reg, "variants": inner,
                                        "__rl": "mod:thing"})
    m.statics[("com/example/ilib/ILib", "INSTANCE")] = "kept"
    m._havoc([lib, arr], "test")
    assert lib.fields["modid"] is UNKNOWN and lib.fields["registry"] is UNKNOWN
    assert lib.fields["__rl"] == "mod:thing"  # what the machine keeps of construction
    assert reg.fields["internalNames"] is mp  # final field: same map ...
    assert mp.havoc  # ... whose contents are unknown
    assert reg.fields["z"] is UNKNOWN  # non-final
    assert inner.havoc and arr.items == [UNKNOWN]
    assert m.statics[("com/example/ilib/ILib", "INSTANCE")] == "kept"  # pick 4a: statics stay
    assert m.havocs == ["test"]


def test_ways_returning_the_same_value_go_on_as_one():
    assert blockcode._value_equal("a", "a")
    assert blockcode._value_equal(RL("m:x"), RL("m:x"))
    o = Obj("com/example/ilib/ILib")
    assert blockcode._value_equal(o, o)
    assert not blockcode._value_equal(o, Obj("com/example/ilib/ILib"))
    assert not blockcode._value_equal(UNKNOWN, UNKNOWN)
    assert not blockcode._value_equal(ListV([]), ListV([]))


def test_a_resource_key_names_its_location_for_a_registration():
    m = _machine()
    m.registrations = []
    key = _v(m, "net/minecraft/resources/ResourceKey", "create",
             "(Lnet/minecraft/resources/ResourceKey;Lnet/minecraft/resources/ResourceLocation;)"
             "Lnet/minecraft/resources/ResourceKey;", [UNKNOWN, RL("betterend:mossy_obsidian")], static=True)[0]
    assert key == RKey(RL("betterend:mossy_obsidian"))
    block = Obj("com/example/ilib/IBlock")
    m._record([blockcode.Const("net/minecraft/core/registries/BuiltInRegistries", "BLOCK"), key, block])
    assert [(r.name, r.value) for r in m.registrations] == [("mossy_obsidian", block)]


def test_iterator_over_an_immutable_collection():
    m = _machine()
    it = _v(m, "java/util/List", "iterator", "()Ljava/util/Iterator;", [Coll(("a",))])[0]
    assert isinstance(it, IterV)
    assert _v(m, "java/util/Iterator", "next", "()Ljava/lang/Object;", [it]) == ["a"]
    assert _v(m, "java/util/Iterator", "hasNext", "()Z", [it]) == [0]
