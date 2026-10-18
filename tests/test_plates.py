"""Pressure plates (#296, pick 7b of the doors decision): one block with a
redstone producer on its powered permutation, pressed and released by the
fixed polling runtime.

Offline: the plate templates here are hand-written shapes of vanilla's form
(``minecraft:block/pressure_plate_up`` 1 pixel tall, ``_down`` half a pixel,
both inset a pixel), pointed at with PORTKIT_MODEL_REFERENCE like
tests/test_trapdoors.py; the bytecode reading uses tests/test_doors.py's
stand-in machine.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from portkit import blockcode, pack
from portkit.converters import blocks, convert_all, doors, plates
from portkit.data import block_set_types, models as model_data
from portkit.ingame import testpack
from portkit.model import SourceMod

from test_doors import PNG, ROOT, _Class, _Machine, _write

NS = "examplemod"
PLATE = "net/minecraft/world/level/block/PressurePlateBlock"


def _templates(tmp_path: Path) -> Path:
    """Hand-written plate templates (not Mojang's)."""
    face = {"texture": "#texture"}
    out = {"minecraft:block/block": {}, "minecraft:block/thin_block": {"parent": "minecraft:block/block"}}
    for name, top in (("up", 1), ("down", 0.5)):
        out[f"minecraft:block/pressure_plate_{name}"] = {
            "parent": "minecraft:block/thin_block", "textures": {"particle": "#texture"},
            "elements": [{"from": [1, 0, 1], "to": [15, top, 15],
                          "faces": {d: dict(face) for d in ("north", "east", "south", "west", "up", "down")}}]}
    path = tmp_path / "plate_templates.json"
    path.write_text(json.dumps({"label": "hand-written test plate shapes", "set": "models-vanilla-1.20.1",
                                "models": out}))
    return path


@pytest.fixture
def templates(tmp_path, monkeypatch):
    path = _templates(tmp_path)
    monkeypatch.setenv("PORTKIT_MODEL_REFERENCE", str(path))
    return path


def plate_blockstate(name: str, ns: str = NS) -> dict:
    return {"variants": {"powered=false": {"model": f"{ns}:block/{name}"},
                         "powered=true": {"model": f"{ns}:block/{name}_down"}}}


def _plate(root: Path, name: str, ns: str = NS, parent: str = "minecraft:block/pressure_plate") -> None:
    _write(root, f"assets/{ns}/blockstates/{name}.json", plate_blockstate(name, ns))
    _write(root, f"assets/{ns}/textures/block/{name}.png", PNG.read_bytes())
    _write(root, f"assets/{ns}/models/block/{name}.json",
           {"parent": f"{parent}_up", "textures": {"texture": f"{ns}:block/{name}"}})
    _write(root, f"assets/{ns}/models/block/{name}_down.json",
           {"parent": f"{parent}_down", "textures": {"texture": f"{ns}:block/{name}"}})


def _plate_mod(tmp_path: Path, *, tagged=("oak_pressure_plate",)) -> Path:
    root = tmp_path / "src"
    _plate(root, "oak_pressure_plate")
    _plate(root, "stone_pressure_plate", parent="block/pressure_plate")
    _write(root, "data/minecraft/tags/block/wooden_pressure_plates.json",
           {"replace": False, "values": [f"{NS}:{n}" for n in tagged]})
    _write(root, f"data/{NS}/loot_table/blocks/oak_pressure_plate.json", {"type": "minecraft:block", "pools": [{
        "rolls": 1, "entries": [{"type": "minecraft:item", "name": f"{NS}:oak_pressure_plate"}],
        "conditions": [{"condition": "minecraft:survives_explosion"}]}]})
    return root


def _mod(root: Path) -> SourceMod:
    return SourceMod(root=root, namespace=NS)


# -- detection ---------------------------------------------------------------

def test_plate_variants_are_powered_only_and_unturned():
    variants, why = plates.plate_variants(plate_blockstate("p"))
    assert why == "" and variants == {False: f"{NS}:block/p", True: f"{NS}:block/p_down"}
    lit = {"variants": {"lit=false": {"model": "a"}, "lit=true": {"model": "b"}}}
    assert plates.plate_variants(lit) == (None, "")
    turned = plate_blockstate("p")
    turned["variants"]["powered=true"]["y"] = 90
    variants, why = plates.plate_variants(turned)
    assert variants is None and "turned" in why
    random = plate_blockstate("p")
    random["variants"]["powered=false"] = [{"model": "a"}, {"model": "b"}]
    assert "randomly" in plates.plate_variants(random)[1]


def test_only_plate_templates_make_a_plate(tmp_path):
    root = tmp_path / "src"
    _plate(root, "oak_pressure_plate")
    _plate(root, "lamp", parent="minecraft:block/cube")
    mod = _mod(root)
    assert plates.is_plate_shaped(mod, plates.plate_variants(plate_blockstate("oak_pressure_plate"))[0])
    assert not plates.is_plate_shaped(mod, plates.plate_variants(plate_blockstate("lamp"))[0])
    swapped = {False: f"{NS}:block/oak_pressure_plate_down", True: f"{NS}:block/oak_pressure_plate"}
    assert not plates.is_plate_shaped(mod, swapped)


class _Obj:
    def __init__(self, cls, *consts):
        self.cls = cls
        self.fields = {}
        if consts:
            self.fields["__vanilla_ctor"] = (PLATE, "()V", tuple(consts) + (object(),))


def _read(monkeypatch, objs, chains, classes):
    machine = _Machine(chains, classes)
    monkeypatch.setattr(blockcode, "_registered", lambda c, names: (machine, objs))
    return doors.read_code(["stand-in"], list(objs), "plate")


def _set(name):
    return blockcode.Const(block_set_types.CLASS, name)


def _sens(name):
    return blockcode.Const(block_set_types.SENSITIVITY_CLASS, name)


def test_read_vanilla_plate_1_21_and_1_20(monkeypatch):
    own = "com/example/PlayerPlate"
    weighted = "net/minecraft/world/level/block/WeightedPressurePlateBlock"
    got = _read(monkeypatch,
                {"oak": ([_Obj(PLATE, _set("OAK"))], ""), "stone": ([_Obj(PLATE, _set("STONE"))], ""),
                 "old_stone": ([_Obj(PLATE, _sens("MOBS"), _set("OAK"))], ""),
                 "own": ([_Obj(own, _set("STONE"))], ""), "gold": ([_Obj(weighted, _set("GOLD"))], ""),
                 "custom": ([_Obj(PLATE, blockcode.Const("com/example/Types", "ROCK"))], ""),
                 "lost": ([], "registered through a library")},
                {PLATE: [PLATE], own: [own, PLATE], weighted: [weighted]},
                {own: _Class(["getSignalStrength", "<init>"])})
    assert got["oak"].verdict == "vanilla" and got["oak"].door == ("EVERYTHING", "WOODEN")
    assert got["oak"].door_from == "BlockSetType.OAK"
    assert got["stone"].door == ("MOBS", "STONE")
    # 1.20.1: the constructor's Sensitivity wins over the BlockSetType's (1.21) one.
    assert got["old_stone"].door == ("MOBS", "WOODEN")
    assert got["old_stone"].door_from == "Sensitivity.MOBS, BlockSetType.OAK"
    assert got["own"].verdict == "refused" and "PlayerPlate#getSignalStrength" in got["own"].why
    assert got["gold"].verdict == "refused" and "not PressurePlateBlock" in got["gold"].why
    assert got["custom"].verdict == "vanilla" and got["custom"].door is None
    assert got["lost"].verdict == "unread"


def test_plate_types_and_sounds_cover_every_constant():
    assert set(block_set_types.PLATE_TYPES) == set(block_set_types.DOOR_TYPES)
    assert {f for _, f in block_set_types.PLATE_TYPES.values()} == set(block_set_types.PLATE_SOUNDS)
    assert {s for s, _ in block_set_types.PLATE_TYPES.values()} == set(block_set_types.SENSITIVITIES)
    assert block_set_types.PLATE_TYPES["STONE"] == ("MOBS", "STONE")
    assert block_set_types.PLATE_SOUNDS["WOODEN"][:2] == ("click_on.wooden_pressure_plate",
                                                         "click_off.wooden_pressure_plate")


def test_templates_are_fetched():
    for t in plates.PLATE_TEMPLATES:
        assert t.partition(":")[2] in model_data.TEMPLATES


# -- writing -----------------------------------------------------------------

def test_tagged_plate_converts_untagged_is_residue(tmp_path, templates):
    result = blocks.convert(_mod(_plate_mod(tmp_path)))
    doc = result.files["blocks/oak_pressure_plate.json"]
    assert doc["format_version"] == plates.PLATE_FORMAT == "1.21.130"
    block = doc["minecraft:block"]
    assert block["description"]["states"] == {f"{NS}:powered": [False, True]}
    comps = block["components"]
    assert comps["minecraft:collision_box"] is False
    assert comps["minecraft:redstone_producer"] == {"power": 0, "strongly_powered_face": "down"}
    assert comps["minecraft:tick"] == {"interval_range": [2, 2], "looping": True}
    assert comps["minecraft:placement_filter"] == {"conditions": [{"allowed_faces": ["up"]}]}
    assert comps["minecraft:selection_box"] == {"origin": [-7.0, 0.0, -7.0], "size": [14.0, 1.0, 14.0]}
    assert comps["minecraft:geometry"].endswith(".up") and f"{NS}:portkit_pressure_plate" in comps
    (perm,) = block["permutations"]
    assert perm["condition"] == f"q.block_state('{NS}:powered')"
    assert perm["components"]["minecraft:geometry"].endswith(".down")
    assert perm["components"]["minecraft:redstone_producer"] == {"power": 15, "strongly_powered_face": "down"}
    assert perm["components"]["minecraft:selection_box"]["size"] == [14.0, 0.5, 14.0]
    assert "blocks/stone_pressure_plate.json" not in result.files
    (residue,) = [u for u in result.unhandled if "stone_pressure_plate" in u.source]
    assert "wooden_pressure_plates tag doesn't list" in residue.reason and "#296" in residue.reason
    note = next(n for n in result.notes if n.startswith("oak_pressure_plate:"))
    assert "DEFAULT" in note and "any entity" in note and "wooden pressure plate clicks" in note
    assert "20-tick" in note
    geo = result.files["models/blocks/oak_pressure_plate.geo.json"]["minecraft:geometry"]
    assert sorted(g["description"]["identifier"].rsplit(".", 1)[1] for g in geo) == ["down", "up"]
    assert result.java_states[f"{NS}:oak_pressure_plate"]["powered"]["true"] == f"q.block_state('{NS}:powered')"


def test_plate_table_runtime_entry_and_versions(tmp_path, templates):
    result = convert_all(_mod(_plate_mod(tmp_path)))
    table = result.files[plates.table_path(NS)]
    body = json.loads(table.partition("export default ")[2].rstrip().rstrip(";"))
    assert body["pressed_ticks"] == 20 and body["powered"] == f"{NS}:powered"
    assert body["touch"] == {"min": [0.0625, 0.0, 0.0625], "max": [0.9375, 0.25, 0.9375]}
    assert body["plates"][f"{NS}:oak_pressure_plate"] == {
        "mobs_only": False, "on_sound": "click_on.wooden_pressure_plate",
        "off_sound": "click_off.wooden_pressure_plate", "on_pitch": 1.0, "off_pitch": 1.0}
    assert result.files[plates.PLATE_RUNTIME].startswith("// portkit runtime: pressure plates")
    assert plates.PLATE_CORE in result.files
    entry = result.files["scripts/portkit/main.js"]
    assert "registerPressurePlates(plateTable);" in entry and "registerTrapdoors" not in entry
    assert pack.script_version(result.files) == (2, 0, 0)
    assert pack.engine_floor(result.files) >= (1, 21, 130)
    assert not [u for u in result.unhandled if "loot_table/blocks/oak_pressure_plate" in u.source]


def test_read_stone_plate_is_mobs_only(tmp_path, templates, monkeypatch):
    root = _plate_mod(tmp_path)
    real = doors.read_code

    def fake(classes, names, kind):
        out = real(None, names, kind)
        if kind == "plate" and "stone_pressure_plate" in out:
            r = out["stone_pressure_plate"]
            r.verdict, r.cls, r.door, r.door_from = "vanilla", "net.minecraft.world.level.block.PressurePlateBlock", \
                ("MOBS", "STONE"), "BlockSetType.STONE"
        return out

    monkeypatch.setattr(doors, "read_code", fake)
    result = convert_all(_mod(root))
    assert "blocks/stone_pressure_plate.json" in result.files
    table = result.files[plates.table_path(NS)]
    assert '"click_on.stone_pressure_plate"' in table and '"mobs_only": true' in table
    note = next(n for n in result.notes if n.startswith("stone_pressure_plate:"))
    assert "players and mobs" in note and "read from its code" in note and "BlockSetType.STONE" in note


def test_no_templates_is_residue(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTKIT_MODEL_REFERENCE", str(tmp_path / "missing.json"))
    result = blocks.convert(_mod(_plate_mod(tmp_path)))
    assert "blocks/oak_pressure_plate.json" not in result.files
    assert any("oak_pressure_plate" in u.source for u in result.unhandled)
    assert plates.table_path(NS) not in result.files


def test_in_game_check_reads_the_converted_plate(tmp_path, templates):
    result = convert_all(_mod(_plate_mod(tmp_path)))
    bp = tmp_path / "bp"
    for rel, body in result.files.items():
        if rel.startswith("blocks/") or rel.startswith("scripts/"):
            path = bp / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body if isinstance(body, str) else json.dumps(body))
    checks = testpack.read_checks(bp)
    assert checks.plates == [{"id": f"{NS}:oak_pressure_plate", "powered": f"{NS}:powered", "mobs_only": False,
                              "expect": [{"item": f"{NS}:oak_pressure_plate", "count": 1}]}]
    assert checks.as_json()["plates"] == checks.plates


# -- the runtime under node -----------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_runtime_with_the_generated_table(tmp_path, templates):
    result = convert_all(_mod(_plate_mod(tmp_path)))
    table = tmp_path / "plates.mjs"
    table.write_text(result.files[plates.table_path(NS)])
    run = subprocess.run(["node", "--import", "./tests/js/register.mjs", "--test", "tests/js/pressure_plate.test.mjs"],
                         cwd=ROOT, capture_output=True, text=True, timeout=120,
                         env={**os.environ, "PORTKIT_PLATE_TABLE": str(table)})
    assert run.returncode == 0, run.stdout + run.stderr
