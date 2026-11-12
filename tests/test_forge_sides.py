"""A Forge or NeoForge registration that asks which side it runs on is read
for a client and for a dedicated server, and only what both sides agree on is
kept, as for Fabric (#296, the generalisation of pick a;
``portkit.blockcode._registered``, ``Machine._dist``, ``_dist_executor``):
``FMLEnvironment.dist``, ``FMLLoader#getDist``, ``Dist#isClient`` /
``isDedicatedServer`` and Forge's ``DistExecutor``.

tests/data/fsides is javac 21 output (build.sh): an example mod (classes/).
Forge's, NeoForge's and Minecraft's code isn't there, as when a mod is read
without its loader.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from portkit import blockcode
from portkit.blockcode import UNKNOWN, Const, Machine
from portkit.bytecode import ClassIndex

DATA = Path(__file__).parent / "data" / "fsides"
NAMES = ["fside_split", "fside_neo", "fside_loader", "fside_forked", "fside_called", "fside_ran"]
FORGE_DIST = "net/minecraftforge/api/distmarker/Dist"
NEO_DIST = "net/neoforged/api/distmarker/Dist"


def _index() -> ClassIndex:
    root = DATA / "classes"
    return ClassIndex({p.relative_to(root).as_posix()[:-6]: p.read_bytes() for p in root.rglob("*.class")})


@pytest.fixture(scope="module")
def read():
    return blockcode._registered(_index(), NAMES)


def _block(reg, name):
    objs, why = reg[name]
    assert len(objs) == 1 and objs[0].cls == "com/example/fmod/FBlock", (name, why)
    return objs[0].fields


@pytest.mark.parametrize("side", ["client", "server"])
def test_each_run_answers_its_own_side(side):
    machine, reg = blockcode._registered_on(_index(), NAMES, False, side)
    client = side == "client"
    assert _block(reg, "fside_split")["size"] == (3 if client else 5)
    assert _block(reg, "fside_neo")["size"] == (2 if client else 4)
    assert _block(reg, "fside_loader")["size"] == (2 if client else 1)
    assert _block(reg, "fside_called")["size"] == (11 if client else 10)
    assert reg["fside_forked"][0][0].cls == ("com/example/fmod/FClientBlock" if client else "com/example/fmod/FBlock")
    assert machine.side_asked.split(", ")[0] == "FML's FMLEnvironment.dist"


def test_values_both_sides_give_are_kept_and_the_rest_unknown(read):
    _m, reg = read
    for name, glow in (("fside_split", 7), ("fside_neo", 6), ("fside_loader", 8), ("fside_called", 9)):
        fields = _block(reg, name)
        assert fields["glow"] == glow, name
        assert fields["size"] is UNKNOWN, name
    assert _block(reg, "fside_ran")["glow"] == 4


def test_a_name_the_sides_build_different_classes_for_is_not_read(read):
    machine, reg = read
    objs, why = reg["fside_forked"]
    assert objs == []
    assert why == blockcode._SIDE_WHY.format(machine.side_asked)
    assert "Forge's DistExecutor#runForDist" in why and "FML's FMLEnvironment.dist" in why


def test_outside_a_registration_run_the_side_is_unknown(read):
    machine, _reg = read
    assert machine.side is None
    ref = type("R", (), {"owner": "net/minecraftforge/fml/loading/FMLEnvironment", "name": "dist"})
    assert machine.get_static(ref) is UNKNOWN
    assert machine.call("net/neoforged/fml/loading/FMLLoader", "getDist", f"()L{NEO_DIST};", [],
                        static=True) == [UNKNOWN]
    # DistExecutor is an unknown call again: nothing handed to it runs.
    assert machine.call("net/minecraftforge/fml/DistExecutor", "unsafeCallWhenOn",
                        f"(L{FORGE_DIST};Ljava/util/function/Supplier;)Ljava/lang/Object;",
                        [Const(FORGE_DIST, "CLIENT"), UNKNOWN], static=True) == [UNKNOWN]


@pytest.mark.parametrize("dist, client", [("CLIENT", 1), ("DEDICATED_SERVER", 0)])
def test_dist_is_client_is_the_constant_s_own(dist, client):
    m = Machine(ClassIndex({}))
    for owner in (FORGE_DIST, NEO_DIST):
        assert m.call(owner, "isClient", "()Z", [Const(owner, dist)]) == [client]
        assert m.call(owner, "isDedicatedServer", "()Z", [Const(owner, dist)]) == [1 - client]
    assert m.side_asked == ""


def test_a_run_that_never_asks_is_read_once():
    m = Machine(ClassIndex({}))
    m.side = "client"
    assert m.call(FORGE_DIST, "isClient", "()Z", [Const(FORGE_DIST, "CLIENT")]) == [1]
    assert m.side_asked == ""


def test_only_fml_loader_s_get_dist_is_answered():
    # NeoForge 21.9+'s FMLEnvironment#getDist isn't read here (no jar checked).
    m = Machine(ClassIndex({}))
    m.side = "client"
    assert m.call("net/neoforged/fml/loading/FMLEnvironment", "getDist", f"()L{NEO_DIST};", [],
                  static=True) == [UNKNOWN]
    assert m.call("net/neoforged/fml/loading/FMLLoader", "getDist", f"()L{NEO_DIST};", [],
                  static=True) == [Const(NEO_DIST, "CLIENT")]
    assert m.side_asked == "FML's FMLLoader#getDist"
