"""Trapdoors (#296, pick 7a of the doors decision): one block on Bedrock's
placement traits, use and redstone by the fixed trapdoor runtime.

Offline: the trapdoor templates here are hand-written shapes of vanilla's
form (``minecraft:block/template_trapdoor_{bottom,top,open}``: a 3-pixel slab
at the bottom, the top, or the south side), pointed at with
PORTKIT_MODEL_REFERENCE like tests/test_doors.py; the bytecode reading uses
that file's stand-in machine.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from portkit import blockcode, pack
from portkit.converters import blocks, convert_all, doors, trapdoors
from portkit.data import block_set_types, models as model_data
from portkit.ingame import testpack
from portkit.model import SourceMod

from test_doors import PNG, ROOT, _Class, _Machine, _write

NS = "examplemod"
CARDINALS = ("north", "east", "south", "west")
# Java's trapdoor blockstate turns (datagen BlockModelGenerators#createTrapdoor):
# y 0/90/180/270 for north/east/south/west; an orientable trapdoor's open top
# half adds x 180 and a half turn of y.
_Y = {"north": 0, "east": 90, "south": 180, "west": 270}
TRAP = "net/minecraft/world/level/block/TrapDoorBlock"


def _templates(tmp_path: Path) -> Path:
    """Hand-written trapdoor templates (not Mojang's)."""
    face = {"texture": "#texture"}
    boxes = {"bottom": ([0, 0, 0], [16, 3, 16]), "top": ([0, 13, 0], [16, 16, 16]),
             "open": ([0, 0, 13], [16, 16, 16])}
    out = {"minecraft:block/block": {}}
    for kind in ("", "orientable_"):
        for part, (lo, hi) in boxes.items():
            out[f"minecraft:block/template_{kind}trapdoor_{part}"] = {
                "parent": "minecraft:block/block", "textures": {"particle": "#texture"},
                "elements": [{"from": lo, "to": hi, "faces": {d: dict(face) for d in
                                                              ("north", "east", "south", "west", "up", "down")}}]}
    path = tmp_path / "trapdoor_templates.json"
    path.write_text(json.dumps({"label": "hand-written test trapdoor shapes", "set": "models-vanilla-1.20.1",
                                "models": out}))
    return path


@pytest.fixture
def templates(tmp_path, monkeypatch):
    path = _templates(tmp_path)
    monkeypatch.setenv("PORTKIT_MODEL_REFERENCE", str(path))
    return path


def trapdoor_blockstate(name: str, ns: str = NS, orientable: bool = True, extra: str = "") -> dict:
    variants = {}
    for facing in CARDINALS:
        for half in ("bottom", "top"):
            for opened in (False, True):
                part = "open" if opened else half
                entry = {"model": f"{ns}:block/{name}_{part}"}
                y = _Y[facing]
                if orientable and opened and half == "top":
                    entry["x"] = 180
                    y = (y + 180) % 360
                if y:
                    entry["y"] = y
                variants[f"facing={facing},half={half},open={str(opened).lower()}{extra}"] = entry
    return {"variants": variants}


def _trapdoor(root: Path, name: str, ns: str = NS, orientable: bool = True) -> None:
    _write(root, f"assets/{ns}/blockstates/{name}.json", trapdoor_blockstate(name, ns, orientable))
    _write(root, f"assets/{ns}/textures/block/{name}.png", PNG.read_bytes())
    kind = "orientable_" if orientable else ""
    for part in ("bottom", "top", "open"):
        _write(root, f"assets/{ns}/models/block/{name}_{part}.json",
               {"parent": f"minecraft:block/template_{kind}trapdoor_{part}",
                "textures": {"texture": f"{ns}:block/{name}"}})


def _trapdoor_mod(tmp_path: Path, *, tagged=("oak_trapdoor",)) -> Path:
    root = tmp_path / "src"
    _trapdoor(root, "oak_trapdoor")
    _trapdoor(root, "iron_trapdoor", orientable=False)
    _write(root, "data/minecraft/tags/block/wooden_trapdoors.json",
           {"replace": False, "values": [f"{NS}:{n}" for n in tagged]})
    _write(root, f"data/{NS}/loot_table/blocks/oak_trapdoor.json", {"type": "minecraft:block", "pools": [{
        "rolls": 1, "entries": [{"type": "minecraft:item", "name": f"{NS}:oak_trapdoor"}],
        "conditions": [{"condition": "minecraft:survives_explosion"}]}]})
    return root


def _mod(root: Path) -> SourceMod:
    return SourceMod(root=root, namespace=NS)


# -- detection ---------------------------------------------------------------

def test_trapdoor_variants_need_all_16():
    variants, why = trapdoors.trapdoor_variants(trapdoor_blockstate("oak_trapdoor"))
    assert why == "" and len(variants) == 16
    assert variants[("east", "top", True)] == (f"{NS}:block/oak_trapdoor_open", 180, 270, False)
    assert variants[("north", "bottom", False)] == (f"{NS}:block/oak_trapdoor_bottom", 0, 0, False)
    missing = trapdoor_blockstate("oak_trapdoor")
    del missing["variants"]["facing=west,half=top,open=true"]
    assert trapdoors.trapdoor_variants(missing) == (None, "")


def test_drawless_powered_and_waterlogged_are_ignored():
    plain, _ = trapdoors.trapdoor_variants(trapdoor_blockstate("t"))
    state = {"variants": {}}
    for extra in (",powered=false,waterlogged=false", ",powered=true,waterlogged=false",
                  ",powered=false,waterlogged=true", ",powered=true,waterlogged=true"):
        state["variants"].update(trapdoor_blockstate("t", extra=extra)["variants"])
    assert trapdoors.trapdoor_variants(state)[0] == plain
    other = trapdoor_blockstate("t", extra=",lit=false")
    assert trapdoors.trapdoor_variants(other) == (None, "")


def test_door_and_slab_shapes_are_not_trapdoors():
    from test_doors import door_blockstate
    assert trapdoors.trapdoor_variants(door_blockstate("d")) == (None, "")
    bad_half = {"variants": {k.replace("half=top", "half=upper"): v
                             for k, v in trapdoor_blockstate("t")["variants"].items()}}
    assert trapdoors.trapdoor_variants(bad_half) == (None, "")


def test_unreadable_trapdoor_variant_says_why():
    state = trapdoor_blockstate("t")
    state["variants"]["facing=north,half=bottom,open=false"] = {"model": "a", "x": 45}
    variants, why = trapdoors.trapdoor_variants(state)
    assert variants is None and "turns by x=45" in why


class _Obj:
    def __init__(self, cls, const=None):
        self.cls = cls
        self.fields = {}
        if const is not None:
            self.fields["__vanilla_ctor"] = (TRAP, "()V", (blockcode.Const(block_set_types.CLASS, const), object()))


def _read(monkeypatch, objs, chains, classes):
    machine = _Machine(chains, classes)
    monkeypatch.setattr(blockcode, "_registered", lambda c, names: (machine, objs))
    return doors.read_code(["stand-in"], list(objs), "trapdoor")


def test_read_vanilla_trapdoor(monkeypatch):
    own = "com/example/SpringTrapdoor"
    got = _read(monkeypatch,
                {"iron": ([_Obj(TRAP, "IRON")], ""), "crimson": ([_Obj(TRAP, "CRIMSON")], ""),
                 "spring": ([_Obj(own, "OAK")], ""), "door": ([_Obj("net/minecraft/world/level/block/DoorBlock")], ""),
                 "lost": ([], "registered through a library")},
                {TRAP: [TRAP], own: [own, TRAP], "net/minecraft/world/level/block/DoorBlock":
                 ["net/minecraft/world/level/block/DoorBlock"]},
                {own: _Class(["toggle", "<init>"])})
    assert got["iron"].verdict == "vanilla" and got["iron"].door == (False, "IRON")
    assert got["crimson"].door == (True, "NETHER_WOOD") and got["crimson"].door_from == "BlockSetType.CRIMSON"
    assert got["spring"].verdict == "refused" and "SpringTrapdoor#toggle" in got["spring"].why
    assert got["door"].verdict == "refused" and "not TrapDoorBlock" in got["door"].why
    assert got["lost"].verdict == "unread"


def test_wooden_trapdoors_tag(tmp_path):
    root = tmp_path / "src"
    _write(root, "data/minecraft/tags/blocks/wooden_trapdoors.json", {"values": [f"{NS}:a"]})
    _write(root, "data/minecraft/tags/block/wooden_trapdoors.json", {"values": [{"id": f"{NS}:b"}]})
    _write(root, "data/minecraft/tags/block/wooden_doors.json", {"values": [f"{NS}:c"]})
    assert doors.wooden_doors(_mod(root), "wooden_trapdoors") == {f"{NS}:a", f"{NS}:b"}


def test_sounds_cover_every_block_set_type_family():
    families = {family for _, family in block_set_types.DOOR_TYPES.values()}
    assert families == set(block_set_types.TRAPDOOR_SOUNDS)
    assert block_set_types.TRAPDOOR_SOUNDS["WOODEN"] == ("open.wooden_trapdoor", "close.wooden_trapdoor")


def test_templates_are_fetched():
    for t in trapdoors.TRAPDOOR_TEMPLATES:
        assert t.partition(":")[2] in model_data.TEMPLATES


# -- writing -----------------------------------------------------------------

def test_tagged_trapdoor_converts_untagged_is_residue(tmp_path, templates):
    result = blocks.convert(_mod(_trapdoor_mod(tmp_path)))
    doc = result.files["blocks/oak_trapdoor.json"]
    assert doc["format_version"] == trapdoors.TRAPDOOR_FORMAT == "1.26.0"
    block = doc["minecraft:block"]
    assert block["description"]["traits"] == {
        "minecraft:placement_direction": {"enabled_states": ["minecraft:cardinal_direction"]},
        "minecraft:placement_position": {"enabled_states": ["minecraft:vertical_half"]},
    }
    assert block["description"]["states"] == {f"{NS}:open": [False, True], f"{NS}:powered": [False, True]}
    assert block["components"]["minecraft:redstone_consumer"] == {"min_power": 0}
    assert f"{NS}:portkit_trapdoor" in block["components"]
    assert "minecraft:multi_block" not in block["description"]["traits"]
    assert "blocks/iron_trapdoor.json" not in result.files
    (residue,) = [u for u in result.unhandled if "iron_trapdoor" in u.source]
    assert "wooden_trapdoors tag doesn't list" in residue.reason and "#296" in residue.reason
    note = next(n for n in result.notes if n.startswith("oak_trapdoor:"))
    assert "DEFAULT" in note and "opens by hand" in note and "wooden trapdoor sounds" in note
    assert "waterlogging" in note
    assert result.paired_halves == {}


def test_trapdoor_permutations_and_boxes(tmp_path, templates):
    result = blocks.convert(_mod(_trapdoor_mod(tmp_path)))
    block = result.files["blocks/oak_trapdoor.json"]["minecraft:block"]
    perms = block["permutations"]
    assert len(perms) == 16 and len({p["condition"] for p in perms}) == 16
    for p in perms:
        assert set(p["components"]) == {"minecraft:geometry", "minecraft:collision_box", "minecraft:selection_box"}
    by_cond = {p["condition"]: p["components"] for p in perms}
    # Java facing north (hinged on the south side) is placed by a player facing south.
    north_open = by_cond[trapdoors.condition(NS, "north", "bottom", True)]
    assert "'south'" in trapdoors.condition(NS, "north", "bottom", True)
    assert north_open["minecraft:geometry"].endswith(".north_bottom_open")
    assert north_open["minecraft:collision_box"] == [{"origin": [-8.0, 0.0, 5.0], "size": [16.0, 16.0, 3.0]}]
    top_closed = by_cond[trapdoors.condition(NS, "east", "top", False)]
    assert top_closed["minecraft:collision_box"] == [{"origin": [-8.0, 13.0, -8.0], "size": [16.0, 3.0, 16.0]}]
    # The orientable open top half (x 180, y +180) lands on the same side as the bottom one.
    for facing in CARDINALS:
        a = by_cond[trapdoors.condition(NS, facing, "bottom", True)]["minecraft:collision_box"]
        b = by_cond[trapdoors.condition(NS, facing, "top", True)]["minecraft:collision_box"]
        assert a == b, facing
    geo = result.files["models/blocks/oak_trapdoor.geo.json"]["minecraft:geometry"]
    assert len(geo) == 16 and all([b["name"] for b in g["bones"]] == ["root"] for g in geo)
    assert result.java_states[f"{NS}:oak_trapdoor"]["half"]["top"] == \
        "q.block_state('minecraft:vertical_half') == 'top'"


def test_trapdoor_table_runtime_entry_and_versions(tmp_path, templates):
    result = convert_all(_mod(_trapdoor_mod(tmp_path)))
    table = result.files[trapdoors.table_path(NS)]
    assert '"examplemod:oak_trapdoor"' in table and '"open.wooden_trapdoor"' in table
    assert result.files[trapdoors.TRAPDOOR_RUNTIME].startswith("// portkit runtime: trapdoors")
    assert doors.DOOR_CORE in result.files
    assert doors.door_table_path(NS) not in result.files
    entry = result.files["scripts/portkit/main.js"]
    assert "registerTrapdoors(trapdoorTable);" in entry and "registerDoors" not in entry
    assert pack.script_version(result.files) == (2, 5, 0)
    assert pack.engine_floor(result.files) >= (1, 26, 0)
    # The loot table converts: one trapdoor per break.
    assert not [u for u in result.unhandled if "loot_table/blocks/oak_trapdoor" in u.source]


def test_read_iron_trapdoor_opens_only_by_redstone(tmp_path, templates, monkeypatch):
    root = _trapdoor_mod(tmp_path)
    real = doors.read_code

    def fake(classes, names, kind):
        out = real(None, names, kind)
        if kind == "trapdoor" and "iron_trapdoor" in out:
            r = out["iron_trapdoor"]
            r.verdict, r.cls, r.door, r.door_from = "vanilla", "net.minecraft.world.level.block.TrapDoorBlock", \
                (False, "IRON"), "BlockSetType.IRON"
        return out

    monkeypatch.setattr(doors, "read_code", fake)
    result = convert_all(_mod(root))
    assert "blocks/iron_trapdoor.json" in result.files
    table = result.files[trapdoors.table_path(NS)]
    assert '"open.iron_trapdoor"' in table
    note = next(n for n in result.notes if n.startswith("iron_trapdoor:"))
    assert "opens only by redstone" in note and "read from its code" in note and "BlockSetType.IRON" in note


def test_no_templates_is_residue(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTKIT_MODEL_REFERENCE", str(tmp_path / "missing.json"))
    result = blocks.convert(_mod(_trapdoor_mod(tmp_path)))
    assert "blocks/oak_trapdoor.json" not in result.files
    assert any("oak_trapdoor" in u.source for u in result.unhandled)
    assert trapdoors.table_path(NS) not in result.files


def test_in_game_check_reads_the_converted_trapdoor(tmp_path, templates):
    result = convert_all(_mod(_trapdoor_mod(tmp_path)))
    bp = tmp_path / "bp"
    for rel, body in result.files.items():
        if rel.startswith("blocks/"):
            path = bp / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(body))
    checks = testpack.read_checks(bp)
    assert checks.trapdoors == [{"id": f"{NS}:oak_trapdoor",
                                 "states": {"open": f"{NS}:open", "powered": f"{NS}:powered"},
                                 "expect": [{"item": f"{NS}:oak_trapdoor", "count": 1}]}]


# -- the runtime under node -----------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_runtime_with_the_generated_table(tmp_path, templates):
    result = convert_all(_mod(_trapdoor_mod(tmp_path)))
    table = tmp_path / "trapdoors.mjs"
    table.write_text(result.files[trapdoors.table_path(NS)])
    run = subprocess.run(["node", "--import", "./tests/js/register.mjs", "--test", "tests/js/trapdoor.test.mjs"],
                         cwd=ROOT, capture_output=True, text=True, timeout=120,
                         env={**os.environ, "PORTKIT_TRAPDOOR_TABLE": str(table)})
    assert run.returncode == 0, run.stdout + run.stderr
