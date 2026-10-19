"""``Map.entry`` / ``Map.ofEntries``, ``Object#getClass`` and an iterator per
way of a branch the run can't decide (#280, BetterEnd's last WorldWeaver
wood-set blocks; portkit.blockcode).

WorldWeaver's ``WoodenBlockSet.FUEL_TICKS`` is ``Map.ofEntries(Map.entry(
SlotType.LOG, ..), ..)``, its ``BlockTraitKey#equals`` compares ``getClass()``
of both sides, and ``SignBlockDefinition#buildAndRegisterWallSignBlock`` loops
over a sign's traits with a branch per trait it can't always decide. These
tests pin each JVM shape on its own, with class files assembled here.
"""
from __future__ import annotations

import struct

import pytest

from portkit.blockcode import UNKNOWN, ClassLit, IterV, ListV, Machine, MapV, Obj, PairV, Unreadable
from portkit.bytecode import ClassIndex

from test_blockset_maps import SLOT, _machine, _slot

GET = "(Ljava/lang/Object;)Ljava/lang/Object;"
GET_OR = "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;"
ENTRY = "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/Map$Entry;"
OF_ENTRIES = "([Ljava/util/Map$Entry;)Ljava/util/Map;"


def _static(m: Machine, owner: str, name: str, desc: str, args: list):
    return m.vanilla(owner, name, desc, args, True)


def _call(m: Machine, owner: str, name: str, desc: str, args: list):
    return m.vanilla(owner, name, desc, args, False)


def _entries(m: Machine, pairs) -> list:
    from portkit.blockcode import Arr
    entries = [_static(m, "java/util/Map", "entry", ENTRY, [k, v])[0] for k, v in pairs]
    return _static(m, "java/util/Map", "ofEntries", OF_ENTRIES, [Arr(entries)])


# -- Map.entry / Map.ofEntries / Map.of ------------------------------------------

def test_map_of_entries_looks_up_a_record_key_by_its_components():
    # WoodenBlockSet.fuelTrait(slot): FUEL_TICKS.getOrDefault(slot, null).
    m = _machine()
    planks, logs = _slot("planks"), _slot("log")
    out = _entries(m, [(planks, "PLANK_TICKS"), (logs, "LOG_TICKS")])
    assert len(out) == 1 and isinstance(out[0], MapV)
    fuel = out[0]
    assert fuel.exact and fuel.kind == "fixed"
    assert _call(m, "java/util/Map", "getOrDefault", GET_OR, [fuel, _slot("planks"), None]) == ["PLANK_TICKS"]
    assert _call(m, "java/util/Map", "get", GET, [fuel, logs]) == ["LOG_TICKS"]
    # A slot the map doesn't hold answers the default: every key compares exactly.
    assert _call(m, "java/util/Map", "getOrDefault", GET_OR, [fuel, _slot("sign"), None]) == [None]


def test_map_entry_is_a_pair():
    m = _machine()
    entry = _static(m, "java/util/Map", "entry", ENTRY, ["k", "v"])[0]
    assert entry == PairV("k", "v")
    assert _call(m, "java/util/Map$Entry", "getKey", "()Ljava/lang/Object;", [entry]) == ["k"]
    assert _call(m, "java/util/Map$Entry", "getValue", "()Ljava/lang/Object;", [entry]) == ["v"]


@pytest.mark.parametrize("key, value", [(None, "v"), ("k", None)])
def test_a_null_key_or_value_throws(key, value):
    m = _machine()
    assert _static(m, "java/util/Map", "entry", ENTRY, [key, value]) == []
    assert _static(m, "java/util/Map", "of", "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/Map;",
                   [key, value]) == []


def test_an_equal_key_twice_throws():
    m = _machine()
    assert _entries(m, [(_slot("planks"), 1), (_slot("planks"), 2)]) == []


def test_a_key_that_does_not_compare_exactly_makes_a_miss_unknown():
    m = _machine()
    fuel = _entries(m, [(_slot(UNKNOWN), 1)])[0]
    assert not fuel.exact
    assert _call(m, "java/util/Map", "get", GET, [fuel, _slot("planks")]) == [UNKNOWN]


def test_entries_that_are_not_known_leave_the_map_unknown():
    from portkit.blockcode import Arr
    m = _machine()
    assert _static(m, "java/util/Map", "ofEntries", OF_ENTRIES, [Arr([UNKNOWN])]) == [UNKNOWN]
    assert _static(m, "java/util/Map", "ofEntries", OF_ENTRIES, [UNKNOWN]) == [UNKNOWN]


def test_map_of_compares_record_keys_by_their_components_too():
    m = _machine()
    desc = "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/Map;"
    fixed = _static(m, "java/util/Map", "of", desc, [_slot("planks"), "x"])[0]
    assert _call(m, "java/util/Map", "get", GET, [fixed, _slot("planks")]) == ["x"]


@pytest.mark.parametrize("name, desc, rest", [
    ("put", "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;", ["k", "v"]),
    ("remove", GET, ["k"]),
    ("clear", "()V", []),
])
def test_a_fixed_map_refuses_changes(name, desc, rest):
    m = _machine()
    fixed = _entries(m, [("k", 1)])[0]
    assert _call(m, "java/util/Map", name, desc, [fixed, *rest]) == []  # UnsupportedOperationException
    assert fixed.items == {"k": 1}


# -- Object#getClass -------------------------------------------------------------

def test_get_class_of_an_object_built_here_is_its_class():
    m = _machine()
    key = _slot("model")
    assert _call(m, "java/lang/Object", "getClass", "()Ljava/lang/Class;", [key]) == [ClassLit(SLOT)]


def test_get_class_is_not_answered_for_a_class_outside_the_jar_or_an_unbuilt_object():
    m = _machine()
    vanilla = Obj("net/minecraft/world/level/block/Block")
    unbuilt = Obj(SLOT)
    unbuilt._uninit = True
    for v in (vanilla, unbuilt, UNKNOWN):
        assert _call(m, "java/lang/Object", "getClass", "()Ljava/lang/Class;", [v]) != [ClassLit(SLOT)]
        out = _call(m, "java/lang/Object", "getClass", "()Ljava/lang/Class;", [v])
        assert not (isinstance(out, list) and out and isinstance(out[0], ClassLit))


# -- an iterator per way ---------------------------------------------------------

LOOPER = "com/example/sets/Looper"


def _looper(escape: str = "") -> bytes:
    """``static int loop(List l)``: ``for (Object o : l) { if (o == null)
    continue; }  return 1;``, the iterator kept in local 1; ``escape``
    "static" also stores it in a static field, "call" hands it to
    ``Objects.requireNonNull``."""
    pool: list[bytes] = []
    index: dict = {}

    def add(key, raw):
        if key not in index:
            pool.append(raw)
            index[key] = len(pool)
        return index[key]

    def utf(t):
        d = t.encode()
        return add(("u", t), b"\x01" + struct.pack(">H", len(d)) + d)

    def cls(t):
        return add(("c", t), b"\x07" + struct.pack(">H", utf(t)))

    def nat(n, d):
        return add(("n", n, d), b"\x0c" + struct.pack(">HH", utf(n), utf(d)))

    def iref(o, n, d):
        return add(("i", o, n, d), b"\x0b" + struct.pack(">HH", cls(o), nat(n, d)))

    def mref(o, n, d):
        return add(("m", o, n, d), b"\x0a" + struct.pack(">HH", cls(o), nat(n, d)))

    def fref(o, n, d):
        return add(("f", o, n, d), b"\x09" + struct.pack(">HH", cls(o), nat(n, d)))

    this, sup = cls(LOOPER), cls("java/lang/Object")
    it = iref("java/util/List", "iterator", "()Ljava/util/Iterator;")
    has = iref("java/util/Iterator", "hasNext", "()Z")
    nxt = iref("java/util/Iterator", "next", "()Ljava/lang/Object;")
    head = b"\x2a\xb9" + struct.pack(">H", it) + b"\x01\x00" + b"\x4c"  # aload_0; iterator; astore_1
    if escape == "static":
        head += b"\x2b\xb3" + struct.pack(">H", fref(LOOPER, "IT", "Ljava/util/Iterator;"))
    elif escape == "call":
        head += b"\x2b\xb8" + struct.pack(">H", mref("java/util/Objects", "requireNonNull",
                                                     "(Ljava/lang/Object;)Ljava/lang/Object;")) + b"\x57"
    loop = len(head)
    # L: aload_1; hasNext; ifeq END; aload_1; next; ifnull L; goto L; END: iconst_1; ireturn
    body = b"\x2b\xb9" + struct.pack(">H", has) + b"\x01\x00"
    end_at = loop + len(body) + 3 + 1 + 5 + 3 + 3
    body += b"\x99" + struct.pack(">h", end_at - (loop + len(body)))
    body += b"\x2b\xb9" + struct.pack(">H", nxt) + b"\x01\x00"
    body += b"\xc6" + struct.pack(">h", loop - (loop + len(body)))
    body += b"\xa7" + struct.pack(">h", loop - (loop + len(body)))
    code = head + body + b"\x04\xac"
    assert len(head) + len(body) == end_at
    attr = struct.pack(">HHI", 4, 4, len(code)) + code + struct.pack(">HH", 0, 0)
    method = struct.pack(">HHHH", 0x09, utf("loop"), utf("(Ljava/util/List;)I"), 1)
    method += struct.pack(">HI", utf("Code"), len(attr)) + attr
    fields = b""
    nfields = 0
    if escape == "static":
        fields = struct.pack(">HHHH", 0x09, utf("IT"), utf("Ljava/util/Iterator;"), 0)
        nfields = 1
    out = b"\xca\xfe\xba\xbe" + struct.pack(">HHH", 0, 61, len(pool) + 1) + b"".join(pool)
    out += struct.pack(">HHH", 0x21, this, sup) + struct.pack(">H", 0)
    out += struct.pack(">H", nfields) + fields
    out += struct.pack(">H", 1) + method + struct.pack(">H", 0)
    return out


def _run_loop(escape: str, items: list):
    m = Machine(ClassIndex({LOOPER: _looper(escape)}))
    cf = m.classes.get(LOOPER)
    return m.run(cf, cf.method("loop"), [ListV(list(items))])


def test_each_way_of_an_undecided_branch_advances_its_own_iterator():
    # #280: SignBlockDefinition#buildAndRegisterWallSignBlock's loop over a
    # sign's traits forks on traits it can't decide; the iterator the loop
    # made is held only in its frame, so each way runs on to the end.
    assert set(_run_loop("", [UNKNOWN, UNKNOWN, "known"])) == {1}


def test_a_known_list_needs_no_copies():
    assert set(_run_loop("", ["a", None, "b"])) == {1}


@pytest.mark.parametrize("escape", ["static", "call"])
def test_an_iterator_that_escaped_is_shared_and_stops_the_loop(escape):
    with pytest.raises(Unreadable):
        _run_loop(escape, [UNKNOWN, UNKNOWN])


def test_a_copy_keeps_the_position_and_mod_count():
    m = Machine(ClassIndex({LOOPER: _looper("")}))
    from portkit.blockcode import Frame
    src = ListV([1, 2, 3])
    it = IterV(src, 2, 5, (0, 7))
    g = Frame(0, [None, it], [it])
    code = [object()]
    it.home = (m.depth, id(code))
    m._own_iterators(g, code)
    copy = g.locals[1]
    assert copy is not it and g.stack[0] is copy
    assert (copy.source, copy.pos, copy.mod, copy.home) == (src, 2, 5, it.home)
    assert copy._serial > it._serial
