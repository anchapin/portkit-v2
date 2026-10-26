"""#296: ``Comparator.comparingInt`` and ``Stream#sorted`` (Java SE 21), and
``Direction.Axis#isHorizontal``, read generically by the machine (what a
mod's ``Arrays.stream(Direction.values()).filter(..).sorted(comparingInt(
Direction::get2DDataValue))`` builds)."""
from __future__ import annotations

from portkit.blockcode import UNKNOWN, Const, Dir, IntKeyOrder, Lam, Machine, Strm
from portkit.bytecode import ClassIndex, Handle, Ref

_D = "net/minecraft/core/Direction"
_CMP = "(Ljava/util/function/ToIntFunction;)Ljava/util/Comparator;"
_SORTED = "(Ljava/util/Comparator;)Ljava/util/stream/Stream;"


def _by_2d() -> Lam:
    return Lam(Handle(5, Ref(_D, "get2DDataValue", "()I")), (), "(L%s;)I" % _D, "java/util/function/ToIntFunction")


def test_comparing_int_sorts_by_the_key_stably():
    m = Machine(ClassIndex({}))
    order = m.call("java/util/Comparator", "comparingInt", _CMP, [_by_2d()], static=True)
    assert len(order) == 1 and isinstance(order[0], IntKeyOrder)
    dirs = tuple(Dir(d) for d in ("north", "south", "west", "east"))
    out = m._stream(Strm(dirs), "sorted", _SORTED, [order[0]])
    assert out == [Strm((Dir("south"), Dir("west"), Dir("north"), Dir("east")))]
    # Equal keys keep their encounter order (a stable sort).
    same = m._stream(Strm((Dir("up"), Dir("down"))), "sorted", _SORTED, [order[0]])
    assert same == [Strm((Dir("up"), Dir("down")))]


def test_a_key_that_is_not_known_leaves_the_order_unknown():
    m = Machine(ClassIndex({}))
    out = m._stream(Strm((Dir("north"), Dir("south"))), "sorted", _SORTED, [IntKeyOrder(UNKNOWN)])
    assert out == [UNKNOWN]
    # A comparator that isn't a comparingInt order isn't read.
    assert m._stream(Strm((Dir("north"),)), "sorted", _SORTED, [UNKNOWN]) == [UNKNOWN]


def test_axis_is_horizontal():
    m = Machine(ClassIndex({}))
    axis = _D + "$Axis"
    assert m.call(axis, "isHorizontal", "()Z", [Const(axis, "X")]) == [1]
    assert m.call(axis, "isHorizontal", "()Z", [Const(axis, "Y")]) == [0]
    assert m.call(axis, "isVertical", "()Z", [Const(axis, "Y")]) == [1]
