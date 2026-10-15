"""Station runtimes: the stove's data table, block and fixed script (#177).

Farmer's Delight's stove cooks vanilla ``minecraft:campfire_cooking`` recipes on
six spots while lit. The converter writes every campfire recipe it can state
exactly (vanilla's, from the fetched reference, and the jar's own, which still
convert as Bedrock campfire recipes) into
scripts/portkit/data/<ns>_stove.js, converts the facing x lit block with its
light and the runtime's component and tick, wires the lit stove into the
cooking pot's heat rules and ships the fixed runtime (portkit/adapters/farmersdelight/runtime/stove*.js).

Offline: the tiny FD-shaped mod of tests/test_cooking_pot.py plus a stove, its
own tag reference and its own vanilla recipe reference (PORTKIT_RECIPE_REFERENCE).
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from portkit.adapters.farmersdelight import stove
from portkit.adapters.farmersdelight import cutting_board as stations
from portkit.data import recipes as recipe_data
from portkit.pipeline import convert

from test_cooking_pot import _pot_mod
from test_stations import PNG, ROOT, SHOVELS, _write

DATA = "behavior_pack/scripts/portkit/data/farmersdelight_stove.js"
POT = "behavior_pack/scripts/portkit/data/farmersdelight_cooking_pot.js"


def _camp(ingredient, result, cookingtime=600, **extra):
    return {"type": "minecraft:campfire_cooking", "category": "food", "ingredient": ingredient,
            "result": result, **({"cookingtime": cookingtime} if cookingtime is not None else {}),
            "experience": 0.35, **extra}


JAR_RECIPES = {
    "fried_egg_from_campfire_cooking": _camp({"item": "minecraft:egg"}, {"count": 1, "id": "farmersdelight:fried_egg"}),
    "cooked_bacon_from_campfire_cooking": _camp({"item": "farmersdelight:bacon"},
                                                {"count": 1, "id": "farmersdelight:cooked_bacon"}),
    # residue, each for its own reason
    "rice_from_campfire_cooking": _camp({"item": "farmersdelight:rice"}, {"id": "farmersdelight:fried_egg"}),
    "no_time_from_campfire_cooking": _camp({"item": "minecraft:carrot"}, {"id": "farmersdelight:fried_egg"},
                                           cookingtime=None),
    "kelp_from_campfire_cooking": _camp({"item": "minecraft:kelp"}, {"id": "farmersdelight:fried_egg"}),
    "gated_from_campfire_cooking": {**_camp({"item": "minecraft:apple"}, {"id": "farmersdelight:fried_egg"}),
                                    "neoforge:conditions": [{"type": "neoforge:mod_loaded", "modid": "absentmod"}]},
}
VANILLA = {
    "minecraft:cooked_beef_from_campfire_cooking": _camp({"item": "minecraft:beef"}, {"id": "minecraft:cooked_beef"}),
    "minecraft:dried_kelp_from_campfire_cooking": _camp({"item": "minecraft:kelp"}, {"id": "minecraft:dried_kelp"},
                                                        experience=0.1),
}
ITEMS = ("fried_egg", "bacon", "cooked_bacon")


def _stove_mod(tmp_path, version="1.3.4", jar_recipes=None):
    root = _pot_mod(tmp_path, version=version)
    ns = "farmersdelight"
    png = PNG.read_bytes()
    _write(root, f"assets/{ns}/blockstates/stove.json", {"variants": {
        f"facing={d},lit={lit}": {"model": f"{ns}:block/stove{'_on' if lit == 'true' else ''}", **({"y": y} if y else {})}
        for d, y in (("north", 0), ("east", 90), ("south", 180), ("west", 270)) for lit in ("false", "true")
    }})
    for model, front, top in (("stove", "stove_front", "stove_top"), ("stove_on", "stove_front_on", "stove_top_on")):
        _write(root, f"assets/{ns}/models/block/{model}.json", {
            "parent": "minecraft:block/orientable_with_bottom",
            "textures": {"bottom": f"{ns}:block/stove_bottom", "front": f"{ns}:block/{front}",
                         "side": f"{ns}:block/stove_side", "top": f"{ns}:block/{top}"}})
    for texture in ("stove_bottom", "stove_front", "stove_front_on", "stove_side", "stove_top", "stove_top_on"):
        _write(root, f"assets/{ns}/textures/block/{texture}.png", png)
    for item in ITEMS:
        _write(root, f"assets/{ns}/models/item/{item}.json",
               {"parent": "minecraft:item/generated", "textures": {"layer0": f"{ns}:item/{item}"}})
        _write(root, f"assets/{ns}/textures/item/{item}.png", png)
    lang = json.loads((root / f"assets/{ns}/lang/en_us.json").read_text())
    lang.update({f"item.{ns}.{i}": i for i in ITEMS})
    _write(root, f"assets/{ns}/lang/en_us.json", lang)
    for name, body in (JAR_RECIPES if jar_recipes is None else jar_recipes).items():
        _write(root, f"data/{ns}/recipe/{name}.json", body)
    return root


@pytest.fixture
def reference(tmp_path, monkeypatch):
    ref = tmp_path / "ref"
    _write(ref, "vanilla-1.21.1.json", {"set": "vanilla-1.21.1", "tags": {"minecraft:shovels": SHOVELS}})
    _write(ref, "neoforge-1.21.1.json", {"set": "neoforge-1.21.1", "tags": {
        "c:tools/shear": ["minecraft:shears"], "c:tools/knife": [], "c:buckets/water": ["minecraft:water_bucket"],
        "c:foods/raw_beef": ["minecraft:beef"], "c:drinks/milk": ["minecraft:milk_bucket"],
        "c:foods/vegetable": ["minecraft:carrot", "minecraft:potato", "minecraft:melon_slice"]}})
    monkeypatch.setenv("PORTKIT_TAG_REFERENCE", str(ref))
    vanilla = tmp_path / "campfire.json"
    vanilla.write_text(json.dumps({"recipes": VANILLA}))
    monkeypatch.setenv("PORTKIT_RECIPE_REFERENCE", str(vanilla))
    return ref


def _table(tree: Path, path: str = DATA) -> dict:
    return json.loads((tree / path).read_text().split("export default ", 1)[1].rstrip().rstrip(";"))


@pytest.fixture
def converted(tmp_path, reference):
    result = convert(_stove_mod(tmp_path), tmp_path / "out", emit_addon=False)
    return result, tmp_path / "out"


def test_table_holds_jar_and_vanilla_campfire_recipes(converted):
    result, tree = converted
    table = _table(tree)
    by_id = {r["id"]: r for r in table["recipes"]}
    assert sorted(by_id) == ["farmersdelight:cooked_bacon_from_campfire_cooking",
                             "farmersdelight:fried_egg_from_campfire_cooking",
                             "minecraft:cooked_beef_from_campfire_cooking"]
    assert by_id["minecraft:cooked_beef_from_campfire_cooking"] == {
        "id": "minecraft:cooked_beef_from_campfire_cooking", "ingredient": ["minecraft:beef"],
        "result": {"item": "minecraft:cooked_beef", "count": 1}, "cookingtime": 600}
    assert by_id["farmersdelight:fried_egg_from_campfire_cooking"]["result"] == {
        "item": "farmersdelight:fried_egg", "count": 1}
    assert table["slots"] == 6 and table["tick_interval"] == 10 and table["lit_state"] == "farmersdelight:lit"
    assert result.stations["minecraft:campfire_cooking"] == {
        "converted": 3, "residue": 3, "vanilla": 1, "data": "scripts/portkit/data/farmersdelight_stove.js",
        "block": "farmersdelight:stove"}


def test_residue_and_notes_say_why(converted):
    result, _ = converted
    reasons = {Path(u.source).stem.replace("_from_campfire_cooking", ""): (u.kind, u.reason)
               for u in result.unhandled if "campfire_cooking" in u.source}
    assert reasons["rice"] == ("station_recipe", "ingredient farmersdelight:rice is not converted")
    assert "cookingtime" in reasons["no_time"][1] and reasons["no_time"][0] == "station_recipe"
    # The jar's kelp recipe and vanilla's dried kelp take the same item: neither is written.
    assert "minecraft:dried_kelp_from_campfire_cooking" in reasons["kelp"][1]
    assert any("minecraft:dried_kelp_from_campfire_cooking" in n and "isn't in the table" in n for n in result.notes)
    # Load conditions decide first: a recipe Java doesn't load never reaches the stove.
    assert reasons["gated"][0] == "conditional_recipe"


def test_campfire_recipes_still_convert_as_bedrock_recipes(converted):
    result, tree = converted
    egg = json.loads((tree / "behavior_pack/recipes/fried_egg_from_campfire_cooking.json").read_text())
    assert egg["minecraft:recipe_furnace"]["tags"] == ["campfire", "soul_campfire"]


def test_lighting_and_putting_out(converted):
    _, tree = converted
    table = _table(tree)
    assert table["extinguish"] == {"shovel": {"items": sorted(SHOVELS), "tags": ["minecraft:is_shovel"]},
                                   "water": {"minecraft:water_bucket": "minecraft:bucket"}}
    assert table["ignite"] == {"fire_charge": ["minecraft:fire_charge"], "flint_and_steel": ["minecraft:flint_and_steel"]}
    assert table["burn"] == {"amount": 1.0, "cause": "campfire"}
    sounds = table["sounds"]
    assert sounds["place"] == {"id": "block.lantern.place", "volume": 0.5, "pitch": 1.0}
    assert sounds["crackle"]["id"] == "block.campfire.crackle" and sounds["crackle"]["chance_per_tick"] == 0.1
    assert sounds["flint_and_steel"]["id"] == "fire.ignite" and sounds["water"]["id"] == "random.fizz"


def test_block_converts_lit_and_turned(converted):
    result, tree = converted
    body = json.loads((tree / "behavior_pack/blocks/stove.json").read_text())
    block = body["minecraft:block"]
    assert body["format_version"] == "1.21.90"
    assert block["description"]["states"] == {"farmersdelight:lit": ["false", "true"]}
    assert block["description"]["traits"]["minecraft:placement_direction"]["y_rotation_offset"] == 180
    comps = block["components"]
    assert comps["minecraft:geometry"] == "minecraft:geometry.full_block"
    assert comps["minecraft:material_instances"]["north"] == {"texture": "farmersdelight:stove_front"}
    assert comps["minecraft:tick"] == {"interval_range": [10, 10], "looping": True}
    assert comps["farmersdelight:portkit_stove"] == {}
    perms = {p["condition"]: p["components"] for p in block["permutations"]}
    assert len(perms) == 8
    lit_east = perms["q.block_state('minecraft:cardinal_direction') == 'east' && "
                     "q.block_state('farmersdelight:lit') == 'true'"]
    assert lit_east["minecraft:transformation"] == {"rotation": [0, -90, 0]}
    assert lit_east["minecraft:light_emission"] == 13
    assert lit_east["minecraft:material_instances"]["north"] == {"texture": "farmersdelight:stove_front_on"}
    assert lit_east["minecraft:material_instances"]["up"] == {"texture": "farmersdelight:stove_top_on"}
    unlit_west = perms["q.block_state('minecraft:cardinal_direction') == 'west' && "
                       "q.block_state('farmersdelight:lit') == 'false'"]
    assert "minecraft:light_emission" not in unlit_west
    assert unlit_west["minecraft:material_instances"]["north"] == {"texture": "farmersdelight:stove_front"}
    assert not (tree / "resource_pack/models/blocks/stove.geo.json").exists()
    assert not any(u.source.endswith("blockstates/stove.json") for u in result.unhandled)


def test_lit_stove_heats_the_cooking_pot(converted):
    result, tree = converted
    heat = _table(tree, POT)["heat"]
    assert {"id": "farmersdelight:stove", "states": {"farmersdelight:lit": "true"}} in heat["sources"]
    assert not any("heat source block farmersdelight:stove" in n for n in result.notes)


def test_entry_wires_the_stove_beside_the_pot_and_the_tree_validates(converted):
    result, tree = converted
    main = (tree / "behavior_pack/scripts/portkit/main.js").read_text()
    for call in ("registerCookingPot(cookingPotTable)", "registerStove(stoveTable)"):
        assert call in main
    for name in ("stove.js", "stove_core.js", "station_storage.js"):
        assert (tree / "behavior_pack/scripts/portkit" / name).read_text() == stations.runtime_source(name)
    assert result.report.ok, result.report.errors


def test_without_vanilla_reference_only_the_jars_recipes(tmp_path, reference, monkeypatch):
    monkeypatch.delenv("PORTKIT_RECIPE_REFERENCE")
    result = convert(_stove_mod(tmp_path), tmp_path / "out", emit_addon=False)
    ids = [r["id"] for r in _table(tmp_path / "out")["recipes"]]
    assert all(i.startswith("farmersdelight:") for i in ids) and "farmersdelight:kelp_from_campfire_cooking" in ids
    assert any("aren't cached" in n and "portkit reference fetch" in n for n in result.notes)


def test_unread_version_leaves_the_stove_as_residue(tmp_path, reference):
    result = convert(_stove_mod(tmp_path, version="1.2.9"), tmp_path / "out", emit_addon=False)
    assert not (tmp_path / "out" / DATA).exists()
    assert any(u.source.endswith("blockstates/stove.json") for u in result.unhandled)
    # The jar's campfire recipes are plain Bedrock campfire recipes, not stove residue.
    assert not any(u.kind == "station_recipe" and "campfire" in u.source for u in result.unhandled)
    assert (tmp_path / "out/behavior_pack/recipes/fried_egg_from_campfire_cooking.json").is_file()


def test_output_is_deterministic(tmp_path, reference):
    first = convert(_stove_mod(tmp_path), tmp_path / "a", emit_addon=False)
    second = convert(_stove_mod(tmp_path), tmp_path / "b", emit_addon=False)
    assert (first.tree / DATA).read_bytes() == (second.tree / DATA).read_bytes()


def test_stove_blocks_pin_both_loaders():
    for loader in ("neoforge", "fabric"):
        block = stove.STOVE_BLOCKS[loader]
        assert block.values == ("false", "true") and block.placement_offset == 180
        assert block.value_components == {"true": {"minecraft:light_emission": 13}}


def test_recipe_reference_keeps_campfire_recipes_and_picks_the_nearest_version():
    summary = json.dumps({
        "cooked_beef_from_campfire_cooking": VANILLA["minecraft:cooked_beef_from_campfire_cooking"],
        "cooked_beef": {"type": "minecraft:smelting", "ingredient": "minecraft:beef"},
    }).encode()
    derived = json.loads(recipe_data.derive(recipe_data.SETS[0], summary))
    assert list(derived["recipes"]) == ["minecraft:cooked_beef_from_campfire_cooking"]
    assert recipe_data.select("1.21.1").minecraft == "1.21.1"
    assert recipe_data.select("26.1.2").minecraft == "26.1"
    assert recipe_data.select("1.20.1").minecraft == "1.21.1"
    assert recipe_data.select(None) is None
    with pytest.raises(ValueError):
        recipe_data.derive(recipe_data.SETS[0], b"{}")


def test_recipe_reference_missing_from_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("PORTKIT_REFERENCE_CACHE", str(tmp_path))
    found, chosen = recipe_data.campfire_recipes("1.21.1")
    assert found is None and chosen.minecraft == "1.21.1"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_runtime_under_node(converted):
    _, tree = converted
    js = ROOT / "tests" / "js"
    for env in ({}, {"PORTKIT_STOVE_TABLE": str(tree / DATA)}):
        proc = subprocess.run(
            ["node", "--import", str(js / "register.mjs"), "--test", str(js / "adapters" / "farmersdelight" / "stove.test.mjs")],
            capture_output=True, text=True, timeout=120, env={"PATH": os.environ["PATH"], **env},
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
