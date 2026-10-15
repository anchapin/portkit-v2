"""Station runtimes: the skillet's data table, block, item and fixed script (#177).

Farmer's Delight's skillet cooks the stove's campfire recipes as a placed block
(over the cooking pot's heat rule) and as a held item (food in the other hand,
near a heat source), and is an iron-tier weapon. The converter writes
scripts/portkit/data/<ns>_skillet.js, the facing x support block with the
runtime's component and tick, the skillet item (the block's own item, a
weapon allowed in the off-hand) and ships the fixed runtime
(portkit/adapters/farmersdelight/runtime/skillet*.js plus the cooking pot's heat helpers).

Offline: the FD-shaped mod of tests/test_stove.py plus a skillet.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from portkit.adapters.farmersdelight import skillet
from portkit.adapters.farmersdelight import cutting_board as stations
from portkit.pipeline import convert

from test_stations import PNG, ROOT, _write
from test_stove import _stove_mod, reference  # noqa: F401  (fixture)

DATA = "behavior_pack/scripts/portkit/data/farmersdelight_skillet.js"
STOVE = "behavior_pack/scripts/portkit/data/farmersdelight_stove.js"


def _skillet_mod(tmp_path, version="1.3.4", jar_recipes=None, loader_files=True):
    root = _stove_mod(tmp_path, version=version, jar_recipes=jar_recipes)
    ns = "farmersdelight"
    _write(root, f"assets/{ns}/blockstates/skillet.json", {"variants": {
        f"facing={d},support={s}": {"model": f"{ns}:block/skillet{'_tray' if s == 'true' else ''}", **({"y": y} if y else {})}
        for d, y in (("north", 0), ("east", 90), ("south", 180), ("west", 270)) for s in ("false", "true")
    }})
    faces = {f: {"uv": [1, 1, 15, 15], "texture": "#side"} for f in ("north", "east", "south", "west", "up", "down")}
    pan = {"name": "pan", "from": [1, 0, 1], "to": [15, 4, 15], "faces": faces}
    handle = {"name": "handle", "from": [7, 2, 15], "to": [9, 3, 16], "faces": faces}
    textures = {"side": f"{ns}:block/skillet_side", "particle": f"{ns}:block/skillet_side"}
    _write(root, f"assets/{ns}/models/block/skillet.json", {"textures": textures, "elements": [pan, handle]})
    _write(root, f"assets/{ns}/models/block/skillet_tray.json", {"textures": textures, "elements": [
        pan, handle, {"name": "grate", "from": [0, -1, 0], "to": [16, 0, 16], "faces": faces}]})
    _write(root, f"assets/{ns}/models/item/skillet.json", {"parent": f"{ns}:block/skillet"})
    _write(root, f"assets/{ns}/textures/block/skillet_side.png", PNG.read_bytes())
    lang = json.loads((root / f"assets/{ns}/lang/en_us.json").read_text())
    lang.update({f"block.{ns}.skillet": "Skillet",
                 f"block.{ns}.skillet.invalid_item": "This can't be cooked...",
                 f"item.{ns}.skillet.underwater": "Can't cook underwater...",
                 f"item.{ns}.skillet.how_to_cook": "Use your other hand to hold ingredients!"})
    _write(root, f"assets/{ns}/lang/en_us.json", lang)
    return root


def _table(tree: Path, path: str = DATA) -> dict:
    return json.loads((tree / path).read_text().split("export default ", 1)[1].rstrip().rstrip(";"))


@pytest.fixture
def converted(tmp_path, reference):  # noqa: F811
    result = convert(_skillet_mod(tmp_path), tmp_path / "out", emit_addon=False)
    return result, tmp_path / "out"


def test_table_cooks_the_stoves_recipes(converted):
    result, tree = converted
    table = _table(tree)
    assert [r["id"] for r in table["recipes"]] == [r["id"] for r in _table(tree, STOVE)["recipes"]]
    assert table["cooking"] == {"default_cooking_time": 600, "fire_aspect_step": 0.05, "min_cooking_time": 60,
                                "reduction": 0.2}
    assert table["tick_interval"] == 10 and table["support_state"] == "farmersdelight:support"
    assert table["launch"] == {"dy": 0.3, "speed": 0.08, "up": 0.25}
    assert table["item"] == table["block"] == "farmersdelight:skillet"
    assert result.stations["minecraft:campfire_cooking (skillet)"]["converted"] == len(table["recipes"])
    # The skillet adds no residue of its own: unstatable campfire recipes are the stove's.
    stove_residue = [u for u in result.unhandled if u.kind == "station_recipe" and "campfire" in u.source]
    assert len(stove_residue) == len({u.source for u in stove_residue})


def test_heat_rules_are_the_pots_plus_the_tag_alone_for_held_cooking(converted):
    _, tree = converted
    heat = _table(tree)["heat"]
    assert {"id": "minecraft:campfire", "states": {"extinguished": False}} in heat["sources"]
    assert {"id": "farmersdelight:stove", "states": {"farmersdelight:lit": "true"}} in heat["sources"]
    # Held: SkilletItem#isPlayerNearHeatSource tests the tag only, so no lit state.
    assert {"id": "minecraft:campfire"} in heat["nearby"] and {"id": "farmersdelight:stove"} in heat["nearby"]
    assert heat["conductors"] == [{"id": "minecraft:hopper"}]
    assert {"id": "minecraft:campfire"} in heat["tray"]


def test_messages_and_sounds(converted):
    _, tree = converted
    table = _table(tree)
    assert table["messages"] == {"how_to_cook": "item.farmersdelight:skillet.how_to_cook.name",
                                 "invalid_item": "tile.farmersdelight:skillet.invalid_item.name",
                                 "underwater": "item.farmersdelight:skillet.underwater.name"}
    assert table["sounds"]["place"] == {"id": "block.lantern.place", "volume": 0.7, "pitch": 1.0}
    # FD's own sound events aren't in this tiny mod: silent, and said so.
    assert table["sounds"]["attack"] is None and table["sounds"]["sizzle"] is None


def test_block_converts_with_its_support_state_and_the_runtime(converted):
    result, tree = converted
    body = json.loads((tree / "behavior_pack/blocks/skillet.json").read_text())
    block = body["minecraft:block"]
    assert body["format_version"] == "1.21.90"
    assert block["description"]["states"] == {"farmersdelight:support": ["false", "true"]}
    # getHorizontalDirection(): the player's own facing, offset 0.
    assert block["description"]["traits"]["minecraft:placement_direction"].get("y_rotation_offset", 0) == 0
    comps = block["components"]
    assert comps["minecraft:collision_box"] == {"origin": [-7, 0, -7], "size": [14, 4, 14]}
    assert comps["minecraft:tick"] == {"interval_range": [10, 10], "looping": True}
    assert comps["farmersdelight:portkit_skillet"] == {}
    assert "minecraft:loot" not in comps
    assert not any(u.source.endswith("blockstates/skillet.json") for u in result.unhandled)


def test_item_is_the_blocks_own_item_and_an_iron_weapon(converted):
    _, tree = converted
    item = json.loads((tree / "behavior_pack/items/skillet.json").read_text())
    assert item["format_version"] == "1.21.50"
    comps = item["minecraft:item"]["components"]
    assert comps["minecraft:block_placer"] == {"block": "farmersdelight:skillet", "replace_block_item": True}
    assert comps["minecraft:max_stack_size"] == 1
    assert comps["minecraft:durability"] == {"max_durability": 250}
    assert comps["minecraft:damage"] == {"value": 8}  # 1 + 5 + iron's 2
    assert comps["minecraft:enchantable"] == {"slot": "sword", "value": 14}
    assert comps["minecraft:repairable"]["repair_items"] == [
        {"items": ["minecraft:iron_ingot"], "repair_amount": "query.max_durability * 0.25"}]
    assert comps["minecraft:allow_off_hand"] == {"value": True}
    assert comps["minecraft:can_destroy_in_creative"] == {"value": False}  # NeoForge canAttackBlock


def test_entry_wires_the_skillet_and_the_tree_validates(converted):
    result, tree = converted
    main = (tree / "behavior_pack/scripts/portkit/main.js").read_text()
    assert "registerSkillet(skilletTable)" in main and "registerStove(stoveTable)" in main
    for name in ("skillet.js", "skillet_core.js", "cooking_pot_core.js", "station_core.js", "station_storage.js"):
        assert (tree / "behavior_pack/scripts/portkit" / name).read_text() == stations.runtime_source(name)
    assert result.report.ok, result.report.errors
    note = next(n for n in result.notes if n.startswith("farmersdelight:skillet: cooks"))
    for words in ("off-hand", "attack speed", "knockback", "waterlogging", "sneak to place"):
        assert words in note


def test_recipes_under_the_skillet_minimum_stay_on_the_stove(tmp_path, reference):  # noqa: F811
    jar = {"quick_from_campfire_cooking": {
        "type": "minecraft:campfire_cooking", "ingredient": {"item": "minecraft:egg"},
        "result": {"id": "farmersdelight:fried_egg"}, "cookingtime": 40}}
    result = convert(_skillet_mod(tmp_path, jar_recipes=jar), tmp_path / "out", emit_addon=False)
    ids = [r["id"] for r in _table(tmp_path / "out")["recipes"]]
    assert "farmersdelight:quick_from_campfire_cooking" not in ids
    assert "farmersdelight:quick_from_campfire_cooking" in [r["id"] for r in _table(tmp_path / "out", STOVE)["recipes"]]
    assert any("60-tick minimum" in n for n in result.notes)


def test_unread_version_leaves_the_skillet_as_residue(tmp_path, reference):  # noqa: F811
    result = convert(_skillet_mod(tmp_path, version="1.2.9"), tmp_path / "out", emit_addon=False)
    assert not (tmp_path / "out" / DATA).exists()
    # No station runtime for this version: the skillet is a plain facing and
    # boolean block now (facing plus support), its placement, box and
    # starting support the documented defaults (the fixture ships no class
    # files), and the notes say so; nothing toggles it.
    assert not any(u.source.endswith("blockstates/skillet.json") for u in result.unhandled)
    block = json.loads((tmp_path / "out/behavior_pack/blocks/skillet.json").read_text())["minecraft:block"]
    assert block["description"]["states"] == {"farmersdelight:support": [False, True]}
    assert "farmersdelight:portkit_toggle" not in block["components"]
    notes = " ".join(result.notes)
    assert "Starting value DEFAULT" in notes and "skillet" in notes


def test_output_is_deterministic(tmp_path, reference):  # noqa: F811
    first = convert(_skillet_mod(tmp_path), tmp_path / "a", emit_addon=False)
    second = convert(_skillet_mod(tmp_path), tmp_path / "b", emit_addon=False)
    assert (first.tree / DATA).read_bytes() == (second.tree / DATA).read_bytes()


def test_skillet_blocks_pin_both_loaders():
    for loader in ("neoforge", "fabric"):
        block = skillet.SKILLET_BLOCKS[loader]
        assert block.values == ("false", "true") and block.placement_offset == 0
        assert block.box == {"origin": [-7, 0, -7], "size": [14, 4, 14]}
    assert skillet.IRON_TIER == {"durability": 250, "attack_damage_bonus": 2.0, "enchantment_value": 14,
                                 "repair": "minecraft:iron_ingot"}


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_runtime_under_node(converted):
    _, tree = converted
    js = ROOT / "tests" / "js"
    for env in ({}, {"PORTKIT_SKILLET_TABLE": str(tree / DATA)}):
        proc = subprocess.run(
            ["node", "--import", str(js / "register.mjs"), "--test", str(js / "adapters" / "farmersdelight" / "skillet.test.mjs")],
            capture_output=True, text=True, timeout=120, env={"PATH": os.environ["PATH"], **env},
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
