"""#302: bare recipe types, and recipes whose items are residue of their own."""
import json

import pytest

from portkit.converters import recipes
from portkit.model import ConversionResult, SourceMod, Unhandled


def build(tmp_path, name, body):
    src = tmp_path / "data" / "examplemod" / "recipes"
    src.mkdir(parents=True, exist_ok=True)
    (src / f"{name}.json").write_text(json.dumps(body))
    return SourceMod(root=tmp_path, namespace="examplemod")


SHAPED = {
    "pattern": ["##", "##"],
    "key": {"#": {"item": "examplemod:black_sand"}},
    "result": {"item": "examplemod:black_sandstone"},
}


@pytest.mark.parametrize("bare, body_key", [
    ("crafting_shaped", "minecraft:recipe_shaped"),
    ("crafting_shapeless", "minecraft:recipe_shapeless"),
    ("smelting", "minecraft:recipe_furnace"),
])
def test_a_bare_type_is_read_as_minecraft(tmp_path, bare, body_key):
    """Java reads "crafting_shaped" as minecraft:crafting_shaped (ResourceLocation's
    default namespace); Biomes O' Plenty writes its recipes that way."""
    if bare == "crafting_shaped":
        body = {"type": bare, **SHAPED}
    elif bare == "crafting_shapeless":
        body = {"type": bare, "ingredients": [{"item": "examplemod:black_sand"}],
                "result": {"item": "examplemod:black_sandstone"}}
    else:
        body = {"type": bare, "ingredient": {"item": "examplemod:black_sand"},
                "result": "examplemod:black_glass"}
    result = recipes.convert(build(tmp_path, "black_sandstone", body))
    assert result.unhandled == [], [u.reason for u in result.unhandled]
    (written,) = result.files.values()
    assert body_key in written


def test_a_bare_unknown_type_is_refused_under_its_java_name(tmp_path):
    result = recipes.convert(build(tmp_path, "odd", {"type": "sawmill", **SHAPED}))
    (u,) = result.unhandled
    assert u.kind == "recipe" and "'minecraft:sawmill'" in u.reason


def test_with_namespaced_type_leaves_namespaced_and_odd_types_alone():
    assert recipes.with_namespaced_type({"type": "mod:thing"})["type"] == "mod:thing"
    assert recipes.with_namespaced_type({"type": "Not Valid"})["type"] == "Not Valid"
    assert recipes.with_namespaced_type({"type": 3})["type"] == 3
    assert "type" not in recipes.with_namespaced_type({})


def _u(source, kind, reason="why"):
    return Unhandled(source=source, kind=kind, reason=reason)


def test_a_recipe_whose_unshipped_items_are_all_residue_is_owned_by_residue():
    unhandled = [
        _u("assets/ex/blockstates/portal.json", "block", "three blockstate variants"),
        _u("assets/ex/models/item/rod.json", "item", "item model stacks 2 texture layers"),
        _u("data/ex/recipes/portal.json", "recipe", "names ex:portal, ex:rod, which the pack doesn't ship"),
        _u("data/ex/recipes/ghost.json", "recipe", "names ex:ghost, which the pack doesn't ship"),
        _u("data/ex/recipes/mixed.json", "recipe", "names ex:portal, other:gear, which the pack doesn't ship"),
        _u("data/ex/recipes/tagged.json", "recipe", "ingredient uses tag 'ex:rods', which covers 2 items"),
    ]
    unshipped = {
        "data/ex/recipes/portal.json": ["ex:portal", "ex:rod"],
        "data/ex/recipes/ghost.json": ["ex:ghost"],
        "data/ex/recipes/mixed.json": ["ex:portal", "other:gear"],
    }
    out = recipes.refine_owned(unhandled, unshipped)
    kinds = {u.source: u.kind for u in out}
    assert kinds["data/ex/recipes/portal.json"] == "owned_by_residue"
    # An item with no entry of its own (never defined in the jar, another mod's)
    # leaves the recipe a converter gap.
    assert kinds["data/ex/recipes/ghost.json"] == "recipe"
    assert kinds["data/ex/recipes/mixed.json"] == "recipe"
    # Only recipes drop_unshipped_recipes withdrew are considered.
    assert kinds["data/ex/recipes/tagged.json"] == "recipe"
    portal = next(u for u in out if u.source == "data/ex/recipes/portal.json")
    assert "assets/ex/blockstates/portal.json: block" in portal.reason
    assert "assets/ex/models/item/rod.json: item" in portal.reason
    assert "which the pack doesn't ship" in portal.reason  # the original reason is kept
    assert len(out) == len(unhandled)


def test_an_unowned_model_is_not_an_owner():
    unhandled = [
        _u("assets/ex/models/item/rod.json", "unowned"),
        _u("data/ex/recipes/rod.json", "recipe"),
    ]
    out = recipes.refine_owned(unhandled, {"data/ex/recipes/rod.json": ["ex:rod"]})
    assert out[1].kind == "recipe"


def test_drop_unshipped_recipes_records_every_unshipped_item():
    result = ConversionResult()
    result.files["recipes/a.json"] = {"format_version": "1.20.10", "minecraft:recipe_shapeless": {
        "description": {"identifier": "ex:a"}, "tags": ["crafting_table"],
        "ingredients": [{"item": f"ex:part_{i}"} for i in range(7)],
        "result": {"item": "ex:a"}}}
    result.recipe_sources["recipes/a.json"] = "data/ex/recipes/a.json"
    recipes.drop_unshipped_recipes(result)
    (u,) = result.unhandled
    assert "and 3 more" in u.reason  # the reason shortens the list
    assert result.unshipped_names["data/ex/recipes/a.json"] == sorted(
        ["ex:a"] + [f"ex:part_{i}" for i in range(7)])


def _tag_mod(tmp_path, recipe, members):
    root = tmp_path / "mod"
    for rel, body in (("data/examplemod/recipes/thing.json", recipe),
                      ("data/examplemod/tags/items/flowers.json", {"values": members})):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body))
    return SourceMod(root=root, namespace="examplemod", loader="forge", minecraft="1.20.1")


TAGGED = {"type": "minecraft:crafting_shapeless",
          "ingredients": [{"tag": "examplemod:flowers"}, {"item": "minecraft:stick"}],
          "result": {"item": "examplemod:wand"}}


def test_a_tag_whose_every_member_did_not_convert_records_them(tmp_path):
    """#302 pick 3: the members go to refine_owned like unshipped items do."""
    mod = _tag_mod(tmp_path, TAGGED, ["examplemod:red_flower", "examplemod:blue_flower"])
    result = recipes.convert(mod, emitted={})
    (u,) = result.unhandled
    assert u.kind == "recipe"
    assert result.unshipped_names[u.source] == ["examplemod:blue_flower", "examplemod:red_flower"]
    residue = [_u("assets/examplemod/blockstates/red_flower.json", "block"),
               _u("assets/examplemod/blockstates/blue_flower.json", "code_drawn_block"), u]
    (owned,) = [x for x in recipes.refine_owned(residue, result.unshipped_names) if x.source == u.source]
    assert owned.kind == "owned_by_residue"
    assert u.reason in owned.reason  # the original reason is kept
    assert "examplemod:red_flower" in owned.reason


def test_a_tag_with_a_member_that_converted_or_a_vanilla_one_is_not_recorded(tmp_path):
    emitted = {"examplemod:red_flower": ("item", "items/red_flower.json",
                                         {"minecraft:item": {"description": {"identifier": "examplemod:red_flower"}}})}
    mod = _tag_mod(tmp_path, TAGGED, ["examplemod:red_flower", "examplemod:blue_flower"])
    result = recipes.convert(mod, emitted=emitted)
    assert [u.kind for u in result.unhandled] == ["recipe"] and result.unshipped_names == {}
    mod = _tag_mod(tmp_path / "b", TAGGED, ["minecraft:poppy", "minecraft:dandelion", "examplemod:blue_flower"])
    result = recipes.convert(mod, emitted={})
    assert [u.kind for u in result.unhandled] == ["recipe"] and result.unshipped_names == {}


def test_one_member_without_an_entry_of_its_own_keeps_it_recipe(tmp_path):
    mod = _tag_mod(tmp_path, TAGGED, ["examplemod:red_flower", "examplemod:blue_flower"])
    result = recipes.convert(mod, emitted={})
    (u,) = result.unhandled
    residue = [_u("assets/examplemod/blockstates/red_flower.json", "block"), u]
    out = recipes.refine_owned(residue, result.unshipped_names)
    assert [x.kind for x in out if x.source == u.source] == ["recipe"]


def test_merge_keeps_unshipped_names():
    a, b = ConversionResult(), ConversionResult()
    a.unshipped_names["x"] = ["ex:a"]
    b.unshipped_names["y"] = ["ex:b"]
    assert a.merge(b).unshipped_names == {"x": ["ex:a"], "y": ["ex:b"]}
