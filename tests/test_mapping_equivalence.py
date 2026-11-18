"""The #235 equivalence proof, measured: the same code renamed the way a
Forge (SRG) or a Fabric (intermediary) build renames it must give every
reader the same facts as its Mojang-named build.

``tests/test_name_mappings.py`` already checks that a renamed build reads the
same as the Mojang-named one (and that it reads nothing without the
remapper). This file is the measured form of that proof: it runs the reader
paths the brief names (facing, boolean, light, container) plus blocks and
entities on all three spellings, counts the facts compared per path and the
mismatches, and fails on any mismatch. The numbers it prints are the proof
quoted in the report.

The renaming is synthetic and offline: the repo's own javac fixture under
``tests/data/blockcode`` and ``tests/data/entitycode`` (Mojang names) is
rewritten the way a SRG or an intermediary build rewrites it, using the
repo's own renaming helper (:class:`test_name_mappings._Scheme`), and read
through a :class:`portkit.data.mappings.Remapper` built from the same table.
No jar is downloaded.

What this fixture can and cannot cover:

* it covers the reader paths a mod's own block classes drive: registration,
  placement and facing rules, boxes, collision, light, boolean states,
  containers and entities, read from the class files of one example mod;
* it cannot cover a real dual-published mod jar (that needs the network and
  the upstream mapping tables), the record components ``comp_N`` of a
  intermediary build, Forge 1.21+ / MCP-era names, the registration patterns
  the readers cannot follow whatever the names are (Registrate, Balm, owo,
  BCLib), or the corpus measurement on the real jars (the corpus jars live
  in the user's cache, not in the repo).
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from portkit import blockcode, entities
from portkit.data import mappings

from test_name_mappings import (BLOCK_NAMES, BOOLS, BLOCKS, MOBS, _index, _load,
                                _Scheme)

# The reader paths this file measures, with the arguments each one needs on
# the example mod's fixture. Every path must read something: a path that
# reads nothing would compare equal on any build and prove nothing.
HOPPER = ("down", "north", "south", "west", "east")

FACING_KINDS = {"spout": "facing", "ledge": "facing", "peg": "facing"}
FACING_VALUES = {"spout": HOPPER, "ledge": HOPPER, "peg": ("down", "up")}
DRAWN = {"toggle": {"lit"}}


def _readers(index) -> dict:
    """Every reader path the brief names, on one class index."""
    return {
        "blocks": blockcode.read_blocks(index, BLOCK_NAMES),
        "facing": blockcode.read_directional(index, FACING_KINDS, facings=FACING_VALUES),
        "boolean": blockcode.read_state_blocks(index, BOOLS),
        "light": blockcode.read_light(index, BLOCK_NAMES, DRAWN),
        "container": blockcode.read_containers(index, BLOCK_NAMES),
    }


def _entity_facts(index) -> dict:
    return dataclasses.asdict(entities.read(index))


# --- facts, counted ---------------------------------------------------------

def _facts(value, path: str = "") -> dict[str, object]:
    """Every leaf of a reading (or a dict of readings) as ``path -> value``."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        value = dataclasses.asdict(value)
    out: dict[str, object] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            out.update(_facts(item, f"{path}.{key}" if path else str(key)))
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            out.update(_facts(item, f"{path}[{i}]"))
    else:
        out[path] = value
    return out


_MISSING = object()


def _compare(want: dict[str, object], got: dict[str, object]) -> tuple[int, list[str]]:
    """(facts compared, mismatching paths) between two fact maps."""
    keys = set(want) | set(got)
    mismatches = [k for k in sorted(keys)
                  if want.get(k, _MISSING) != got.get(k, _MISSING)]
    return len(keys), mismatches


# --- the fixture -------------------------------------------------------------

@pytest.fixture(scope="module")
def block_raw():
    return _load(BLOCKS)


@pytest.fixture(scope="module")
def mojang_facts(block_raw):
    """The facts of the Mojang-named build: the reference every other
    spelling must give."""
    index = _index(block_raw, None, False)
    facts = {name: _facts(reading) for name, reading in _readers(index).items()}
    facts["entities"] = _facts(_entity_facts(_index(_load(MOBS), None, False)))
    return facts


# --- the equivalence ---------------------------------------------------------

@pytest.mark.parametrize("scheme", ["srg", "intermediary"])
def test_a_renamed_build_gives_the_same_facts_on_every_reader_path(
        block_raw, mojang_facts, scheme):
    """The measured proof of #235: on every reader path the fixture can
    exercise, a Forge (SRG) or a Fabric (intermediary) build of the same code
    gives exactly the facts its Mojang-named build gives."""
    renaming = _Scheme(block_raw, scheme)
    assert renaming.members
    index = _index(block_raw, renaming, True)
    got = {name: _facts(reading) for name, reading in _readers(index).items()}
    # The entity fixture is its own code: it is renamed by its own scheme.
    mob_raw = _load(MOBS)
    mob_renaming = _Scheme(mob_raw, scheme)
    assert mob_renaming.members
    got["entities"] = _facts(_entity_facts(_index(mob_raw, mob_renaming, True)))

    lines, total, mismatches_total = [], 0, 0
    for path in sorted(mojang_facts):
        compared, mismatches = _compare(mojang_facts[path], got[path])
        total += compared
        mismatches_total += len(mismatches)
        lines.append(f"{scheme:12} {path:10} facts compared {compared:5}  mismatches {len(mismatches)}")
        assert not mismatches, f"{path}: {mismatches[:5]}"
    print("\n" + "\n".join(lines))
    print(f"{scheme:12} {'TOTAL':10} facts compared {total:5}  mismatches {mismatches_total}")
    # The proof is only worth something if the paths read facts at all.
    assert total > 0


@pytest.mark.parametrize("scheme", ["srg", "intermediary"])
def test_the_fixture_reads_real_facts_and_the_remapper_is_what_reads_them(
        block_raw, mojang_facts, scheme):
    """The other half of the proof: the facts compared above are real ones,
    and they are read only through the remapper (without it the same build
    reads less, so equality is not a coincidence of empty readings)."""
    renaming = _Scheme(block_raw, scheme)
    blind = {name: _facts(reading)
             for name, reading in _readers(_index(block_raw, renaming, False)).items()}
    mob_raw = _load(MOBS)
    blind["entities"] = _facts(_entity_facts(_index(mob_raw, _Scheme(mob_raw, scheme), False)))
    for path, want in mojang_facts.items():
        compared, mismatches = _compare(want, blind[path])
        assert compared > 0
        assert mismatches, f"{path}: the blind build reads the same as the Mojang-named one"

    # The facts are the ones the Mojang-named build reads: a placement, a
    # facing rule, a light value and a container's slots.
    blocks = mojang_facts["blocks"]
    assert blocks["lamp.placement"] == 180
    assert mojang_facts["facing"]["spout.rule_from"] == \
        "com.example.deco.SpoutBlock#getStateForPlacement"
    assert mojang_facts["light"]["glow.value"] == 12
    assert mojang_facts["container"]["crate.slots"] == 27
    assert mojang_facts["entities"]
