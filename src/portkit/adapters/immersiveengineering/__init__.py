"""Immersive Engineering (#296): the facing its block entities give a block after it is placed.

Immersive Engineering (BluSunrize/ImmersiveEngineering, tag ``12.4.2-194``,
the gauntlet's 1.21.1 NeoForge jar) doesn't set a directional block's
``facing`` in ``getStateForPlacement``: ``IEBaseBlock#getStateForPlacement``
(``common/blocks/IEBaseBlock.java`` L210-215) is ``defaultBlockState()`` with
``waterlogged`` from the clicked position's fluid. The facing is set once the
block is in the world:

* ``BlockItemIE#placeBlock`` (``common/blocks/BlockItemIE.java`` L96-108):
  for an ``IEBaseBlock``, refuse unless ``canIEBlockBePlaced(state, context)``
  (``IEBaseBlock`` L141-144: true), then ``super.placeBlock`` (vanilla sets the
  block and makes its block entity), then ``onIEBlockPlacedBy(context,
  state)``. Every IE block's item is a ``BlockItemIE`` (``IEBlocks#init``
  L853-874 registers each entry's item through a ``Function<Block,
  BlockItemIE>``, ``BlockItemIE::new`` unless one of its subclasses).
* ``IEEntityBlock#onIEBlockPlacedBy`` (``common/blocks/IEEntityBlock.java``
  L189-211): when the block entity at the position is an ``IDirectionalBE``,
  ``setFacing(getFacingForPlacement(context))``; then an
  ``IAdvancedDirectionalBE`` is told the hit point, an ``IHasDummyBlocks``
  places its other blocks and an ``IPlacementInteraction`` runs ``onBEPlaced``.
* ``IDirectionalBE#getFacingForPlacement`` (``IEBlockInterfaces.java`` L124-129):
  ``getFacingLimitation().getDirectionForPlacement(context)``, turned round
  when ``mirrorFacingOnPlacement(player)``; ``PlacementLimitation``
  (``common/blocks/PlacementLimitation.java``) is an enum of lambdas over the
  clicked face, the player and the point clicked.
* ``IStateBasedDirectional#setFacing`` (L170-175):
  ``setState(getState().setValue(getFacingProperty(), facing))``.

:func:`orientations` reads all of that from the jar, never from a table:

* the instructions of ``BlockItemIE#placeBlock``, ``IEEntityBlock#onIEBlockPlacedBy``,
  ``IStateBasedDirectional#setFacing`` and ``IEBaseBlock#getStateForPlacement``
  (each must be exactly the form above), and that no subclass of
  ``BlockItemIE`` overrides ``placeBlock``;
* the methods the block's class resolves (``getStateForPlacement``,
  ``canIEBlockBePlaced``, ``onIEBlockPlacedBy``, ``setPlacedBy``,
  ``onPlace``);
* which block entity the block makes: the code whose ``new`` made the
  registered block (the core's registration run records it) reads one static
  field of the mod's, its block entity type; exactly one block entity class
  of the jar gets its type from that field in a constructor, and the code
  that registers the type builds that class (``IEBlockEntities``'
  ``register(name, makeType(Foo::new, block))``, or
  ``EnergyConnectorBlockEntity#registerConnectorTEs``);
* that block entity's interfaces (an ``IAdvancedDirectionalBE`` or
  ``IHasDummyBlocks`` isn't read; an ``IPlacementInteraction`` only when its
  ``onBEPlaced`` sets no state), its facing property (``facing``), and its
  ``getFacingForPlacement`` run per clicked face by the core
  (:func:`portkit.blockcode.read_placed_direction`), which follows the
  limitation's lambda and the mirror.

A jar whose code differs gets the reason it isn't read, never a guess. The
rule given is the facing per clicked face; the core converts it as a rule read
from getStateForPlacement (Bedrock ``minecraft:block_face`` and, where the
player's facing decides, ``minecraft:cardinal_direction``).
"""
from __future__ import annotations

from .. import Adapter, Orientation

NAMESPACE = "immersiveengineering"
_IE = "blusunrize/immersiveengineering/common/blocks/"
_BASE = _IE + "IEBaseBlock"
_ENTITY_BLOCK = _IE + "IEEntityBlock"
_ITEM = _IE + "BlockItemIE"
_IFACES = _IE + "IEBlockInterfaces$"
_DIRECTIONAL = _IFACES + "IDirectionalBE"
_STATE_BASED = _IFACES + "IStateBasedDirectional"
_ADVANCED = _IFACES + "IAdvancedDirectionalBE"
_DUMMIES = _IFACES + "IHasDummyBlocks"
_PLACEMENT_INTERACTION = _IFACES + "IPlacementInteraction"
_BLOCK_ENTITY = "net/minecraft/world/level/block/entity/BlockEntity"
_CTX = "Lnet/minecraft/world/item/context/BlockPlaceContext;"
_STATE = "Lnet/minecraft/world/level/block/state/BlockState;"
_PLACEMENT_DESC = f"({_CTX}){_STATE}"
_PLACE_BLOCK_DESC = f"({_CTX}{_STATE})Z"
_PLACED_BY_DESC = f"({_CTX}{_STATE})V"
_FACING_DESC = f"({_CTX})Lnet/minecraft/core/Direction;"
_SET_FACING_DESC = "(Lnet/minecraft/core/Direction;)V"
_PROPERTY_DESC = "()Lnet/minecraft/world/level/block/state/properties/Property;"
_SET_PLACED_BY_DESC = ("(Lnet/minecraft/world/level/Level;Lnet/minecraft/core/BlockPos;" + _STATE
                       + "Lnet/minecraft/world/entity/LivingEntity;Lnet/minecraft/world/item/ItemStack;)V")
_ON_PLACE_DESC = ("(" + _STATE + "Lnet/minecraft/world/level/Level;Lnet/minecraft/core/BlockPos;" + _STATE + "Z)V")

# The compiled calls (and instanceof checks) of the methods read here, as
# tag 12.4.2-194 has them (see the module docstring for the lines).
_GET_STATE_FOR_PLACEMENT = (
    ("invokevirtual", "IEBaseBlock.defaultBlockState"), ("invokevirtual", "BlockPlaceContext.getLevel"),
    ("invokevirtual", "BlockPlaceContext.getClickedPos"), ("invokestatic", "IEBaseBlock.applyLocationalWaterlogging"),
    ("areturn", None))
_PLACE_BLOCK = (
    ("invokevirtual", "BlockState.getBlock"), ("instanceof", "IEBaseBlock"),
    ("invokevirtual", "IEBaseBlock.canIEBlockBePlaced"), ("invokespecial", "BlockItem.placeBlock"),
    ("invokevirtual", "IEBaseBlock.onIEBlockPlacedBy"), ("invokespecial", "BlockItem.placeBlock"))
_ON_PLACED = (
    ("invokevirtual", "BlockPlaceContext.getLevel"), ("invokevirtual", "BlockPlaceContext.getClickedPos"),
    ("invokevirtual", "Level.getBlockEntity"), ("invokevirtual", "BlockPlaceContext.getPlayer"),
    ("invokevirtual", "BlockPlaceContext.getClickedFace"), ("invokevirtual", "BlockPlaceContext.getClickLocation"),
    ("invokevirtual", "BlockPos.getX"), ("invokevirtual", "BlockPlaceContext.getClickLocation"),
    ("invokevirtual", "BlockPos.getY"), ("invokevirtual", "BlockPlaceContext.getClickLocation"),
    ("invokevirtual", "BlockPos.getZ"), ("instanceof", "IEBlockInterfaces$IDirectionalBE"),
    ("invokeinterface", "IEBlockInterfaces$IDirectionalBE.getFacingForPlacement"),
    ("invokeinterface", "IEBlockInterfaces$IDirectionalBE.setFacing"),
    ("instanceof", "IEBlockInterfaces$IAdvancedDirectionalBE"),
    ("invokeinterface", "IEBlockInterfaces$IAdvancedDirectionalBE.onDirectionalPlacement"),
    ("instanceof", "IEBlockInterfaces$IHasDummyBlocks"),
    ("invokeinterface", "IEBlockInterfaces$IHasDummyBlocks.placeDummies"),
    ("instanceof", "IEBlockInterfaces$IPlacementInteraction"),
    ("invokeinterface", "IEBlockInterfaces$IPlacementInteraction.onBEPlaced"))
_SET_FACING = (
    ("invokeinterface", "IEBlockInterfaces$IStateBasedDirectional.getState"),
    ("invokeinterface", "IEBlockInterfaces$IStateBasedDirectional.getFacingProperty"),
    ("invokevirtual", "BlockState.setValue"),
    ("invokeinterface", "IEBlockInterfaces$IStateBasedDirectional.setState"))
_CAN_BE_PLACED = (("iconst_1", None), ("ireturn", None))
_SET_PLACED_BY = (("invokespecial", "Block.setPlacedBy"),)
# Calls an onBEPlaced may not make for the facing read here to stand.
_SETS_STATE = frozenset({"setFacing", "setState", "setBlock", "setBlockAndUpdate", "setValue",
                         "setBlockState"})


def _short(name: str) -> str:
    return name.rsplit("/", 1)[-1]


def _shape(cf, method, keep=("invoke", "instanceof")) -> tuple:
    """The method's calls and instanceof checks (plus ``areturn`` and the
    named opcodes in ``keep``), as (opcode, Owner.name) pairs."""
    from ...bytecode import Ref, instructions
    out = []
    for insn in instructions(cf, method.code):
        if not insn.name.startswith(keep):
            continue
        arg = insn.arg
        if isinstance(arg, Ref):
            arg = f"{_short(arg.owner)}.{arg.name}"
        elif insn.name == "instanceof" and isinstance(arg, tuple):
            arg = _short(arg[1])
        else:
            arg = None
        out.append((insn.name, arg))
    return tuple(out)


def _declaring(classes, cls: str, name: str, desc: str):
    """(class file, method) of the first class from ``cls`` up that declares
    ``name``/``desc`` with code, else (None, None)."""
    seen = set()
    while cls and cls not in seen:
        seen.add(cls)
        cf = classes.get(cls)
        if cf is None:
            return None, None
        method = cf.method(name, desc)
        if method is not None and method.code is not None:
            return cf, method
        cls = cf.super_name
    return None, None


def _chain(classes, cls: str) -> list[str]:
    out, seen = [], set()
    while cls and cls not in seen:
        seen.add(cls)
        out.append(cls)
        cf = classes.get(cls)
        if cf is None:
            break
        cls = cf.super_name
    return out


def _interfaces(classes, cls: str) -> set[str]:
    """Every interface ``cls`` implements, through its superclasses and
    super-interfaces (as far as the jar holds them)."""
    out: set[str] = set()
    todo = []
    for c in _chain(classes, cls):
        cf = classes.get(c)
        if cf is not None:
            todo += list(cf.interfaces)
    while todo:
        i = todo.pop()
        if i in out:
            continue
        out.add(i)
        cf = classes.get(i)
        if cf is not None:
            todo += list(cf.interfaces)
    return out


def _mod_classes(classes):
    for name in classes.names():
        if not classes.is_library(name):
            cf = classes.get(name)
            if cf is not None:
                yield cf


def _shared_checks(classes) -> str:
    """Why the placement chain shared by every IE block isn't the form read
    here ("" when it is)."""
    cf, m = _declaring(classes, _ITEM, "placeBlock", _PLACE_BLOCK_DESC)
    if cf is None or cf.name != _ITEM or _shape(cf, m) != _PLACE_BLOCK:
        return "BlockItemIE#placeBlock isn't the form read here"
    for sub in _mod_classes(classes):
        own = sub.method("placeBlock", _PLACE_BLOCK_DESC)
        if sub.name == _ITEM or own is None or own.code is None or _ITEM not in _chain(classes, sub.super_name or ""):
            continue
        # A subclass may move the placement (BlockItemBalloon#placeBlock:
        # BlockPlaceContext.at(context, pos, context.getClickedFace()) a few
        # blocks up), as long as it hands on the clicked face to
        # BlockItemIE's and sets no state itself.
        calls = _shape(sub, own, keep=("invoke",))
        names = [a.rsplit(".", 1)[-1] for _, a in calls]
        at = [k for k, (_, a) in enumerate(calls) if a == "BlockPlaceContext.at"]
        if calls.count(("invokespecial", "BlockItemIE.placeBlock")) != 1 or set(names) & _SETS_STATE \
                or any(k == 0 or calls[k - 1][1] != "BlockPlaceContext.getClickedFace" for k in at):
            return f"{sub.name.replace('/', '.')}#placeBlock (a BlockItemIE) isn't read"
    cf, m = _declaring(classes, _ENTITY_BLOCK, "onIEBlockPlacedBy", _PLACED_BY_DESC)
    if cf is None or cf.name != _ENTITY_BLOCK or _shape(cf, m) != _ON_PLACED:
        return "IEEntityBlock#onIEBlockPlacedBy isn't the form read here"
    base = classes.get(_STATE_BASED)
    m = base.method("setFacing", _SET_FACING_DESC) if base is not None else None
    if m is None or m.code is None or _shape(base, m) != _SET_FACING:
        return "IStateBasedDirectional#setFacing isn't the form read here"
    return ""


def _block_checks(classes, cls: str) -> str:
    """Why ``cls``'s own placement isn't the chain read here ("" when it is)."""
    chain = _chain(classes, cls)
    if _ENTITY_BLOCK not in chain:
        return f"{cls.replace('/', '.')} isn't an IEEntityBlock (it makes no block entity IE places through)"
    cf, m = _declaring(classes, cls, "getStateForPlacement", _PLACEMENT_DESC)
    if cf is None or cf.name != _BASE or _shape(cf, m, keep=("invoke", "areturn")) != _GET_STATE_FOR_PLACEMENT:
        return "its getStateForPlacement isn't IEBaseBlock's (defaultBlockState with waterlogged)"
    cf, m = _declaring(classes, cls, "canIEBlockBePlaced", f"({_STATE}{_CTX})Z")
    if cf is None or cf.name != _BASE or _shape(cf, m, keep=("iconst", "ireturn")) != _CAN_BE_PLACED:
        where = cf.name.replace("/", ".") if cf is not None else cls.replace("/", ".")
        return f"{where}#canIEBlockBePlaced may refuse a placement, which isn't read"
    cf, m = _declaring(classes, cls, "onIEBlockPlacedBy", _PLACED_BY_DESC)
    if cf is None or cf.name != _ENTITY_BLOCK:
        where = cf.name.replace("/", ".") if cf is not None else cls.replace("/", ".")
        return f"{where}#onIEBlockPlacedBy isn't IEEntityBlock's"
    for name, desc in (("setPlacedBy", _SET_PLACED_BY_DESC), ("onPlace", _ON_PLACE_DESC)):
        cf, m = _declaring(classes, cls, name, desc)
        if cf is None or classes.is_library(cf.name) or not cf.name.startswith("blusunrize/"):
            continue
        if cf.name == _BASE and name == "setPlacedBy" and _shape(cf, m) == _SET_PLACED_BY:
            continue
        return f"{cf.name.replace('/', '.')}#{name} may change the placed block, which isn't read"
    return ""


def _static_reads(classes, cf, m) -> dict:
    from ...bytecode import Ref, instructions
    reads = {}
    for insn in instructions(cf, m.code):
        if insn.name == "getstatic" and isinstance(insn.arg, Ref) and not classes.is_library(insn.arg.owner) \
                and classes.get(insn.arg.owner) is not None:
            reads[(insn.arg.owner, insn.arg.name)] = insn.arg
    return reads


def _type_field(classes, site, cls: str) -> tuple[object, str]:
    """(Ref of the one static field of the mod's, its block entity type, that
    the code whose ``new`` made the block reads; or, when that code reads
    none (a constructor reference handed on, ``FooBlock::new``), that the
    block class's own constructors read), or (None, why)."""
    if not site:
        return None, "where its registered block is made isn't known"
    owner, name, desc = site
    cf = classes.get(owner)
    m = cf.method(name, desc) if cf is not None else None
    if m is None or m.code is None:
        return None, f"{owner.replace('/', '.')}#{name} isn't found"
    reads = _static_reads(classes, cf, m)
    where = f"{owner.replace('/', '.')}#{name}, which makes the block,"
    if not reads:
        own = classes.get(cls)
        for ctor in (own.methods if own is not None else ()):
            if ctor.name == "<init>" and ctor.code is not None:
                reads.update(_static_reads(classes, own, ctor))
        where = f"{where} reads none; {cls.replace('/', '.')}'s constructors"
    if len(reads) != 1:
        return None, f"{where} read {len(reads)} static fields of the mod's, not one block entity type"
    return next(iter(reads.values())), ""


def _is_entity(classes, cls: str) -> bool:
    return _BLOCK_ENTITY in _chain(classes, cls)


def _made_classes(classes, cf, insns, depth: int = 2) -> set[str]:
    """Block entity classes the method references in ``insns`` hand to the
    registry: a constructor reference (``Foo::new``), or a lambda of the
    class returning one (or returning a type, followed ``depth`` deep)."""
    from ...bytecode import Handle, instructions
    out: set[str] = set()
    for insn in insns:
        if insn.name != "invokedynamic":
            continue
        for arg in getattr(insn.arg, "args", ()) or ():
            if not isinstance(arg, Handle):
                continue
            ref = arg.ref
            if ref.name == "<init>" and _is_entity(classes, ref.owner):
                out.add(ref.owner)
                continue
            ret = ref.desc.rsplit(")", 1)[-1]
            if ret.startswith("L") and _is_entity(classes, ret[1:-1]):
                out.add(ret[1:-1])
            elif ret == "Lnet/minecraft/world/level/block/entity/BlockEntityType;" and depth > 0:
                lcf = classes.get(ref.owner)
                lm = lcf.method(ref.name, ref.desc) if lcf is not None else None
                if lm is not None and lm.code is not None:
                    out |= _made_classes(classes, lcf, instructions(lcf, lm.code), depth - 1)
    return out


def _registered_entity(classes, field) -> tuple[str | None, str]:
    """The block entity class the type in static ``field`` is registered to
    build, or (None, why): every write of the field (``putstatic``, or a
    ``Map.put`` on it) must follow, in its method, code that builds exactly
    that one class since the previous write."""
    from ...bytecode import Ref, instructions
    found: set[str] = set()
    writes = 0
    for cf in _mod_classes(classes):
        for m in cf.methods:
            if m.code is None:
                continue
            insns = instructions(cf, m.code)
            start = 0
            loaded = False
            for k, insn in enumerate(insns):
                arg = insn.arg
                same = isinstance(arg, Ref) and (arg.owner, arg.name) == (field.owner, field.name)
                if insn.name == "getstatic" and same:
                    loaded = True
                    continue
                map_put = isinstance(arg, Ref) and insn.name == "invokeinterface" \
                    and arg.owner == "java/util/Map" and arg.name == "put"
                put = (insn.name == "putstatic" and same) or (loaded and map_put)
                if not put:
                    if insn.name == "putstatic" or map_put:
                        # Another field's (or map's) registration ends here.
                        start, loaded = k + 1, False
                    continue
                if insn.name == "putstatic" and field.desc.startswith("Ljava/util/") \
                        and field.desc.endswith("Map;") and k >= 2 and insns[k - 1].name == "invokespecial" \
                        and getattr(insns[k - 1].arg, "name", "") == "<init>":
                    # The map itself made empty (``new HashMap<>()``): its
                    # types come with its ``put``s.
                    start = k + 1
                    continue
                writes += 1
                made = _made_classes(classes, cf, insns[start:k])
                if len(made) != 1:
                    return None, (f"{field.owner.replace('/', '.')}.{field.name} is written in "
                                  f"{cf.name.replace('/', '.')}#{m.name} beside {len(made)} block entity classes")
                found |= made
                start, loaded = k + 1, False
    if not writes:
        return None, f"nothing writes {field.owner.replace('/', '.')}.{field.name}"
    if len(found) != 1:
        return None, f"{field.owner.replace('/', '.')}.{field.name} holds types of {len(found)} block entity classes"
    return found.pop(), ""


def _entity_of(classes, field, memo: dict | None = None) -> tuple[str | None, str]:
    """The one block entity class whose constructor gets its type from
    ``field`` and that the field's registration builds, or (None, why);
    ``memo`` keeps the answer per field across one conversion's blocks."""
    key = (field.owner, field.name)
    if memo is not None and key in memo:
        return memo[key]
    got = _entity_of_unmemoized(classes, field)
    if memo is not None:
        memo[key] = got
    return got


def _entity_of_unmemoized(classes, field) -> tuple[str | None, str]:
    from ...bytecode import Ref, instructions
    readers = set()
    for cf in _mod_classes(classes):
        if not _is_entity(classes, cf.name):
            continue
        for m in cf.methods:
            if m.name != "<init>" or m.code is None:
                continue
            if any(i.name == "getstatic" and isinstance(i.arg, Ref)
                   and (i.arg.owner, i.arg.name) == (field.owner, field.name) for i in instructions(cf, m.code)):
                readers.add(cf.name)
    where = f"{field.owner.replace('/', '.')}.{field.name}"
    if len(readers) != 1:
        return None, f"{len(readers)} block entity classes get their type from {where}"
    be = readers.pop()
    registered, why = _registered_entity(classes, field)
    if registered is None:
        return None, why
    if registered != be:
        return None, f"{where} is registered for {registered.replace('/', '.')}, read by {be.replace('/', '.')}"
    return be, ""


def _entity_checks(classes, be: str, machine) -> tuple[str, str]:
    """(why the block entity's placement isn't read, its facing property's
    name)."""
    from ... import blockcode
    from ...bytecode import Ref, instructions
    dotted = be.replace("/", ".")
    ifaces = _interfaces(classes, be)
    if _DIRECTIONAL not in ifaces:
        return f"its block entity {dotted} isn't an IDirectionalBE, so placement leaves facing at its default", ""
    if _STATE_BASED not in ifaces:
        return f"its block entity {dotted} isn't an IStateBasedDirectional (its facing isn't a block state)", ""
    for iface, what in ((_ADVANCED, "is told the point clicked (IAdvancedDirectionalBE)"),
                        (_DUMMIES, "places more blocks (IHasDummyBlocks)")):
        if iface in ifaces:
            return f"its block entity {dotted} {what}, which isn't read", ""
    if _PLACEMENT_INTERACTION in ifaces:
        found = machine.find_method(be, "onBEPlaced", f"({_CTX})V") or machine.default_method(
            be, "onBEPlaced", f"({_CTX})V")
        if found is None:
            return f"its block entity {dotted}'s onBEPlaced isn't found", ""
        cf, m = found
        calls = {i.arg.name for i in instructions(cf, m.code or b"") if isinstance(i.arg, Ref)
                 and i.name.startswith("invoke")}
        if calls & _SETS_STATE:
            return f"{cf.name.replace('/', '.')}#onBEPlaced may set the block's state after placement", ""
    for name, desc in (("setFacing", _SET_FACING_DESC),):
        found = machine.find_method(be, name, desc)
        if found is not None and found[0].name != _STATE_BASED:
            return f"{found[0].name.replace('/', '.')}#{name} overrides IStateBasedDirectional's", ""
    found = machine.find_method(be, "getFacingProperty", _PROPERTY_DESC) or machine.default_method(
        be, "getFacingProperty", _PROPERTY_DESC)
    if found is None:
        return f"its block entity {dotted}'s getFacingProperty isn't found", ""
    obj = blockcode.Obj(be)
    obj._uninit = False
    machine.steps = 0
    try:
        props = machine.run(*found, [obj])
    except blockcode.Unreadable as exc:
        return f"{found[0].name.replace('/', '.')}#getFacingProperty can't be followed ({exc})", ""
    names = {p.name for p in props if isinstance(p, blockcode.Prop)}
    if len(names) != 1 or len(props) != len([p for p in props if isinstance(p, blockcode.Prop)]):
        return f"{found[0].name.replace('/', '.')}#getFacingProperty doesn't give one property", ""
    prop = names.pop()
    if prop not in ("facing", "facing6"):
        return f"{found[0].name.replace('/', '.')}#getFacingProperty gives {prop}, not facing", ""
    return "", prop


def orientations(mod, classes_by_name, sites=None) -> dict[str, Orientation]:
    """{blockstate name: Orientation} (``states`` ``("facing",)`` with its
    ``rule``, or its ``why``) for the names of ``classes_by_name`` whose IE
    block entity sets the facing after placement. Asked only with ``sites``
    (facing set after placement); nothing for any other question."""
    from ... import blockcode
    classes = getattr(mod, "classes", None)
    if sites is None or getattr(mod, "namespace", "") != NAMESPACE or classes is None \
            or classes.get(_BASE) is None:
        return {}
    shared = None
    machine = None
    memo: dict = {}
    out = {}
    for name, dotted in sorted(classes_by_name.items()):
        cls = (dotted or "").replace(".", "/")
        if not cls or _BASE not in _chain(classes, cls):
            continue
        if shared is None:
            shared = _shared_checks(classes)
            machine = blockcode.Machine(classes)
        why = shared or _block_checks(classes, cls)
        be = None
        if not why:
            field, why = _type_field(classes, sites.get(name), cls)
            if field is not None:
                be, why = _entity_of(classes, field, memo)
        prop = ""
        if be is not None and not why:
            why, prop = _entity_checks(classes, be, machine)
        rule = None
        if not why:
            tokens, why = blockcode.read_placed_direction(classes, be, "getFacingForPlacement", _FACING_DESC,
                                                          machine=machine)
            if tokens is not None:
                rule = {c: ("", t) for c, t in tokens.items()}
        source = ""
        if rule is not None:
            source = (f"Immersive Engineering BlockItemIE#placeBlock -> IEEntityBlock#onIEBlockPlacedBy -> "
                      f"{be.replace('/', '.')}#getFacingForPlacement -> IStateBasedDirectional#setFacing "
                      "(the block entity sets facing once the block is placed), read from the jar")
        out[name] = Orientation(states=("facing",), rule=rule, source=source, why=why if rule is None else "")
    return out


ADAPTER = Adapter(name="immersiveengineering", namespaces=frozenset({NAMESPACE}), orientations=orientations)
