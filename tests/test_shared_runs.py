"""Registrations read across a mod's top-level runs (#280, portkit.blockcode):
a block constructor that hands its own name, the module runs that build such
a block and name variants from it, and a list a static final holds that one
module's run fills and another's loops over.

The class files under tests/data/sharedcode are javac 21 output (build.sh): an
example mod in Quark's shapes over ../inheritcode's example library (Zeta's
shapes), whose classes are read-only library classes here.
"""
from __future__ import annotations

from pathlib import Path

from portkit import blockcode
from portkit.blockcode import ListV, Machine
from portkit.bytecode import ClassIndex

DATA = Path(__file__).parent / "data" / "sharedcode"
NAMES = ["sturdy_stone", "plain_stone", "thatch", "thatch_slab", "thatch_wall",
         "blue_hedge", "red_hedge", "pink_bush"]


def _entries(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix()[:-6]: p.read_bytes() for p in root.rglob("*.class")}


def _index() -> ClassIndex:
    return ClassIndex(_entries(DATA / "classes"), _entries(DATA / "library"))


def _read(names=NAMES):
    machine, reg = blockcode._registered(_index(), list(names))
    return machine, reg


def _cls(reg, name):
    objs, why = reg[name]
    return objs[0].cls if objs else why


def test_a_constructor_handing_its_own_name_is_read_on_a_new_object_of_its_class():
    _m, reg = _read(["sturdy_stone"])
    assert _cls(reg, "sturdy_stone") == "com/example/smod/SturdyBlock"


def test_the_constructor_run_only_stands_in_when_no_other_run_registers_the_name():
    # SturdyModule.register (new SturdyBlock(this)) is run too; one registration, not two.
    _m, reg = _read()
    assert len(reg["sturdy_stone"][0]) == 1


def test_a_constructor_of_a_class_something_extends_is_not_read_as_that_class():
    # A subclass's object runs the same constructor: which class is registered can't be told.
    _m, reg = _read()
    assert reg["plain_stone"][0] == []
    m = Machine(_index())
    assert m.has_subclass("com/example/smod/PlainBlock")
    assert not m.has_subclass("com/example/smod/SturdyBlock")


def test_variants_named_from_a_block_its_module_builds_by_constructor_are_read():
    _m, reg = _read()
    assert _cls(reg, "thatch") == "com/example/smod/ThatchBlock"
    assert _cls(reg, "thatch_slab") == "com/example/ilib/ISlabBlock"
    assert _cls(reg, "thatch_wall") == "com/example/ilib/IWallBlock"


def test_a_loop_over_a_list_another_run_fills_is_read_in_the_second_pass():
    # HedgesModule sorts (and runs) before TreesModule; the loop waits for it.
    m, reg = _read()
    assert _cls(reg, "blue_hedge") == "com/example/ilib/IBlock"
    assert _cls(reg, "red_hedge") == "com/example/ilib/IBlock"
    trees = m.statics[("com/example/smod/TreesModule", "trees")]
    assert isinstance(trees, ListV) and trees.shared == ("com/example/smod/TreesModule", "trees")
    assert [t.fields["name"] for t in trees.items] == ["blue", "red"]


def test_a_list_a_method_the_reader_never_ran_adds_to_is_not_read():
    # OtherTreesModule.later() adds too, and isn't run: the list isn't known in full.
    m, reg = _read()
    assert reg["pink_bush"][0] == []
    others = m.statics[("com/example/smod/OtherTreesModule", "others")]
    assert not m._shared_complete(others)


def test_a_read_only_use_of_the_list_does_not_need_its_method_run():
    # TreesModule.setup() only loops over the list (the next instruction is iterator()).
    m, _reg = _read()
    trees = m.statics[("com/example/smod/TreesModule", "trees")]
    assert m._shared_complete(trees)


def test_without_registrations_a_static_list_is_not_shared():
    m = Machine(_index())
    m.init_class("com/example/smod/TreesModule")
    assert m.statics[("com/example/smod/TreesModule", "trees")].shared is None
