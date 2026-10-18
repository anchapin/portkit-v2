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

_MAX_STEPS = 400_000
_MAX_PATHS = 256
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

    def __post_init__(self):
        self._serial = _next_serial()


@dataclass(eq=False)
class Builder:
    parts: list

    def __post_init__(self):
        self._serial = _next_serial()


@dataclass(frozen=True)
class Strm:
    items: tuple


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
        self.depth = 0
        # Whether the instruction being run sits after an undecided branch.
        self._forked = False
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
            self._record(args)
        if self.is_mod(start):
            if static:
                self.init_class(start)
            found = self.find_method(start, name, desc)
            if found is not None:
                return self.run(*found, args)
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
        self._record(args)
        _n, returns = _arg_count(desc)
        for a in args:
            if isinstance(a, Arr):
                a.items = [UNKNOWN] * len(a.items)
            elif isinstance(a, MapV):
                a.items = {}
        return [UNKNOWN] if returns else [None]

    def _record(self, args: list) -> None:
        if self.registrations is None:
            return
        if any(isinstance(a, RL) and a.lookup for a in args):
            return
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
        self.depth += 1
        try:
            return self._run(cf, m, args)
        finally:
            self.depth -= 1

    def _run(self, cf: ClassFile, m: Method, args: list) -> list:
        code = instructions(cf, m.code)
        at = {insn.offset: k for k, insn in enumerate(code)}
        self._code.append((code, at))
        try:
            return self._run_code(cf, m, args, code, at)
        finally:
            self._code.pop()

    def _run_code(self, cf: ClassFile, m: Method, args: list, code: list, at: dict) -> list:
        # Longs and doubles take two local slots (JVMS 2.6.1).
        local = self._wide_locals(m, args) + [UNKNOWN] * 256
        work = [Frame(0, local, [])]
        results: list = []
        paths = 1
        while work:
            frame = work.pop()
            while True:
                self.steps += 1
                if self.steps > _MAX_STEPS:
                    raise Unreadable("too much code to follow")
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
                    if self.effects is not None and self.depth == self.effects_depth:
                        self.effects.append((payload, frame.effects))
                    break
                if kind == "throw":
                    break
                if kind == "fork":
                    for g in payload:
                        g.fork_serial = _ALLOCATED[0]
                    paths += len(payload) - 1
                    if paths > _MAX_PATHS:
                        raise Unreadable(f"too many paths through {cf.name}.{m.name}")
                    for other in payload[1:]:
                        work.append(other)
                    frame = payload[0]
                    continue
        return results

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
        if frame.forked and (target is None or getattr(target, "_serial", -1) <= frame.fork_serial):
            raise Unreadable("writes to memory after a branch it can't decide")

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
            if isinstance(arr, Arr):
                self._write(f, arr)
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
            return ("return", s.pop())
        elif op == 0xB1:
            return ("return", None)
        elif op == 0xB2:
            s.append(self.get_static(insn.arg))
        elif op == 0xB3:
            ref = insn.arg
            self._write(f)
            owner = self._field_owner(ref.owner, ref.name)
            self.statics[(owner, ref.name)] = s.pop()
        elif op == 0xB4:
            obj = s.pop()
            name = insn.arg.name
            if isinstance(obj, Obj):
                s.append(obj.fields.get(name, UNKNOWN))
            else:
                s.append(UNKNOWN)
        elif op == 0xB5:
            val, obj = s.pop(), s.pop()
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
        if not self._code:
            return False
        code, at = self._code[-1]
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
            return MapV({})
        if cls == "java/lang/StringBuilder":
            return Builder([])
        return Obj(cls)

    def _indy(self, indy: Indy, f: Frame):
        n, _ = _arg_count(indy.desc)
        args = [f.stack.pop() for _ in range(n)][::-1]
        bsm = indy.bootstrap.ref if indy.bootstrap else None
        if bsm and bsm.owner == "java/lang/invoke/LambdaMetafactory" and len(indy.args) >= 2 \
                and isinstance(indy.args[1], Handle):
            itype = indy.args[2] if len(indy.args) >= 3 else None
            itype = itype[1] if isinstance(itype, tuple) and itype[:1] == ("methodtype",) else None
            f.stack.append(Lam(indy.args[1], tuple(args), itype))
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
        n, returns = _arg_count(ref.desc)
        static = op == 0xB8
        total = n + (0 if static else 1)
        args = [f.stack.pop() for _ in range(total)][::-1]
        if ref.name == "<init>":
            obj = args[0]
            if isinstance(obj, Builder):
                # new StringBuilder(String | CharSequence) starts with it.
                if ref.desc in ("(Ljava/lang/String;)V", "(Ljava/lang/CharSequence;)V"):
                    text = self.stringify(args[1])
                    obj.parts.append(text if text is not None else UNKNOWN)
                return None
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
        if not results:
            return ("throw", None)
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
        if owner in ("com/google/common/collect/ImmutableMap", "java/util/Map") and static \
                and name in ("of", "ofEntries"):
            if name == "of" and len(rest) % 2 == 0:
                items = {}
                for k in range(0, len(rest), 2):
                    if not _hashable(rest[k]):
                        return [UNKNOWN]
                    items[rest[k]] = rest[k + 1]
                return [MapV(items)]
            return [UNKNOWN]
        if owner == "com/google/common/collect/Maps" and static:
            if name == "newEnumMap" and rest and isinstance(rest[0], MapV):
                return [MapV(dict(rest[0].items))]
            if name in ("newEnumMap", "newHashMap"):
                return [MapV({})] if not rest or isinstance(rest[0], ClassLit) else [UNKNOWN]
        if isinstance(recv, MapV):
            if name in ("get", "getOrDefault") and rest:
                if not _hashable(rest[0]):
                    return [UNKNOWN]
                default = rest[1] if name == "getOrDefault" and len(rest) > 1 else None
                return [recv.items.get(rest[0], default if rest[0] is not UNKNOWN else UNKNOWN)]
            if name == "put" and len(rest) == 2:
                if not _hashable(rest[0]) or rest[0] is UNKNOWN:
                    recv.items = {}
                    return [UNKNOWN]
                old = recv.items.get(rest[0])
                recv.items[rest[0]] = rest[1]
                return [old]
            return [UNKNOWN]
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
        if isinstance(recv, Opt):
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
_BUILTIN_REGISTRIES = "net/minecraft/core/registries/BuiltInRegistries"
# A resource location's characters (ResourceLocation#isValidNamespace /
# isValidPath, MC 1.21.1: namespace [a-z0-9_.-], path [a-z0-9_./-]).
_RESOURCE_NAME = re.compile(r"([a-z0-9_.-]+:)?[a-z0-9_./-]+")


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


def _piece_methods(classes: ClassIndex, names: set[str], done: set) -> list:
    """Methods of the mod's own classes (not a library's, never its static
    initializers, abstract ones skipped, those in ``done`` skipped) that may
    build one of ``names`` by concatenation (#280): one that loads (``ldc``)
    a whole-word piece of a name (``"azalea"`` handed to a helper that
    appends ``"_planks"``; ``"_shingles"`` appended in a loop), or one whose
    ``makeConcatWithConstants`` recipe matches a whole name
    (``"\\x01_pressure_plate"``). Which name it builds is only what the
    machine evaluates; this only chooses what to run."""
    pieces = _name_pieces(names)
    bare = {n.rsplit(":", 1)[-1] for n in names}
    out = []
    for cname in classes.names():
        cf = classes.get(cname)
        if cf is None:
            continue
        strings = {cf.pool[e[1]][1] for e in cf.pool if e is not None and e[0] == 8}
        if not any(s.strip("_") in pieces or "\x01" in s for s in strings):
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
    targets = {(cf.name, m.name, m.desc) for cf, m in out}
    chosen = set(targets)
    callers = []
    for cname in classes.names():
        cf = classes.get(cname)
        if cf is None:
            continue
        for m in cf.methods:
            key = (cname, m.name, m.desc)
            if m.name == "<clinit>" or m.code is None or key in chosen or key in done:
                continue
            try:
                code = instructions(cf, m.code)
            except Exception:  # noqa: BLE001
                continue
            if any(i.op in (0xB6, 0xB7, 0xB8, 0xB9) and isinstance(i.arg, Ref)
                   and (i.arg.owner, i.arg.name, i.arg.desc) in targets for i in code):
                callers.append((cf, m))
                chosen.add(key)
    return out + callers


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
        machine.run(cf, m, [UNKNOWN] * (n + (0 if static else 1)))
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
