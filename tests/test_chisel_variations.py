"""Named variations (#296): Chisel's Features builder chains, read by its
adapter (``portkit.adapters.chisel``), and the generic core pass
(``portkit.converters.variations``) that converts each registered variant.

The class files under tests/data/chisel/classes are javac 21 output
(tests/data/chisel/build.sh) of classes shaped as Chisel 1.12/dev's own:
``team.chisel.Features`` (constants with builder chains, a required mod, a
commented-out ANCIENT_STONE), the ``ChiselBlockFactory`` /
``ChiselBlockBuilder`` / ``VariationBuilder`` API and two block classes.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from portkit.adapters import chisel
from portkit.bytecode import ClassIndex
from portkit.converters import blocks
from portkit.converters.variations import CONDITIONAL_BLOCK
from portkit.model import SourceMod
from portkit.png import encode_png

CLASSES = Path(__file__).parent / "data" / "chisel" / "classes"
NS = "chisel"


def _png() -> bytes:
    return encode_png(1, 1, bytes([120, 120, 120, 255]))


def test_adapter_reads_the_chains():
    sets, problems = chisel.read(ClassIndex.from_source(CLASSES))
    assert problems == []
    # Java asks for the variant lowercased (1.12 ModelResourceLocation).
    assert [v.name for v in sets["andesite"].variations] == ["cracked", "bricks-soft", "circularct", "pillar",
                                                             "encased", "screenmetallic", "bricks"]
    assert {v.lang_key for v in sets["andesite"].variations} == {"tile.chisel.andesite.name"}
    assert not any(v.gate for v in sets["andesite"].variations)
    # setParentFolder moves the blockstate; the name keys the translation.
    assert [v.name for v in sets["metals/aluminum"].variations] == ["caution", "crate"]
    assert sets["metals/aluminum"].variations[0].lang_key == "tile.chisel.blockAluminum.name"
    # The creator/blockClass overload.
    assert [v.name for v in sets["marble"].variations] == ["raw", "a1-stonecarving"]
    # A required mod gates the feature.
    [blood] = sets["bloodmagic"].variations
    assert "'bloodmagic' is loaded" in blood.gate
    # A block class other than BlockCarvable offers no variations.
    assert sets["carpet_white"].variations == () and "BlockCarvableCarpet" in sets["carpet_white"].why
    assert "carpet_black" in sets
    # ANCIENT_STONE is commented out: nothing registers it.
    assert "ancient_stone" not in sets


def _forge(variants: dict, defaults: dict | None = None) -> dict:
    return {"forge_marker": 1, "defaults": defaults or {"model": "cube_all"}, "variants": variants}


def _tex(path: str) -> list:
    return [{"textures": {"all": f"chisel:blocks/{path}"}}]


def _mod(tmp_path: Path) -> SourceMod:
    root = tmp_path / "mod"
    a = root / "assets" / NS
    for sub in ("blockstates", "models/block", "lang", "textures/blocks/andesite", "textures/blocks/marble"):
        (a / sub).mkdir(parents=True)
    for t in ("andesite/cracked", "andesite/bricks-soft", "andesite/circular", "andesite/circular-ctm",
              "andesite/pillar-side", "andesite/pillar-top", "andesite/encased", "andesite/emboss",
              "andesite/encased-ctm", "marble/raw"):
        (a / f"textures/blocks/{t}.png").write_bytes(_png())
    (a / "textures/blocks/andesite/bricks.png").write_bytes(_png())
    (a / "textures/blocks/andesite/bricks.png.mcmeta").write_text(json.dumps({"villager": {}}))
    (a / "textures/blocks/andesite/encased.png.mcmeta").write_text(json.dumps(
        {"ctm": {"ctm_version": 1, "type": "ctm", "textures": ["chisel:blocks/andesite/encased-ctm"]}}))
    (a / "models/block/cube_ctm.json").write_text(json.dumps({
        "parent": "block/block", "textures": {"particle": "#all"},
        "elements": [{"from": [0, 0, 0], "to": [16, 16, 16],
                      "faces": {f: {"texture": "#all"} for f in ("down", "up", "north", "south", "west", "east")}}],
        "ctm_version": 1, "ctm_overrides": {"0": {"type": "ctm", "textures": ["#connected_tex"]}}}))
    states = {
        "andesite": _forge({
            "cracked": _tex("andesite/cracked"),
            "bricks-soft": _tex("andesite/bricks-soft"),
            "circularct": [{"model": "chisel:cube_ctm", "textures": {
                "all": "chisel:blocks/andesite/circular", "connected_tex": "chisel:blocks/andesite/circular-ctm"}}],
            "pillar": [{"model": "cube_column", "textures": {
                "side": "chisel:blocks/andesite/pillar-side", "end": "chisel:blocks/andesite/pillar-top"}}],
            "encased": _tex("andesite/encased"),
            "emboss": _tex("andesite/emboss"),
            "screenmetallic": _tex("andesite/cracked"),
            "bricks": _tex("andesite/bricks"),
        }),
        "ancient_stone": _forge({"cracked": _tex("andesite/cracked"), "raw": _tex("andesite/emboss")}),
        "bloodmagic": _forge({"brick": _tex("andesite/cracked")}),
        "carpet_white": _forge({"legacy": _tex("andesite/cracked")}),
        "marble": _forge({"raw": _tex("marble/raw")}),
    }
    for name, bs in states.items():
        (a / f"blockstates/{name}.json").write_text(json.dumps(bs))
    (a / "lang/en_us.lang").write_text(
        "# comment\ntile.chisel.andesite.name=Andesite\ntile.chisel.andesite.cracked.desc.1=Cracked\n"
        "tile.chisel.marble.name=Marble\n")
    (a / "lang/en_ud.lang").write_text("tile.chisel.andesite.name=ǝʇısǝpuⱯ\n")
    return SourceMod(root=root, namespace=NS, classes=ClassIndex.from_source(CLASSES), minecraft="1.12.2")


@pytest.fixture()
def converted(tmp_path):
    return blocks.convert(_mod(tmp_path))


def _residue(result, name):
    return [u for u in result.unhandled if u.source == f"assets/{NS}/blockstates/{name}.json"]


def test_registered_variations_convert(converted):
    files = converted.files
    for v in ("cracked", "bricks-soft", "pillar", "screenmetallic"):
        assert f"blocks/andesite_{v}.json" in files
    cracked = files["blocks/andesite_cracked.json"]["minecraft:block"]
    assert cracked["description"]["identifier"] == "chisel:andesite_cracked"
    assert cracked["components"]["minecraft:material_instances"] == {"*": {"texture": "chisel:andesite_cracked"}}
    pillar = files["blocks/andesite_pillar.json"]["minecraft:block"]["components"]["minecraft:material_instances"]
    assert pillar["up"] == {"texture": "chisel:andesite_pillar_top"}
    assert pillar["*"] == {"texture": "chisel:andesite_pillar_side"}
    # A mixed file counts as converted (pick 5a): no residue entry.
    assert _residue(converted, "andesite") == []
    # Connected textures (pick 3a), the unregistered variant, never shipped.
    for v in ("circularct", "encased", "emboss"):
        assert f"blocks/andesite_{v}.json" not in files
    [note] = [n for n in converted.notes if n.startswith("andesite:")]
    assert "circularct (connected_texture" in note and "encased (connected_texture" in note
    assert "not registered by the mod's code: emboss" in note
    # A texture the textures converter refuses: the variant is never emitted.
    assert "blocks/andesite_bricks.json" not in files
    assert "bricks (block: uses texture chisel:andesite_bricks, which did not convert" in note


def test_display_name_is_javas(converted):
    lang = converted.files["texts/en_US.lang"]
    assert "tile.chisel:andesite_cracked.name=Andesite\n" in lang
    assert "tile.chisel:marble_raw.name=Marble\n" in lang
    assert "Cracked" not in lang  # the tooltip is not part of the name (pick 2a)
    assert converted.files["texts/languages.json"] == ["en_US"]  # en_ud has no Bedrock slot


def test_left_variations(converted):
    files = converted.files
    # ANCIENT_STONE is commented out in Features: its blockstate keeps the old residue.
    [ancient] = _residue(converted, "ancient_stone")
    assert ancient.kind == "block" and "blockstate variant(s)" in ancient.reason
    assert not any(p.startswith("blocks/ancient_stone") for p in files)
    # Gated on another mod (pick 4a).
    [blood] = _residue(converted, "bloodmagic")
    assert blood.kind == CONDITIONAL_BLOCK and "'bloodmagic'" in blood.reason
    [carpet] = _residue(converted, "carpet_white")
    assert carpet.kind == "block" and "BlockCarvableCarpet" in carpet.reason
    # A registered variation the blockstate lacks is said; the file still converts.
    assert "blocks/marble_raw.json" in files and _residue(converted, "marble") == []
    [note] = [n for n in converted.notes if n.startswith("marble:")]
    assert "a1-stonecarving (block: the code registers it but the blockstate has no such variant" in note


def test_no_chisel_classes_no_variations(tmp_path):
    mod = _mod(tmp_path)
    plain = SourceMod(root=mod.root, namespace=NS, classes=None, minecraft="1.12.2")
    result = blocks.convert(plain)
    assert not any(p.startswith("blocks/andesite_") for p in result.files)
    [res] = _residue(result, "andesite")
    assert "blockstate variant(s)" in res.reason
