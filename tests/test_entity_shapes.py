"""#296: a block's shape read with the block entity its placement makes
(``blockcode._EntityWorld`` / ``_shape_call``), the block entity type
plumbing a second registration run follows for it, and Immersive
Engineering's ``entity_placement`` check. Classes are made here, not read
from any jar."""
from __future__ import annotations

from portkit import blockcode
from portkit.adapters import entity_placement
from portkit.adapters.immersiveengineering import entity_placement as ie_entity_placement
from portkit.bytecode import ClassIndex, Handle, Ref

_TYPE = "net/minecraft/world/level/block/entity/BlockEntityType"
_LEVEL_GET = blockcode._GET_BLOCK_ENTITY


def _lam(returns: str) -> blockcode.Lam:
    return blockcode.Lam(Handle(6, Ref("a/Reg", "lambda$0", "()" + returns)))


def _world(entity, obj, state) -> blockcode._EntityWorld:
    world = object.__new__(blockcode._EntityWorld)
    world.why, world.entity, world.machine, world.obj = "", entity, None, obj
    world.level, world.pos, world.state, world.asked = blockcode._PlacedLevel(), blockcode._Near(), state, ""
    return world


def test_level_answers_its_own_block_entity_only():
    be, block = blockcode.Obj("a/Be"), blockcode.Obj("a/Block")
    state = blockcode.State((("facing", blockcode.Dir("north")),))
    world = _world(be, block, state)
    hook = world.hook(None)
    level, pos = world.level, world.pos
    assert hook("net/minecraft/world/level/BlockGetter", *_LEVEL_GET, [level, pos], False) == [be]
    assert hook("net/minecraft/world/level/BlockGetter", *_LEVEL_GET, [level, pos.moved((0, 1, 0))], False) == [None]
    assert hook("net/minecraft/core/BlockPos", "above", "()Lnet/minecraft/core/BlockPos;", [pos], False) \
        == [blockcode._Near(0, 1, 0)]
    # The block entity's state is the state the shape is read at, and that
    # state's block is the block asked.
    assert hook("net/minecraft/world/level/block/entity/BlockEntity", "getBlockState",
                "()Lnet/minecraft/world/level/block/state/BlockState;", [be], False) == [state]
    assert hook("net/minecraft/world/level/block/state/BlockState", "getBlock",
                "()Lnet/minecraft/world/level/block/Block;", [state], False) == [block]
    # Anything else asked of the level is unknown, and named.
    assert hook("net/minecraft/world/level/Level", "getBlockState", "(Lnet/minecraft/core/BlockPos;)"
                "Lnet/minecraft/world/level/block/state/BlockState;", [level, pos], False) == [blockcode.UNKNOWN]
    assert world.asked == "asks the level getBlockState, which isn't read"


def test_unknown_state_is_never_taken_for_the_blocks_own():
    world = _world(blockcode.Obj("a/Be"), blockcode.Obj("a/Block"), blockcode.UNKNOWN)
    hook = world.hook(lambda *a: ["saved"])
    assert hook("net/minecraft/world/level/block/state/BlockState", "getBlock",
                "()Lnet/minecraft/world/level/block/Block;", [blockcode.UNKNOWN], False) == ["saved"]


def test_registration_with_types_makes_holders_of_type_suppliers_only():
    machine = blockcode.Machine(ClassIndex({}))
    machine.holders = machine.entity_types = True
    reg = "net/neoforged/neoforge/registries/DeferredRegister"
    desc = "(Ljava/lang/String;Ljava/util/function/Supplier;)Lnet/neoforged/neoforge/registries/DeferredHolder;"
    block = _lam("Lnet/minecraft/world/level/block/Block;")
    assert machine._holder_call(reg, "register", desc, blockcode.Obj(reg), ["lamp", block], False) \
        is blockcode._NOT_HANDLED
    kind = _lam(f"L{_TYPE};")
    got = machine._holder_call(reg, "register", desc, blockcode.Obj(reg), ["lamp", kind], False)
    assert got[0].cls == "__holder" and got[0].fields["supplier"] is kind
    # Without entity_types (read_containers) every one-supplier register is
    # a holder, as before.
    machine.entity_types = False
    assert machine._holder_call(reg, "register", desc, blockcode.Obj(reg), ["lamp", block], False)[0].cls \
        == "__holder"


def test_constructed_type_creates_through_its_factory(monkeypatch):
    machine = blockcode.Machine(ClassIndex({}))
    machine.holders = True
    factory = _lam("Lnet/minecraft/world/level/block/entity/BlockEntity;")
    calls = []
    monkeypatch.setattr(machine, "call_lambda", lambda lam, args: calls.append((lam, args)) or ["made"])
    kind = blockcode.Obj(_TYPE, {"factory": factory})
    assert machine._holder_call(_TYPE, "create", "(Lnet/minecraft/core/BlockPos;"
                                "Lnet/minecraft/world/level/block/state/BlockState;)"
                                "Lnet/minecraft/world/level/block/entity/BlockEntity;",
                                kind, ["pos", "state"], False) == ["made"]
    assert calls == [(factory, ["pos", "state"])]
    # A type the reader didn't see built (no factory) isn't created.
    assert machine._holder_call(_TYPE, "create", "(..)", blockcode.Obj(_TYPE), ["pos", "state"], False) \
        is blockcode._NOT_HANDLED


def test_joined_constructor_fields_are_named():
    out = blockcode._join_fields([{"a": 1, "b": 2}, {"a": 1, "b": 3}])
    assert out["a"] == 1 and out["b"] is blockcode.UNKNOWN
    assert out["__partial"] == blockcode._JOINED + "b different"


def test_no_adapter_no_entity_shape():
    class Mod:
        namespace = "examplemod"
    assert entity_placement(Mod(), ClassIndex({})) is None
    machine = blockcode.Machine(ClassIndex({}))
    world = blockcode._EntityWorld(machine, blockcode.Obj("a/Block"), "lamp")
    assert world.machine is None
    assert world.why == "how the mod places the block entity it makes isn't read (no adapter reads it)"


def test_ie_check_needs_ie_classes():
    assert ie_entity_placement(ClassIndex({})) is None
    assert ie_entity_placement(None) is None
