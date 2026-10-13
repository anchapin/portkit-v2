"""Station runtimes: the cooking pot's data table, block and fixed script (#177).

A Farmer's Delight ``farmersdelight:cooking`` recipe is data FD's cooking pot
block entity interprets. The converter writes every recipe it can state
exactly into scripts/portkit/data/<ns>_cooking_pot.js, gives the pot block the
runtime's custom component and a tick, and ships the fixed runtime
(portkit/runtime/cooking_pot*.js); anything it can't state stays
``station_recipe`` residue with the reason.

Offline: a tiny FD-shaped mod in tmp_path (tests/test_stations.py's helpers)
with its own tag reference.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from portkit.converters import cooking_pot, stations
from portkit.pipeline import convert

from test_stations import PNG, ROOT, _fd_mod, _write

DATA = "behavior_pack/scripts/portkit/data/farmersdelight_cooking_pot.js"


def _cook(ingredients, result, **extra):
    return {"type": "farmersdelight:cooking", "ingredients": ingredients, "result": result, **extra}


def _res(ident, count=1):
    return {"count": count, "id": ident}


RECIPES = {
    "cooking/beef_stew": _cook([{"tag": "c:foods/raw_beef"}, {"item": "minecraft:carrot"}, {"item": "minecraft:potato"}],
                               _res("farmersdelight:beef_stew"), experience=1.0),
    "cooking/hot_cocoa": _cook([{"tag": "c:drinks/milk"}, {"item": "minecraft:sugar"}, {"item": "minecraft:cocoa_beans"},
                                {"item": "minecraft:cocoa_beans"}], _res("farmersdelight:hot_cocoa"), experience=1.0),
    "cooking/mushroom_stew": _cook([{"item": "minecraft:brown_mushroom"}, {"item": "minecraft:red_mushroom"}],
                                   _res("minecraft:mushroom_stew"), container=_res("minecraft:bowl"), experience=1.0),
    "cooking/dumplings": _cook([{"item": "farmersdelight:cabbage"}, {"type": "neoforge:difference",
                                                                     "base": {"tag": "c:foods/vegetable"},
                                                                     "subtracted": {"item": "minecraft:melon_slice"}}],
                               _res("farmersdelight:dumplings", 2), cookingtime=100, experience=0.35),
    # residue, each for its own reason
    "cooking/rice": _cook([{"item": "farmersdelight:rice"}], _res("farmersdelight:cooked_rice")),
    "cooking/rabbit": _cook([{"item": "minecraft:rabbit"}], _res("minecraft:rabbit_stew")),
    "cooking/honey": _cook([{"item": "minecraft:honey_bottle"}], _res("farmersdelight:hot_cocoa")),
    "cooking/seven": _cook([{"item": "minecraft:carrot"}] * 7, _res("farmersdelight:beef_stew")),
    "cooking/carrot_a": _cook([{"item": "minecraft:carrot"}, {"item": "minecraft:apple"}], _res("farmersdelight:beef_stew")),
    "cooking/carrot_b": _cook([{"item": "minecraft:apple"}, {"tag": "c:foods/vegetable"}], _res("farmersdelight:hot_cocoa")),
}
ITEMS = ("beef_stew", "hot_cocoa", "dumplings", "cabbage", "milk_bottle", "cooked_rice")
SUPPORT = ("none", "handle", "tray")


def _pot_mod(tmp_path, recipes_=None, version="1.3.4"):
    root = _fd_mod(tmp_path, version=version, recipes_={})
    ns = "farmersdelight"
    png = PNG.read_bytes()
    models = {"none": "cooking_pot", "handle": "cooking_pot_handle", "tray": "cooking_pot_tray"}
    _write(root, f"assets/{ns}/blockstates/cooking_pot.json", {"variants": {
        f"facing={d},support={v}": {"model": f"{ns}:block/{models[v]}", **({"y": y} if y else {})}
        for d, y in (("north", 0), ("east", 90), ("south", 180), ("west", 270)) for v in SUPPORT
    }})
    side = {f: {"uv": [2, 6, 14, 16], "texture": "#side"} for f in ("north", "east", "south", "west", "up", "down")}
    pot = {"name": "pot", "from": [2, 0, 2], "to": [14, 10, 14], "faces": side}
    spoon = {"name": "spoon", "from": [7, 3, 7], "to": [9, 15, 9],
             "rotation": {"angle": -22.5, "axis": "z", "origin": [8, 3, 8]}, "faces": side}
    textures = {"side": f"{ns}:block/cooking_pot_side", "particle": f"{ns}:block/cooking_pot_side"}
    _write(root, f"assets/{ns}/models/block/cooking_pot.json", {"textures": textures, "elements": [pot, spoon]})
    _write(root, f"assets/{ns}/models/block/cooking_pot_handle.json", {"textures": textures, "elements": [
        pot, spoon, {"name": "hoop", "from": [1, 8, 8], "to": [15, 16, 8], "faces": side}]})
    _write(root, f"assets/{ns}/models/block/cooking_pot_tray.json", {"textures": textures, "elements": [
        pot, spoon, {"name": "north_legs", "from": [0, -16, 0], "to": [16, 0, 0], "faces": side}]})
    _write(root, f"assets/{ns}/textures/block/cooking_pot_side.png", png)
    for item in ITEMS:
        _write(root, f"assets/{ns}/models/item/{item}.json",
               {"parent": "minecraft:item/generated", "textures": {"layer0": f"{ns}:item/{item}"}})
        _write(root, f"assets/{ns}/textures/item/{item}.png", png)
    lang = json.loads((root / f"assets/{ns}/lang/en_us.json").read_text())
    lang.update({f"item.{ns}.{i}": i for i in ITEMS})
    _write(root, f"assets/{ns}/lang/en_us.json", lang)
    _write(root, f"data/{ns}/tags/block/heat_sources.json", {"values": [
        "minecraft:magma_block", "minecraft:lava_cauldron", f"{ns}:stove", f"#{ns}:tray_heat_sources"]})
    _write(root, f"data/{ns}/tags/block/heat_conductors.json", {"values": [
        "minecraft:hopper", {"id": "create:chute", "required": False}]})
    _write(root, f"data/{ns}/tags/block/tray_heat_sources.json", {"values": [
        "minecraft:lava", "#minecraft:campfires", "#minecraft:fire"]})
    _write(root, f"data/{ns}/tags/item/serving_containers.json", {"values": [
        "minecraft:bowl", "minecraft:glass_bottle", "minecraft:bucket"]})
    _write(root, "data/c/tags/item/drinks/milk.json", {"values": ["farmersdelight:milk_bottle"]})
    for name, body in (RECIPES if recipes_ is None else recipes_).items():
        _write(root, f"data/{ns}/recipe/{name}.json", body)
    return root


@pytest.fixture
def reference(tmp_path, monkeypatch):
    ref = tmp_path / "ref"
    _write(ref, "vanilla-1.21.1.json", {"set": "vanilla-1.21.1", "tags": {}})
    _write(ref, "neoforge-1.21.1.json", {"set": "neoforge-1.21.1", "tags": {
        "c:tools/shear": ["minecraft:shears"], "c:tools/knife": [],
        "c:foods/raw_beef": ["minecraft:beef"], "c:drinks/milk": ["minecraft:milk_bucket"],
        "c:foods/vegetable": ["minecraft:carrot", "minecraft:potato", "minecraft:melon_slice"]}})
    monkeypatch.setenv("PORTKIT_TAG_REFERENCE", str(ref))
    return ref


def _table(tree: Path) -> dict:
    return json.loads((tree / DATA).read_text().split("export default ", 1)[1].rstrip().rstrip(";"))


@pytest.fixture
def converted(tmp_path, reference):
    result = convert(_pot_mod(tmp_path), tmp_path / "out", emit_addon=False)
    return result, tmp_path / "out"


def test_table_holds_the_recipes_it_can_state(converted):
    result, tree = converted
    table = _table(tree)
    by_id = {r["id"]: r for r in table["recipes"]}
    assert sorted(by_id) == ["farmersdelight:cooking/beef_stew", "farmersdelight:cooking/dumplings",
                             "farmersdelight:cooking/hot_cocoa", "farmersdelight:cooking/mushroom_stew"]
    stew = by_id["farmersdelight:cooking/beef_stew"]
    assert stew["ingredients"] == [["minecraft:beef"], ["minecraft:carrot"], ["minecraft:potato"]]
    # No container in the recipe: the result's crafting remainder (FD's bowlFoodItem).
    assert stew["container"] == "minecraft:bowl"
    assert stew["cookingtime"] == 200 and stew["experience"] == 1.0
    assert by_id["farmersdelight:cooking/mushroom_stew"]["container"] == "minecraft:bowl"
    # neoforge:difference: the base's items less the subtracted ones.
    dumplings = by_id["farmersdelight:cooking/dumplings"]
    assert dumplings["ingredients"][1] == ["minecraft:carrot", "minecraft:potato"]
    assert dumplings["container"] is None and dumplings["result"] == {"item": "farmersdelight:dumplings", "count": 2}
    assert by_id["farmersdelight:cooking/hot_cocoa"]["ingredients"][0] == ["farmersdelight:milk_bottle",
                                                                           "minecraft:milk_bucket"]
    # Remainders of what a written recipe consumes: milk bucket (vanilla, cited), milk bottle (FD).
    assert table["remainders"] == {"farmersdelight:milk_bottle": "minecraft:glass_bottle",
                                   "minecraft:milk_bucket": "minecraft:bucket"}
    assert table["serving_containers"] == ["minecraft:bowl", "minecraft:bucket", "minecraft:glass_bottle"]
    assert table["sounds"]["serve"]["id"] == "armor.equip_generic"
    assert table["sounds"]["handle"] == {"id": "block.lantern.place", "volume": 0.7, "pitch": 1.0}
    assert table["tick_interval"] == 10 and table["support_state"] == "farmersdelight:support"
    assert result.stations["farmersdelight:cooking"]["converted"] == 4


def test_heat_rules_come_from_fds_tags(converted):
    result, tree = converted
    heat = _table(tree)["heat"]
    assert {"id": "minecraft:magma"} in heat["sources"]
    assert {"id": "minecraft:campfire", "states": {"extinguished": False}} in heat["sources"]
    assert {"id": "minecraft:cauldron", "states": {"cauldron_liquid": "lava"}, "not": {"fill_level": 0}} in heat["sources"]
    assert {"id": "minecraft:flowing_lava"} in heat["sources"]
    # The tray only asks what the block is, lit or not.
    assert {"id": "minecraft:campfire"} in heat["tray"] and {"id": "minecraft:soul_fire"} in heat["tray"]
    assert heat["conductors"] == [{"id": "minecraft:hopper"}]  # create:chute is optional and absent
    assert any("farmersdelight:stove" in n for n in result.notes)


def test_residue_says_why(converted):
    result, _ = converted
    reasons = {Path(u.source).stem: (u.kind, u.reason) for u in result.unhandled if "/cooking/" in u.source}
    assert reasons["rice"] == ("station_recipe", "ingredient farmersdelight:rice is not converted")
    assert "crafting remainder" in reasons["rabbit"][1] and reasons["rabbit"][0] == "station_recipe"
    assert "honey_bottle" in reasons["honey"][1]
    assert "one to six" in reasons["seven"][1]
    assert "cooking/carrot_b" in reasons["carrot_a"][1] and "cooking/carrot_a" in reasons["carrot_b"][1]
    assert result.stations["farmersdelight:cooking"]["residue"] == 6


def test_block_converts_with_support_state_tick_and_component(converted):
    result, tree = converted
    body = json.loads((tree / "behavior_pack/blocks/cooking_pot.json").read_text())
    block = body["minecraft:block"]
    assert body["format_version"] == "1.21.90"
    assert block["description"]["states"] == {"farmersdelight:support": list(SUPPORT)}
    assert block["description"]["traits"]["minecraft:placement_direction"]["y_rotation_offset"] == 180
    comps = block["components"]
    assert comps["minecraft:collision_box"] == {"origin": [-6, 0, -6], "size": [12, 10, 12]}
    assert comps["minecraft:tick"] == {"interval_range": [10, 10], "looping": True}
    assert comps["farmersdelight:portkit_cooking_pot"] == {}
    assert comps["minecraft:geometry"]["bone_visibility"] == {
        v: f"q.block_state('farmersdelight:support') == '{v}'" for v in SUPPORT}
    turns = {p["condition"].split("== ")[1].strip("'"): p["components"]["minecraft:transformation"]["rotation"][1]
             for p in block["permutations"]}
    assert turns == {"north": 0, "east": -90, "south": 180, "west": 90}
    geo = json.loads((tree / "resource_pack/models/blocks/cooking_pot.geo.json").read_text())
    bones = {b["name"]: b for b in geo["minecraft:geometry"][0]["bones"]}
    assert set(bones) == set(SUPPORT)
    # The tray's legs sit wholly in the block below: not drawn (30-pixel limit), and said.
    assert len(bones["tray"]["cubes"]) == 2
    assert any("north_legs" in n for n in result.notes)
    assert not any(u.source.endswith("blockstates/cooking_pot.json") for u in result.unhandled)


def test_entry_wires_both_stations_and_the_tree_validates(converted):
    result, tree = converted
    main = (tree / "behavior_pack/scripts/portkit/main.js").read_text()
    assert "registerCookingPot(cookingPotTable)" in main
    for name in ("cooking_pot.js", "cooking_pot_core.js", "station_storage.js"):
        assert (tree / "behavior_pack/scripts/portkit" / name).read_text() == stations.runtime_source(name)
    assert result.report.ok, result.report.errors


def test_cutting_board_still_ships_alone(tmp_path, reference):
    # No cooking recipes: no pot table, the cutting board entry unchanged in shape.
    result = convert(_fd_mod(tmp_path), tmp_path / "out", emit_addon=False)
    main = (tmp_path / "out/behavior_pack/scripts/portkit/main.js").read_text()
    assert "registerCuttingBoard" in main and "CookingPot" not in main
    assert (tmp_path / "out/behavior_pack/scripts/portkit/station_storage.js").is_file()
    assert result.report.ok, result.report.errors


def test_output_is_deterministic(tmp_path, reference):
    first = convert(_pot_mod(tmp_path), tmp_path / "a", emit_addon=False)
    second = convert(_pot_mod(tmp_path), tmp_path / "b", emit_addon=False)
    assert (first.tree / DATA).read_bytes() == (second.tree / DATA).read_bytes()


def test_unread_version_stays_residue(tmp_path, reference):
    result = convert(_pot_mod(tmp_path, version="1.2.9"), tmp_path / "out", emit_addon=False)
    assert not (tmp_path / "out" / DATA).exists()
    cooking = [u for u in result.unhandled if u.kind == "station_recipe" and "/cooking/" in u.source]
    assert cooking and all("1.2.9" in u.reason and "cooking-pot" in u.reason for u in cooking)


def test_remainder_tables_cover_both_loaders():
    neo, fab = cooking_pot.FD_CRAFT_REMAINDERS["neoforge"], cooking_pot.FD_CRAFT_REMAINDERS["fabric"]
    assert set(neo) == set(fab)
    assert all(neo[k][0] == fab[k][0] for k in neo)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_runtime_under_node(converted):
    _, tree = converted
    js = ROOT / "tests" / "js"
    for env in ({}, {"PORTKIT_COOKING_TABLE": str(tree / DATA)}):
        proc = subprocess.run(
            ["node", "--import", str(js / "register.mjs"), "--test", str(js / "cooking_pot.test.mjs")],
            capture_output=True, text=True, timeout=120, env={"PATH": os.environ["PATH"], **env},
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
