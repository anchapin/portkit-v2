"""#365: a class initializer read past capability bookkeeping, and a caching
renderer provider read as the client's first call.

The class files under tests/data/clinitcode/classes are javac 21 output of
tests/data/clinitcode/src (rebuild with build.sh), in the shapes of
Mekanism's ``MekanismTileEntityTypes`` and ``ClientRegistrationUtil``: a type
builder whose capability list the run can't know (each compat may or may not
add one), ``without(...)`` removing from it through its iterator, the type
registered under a name read from a loader call, and one caching provider
bound to several types.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from portkit import blockcode, rendershape
from portkit.blockcode import UNKNOWN, Lam, ListV, Machine, Obj, Unreadable
from portkit.bytecode import ClassIndex, Handle, Ref

CLASSES = Path(__file__).parent / "data" / "clinitcode" / "classes"
P = "com/example/clinit/"
D = "com.example.clinit."


@pytest.fixture()
def classes():
    return ClassIndex.from_source(CLASSES)


def _holders(classes) -> Machine:
    m = Machine(classes)
    m.holders = True
    return m


def test_a_class_initializer_goes_past_a_read_only_loop_over_an_unknown_list(classes):
    m = _holders(classes)
    m.init_class(P + "Types")
    assert P + "Types" not in m._clinit_failed
    for name in ("PLAIN", "BIN", "FORKED"):
        holder = m.statics[(P + "Types", name)]
        assert isinstance(holder, Obj) and holder.cls == "__holder", name
    # The list the bookkeeping left unknown stays unknown: nothing is claimed about it.
    builder = m.statics[(P + "Types", "BIN")].fields["supplier"].captured[0]
    assert builder.fields["caps"].havoc


def test_a_loop_that_writes_anything_else_still_stops_the_initializer(classes):
    m = _holders(classes)
    m.init_class(P + "WritingTypes")
    assert P + "WritingTypes" in m._clinit_failed
    assert (P + "WritingTypes", "BIN") not in m.statics


def test_outside_a_class_initializer_the_loop_still_stops(classes):
    m = _holders(classes)
    builder = Obj(P + "TypeBuilder", {"caps": ListV([], havoc=True)})
    cf = classes.get(P + "TypeBuilder")
    without = cf.method("without", "([Ljava/lang/Object;)L" + P + "TypeBuilder;")
    gone = blockcode.Arr(["energy"])
    with pytest.raises(Unreadable, match="contents aren't known"):
        m.run(cf, without, [builder, gone])
    m._clinit_depth = 1  # the same call made while a class initializer runs
    assert m.run(cf, without, [builder, gone]) == [builder]
    assert builder.fields["caps"].havoc


def test_a_supplier_registered_under_an_unspelt_name_is_a_holder():
    m = Machine(ClassIndex({}))
    m.holders = True
    lam = Lam(Handle(6, Ref("a/B", "lambda$0", "()Ljava/lang/Object;")))
    desc = "(Ljava/lang/String;Ljava/util/function/Supplier;)Ljava/lang/Object;"
    got = m._holder_call("x/Register", "register", desc, Obj("x/Register"), [UNKNOWN, lam], False)
    assert got[0].cls == "__holder" and got[0].fields["supplier"] is lam
    # Not a register(String, Supplier): not read as one.
    other = "(Ljava/lang/Object;Ljava/util/function/Supplier;)Ljava/lang/Object;"
    assert m._holder_call("x/Register", "register", other, Obj("x/Register"), [UNKNOWN, lam], False) \
        is blockcode._NOT_HANDLED


def test_holders_of_one_supplier_are_one_value_and_of_others_not():
    builder = Obj("a/Builder")
    h = Handle(5, Ref("a/Builder", "lambda$build$0", "()Ljava/lang/Object;"))
    a = Obj("__holder", {"supplier": Lam(h, (builder,))})
    b = Obj("__holder", {"supplier": Lam(h, (builder,))})
    c = Obj("__holder", {"supplier": Lam(h, (Obj("a/Builder"),))})
    assert blockcode._value_equal(a, b)
    assert not blockcode._value_equal(a, c)
    assert not blockcode._value_equal(Obj("a/X"), Obj("a/X"))


def test_a_caching_provider_bound_to_several_types_reads_the_same_each_time(classes):
    found = [(b.renderer, b.entity) for b in rendershape.bindings(classes) if b.where == D + "Client#onRegister"]
    # Types.BIN and Types.FORKED, both through the one Caching object.
    assert found == [(D + "BinRenderer", D + "BinEntity")]
    calls = [b for b in rendershape.bindings(classes) if b.where == D + "Client#onRegister"]
    assert all(not b.why for b in calls)


def test_reading_a_caching_provider_leaves_its_fields_as_they_were(classes):
    m = _holders(classes)
    types = rendershape._Types(classes)
    inner = Lam(Handle(8, Ref(P + "BinRenderer", "<init>",
                              "(Lnet/minecraft/client/renderer/blockentity/BlockEntityRendererProvider$Context;)V")))
    prov = Obj(P + "Caching", {"inner": inner})
    prov._defaults = True
    for _ in range(3):
        assert rendershape._renderer_of(m, types, prov) == (P + "BinRenderer", "")
    assert set(prov.fields) == {"inner"}
