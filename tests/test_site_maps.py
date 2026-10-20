"""A per-object map in a final instance field, filled in one top-level run
through an object the reader can't pin and read in another (#280,
portkit.blockcode.Machine._site_map).

Zeta builds one ``VariantRegistry`` per library instance, each with its own
``final Map slabs = new LinkedHashMap<>()``; a module's ``register(event)``
fills it through the registry the event hands over, and Quark's
``VerticalSlabsModule#postRegister`` loops over ``slabs.values()`` to build a
vertical slab of each. The class files under tests/data/sitecode are javac 21
output (build.sh): an example mod over an example library in those shapes.
"""
from __future__ import annotations

from pathlib import Path

from portkit import blockcode
from portkit.blockcode import UNKNOWN, Machine, MapV, Unreadable
from portkit.bytecode import ClassIndex, instructions

DATA = Path(__file__).parent / "data" / "sitecode"
NAMES = ["jasper", "jasper_slab", "jasper_wall", "jasper_slab_upright", "jasper_wall_upright"]
REGISTRY = "com/example/vlib/VRegistry"


def _entries(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix()[:-6]: p.read_bytes() for p in root.rglob("*.class")}


def _index() -> ClassIndex:
    return ClassIndex(_entries(DATA / "classes"), _entries(DATA / "library"))


def _read(names=NAMES):
    return blockcode._registered(_index(), list(names))


def _cls(reg, name):
    objs, why = reg[name]
    return objs[0].cls if objs else why


def test_a_variant_of_every_element_of_a_map_another_run_fills_is_read():
    machine, reg = _read()
    assert _cls(reg, "jasper") == "com/example/vmod/JasperBlock"
    assert _cls(reg, "jasper_slab") == "com/example/ilib/ISlabBlock"
    # UprightModule.postRegister: event.getVariants().slabs.values().forEach(..)
    assert _cls(reg, "jasper_slab_upright") == "com/example/vmod/UprightBlock"
    shared = machine._site_maps[(REGISTRY, "slabs")]
    assert shared.shared == (REGISTRY, "slabs") and len(shared.items) == 1


def test_a_map_a_method_the_reader_never_ran_hands_on_is_not_read():
    # Datagen.walls passes walls to another method and never ran: what else
    # it may put there isn't known, so the loop over walls reads nothing.
    machine, reg = _read()
    assert _cls(reg, "jasper_wall") == "com/example/ilib/IWallBlock"
    assert reg["jasper_wall_upright"][0] == []
    assert machine._site_ok[(REGISTRY, "walls")] is False
    # Datagen.slabOf only calls slabs.get(b): a read, no run needed.
    assert machine._site_ok[(REGISTRY, "slabs")] is True


def test_only_a_final_field_every_constructor_sets_to_a_new_linked_hash_map_qualifies():
    m = Machine(_index())
    assert m._site_field(REGISTRY, "slabs")
    loose = "com/example/vlib/VLoose"
    assert not m._site_field(loose, "handed")   # set from a constructor argument
    assert not m._site_field(loose, "open")     # not final
    assert not m._site_field(loose, "hashed")   # HashMap: its order isn't known
    assert not m._site_field("java/util/HashMap", "table")  # not the mod's or a library's


def test_outside_the_registration_runs_a_field_of_an_unknown_object_stays_unknown():
    m = Machine(_index())
    ref = blockcode.Ref(REGISTRY, "slabs", "Ljava/util/Map;")
    assert m._site_map(ref) is None
    m.registrations, m.pass_no = [], 1
    m._clinit_depth = 1
    assert m._site_map(ref) is None  # a class initializer reads as before
    m._clinit_depth = 0
    site = m._site_map(ref)
    assert isinstance(site, MapV) and m._site_map(ref) is site


def test_first_pass_puts_are_kept_and_a_read_waits_for_the_second_pass():
    m = Machine(_index())
    m.registrations, m.pass_no = [], 1
    site = m._site_map(blockcode.Ref(REGISTRY, "slabs", "Ljava/util/Map;"))
    assert m._shared_map(site, "put", ["k", "v"])
    m._map_call(site, "put", "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;", ["k", "v"])
    try:
        m._shared_map(site, "values", [])
        raise AssertionError("a first-pass read must wait")
    except Unreadable:
        assert m._deferred_now
    # A pair whose key isn't known is left out; the map stays readable.
    m._map_call(site, "put", "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;", [UNKNOWN, "w"])
    assert site.items == {"k": "v"} and not site.havoc and not site.exact
    m.pass_no = 2
    m._site_ok[(REGISTRY, "slabs")] = True
    assert m._shared_map(site, "put", ["k", "v"])  # the same pair again changes nothing
    try:
        m._shared_map(site, "put", ["k2", "v2"])
        raise AssertionError("a second-pass change must stop the run")
    except Unreadable:
        pass


def test_map_read_only_follows_arguments_loaded_above_the_map():
    idx = _index()
    cf = idx.get("com/example/vmod/Datagen")
    reads = {}
    for meth in cf.methods:
        if meth.code is None:
            continue
        code = instructions(cf, meth.code)
        for k, insn in enumerate(code):
            if insn.op == 0xB4:
                reads[(meth.name, insn.arg.name)] = blockcode._map_read_only(code, k)
    assert reads == {("slabOf", "slabs"): True, ("walls", "walls"): False}
