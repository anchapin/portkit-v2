"""The ``block`` residue class of a Chisel-shaped blockstate (#288).

A Chisel-style blockstate is a Forge 1.12 variation set: its ``variants``
are named looks ("cracked", "legacy"), not the block's states. Two refusals
used to land as the generic kind ``block``:

1. the generic multi-variant refusal (``portkit.converters.blocks``
   ``_single_model``: "block has N blockstate variant(s)"), which now becomes
   the explained kind ``named_variant_blockstate``;
2. the variations path's "no registered variation converts", which now
   becomes the explained kind ``unregistered_variations`` when the reading
   found no look of the blockstate registered as a block of its own.

A blockstate that states Java properties ("facing=north") is not a named
look: it stays the generic kind, with the reason it had.
"""
from __future__ import annotations

import json
from pathlib import Path

from portkit.agent.residue import SKIP_KINDS
from portkit.bytecode import ClassIndex
from portkit.converters import blocks
from portkit.converters.blocks import (
    NAMED_VARIANT_BLOCKSTATE,
    UNREGISTERED_VARIATIONS,
)
from portkit.model import SourceMod

CLASSES = Path(__file__).parent / "data" / "chisel" / "classes"
NS = "chisel"


def _build(tmp_path: Path, states: dict, ns: str = "examplemod") -> SourceMod:
    assets = tmp_path / "assets" / ns
    (assets / "blockstates").mkdir(parents=True, exist_ok=True)
    (assets / "models" / "block").mkdir(parents=True, exist_ok=True)
    (assets / "textures" / "block").mkdir(parents=True, exist_ok=True)
    for name, blockstate in states.items():
        (assets / f"blockstates/{name}.json").write_text(json.dumps(blockstate))
    (assets / "models" / "block" / "cube.json").write_text(json.dumps({
        "parent": "minecraft:block/cube_all", "textures": {"all": f"{ns}:block/steel_block"}}))
    (assets / "textures" / "block" / "steel_block.png").write_bytes(b"png")
    return SourceMod(root=tmp_path, namespace=ns)


def _residue(result, name):
    return [u for u in result.unhandled if u.source == f"assets/examplemod/blockstates/{name}.json"]


def test_named_looks_are_explained_residue(tmp_path):
    """A Forge-style variation set the converter can't turn into states."""
    mod = _build(tmp_path, {"steel_block": {"variants": {
        "cracked": {"model": "examplemod:block/cube"},
        "bricks-soft": {"model": "examplemod:block/cube"},
        "legacy": {"model": "examplemod:block/cube"}}}})
    result = blocks.convert(mod)
    assert result.files == {}
    [res] = _residue(result, "steel_block")
    assert res.kind == NAMED_VARIANT_BLOCKSTATE
    assert "named looks" in res.reason
    assert "cracked" in res.reason and "bricks-soft" in res.reason
    assert NAMED_VARIANT_BLOCKSTATE in SKIP_KINDS


def test_a_blockstate_of_java_properties_keeps_the_generic_kind(tmp_path):
    """A property-shaped blockstate is not a named look: it stays ``block``."""
    mod = _build(tmp_path, {"steel_block": {"variants": {
        "facing=north": {"model": "examplemod:block/cube"},
        "facing=south": {"model": "examplemod:block/cube"}}}})
    result = blocks.convert(mod)
    [res] = _residue(result, "steel_block")
    assert res.kind == "block"
    assert "facing (north, south)" in res.reason


def test_a_mixed_blockstate_keeps_the_generic_kind(tmp_path):
    """A blockstate that names a property as well as a look is not a set of
    named looks, so the generic reason stands."""
    mod = _build(tmp_path, {"steel_block": {"variants": {
        "cracked": {"model": "examplemod:block/cube"},
        "facing=north": {"model": "examplemod:block/cube"}}}})
    result = blocks.convert(mod)
    [res] = _residue(result, "steel_block")
    assert res.kind == "block"
    assert "block has 2 blockstate variant(s)" in res.reason


def test_a_multipart_blockstate_keeps_the_generic_kind(tmp_path):
    mod = _build(tmp_path, {"steel_block": {"multipart": [
        {"when": {"north": "true"}, "apply": {"model": "examplemod:block/cube"}}]}})
    result = blocks.convert(mod)
    [res] = _residue(result, "steel_block")
    assert res.kind == "block"
    assert "multipart" in res.reason


def test_a_variation_set_with_no_registered_look_is_explained(tmp_path):
    """The Chisel fixture: a block whose class offers no variations, so the
    code registers no look of its blockstate (the adapter says why)."""
    import test_chisel_variations as chisel_tests

    mod = chisel_tests._mod(tmp_path)
    result = blocks.convert(mod)
    [res] = [u for u in result.unhandled if u.source == "assets/chisel/blockstates/carpet_white.json"]
    assert res.kind == UNREGISTERED_VARIATIONS
    assert "no look of this blockstate registered" in res.reason
    assert "BlockCarvableCarpet" in res.reason
    assert UNREGISTERED_VARIATIONS in SKIP_KINDS


def test_the_reading_that_cannot_be_followed_is_not_a_claim(tmp_path):
    """A block the mod's code registers is a real block: its blockstate keeps
    the residue it had, under the named-look kind."""
    import test_chisel_variations as chisel_tests

    mod = chisel_tests._mod(tmp_path)
    result = blocks.convert(mod)
    [res] = [u for u in result.unhandled if u.source == "assets/chisel/blockstates/auto_chisel.json"]
    assert res.kind == NAMED_VARIANT_BLOCKSTATE
    assert "named looks" in res.reason
    assert not any(p.startswith("blocks/auto_chisel") for p in result.files)
    assert ClassIndex.from_source(CLASSES) is not None
