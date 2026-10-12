"""Do the block states on an agent-written block come from its Java blockstate? (#149)

On storage drawers and waystones residue GLM 5.3 wrote block states and
permutations as integer enums where the Java blockstate names its values
(``facing=north`` became a made-up ``0/1/2`` mapping), and used state values
the Java blockstate never lists. The structural validator can't know that, and
none of the other guards read block states.

So the residue agent holds the blocks it writes to a deterministic rule, in the
spirit of ``refs.py`` and ``stats.py``. When an agent-written ``minecraft:block``
has a Java blockstate file (``assets/<ns>/blockstates/<name>.json``):

- every *custom* state it declares in ``description.states`` must be a state
  the Java blockstate keys on (the Bedrock namespace dropped: ``ns:facing`` is
  Java's ``facing``), and every value one Java lists for that state;
- every ``q.block_state('<custom state>')`` in the file (permutation
  conditions, ``bone_visibility``, anywhere) must name such a state and, when
  compared with ``==`` or ``!=``, a value Java lists.

Values compare as Java writes them: ``"north"``, ``"0"``, ``"true"``. So an
integer standing for a named Java value (``facing`` as ``0..3``) is rejected,
while integers pass when Java itself uses them (``level=0..15``), and a Bedrock
``true`` matches Java's ``true``.

Vanilla ``minecraft:`` states are not the mod's: they come from Bedrock's block
traits, and they are exactly how the deterministic block converter maps Java
states (``facing`` to ``minecraft:cardinal_direction``, ``axis`` to
``minecraft:block_face``, side connections to ``minecraft:connection_*``). They
are accepted, but a value outside the trait's own set (``cardinal_direction ==
2``) is the same integer-enum fabrication and is rejected. A ``minecraft:``
state not listed in :data:`TRAIT_VALUES` is taken on faith.

A declared state named ``<prefix>_<javastate>`` (``waystones:portstone_half``
for Java's ``half``) counts as that Java state when it is a rename, not an
encoding: its suffix matches exactly one Java state, and the values it
declares are that state's values exactly, the same set and spelled as Java
names them (no integers, so a numeric Java state is never aliased). DeepSeek
wrote waystones portstones this way with the real ``lower``/``upper`` values
(an offline check of its output found 13); a renamed state invents nothing. A
``q.block_state()`` may use the alias only when ``description.states``
declares it and it passed. An alias with invented, missing or integer values,
one whose suffix matches two Java states, or one never declared is rejected.

A boolean Java state counts as both ``true`` and ``false`` even when a
multipart only tests one of them. A block with no Java blockstate under its name is not checked: there is
nothing to compare against. A state the Java blockstate never mentions (often
``waterlogged``, which no model depends on) is rejected even if the mod's code
has it; the agent reads only text files, so it could not have taken it from
the source.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

_VANILLA = "minecraft"

# The states Bedrock's block traits define, with the values each can take.
# These are what the deterministic converter emits (see converters/blocks.py).
_SIX = frozenset({"down", "up", "north", "south", "east", "west"})
_BOOL = frozenset({"true", "false"})
TRAIT_VALUES: dict[str, frozenset[str]] = {
    "minecraft:cardinal_direction": frozenset({"north", "south", "east", "west"}),
    "minecraft:facing_direction": _SIX,
    "minecraft:block_face": _SIX,
    "minecraft:vertical_half": frozenset({"bottom", "top"}),
    **{f"minecraft:connection_{d}": _BOOL for d in ("north", "east", "south", "west")},
}

# q.block_state('name') or query.block_state("name"), optionally compared.
_BLOCK_STATE = re.compile(
    r"""(?:q|query)\.block_state\(\s*(['"])([^'"]+)\1\s*\)"""
    r"""(?:\s*(==|!=)\s*(?:'([^']*)'|"([^"]*)"|(-?\d+(?:\.\d+)?)|(true|false)))?"""
)


@dataclass(frozen=True)
class BadState:
    path: str  # the pack file, relative to the output tree
    block: str  # the block identifier
    where: str  # "description.states" or the JSON path of a Molang string
    state: str  # the state as written, e.g. "storagedrawers:facing"
    value: str | None  # the offending value, or None when the name itself is unknown
    java: str  # what Java has: the blockstate file, or the trait
    allowed: tuple[str, ...]  # the names (value None) or values Java allows
    alias_of: tuple[str, ...] = ()  # the Java state(s) a rejected ``<prefix>_<state>`` name suffix-matches

    def describe(self) -> str:
        if self.value is None:
            return f"{self.path} {self.where}: state {self.state!r} ({self.block})"
        return f"{self.path} {self.where}: {self.state} = {self.value} ({self.block})"


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _norm(value) -> str:
    """A value as Java's blockstate would spell it."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip().lower()


# -- what Java has ---------------------------------------------------------

def _variant_key(key: str, into: dict[str, set[str]]) -> None:
    for pair in key.split(","):
        name, sep, value = pair.partition("=")
        if sep and name.strip():
            into.setdefault(name.strip(), set()).add(value.strip().lower())


def _when(clause, into: dict[str, set[str]]) -> None:
    if isinstance(clause, list):
        for entry in clause:
            _when(entry, into)
        return
    if not isinstance(clause, dict):
        return
    for key, value in clause.items():
        if key in ("OR", "AND"):
            _when(value, into)
        else:
            into.setdefault(key, set()).update(v.strip().lower() for v in _norm(value).split("|"))


def java_states(blockstate: dict) -> dict[str, set[str]]:
    """{state: values} the Java blockstate keys on (variants, multipart, forge)."""
    found: dict[str, set[str]] = {}
    variants = blockstate.get("variants")
    if isinstance(variants, dict):
        forge = "forge_marker" in blockstate
        for key, entry in variants.items():
            if "=" in key:
                _variant_key(key, found)
            elif forge and isinstance(entry, dict) and entry and all(isinstance(v, dict) for v in entry.values()):
                # Forge blockstate v1: "facing": {"north": {...}, "south": {...}}
                found.setdefault(key, set()).update(str(v).strip().lower() for v in entry)
    for part in blockstate.get("multipart") or []:
        if isinstance(part, dict):
            _when(part.get("when"), found)
    # A multipart only spells the values that add a part: ``"lit": "true"``
    # never lists false, yet the state is a boolean and Bedrock must declare
    # both. The other half of a boolean is not an invention.
    for values in found.values():
        if values and values <= _BOOL:
            values.update(_BOOL)
    return found


def blockstate_file(source_root: Path, identifier: str) -> Path | None:
    """The Java blockstate for a Bedrock block id: same namespace first, then
    the one namespace that has a blockstate of that name, if exactly one does."""
    ns, _, name = identifier.partition(":")
    if not name:
        return None
    assets = source_root / "assets"
    direct = assets / ns / "blockstates" / f"{name}.json"
    if direct.is_file():
        return direct
    found = sorted(assets.glob(f"*/blockstates/{name}.json")) if assets.is_dir() else []
    return found[0] if len(found) == 1 else None


# -- what the block claims ---------------------------------------------------

def _declared_values(spec) -> list | None:
    """The values one ``description.states`` entry lists, or None if unreadable."""
    if isinstance(spec, list):
        return spec
    if isinstance(spec, dict):
        values = spec.get("values")
        if isinstance(values, dict):
            lo, hi = values.get("min"), values.get("max")
            if isinstance(lo, int) and isinstance(hi, int) and not isinstance(lo, bool) and hi - lo <= 1024:
                return list(range(lo, hi + 1))
        if isinstance(values, list):
            return values
    return None


def _strings(node, where: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(node, str):
        yield where or "(value)", node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(value, f"{where}.{key}" if where else str(key))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _strings(value, f"{where}[{i}]")


def _bare(state: str) -> str:
    return state.split(":", 1)[1] if ":" in state else state


_INTEGER = re.compile(r"-?\d+")


def _suffix_matches(name: str, java: dict[str, set[str]]) -> list[str]:
    """The Java states ``name`` could be a ``<prefix>_<state>`` rename of."""
    return sorted(j for j in java if name.endswith("_" + j) and len(name) > len(j) + 1)


def _same_named_values(values: list | None, java_values: set[str]) -> bool:
    """The declared values are exactly Java's, and none is an integer code."""
    if not values:
        return False
    for value in values:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return False
        if _INTEGER.fullmatch(_norm(value)):
            return False
    return {_norm(v) for v in values} == java_values


def invented_states_in(out_tree: Path, rel: str, source_root: Path) -> list[BadState]:
    """Block states in one pack block file that its Java blockstate doesn't have."""
    data = _load(out_tree / rel)
    if not isinstance(data, dict) or not isinstance(data.get("minecraft:block"), dict):
        return []
    body = data["minecraft:block"]
    description = body.get("description") if isinstance(body.get("description"), dict) else {}
    ident = description.get("identifier")
    if not isinstance(ident, str):
        return []
    java_file = blockstate_file(source_root, ident)
    blockstate = _load(java_file) if java_file else None
    java = java_states(blockstate) if isinstance(blockstate, dict) else None
    java_rel = java_file.relative_to(source_root).as_posix() if java_file else ""
    bad: list[BadState] = []
    aliases: dict[str, str] = {}  # a declared ``<prefix>_<state>`` rename -> Java's state

    def check(where: str, state: str, value) -> None:
        if state.split(":", 1)[0] == _VANILLA:
            allowed = TRAIT_VALUES.get(state)
            if allowed is not None and value is not None and _norm(value) not in allowed:
                bad.append(BadState(rel, ident, where, state, _norm(value), "Bedrock's trait", tuple(sorted(allowed))))
            return
        if java is None:
            return  # no Java blockstate to compare against
        name = _bare(state)
        if name not in java and state in aliases:
            name = aliases[state]
        if name not in java:
            bad.append(BadState(rel, ident, where, state, None, java_rel, tuple(sorted(java))))
        elif value is not None and _norm(value) not in java[name]:
            bad.append(BadState(rel, ident, where, state, _norm(value), java_rel, tuple(sorted(java[name]))))

    states = description.get("states")
    if isinstance(states, dict):
        for state, spec in states.items():
            if not isinstance(state, str):
                continue
            values = _declared_values(spec)
            if java is not None and state.split(":", 1)[0] != _VANILLA and _bare(state) not in java:
                matches = _suffix_matches(_bare(state), java)
                if len(matches) == 1 and _same_named_values(values, java[matches[0]]):
                    aliases[state] = matches[0]
                elif matches:
                    bad.append(BadState(rel, ident, "description.states", state, None, java_rel,
                                        tuple(sorted(java)), tuple(matches)))
                    continue
            before = len(bad)
            check("description.states", state, None)
            if len(bad) == before:  # a known name: now each value
                for value in values or []:
                    check("description.states", state, value)

    seen: set[tuple[str, str, str | None]] = set()
    for where, text in _strings(body, "minecraft:block"):
        for match in _BLOCK_STATE.finditer(text):
            state = match.group(2)
            value = next((g for g in match.groups()[3:] if g is not None), None)
            if (where, state, value) in seen:
                continue
            seen.add((where, state, value))
            check(where, state, value)
    return bad


# -- the check ---------------------------------------------------------

def invented_states(out_tree: Path, written: list[str], source_root: Path) -> list[BadState]:
    """Block states in the blocks listed in ``written`` that Java doesn't have."""
    bad: list[BadState] = []
    for rel in sorted({r.replace("\\", "/") for r in written}):
        if rel.startswith("behavior_pack/") and rel.endswith(".json") and (out_tree / rel).is_file():
            bad.extend(invented_states_in(out_tree, rel, source_root))
    return bad


def finding(bad: BadState) -> dict:
    """The validate-tool finding for one invented state or value, as the agent sees it."""
    allowed = ", ".join(bad.allowed) or "none"
    if bad.value is None:
        message = (
            f"{bad.where}: block state {bad.state!r} on {bad.block} is not a state {bad.java} "
            f"has (it has: {allowed}). Use the Java blockstate's own state names, namespaced, "
            "or a Bedrock trait state for placement (minecraft:cardinal_direction, "
            "minecraft:block_face, ...); never invent a state."
        )
        if len(bad.alias_of) > 1:
            message += (f" {bad.state!r} could be a rename of any of {', '.join(bad.alias_of)}, "
                        "so it is not accepted as one.")
        elif bad.alias_of:
            java_state = bad.alias_of[0]
            message += (f" A renamed {java_state!r} passes only when it declares exactly "
                        f"{java_state}'s values as Java names them, no integers; better, use "
                        f"{java_state!r} itself.")
    else:
        message = (
            f"{bad.where}: {bad.state} = {bad.value!r} on {bad.block}, but {bad.java} only has "
            f"{allowed} for it. Write the values exactly as Java names them (no integer codes "
            "for named values); never invent a value."
        )
    return {"path": bad.path, "rule": "agent.invented_state", "message": message, "severity": "error"}
