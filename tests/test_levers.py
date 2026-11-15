"""Levers (#237): vanilla LeverBlock read from code converts with the fixed
persistent-toggle runtime (converters/levers.py and portkit/runtime/toggle.js).

There is no compiled LeverBlock fixture in this environment, so the
constructor readings and the conversion use hand-built ``blockcode`` values
and a ``DirStateReading``, as tests/test_set_types.py does for set types.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from portkit import blockcode
from portkit.converters import blocks, convert_all, levers
from portkit.data import block_set_types as BST
from portkit.model import ConversionResult, SourceMod

from test_facing_boolean import _png

NS = "examplemod"
CTOR = next(iter(BST.LEVER_BLOCK_CTORS))


def _reading(ctor, overrides=(), why="", ctors=None):
    return SimpleNamespace(cls="com.example.Lever", lever_ctor=ctor, lever_overrides=list(overrides),
                           lever_why=why, lever_ctors=ctors if ctors is not None else [ctor])


def _dir_reading(ctor=CTOR, overrides=()):
    reading = blockcode.DirStateReading("lever", kind="attach", bools=("powered",))
    reading.cls = "com.example.Lever"
    reading.vanilla_parent = "net.minecraft.world.level.block.LeverBlock"
    reading.lever_ctor = (BST.LEVER_CLASS, ctor, (object(),))
    reading.lever_ctors = [reading.lever_ctor]
    reading.lever_overrides = list(overrides)
    reading.rule = blockcode.default_rule("attach")
    reading.rule_from = "net.minecraft.world.level.block.FaceAttachedHorizontalDirectionalBlock#getStateForPlacement"
    reading.support_assumed = True
    reading.defaults = {"powered": (False, "placed", reading.rule_from)}
    reading.states = ("powered",)
    reading.behaviour = ("useWithoutItem",)
    reading.toggle = "powered"
    reading.toggle_from = "net.minecraft.world.level.block.LeverBlock#useWithoutItem"
    return reading


# -- reading -------------------------------------------------------------------

def test_vanilla_constructor_is_read():
    got, why = levers.read(_reading((BST.LEVER_CLASS, CTOR, (object(),))))
    assert why == ""
    assert got["from"] == f"com.example.Lever new LeverBlock{CTOR}"


def test_what_stays_residue_says_why():
    assert "overrides vanilla LeverBlock behaviour (Lever#useWithoutItem)" in levers.read(
        _reading((BST.LEVER_CLASS, CTOR, (object(),)), ["Lever#useWithoutItem"]))[1]
    assert "constructor call isn't read" in levers.read(_reading(None))[1]
    assert "a constructor this doesn't read" in levers.read(
        _reading((BST.LEVER_CLASS, "(I)V", (1,))))[1]
    assert "registered twice" in levers.read(
        _reading(None, why="registered twice with different constructor arguments"))[1]


def test_every_way_the_registration_takes_must_be_read():
    way = lambda desc: (BST.LEVER_CLASS, desc, (object(),))
    got, why = levers.read(_reading(way(CTOR), ctors=[way(CTOR), way("(I)V")]))
    assert got is None
    assert "a constructor this doesn't read" in why
    got, why = levers.read(_reading(way(CTOR), ctors=[way(CTOR), way(CTOR)]))
    assert why == "" and got is not None


def test_attached_face_is_the_block_it_hangs_on():
    assert levers.attached_face(("floor", "east")) == "down"
    assert levers.attached_face(("ceiling", "north")) == "up"
    # facing north on a wall: the block behind it is south.
    assert levers.attached_face(("wall", "north")) == "south"
    assert levers.attached_face(("wall", "west")) == "east"


def test_reader_names_the_vanilla_lever_behaviour_it_refuses_to_replace():
    assert "useWithoutItem" in blockcode.LEVER_BEHAVIOUR
    assert "getDirectSignal" in blockcode.LEVER_BEHAVIOUR
    assert "updateShape" in blockcode.LEVER_BEHAVIOUR


# -- conversion ------------------------------------------------------------------

def _mod(tmp_path: Path) -> SourceMod:
    root = tmp_path / "mod"
    (root / f"assets/{NS}/models/block").mkdir(parents=True)
    (root / f"assets/{NS}/textures/block").mkdir(parents=True)
    (root / f"assets/{NS}/blockstates").mkdir(parents=True)
    (root / f"assets/{NS}/textures/block/lever.png").write_bytes(_png())
    model = {
        "textures": {"all": f"{NS}:block/lever", "particle": f"{NS}:block/lever"},
        "elements": [{"from": [2, 0, 2], "to": [14, 4, 14],
                      "faces": {f: {"texture": "#all"} for f in ("north", "south", "east", "west", "up", "down")}}],
    }
    (root / f"assets/{NS}/models/block/lever.json").write_text(json.dumps(model))
    variants = {}
    for face, facing in blockcode.directional_keys("attach"):
        for powered in (False, True):
            variants[f"face={face},facing={facing},powered={str(powered).lower()}"] = {
                "model": f"{NS}:block/lever"}
    (root / f"assets/{NS}/blockstates/lever.json").write_text(json.dumps({"variants": variants}))
    return SourceMod(root=root, namespace=NS)


def _cells():
    out = {}
    for key in blockcode.directional_keys("attach"):
        for combo in blockcode.combinations(("powered",)):
            out[(key, combo)] = (f"{NS}:block/lever", 0, 0, False)
    return out


def _convert(mod, result, reading):
    return blocks._convert_directional(mod, result, "blockstates/lever.json", "lever", "attach",
                                      _cells(), reading, ("powered",))


def test_lever_block_permutions_and_redstone(tmp_path):
    mod = _mod(tmp_path)
    result = ConversionResult()
    record = _convert(mod, result, _dir_reading())
    assert record is not None and not result.unhandled

    definition = result.files["blocks/lever.json"]
    block = definition["minecraft:block"]
    assert definition["format_version"] == levers.LEVER_FORMAT
    assert block["description"]["states"] == {f"{NS}:powered": [False, True]}
    assert block["description"]["traits"] == {
        "minecraft:placement_position": {"enabled_states": ["minecraft:block_face"]},
        "minecraft:placement_direction": {"enabled_states": ["minecraft:cardinal_direction"]},
    }
    assert block["components"]["minecraft:redstone_producer"] == {"power": 0}
    assert f"{NS}:portkit_toggle" in block["components"]

    power = [p for p in block["permutations"] if "minecraft:redstone_producer" in p["components"]]
    faces = {p["components"]["minecraft:redstone_producer"]["strongly_powered_face"] for p in power}
    assert faces == {"up", "down", "north", "south", "east", "west"}
    assert all(p["components"]["minecraft:redstone_producer"]["power"] == 15 for p in power)
    assert all(f"q.block_state('{NS}:powered')" in p["condition"] for p in power)

    # The persistent toggle is the already-fixed generic runtime, not a
    # button-style press/release runtime.
    blocks._toggle_table(mod, result, [record])
    assert blocks.toggle_table_path(NS) in result.files
    assert result.files[blocks.TOGGLE_RUNTIME].startswith("// portkit runtime: a boolean block state")
    assert f'"{NS}:lever": "{NS}:powered"' in result.files[blocks.toggle_table_path(NS)]
    assert not any("button" in name for name in result.files)


def test_full_pipeline_wires_the_existing_toggle_runtime(tmp_path, monkeypatch):
    mod = _mod(tmp_path)

    def read(classes, specs, run=None):
        assert specs == {"lever": ("attach", ("powered",))}
        return {"lever": _dir_reading()}

    monkeypatch.setattr(blockcode, "read_directional_states", read)
    result = convert_all(mod)

    assert not result.unhandled
    assert "blocks/lever.json" in result.files
    assert blocks.toggle_table_path(NS) in result.files
    assert blocks.TOGGLE_RUNTIME in result.files
    main = result.files["scripts/portkit/main.js"]
    assert 'import { registerToggles } from "./toggle.js";' in main
    assert f'import toggleTable from "./data/{NS}_toggle.js";' in main
    assert "registerToggles(toggleTable);" in main
    notes = "\n".join(result.notes)
    assert "lever: lever toggled by a use" in notes
    assert "keeps that state until the next use" in notes


def test_incomplete_lever_reading_stays_residue(tmp_path):
    mod = _mod(tmp_path)
    result = ConversionResult()
    reading = _dir_reading()
    reading.lever_ctor = None
    reading.lever_ctors = [None]
    assert _convert(mod, result, reading) is None
    assert result.unhandled
    assert "LeverBlock constructor call isn't read" in result.unhandled[0].reason

    result = ConversionResult()
    reading = _dir_reading(overrides=["com.example.Lever#useWithoutItem"])
    assert _convert(mod, result, reading) is None
    assert result.unhandled
    assert "overrides vanilla LeverBlock behaviour" in result.unhandled[0].reason
