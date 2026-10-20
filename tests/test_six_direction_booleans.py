"""Blocks whose blockstate draws 6-way ``facing`` or ``face`` + ``facing``
together with one to four booleans (ceiling fans, light switches...): the
placement rule read per clicked face as for 6-way / attach-face blocks
(#218), each boolean's start, box, use toggle and light as for facing +
boolean blocks (#215), combined into one Bedrock block whose permutations
test the placement states and the boolean states together.

The class files under tests/data/blockcode/classes are javac 21 output of the
example mod in tests/data/blockcode/src (DirStateBlocks.java, FanBlock,
SwitchBlock, TopLitBlock; rebuild with build.sh): real compiler patterns, no
Minecraft code.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from portkit import blockcode
from portkit.bytecode import ClassIndex
from portkit.converters import blocks, convert_all
from portkit.model import SourceMod

from test_facing_boolean import NS, _png
from test_six_direction_facing import ATTACH_TURNS, ROD_TURNS, SIX

CLASSES = Path(__file__).parent / "data" / "blockcode" / "classes"
JS = Path(__file__).parent / "js"
SPECS = {"ceiling_fan": ("facing6", ("lit", "powered")), "switch": ("attach", ("enabled",)),
         "oak_knob": ("attach", ("powered",)), "top_lit": ("facing6", ("lit",))}
FACE = "q.block_state('minecraft:block_face')"


@pytest.fixture(scope="module")
def readings():
    return blockcode.read_directional_states(ClassIndex.from_source(CLASSES), SPECS)


# --- reading ------------------------------------------------------------------

def test_fan_rule_start_toggle_and_light(readings):
    fan = readings["ceiling_fan"]
    # getClickedFace().getOpposite(): clicking a ceiling's underside faces up.
    assert fan.rule["down"] == ("", ("dir", "up")) and fan.rule["east"] == ("", ("dir", "west"))
    assert fan.rule_from == "com.example.deco.FanBlock#getStateForPlacement"
    assert fan.defaults == {"lit": (False, "placed", "com.example.deco.FanBlock#getStateForPlacement"),
                            "powered": (False, "placed", "com.example.deco.FanBlock#getStateForPlacement")}
    # Flips lit on every path, client or server (no isClientSide test).
    assert (fan.toggle, fan.toggle_from) == ("lit", "com.example.deco.FanBlock#useWithoutItem")
    assert fan.changed_by == {"lit": ["useWithoutItem"]}
    assert fan.light_by == {(0, 0): 0, (0, 1): 0, (1, 0): 0, (1, 1): 15}
    assert (fan.light_kind, fan.light_source) == ("per_state", "com.example.deco.FanBlock#light")


def test_fan_shape_per_facing_and_boolean(readings):
    shapes = readings["ceiling_fan"].shapes_by
    assert len(shapes) == 6 * 4
    assert shapes[(("", "north"), (1, 0))] == ((2.0, 2.0, 10.0, 14.0, 14.0, 16.0),)
    assert shapes[(("", "north"), (0, 0))] == ((2.0, 2.0, 12.0, 14.0, 14.0, 16.0),)
    assert shapes[(("", "up"), (0, 1))] == ((2.0, 0.0, 2.0, 14.0, 4.0, 14.0),)


def test_switch_inherits_vanilla_attach_placement(readings):
    sw = readings["switch"]
    assert sw.rule == blockcode.default_rule("attach") and sw.support_assumed
    assert sw.rule_from.startswith("net.minecraft.world.level.block.FaceAttachedHorizontalDirectionalBlock"
                                   "#getStateForPlacement L39-52 (vanilla, inherited)")
    # The inherited placement starts from the registered default state.
    assert sw.defaults["enabled"][:2] == (False, "placed")
    assert (sw.toggle, sw.toggle_from) == ("enabled", "com.example.deco.SwitchBlock#useWithoutItem")
    assert sw.light_by == {(0,): 0, (1,): 7} and sw.collision is False
    assert sw.shapes_by[(("ceiling", "west"), (1,))] == ((5.0, 14.0, 4.0, 11.0, 16.0, 12.0),)


def test_vanilla_button_is_a_vanilla_parent_read_as_attach_face(readings):
    knob = readings["oak_knob"]
    assert knob.vanilla_parent == "net.minecraft.world.level.block.ButtonBlock"
    # #280: read like a plain attach-face block (FaceAttached placement,
    # supplied) and its ButtonBlock constructor call kept for buttons.py.
    assert knob.rule == blockcode.default_rule("attach") and knob.toggle is None
    owner, desc, args = knob.button_ctor
    assert owner == "net/minecraft/world/level/block/ButtonBlock"
    assert args[0] == blockcode.Const("net/minecraft/world/level/block/state/properties/BlockSetType", "OAK")
    assert args[1] == 30 and knob.button_overrides == []


def test_start_that_depends_on_the_clicked_face_is_the_registered_one(readings):
    top = readings["top_lit"]
    value, kind, src = top.defaults["lit"]
    assert (value, kind) == (False, "registered")
    assert "TopLitBlock#getStateForPlacement differs between paths" in src


# --- blockstates ------------------------------------------------------------------

def _fan_states(model_off: str, model_on: str) -> dict:
    variants = {}
    for d, (x, y) in ROD_TURNS.items():
        for lit in ("false", "true"):
            for powered in ("false", "true"):
                model = model_on if lit == "true" and powered == "true" else model_off
                variants[f"facing={d},lit={lit},powered={powered}"] = {
                    "model": model, **({"x": x} if x else {}), **({"y": y} if y else {})}
    return {"variants": variants}


def _switch_states(model_off: str, model_on: str) -> dict:
    return {"variants": {
        f"enabled={e},face={f},facing={d}": {"model": model_on if e == "true" else model_off,
                                              **({"x": x} if x else {}), **({"y": y} if y else {})}
        for (f, d), (x, y) in ATTACH_TURNS.items() for e in ("false", "true")}}


def test_variants_parse():
    kind, bools, cells, why = blocks._directional_bool_variants(_fan_states("a", "b"))
    assert (kind, bools, why) == ("facing6", ("lit", "powered"), "")
    assert cells[(("", "west"), (1, 1))] == ("b", 90, 270, False)
    assert cells[(("", "west"), (1, 0))] == ("a", 90, 270, False)
    kind, bools, cells, _ = blocks._directional_bool_variants(_switch_states("a", "b"))
    assert (kind, bools) == ("attach", ("enabled",)) and len(cells) == 24
    # Without booleans it is #218's, not this.
    assert blocks._directional_bool_variants({"variants": {f"facing={d}": {"model": "m"} for d in SIX}})[0] is None
    five = {"variants": {f"facing={d},a=true,b=true,c=true,d=true,e=true": {"model": "m"} for d in SIX}}
    assert "5 booleans, more than 4" in blocks._directional_bool_variants(five)[3]
    missing = _fan_states("a", "b")
    del missing["variants"]["facing=up,lit=true,powered=true"]
    assert blocks._directional_bool_variants(missing)[3] == (
        "6-way facing and booleans: not every combination has a variant")


def test_multipart_one_part_per_state():
    parts = [{"when": {"facing": d, "lit": v}, "apply": {"model": f"m_{v}", **({"x": x} if x else {}),
                                                         **({"y": y} if y else {})}}
             for d, (x, y) in ROD_TURNS.items() for v in ("true", "false")]
    kind, bools, cells, why = blocks._directional_bool_variants({"multipart": parts})
    assert (kind, bools, why) == ("facing6", ("lit",), "")
    assert cells[(("", "down"), (1,))] == ("m_true", 180, 0, False)
    twice = parts + [{"when": {"facing": "down"}, "apply": {"model": "extra"}}]
    assert "draws 2 parts at facing=down" in blocks._directional_bool_variants({"multipart": twice})[3]


def test_bedrock_permutation_count_stays_far_below_the_limit():
    # A block can't have more than 65,536 permutations (Bedrock-OSS
    # bedrock-wiki docs/blocks/block-permutations.md); the most this path can
    # give is block_face x cardinal_direction x facing_direction x 2^4.
    assert 6 * 4 * 6 * 2 ** blocks._MAX_BOOLS < 65_536


# --- conversion ------------------------------------------------------------------

def _model(depth: int) -> dict:
    faces = {f: {"texture": "#all"} for f in SIX}
    return {"textures": {"all": f"{NS}:block/wood", "particle": f"{NS}:block/wood"},
            "elements": [{"from": [2, 0, 2], "to": [14, depth, 14], "faces": faces}]}


def _mod(tmp_path: Path, classes: bool = True) -> SourceMod:
    root = tmp_path / "mod"
    for sub in ("textures/block", "models/block", "blockstates"):
        (root / f"assets/{NS}/{sub}").mkdir(parents=True)
    (root / f"assets/{NS}/textures/block/wood.png").write_bytes(_png())
    for name, depth in (("fan_off", 4), ("fan_on", 6), ("switch_off", 2), ("switch_on", 3)):
        (root / f"assets/{NS}/models/block/{name}.json").write_text(json.dumps(_model(depth)))
    states = {"ceiling_fan": _fan_states(f"{NS}:block/fan_off", f"{NS}:block/fan_on"),
              "top_lit": _fan_states(f"{NS}:block/fan_off", f"{NS}:block/fan_on"),
              "switch": _switch_states(f"{NS}:block/switch_off", f"{NS}:block/switch_on"),
              "oak_knob": _switch_states(f"{NS}:block/switch_off", f"{NS}:block/switch_on")}
    # top_lit draws lit only.
    states["top_lit"] = {"variants": {k.replace(",powered=false", ""): v for k, v in
                                      states["top_lit"]["variants"].items() if k.endswith("powered=false")}}
    states["oak_knob"] = {"variants": {k.replace("enabled=", "powered="): v
                                       for k, v in states["oak_knob"]["variants"].items()}}
    for name, bs in states.items():
        (root / f"assets/{NS}/blockstates/{name}.json").write_text(json.dumps(bs))
    return SourceMod(root=root, namespace=NS, classes=ClassIndex.from_source(CLASSES) if classes else None)


@pytest.fixture()
def converted(tmp_path):
    return blocks.convert(_mod(tmp_path))


def _block(result, name):
    return result.files[f"blocks/{name}.json"]["minecraft:block"]


def test_fan_states_and_traits(converted):
    fan = _block(converted, "ceiling_fan")
    assert fan["description"]["states"] == {f"{NS}:lit": [False, True], f"{NS}:powered": [False, True]}
    assert fan["description"]["traits"] == {
        "minecraft:placement_position": {"enabled_states": ["minecraft:block_face"]}}
    assert converted.files["blocks/ceiling_fan.json"]["format_version"] == "1.21.90"
    assert f"{NS}:portkit_toggle" in fan["components"]


def test_fan_models_per_face_and_boolean(converted):
    vis = _block(converted, "ceiling_fan")["components"]["minecraft:geometry"]["bone_visibility"]
    # Clicking a ceiling's underside (block_face down) places it facing up:
    # the unturned model, x=0.
    on = f"q.block_state('{NS}:lit') && q.block_state('{NS}:powered')"
    assert vis["m1_x0"] == f"{FACE} == 'down' && {on}"
    assert vis["m0_x0"].count(f"{FACE} == 'down'") == 3 and f"'down' && {on})" not in vis["m0_x0"]
    geo = converted.files["models/blocks/ceiling_fan.geo.json"]["minecraft:geometry"][0]
    assert {b["name"] for b in geo["bones"]} == {f"m{m}_x{x}" for m in (0, 1) for x in (0, 90, 180)}


def test_fan_permutations(converted):
    perms = {p["condition"]: p["components"] for p in _block(converted, "ceiling_fan")["permutations"]}
    # Light follows the booleans alone; the turn follows the face alone.
    assert perms[f"q.block_state('{NS}:lit') && q.block_state('{NS}:powered')"] == {"minecraft:light_emission": 15}
    assert perms[f"!q.block_state('{NS}:lit') && q.block_state('{NS}:powered')"] == {"minecraft:light_emission": 0}
    # Clicked east -> facing west (x=90, y=270): Bedrock turns +90.
    assert perms[f"{FACE} == 'east'"] == {"minecraft:transformation": {"rotation": [0, 90, 0]}}
    # The box follows both: Java's lit box (2,2,10)-(14,14,16) at facing north
    # (clicked south), in the turned model's frame.
    north_lit = perms[f"{FACE} == 'south' && q.block_state('{NS}:lit') && !q.block_state('{NS}:powered')"]
    assert set(north_lit) == {"minecraft:collision_box", "minecraft:selection_box"}
    assert north_lit["minecraft:selection_box"]["size"] == [12, 12, 6]


def test_switch_conditions_and_toggle(converted):
    sw = _block(converted, "switch")
    traits = sw["description"]["traits"]
    assert set(traits) == {"minecraft:placement_position", "minecraft:placement_direction"}
    vis = sw["components"]["minecraft:geometry"]["bone_visibility"]
    assert vis["m1_x0"] == f"{FACE} == 'up' && q.block_state('{NS}:enabled')"
    assert vis["m0_x180"] == f"{FACE} == 'down' && !q.block_state('{NS}:enabled')"
    perms = {p["condition"]: p["components"] for p in sw["permutations"]}
    assert perms[f"q.block_state('{NS}:enabled')"] == {"minecraft:light_emission": 7}
    # noCollission, read.
    assert all(c.get("minecraft:collision_box", False) is False for c in perms.values())
    table = converted.files[f"scripts/portkit/data/{NS}_toggle.js"]
    assert f'"{NS}:switch": "{NS}:enabled"' in table and f'"{NS}:ceiling_fan": "{NS}:lit"' in table


def test_button_converts_and_start_fallback(converted):
    # #280: vanilla ButtonBlock(BlockSetType.OAK, 30, ...) converts with the
    # button runtime (tests/test_buttons.py has the rest).
    knob = _block(converted, "oak_knob")
    assert f"{NS}:portkit_button" in knob["components"]
    assert not [u.reason for u in converted.unhandled if u.source.endswith("oak_knob.json")]
    top = _block(converted, "top_lit")
    assert top["description"]["states"] == {f"{NS}:lit": [False, True]}
    assert f"{NS}:portkit_toggle" not in top["components"]


def test_notes(converted):
    notes = "\n".join(converted.notes)
    assert "4 6-way facing / attach-face block(s) with boolean states convert" in notes
    assert "lit (com.example.deco.FanBlock#useWithoutItem): ceiling_fan" in notes
    assert "enabled (com.example.deco.SwitchBlock#useWithoutItem): switch" in notes
    assert "powered: no method of the block's own classes sets it" in notes
    assert "com.example.deco.FanBlock#light: none=0, powered=0, lit=0, lit+powered=15: ceiling_fan" in notes
    assert "lit=false (registered: com.example.deco.TopLitBlock#<init>" in notes
    assert "Support is not emulated" in notes and "switch" in notes


def test_without_classes_everything_is_a_labelled_default(tmp_path):
    result = blocks.convert(_mod(tmp_path, classes=False))
    fan = _block(result, "ceiling_fan")
    assert fan["description"]["states"] == {f"{NS}:lit": [False, True], f"{NS}:powered": [False, True]}
    # DEFAULT 6-way rule: facing = the clicked face, so clicking up shows x=0.
    vis = fan["components"]["minecraft:geometry"]["bone_visibility"]
    assert vis["m1_x0"] == f"{FACE} == 'up' && q.block_state('{NS}:lit') && q.block_state('{NS}:powered')"
    assert f"{NS}:portkit_toggle" not in fan["components"]
    assert "minecraft:light_emission" not in json.dumps(fan)
    # Unread, a button's vanilla class isn't known: a static DEFAULT block.
    assert "blocks/oak_knob.json" in result.files
    notes = "\n".join(result.notes)
    assert "Starting value DEFAULT, not read from code (false) - " in notes
    assert "6-way facing placement DEFAULT" in notes


def test_a_block_that_fails_claims_no_models(tmp_path):
    mod = _mod(tmp_path)
    bs = mod.assets / "blockstates" / "ceiling_fan.json"
    data = json.loads(bs.read_text())
    data["variants"]["facing=up,lit=true,powered=true"]["model"] = f"{NS}:block/missing"
    bs.write_text(json.dumps(data))
    result = blocks.convert(mod)
    assert "blocks/ceiling_fan.json" not in result.files
    assert f"assets/{NS}/blockstates/ceiling_fan.json" in result.consumed
    assert any(u.source.endswith("ceiling_fan.json") and "missing" in u.reason for u in result.unhandled)


def test_main_js_wires_the_toggle_runtime(tmp_path):
    result = convert_all(_mod(tmp_path))
    assert 'import { registerToggles } from "./toggle.js";' in result.files["scripts/portkit/main.js"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_runtime_flips_the_generated_table(tmp_path):
    result = blocks.convert(_mod(tmp_path))
    table = tmp_path / "toggle_table.js"
    table.write_text(result.files[f"scripts/portkit/data/{NS}_toggle.js"])
    proc = subprocess.run(
        ["node", "--import", str(JS / "register.mjs"), "--test", str(JS / "toggle.test.mjs")],
        capture_output=True, text=True, env={**os.environ, "PORTKIT_TOGGLE_TABLE": str(table)})
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_a_definition_named_like_a_tooling_file_is_written_beside_it(tmp_path):
    # mct reads any package.json as npm's; a pack with scripts then fails its
    # SCRIPTMODULE check. Bedrock finds item definitions by folder.
    from portkit.model import ConversionResult
    from portkit.pack import write_tree

    files = {"items/package.json": {"format_version": "1.20.20"}, "items/box.json": {"format_version": "1.20.20"},
             "blocks/tsconfig.json": {"format_version": "1.20.20"}, "blocks/_jsdoc.json": {}, "blocks/jsdoc.json": {}}
    out = write_tree(ConversionResult(files=files), NS, tmp_path / "out")
    bp = out / "behavior_pack"
    assert (bp / "items/_package.json").is_file() and not (bp / "items/package.json").exists()
    assert (bp / "items/box.json").is_file() and (bp / "blocks/_tsconfig.json").is_file()
    # Never onto another definition's name.
    assert (bp / "blocks/jsdoc.json").is_file() and (bp / "blocks/_jsdoc.json").is_file()
