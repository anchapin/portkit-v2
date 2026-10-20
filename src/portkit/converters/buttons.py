"""Buttons (#280; docs/decisions.md 2026-10-20 buttons, pending Alex's picks).

A **button** is an attach-face blockstate (``face`` + ``facing``) drawing one
boolean, ``powered``, whose registration the code reader follows
(``portkit.blockcode.read_directional_states``) to vanilla ``ButtonBlock``
built with a constructor this reads, no mod class in between overriding
:data:`portkit.blockcode.BUTTON_BEHAVIOUR`. Before this, #321 pick 5a kept
such a block residue: its press and scheduled release are vanilla code.
They are ported here, read from Mojang's 1.21.1 client jar (sha1 30c73b1c,
``ButtonBlock`` = ``dgi`` through client.txt sha1 2244b6f0) and checked
against 1.20.1 (sha1 0c3ec587, ``cpw`` through client.txt 6c48521e), read
2026-10-20:

- **press** (``useWithoutItem`` / 1.20.1 ``use``): a powered button does
  nothing (``InteractionResult.CONSUME``); otherwise ``press``: ``powered``
  true, neighbours updated, a tick scheduled ``ticksToStayPressed`` later,
  ``getSound(true)`` = the set type's ``buttonClickOn`` played;
- **release** (``tick`` -> ``checkPressed``): when the set type's
  ``canButtonBeActivatedByArrows`` (1.20.1: the button's own
  ``arrowsCanPress``) holds, the first ``AbstractArrow`` inside the button's
  shape keeps it pressed and schedules the next check ``ticksToStayPressed``
  later; with none it turns ``powered`` false and plays ``buttonClickOff``;
- **arrows** (``entityInside``): an arrow entering an unpowered button whose
  set type lets arrows press it runs ``checkPressed``, which presses it;
- **redstone** (``getSignal`` / ``getDirectSignal``): 15 on every side while
  powered; strongly (direct) only into the block it hangs on
  (``getConnectedDirection``: floor -> the block below, ceiling -> above,
  wall -> the block behind it);
- **explosions** (1.21 ``onExplosionHit``) press it: not carried.

What is read per button, from the vanilla constructor call its object was
built with (:data:`portkit.data.block_set_types.BUTTON_BLOCK_CTORS`): the
press time (an int literal), and from its ``BlockSetType`` (a vanilla
constant, :data:`~portkit.data.block_set_types.BUTTON_TYPES`, or one built in
code, see :func:`set_type_button`) whether arrows press it and its click
sounds. A button whose press time or set type isn't read stays residue
naming what is missing: there is no DEFAULT press time (#87).

The shape, placement and textures are the attach-face converter's
(``blocks._convert_directional``, #218); this module adds the button's
Bedrock parts: ``minecraft:redstone_producer`` (power 15 on the powered
permutations, ``strongly_powered_face`` the face touching the block it hangs
on), the button custom component and a ``minecraft:tick`` that releases a
button whose release timer a world reload dropped, all run by the fixed
runtime ``portkit/runtime/button.js``.
"""
from __future__ import annotations

from .. import blockcode
from ..data import block_set_types

BUTTON_RUNTIME = "scripts/portkit/button.js"
BUTTON_CORE = "scripts/portkit/button_core.js"
# Pick 4a: the plates' block format. learn.microsoft.com minecraft:redstone_producer:
# "requires a format version of at least 1.21.120"; MCPE-229570 (a producer
# toggled by permutation didn't update its signal) is fixed in 1.21.130.
BUTTON_FORMAT = "1.21.130"
# Pick 5a: the scriptevent id the runtime presses a button on (the same press
# a player's use takes); "<namespace>:<x> <y> <z>" is not needed, the message
# is "x y z" in the dimension of the command's source.
PRESS_EVENT = "portkit:button_press"


def component(namespace: str) -> str:
    return f"{namespace}:portkit_button"


def table_path(namespace: str) -> str:
    return f"scripts/portkit/data/{namespace}_buttons.js"


def _int(a) -> int | None:
    return a if isinstance(a, int) and not isinstance(a, bool) else None


def set_type_button(v) -> tuple[bool | None, str | None, str]:
    """(arrows press it, click family, where) of a set type: a vanilla
    ``BlockSetType`` constant (:data:`block_set_types.BUTTON_TYPES`), or one
    built in code with ``new BlockSetType(...)`` (Fabric API's
    ``BlockSetTypeBuilder`` builds one) whose arguments are the one-argument
    constructor's name, or vanilla constants (``0``/``1``,
    ``SoundEvents.<family>_BUTTON_CLICK_OFF/_ON``) and components of a
    vanilla constant (``BlockSetType.STONE.canButtonBeActivatedByArrows()``,
    ``.buttonClickOn()``: what ``BlockSetTypeBuilder.copyOf`` copies). In the
    1.20.1 constructor arrows is None (the button carries it). The family is
    None when it can't be read."""
    types = block_set_types.BUTTON_TYPES
    if isinstance(v, blockcode.Const):
        if v.owner != block_set_types.CLASS or v.name not in types:
            return None, None, ""
        return types[v.name][0], types[v.name][1], f"BlockSetType.{v.name}"
    ctor = v.fields.get("__vanilla_ctor") if isinstance(v, blockcode.Obj) else None
    if not ctor or ctor[0] != block_set_types.CLASS:
        return None, None, ""
    desc, args = ctor[1], ctor[2]
    if desc == block_set_types.ONE_ARG_CTOR:
        arrows, family = block_set_types.ONE_ARG_BUTTON
        return arrows, family, "new BlockSetType(String)"
    slots = block_set_types.BUTTON_CTORS.get(desc)
    if slots is None or len(args) <= max(s for s in slots if s is not None):
        return None, None, ""
    at_arrows, at_off, at_on = slots

    def part(a, comp):
        if isinstance(a, blockcode.Part) and a.name == comp and a.of.owner == block_set_types.CLASS \
                and a.of.name in types:
            return a.of.name
        return None

    arrows, arrows_from = None, ""
    if at_arrows is not None:
        a = args[at_arrows]
        if isinstance(a, bool) or (_int(a) is not None and a in (0, 1)):
            arrows, arrows_from = bool(a), str(bool(a)).lower()
        elif part(a, "canButtonBeActivatedByArrows"):
            k = part(a, "canButtonBeActivatedByArrows")
            arrows, arrows_from = types[k][0], f"BlockSetType.{k}.canButtonBeActivatedByArrows()"
        else:
            return None, None, ""
    families, clicks = [], []
    for at, comp, suffix in ((at_off, "buttonClickOff", "_BUTTON_CLICK_OFF"),
                             (at_on, "buttonClickOn", "_BUTTON_CLICK_ON")):
        a = args[at]
        if isinstance(a, blockcode.Const) and a.owner == block_set_types.SOUND_EVENTS \
                and a.name.endswith(suffix) and a.name[:-len(suffix)] in block_set_types.BUTTON_SOUNDS:
            families.append(a.name[:-len(suffix)])
            clicks.append(f"SoundEvents.{a.name}")
        elif part(a, comp):
            k = part(a, comp)
            families.append(types[k][1])
            clicks.append(f"BlockSetType.{k}.{comp}()")
        else:
            return None, None, ""
    if families[0] != families[1]:
        return None, None, ""
    where = "new BlockSetType(" + ", ".join(x for x in (arrows_from, *clicks) if x) + ")"
    return arrows, families[0], where


def read(reading) -> tuple[dict | None, str]:
    """The button's facts from a :class:`blockcode.DirStateReading` read as
    vanilla ``ButtonBlock``: ({"ticks", "arrows", "family", "from"}, "") or
    (None, why it stays residue). Its registration may build the block on
    more than one way through branches the reader can't decide (one object
    per way); the facts must be the same on every way."""
    cls = reading.cls
    if reading.button_overrides:
        return None, (f"button: its class {cls} overrides vanilla ButtonBlock behaviour "
                      f"({', '.join(reading.button_overrides)}), which is its own code")
    if reading.button_why:
        return None, f"button: {reading.button_why}"
    ctors = list(getattr(reading, "button_ctors", None) or [reading.button_ctor])
    got = [_read_one(cls, c) for c in ctors]
    for facts, why in got:
        if facts is None:
            return None, why
    distinct = {(f["ticks"], f["arrows"], f["family"]) for f, _ in got}
    if len(distinct) > 1:
        ticks = sorted({t for t, _, _ in distinct})
        arrows = sorted({a for _, a, _ in distinct})
        families = sorted({f for _, _, f in distinct})
        what = []
        if len(ticks) > 1:
            what.append("press time " + ", ".join(map(str, ticks)) + " ticks")
        if len(arrows) > 1:
            what.append("whether arrows press it")
        if len(families) > 1:
            what.append("click sounds " + ", ".join(f.lower() for f in families))
        return None, (f"button: its registration builds it on {len(ctors)} ways through branches the reader "
                      f"can't decide, and they disagree ({'; '.join(what)}), so which one the game makes isn't "
                      "known (no DEFAULT, #87)")
    return got[0][0], ""


def _read_one(cls: str, ctor) -> tuple[dict | None, str]:
    """One ButtonBlock constructor call's facts, as :func:`read`."""
    if not ctor or ctor[0] != block_set_types.BUTTON_CLASS:
        return None, (f"button: {cls} reaches vanilla ButtonBlock, but the ButtonBlock constructor call "
                      "isn't read, so its press time and set type aren't known")
    slots = block_set_types.BUTTON_BLOCK_CTORS.get(ctor[1])
    args = ctor[2]
    if slots is None or len(args) <= max(s for s in slots if s is not None):
        return None, f"button: {cls} calls ButtonBlock{ctor[1]}, a constructor this doesn't read"
    at_set, at_ticks, at_arrows = slots
    ticks = _int(args[at_ticks])
    if ticks is None or not 1 <= ticks <= 1024:
        # ButtonBlock's codec: ticks_to_stay_pressed Codec.intRange(1, 1024) (1.21.1).
        return None, (f"button: {cls}'s press time (ButtonBlock's ticksToStayPressed) isn't an int literal "
                      "read here, so how long it stays pressed isn't known (no DEFAULT, #87)")
    arrows, family, where = set_type_button(args[at_set])
    if family is None:
        return None, (f"button: {cls}'s BlockSetType isn't a vanilla constant or a set type built in code "
                      "read here, so whether arrows press it and its click sounds aren't known (#280)")
    if at_arrows is not None:
        a = args[at_arrows]
        if isinstance(a, bool) or (_int(a) is not None and a in (0, 1)):
            arrows = bool(a)
            where = f"{where}, arrowsCanPress {str(arrows).lower()}"
        else:
            return None, (f"button: {cls}'s arrowsCanPress (1.20 ButtonBlock) isn't a literal read here")
    if arrows is None:
        return None, f"button: whether arrows press {cls} isn't read"
    return {"ticks": ticks, "arrows": arrows, "family": family,
            "from": f"{cls} new ButtonBlock({where}, {ticks} ticks)"}, ""


def attached_face(java_key: tuple) -> str:
    """The Bedrock face of the button touching the block it hangs on, from
    its Java (face, facing): ``getConnectedDirection`` is UP on the floor,
    DOWN on the ceiling and ``facing`` on a wall, and the block powered
    directly is the neighbour on the other side of that direction."""
    face, facing = java_key
    if face == "floor":
        return "down"
    if face == "ceiling":
        return "up"
    return {"north": "south", "south": "north", "east": "west", "west": "east"}[facing]


def table(namespace: str, result, records: list[dict]) -> None:
    """The button runtime's data table and the runtime, when a button converted."""
    from .station_kit import js_module, runtime_source

    rows = {}
    for r in records:
        b = r["button"]
        on, off, on_pitch, off_pitch = block_set_types.BUTTON_SOUNDS[b["family"]]
        rows[f"{namespace}:{r['name']}"] = {
            "ticks": b["ticks"], "arrows": b["arrows"],
            "on_sound": on, "off_sound": off, "on_pitch": on_pitch, "off_pitch": off_pitch,
        }
    if not rows:
        return
    header = ("// Read by the fixed runtime scripts/portkit/button.js (portkit/runtime): per button its press "
              "time in ticks, whether arrows press it and its clicks, read from its code (see the notes).")
    result.files[table_path(namespace)] = js_module(header, {
        "component": component(namespace),
        "powered": f"{namespace}:powered",
        "press_event": PRESS_EVENT,
        "buttons": rows,
    })
    result.files[BUTTON_RUNTIME] = runtime_source("button.js")
    result.files[BUTTON_CORE] = runtime_source("button_core.js")


def notes(records: list[dict]) -> list[str]:
    out = []
    for r in records:
        b = r["button"]
        who = "a hand or an arrow" if b["arrows"] else "a hand (not arrows)"
        out.append(
            f"{r['name']}: button pressed by {who}, read from its code ({b['from']}): it gives redstone power 15 "
            f"while pressed (the block it hangs on strongly) and releases {b['ticks']} ticks after the press"
            + (", staying pressed while an arrow is in it, as Java" if b["arrows"] else ", as Java")
            + f", with {b['family'].lower().replace('_', ' ')} button clicks. Not carried: explosions pressing it, "
            "the support rule (Java pops a button whose block is gone), game events (sculk sensors). An arrow "
            "presses it when it hits the button (Bedrock's projectile hit event), not when it enters the shape.")
    return out
