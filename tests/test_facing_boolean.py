"""Blocks with facing and boolean states (lit, open, powered...), converted
outside station runtimes: one Bedrock state per boolean, starting at the
value read from bytecode (getStateForPlacement, the registered default state,
StateDefinition#any) or a labelled DEFAULT; the model drawn at each state;
the box per (facing, booleans) and the light per booleans; a use toggle only
where useWithoutItem was read to flip that one boolean, through the fixed
toggle runtime.

The class files under tests/data/blockcode/classes are javac 21 output of the
example mod in tests/data/blockcode/src (StateBlocks.java, ToggleLampBlock,
FlipBlock, ItemFlipBlock, PoweredLampBlock, GateBlock; rebuild with build.sh):
real compiler patterns, no Minecraft code.
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

import pytest

from portkit import blockcode
from portkit.bytecode import ClassIndex
from portkit.converters import blocks, convert_all
from portkit.model import SourceMod

CLASSES = Path(__file__).parent / "data" / "blockcode" / "classes"
JS = Path(__file__).parent / "js"
CARDINALS = ("north", "east", "south", "west")
TURN = {"north": 0, "east": 90, "south": 180, "west": 270}
NS = "examplemod"
BOOLS = {"toggle_lamp": ("lit",), "flip_box": ("open",), "item_flip": ("open",),
         "powered_lamp": ("on", "powered"), "gate_block": ("open",)}


@pytest.fixture(scope="module")
def readings():
    return blockcode.read_state_blocks(ClassIndex.from_source(CLASSES), BOOLS)


# --- reading ------------------------------------------------------------------

def test_starting_values(readings):
    lamp = readings["toggle_lamp"].defaults["lit"]
    assert lamp == (False, "placed", "com.example.deco.ToggleLampBlock#getStateForPlacement")
    assert readings["flip_box"].defaults["open"][:2] == (False, "placed")
    powered = readings["powered_lamp"].defaults
    # Placement reads redstone: Bedrock starts at the registered default state.
    assert powered["powered"][:2] == (False, "registered")
    assert "PoweredLampBlock#<init> (registerDefaultState)" in powered["powered"][2]
    assert "sets it from the world" in powered["powered"][2]
    # Never set in code: StateDefinition#any, whose booleans are true.
    assert powered["on"][:2] == (True, "any")


def test_use_toggles(readings):
    assert readings["toggle_lamp"].toggle == "lit"
    assert readings["toggle_lamp"].toggle_from == "com.example.deco.ToggleLampBlock#useWithoutItem"
    assert readings["flip_box"].toggle == "open"
    item = readings["item_flip"]
    assert item.toggle is None and "ItemFlipBlock#useItemOn decides" in item.toggle_why
    lamp = readings["powered_lamp"]
    assert lamp.toggle is None and "some ways through it leave the block as it is" in lamp.toggle_why


def test_what_changes_a_boolean(readings):
    assert readings["powered_lamp"].changed_by == {"powered": ["neighborChanged+redstone"],
                                                   "on": ["useWithoutItem"]}


def test_shape_per_state(readings):
    shapes = readings["toggle_lamp"].shapes_by
    assert shapes[("north", (0,))] == ((4.0, 0.0, 4.0, 12.0, 10.0, 12.0),)
    assert shapes[("west", (1,))] == ((4.0, 0.0, 4.0, 12.0, 14.0, 12.0),)


def test_light_per_state(readings):
    lamp = readings["toggle_lamp"]
    assert (lamp.light_by, lamp.light_kind) == ({(0,): 0, (1,): 15}, "per_state")
    assert lamp.light_source == "com.example.deco.StateBlocks#lambda$static$0"
    powered = readings["powered_lamp"]
    # (on, powered): powered ? 12 : on ? 3 : 0.
    assert powered.light_by == {(0, 0): 0, (0, 1): 12, (1, 0): 3, (1, 1): 12}
    assert (readings["flip_box"].light_kind, set(readings["flip_box"].light_by.values())) == ("dark", {0})


def test_vanilla_parent_is_not_read(readings):
    gate = readings["gate_block"]
    assert gate.vanilla_parent == "net.minecraft.world.level.block.FenceGateBlock"
    assert gate.defaults == {} and gate.toggle is None


def test_a_property_under_an_unread_name_is_never_any():
    # A state whose boolean was set under a name that wasn't read keeps the
    # value unknown rather than StateDefinition#any's.
    state = blockcode.State(((blockcode._ANY, 1), ("?123", 0)))
    assert blockcode._bool_value(state, "enabled") is blockcode.UNKNOWN
    assert blockcode._bool_value(blockcode.State(((blockcode._ANY, 1),)), "enabled") == 1


def test_vanilla_boolean_properties_by_name():
    machine = blockcode.Machine(ClassIndex({}))
    ref = blockcode.Ref(blockcode._STATE_PROPS, "ENABLED", "Lnet/minecraft/world/level/block/state/properties/BooleanProperty;")
    assert machine.get_static(ref) == blockcode.Prop("enabled")
    ref = blockcode.Ref(blockcode._STATE_PROPS, "CHISELED_BOOKSHELF_SLOT_0_OCCUPIED", "x")
    assert machine.get_static(ref) == blockcode.Prop("slot_0_occupied")


# --- blockstates ----------------------------------------------------------------

def _variants(models_by_combo: dict, bools: tuple, uvlock: bool = False) -> dict:
    out = {}
    for combo, model in models_by_combo.items():
        for d in CARDINALS:
            key = ",".join(sorted([f"facing={d}"] + [f"{p}={'true' if v else 'false'}" for p, v in zip(bools, combo)]))
            out[key] = {"model": model, **({"y": TURN[d]} if TURN[d] else {}), **({"uvlock": True} if uvlock else {})}
    return {"variants": out}


def test_variants_parse():
    spec, why = blocks._coded_bool_variants(_variants({(0,): "a", (1,): "b"}, ("lit",)))
    assert why == "" and spec["bools"] == ("lit",)
    assert spec["cells"][("east", (1,))] == ("b", 90, False)


def test_multipart_parse_one_part_per_state():
    parts = [{"when": {"facing": d, "open": v}, "apply": {"model": f"m_{v}", "y": TURN[d]}}
             for d in CARDINALS for v in ("true", "false")]
    spec, why = blocks._coded_bool_variants({"multipart": parts})
    assert spec["cells"][("south", (1,))] == ("m_true", 180, False)
    extra = parts + [{"apply": {"model": "base"}}]
    # Two parts at one state: left to the other multipart converters.
    assert blocks._coded_bool_variants({"multipart": extra}) == (None, "")


def test_not_this_shape():
    # Facing-only, waterlogged and non-boolean states are other converters'.
    assert blocks._coded_bool_variants({"variants": {f"facing={d}": {"model": "a"} for d in CARDINALS}}) == (None, "")
    assert blocks._coded_bool_variants(_variants({(0,): "a", (1,): "a"}, ("waterlogged",))) == (None, "")
    half = {"variants": {f"facing={d},half={h}": {"model": "a"} for d in CARDINALS for h in ("top", "bottom")}}
    assert blocks._coded_bool_variants(half) == (None, "")
    partial = _variants({(0,): "a", (1,): "b"}, ("lit",))
    del partial["variants"]["facing=north,lit=true"]
    spec, why = blocks._coded_bool_variants(partial)
    assert spec is None and "not every combination" in why


# --- converting ------------------------------------------------------------------

def _png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    raw = b"".join(b"\x00" + b"\x80\x60\x40\xff" * 16 for _ in range(16))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _model(top: int, texture: str, uv: bool = True) -> dict:
    faces = {f: {"texture": "#all", **({"uv": [0, 0, 8, 8]} if uv else {})}
             for f in ("north", "south", "east", "west", "up", "down")}
    return {"textures": {"all": f"{NS}:block/{texture}", "particle": f"{NS}:block/{texture}"}, "elements": [
        {"from": [4, 0, 4], "to": [12, top, 12], "faces": faces},
        {"from": [6, top, 10], "to": [10, top + 2, 16], "faces": faces}]}


def _mod(tmp_path: Path, classes: bool = True) -> SourceMod:
    root = tmp_path / "mod"
    for sub in ("textures/block", "models/block", "blockstates"):
        (root / f"assets/{NS}/{sub}").mkdir(parents=True)
    for tex in ("wood", "glow"):
        (root / f"assets/{NS}/textures/block/{tex}.png").write_bytes(_png())
    models = {"lamp_off": _model(10, "wood"), "lamp_on": _model(14, "glow"), "box": _model(8, "wood", uv=False),
              "box_open": _model(9, "wood", uv=False)}
    for name, model in models.items():
        (root / f"assets/{NS}/models/block/{name}.json").write_text(json.dumps(model))
    states = {
        "toggle_lamp": _variants({(0,): f"{NS}:block/lamp_off", (1,): f"{NS}:block/lamp_on"}, ("lit",)),
        "flip_box": {"multipart": [{"when": {"facing": d, "open": v},
                                    "apply": {"model": f"{NS}:block/{'box_open' if v == 'true' else 'box'}",
                                              **({"y": TURN[d]} if TURN[d] else {})}}
                                   for d in CARDINALS for v in ("true", "false")]},
        "item_flip": _variants({(0,): f"{NS}:block/box", (1,): f"{NS}:block/box_open"}, ("open",), uvlock=True),
        "powered_lamp": _variants({(0, 0): f"{NS}:block/lamp_off", (0, 1): f"{NS}:block/lamp_on",
                                   (1, 0): f"{NS}:block/lamp_on", (1, 1): f"{NS}:block/lamp_on"}, ("on", "powered")),
        "gate_block": _variants({(0,): f"{NS}:block/box", (1,): f"{NS}:block/box_open"}, ("open",)),
    }
    for name, bs in states.items():
        (root / f"assets/{NS}/blockstates/{name}.json").write_text(json.dumps(bs))
    return SourceMod(root=root, namespace=NS, classes=ClassIndex.from_source(CLASSES) if classes else None)


@pytest.fixture()
def converted(tmp_path):
    return blocks.convert(_mod(tmp_path))


def _block(result, name):
    return result.files[f"blocks/{name}.json"]["minecraft:block"]


def test_states_start_at_the_read_value(converted):
    assert _block(converted, "toggle_lamp")["description"]["states"] == {f"{NS}:lit": [False, True]}
    assert _block(converted, "powered_lamp")["description"]["states"] == {
        f"{NS}:on": [True, False], f"{NS}:powered": [False, True]}


def test_models_per_state(converted):
    lamp = _block(converted, "toggle_lamp")
    vis = lamp["components"]["minecraft:geometry"]["bone_visibility"]
    assert vis == {"m0": f"!q.block_state('{NS}:lit')", "m1": f"q.block_state('{NS}:lit')"}
    geo = converted.files["models/blocks/toggle_lamp.geo.json"]["minecraft:geometry"][0]
    assert [b["name"] for b in geo["bones"]] == ["m0", "m1"]
    # Two textures under one key: the second model's gets its own.
    assert set(lamp["components"]["minecraft:material_instances"]) >= {"*"}
    trait = lamp["description"]["traits"]["minecraft:placement_direction"]
    assert trait == {"enabled_states": ["minecraft:cardinal_direction"], "y_rotation_offset": 180}


def test_box_and_light_per_permutation(converted):
    lamp = _block(converted, "toggle_lamp")
    perms = {p["condition"]: p["components"] for p in lamp["permutations"]}
    lit_east = perms[f"q.block_state('minecraft:cardinal_direction') == 'east' && q.block_state('{NS}:lit')"]
    assert lit_east["minecraft:light_emission"] == 15
    assert lit_east["minecraft:transformation"] == {"rotation": [0, -90, 0]}
    # Java's lit box (4,0,4)-(12,14,12), in the model's frame.
    assert lit_east["minecraft:selection_box"]["size"] == [8, 14, 8]
    off_north = perms[f"q.block_state('minecraft:cardinal_direction') == 'north' && !q.block_state('{NS}:lit')"]
    assert off_north["minecraft:light_emission"] == 0
    assert off_north["minecraft:selection_box"]["size"] == [8, 10, 8]
    assert "minecraft:transformation" not in off_north
    assert len(lamp["permutations"]) == 8


def test_multipart_and_uvlock(converted):
    box = _block(converted, "flip_box")
    assert box["components"]["minecraft:geometry"]["bone_visibility"] == {
        "m0": f"!q.block_state('{NS}:open')", "m1": f"q.block_state('{NS}:open')"}
    assert box["description"]["traits"]["minecraft:placement_direction"] == {
        "enabled_states": ["minecraft:cardinal_direction"]}
    # uvlock: one bone per model and turn, no transformation.
    item = _block(converted, "item_flip")
    vis = item["components"]["minecraft:geometry"]["bone_visibility"]
    assert len(vis) == 8
    assert vis["m0_y90"] == (f"q.block_state('minecraft:cardinal_direction') == 'east' && "
                             f"!q.block_state('{NS}:open')")
    assert not any("minecraft:transformation" in p["components"] for p in item.get("permutations", []))


def test_toggle_component_only_where_read(converted):
    assert f"{NS}:portkit_toggle" in _block(converted, "toggle_lamp")["components"]
    assert converted.files["blocks/toggle_lamp.json"]["format_version"] == "1.21.90"
    assert f"{NS}:portkit_toggle" in _block(converted, "flip_box")["components"]
    for name in ("item_flip", "powered_lamp"):
        assert f"{NS}:portkit_toggle" not in _block(converted, name)["components"]
        assert converted.files[f"blocks/{name}.json"]["format_version"] == "1.20.20"
    table = converted.files[f"scripts/portkit/data/{NS}_toggle.js"]
    assert f'"{NS}:toggle_lamp": "{NS}:lit"' in table and f'"{NS}:flip_box": "{NS}:open"' in table
    assert "item_flip" not in table
    assert "registerToggles" in converted.files["scripts/portkit/toggle.js"]


def test_vanilla_parent_stays_residue(converted):
    assert "blocks/gate_block.json" not in converted.files
    why = [u.reason for u in converted.unhandled if u.source.endswith("gate_block.json")]
    assert why and "is a vanilla FenceGateBlock" in why[0]


def test_notes_name_each_value(converted):
    notes = "\n".join(converted.notes)
    assert "4 block(s) with facing and boolean states convert" in notes
    assert ("powered=false (registered: com.example.deco.PoweredLampBlock#<init> (registerDefaultState); "
            "com.example.deco.PoweredLampBlock#getStateForPlacement sets it from the world): powered_lamp") in notes
    assert "on=true (any:" in notes
    assert "lit (com.example.deco.ToggleLampBlock#useWithoutItem): toggle_lamp" in notes
    assert "powered: Java changes it in neighborChanged+redstone (redstone: no Bedrock custom block input" in notes
    assert "com.example.deco.StateBlocks#lambda$static$0: none=0, lit=15: toggle_lamp" in notes


def test_without_classes_everything_is_a_labelled_default(tmp_path):
    result = blocks.convert(_mod(tmp_path, classes=False))
    lamp = _block(result, "toggle_lamp")
    assert lamp["description"]["states"] == {f"{NS}:lit": [False, True]}
    assert f"{NS}:portkit_toggle" not in lamp["components"]
    assert "minecraft:light_emission" not in json.dumps(lamp)
    notes = "\n".join(result.notes)
    assert "Starting value DEFAULT, not read from code (false) - " in notes
    assert "lit (the mod ships no class files): toggle_lamp" in notes
    assert f"scripts/portkit/data/{NS}_toggle.js" not in result.files


def test_a_block_that_fails_claims_no_models(tmp_path):
    mod = _mod(tmp_path)
    bs = mod.assets / "blockstates" / "toggle_lamp.json"
    data = json.loads(bs.read_text())
    data["variants"]["facing=north,lit=true"]["model"] = f"{NS}:block/missing"
    bs.write_text(json.dumps(data))
    (mod.assets / "models/block/lamp_on.json").unlink()
    (mod.assets / "models/block/only_here.json").write_text(json.dumps(_model(3, "wood")))
    result = blocks.convert(mod)
    assert "blocks/toggle_lamp.json" not in result.files
    assert f"assets/{NS}/blockstates/toggle_lamp.json" in result.consumed
    assert f"assets/{NS}/models/block/lamp_off.json" not in result.consumed or any(
        k.startswith("blocks/") and "lamp_off" in json.dumps(v) for k, v in result.files.items())


def test_main_js_wires_the_toggle_runtime(tmp_path):
    result = convert_all(_mod(tmp_path))
    main = result.files["scripts/portkit/main.js"]
    assert 'import { registerToggles } from "./toggle.js";' in main
    assert f'import toggleTable from "./data/{NS}_toggle.js";' in main
    assert "scripts/portkit/station_storage.js" not in result.files


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_runtime_flips_the_generated_table(tmp_path):
    result = blocks.convert(_mod(tmp_path))
    table = tmp_path / "toggle_table.js"
    table.write_text(result.files[f"scripts/portkit/data/{NS}_toggle.js"])
    proc = subprocess.run(
        ["node", "--import", str(JS / "register.mjs"), "--test", str(JS / "toggle.test.mjs")],
        capture_output=True, text=True, env={**os.environ, "PORTKIT_TOGGLE_TABLE": str(table)})
    assert proc.returncode == 0, proc.stdout + proc.stderr
