"""Recipe unlock data from the Java recipe advancement (#260)."""
import json

from portkit.converters import recipes
from portkit.converters.recipe_unlock import ALWAYS_UNLOCKED, advancement_index, criteria
from portkit.model import SourceMod

SHAPED = {
    "type": "minecraft:crafting_shaped",
    "pattern": ["WS"],
    "key": {"W": {"item": "examplemod:warp_stone"}, "S": {"item": "minecraft:stone"}},
    "result": {"item": "examplemod:waystone"},
}


def build(tmp_path, recipes_by_name, advancements=None, lane="recipe", adv_lane="advancement"):
    src = tmp_path / "data" / "examplemod" / lane
    src.mkdir(parents=True, exist_ok=True)
    for name, body in recipes_by_name.items():
        (src / f"{name}.json").parent.mkdir(parents=True, exist_ok=True)
        (src / f"{name}.json").write_text(json.dumps(body))
    for name, body in (advancements or {}).items():
        path = tmp_path / "data" / "examplemod" / adv_lane / "recipes" / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body))
    return SourceMod(root=tmp_path, namespace="examplemod")


def adv(recipe, criteria_, requirements="or"):
    body = {
        "parent": "minecraft:recipes/root",
        "criteria": {
            "has_the_recipe": {"trigger": "minecraft:recipe_unlocked", "conditions": {"recipe": recipe}},
            **criteria_,
        },
        "rewards": {"recipes": [recipe]},
    }
    if requirements == "or":
        body["requirements"] = [["has_the_recipe", *criteria_]]
    elif requirements is not None:
        body["requirements"] = requirements
    return body


def has(pred):
    return {"trigger": "minecraft:inventory_changed", "conditions": {"items": [pred]}}


def body_of(result, path):
    (key,) = [k for k in result.files[path] if k != "format_version"]
    return result.files[path][key]


def test_unlock_comes_from_the_recipe_advancement(tmp_path):
    mod = build(tmp_path, {"waystone": SHAPED}, {
        "waystone": adv("examplemod:waystone", {"has_warp_stone": has({"items": "examplemod:warp_stone"})}),
    })
    result = recipes.convert(mod)
    body = body_of(result, "recipes/waystone.json")
    assert body["unlock"] == [{"item": "examplemod:warp_stone"}]
    # Placed before the result, as vanilla writes it.
    assert list(body)[-2:] == ["unlock", "result"]
    assert "data/examplemod/advancement/recipes/waystone.json" in result.consumed


def test_no_advancement_falls_back_to_always_unlocked_with_a_note(tmp_path):
    result = recipes.convert(build(tmp_path, {"waystone": SHAPED}))
    assert body_of(result, "recipes/waystone.json")["unlock"] == ALWAYS_UNLOCKED
    assert any("no Java recipe advancement" in n and "AlwaysUnlocked (fallback)" in n for n in result.notes)


def test_an_item_neither_shipped_nor_in_the_recipe_is_dropped(tmp_path):
    # minecraft:ender_pearl is not in the recipe: a vanilla id we can't check
    # against Bedrock's item list, so it isn't written (#261).
    mod = build(tmp_path, {"waystone": SHAPED}, {
        "waystone": adv("examplemod:waystone", {
            "has_pearl": has({"items": ["minecraft:ender_pearl"]}),
            "has_stone": has({"items": ["minecraft:stone"]}),
        }),
    })
    body = body_of(recipes.convert(mod), "recipes/waystone.json")
    assert body["unlock"] == [{"item": "minecraft:stone"}]


def test_emitted_items_are_kept_even_outside_the_recipe(tmp_path):
    mod = build(tmp_path, {"waystone": SHAPED}, {
        "waystone": adv("examplemod:waystone", {"has_dust": has({"items": "examplemod:warp_dust"})}),
    })
    emitted = {"examplemod:warp_dust": ("item", "items/warp_dust.json", {})}
    body = body_of(recipes.convert(mod, emitted=emitted), "recipes/waystone.json")
    assert body["unlock"] == [{"item": "examplemod:warp_dust"}]


def test_nothing_expressible_falls_back_with_a_per_recipe_note(tmp_path):
    mod = build(tmp_path, {"waystone": SHAPED}, {
        "waystone": adv("examplemod:waystone", {
            "has_many": has({"items": "examplemod:warp_stone", "count": {"min": 4}}),
        }),
    })
    result = recipes.convert(mod)
    assert body_of(result, "recipes/waystone.json")["unlock"] == ALWAYS_UNLOCKED
    assert any("waystone.json: unlock AlwaysUnlocked (fallback)" in n and "beyond the item" in n
               for n in result.notes)


def test_an_and_of_criteria_is_not_used(tmp_path):
    mod = build(tmp_path, {"waystone": SHAPED}, {
        "waystone": adv("examplemod:waystone", {
            "has_a": has({"items": "examplemod:warp_stone"}),
            "has_b": has({"items": "minecraft:stone"}),
        }, requirements=[["has_the_recipe", "has_a"], ["has_the_recipe", "has_b"]]),
    })
    result = recipes.convert(mod)
    assert body_of(result, "recipes/waystone.json")["unlock"] == ALWAYS_UNLOCKED
    assert any("not one OR group" in n for n in result.notes)


def test_tag_criteria_old_item_key_and_hash_strings(tmp_path):
    shapeless = {
        "type": "minecraft:crafting_shapeless",
        "ingredients": [{"tag": "minecraft:planks"}, {"item": "examplemod:warp_stone"}],
        "result": {"item": "examplemod:sign"},
    }
    mod = build(tmp_path, {"sign": shapeless}, {
        "sign": adv("examplemod:sign", {
            "has_planks": has({"tag": "minecraft:planks"}),
            "has_stone": has({"item": "examplemod:warp_stone"}),
            "has_logs": has({"items": "#minecraft:logs"}),  # not in the recipe: dropped
        }),
    }, lane="recipes", adv_lane="advancements")
    body = body_of(recipes.convert(mod), "recipes/sign.json")
    assert body["unlock"] == [{"item": "examplemod:warp_stone"}, {"tag": "minecraft:planks"}]


def test_shared_advancement_and_nested_recipe_ids(tmp_path):
    shared = {
        "criteria": {"has_stone": has({"items": ["examplemod:warp_stone"]})},
        "rewards": {"recipes": ["examplemod:stones/a", "examplemod:stones/b"]},
    }  # no requirements: every criterion, here just one
    mod = build(tmp_path, {"stones/a": SHAPED, "stones/b": {**SHAPED, "result": {"item": "examplemod:other"}}},
                {"shared": shared})
    result = recipes.convert(mod)
    for name in ("a", "b"):
        assert body_of(result, f"recipes/{name}.json")["unlock"] == [{"item": "examplemod:warp_stone"}]


def test_furnace_recipes_take_no_unlock(tmp_path):
    mod = build(tmp_path, {"cook": {
        "type": "minecraft:smelting",
        "ingredient": {"item": "examplemod:root"},
        "result": {"item": "examplemod:cooked_root"},
    }})
    assert "unlock" not in body_of(recipes.convert(mod), "recipes/cook.json")


def test_index_and_criteria_read_namespace_less_ids(tmp_path):
    path = tmp_path / "data" / "other" / "advancements" / "x.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "criteria": {"has": has({"items": ["stick"]}), "tick": {"trigger": "minecraft:tick"}},
        "requirements": [["has", "tick"]],
        "rewards": {"recipes": ["torch"]},
    }))
    index = advancement_index(tmp_path)
    found = criteria(index["minecraft:torch"])
    assert found.items == ["minecraft:stick"]
    assert found.dropped == ["data/other/advancements/x.json#tick: minecraft:tick criterion is not one held item"]
