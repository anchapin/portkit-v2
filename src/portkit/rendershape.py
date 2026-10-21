"""How Java draws a block, read from bytecode (#352, part of #277).

Two facts per registered block class:

* **Render shape.** ``BlockBehaviour#getRenderShape(BlockState)`` (1.12:
  ``Block#getRenderType(IBlockState)``) returns ``MODEL``, ``ENTITYBLOCK_ANIMATED``
  or ``INVISIBLE`` (1.12 also ``LIQUID``). The client bakes a block's
  blockstate model into the world only for ``MODEL``: the section compiler
  (1.21.1 ``SectionCompiler#compile``, 1.20.1 ``BlockRenderDispatcher#renderBatched``)
  compares the shape with ``RenderShape.MODEL`` (``getstatic`` / ``if_acmpne``)
  before it renders the model. Any other shape is drawn by code (a block-entity
  renderer) or not at all. The method is found by its descriptor, so any name
  (Mojang, a remapped SRG/intermediary jar, 1.12/1.16 MCP class names) reads
  the same. A mod class that overrides it decides; else the first vanilla
  superclass's answer comes from :data:`VANILLA`, read from Mojang's client
  jars per game version (cited there). A game version without a table, a
  method that calls another method for its answer, or a value that is not one
  of the enum's constants is *unread*: nothing changes for that block.

* **Block-entity renderer.** A renderer class of the jar (it implements
  ``BlockEntityRenderer``, 1.12/1.16 extends ``TileEntitySpecialRenderer`` /
  ``TileEntityRenderer``) whose generic signature accepts the block's block
  entity class, and that some other class of the jar names (so it is used).
  The block's block entity classes are the ones its ``BlockEntity``-returning
  methods construct (``newBlockEntity``, 1.12 ``createNewTileEntity``) and the
  block entity classes its own generic signature names (``implements
  IBE<FooBlockEntity>``-style interfaces). A renderer accepts a class when the
  class is a subtype of a concrete block-entity type argument in the
  renderer's signature, or of every bound of one of its type parameters.
  This is read from class signatures, not from the renderer registration
  call, so it says a renderer *can* draw the block entity (labelled so).

No mod is named here (#220).
"""
from __future__ import annotations

from dataclasses import dataclass

from .bytecode import ClassIndex, instructions

# getRenderShape descriptors -> the render-shape enum class (any method name).
_SHAPE_DESCS = {
    # 1.17+ Mojang names (NeoForge, and Forge/Fabric jars read through mappings).
    "(Lnet/minecraft/world/level/block/state/BlockState;)Lnet/minecraft/world/level/block/RenderShape;":
        "net/minecraft/world/level/block/RenderShape",
    # 1.14-1.16 MCP class names (Forge SRG jars keep MCP class names).
    "(Lnet/minecraft/block/BlockState;)Lnet/minecraft/block/BlockRenderType;": "net/minecraft/block/BlockRenderType",
    # 1.12 MCP class names.
    "(Lnet/minecraft/block/state/IBlockState;)Lnet/minecraft/util/EnumBlockRenderType;":
        "net/minecraft/util/EnumBlockRenderType",
}
SHAPES = frozenset({"MODEL", "ENTITYBLOCK_ANIMATED", "INVISIBLE", "LIQUID"})
CODE_SHAPES = frozenset({"ENTITYBLOCK_ANIMATED", "INVISIBLE"})

_BE_BASES = frozenset({"net/minecraft/world/level/block/entity/BlockEntity", "net/minecraft/tileentity/TileEntity"})
_BER_BASES = frozenset({
    "net/minecraft/client/renderer/blockentity/BlockEntityRenderer",   # 1.17+ Mojang
    "net/minecraft/client/renderer/tileentity/TileEntityRenderer",     # 1.15-1.16 MCP
    "net/minecraft/client/renderer/tileentity/TileEntitySpecialRenderer",  # 1.12 MCP
})


@dataclass(frozen=True)
class VanillaShapes:
    minecraft: str
    jar_sha1: str
    mojang_sha1: str
    # Vanilla block classes (Mojang names) whose getRenderShape, resolved up
    # the vanilla hierarchy, is not MODEL. Every other vanilla subclass of
    # BlockBehaviour resolves to BlockBehaviour#getRenderShape = MODEL.
    not_model: dict

    @property
    def source(self) -> str:
        return f"Minecraft {self.minecraft} client.jar sha1 {self.jar_sha1} (names: client.txt sha1 {self.mojang_sha1})"


_P = "net/minecraft/world/level/block/"
_INVISIBLE_1192 = ("AbstractBannerBlock", "AbstractChestBlock", "AbstractSkullBlock", "AirBlock", "BannerBlock",
                   "BarrierBlock", "BaseEntityBlock", "BubbleColumnBlock", "EndGatewayBlock", "EndPortalBlock",
                   "LightBlock", "LiquidBlock", "PlayerHeadBlock", "PlayerWallHeadBlock", "SignBlock", "SkullBlock",
                   "StandingSignBlock", "StructureVoidBlock", "WallBannerBlock", "WallSignBlock", "WallSkullBlock",
                   "WitherSkullBlock", "WitherWallSkullBlock", "piston/MovingPistonBlock")
_ANIMATED = ("BedBlock", "ChestBlock", "ConduitBlock", "EnderChestBlock", "ShulkerBoxBlock", "TrappedChestBlock")
_INVISIBLE_1201 = _INVISIBLE_1192 + ("CeilingHangingSignBlock", "DecoratedPotBlock", "PiglinWallSkullBlock",
                                     "WallHangingSignBlock")


def _table(invisible, animated=_ANIMATED) -> dict:
    return {**{_P + c: "INVISIBLE" for c in invisible}, **{_P + c: "ENTITYBLOCK_ANIMATED" for c in animated}}


# Read with portkit.bytecode from each client jar: every class whose
# getRenderShape (descriptor above, through client.txt) has code, its
# getstatic RenderShape constants, resolved down the vanilla hierarchy
# (#352; the scan is described in docs/decisions.md 2026-10-21). 1.21.2+
# dropped ENTITYBLOCK_ANIMATED and BaseEntityBlock's override.
VANILLA: tuple[VanillaShapes, ...] = (
    VanillaShapes("1.19.2", "055b30d860ead928cba3849ba920c88b6950b654", "8e8c9be5dc27802caba47053d4fdea328f7f89bd",
                  _table(_INVISIBLE_1192)),
    VanillaShapes("1.20.1", "0c3ec587af28e5a785c0b4a7b8a30f9a8f78f838", "6c48521eed01fe2e8ecdadbd5ae348415f3c47da",
                  _table(_INVISIBLE_1201)),
    VanillaShapes("1.21.1", "30c73b1c5da787909b2f73340419fdf13b9def88", "2244b6f072256667bcd9a73df124d6c58de77992",
                  _table(_INVISIBLE_1201)),
    VanillaShapes("1.21.8", "a19d9badbea944a4369fd0059e53bf7286597576", "bdeb624c3aefba11d9d40f34bc96176350b549b6",
                  _table(("AirBlock", "BarrierBlock", "BubbleColumnBlock", "EndGatewayBlock", "EndPortalBlock",
                          "LightBlock", "LiquidBlock", "StructureVoidBlock", "piston/MovingPistonBlock"), ())),
)


def vanilla_for(minecraft: str | None) -> VanillaShapes | None:
    """The table for exactly the game version a mod declares, or None."""
    if not minecraft:
        return None
    if minecraft.endswith(".0"):
        minecraft = minecraft[:-2]
    return next((t for t in VANILLA if t.minecraft == minecraft), None)


@dataclass
class RenderReading:
    name: str
    cls: str | None = None
    # The shapes getRenderShape can return (one for a constant), or None (why).
    shapes: frozenset | None = None
    source: str = ""
    why: str = ""
    # Block entity classes the block makes, and renderer classes whose
    # signature accepts one of them (used somewhere in the jar).
    block_entities: tuple = ()
    renderers: tuple = ()

    @property
    def code_drawn(self) -> bool:
        """Every state's shape is one the client doesn't bake a model for."""
        return bool(self.shapes) and self.shapes <= CODE_SHAPES


def _dotted(name: str) -> str:
    return name.replace("/", ".")


def _method_shapes(cf, m, enum: str):
    """(constants, calls super) for a getRenderShape body, or (None, why)."""
    found: set[str] = set()
    calls_super = False
    for insn in instructions(cf, m.code):
        arg = insn.arg
        if insn.op == 0xB2 and getattr(arg, "owner", None) == enum:  # getstatic
            if arg.name not in SHAPES:
                return None, f"{_dotted(cf.name)}#{m.name} reads {enum.rsplit('/', 1)[-1]}.{arg.name}, not a constant read here"
            found.add(arg.name)
        elif insn.op in (0xB6, 0xB7, 0xB8, 0xB9, 0xB4) and getattr(arg, "desc", "").endswith(f"L{enum};"):
            if insn.op == 0xB7 and arg.desc == m.desc and arg.name == m.name and arg.owner != cf.name:
                calls_super = True
                continue
            return None, (f"{_dotted(cf.name)}#{m.name} takes its answer from "
                          f"{_dotted(getattr(arg, 'owner', '?'))}#{getattr(arg, 'name', '?')}, which isn't followed")
    if not found and not calls_super:
        return None, f"{_dotted(cf.name)}#{m.name} returns no constant read here"
    return found, calls_super


def _run_shapes(machine, cf, m, obj, enum: str):
    """The shapes ``m`` returns on the registered object ``obj`` (its fields
    as its constructor left them; the state unknown), or None."""
    from .blockcode import UNKNOWN, Const, Unreadable
    if machine is None or obj is None:
        return None
    machine.steps = 0
    machine.new_epoch()
    try:
        values = machine.run(cf, m, [obj, UNKNOWN])
    except Unreadable:
        return None
    if not values or any(not isinstance(v, Const) or v.owner != enum or v.name not in SHAPES for v in values):
        return None
    return {v.name for v in values}


def read_shape(classes: ClassIndex, cls: str, vanilla: VanillaShapes | None, machine=None, obj=None):
    """(shapes, source, why) for a block class, walking its superclasses.

    The first class that declares getRenderShape (by descriptor) decides:
    run on the registered object when the machine can follow it, else read
    from its constants when it returns exactly one and calls nothing. A
    vanilla superclass's answer comes from ``vanilla``."""
    seen: set[str] = set()
    name = cls
    while name and name not in seen:
        seen.add(name)
        cf = classes.get(name)
        if cf is None:  # the first vanilla superclass
            if vanilla is None:
                return None, "", (f"inherits {_dotted(name)}'s render shape, and no table of vanilla render "
                                  "shapes is pinned for the mod's game version")
            shape = vanilla.not_model.get(name, "MODEL")
            return (frozenset({shape}),
                    f"{_dotted(name)}#getRenderShape = {shape} (vanilla, inherited; {vanilla.source})", "")
        own = next((m for m in cf.methods if m.desc in _SHAPE_DESCS and m.code is not None
                    and not m.access & 0x0008), None)
        if own is not None:
            enum = _SHAPE_DESCS[own.desc]
            ran = _run_shapes(machine, cf, own, obj, enum)
            if ran is not None:
                return (frozenset(ran), f"{_dotted(cf.name)}#{own.name} = {', '.join(sorted(ran))} "
                        "(run on the registered block)", "")
            got, more = _method_shapes(cf, own, enum)
            if got is None:
                return None, "", more
            if len(got) == 1 and not more:
                return frozenset(got), f"{_dotted(cf.name)}#{own.name} = {next(iter(got))}", ""
            return None, "", (f"{_dotted(cf.name)}#{own.name} returns {', '.join(sorted(got)) or 'a value'} "
                              f"{'or its superclass answer ' if more else ''}depending on what it reads, "
                              "and the run on the registered block didn't decide it")
        name = cf.super_name
    return None, "", f"{_dotted(cls)}'s superclasses don't reach a vanilla class"


# -- block-entity renderers -------------------------------------------------

def _supertypes(classes: ClassIndex, name: str, memo: dict) -> frozenset:
    """``name`` and every class and interface above it that the index (or its
    first missing ancestor's name) shows."""
    if name in memo:
        return memo[name]
    memo[name] = frozenset({name})  # cycle guard
    out = {name}
    cf = classes.get(name)
    if cf is not None:
        for parent in (cf.super_name, *cf.interfaces):
            if parent:
                out |= _supertypes(classes, parent, memo)
    memo[name] = frozenset(out)
    return memo[name]


def _class_names(text: str) -> list[str]:
    out, i = [], 0
    while i < len(text):
        if text[i] == "L":
            j = i + 1
            while j < len(text) and text[j] not in ";<":
                j += 1
            out.append(text[i + 1:j])
            i = j
        else:
            i += 1
    return out


def _ref(sig: str, i: int) -> tuple[str | None, int]:
    """Parse one reference type signature at ``i``: (its class name, or None
    for a type variable or array, and the index after it)."""
    ch = sig[i]
    if ch == "[":
        return None, _ref(sig, i + 1)[1] if sig[i + 1] in "LT[" else i + 2
    if ch == "T":
        return None, sig.index(";", i) + 1
    if ch != "L":
        return None, i + 1
    j = i + 1
    name = ""
    while sig[j] != ";":
        if sig[j] == "<":
            j += 1
            while sig[j] != ">":
                if sig[j] == "*":
                    j += 1
                    continue
                if sig[j] in "+-":
                    j += 1
                j = _ref(sig, j)[1]
            j += 1
            continue
        if sig[j] == ".":  # inner class suffix
            name += "$"
            j += 1
            continue
        name += sig[j]
        j += 1
    return name, j + 1


def _signature_parts(sig: str) -> tuple[list[list[str]], list[str]]:
    """(per formal type parameter, its class and interface bounds; every
    class name in the superclass and interface signatures, type arguments
    included)."""
    params: list[list[str]] = []
    i = 0
    try:
        if sig.startswith("<"):
            i = 1
            while sig[i] != ">":
                i = sig.index(":", i)
                bounds = []
                while i < len(sig) and sig[i] == ":":
                    i += 1
                    if sig[i] == ":":
                        continue
                    top, i = _ref(sig, i)
                    if top:
                        bounds.append(top)
                params.append(bounds)
            i += 1
    except (IndexError, ValueError):
        return [], []
    return params, _class_names(sig[i:])


class _Renderers:
    """The jar's used block-entity renderer classes and what each accepts."""

    def __init__(self, classes: ClassIndex):
        self.classes = classes
        self.memo: dict = {}
        self.found: list[tuple[str, list[str], list[list[str]]]] = []
        names = classes.names()
        for name in names:
            cf = classes.get(name)
            if cf is None or cf.access & 0x0200:
                continue
            if not (self.supers(name) & _BER_BASES):
                continue
            # Only the class's own signature: a superclass's type parameter
            # is bound by this one (``extends Base<FooBlockEntity>``). A bound
            # or argument that is the vanilla block entity class itself says
            # nothing about which block entity the renderer draws.
            concrete: list[str] = []
            bounded: list[list[str]] = []
            if cf.signature and not cf.access & 0x0400:
                params, rest = _signature_parts(cf.signature)
                concrete = [x for x in rest if x not in _BE_BASES and self.is_be(x)]
                bounded = [p for p in params if any(x not in _BE_BASES and self.is_be(x) for x in p)]
            if (concrete or bounded) and self._used(name):
                self.found.append((name, concrete, bounded))

    def supers(self, name: str) -> frozenset:
        return _supertypes(self.classes, name, self.memo)

    def is_be(self, name: str) -> bool:
        return bool(self.supers(name) & _BE_BASES)

    def _used(self, name: str) -> bool:
        needle = name.encode()
        top = name.split("$", 1)[0]
        for other in self.classes.names():
            if other == name or other.split("$", 1)[0] == top and other.startswith(name):
                continue
            raw = self.classes.raw(other)
            if raw is not None and needle in raw:
                return True
        return False

    def accepting(self, be: str) -> list[str]:
        sup = self.supers(be)
        out = []
        for name, concrete, bounded in self.found:
            if any(c in sup for c in concrete) or any(all(b in sup for b in p) for p in bounded):
                out.append(name)
        return out


def block_entities(classes: ClassIndex, cls: str, renderers: _Renderers) -> list[str]:
    """Block entity classes a block class constructs or names in its generic signature."""
    found: list[str] = []
    seen: set[str] = set()
    name = cls
    while name and name not in seen:
        seen.add(name)
        cf = classes.get(name)
        if cf is None:
            break
        for m in cf.methods:
            ret = m.desc.rsplit(")", 1)[-1]
            if m.code is None or not ret.startswith("L") or not renderers.is_be(ret[1:-1]):
                continue
            for insn in instructions(cf, m.code):
                if insn.op == 0xBB:  # new
                    target = insn.arg[1] if isinstance(insn.arg, tuple) else None
                    if isinstance(target, str) and renderers.is_be(target):
                        found.append(target)
        if cf.signature:
            params, rest = _signature_parts(cf.signature)
            found += [x for x in rest if renderers.is_be(x)]
        name = cf.super_name
    return list(dict.fromkeys(found))


def read(classes: ClassIndex | None, registered: dict, minecraft: str | None,
         machine=None) -> dict[str, RenderReading]:
    """A :class:`RenderReading` per name of ``registered`` (name -> (block
    objects, why), as :func:`portkit.blockcode._registered` returns, run by
    ``machine``). A block refused there only for SRG/intermediary member
    names is read too (the method is found by its descriptor)."""
    renamed = getattr(machine, "renamed", None) or {}
    out: dict[str, RenderReading] = {}
    if classes is None or not len(classes):
        return {n: RenderReading(n, why="the mod ships no class files") for n in registered}
    vanilla = vanilla_for(minecraft)
    renderers: _Renderers | None = None
    for name, (objs, why) in registered.items():
        r = RenderReading(name)
        out[name] = r
        if not objs:
            objs = renamed.get(name) or []
        if not objs:
            r.why = why
            continue
        clss = sorted({o.cls for o in objs})
        if len(clss) != 1:
            r.why = "registered with different classes"
            continue
        r.cls = _dotted(clss[0])
        answers = {read_shape(classes, clss[0], vanilla, machine, o) for o in objs}
        if len(answers) != 1:
            r.why = "registered more than once with different render shapes"
            continue
        r.shapes, r.source, r.why = answers.pop()
        if r.shapes is not None and "MODEL" in r.shapes:
            if renderers is None:
                renderers = _Renderers(classes)
            bes = block_entities(classes, clss[0], renderers)
            r.block_entities = tuple(_dotted(b) for b in bes)
            r.renderers = tuple(sorted({_dotted(x) for b in bes for x in renderers.accepting(b)}))
    return out
