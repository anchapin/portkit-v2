"""Doors and plain two-tall blocks on Bedrock's multi_block trait (#296).

Offline: the door templates here are hand-written shapes of vanilla's form
(``minecraft:block/door_{bottom,top}_{left,right}[_open]``, a 3-pixel slab
on one side), pointed at with PORTKIT_MODEL_REFERENCE like
tests/test_shape_blocks.py. The bytecode reading is checked against a small
stand-in for :class:`portkit.blockcode.Machine` (no Minecraft classes are
vendored); the example mods are written into ``tmp_path``.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from portkit import blockcode, pack
from portkit.converters import blocks, convert_all, doors, loot
from portkit.data import block_set_types
from portkit.model import SourceMod

ROOT = Path(__file__).resolve().parents[1]
PNG = ROOT / "fixtures" / "agent_mod" / "input" / "assets" / "examplemod" / "textures" / "block" / "alloy_block.png"
JS = ROOT / "tests" / "js"
NS = "examplemod"
CARDINALS = ("north", "east", "south", "west")
# Java's door blockstate turns (datagen BlockModelGenerators#createDoor):
# east 0, south 90, west 180, north 270, and a closed door's hinge flips the
# open model's turn by a quarter; the exact turns don't matter here, only
# that every one of the 32 variants is a quarter turn of a template.
_Y = {"east": 0, "south": 90, "west": 180, "north": 270}


def _slab(side_x0, side_x1):
    face = {"texture": "#side"}
    return [{"from": [side_x0, 0, 0], "to": [side_x1, 16, 16],
             "faces": {d: dict(face) for d in ("north", "east", "south", "west", "up", "down")}}]


def _templates(tmp_path: Path) -> Path:
    """Hand-written door templates (not Mojang's): a 3-pixel slab, left or
    right, its texture #bottom or #top."""
    out = {}
    for part, tex in (("bottom", "#bottom"), ("top", "#top")):
        for hinge in ("left", "right"):
            for opened in (False, True):
                x0, x1 = (0, 3) if (hinge == "left") != opened else (13, 16)
                elements = _slab(x0, x1)
                for e in elements:
                    for f in e["faces"].values():
                        f["texture"] = tex
                out[f"minecraft:block/door_{part}_{hinge}{'_open' if opened else ''}"] = {
                    "parent": "minecraft:block/block", "textures": {"particle": tex}, "elements": elements}
    out["minecraft:block/block"] = {}
    path = tmp_path / "door_templates.json"
    path.write_text(json.dumps({"label": "hand-written test door shapes", "set": "models-vanilla-1.20.1",
                                "models": out}))
    return path


@pytest.fixture
def templates(tmp_path, monkeypatch):
    path = _templates(tmp_path)
    monkeypatch.setenv("PORTKIT_MODEL_REFERENCE", str(path))
    return path


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(body, bytes):
        path.write_bytes(body)
    else:
        path.write_text(body if isinstance(body, str) else json.dumps(body))


def door_blockstate(name: str, ns: str = NS, powered: bool = True) -> dict:
    variants = {}
    for facing in CARDINALS:
        for half in ("lower", "upper"):
            for hinge in ("left", "right"):
                for opened in (False, True):
                    model = f"{ns}:block/{name}_{'bottom' if half == 'lower' else 'top'}_{hinge}" \
                            f"{'_open' if opened else ''}"
                    entry = {"model": model}
                    if _Y[facing]:
                        entry["y"] = _Y[facing]
                    for p in (("false", "true") if powered else (None,)):
                        key = f"facing={facing},half={half},hinge={hinge},open={str(opened).lower()}"
                        if p is not None:
                            key += f",powered={p}"
                        variants[key] = entry
    return {"variants": variants}


def _door(root: Path, name: str, ns: str = NS) -> None:
    _write(root, f"assets/{ns}/blockstates/{name}.json", door_blockstate(name, ns))
    for part in ("bottom", "top"):
        _write(root, f"assets/{ns}/textures/block/{name}_{part}.png", PNG.read_bytes())
        for hinge in ("left", "right"):
            for opened in ("", "_open"):
                _write(root, f"assets/{ns}/models/block/{name}_{part}_{hinge}{opened}.json",
                       {"parent": f"minecraft:block/door_{part}_{hinge}{opened}",
                        "textures": {"bottom": f"{ns}:block/{name}_bottom", "top": f"{ns}:block/{name}_top"}})


def _two_tall(root: Path, name: str, ns: str = NS) -> None:
    _write(root, f"assets/{ns}/blockstates/{name}.json", {"variants": {
        "half=lower": {"model": f"{ns}:block/{name}_bottom"},
        "half=upper": {"model": f"{ns}:block/{name}_top"},
    }})
    for part in ("bottom", "top"):
        _write(root, f"assets/{ns}/textures/block/{name}_{part}.png", PNG.read_bytes())
        _write(root, f"assets/{ns}/models/block/{name}_{part}.json",
               {"parent": "minecraft:block/cross", "textures": {"cross": f"{ns}:block/{name}_{part}"},
                "elements": [{"from": [0.8, 0, 8], "to": [15.2, 16, 8], "shade": False,
                              "faces": {"north": {"uv": [0, 0, 16, 16], "texture": "#cross"},
                                        "south": {"uv": [0, 0, 16, 16], "texture": "#cross"}}}]})


DOOR_LOOT = {"type": "minecraft:block", "pools": [{
    "rolls": 1, "bonus_rolls": 0,
    "entries": [{"type": "minecraft:item", "name": f"{NS}:oak_door",
                 "conditions": [{"condition": "minecraft:block_state_property", "block": f"{NS}:oak_door",
                                 "properties": {"half": "lower"}}]}],
    "conditions": [{"condition": "minecraft:survives_explosion"}],
}]}


def _door_mod(tmp_path: Path, *, tagged=("oak_door",), plant=True, loot_table=True) -> Path:
    root = tmp_path / "src"
    _door(root, "oak_door")
    _door(root, "iron_door")
    if plant:
        _two_tall(root, "tall_bloom")
    _write(root, "data/minecraft/tags/blocks/wooden_doors.json",
           {"replace": False, "values": [f"{NS}:{n}" for n in tagged]})
    if loot_table:
        _write(root, f"data/{NS}/loot_tables/blocks/oak_door.json", DOOR_LOOT)
    return root


def _mod(root: Path) -> SourceMod:
    return SourceMod(root=root, namespace=NS)


# -- detection ---------------------------------------------------------------

def test_door_variants_need_all_32_and_ignore_powered():
    variants, why = doors.door_variants(door_blockstate("oak_door"))
    assert why == "" and len(variants) == 32
    assert variants[("north", "lower", "left", False)] == (f"{NS}:block/oak_door_bottom_left", 270, False)
    without = door_blockstate("oak_door", powered=False)
    assert doors.door_variants(without)[0] == variants
    missing = door_blockstate("oak_door")
    del missing["variants"]["facing=east,half=upper,hinge=right,open=true,powered=false"]
    assert doors.door_variants(missing) == (None, "")
    extra = {"variants": {k + ",waterlogged=false": v for k, v in door_blockstate("oak_door")["variants"].items()}}
    assert doors.door_variants(extra) == (None, "")


def test_door_variant_that_cannot_be_read_says_why():
    state = door_blockstate("oak_door")
    state["variants"]["facing=north,half=lower,hinge=left,open=false,powered=false"] = [
        {"model": "a"}, {"model": "b"}]
    variants, why = doors.door_variants(state)
    assert variants is None and "picks randomly" in why


def test_two_tall_variants_are_half_only():
    halves, why = doors.two_tall_variants({"variants": {"half=lower": {"model": "a"}, "half=upper": {"model": "b"}}})
    assert halves == {"lower": "a", "upper": "b"} and why == ""
    assert doors.two_tall_variants({"variants": {"half=lower": {"model": "a"}}}) == (None, "")
    turned, why = doors.two_tall_variants({"variants": {"half=lower": {"model": "a", "y": 90},
                                                        "half=upper": {"model": "b"}}})
    assert turned is None and "turns by y=90" in why


class _Method:
    def __init__(self, name, code=True):
        self.name, self.code = name, (b"" if code else None)


class _Class:
    def __init__(self, methods):
        self.methods = [_Method(m) for m in methods]


class _Machine:
    """Stand-in for blockcode.Machine: a class chain ending at a vanilla class."""

    def __init__(self, chains, classes):
        self.chains, self.classes = chains, classes

    def chain(self, name):
        return self.chains[name]

    def vanilla_base(self, name):
        return self.chains[name][-1]


class _Obj:
    def __init__(self, cls, ctor_const=None):
        self.cls = cls
        self.fields = {}
        if ctor_const is not None:
            self.fields["__vanilla_ctor"] = (
                "net/minecraft/world/level/block/DoorBlock", "()V",
                (blockcode.Const(block_set_types.CLASS, ctor_const), object()))


DOOR = "net/minecraft/world/level/block/DoorBlock"


def _read(monkeypatch, objs, chains, classes, kind="door"):
    machine = _Machine(chains, classes)
    monkeypatch.setattr(blockcode, "_registered", lambda c, names: (machine, objs))
    return doors.read_code(["stand-in"], list(objs), kind)


def test_read_vanilla_door_takes_its_block_set_type(monkeypatch):
    got = _read(monkeypatch,
                {"iron_door": ([_Obj(DOOR, "IRON")], ""), "oak_door": ([_Obj(DOOR, "OAK")], ""),
                 "odd_door": ([_Obj(DOOR, "SOMETHING_NEW")], "")},
                {DOOR: [DOOR]}, {})
    assert got["iron_door"].verdict == "vanilla" and got["iron_door"].door == (False, "IRON")
    assert got["iron_door"].door_from == "BlockSetType.IRON"
    assert got["oak_door"].door == (True, "WOODEN")
    # A constant this doesn't know: vanilla code, the DEFAULT door's behaviour.
    assert got["odd_door"].verdict == "vanilla" and got["odd_door"].door is None


def test_door_subclass_overriding_behaviour_is_refused(monkeypatch):
    own = "com/example/LockedDoor"
    plain = "com/example/PlainDoor"
    got = _read(monkeypatch,
                {"locked": ([_Obj(own, "IRON")], ""), "plain": ([_Obj(plain, "OAK")], "")},
                {own: [own, DOOR], plain: [plain, DOOR]},
                {own: _Class(["neighborChanged", "<init>"]), plain: _Class(["<init>", "getName"])})
    assert got["locked"].verdict == "refused" and "LockedDoor#neighborChanged" in got["locked"].why
    assert got["plain"].verdict == "vanilla"


def test_other_vanilla_class_and_unfollowed_registration(monkeypatch):
    trap = "net/minecraft/world/level/block/TrapDoorBlock"
    got = _read(monkeypatch, {"odd": ([_Obj(trap)], ""), "lost": ([], "registered through a library")},
                {trap: [trap]}, {})
    assert got["odd"].verdict == "refused" and "not DoorBlock" in got["odd"].why
    assert got["lost"].verdict == "unread" and got["lost"].why == "registered through a library"


def test_no_classes_is_unread():
    got = doors.read_code(None, ["oak_door"], "door")
    assert got["oak_door"].verdict == "unread" and "no class files" in got["oak_door"].why


def test_wooden_doors_tag_both_layouts(tmp_path):
    root = tmp_path / "src"
    _write(root, "data/minecraft/tags/blocks/wooden_doors.json", {"values": [f"{NS}:a", {"id": f"{NS}:b"}]})
    _write(root, "data/minecraft/tags/block/wooden_doors.json", {"values": [f"{NS}:c"]})
    assert doors.wooden_doors(_mod(root)) == {f"{NS}:a", f"{NS}:b", f"{NS}:c"}


# -- writing -----------------------------------------------------------------

def test_tagged_door_converts_untagged_is_residue(tmp_path, templates):
    root = _door_mod(tmp_path)
    result = blocks.convert(_mod(root))
    door = result.files["blocks/oak_door.json"]
    assert door["format_version"] == doors.MULTI_FORMAT == "1.26.40"
    block = door["minecraft:block"]
    traits = block["description"]["traits"]
    assert traits["minecraft:multi_block"] == {"enabled_states": ["minecraft:multi_block_part"],
                                               "direction": "up", "parts": 2}
    assert traits["minecraft:placement_direction"] == {"enabled_states": ["minecraft:cardinal_direction"]}
    assert set(traits) == {"minecraft:multi_block", "minecraft:placement_direction"}
    assert block["components"]["minecraft:movable"] == {"movement_type": "popped"}
    assert block["components"]["minecraft:redstone_consumer"] == {"min_power": 0}
    assert f"{NS}:portkit_door" in block["components"]
    assert "blocks/iron_door.json" not in result.files
    (residue,) = [u for u in result.unhandled if "iron_door" in u.source]
    assert "wooden_doors tag doesn't list" in residue.reason and "#296" in residue.reason
    note = next(n for n in result.notes if n.startswith("oak_door:"))
    assert "DEFAULT" in note and "opens by hand" in note and "wooden door sounds" in note


def test_door_permutations_cover_every_state(tmp_path, templates):
    result = blocks.convert(_mod(_door_mod(tmp_path)))
    block = result.files["blocks/oak_door.json"]["minecraft:block"]
    perms = block["permutations"]
    assert len(perms) == 32 and len({p["condition"] for p in perms}) == 32
    for p in perms:
        # No permutation sets a component Bedrock refuses there.
        assert set(p["components"]) == {"minecraft:geometry", "minecraft:collision_box", "minecraft:selection_box"}
    one = next(p for p in perms if "== 1" in p["condition"] and "'north'" in p["condition"]
               and "'right'" in p["condition"] and "!q.block_state" not in p["condition"])
    assert one["components"]["minecraft:geometry"].endswith(".north_upper_right_open")
    # One geometry per state combination, every one a single 'root' bone.
    geo = result.files["models/blocks/oak_door.geo.json"]["minecraft:geometry"]
    assert len(geo) == 32 and all([b["name"] for b in g["bones"]] == ["root"] for g in geo)
    states = block["description"]["states"]
    assert states == {f"{NS}:hinge": ["left", "right"], f"{NS}:open": [False, True], f"{NS}:powered": [False, True]}


def test_door_table_runtime_and_entry(tmp_path, templates):
    result = convert_all(_mod(_door_mod(tmp_path)))
    table = result.files[doors.door_table_path(NS)]
    assert '"examplemod:oak_door"' in table and '"open.wooden_door"' in table
    assert result.files[doors.DOOR_RUNTIME].startswith("// portkit runtime: doors")
    assert doors.DOOR_CORE in result.files
    entry = result.files["scripts/portkit/main.js"]
    assert "registerDoors(doorTable);" in entry


def test_two_tall_block(tmp_path, templates):
    result = blocks.convert(_mod(_door_mod(tmp_path)))
    block = result.files["blocks/tall_bloom.json"]["minecraft:block"]
    assert block["description"]["traits"] == {"minecraft:multi_block": {
        "enabled_states": ["minecraft:multi_block_part"], "direction": "up", "parts": 2}}
    assert block["components"]["minecraft:collision_box"] is False
    assert block["components"]["minecraft:geometry"].endswith("tall_bloom_lower")
    (upper,) = block["permutations"]
    assert upper["condition"] == "q.block_state('minecraft:multi_block_part') == 1"
    assert upper["components"]["minecraft:geometry"].endswith("tall_bloom_upper")
    assert "models/blocks/tall_bloom_lower.geo.json" in result.files
    note = next(n for n in result.notes if n.startswith("tall_bloom:"))
    assert "two-tall block" in note and "DEFAULT" in note
    assert result.paired_halves == {f"{NS}:oak_door": "half", f"{NS}:tall_bloom": "half"}


def test_no_templates_is_residue(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTKIT_MODEL_REFERENCE", str(tmp_path / "missing.json"))
    result = blocks.convert(_mod(_door_mod(tmp_path, plant=False)))
    assert "blocks/oak_door.json" not in result.files
    assert any("oak_door" in u.source for u in result.unhandled)
    assert doors.door_table_path(NS) not in result.files


# -- loot --------------------------------------------------------------------

def test_fold_paired_half_drops_only_the_lower_test():
    folded = loot.fold_paired_half(DOOR_LOOT, f"{NS}:oak_door", "half")
    (pool,) = folded["pools"]
    assert pool["entries"][0]["conditions"] == []
    assert pool["conditions"] == [{"condition": "minecraft:survives_explosion"}]
    upper = json.loads(json.dumps(DOOR_LOOT).replace('"lower"', '"upper"'))
    assert loot.fold_paired_half(upper, f"{NS}:oak_door", "half") == upper
    other = json.loads(json.dumps(DOOR_LOOT).replace(f'"block": "{NS}:oak_door"', '"block": "x:y"'))
    assert loot.fold_paired_half(other, f"{NS}:oak_door", "half") == other
    assert DOOR_LOOT["pools"][0]["entries"][0]["conditions"]  # the input is untouched


def test_door_loot_drops_the_door_once(tmp_path, templates):
    # Unfolded, the half=lower test is a block-state condition Bedrock's
    # table can't hold; folded it is one door per broken part.
    assert loot.convert_table(DOOR_LOOT, f"{NS}:oak_door", {}, [])[0] is None
    (case,) = loot.convert_table(loot.fold_paired_half(DOOR_LOOT, f"{NS}:oak_door", "half"),
                                 f"{NS}:oak_door", {}, [])[0]
    (pool,) = case[1]["pools"]
    assert pool["rolls"] == 1 and [e["name"] for e in pool["entries"]] == [f"{NS}:oak_door"]
    result = convert_all(_mod(_door_mod(tmp_path)))
    assert not [u for u in result.unhandled if "loot_tables/blocks/oak_door" in u.source]
    # One of itself is Bedrock's default for a block: no minecraft:loot, so
    # the broken part (Bedrock drops only that part's loot) drops one door.
    assert "minecraft:loot" not in result.files["blocks/oak_door.json"]["minecraft:block"]["components"]


# -- pack versioning ---------------------------------------------------------

def test_script_version_follows_the_door_runtime(tmp_path, templates):
    result = convert_all(_mod(_door_mod(tmp_path)))
    assert pack.script_version(result.files) == (2, 5, 0)
    assert pack.engine_floor(result.files) >= (1, 26, 40)
    assert pack.script_version({"scripts/portkit/main.js": "// nothing\n"}) == (2, 0, 0)
    assert pack.script_version({"other/x.js": "// portkit-requires: @minecraft/server 9.0.0\n"}) == (2, 0, 0)


def test_manifest_declares_the_script_module():
    data = pack.manifest(NS, "behavior", None, [], (1, 26, 40), "scripts/portkit/main.js", script_module=(2, 5, 0))
    (dep,) = [d for d in data["dependencies"] if d.get("module_name") == "@minecraft/server"]
    assert dep["version"] == "2.5.0"
    plain = pack.manifest(NS, "behavior", None, [], (1, 21, 90), "scripts/portkit/main.js")
    (dep,) = [d for d in plain["dependencies"] if d.get("module_name") == "@minecraft/server"]
    assert dep["version"] == pack.SCRIPT_DEPENDENCY["version"]


# -- the runtime under node -----------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_runtime_with_the_generated_table(tmp_path, templates):
    result = convert_all(_mod(_door_mod(tmp_path)))
    table = tmp_path / "doors.mjs"
    table.write_text(result.files[doors.door_table_path(NS)])
    run = subprocess.run(["node", "--import", "./tests/js/register.mjs", "--test", "tests/js/door_core.test.mjs"],
                         cwd=ROOT, capture_output=True, text=True, timeout=120,
                         env={**os.environ, "PORTKIT_DOOR_TABLE": str(table)})
    assert run.returncode == 0, run.stdout + run.stderr
