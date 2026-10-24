"""Collision read from a block's code (#296, follow-up of #385: the
Supplementaries sconces still collided on Bedrock though Java players walk
through them).

tests/data/nocoll/classes are javac 21 output (build.sh): an example mod whose
blocks get their collision from Properties#noCollission, from a Properties
copy of a block that has it, or from a getCollisionShape override. Bedrock has
one collision box for every entity, so an override is read for an entity its
code doesn't single out (``blockcode.Collider``): ``sconce`` is
Supplementaries 1.20.1 SconceBlock's shape (``context instanceof
EntityCollisionContext ec && ec.getEntity() instanceof Projectile ?
state.getShape(level, pos) : Shapes.empty()``).
"""
from __future__ import annotations

from pathlib import Path

from portkit import blockcode
from portkit.bytecode import ClassIndex

DATA = Path(__file__).parent / "data" / "nocoll" / "classes"
NAMES = ["sconce", "sconce_plain", "copied", "copied_old", "plain", "no_coll", "grate", "gate", "solid", "has"]


def _index() -> ClassIndex:
    return ClassIndex({p.relative_to(DATA).as_posix()[:-6]: p.read_bytes() for p in DATA.rglob("*.class")})


def _read() -> dict:
    return blockcode.read_state_blocks(_index(), {n: ("lit",) for n in NAMES}, facingless=frozenset(NAMES))


def test_an_override_that_is_empty_for_any_entity_it_doesnt_single_out_has_no_collision():
    r = _read()
    for name in ("sconce", "sconce_plain"):  # the override decides, whatever the Properties say
        assert r[name].collision is False, (name, r[name].collision_why)
        assert r[name].collision_from == "com.example.nmod.NSconce#getCollisionShape"
    # The selection box is still getShape's.
    assert set(r["sconce"].shapes_by.values()) == {((6.0, 0.0, 6.0, 10.0, 11.0, 10.0),)}


def test_properties_decide_without_an_override():
    r = _read()
    assert r["plain"].collision is True and r["plain"].collision_from == ""
    assert r["no_coll"].collision is False and r["no_coll"].collision_from == ""


def test_a_copy_of_a_mod_blocks_properties_carries_its_collision():
    r = _read()
    assert r["copied"].collision is False  # ofFullCopy (1.21.1)
    assert r["copied_old"].collision is False  # copy (1.20.1)


def test_an_override_that_collides_somewhere_keeps_the_default():
    r = _read()
    # Only projectiles pass: every other entity collides.
    assert r["grate"].collision is None
    assert "box of its own" in r["grate"].collision_why
    # Empty only in some states: every state is followed.
    assert r["gate"].collision is None
    # noCollission Properties, but the override collides (it wins, as in Java).
    assert r["solid"].collision is None
    assert "NSolid#getCollisionShape" in r["solid"].collision_why
    # Every state of the block has lit, so hasProperty(lit) is true.
    assert r["has"].collision is None


def test_collider_answers_only_what_every_entity_context_is():
    m = blockcode.Machine(_index())
    ctx, ent = blockcode.COLLIDER_CONTEXT, blockcode.COLLIDER_ENTITY
    assert m.instance_of(ctx, "net/minecraft/world/phys/shapes/EntityCollisionContext") == 1
    assert m.instance_of(ctx, "net/minecraft/world/phys/shapes/CollisionContext") == 1
    assert m.instance_of(ent, "net/minecraft/world/entity/Entity") == 1
    assert m.instance_of(ent, "net/minecraft/world/entity/projectile/Projectile") == 0
    assert m.instance_of(ent, "net/minecraft/world/entity/player/Player") == 0


def test_notes_name_where_no_collision_was_read():
    from portkit.converters.blocks import _no_collision_notes
    notes = _no_collision_notes([
        {"name": "a", "collision": False, "collision_from": ""},
        {"name": "b", "collision": False, "collision_from": "x.B#getCollisionShape"},
        {"name": "c", "collision": None, "collision_from": ""},
    ])
    assert notes[0].startswith("No collision, read from bytecode (the block's Properties call noCollission")
    assert notes[0].endswith(": a.")
    assert "Shapes.empty() in every state" in notes[1] and notes[1].endswith("x.B#getCollisionShape: b.")
