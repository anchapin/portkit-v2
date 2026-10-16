"""FD knives carry their tier's durability so Bedrock's smithing table takes the
diamond knife as the netherite upgrade's base (#263)."""
import json

from portkit.adapters.farmersdelight import knives
from portkit.converters import recipes
from portkit.model import SourceMod


def _item(name, **components):
    return {"format_version": "1.20.30", "minecraft:item": {
        "description": {"identifier": f"farmersdelight:{name}", "menu_category": {"category": "items"}},
        "components": {"minecraft:icon": f"farmersdelight:{name}", "minecraft:max_stack_size": 64,
                       "minecraft:hand_equipped": True, **components}}}


def _mod(tmp_path, loader="neoforge", version="1.3.4"):
    return SourceMod(root=tmp_path, namespace="farmersdelight", loader=loader, mods={"farmersdelight": version})


def test_each_knife_gets_its_tiers_durability_and_one_per_stack(tmp_path):
    tags = {"minecraft:tags": {"tags": ["minecraft:transformable_items"]}}
    files = {f"items/{n}.json": _item(n, **(tags if n == "diamond_knife" else {}))
             for n in ("flint_knife", "iron_knife", "diamond_knife", "netherite_knife", "golden_knife")}
    result = knives.convert(_mod(tmp_path), files)
    got = {path: body["minecraft:item"]["components"] for path, body in result.files.items()}
    assert {p: c["minecraft:durability"]["max_durability"] for p, c in got.items()} == {
        "items/flint_knife.json": 131, "items/iron_knife.json": 250, "items/diamond_knife.json": 1561,
        "items/netherite_knife.json": 2031, "items/golden_knife.json": 32}
    assert all(c["minecraft:max_stack_size"] == 1 for c in got.values())
    # The smithing slot tag the recipe converter gave it stays.
    assert got["items/diamond_knife.json"]["minecraft:tags"] == tags["minecraft:tags"]
    assert any("diamond_knife 1561 (Tiers.DIAMOND)" in n for n in result.notes)


def test_refabricated_reads_its_own_table_and_leaves_copper_alone(tmp_path):
    files = {f"items/{n}.json": _item(n) for n in ("copper_knife", "diamond_knife")}
    result = knives.convert(_mod(tmp_path, "fabric", "26.1-3.6.28+refabricated"), files)
    assert set(result.files) == {"items/diamond_knife.json"}


def test_an_unread_version_or_another_mod_gets_nothing(tmp_path):
    files = {"items/diamond_knife.json": _item("diamond_knife")}
    assert knives.convert(_mod(tmp_path, version="1.2.0"), files).files == {}
    other = SourceMod(root=tmp_path, namespace="examplemod", loader="neoforge", mods={"farmersdelight": "1.3.4"})
    assert knives.convert(other, files).files == {}


def test_a_knife_that_did_not_convert_is_not_made_up(tmp_path):
    assert knives.convert(_mod(tmp_path), {}).files == {}


def _smithing_mod(tmp_path, recipe):
    src = tmp_path / "data" / "examplemod" / "recipes"
    src.mkdir(parents=True)
    (src / "upgrade.json").write_text(json.dumps(recipe))
    return SourceMod(root=tmp_path, namespace="examplemod")


def _emitted(*names):
    return {f"examplemod:{n}": ("item", f"items/{n}.json", {
        "format_version": "1.20.10",
        "minecraft:item": {"description": {"identifier": f"examplemod:{n}"}, "components": {}}}) for n in names}


def test_mod_items_in_smithing_slots_carry_the_slot_tag(tmp_path):
    mod = _smithing_mod(tmp_path, {
        "type": "minecraft:smithing_transform",
        "template": {"item": "examplemod:steel_template"},
        "base": {"item": "examplemod:steel_sword"},
        "addition": {"item": "examplemod:steel_plate"},
        "result": {"id": "examplemod:netherite_steel_sword"},
    })
    result = recipes.convert(mod, emitted=_emitted("steel_template", "steel_sword", "steel_plate",
                                                   "netherite_steel_sword"))
    tags = {p: b["minecraft:item"]["components"].get("minecraft:tags") for p, b in result.files.items()
            if p.startswith("items/")}
    assert tags == {
        "items/steel_template.json": {"tags": ["minecraft:transform_templates"]},
        "items/steel_sword.json": {"tags": ["minecraft:transformable_items"]},
        "items/steel_plate.json": {"tags": ["minecraft:transform_materials"]},
    }
    assert result.files["items/steel_sword.json"]["format_version"] == "1.20.50"


def test_vanilla_slots_blocks_and_no_emitted_list_get_no_tags(tmp_path):
    recipe = {
        "type": "minecraft:smithing_transform",
        "template": {"item": "minecraft:netherite_upgrade_smithing_template"},
        "base": {"item": "examplemod:steel_sword"},
        "addition": {"item": "minecraft:netherite_ingot"},
        "result": {"id": "examplemod:netherite_steel_sword"},
    }
    result = recipes.convert(_smithing_mod(tmp_path / "a", recipe))
    assert [p for p in result.files if p.startswith("items/")] == []
    block = {"examplemod:steel_sword": ("block", "blocks/steel_sword.json", {
        "format_version": "1.21.0",
        "minecraft:block": {"description": {"identifier": "examplemod:steel_sword"}, "components": {}}})}
    result = recipes.convert(_smithing_mod(tmp_path / "b", recipe), emitted=block)
    assert [p for p in result.files if p.startswith("items/")] == []
