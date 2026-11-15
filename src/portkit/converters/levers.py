"""Levers (#237, the known-superclass table's ``LeverBlock`` row).

A **lever** is an attach-face blockstate (``face`` + ``facing``) drawing one
boolean, ``powered``.  Its registration is followed to vanilla
``LeverBlock`` by :func:`portkit.blockcode.read_directional_states`; a mod
class between the registration and ``LeverBlock`` may not replace the
lever behaviour.

The vanilla behaviour ported here was read from Mojang's 1.21.1 client jar
(sha1 30c73b1c, ``net.minecraft.world.level.block.LeverBlock`` through
client.txt sha1 2244b6f0) and checked against 1.20.1 (sha1 0c3ec587,
client.txt 6c48521e), read 2026-11-14:

- **use** (``useWithoutItem`` / ``use`` in 1.20.1): the lever flips
  ``powered`` and keeps that value until another use flips it again;
- **redstone** (``getSignal`` / ``getDirectSignal``): while powered it gives
  signal 15 on every side, and directly (strongly) to the block it hangs
  on.  The attached block is below a floor lever, above a ceiling lever and
  behind a wall lever;
- **click** (``useWithoutItem``): a use plays ``SoundEvents.LEVER_CLICK``
  from the block (``SoundSource.BLOCKS``);
- **attachment** (``getStateForPlacement`` / ``canSurvive`` /
  ``updateShape``): the lever hangs on the block at its attach face.  The
  generic directional converter supplies that placement rule; the later loss
  of the support isn't carried.

The existing cited reading in :mod:`portkit.blockcode` also records that
``LeverBlock`` flips ``powered`` in vanilla code and that it declares
``getShape`` but no ``getCollisionShape``.  The attach-face placement,
shape and attachment rules are the generic directional converter's rules
(:func:`portkit.converters.blocks._convert_directional`, #218 and the
2026-10-14 facing-and-boolean decision), not a new lever default.

The persistent use toggle is carried by the fixed ``toggle.js`` runtime:
``onPlayerInteract`` flips the one boolean named in its data table and the
new permutation remains.  A lever has no press timer, arrow press or
scheduled release.  The vanilla click is named in the notes but is not
carried by that generic runtime.

No behaviour is invented: a registration whose vanilla ``LeverBlock``
constructor call or whose own override of lever behaviour isn't read stays
residue naming what is missing (#87).
"""
from __future__ import annotations

from ..data import block_set_types

# learn.microsoft.com minecraft:redstone_producer: "requires a format
# version of at least 1.21.120"; MCPE-229570 (a producer toggled by
# permutation didn't update its signal) is fixed in 1.21.130.
LEVER_FORMAT = "1.21.130"


def attached_face(java_key: tuple) -> str:
    """The Bedrock face of the lever touching the block it hangs on, from
    its Java (face, facing).

    A floor lever hangs below its block, a ceiling lever above its block,
    and a wall lever on the block opposite the way it faces.
    """
    face, facing = java_key
    if face == "floor":
        return "down"
    if face == "ceiling":
        return "up"
    return {"north": "south", "south": "north", "east": "west", "west": "east"}[facing]


def read(reading) -> tuple[dict | None, str]:
    """The lever's facts from a :class:`blockcode.DirStateReading` read as
    vanilla ``LeverBlock``.

    The result is ``({"from": ...}, "")`` when the registration reaches
    ``LeverBlock`` without replacing its behaviour and its constructor call
    is read; otherwise ``(None, why it stays residue)``.
    """
    cls = reading.cls
    if reading.lever_overrides:
        return None, (f"lever: its class {cls} overrides vanilla LeverBlock behaviour "
                      f"({', '.join(reading.lever_overrides)}), which is its own code")
    if reading.lever_why:
        return None, f"lever: {reading.lever_why}"
    ctors = list(getattr(reading, "lever_ctors", None) or [reading.lever_ctor])
    got = [_read_one(cls, ctor) for ctor in ctors]
    for facts, why in got:
        if facts is None:
            return None, why
    distinct = {facts["from"] for facts, _ in got}
    if len(distinct) > 1:
        return None, (f"lever: its registration builds it on {len(ctors)} ways through branches the reader "
                      "can't decide, and they disagree on the LeverBlock constructor, so which one the game "
                      "makes isn't known (no DEFAULT, #87)")
    return got[0][0], ""


def _read_one(cls: str, ctor) -> tuple[dict | None, str]:
    """One ``LeverBlock`` constructor call's facts, as :func:`read`."""
    if not ctor or ctor[0] != block_set_types.LEVER_CLASS:
        return None, (f"lever: {cls} reaches vanilla LeverBlock, but the LeverBlock constructor call "
                      "isn't read, so the vanilla lever it builds isn't known")
    desc = ctor[1]
    if desc not in block_set_types.LEVER_BLOCK_CTORS:
        return None, f"lever: {cls} calls LeverBlock{desc}, a constructor this doesn't read"
    return {"from": f"{cls} new LeverBlock{desc}"}, ""


def notes(records: list[dict]) -> list[str]:
    """The notes for converted levers."""
    out = []
    for record in records:
        out.append(
            f"{record['name']}: lever toggled by a use, read from its code ({record['lever']['from']}); it "
            "keeps that state until the next use and gives redstone power 15 on every side while powered "
            "(the block it hangs on strongly), as Java. The use plays Java's block-source "
            "SoundEvents.LEVER_CLICK; the generic toggle runtime doesn't carry that click. Not carried: "
            "the support rule beyond the attach-face converter's placement rule (Java drops a lever whose "
            "support is gone), game events and explosions.")
    return out
