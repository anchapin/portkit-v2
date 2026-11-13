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


def _mod(tmp_path, recipe, name="thing", tags=None, items=()):
    root = tmp_path / "mod"
    _write(root, f"data/examplemod/recipe/{name}.json", recipe)
    for tag, values in (tags or {}).items():
        _write(root, f"data/examplemod/tags/items/{tag}.json", {"values": values})
    for item in items:
        _write(root, f"assets/examplemod/models/item/{item}.json", {"parent": "minecraft:item/generated"})
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


def test_list_filling_several_slots_writes_one_recipe_per_combination(tmp_path):
    """#302 sub-reason 4: a list over several slots is written once per mix.

    The player may put a different item of the list in each slot, so a recipe
    per item would forbid it; a recipe per combination of the items over the
    slots is exact, under the same cap and the same rules as a vanilla-only
    tag's combinations (#302 pick 1)."""
    recipe = {"type": "minecraft:crafting_shaped", "pattern": ["BPB"],
              "key": {"B": ["examplemod:a", "examplemod:b"], "P": "minecraft:sugar"},
              "result": {"id": "examplemod:pie"}}
    result = recipes.convert(_mod(tmp_path, recipe), _emitted("a", "b", "pie"))
    files = _recipes(result)
    # (a, a), (a, b) and (b, b): the mirror image of (a, b) is written once.
    assert sorted(files) == [
        "recipes/thing__examplemod_a__examplemod_a.json",
        "recipes/thing__examplemod_a__examplemod_b.json",
        "recipes/thing__examplemod_b__examplemod_b.json",
    ]
    mixed = files["recipes/thing__examplemod_a__examplemod_b.json"]["minecraft:recipe_shaped"]
    assert mixed["pattern"] == ["APC"]
    assert mixed["key"] == {"A": {"item": "examplemod:a"},
                             "C": {"item": "examplemod:b"},
                             "P": {"item": "minecraft:sugar"}}
    same = files["recipes/thing__examplemod_a__examplemod_a.json"]["minecraft:recipe_shaped"]
    assert same["pattern"] == ["BPB"]
    assert same["key"] == {"B": {"item": "examplemod:a"}, "P": {"item": "minecraft:sugar"}}
    assert not _reasons(result)
    assert any("combination" in n for n in result.notes)


def test_list_over_several_slots_over_the_cap_stays_residue(tmp_path):
    """The per-combination form is capped like every other expansion (#302)."""
    recipe = {"type": "minecraft:crafting_shaped", "pattern": ["BB"],
              "key": {"B": ["examplemod:a", "examplemod:b", "examplemod:c", "examplemod:d",
                           "examplemod:e"]},
              "result": {"id": "examplemod:pie"}}
    result = recipes.convert(_mod(tmp_path, recipe), _emitted(*"abcde", "pie"))
    assert not _recipes(result)
    (u,) = result.unhandled
    assert u.kind == recipes.OVER_CAP
    assert "25 recipes" in u.reason and "over the 16" in u.reason
    assert "filling 2 grid slots" in u.reason


def test_list_mixing_item_and_tag_entries_is_their_union(tmp_path):
    """#302 sub-reason 4: a list may name a tag as well as items."""
    recipe = {"type": "minecraft:crafting_shapeless",
              "ingredients": [[{"item": "minecraft:coal"}, {"tag": "examplemod:ores"}]],
              "result": {"id": "examplemod:slag"}}
    mod = _mod(tmp_path, recipe, name="slag")
    tag = mod.root / "data/examplemod/tags/items/ores.json"
    tag.parent.mkdir(parents=True, exist_ok=True)
    tag.write_text(json.dumps({"values": ["examplemod:tin_ore"]}))
    result = recipes.convert(mod, _emitted("tin_ore", "slag"))
    files = _recipes(result)
    assert sorted(files) == ["recipes/slag__examplemod_tin_ore.json",
                             "recipes/slag__minecraft_coal.json"]
    body = files["recipes/slag__minecraft_coal.json"]["minecraft:recipe_shapeless"]
    assert body["ingredients"] == [{"item": "minecraft:coal"}]
    assert not _reasons(result)


def test_list_holding_a_tag_whose_membership_is_unknown_stays_residue(tmp_path):
    """The membership of a tag the jar doesn't know can't be written down."""
    recipe = {"type": "minecraft:crafting_shapeless",
              "ingredients": [[{"item": "minecraft:coal"}, {"tag": "c:ores/tin"}]],
              "result": {"id": "examplemod:slag"}}
    result = recipes.convert(_mod(tmp_path, recipe), _emitted("slag"))
    assert not _recipes(result)
    (reason,) = _reasons(result)
    assert "list holding a tag" in reason


def test_a_list_whose_every_item_did_not_convert_goes_with_them(tmp_path):
    """#302 pick 3 for lists: the recipe can't match anything until its items do."""
    recipe = {"type": "minecraft:crafting_shapeless",
              "ingredients": [["examplemod:red_ore", "examplemod:blue_ore"]],
              "result": {"id": "examplemod:slag"}}
    result = recipes.convert(_mod(tmp_path, recipe), _emitted("slag"))
    assert not _recipes(result)
    (u,) = result.unhandled
    assert u.kind == "recipe"
    assert result.unshipped_names[u.source] == ["examplemod:blue_ore", "examplemod:red_ore"]
    residue = [recipes.Unhandled("assets/examplemod/blockstates/red_ore.json", "block", "why"),
               recipes.Unhandled("assets/examplemod/blockstates/blue_ore.json", "code_drawn_block",
                                 "why"),
               u]
    (owned,) = [x for x in recipes.refine_owned(residue, result.unshipped_names)
                if x.source == u.source]
    assert owned.kind == "owned_by_residue"
    assert u.reason in owned.reason


def test_two_item_lists_in_different_slots_write_one_recipe_per_combination(tmp_path):
    """#302 sub-reason 4: two lists in different slots are written once per mix.

    The player may put any item of either list in its own slot, so a recipe
    per item would forbid it; a recipe per combination of the two lists is
    exact, under the same cap and the same rules as a vanilla-only tag's
    combinations (#302 pick 1)."""
    recipe = {"type": "minecraft:crafting_shapeless",
              "ingredients": [["examplemod:a", "examplemod:b"], ["examplemod:c", "examplemod:d"]],
              "result": {"id": "examplemod:thing"}}
    result = recipes.convert(_mod(tmp_path, recipe), _emitted("a", "b", "c", "d", "thing"))
    files = _recipes(result)
    assert sorted(files) == [
        "recipes/thing__examplemod_a__examplemod_c.json",
        "recipes/thing__examplemod_a__examplemod_d.json",
        "recipes/thing__examplemod_b__examplemod_c.json",
        "recipes/thing__examplemod_b__examplemod_d.json",
    ]
    body = files["recipes/thing__examplemod_a__examplemod_c.json"]["minecraft:recipe_shapeless"]
    assert body["ingredients"] == [{"item": "examplemod:a"}, {"item": "examplemod:c"}]
    assert not _reasons(result)
    assert any("combination" in n for n in result.notes)


def test_two_item_lists_in_a_shaped_grid_write_one_recipe_per_combination(tmp_path):
    """#302 sub-reason 4: the same in a shaped grid, one list over two slots.

    The list over the two slots may hold a different item in each, so the
    combinations are the mixes of both lists (2 over one slot, 2 over two:
    eight recipes)."""
    recipe = {"type": "minecraft:crafting_shaped", "pattern": ["ABB"],
              "key": {"A": ["examplemod:a", "examplemod:b"], "B": ["examplemod:c", "examplemod:d"]},
              "result": {"id": "examplemod:thing"}}
    result = recipes.convert(_mod(tmp_path, recipe), _emitted("a", "b", "c", "d", "thing"))
    files = _recipes(result)
    assert len(files) == 8
    mixed = files["recipes/thing__examplemod_a__examplemod_c__examplemod_d.json"]["minecraft:recipe_shaped"]
    assert mixed["pattern"] == ["ACD"]
    assert mixed["key"] == {"A": {"item": "examplemod:a"},
                             "C": {"item": "examplemod:c"},
                             "D": {"item": "examplemod:d"}}
    same = files["recipes/thing__examplemod_a__examplemod_c__examplemod_c.json"]["minecraft:recipe_shaped"]
    assert same["pattern"] == ["ABB"]
    assert same["key"] == {"A": {"item": "examplemod:a"}, "B": {"item": "examplemod:c"}}
    assert not _reasons(result)


def test_a_list_beside_a_multi_member_tag_writes_one_recipe_per_combination(tmp_path):
    """#302 sub-reason 4: a list beside a multi-member tag, one of each.

    The tag holds only vanilla items, which an add-on can't tag, so it is
    written out member by member, and the list beside it is written out too:
    one recipe per combination of the two (#302 pick 1)."""
    recipe = {"type": "minecraft:crafting_shapeless",
              "ingredients": [["examplemod:a", "examplemod:b"], {"tag": "examplemod:coals"}],
              "result": {"id": "examplemod:thing"}}
    result = recipes.convert(
        _mod(tmp_path, recipe, tags={"coals": ["minecraft:coal", "minecraft:charcoal"]}),
        _emitted("a", "b", "thing"))
    files = _recipes(result)
    assert sorted(files) == [
        "recipes/thing__examplemod_a__charcoal.json",
        "recipes/thing__examplemod_a__coal.json",
        "recipes/thing__examplemod_b__charcoal.json",
        "recipes/thing__examplemod_b__coal.json",
    ]
    body = files["recipes/thing__examplemod_a__coal.json"]["minecraft:recipe_shapeless"]
    assert body["ingredients"] == [{"item": "examplemod:a"}, {"item": "minecraft:coal"}]
    assert not _reasons(result)


def test_a_list_beside_a_tag_of_this_mod_writes_one_recipe_per_combination(tmp_path):
    """#302 sub-reason 4: a list beside a tag this mod's own member carries.

    The tag's own member carries the tag, so the recipe takes the tag; the
    vanilla member of the tag can't carry it and gets a value of its own, so
    the combinations are the list's items times the tag and that member."""
    recipe = {"type": "minecraft:crafting_shapeless",
              "ingredients": [["examplemod:a", "examplemod:b"], {"tag": "examplemod:mixed"}],
              "result": {"id": "examplemod:thing"}}
    result = recipes.convert(
        _mod(tmp_path, recipe, tags={"mixed": ["examplemod:x", "minecraft:coal"]}, items=["x"]),
        _emitted("a", "b", "x", "thing"))
    files = _recipes(result)
    assert sorted(files) == [
        "recipes/thing__examplemod_a__coal.json",
        "recipes/thing__examplemod_a__examplemod_mixed.json",
        "recipes/thing__examplemod_b__coal.json",
        "recipes/thing__examplemod_b__examplemod_mixed.json",
    ]
    tagged = files["recipes/thing__examplemod_a__examplemod_mixed.json"]["minecraft:recipe_shapeless"]
    assert tagged["ingredients"] == [{"item": "examplemod:a"}, {"tag": "examplemod:mixed"}]
    plain = files["recipes/thing__examplemod_a__coal.json"]["minecraft:recipe_shapeless"]
    assert plain["ingredients"] == [{"item": "examplemod:a"}, {"item": "minecraft:coal"}]
    # The tag is written, so the recipe that takes it matches.
    item = result.files["items/x.json"]["minecraft:item"]["components"]
    assert item["minecraft:tags"] == {"tags": ["examplemod:mixed"]}
    assert not _reasons(result)


def test_the_combinations_over_the_cap_stay_residue_with_their_count(tmp_path):
    """#302 sub-reason 4: the combinations are capped like every other expansion.

    Four items in one slot and five in another are 20 combinations, over
    :data:`EXPANSION_CAP`, so the recipe stays residue and says how many it
    would take."""
    recipe = {"type": "minecraft:crafting_shapeless",
              "ingredients": [["examplemod:a", "examplemod:b", "examplemod:c", "examplemod:d"],
                              ["examplemod:e", "examplemod:f", "examplemod:g", "examplemod:h",
                               "examplemod:i"]],
              "result": {"id": "examplemod:thing"}}
    result = recipes.convert(_mod(tmp_path, recipe), _emitted(*"abcdefghi", "thing"))
    assert not _recipes(result)
    (u,) = result.unhandled
    assert u.kind == recipes.OVER_CAP
    assert "20 recipes" in u.reason and "over the 16" in u.reason
    assert "one recipe per combination" in u.reason


def test_a_single_list_beside_a_plain_item_is_written_once_per_item(tmp_path):
    """One multi-item ingredient on its own keeps the one-recipe-per-item form."""
    recipe = {"type": "minecraft:crafting_shapeless",
              "ingredients": [["examplemod:a", "examplemod:b"], {"item": "minecraft:stick"}],
              "result": {"id": "examplemod:thing"}}
    result = recipes.convert(_mod(tmp_path, recipe), _emitted("a", "b", "thing"))
    files = _recipes(result)
    assert sorted(files) == ["recipes/thing__examplemod_a.json", "recipes/thing__examplemod_b.json"]
    body = files["recipes/thing__examplemod_a.json"]["minecraft:recipe_shapeless"]
    assert body["ingredients"] == [{"item": "examplemod:a"}, {"item": "minecraft:stick"}]
    assert not _reasons(result)


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
    # #342 (pending Alex, pick 2a): only the cap refuses it, so it is explained.
    (u,) = result.unhandled
    assert u.kind == recipes.OVER_CAP
    assert f"more than the {recipes.EXPANSION_CAP}" in u.reason and "17 recipes" in u.reason


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
