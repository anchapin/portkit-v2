"""#375: one registration run shared by every block reader, and the
registration values a run doesn't build because they can't return a block.

The class files under tests/data/blockcode/classes are the javac 21 example
mod test_two_lambda_registrations.py reads (no Minecraft code).
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from portkit import blockcode
from portkit.bytecode import ClassIndex, Handle, Ref

CLASSES = Path(__file__).parent / "data" / "blockcode" / "classes"
NAMES = ["pair_lamp", "pair_statue", "lamp", "statue"]
BLOCK = "net/minecraft/world/level/block/Block"


@pytest.fixture(scope="module")
def index():
    return ClassIndex.from_source(CLASSES)


@pytest.fixture(scope="module")
def run(index):
    return blockcode._registered(index, NAMES)


# --- one run, shared -------------------------------------------------------------

def test_a_reader_on_a_run_that_covers_its_names_reads_that_run(index, run):
    machine, registered = blockcode._from_run(run, index, ["lamp", "statue"])
    assert machine is run[0]
    assert set(registered) == {"lamp", "statue"}
    assert registered["lamp"] is run[1]["lamp"]


def test_a_reader_with_a_name_the_run_doesnt_cover_makes_its_own(index, run):
    machine, registered = blockcode._from_run(run, index, ["lamp", "not_in_the_run"])
    assert machine is not run[0]
    assert set(registered) == {"lamp", "not_in_the_run"}


def test_a_run_over_other_classes_isnt_shared(run):
    other = ClassIndex.from_source(CLASSES)
    machine, _ = blockcode._from_run(run, other, ["lamp"])
    assert machine is not run[0]


def test_no_run_makes_its_own(index):
    machine, registered = blockcode._from_run(None, index, ["lamp"])
    assert set(registered) == {"lamp"}


def test_the_shared_run_reads_as_a_run_of_its_own(index):
    shared = blockcode._registered(index, NAMES)
    own = blockcode.read_blocks(index, ["pair_lamp", "lamp"])
    on_shared = blockcode.read_blocks(index, ["pair_lamp", "lamp"], run=shared)
    for name in ("pair_lamp", "lamp"):
        assert (on_shared[name].cls, on_shared[name].placement, on_shared[name].shapes) == \
            (own[name].cls, own[name].placement, own[name].shapes)


# --- values that can't return a block --------------------------------------------

class _Machine:
    """What _never_block asks of a machine: block classes by name, the jar's
    classes and superclass chains."""

    def __init__(self, classes: dict):
        self.classes = classes

    def chain(self, name):
        out = [name]
        while name in self.classes:
            name = self.classes[name].super_name
            out.append(name)
        return out

    def is_block_class(self, name):
        last = self.chain(name)[-1]
        return last == BLOCK or last.endswith("/AbstractBlock")


def _cls(super_name, interface=False):
    return SimpleNamespace(super_name=super_name, access=0x0200 if interface else 0x0021)


def _lam(desc, kind=6, itype=None):
    return blockcode.Lam(Handle(kind, Ref("com/x/Reg", "lambda$0", desc)), itype=itype)


MACHINE = _Machine({
    "com/x/LampBlock": _cls(BLOCK),
    "com/x/LampItem": _cls("net/minecraft/world/item/Item"),
    "com/x/Holder": _cls("java/lang/Object"),
    "com/x/Builder": _cls("com/lib/MissingBase"),
    "com/x/HasBlock": _cls("java/lang/Object", interface=True),
})


@pytest.mark.parametrize("asked", [True, False])
@pytest.mark.parametrize("desc", ["(Lcom/x/LampBlock;)V", "()V", "()I", "(Ljava/lang/Object;)Z"])
def test_void_and_primitive_returns_arent_built(desc, asked):
    assert blockcode._never_block(MACHINE, _lam(desc), asked)


@pytest.mark.parametrize("asked", [True, False])
@pytest.mark.parametrize("desc", ["()Lcom/x/LampBlock;", "()Ljava/lang/Object;", "()Lcom/x/HasBlock;",
                                  "()Lcom/x/Builder;", "()Lcom/lib/Unknown;", "()" + "L" + BLOCK + ";"])
def test_block_object_interface_and_unplaced_returns_are_built(desc, asked):
    assert not blockcode._never_block(MACHINE, _lam(desc), asked)


@pytest.mark.parametrize("desc", ["()Lcom/x/LampItem;", "()Lcom/x/Holder;", "()[Lcom/x/LampBlock;",
                                  "()Lnet/minecraft/world/item/Item;"])
def test_other_returns_arent_built_for_a_name_no_reader_asked_for(desc):
    assert blockcode._never_block(MACHINE, _lam(desc), asked=False)
    # What an asked name's value builds names why it isn't a block.
    assert not blockcode._never_block(MACHINE, _lam(desc), asked=True)


def test_the_call_sites_type_comes_before_the_methods():
    # A generic Supplier<T>'s method returns Object; the call site says LampItem.
    lam = _lam("()Ljava/lang/Object;", itype="()Lcom/x/LampItem;")
    assert blockcode._never_block(MACHINE, lam, asked=False)


def test_constructor_references_and_non_lambdas_are_built():
    assert not blockcode._never_block(MACHINE, _lam("()V", kind=8), asked=False)
    assert not blockcode._never_block(MACHINE, object(), asked=False)
