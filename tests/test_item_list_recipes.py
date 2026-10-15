"""Item-list ingredients (Java's "any of these items") convert one recipe per
item, under the same conditions as a multi-member tag's form 3 (#160).

Mythic Metals' ore/armour furnace recipes are the corpus case:
``"ingredient": [{"item": "...:deepslate_adamantite_ore"}, {"item": "...:adamantite_ore"}]``.
Vanilla Bedrock writes its armour -> nugget furnace recipes the same way, one per
piece (bedrock-samples behavior_pack/recipes/furnace_iron_helmet.json).
"""
import json
from pathlib import Path

from portkit.converters import recipes
from portkit.model import SourceMod


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body))


def _mod(tmp_path, recipe, name="thing"):
    root = tmp_path / "mod"
    _write(root, f"data/examplemod/recipe/{name}.json", recipe)
    return SourceMod(root=root, namespace="examplemod", loader="fabric", minecraft="1.21.1")


def _emitted(*items):
    found = {}
    for name in items:
        ident = f"examplemod:{name}"
        body = {"format_version": "1.20.10",
                "minecraft:item": {"description": {"identifier": ident}, "components": {}}}
        found[ident] = ("item", f"items/{name}.json", body)
    return found


def _recipes(result):
    return {k: v for k, v in result.files.items() if k.startswith("recipes/")}


def _reasons(result):
    return [u.reason for u in result.unhandled if u.kind == "recipe"]


FURNACE = {
    "type": "minecraft:blasting",
    "ingredient": [{"item": "examplemod:deepslate_tin_ore"}, {"item": "examplemod:tin_ore"}],
    "result": {"id": "examplemod:tin_ingot", "count": 1},
    "cookingtime": 100,
}


def test_furnace_item_list_writes_one_recipe_per_item(tmp_path):
    mod = _mod(tmp_path, FURNACE, name="tin_from_ores")
    result = recipes.convert(mod, _emitted("deepslate_tin_ore", "tin_ore", "tin_ingot"))
    files = _recipes(result)
    assert sorted(files) == [
        "recipes/tin_from_ores__examplemod_deepslate_tin_ore.json",
        "recipes/tin_from_ores__examplemod_tin_ore.json",
    ]
    body = files["recipes/tin_from_ores__examplemod_tin_ore.json"]["minecraft:recipe_furnace"]
    assert body["input"] == "examplemod:tin_ore"
    assert body["output"] == "examplemod:tin_ingot"
    assert body["tags"] == ["blast_furnace"]
    assert body["description"]["identifier"] == "examplemod:tin_from_ores__examplemod_tin_ore"
    assert not _reasons(result)
    assert any("lists 2 items" in n for n in result.notes)


def test_bare_string_list_and_vanilla_members(tmp_path):
    recipe = {"type": "minecraft:crafting_shapeless",
              "ingredients": ["minecraft:bone_meal", ["minecraft:coal", "minecraft:charcoal"]],
              "result": {"id": "minecraft:gunpowder", "count": 1}}
    result = recipes.convert(_mod(tmp_path, recipe, name="gunpowder"), _emitted())
    files = _recipes(result)
    assert sorted(files) == ["recipes/gunpowder__minecraft_charcoal.json",
                             "recipes/gunpowder__minecraft_coal.json"]
    body = files["recipes/gunpowder__minecraft_coal.json"]["minecraft:recipe_shapeless"]
    assert body["ingredients"] == [{"item": "minecraft:bone_meal"}, {"item": "minecraft:coal"}]


def test_one_entry_list_is_its_item(tmp_path):
    recipe = dict(FURNACE, ingredient=[{"item": "examplemod:tin_ore"}])
    result = recipes.convert(_mod(tmp_path, recipe, name="one"), _emitted("tin_ore", "tin_ingot"))
    files = _recipes(result)
    assert list(files) == ["recipes/one.json"]
    assert files["recipes/one.json"]["minecraft:recipe_furnace"]["input"] == "examplemod:tin_ore"


def test_list_member_not_converted_stays_residue(tmp_path):
    result = recipes.convert(_mod(tmp_path, FURNACE), _emitted("tin_ore", "tin_ingot"))
    assert not _recipes(result)
    (reason,) = _reasons(result)
    assert "list of 2 items" in reason
    assert "not converted: examplemod:deepslate_tin_ore" in reason


def test_list_filling_several_slots_stays_residue(tmp_path):
    recipe = {"type": "minecraft:crafting_shaped", "pattern": ["BPB"],
              "key": {"B": ["examplemod:a", "examplemod:b"], "P": "minecraft:sugar"},
              "result": {"id": "examplemod:pie"}}
    result = recipes.convert(_mod(tmp_path, recipe), _emitted("a", "b", "pie"))
    assert not _recipes(result)
    (reason,) = _reasons(result)
    assert "filling 2 grid slots" in reason


def test_list_beside_another_multi_ingredient_stays_residue(tmp_path):
    recipe = {"type": "minecraft:crafting_shapeless",
              "ingredients": [["examplemod:a", "examplemod:b"], ["examplemod:c", "examplemod:d"]],
              "result": {"id": "examplemod:thing"}}
    result = recipes.convert(_mod(tmp_path, recipe), _emitted("a", "b", "c", "d", "thing"))
    assert not _recipes(result)
    (reason,) = _reasons(result)
    assert "beside another multi-item ingredient" in reason


def test_list_holding_a_tag_stays_residue(tmp_path):
    recipe = dict(FURNACE, ingredient=[{"tag": "c:ores/tin"}, {"item": "examplemod:tin_ore"}])
    result = recipes.convert(_mod(tmp_path, recipe), _emitted("tin_ore", "tin_ingot"))
    assert not _recipes(result)
    assert _reasons(result) == ["ingredient is a list holding a tag or a non-item entry"]


def test_list_over_the_cap_stays_residue(tmp_path):
    names = [f"m{i}" for i in range(recipes.EXPANSION_CAP + 1)]
    recipe = dict(FURNACE, ingredient=[{"item": f"examplemod:{n}"} for n in names])
    result = recipes.convert(_mod(tmp_path, recipe), _emitted(*names, "tin_ingot"))
    assert not _recipes(result)
    (reason,) = _reasons(result)
    assert f"more than the {recipes.EXPANSION_CAP}" in reason


def test_alloy_forging_residue_names_the_forge(tmp_path):
    # Alloy Forgery's forging recipes need the forge from another mod's jar:
    # machine_recipe residue with the recipe's facts (#171, see
    # tests/adapters/alloy_forgery/test_alloy_forge.py and docs/decisions.md, 2026-10-15).
    recipe = {"type": "alloy_forgery:forging", "inputs": [{"item": "examplemod:a", "count": 2}],
              "output": {"id": "examplemod:b", "count": 1}, "min_forge_tier": 1, "fuel_per_tick": 5}
    result = recipes.convert(_mod(tmp_path, recipe), _emitted("a", "b"))
    assert not _recipes(result)
    assert not _reasons(result)
    (entry,) = result.unhandled
    assert entry.kind == "machine_recipe"
    assert entry.reason.startswith("an Alloy Forgery forge recipe: it forges 2 x examplemod:a into 1 examplemod:b")
    assert "isn't converted with this one" in entry.reason
