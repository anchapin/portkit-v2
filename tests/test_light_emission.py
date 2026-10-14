"""Block light emission read from the jar's bytecode (portkit.blockcode
read_light): Properties.lightLevel's function, run on abstract states.

The class files under tests/data/blockcode/classes are javac 21 output of the
example mod in tests/data/blockcode/src (LightBlocks.java, NightLampBlock.java,
WorldLitBlock.java; rebuild with build.sh): real compiler patterns, no
Minecraft code.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from portkit import blockcode
from portkit.bytecode import ClassIndex
from portkit.converters import blocks
from portkit.model import SourceMod

CLASSES = Path(__file__).parent / "data" / "blockcode" / "classes"
CARDINALS = ("north", "east", "south", "west")
NAMES = ["glow", "night_lamp", "toggle", "copy", "copy_set", "world_lit", "too_bright", "plain",
         "renamed", "discarded", "door", "lamp", "ghost", "shared_lit", "shared_plain"]


@pytest.fixture(scope="module")
def light():
    return blockcode.read_light(ClassIndex.from_source(CLASSES), NAMES, {"toggle": {"lit"}})


# --- reading ------------------------------------------------------------------

def test_constant_lambda(light):
    glow = light["glow"]
    assert (glow.value, glow.kind) == (12, "constant")
    assert glow.source == "com.example.deco.LightBlocks#lambda$static$0"


def test_code_only_states_read_at_the_placed_state(light):
    # lit ? brightness : 0, and getStateForPlacement sets lit=true, brightness=9.
    lamp = light["night_lamp"]
    assert (lamp.value, lamp.kind) == (9, "placed")
    assert lamp.states == ("brightness", "lit")
    assert lamp.source == "com.example.deco.NightLampBlock#lambda$new$0"


def test_light_on_a_drawn_state_is_not_read(light):
    toggle = light["toggle"]
    assert toggle.value is None
    assert "depends on lit, a state the converted block carries" in toggle.why


def test_drawn_states_decide_whether_the_placed_state_counts():
    # Without the blockstate drawing lit, the same block is read at its placed
    # state; vanilla Block's placement keeps the default state, whose lit
    # isn't known, so the two paths disagree and nothing is read.
    r = blockcode.read_light(ClassIndex.from_source(CLASSES), ["toggle"])["toggle"]
    assert r.value is None and "differs between paths (0, 15)" in r.why


def test_copied_vanilla_properties_are_unread_without_a_table(light):
    copy = light["copy"]
    assert copy.value is None and copy.copied == "Blocks.GLOWSTONE"
    assert "no cited table of vanilla light levels" in copy.why
    # A lightLevel after the copy is the block's own and is read.
    assert (light["copy_set"].value, light["copy_set"].kind) == (3, "constant")


def test_world_dependent_override_is_unread(light):
    assert light["world_lit"].value is None
    assert "WorldLitBlock#getLightEmission overrides the light" in light["world_lit"].why


def test_out_of_range_is_unread(light):
    assert light["too_bright"].value is None
    assert "Java gives 20, outside Bedrock's 0-15" in light["too_bright"].why


def test_never_set_is_dark(light):
    for name in ("plain", "lamp"):
        assert (light[name].value, light[name].kind) == (0, "dark")


def test_renamed_setting_is_unread_not_dark(light):
    # Properties.m_60953_ (a Forge SRG name) might be lightLevel: not "dark".
    assert light["renamed"].value is None and "renamed setting" in light["renamed"].why


def test_properties_change_in_place(light):
    # p.lightLevel(...) with its return value dropped still sets p's light.
    assert (light["discarded"].value, light["discarded"].kind) == (7, "constant")


def test_shared_properties_changed_by_another_registration_are_unread(light):
    # shared_lit calls SHARED.lightLevel(...) inside its supplier: in Java that
    # lights every block built from SHARED after it, so shared_plain's light
    # depends on registration order. Neither is read.
    for name in ("shared_lit", "shared_plain"):
        assert light[name].value is None and "depends on registration order" in light[name].why


def test_shared_change_is_seen_without_asking_for_the_changer():
    # Every registration is built, so shared_plain alone is still unread.
    r = blockcode.read_light(ClassIndex.from_source(CLASSES), ["shared_plain"])["shared_plain"]
    assert r.value is None and "depends on registration order" in r.why


def test_vanilla_block_class_with_properties_second(light):
    # new DoorBlock(BlockSetType.OAK, Properties.of().lightLevel(s -> 5))
    assert light["door"].value == 5


def test_unregistered_and_classless_blocks_are_unread(light):
    assert light["ghost"].value is None and "no registration" in light["ghost"].why
    r = blockcode.read_light(ClassIndex({}), ["glow"])["glow"]
    assert r.value is None and r.why == "the mod ships no class files"


def test_facing_readings_are_unchanged_by_the_light_reader():
    # read_blocks shares the registration code; noCollission still reads.
    readings = blockcode.read_blocks(ClassIndex.from_source(CLASSES), ["lamp", "night_lamp"])
    assert readings["lamp"].collision is False
    assert readings["night_lamp"].placement == 180
    assert readings["night_lamp"].states == ("brightness", "facing", "lit")


# --- converting ---------------------------------------------------------------

def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body))


def _solid_png() -> bytes:
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    raw = b"".join(b"\x00" + b"\x80\x60\x40\xff" * 16 for _ in range(16))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _mod(tmp_path: Path, classes: bool = True) -> SourceMod:
    root = tmp_path / "mod"
    ns = "examplemod"
    (root / f"assets/{ns}/textures/block").mkdir(parents=True)
    (root / f"assets/{ns}/textures/block/wood.png").write_bytes(_solid_png())
    cube = {"parent": "minecraft:block/cube_all", "textures": {"all": f"{ns}:block/wood"}}
    shaped = {"textures": {"all": f"{ns}:block/wood", "particle": f"{ns}:block/wood"}, "elements": [
        {"from": [4, 0, 4], "to": [12, 8, 12],
         "faces": {f: {"texture": "#all"} for f in ("north", "south", "east", "west", "up", "down")}}]}
    for name in ("glow", "copy", "plain", "too_bright"):
        _write(root, f"assets/{ns}/models/block/{name}.json", cube)
        _write(root, f"assets/{ns}/blockstates/{name}.json", {"variants": {"": {"model": f"{ns}:block/{name}"}}})
    _write(root, f"assets/{ns}/models/block/night_lamp.json", shaped)
    _write(root, f"assets/{ns}/blockstates/night_lamp.json", {"variants": {
        f"facing={d}": {"model": f"{ns}:block/night_lamp", **({"y": t} if t else {})}
        for d, t in zip(CARDINALS, (0, 90, 180, 270))}})
    return SourceMod(root=root, namespace=ns, classes=ClassIndex.from_source(CLASSES) if classes else None)


def _components(result, name):
    return result.files[f"blocks/{name}.json"]["minecraft:block"]["components"]


def test_read_light_lands_in_the_definition(tmp_path):
    result = blocks.convert(_mod(tmp_path))
    assert _components(result, "glow")["minecraft:light_emission"] == 12
    # The facing block's light sits with its other components, for every
    # permutation (none of them overrides it).
    lamp = result.files["blocks/night_lamp.json"]["minecraft:block"]
    assert lamp["components"]["minecraft:light_emission"] == 9
    assert not any("minecraft:light_emission" in p["components"] for p in lamp.get("permutations", []))
    for name in ("copy", "plain", "too_bright"):
        assert "minecraft:light_emission" not in _components(result, name)


def test_notes_say_what_was_read_and_what_was_not(tmp_path):
    notes = "\n".join(blocks.convert(_mod(tmp_path)).notes)
    assert "com.example.deco.LightBlocks#lambda$static$0 = 12: glow" in notes
    assert "Light emission read from bytecode at the placed state" in notes
    assert "com.example.deco.NightLampBlock#lambda$new$0 = 9 (reads brightness, lit): night_lamp" in notes
    assert "No light, read from bytecode: 1 block(s)" in notes
    assert "Light emission NOT converted, the block emits none: its Properties copy" in notes
    assert "Blocks.GLOWSTONE: copy" in notes
    assert "outside Bedrock's 0-15: too_bright" in notes


def test_without_classes_nothing_lights(tmp_path):
    result = blocks.convert(_mod(tmp_path, classes=False))
    assert not any("minecraft:light_emission" in json.dumps(v) for k, v in result.files.items()
                   if k.startswith("blocks/"))
    assert "the mod ships no class files" in "\n".join(n for n in result.notes if "Light" in n)


def test_light_another_path_set_is_kept(tmp_path):
    result = blocks.ConversionResult()
    result.files["blocks/glow.json"] = {"minecraft:block": {"components": {},
                                                           "permutations": [{"condition": "x", "components": {
                                                               "minecraft:light_emission": 13}}]}}
    mod = _mod(tmp_path)
    blocks._add_light(mod, result, mod.assets / "blockstates")
    assert "minecraft:light_emission" not in result.files["blocks/glow.json"]["minecraft:block"]["components"]
    assert result.notes == []


def test_drawn_states():
    assert blocks._drawn_states({"variants": {"facing=north,lit=true": {}, "": {}}}) == {"facing", "lit"}
    assert blocks._drawn_states({"multipart": [{"when": {"OR": [{"north": "true"}, {"up": "true"}]}},
                                               {"apply": {}}]}) == {"north", "up"}
