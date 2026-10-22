"""Vanilla Java ``SoundEvents`` fields -> the Bedrock sound definition vanilla Bedrock plays
for the same block sound event (#367 pick 9a).

A block built with a vanilla ``SoundEvents`` constant (Forge/NeoForge's
``FenceGateBlock(Properties, SoundEvent openSound, SoundEvent closeSound)``) plays that
event. This map is not a new hand table (#220): every row is derived from the block sound
tables already sourced from Mojang/bedrock-samples@46ba6ea9 ``resource_pack/sounds.json``
``block_sounds`` (one family's ``fence_gate.*`` / ``door.*`` / ``trapdoor.*`` /
``pressure_plate.*`` events, e.g. ``"copper": {"events": {"door.open": {"sound":
"open_door.copper"}, "door.close": {"sound": "close_door.copper"}}}``), with the Java field
names those tables already read from Mojang's ``BlockSetType`` / ``WoodType`` bytecode:

* ``<family>FENCE_GATE_OPEN`` / ``_CLOSE``: :data:`portkit.data.wood_types.OPEN_EVENTS`,
  ``CLOSE_EVENTS`` -> ``wood_types.SOUNDS`` (``fence_gate.open`` / ``fence_gate.close``);
* ``<family>_DOOR_OPEN`` / ``_CLOSE``: ``block_set_types.SOUNDS`` (``door.open`` /
  ``door.close``: WOODEN, IRON, COPPER, CHERRY_WOOD, NETHER_WOOD, BAMBOO_WOOD);
* ``<family>_TRAPDOOR_OPEN`` / ``_CLOSE``: ``block_set_types.TRAPDOOR_SOUNDS``
  (``trapdoor.open`` / ``trapdoor.close``; Bedrock's copper family plays
  ``open_trapdoor.copper`` for both);
* ``<family>_PRESSURE_PLATE_CLICK_ON`` / ``_OFF``: ``block_set_types.PLATE_SOUNDS``, only
  the families Bedrock has ``pressure_plate.*`` events for at pitch 1 (not METAL, whose
  ``random.click`` at 0.6 / 0.5 is an approximation, and not the button clicks, which
  Bedrock plays at a changed pitch: neither is the same sound).

A field not here has no Bedrock equivalent read: :func:`bedrock_sound` returns None and the
caller labels its own DEFAULT; nothing is guessed (#87).
"""
from __future__ import annotations

from . import block_set_types, wood_types

_SRC = "Mojang/bedrock-samples@46ba6ea9 resource_pack/sounds.json block_sounds"


def _build() -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for events, at in ((wood_types.OPEN_EVENTS, 0), (wood_types.CLOSE_EVENTS, 1)):
        for field, family in events.items():
            verb = "open" if at == 0 else "close"
            out[field] = (wood_types.SOUNDS[family][at],
                          f"{_SRC} {family.lower()} fence_gate.{verb}")
    for table, part in ((block_set_types.SOUNDS, "DOOR"), (block_set_types.TRAPDOOR_SOUNDS, "TRAPDOOR")):
        for family, (opened, closed) in table.items():
            event = part.lower()
            fam = "wood" if family == "WOODEN" else family.lower()
            out[f"{family}_{part}_OPEN"] = (opened, f"{_SRC} {fam} {event}.open")
            out[f"{family}_{part}_CLOSE"] = (closed, f"{_SRC} {fam} {event}.close")
    for family, (on, off, on_pitch, off_pitch) in block_set_types.PLATE_SOUNDS.items():
        if (on_pitch, off_pitch) != (1.0, 1.0) or on == "random.click":
            continue
        fam = "wood" if family == "WOODEN" else family.lower()
        out[f"{family}_PRESSURE_PLATE_CLICK_ON"] = (on, f"{_SRC} {fam} pressure_plate.click_on")
        out[f"{family}_PRESSURE_PLATE_CLICK_OFF"] = (off, f"{_SRC} {fam} pressure_plate.click_off")
    return out


EVENTS: dict[str, tuple[str, str]] = _build()
"""``SoundEvents`` field -> (Bedrock sound definition, where it comes from)."""


def bedrock_sound(field: str) -> tuple[str, str] | None:
    """(Bedrock sound definition, source) for a vanilla ``SoundEvents`` field, or None."""
    return EVENTS.get(field)
