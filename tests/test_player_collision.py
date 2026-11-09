"""#296: a getCollisionShape that tests the colliding entity's type is read
for a player (``blockcode._override_collision``, ``Collider`` ``player``).

Bedrock has one collision box for every entity, so where Java gives players
one box and other entities another, the box Bedrock players feel is the one
Java gives a player, labelled as read for that reason. ``seat`` in
tests/data/nocoll (javac 21 output of src/, rebuild with build.sh) is Create
6.0.x SeatBlock's shapes: ``getShape`` an 8 px slab; ``getCollisionShape``
3 px for a player and 6 px for every other entity. A test on a type every
entity answers alike for a player and for any other entity (the sconce's
``instanceof Projectile``) changes nothing and is not labelled.
"""
from __future__ import annotations

from pathlib import Path

from portkit import blockcode
from portkit.bytecode import ClassIndex
from portkit.converters import blocks
from portkit.model import ConversionResult, SourceMod

DATA = Path(__file__).parent / "data" / "nocoll" / "classes"
SEAT = (0.0, 0.0, 0.0, 16.0, 8.0, 16.0)
PLAYERS = (0.0, 0.0, 0.0, 16.0, 3.0, 16.0)


def _index() -> ClassIndex:
    return ClassIndex({p.relative_to(DATA).as_posix()[:-6]: p.read_bytes() for p in DATA.rglob("*.class")})


def test_a_player_context_answers_what_a_player_is():
    m = blockcode.Machine(_index())
    ctx, ent = blockcode.PLAYER_CONTEXT, blockcode.PLAYER_ENTITY
    assert m.instance_of(ctx, "net/minecraft/world/phys/shapes/EntityCollisionContext") == 1
    assert m.instance_of(ent, "net/minecraft/world/entity/Entity") == 1
    assert m.instance_of(ent, "net/minecraft/world/entity/LivingEntity") == 1
    assert m.instance_of(ent, "net/minecraft/world/entity/player/Player") == 1
    assert m.instance_of(ent, "net/minecraft/world/entity/projectile/Projectile") == 0
    assert m.instance_of(ent, "net/minecraft/world/entity/item/ItemEntity") == 0
    # The server's or the client's player: which one asks isn't known.
    assert m.instance_of(ent, "net/minecraft/server/level/ServerPlayer") is blockcode.UNKNOWN
    # Every test of the entity's type is recorded, the Entity check aside.
    assert m.collider_tests == {"net/minecraft/world/entity/LivingEntity", "net/minecraft/world/entity/player/Player",
                                "net/minecraft/world/entity/projectile/Projectile",
                                "net/minecraft/world/entity/item/ItemEntity",
                                "net/minecraft/server/level/ServerPlayer"}
    # The context hands on a player entity.
    got = m.vanilla("net/minecraft/world/phys/shapes/EntityCollisionContext", "getEntity",
                    "()Lnet/minecraft/world/entity/Entity;", [ctx], False)
    assert got == [ent]


def test_a_seat_collides_as_a_player_does_with_its_own_box():
    r = blockcode.read_stateless_shapes(_index(), ["seat"])["seat"]
    assert r.shapes == (SEAT,)
    assert r.collision is True
    assert r.collision_boxes == (PLAYERS,)
    assert r.collision_from.startswith("com.example.nmod.NSeat#getCollisionShape, read for a player: ")
    assert "tests the entity's type (Player)" in r.collision_for
    assert "for a player it gives [0, 0, 0, 16, 3, 16] (pixels)" in r.collision_for
    assert "for an entity it doesn't single out [0, 0, 0, 16, 6, 16] (pixels)" in r.collision_for


def test_a_box_of_its_own_outside_the_one_look_reader_keeps_the_default_labelled():
    # The facing / state readers write the selection box as the collision
    # box, so a box of its own stays a DEFAULT there, with why.
    r = blockcode.read_state_blocks(_index(), {"seat": ("lit",)}, facingless=frozenset(["seat"]))["seat"]
    assert r.collision is None and r.collision_boxes is None
    assert "a box of its own" in r.collision_why and "read for a player" in r.collision_why


def test_a_test_every_entity_answers_alike_changes_nothing():
    got = blockcode.read_stateless_shapes(_index(), ["sconce", "grate"])
    # instanceof Projectile: a player is no more one than any other entity.
    assert got["sconce"].collision is False and got["grate"].collision is True
    for name in ("sconce", "grate"):
        assert got[name].collision_for == "" and got[name].collision_boxes is None
        assert ", read for a player" not in got[name].collision_from


def test_the_seat_block_file_gets_the_players_box(monkeypatch):
    readings = blockcode.read_stateless_shapes(_index(), ["seat"])
    monkeypatch.setattr(blockcode, "read_stateless_shapes", lambda classes, names, run=None:
                        {n: readings[n] for n in names})
    mod = SourceMod(root=DATA, namespace="nmod", classes=_index())
    result = ConversionResult()
    result.files["blocks/seat.json"] = blocks._block_definition("nmod", "seat", "geometry.nmod.seat", {})
    notes = blocks._stateless_boxes(mod, result, ["seat"], lambda: None)
    comps = result.files["blocks/seat.json"]["minecraft:block"]["components"]
    assert comps["minecraft:selection_box"] == blocks._bedrock_box(SEAT)
    assert comps["minecraft:collision_box"] == blocks._bedrock_box(PLAYERS)
    assert comps["minecraft:collision_box"] == {"origin": [-8, 0, -8], "size": [16, 3, 16]}
    player = [n for n in notes if n.startswith("Collision read from bytecode for a player")]
    assert len(player) == 1 and player[0].endswith(": seat.")
    assert not any(n.startswith("Collision DEFAULT") for n in notes)
    # One box, not an array: the block format is untouched.
    assert blocks._raise_for_arrays(result) == []
