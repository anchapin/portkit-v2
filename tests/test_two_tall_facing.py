"""Two-tall blocks with a facing, and adapter precedence over them (#296).

Slice 1a's remaining state set: a two-tall block whose blockstate draws
``half`` and ``facing`` (the Botania / Biomes O' Plenty / Immersive
Engineering share of the board's ~70 half-keyed files; Waystones' 42 are
the adapter's). The generic converter writes it on the multi_block trait
with the facing on placement_direction, exactly as a door's halves are
written — unless an adapter stakes the block, in which case no generic
reader may convert it (Alex's adapter-precedence decision, 2026-11-13).

Offline: the example mod is written into ``tmp_path`` with hand-written
models carrying their own elements (no template fetch), following
tests/test_doors.py's fixture shape.
"""
from __future__ import annotations

import json
from pathlib import Path

from portkit import adapters
from portkit.converters import blocks, doors
from portkit.model import SourceMod

ROOT = Path(__file__).resolve().parents[1]
PNG = ROOT / "fixtures" / "agent_mod" / "input" / "assets" / "examplemod" / "textures" / "block" / "alloy_block.png"
NS = "examplemod"
CARDINALS = ("north", "east", "south", "west")
_Y = {"east": 0, "south": 90, "west": 180, "north": 270}


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(body, bytes):
        path.write_bytes(body)
    else:
        path.write_text(body if isinstance(body, str) else json.dumps(body))


def _wall_bloom(root: Path, name: str, ns: str = NS) -> None:
    """A two-tall block drawing half x facing (8 variants, quarter turns)."""
    variants = {}
    for half in ("lower", "upper"):
        for facing in CARDINALS:
            variants[f"facing={facing},half={half}"] = {
                "model": f"{ns}:block/{name}_{half}", "y": _Y[facing]}
    _write(root, f"assets/{ns}/blockstates/{name}.json", {"variants": variants})
    for part in ("lower", "upper"):
        _write(root, f"assets/{ns}/textures/block/{name}_{part}.png", PNG.read_bytes())
        _write(root, f"assets/{ns}/models/block/{name}_{part}.json",
               {"textures": {"cross": f"{ns}:block/{name}_{part}"},
                "elements": [{"from": [0.8, 0, 8], "to": [15.2, 16, 8], "shade": False,
                              "faces": {"north": {"uv": [0, 0, 16, 16], "texture": "#cross"},
                                        "south": {"uv": [0, 0, 16, 16], "texture": "#cross"}}}]})
    _write(root, f"assets/{ns}/lang/en_us.json", {f"block.{ns}.{name}": name})


def _mod(root: Path) -> SourceMod:
    return SourceMod(root=root, namespace=NS)


# -- detection ---------------------------------------------------------------

def test_two_tall_facing_variants_need_all_eight():
    blockstate = {"variants": {
        f"facing={f},half={h}": {"model": "a", "y": _Y[f]}
        for h in ("lower", "upper") for f in CARDINALS}}
    turned, why = doors.two_tall_facing_variants(blockstate)
    assert why == "" and turned is not None and len(turned) == 8
    assert turned[("lower", "east")] == ("a", 0, False)
    del blockstate["variants"]["facing=west,half=upper"]
    assert doors.two_tall_facing_variants(blockstate) == (None, "")
    # The half-only shape stays the plain two-tall reader's, not this one's.
    assert doors.two_tall_facing_variants(
        {"variants": {"half=lower": {"model": "a"}, "half=upper": {"model": "b"}}}) == (None, "")


# -- conversion ----------------------------------------------------------------

def test_two_tall_facing_block_converts(tmp_path):
    root = tmp_path / "src"
    _wall_bloom(root, "wall_bloom")
    result = blocks.convert(_mod(root))
    assert "blocks/wall_bloom.json" in result.files
    block = result.files["blocks/wall_bloom.json"]["minecraft:block"]
    traits = block["description"]["traits"]
    assert traits["minecraft:multi_block"] == {
        "enabled_states": ["minecraft:multi_block_part"], "direction": "up", "parts": 2}
    assert traits["minecraft:placement_direction"] == {
        "enabled_states": ["minecraft:cardinal_direction"]}
    # One permutation per (half, facing) pair.
    assert len(block["permutations"]) == 8
    conditions = {p["condition"] for p in block["permutations"]}
    assert any("multi_block_part') == 1" in c and "cardinal_direction') == 'east'" in c
               for c in conditions)
    assert "models/blocks/wall_bloom_lower.geo.json" in result.files
    assert "models/blocks/wall_bloom_upper.geo.json" in result.files
    assert result.paired_halves.get(f"{NS}:wall_bloom") == "half"


# -- adapter precedence ----------------------------------------------------------

def test_adapter_claim_keeps_the_block_residue(tmp_path, monkeypatch):
    root = tmp_path / "src"
    _wall_bloom(root, "wall_bloom")
    staking = adapters.Adapter(
        name="example", namespaces=frozenset({NS}),
        block_claims=lambda mod: {"wall_bloom": "the example adapter stakes wall_bloom"})
    monkeypatch.setattr(adapters, "ADAPTERS", adapters.ADAPTERS + (staking,))
    result = blocks.convert(_mod(root))
    assert "blocks/wall_bloom.json" not in result.files
    hits = [u for u in result.unhandled if "wall_bloom" in u.source]
    assert hits and "stakes wall_bloom" in hits[0].reason


def test_unclaimed_block_still_converts_beside_a_claim(tmp_path, monkeypatch):
    root = tmp_path / "src"
    _wall_bloom(root, "wall_bloom")
    _wall_bloom(root, "free_bloom")
    staking = adapters.Adapter(
        name="example", namespaces=frozenset({NS}),
        block_claims=lambda mod: {"wall_bloom": "the example adapter stakes wall_bloom"})
    monkeypatch.setattr(adapters, "ADAPTERS", adapters.ADAPTERS + (staking,))
    result = blocks.convert(_mod(root))
    assert "blocks/wall_bloom.json" not in result.files
    assert "blocks/free_bloom.json" in result.files
