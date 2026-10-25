"""Held states (#296): an enum state the player doesn't set on placement.

A blockstate that draws placement states (``facing`` over the four
horizontals, or ``axis``) and one more state whose values are not booleans
(a hollow log's ``variant``: empty, moss, snow...), or that draws one enum
state alone (a device's ``state``: idle, active...), is read from the
block's code: the value Java starts that state at (``getStateForPlacement`` on every
path, else the registered default state, as #215 item 2 reads a boolean's
start) and the methods that change it later. When the start is read, the
blockstate is held at it: only the variants at the start value are kept, the
state is dropped from their keys, and what is left goes to the converters
that read placement states alone (pillars, facing blocks), or, for an enum
drawn alone, to the stateless block path. The other values'
models are read and named in a note, not drawn (#215 item 6: everything the
code changes after placement is static at the start value). Nothing is held
at a value the code doesn't give (#87): an unread start leaves the
blockstate as it was.

A block's own ``shape`` enum (a railing's short/tall/connected, a vine's
bottom/middle/top, set from its neighbours) is held like any other enum
when no ``half`` is beside it: the stairs reader draws ``shape`` only with
``half``. Booleans beside the enum (not named for a direction: those are
connections, #221) are left in the blockstate for the boolean readers
(#215, #384), which read their own starts.
"""
from __future__ import annotations

from .. import blockcode

PLACEMENT_STATES = ("axis", "facing")
_CARDINALS = {"north", "east", "south", "west"}
_BOOLS = {"true", "false"}
# Booleans named for a direction are connection states (#221).
_CONNECTIONS = {"north", "east", "south", "west", "up", "down"}
# States other readers own as placement or shape: attach-face blocks
# (``face``), slabs and vertical slabs (``type``), stairs, doors, trapdoors
# and two-tall blocks (``half``, ``shape``, ``hinge``), beds (``part``).
PLACEMENT_OWNED = {"face", "type", "half", "shape", "hinge", "part"}
_PLACEMENT_OWNED = PLACEMENT_OWNED


def held_prop(blockstate: dict) -> tuple[str, tuple] | None:
    """(state, values) when ``blockstate`` is a variants map over placement
    states (none, for an enum whose values aren't numbers), exactly one
    non-boolean state and any booleans not named for a direction (left to
    the boolean readers once the enum is held), every combination named;
    else None."""
    variants = blockstate.get("variants")
    if not isinstance(variants, dict) or len(variants) < 2:
        return None
    props: dict[str, set] = {}
    cells = []
    for key in variants:
        pairs = [p.split("=", 1) for p in key.split(",") if p]
        if not pairs or any(len(p) != 2 for p in pairs):
            return None
        cell = {a.strip(): b.strip() for a, b in pairs}
        cells.append(cell)
        for a, b in cell.items():
            props.setdefault(a, set()).add(b)
    rest = [p for p in props if p not in PLACEMENT_STATES]
    enums = [p for p in rest if not props[p] <= _BOOLS]
    flags = [p for p in rest if props[p] <= _BOOLS]
    # A ``shape`` beside no ``half`` is not a stair's shape: the stairs
    # reader draws ``shape`` only with ``half``, so a block's own ``shape``
    # enum (a railing's short/tall/connected, set from its neighbours) is
    # held like any other enum.
    owned = _PLACEMENT_OWNED if "half" in props else _PLACEMENT_OWNED - {"shape"}
    if len(enums) != 1 or enums[0] in owned or len(props[enums[0]]) < 2:
        return None
    if any(f in _CONNECTIONS or f == "waterlogged" for f in flags):
        # A direction-named boolean is a connection (#221's multipart
        # reader); a held block keeps no water (#383 item 4).
        return None
    alone = not any(p in PLACEMENT_STATES for p in props)
    if alone and any(v.lstrip("-").isdigit() for v in props[enums[0]]):
        # An enum drawn alone (or beside booleans the boolean readers take
        # once it is held) is held as it is beside a placement state; a
        # number drawn alone (a crop's age, a pile's layers) is not: no
        # approved rule holds a count at its start.
        return None
    if len(props) == 1 and len({repr(v) for v in variants.values()}) == 1:
        # Every value draws the same look: nothing to hold (the blocks
        # converter takes it as that one look).
        return None
    if "facing" in props and not props["facing"] <= _CARDINALS:
        return None
    if "axis" in props and "facing" in props:
        return None
    if any(set(c) != set(props) for c in cells):
        return None
    combos = 1
    for values in props.values():
        combos *= len(values)
    if combos != len(variants):
        return None
    prop = enums[0]
    return prop, tuple(sorted(props[prop]))


def hold(blockstate: dict, prop: str, value: str) -> tuple[dict | None, list[str]]:
    """(the blockstate held at ``prop`` = ``value``, the models only the
    other values draw); (None, []) when no variant has that value."""
    kept, others = {}, []
    for key, entry in blockstate["variants"].items():
        pairs = [tuple(x.strip() for x in p.split("=", 1)) for p in key.split(",") if p]
        cell = dict(pairs)
        rest = ",".join(f"{a}={b}" for a, b in pairs if a != prop)
        if cell[prop] == value:
            kept[rest] = entry
        else:
            for e in entry if isinstance(entry, list) else [entry]:
                m = e.get("model") if isinstance(e, dict) else None
                if isinstance(m, str):
                    others.append(m)
    if not kept:
        return None, []
    drawn = set()
    for entry in kept.values():
        for e in entry if isinstance(entry, list) else [entry]:
            if isinstance(e, dict) and isinstance(e.get("model"), str):
                drawn.add(e["model"])
    out = dict(blockstate)
    out["variants"] = kept
    return out, sorted(set(others) - drawn)


def read(mod, loaded: dict, skip, shared=None) -> dict:
    """{stem: (reading, values)} for every blockstate of ``loaded`` with a
    held-state shape (``skip``: names another reader owns)."""
    props = {}
    for stem, blockstate in loaded.items():
        if stem in skip:
            continue
        found = held_prop(blockstate)
        if found is not None:
            props[stem] = found
    if not props:
        return {}
    readings = blockcode.read_held_states(getattr(mod, "classes", None),
                                          {n: p for n, (p, _) in props.items()},
                                          run=shared() if shared else None)
    return {n: (readings[n], props[n][1]) for n in props}


def note(name: str, reading, values: tuple, passed_over: list[str]) -> str:
    others = [v for v in values if v != reading.value]
    changed = ", ".join(reading.changed_by) if reading.changed_by else "no method of the block's own classes"
    looks = ", ".join(m.split("/")[-1] for m in passed_over) or "no other model"
    return (f"{name}: Java's {reading.prop} starts at {reading.value} ({reading.kind}: {reading.source}) "
            f"and is changed by {changed}; Bedrock holds it at {reading.value}, so "
            f"{', '.join(others)} ({looks}) aren't drawn")


def refusal(reading, values: tuple) -> str:
    """The residue reason when the start isn't read."""
    return (f"held state: {reading.prop} ({', '.join(values)}) isn't set by the player on placement "
            f"and its start isn't read: {reading.why}")
