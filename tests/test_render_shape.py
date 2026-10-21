"""#352: Java's render shape and block-entity renderers, read from bytecode
(portkit.rendershape), and what the block converter does with them.

The class files under tests/data/rendershape/classes are javac 21 output of
tests/data/rendershape/src (rebuild with build.sh): real compiler patterns,
no Minecraft code. The vanilla tables are read from Mojang's client jars
(cited in portkit.rendershape.VANILLA).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from portkit import blockcode, rendershape
from portkit.agent.residue import SKIP_KINDS
from portkit.bytecode import ClassIndex
from portkit.converters import blocks
from portkit.model import ConversionResult, SourceMod
from portkit.pipeline import drop_untextured

CLASSES = Path(__file__).parent / "data" / "rendershape" / "classes"
P = "com/example/render/"


@pytest.fixture(scope="module")
def classes():
    return ClassIndex.from_source(CLASSES)


# --- the render shape -----------------------------------------------------

def test_a_constant_override_is_read(classes):
    shapes, source, why = rendershape.read_shape(classes, P + "SpinnerBlock", None)
    assert shapes == {"ENTITYBLOCK_ANIMATED"} and not why
    assert source == "com.example.render.SpinnerBlock#getRenderShape = ENTITYBLOCK_ANIMATED"


def test_a_field_dependent_override_is_unread_without_the_object(classes):
    shapes, _, why = rendershape.read_shape(classes, P + "PoolBlock", None)
    assert shapes is None and "depending on what it reads" in why


def test_a_field_dependent_override_is_run_on_the_registered_object(classes):
    machine = blockcode.Machine(classes)
    fancy = blockcode.Obj(P + "PoolBlock", {"fancy": 1})
    plain = blockcode.Obj(P + "PoolBlock", {"fancy": 0})
    assert rendershape.read_shape(classes, P + "PoolBlock", None, machine, fancy)[0] == {"ENTITYBLOCK_ANIMATED"}
    shapes, source, _ = rendershape.read_shape(classes, P + "PoolBlock", None, machine, plain)
    assert shapes == {"MODEL"} and "run on the registered block" in source


def test_an_answer_from_another_method_is_unread(classes):
    shapes, _, why = rendershape.read_shape(classes, P + "AskingBlock", None)
    assert shapes is None and "takes its answer from com.example.render.AskingBlock#pick" in why


def test_an_inherited_shape_comes_from_the_cited_vanilla_table(classes):
    for version, shape in (("1.19.2", "INVISIBLE"), ("1.20.1", "INVISIBLE"), ("1.21.1", "INVISIBLE"),
                           ("1.21.8", "MODEL")):
        shapes, source, _ = rendershape.read_shape(classes, P + "CabinetBlock", rendershape.vanilla_for(version))
        assert shapes == {shape}, version
        assert "net.minecraft.world.level.block.BaseEntityBlock#getRenderShape" in source
        assert "client.jar sha1" in source
    # A plain Block resolves to BlockBehaviour's MODEL.
    assert rendershape.read_shape(classes, P + "ShaftBlock", rendershape.vanilla_for("1.21.1"))[0] == {"MODEL"}


def test_an_inherited_shape_without_a_table_is_unread(classes):
    shapes, _, why = rendershape.read_shape(classes, P + "CabinetBlock", rendershape.vanilla_for("1.16.5"))
    assert shapes is None and "no table of vanilla render shapes" in why
    assert rendershape.vanilla_for("1.21.0") is None  # 1.21 has no pinned table


def test_vanilla_tables_hold_only_non_model_shapes():
    for table in rendershape.VANILLA:
        assert set(table.not_model.values()) <= {"INVISIBLE", "ENTITYBLOCK_ANIMATED"}
        assert all(k.startswith("net/minecraft/world/level/block/") for k in table.not_model)
    # 1.21.2+ dropped ENTITYBLOCK_ANIMATED.
    assert "ENTITYBLOCK_ANIMATED" not in rendershape.vanilla_for("1.21.8").not_model.values()


# --- block-entity renderers -------------------------------------------------

def test_block_entities_from_construction_and_signature(classes):
    renderers = rendershape._Renderers(classes)
    assert rendershape.block_entities(classes, P + "SpinnerBlock", renderers) == [P + "SpinnerBlockEntity"]
    assert rendershape.block_entities(classes, P + "BearingBlock", renderers) == [P + "BearingBlockEntity"]


def test_renderers_accept_by_type_argument_and_by_every_bound(classes):
    renderers = rendershape._Renderers(classes)
    assert renderers.accepting(P + "PoolBlockEntity") == [P + "PoolRenderer"]
    assert renderers.accepting(P + "BearingBlockEntity") == [P + "BearingRenderer"]
    # Kinetic but not a Bearing; and the only renderer naming it is unused.
    assert renderers.accepting(P + "ShaftBlockEntity") == []
    assert P + "UnusedRenderer" not in [name for name, _, _ in renderers.found]


def test_read_combines_both(classes):
    machine = blockcode.Machine(classes)
    registered = {
        "pool": ([blockcode.Obj(P + "PoolBlock", {"fancy": 0})], ""),
        "fabulous_pool": ([blockcode.Obj(P + "PoolBlock", {"fancy": 1})], ""),
        "missing": ([], "no registration of this block was found in the mod's classes"),
    }
    out = rendershape.read(classes, registered, "1.21.1", machine)
    assert out["pool"].shapes == {"MODEL"} and out["pool"].renderers == ("com.example.render.PoolRenderer",)
    assert out["fabulous_pool"].code_drawn and out["fabulous_pool"].renderers == ()
    assert out["missing"].shapes is None and "no registration" in out["missing"].why


# --- the block converter ------------------------------------------------------

ONE = {"variants": {"": {"model": "examplemod:block/thing"}}}
CUBE = {"parent": "examplemod:block/base", "textures": {"all": "examplemod:block/thing"}}
BASE = {"elements": [{"from": [0, 0, 0], "to": [16, 8, 16],
                      "faces": {d: {"texture": "#all", "uv": [0, 0, 16, 8]}
                                for d in ("north", "south", "east", "west", "up", "down")}}]}


def build(tmp_path):
    assets = tmp_path / "assets" / "examplemod"
    (assets / "blockstates").mkdir(parents=True)
    (assets / "blockstates" / "thing.json").write_text(json.dumps(ONE))
    (assets / "models" / "block").mkdir(parents=True)
    (assets / "models" / "block" / "thing.json").write_text(json.dumps(CUBE))
    (assets / "models" / "block" / "base.json").write_text(json.dumps(BASE))
    return SourceMod(root=tmp_path, namespace="examplemod")


def with_reading(monkeypatch, reading):
    monkeypatch.setattr(blocks._RenderRun, "__call__", lambda self: {"thing": reading})


def test_without_a_reading_the_block_ships(tmp_path):
    result = blocks.convert(build(tmp_path))
    assert "blocks/thing.json" in result.files and not result.unhandled


def test_a_code_drawn_shape_refuses_the_block(tmp_path, monkeypatch):
    with_reading(monkeypatch, rendershape.RenderReading(
        "thing", "com.example.render.SpinnerBlock", frozenset({"ENTITYBLOCK_ANIMATED"}),
        "com.example.render.SpinnerBlock#getRenderShape = ENTITYBLOCK_ANIMATED"))
    result = blocks.convert(build(tmp_path))
    assert not any(k.startswith(("blocks/", "models/")) for k in result.files)
    (entry,) = result.unhandled
    assert (entry.source, entry.kind, entry.count) == ("assets/examplemod/blockstates/thing.json",
                                                       "code_drawn_block", 1)
    assert "RenderShape.ENTITYBLOCK_ANIMATED for every state" in entry.reason
    assert "SpinnerBlock#getRenderShape" in entry.reason
    # The model and its parent are claimed, as a refused block's are.
    assert {"assets/examplemod/models/block/thing.json", "assets/examplemod/models/block/base.json"} \
        <= result.consumed


def test_a_mixed_or_unread_shape_changes_nothing(tmp_path, monkeypatch):
    with_reading(monkeypatch, rendershape.RenderReading("thing", why="unread"))
    assert "blocks/thing.json" in blocks.convert(build(tmp_path)).files


def test_model_with_a_renderer_ships_and_is_flagged_at_zero_files(tmp_path, monkeypatch):
    with_reading(monkeypatch, rendershape.RenderReading(
        "thing", "com.example.render.PoolBlock", frozenset({"MODEL"}), "PoolBlock#getRenderShape = MODEL",
        block_entities=("com.example.render.PoolBlockEntity",), renderers=("com.example.render.PoolRenderer",)))
    result = blocks.convert(build(tmp_path))
    assert "blocks/thing.json" in result.files
    (entry,) = result.unhandled
    assert (entry.kind, entry.count) == ("renderer_drawn_parts", 0)
    assert "com.example.render.PoolRenderer" in entry.reason


def test_both_kinds_are_explained():
    assert "code_drawn_block" in SKIP_KINDS and "renderer_drawn_parts" in SKIP_KINDS


# --- a withdrawn block's geometry -----------------------------------------------

def _block(ident, geometry, texture):
    return {"minecraft:block": {"description": {"identifier": ident}, "components": {
        "minecraft:geometry": geometry,
        "minecraft:material_instances": {"*": {"texture": texture}}}}}


def _geo(ident):
    return {"format_version": "1.12.0", "minecraft:geometry": [{"description": {"identifier": ident}}]}


def test_a_block_withdrawn_for_its_texture_takes_its_geometry():
    result = ConversionResult()
    result.files = {
        "blocks/a.json": _block("x:a", "geometry.x.a", "x_missing"),
        "models/blocks/a.geo.json": _geo("geometry.x.a"),
        "blocks/b.json": _block("x:b", {"identifier": "geometry.x.shared"}, "x_b"),
        "blocks/c.json": _block("x:c", "geometry.x.shared", "x_missing"),
        "models/blocks/shared.geo.json": _geo("geometry.x.shared"),
        "textures/terrain_texture.json": {"texture_data": {"x_b": {"textures": "textures/blocks/b"}}},
    }
    drop_untextured(result, "x")
    assert "blocks/a.json" not in result.files and "models/blocks/a.geo.json" not in result.files
    # Still named by a block that stays.
    assert "models/blocks/shared.geo.json" in result.files and "blocks/b.json" in result.files
    assert any("models/blocks/a.geo.json: dropped with its block" in n for n in result.notes)
