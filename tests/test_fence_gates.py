"""Fence gates (#367): one block on Bedrock's placement_direction trait; use, redstone and
in_wall by the fixed fence gate runtime; sounds from the gate's WoodType.

Offline: the gate templates here are hand-written shapes of vanilla's form
(``minecraft:block/template_fence_gate``, ``_open``, ``_wall``, ``_wall_open``), pointed at
with PORTKIT_MODEL_REFERENCE like tests/test_trapdoors.py; the bytecode reading uses
tests/test_doors.py's stand-in machine.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from portkit import blockcode, pack
from portkit.converters import blocks, convert_all, doors, fence_gates
from portkit.data import models as model_data, wood_types
from portkit.ingame import testpack
from portkit.model import SourceMod

from test_doors import PNG, ROOT, _Class, _Machine, _write

NS = "examplemod"
CARDINALS = ("north", "east", "south", "west")
# Java's gate blockstate turns (datagen BlockModelGenerators#createFenceGate): y 0/90/180/270
# for south/west/north/east, uvlock true.
_Y = {"south": 0, "west": 90, "north": 180, "east": 270}
GATE = wood_types.FENCE_GATE_CLASS


def _templates(tmp_path: Path) -> Path:
    """Hand-written gate templates (not Mojang's): a post pair, lower when in a wall."""
    face = {"texture": "#texture"}
    out = {"minecraft:block/block": {}}
    for suffix, top in (("", 16), ("_open", 16), ("_wall", 13), ("_wall_open", 13)):
        out[f"minecraft:block/template_fence_gate{suffix}"] = {
            "parent": "minecraft:block/block", "textures": {"particle": "#texture"},
            "elements": [{"from": [0, 5, 7], "to": [2, top, 9],
                          "faces": {d: dict(face) for d in ("north", "east", "south", "west", "up", "down")}},
                         {"from": [14, 5, 7], "to": [16, top, 9],
                          "faces": {d: dict(face) for d in ("north", "east", "south", "west", "up", "down")}}]}
    path = tmp_path / "gate_templates.json"
    path.write_text(json.dumps({"label": "hand-written test gate shapes", "set": "models-vanilla-1.20.1",
                                "models": out}))
    return path


@pytest.fixture
def templates(tmp_path, monkeypatch):
    path = _templates(tmp_path)
    monkeypatch.setenv("PORTKIT_MODEL_REFERENCE", str(path))
    return path


def gate_blockstate(name: str, ns: str = NS, extra: str = "") -> dict:
    variants = {}
    for facing in CARDINALS:
        for wall in (False, True):
            for opened in (False, True):
                suffix = ("_wall" if wall else "") + ("_open" if opened else "")
                entry = {"model": f"{ns}:block/{name}{suffix}", "uvlock": True}
                if _Y[facing]:
                    entry["y"] = _Y[facing]
                variants[f"facing={facing},in_wall={str(wall).lower()},open={str(opened).lower()}{extra}"] = entry
    return {"variants": variants}


def _gate(root: Path, name: str, ns: str = NS) -> None:
    _write(root, f"assets/{ns}/blockstates/{name}.json", gate_blockstate(name, ns))
    _write(root, f"assets/{ns}/textures/block/{name}.png", PNG.read_bytes())
    for suffix in ("", "_open", "_wall", "_wall_open"):
        _write(root, f"assets/{ns}/models/block/{name}{suffix}.json",
               {"parent": f"minecraft:block/template_fence_gate{suffix}",
                "textures": {"texture": f"{ns}:block/{name}"}})


def _gate_mod(tmp_path: Path, *, tagged=("oak_fence_gate",)) -> Path:
    root = tmp_path / "src"
    _gate(root, "oak_fence_gate")
    _gate(root, "odd_fence_gate")
    _write(root, "data/minecraft/tags/block/fence_gates.json",
           {"replace": False, "values": [f"{NS}:{n}" for n in tagged]})
    return root


def _mod(root: Path) -> SourceMod:
    return SourceMod(root=root, namespace=NS)


# -- detection ---------------------------------------------------------------

def test_gate_variants_need_all_16():
    variants, why = fence_gates.gate_variants(gate_blockstate("g"))
    assert why == "" and len(variants) == 16
    assert variants[("east", True, False)] == (f"{NS}:block/g_wall", 270, True)
    assert variants[("south", False, True)] == (f"{NS}:block/g_open", 0, True)
    missing = gate_blockstate("g")
    del missing["variants"]["facing=west,in_wall=true,open=true"]
    assert fence_gates.gate_variants(missing) == (None, "")


def test_drawless_powered_is_ignored_other_states_are_not_gates():
    plain, _ = fence_gates.gate_variants(gate_blockstate("g"))
    state = {"variants": {}}
    for extra in (",powered=false", ",powered=true"):
        state["variants"].update(gate_blockstate("g", extra=extra)["variants"])
    assert fence_gates.gate_variants(state)[0] == plain
    assert fence_gates.gate_variants(gate_blockstate("g", extra=",lit=false")) == (None, "")
    from test_trapdoors import trapdoor_blockstate
    assert fence_gates.gate_variants(trapdoor_blockstate("t")) == (None, "")


def test_unreadable_gate_variant_says_why():
    state = gate_blockstate("g")
    state["variants"]["facing=north,in_wall=false,open=false"] = {"model": "a", "x": 90}
    variants, why = fence_gates.gate_variants(state)
    assert variants is None and "turns by x=90" in why


def test_templates_are_fetched():
    for t in fence_gates.GATE_TEMPLATES:
        assert t.partition(":")[2] in model_data.TEMPLATES


# -- reading the WoodType -------------------------------------------------------

def _wood(desc, *args):
    obj = blockcode.Obj(wood_types.CLASS)
    obj.fields["__vanilla_ctor"] = (wood_types.CLASS, desc, tuple(args))
    return obj


def _gate_obj(cls, *ctor_args):
    obj = blockcode.Obj(cls)
    obj.fields["__vanilla_ctor"] = (GATE, "(...)V", tuple(ctor_args))
    return obj


def _se(name):
    return blockcode.Const(wood_types.SOUND_EVENTS, name)


def test_read_wood_constant_and_built_in_code():
    props = object()
    got = fence_gates.read_wood(_gate_obj(GATE, blockcode.Const(wood_types.CLASS, "CHERRY"), props))
    assert got == ("CHERRY_WOOD", "WoodType.CHERRY")
    # 1.20.1 order (Properties, WoodType).
    assert fence_gates.read_wood(_gate_obj(GATE, props, blockcode.Const(wood_types.CLASS, "OAK")))[0] == "WOOD"
    # Mantle's new WoodType(name, setType): the two-argument constructor's sounds.
    two = _wood(wood_types.TWO_ARG_CTOR, "tconstruct:greenheart", object())
    assert fence_gates.read_wood(_gate_obj(GATE, props, two)) == ("WOOD", "new WoodType(String, BlockSetType)")
    full = _wood(wood_types.CANONICAL_CTOR, "x", object(), object(), object(),
                 _se("NETHER_WOOD_FENCE_GATE_CLOSE"), _se("NETHER_WOOD_FENCE_GATE_OPEN"))
    assert fence_gates.read_wood(_gate_obj(GATE, full, props))[0] == "NETHER_WOOD"
    mixed = _wood(wood_types.CANONICAL_CTOR, "x", object(), object(), object(),
                  _se("FENCE_GATE_CLOSE"), _se("BAMBOO_WOOD_FENCE_GATE_OPEN"))
    family, why = fence_gates.read_wood(_gate_obj(GATE, mixed, props))
    assert family is None and "two families" in why
    family, why = fence_gates.read_wood(_gate_obj(GATE, blockcode.Const(wood_types.CLASS, "MODDED"), props))
    assert family is None and "isn't a vanilla constant" in why
    family, why = fence_gates.read_wood(_gate_obj(GATE, props, _se("FENCE_GATE_OPEN"), _se("FENCE_GATE_CLOSE")))
    assert family is None and "isn't given one WoodType" in why


def test_gate_types_cover_the_sound_table():
    assert set(wood_types.GATE_TYPES.values()) == set(wood_types.SOUNDS)
    assert wood_types.SOUNDS["WOOD"] == ("open.fence_gate", "close.fence_gate")
    assert "minecraft:cobblestone_wall" in wood_types.VANILLA_WALLS and len(wood_types.VANILLA_WALLS) == 26


def _read(monkeypatch, objs, chains, classes):
    machine = _Machine(chains, classes)
    monkeypatch.setattr(blockcode, "_registered", lambda c, names: (machine, objs))
    return doors.read_code(["stand-in"], list(objs), "gate")


def test_read_vanilla_gate(monkeypatch):
    own = "com/example/SpringGate"
    plain = "com/example/PlainGate"
    trap = "net/minecraft/world/level/block/TrapDoorBlock"
    got = _read(monkeypatch,
                {"bamboo": ([_gate_obj(GATE, blockcode.Const(wood_types.CLASS, "BAMBOO"), object())], ""),
                 "plain": ([_gate_obj(plain, blockcode.Const(wood_types.CLASS, "OAK"), object())], ""),
                 "spring": ([_gate_obj(own, blockcode.Const(wood_types.CLASS, "OAK"), object())], ""),
                 "trap": ([_gate_obj(trap)], ""),
                 "odd": ([_gate_obj(GATE, object())], ""),
                 "lost": ([], "registered through a library")},
                {GATE: [GATE], own: [own, GATE], plain: [plain, GATE], trap: [trap]},
                {own: _Class(["useWithoutItem", "<init>"]), plain: _Class(["<init>", "getName"])})
    assert got["bamboo"].verdict == "vanilla" and got["bamboo"].door == "BAMBOO_WOOD"
    assert got["plain"].verdict == "vanilla" and got["plain"].door == "WOOD"
    assert got["spring"].verdict == "refused" and "SpringGate#useWithoutItem" in got["spring"].why
    assert got["trap"].verdict == "refused" and "not FenceGateBlock" in got["trap"].why
    assert got["odd"].verdict == "vanilla" and got["odd"].door is None and "WoodType" in got["odd"].wood_why
    assert got["lost"].verdict == "unread"


# -- writing -----------------------------------------------------------------

def test_tagged_gate_converts_untagged_is_residue(tmp_path, templates):
    result = blocks.convert(_mod(_gate_mod(tmp_path)))
    doc = result.files["blocks/oak_fence_gate.json"]
    assert doc["format_version"] == fence_gates.GATE_FORMAT == "1.26.0"
    block = doc["minecraft:block"]
    assert block["description"]["traits"] == {
        "minecraft:placement_direction": {"enabled_states": ["minecraft:cardinal_direction"]}}
    assert block["description"]["states"] == {
        f"{NS}:open": [False, True], f"{NS}:in_wall": [False, True], f"{NS}:powered": [False, True]}
    assert block["components"]["minecraft:redstone_consumer"] == {"min_power": 0}
    assert f"{NS}:portkit_fence_gate" in block["components"]
    assert "blocks/odd_fence_gate.json" not in result.files
    (residue,) = [u for u in result.unhandled if "odd_fence_gate" in u.source]
    assert "fence_gates tag doesn't list" in residue.reason and "#367" in residue.reason
    note = next(n for n in result.notes if n.startswith("oak_fence_gate:"))
    assert "DEFAULT" in note and "wood fence gate sounds" in note and "away from the player" in note


def test_gate_permutations_and_boxes(tmp_path, templates):
    result = blocks.convert(_mod(_gate_mod(tmp_path)))
    perms = result.files["blocks/oak_fence_gate.json"]["minecraft:block"]["permutations"]
    assert len(perms) == 16 and len({p["condition"] for p in perms}) == 16
    by_cond = {p["condition"]: p["components"] for p in perms}
    # Java facing F is cardinal_direction F (the player's facing, as for doors).
    assert "'north'" in fence_gates.condition(NS, "north", False, False)
    north = by_cond[fence_gates.condition(NS, "north", False, False)]
    assert north["minecraft:collision_box"] == [{"origin": [-8, 0, -2], "size": [16, 24, 4]}]
    assert north["minecraft:selection_box"] == {"origin": [-8, 0, -2], "size": [16, 16, 4]}
    east_wall = by_cond[fence_gates.condition(NS, "east", True, False)]
    assert east_wall["minecraft:collision_box"] == [{"origin": [-2, 0, -8], "size": [4, 24, 16]}]
    assert east_wall["minecraft:selection_box"] == {"origin": [-2, 0, -8], "size": [4, 13, 16]}
    for facing in CARDINALS:
        for wall in (False, True):
            assert by_cond[fence_gates.condition(NS, facing, wall, True)]["minecraft:collision_box"] is False
    geo = result.files["models/blocks/oak_fence_gate.geo.json"]["minecraft:geometry"]
    assert len(geo) == 16 and all([b["name"] for b in g["bones"]] == ["root"] for g in geo)
    assert result.java_states[f"{NS}:oak_fence_gate"]["in_wall"]["true"] == f"q.block_state('{NS}:in_wall')"


def test_gate_table_runtime_entry_and_versions(tmp_path, templates):
    root = _gate_mod(tmp_path)
    result = convert_all(_mod(root))
    table = result.files[fence_gates.table_path(NS)]
    assert '"examplemod:oak_fence_gate"' in table and '"open.fence_gate"' in table
    assert '"minecraft:cobblestone_wall"' in table and '"portkit:fence_gate_use"' in table
    assert result.files[fence_gates.GATE_RUNTIME].startswith("// portkit runtime: fence gates")
    assert fence_gates.GATE_CORE in result.files
    entry = result.files["scripts/portkit/main.js"]
    assert "registerFenceGates(gateTable);" in entry
    assert pack.script_version(result.files) == (2, 5, 0)
    assert pack.engine_floor(result.files) >= (1, 26, 0)


def test_mod_walls_join_the_table(tmp_path, templates):
    root = _gate_mod(tmp_path)
    _write(root, f"assets/{NS}/blockstates/marble_wall.json", {"variants": {"": {"model": f"{NS}:block/marble"}}})
    _write(root, f"assets/{NS}/models/block/marble.json",
           {"parent": "minecraft:block/cube_all", "textures": {"all": f"{NS}:block/marble"}})
    _write(root, f"assets/{NS}/textures/block/marble.png", PNG.read_bytes())
    _write(root, "data/minecraft/tags/block/walls.json",
           {"values": [f"{NS}:marble_wall", f"{NS}:missing_wall", "other:wall", "#c:walls"]})
    result = convert_all(_mod(root))
    if "blocks/marble_wall.json" in result.files:
        assert fence_gates.mod_walls(_mod(root), result) == [f"{NS}:marble_wall"]
    assert f"{NS}:missing_wall" not in fence_gates.mod_walls(_mod(root), result)


def test_read_cherry_gate_and_unread_wood_without_tag(tmp_path, templates, monkeypatch):
    root = _gate_mod(tmp_path, tagged=())
    real = doors.read_code

    def fake(classes, names, kind, **kw):
        out = real(None, names, kind)
        if kind == "gate":
            r = out["oak_fence_gate"]
            r.verdict, r.cls, r.door, r.door_from = "vanilla", "net.minecraft.world.level.block.FenceGateBlock", \
                "CHERRY_WOOD", "WoodType.CHERRY"
            r = out["odd_fence_gate"]
            r.verdict, r.cls, r.door, r.wood_why = "vanilla", "net.minecraft.world.level.block.FenceGateBlock", \
                None, "its WoodType's constructor call isn't read"
        return out

    monkeypatch.setattr(doors, "read_code", fake)
    result = convert_all(_mod(root))
    assert "blocks/oak_fence_gate.json" in result.files
    assert '"open.cherry_wood_fence_gate"' in result.files[fence_gates.table_path(NS)]
    note = next(n for n in result.notes if n.startswith("oak_fence_gate:"))
    assert "read from its code" in note and "WoodType.CHERRY" in note and "cherry wood" in note
    (residue,) = [u for u in result.unhandled if "odd_fence_gate" in u.source]
    assert "read as vanilla" in residue.reason and "constructor call isn't read" in residue.reason


def test_no_templates_is_residue(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTKIT_MODEL_REFERENCE", str(tmp_path / "missing.json"))
    result = blocks.convert(_mod(_gate_mod(tmp_path)))
    assert "blocks/oak_fence_gate.json" not in result.files
    assert any("oak_fence_gate" in u.source for u in result.unhandled)
    assert fence_gates.table_path(NS) not in result.files


def test_in_game_check_reads_the_converted_gate(tmp_path, templates):
    result = convert_all(_mod(_gate_mod(tmp_path)))
    bp = tmp_path / "bp"
    for rel, body in result.files.items():
        if rel.startswith("blocks/") or rel.startswith("scripts/portkit/data/"):
            path = bp / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body if isinstance(body, str) else json.dumps(body))
    checks = testpack.read_checks(bp)
    assert checks.gates == [{"id": f"{NS}:oak_fence_gate",
                             "states": {"open": f"{NS}:open", "in_wall": f"{NS}:in_wall",
                                        "powered": f"{NS}:powered"},
                             "event": "portkit:fence_gate_use", "wall": "minecraft:cobblestone_wall",
                             "expect": [{"item": f"{NS}:oak_fence_gate", "count": 1}]}]


# -- the runtime under node -----------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_runtime_with_the_generated_table(tmp_path, templates):
    result = convert_all(_mod(_gate_mod(tmp_path)))
    table = tmp_path / "gates.mjs"
    table.write_text(result.files[fence_gates.table_path(NS)])
    run = subprocess.run(["node", "--import", "./tests/js/register.mjs", "--test", "tests/js/fence_gate.test.mjs"],
                         cwd=ROOT, capture_output=True, text=True, timeout=120,
                         env={**os.environ, "PORTKIT_FENCE_GATE_TABLE": str(table)})
    assert run.returncode == 0, run.stdout + run.stderr
