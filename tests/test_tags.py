"""Tag-aware recipe emission (#88): a tag resolves when the addon can only mean one item."""
import json

from portkit.converters import recipes
from portkit.model import SourceMod


def _mod(tmp_path, ingredient, items=(), tag_files=None):
    root = tmp_path
    rec = root / "data" / "examplemod" / "recipes"
    rec.mkdir(parents=True, exist_ok=True)
    (rec / "steel_block.json").write_text(json.dumps({
        "type": "minecraft:crafting_shapeless",
        "ingredients": [{"tag": ingredient}],
        "result": {"item": "examplemod:steel_block"},
    }))
    models = root / "assets" / "examplemod" / "models" / "item"
    models.mkdir(parents=True, exist_ok=True)
    for name in items:
        (models / f"{name}.json").write_text('{"parent": "minecraft:item/generated"}')
    for rel, values in (tag_files or {}).items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"values": values}))
    return SourceMod(root=root, namespace="examplemod")


def _ingredients(result):
    body = result.files["recipes/steel_block.json"]["minecraft:recipe_shapeless"]
    return body["ingredients"]


def test_convention_name_resolves_to_the_mods_only_matching_item(tmp_path):
    result = recipes.convert(_mod(tmp_path, "c:ingots/steel", items=["steel_ingot"]))
    assert result.unhandled == []
    assert _ingredients(result) == [{"item": "examplemod:steel_ingot"}]
    assert "conventional name" in result.notes[0]


def test_convention_name_with_no_matching_item_stays_residue(tmp_path):
    result = recipes.convert(_mod(tmp_path, "c:ingots/steel", items=["bronze_ingot"]))
    assert result.files == {}
    assert "which covers more than one item" in result.unhandled[0].reason


def test_storage_blocks_and_raw_materials_follow_their_own_names(tmp_path):
    result = recipes.convert(_mod(tmp_path, "forge:raw_materials/tin", items=["raw_tin"]))
    assert _ingredients(result) == [{"item": "examplemod:raw_tin"}]


def test_tag_file_with_one_member_resolves_and_is_claimed(tmp_path):
    rel = "data/c/tags/items/ingots/steel.json"
    mod = _mod(tmp_path, "c:ingots/steel", items=["refined_steel"],
               tag_files={rel: ["examplemod:refined_steel"]})
    result = recipes.convert(mod)
    assert _ingredients(result) == [{"item": "examplemod:refined_steel"}]
    assert rel in result.consumed
    assert rel in result.notes[0]


def test_tag_file_beats_the_convention_name(tmp_path):
    mod = _mod(tmp_path, "c:ingots/steel", items=["steel_ingot", "refined_steel"],
               tag_files={"data/c/tags/item/ingots/steel.json": ["examplemod:refined_steel"]})
    assert _ingredients(recipes.convert(mod)) == [{"item": "examplemod:refined_steel"}]


def test_other_mods_members_are_dropped_and_said(tmp_path):
    mod = _mod(tmp_path, "c:ingots/steel", items=["steel_ingot"], tag_files={
        "data/c/tags/items/ingots/steel.json": [
            "examplemod:steel_ingot", {"id": "othermod:steel_ingot", "required": False},
        ],
    })
    result = recipes.convert(mod)
    assert _ingredients(result) == [{"item": "examplemod:steel_ingot"}]
    assert "othermod:steel_ingot" in result.notes[0]


def test_several_members_stay_residue_and_the_reason_lists_them(tmp_path):
    mod = _mod(tmp_path, "c:ingots/steel", items=["steel_ingot"], tag_files={
        "data/c/tags/items/ingots/steel.json": ["examplemod:steel_ingot", "minecraft:iron_ingot"],
    })
    result = recipes.convert(mod)
    assert result.files == {}
    reason = result.unhandled[0].reason
    assert "covers 2 items" in reason
    assert "examplemod:steel_ingot" in reason and "minecraft:iron_ingot" in reason


def test_nested_tags_expand_and_cycles_terminate(tmp_path):
    mod = _mod(tmp_path, "c:ingots/steel", items=["steel_ingot"], tag_files={
        "data/c/tags/items/ingots/steel.json": ["#examplemod:steels"],
        "data/examplemod/tags/items/steels.json": ["examplemod:steel_ingot", "#c:ingots/steel"],
    })
    assert _ingredients(recipes.convert(mod)) == [{"item": "examplemod:steel_ingot"}]


def test_a_tag_whose_members_are_all_elsewhere_says_so(tmp_path):
    mod = _mod(tmp_path, "c:ingots/steel", tag_files={
        "data/c/tags/items/ingots/steel.json": ["othermod:steel_ingot"],
    })
    reason = recipes.convert(mod).unhandled[0].reason
    assert "none of them in this addon" in reason


def test_a_mods_addition_to_a_vanilla_tag_is_not_the_whole_tag(tmp_path):
    """data/minecraft/tags/... in a mod appends to vanilla's list; it can't name the tag."""
    mod = _mod(tmp_path, "minecraft:leaves", items=["steel_leaves"], tag_files={
        "data/minecraft/tags/items/leaves.json": ["examplemod:steel_leaves"],
    })
    result = recipes.convert(mod)
    assert result.files == {}
    assert "covers more than one item" in result.unhandled[0].reason
