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
  each blockstate name to the object constructed for it.

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
_PLACEMENT_DESC = ("(Lnet/minecraft/world/item/context/BlockPlaceContext;)"
                   "Lnet/minecraft/world/level/block/state/BlockState;")

# Vanilla property fields the interpreter knows by name: field -> property name.
_VANILLA_PROPS = {
    ("net/minecraft/world/level/block/HorizontalDirectionalBlock", "FACING"): "facing",
    (_STATE_PROPS, "HORIZONTAL_FACING"): "facing",
    (_STATE_PROPS, "FACING"): "facing6",
    (_STATE_PROPS, "WATERLOGGED"): "waterlogged",
    (_STATE_PROPS, "LIT"): "lit",
    (_STATE_PROPS, "POWERED"): "powered",
    (_STATE_PROPS, "OPEN"): "open",
}

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


@dataclass(eq=False)
class Obj:
    cls: str
    fields: dict = field(default_factory=dict)


@dataclass(eq=False)
class Arr:
    items: list


@dataclass(eq=False)
class MapV:
    items: dict


@dataclass(eq=False)
class Builder:
    parts: list


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
class RL:
    path: str


class _Ctx:
    def __repr__(self):
        return "ctx"


PLACE_CTX = _Ctx()


@dataclass
class Frame:
    pc: int
    locals: list
    stack: list
    forked: bool = False

    def copy(self) -> "Frame":
        return Frame(self.pc, list(self.locals), list(self.stack), True)


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
    value: object  # Lam or Obj


class Machine:
    """Runs the methods of one mod's classes on abstract values."""

    def __init__(self, classes: ClassIndex):
        self.classes = classes
        self.statics: dict[tuple[str, str], object] = {}
        self._clinit_done: set[str] = set()
        self._clinit_failed: set[str] = set()
        self.steps = 0
        self.registrations: list[Registration] | None = None
        self.depth = 0
        # Whether the instruction being run sits after an undecided branch.
        self._forked = False
        # Which evaluation is running (see Props.epoch).
        self.epoch = 0
        self._epochs = 0
        # BlockState property names read (getValue) while it is a set.
        self.state_reads: set | None = None

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
        start = recv.cls if isinstance(recv, Obj) and not special and not static else owner
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
        names = [a.path if isinstance(a, RL) else a.fields["__rl"] if isinstance(a, Obj) and "__rl" in a.fields
                 else a for a in args
                 if isinstance(a, (str, RL)) or (isinstance(a, Obj) and "__rl" in a.fields)]
        values = [a for a in args if isinstance(a, Lam) or (isinstance(a, Obj) and "__rl" not in a.fields)]
        if len(names) == 1 and len(values) == 1:
            self.registrations.append(Registration(names[0].rsplit(":", 1)[-1], values[0]))

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
                    break
                if kind == "throw":
                    break
                if kind == "fork":
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

    def _write(self, frame: Frame) -> None:
        if frame.forked:
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
                self._write(f)
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
            return self._branch(op, insn.arg, f)
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
                self._write(f)
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
            s.pop()
            s.append(UNKNOWN)
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

    def _branch(self, op: int, target: int, f: Frame):
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
        if taken is None:
            g = f.copy()
            g.pc = target
            h = f.copy()
            return ("fork", [g, h])
        if taken:
            f.pc = target
        return None

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
            f.stack.append(Lam(indy.args[1], tuple(args)))
        elif bsm and bsm.owner == "java/lang/invoke/StringConcatFactory" and indy.args \
                and isinstance(indy.args[0], str):
            recipe, consts = indy.args[0], list(indy.args[1:])
            out, k = [], 0
            for ch in recipe:
                if ch == "\x01":
                    v = args[k]
                    k += 1
                    if not isinstance(v, (str, int)) or isinstance(v, bool):
                        f.stack.append(UNKNOWN)
                        return None
                    out.append(str(v))
                elif ch == "\x02":
                    out.append(str(consts.pop(0)))
                else:
                    out.append(ch)
            f.stack.append("".join(out))
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
            if isinstance(obj, Obj) and self.is_mod(ref.owner):
                found = self.find_method(ref.owner, "<init>", ref.desc)
                if found is not None:
                    self._write(f)
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
        if ref.desc.startswith(f"(L{_PROPERTIES};") and len(args) > 1:
            obj.fields.setdefault("__props", _snapshot(args[1]))
        elif ref.owner.startswith(_VANILLA_BLOCK_PACKAGE) and len(props_at) == 1 \
                and _only_objects(ref.desc) and props_at[0] + 1 < len(args):
            obj.fields.setdefault("__props", _snapshot(args[props_at[0] + 1]))
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
        if owner == _DIRECTION or isinstance(recv, (Dir, PlayerDir)):
            return self._direction(name, recv, rest, static)
        if recv is PLACE_CTX:
            if name == "getHorizontalDirection":
                return [PlayerDir(0)]
            return [UNKNOWN]
        if isinstance(recv, State):
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
        if isinstance(recv, Obj) and self.is_block_class(recv.cls):
            base = self.vanilla_base(recv.cls)
            if name == "defaultBlockState":
                return [recv.fields.get("__default", State())]
            if name == "registerDefaultState" and rest:
                if isinstance(rest[0], State):
                    recv.fields["__default"] = rest[0]
                return [None]
            if name in ("getStateDefinition",):
                return [Obj("__statedef")]
            if base in _PLAIN_VANILLA:
                if name == "getStateForPlacement" and desc == _PLACEMENT_DESC:
                    return [recv.fields.get("__default", State())]
                if name == "getShape" and desc == _GET_SHAPE_DESC:
                    return [Shape(((0.0, 0.0, 0.0, 16.0, 16.0, 16.0),))]
        if isinstance(recv, Obj) and recv.cls == "__statedef" and name == "any":
            return [State()]
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
                recv.parts.append(rest[0])
                return [recv]
            if name == "toString":
                if all(isinstance(p, (str, int)) and not isinstance(p, bool) for p in recv.parts):
                    return ["".join(str(p) for p in recv.parts)]
                return [UNKNOWN]
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
        if owner == "net/minecraft/resources/ResourceLocation" and static:
            strs = [a for a in rest if isinstance(a, str)]
            if name in ("fromNamespaceAndPath", "tryBuild") and len(strs) == 2 and len(rest) == 2:
                return [RL(f"{strs[0]}:{strs[1]}")]
            if name in ("parse", "tryParse", "withDefaultNamespace") and len(strs) == 1 and len(rest) == 1:
                return [RL(strs[0])]
        if name == "hashCode" or name == "equals":
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
            if name in ("ofFullCopy", "ofLegacyCopy") and rest:
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
    if isinstance(a, PlayerDir) or isinstance(b, PlayerDir):
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


def _registered(classes: ClassIndex, names: list[str]) -> tuple[Machine, dict[str, tuple[list, str]]]:
    """Run the registration code that names each blockstate in ``names`` and
    return, per name, the block objects built for it (``[]`` with the reason
    when none was found or it can't be followed)."""
    machine = Machine(classes)
    machine.registrations = []
    for cname in _wanted_classes(classes, set(names)):
        machine.steps = 0
        machine.init_class(cname)
    regs: dict[str, list] = {}
    for reg in machine.registrations:
        regs.setdefault(reg.name, []).append(reg.value)
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
            others += [o.cls for o in built if isinstance(o, Obj) and not machine.is_block_class(o.cls)
                       and "Item" not in o.cls.rsplit("/", 1)[-1] and "Entity" not in o.cls.rsplit("/", 1)[-1]]
        others = [o for o in others if not machine.vanilla_base(o).startswith(("java/", "com/mojang/"))]
        if not objs and others:
            outside = machine.vanilla_base(others[0])
            why = why or (f"registered as {others[0].replace('/', '.')}, whose superclasses leave the jar at "
                          f"{outside.replace('/', '.')} rather than reach a vanilla block class")
        if not objs:
            why = why or "no registration of this block was found in the mod's classes"
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
