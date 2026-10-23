"""#366: a block's own block entity type method, read through Registrate.

The class files under tests/data/registrate/classes are javac 21 output of
tests/data/registrate/src (rebuild with build.sh) against stand-ins of
Registrate MC1.20-1.3.3's builder signatures: Create's pattern, where one
block class (GaugeBlock) names an abstract base block entity in its
signature and picks the type from a field in ``getBlockEntityType()``, a
Registrate ``BlockEntityEntry`` whose chain binds the renderer.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from portkit import adapters, rendershape
from portkit.blockcode import UNKNOWN, Machine, Obj
from portkit.bytecode import ClassIndex

CLASSES = Path(__file__).parent / "data" / "registrate" / "classes"
P = "com/example/regi/"
D = "com.example.regi."


@pytest.fixture(scope="module")
def classes():
    return ClassIndex.from_source(CLASSES)


def _gauges():
    return {"speedometer": [Obj(P + "GaugeBlock", {"speed": 1})],
            "stressometer": [Obj(P + "GaugeBlock", {"speed": 0})]}


def test_registrate_adapter_offers_a_type_hook(classes):
    found = [a for a in adapters.ADAPTERS if a.name == "registrate"]
    assert found and found[0].block_entity_types is not None
    assert adapters.check() == []
    hook, again = adapters.block_entity_types(rendershape._Types(classes))
    assert hook is not None and again == {P + "ModTypes"}
    # A jar that never names Registrate's builder gets no hook.
    hook, again = adapters.block_entity_types(rendershape._Types(ClassIndex({})))
    assert hook is None and again == set()


def test_the_chain_binds_the_renderer_to_each_concrete_type(classes):
    found = {(b.renderer, b.entity) for b in rendershape.bindings(classes) if b.renderer and b.entity}
    assert found == {(D + "GaugeRenderer", D + "SpeedGaugeBlockEntity"),
                     (D + "GaugeRenderer", D + "StressGaugeBlockEntity")}


def test_the_type_method_is_run_on_the_registered_object(classes):
    machine = Machine(classes)
    typed = rendershape.typed_entities(machine, rendershape._Types(classes), _gauges())
    assert typed == {"speedometer": P + "SpeedGaugeBlockEntity", "stressometer": P + "StressGaugeBlockEntity"}


def test_the_machine_is_put_back_as_it_was(classes):
    machine = Machine(classes)
    machine.init_class(P + "ModTypes")  # the registration run ran it without the hook
    before = (dict(machine.statics), set(machine._clinit_done), set(machine._clinit_failed))
    rendershape.typed_entities(machine, rendershape._Types(classes), _gauges())
    assert (dict(machine.statics), set(machine._clinit_done), set(machine._clinit_failed)) == before
    assert machine.holders is False and machine.call_hook is None


def test_a_field_the_run_did_not_read_pairs_nothing(classes):
    machine = Machine(classes)
    objs = {"gauge": [Obj(P + "GaugeBlock", {"speed": UNKNOWN})]}
    # Both paths return a type, of two different block entities: no guess.
    assert rendershape.typed_entities(machine, rendershape._Types(classes), objs) == {}


def test_two_objects_must_agree(classes):
    machine = Machine(classes)
    objs = {"gauge": [Obj(P + "GaugeBlock", {"speed": 1}), Obj(P + "GaugeBlock", {"speed": 0})]}
    assert rendershape.typed_entities(machine, rendershape._Types(classes), objs) == {}


def test_a_type_method_returning_no_type_pairs_nothing(classes):
    machine = Machine(classes)
    objs = {"plain": [Obj(P + "PlainGaugeBlock")]}
    assert rendershape.typed_entities(machine, rendershape._Types(classes), objs) == {}


def test_the_type_methods_are_found_by_descriptor(classes):
    machine = Machine(classes)
    found = rendershape._type_methods(machine, P + "GaugeBlock")
    assert [(cf.name, m.name) for cf, m in found] == [(P + "GaugeBlock", "getBlockEntityType")]


def test_signature_and_constructed_classes_apart(classes):
    types = rendershape._Types(classes)
    made, named = rendershape.block_entities(classes, P + "GaugeBlock", types, parts=True)
    assert made == [] and named == [P + "GaugeBlockEntity"]
    assert rendershape.block_entities(classes, P + "GaugeBlock", types) == [P + "GaugeBlockEntity"]


def test_read_pairs_each_gauge_with_its_types_renderer(classes):
    machine = Machine(classes)
    registered = {n: (objs, "") for n, objs in _gauges().items()}
    registered["plain"] = ([Obj(P + "PlainGaugeBlock")], "")
    readings = rendershape.read(classes, registered, "1.20.1", machine)
    speed, stress, plain = readings["speedometer"], readings["stressometer"], readings["plain"]
    assert speed.shapes == {"MODEL"} and speed.renderers == (D + "GaugeRenderer",)
    # The type read stands in for the abstract base the signature names.
    assert speed.block_entities == (D + "SpeedGaugeBlockEntity",)
    assert speed.bound_to == (D + "SpeedGaugeBlockEntity",)
    assert stress.block_entities == (D + "StressGaugeBlockEntity",) and stress.renderers == (D + "GaugeRenderer",)
    # No type read: the signature's abstract base, bound to nothing (#362
    # pick 3a, never every bound subclass, 3b rejected).
    assert plain.block_entities == (D + "GaugeBlockEntity",) and plain.renderers == ()
