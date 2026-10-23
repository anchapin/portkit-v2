"""Blocks that hold items behind a menu (#179): slot count, menu and opening
read from the jar's bytecode (portkit.blockcode.read_containers), shipped as
a Bedrock block container (minecraft:block_entity container.slot_count) only
when the conversion runs with --experiment upcoming_creator_features.

The class files under tests/data/blockcode/classes are javac 21 output of
tests/data/blockcode/src (ContainerBlocks.java; rebuild with build.sh): real
compiler patterns, no Minecraft code.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from portkit import blockcode, pipeline
from portkit.bytecode import ClassIndex
from portkit.converters import blocks
from portkit.model import SourceMod

CLASSES = Path(__file__).parent / "data" / "blockcode" / "classes"
NAMES = ["crate", "box", "toaster", "oven", "smoker", "vault", "hamper", "chesty", "bin", "lamp"]
EXP = frozenset({blocks.UPCOMING_CREATOR_FEATURES})


@pytest.fixture(scope="module")
def read():
    return blockcode.read_containers(ClassIndex.from_source(CLASSES), NAMES)


# --- reading ------------------------------------------------------------------

def test_block_entity_built_directly(read):
    crate = read["crate"]
    assert crate.slots == 27
    assert crate.slots_from == ("com.example.deco.ContainerBlocks$CrateEntity#getContainerSize via "
                                "com.example.deco.ContainerBlocks$Crate#newBlockEntity")
    assert crate.menu == "net.minecraft.world.inventory.ChestMenu"
    assert crate.menu_where == "com.example.deco.ContainerBlocks$CrateEntity#createMenu"
    # The use method is inherited from the block's superclass.
    assert crate.menu_from == "com.example.deco.ContainerBlocks$Storage#useWithoutItem"
    assert not crate.ticks and not crate.why


def test_block_entity_built_through_its_registered_type(read):
    # TWO_ROWS.get().create(pos, state): the holder runs its supplier, the
    # type keeps Builder.of's factory and create calls it with rows = 2.
    box = read["box"]
    assert box.slots == 18 and box.be == "com.example.deco.ContainerBlocks$RowBox"
    assert box.menu == "net.minecraft.world.inventory.ChestMenu"


def test_no_menu_is_read_as_such(read):
    assert read["toaster"].slots == 2 and read["toaster"].menu_from == ""


def test_mod_menu_is_not_a_grid(read):
    oven = read["oven"]
    assert oven.slots == 3 and oven.menu == ""
    assert "builds the mod's own menu (com.example.deco.ContainerBlocks$OvenMenu)" in oven.menu_why


def test_ticker_is_named(read):
    assert read["smoker"].ticks == "com.example.deco.ContainerBlocks$Smoker#getTicker"


def test_too_many_slots_is_unread(read):
    assert read["vault"].slots is None
    assert "gives 60 slots; a Bedrock block container holds 1 to 54" in read["vault"].why


def test_unknown_slot_count_is_unread(read):
    assert read["hamper"].slots is None and "doesn't give one slot count" in read["hamper"].why


def test_vanilla_container_with_behaviour_is_not_plain(read):
    assert read["chesty"].slots is None and "ChestBlockEntity, which is not a plain container" in read["chesty"].why


def test_block_without_block_entity(read):
    assert not read["lamp"].entity and read["lamp"].slots is None and not read["lamp"].why


def test_no_classes():
    r = blockcode.read_containers(ClassIndex({}), ["crate"])["crate"]
    assert r.slots is None and r.why == "the mod ships no class files"


def test_other_readers_unchanged_by_the_holder_mode():
    # The container reader follows registry holders on its own machine pass;
    # the facing reader still sees the same block classes.
    facing = blockcode.read_blocks(ClassIndex.from_source(CLASSES), ["crate"])["crate"]
    assert facing.cls == "com.example.deco.ContainerBlocks$Crate"
    assert "newBlockEntity" in facing.behaviour


# --- converting ----------------------------------------------------------------

def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body))


def _png() -> bytes:
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    raw = b"".join(b"\x00" + b"\x80\x60\x40\xff" * 16 for _ in range(16))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _mod(tmp_path: Path) -> SourceMod:
    root = tmp_path / "mod"
    ns = "examplemod"
    (root / f"assets/{ns}/textures/block").mkdir(parents=True)
    (root / f"assets/{ns}/textures/block/wood.png").write_bytes(_png())
    tex = {"all": f"{ns}:block/wood", "particle": f"{ns}:block/wood"}
    box = {"textures": tex, "elements": [{"from": [1, 0, 1], "to": [15, 12, 15], "faces": {
        f: {"texture": "#all"} for f in ("north", "south", "east", "west", "up", "down")}}]}
    for name in ("crate", "box", "toaster", "oven", "smoker"):
        _write(root, f"assets/{ns}/models/block/{name}.json", box)
        _write(root, f"assets/{ns}/blockstates/{name}.json", {"variants": {"": {"model": f"{ns}:block/{name}"}}})
    # A plain cube: Bedrock's full_block geometry, which changes at 1.26.0.
    _write(root, f"assets/{ns}/models/block/bin.json", {"parent": "minecraft:block/cube_all", "textures": tex})
    _write(root, f"assets/{ns}/blockstates/bin.json", {"variants": {"": {"model": f"{ns}:block/bin"}}})
    return SourceMod(root=root, namespace=ns, classes=ClassIndex.from_source(CLASSES))


def _def(result, name):
    return result.files[f"blocks/{name}.json"]


def test_without_the_experiment_nothing_changes_but_the_notes(tmp_path):
    mod = _mod(tmp_path)
    result = blocks.convert(mod)
    for name in ("crate", "box", "toaster", "bin"):
        assert "minecraft:block_entity" not in _def(result, name)["minecraft:block"]["components"]
        assert _def(result, name)["format_version"] != "1.26.50"
    note = next(n for n in result.notes if "hold items behind a vanilla grid menu" in n)
    assert "decoration only" in note and "--experiment upcoming_creator_features" in note
    assert "27 slots (com.example.deco.ContainerBlocks$CrateEntity#getContainerSize" in note
    assert "18 slots" in note and ": box" in note


def test_with_the_experiment_menu_blocks_become_containers(tmp_path):
    mod = _mod(tmp_path)
    result = blocks.convert(mod, experiments=EXP)
    crate = _def(result, "crate")
    assert crate["format_version"] == "1.26.50"
    assert crate["minecraft:block"]["components"]["minecraft:block_entity"] == {"container": {"slot_count": 27}}
    assert _def(result, "box")["minecraft:block"]["components"]["minecraft:block_entity"] == {
        "container": {"slot_count": 18}}
    note = next(n for n in result.notes if "ship as Bedrock containers" in n)
    assert "Upcoming Creator Features" in note and "contents drop when the block is destroyed" in note


def test_blocks_that_do_more_than_store_stay_decoration(tmp_path):
    result = blocks.convert(_mod(tmp_path), experiments=EXP)
    for name in ("toaster", "oven", "smoker", "bin"):
        assert "minecraft:block_entity" not in _def(result, name)["minecraft:block"]["components"], name
    held = next(n for n in result.notes if n.startswith("Hold items in Java"))
    assert "2 slots; its use method opens no menu" in held and "toaster" in held
    assert "OvenMenu" in held and "it ticks (com.example.deco.ContainerBlocks$Smoker#getTicker)" in held
    assert "minecraft:geometry.full_block, which is a different geometry from block format 1.26.0" in held


def test_container_bump_guards():
    assert blocks._container_bump({"format_version": "1.20.20", "minecraft:block": {"components": {
        "tag:wood": {}}}}).startswith("it carries tag:*")
    assert "ambient_occlusion" in blocks._container_bump({"format_version": "1.26.0", "minecraft:block": {
        "components": {"minecraft:material_instances": {"*": {"ambient_occlusion": False}}}}})
    # full_block is only a problem below 1.26.0.
    assert blocks._container_bump({"format_version": "1.26.0", "minecraft:block": {"components": {
        "minecraft:geometry": "minecraft:geometry.full_block"}}}) == ""


def test_liquid_clipping_keeps_its_old_default_when_moved_past_1_26_0(tmp_path):
    mod = _mod(tmp_path)
    result = blocks.convert(mod)
    definition = _def(result, "crate")
    definition["minecraft:block"]["components"]["minecraft:liquid_detection"] = {
        "detection_rules": [{"liquid_type": "water", "can_contain_liquid": True}]}
    blocks._add_containers(mod, result, {}, EXP)
    rule = definition["minecraft:block"]["components"]["minecraft:liquid_detection"]["detection_rules"][0]
    assert rule["use_liquid_clipping"] is True and definition["format_version"] == "1.26.50"


def test_station_blocks_are_left_alone(tmp_path):
    mod = _mod(tmp_path)
    result = blocks.convert(mod)
    made = blocks._add_containers(mod, result, {"crate": object()}, EXP)
    assert "crate" not in made and "box" in made


def test_pipeline_rejects_an_unknown_experiment(tmp_path):
    with pytest.raises(ValueError, match="unknown Bedrock experiment"):
        pipeline.convert(tmp_path / "missing.jar", tmp_path / "out", experiments=["holiday_creator_features"])


def test_emitted_block_passes_the_schema(tmp_path):
    from portkit.validate.report import ValidationReport
    from portkit.validate.schema import check_block
    result = blocks.convert(_mod(tmp_path), experiments=EXP)
    report = ValidationReport()
    check_block(report, _def(result, "crate"), "blocks/crate.json")
    assert report.findings == []


def test_water_added_by_the_block_converter_keeps_its_clipping(tmp_path, monkeypatch):
    # A waterlogged crate that holds water (read_water stubbed to say so):
    # _add_water runs before the container's format move.
    monkeypatch.setattr(blocks.blockcode, "read_water", lambda classes, names, run=None: {
        n: blockcode.WaterReading(n, holds=True, source="test") for n in names})
    mod = _mod(tmp_path)
    ns = mod.namespace
    _write(mod.root, f"assets/{ns}/blockstates/crate.json", {"variants": {
        "waterlogged=false": {"model": f"{ns}:block/crate"}, "waterlogged=true": {"model": f"{ns}:block/crate"}}})
    result = blocks.convert(mod, experiments=EXP)
    crate = _def(result, "crate")
    rules = crate["minecraft:block"]["components"].get("minecraft:liquid_detection", {}).get("detection_rules", [])
    assert crate["minecraft:block"]["components"]["minecraft:block_entity"] == {"container": {"slot_count": 27}}
    assert rules and all(rule["use_liquid_clipping"] is True for rule in rules)
