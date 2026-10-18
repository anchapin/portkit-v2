"""Registration names derived from another block's registered name (#280,
portkit.blockcode).

The class files under tests/data/inheritcode are javac 21 output (build.sh):
an example library in Zeta's shapes (a registry keeping names in an identity
map with the vanilla block registry as fallback, ``inherit(parent, "%s_slab")``
formatting ``"<modid>:%s_slab"`` with the parent's registered path, an
interface whose default methods hand back the block, a slab whose constructor
throws when its parent has no module) and an example mod module registering
"jade_bricks" and "jade_tiles" and their slabs and walls, a slab of a vanilla
block, and a block handed two names.
"""
from __future__ import annotations

from pathlib import Path

from portkit import blockcode
from portkit.blockcode import UNKNOWN, Arr, Machine, Obj, RL, Tail, _format, _join
from portkit.bytecode import ClassIndex

DATA = Path(__file__).parent / "data" / "inheritcode"
READ = {
    "jade_bricks": "com/example/ilib/IBlock",
    "jade_bricks_slab": "com/example/ilib/ISlabBlock",
    "jade_bricks_wall": "com/example/ilib/IWallBlock",
    "polished_jade": "com/example/ilib/IBlock",
    "jade_tiles": "com/example/ilib/IBlock",
    "jade_tiles_slab": "com/example/ilib/ISlabBlock",
    "jade_tiles_wall": "com/example/ilib/IWallBlock",
    "onyx": "com/example/ilib/IBlock",
}
UNREAD = ["stone_slab", "onyx_slab", "onyx_wall"]
NONE = "no registration of this block was found in the mod's classes"


def _entries(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix()[:-6]: p.read_bytes() for p in root.rglob("*.class")}


def _index() -> ClassIndex:
    return ClassIndex(_entries(DATA / "classes"), _entries(DATA / "library"))


def _read(names):
    _machine, reg = blockcode._registered(_index(), list(names))
    return reg


def test_names_inherited_from_a_registered_parent_are_read():
    reg = _read([*READ, *UNREAD])
    for name, cls in READ.items():
        objs, why = reg[name]
        assert objs and objs[0].cls == cls, (name, why)


def test_a_parent_whose_registered_name_is_not_read_leaves_the_variant_unread():
    reg = _read([*READ, *UNREAD])
    # A vanilla parent (Blocks.STONE: its registered name isn't modelled) and
    # a parent handed two names (which one the registry keeps can't be told).
    for name in UNREAD:
        assert reg[name] == ([], NONE), name


def test_without_the_library_nothing_new_is_read():
    _machine, reg = blockcode._registered(ClassIndex(_entries(DATA / "classes")), [*READ, *UNREAD])
    assert all(objs == [] for objs, _why in reg.values())


def test_a_string_whose_start_is_unknown_keeps_its_path():
    assert _join(["a", "b"]) == "ab"
    assert _join([UNKNOWN, ":x_slab"]) == Tail("x_slab")
    assert _join([UNKNOWN, ":ns:x"]) == Tail("x")
    assert _join([UNKNOWN, "_slab"]) is UNKNOWN
    assert _join(["q:", UNKNOWN]) is UNKNOWN
    assert _join([Tail("oak"), "_slab"]) == Tail("oak_slab")


def test_format_with_an_unknown_namespace_then_the_parents_path():
    # Zeta's RegistryUtil#inherit: format(format("%s:%s", modid, "%s_slab"), path)
    fmt = _format(["%s:%s", Arr([UNKNOWN, "%s_slab"])])
    assert fmt == Tail("%s_slab")
    assert _format([fmt, Arr(["jade_bricks"])]) == Tail("jade_bricks_slab")
    # The known text must take exactly the arguments given (an unknown start
    # that took one would leave it short, which throws).
    assert _format([fmt, Arr(["a", "b"])]) is UNKNOWN
    assert _format([Tail("x"), Arr(["a"])]) is UNKNOWN
    assert _format([Tail("%d"), Arr([1])]) is UNKNOWN
    # Unchanged: a plain format with an unknown argument and no ":" after it.
    assert _format(["%s_slab", Arr([UNKNOWN])]) is UNKNOWN


def test_block_registry_get_key_answers_only_a_single_recorded_name():
    m = Machine(_index())
    m.registrations = []
    reg = Obj("com/example/ilib/IBlock")
    m._record([UNKNOWN, reg, "jade_bricks"])
    m._record([UNKNOWN, reg, "%s_wall"])  # a format handed with the block is no key
    key = blockcode.Const(blockcode._BUILTIN_REGISTRIES, "BLOCK")
    desc = "(Ljava/lang/Object;)Lnet/minecraft/resources/ResourceLocation;"
    assert m.vanilla("net/minecraft/core/Registry", "getKey", desc, [key, reg], False) == [RL(Tail("jade_bricks"), True)]
    other = Obj("com/example/ilib/IBlock")
    assert m.vanilla("net/minecraft/core/Registry", "getKey", desc, [key, other], False) == [UNKNOWN]
    m._record([UNKNOWN, reg, "jade_alt"])
    assert m.vanilla("net/minecraft/core/Registry", "getKey", desc, [key, reg], False) == [UNKNOWN]
    # A looked-up key handed on with another block registers nothing.
    n = len(m.registrations)
    m._record([UNKNOWN, RL(Tail("jade_bricks"), True), other])
    assert len(m.registrations) == n


def test_resource_location_path_and_namespace():
    m = Machine(_index())
    get = lambda rl, name: m.vanilla("net/minecraft/resources/ResourceLocation", name, "()Ljava/lang/String;",
                                     [rl], False)
    assert get(RL("quark:oak"), "getPath") == ["oak"]
    assert get(RL("oak"), "getNamespace") == ["minecraft"]
    assert get(RL(Tail("oak")), "getPath") == ["oak"]
    assert get(RL(Tail("oak")), "getNamespace") == [UNKNOWN]


def test_instanceof_is_exact_for_a_block_of_the_jar():
    m = Machine(_index())
    slab = Obj("com/example/ilib/ISlabBlock")
    block = Obj("com/example/ilib/IBlock")
    assert m.instance_of(None, "com/example/ilib/IEmissive") == 0
    assert m.instance_of(block, "com/example/ilib/IVariantBlock") == 1
    assert m.instance_of(block, "com/example/ilib/IEmissive") == 0
    assert m.instance_of(slab, "net/minecraft/world/level/block/SlabBlock") == 1
    assert m.instance_of(block, "com/example/ilib/ISlabBlock") == 0
    # A vanilla type the chain doesn't name: its vanilla base may be one.
    assert m.instance_of(block, "net/minecraft/world/level/block/SlabBlock") is UNKNOWN
    assert m.instance_of(UNKNOWN, "com/example/ilib/IEmissive") is UNKNOWN


def test_default_interface_methods_are_reached():
    m = Machine(_index())
    found = m.default_method("com/example/ilib/IBlock", "setTab", "(I)Lnet/minecraft/world/level/block/Block;")
    assert found is not None and found[0].name == "com/example/ilib/IVariantBlock"
    assert m.default_method("com/example/ilib/IBlock", "nothing", "()V") is None
