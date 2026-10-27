"""Layered block models (#296): Forge 1.12's ``forge:multi-layer`` and
NeoForge/Forge ``composite`` are merged exactly into one geometry.

tests/data/multilayer is written for these tests (not taken from any jar):
``layered`` is a frame (Solid) and glass (Cutout) block like Chisel's auto
chisel, ``holey`` the same with a solid texture that has holes, ``stained`` a
Solid beside a Translucent layer, ``stateful`` a variant no layer names;
``lantern`` a composite with a hidden translucent child and ``jar`` the same
child shown; ``shelled`` a composite with a solid core (its ``core.png`` has a
transparent border ring its faces' uv never samples) inside a translucent
shell, which draws wholly blend as the labelled DEFAULT (pick 1a). classes/ (``build.sh``) holds blocks answering Forge 1.12's
``canRenderInLayer``/``getBlockLayer`` in each shape the reader takes, and one
it doesn't.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from portkit import rendershape
from portkit.bytecode import ClassIndex
from portkit.converters import blocks, models, multilayer
from portkit.model import ConversionResult, SourceMod

DATA = Path(__file__).parent / "data" / "multilayer"
NS = "examplemod"
PKG = "com/example/layered/"


def _index() -> ClassIndex:
    root = DATA / "classes"
    return ClassIndex({p.relative_to(root).as_posix()[:-6]: p.read_bytes() for p in root.rglob("*.class")})


@pytest.fixture()
def mod(tmp_path) -> SourceMod:
    shutil.copytree(DATA / "assets", tmp_path / "mod" / "assets")
    m = SourceMod(root=tmp_path / "mod", namespace=NS)
    m.classes = _index()
    return m


def _blockstate(mod: SourceMod, name: str) -> dict:
    return json.loads((mod.assets / "blockstates" / f"{name}.json").read_text())


def _convert(mod: SourceMod, name: str, cls: str):
    """_convert_forge_multilayer with a registration run that built ``cls``
    as a 1.12 block (blockcode Machine.outside)."""
    result = ConversionResult()
    seen: set = set()
    run = (SimpleNamespace(outside={name: PKG + cls}), {})
    why = blocks._convert_forge_multilayer(mod, result, name, _blockstate(mod, name), {}, seen, run)
    blocks._one_render_method(result, {name: seen})
    return result, why, seen


def test_layers_read_from_code():
    index = _index()
    got = {cls: rendershape.read_layers_112(index, PKG + cls)[0]
           for cls in ("LayeredBlock", "PlainBlock", "GlassyBlock", "SwitchedBlock")}
    assert got["LayeredBlock"] == {"SOLID", "CUTOUT"}
    assert got["PlainBlock"] == {"SOLID"}       # Block: getBlockLayer() == layer, SOLID
    assert got["GlassyBlock"] == {"CUTOUT"}     # its own getBlockLayer
    assert got["SwitchedBlock"] is None
    assert "does more than compare" in rendershape.read_layers_112(index, PKG + "SwitchedBlock")[2]


def test_forge_layers(mod):
    layers, base, why = multilayer.forge_layers(mod, "layered", _blockstate(mod, "layered"))
    assert why == ""
    # base is no layer; "unknown" isn't a BlockRenderLayer name, so Forge drops it.
    assert [(layer.label, layer.render_type) for layer in layers] == [
        ("SOLID", "minecraft:solid"), ("CUTOUT", "minecraft:cutout")]
    assert layers[0].model == {"parent": "examplemod:block/layered/frame"}
    assert base == {"parent": "examplemod:block/layered/frame"}
    assert multilayer.is_forge_multilayer(_blockstate(mod, "layered"))
    assert not multilayer.is_forge_multilayer(_blockstate(mod, "lantern"))


def test_frame_and_glass_merge_into_one_block(mod):
    result, why, seen = _convert(mod, "layered", "LayeredBlock")
    assert why == ""
    geo = result.files["models/blocks/layered.geo.json"]
    cubes = geo["minecraft:geometry"][0]["bones"][0]["cubes"]
    assert len(cubes) == 3  # two frame boxes, one glass box
    instances = result.files["blocks/layered.json"]["minecraft:block"]["components"][
        "minecraft:material_instances"]
    # One render method for the block: the glass's, which draws the opaque
    # frame textures the same.
    assert {spec.get("render_method") for spec in instances.values()} == {"alpha_test"}
    # The two layers' "side" textures differ, so the glass one is renamed apart.
    assert {spec["texture"] for spec in instances.values()} >= {
        f"{NS}:frame", f"{NS}:side", f"{NS}:pane"}
    assert "cutout_side" in instances
    assert seen == {"minecraft:cutout"}
    claimed = {Path(p).as_posix().split("models/block/")[-1] for p in result.consumed}
    assert {"layered/frame.json", "layered/pane.json"} <= claimed
    note = next(n for n in result.notes if n.startswith("layered:"))
    assert "SOLID minecraft:solid, CUTOUT minecraft:cutout" in note and "no transparent pixel" in note


def test_layer_the_block_never_renders_in_is_not_drawn(mod):
    result, why, seen = _convert(mod, "layered", "PlainBlock")
    assert why == ""
    cubes = result.files["models/blocks/layered.geo.json"]["minecraft:geometry"][0]["bones"][0]["cubes"]
    assert len(cubes) == 2
    assert "CUTOUT layer model isn't drawn" in next(n for n in result.notes if n.startswith("layered:"))
    assert seen == {"minecraft:solid"}


def test_unread_layers_and_unreadable_mixes_give_reasons(mod):
    _r, why, _s = _convert(mod, "layered", "SwitchedBlock")
    assert "render layers the block draws in aren't read" in why
    result, why, _s = _convert(mod, "holey", "LayeredBlock")
    assert "has transparent pixels" in why and not result.files and not result.consumed
    _r, why, _s = _convert(mod, "stained", "LayeredBlock")
    assert "TRANSLUCENT" in why or "a layer the model doesn't name" in why
    _r, why, _s = _convert(mod, "stateful", "LayeredBlock")
    assert "facing=north" in why
    result = ConversionResult()
    why = blocks._convert_forge_multilayer(mod, result, "layered", _blockstate(mod, "layered"), {}, set(), None)
    assert "its class isn't read" in why


def test_solid_beside_translucent_merges_as_blend_default(mod):
    # Forge 1.12 layers: opaque frame (Solid) beside pane (Translucent).
    layers = [multilayer.Layer("SOLID", "minecraft:solid", {"parent": "examplemod:block/layered/frame"}),
              multilayer.Layer("TRANSLUCENT", "minecraft:translucent", {"parent": "examplemod:block/layered/pane"})]
    merged, _files, kinds, why = multilayer.merge(mod, layers)
    assert why == "" and kinds == {"minecraft:solid", "minecraft:translucent"}
    assert len(merged["elements"]) == 3
    assert multilayer.shared_type(kinds)[0] == multilayer.BLEND_DEFAULT


def test_solid_core_sampling_transparent_pixels_is_a_reason(mod):
    # core.png's border ring is transparent: a face with no uv samples the
    # whole texture, so blend would show pixels Java's solid layer draws.
    bare = {"parent": "block/block", "textures": {"all": "examplemod:blocks/core"}, "elements": [
        {"from": [1, 1, 1], "to": [15, 15, 15], "faces": {"up": {"texture": "#all"}}}]}
    edge = {"parent": "block/block", "textures": {"all": "examplemod:blocks/core"}, "elements": [
        {"from": [0, 0, 0], "to": [16, 16, 16], "faces": {"up": {"uv": [0, 0, 16, 16], "texture": "#all"}}}]}
    shell = json.loads((mod.assets / "models/block/shelled.json").read_text())["children"]["shell"]
    for core, words in ((bare, "has transparent pixels"), (edge, "where a face samples it")):
        layers = [multilayer.Layer("core", "minecraft:solid", core),
                  multilayer.Layer("shell", "minecraft:translucent", shell)]
        merged, _files, _kinds, why = multilayer.merge(mod, layers)
        assert merged is None and words in why and "blend" in why


def test_composite_translucent_shell_over_solid_core_draws_blend(mod):
    seen: set = set()
    token = models.RENDER_TYPES_SEEN.set(seen)
    try:
        flat, _files, why = models.resolve(mod, json.loads((mod.assets / "models/block/shelled.json").read_text()))
    finally:
        models.RENDER_TYPES_SEEN.reset(token)
    assert why == "" and len(flat["elements"]) == 2
    assert seen == {multilayer.BLEND_DEFAULT}
    result = blocks.convert(mod)
    instances = result.files["blocks/shelled.json"]["minecraft:block"]["components"]["minecraft:material_instances"]
    # Forced: each face's own texture alpha would give opaque/blend, and
    # agreement among faces would otherwise leave them as they are.
    assert {spec.get("render_method") for spec in instances.values()} == {"blend"}
    assert {spec["texture"] for spec in instances.values()} == {f"{NS}:core", f"{NS}:shell"}
    note = next(n for n in result.notes if n.startswith("shelled: every face draws blend"))
    assert "DEFAULT (pick 1a" in note


def test_composite_merges_visible_children(mod):
    seen: set = set()
    token = models.RENDER_TYPES_SEEN.set(seen)
    try:
        flat, files, why = models.resolve(mod, json.loads((mod.assets / "models/block/lantern.json").read_text()))
    finally:
        models.RENDER_TYPES_SEEN.reset(token)
    assert why == ""
    assert len(flat["elements"]) == 2  # body + glass; the hidden child isn't baked
    assert seen == {"minecraft:cutout"}
    assert any(p.name == "lantern_body.json" for p in files)
    result = blocks.convert(mod)
    assert "blocks/lantern.json" in result.files
    instances = result.files["blocks/lantern.json"]["minecraft:block"]["components"]["minecraft:material_instances"]
    assert {spec.get("render_method") for spec in instances.values()} == {"alpha_test"}


def test_composite_with_translucent_child_or_extended_is_a_reason(mod):
    flat, _files, why = models.resolve(mod, json.loads((mod.assets / "models/block/jar.json").read_text()))
    assert flat == {} and "translucent" in why
    child = {"parent": "examplemod:block/lantern", "textures": {"side": "examplemod:blocks/frame"}}
    _flat, _files, why = models.resolve(mod, child)
    assert "extends a composite model" in why
    result = blocks.convert(mod)
    reason = next(u.reason for u in result.unhandled if u.source.endswith("blockstates/jar.json"))
    assert "composite" in reason and "translucent" in reason


def test_face_naming_a_texture_its_layer_lacks_is_a_reason(mod):
    lacking = {"parent": "block/block", "elements": [
        {"from": [0, 0, 0], "to": [16, 1, 16], "faces": {"up": {"texture": "#frame"}}}]}
    layers = [multilayer.Layer("SOLID", "minecraft:solid", {"parent": "examplemod:block/layered/frame"}),
              multilayer.Layer("CUTOUT", "minecraft:cutout", lacking)]
    merged, _files, _kinds, why = multilayer.merge(mod, layers)
    assert merged is None and "#frame, which it doesn't set" in why


def test_shared_type():
    assert multilayer.shared_type({"minecraft:cutout", "minecraft:cutout_mipped"}) == ("minecraft:cutout", "")
    assert multilayer.shared_type({"minecraft:solid", "minecraft:cutout_mipped"})[0] == "minecraft:cutout_mipped"
    kind, why = multilayer.shared_type({"minecraft:solid", "minecraft:translucent"})
    assert kind == multilayer.BLEND_DEFAULT and why.startswith("DEFAULT (pick 1a")
    assert blocks._JAVA_RENDER_METHOD[kind] == "blend"
    assert multilayer.shared_type({"minecraft:cutout", "minecraft:translucent"}) == (None, "")
    assert multilayer.shared_type({None}) == (None, "")
