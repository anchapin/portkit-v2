"""Blocks whose blockstate draws waterlogged: the state draws nothing in Java
(the water is the state's fluid), so it is dropped and the block rides on the
converter its other states fit; Bedrock holds the water through
minecraft:liquid_detection when getFluidState says the block holds water
(read from bytecode), else when the code isn't read (a labelled DEFAULT).

The class files under tests/data/blockcode/classes are javac 21 output of the
example mod in tests/data/blockcode/src (WaterBlocks.java, PondBlock,
PondLampBlock, DryVaseBlock, FountainBlock; rebuild with build.sh): real
compiler patterns, no Minecraft code.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from portkit import blockcode, pack
from portkit.bytecode import ClassIndex
from portkit.converters import blocks
from portkit.model import SourceMod

from test_facing_boolean import CARDINALS, NS, TURN, _model, _png

CLASSES = Path(__file__).parent / "data" / "blockcode" / "classes"
RULE = {"liquid_type": "water", "can_contain_liquid": True, "on_liquid_touches": "blocking"}


def _facing_water(model: str, extra: dict | None = None, differ: str | None = None) -> dict:
    """facing (+ ``extra`` booleans: name -> (false model, true model)) +
    waterlogged variants, the same model at waterlogged true and false unless
    ``differ`` names the model drawn at waterlogged=true."""
    from itertools import product

    extra = extra or {}
    out = {}
    for d in CARDINALS:
        for combo in product((0, 1), repeat=len(extra)):
            m = model
            for (prop, models), v in zip(extra.items(), combo):
                if v:
                    m = models[1]
            for w in ("false", "true"):
                pairs = [f"facing={d}"] + [f"{p}={'true' if v else 'false'}" for p, v in zip(extra, combo)]
                pairs.append(f"waterlogged={w}")
                out[",".join(pairs)] = {"model": differ if (differ and w == "true") else m,
                                       **({"y": TURN[d]} if TURN[d] else {})}
    return {"variants": out}


# --- dropping the state ---------------------------------------------------------

def test_drops_waterlogged_when_every_model_agrees():
    reduced, why = blocks._drop_waterlogged(_facing_water("m"))
    assert why == ""
    assert set(reduced["variants"]) == {f"facing={d}" for d in CARDINALS}
    assert reduced["variants"]["facing=east"] == {"model": "m", "y": 90}
    # Only waterlogged: one model for the block.
    only = {"variants": {"waterlogged=false": {"model": "m"}, "waterlogged=true": {"model": "m"}}}
    assert blocks._drop_waterlogged(only)[0] == {"variants": {"": {"model": "m"}}}


def test_keeps_the_other_states_in_order():
    bs = {"variants": {"lit=false,waterlogged=false,facing=north": {"model": "a"},
                       "lit=false,waterlogged=true,facing=north": {"model": "a"}}}
    assert list(blocks._drop_waterlogged(bs)[0]["variants"]) == ["lit=false,facing=north"]


def test_does_not_drop_what_it_cannot():
    assert blocks._drop_waterlogged(_facing_water("m", differ="wet"))[1] == (
        "waterlogged: facing=north draws a different model at waterlogged=true and false")
    half = {"variants": {"waterlogged=false": {"model": "m"}}}
    assert blocks._drop_waterlogged(half)[1] == "waterlogged: the block has no variant at waterlogged=true"
    mixed = {"variants": {"waterlogged=false": {"model": "m"}, "": {"model": "m"}}}
    assert blocks._drop_waterlogged(mixed)[1] == "waterlogged: some variants don't name it"
    multipart = {"multipart": [{"when": {"waterlogged": "false"}, "apply": {"model": "m"}}]}
    assert blocks._drop_waterlogged(multipart)[1] == "waterlogged: a multipart part depends on it, which isn't read"
    # Not drawn at all: nothing to do, no reason.
    assert blocks._drop_waterlogged({"variants": {"facing=north": {"model": "m"}}}) == (None, "")
    assert blocks._drop_waterlogged({"multipart": [{"apply": {"model": "m"}}]}) == (None, "")


# --- reading getFluidState -------------------------------------------------------

@pytest.fixture(scope="module")
def water():
    return blockcode.read_water(ClassIndex.from_source(CLASSES),
                                ["pond", "pond_lamp", "dry_vase", "fountain", "lamp", "nowhere"])


def test_reads_water_when_waterlogged(water):
    pond = water["pond"]
    assert (pond.holds, pond.source, pond.bucket) == (True, "com.example.deco.PondBlock#getFluidState", True)
    # Inherited from a mod superclass.
    lamp = water["pond_lamp"]
    assert (lamp.holds, lamp.source) == (True, "com.example.deco.PondBlock#getFluidState")


def test_vanilla_fluid_state_means_never_water(water):
    dry = water["dry_vase"]
    assert dry.holds is False
    assert dry.source == "net.minecraft.world.level.block.state.BlockBehaviour#getFluidState (vanilla, inherited)"
    assert dry.bucket is False


def test_unreadable_or_odd_fluid_code_is_not_a_reading(water):
    fountain = water["fountain"]
    assert fountain.holds is None
    assert fountain.why == ("com.example.deco.FountainBlock#getFluidState: gives water at waterlogged=true "
                            "and water at false, which isn't water only when waterlogged")
    assert water["nowhere"].holds is None and "no registration" in water["nowhere"].why
    assert blockcode.read_water(None, ["pond"])["pond"].why == "the mod ships no class files"


# --- converting --------------------------------------------------------------------

def _mod(tmp_path: Path, classes: bool = True) -> SourceMod:
    root = tmp_path / "mod"
    for sub in ("textures/block", "models/block", "blockstates"):
        (root / f"assets/{NS}/{sub}").mkdir(parents=True)
    for tex in ("wood", "glow"):
        (root / f"assets/{NS}/textures/block/{tex}.png").write_bytes(_png())
    for name, model in {"pond": _model(10, "wood"), "pond_on": _model(14, "glow"),
                        "wet": _model(12, "wood")}.items():
        (root / f"assets/{NS}/models/block/{name}.json").write_text(json.dumps(model))
    m = f"{NS}:block/pond"
    states = {
        "pond": _facing_water(m),
        "pond_lamp": _facing_water(m, {"lit": (m, f"{NS}:block/pond_on")}),
        "dry_vase": _facing_water(m),
        "pond_cube": {"variants": {"waterlogged=false": {"model": m}, "waterlogged=true": {"model": m}}},
        "fountain": {"variants": {"waterlogged=false": {"model": m}, "waterlogged=true": {"model": m}}},
        "soggy": _facing_water(m, differ=f"{NS}:block/wet"),
    }
    for name, bs in states.items():
        (root / f"assets/{NS}/blockstates/{name}.json").write_text(json.dumps(bs))
    return SourceMod(root=root, namespace=NS, classes=ClassIndex.from_source(CLASSES) if classes else None)


@pytest.fixture()
def converted(tmp_path):
    return blocks.convert(_mod(tmp_path))


def _file(result, name):
    return result.files[f"blocks/{name}.json"]


def test_facing_block_holds_water(converted):
    pond = _file(converted, "pond")
    block = pond["minecraft:block"]
    assert block["components"]["minecraft:liquid_detection"] == {"detection_rules": [RULE]}
    assert pond["format_version"] == "1.21.60"
    # Converted as a facing block (#212), placement read from its code.
    assert block["description"]["traits"]["minecraft:placement_direction"] == {
        "enabled_states": ["minecraft:cardinal_direction"], "y_rotation_offset": 180}
    assert "states" not in block["description"]


def test_facing_and_boolean_block_keeps_only_its_booleans(converted):
    block = _file(converted, "pond_lamp")["minecraft:block"]
    # lit is never set: defaultBlockState() is Block#<init>'s
    # stateDefinition.any(), BooleanProperty's first value (true), start first.
    assert block["description"]["states"] == {f"{NS}:lit": [True, False]}
    assert block["components"]["minecraft:liquid_detection"] == {"detection_rules": [RULE]}
    assert "waterlogged" not in json.dumps(block)


def test_plain_block_holds_water(converted):
    cube = _file(converted, "pond_cube")
    assert cube["minecraft:block"]["components"]["minecraft:liquid_detection"] == {"detection_rules": [RULE]}
    assert cube["format_version"] == "1.21.60"


def test_cosmetic_waterlogged_gets_no_water(converted):
    dry = _file(converted, "dry_vase")
    assert "minecraft:liquid_detection" not in dry["minecraft:block"]["components"]
    assert dry["format_version"] == "1.20.20"


def test_unread_code_is_the_labelled_default(converted):
    fountain = _file(converted, "fountain")["minecraft:block"]
    assert fountain["components"]["minecraft:liquid_detection"] == {"detection_rules": [RULE]}
    notes = "\n".join(converted.notes)
    assert "Holds water DEFAULT, not read from code (can_contain_liquid true" in notes
    assert "fountain" in notes.split("Holds water DEFAULT")[1]


def test_a_model_that_depends_on_it_stays_residue(converted):
    assert "blocks/soggy.json" not in converted.files
    why = [u.reason for u in converted.unhandled if u.source.endswith("soggy.json")]
    assert why == ["waterlogged: facing=north draws a different model at waterlogged=true and false"]


def test_notes_name_each_reading(converted):
    notes = "\n".join(converted.notes)
    assert "5 converted block(s) draw a waterlogged state" in notes
    assert ("Holds water when waterlogged, read from bytecode (getFluidState gives Fluids.WATER's source at "
            "waterlogged=true) - com.example.deco.PondBlock#getFluidState: pond, pond_cube, pond_lamp.") in notes
    assert "Never holds water, read from bytecode" in notes and "dry_vase" in notes
    # waterlogged is not listed among code states the blockstate doesn't draw.
    assert not any("doesn't draw" in n and "waterlogged" in n for n in converted.notes)


def test_without_classes_every_waterlogged_block_is_a_default(tmp_path):
    result = blocks.convert(_mod(tmp_path, classes=False))
    for name in ("pond", "pond_lamp", "dry_vase", "pond_cube", "fountain"):
        assert "minecraft:liquid_detection" in _file(result, name)["minecraft:block"]["components"]
    assert "(the mod ships no class files)" in "\n".join(result.notes)


def test_pack_floor_follows(converted):
    assert pack.engine_floor({"blocks/pond.json": _file(converted, "pond")}) >= (1, 21, 60)
    assert pack.engine_floor({"blocks/dry_vase.json": _file(converted, "dry_vase")}) < (1, 21, 60)


def test_toggle_format_is_not_lowered(tmp_path):
    result = blocks.ConversionResult()
    result.files["blocks/pond.json"] = {"format_version": "1.21.90", "minecraft:block": {"components": {}}}
    blocks._add_water(_mod(tmp_path), result, ["pond"])
    assert result.files["blocks/pond.json"]["format_version"] == "1.21.90"
    assert "minecraft:liquid_detection" in result.files["blocks/pond.json"]["minecraft:block"]["components"]
