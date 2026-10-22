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
    types = rendershape._Types(classes)
    assert rendershape.block_entities(classes, P + "SpinnerBlock", types) == [P + "SpinnerBlockEntity"]
    assert rendershape.block_entities(classes, P + "BearingBlock", types) == [P + "BearingBlockEntity"]


D = "com.example.render."


def test_registration_calls_pair_renderer_and_block_entity(classes):
    """#355 pick 4c: the call itself is read (ClientSetup, OldClientProxy)."""
    found = {(b.renderer, b.entity) for b in rendershape.bindings(classes) if b.renderer and b.entity}
    assert found == {
        (D + "PoolRenderer", D + "PoolBlockEntity"),          # Forge event, constructor reference
        (D + "SpinnerRenderer", D + "SpinnerBlockEntity"),    # a lambda building the renderer
        (D + "KineticRenderer", D + "BearingBlockEntity"),    # vanilla BlockEntityRenderers, Registry.register
        (D + "OldChestRenderer", D + "OldChestTile"),         # 1.12 class literal and renderer object
        (D + "TankRenderer", D + "TankBlockEntity"),          # new BlockEntityType(factory, blocks, null)
        (D + "LampRenderer", D + "LampBlockEntity"),          # a helper, read through its caller
    }


def test_a_call_whose_type_comes_from_the_caller_pairs_nothing(classes):
    later = [b for b in rendershape.bindings(classes) if b.where == D + "ClientSetup#later"]
    assert len(later) == 1 and later[0].entity is None and later[0].renderer == D + "KineticRenderer"
    assert "isn't a block entity type the run builds" in later[0].why


def test_a_helper_making_the_call_is_read_through_its_caller(classes):
    lamp = [b for b in rendershape.bindings(classes) if b.entity == D + "LampBlockEntity"]
    assert [b.where for b in lamp] == [D + "ClientHelpers#onRegister"]


def test_a_renderer_on_the_mods_base_class_draws_only_what_it_is_bound_to(classes):
    """KineticRenderer<T extends KineticBlockEntity> would accept the shaft by
    its signature (#354's over-match); the client binds it to the bearing only."""
    machine = blockcode.Machine(classes)
    out = rendershape.read(classes, {"bearing": ([blockcode.Obj(P + "BearingBlock", {})], ""),
                                     "shaft": ([blockcode.Obj(P + "ShaftBlock", {})], "")}, "1.21.1", machine)
    assert out["bearing"].renderers == (D + "KineticRenderer",)
    assert out["bearing"].bound_by == (D + "ClientSetup#registerRenderers",)
    assert out["shaft"].block_entities == (D + "ShaftBlockEntity",) and out["shaft"].renderers == ()


def test_a_jar_without_registration_calls_binds_nothing():
    assert rendershape.bindings(ClassIndex({})) == []


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
        block_entities=("com.example.render.PoolBlockEntity",), renderers=("com.example.render.PoolRenderer",),
        bound_by=("com.example.render.ClientSetup#registerRenderers",),
        bound_to=("com.example.render.PoolBlockEntity",)))
    result = blocks.convert(build(tmp_path))
    assert "blocks/thing.json" in result.files
    (entry,) = result.unhandled
    assert (entry.kind, entry.count) == ("renderer_drawn_parts", 0)
    assert "com.example.render.PoolRenderer" in entry.reason
    assert "registration call in com.example.render.ClientSetup#registerRenderers" in entry.reason


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


def test_a_zero_count_entry_counts_no_file_in_reports():
    from portkit.gaps import group_residue
    from portkit.model import Unhandled
    from portkit.report import Residue
    grouped = group_residue([Unhandled("assets/x/blockstates/a.json", "renderer_drawn_parts", "r", count=0),
                             {"source": "b", "kind": "block", "reason": "r"}])
    assert sorted((v["kind"], v["entries"], v["files"]) for v in grouped.values()) == [
        ("block", 1, 1), ("renderer_drawn_parts", 1, 0)]
    import json as _json, tempfile, pathlib
    tree = pathlib.Path(tempfile.mkdtemp())
    (tree / "unhandled.json").write_text(_json.dumps([{"source": "a", "kind": "renderer_drawn_parts",
                                                       "reason": "r", "count": 0}]))
    assert [r.count for r in Residue.load(tree)] == [0]
