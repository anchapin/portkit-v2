"""Facing set by a block entity after placement, read by an adapter (#296).

Immersive Engineering's directional blocks leave ``facing`` at its default in
``getStateForPlacement`` (``IEBaseBlock``): its block item places the block,
then ``IEEntityBlock#onIEBlockPlacedBy`` asks the block entity
(``IDirectionalBE#getFacingForPlacement``, a ``PlacementLimitation`` lambda
and a mirror) and sets the facing through ``IStateBasedDirectional#setFacing``.
The immersiveengineering adapter checks that chain's instructions, pairs each
block with the block entity type its factory reads, and has the core run the
block entity's ``getFacingForPlacement`` per clicked face
(``blockcode.read_placed_direction``); the core converts the rule as one read
from getStateForPlacement. A block entity told the clicked face after its
facing (``IAdvancedDirectionalBE#onDirectionalPlacement``) may set another
state of its block from it (IE's strip curtain: ``ceiling_attached``);
``blockcode.read_placed_states`` reads what it sets per clicked face, and the
core converts that state as the second state of a facing-with-second-state
block. A block entity placing more blocks (``IHasDummyBlocks``) is named.

The class files under tests/data/ieplace/classes are javac 21 output of
tests/data/ieplace/src (rebuild with build.sh) against
tests/data/blockcode/stubs: IE's placement classes cut down to what is read
(blusunrize/immersiveengineering/... at 12.4.2-194), no Minecraft code.
"""
from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import pytest

from portkit import blockcode
from portkit.adapters import immersiveengineering as ie
from portkit.bytecode import ClassIndex
from portkit.converters import blocks
from portkit.model import SourceMod

CLASSES = Path(__file__).parent / "data" / "ieplace" / "classes"
NS = "immersiveengineering"
BLOCK = "blusunrize.immersiveengineering.common.blocks.IEEntityBlock"
NAMES = ("connector", "board", "sneak", "hit", "curtain", "mid", "two_high")
# Facing beside another state (#296): the second state each blockstate draws.
SECOND = {"curtain": "ceiling_attached", "mid": "ceiling_attached", "two_high": "multiblockslave"}
ADVANCED_DESC = "(Lnet/minecraft/core/Direction;FFFLnet/minecraft/world/entity/LivingEntity;)V"
FACING_DESC = "(Lnet/minecraft/world/item/context/BlockPlaceContext;)Lnet/minecraft/core/Direction;"
THINGS = "blusunrize/immersiveengineering/common/blocks/Things$"
# A model's y turn per horizontal facing, as IE's datagen writes them.
Y = {"north": 0, "east": 90, "south": 180, "west": 270}
X6 = {"down": (90, 0), "up": (270, 0), "north": (0, 0), "south": (0, 180), "west": (0, 270), "east": (0, 90)}


def _png() -> bytes:
    raw = b"".join(b"\x00" + b"\x80\x80\x80\xff" * 16 for _ in range(16))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _model(tex: str) -> dict:
    return {"textures": {"all": f"{NS}:block/{tex}", "particle": f"{NS}:block/{tex}"},
            "elements": [{"from": [5, 0, 5], "to": [11, 8, 11],
                          "faces": {f: {"texture": "#all", "uv": [0, 0, 6, 8]}
                                    for f in ("north", "south", "east", "west", "up", "down")}}]}


def _blockstate(stem: str) -> dict:
    if stem in SECOND:
        # IE's strip curtain: a model per second state, turned by facing.
        return {"variants": {f"{SECOND[stem]}={b},facing={f}": {
            "model": f"{NS}:block/{stem}" + ("_top" if b == "true" else ""), **({"y": y} if y else {})}
            for b in ("false", "true") for f, y in Y.items()}}
    if stem == "board":
        return {"variants": {f"facing={f}": {"model": f"{NS}:block/{stem}", **({"y": y} if y else {})}
                             for f, y in Y.items()}}
    return {"variants": {f"facing={f}": {"model": f"{NS}:block/{stem}", **({"x": x} if x else {}),
                                         **({"y": y} if y else {})} for f, (x, y) in X6.items()}}


def _mod(tmp_path: Path, ns: str = NS) -> SourceMod:
    root = tmp_path / "mod"
    for sub in ("textures/block", "models/block", "blockstates"):
        (root / f"assets/{ns}/{sub}").mkdir(parents=True)
    for stem in NAMES:
        (root / f"assets/{ns}/textures/block/{stem}.png").write_bytes(_png())
        (root / f"assets/{ns}/models/block/{stem}.json").write_text(json.dumps(_model(stem)).replace(f"{NS}:", f"{ns}:"))
        if stem in SECOND:
            top = _model(stem)
            top["elements"][0].update({"from": [0, 13, 7], "to": [16, 16, 9]})
            (root / f"assets/{ns}/models/block/{stem}_top.json").write_text(json.dumps(top).replace(f"{NS}:", f"{ns}:"))
        (root / f"assets/{ns}/blockstates/{stem}.json").write_text(
            json.dumps(_blockstate(stem)).replace(f"{NS}:block", f"{ns}:block"))
    return SourceMod(root=root, namespace=ns, classes=ClassIndex.from_source(CLASSES))


def _sites(classes) -> dict:
    _machine, registered = blockcode._registered(classes, list(NAMES))
    return {n: registered[n][0][0]._made_in for n in NAMES}


@pytest.fixture()
def converted(tmp_path):
    return blocks.convert(_mod(tmp_path))


def test_registration_records_where_each_block_is_made():
    sites = _sites(ClassIndex.from_source(CLASSES))
    assert sites["connector"][0] == "blusunrize/immersiveengineering/common/register/IEBlocks"
    assert sites["connector"][1].startswith("lambda$static$")
    assert len(set(sites.values())) == len(NAMES)


def test_core_runs_a_block_entitys_placement_per_clicked_face():
    classes = ClassIndex.from_source(CLASSES)
    # SIDE_CLICKED, mirrored: facing = the clicked face turned round.
    rule, why = blockcode.read_placed_direction(classes, THINGS + "ConnectorBE", "getFacingForPlacement", FACING_DESC)
    assert why == "" and rule == {c: ("dir", blockcode.Dir(c).opposite().name) for c in blockcode.DIRECTIONS}
    # HORIZONTAL_PREFER_SIDE: a side face turned round, else the player's facing.
    rule, _ = blockcode.read_placed_direction(classes, THINGS + "BoardBE", "getFacingForPlacement", FACING_DESC)
    assert rule["up"] == rule["down"] == ("player", 0) and rule["east"] == ("dir", "west")
    # Mirrored only while sneaking: the paths disagree, so nothing is read.
    rule, why = blockcode.read_placed_direction(classes, THINGS + "SneakBE", "getFacingForPlacement", FACING_DESC)
    assert rule is None and "doesn't give one direction" in why


def test_the_player_answers_only_while_an_adapter_reads():
    machine = blockcode.Machine(ClassIndex.from_source(CLASSES))
    assert machine.player is False
    assert machine.call("net/minecraft/world/item/context/BlockPlaceContext", "getPlayer",
                        "()Lnet/minecraft/world/entity/player/Player;", [blockcode._Ctx("up")]) == [blockcode.UNKNOWN]


def test_adapter_reads_the_chain_from_the_jar(tmp_path):
    mod = _mod(tmp_path)
    got = ie.orientations(mod, {n: BLOCK for n in NAMES}, sites=_sites(mod.classes))
    assert got["connector"].states == ("facing",) and got["connector"].why == ""
    assert got["connector"].rule["up"] == ("", ("dir", "down"))
    assert "ConnectorBE#getFacingForPlacement" in got["connector"].source
    assert got["board"].rule["north"] == ("", ("dir", "south")) and got["board"].rule["up"] == ("", ("player", 0))
    # Told the point clicked, but onDirectionalPlacement sets nothing: the
    # facing rule stands alone.
    assert got["hit"].why == "" and got["hit"].rule["up"] == ("", ("dir", "up")) and got["hit"].placed_states is None
    assert "SneakBE#getFacingForPlacement" in got["sneak"].why
    # Asked about the states beside facing (their registered start unknown).
    got = ie.orientations(mod, {n: BLOCK for n in SECOND}, sites=_sites(mod.classes),
                          states={n: {SECOND[n]: None} for n in SECOND})
    curtain = got["curtain"]
    assert curtain.why == "" and curtain.rule["down"] == ("", ("player", 0))
    assert curtain.placed_states == {c: (("ceiling_attached", "true" if c == "down" else "false"),)
                                     for c in blockcode.DIRECTIONS}
    assert "CurtainBE#onDirectionalPlacement (it sets ceiling_attached from the clicked face)" in curtain.source
    assert got["mid"].rule is None and "follows something besides the clicked face" in got["mid"].why
    assert got["two_high"].rule is None and "IHasDummyBlocks" in got["two_high"].why
    assert "TwoHighBE#placeDummies" in got["two_high"].why
    # Asked without sites (the facing-and-spin question), or for another
    # namespace, the adapter gives nothing.
    assert ie.orientations(mod, {n: BLOCK for n in NAMES}) == {}
    assert ie.orientations(_mod(tmp_path / "o", ns="examplemod"), {n: BLOCK for n in NAMES}, sites={}) == {}
    # A block whose site is unknown names that.
    assert "isn't known" in ie.orientations(mod, {"connector": BLOCK}, sites={})["connector"].why


def test_six_way_connector_converts_on_the_clicked_face(converted):
    assert "blocks/connector.json" in converted.files
    assert not [u for u in converted.unhandled if u.source.endswith("blockstates/connector.json")]
    block = converted.files["blocks/connector.json"]["minecraft:block"]
    assert block["description"]["traits"] == {"minecraft:placement_position": {"enabled_states": ["minecraft:block_face"]}}
    text = json.dumps(block)
    # Clicking a block's top face puts the connector on it, facing down.
    assert "'minecraft:block_face') == 'up'" in text and "cardinal_direction" not in text


def test_horizontal_board_follows_the_side_clicked_or_the_player(converted):
    assert "blocks/board.json" in converted.files
    block = converted.files["blocks/board.json"]["minecraft:block"]
    traits = block["description"]["traits"]
    assert traits["minecraft:placement_position"]["enabled_states"] == ["minecraft:block_face"]
    assert traits["minecraft:placement_direction"]["enabled_states"] == ["minecraft:cardinal_direction"]
    conds = [p["condition"] for p in block["permutations"]]
    # facing south (y 180): clicked north, or clicked top/bottom facing south.
    south = next(p for p in block["permutations"] if p["components"].get("minecraft:transformation", {})
                 .get("rotation") == [0, 180, 0])
    assert "'minecraft:block_face') == 'north'" in south["condition"]
    assert "'minecraft:cardinal_direction') == 'south'" in south["condition"]
    assert len(conds) == 3


def test_unread_placements_stay_residue_with_their_reason(converted):
    assert "blocks/hit.json" in converted.files
    for stem, part in (("sneak", "doesn't give one direction"),):
        assert f"blocks/{stem}.json" not in converted.files
        why = next(u.reason for u in converted.unhandled if u.source.endswith(f"blockstates/{stem}.json"))
        assert "doesn't set facing" in why and "the mod's placement after the block is set isn't read" in why
        assert part in why


def test_core_reads_the_states_a_block_entity_sets_on_its_own_block():
    classes = ClassIndex.from_source(CLASSES)
    sets, why = blockcode.read_placed_states(classes, THINGS + "CurtainBE", "onDirectionalPlacement", ADVANCED_DESC,
                                             {"ceiling_attached": None, "facing": "north"})
    assert why == "" and sets["down"] == (("ceiling_attached", "true"),) and sets["up"] == (("ceiling_attached", "false"),)
    # With a known start, a state set to it is the start (nothing changes).
    sets, _ = blockcode.read_placed_states(classes, THINGS + "CurtainBE", "onDirectionalPlacement", ADVANCED_DESC,
                                           {"ceiling_attached": "false", "facing": "east"})
    assert sets["up"] == () and sets["down"] == (("ceiling_attached", "true"),)
    # A state it wasn't asked about isn't taken.
    sets, why = blockcode.read_placed_states(classes, THINGS + "CurtainBE", "onDirectionalPlacement", ADVANCED_DESC,
                                             {"facing": "north"})
    assert sets is None and "wasn't asked about" in why
    # A state set from the point clicked (unknown) has no one answer.
    sets, why = blockcode.read_placed_states(classes, THINGS + "MidBE", "onDirectionalPlacement", ADVANCED_DESC,
                                             {"ceiling_attached": None, "facing": "north"})
    assert sets is None and "takes 2 ways through" in why
    sets, why = blockcode.read_placed_states(classes, THINGS + "TwoHighBE", "placeDummies",
                                             "(Lnet/minecraft/world/item/context/BlockPlaceContext;"
                                             "Lnet/minecraft/world/level/block/state/BlockState;)V", {})
    assert sets is None and "takes no Direction" in why


def test_curtain_converts_with_its_second_state_from_the_clicked_face(converted):
    assert "blocks/curtain.json" in converted.files
    assert not [u for u in converted.unhandled if u.source.endswith("blockstates/curtain.json")]
    block = converted.files["blocks/curtain.json"]["minecraft:block"]
    traits = block["description"]["traits"]
    assert traits["minecraft:placement_position"]["enabled_states"] == ["minecraft:block_face"]
    assert traits["minecraft:placement_direction"]["enabled_states"] == ["minecraft:cardinal_direction"]
    # No Bedrock state of its own: ceiling_attached follows the clicked face.
    assert "states" not in block["description"]
    vis = block["components"]["minecraft:geometry"]["bone_visibility"]
    assert len(vis) == 2
    top = [b for b, c in vis.items() if c == "q.block_state('minecraft:block_face') == 'down'"]
    assert len(top) == 1
    # facing = the player's facing: south turns the model 180 on either half.
    south = [p for p in block["permutations"]
             if p["components"].get("minecraft:transformation", {}).get("rotation") == [0, 180, 0]]
    assert south and all("'minecraft:cardinal_direction') == 'south'" in p["condition"] for p in south)


def test_facing_beside_unread_states_stays_residue_with_its_reason(converted):
    for stem, part in (("mid", "follows something besides the clicked face"), ("two_high", "IHasDummyBlocks")):
        assert f"blocks/{stem}.json" not in converted.files
        why = next(u.reason for u in converted.unhandled if u.source.endswith(f"blockstates/{stem}.json"))
        assert "doesn't set facing" in why and "the mod's placement after the block is set isn't read" in why
        assert part in why
