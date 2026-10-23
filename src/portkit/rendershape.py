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

* **Block-entity renderer** (#355, pick 4c). The renderer the client binds
  to the block's block entity type, read from the registration call itself:
  vanilla ``BlockEntityRenderers.register(type, provider)`` (1.17+; Fabric
  jars read through mappings call it as ``BlockEntityRendererFactories``),
  Forge/NeoForge ``EntityRenderersEvent$RegisterRenderers
  #registerBlockEntityRenderer(type, provider)``, Forge 1.14-1.16
  ``ClientRegistry.bindTileEntityRenderer(type, factory)``, 1.12
  ``ClientRegistry.bindTileEntitySpecialRenderer(class, renderer)`` and
  Fabric API's ``BlockEntityRendererRegistry.register(type, factory)``.
  Each method of the jar that makes such a call is run once, as the loader
  runs a client-setup handler (on an unknown event), on a fresh machine
  that follows registry holders and block entity type builders
  (``blockcode.Machine.holders``). A call pairs a renderer class (the
  provider's constructor reference, the class a provider lambda builds, or
  the 1.12 renderer object) with a block entity class (the type's factory,
  run, or the 1.12 class literal). A block's block entity classes are the
  ones its ``BlockEntity``-returning methods construct (``newBlockEntity``,
  1.12 ``createNewTileEntity``), the ones its own generic signature names,
  and the one its own no-argument method returning its block entity type
  builds (#366, :func:`typed_entities`: a block class whose field picks one
  of several types, each registered through a library's builder, read by
  that library's adapter), which stands in for the signature's when read; a
  renderer is the block's only when a read call binds it to exactly one of
  those classes. A call that can't be read pairs nothing: the block ships as
  before, with no entry (the rule for an unread shape), never a guess from
  the renderer's class signature (which over-matches every block entity
  under a mod's own base class, #354 pick 4's known limit).

No mod is named here (#220).
"""
from __future__ import annotations

from dataclasses import dataclass

from .bytecode import ClassIndex, Handle, Indy, instructions

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
    # Block entity classes the block makes, and the renderer classes a read
    # registration call binds to one of them.
    block_entities: tuple = ()
    renderers: tuple = ()
    # The methods whose renderer registration call binds them, and the
    # block entity classes those calls name (#355).
    bound_by: tuple = ()
    bound_to: tuple = ()

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


class _Types:
    """Supertype lookups over the jar's classes (and its libraries')."""

    def __init__(self, classes: ClassIndex):
        self.classes = classes
        self.memo: dict = {}

    def supers(self, name: str) -> frozenset:
        return _supertypes(self.classes, name, self.memo)

    def is_be(self, name: str) -> bool:
        return bool(self.supers(name) & _BE_BASES)

    def is_renderer(self, name: str) -> bool:
        return bool(self.supers(name) & _BER_BASES)


# The client's block-entity renderer registration calls (#355, pick 4c),
# (owner, method) in Mojang names (a Forge SRG or Fabric intermediary jar is
# read through mappings, #235). The block entity type (1.12: its class) is
# the second-to-last argument, the renderer provider (1.12: the renderer)
# the last.
BIND_CALLS = frozenset({
    # Vanilla 1.17+ (Fabric's BlockEntityRendererFactories, yarn name).
    ("net/minecraft/client/renderer/blockentity/BlockEntityRenderers", "register"),
    # Forge 1.17+ and NeoForge, the mod-bus event.
    ("net/minecraftforge/client/event/EntityRenderersEvent$RegisterRenderers", "registerBlockEntityRenderer"),
    ("net/neoforged/neoforge/client/event/EntityRenderersEvent$RegisterRenderers", "registerBlockEntityRenderer"),
    # Forge 1.14-1.16 and 1.12.
    ("net/minecraftforge/fml/client/registry/ClientRegistry", "bindTileEntityRenderer"),
    ("net/minecraftforge/fml/client/registry/ClientRegistry", "bindTileEntitySpecialRenderer"),
    # Fabric API (v1, and the older rendereregistry package).
    ("net/fabricmc/fabric/api/client/rendering/v1/BlockEntityRendererRegistry", "register"),
    ("net/fabricmc/fabric/api/client/rendereregistry/v1/BlockEntityRendererRegistry", "register"),
})
_INVOKES = (0xB6, 0xB7, 0xB8, 0xB9)
_PROVIDER = "net/minecraft/client/renderer/blockentity/BlockEntityRendererProvider"
_PROVIDER_CREATE = (f"(L{_PROVIDER}$Context;)"
                    "Lnet/minecraft/client/renderer/blockentity/BlockEntityRenderer;")
_BE_TYPES = frozenset({"net/minecraft/world/level/block/entity/BlockEntityType",
                       "net/minecraft/tileentity/TileEntityType"})


@dataclass(frozen=True)
class Binding:
    """One renderer registration call read: the renderer class and the block
    entity class it is bound to (dotted), or None with why."""
    where: str
    renderer: str | None = None
    entity: str | None = None
    why: str = ""


def _calls_bind(cf) -> bool:
    for i in range(1, len(cf.pool)):
        try:
            c = cf.constant(i)
        except Exception:  # noqa: BLE001 - a pool slot that isn't loadable
            continue
        if getattr(c, "owner", None) is not None and (c.owner, c.name) in BIND_CALLS:
            return True
    return False


def _bind_sites(classes: ClassIndex) -> list:
    """(class, method) of every method of the mod (not its libraries) that
    calls one of BIND_CALLS."""
    sites = []
    for name in classes.names():
        cf = classes.get(name)
        if cf is None or not _calls_bind(cf):
            continue
        for m in cf.methods:
            if m.code is not None and any(_is_bind(i) for i in instructions(cf, m.code)):
                sites.append((cf, m))
    return sites


def _is_bind(insn) -> bool:
    """Whether ``insn`` calls one of BIND_CALLS, directly or by making a
    method reference to it (``event::registerBlockEntityRenderer`` handed to a
    helper that calls it as its own functional interface)."""
    arg = insn.arg
    if insn.op in _INVOKES:
        return (getattr(arg, "owner", None), getattr(arg, "name", None)) in BIND_CALLS
    if insn.op == 0xBA and isinstance(arg, Indy):
        return any(isinstance(a, Handle) and (a.ref.owner, a.ref.name) in BIND_CALLS for a in arg.args)
    return False


def _one_class(values, test) -> tuple[str | None, str]:
    from .blockcode import Obj
    clss = {v.cls for v in values if isinstance(v, Obj)}
    if not values or len(clss) != 1 or not all(isinstance(v, Obj) for v in values):
        return None, "doesn't build one object of one class"
    cls = clss.pop()
    if not test(cls):
        return None, f"builds {_dotted(cls)}"
    return cls, ""


def _renderer_of(machine, types: _Types, prov) -> tuple[str | None, str]:
    from .blockcode import Lam, Obj, UNKNOWN, Unreadable
    if isinstance(prov, Obj) and types.is_renderer(prov.cls):  # 1.12: the renderer object itself
        return prov.cls, ""
    if isinstance(prov, Obj) and _PROVIDER in types.supers(prov.cls):
        # A provider object of the mod's own class (a wrapper that caches
        # the renderer another provider builds): its ``create`` is run, as
        # the client calls it (BlockEntityRenderers#createEntityRenderers,
        # MC 1.21.1).
        machine.steps = 0
        machine.new_epoch()
        try:
            built = machine.call(prov.cls, "create", _PROVIDER_CREATE, [prov, UNKNOWN])
        except Unreadable as exc:
            return None, f"is a {_dotted(prov.cls)} whose create can't be followed ({exc})"
        return _one_class(built, types.is_renderer)
    if isinstance(prov, Obj):
        return None, f"is a {_dotted(prov.cls)}"
    if not isinstance(prov, Lam):
        return None, "isn't a value the run reads"
    if prov.handle.kind == 8:  # Renderer::new
        cls = prov.handle.ref.owner
        return (cls, "") if types.is_renderer(cls) else (None, f"constructs {_dotted(cls)}")
    machine.steps = 0
    machine.new_epoch()
    try:
        built = machine.call_lambda(prov, [UNKNOWN])
    except Unreadable as exc:
        return None, f"can't be followed ({exc})"
    return _one_class(built, types.is_renderer)


def _entity_of(machine, types: _Types, typ) -> tuple[str | None, str]:
    from .blockcode import ClassLit, Lam, Obj, UNKNOWN, Unreadable
    if isinstance(typ, ClassLit):  # 1.12: the block entity class
        return (typ.name, "") if types.is_be(typ.name) else (None, f"is the class {_dotted(typ.name)}")
    factory = None
    if isinstance(typ, Obj) and typ.cls == "__betype":  # a builder's build()
        factory = typ.fields["factory"]
    elif isinstance(typ, Obj) and typ.cls in _BE_TYPES:
        # ``new BlockEntityType(factory, validBlocks, dataType)`` (1.20.1;
        # 1.16 ``TileEntityType(supplier, validBlocks, dataType)``): the
        # factory is the first constructor argument.
        ctor = typ.fields.get("__vanilla_ctor")
        if ctor and ctor[0] == typ.cls and ctor[2] and isinstance(ctor[2][0], Lam):
            factory = ctor[2][0]
    if factory is None:
        return None, "isn't a block entity type the run builds"
    machine.steps = 0
    machine.new_epoch()
    try:
        built = machine.call_lambda(factory, [UNKNOWN, UNKNOWN])
    except Unreadable as exc:
        return None, f"its factory can't be followed ({exc})"
    return _one_class(built, types.is_be)


def _callers(classes: ClassIndex, target) -> list:
    """(class, method) of every method of the mod that invokes ``target``."""
    cf_t, m_t = target
    out = []
    owner, mname = cf_t.name.encode(), m_t.name.encode()
    for name in classes.names():
        raw = classes.raw(name)
        if raw is None or owner not in raw or mname not in raw:
            continue
        cf = classes.get(name)
        if cf is None:
            continue
        for m in cf.methods:
            if m.code is not None and (cf.name, m.name, m.desc) != (cf_t.name, m_t.name, m_t.desc) and any(
                    i.op in _INVOKES and getattr(i.arg, "owner", None) == cf_t.name
                    and getattr(i.arg, "name", None) == m_t.name and getattr(i.arg, "desc", None) == m_t.desc
                    for i in instructions(cf, m.code)):
                out.append((cf, m))
    return out


def _run_site(machine, types: _Types, cf, m) -> list[Binding]:
    from .blockcode import UNKNOWN, Unreadable, _arg_count
    where = f"{_dotted(cf.name)}#{m.name}"
    machine.binds = []
    stopped = ""
    n, _ = _arg_count(m.desc)
    try:
        machine.steps = 0
        machine.init_class(cf.name)
        machine.steps = 0
        machine.new_epoch()
        machine.run(cf, m, ([] if m.access & 0x0008 else [UNKNOWN]) + [UNKNOWN] * n)
    except Unreadable as exc:
        stopped = str(exc)
    calls, machine.binds = machine.binds, None
    out: list[Binding] = []
    if stopped:
        out.append(Binding(where, why=f"{where} can't be followed to the end ({stopped})"))
    seen = set()
    for args, _cls in calls:
        if len(args) < 2:
            continue
        renderer, rwhy = _renderer_of(machine, types, args[-1])
        entity, ewhy = _entity_of(machine, types, args[-2])
        key = (renderer, entity, rwhy, ewhy)
        if key in seen:
            continue
        seen.add(key)
        why = "; ".join(x for x in (rwhy and f"the renderer {rwhy}", ewhy and f"the type {ewhy}") if x)
        out.append(Binding(where, renderer and _dotted(renderer), entity and _dotted(entity),
                           f"a call in {where}: {why}" if why else ""))
    return out


# How many callers up a registration call made in a helper (its type and
# renderer handed in as arguments) is followed: the helper is run from each
# method that calls it, with the values that method hands it.
_CALLER_DEPTH = 2


def bindings(classes: ClassIndex | None) -> list[Binding]:
    """Every renderer registration call of the jar, read (see the module
    docstring). Each calling method is run once on unknown arguments, its
    class initialized first, on a machine of its own; when a call there
    isn't read (or the run makes none), the methods that call it are run
    the same way, up to _CALLER_DEPTH callers up, so a helper that makes
    the call with the values its caller hands it is read through its
    callers (a client-setup handler calling ``bind(event, TYPE, R::new)``)."""
    from .blockcode import Machine
    if classes is None or not len(classes):
        return []
    from . import adapters
    extra = adapters.renderer_bindings(classes)
    sites = _bind_sites(classes)
    if not sites:
        return extra
    types = _Types(classes)
    machine = Machine(classes)
    machine.holders = True
    machine.bind_calls = BIND_CALLS
    out: list[Binding] = []
    done: set = set()
    todo = [(cf, m, 0) for cf, m in sites]
    while todo:
        cf, m, depth = todo.pop(0)
        key = (cf.name, m.name, m.desc)
        if key in done:
            continue
        done.add(key)
        found = _run_site(machine, types, cf, m)
        out += found
        if depth < _CALLER_DEPTH and (not found or any(not (b.renderer and b.entity) for b in found)):
            todo += [(c, cm, depth + 1) for c, cm in _callers(classes, (cf, m))]
    return out + extra


def block_entities(classes: ClassIndex, cls: str, renderers: _Types, parts: bool = False):
    """Block entity classes a block class constructs or names in its generic
    signature; with ``parts``, (constructed, signature-named) apart."""
    found: list[str] = []
    named: list[str] = []
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
            named += [x for x in rest if renderers.is_be(x)]
        name = cf.super_name
    if parts:
        return list(dict.fromkeys(found)), list(dict.fromkeys(named))
    return list(dict.fromkeys(found + named))


# A block's own method returning its block entity type (#366), by descriptor
# (any name: the method is the mod's, or a library's interface the mod
# implements); 1.17+ Mojang names and the 1.14-1.16 MCP class name.
_TYPE_DESCS = frozenset({"()Lnet/minecraft/world/level/block/entity/BlockEntityType;",
                         "()Lnet/minecraft/tileentity/TileEntityType;"})


def _type_methods(machine, cls: str) -> list:
    """(class, method) a call on a ``cls`` object reaches for each
    non-static no-argument method returning a block entity type that its
    classes or their interfaces declare (synthetic bridges left out)."""
    keys: list = []
    todo: list = []
    for c in machine.chain(cls):
        cf = machine.classes.get(c)
        if cf is None:
            break
        todo += list(cf.interfaces)
        keys += [(m.name, m.desc) for m in cf.methods
                 if m.desc in _TYPE_DESCS and not m.access & 0x1008]
    seen: set = set()
    while todo:
        iname = todo.pop(0)
        cf = None if iname in seen else machine.classes.get(iname)
        seen.add(iname)
        if cf is None:
            continue
        todo += list(cf.interfaces)
        keys += [(m.name, m.desc) for m in cf.methods
                 if m.desc in _TYPE_DESCS and not m.access & 0x1008]
    out = []
    for name, desc in dict.fromkeys(keys):
        found = machine.find_method(cls, name, desc) or machine.default_method(cls, name, desc)
        if found is not None and not found[1].access & 0x0008:
            out.append(found)
    return out


class _TypedRun:
    """The readings of :func:`typed_entities` over one registration run's
    machine (#366): opened once, it saves the machine's static state, turns
    on registry holders and type builders (Machine.holders) and the library
    adapters' type hooks (portkit.adapters.block_entity_types), and runs
    again, under them, the class initializers the adapters name (the mod's
    classes that register types through the library: the registration run
    ran them without the library's reading, so their entries hold no type
    the core can read). Closing puts the machine back as it was, so the
    readers that share the run see it unchanged."""

    def __init__(self, machine, types: _Types):
        self.machine, self.types, self.saved = machine, types, None

    def __enter__(self):
        from . import adapters
        from .blockcode import Unreadable
        m = self.machine
        self.saved = (dict(m.statics), set(m._clinit_done), set(m._clinit_failed), m.holders, m.call_hook)
        hook, again = adapters.block_entity_types(self.types)
        m.holders, m.call_hook = True, hook
        for name in sorted(again):
            m._clinit_done.discard(name)
            m._clinit_failed.discard(name)
            m.steps = 0
            try:
                m.init_class(name)
            except Unreadable:
                m._clinit_failed.add(name)
        return self

    def __exit__(self, *exc):
        m = self.machine
        m.statics, m._clinit_done, m._clinit_failed, m.holders, m.call_hook = self.saved
        return False

    def entity(self, obj) -> tuple[str | None, str]:
        """The block entity class (slashed) ``obj``'s type methods build, or
        None with why (see :func:`typed_entities`)."""
        from .blockcode import Unreadable
        machine, types = self.machine, self.types
        methods = _type_methods(machine, obj.cls)
        if not methods:
            return None, ""
        found: set = set()
        for cf, m in methods:
            where = f"{_dotted(cf.name)}#{m.name}"
            machine.steps = 0
            machine.new_epoch()
            try:
                values = machine.run(cf, m, [obj])
            except Unreadable as exc:
                return None, f"{where} can't be followed ({exc})"
            if not values:
                return None, f"{where} returns no value the run reads"
            for v in values:
                cls, why = _entity_of(machine, types, v)
                if cls is None:
                    return None, f"the type {where} returns {why}"
                found.add(cls)
        if len(found) != 1:
            return None, ("its type methods build different block entities: "
                          + ", ".join(sorted(map(_dotted, found))))
        return found.pop(), ""


def typed_entities(machine, types: _Types, objs: dict) -> dict:
    """Per name of ``objs`` (name -> block objects of one class, built by
    ``machine``'s registration run), the block entity class (slashed) the
    type its own no-argument method returning a block entity type gives is
    built to make (#366): one block class whose field picks which of two
    registered entries' ``get()`` it returns, each a type a library's
    builder makes (read by that library's adapter). A name is
    left out unless every path of every such method, on every object,
    returns a type whose factory builds one class, the same one: a type that
    isn't read pairs nothing (never a guess from the signature)."""
    out: dict = {}
    if machine is None or not objs:
        return out
    with _TypedRun(machine, types) as run:
        for name, group in objs.items():
            got = {run.entity(o) for o in group}
            clss = {c for c, _ in got}
            if len(clss) == 1 and None not in clss:
                out[name] = clss.pop()
    return out


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
    types: _Types | None = None
    bound: dict | None = None
    model: dict = {}
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
            if types is None:
                types = _Types(classes)
                bound = {}
                for b in bindings(classes):
                    if b.renderer and b.entity:
                        bound.setdefault(b.entity, set()).add((b.renderer, b.where))
            model[name] = (objs, block_entities(classes, clss[0], types, parts=True))
    # Second pass, once every render shape is read on the machine as the
    # run left it: each MODEL block's own type method (#366).
    typed = typed_entities(machine, types, {n: objs for n, (objs, _) in model.items()}) if model else {}
    for name, (_objs, (made, named)) in model.items():
        r = out[name]
        # A type read from the block's own method stands in for the classes
        # its signature names (#366): the signature may name an abstract
        # base, or a base of the type the block really makes.
        bes = list(dict.fromkeys(made + ([typed[name]] if name in typed else named)))
        r.block_entities = tuple(_dotted(b) for b in bes)
        pairs = {p for b in r.block_entities for p in bound.get(b, ())}
        r.renderers = tuple(sorted({p[0] for p in pairs}))
        r.bound_by = tuple(sorted({p[1] for p in pairs}))
        r.bound_to = tuple(b for b in r.block_entities if b in bound)
    return out
