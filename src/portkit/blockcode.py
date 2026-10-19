"""What a block's compiled code says about its facing and its shape.

A Java block whose only state is a horizontal ``facing`` gets two things from
code alone: which way it faces when a player places it
(``getStateForPlacement``) and the box it collides with and is selected by
(``getShape``, ``getCollisionShape`` and the block's ``Properties``). This
module reads both out of the mod's class files by running the few methods
involved on a tiny abstract interpreter (:class:`Machine`):

* the placement context answers ``getHorizontalDirection()`` with a symbol
  for "the player's horizontal facing", so the state the method returns says
  how ``facing`` relates to it (the same, or ``getOpposite()``);
* ``getShape`` runs once per facing with that facing fixed in the state, and
  ``Block.box`` / ``Shapes.box`` / ``Shapes.or`` / ``Shapes.join(.., OR)`` /
  ``Stream.reduce`` / static fields / enum-switch maps / ``Map.get`` evaluate
  to the boxes Java collides with;
* the block's registration (``DeferredRegister.register("name", ...)``,
  ``Registry.register(.., id, new Block(..))`` and helpers around them) ties
  each blockstate name to the object constructed for it; a call that passes
  the block and its item as separate lambdas registers the one lambda that
  takes nothing and returns a block class, by its dynamicMethodType.

Anything the interpreter does not know is an unknown value. A branch on an
unknown value runs both ways, and the answer counts only when every way agrees.
When an answer can't be had (unknown calls in the way, ambiguous registrations,
a renamed jar), the caller gets the reason instead of a value and falls back to
a documented default; nothing here ever guesses.

Vanilla behaviour the interpreter supplies itself, read from the Minecraft
1.21.1 client jar with Mojang's mappings (client.txt):

* ``Block#getStateForPlacement`` returns ``defaultBlockState()``;
* ``BlockBehaviour#getShape`` returns ``Shapes.block()``;
* ``BlockBehaviour#getCollisionShape`` returns ``hasCollision ?
  state.getShape(level, pos) : Shapes.empty()`` (``hasCollision`` is cleared
  by ``Properties#noCollission``);
* ``HorizontalDirectionalBlock`` declares only ``FACING`` (=
  ``BlockStateProperties.HORIZONTAL_FACING``, named ``facing``), ``codec``,
  ``rotate`` and ``mirror``; ``TransparentBlock``, ``HalfTransparentBlock``
  and ``BaseEntityBlock`` don't declare any of the three methods above either.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .bytecode import ClassFile, ClassIndex, Handle, Indy, Insn, Method, Ref, instructions

# Java's Direction enum, in declaration (ordinal) order.
DIRECTIONS = ("down", "up", "north", "south", "west", "east")
HORIZONTAL = ("north", "east", "south", "west")  # clockwise from above
_VANILLA_BLOCK_PACKAGE = "net/minecraft/world/level/block/"
_BLOCK = "net/minecraft/world/level/block/Block"
# Vanilla classes known (see the module docstring) not to override
# getStateForPlacement, getShape or getCollisionShape below Block.
# HorizontalDirectionalBlock, TransparentBlock, HalfTransparentBlock and
# BaseEntityBlock declare none of the three (client.txt, 1.21.1).
_PLAIN_VANILLA = {
    _BLOCK,
    "net/minecraft/world/level/block/HorizontalDirectionalBlock",
    # DirectionalBlock declares only FACING and codec (client.txt 1.21.1).
    "net/minecraft/world/level/block/DirectionalBlock",
    "net/minecraft/world/level/block/TransparentBlock",
    "net/minecraft/world/level/block/HalfTransparentBlock",
    "net/minecraft/world/level/block/BaseEntityBlock",
}
_SHAPES = "net/minecraft/world/phys/shapes/Shapes"
_DIRECTION = "net/minecraft/core/Direction"
_PLACE_CONTEXT = "net/minecraft/world/item/context/BlockPlaceContext"
_STATE_PROPS = "net/minecraft/world/level/block/state/properties/BlockStateProperties"
_PROPERTIES = "net/minecraft/world/level/block/state/BlockBehaviour$Properties"
_GET_SHAPE_DESC = ("(Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/world/level/BlockGetter;"
                   "Lnet/minecraft/core/BlockPos;Lnet/minecraft/world/phys/shapes/CollisionContext;)"
                   "Lnet/minecraft/world/phys/shapes/VoxelShape;")
_BE_BUILDER = "net/minecraft/world/level/block/entity/BlockEntityType$Builder"
_PLACEMENT_DESC = ("(Lnet/minecraft/world/item/context/BlockPlaceContext;)"
                   "Lnet/minecraft/world/level/block/state/BlockState;")

# Vanilla property fields the interpreter knows by name: field -> property name.
_VANILLA_PROPS = {
    ("net/minecraft/world/level/block/HorizontalDirectionalBlock", "FACING"): "facing",
    (_STATE_PROPS, "HORIZONTAL_FACING"): "facing",
    (_STATE_PROPS, "FACING"): "facing6",
    # DirectionalBlock.FACING = BlockStateProperties.FACING (DirectionalBlock
    # <clinit> L8); FaceAttachedHorizontalDirectionalBlock.FACE =
    # BlockStateProperties.ATTACH_FACE, an EnumProperty named "face" of
    # AttachFace (L17); its FACING is HorizontalDirectionalBlock's (client.txt
    # 1.21.1: the class declares only FACE).
    ("net/minecraft/world/level/block/DirectionalBlock", "FACING"): "facing6",
    (_STATE_PROPS, "ATTACH_FACE"): "face",
    ("net/minecraft/world/level/block/FaceAttachedHorizontalDirectionalBlock", "FACE"): "face",
    ("net/minecraft/world/level/block/FaceAttachedHorizontalDirectionalBlock", "FACING"): "facing",
    # Every BooleanProperty field of BlockStateProperties, by the name its
    # <clinit> creates it with (BooleanProperty.create("...") into the field;
    # MC 1.21.1 client jar class dts + Mojang mappings client.txt).
    (_STATE_PROPS, "ATTACHED"): "attached",
    (_STATE_PROPS, "BOTTOM"): "bottom",
    (_STATE_PROPS, "CONDITIONAL"): "conditional",
    (_STATE_PROPS, "DISARMED"): "disarmed",
    (_STATE_PROPS, "DRAG"): "drag",
    (_STATE_PROPS, "ENABLED"): "enabled",
    (_STATE_PROPS, "EXTENDED"): "extended",
    (_STATE_PROPS, "EYE"): "eye",
    (_STATE_PROPS, "FALLING"): "falling",
    (_STATE_PROPS, "HANGING"): "hanging",
    (_STATE_PROPS, "HAS_BOTTLE_0"): "has_bottle_0",
    (_STATE_PROPS, "HAS_BOTTLE_1"): "has_bottle_1",
    (_STATE_PROPS, "HAS_BOTTLE_2"): "has_bottle_2",
    (_STATE_PROPS, "HAS_RECORD"): "has_record",
    (_STATE_PROPS, "HAS_BOOK"): "has_book",
    (_STATE_PROPS, "INVERTED"): "inverted",
    (_STATE_PROPS, "IN_WALL"): "in_wall",
    (_STATE_PROPS, "LIT"): "lit",
    (_STATE_PROPS, "LOCKED"): "locked",
    (_STATE_PROPS, "OCCUPIED"): "occupied",
    (_STATE_PROPS, "OPEN"): "open",
    (_STATE_PROPS, "PERSISTENT"): "persistent",
    (_STATE_PROPS, "POWERED"): "powered",
    (_STATE_PROPS, "SHORT"): "short",
    (_STATE_PROPS, "SIGNAL_FIRE"): "signal_fire",
    (_STATE_PROPS, "SNOWY"): "snowy",
    (_STATE_PROPS, "TRIGGERED"): "triggered",
    (_STATE_PROPS, "UNSTABLE"): "unstable",
    (_STATE_PROPS, "WATERLOGGED"): "waterlogged",
    (_STATE_PROPS, "BERRIES"): "berries",
    (_STATE_PROPS, "BLOOM"): "bloom",
    (_STATE_PROPS, "SHRIEKING"): "shrieking",
    (_STATE_PROPS, "CAN_SUMMON"): "can_summon",
    (_STATE_PROPS, "UP"): "up",
    (_STATE_PROPS, "DOWN"): "down",
    (_STATE_PROPS, "NORTH"): "north",
    (_STATE_PROPS, "EAST"): "east",
    (_STATE_PROPS, "SOUTH"): "south",
    (_STATE_PROPS, "WEST"): "west",
    (_STATE_PROPS, "CHISELED_BOOKSHELF_SLOT_0_OCCUPIED"): "slot_0_occupied",
    (_STATE_PROPS, "CHISELED_BOOKSHELF_SLOT_1_OCCUPIED"): "slot_1_occupied",
    (_STATE_PROPS, "CHISELED_BOOKSHELF_SLOT_2_OCCUPIED"): "slot_2_occupied",
    (_STATE_PROPS, "CHISELED_BOOKSHELF_SLOT_3_OCCUPIED"): "slot_3_occupied",
    (_STATE_PROPS, "CHISELED_BOOKSHELF_SLOT_4_OCCUPIED"): "slot_4_occupied",
    (_STATE_PROPS, "CHISELED_BOOKSHELF_SLOT_5_OCCUPIED"): "slot_5_occupied",
    (_STATE_PROPS, "CRACKED"): "cracked",
    (_STATE_PROPS, "CRAFTING"): "crafting",
    (_STATE_PROPS, "OMINOUS"): "ominous",
}

# Vanilla subclasses of FaceAttachedHorizontalDirectionalBlock that declare no
# getStateForPlacement of their own, and inherit FACE/FACING (client.txt
# 1.21.1: ButtonBlock, LeverBlock, GrindstoneBlock).
_FACE_ATTACHED = "net/minecraft/world/level/block/FaceAttachedHorizontalDirectionalBlock"
_FACE_ATTACHED_KIN = {
    _FACE_ATTACHED,
    "net/minecraft/world/level/block/ButtonBlock",
    "net/minecraft/world/level/block/LeverBlock",
    "net/minecraft/world/level/block/GrindstoneBlock",
}
_ATTACH_FACE = "net/minecraft/world/level/block/state/properties/AttachFace"
_CAN_SURVIVE_DESC = ("(Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/world/level/LevelReader;"
                     "Lnet/minecraft/core/BlockPos;)Z")
_ATTACH_ORDER = ("FLOOR", "WALL", "CEILING")  # AttachFace declaration order (dtn a, b, c)
# net.minecraft.world.item.DyeColor (MC 1.21.1, Mojang mappings): its
# constants in declaration (ordinal) order, each built as
# ``NAME(id, "name", ...)`` with id = the ordinal and name = the constant's
# name in lower case; ``getName()`` and ``getSerializedName()`` return that
# name (the dye ids on minecraft.wiki "Dye#Data values" are the same 0-15).
_DYE_COLOR = "net/minecraft/world/item/DyeColor"
_DYE_ORDER = ("WHITE", "ORANGE", "MAGENTA", "LIGHT_BLUE", "YELLOW", "LIME", "PINK", "GRAY", "LIGHT_GRAY",
              "CYAN", "PURPLE", "BLUE", "BROWN", "GREEN", "RED", "BLACK")

# Level methods that put a state in the world (MC 1.21.1 Level#setBlock
# (pos, state, flags) and LevelWriter#setBlockAndUpdate (pos, state)).
_SET_BLOCK = ("setBlock", "setBlockAndUpdate")
_LEVEL = "net/minecraft/world/level/Level"
# Marks a state built from StateDefinition#any (see Machine.vanilla).
_ANY = "__any"

# Steps per top-level run (#280 pick 4a of PR #330; 1,000,000 under #328 pick
# 2a): a class initializer reached from another top-level run shares that
# run's budget, and BetterEnd's EndWoodBlocks, once its wood sets' planks,
# bookshelves and signs are followed, needs about 934k on top of the 159k
# its caller used.
_MAX_STEPS = 2_000_000
_MAX_PATHS = 256
# While registrations are collected, a dependency jar's method gives up
# sooner (#280): its caller takes it as havoc (Machine._havoc), so
# exploring more of its ways only spends the step budget.
_MAX_LIBRARY_PATHS = 16
_HAVOC_STATICS = False
_MAX_DEPTH = 24


class Unreadable(Exception):
    """The code can't be read deterministically; the message says why."""


# --- Values -----------------------------------------------------------------

class _Unknown:
    _inst = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

    def __repr__(self):
        return "?"


UNKNOWN = _Unknown()


@dataclass(frozen=True)
class Dir:
    name: str

    def turned(self, quarters: int) -> "Dir":
        if self.name not in HORIZONTAL:
            raise Unreadable(f"turns a vertical direction ({self.name})")
        return Dir(HORIZONTAL[(HORIZONTAL.index(self.name) + quarters) % 4])

    def opposite(self) -> "Dir":
        pairs = {"down": "up", "up": "down"}
        if self.name in pairs:
            return Dir(pairs[self.name])
        return self.turned(2)


@dataclass(frozen=True)
class PlayerDir:
    """The player's horizontal facing, turned clockwise by ``quarters``."""

    quarters: int = 0


@dataclass(frozen=True)
class LookDir:
    """The direction the player looks along, nearest of all six
    (BlockPlaceContext#getNearestLookingDirection L68), or its opposite."""

    opposite: bool = False


@dataclass(frozen=True)
class Prop:
    name: str


@dataclass(frozen=True)
class State:
    values: tuple = ()  # sorted (property name, value) pairs

    def get(self, name):
        return dict(self.values).get(name, UNKNOWN)

    def set(self, name, value) -> "State":
        d = dict(self.values)
        d[name] = value
        return State(tuple(sorted(d.items(), key=lambda kv: kv[0])))


@dataclass(frozen=True)
class Shape:
    """A union of boxes, each (x1, y1, z1, x2, y2, z2) in pixels."""

    boxes: tuple = ()

    def union(self, other: "Shape") -> "Shape":
        return Shape(self.boxes + tuple(b for b in other.boxes if b not in self.boxes))


@dataclass(frozen=True)
class Const:
    """A vanilla static constant whose value doesn't matter, only identity."""

    owner: str
    name: str


@dataclass(frozen=True)
class ClassLit:
    name: str


@dataclass(frozen=True)
class Lam:
    handle: Handle
    captured: tuple = ()
    # The lambda's dynamicMethodType (instantiatedMethodType in older javadoc):
    # the third static argument of LambdaMetafactory.metafactory and
    # altMetafactory, "the signature and return type that should be enforced
    # dynamically at invocation time" (java.lang.invoke.LambdaMetafactory,
    # Java SE 21 javadoc). It says what this lambda takes and
    # returns at its call site, e.g. ``()Lcom/x/LampBlock;`` for a block
    # Supplier and ``(Lcom/x/LampBlock;)Lcom/x/LampItem;`` for an item
    # Function. None when the call site doesn't carry one.
    itype: str | None = None
    # The functional interface the lambda object implements (the call
    # site's return type), when made by LambdaMetafactory.metafactory: its
    # class extends Object and implements only that interface (Java SE 21,
    # LambdaMetafactory); None otherwise (altMetafactory may add markers).
    iface: str | None = None


# Every object, array, map and string builder the machine makes is numbered
# in order (``_serial``): what a path allocated after a branch it couldn't
# decide, no other path sees (Machine._write).
_ALLOCATED = [0]


def _next_serial() -> int:
    _ALLOCATED[0] += 1
    return _ALLOCATED[0]


@dataclass(eq=False)
class Obj:
    cls: str
    fields: dict = field(default_factory=dict)

    def __post_init__(self):
        self._serial = _next_serial()


@dataclass(eq=False)
class Arr:
    items: list

    def __post_init__(self):
        self._serial = _next_serial()


@dataclass(eq=False)
class MapV:
    items: dict
    # Set when a call the machine couldn't follow may have changed the map
    # (Machine._havoc, #280): a lookup in it is then unknown.
    havoc: bool = False
    # ``"linked"`` for a ``java.util.LinkedHashMap`` built here in insertion
    # order (its no-argument, capacity or capacity+load-factor constructor):
    # the only kind whose iteration order is known (see Machine._map_view).
    # ``"fixed"`` for an unmodifiable ``Map.of`` / ``Map.ofEntries`` /
    # ``ImmutableMap.of`` map (see Machine._fixed_map).
    kind: str | None = None
    # Structural changes (a key added or removed, a clear), as the map's
    # ``modCount`` (HashMap): an iterator made before one fails fast.
    mod: int = 0
    # False once anything the machine can't model exactly reached the map
    # (a key whose equality isn't known, a change on a way of a branch the
    # run can't decide, a call outside the model): then which keys it holds
    # isn't known in full (a lookup that misses is unknown, and it isn't
    # iterated).
    exact: bool = True
    # canonical key (Machine._map_key) -> the key object the map holds.
    canon: dict = field(default_factory=dict)
    # False once the map was changed on a way past a branch the run can't
    # decide (Machine._map_touch): it is then not iterated.
    clean: bool = True
    # The top-level run that allocated the map (Machine._top).
    run: int = -1

    def __post_init__(self):
        self._serial = _next_serial()


@dataclass(eq=False)
class MapView:
    """``values()`` / ``keySet()`` of a :class:`MapV` whose iteration order
    and keys are known (#280): a live view, iterated in the map's order."""

    map: MapV
    kind: str

    def __post_init__(self):
        self._serial = _next_serial()


@dataclass(eq=False)
class Builder:
    parts: list

    def __post_init__(self):
        self._serial = _next_serial()


@dataclass(eq=False)
class ListV:
    """A mutable ``java.util.ArrayList`` / ``LinkedList`` (#280 pick 2):
    its elements in order, how often it was structurally changed
    (``modCount``, AbstractList), and whether a call the machine couldn't
    follow may have changed it (then nothing about it is known)."""

    items: list
    mod: int = 0
    havoc: bool = False

    def __post_init__(self):
        self._serial = _next_serial()


@dataclass(eq=False)
class IterV:
    """An iterator over a :class:`ListV` or an immutable collection: the
    next index, and the list's ``modCount`` when it was made (a list changed
    other than through the iterator fails fast, ArrayList$Itr)."""

    source: object
    pos: int = 0
    mod: int = 0
    # (depth, method run) of the frame that called ``iterator()`` and got
    # this iterator back, while nothing else can reach it (see
    # Machine._own_iterators): each way of a branch that frame can't decide
    # then advances its own copy.
    home: tuple | None = None
    # Set once the iterator is handed anywhere but its own hasNext / next /
    # remove: stored in a field, a static or an array, passed to a call or
    # a lambda, or returned.
    escaped: bool = False

    def __post_init__(self):
        self._serial = _next_serial()


@dataclass(frozen=True)
class CollectorV:
    """A ``java.util.stream.Collectors`` collector: ``toList`` /
    ``toUnmodifiableList`` / ``toSet``-less list kinds, or ``toCollection``
    with its supplier."""

    kind: str
    supplier: object = None


@dataclass(frozen=True)
class RKey:
    """A ``ResourceKey``: the location it names (ResourceKey#create(registry,
    location), MC 1.21; ``location()`` returns it)."""

    location: object


@dataclass(frozen=True)
class Strm:
    items: tuple


@dataclass(frozen=True)
class Coll:
    """An immutable collection built from known elements (#280): Guava's
    ``ImmutableList.of`` / ``ImmutableSet.of`` and ``java.util.List.of`` /
    ``Set.of``, elements in iteration order (a Guava ImmutableSet keeps the
    first of equal elements in the order given; ``Set.of`` refuses
    duplicates, and its iteration order is unspecified, so only a set of at
    most one element is kept as known)."""

    items: tuple


@dataclass(frozen=True)
class PairV:
    """An Apache Commons Lang ``ImmutablePair`` (#280): ``Pair.of(left,
    right)`` / ``ImmutablePair.of`` keep both elements, and ``getLeft`` /
    ``getKey`` and ``getRight`` / ``getValue`` return them (commons-lang3
    3.x, org.apache.commons.lang3.tuple; Minecraft ships the library)."""

    left: object
    right: object


@dataclass(frozen=True)
class Opt:
    value: object


@dataclass(frozen=True)
class Dark:
    """The light vanilla Properties start with: ``lightEmission = state -> 0``
    (BlockBehaviour$Properties#<init>, MC 1.21.1; its lambda is ``iconst_0;
    ireturn``)."""


DARK = Dark()


@dataclass(frozen=True)
class CopiedLight:
    """The light of a vanilla block whose Properties were copied
    (``ofFullCopy``/``ofLegacyCopy`` copy ``lightEmission``, MC 1.21.1)."""

    source: str


@dataclass
class Props:
    """BlockBehaviour.Properties, as far as collision and light go.

    ``light`` is the ToIntFunction<BlockState> Java's states take their light
    from: :data:`DARK` (never set), a :class:`Lam` or mod object (set with
    ``lightLevel``), a :class:`CopiedLight`, or UNKNOWN.
    """

    has_collision: object = True  # True, False or UNKNOWN
    light: object = DARK
    # The evaluation (a class initialiser or one registration's supplier)
    # that built it; a change made from another one marks it shared_changed,
    # since which blocks see that change then depends on registration order.
    epoch: int = 0
    shared_changed: bool = False
    # For the copy a block keeps: the Properties object it was taken from.
    origin: object = None


@dataclass(frozen=True)
class Tail:
    """A string whose start is unknown but which is known to end with ``":"``
    followed by ``text`` (``text`` has no ``":"``): a resource location
    whose namespace isn't known but whose path is (#280, a name derived from
    another block's registered name, ``String.format("%s:%s", modid, ..)``).
    Its last ``:``-separated segment, which is what a registration name is
    matched by (``_record`` drops the namespace), is ``text`` exactly,
    whatever the unknown start holds."""

    text: str


@dataclass(frozen=True)
class RL:
    path: "str | Tail"  # "namespace:path" (or just "path"), or a Tail
    # Set on the key a block registry's getKey answered (Machine._registry_key):
    # it names a registration already made, so handing it on with a block
    # (a potted plant's pot filed under its plant's key) registers nothing.
    lookup: bool = False


class _Ctx:
    """A BlockPlaceContext. ``clicked`` is the face the player clicked
    (UseOnContext#getClickedFace), fixed per run by read_directional;
    None everywhere else, where only the player's horizontal facing is known."""

    def __init__(self, clicked: str | None = None):
        self.clicked = clicked

    def __repr__(self):
        return "ctx" if self.clicked is None else f"ctx({self.clicked})"


PLACE_CTX = _Ctx()


@dataclass
class Frame:
    pc: int
    locals: list
    stack: list
    forked: bool = False
    # The blocks this path set in the world (Level#setBlock), as (pos,
    # state) pairs, when the machine tracks them (Machine.effects).
    effects: tuple = ()
    # The last ``_serial`` allocated when this path last passed a branch it
    # couldn't decide: what is allocated after it, no other path sees (see
    # Machine._write).
    fork_serial: int = -1
    # In a constructor run (Machine._run_code), the receiver's fields as this
    # path left them: each path after an undecided branch writes its own copy,
    # and the copies are joined where the constructor returns (#280).
    recv_fields: dict | None = None

    def copy(self) -> "Frame":
        return Frame(self.pc, list(self.locals), list(self.stack), True, self.effects)


def _arg_count(desc: str) -> tuple[int, bool]:
    """(number of arguments, returns a value) for a method descriptor."""
    i, n = 1, 0
    while desc[i] != ")":
        c = desc[i]
        while c == "[":
            i += 1
            c = desc[i]
        if c == "L":
            i = desc.index(";", i)
        i += 1
        n += 1
    return n, desc[i + 1] != "V"


def _arg_kinds(desc: str) -> list[str]:
    """One descriptor letter per argument of ``desc`` (``L`` for any
    reference, ``[`` arrays included)."""
    out, i = [], 1
    while i < len(desc) and desc[i] != ")":
        c = desc[i]
        if c == "[":
            while desc[i] == "[":
                i += 1
            if desc[i] == "L":
                i = desc.index(";", i)
            out.append("L")
        elif c == "L":
            i = desc.index(";", i)
            out.append("L")
        else:
            out.append(c)
        i += 1
    return out


def _join(pieces: list):
    """The concatenation of ``pieces`` (strings, UNKNOWN or :class:`Tail`):
    the string when every piece is known; else a :class:`Tail` of what
    follows the last ``":"`` after the last unknown piece, when that run is
    known and holds a ``":"``; else UNKNOWN. A Tail piece is an unknown start
    and ``":" + text``."""
    flat = []
    for p in pieces:
        if isinstance(p, Tail):
            flat += [UNKNOWN, ":" + p.text]
        else:
            flat.append(p if isinstance(p, str) else UNKNOWN)
    if all(isinstance(p, str) for p in flat):
        return "".join(flat)
    last = max(k for k, p in enumerate(flat) if not isinstance(p, str))
    after = "".join(flat[last + 1:])
    if ":" not in after:
        return UNKNOWN
    return Tail(after.rsplit(":", 1)[1])


def _format(rest: list):
    """``String.format(fmt, args)`` for a format of only ``%s`` and ``%%``;
    anything else is unknown. An argument that isn't a known string prints
    as an unknown piece (see :func:`_join`). A format that is a
    :class:`Tail` (``"<unknown>:%s_slab"``) formats its known text only when
    that text's ``%s`` take exactly the arguments given: no format specifier
    can span the ``":"`` (``:`` is not a conversion character, so a
    specifier the unknown start opens throws), and one there that takes an
    argument leaves the text's ``%s`` one short, which throws; so whenever
    the call returns, the text's ``%s`` took the arguments in order
    (java.util.Formatter, Java SE 21 javadoc)."""
    fmt, arr = rest
    if not isinstance(arr, Arr):
        return UNKNOWN
    head = []
    if isinstance(fmt, Tail):
        head, fmt = [UNKNOWN, ":"], fmt.text
    if not isinstance(fmt, str):
        return UNKNOWN
    out, k, i = list(head), 0, 0
    while i < len(fmt):
        c = fmt[i]
        if c != "%":
            out.append(c)
            i += 1
            continue
        spec = fmt[i + 1:i + 2]
        if spec == "%":
            out.append("%")
        elif spec == "s" and k < len(arr.items):
            item = arr.items[k]
            out.append(item if isinstance(item, (str, Tail)) else UNKNOWN)
            k += 1
        else:
            return UNKNOWN
        i += 2
    if head and k != len(arr.items):
        return UNKNOWN
    return _join(out)


def _snapshot(props):
    if not isinstance(props, Props):
        return props
    return Props(props.has_collision, props.light, props.epoch, origin=props.origin or props)


def _shared_changed(props) -> bool:
    """Whether the Properties a block was built from were changed by another
    evaluation than the one that built them (see Props.epoch)."""
    return isinstance(props, Props) and isinstance(props.origin, Props) and props.origin.shared_changed


def _only_objects(desc: str) -> bool:
    """Whether every argument in a method descriptor is a plain object
    reference (so splitting on ';' indexes them)."""
    inner = desc[1:desc.index(")")]
    return all(part.startswith("L") for part in inner.split(";") if part)


def _is_wide(desc_char: str) -> bool:
    return desc_char in "JD"


@dataclass
class Registration:
    name: str
    value: object  # Lam or Obj; None when the call can't be read (see why)
    why: str = ""
    # Recorded while running a method chosen because it may build a name by
    # concatenation (_piece_methods): it counts only if it builds a block,
    # never as the reason another name went unread.
    concat: bool = False


class Machine:
    """Runs the methods of one mod's classes on abstract values."""

    def __init__(self, classes: ClassIndex):
        self.classes = classes
        self._subclassed: set | None = None  # see has_subclass
        self.statics: dict[tuple[str, str], object] = {}
        self._clinit_done: set[str] = set()
        self._clinit_failed: set[str] = set()
        self.steps = 0
        self.registrations: list[Registration] | None = None
        # id(block object) -> (the object, the names it was registered
        # with), as recorded by _record: what a block registry's getKey
        # answers for it (see _registry_key, #280).
        self.names_of: dict[int, tuple] = {}
        # (instructions, offset -> index) of each method being run, innermost
        # last (see _throws_only).
        self._code: list = []
        # The class of each method being run, innermost last.
        self._running: list = []
        self.depth = 0
        # Whether the instruction being run sits after an undecided branch.
        self._forked = False
        # (depth, receiver) of each constructor being run (see _run_code):
        # its paths may write to the receiver after a branch they can't
        # decide, each on its own copy of its fields, joined at the end.
        self._receivers: list = []
        # Which evaluation is running (see Props.epoch).
        self.epoch = 0
        self._epochs = 0
        # BlockState property names read (getValue) while it is a set.
        self.state_reads: set | None = None
        # While a list: (return value, effects) per path of the method run at
        # depth ``effects_depth``, whose Level#setBlock calls are recorded on
        # its frames instead of being unknown calls (see read_toggle).
        self.effects: list | None = None
        self.effects_depth = 0
        # Set when a method that method calls sets a block itself.
        self.deep_effect = False
        # While reading a 6-way / attach-face placement (read_directional):
        # BlockState#canSurvive answers true, and support_assumed records it.
        self.assume_support = False
        self.support_assumed = False
        # While reading a block entity (read_containers): registry holders,
        # BlockEntityType builders and BlockEntityType#create are followed
        # (see _holder_call) instead of being unknown calls.
        self.holders = False
        # (class, static field) -> whether it reads as null until written
        # (see _lazy_null).
        self._lazy: dict = {}
        # Whether a class of the mod or its libraries can change a system
        # property (see _system_property); computed on first use.
        self._sets_properties: bool | None = None
        # How many library calls the run couldn't follow and took as havoc
        # (see _havoc), with the first reason.
        self.havocs: list = []
        # The frame of the call being made (see _invoke): a modelled change
        # to a mutable java.util collection is a write by it (see _write).
        self._frame: Frame | None = None
        # The latest ``fork_serial`` of any frame on the call stack that is
        # past a branch it can't decide (see _invoke, _map_touch): a change
        # to a map allocated before it may happen on one way only.
        self._fork_floor = -1
        # Counts top-level runs (a run entered at depth 0, see run).
        self._top = 0

    # -- classes ------------------------------------------------------------

    def is_mod(self, name: str | None) -> bool:
        return name is not None and self.classes.get(name) is not None

    def chain(self, name: str) -> list[str]:
        """``name`` and its superclasses, as far as the mod's classes go,
        then the first vanilla superclass."""
        out = []
        seen = set()
        while name and name not in seen:
            seen.add(name)
            out.append(name)
            cf = self.classes.get(name)
            if cf is None:
                break
            name = cf.super_name
        return out

    def _library(self, name: str) -> bool:
        lib = getattr(self.classes, "is_library", None)
        return bool(lib and lib(name))

    def has_subclass(self, name: str) -> bool:
        """Whether any class of the mod or its libraries names ``name`` as
        its superclass (a class that can't be parsed counts as one)."""
        if self._subclassed is None:
            supers = set()
            for src in (self.classes._raw, self.classes._lib):
                for k in src:
                    cf = self.classes.get(k)
                    if cf is None:
                        supers.add(None)
                    elif cf.super_name:
                        supers.add(cf.super_name)
            self._subclassed = supers
        return name in self._subclassed or None in self._subclassed

    def is_block_class(self, name: str) -> bool:
        last = self.chain(name)[-1]
        return last.startswith(_VANILLA_BLOCK_PACKAGE) and "/entity/" not in last \
            and "/state/" not in last and last.rsplit("/", 1)[-1].endswith("Block")

    def find_method(self, start: str, name: str, desc: str) -> tuple[ClassFile, Method] | None:
        for cname in self.chain(start):
            cf = self.classes.get(cname)
            if cf is None:
                return None
            m = cf.method(name, desc)
            if m is not None and m.code is not None:
                return cf, m
            if m is not None:  # abstract
                continue
        return None

    def default_method(self, start: str, name: str, desc: str) -> tuple[ClassFile, Method] | None:
        """An interface's default method that a call on a ``start`` object
        reaches when no class in its chain declares one (JVMS 5.4.3.3 /
        5.4.6: the maximally-specific superinterface method that isn't
        abstract), searched in the interfaces of the classes in the jar
        and their superinterfaces. None unless exactly one interface has a
        non-abstract one and none of the chain's classes declares the method
        at all (a vanilla superclass might, out of sight)."""
        chain = [c for c in self.chain(start) if self.classes.get(c) is not None]
        found, seen = [], set()
        todo = [i for c in chain for i in self.classes.get(c).interfaces]
        while todo:
            iname = todo.pop(0)
            if iname in seen:
                continue
            seen.add(iname)
            cf = self.classes.get(iname)
            if cf is None:
                continue
            m = cf.method(name, desc)
            if m is not None and m.code is not None and not m.access & 0x0008:
                found.append((cf, m))
                continue  # a superinterface's is less specific
            todo.extend(cf.interfaces)
        return found[0] if len({cf.name for cf, _m in found}) == 1 else None

    def instance_of(self, v, cls) -> object:
        """``v instanceof cls`` (1 or 0), or UNKNOWN. Exact for null and for
        an object of a class in the jar: its superclasses are known as far as
        its vanilla base, and a vanilla class can't extend or implement a
        class or interface of the jar, so a jar type that isn't among them
        isn't one of its types. A vanilla type beyond the vanilla base is
        unknown (#280: Zeta's ``parent instanceof IVariantsShouldBeEmissive``
        on a block of the jar)."""
        if v is None:
            return 0
        if isinstance(cls, str) and self._vanilla_block_id(v) is not None and self.is_mod(cls):
            # A vanilla Blocks constant is an object of a vanilla class (#280).
            return 0
        if isinstance(v, Lam) and v.iface is not None and isinstance(cls, str) and self.is_mod(cls):
            # A lambda's class extends Object and implements only its
            # functional interface (#280: ``setter instanceof TraitOp``).
            target = self.classes.get(cls)
            if not target.access & 0x0200:
                return 0
            seen, todo = set(), [v.iface]
            while todo:
                name = todo.pop()
                if name == cls:
                    return 1
                if name in seen:
                    continue
                seen.add(name)
                icf = self.classes.get(name)
                if icf is None:
                    return UNKNOWN  # a vanilla or java interface: its supers aren't known here
                todo.extend(icf.interfaces)
            return 0
        if not isinstance(v, Obj) or not isinstance(cls, str) or not self.is_mod(v.cls):
            return UNKNOWN
        chain = self.chain(v.cls)
        if cls in chain:
            return 1
        target = self.classes.get(cls)
        if target is None:
            return UNKNOWN  # a vanilla type: the vanilla base may be one
        if not target.access & 0x0200:
            return 0
        seen, todo = set(), [i for c in chain if self.classes.get(c) is not None
                             for i in self.classes.get(c).interfaces]
        while todo:
            name = todo.pop()
            if name == cls:
                return 1
            if name in seen:
                continue
            seen.add(name)
            cf = self.classes.get(name)
            if cf is not None:
                todo.extend(cf.interfaces)
        return 0

    def vanilla_base(self, start: str) -> str:
        return self.chain(start)[-1]

    # -- statics ------------------------------------------------------------

    def _field_owner(self, owner: str, name: str) -> str:
        """The class that declares a static field referenced through ``owner``."""
        todo = [owner]
        seen = set()
        while todo:
            cname = todo.pop(0)
            if cname in seen:
                continue
            seen.add(cname)
            cf = self.classes.get(cname)
            if cf is None:
                if cname == owner:
                    return owner
                continue
            if name in cf.fields:
                return cname
            if cf.super_name:
                todo.append(cf.super_name)
            todo.extend(cf.interfaces)
        # Inherited from a vanilla class: the first non-mod class in the chain.
        return self.vanilla_base(owner)

    def init_class(self, name: str) -> None:
        if name in self._clinit_done or not self.is_mod(name):
            return
        self._clinit_done.add(name)
        cf = self.classes.get(name)
        if cf.super_name:
            self.init_class(cf.super_name)
        m = cf.method("<clinit>", "()V")
        if m is None or m.code is None:
            return
        saved = self.epoch
        self.new_epoch()
        try:
            self.run(cf, m, [])
        except Unreadable:
            self._clinit_failed.add(name)
        finally:
            self.epoch = saved

    def new_epoch(self) -> None:
        self._epochs += 1
        self.epoch = self._epochs

    def get_static(self, ref: Ref):
        owner = self._field_owner(ref.owner, ref.name)
        if self.is_mod(owner):
            self.init_class(owner)
            return self.statics.get((owner, ref.name), UNKNOWN)
        prop = _VANILLA_PROPS.get((owner, ref.name))
        if prop is None and owner in _FACE_ATTACHED_KIN:
            prop = _VANILLA_PROPS.get((_FACE_ATTACHED, ref.name))
        if prop is not None:
            return Prop(prop)
        if owner == _DIRECTION and ref.name.lower() in DIRECTIONS:
            return Dir(ref.name.lower())
        return Const(owner, ref.name)

    def _lazy_guard(self, insn: Insn) -> bool:
        """Whether ``insn``, a ``getstatic F`` the run is at, is the test of
        a lazy-initialisation guard ``if (F == null) F = <expr>;``
        (``getstatic F; ifnonnull L; ...; putstatic F; L:``, #280) on a
        field that only such guards write (see _lazy_field). Such a test
        may be taken as finding null: when the field is set, it holds what
        an earlier run of a guard on it computed, so running the guard's
        computation again yields what the read would have (javac's lazy
        singleton, e.g. ``getBlockRegistry()``). Only the guard's own test
        is read this way; any other read of the field is as before."""
        found = self._code[-1] if self._code else None
        if found is None:
            return False
        _depth, code, at = found
        k = at.get(insn.offset)
        if k is None or k + 1 >= len(code) or code[k + 1].op != 0xC7 or not isinstance(insn.arg, Ref):
            return False
        owner = self._field_owner(insn.arg.owner, insn.arg.name)
        if not self.is_mod(owner) or not self._lazy_field(owner, insn.arg.name):
            return False
        target = code[k + 1].arg
        # The write this test guards: its guard must be this very test, not
        # an inner one (code between two tests may run in the game only
        # while the field is null).
        return any(c.op == 0xB3 and isinstance(c.arg, Ref) and c.arg.name == insn.arg.name
                   and code[i + 1].offset == target
                   and _lazy_guarded(code, i, owner, insn.arg.name, self) == k + 1
                   for i, c in enumerate(code[k + 2:], k + 2) if i + 1 < len(code))

    def _lazy_field(self, owner: str, name: str) -> bool:
        """Whether static ``owner.name`` is written only by a lazy-
        initialisation guard: a private, non-final reference field without
        a ConstantValue (so only its own nest can write it, JVMS 5.4.4,
        and it starts null, JVMS 2.3, 5.4.2) with exactly one ``putstatic``
        in its nest's classes, its static initializer included, and that
        one guarded (see _lazy_guarded). One write, so a set field holds
        what that same guard computed: two guards could compute different
        values, and which ran first in the game isn't known."""
        key = (owner, name)
        if key in self._lazy:
            return self._lazy[key]
        self._lazy[key] = False
        cf = self.classes.get(owner)
        access = getattr(cf, "field_access", {}).get(name) if cf is not None else None
        desc = cf.fields.get(name, "") if cf is not None else ""
        # ACC_STATIC and ACC_PRIVATE set; ACC_FINAL and ConstantValue not.
        if access is None or access & 0x1001A != 0x000A or not desc.startswith(("L", "[")):
            return False
        nest = getattr(self.classes, "nest", None)
        writers = 0
        for cname in (nest(owner) if nest else [owner]):
            other = self.classes.get(cname)
            if other is None:
                continue
            for m in other.methods:
                if m.code is None:
                    continue
                code = instructions(other, m.code)
                for k, insn in enumerate(code):
                    if insn.op != 0xB3 or not isinstance(insn.arg, Ref) or insn.arg.name != name \
                            or self._field_owner(insn.arg.owner, name) != owner:
                        continue
                    if _lazy_guarded(code, k, owner, name, self) is None:
                        return False
                    writers += 1
        self._lazy[key] = writers == 1
        return self._lazy[key]

    # -- running ------------------------------------------------------------

    def call(self, owner: str, name: str, desc: str, args: list, special: bool = False,
             static: bool = False) -> list:
        """Possible results of calling ``owner.name(desc)`` with ``args``
        (receiver first unless static)."""
        recv = None if static or not args else args[0]
        if isinstance(recv, Lam) and name not in ("equals", "hashCode", "toString"):
            return self.call_lambda(recv, args[1:])
        if self.assume_support and name == "canSurvive" and desc == _CAN_SURVIVE_DESC:
            # The block's own canSurvive(state, level, pos), called directly
            # while a placement is read: assumed true (see read_directional).
            self.support_assumed = True
            return [1]
        start = recv.cls if isinstance(recv, Obj) and not special and not static else owner
        if self.is_mod(start) and self.registrations is not None and self._library(owner):
            # A call into a dependency jar's code (#280) is a registration
            # the same way a call into code that isn't there is (a name and
            # the block handed to it, see _record), and is followed as well.
            # The object it is called on, when it is one of the jar's own
            # objects and no block (a library's registry or block builder),
            # is what the call is made on, not something handed to it (#280
            # pick 4: ``registry.defineDefaultBlock(name, factory)`` once the
            # registry is known).
            handed = args[1:] if recv is not None and isinstance(recv, Obj) and self.is_mod(recv.cls) \
                and not self.is_block_class(recv.cls) else args
            self._record(handed)
        if self.is_mod(start):
            if static:
                self.init_class(start)
            found = self.find_method(start, name, desc)
            if found is not None:
                if self.registrations is None or not self._library(found[0].name):
                    return self.run(*found, args)
                try:
                    results = self.run(*found, args)
                except Unreadable as exc:
                    if str(exc) == _TOO_MUCH:
                        raise
                    # A dependency jar's method the registration run can't
                    # follow (#280 pick 4): taken as havoc on everything it
                    # could write, what it returns unknown.
                    self._havoc(args, f"{found[0].name}.{name}: {exc}")
                    return [UNKNOWN] if _arg_count(desc)[1] else [None]
                if len(results) > 1 and not all(_value_equal(r, results[0]) for r in results[1:]) \
                        and not (self._running and self._library(self._running[-1])) \
                        and not any(isinstance(r, (str, Tail, RL, RKey)) for r in results):
                    # Its ways return different values, none of them a name:
                    # the mod's code goes on with one unknown value instead
                    # of one way per value (what the ways wrote after their
                    # branch is only what they allocated since, see _write,
                    # so nothing else differs between them). A name a way
                    # returns keeps its own way (#325: the way where the
                    # library's lookup answered registers that name).
                    return [UNKNOWN]
                return results
            vowner = self.vanilla_base(start)
        else:
            vowner = owner
        handled = self.vanilla(vowner, name, desc, args, static)
        if handled is not _NOT_HANDLED:
            return handled
        if self.is_mod(start) and not static:
            # Neither the jar's classes nor what is modelled of vanilla
            # answer it: an interface's default method in the jar may (#280,
            # Zeta's IZetaBlock#setCreativeTab returning the block).
            found = self.default_method(start, name, desc)
            if found is not None:
                return self.run(*found, args)
        if not (owner in _JAVA_MAPS and name in ("put", "putIfAbsent")):
            # A java.util Map#put stores a pair in a map; it registers
            # nothing (#280: a library's ``colorProviderNames.put(crystal,
            # "<stone>")`` had filed a crystal block under a stone's name).
            self._record(args)
        _n, returns = _arg_count(desc)
        for a in args:
            if isinstance(a, Arr):
                a.items = [UNKNOWN] * len(a.items)
            elif isinstance(a, MapV):
                a.items, a.havoc, a.exact = {}, True, False
            elif isinstance(a, ListV):
                a.items, a.havoc = [], True
                a.mod += 1
            elif isinstance(a, Obj):
                # Code that isn't there may set any field of an object handed
                # to it (by reflection, an event bus, a config loader), so a
                # field nothing here wrote no longer reads as its default.
                a._defaults = False
        return [UNKNOWN] if returns else [None]

    def _system_property(self, key):
        """``System.getProperty(key)`` (#280 pick 1): null for a known key
        outside what the JVM and the game's launchers define
        (_RESERVED_PROPERTIES) when no class of the mod or its libraries
        can set a system property (``System.setProperty``,
        ``setProperties``, ``clearProperty`` or the mutable
        ``getProperties()``), as in a player's game started without
        ``-D<key>``; anything else is unknown."""
        if not isinstance(key, str) or not key or key.startswith(_RESERVED_PROPERTIES):
            return UNKNOWN
        if self._sets_properties is None:
            self._sets_properties = self._can_set_properties()
        return UNKNOWN if self._sets_properties else None

    def _can_set_properties(self) -> bool:
        """Whether a class of the mod or its libraries can change a system
        property: its constant pool refers to ``java.lang.System``'s
        ``setProperty``, ``setProperties``, ``clearProperty`` or
        ``getProperties`` (the one way to the mutable system Properties
        object, java.lang.System, Java SE 21), or holds one of those names
        as a string constant (a reflective lookup). A method or field of
        another class that happens to carry such a name (a server.properties
        ``Properties#setProperty``, a builder's ``setProperties``) can't."""
        classes = self.classes
        mentions = getattr(classes, "mentions", None)
        raws = getattr(classes, "_raw", None), getattr(classes, "_lib", None)
        if mentions is None or raws[0] is None or raws[1] is None:
            return True
        needles = (b"setProperty", b"setProperties", b"clearProperty", b"getProperties")
        for src in raws:
            for name, raw in src.items():
                if not any(n in raw for n in needles):
                    continue
                cf = classes.get(name, remap=False)
                if cf is None:
                    return True
                for k, entry in enumerate(cf.pool):
                    if entry is None or entry[0] not in _SETTER_TAGS:
                        continue
                    c = cf.constant(k)
                    if isinstance(c, Handle):
                        c = c.ref
                    if isinstance(c, Ref) and c.owner == "java/lang/System" and c.name in _SYSTEM_SETTERS:
                        return True
                    if entry[0] == _CP_STRING and c in _SYSTEM_SETTERS:
                        return True
        return False

    def _havoc(self, roots: list, why: str) -> None:
        """What a call the machine couldn't follow may have written is made
        unknown (#280 pick 4a): every object, array, map and string builder
        reachable from the call's receiver and arguments loses what it held
        (statics are kept unless ``_HAVOC_STATICS``, pick 4b, which also
        drops every non-final static and havocs what the finals reach;
        measured worse: Quark reads 145 fewer, BetterEnd the same): its
        non-final fields (as the mod's and
        libraries' classes declare them; every field of a vanilla object)
        read unknown, an array's elements and a builder's text are unknown,
        a map's lookups are unknown, and a Properties object's collision
        and light are unknown. Final fields keep their values (JVMS 6.5
        putfield/putstatic: a final field is written only by its own class's
        constructor or initializer). Making a value unknown holds for every
        way of a fork, so it is allowed after a branch the run can't decide."""
        self.havocs.append(why)
        todo = list(roots)
        if _HAVOC_STATICS:
            for (owner, fname), value in list(self.statics.items()):
                if self._final_field(owner, fname):
                    todo.append(value)
                else:
                    del self.statics[(owner, fname)]
        seen: set = set()
        while todo:
            v = todo.pop()
            if id(v) in seen or not isinstance(v, (Obj, Arr, MapV, Builder, Props, Coll, PairV, Opt, Strm,
                                                   ListV, IterV, RKey, MapView)):
                continue
            seen.add(id(v))
            if isinstance(v, Obj):
                v._defaults = False
                for key, val in list(v.fields.items()):
                    # ``__`` keys are what the machine keeps of an object's
                    # construction (the Properties a block took, which
                    # vanilla copies into each state when it is built; a
                    # vanilla constructor's arguments; a name), not fields.
                    if key.startswith("__"):
                        continue
                    todo.append(val)
                    if not self._final_field(v.cls, key, static=False):
                        v.fields[key] = UNKNOWN
            elif isinstance(v, Arr):
                todo.extend(v.items)
                v.items = [UNKNOWN] * len(v.items)
            elif isinstance(v, MapV):
                todo.extend(v.items.keys())
                todo.extend(v.items.values())
                v.items, v.havoc, v.exact = {}, True, False
            elif isinstance(v, MapView):
                todo.append(v.map)
            elif isinstance(v, Builder):
                v.parts = [UNKNOWN]
            elif isinstance(v, ListV):
                todo.extend(v.items)
                v.items, v.havoc = [], True
                v.mod += 1
            elif isinstance(v, IterV):
                todo.append(v.source)
            elif isinstance(v, RKey):
                todo.append(v.location)
            elif isinstance(v, Props):
                v.has_collision, v.light = UNKNOWN, UNKNOWN
            elif isinstance(v, (Coll, Strm)):
                todo.extend(v.items)
            elif isinstance(v, PairV):
                todo += [v.left, v.right]
            elif isinstance(v, Opt):
                todo.append(v.value)

    def _final_field(self, owner: str, name: str, static: bool = True) -> bool:
        """Whether ``owner`` (or the class in its chain declaring ``name``)
        declares field ``name`` final; False for a field no class of the
        mod or its libraries declares (a vanilla object's)."""
        for cname in self.chain(owner):
            cf = self.classes.get(cname)
            if cf is None:
                return False
            access = getattr(cf, "field_access", {}).get(name)
            if access is not None:
                return bool(access & 0x0010) and bool(access & 0x0008) == static
        return False

    def _record(self, args: list) -> None:
        if self.registrations is None:
            return
        if any(isinstance(a, RL) and a.lookup for a in args):
            return
        args = [a.location if isinstance(a, RKey) else a for a in args]
        names = [a.path if isinstance(a, RL) else a.fields["__rl"] if isinstance(a, Obj) and "__rl" in a.fields
                 else a for a in args
                 if isinstance(a, (str, RL, Tail)) or (isinstance(a, Obj) and "__rl" in a.fields)]
        names = [n.text if isinstance(n, Tail) else n for n in names]
        values = [a for a in args if isinstance(a, Lam) or (isinstance(a, Obj) and "__rl" not in a.fields)]
        if len(names) != 1 or not values:
            return
        name = names[0].rsplit(":", 1)[-1]
        if len(values) == 1:
            self.registrations.append(Registration(name, values[0]))
            if isinstance(values[0], Obj) and _RESOURCE_NAME.fullmatch(names[0]):
                # Only a valid resource location can be a registry key (a
                # format such as "%s_wall" handed with the block isn't one).
                self.names_of.setdefault(id(values[0]), (values[0], set()))[1].add(names[0])
            return
        # Several lambdas in one call: a block registration that also makes
        # the block's item, e.g. MrCrayfish Framework's
        # RegistryEntry.blockWithItem(id, Supplier<T> supplier, Function<T, E>
        # function) (T extends Block, E extends BlockItem). The block is the
        # lambda that takes nothing and returns a block class; the item
        # function takes the block. Only lambdas, and exactly one such
        # supplier, count; anything else is left unread with the reason.
        if not all(isinstance(v, Lam) for v in values):
            return
        suppliers = [v for v in values if self.supplies_block(v)]
        if len(suppliers) == 1:
            self.registrations.append(Registration(name, suppliers[0]))
        else:
            self.registrations.append(Registration(name, None, (
                f"its registration passes {len(values)} lambdas and {len(suppliers)} of them take no arguments "
                "and return a block class (by the lambda's dynamicMethodType; exactly one must), so which "
                "one builds the block can't be told")))

    def supplies_block(self, lam: Lam) -> bool:
        """Whether ``lam``, by its dynamicMethodType, takes no arguments
        and returns a class that reaches a vanilla block class."""
        if not lam.itype or not lam.itype.startswith("()L") or not lam.itype.endswith(";"):
            return False
        return self.is_block_class(lam.itype[3:-1])

    def run(self, cf: ClassFile, m: Method, args: list) -> list:
        """Every value ``m`` may return (None for void), over all paths."""
        if self.depth >= _MAX_DEPTH:
            raise Unreadable("calls nest too deeply")
        if self.depth == 0:
            self._top += 1
        self.depth += 1
        try:
            return self._run(cf, m, args)
        finally:
            self.depth -= 1

    def _run(self, cf: ClassFile, m: Method, args: list) -> list:
        code = instructions(cf, m.code)
        at = {insn.offset: k for k, insn in enumerate(code)}
        self._code.append((self.depth, code, at))
        self._running.append(cf.name)
        try:
            return self._run_code(cf, m, args, code, at)
        finally:
            self._code.pop()
            self._running.pop()

    def _run_code(self, cf: ClassFile, m: Method, args: list, code: list, at: dict) -> list:
        # Longs and doubles take two local slots (JVMS 2.6.1).
        local = self._wide_locals(m, args) + [UNKNOWN] * 256
        work = [Frame(0, local, [])]
        results: list = []
        paths = 1
        stopped: Unreadable | None = None
        # A constructor's receiver (#280): each path after an undecided branch
        # keeps its own copy of the receiver's fields (Frame.recv_fields), so
        # a write to the object under construction no longer stops the run;
        # the copies of the paths that return are joined below (_join_fields).
        recv = args[0] if m.name == "<init>" and args and isinstance(args[0], Obj) else None
        ends: list = []
        if recv is not None:
            work[0].recv_fields = recv.fields
            self._receivers.append((self.depth, recv))
        try:
            return self._run_paths(cf, m, code, at, work, results, paths, stopped, recv, ends)
        finally:
            if recv is not None:
                self._receivers.pop()
                if ends:
                    recv.fields = _join_fields(ends)

    def _run_paths(self, cf, m, code, at, work, results, paths, stopped, recv, ends) -> list:
        while work:
            frame = work.pop()
            if recv is not None:
                recv.fields = frame.recv_fields
            try:
                while True:
                    self.steps += 1
                    if self.steps > _MAX_STEPS:
                        raise Unreadable(_TOO_MUCH)
                    insn = code[at[frame.pc]] if frame.pc in at else None
                    if insn is None:
                        raise Unreadable(f"jump into the middle of an instruction in {cf.name}.{m.name}")
                    nxt = code[at[frame.pc] + 1].offset if at[frame.pc] + 1 < len(code) else None
                    outcome = self.step(cf, insn, frame, nxt)
                    if outcome is None:
                        continue
                    kind, payload = outcome
                    if kind == "return":
                        results.append(payload)
                        if recv is not None:
                            ends.append(recv.fields)
                        if self.effects is not None and self.depth == self.effects_depth:
                            self.effects.append((payload, frame.effects))
                        break
                    if kind == "throw":
                        break
                    if kind == "fork":
                        for g in payload:
                            g.fork_serial = _ALLOCATED[0]
                        for g in payload:
                            self._own_iterators(g, code)
                        paths += len(payload) - 1
                        if paths > (_MAX_LIBRARY_PATHS if self._weak_ok() else _MAX_PATHS):
                            raise Unreadable(f"too many paths through {cf.name}.{m.name}")
                        if recv is not None:
                            # Every way starts from the receiver as it is now.
                            snap = dict(recv.fields)
                            payload[0].recv_fields = recv.fields
                            for other in payload[1:]:
                                other.recv_fields = dict(snap)
                        for other in payload[1:]:
                            work.append(other)
                        frame = payload[0]
                        continue
            except Unreadable as exc:
                # While registrations are collected, a way of a fork that
                # stops at a write (see _write) doesn't keep its sibling ways
                # from running for the registrations they make (#280: the way
                # where a library's name lookup answered unknown stops at a
                # write, the way where it answered the vanilla key registers
                # its name first). The run still stops once they are done:
                # what it returns and writes isn't known.
                if self.registrations is None or not frame.forked or str(exc) != _FORKED_WRITE:
                    raise
                stopped = stopped or exc
        if stopped is not None:
            raise stopped
        return results

    def _own_iterators(self, g: Frame, code: list) -> None:
        """Each way of a branch the run can't decide gets its own copy of an
        iterator only this frame can reach (#280): one the frame's own
        ``iterator()`` call returned (IterV.home) and that hasn't escaped
        (IterV.escaped). In the game each way is a run of its own, so its
        iterator's position is its own; with no field, array, static, call
        or lambda holding it, nothing but this frame's locals and stack can
        see which object it is. A copy is allocated after the branch, so
        advancing it is a write this way alone makes (see _write)."""
        home = (self.depth, id(code))
        copies: dict = {}
        for slots in (g.locals, g.stack):
            for i, v in enumerate(slots):
                if isinstance(v, IterV) and not v.escaped and v.home == home:
                    if id(v) not in copies:
                        copies[id(v)] = IterV(v.source, v.pos, v.mod, home)
                    slots[i] = copies[id(v)]

    def _wide_locals(self, m: Method, args: list) -> list:
        out = []
        static = bool(m.access & 0x0008)
        k = 0
        if not static:
            out.append(args[0])
            k = 1
        desc = m.desc
        i = 1
        while desc[i] != ")":
            start = i
            while desc[i] == "[":
                i += 1
            if desc[i] == "L":
                i = desc.index(";", i)
            wide = desc[start] in "JD"
            i += 1
            out.append(args[k] if k < len(args) else UNKNOWN)
            if wide:
                out.append(UNKNOWN)
            k += 1
        return out

    def _write(self, frame: Frame, target=None) -> None:
        """A write by ``frame`` after a branch it can't decide may happen on
        one way and not the other, so it stops the run (Unreadable), unless
        it is to ``target``, an object or array this way allocated since
        (no other way sees it: its ``_serial`` is above the frame's
        ``fork_serial``; #280, an array built for String.format after Zeta's
        registry lookup forks)."""
        if not frame.forked:
            return
        if target is not None and self._receivers and self._receivers[-1][0] == self.depth \
                and target is self._receivers[-1][1]:
            return  # the object this constructor builds: each way has its own copy (_run_code)
        if target is None or getattr(target, "_serial", -1) <= frame.fork_serial:
            raise Unreadable(_FORKED_WRITE)

    def step(self, cf: ClassFile, insn: Insn, f: Frame, nxt: int | None):
        op = insn.op
        s = f.stack
        f.pc = nxt if nxt is not None else -1
        if op == 0x00:
            return None
        if op == 0x01:
            s.append(None)
        elif 0x02 <= op <= 0x08:
            s.append(op - 0x03)
        elif op in (0x09, 0x0A):
            s.append(op - 0x09)
        elif 0x0B <= op <= 0x0D:
            s.append(float(op - 0x0B))
        elif op in (0x0E, 0x0F):
            s.append(float(op - 0x0E))
        elif op in (0x10, 0x11):
            s.append(insn.arg)
        elif op in (0x12, 0x13, 0x14):
            v = insn.arg
            if isinstance(v, tuple) and v and v[0] == "class":
                v = ClassLit(v[1])
            elif isinstance(v, tuple):
                v = UNKNOWN
            s.append(v)
        elif 0x15 <= op <= 0x19:
            s.append(f.locals[insn.arg])
        elif 0x1A <= op <= 0x2D:
            s.append(f.locals[(op - 0x1A) % 4])
        elif 0x2E <= op <= 0x35:  # xaload
            idx, arr = s.pop(), s.pop()
            if isinstance(arr, Arr) and isinstance(idx, int) and 0 <= idx < len(arr.items):
                s.append(arr.items[idx])
            else:
                s.append(UNKNOWN)
        elif 0x36 <= op <= 0x3A:
            f.locals[insn.arg] = s.pop()
        elif 0x3B <= op <= 0x4E:
            f.locals[(op - 0x3B) % 4] = s.pop()
        elif 0x4F <= op <= 0x56:  # xastore
            val, idx, arr = s.pop(), s.pop(), s.pop()
            if isinstance(val, IterV):
                val.escaped = True
            if isinstance(arr, Arr):
                try:
                    self._write(f, arr)
                except Unreadable:
                    if not self._weak_ok():
                        raise
                    # A dependency jar's store into an array on one way of
                    # a branch the run can't decide (#280 pick 2): the
                    # array's elements are unknown from then on, on every way.
                    arr.items = [UNKNOWN] * len(arr.items)
                    return None
                if isinstance(idx, int) and 0 <= idx < len(arr.items):
                    arr.items[idx] = val
                else:
                    arr.items = [UNKNOWN] * len(arr.items)
        elif op == 0x57:
            s.pop()
        elif op == 0x58:  # pop2: one double (kept in one slot here) or two words
            if not isinstance(s.pop(), float) and s:
                s.pop()
        elif op == 0x59:
            s.append(s[-1])
        elif op == 0x5A:
            a, b = s.pop(), s.pop()
            s += [a, b, a]
        elif op == 0x5B:
            a, b, c = s.pop(), s.pop(), s.pop()
            s += [a, c, b, a]
        elif op == 0x5C:  # dup2 (category-1 pair only; we keep wide values in one slot)
            s += [s[-1]] if isinstance(s[-1], float) else [s[-2], s[-1]]
        elif op == 0x5F:
            s[-1], s[-2] = s[-2], s[-1]
        elif 0x60 <= op <= 0x83:
            self._arith(op, s)
        elif op == 0x84:  # iinc
            index, delta = insn.arg
            v = f.locals[index]
            f.locals[index] = v + delta if isinstance(v, int) and not isinstance(v, bool) else UNKNOWN
        elif 0x85 <= op <= 0x93:  # conversions
            v = s.pop()
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                v = float(v) if op in (0x86, 0x87, 0x89, 0x8A, 0x8D, 0x90) else int(v)
            s.append(v)
        elif 0x94 <= op <= 0x98:
            b, a = s.pop(), s.pop()
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                s.append((a > b) - (a < b))
            else:
                s.append(UNKNOWN)
        elif 0x99 <= op <= 0xA6 or op in (0xC6, 0xC7):
            return self._branch(op, insn.arg, f, nxt)
        elif op == 0xA7 or op == 0xC8:
            f.pc = insn.arg
        elif op in (0xAA, 0xAB):
            key = s.pop()
            default, table = insn.arg
            if isinstance(key, int) and not isinstance(key, bool):
                f.pc = table.get(key, default)
            else:
                targets = sorted({default, *table.values()})
                frames = []
                for t in targets:
                    g = f.copy()
                    g.pc = t
                    frames.append(g)
                return ("fork", frames)
        elif 0xAC <= op <= 0xB0:
            v = s.pop()
            if isinstance(v, IterV):
                v.escaped = True
            return ("return", v)
        elif op == 0xB1:
            return ("return", None)
        elif op == 0xB2:
            value = self.get_static(insn.arg)
            if (value is UNKNOWN or value is None) and self._lazy_guard(insn):
                value = None
            s.append(value)
        elif op == 0xB3:
            ref = insn.arg
            self._write(f)
            owner = self._field_owner(ref.owner, ref.name)
            v = s.pop()
            if isinstance(v, IterV):
                v.escaped = True
            self.statics[(owner, ref.name)] = v
        elif op == 0xB4:
            obj = s.pop()
            name = insn.arg.name
            if isinstance(obj, Obj):
                s.append(obj.fields[name] if name in obj.fields else self._field_default(obj, name))
            else:
                s.append(UNKNOWN)
        elif op == 0xB5:
            val, obj = s.pop(), s.pop()
            if isinstance(val, IterV):
                val.escaped = True
            if isinstance(obj, Obj):
                self._write(f, obj)
                obj.fields[insn.arg.name] = val
        elif op in (0xB6, 0xB7, 0xB8, 0xB9):
            return self._invoke(op, insn.arg, f)
        elif op == 0xBA:
            return self._indy(insn.arg, f)
        elif op == 0xBB:
            cls = insn.arg[1]
            s.append(self._new(cls))
        elif op == 0xBC or op == 0xBD:
            n = s.pop()
            fill = 0 if op == 0xBC else None
            s.append(Arr([fill] * n) if isinstance(n, int) and 0 <= n <= 4096 else UNKNOWN)
        elif op == 0xBE:
            a = s.pop()
            s.append(len(a.items) if isinstance(a, Arr) else UNKNOWN)
        elif op == 0xBF:
            return ("throw", None)
        elif op == 0xC0:
            pass
        elif op == 0xC1:
            v = s.pop()
            cls = insn.arg[1] if isinstance(insn.arg, tuple) else insn.arg
            s.append(self.instance_of(v, cls))
        elif op in (0xC2, 0xC3):
            s.pop()
        else:
            raise Unreadable(f"opcode {insn.name} is not followed")
        return None

    def _arith(self, op: int, s: list) -> None:
        if op in (0x74, 0x75, 0x76, 0x77):  # neg
            v = s.pop()
            s.append(-v if isinstance(v, (int, float)) and not isinstance(v, bool) else UNKNOWN)
            return
        b, a = s.pop(), s.pop()
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (a, b)):
            s.append(UNKNOWN)
            return
        kind = (op - 0x60) // 4
        try:
            if kind == 0:
                r = a + b
            elif kind == 1:
                r = a - b
            elif kind == 2:
                r = a * b
            elif kind == 3:
                r = a / b if isinstance(a, float) or isinstance(b, float) else int(a / b)
            elif kind == 4:
                r = a % b
            else:
                r = UNKNOWN
        except ZeroDivisionError:
            r = UNKNOWN
        s.append(r)

    def _throws_only(self, offset: int) -> bool:
        """Whether the code at ``offset`` (in the method being run) only
        builds and throws a ``java.lang`` exception: ``new``, ``dup``,
        constants and local loads, a string concatenation for its message,
        the exception's own constructor, then ``athrow``; nothing it does
        reaches memory or a call into other code."""
        if not self._code or self._code[-1][0] != self.depth:
            return False  # not run by _run (a subclass's own loop)
        _depth, code, at = self._code[-1]
        k = at.get(offset)
        if k is None:
            return False
        for insn in code[k:k + 12]:
            op = insn.op
            if op == 0xBF:  # athrow
                return True
            if op == 0xBB:  # new
                cls = insn.arg[1] if isinstance(insn.arg, tuple) else insn.arg
                if not (isinstance(cls, str) and cls.startswith("java/lang/")
                        and cls.endswith(("Exception", "Error"))):
                    return False
            elif op == 0xB7:  # invokespecial
                ref = insn.arg
                if not (isinstance(ref, Ref) and ref.name == "<init>" and ref.owner.startswith("java/lang/")
                        and ref.owner.endswith(("Exception", "Error"))):
                    return False
            elif op == 0xBA:  # invokedynamic: only a string concatenation
                indy = insn.arg
                if not (isinstance(indy, Indy) and indy.bootstrap
                        and indy.bootstrap.ref.owner == "java/lang/invoke/StringConcatFactory"):
                    return False
            elif not (op == 0x59 or 0x01 <= op <= 0x14 or 0x15 <= op <= 0x2D):
                # dup, constants (aconst_null..ldc2_w), loads (iload..aload_3)
                return False
        return False

    def _branch(self, op: int, target: int, f: Frame, nxt: int | None = None):
        s = f.stack
        if op <= 0x9E or op in (0xC6, 0xC7):
            v = s.pop()
            if op in (0xC6, 0xC7):
                decided = None if v is UNKNOWN else (v is None)
                taken = decided if op == 0xC6 else (None if decided is None else not decided)
            else:
                if isinstance(v, bool):
                    v = int(v)
                if not isinstance(v, (int, float)):
                    taken = None
                else:
                    taken = {0x99: v == 0, 0x9A: v != 0, 0x9B: v < 0, 0x9C: v >= 0,
                             0x9D: v > 0, 0x9E: v <= 0}[op]
        else:
            b, a = s.pop(), s.pop()
            if op <= 0xA4:
                if isinstance(a, bool):
                    a = int(a)
                if isinstance(b, bool):
                    b = int(b)
                if not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
                    taken = None
                else:
                    taken = {0x9F: a == b, 0xA0: a != b, 0xA1: a < b, 0xA2: a >= b,
                             0xA3: a > b, 0xA4: a <= b}[op]
            else:
                same = _same(a, b)
                taken = None if same is None else (same if op == 0xA5 else not same)
        if taken is None and nxt is not None:
            # A guard whose one way only throws (``if (x == null) throw new
            # IllegalArgumentException(..)``): that way registers and returns
            # nothing, so the other is the only way on, and not a fork (#280).
            if self._throws_only(nxt):
                taken = True
            elif self._throws_only(target):
                taken = False
        if taken is None:
            g = f.copy()
            g.pc = target
            h = f.copy()
            return ("fork", [g, h])
        if taken:
            f.pc = target
        return None

    def _holder_call(self, owner: str, name: str, desc: str, recv, rest: list, static: bool):
        """Registry plumbing a block entity is made through, followed while
        reading one (Machine.holders):

        * a ``register`` call naming one id and passing one supplier lambda
          (NeoForge/Forge ``DeferredRegister#register(String, Supplier)``)
          returns a holder of that supplier, and ``get``/``value`` on the
          holder runs it (what the registry does once, at registration);
        * ``BlockEntityType$Builder.of(factory, blocks...)`` and its
          ``build(type)`` keep the factory (BlockEntityType$Builder#of and
          #build, MC 1.21.1: the type stores the factory), and
          ``BlockEntityType#create(pos, state)`` calls it
          (``this.factory.create(pos, state)``, MC 1.21.1).

        Anything else is not handled here."""
        if name == "register" and not static and not desc.endswith(")V"):
            ids = [a for a in rest if isinstance(a, (str, RL))]
            lams = [a for a in rest if isinstance(a, Lam)]
            if len(ids) == 1 and len(lams) == 1 and len(rest) == 2:
                return [Obj("__holder", {"supplier": lams[0]})]
        if isinstance(recv, Obj) and recv.cls == "__holder" and name in ("get", "value") and not rest:
            return self.call_lambda(recv.fields["supplier"], [])
        if owner == _BE_BUILDER and static and name == "of" and rest and isinstance(rest[0], Lam):
            return [Obj("__betype_builder", {"factory": rest[0]})]
        if isinstance(recv, Obj) and recv.cls == "__betype_builder" and name == "build":
            return [Obj("__betype", {"factory": recv.fields["factory"]})]
        if isinstance(recv, Obj) and recv.cls == "__betype" and name == "create" and len(rest) == 2:
            return self.call_lambda(recv.fields["factory"], list(rest))
        return _NOT_HANDLED

    def _new(self, cls: str):
        if cls in ("java/util/EnumMap", "java/util/HashMap", "java/util/LinkedHashMap",
                   "java/util/TreeMap"):
            return MapV({}, kind="linked" if cls == "java/util/LinkedHashMap" else None, run=self._top)
        if cls == "java/lang/StringBuilder":
            return Builder([])
        if cls in _MUTABLE_LISTS:
            return ListV([])
        obj = Obj(cls)
        obj._uninit = True  # until its constructor is called (see _invoke)
        # A new object's fields hold their default values (null, 0, false)
        # until written (JVMS 2.3, 2.4, 6.5 new); the fields the mod's and
        # libraries' classes declare are read so (see _field_default).
        obj._defaults = self.is_mod(cls)
        return obj

    def _field_default(self, obj: "Obj", name: str):
        """The default value a field ``name`` of ``obj`` that nothing wrote
        holds (null, 0, 0.0), when a class of the mod or its libraries in
        ``obj``'s chain declares it, the object was made by ``new`` here,
        its constructor was followed to the end and nothing the machine
        couldn't follow has had it since; else UNKNOWN."""
        if not getattr(obj, "_defaults", False) or "__partial" in obj.fields:
            return UNKNOWN
        for cname in self.chain(obj.cls):
            cf = self.classes.get(cname)
            if cf is None:
                return UNKNOWN
            desc = cf.fields.get(name)
            if desc is not None:
                if getattr(cf, "field_access", {}).get(name, 0) & 0x0008:
                    return UNKNOWN  # a static, not this object's
                if desc[0] in "L[":
                    return None
                return 0.0 if desc[0] in "FD" else 0
        return UNKNOWN

    def _indy(self, indy: Indy, f: Frame):
        n, _ = _arg_count(indy.desc)
        args = [f.stack.pop() for _ in range(n)][::-1]
        for a in args:
            if isinstance(a, IterV):
                a.escaped = True
        bsm = indy.bootstrap.ref if indy.bootstrap else None
        if bsm and bsm.owner == "java/lang/invoke/LambdaMetafactory" and len(indy.args) >= 2 \
                and isinstance(indy.args[1], Handle):
            itype = indy.args[2] if len(indy.args) >= 3 else None
            itype = itype[1] if isinstance(itype, tuple) and itype[:1] == ("methodtype",) else None
            ret = indy.desc.rsplit(")", 1)[-1]
            iface = ret[1:-1] if bsm.name == "metafactory" and ret.startswith("L") else None
            f.stack.append(Lam(indy.args[1], tuple(args), itype, iface))
        elif bsm and bsm.owner == "java/lang/invoke/StringConcatFactory" and indy.args \
                and isinstance(indy.args[0], str):
            recipe, consts = indy.args[0], list(indy.args[1:])
            kinds = _arg_kinds(indy.desc)
            out, k = [], 0
            for ch in recipe:
                if ch == "\x01":
                    v = args[k] if isinstance(args[k], Tail) else \
                        self.stringify(args[k], kinds[k] if k < len(kinds) else "L")
                    k += 1
                    out.append(v if v is not None else UNKNOWN)
                elif ch == "\x02":
                    out.append(str(consts.pop(0)))
                else:
                    out.append(ch)
            f.stack.append(_join(out))
        else:
            f.stack.append(UNKNOWN)
        return None

    def _invoke(self, op: int, ref: Ref, f: Frame):
        # What the call does happens on this way only when ``f`` is past a
        # branch it can't decide (see _map_touch).
        saved = self._fork_floor
        if f.forked:
            self._fork_floor = max(saved, f.fork_serial)
        try:
            return self._invoke_on(op, ref, f)
        finally:
            self._fork_floor = saved

    def _invoke_on(self, op: int, ref: Ref, f: Frame):
        n, returns = _arg_count(ref.desc)
        static = op == 0xB8
        total = n + (0 if static else 1)
        args = [f.stack.pop() for _ in range(total)][::-1]
        for k, a in enumerate(args):
            # An iterator's own hasNext / next / remove (modelled in
            # _mutable) keep it this frame's; anything else it is handed to
            # may keep it (see _own_iterators).
            if isinstance(a, IterV) and not (k == 0 and not static and not n
                                             and ref.name in ("hasNext", "next", "remove")):
                a.escaped = True
        serial = _ALLOCATED[0]
        if ref.name == "<init>":
            obj = args[0]
            if isinstance(obj, ListV):
                # new ArrayList() / ArrayList(int capacity) / LinkedList()
                # start empty; ArrayList(Collection) / LinkedList(Collection)
                # start with the collection's elements in its iteration order.
                if ref.desc == "(Ljava/util/Collection;)V":
                    items = self._known_items(args[1])
                    if items is None:
                        obj.havoc = True
                    else:
                        obj.items = list(items)
                elif ref.desc not in ("()V", "(I)V"):
                    obj.havoc = True
                return None
            if isinstance(obj, MapV):
                # new HashMap() / (int) / (int, float) start empty, and a
                # LinkedHashMap so built keeps insertion order (Java SE 21);
                # any other constructor (a copy, a comparator, access order)
                # leaves what it holds, or its order, not modelled.
                if ref.desc not in ("()V", "(I)V", "(IF)V"):
                    obj.items, obj.havoc, obj.exact, obj.kind = {}, True, False, None
                return None
            if isinstance(obj, Builder):
                # new StringBuilder(String | CharSequence) starts with it.
                if ref.desc in ("(Ljava/lang/String;)V", "(Ljava/lang/CharSequence;)V"):
                    text = self.stringify(args[1])
                    obj.parts.append(text if text is not None else UNKNOWN)
                return None
            if isinstance(obj, Obj) and getattr(obj, "_uninit", False):
                if not (f.forked and obj._serial <= f.fork_serial):
                    obj._uninit = False
                else:
                    # ``new`` ran before a branch this path can't decide and
                    # the constructor after it: until its constructor is
                    # called the object can only sit on this frame's stack
                    # and locals (JVMS 4.10.1.9, uninitialized references:
                    # no field, array or call sees it), where every way of
                    # the branch holds the same reference. Each way builds
                    # its own copy (#280: a module's ``new LeafCarpetBlock(
                    # inherit(leaf, ..), ..)``, where the library's name
                    # lookup forks between ``new`` and the constructor).
                    copy = Obj(obj.cls, dict(obj.fields))
                    f.stack[:] = [copy if v is obj else v for v in f.stack]
                    f.locals[:] = [copy if v is obj else v for v in f.locals]
                    args[0] = obj = copy
            if isinstance(obj, Obj) and self.is_mod(ref.owner):
                found = self.find_method(ref.owner, "<init>", ref.desc)
                if found is not None:
                    # Constructing an object this way allocated since its
                    # last undecided branch writes to that object.
                    self._write(f, obj)
                    try:
                        self.run(*found, args)
                    except Unreadable as exc:
                        # The object exists, but what its constructor went on
                        # to store is not known.
                        obj.fields.setdefault("__partial", str(exc))
                    return None
            self._vanilla_init(ref, args, f)
            return None
        self._forked = f.forked
        self._frame = f
        if self.effects is not None and ref.name in _SET_BLOCK and not static and args \
                and isinstance(args[0], Obj) and args[0].cls == _LEVEL:
            if self.depth != self.effects_depth:
                self.deep_effect = True
            f.effects = f.effects + ((args[1], args[2]),)
            f.stack.append(1)
            return None
        results = self.call(ref.owner, ref.name, ref.desc, args, special=op == 0xB7, static=static)
        if not returns:
            return None
        if len(results) == 1 and isinstance(results[0], IterV) and results[0]._serial > serial \
                and ref.name in ("iterator", "listIterator") and n == 0 and not static:
            # A new iterator this frame's own call made (see _own_iterators).
            results[0].home = (self.depth, id(self._code[-1][1]))
        if not results:
            return ("throw", None)
        if len(results) > 1 and all(_value_equal(r, results[0]) for r in results[1:]):
            # Every way of the callee returned the same value (#280): a
            # string, number, constant or name (equal by value), or the same
            # object. What its ways wrote after the branch they split at is
            # only what they allocated since (see _write), which nothing but
            # an equal value can carry out, so the caller goes on as one way.
            results = results[:1]
        if len(results) == 1:
            f.stack.append(results[0])
            return None
        frames = []
        for r in results:
            g = f.copy()
            g.stack.append(r)
            frames.append(g)
        return ("fork", frames)

    def _vanilla_init(self, ref: Ref, args: list, f: Frame) -> None:
        obj = args[0]
        if not isinstance(obj, Obj):
            return
        # The vanilla Block constructor keeps the Properties it was given, and
        # vanilla block classes taking more (DoorBlock(BlockSetType,
        # Properties), ...) hand theirs on to it.
        props_at = [k for k, a in enumerate(ref.desc[1:ref.desc.index(")")].split(";")) if a.endswith(_PROPERTIES)]
        # The block takes the settings as they are now (BlockBehaviour copies
        # hasCollision, and each state its light, when it is built), so a
        # later change to a shared Properties doesn't reach it.
        if ref.owner.startswith(_VANILLA_BLOCK_PACKAGE):
            # The vanilla block constructor the block reached and what it was
            # given (a door's BlockSetType, #296): the first one called is
            # the most derived vanilla class's.
            obj.fields.setdefault("__vanilla_ctor", (ref.owner, ref.desc, tuple(args[1:])))
        if ref.desc.startswith(f"(L{_PROPERTIES};") and len(args) > 1:
            obj.fields.setdefault("__props", _snapshot(args[1]))
        elif ref.owner.startswith(_VANILLA_BLOCK_PACKAGE) and len(props_at) == 1 \
                and _only_objects(ref.desc) and props_at[0] + 1 < len(args):
            obj.fields.setdefault("__props", _snapshot(args[props_at[0] + 1]))
        elif ref.owner == "java/lang/Enum" and ref.desc == "(Ljava/lang/String;I)V" and len(args) == 3:
            # java.lang.Enum(String name, int ordinal): what name() and
            # ordinal() return.
            if isinstance(args[1], str):
                obj.fields["__enum_name"] = args[1]
            if isinstance(args[2], int) and not isinstance(args[2], bool):
                obj.fields["__ordinal"] = args[2]
        elif obj.cls == "net/minecraft/resources/ResourceLocation" and len(args) == 3 \
                and all(isinstance(a, str) for a in args[1:]):
            obj.fields["__rl"] = f"{args[1]}:{args[2]}"

    def call_lambda(self, lam: Lam, args: list) -> list:
        h = lam.handle
        full = list(lam.captured) + list(args)
        if h.kind == 8:  # constructor reference
            obj = self._new(h.ref.owner)
            found = self.find_method(h.ref.owner, "<init>", h.ref.desc) if self.is_mod(h.ref.owner) else None
            n, _ = _arg_count(h.ref.desc)
            ctor_args = [obj] + (full + [UNKNOWN] * n)[:n]
            if found is not None:
                try:
                    self.run(*found, ctor_args)
                except Unreadable as exc:
                    obj.fields.setdefault("__partial", str(exc))
            else:
                self._vanilla_init(h.ref, ctor_args, Frame(0, [], []))
            return [obj]
        static = h.kind == 6
        n, _ = _arg_count(h.ref.desc)
        need = n + (0 if static else 1)
        full = (full + [UNKNOWN] * need)[:need]
        return self.call(h.ref.owner, h.ref.name, h.ref.desc, full, special=h.kind == 7, static=static)

    # -- vanilla ------------------------------------------------------------

    def vanilla(self, owner: str, name: str, desc: str, args: list, static: bool):
        recv = None if static else (args[0] if args else None)
        rest = args if static else args[1:]
        if name == "getClass" and desc == "()Ljava/lang/Class;" and not static and not rest \
                and isinstance(recv, Obj) and self.is_mod(recv.cls) and not getattr(recv, "_uninit", False):
            # Object#getClass (final, Java SE 21) of an object the run built
            # with ``new`` of a class in the jar or its libraries: that
            # class (#280: a trait key's javac-style ``equals`` compares
            # ``getClass()`` of both sides).
            return [ClassLit(recv.cls)]
        if owner == "java/lang/System" and static and name == "getProperty" \
                and desc == "(Ljava/lang/String;)Ljava/lang/String;" and len(rest) == 1:
            return [self._system_property(rest[0])]
        if owner == "java/lang/Class" and name == "desiredAssertionStatus" and not static and not rest \
                and isinstance(recv, ClassLit):
            # javac's ``$assertionsDisabled`` test: assertions are off unless
            # the JVM is started with -ea (Class#desiredAssertionStatus,
            # Java SE 21), which a player's game isn't (#280 pick 1).
            return [0]
        if recv is UNKNOWN and name == "hasNext" and owner == "java/util/Iterator" and not static \
                and self.registrations is not None and self._running and self._library(self._running[-1]):
            # A dependency jar's loop over a collection whose contents aren't
            # known (#280 pick 2): it can't be followed, and each way would
            # only add another unknown turn.
            raise Unreadable("iterates a collection whose contents aren't known")
        try:
            handled = self._mutable(owner, name, desc, recv, rest, static)
        except _WeakWrite:
            target = recv.source if isinstance(recv, IterV) else recv
            if isinstance(target, ListV):
                target.items, target.havoc = [], True
                target.mod += 1
            return [UNKNOWN] if _arg_count(desc)[1] else [None]
        if handled is not _NOT_HANDLED:
            return handled
        if self.holders:
            held = self._holder_call(owner, name, desc, recv, rest, static)
            if held is not _NOT_HANDLED:
                return held
        if owner in ("net/minecraft/world/level/block/Block",) or (
                owner.startswith(_VANILLA_BLOCK_PACKAGE) and name == "box" and static):
            if name == "box" and static and len(rest) == 6:
                return [_box(rest, 1.0)]
        if owner == _SHAPES:
            if name == "box" and len(rest) == 6:
                return [_box(rest, 16.0)]
            if name == "block":
                return [Shape(((0.0, 0.0, 0.0, 16.0, 16.0, 16.0),))]
            if name == "empty":
                return [Shape(())]
            if name == "or":
                return [_union(rest)]
            if name == "join" and len(rest) == 3:
                op = rest[2]
                if isinstance(op, Const) and op.name == "OR":
                    return [_union(rest[:2])]
                return [UNKNOWN]
        if isinstance(recv, Shape) and name in ("optimize", "singleEncompassing"):
            if name == "singleEncompassing" and recv.boxes:
                return [Shape((_bbox(recv.boxes),))]
            return [recv]
        if isinstance(recv, Shape) and name == "isEmpty":
            return [int(not recv.boxes)]
        if static and name == "getConnectedDirection" and owner in _FACE_ATTACHED_KIN and len(rest) == 1 \
                and isinstance(rest[0], State):
            # FaceAttachedHorizontalDirectionalBlock#getConnectedDirection
            # L64-70: CEILING -> DOWN, FLOOR -> UP, otherwise facing.
            face = rest[0].get("face")
            if face == Const(_ATTACH_FACE, "CEILING"):
                return [Dir("down")]
            if face == Const(_ATTACH_FACE, "FLOOR"):
                return [Dir("up")]
            if face == Const(_ATTACH_FACE, "WALL"):
                return [rest[0].get("facing")]
            return [UNKNOWN]
        if owner == _ATTACH_FACE and static and name == "values":
            # AttachFace: FLOOR, WALL, CEILING in declaration order.
            return [Arr([Const(_ATTACH_FACE, n) for n in _ATTACH_ORDER])]
        if isinstance(recv, Const) and recv.owner == _ATTACH_FACE and name == "ordinal" \
                and recv.name in _ATTACH_ORDER:
            return [_ATTACH_ORDER.index(recv.name)]
        if owner == _DIRECTION or isinstance(recv, (Dir, PlayerDir, LookDir)):
            return self._direction(name, recv, rest, static)
        if isinstance(recv, _Ctx):
            if name == "getHorizontalDirection":
                return [PlayerDir(0)]
            if recv.clicked is not None:
                if name == "getClickedFace":
                    return [Dir(recv.clicked)]
                if name == "getNearestLookingDirection":
                    return [LookDir(False)]
                if name == "getNearestLookingDirections":
                    # BlockPlaceContext#getNearestLookingDirections L76-96:
                    # Direction.orderedByNearest(player), then (unless
                    # replaceClicked) the clicked face's opposite moved to
                    # the front. Only the front one is known here.
                    return [Arr([Dir(recv.clicked).opposite()] + [UNKNOWN] * 5)]
            return [UNKNOWN]
        if isinstance(recv, State) and name == "canSurvive" and self.assume_support:
            # Not emulated (no world): placement is read as if the clicked
            # face holds the block up (see read_directional).
            self.support_assumed = True
            return [1]
        if isinstance(recv, Obj) and recv.cls == _LEVEL and name == "isClientSide":
            return [0]
        if isinstance(recv, State):
            if name == "cycle" and len(rest) == 1 and isinstance(rest[0], Prop) and self.effects is not None:
                # StateHolder#cycle (L54) takes the next of the property's
                # values (findNextInCollection, L58-69); a boolean's are
                # (true, false) (BooleanProperty#<init>, L12-14), so it flips.
                # Only while a toggle is read, which keeps only flips of the
                # booleans the blockstate draws (an IntegerProperty at 0 or 1
                # would cycle otherwise).
                v = recv.get(rest[0].name)
                return [recv.set(rest[0].name, 1 - v) if v in (0, 1) and not isinstance(v, bool) else UNKNOWN]
            if name == "setValue" and len(rest) == 2:
                prop = rest[0]
                key = prop.name if isinstance(prop, Prop) else f"?{id(prop)}"
                return [recv.set(key, rest[1])]
            if name == "getValue" and len(rest) == 1:
                prop = rest[0]
                if self.state_reads is not None:
                    self.state_reads.add(prop.name if isinstance(prop, Prop) else "?")
                return [recv.get(prop.name) if isinstance(prop, Prop) else UNKNOWN]
            if name == "hasProperty" and len(rest) == 1 and isinstance(rest[0], Prop):
                return [int(rest[0].name in dict(recv.values))]
            if name == "getBlock" and "__block" in dict(recv.values):
                return [dict(recv.values)["__block"]]
        # Fluids (see read_water): Fluids.WATER.getSource(false) is a still
        # water source (FlowingFluid#getSource L251), Fluids.EMPTY's default
        # state no fluid, and so is vanilla BlockBehaviour#getFluidState
        # (L248) under a plain vanilla block class.
        if recv == Const(_FLUIDS, "WATER") and name == "getSource" and len(rest) == 1 and rest[0] in (0, False):
            return [WATER_SOURCE]
        if recv == Const(_FLUIDS, "EMPTY") and name == "defaultFluidState" and not rest:
            return [NO_FLUID]
        if isinstance(recv, Obj) and self.is_block_class(recv.cls):
            base = self.vanilla_base(recv.cls)
            if name == "getFluidState" and desc == _FLUID_STATE_DESC and base in _PLAIN_VANILLA:
                return [NO_FLUID]
            if name == "defaultBlockState":
                return [recv.fields.get("__default", State())]
            if name == "registerDefaultState" and rest:
                if isinstance(rest[0], State):
                    recv.fields["__default"] = rest[0]
                return [None]
            if name in ("getStateDefinition",):
                return [Obj("__statedef")]
            if base in _FACE_ATTACHED_KIN and name == "getStateForPlacement" and desc == _PLACEMENT_DESC \
                    and rest and isinstance(rest[0], _Ctx) and rest[0].clicked is not None:
                # FaceAttachedHorizontalDirectionalBlock#getStateForPlacement
                # L39-52 (MC 1.21.1 client jar, Mojang mappings): for each of
                # getNearestLookingDirections() (the clicked face's opposite
                # first), vertical -> face CEILING (UP) / FLOOR (DOWN) and
                # facing = getHorizontalDirection(); horizontal -> face WALL
                # and facing = its opposite; the first state that canSurvive
                # is placed. Support is not emulated: the first is taken.
                first = Dir(rest[0].clicked).opposite()
                state = recv.fields.get("__default", State())
                if first.name in ("up", "down"):
                    state = state.set("face", Const(_ATTACH_FACE, "CEILING" if first.name == "up" else "FLOOR"))
                    state = state.set("facing", PlayerDir(0))
                else:
                    state = state.set("face", Const(_ATTACH_FACE, "WALL")).set("facing", first.opposite())
                self.support_assumed = True
                return [state]
            if base == _FACE_ATTACHED and name == "getShape" and desc == _GET_SHAPE_DESC:
                # It declares no getShape (client.txt 1.21.1): BlockBehaviour's.
                return [Shape(((0.0, 0.0, 0.0, 16.0, 16.0, 16.0),))]
            if base in _PLAIN_VANILLA:
                if name == "getStateForPlacement" and desc == _PLACEMENT_DESC:
                    return [recv.fields.get("__default", State())]
                if name == "getShape" and desc == _GET_SHAPE_DESC:
                    return [Shape(((0.0, 0.0, 0.0, 16.0, 16.0, 16.0),))]
        if isinstance(recv, Obj) and recv.cls == "__statedef" and name == "any":
            # StateDefinition#any is the first possible state (L92), each
            # property at its first value; the marker lets a reader take a
            # boolean's (true, BooleanProperty#<init> L12-14) where the code
            # never sets it.
            return [State(((_ANY, 1),))]
        if isinstance(recv, Obj) and recv.cls == "__statebuilder" and name == "add":
            props = rest[0].items if rest and isinstance(rest[0], Arr) else rest
            for p in props:
                recv.fields.setdefault("names", []).append(p.name if isinstance(p, Prop) else "?")
            return [recv]
        if owner == _PROPERTIES or isinstance(recv, Props):
            return self._properties(name, recv, rest, static)
        if owner.endswith("/properties/DirectionProperty") or owner.endswith("/properties/EnumProperty") \
                or owner.endswith("/properties/BooleanProperty") or owner.endswith("/properties/IntegerProperty"):
            if static and name == "create" and rest and isinstance(rest[0], str):
                return [Prop(rest[0])]
        if owner in ("java/lang/Boolean", "java/lang/Integer", "java/lang/Double", "java/lang/Float") \
                and name == "valueOf" and len(rest) == 1:
            return [rest[0]]
        if name in ("booleanValue", "intValue", "doubleValue") and recv is not None and not static:
            return [recv]
        coll = self._collections(owner, name, desc, recv, rest, static)
        if coll is not _NOT_HANDLED:
            return coll
        if owner == "java/util/Map" and static and name == "entry" and len(rest) == 2:
            # Map.entry(k, v) (Java SE 21): an unmodifiable pair; a null key
            # or value throws NullPointerException.
            if rest[0] is None or rest[1] is None:
                return []
            return [PairV(rest[0], rest[1])]
        if owner in ("com/google/common/collect/ImmutableMap", "java/util/Map") and static \
                and name in ("of", "ofEntries"):
            if name == "of" and len(rest) % 2 == 0:
                return self._fixed_map([(rest[k], rest[k + 1]) for k in range(0, len(rest), 2)])
            if name == "ofEntries" and owner == "java/util/Map" and len(rest) == 1 \
                    and isinstance(rest[0], Arr) and all(isinstance(e, PairV) for e in rest[0].items):
                return self._fixed_map([(e.left, e.right) for e in rest[0].items])
            return [UNKNOWN]
        if owner == "com/google/common/collect/Maps" and static:
            if name == "newEnumMap" and rest and isinstance(rest[0], MapV):
                return [MapV(dict(rest[0].items))]
            if name in ("newEnumMap", "newHashMap"):
                return [MapV({})] if not rest or isinstance(rest[0], ClassLit) else [UNKNOWN]
        if isinstance(recv, MapV):
            return self._map_call(recv, name, desc, rest)
        if isinstance(recv, Builder):
            if name == "append" and rest:
                # StringBuilder#append(x) appends String.valueOf(x); the
                # descriptor says how a JVM int is printed (char, boolean).
                text = rest[0] if isinstance(rest[0], Tail) else \
                    self.stringify(rest[0], _arg_kinds(desc)[0] if _arg_kinds(desc) else "L")
                recv.parts.append(text if text is not None else UNKNOWN)
                return [recv]
            if name == "toString":
                return [_join(recv.parts)]
        strings = self._strings(owner, name, desc, recv, rest, static)
        if strings is not _NOT_HANDLED:
            return strings
        if owner == "java/util/stream/Stream" and static and name == "of":
            if len(rest) == 1 and isinstance(rest[0], Arr):
                return [Strm(tuple(rest[0].items))]
            return [Strm(tuple(rest))]
        if owner == "java/util/Arrays" and static and name == "stream" and rest and isinstance(rest[0], Arr):
            return [Strm(tuple(rest[0].items))]
        if isinstance(recv, Strm) and name == "reduce":
            return self._reduce(recv, rest)
        if isinstance(recv, Strm):
            return self._stream(recv, name, desc, rest)
        if owner == "java/util/stream/Collectors" and static:
            if name in ("toList", "toUnmodifiableList") and not rest:
                return [CollectorV(name)]
            if name == "toCollection" and len(rest) == 1:
                return [CollectorV(name, rest[0])]
            return [UNKNOWN]
        if owner == "net/minecraft/resources/ResourceKey" and static and name == "create" and len(rest) == 2 \
                and (isinstance(rest[1], RL) or (isinstance(rest[1], Obj) and "__rl" in rest[1].fields)):
            return [RKey(rest[1])]
        if isinstance(recv, RKey) and name == "location" and not rest:
            return [recv.location]
        if isinstance(recv, Opt):
            if name in ("isPresent", "isEmpty") and not rest:
                return [int((recv.value is not None) == (name == "isPresent"))]
            if name in ("get", "orElseThrow"):
                return [recv.value] if recv.value is not None else []
            if name == "orElse" and rest:
                return [recv.value if recv.value is not None else rest[0]]
        key = self._registry_key(owner, name, desc, recv, rest, static)
        if key is not _NOT_HANDLED:
            return key
        if owner == "net/minecraft/resources/ResourceLocation" and static and len(rest) == 2 \
                and name in ("fromNamespaceAndPath", "tryBuild") and isinstance(rest[1], str) \
                and not isinstance(rest[0], str) and ":" not in rest[1]:
            # The namespace isn't known, the path is.
            return [RL(Tail(rest[1]))]
        if owner == "net/minecraft/resources/ResourceLocation" and static and len(rest) == 1 \
                and name in ("parse", "tryParse") and isinstance(rest[0], Tail):
            return [RL(rest[0])]
        if owner == "net/minecraft/resources/ResourceLocation" and static:
            strs = [a for a in rest if isinstance(a, str)]
            if name in ("fromNamespaceAndPath", "tryBuild") and len(strs) == 2 and len(rest) == 2:
                return [RL(f"{strs[0]}:{strs[1]}")]
            if name in ("parse", "tryParse", "withDefaultNamespace") and len(strs) == 1 and len(rest) == 1:
                return [RL(strs[0])]
        if name == "hashCode" or name == "equals":
            return [UNKNOWN]
        return _NOT_HANDLED

    def _registry_key(self, owner: str, name: str, desc: str, recv, rest: list, static: bool):
        """The block registry's ``getKey(block)`` (``BuiltInRegistries.BLOCK``,
        vanilla ``Registry#getKey(Object)``: "the key of the value", MC 1.21.1)
        for a block object this run recorded as registered under exactly one
        name: that name (#280, a name derived from another block's registered
        name). A name recorded without a namespace keeps it unknown
        (:class:`Tail`). And ``ResourceLocation#getPath`` /
        ``getNamespace`` / ``toString`` of a location known here. Anything else
        is not handled here."""
        if not static and name == "getKey" and desc == "(Ljava/lang/Object;)Lnet/minecraft/resources/ResourceLocation;" \
                and recv == Const(_BUILTIN_REGISTRIES, "BLOCK") and len(rest) == 1:
            vanilla = self._vanilla_block_id(rest[0])
            if vanilla is not None:
                return [RL(f"minecraft:{vanilla}", True)]
            entry = self.names_of.get(id(rest[0])) if isinstance(rest[0], Obj) else None
            if entry is None or entry[0] is not rest[0] or len(entry[1]) != 1:
                return [UNKNOWN]
            (raw,) = entry[1]
            return [RL(raw, True) if ":" in raw else RL(Tail(raw), True)]
        if isinstance(recv, RL) and not rest and not static:
            loc = recv.path
            if name == "getPath" and desc == "()Ljava/lang/String;":
                if isinstance(loc, Tail):
                    return [loc.text]
                return [loc.split(":", 1)[1] if ":" in loc else loc]
            if name == "getNamespace" and desc == "()Ljava/lang/String;":
                if isinstance(loc, Tail):
                    return [UNKNOWN]
                return [loc.split(":", 1)[0] if ":" in loc else "minecraft"]
            if name == "toString" and desc == "()Ljava/lang/String;":
                return [loc if isinstance(loc, Tail) or ":" in loc else f"minecraft:{loc}"]
        return _NOT_HANDLED

    def _vanilla_block_id(self, v) -> str | None:
        """The registry id of a vanilla block constant (``Blocks.OAK_SLAB``, a
        ``getstatic`` the machine keeps as a :class:`Const`) from the table read
        out of the declared game version's client jar
        (:mod:`portkit.data.vanilla_blocks`, #280), or None when it isn't a
        ``Blocks`` field, the table isn't cached or doesn't list it."""
        if not isinstance(v, Const) or v.owner != _VANILLA_BLOCKS:
            return None
        table = getattr(self.classes, "vanilla_blocks", None)
        return table.get(v.name) if table else None

    def stringify(self, v, kind: str = "L") -> str | None:
        """``String.valueOf(v)`` for a value of JVM type ``kind`` (a
        descriptor letter), or None when it isn't known. A mod enum
        constant prints its name unless its class overrides toString
        (java.lang.Enum#toString returns name())."""
        if isinstance(v, bool):
            v = int(v)
        if kind == "Z":
            return {0: "false", 1: "true"}.get(v) if isinstance(v, int) else None
        if kind == "C":
            return chr(v) if isinstance(v, int) and 0 <= v <= 0xFFFF else None
        if kind in "BSIJ":
            return str(v) if isinstance(v, int) else None
        if kind in "FD":
            return None  # Java's float printing isn't Python's
        if isinstance(v, str):
            return v
        if isinstance(v, Obj) and "__enum_name" in v.fields and self.is_mod(v.cls) \
                and self.find_method(v.cls, "toString", "()Ljava/lang/String;") is None:
            return v.fields["__enum_name"]
        return None

    def _strings(self, owner: str, name: str, desc: str, recv, rest: list, static: bool):
        """java.lang.String, java.lang.Enum and the vanilla enums whose
        constants' names are known (DyeColor), evaluated exactly; anything
        else is not handled here (#280: names built by concatenation)."""
        if isinstance(recv, Arr) and name == "clone" and not rest:
            return [Arr(list(recv.items))]
        if isinstance(recv, Obj) and "__enum_name" in recv.fields and not rest:
            if name == "name" and desc == "()Ljava/lang/String;":
                return [recv.fields["__enum_name"]]
            if name == "ordinal" and desc == "()I":
                return [recv.fields.get("__ordinal", UNKNOWN)]
            if name == "toString" and desc == "()Ljava/lang/String;":
                return [recv.fields["__enum_name"]]  # not overridden (see call)
        if owner == _DYE_COLOR and static and name == "values" and not rest:
            return [Arr([Const(_DYE_COLOR, n) for n in _DYE_ORDER])]
        if isinstance(recv, Const) and recv.owner == _DYE_COLOR and recv.name in _DYE_ORDER and not rest:
            if name in ("getName", "getSerializedName", "name") and desc == "()Ljava/lang/String;":
                return [recv.name.lower() if name != "name" else recv.name]
            if name in ("ordinal", "getId") and desc == "()I":
                return [_DYE_ORDER.index(recv.name)]
        if owner == "java/lang/String" and static and name == "valueOf" and len(rest) == 1:
            text = self.stringify(rest[0], _arg_kinds(desc)[0])
            return [text if text is not None else UNKNOWN]
        if owner == "java/lang/String" and static and name == "format" and desc.startswith("(Ljava/lang/String;"):
            return [_format(rest) if len(rest) == 2 else UNKNOWN]
        if isinstance(recv, str) and owner == "java/lang/String" and not static:
            if name in ("toLowerCase", "toUpperCase") and (
                    not rest or (isinstance(rest[0], Const) and rest[0].owner == "java/util/Locale")):
                # No Locale, or one of java.util.Locale's constants (ROOT,
                # ENGLISH, US, ...; none is Turkish or Azeri, the only ones
                # that case ASCII letters differently): on ASCII text the
                # result is the plain ASCII case change.
                if not recv.isascii():
                    return [UNKNOWN]
                return [recv.lower() if name == "toLowerCase" else recv.upper()]
            if name == "concat" and len(rest) == 1:
                return [recv + rest[0] if isinstance(rest[0], str) else UNKNOWN]
            if name == "toString" and not rest:
                return [recv]
            if name == "replace" and len(rest) == 2:
                if desc == "(CC)Ljava/lang/String;" and all(isinstance(a, int) for a in rest):
                    return [recv.replace(chr(rest[0]), chr(rest[1]))]
                if desc.startswith("(Ljava/lang/CharSequence;") and all(isinstance(a, str) for a in rest):
                    return [recv.replace(rest[0], rest[1])]
                return [UNKNOWN]
            if name in ("replaceAll", "replaceFirst") and len(rest) == 2:
                # A regex with no metacharacter matches itself literally, and
                # a replacement with no '\\' or '$' is inserted as it is
                # (java.util.regex.Pattern, Matcher#appendReplacement, Java
                # SE 21): then it is a plain left-to-right replacement (#280:
                # Quark's ``path.replaceAll("_leaves", "_leaf_carpet")``).
                regex, repl = rest
                if isinstance(regex, str) and isinstance(repl, str) and regex \
                        and not any(c in _REGEX_META for c in regex) and not any(c in "\\$" for c in repl):
                    return [recv.replace(regex, repl, -1 if name == "replaceAll" else 1)]
                return [UNKNOWN]
            if name in ("isEmpty", "length") and not rest:
                return [int(not recv) if name == "isEmpty" else len(recv)]
            if name in ("startsWith", "endsWith", "contains", "equals") and len(rest) == 1:
                if not isinstance(rest[0], str):
                    return [UNKNOWN]
                return [int({"startsWith": recv.startswith, "endsWith": recv.endswith,
                             "contains": recv.__contains__, "equals": recv.__eq__}[name](rest[0]))]
            return [UNKNOWN]
        return _NOT_HANDLED

    def _properties(self, name: str, recv, rest: list, static: bool) -> list:
        """BlockBehaviour.Properties. Java's builder changes itself and returns
        itself, and so does this one (a dropped return value still counts),
        unless the call sits after a branch that wasn't decided: then the
        change is a copy only that path sees."""
        if static:
            if name == "of":
                return [Props(True, DARK, self.epoch)]
            # ``copy`` is ofFullCopy's name up to 1.20.4: in 1.20.1 it copies
            # lightEmission too (BlockBehaviour$Properties#copy L508-535,
            # client jar dca$d.a(dca) bytecode 57-60 + client.txt), so it reads
            # the same once an SRG / intermediary jar is remapped (#235).
            if name in ("ofFullCopy", "ofLegacyCopy", "copy") and rest:
                src = rest[0]
                if isinstance(src, Obj) and isinstance(src.fields.get("__props"), Props):
                    light = src.fields["__props"].light  # a mod block's own Properties
                elif isinstance(src, Const):
                    light = CopiedLight(f"{src.owner.rsplit('/', 1)[-1]}.{src.name}")
                else:
                    light = CopiedLight("a block it can't read")
                # Whether it collides is the copied block's (not read here).
                return [Props(UNKNOWN, light, self.epoch)]
            return [Props(UNKNOWN, UNKNOWN, self.epoch)]
        if not isinstance(recv, Props):
            return [UNKNOWN]
        if name == "noCollission":
            collision, light = False, recv.light
        elif name == "lightLevel" and len(rest) == 1:
            fn = rest[0]
            ok = isinstance(fn, Lam) or (isinstance(fn, Obj) and self.is_mod(fn.cls))
            collision, light = recv.has_collision, fn if ok else UNKNOWN
        elif _OBFUSCATED.match(name):
            # A Forge SRG / Fabric intermediary name: which setting it is
            # can't be told, so neither collision nor light is known.
            collision, light = UNKNOWN, UNKNOWN
        else:
            return [recv]
        if self._forked:
            return [Props(collision, light, self.epoch)]
        if recv.epoch != self.epoch:
            recv.shared_changed = True
        recv.has_collision, recv.light = collision, light
        return [recv]

    def _direction(self, name: str, recv, rest: list, static: bool):
        if static and name == "values":
            return [Arr([Dir(d) for d in DIRECTIONS])]
        if isinstance(recv, Dir):
            if name == "ordinal":
                return [DIRECTIONS.index(recv.name)]
            if name == "getOpposite":
                return [recv.opposite()]
            if name == "getClockWise":
                return [recv.turned(1)]
            if name == "getCounterClockWise":
                return [recv.turned(3)]
            if name == "get2DDataValue":
                return [{"south": 0, "west": 1, "north": 2, "east": 3}.get(recv.name, -1)]
            if name == "equals" and len(rest) == 1:
                # Direction is an enum: equals is identity.
                other = rest[0]
                return [int(other == recv)] if isinstance(other, Dir) else [UNKNOWN]
            if name == "getAxis":
                axis = "Y" if recv.name in ("up", "down") else "Z" if recv.name in ("north", "south") else "X"
                return [Const(_DIRECTION + "$Axis", axis)]
        if isinstance(recv, LookDir):
            if name == "getOpposite":
                return [LookDir(not recv.opposite)]
            return [UNKNOWN]
        if isinstance(recv, PlayerDir):
            if name == "getOpposite":
                return [PlayerDir((recv.quarters + 2) % 4)]
            if name == "getClockWise":
                return [PlayerDir((recv.quarters + 1) % 4)]
            if name == "getCounterClockWise":
                return [PlayerDir((recv.quarters + 3) % 4)]
            return [UNKNOWN]
        return [UNKNOWN]

    def _collections(self, owner: str, name: str, desc: str, recv, rest: list, static: bool):
        """Immutable lists and sets of known elements and ``forEach`` over
        them (#280: ``ImmutableSet.of(Blocks.OAK_SLAB, ..).forEach(slab ->
        new VerticalSlabBlock(slab, ..))``). ``Iterable#forEach(Consumer)``
        runs the consumer on each element in iteration order (Java SE 21);
        anything else is not handled here."""
        if static and name == "of" and owner in _IMMUTABLE_OF:
            items = list(rest)
            if items and desc.split(")", 1)[0].endswith("[Ljava/lang/Object;"):
                if not isinstance(items[-1], Arr):
                    return [UNKNOWN]
                items = items[:-1] + list(items[-1].items)
            if owner in _SET_OF:
                if any(i is UNKNOWN or not _hashable(i) for i in items):
                    return [UNKNOWN]
                kept = []
                for i in items:
                    same = [_same(i, k) for k in kept]
                    if None in same:
                        return [UNKNOWN]
                    if not any(same):
                        kept.append(i)
                if owner == "java/util/Set" and (len(kept) != len(items) or len(kept) > 1):
                    return [UNKNOWN]
                items = kept
            return [Coll(tuple(items))]
        if static and name == "of" and owner in _PAIR_OF and desc == _PAIR_OF_DESC.get(owner) and len(rest) == 2:
            return [PairV(rest[0], rest[1])]
        if isinstance(recv, PairV) and not static and not rest:
            if name in ("getLeft", "getKey"):
                return [recv.left]
            if name in ("getRight", "getValue"):
                return [recv.right]
            return [UNKNOWN] if _arg_count(desc)[1] else [None]
        if isinstance(recv, Coll) and not static:
            if name == "forEach" and len(rest) == 1 and desc == "(Ljava/util/function/Consumer;)V":
                if not isinstance(rest[0], Lam):
                    return [None]
                for item in recv.items:
                    self.call_lambda(rest[0], [item])
                return [None]
            if name == "size" and not rest:
                return [len(recv.items)]
            if name == "stream" and not rest:
                return [Strm(recv.items)]
            return [UNKNOWN] if _arg_count(desc)[1] else [None]
        return _NOT_HANDLED

    # -- mutable java.util collections (#280 pick 2) ------------------------

    def _known_items(self, v):
        """The elements of a collection known in full, in iteration order,
        or None."""
        if isinstance(v, ListV):
            return None if v.havoc else list(v.items)
        if isinstance(v, (Coll, Strm)):
            return list(v.items)
        if isinstance(v, MapView):
            if self._map_view(v.map, v.kind) is None:
                return None
            return list(v.map.items.values() if v.kind == "values" else v.map.items.keys())
        return None

    def _weak_ok(self) -> bool:
        """Whether a write after an undecided branch may make what it writes
        unknown on every way instead of stopping the run: while
        registrations are collected, in a dependency jar's code."""
        return self.registrations is not None and bool(self._running) and self._library(self._running[-1])

    def _write_by_call(self, target) -> None:
        """A modelled change to ``target`` made by the call being run is a
        write by that call's frame (see _write). A list changed on one way
        of a branch the run can't decide (not one that way allocated) is
        unknown from then on, on every way (whichever way the game takes,
        nothing about it is claimed), instead of stopping the run."""
        if self._frame is None:
            return
        try:
            self._write(self._frame, target)
        except Unreadable:
            if not isinstance(target, (ListV, IterV)):
                raise
            raise _WeakWrite()

    def _map_call(self, recv: "MapV", name: str, desc: str, rest: list) -> list:
        """A call on a map built here (java.util HashMap / LinkedHashMap /
        TreeMap / EnumMap, Java SE 21). A lookup that misses answers the
        default only when the map's keys are known exactly (MapV.exact) and
        the key compares as it does here (_map_key); a change the model
        doesn't cover leaves the map unknown."""
        returns = _arg_count(desc)[1]
        if recv.havoc:
            return [UNKNOWN] if returns else [None]
        if recv.kind == "fixed" and name in _MAP_CHANGES:
            return []  # UnsupportedOperationException (ImmutableCollections)
        if name in ("get", "getOrDefault", "containsKey") and rest:
            key = rest[0]
            if key is UNKNOWN or not _hashable(key):
                return [UNKNOWN]
            found, value = self._map_find(recv, key)
            if name == "containsKey":
                if found:
                    return [1]
                return [0] if recv.exact and self._map_key(key) is not _NOKEY else [UNKNOWN]
            if found:
                return [value]
            if not recv.exact or self._map_key(key) is _NOKEY:
                return [UNKNOWN]
            return [rest[1] if name == "getOrDefault" and len(rest) > 1 else None]
        if name == "put" and len(rest) == 2:
            key = rest[0]
            if key is UNKNOWN or not _hashable(key):
                recv.items, recv.havoc, recv.exact = {}, True, False
                return [UNKNOWN]
            self._map_touch(recv)
            found, old = self._map_find(recv, key)
            if found:
                stored = key if key in recv.items else recv.canon[self._map_key(key)]
                recv.items[stored] = rest[1]
                return [old]
            canon = self._map_key(key)
            if canon is _NOKEY:
                recv.exact = False
            else:
                recv.canon[canon] = key
            recv.items[key] = rest[1]
            recv.mod += 1
            return [None if recv.exact else UNKNOWN]
        if name == "remove" and desc == "(Ljava/lang/Object;)Ljava/lang/Object;" and len(rest) == 1:
            key = rest[0]
            found, old = self._map_find(recv, key) if key is not UNKNOWN and _hashable(key) else (False, None)
            if not found and (not recv.exact or key is UNKNOWN or not _hashable(key)
                              or self._map_key(key) is _NOKEY):
                recv.items, recv.havoc, recv.exact = {}, True, False
                return [UNKNOWN]
            self._map_touch(recv)
            if found:
                stored = key if key in recv.items else recv.canon[self._map_key(key)]
                del recv.items[stored]
                recv.canon = {c: k for c, k in recv.canon.items() if k is not stored}
                recv.mod += 1
            return [old]
        if name == "clear" and not rest:
            self._map_touch(recv)
            if recv.items:
                recv.mod += 1
            recv.items, recv.canon, recv.exact = {}, {}, True
            return [None]
        if name in ("isEmpty", "size") and not rest:
            return [int(not recv.items)] if name == "isEmpty" else [len(recv.items)]
        if name in ("values", "keySet") and not rest:
            view = self._map_view(recv, name)
            if view is None:
                # A view the machine doesn't model may change the map
                # (``values().removeIf``), so nothing about it is known.
                recv.items, recv.havoc, recv.exact = {}, True, False
                return [UNKNOWN]
            return [view]
        if name == "computeIfAbsent" and len(rest) == 2 and self._key_ok(rest[0]):
            # Map#computeIfAbsent (Java SE 21, HashMap): the value held
            # for the key, else the function's value for it, kept unless
            # null.
            if rest[0] in recv.items and recv.items[rest[0]] is not None:
                return [recv.items[rest[0]]]
            out = self._apply(rest[1], "apply", "(Ljava/lang/Object;)Ljava/lang/Object;", [rest[0]])
            if out is UNKNOWN or isinstance(out, _Many):
                self._write_by_call(recv)
                recv.items, recv.havoc, recv.exact = {}, True, False
                return [UNKNOWN]
            if out is not None:
                self._write_by_call(recv)
                self._map_touch(recv)
                if rest[0] not in recv.items:
                    recv.mod += 1
                    recv.canon[self._map_key(rest[0])] = rest[0]
                recv.items[rest[0]] = out
            return [out]
        if name in _MAP_READS:
            return [UNKNOWN] if returns else [None]
        # Any other call (putAll, merge, compute, replace, entrySet, ...) may
        # change the map in a way not modelled here.
        recv.items, recv.havoc, recv.exact = {}, True, False
        return [UNKNOWN] if returns else [None]

    def _fixed_map(self, pairs: list) -> list:
        """``Map.of(k1, v1, ..)`` / ``Map.ofEntries(Map.entry(k, v), ..)`` /
        Guava ``ImmutableMap.of`` (Java SE 21, Guava 33): an unmodifiable map
        of the pairs. A null key or value throws NullPointerException and a
        key equal to an earlier one throws IllegalArgumentException; its
        keys are looked up as a map compares them (_map_key, a record by its
        components), and when one doesn't compare exactly here a lookup that
        misses is unknown (MapV.exact). Its iteration order isn't modelled
        (``Map.of``'s is unspecified), so it is never iterated; a change to
        it throws UnsupportedOperationException."""
        m = MapV({}, kind="fixed")
        for key, value in pairs:
            if key is None or value is None:
                return []
            if key is UNKNOWN or not _hashable(key):
                return [UNKNOWN]
            found, _old = self._map_find(m, key)
            if found:
                return []
            canon = self._map_key(key)
            if canon is _NOKEY:
                m.exact = False
            else:
                m.canon[canon] = key
            m.items[key] = value
        return [m]

    def _map_find(self, m: "MapV", key) -> tuple:
        """(found, value) for ``key`` in ``m``: the same key object, or a key
        the map holds that Java's ``equals`` finds equal (_map_key)."""
        if key in m.items:
            return True, m.items[key]
        canon = self._map_key(key)
        if canon is not _NOKEY and canon in m.canon:
            return True, m.items[m.canon[canon]]
        return False, None

    def _map_touch(self, m: "MapV") -> None:
        """A modelled change to ``m``: made on a way past a branch the run
        can't decide (any frame on the call stack, see _invoke) to a map
        allocated before that branch, it may not happen in the game, so the
        map is no longer iterated (MapV.clean)."""
        if m._serial <= self._fork_floor or (self._frame is not None and self._frame.forked
                                             and m._serial <= self._frame.fork_serial):
            m.clean = False

    def _map_view(self, m: "MapV", kind: str):
        """``values()`` / ``keySet()`` of ``m`` when its iteration is known
        exactly (#280): a LinkedHashMap built here in insertion order
        (LinkedHashMap: "the order in which keys were inserted into the map
        ... not affected if a key is re-inserted", Java SE 21) whose every
        change was modelled exactly, on keys that compare as they do here,
        in this top-level run and on no way of an undecided branch; else
        None."""
        if m.kind != "linked" or m.havoc or not m.exact or not m.clean or m.run != self._top:
            return None
        return MapView(m, kind)

    def _map_key(self, key):
        """``key`` as a map compares it (Object#equals / hashCode, Java SE
        21), or _NOKEY when that isn't known here: a known string, number or
        constant, or an object whose class declares no ``equals`` (identity,
        see _key_ok) is itself; a record whose ``equals`` is the one javac
        generates (``ObjectMethods.bootstrap``: equal when of the same class
        and each component is equal, java.lang.Record) is its class and its
        components' keys, when each is known.

        A record's key holds after the record was handed to code the machine
        couldn't follow (which clears ``_defaults``, see _havoc): a record's
        only instance fields are its components, each ``private final``
        (JLS 8.10.3), and no code can write them afterwards, reflection
        included (``Field#set`` refuses a final field of a record class,
        Java SE 21), so the components its constructor stored are the ones
        it compares by (#280: WorldWeaver's shared ``SlotType`` keys, handed
        to a library call by one material set, key the next set's map).
        Its constructor must still have been followed to the end and have
        stored every component."""
        if key is UNKNOWN or not _hashable(key):
            return _NOKEY
        if isinstance(key, Obj) and not self._key_ok(key):
            comps = self._record_components(key.cls)
            if comps is None or "__partial" in key.fields or getattr(key, "_uninit", False):
                return _NOKEY
            parts = []
            for c in comps:
                if c not in key.fields:
                    return _NOKEY
                v = key.fields[c]
                if isinstance(v, float):
                    return _NOKEY  # Float/Double#equals isn't Python's ==
                k = self._map_key(v) if v is not None else None
                if k is _NOKEY:
                    return _NOKEY
                parts.append(k)
            return ("__record", key.cls, tuple(parts))
        if not self._key_ok(key):
            return _NOKEY
        return key

    def _record_components(self, cls: str):
        """The component names of ``cls`` when it is a record (a direct
        subclass of java.lang.Record) whose ``equals`` is javac's generated
        one (``aload_0; aload_1; invokedynamic equals ObjectMethods.bootstrap;
        ireturn``), else None."""
        cf = self.classes.get(cls)
        if cf is None or cf.super_name != "java/lang/Record":
            return None
        m = cf.method("equals", "(Ljava/lang/Object;)Z")
        if m is None or m.code is None:
            return None
        code = instructions(cf, m.code)
        if [i.op for i in code] != [0x2A, 0x2B, 0xBA, 0xAC]:
            return None
        indy = code[2].arg
        bsm = indy.bootstrap.ref if isinstance(indy, Indy) and indy.bootstrap else None
        if bsm is None or bsm.owner != "java/lang/runtime/ObjectMethods" or bsm.name != "bootstrap" \
                or indy.name != "equals" or len(indy.args) < 2 or not isinstance(indy.args[1], str):
            return None
        names = [n for n in indy.args[1].split(";") if n]
        if len(names) != len(indy.args) - 2:
            return None
        return names

    def _key_ok(self, key) -> bool:
        """Whether ``key`` compares in a Java map as it does here: a known
        string, number or constant, or an object whose class (the mod's or a
        library's, up to java.lang.Object or Enum) declares no ``equals``,
        so Object#equals (identity) decides."""
        if key is UNKNOWN or not _hashable(key):
            return False
        if isinstance(key, (ListV, IterV, MapV, Arr, Builder, Props)):
            return False
        if isinstance(key, Obj):
            chain = self.chain(key.cls)
            if chain[-1] not in ("java/lang/Object", "java/lang/Enum"):
                return False
            return not any(self.classes.get(c) is not None
                           and self.classes.get(c).method("equals", "(Ljava/lang/Object;)Z") is not None
                           for c in chain)
        return True

    def _apply(self, fn, method: str, desc: str, args: list):
        """The one value ``fn`` (a lambda, or an object of the mod's or a
        library's class implementing a functional interface's ``method``)
        returns for ``args``; UNKNOWN when it can't be called or returns
        unknown, a :class:`_Many` when its ways return different values."""
        frame = self._frame
        try:
            if isinstance(fn, Lam):
                out = self.call_lambda(fn, args)
            elif isinstance(fn, Obj) and self.is_mod(fn.cls):
                found = self.find_method(fn.cls, method, desc)
                if found is None:
                    return UNKNOWN
                out = self.run(*found, [fn, *args])
            else:
                return UNKNOWN
        finally:
            self._frame = frame
        if not out:
            raise Unreadable("a function handed to a collection throws")
        first = out[0]
        if all(o is first or _equal(o, first) for o in out[1:]):
            return first
        return _Many(tuple(out))

    def _test(self, fn, item):
        """``fn.test(item)`` as 1 or 0, or None when not known."""
        out = self._apply(fn, "test", "(Ljava/lang/Object;)Z", [item])
        if isinstance(out, bool):
            out = int(out)
        return out if out in (0, 1) and not isinstance(out, _Many) else None

    def _havoc_list(self, lst: "ListV", returns: bool) -> list:
        self._write_by_call(lst)
        lst.items, lst.havoc = [], True
        lst.mod += 1
        return [UNKNOWN] if returns else [None]

    def _mutable(self, owner: str, name: str, desc: str, recv, rest: list, static: bool):
        """Calls on a mutable list (:class:`ListV`), an iterator
        (:class:`IterV`), and ``iterator`` / ``isEmpty`` / ``get`` /
        ``contains`` on an immutable collection (:class:`Coll`), as
        java.util's ArrayList, LinkedList and their iterators do them
        (Java SE 21). A change is a write by the calling frame (see _write);
        a call on a list not modelled here may change it, so it leaves the
        list unknown."""
        returns = _arg_count(desc)[1]
        if isinstance(recv, IterV) and isinstance(recv.source, MapView):
            # An iterator over a map's values() / keySet() (#280): the map's
            # order; a change to the map since the iterator was made fails
            # fast (HashMap$HashIterator, ConcurrentModificationException).
            view = recv.source
            items = self._known_items(view)
            if items is None:
                raise Unreadable("iterates a map whose contents aren't known")
            if view.map.mod != recv.mod:
                raise Unreadable("a map changes while it is iterated (ConcurrentModificationException)")
            if name == "hasNext" and not rest:
                return [int(recv.pos < len(items))]
            if name == "next" and not rest:
                if recv.pos >= len(items):
                    return []  # NoSuchElementException
                self._write_by_call(recv)
                recv.pos += 1
                return [items[recv.pos - 1]]
            view.map.items, view.map.havoc, view.map.exact = {}, True, False
            return [UNKNOWN] if returns else [None]
        if isinstance(recv, MapView) and not static:
            items = self._known_items(recv)
            if name == "iterator" and not rest and items is not None:
                return [IterV(recv, 0, recv.map.mod)]
            if name in ("isEmpty", "size") and not rest and items is not None:
                return [int(not items)] if name == "isEmpty" else [len(items)]
            recv.map.items, recv.map.havoc, recv.map.exact = {}, True, False
            return [UNKNOWN] if returns else [None]
        if isinstance(recv, IterV):
            src = recv.source
            items = self._known_items(src)
            if isinstance(src, ListV) and src.havoc and name in ("hasNext", "next"):
                # A loop over a list whose contents aren't known can't be
                # followed (each way would only add another unknown turn).
                raise Unreadable("iterates a list whose contents aren't known")
            if items is None or (isinstance(src, ListV) and src.mod != recv.mod):
                if name == "next" and isinstance(src, ListV) and not src.havoc and src.mod != recv.mod:
                    raise Unreadable("a list changes while it is iterated (ConcurrentModificationException)")
                return [UNKNOWN] if returns else [None]
            if name == "hasNext" and not rest:
                return [int(recv.pos < len(items))]
            if name == "next" and not rest:
                if recv.pos >= len(items):
                    return []  # NoSuchElementException
                self._write_by_call(recv)
                recv.pos += 1
                return [items[recv.pos - 1]]
            if name == "remove" and not rest and isinstance(src, ListV) and recv.pos > 0:
                self._write_by_call(recv)
                self._write_by_call(src)
                del src.items[recv.pos - 1]
                recv.pos -= 1
                src.mod += 1
                recv.mod = src.mod
                return [None]
            if isinstance(src, ListV):
                return self._havoc_list(src, returns)
            return [UNKNOWN] if returns else [None]
        if isinstance(recv, Coll) and not static:
            if name == "iterator" and not rest:
                return [IterV(recv)]
            if name == "isEmpty" and not rest:
                return [int(not recv.items)]
            if name == "get" and len(rest) == 1 and isinstance(rest[0], int) and not isinstance(rest[0], bool):
                return [recv.items[rest[0]]] if 0 <= rest[0] < len(recv.items) else []
            return _NOT_HANDLED
        if not isinstance(recv, ListV) or static:
            return _NOT_HANDLED
        lst = recv
        if name in ("equals", "hashCode", "toString"):
            return [UNKNOWN]
        if lst.havoc:
            if name in ("iterator", "listIterator") and not rest:
                return [IterV(lst, 0, lst.mod)]
            if name in ("forEach", "removeIf"):
                raise Unreadable("iterates a list whose contents aren't known")
            if name in ("size", "isEmpty", "get", "stream", "contains", "toArray", "indexOf",
                        "getFirst", "getLast", "peek"):
                return [UNKNOWN]
            return self._havoc_list(lst, returns)
        items = lst.items
        if name == "add" and desc == "(Ljava/lang/Object;)Z":
            self._write_by_call(lst)
            items.append(rest[0])
            lst.mod += 1
            return [1]
        if name == "add" and desc == "(ILjava/lang/Object;)V" and isinstance(rest[0], int) \
                and 0 <= rest[0] <= len(items):
            self._write_by_call(lst)
            items.insert(rest[0], rest[1])
            lst.mod += 1
            return [None]
        if name == "addAll" and desc == "(Ljava/util/Collection;)Z":
            more = self._known_items(rest[0])
            if more is None:
                return self._havoc_list(lst, returns)
            self._write_by_call(lst)
            items.extend(more)
            lst.mod += 1
            return [int(bool(more))]
        if name == "size" and not rest:
            return [len(items)]
        if name == "isEmpty" and not rest:
            return [int(not items)]
        if name == "get" and desc == "(I)Ljava/lang/Object;":
            i = rest[0]
            if isinstance(i, int) and not isinstance(i, bool):
                return [items[i]] if 0 <= i < len(items) else []
            return [UNKNOWN]
        if name in ("iterator", "listIterator") and not rest:
            return [IterV(lst, 0, lst.mod)]
        if name == "stream" and not rest:
            return [Strm(tuple(items))]
        if name == "toArray" and desc in ("()[Ljava/lang/Object;", "(Ljava/util/function/IntFunction;)[Ljava/lang/Object;"):
            return [Arr(list(items))]
        if name == "clear" and not rest:
            self._write_by_call(lst)
            lst.items = []
            lst.mod += 1
            return [None]
        if name == "forEach" and desc == "(Ljava/util/function/Consumer;)V":
            # ArrayList#forEach: each element in order; a change to the list
            # meanwhile throws ConcurrentModificationException at the end.
            mod = lst.mod
            for item in list(items):
                out = self._apply(rest[0], "accept", "(Ljava/lang/Object;)V", [item])
                if out is UNKNOWN and not isinstance(rest[0], (Lam, Obj)):
                    return self._havoc_list(lst, False)
            if lst.mod != mod:
                raise Unreadable("a list changes while it is iterated (ConcurrentModificationException)")
            return [None]
        if name == "removeIf" and desc == "(Ljava/util/function/Predicate;)Z":
            # Collection#removeIf / ArrayList#removeIf: the elements the
            # predicate holds for are removed, in one pass.
            verdicts = [self._test(rest[0], item) for item in items]
            if None in verdicts:
                return self._havoc_list(lst, True)
            if any(verdicts):
                self._write_by_call(lst)
                lst.items = [i for i, v in zip(items, verdicts) if not v]
                lst.mod += 1
            return [int(any(verdicts))]
        if name == "contains" and len(rest) == 1:
            same = [_same(rest[0], i) for i in items]
            if None in same:
                return [UNKNOWN]
            return [int(any(same))]
        return self._havoc_list(lst, returns)

    def _stream(self, strm: "Strm", name: str, desc: str, rest: list):
        """Sequential ``java.util.stream.Stream`` operations on known
        elements (Java SE 21): ``filter``, ``map``, ``count``, ``toList``,
        ``collect`` with ``Collectors.toList`` / ``toUnmodifiableList`` /
        ``toCollection``, ``anyMatch`` / ``allMatch`` / ``noneMatch``,
        ``findFirst`` and ``forEach``, each in encounter order. Anything
        else, or a function whose value isn't known, is unknown."""
        items = list(strm.items)
        if name == "filter" and len(rest) == 1:
            verdicts = [self._test(rest[0], i) for i in items]
            if None in verdicts:
                return [UNKNOWN]
            return [Strm(tuple(i for i, v in zip(items, verdicts) if v))]
        if name == "map" and len(rest) == 1:
            out = [self._apply(rest[0], "apply", "(Ljava/lang/Object;)Ljava/lang/Object;", [i]) for i in items]
            if any(o is UNKNOWN or isinstance(o, _Many) for o in out):
                return [UNKNOWN]
            return [Strm(tuple(out))]
        if name == "count" and not rest:
            return [len(items)]
        if name == "toList" and not rest:
            return [Coll(tuple(items))]
        if name in ("anyMatch", "allMatch", "noneMatch") and len(rest) == 1:
            verdicts = [self._test(rest[0], i) for i in items]
            if None in verdicts:
                return [UNKNOWN]
            return [int({"anyMatch": any, "allMatch": all}.get(name, lambda v: not any(v))(verdicts))]
        if name == "findFirst" and not rest:
            return [Opt(items[0] if items else None)]
        if name == "findAny" and not rest:
            # Any element (Stream#findAny is free to pick); whether there is
            # one is known.
            return [Opt(None if not items else items[0] if len(items) == 1 else UNKNOWN)]
        if name == "forEach" and len(rest) == 1:
            for i in items:
                self._apply(rest[0], "accept", "(Ljava/lang/Object;)V", [i])
            return [None]
        if name == "collect" and len(rest) == 1 and isinstance(rest[0], CollectorV):
            c = rest[0]
            if c.kind == "toUnmodifiableList":
                return [Coll(tuple(items))]
            if c.kind == "toList":
                return [ListV(items)]
            made = self._apply(c.supplier, "get", "()Ljava/lang/Object;", [])
            if isinstance(made, ListV) and not made.havoc:
                made.items.extend(items)
                made.mod += 1
                return [made]
            return [UNKNOWN]
        return [UNKNOWN] if _arg_count(desc)[1] else [None]

    def _reduce(self, strm: Strm, rest: list):
        if len(rest) == 1:
            op, items, acc = rest[0], list(strm.items), None
            if not items:
                return [Opt(None)]
            acc, items = items[0], items[1:]
        elif len(rest) == 2:
            acc, op, items = rest[0], rest[1], list(strm.items)
        else:
            return [UNKNOWN]
        if not isinstance(op, Lam):
            return [UNKNOWN]
        for item in items:
            out = self.call_lambda(op, [acc, item])
            if len(out) != 1:
                raise Unreadable("a shape fold has more than one outcome")
            acc = out[0]
        return [Opt(acc)] if len(rest) == 1 else [acc]


_NOT_HANDLED = object()
# java.util's Map interface and its implementations (Java SE 21).
# Constant pool tags (JVMS 4.4): String, Methodref, InterfaceMethodref,
# MethodHandle.
_CP_STRING = 8
_SETTER_TAGS = frozenset({8, 10, 11, 15})
_SYSTEM_SETTERS = frozenset({"setProperty", "setProperties", "clearProperty", "getProperties"})
_NOKEY = object()  # a map key whose equality isn't known (Machine._map_key)
# Map methods that change a map: an unmodifiable map (Map.of) throws
# UnsupportedOperationException for each (ImmutableCollections, Java SE 21).
_MAP_CHANGES = frozenset({"put", "putAll", "putIfAbsent", "remove", "clear", "compute", "computeIfAbsent",
                          "computeIfPresent", "merge", "replace", "replaceAll"})
# Map methods that change nothing (java.util.Map, Java SE 21).
_MAP_READS = frozenset({"containsValue", "equals", "hashCode", "toString", "getClass", "forEach"})
_JAVA_MAPS = frozenset({"java/util/Map", "java/util/HashMap", "java/util/LinkedHashMap", "java/util/TreeMap",
                        "java/util/IdentityHashMap", "java/util/WeakHashMap", "java/util/EnumMap",
                        "java/util/SortedMap", "java/util/NavigableMap", "java/util/AbstractMap",
                        "java/util/concurrent/ConcurrentHashMap", "java/util/concurrent/ConcurrentMap"})
# How many levels of callers of a name-building method _piece_methods runs.
_CALLER_LEVELS = 4
_PAIR_OF = ("org/apache/commons/lang3/tuple/Pair", "org/apache/commons/lang3/tuple/ImmutablePair")
_PAIR_OF_DESC = {
    "org/apache/commons/lang3/tuple/Pair": "(Ljava/lang/Object;Ljava/lang/Object;)Lorg/apache/commons/lang3/tuple/Pair;",
    "org/apache/commons/lang3/tuple/ImmutablePair":
        "(Ljava/lang/Object;Ljava/lang/Object;)Lorg/apache/commons/lang3/tuple/ImmutablePair;",
}
# java.util.regex metacharacters (Pattern, Java SE 21): a regex without
# any of them matches only itself.
_REGEX_META = set("\\^$.|?*+()[]{}")
_FORKED_WRITE = "writes to memory after a branch it can't decide"
_TOO_MUCH = "too much code to follow"
# java.util's mutable lists the machine models (#280 pick 2).
_MUTABLE_LISTS = frozenset({"java/util/ArrayList", "java/util/LinkedList"})


class _WeakWrite(Exception):
    """A modelled list change on one way of an undecided branch (see
    Machine._write_by_call)."""


@dataclass(frozen=True)
class _Many:
    """The values a function's ways return when they differ."""

    values: tuple
# System properties the JVM or a game launcher may define (#280 pick 1):
# the standard properties of System#getProperties (Java SE 21 javadoc:
# java.*, os.*, file.*, path.*, line.*, user.*, native.*, stdout.*, stderr.*;
# implementation properties jdk.*, sun.*, com.sun.*; javax.*, awt.*), the
# networking properties (java.net docs, "Networking Properties": http.*,
# https.*, ftp.*, socksProxy*, socksNonProxyHosts, networkaddress.*), and the
# namespaces of the mod loaders and their launch stack (Fabric Loader
# ``fabric.*``, Quilt ``quilt.*`` / ``loader.*``, Forge/NeoForge FML
# ``fml.*`` / ``forge*`` / ``neoforge*``, ``mixin.*``, ``log4j*``,
# ``org.lwjgl.*``, ``minecraft.*``). Any other property is unset in a
# player's game unless something sets it.
_RESERVED_PROPERTIES = ("java.", "javax.", "jdk.", "sun.", "com.sun.", "os.", "file.", "path.", "line.",
                        "user.", "native.", "stdout.", "stderr.", "awt.", "http.", "https.", "ftp.",
                        "socksProxy", "socksNonProxyHosts", "networkaddress.", "fabric.", "quilt.",
                        "loader.", "fml.", "forge", "neoforge", "mixin.", "log4j", "org.lwjgl.",
                        "minecraft.")
# Static ``of`` factories of immutable collections (Guava, java.util; Java SE 21 /
# Guava 32 javadoc: a list keeps the order given, an ImmutableSet the first of
# equal elements in the order given).
_SET_OF = frozenset({"com/google/common/collect/ImmutableSet", "java/util/Set"})
_IMMUTABLE_OF = _SET_OF | {"com/google/common/collect/ImmutableList", "java/util/List"}
_BUILTIN_REGISTRIES = "net/minecraft/core/registries/BuiltInRegistries"
_VANILLA_BLOCKS = "net/minecraft/world/level/block/Blocks"
# A resource location's characters (ResourceLocation#isValidNamespace /
# isValidPath, MC 1.21.1: namespace [a-z0-9_.-], path [a-z0-9_./-]).
_RESOURCE_NAME = re.compile(r"([a-z0-9_.-]+:)?[a-z0-9_./-]+")


def _lazy_guarded(code: list, k: int, owner: str, name: str, machine: "Machine") -> int | None:
    """The index of the ``ifnonnull`` guarding the ``putstatic`` at
    ``code[k]`` as ``getstatic F; ifnonnull L; ...; putstatic F; L:``, with
    nothing between the guard and the write jumping out of it or into it
    from elsewhere, returning or throwing, and no local variable read there that the stretch didn't
    first write (a computation from the method's arguments or earlier
    locals could yield a different value each call), or None."""
    after = code[k + 1].offset if k + 1 < len(code) else None
    for j in range(k - 1, 0, -1):
        insn = code[j]
        if insn.op == 0xC7 and insn.arg == after:
            prev = code[j - 1]
            if not (prev.op == 0xB2 and isinstance(prev.arg, Ref) and prev.arg.name == name
                    and machine._field_owner(prev.arg.owner, name) == owner):
                return None
            inside = {c.offset for c in code[j + 1:k + 1]}
            for i, other in enumerate(code):
                if j <= i <= k:
                    targets = _targets(other)
                    if i > j and any(t not in inside and t != after for t in targets):
                        return None
                    continue
                if any(t in inside for t in _targets(other)):
                    return None
            written: set = set()
            for other in code[j + 1:k]:
                if 0xAC <= other.op <= 0xB1 or other.op == 0xBF:
                    return None  # leaves the method before the write
                load = _local_load(other)
                if load is not None and load not in written:
                    return None
                store = _local_store(other)
                if store is not None:
                    written.add(store)
            return j
    return None


def _local_load(insn) -> int | None:
    """The local variable slot ``insn`` reads (xload, iinc, ret), if any."""
    op = insn.op
    if 0x15 <= op <= 0x19 or op == 0xA9:
        return insn.arg
    if 0x1A <= op <= 0x2D:
        return (op - 0x1A) % 4
    if op == 0x84:
        return insn.arg[0]
    return None


def _local_store(insn) -> int | None:
    """The local variable slot ``insn`` writes (xstore), if any."""
    op = insn.op
    if 0x36 <= op <= 0x3A:
        return insn.arg
    if 0x3B <= op <= 0x4E:
        return (op - 0x3B) % 4
    return None


def _targets(insn) -> list:
    """The offsets ``insn`` may jump to (not its fall-through)."""
    if 0x99 <= insn.op <= 0xA8 or insn.op in (0xC6, 0xC7, 0xC8):
        return [insn.arg]
    if insn.op in (0xAA, 0xAB):
        default, table = insn.arg
        return [default, *table.values()]
    return []


def _join_fields(ends: list) -> dict:
    """The fields a constructor leaves on its receiver, joined over the
    paths that returned (#280). A field every path left the same (the same
    object, or an equal value: a string, a number, a constant, an equal
    Properties copy) keeps it; a field the paths left differently, or that
    some path didn't set, is UNKNOWN and the object is marked ``__partial``
    (what its constructor stored isn't known), so no reader takes it."""
    if len(ends) == 1:
        return ends[0]
    out: dict = {}
    differ = []
    for key in sorted({k for e in ends for k in e}, key=str):
        if key == "__partial":
            continue
        vals = [e.get(key, _MISSING) for e in ends]
        first = vals[0]
        if all(v is first or (v is not _MISSING and first is not _MISSING and _equal(v, first)) for v in vals[1:]):
            out[key] = first
        else:
            out[key] = UNKNOWN
            differ.append(key)
    partial = [e["__partial"] for e in ends if "__partial" in e]
    if partial:
        out["__partial"] = partial[0]
    elif differ:
        out["__partial"] = ("its constructor's ways after a branch it can't decide leave "
                            + ", ".join(differ) + " different")
    return out


_MISSING = object()


def _equal(a, b) -> bool:
    """Value equality for joining: identity for objects, arrays, maps and
    builders (Obj and friends compare by identity), == for everything else
    (frozen dataclasses and Props compare by value; tuples element-wise)."""
    try:
        return bool(a == b)
    except Exception:
        return False


def _value_equal(a, b) -> bool:
    """Whether two returned values are the same value: the same object, or
    equal immutable values (strings, numbers, constants, names, directions,
    shapes); never UNKNOWN or a mutable value of the machine's."""
    if a is b:
        return a is not UNKNOWN
    if isinstance(a, (str, int, float, Const, ClassLit, RL, RKey, Dir, Shape, Tail)) \
            and type(a) is type(b):
        return _equal(a, b)
    return False


def _hashable(v) -> bool:
    try:
        hash(v)
    except TypeError:
        return False
    return True


def _same(a, b):
    """Reference equality of two abstract values, or None when undecidable."""
    if a is UNKNOWN or b is UNKNOWN:
        return None
    if isinstance(a, (Obj, Arr, MapV, Builder)) or isinstance(b, (Obj, Arr, MapV, Builder)):
        return a is b
    if isinstance(a, (PlayerDir, LookDir)) or isinstance(b, (PlayerDir, LookDir)):
        return None
    return a == b


def _box(args: list, scale: float) -> Shape:
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in args):
        return UNKNOWN
    x1, y1, z1, x2, y2, z2 = (float(v) * scale for v in args)
    return Shape(((min(x1, x2), min(y1, y2), min(z1, z2), max(x1, x2), max(y1, y2), max(z1, z2)),))


def _union(parts: list):
    flat = []
    for p in parts:
        if isinstance(p, Arr):
            flat.extend(p.items)
        else:
            flat.append(p)
    out = Shape(())
    for p in flat:
        if not isinstance(p, Shape):
            return UNKNOWN
        out = out.union(p)
    return out


def _bbox(boxes) -> tuple:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), min(b[2] for b in boxes),
            max(b[3] for b in boxes), max(b[4] for b in boxes), max(b[5] for b in boxes))


# --- What a converter asks for ---------------------------------------------

@dataclass
class Reading:
    """One block's facing and shape as its code gives them.

    ``placement`` is the y_rotation_offset of Bedrock's placement_direction
    trait (0: facing = the player's facing; 180: the opposite), or None with
    ``placement_why``. ``shapes`` maps each horizontal facing to Java's shape
    boxes (pixels), or is None with ``shape_why``. ``collision`` is True when
    the block collides with that same shape, False when its Properties say
    noCollission, or None with ``collision_why``. ``where`` names the class
    each answer was read from.
    """

    name: str
    cls: str | None = None
    placement: int | None = None
    placement_why: str = ""
    placement_from: str = ""
    # Set when the code was read and its rule is one Bedrock's placement
    # trait can't give (a quarter turn from the player, or a facing the
    # player doesn't set): the block then stays residue rather than take the
    # default against what its code says.
    placement_conflict: str = ""
    shapes: dict | None = None
    shape_why: str = ""
    shape_from: str = ""
    collision: bool | None = None
    collision_why: str = ""
    # The state names createBlockStateDefinition adds, or None if unread.
    states: tuple | None = None
    # Behaviour methods the block's own classes override (use, ticks, a block
    # entity...), which a converted facing block doesn't carry.
    behaviour: tuple = ()


_SHARED_WHY = ("its Properties object is shared with other registrations that change it, so "
               "what it holds when this block is built depends on registration order")
_OBFUSCATED = re.compile(r"^(m_\d+_|f_\d+_|method_\d+|field_\d+|func_\d+_[a-z]+)$")


def _renamed(machine: Machine, cls: str) -> bool:
    """Whether the block's own classes use Forge SRG (``m_5573_``) or Fabric
    intermediary (``method_9605``) member names: then a method we look for by
    its Mojang name may be there under another, and "not overridden" can't be
    told from "renamed"."""
    for cname in machine.chain(cls):
        cf = machine.classes.get(cname)
        if cf is None:
            break
        if any(_OBFUSCATED.match(m.name) for m in cf.methods):
            return True
    return False


def _declaring(machine: Machine, cls: str, name: str, desc: str) -> str:
    found = machine.find_method(cls, name, desc) if machine.is_mod(cls) else None
    if found is not None:
        return f"{found[0].name.replace('/', '.')}#{name}"
    return f"{machine.vanilla_base(cls).replace('/', '.')}#{name} (vanilla, inherited)"


def _wanted_classes(classes: ClassIndex, names: set[str]) -> list[str]:
    """Classes whose constant pool holds one of ``names`` as a string."""
    out = []
    for cname in classes.names():
        cf = classes.get(cname)
        if cf is None:
            continue
        for entry in cf.pool:
            if entry is not None and entry[0] == 8:  # CONSTANT_String
                text = cf.pool[entry[1]][1]
                if text in names or text.rsplit(":", 1)[-1] in names:
                    out.append(cname)
                    break
    return out


def _naming_methods(classes: ClassIndex, cname: str, names: set[str]) -> list:
    """The methods of ``cname`` other than its static initializer that load
    one of ``names`` as a String constant (``ldc``), abstract ones skipped."""
    cf = classes.get(cname)
    if cf is None:
        return []
    out = []
    for m in cf.methods:
        if m.name == "<clinit>" or m.code is None:
            continue
        try:
            code = instructions(cf, m.code)
        except Exception:  # noqa: BLE001 - an unreadable method names nothing
            continue
        if any(i.op in (0x12, 0x13) and isinstance(i.arg, str)
               and (i.arg in names or i.arg.rsplit(":", 1)[-1] in names) for i in code):
            out.append((cf, m))
    return out


def _name_pieces(names: set[str]) -> set[str]:
    """Every run of whole ``_``-separated words of each name in ``names``
    that is not the whole name (``azalea_pressure_plate``: ``azalea``,
    ``pressure``, ``plate``, ``azalea_pressure``, ``pressure_plate``)."""
    out = set()
    for n in names:
        words = n.rsplit(":", 1)[-1].split("_")
        for i in range(len(words)):
            for j in range(i + 1, len(words) + 1):
                if j - i < len(words):
                    out.add("_".join(words[i:j]))
    out.discard("")
    return out


def _recipe_matcher(recipe: str) -> "re.Pattern":
    """A StringConcatFactory recipe (``\\x01`` an argument, ``\\x02`` a
    constant) as a pattern a whole name must match, each slot a non-empty
    run of name characters."""
    parts = re.split("[\x01\x02]", recipe)
    return re.compile("[a-z0-9_./-]+".join(re.escape(p) for p in parts))


def _format_matcher(text: str) -> "re.Pattern | None":
    """A ``String.format`` pattern whose only specifiers are ``%s`` as a
    pattern a whole name must match, each ``%s`` a non-empty run of name
    characters; None for any other specifier (``%%`` included) and for one
    with no letter or digit of its own (``"%s"``, ``"%s_%s"`` would match
    nearly every name)."""
    if re.search(r"%(?!s)", text):
        return None
    parts = text.split("%s")
    if len(parts) < 2 or not re.search("[a-z0-9]", "".join(parts)):
        return None
    return re.compile("[a-z0-9_./-]+".join(re.escape(p) for p in parts))


def _piece_methods(classes: ClassIndex, names: set[str], done: set) -> list:
    """Methods of the mod's own classes (not a library's, never its static
    initializers, abstract ones skipped, those in ``done`` skipped) that may
    build one of ``names`` by concatenation (#280): one that loads (``ldc``)
    a whole-word piece of a name (``"azalea"`` handed to a helper that
    appends ``"_planks"``; ``"_shingles"`` appended in a loop), or one whose
    ``makeConcatWithConstants`` recipe matches a whole name
    (``"\\x01_pressure_plate"``), or one that loads a ``%s`` format string
    whose filled slots match a whole name (``"hollow_%s"``). Which name it builds is only what the
    machine evaluates; this only chooses what to run."""
    pieces = _name_pieces(names)
    bare = {n.rsplit(":", 1)[-1] for n in names}
    out = []
    for cname in classes.names():
        cf = classes.get(cname)
        if cf is None:
            continue
        strings = {cf.pool[e[1]][1] for e in cf.pool if e is not None and e[0] == 8}
        fmts = [_format_matcher(s) for s in strings if "%s" in s]
        fmts = {s.pattern for s in fmts if s is not None and any(s.fullmatch(n) for n in bare)}
        if not any(s.strip("_") in pieces or "\x01" in s for s in strings) and not fmts:
            continue
        for m in cf.methods:
            if m.name == "<clinit>" or m.code is None or (cname, m.name, m.desc) in done:
                continue
            try:
                code = instructions(cf, m.code)
            except Exception:  # noqa: BLE001 - an unreadable method builds nothing
                continue
            hit = False
            for i in code:
                if i.op in (0x12, 0x13) and isinstance(i.arg, str) and i.arg.strip("_") in pieces:
                    hit = True
                elif i.op in (0x12, 0x13) and isinstance(i.arg, str) and "%s" in i.arg:
                    # A format string whose %s slots, filled, give a whole
                    # name ("hollow_%s" handed to a library's inherit with
                    # the parent block, #280).
                    pat = _format_matcher(i.arg)
                    hit = pat is not None and pat.pattern in fmts
                elif i.op == 0xBA and isinstance(i.arg, Indy) and i.arg.bootstrap \
                        and i.arg.bootstrap.ref.owner == "java/lang/invoke/StringConcatFactory" \
                        and i.arg.args and isinstance(i.arg.args[0], str) and "\x01" in i.arg.args[0]:
                    pat = _recipe_matcher(i.arg.args[0])
                    hit = any(pat.fullmatch(n) for n in bare)
                if hit:
                    break
            if hit:
                out.append((cf, m))
    # One level up: a method that calls one of those (a module's
    # register(event) looping over DyeColor.values() into
    # ``new StoolBlock(this, dye)``, whose constructor appends "_stool").
    # Callers are searched up to _CALLER_LEVELS levels, and a lambda or method
    # reference (an invokedynamic naming the method) counts as a call (#280:
    # a module's register method hands each vanilla slab to a lambda that
    # builds the mod's vertical slab, whose constructor takes its name from a
    # lambda appending "_vertical_slab").
    targets = {(cf.name, m.name, m.desc) for cf, m in out}
    # A block constructor that loads a whole name (run on its own object,
    # see _constructed) is a target too: a module's ``register(event)``
    # doing ``thatch = new ThatchBlock(this)`` and then handing it to a
    # library's ``addSlabAndStairs`` names the slab from the block's
    # registered name, which only that run holds (#280).
    targets |= {k for k in done if k[1] == "<init>"}
    chosen = set(targets)
    callers = []
    codes = []
    for cname in classes.names():
        cf = classes.get(cname)
        if cf is None:
            continue
        for m in cf.methods:
            if m.name == "<clinit>" or m.code is None:
                continue
            try:
                code = instructions(cf, m.code)
            except Exception:  # noqa: BLE001
                continue
            called = set()
            for i in code:
                if i.op in (0xB6, 0xB7, 0xB8, 0xB9) and isinstance(i.arg, Ref):
                    called.add((i.arg.owner, i.arg.name, i.arg.desc))
                elif i.op == 0xBA and isinstance(i.arg, Indy):
                    called.update((h.ref.owner, h.ref.name, h.ref.desc) for h in i.arg.args
                                  if isinstance(h, Handle))
            codes.append((cf, m, called))
    for _level in range(_CALLER_LEVELS):
        found = []
        for cf, m, called in codes:
            key = (cf.name, m.name, m.desc)
            if key in chosen or key in done or not called & targets:
                continue
            found.append((cf, m))
            chosen.add(key)
        if not found:
            break
        callers += found
        targets = {(cf.name, m.name, m.desc) for cf, m in found}
    return out + callers


def _constructed(machine: Machine, cf: ClassFile, m: Method):
    """The receiver a method of ``cf`` run on its own (see _run_method) is
    given: for a constructor of a block class that is neither abstract nor
    an interface and that no class of the mod or its libraries extends, a
    new object of exactly that class (#280: a block whose constructor hands
    its own name, ``super("sturdy_stone", module, ..)``, while the module
    only does ``new SturdyStoneBlock(this)``). An instance initialization
    method is only ever invoked on an object ``new`` just made of its class
    or of a subclass, which then calls it as its super constructor (JVMS
    2.9.1, 4.10.1.9 invokespecial, 6.5 new); with no subclass anywhere in
    the jar or its libraries (closed: the classes read are the mod's), the
    object is one of exactly ``cf``. Anything else stays UNKNOWN."""
    if m.name != "<init>" or cf.access & 0x0600 or not machine.is_block_class(cf.name) \
            or machine.has_subclass(cf.name):
        return UNKNOWN
    obj = machine._new(cf.name)
    obj._uninit = False
    return obj


def _run_method(machine: Machine, cf: ClassFile, m: Method) -> None:
    """Run ``m`` once on unknown arguments for the registrations it makes,
    its class initialized first. A run that stops part way (Unreadable)
    leaves the statics it wrote half done (a library's "chain started" flag
    set and never cleared, which the next run would branch on), so they go
    back to what they were before it; registrations it recorded stay."""
    saved = (dict(machine.statics), set(machine._clinit_done), set(machine._clinit_failed))
    static = bool(m.access & 0x0008)
    n, _ = _arg_count(m.desc)
    try:
        machine.steps = 0
        machine.init_class(cf.name)
        machine.steps = 0
        machine.new_epoch()
        recv = [] if static else [_constructed(machine, cf, m)]
        machine.run(cf, m, recv + [UNKNOWN] * n)
    except Unreadable:
        machine.statics, machine._clinit_done, machine._clinit_failed = saved


def _registered(classes: ClassIndex, names: list[str]) -> tuple[Machine, dict[str, tuple[list, str]]]:
    """Run the registration code that names each blockstate in ``names`` and
    return, per name, the block objects built for it (``[]`` with the reason
    when none was found or it can't be followed)."""
    machine = Machine(classes)
    machine.registrations = []
    wanted = _wanted_classes(classes, set(names))
    for cname in wanted:
        machine.steps = 0
        machine.init_class(cname)
    # Registrations made in a method rather than a static initializer (#280):
    # a module's or an initializer's ``register(event)`` / ``onInitialize()``
    # constructing ``new FooBlock("name", ...)``. Each method of a wanted class
    # that loads one of the names runs once on unknown arguments.
    done = set()
    for cname in wanted:
        for cf, m in _naming_methods(classes, cname, set(names)):
            done.add((cf.name, m.name, m.desc))
            _run_method(machine, cf, m)
    # Names built by concatenation (#280): every other method that may build
    # one (see _piece_methods) runs the same way, its class initialized
    # first (a static initializer building names in a loop over an enum).
    first = len(machine.registrations)
    for cf, m in _piece_methods(classes, set(names), done):
        _run_method(machine, cf, m)
    for reg in machine.registrations[first:]:
        reg.concat = True
    regs: dict[str, list] = {}
    unread: dict[str, str] = {}
    concat_only: set = set()
    plain: set = set()
    for reg in machine.registrations:
        if reg.value is None:
            if not reg.concat:
                unread.setdefault(reg.name, reg.why)
                regs.setdefault(reg.name, [])
            continue
        (concat_only if reg.concat else plain).add(id(reg.value))
        found = regs.setdefault(reg.name, [])
        # The same object handed on through a library's own registry
        # methods (each recorded, #280) is one registration.
        if not any(v is reg.value for v in found):
            found.append(reg.value)
    machine.registrations = None

    out: dict[str, tuple[list, str]] = {}
    # Every registration found is built, wanted or not: one that changes a
    # shared Properties object must mark it (Props.shared_changed) before
    # any block built from that object is read.
    for name in [*names, *sorted(set(regs) - set(names))]:
        objs, others = [], []
        why = ""
        for value in regs.get(name, []):
            machine.steps = 0
            machine.new_epoch()
            try:
                built = machine.call_lambda(value, []) if isinstance(value, Lam) else [value]
            except Unreadable as exc:
                why = f"its registration can't be followed ({exc})"
                continue
            objs += [o for o in built if isinstance(o, Obj) and machine.is_block_class(o.cls)]
            if id(value) in concat_only and id(value) not in plain:
                continue
            others += [o.cls for o in built if isinstance(o, Obj) and not machine.is_block_class(o.cls)
                       and "Item" not in o.cls.rsplit("/", 1)[-1] and "Entity" not in o.cls.rsplit("/", 1)[-1]]
        others = [o for o in others if not machine.vanilla_base(o).startswith(("java/", "com/mojang/"))]
        if not objs and others:
            outside = machine.vanilla_base(others[0])
            why = why or (f"registered as {others[0].replace('/', '.')}, whose superclasses leave the jar at "
                          f"{outside.replace('/', '.')} rather than reach a vanilla block class")
        if not objs:
            why = why or unread.get(name) or "no registration of this block was found in the mod's classes"
        elif len({o.cls for o in objs}) != 1:
            why = "registered more than once with different classes: " + ", ".join(sorted({o.cls for o in objs}))
            objs = []
        elif _renamed(machine, objs[0].cls):
            why = (f"{objs[0].cls.replace('/', '.')} uses Forge SRG or Fabric intermediary member names, so its "
                   "methods can't be told apart from vanilla's by name")
            objs = []
        out[name] = (objs, why)
    return machine, {n: out[n] for n in names}


def read_blocks(classes: ClassIndex | None, names: list[str]) -> dict[str, Reading]:
    """A :class:`Reading` per blockstate name in ``names``."""
    readings = {n: Reading(n) for n in names}
    if classes is None or not len(classes):
        for r in readings.values():
            r.placement_why = r.shape_why = r.collision_why = "the mod ships no class files"
        return readings
    machine, registered = _registered(classes, names)
    for name, r in readings.items():
        objs, why = registered[name]
        if not objs:
            r.placement_why = r.shape_why = r.collision_why = why
            continue
        obj = objs[0]
        r.cls = obj.cls.replace("/", ".")
        _read_states(machine, obj, r)
        r.behaviour = _behaviour(machine, obj.cls)
        _read_placement(machine, obj, r)
        _read_shape(machine, obj, r)
        if len(objs) > 1:
            # The same class built twice (an item and a block registry both
            # naming it would be filtered above); answers must agree.
            other = Reading(name)
            _read_placement(machine, objs[1], other)
            _read_shape(machine, objs[1], other)
            if (other.placement, other.shapes, other.collision) != (r.placement, r.shapes, r.collision):
                r.placement, r.shapes, r.collision = None, None, None
                r.placement_why = r.shape_why = r.collision_why = "registered twice with different settings"
    return readings


# Block methods (Mojang names, 1.21.1 BlockBehaviour/Block/EntityBlock) whose
# override means the block does something when used, ticked, walked on or
# changed around it, or keeps a block entity.
_BEHAVIOUR = ("useWithoutItem", "useItemOn", "use", "newBlockEntity", "getTicker", "tick",
              "randomTick", "onPlace", "onRemove", "neighborChanged", "entityInside", "stepOn",
              "fallOn", "attack", "playerWillDestroy", "setPlacedBy", "getAnalogOutputSignal",
              "getSignal", "animateTick", "triggerEvent")


def _behaviour(machine: Machine, cls: str) -> tuple:
    found = []
    for cname in machine.chain(cls):
        cf = machine.classes.get(cname)
        if cf is None:
            break
        found += [m.name for m in cf.methods if m.name in _BEHAVIOUR and m.code is not None]
    return tuple(sorted(set(found)))


def _read_states(machine: Machine, obj: Obj, r: Reading) -> None:
    machine.steps = 0
    desc = "(Lnet/minecraft/world/level/block/state/StateDefinition$Builder;)V"
    if machine.find_method(obj.cls, "createBlockStateDefinition", desc) is None:
        return
    builder = Obj("__statebuilder")
    try:
        machine.call(obj.cls, "createBlockStateDefinition", desc, [obj, builder])
    except Unreadable:
        return
    names = builder.fields.get("names", [])
    if names and "?" not in names:
        r.states = tuple(sorted(set(names)))


def _read_placement(machine: Machine, obj: Obj, r: Reading) -> None:
    machine.steps = 0
    where = _declaring(machine, obj.cls, "getStateForPlacement", _PLACEMENT_DESC)
    try:
        results = machine.call(obj.cls, "getStateForPlacement", _PLACEMENT_DESC, [obj, PLACE_CTX])
    except Unreadable as exc:
        r.placement_why = f"{where}: {exc}"
        return
    facings = set()
    for res in results:
        facings.add(res.get("facing") if isinstance(res, State) else UNKNOWN)
    if len(facings) != 1:
        r.placement_why = f"{where}: facing differs between paths through the method"
        return
    facing = facings.pop()
    # A state the code built without ever setting facing keeps the block's
    # default facing, whoever places it.
    if isinstance(facing, Dir) or (facing is UNKNOWN and results and all(isinstance(x, State) for x in results)
                                   and not any("facing" in dict(x.values) for x in results)):
        r.placement_conflict = (f"{where}: the player doesn't set facing (the block keeps "
                                "its default facing), which Bedrock's placement trait can't give")
        r.placement_why = r.placement_conflict
        return
    if not isinstance(facing, PlayerDir):
        r.placement_why = f"{where}: facing is not set from the player's horizontal direction"
        return
    if facing.quarters not in (0, 2):
        r.placement_conflict = (f"{where}: facing is the player's direction turned a quarter turn, "
                                "and which way Bedrock's y_rotation_offset turns is not verified")
        r.placement_why = r.placement_conflict
        return
    r.placement = 0 if facing.quarters == 0 else 180
    r.placement_from = where


def _read_shape(machine: Machine, obj: Obj, r: Reading) -> None:
    machine.steps = 0
    where = _declaring(machine, obj.cls, "getShape", _GET_SHAPE_DESC)
    default = obj.fields.get("__default", State())
    shapes = {}
    try:
        if "__partial" in obj.fields:
            raise Unreadable(f"its constructor can't be followed to the end ({obj.fields['__partial']})")
        for d in HORIZONTAL:
            state = (default if isinstance(default, State) else State()).set("facing", Dir(d))
            results = machine.call(obj.cls, "getShape", _GET_SHAPE_DESC, [obj, state, UNKNOWN, UNKNOWN, UNKNOWN])
            if not results or any(not isinstance(x, Shape) for x in results):
                raise Unreadable(f"the shape at facing={d} is not built from boxes it can read")
            if len({x for x in results}) != 1:
                raise Unreadable(f"the shape at facing={d} depends on more than the facing")
            shapes[d] = results[0].boxes
    except Unreadable as exc:
        r.shape_why = f"{where}: {exc}"
    else:
        r.shapes = shapes
        r.shape_from = where
    # Collision: the vanilla getCollisionShape (hasCollision ? getShape :
    # empty) unless the mod overrides it.
    collision_desc = _GET_SHAPE_DESC
    own = machine.find_method(obj.cls, "getCollisionShape", collision_desc)
    if own is not None:
        r.collision_why = (f"{own[0].name.replace('/', '.')}#getCollisionShape overrides the "
                           "collision shape")
        return
    props = obj.fields.get("__props", UNKNOWN)
    if _shared_changed(props):
        r.collision_why = _SHARED_WHY
        return
    if not isinstance(props, Props) or props.has_collision is UNKNOWN:
        r.collision_why = ("its Properties copy a vanilla block's or aren't read, so whether "
                           "it collides isn't known")
        return
    r.collision = bool(props.has_collision)


# --- Light ------------------------------------------------------------------
#
# Java gives every block state a light level when the state is built:
# ``BlockStateBase.lightEmission = properties.lightEmission.applyAsInt(this)``
# (BlockBehaviour$BlockStateBase#<init> L808-834, MC 1.21.1 client jar +
# Mojang mappings; the states are built in the Block constructor),
# the function being whatever ``Properties.lightLevel`` was last given
# (``state -> 0`` when nothing was; ``ofFullCopy``/``ofLegacyCopy`` copy the
# copied block's). NeoForge also lets a block override
# ``IBlockExtension#getLightEmission(state, level, pos)``, which can depend on
# the world, so such a block's light is not read.

_PLACEMENT_LIGHT = "getStateForPlacement"


@dataclass
class LightReading:
    """One block's light as its code gives it.

    ``value`` is the light level (0-15) or None with ``why``. ``kind`` says how
    it was read: ``dark`` (the Properties never set a light), ``constant`` (the
    function gives one value for every state) or ``placed`` (the value at the
    state the block is placed in, when the function reads only states the
    converted block doesn't carry; ``states`` names them). ``source`` cites
    where it was read (class#method of the function, or the vanilla default).
    ``copied`` names the vanilla block whose Properties were copied when that
    is why it is unread.
    """

    name: str
    cls: str | None = None
    value: int | None = None
    kind: str = ""
    source: str = ""
    states: tuple = ()
    why: str = ""
    copied: str = ""


def _lambda_name(fn) -> str:
    if isinstance(fn, Lam):
        return f"{fn.handle.ref.owner.replace('/', '.')}#{fn.handle.ref.name}"
    return f"{fn.cls.replace('/', '.')}#applyAsInt"


def _apply_light(machine: Machine, fn, state) -> list:
    if isinstance(fn, Lam):
        return machine.call_lambda(fn, [state])
    return machine.call(fn.cls, "applyAsInt", "(Ljava/lang/Object;)I", [fn, state])


def _light_values(results: list) -> set | None:
    if not results or any(not isinstance(v, int) or isinstance(v, bool) for v in results):
        return None
    return set(results)


def read_light(classes: ClassIndex | None, names: list[str],
               drawn: dict[str, set] | None = None) -> dict[str, LightReading]:
    """A :class:`LightReading` per blockstate name in ``names``. ``drawn`` maps
    a name to the Java state names its converted Bedrock block carries (the
    ones its blockstate draws); a light that depends on one of those isn't
    read, since one value can't stand for every permutation."""
    readings = {n: LightReading(n) for n in names}
    if classes is None or not len(classes):
        for r in readings.values():
            r.why = "the mod ships no class files"
        return readings
    machine, registered = _registered(classes, names)
    for name, r in readings.items():
        objs, why = registered[name]
        if not objs:
            r.why = why
            continue
        values = []
        for obj in objs:
            one = LightReading(name)
            _read_light(machine, obj, one, (drawn or {}).get(name, set()))
            values.append(one)
        first = values[0]
        if any((v.value, v.why) != (first.value, first.why) for v in values[1:]):
            r.cls = first.cls
            r.why = "registered twice with different light"
            continue
        readings[name] = first
    return readings


def _read_light(machine: Machine, obj: Obj, r: LightReading, drawn: set) -> None:
    r.cls = obj.cls.replace("/", ".")
    for cname in machine.chain(obj.cls):
        cf = machine.classes.get(cname)
        if cf is None:
            break
        if any(m.name == "getLightEmission" and m.code is not None for m in cf.methods):
            r.why = (f"{cname.replace('/', '.')}#getLightEmission overrides the light "
                     "(it can depend on the world, not only the state)")
            return
    props = obj.fields.get("__props", UNKNOWN)
    if not isinstance(props, Props):
        r.why = "the Properties its constructor passes on aren't read"
        return
    if _shared_changed(props):
        r.why = _SHARED_WHY
        return
    light = props.light
    if light is DARK:
        r.value, r.kind = 0, "dark"
        r.source = "BlockBehaviour$Properties default (state -> 0)"
        return
    if isinstance(light, CopiedLight):
        r.copied = light.source
        r.why = (f"its Properties copy {light.source}'s, and the repo has no cited table of "
                 "vanilla light levels")
        return
    if light is UNKNOWN:
        r.why = "Properties.lightLevel is given a function it can't read (or a renamed setting)"
        return
    src = _lambda_name(light)
    machine.steps = 0
    machine.state_reads = set()
    try:
        any_state = _light_values(_apply_light(machine, light, State()))
    except Unreadable as exc:
        r.why = f"{src}: {exc}"
        return
    finally:
        reads, machine.state_reads = machine.state_reads, None
    if any_state is not None and len(any_state) == 1:
        r.value, r.kind, r.source = any_state.pop(), "constant", src
    elif "?" in reads or not reads:
        r.why = f"{src}: the light is not built from values it can read"
        return
    elif reads & drawn:
        r.why = (f"{src}: the light depends on {', '.join(sorted(reads & drawn))}, a state the "
                 "converted block carries, and one light per permutation isn't read")
        return
    else:
        # Bedrock doesn't carry these states, so the block keeps the state
        # it was placed in: its light is the function's value there.
        machine.steps = 0
        try:
            # A path returning null is one where Java doesn't place the block.
            placed = [s for s in machine.call(obj.cls, _PLACEMENT_LIGHT, _PLACEMENT_DESC, [obj, PLACE_CTX])
                      if s is not None]
            if not placed or any(not isinstance(s, State) for s in placed):
                raise Unreadable("the placed state isn't read")
            got = set()
            for s in placed:
                vals = _light_values(_apply_light(machine, light, s))
                if vals is None:
                    raise Unreadable("the light at the placed state isn't read")
                got |= vals
        except Unreadable as exc:
            r.why = (f"{src}: the light depends on {', '.join(sorted(reads))} and "
                     f"{_declaring(machine, obj.cls, _PLACEMENT_LIGHT, _PLACEMENT_DESC)}: {exc}")
            return
        if len(got) != 1:
            r.why = (f"{src}: the light at the placed state differs between paths "
                     f"({', '.join(str(v) for v in sorted(got))})")
            return
        r.value, r.kind, r.source = got.pop(), "placed", src
        r.states = tuple(sorted(reads))
    if not 0 <= r.value <= 15:
        r.why = f"{src}: Java gives {r.value}, outside Bedrock's 0-15"
        r.value, r.kind, r.source, r.states = None, "", "", ()


# --- Facing plus boolean states ---------------------------------------------
#
# A block whose blockstate draws ``facing`` and one or more boolean states
# (lit, open, powered...) carries those booleans on Bedrock as custom states.
# Per boolean the code gives (each read, or the reason it wasn't):
#
# * the value a placed block starts with: the one getStateForPlacement puts
#   in the state it returns (``placed``); when that depends on the world (a
#   redstone signal, the fluid there), the registered default state's
#   (``registered``, Block#registerDefaultState in the constructor); a boolean
#   the code never sets takes StateDefinition#any's, the first state, whose
#   booleans are true (``any``: StateDefinition#any L92, BooleanProperty
#   values ImmutableSet.of(true, false) in BooleanProperty#<init> L12-14, MC
#   1.21.1 client jar + Mojang mappings);
# * whether using the block flips it: useWithoutItem (``use`` before 1.20.5)
#   run on the server at every state, where every way through it puts the
#   same state back with that one boolean flipped (Level#setBlock in the
#   method itself, ``state.cycle(P)`` or ``state.setValue(P, !state.getValue(P))``);
# * the methods of the block's own classes that set it otherwise (and
#   whether they read redstone), for the notes;
# * the shape at every (facing, booleans) and the light at every booleans.

_USE_DESCS = (
    ("useWithoutItem", "(Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/world/level/Level;"
                       "Lnet/minecraft/core/BlockPos;Lnet/minecraft/world/entity/player/Player;"
                       "Lnet/minecraft/world/phys/BlockHitResult;)Lnet/minecraft/world/InteractionResult;"),
    ("use", "(Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/world/level/Level;"
            "Lnet/minecraft/core/BlockPos;Lnet/minecraft/world/entity/player/Player;"
            "Lnet/minecraft/world/InteractionHand;Lnet/minecraft/world/phys/BlockHitResult;)"
            "Lnet/minecraft/world/InteractionResult;"),
)
_USE_ITEM_ON = "useItemOn"
_REDSTONE_READS = ("hasNeighborSignal", "getBestNeighborSignal", "getDirectSignal", "getSignal",
                   "hasSignal", "getDirectSignalTo")
_STATE_CHANGES = ("setValue", "cycle")
# The drawn states placement sets (horizontal facing, 6-way facing, attach
# face): a toggle must leave them as they are.
_PLACED_KEYS = ("facing", "facing6", "face")


@dataclass
class StateReading(Reading):
    """A :class:`Reading` for a block with facing and boolean states.

    ``bools`` names the booleans (sorted); a combination is a tuple of 0/1 in
    that order. ``shapes_by`` maps (facing, combination) to Java's boxes, or is
    None with ``shape_why``. ``defaults`` maps each boolean to (value, kind,
    source): kind ``placed``, ``registered`` or ``any`` (read, ``source``
    cites it) or ``DEFAULT`` (not read, ``source`` says why; the value is
    false). ``toggle`` names the boolean using the block flips (read from
    ``toggle_from``), or is None with ``toggle_why``. ``changed_by`` maps a
    boolean to the methods of the block's classes that set it (``+redstone``
    when the method reads a redstone signal). ``light_by`` maps each
    combination to its light, or is None with ``light_why``; ``light_kind`` is
    dark/constant/per_state and ``light_source`` cites it.
    """

    bools: tuple = ()
    # Set (and nothing else read) when the block class reaches a vanilla
    # block class other than the plain ones (_PLAIN_VANILLA).
    vanilla_parent: str = ""
    shapes_by: dict | None = None
    defaults: dict = field(default_factory=dict)
    toggle: str | None = None
    toggle_from: str = ""
    toggle_why: str = ""
    changed_by: dict = field(default_factory=dict)
    light_by: dict | None = None
    light_kind: str = ""
    light_source: str = ""
    light_why: str = ""
    light_copied: str = ""


def combinations(bools: tuple) -> list[tuple]:
    """Every (0/1, ...) combination of ``bools``, all-false first."""
    out = [()]
    for _ in bools:
        out = [c + (v,) for c in out for v in (0, 1)]
    return out


def _with(state, bools: tuple, combo: tuple) -> "State":
    base = state if isinstance(state, State) else State()
    for prop, v in zip(bools, combo):
        base = base.set(prop, v)
    return base


def read_state_blocks(classes: ClassIndex | None, bools: dict[str, tuple]) -> dict[str, StateReading]:
    """A :class:`StateReading` per blockstate name in ``bools`` (name ->
    the boolean state names its blockstate draws)."""
    names = list(bools)
    readings = {n: StateReading(n, bools=tuple(sorted(bools[n]))) for n in names}
    if classes is None or not len(classes):
        for r in readings.values():
            r.placement_why = r.shape_why = r.collision_why = r.toggle_why = r.light_why = \
                "the mod ships no class files"
        return readings
    machine, registered = _registered(classes, names)
    for name, r in readings.items():
        objs, why = registered[name]
        if not objs:
            r.placement_why = r.shape_why = r.collision_why = r.toggle_why = r.light_why = why
            continue
        obj = objs[0]
        r.cls = obj.cls.replace("/", ".")
        base = machine.vanilla_base(obj.cls)
        if base not in _PLAIN_VANILLA:
            # A vanilla block class with behaviour of its own (FenceGateBlock,
            # LanternBlock...) places, shapes and changes its states in code
            # the jar doesn't hold, which isn't read.
            r.vanilla_parent = base.replace("/", ".")
            continue
        _read_states(machine, obj, r)
        r.behaviour = _behaviour(machine, obj.cls)
        _read_placement(machine, obj, r)
        placed = _placed_states(machine, obj)
        _read_defaults(machine, obj, r, placed)
        _read_state_shapes(machine, obj, r)
        _read_shape_collision(machine, obj, r)
        _read_toggle(machine, obj, r)
        r.changed_by = _changed_by(machine, obj.cls, r.bools)
        _read_state_light(machine, obj, r, placed)
        if len(objs) > 1:
            other = StateReading(name, bools=r.bools)
            _read_placement(machine, objs[1], other)
            _read_defaults(machine, objs[1], other, _placed_states(machine, objs[1]))
            _read_state_shapes(machine, objs[1], other)
            _read_shape_collision(machine, objs[1], other)
            if (other.placement, other.shapes_by, other.collision, other.defaults) != \
                    (r.placement, r.shapes_by, r.collision, r.defaults):
                r.placement, r.shapes_by, r.collision = None, None, None
                r.placement_why = r.shape_why = r.collision_why = "registered twice with different settings"
                r.defaults = {}
    return readings


def _placed_states(machine: Machine, obj: Obj) -> list | None:
    """The states getStateForPlacement returns (paths returning null, where
    Java doesn't place the block, left out), or None if unread."""
    machine.steps = 0
    try:
        results = machine.call(obj.cls, "getStateForPlacement", _PLACEMENT_DESC, [obj, PLACE_CTX])
    except Unreadable:
        return None
    placed = [s for s in results if s is not None]
    if not placed or any(not isinstance(s, State) for s in placed):
        return None
    return placed


def _bool_value(state: State, prop: str):
    """0/1 for ``prop`` in ``state``, the StateDefinition#any value (1) for
    one the code never set on a state built from it, else UNKNOWN."""
    values = dict(state.values)
    v = values.get(prop, UNKNOWN)
    if prop not in values and _ANY in values and not any(str(k).startswith("?") for k in values):
        # (A property set under a name that wasn't read could be this one.)
        return 1
    return v if v in (0, 1) and not isinstance(v, bool) else UNKNOWN


def _read_defaults(machine: Machine, obj: Obj, r: StateReading, placed: list | None,
                   where: str | None = None) -> None:
    if where is None:
        where = _declaring(machine, obj.cls, "getStateForPlacement", _PLACEMENT_DESC)
    default = obj.fields.get("__default")
    ctor = f"{r.cls}#<init> (registerDefaultState)"
    for prop in r.bools:
        why = ""
        if placed is None:
            why = f"{where} isn't read"
        else:
            values = {_bool_value(s, prop) for s in placed}
            set_here = any(prop in dict(s.values) for s in placed)
            if len(values) == 1 and UNKNOWN not in values:
                value = values.pop()
                kind = "placed" if set_here else "any"
                src = where if set_here else (f"{where} leaves it at StateDefinition#any's value "
                                              "(BooleanProperty's first value, true)")
                r.defaults[prop] = (bool(value), kind, src)
                continue
            why = f"{where} sets it from the world" if UNKNOWN in values else f"{where} differs between paths"
        if isinstance(default, State) and _bool_value(default, prop) is not UNKNOWN:
            value = _bool_value(default, prop)
            if prop in dict(default.values):
                r.defaults[prop] = (bool(value), "registered", f"{ctor}; {why}")
            else:
                r.defaults[prop] = (bool(value), "any", f"{ctor} from StateDefinition#any (BooleanProperty's "
                                                      f"first value, true); {why}")
            continue
        r.defaults[prop] = (False, "DEFAULT", why or "the default state isn't read")


def _read_state_shapes(machine: Machine, obj: Obj, r: StateReading) -> None:
    machine.steps = 0
    where = _declaring(machine, obj.cls, "getShape", _GET_SHAPE_DESC)
    default = obj.fields.get("__default", State())
    shapes = {}
    try:
        if "__partial" in obj.fields:
            raise Unreadable(f"its constructor can't be followed to the end ({obj.fields['__partial']})")
        for combo in combinations(r.bools):
            for d in HORIZONTAL:
                state = _with(default, r.bools, combo).set("facing", Dir(d))
                results = machine.call(obj.cls, "getShape", _GET_SHAPE_DESC, [obj, state, UNKNOWN, UNKNOWN, UNKNOWN])
                if not results or any(not isinstance(x, Shape) for x in results):
                    raise Unreadable(f"the shape at facing={d} is not built from boxes it can read")
                if len({x for x in results}) != 1:
                    raise Unreadable(f"the shape at facing={d} depends on more than the drawn states")
                shapes[(d, combo)] = results[0].boxes
    except Unreadable as exc:
        r.shape_why = f"{where}: {exc}"
    else:
        r.shapes_by = shapes
        r.shape_from = where


def _read_shape_collision(machine: Machine, obj: Obj, r: Reading) -> None:
    """Collision as _read_shape reads it (Properties#noCollission, or a
    getCollisionShape override), without reading the facing-only shapes."""
    own = machine.find_method(obj.cls, "getCollisionShape", _GET_SHAPE_DESC)
    if own is not None:
        r.collision_why = f"{own[0].name.replace('/', '.')}#getCollisionShape overrides the collision shape"
        return
    props = obj.fields.get("__props", UNKNOWN)
    if _shared_changed(props):
        r.collision_why = _SHARED_WHY
        return
    if not isinstance(props, Props) or props.has_collision is UNKNOWN:
        r.collision_why = ("its Properties copy a vanilla block's or aren't read, so whether "
                           "it collides isn't known")
        return
    r.collision = bool(props.has_collision)


def _read_toggle(machine: Machine, obj: Obj, r: StateReading, cells: list | None = None) -> None:
    """``cells`` are the drawn states other than the booleans (each a
    function from the default state to that state), every horizontal facing
    when None."""
    found = None
    for name, desc in _USE_DESCS:
        found = machine.find_method(obj.cls, name, desc) if machine.is_mod(obj.cls) else None
        if found is not None:
            break
    if found is None:
        r.toggle_why = "the block's classes don't override useWithoutItem, so using it changes nothing"
        return
    cf, m = found
    where = f"{cf.name.replace('/', '.')}#{m.name}"
    own_item = None
    for cname in machine.chain(obj.cls):
        c = machine.classes.get(cname)
        if c is None:
            break
        if any(x.name == _USE_ITEM_ON and x.code is not None for x in c.methods):
            own_item = cname
            break
    default = obj.fields.get("__default", State())
    level = Obj(_LEVEL, {"isClientSide": 0})
    pos = Obj("__pos")
    flipped = set()
    if cells is None:
        cells = [lambda s, d=d: s.set("facing", Dir(d)) for d in HORIZONTAL]
    try:
        for combo in combinations(r.bools):
            for cell in cells:
                state = cell(_with(default, r.bools, combo))
                args = [obj, state, level, pos, UNKNOWN, UNKNOWN]
                if m.name == "use":
                    args.append(UNKNOWN)
                machine.steps = 0
                machine.effects, machine.deep_effect = [], False
                machine.effects_depth = machine.depth + 1
                try:
                    machine.run(cf, m, args)
                    paths = machine.effects
                finally:
                    machine.effects = None
                if machine.deep_effect:
                    raise Unreadable("a method it calls changes the block")
                if not paths:
                    raise Unreadable("no way through it returns")
                for _ret, effects in paths:
                    if not effects:
                        raise Unreadable("some ways through it leave the block as it is")
                    if len(effects) != 1:
                        raise Unreadable("it sets the block more than once")
                    at, new = effects[0]
                    if at is not pos or not isinstance(new, State):
                        raise Unreadable("it sets another block, or a state it can't read")
                    changed = {k for k in (*r.bools, *_PLACED_KEYS) if new.get(k) != state.get(k)}
                    if len(changed) != 1 or changed <= set(_PLACED_KEYS):
                        raise Unreadable("it doesn't flip exactly one drawn boolean")
                    prop = changed.pop()
                    if new.get(prop) != 1 - state.get(prop):
                        raise Unreadable(f"it doesn't flip {prop}")
                    flipped.add(prop)
    except Unreadable as exc:
        r.toggle_why = f"{where}: {exc}"
        return
    if len(flipped) != 1:
        r.toggle_why = f"{where}: it flips different booleans at different states"
        return
    if own_item is not None:
        r.toggle_why = (f"{where} flips {next(iter(flipped))}, but {own_item.replace('/', '.')}#useItemOn "
                        "decides what using it with an item does first, which isn't carried")
        return
    r.toggle = flipped.pop()
    r.toggle_from = where


def _changed_by(machine: Machine, cls: str, bools: tuple) -> dict:
    """Per boolean: the methods of the block's own classes that load its
    property and change a state (setValue/cycle), with ``+redstone`` when the
    method also reads a redstone signal. A scan, not a run: it says where the
    code changes the boolean, not when."""
    out: dict[str, list] = {}
    for cname in machine.chain(cls):
        cf = machine.classes.get(cname)
        if cf is None:
            break
        for m in cf.methods:
            if m.code is None or m.name in ("<init>", "<clinit>", "getStateForPlacement"):
                continue
            try:
                code = instructions(cf, m.code)
            except Exception:  # noqa: BLE001 - a scan; unreadable code just isn't listed
                continue
            props, changes, redstone = set(), False, False
            for insn in code:
                if insn.op == 0xB2 and isinstance(insn.arg, Ref):
                    try:
                        v = machine.get_static(insn.arg)
                    except Exception:  # noqa: BLE001 - a scan; a field that can't be had isn't listed
                        continue
                    if isinstance(v, Prop) and v.name in bools:
                        props.add(v.name)
                elif insn.op in (0xB6, 0xB7, 0xB8, 0xB9) and isinstance(insn.arg, Ref):
                    if insn.arg.name in _STATE_CHANGES:
                        changes = True
                    elif insn.arg.name in _REDSTONE_READS:
                        redstone = True
            if changes:
                for p in props:
                    label = m.name + ("+redstone" if redstone else "")
                    if label not in out.setdefault(p, []):
                        out[p].append(label)
    return out


def _read_state_light(machine: Machine, obj: Obj, r: StateReading, placed: list | None,
                      unknown: tuple = ("facing",)) -> None:
    """The light per boolean combination: Properties.lightLevel run on the
    state with those booleans (other states at their placed value, which
    Bedrock keeps since it doesn't carry them). The same refusals as
    _read_light: a getLightEmission override, Properties copied from vanilla,
    shared or unread, a value outside 0-15."""
    for cname in machine.chain(obj.cls):
        cf = machine.classes.get(cname)
        if cf is None:
            break
        if any(m.name == "getLightEmission" and m.code is not None for m in cf.methods):
            r.light_why = (f"{cname.replace('/', '.')}#getLightEmission overrides the light "
                           "(it can depend on the world, not only the state)")
            return
    props = obj.fields.get("__props", UNKNOWN)
    if not isinstance(props, Props):
        r.light_why = "the Properties its constructor passes on aren't read"
        return
    if _shared_changed(props):
        r.light_why = _SHARED_WHY
        return
    fn = props.light
    if fn is DARK:
        r.light_by = {c: 0 for c in combinations(r.bools)}
        r.light_kind, r.light_source = "dark", "BlockBehaviour$Properties default (state -> 0)"
        return
    if isinstance(fn, CopiedLight):
        r.light_copied = fn.source
        r.light_why = (f"its Properties copy {fn.source}'s, and the repo has no cited table of "
                       "vanilla light levels")
        return
    if fn is UNKNOWN:
        r.light_why = "Properties.lightLevel is given a function it can't read (or a renamed setting)"
        return
    src = _lambda_name(fn)
    base = placed[0] if placed and len(set(placed)) == 1 else obj.fields.get("__default", State())
    out = {}
    try:
        for combo in combinations(r.bools):
            machine.steps = 0
            machine.state_reads = set()
            try:
                state = _with(base, r.bools, combo)
                for key in unknown:
                    state = state.set(key, UNKNOWN)
                vals = _light_values(_apply_light(machine, fn, state))
            finally:
                reads, machine.state_reads = machine.state_reads, None
            if "?" in reads or vals is None or len(vals) != 1:
                raise Unreadable("the light is not built from values it can read")
            out[combo] = vals.pop()
    except Unreadable as exc:
        r.light_why = f"{src}: {exc}"
        return
    bad = [v for v in out.values() if not 0 <= v <= 15]
    if bad:
        r.light_why = f"{src}: Java gives {bad[0]}, outside Bedrock's 0-15"
        return
    r.light_by, r.light_source = out, src
    r.light_kind = "constant" if len(set(out.values())) == 1 else "per_state"


# --- Water ------------------------------------------------------------------
#
# Java's ``waterlogged`` (BlockStateProperties.WATERLOGGED) draws nothing: the
# water is the block state's fluid, rendered by the fluid renderer, and what
# makes a waterlogged state hold water is the block's ``getFluidState``. The
# vanilla one returns no fluid whatever the state (BlockBehaviour#getFluidState
# L248: ``Fluids.EMPTY.defaultFluidState()``); a waterloggable block overrides
# it to return ``Fluids.WATER.getSource(false)`` (FlowingFluid#getSource L251)
# when WATERLOGGED is true (MC 1.21.1 client jar + Mojang mappings
# client.txt). :func:`read_water` runs that method at waterlogged=true and
# waterlogged=false.

_FLUIDS = "net/minecraft/world/level/material/Fluids"
_FLUID_STATE_DESC = ("(Lnet/minecraft/world/level/block/state/BlockState;)"
                     "Lnet/minecraft/world/level/material/FluidState;")
_WATERLOGGED_IFACE = "net/minecraft/world/level/block/SimpleWaterloggedBlock"


@dataclass(frozen=True)
class FluidVal:
    """A FluidState the interpreter knows: ``water`` (a still water source)
    or ``empty``."""

    kind: str


WATER_SOURCE = FluidVal("water")
NO_FLUID = FluidVal("empty")


@dataclass
class WaterReading:
    """Whether one block holds water when waterlogged, as its code says.

    ``holds`` is True when getFluidState gives a water source at
    waterlogged=true (and not at false), False when the block never holds a
    fluid (getFluidState is vanilla BlockBehaviour's), or None with ``why``.
    ``source`` cites the method read. ``bucket`` says whether the block's
    classes implement SimpleWaterloggedBlock (a bucket can fill and empty
    it in Java), None if unread.
    """

    name: str
    cls: str | None = None
    holds: bool | None = None
    source: str = ""
    why: str = ""
    bucket: bool | None = None


def _implements(machine: Machine, cls: str, iface: str) -> bool | None:
    """Whether ``cls`` or a mod superclass lists ``iface`` (or a mod
    interface that extends it); None when the chain leaves the mod's classes
    at a vanilla class other than a plain one (which may implement it)."""
    todo = []
    for cname in machine.chain(cls):
        cf = machine.classes.get(cname)
        if cf is None:
            if cname not in _PLAIN_VANILLA:
                return None
            break
        todo += list(cf.interfaces)
    seen = set()
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        if name == iface:
            return True
        cf = machine.classes.get(name)
        if cf is not None:
            todo += list(cf.interfaces)
    return False


def read_water(classes: ClassIndex | None, names: list[str]) -> dict[str, WaterReading]:
    """A :class:`WaterReading` per blockstate name in ``names``."""
    readings = {n: WaterReading(n) for n in names}
    if classes is None or not len(classes):
        for r in readings.values():
            r.why = "the mod ships no class files"
        return readings
    machine, registered = _registered(classes, names)
    for name, r in readings.items():
        objs, why = registered[name]
        if not objs:
            r.why = why
            continue
        got = []
        for obj in objs:
            one = WaterReading(name)
            _read_water(machine, obj, one)
            got.append(one)
        first = got[0]
        if any((g.holds, g.why) != (first.holds, first.why) for g in got[1:]):
            r.cls, r.why = first.cls, "registered twice with different fluid code"
            continue
        readings[name] = first
    return readings


def _read_water(machine: Machine, obj: Obj, r: WaterReading) -> None:
    r.cls = obj.cls.replace("/", ".")
    r.bucket = _implements(machine, obj.cls, _WATERLOGGED_IFACE)
    found = machine.find_method(obj.cls, "getFluidState", _FLUID_STATE_DESC)
    base = machine.vanilla_base(obj.cls)
    if found is None:
        if base in _PLAIN_VANILLA:
            r.holds = False
            r.source = "net.minecraft.world.level.block.state.BlockBehaviour#getFluidState (vanilla, inherited)"
        else:
            r.why = (f"getFluidState is inherited from the vanilla {base.replace('/', '.')}, "
                     "whose code isn't read")
        return
    where = f"{found[0].name.replace('/', '.')}#getFluidState"
    default = obj.fields.get("__default", State())
    default = default if isinstance(default, State) else State()
    out = {}
    try:
        for v in (1, 0):
            machine.steps = 0
            results = machine.call(obj.cls, "getFluidState", _FLUID_STATE_DESC, [obj, default.set("waterlogged", v)])
            kinds = {x for x in results}
            if len(kinds) != 1 or not isinstance(next(iter(kinds)), FluidVal):
                raise Unreadable(f"the fluid at waterlogged={'true' if v else 'false'} is not one it can read")
            out[v] = kinds.pop()
    except Unreadable as exc:
        r.why = f"{where}: {exc}"
        return
    if out[1] == WATER_SOURCE and out[0] != WATER_SOURCE:
        r.holds, r.source = True, where
    elif out[1] == NO_FLUID and out[0] == NO_FLUID:
        r.holds, r.source = False, where
    else:
        r.why = (f"{where}: gives {out[1].kind} at waterlogged=true and {out[0].kind} at false, "
                 "which isn't water only when waterlogged")


# --- Six-way facing and attach-face blocks ------------------------------------
#
# A block whose blockstate draws ``facing`` with all six directions
# (DirectionalBlock / BlockStateProperties.FACING) or ``face`` (floor, wall,
# ceiling) with a horizontal ``facing`` (FaceAttachedHorizontalDirectionalBlock
# / ATTACH_FACE). Its placement rule is read by running getStateForPlacement
# once per face the player can click, with that face known
# (UseOnContext#getClickedFace) and the player's horizontal facing
# (getHorizontalDirection) and nearest looking direction
# (getNearestLookingDirection) as symbols. Each run must give one state; the
# rule is then, per clicked face, the ``face`` value and what ``facing`` is:
# a fixed direction, the player's horizontal facing turned by quarters, or the
# player's looking direction (or its opposite).
#
# canSurvive is not emulated (there is no world): wherever placement asks
# BlockState#canSurvive, the answer is true, as if the clicked face held the
# block up; Java would try the next looking direction or refuse to place. The
# reading says when it leaned on this (support_assumed).

DIRECTIONAL_KINDS = ("facing6", "attach", "vslab")
# Vertical slabs (#296): ``type`` = the horizontal side the slab stands
# against, or ``double``. The value is the mod's own enum (no vanilla class
# has this state set), whose serialized names the interpreter doesn't
# evaluate, so the rule and the boxes always fall back to the labelled
# DEFAULT below; the reading still names the class and its collision.
VSLAB_TYPES = ("north", "east", "south", "west", "double")


@dataclass
class DirReading(Reading):
    """A 6-way facing or attach-face block as its code gives it.

    ``rule`` maps each clicked face (DIRECTIONS) to (face, token): ``face``
    is the AttachFace value ("floor"/"wall"/"ceiling", "" for facing6) and
    ``token`` is ("dir", direction), ("player", quarters clockwise) or
    ("look", opposite); None with ``rule_why`` when unread.
    ``shapes_by`` maps each Java key (face, facing) to the shape boxes.
    """

    kind: str = ""
    rule: dict | None = None
    rule_from: str = ""
    rule_why: str = ""
    rule_conflict: str = ""
    support_assumed: bool = False
    shapes_by: dict | None = None


def directional_keys(kind: str) -> list[tuple[str, str]]:
    """The Java (face, facing) keys a kind of blockstate draws."""
    if kind == "facing6":
        return [("", d) for d in DIRECTIONS]
    if kind == "vslab":
        return [("", t) for t in VSLAB_TYPES]
    return [(f, d) for f in ("floor", "wall", "ceiling") for d in HORIZONTAL]


def default_rule(kind: str) -> dict:
    """The labelled DEFAULT placement rule: facing6 faces away from the
    clicked face (facing = the clicked face, as vanilla's rods and amethyst
    clusters do); attach-face follows vanilla
    FaceAttachedHorizontalDirectionalBlock#getStateForPlacement L39-52 with the
    clicked face holding the block up. A vertical slab (``vslab``) stands
    against the side face clicked (type = that face, as vanilla
    SlabBlock#getStateForPlacement puts a slab against the face it was placed
    on); a clicked top or bottom face, where Java code picks the half by the
    point clicked and Bedrock exposes no such point, gives type = the
    player's facing: the half nearest the player."""
    out = {}
    for c in DIRECTIONS:
        if kind == "vslab":
            out[c] = ("", ("player", 0)) if c in ("up", "down") else ("", ("dir", c))
        elif kind == "facing6":
            out[c] = ("", ("dir", c))
        elif c == "up":
            out[c] = ("floor", ("player", 0))
        elif c == "down":
            out[c] = ("ceiling", ("player", 0))
        else:
            out[c] = ("wall", ("dir", c))
    return out


def _token(value):
    if isinstance(value, Dir):
        return ("dir", value.name)
    if isinstance(value, PlayerDir):
        return ("player", value.quarters)
    if isinstance(value, LookDir):
        return ("look", value.opposite)
    return None


def _face_value(value):
    if isinstance(value, Const) and value.owner == _ATTACH_FACE and value.name in ("FLOOR", "WALL", "CEILING"):
        return value.name.lower()
    return None


def _with_key(state: State, kind: str, key: tuple) -> State:
    face, facing = key
    state = state.set("facing", Dir(facing))
    if kind == "facing6":
        return state.set("facing6", Dir(facing))
    return state.set("face", Const(_ATTACH_FACE, face.upper()))


def read_directional(classes: ClassIndex | None, kinds: dict[str, str]) -> dict[str, DirReading]:
    """A :class:`DirReading` per blockstate name in ``kinds`` (name -> kind)."""
    readings = {n: DirReading(n, kind=k) for n, k in kinds.items()}
    if classes is None or not len(classes):
        for r in readings.values():
            r.rule_why = r.shape_why = r.collision_why = "the mod ships no class files"
        return readings
    machine, registered = _registered(classes, list(kinds))
    for name, r in readings.items():
        objs, why = registered[name]
        if not objs:
            r.rule_why = r.shape_why = r.collision_why = why
            continue
        obj = objs[0]
        r.cls = obj.cls.replace("/", ".")
        _read_states(machine, obj, r)
        r.behaviour = _behaviour(machine, obj.cls)
        if r.kind == "vslab":
            r.rule_why = r.shape_why = (
                f"{r.cls}: type is the mod's own enum, whose serialized names the reader doesn't evaluate")
            _read_shape_collision(machine, obj, r)
            continue
        _read_rule(machine, obj, r)
        _read_dir_shapes(machine, obj, r)
        _read_shape_collision(machine, obj, r)
        if len(objs) > 1:
            other = DirReading(name, kind=r.kind)
            _read_rule(machine, objs[1], other)
            _read_dir_shapes(machine, objs[1], other)
            if (other.rule, other.shapes_by) != (r.rule, r.shapes_by):
                r.rule, r.shapes_by = None, None
                r.rule_why = r.shape_why = "registered twice with different settings"
    return readings


def _read_rule(machine: Machine, obj: Obj, r: DirReading) -> None:
    where = _declaring(machine, obj.cls, "getStateForPlacement", _PLACEMENT_DESC)
    if machine.vanilla_base(obj.cls) in _FACE_ATTACHED_KIN and not machine.find_method(
            obj.cls, "getStateForPlacement", _PLACEMENT_DESC):
        where = f"{_FACE_ATTACHED.replace('/', '.')}#getStateForPlacement L39-52 (vanilla, inherited)"
    rule = {}
    machine.assume_support, machine.support_assumed = True, False
    try:
        for c in DIRECTIONS:
            machine.steps = 0
            results = machine.call(obj.cls, "getStateForPlacement", _PLACEMENT_DESC, [obj, _Ctx(c)])
            outs = set()
            for res in results:
                if not isinstance(res, State):
                    outs.add(None)
                    continue
                values = dict(res.values)
                if "facing6" in values or "facing" in values:
                    facing = res.get("facing6") if "facing6" in values else res.get("facing")
                else:
                    r.rule_conflict = (f"{where}: the player doesn't set facing (the block keeps its "
                                       "default facing), which Bedrock's placement traits can't give")
                    raise Unreadable(r.rule_conflict)
                if r.kind == "attach" and "face" not in values:
                    r.rule_conflict = (f"{where}: the player doesn't set face (the block keeps its "
                                       "default face), which Bedrock's placement traits can't give")
                    raise Unreadable(r.rule_conflict)
                face = "" if r.kind == "facing6" else _face_value(res.get("face"))
                token = _token(facing)
                if face is None or token is None:
                    outs.add(None)
                    continue
                if r.kind == "attach" and (token[0] == "look" or (token[0] == "dir" and token[1] in ("up", "down"))):
                    r.rule_conflict = (f"{where}: facing is set from a direction that can be vertical, which "
                                       "a horizontal facing can't hold")
                    raise Unreadable(r.rule_conflict)
                outs.add((face, token))
            if len(outs) != 1 or None in outs:
                raise Unreadable(f"clicking the {c} face, the placed state isn't one the reader can follow "
                                 "(paths disagree, or face/facing aren't set from the clicked face or the player)")
            rule[c] = outs.pop()
    except Unreadable as exc:
        if not r.rule_conflict:
            r.rule_why = f"{where}: {exc}"
        else:
            r.rule_why = r.rule_conflict
        return
    finally:
        machine.assume_support = False
    r.rule = rule
    r.rule_from = where
    r.support_assumed = machine.support_assumed


def _read_dir_shapes(machine: Machine, obj: Obj, r: DirReading) -> None:
    machine.steps = 0
    where = _declaring(machine, obj.cls, "getShape", _GET_SHAPE_DESC)
    default = obj.fields.get("__default", State())
    shapes = {}
    try:
        if "__partial" in obj.fields:
            raise Unreadable(f"its constructor can't be followed to the end ({obj.fields['__partial']})")
        for key in directional_keys(r.kind):
            state = _with_key(default if isinstance(default, State) else State(), r.kind, key)
            results = machine.call(obj.cls, "getShape", _GET_SHAPE_DESC, [obj, state, UNKNOWN, UNKNOWN, UNKNOWN])
            label = f"face={key[0]},facing={key[1]}" if key[0] else f"facing={key[1]}"
            if not results or any(not isinstance(x, Shape) for x in results):
                raise Unreadable(f"the shape at {label} is not built from boxes it can read")
            if len({x for x in results}) != 1:
                raise Unreadable(f"the shape at {label} depends on more than the drawn states")
            shapes[key] = results[0].boxes
    except Unreadable as exc:
        r.shape_why = f"{where}: {exc}"
    else:
        r.shapes_by = shapes
        r.shape_from = where


# --- Six-way facing / attach-face blocks with booleans ------------------------
#
# A blockstate drawing 6-way ``facing`` or ``face`` + ``facing`` together with
# one to four boolean states is read as both readers read their halves: the
# placement rule per clicked face as read_directional (the same rule, the
# same DEFAULT and the same conflicts), and each boolean's start value, box,
# use toggle and light as read_state_blocks, run at every (face, facing,
# booleans) the blockstate draws. A boolean's start is what placement gives on
# every path of all six clicked-face runs (else the registered default state,
# else DEFAULT false), so a start that depends on the clicked face falls back
# like one that reads the world. FaceAttachedHorizontalDirectionalBlock counts
# as plain here (its placement is supplied, see Machine; it changes no
# boolean); ButtonBlock and LeverBlock flip ``powered`` in vanilla code
# (useWithoutItem, tick) the jar doesn't hold, so a block reaching them is a
# vanilla parent, as FenceGateBlock is for read_state_blocks.

_DIR_STATE_PLAIN = _PLAIN_VANILLA | {_FACE_ATTACHED}


@dataclass
class DirStateReading(DirReading):
    """A :class:`DirReading` with booleans. ``shapes_by`` maps (key,
    combination) to Java's boxes; the boolean fields are
    :class:`StateReading`'s."""

    bools: tuple = ()
    vanilla_parent: str = ""
    defaults: dict = field(default_factory=dict)
    toggle: str | None = None
    toggle_from: str = ""
    toggle_why: str = ""
    changed_by: dict = field(default_factory=dict)
    light_by: dict | None = None
    light_kind: str = ""
    light_source: str = ""
    light_why: str = ""
    light_copied: str = ""


def _dir_placed_states(machine: Machine, obj: Obj) -> list | None:
    """Every state getStateForPlacement returns over the six clicked faces
    (support assumed, as _read_rule), or None if unread."""
    placed = []
    machine.assume_support = True
    try:
        for c in DIRECTIONS:
            machine.steps = 0
            try:
                results = machine.call(obj.cls, "getStateForPlacement", _PLACEMENT_DESC, [obj, _Ctx(c)])
            except Unreadable:
                return None
            got = [s for s in results if s is not None]
            if not got or any(not isinstance(s, State) for s in got):
                return None
            placed += got
    finally:
        machine.assume_support = False
    return placed


def _dir_cell(kind: str, key: tuple):
    return lambda s: _with_key(s, kind, key)


def read_directional_states(classes: ClassIndex | None,
                            specs: dict[str, tuple[str, tuple]]) -> dict[str, DirStateReading]:
    """A :class:`DirStateReading` per blockstate name in ``specs`` (name ->
    (kind, the boolean state names its blockstate draws))."""
    readings = {n: DirStateReading(n, kind=k, bools=tuple(sorted(b))) for n, (k, b) in specs.items()}
    if classes is None or not len(classes):
        for r in readings.values():
            r.rule_why = r.shape_why = r.collision_why = r.toggle_why = r.light_why = \
                "the mod ships no class files"
        return readings
    machine, registered = _registered(classes, list(specs))
    for name, r in readings.items():
        objs, why = registered[name]
        if not objs:
            r.rule_why = r.shape_why = r.collision_why = r.toggle_why = r.light_why = why
            continue
        obj = objs[0]
        r.cls = obj.cls.replace("/", ".")
        base = machine.vanilla_base(obj.cls)
        if base not in _DIR_STATE_PLAIN:
            r.vanilla_parent = base.replace("/", ".")
            continue
        _read_states(machine, obj, r)
        r.behaviour = _behaviour(machine, obj.cls)
        _read_rule(machine, obj, r)
        placed = _dir_placed_states(machine, obj)
        where = r.rule_from or _declaring(machine, obj.cls, "getStateForPlacement", _PLACEMENT_DESC)
        _read_defaults(machine, obj, r, placed, where)
        _read_dir_state_shapes(machine, obj, r)
        _read_shape_collision(machine, obj, r)
        cells = [_dir_cell(r.kind, key) for key in directional_keys(r.kind)]
        _read_toggle(machine, obj, r, cells)
        r.changed_by = _changed_by(machine, obj.cls, r.bools)
        _read_state_light(machine, obj, r, placed, unknown=_PLACED_KEYS)
        if len(objs) > 1:
            other = DirStateReading(name, kind=r.kind, bools=r.bools)
            _read_rule(machine, objs[1], other)
            _read_defaults(machine, objs[1], other, _dir_placed_states(machine, objs[1]), where)
            _read_dir_state_shapes(machine, objs[1], other)
            _read_shape_collision(machine, objs[1], other)
            if (other.rule, other.shapes_by, other.collision, other.defaults) != \
                    (r.rule, r.shapes_by, r.collision, r.defaults):
                r.rule, r.shapes_by, r.collision = None, None, None
                r.rule_why = r.shape_why = r.collision_why = "registered twice with different settings"
                r.defaults = {}
    return readings


def _read_dir_state_shapes(machine: Machine, obj: Obj, r: DirStateReading) -> None:
    machine.steps = 0
    where = _declaring(machine, obj.cls, "getShape", _GET_SHAPE_DESC)
    default = obj.fields.get("__default", State())
    default = default if isinstance(default, State) else State()
    shapes = {}
    try:
        if "__partial" in obj.fields:
            raise Unreadable(f"its constructor can't be followed to the end ({obj.fields['__partial']})")
        for combo in combinations(r.bools):
            for key in directional_keys(r.kind):
                state = _with_key(_with(default, r.bools, combo), r.kind, key)
                results = machine.call(obj.cls, "getShape", _GET_SHAPE_DESC, [obj, state, UNKNOWN, UNKNOWN, UNKNOWN])
                label = (f"face={key[0]},facing={key[1]}" if key[0] else f"facing={key[1]}") + "".join(
                    f",{p}={'true' if v else 'false'}" for p, v in zip(r.bools, combo))
                if not results or any(not isinstance(x, Shape) for x in results):
                    raise Unreadable(f"the shape at {label} is not built from boxes it can read")
                if len({x for x in results}) != 1:
                    raise Unreadable(f"the shape at {label} depends on more than the drawn states")
                shapes[(key, combo)] = results[0].boxes
    except Unreadable as exc:
        r.shape_why = f"{where}: {exc}"
    else:
        r.shapes_by = shapes
        r.shape_from = where


# --- Containers (#179) -------------------------------------------------------
#
# A Java block that keeps items and opens a menu for them: newBlockEntity
# builds a block entity that is a vanilla Container (it reaches
# BaseContainerBlockEntity), getContainerSize says how many slots it has, and
# the block's use method hands it to Player#openMenu. Each of the three is
# read from the jar; a block missing any of them is not a container here.

_NEW_BE_DESC = ("(Lnet/minecraft/core/BlockPos;Lnet/minecraft/world/level/block/state/BlockState;)"
                "Lnet/minecraft/world/level/block/entity/BlockEntity;")
_BE_PACKAGE = "net/minecraft/world/level/block/entity/"
# Vanilla block entities whose only behaviour is holding items behind a menu
# (MC 1.21.1, Mojang names): BaseContainerBlockEntity (abstract; Container,
# MenuProvider, Nameable) and RandomizableContainerBlockEntity (adds a loot
# table). Chests, barrels, furnaces, hoppers and the rest add behaviour of
# their own (lids, ticking, smelting, moving items), so a mod block entity
# built on one of them is not read as plain storage.
_PLAIN_CONTAINERS = {
    _BE_PACKAGE + "BaseContainerBlockEntity",
    _BE_PACKAGE + "RandomizableContainerBlockEntity",
}
# Bedrock's custom-block container holds 1 to 54 slots
# (minecraft:block_entity container.slot_count, bedrock-schemas 1.26.50
# block_container.schema.json: minimum 1, maximum 54).
MAX_SLOTS = 54
# The block methods a player's use goes through (MC 1.21.1 BlockBehaviour:
# useWithoutItem, useItemOn; before 1.20.5: use).
_USE_METHODS = ("useWithoutItem", "useItemOn", "use")
# What opens a menu: Player#openMenu(MenuProvider) (vanilla; NeoForge adds an
# overload with a buffer writer), Forge's NetworkHooks.openScreen.
_OPEN_MENU = ("openMenu", "openScreen")
_SIZE_DESC = "()I"
_CREATE_MENU_DESC = "(ILnet/minecraft/world/entity/player/Inventory;)Lnet/minecraft/world/inventory/AbstractContainerMenu;"
# Vanilla menus that only show a container's slots and move stacks in and
# out of them (MC 1.21.1 net.minecraft.world.inventory: ChestMenu, the 9xN
# grid of MenuType.GENERIC_9x1..9x6 and ChestMenu.oneRow..sixRows;
# ShulkerBoxMenu refuses shulker boxes in its slots; DispenserMenu the 3x3
# grid; HopperMenu the 5-slot row). A mod menu, or a vanilla menu with
# rules of its own (furnace, brewing stand...), is the mod's screen.
_INVENTORY = "net/minecraft/world/inventory/"
_GRID_MENUS = {_INVENTORY + c for c in ("ChestMenu", "ShulkerBoxMenu", "DispenserMenu", "HopperMenu")}


@dataclass
class ContainerReading:
    """What a block's code says about the items it holds.

    ``slots`` is the block entity's getContainerSize, or None with ``why``.
    ``menu_from`` names the use method that opens the menu ("" when none
    does). ``ticks`` names the block's getTicker when it overrides one (its
    block entity then does something over time). ``be`` is the block
    entity's class (dotted).
    """

    name: str
    cls: str | None = None
    be: str | None = None
    slots: int | None = None
    slots_from: str = ""
    why: str = ""
    menu_from: str = ""
    ticks: str = ""
    entity: bool = False  # newBlockEntity is overridden
    # The vanilla menu class createMenu builds (dotted) and where it was
    # read, or "" with menu_why.
    menu: str = ""
    menu_where: str = ""
    menu_why: str = ""


def _calls_in(machine: Machine, cls: str, method: str, depth: int = 3, seen: set | None = None) -> str:
    """'Class#method' when ``method`` of ``cls`` (or a mod method it calls,
    ``depth`` calls deep) invokes an openMenu/openScreen method, else ''."""
    seen = set() if seen is None else seen
    for cname in machine.chain(cls):
        cf = machine.classes.get(cname)
        if cf is None:
            break
        declared = [m for m in cf.methods if m.name == method and m.code is not None]
        for m in declared:
            if (cname, m.name, m.desc) in seen:
                continue
            seen.add((cname, m.name, m.desc))
            for insn in instructions(cf, m.code):
                if not isinstance(insn.arg, Ref) or insn.op not in (0xb6, 0xb7, 0xb8, 0xb9):
                    continue
                if insn.arg.name in _OPEN_MENU:
                    return f"{cname.replace('/', '.')}#{m.name}"
                if depth and machine.is_mod(insn.arg.owner):
                    found = _calls_in(machine, insn.arg.owner, insn.arg.name, depth - 1, seen)
                    if found:
                        return found
        if declared:
            # The nearest declaration is the one Java runs; a super call
            # in it was followed above.
            return ""
    return ""


def _menu_built(machine: Machine, be: str) -> tuple[str, str, str]:
    """(menu class, 'Class#createMenu', why): the menu class the block
    entity's createMenu (or a mod method it calls) builds, when it is one of
    _GRID_MENUS and the only menu it builds; else ('', where, why)."""
    found = machine.find_method(be, "createMenu", _CREATE_MENU_DESC)
    if found is None:
        return "", "", f"{be.replace('/', '.')} doesn't implement createMenu in the mod's classes"
    where = f"{found[0].name.replace('/', '.')}#createMenu"
    menus: set[str] = set()
    other: set[str] = set()
    todo, seen = [(found[0], found[1], 2)], set()
    while todo:
        cf, m, depth = todo.pop()
        if (cf.name, m.name, m.desc) in seen:
            continue
        seen.add((cf.name, m.name, m.desc))
        for insn in instructions(cf, m.code):
            if insn.op == 0xbb and isinstance(insn.arg, tuple):  # new
                cls = insn.arg[1]
                if cls in _GRID_MENUS:
                    menus.add(cls)
                elif cls.endswith("Menu") or (machine.is_mod(cls) and machine.vanilla_base(cls).startswith(_INVENTORY)):
                    other.add(cls)
            elif isinstance(insn.arg, Ref) and insn.op in (0xb6, 0xb7, 0xb8, 0xb9):
                ref = insn.arg
                if ref.owner == _INVENTORY + "ChestMenu" and insn.op == 0xb8:
                    menus.add(ref.owner)
                elif machine.is_mod(ref.owner) and depth:
                    target = machine.find_method(ref.owner, ref.name, ref.desc)
                    if target is not None:
                        todo.append((target[0], target[1], depth - 1))
                elif ref.desc.endswith(")L" + _INVENTORY + "AbstractContainerMenu;"):
                    # A menu made somewhere the reader doesn't follow (a
                    # platform service, an interface).
                    other.add(f"{ref.owner}#{ref.name}")
    if other:
        return "", where, f"{where} builds the mod's own menu ({', '.join(sorted(o.replace('/', '.') for o in other))})"
    if len(menus) != 1:
        return "", where, f"{where} builds no vanilla grid menu it can read"
    return menus.pop().replace("/", "."), where, ""


def read_containers(classes: ClassIndex | None, names: list[str]) -> dict[str, ContainerReading]:
    """A :class:`ContainerReading` per blockstate name in ``names``."""
    readings = {n: ContainerReading(n) for n in names}
    if classes is None or not len(classes):
        for r in readings.values():
            r.why = "the mod ships no class files"
        return readings
    machine, registered = _registered(classes, names)
    # Block entity types are registered apart from blocks; follow them fresh.
    machine.holders = True
    machine.statics.clear()
    machine._clinit_done.clear()
    machine._clinit_failed.clear()
    for name, r in readings.items():
        objs, why = registered[name]
        if not objs:
            r.why = why
            continue
        obj = objs[0]
        r.cls = obj.cls.replace("/", ".")
        found = machine.find_method(obj.cls, "newBlockEntity", _NEW_BE_DESC)
        if found is None:
            continue
        r.entity = True
        _read_container(machine, obj, found, r)
    return readings


def _read_container(machine: Machine, obj: Obj, found, r: ContainerReading) -> None:
    where = f"{found[0].name.replace('/', '.')}#newBlockEntity"
    machine.steps = 0
    machine.new_epoch()
    try:
        built = machine.run(*found, [obj, UNKNOWN, UNKNOWN])
    except Unreadable as exc:
        r.why = f"{where} can't be followed ({exc})"
        return
    entities = [b for b in built if isinstance(b, Obj) and machine.is_mod(b.cls)]
    if not entities or len(entities) != len(built):
        r.why = f"{where} doesn't build a block entity of the mod's that can be read"
        return
    if len({e.cls for e in entities}) != 1:
        r.why = f"{where} builds different block entities: " + ", ".join(sorted({e.cls for e in entities}))
        return
    be = entities[0].cls
    r.be = be.replace("/", ".")
    base = machine.vanilla_base(be)
    if base not in _PLAIN_CONTAINERS:
        r.why = (f"its block entity {r.be} is built on {base.replace('/', '.')}, which is not a plain "
                 "container (BaseContainerBlockEntity / RandomizableContainerBlockEntity)")
        return
    if _renamed(machine, be):
        r.why = (f"{r.be} uses Forge SRG or Fabric intermediary member names, so its getContainerSize "
                 "can't be found by name")
        return
    size_m = machine.find_method(be, "getContainerSize", _SIZE_DESC)
    if size_m is None:
        r.why = f"{r.be} doesn't implement getContainerSize in the mod's classes"
        return
    size_where = f"{size_m[0].name.replace('/', '.')}#getContainerSize"
    partial = [e.fields["__partial"] for e in entities if "__partial" in e.fields]
    if partial:
        r.why = f"{r.be}'s constructor can't be followed to the end ({partial[0]})"
        return
    sizes = set()
    try:
        for e in entities:
            machine.steps = 0
            sizes.update(machine.run(*size_m, [e]))
    except Unreadable as exc:
        r.why = f"{size_where} can't be followed ({exc})"
        return
    if len(sizes) != 1 or not all(isinstance(s, int) and not isinstance(s, bool) for s in sizes):
        r.why = f"{size_where} doesn't give one slot count the code fixes"
        return
    size = sizes.pop()
    if not 1 <= size <= MAX_SLOTS:
        r.why = f"{size_where} gives {size} slots; a Bedrock block container holds 1 to {MAX_SLOTS}"
        return
    r.slots, r.slots_from = size, f"{size_where} via {where}"
    for method in _USE_METHODS:
        r.menu_from = _calls_in(machine, obj.cls, method)
        if r.menu_from:
            break
    r.menu, r.menu_where, r.menu_why = _menu_built(machine, be)
    ticker = machine.find_method(obj.cls, "getTicker", (
        "(Lnet/minecraft/world/level/Level;Lnet/minecraft/world/level/block/state/BlockState;"
        "Lnet/minecraft/world/level/block/entity/BlockEntityType;)"
        "Lnet/minecraft/world/level/block/entity/BlockEntityTicker;"))
    if ticker is not None:
        r.ticks = f"{ticker[0].name.replace('/', '.')}#getTicker"
