"""#342: a refused recipe whose result is residue goes with it, and a recipe
refused only for the #302 expansion cap is the explained ``recipe_over_cap``.

Both are pending Alex (picks 1a, 2a on the PR). Neither changes pack bytes.
"""
import json
from pathlib import Path

import pytest

from portkit.agent.residue import SKIP_KINDS
from portkit.converters import recipes
from portkit.model import ConversionResult, SourceMod, Unhandled

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "tests" / "data" / "tag_reference"


@pytest.fixture
def reference(monkeypatch):
    monkeypatch.setenv("PORTKIT_TAG_REFERENCE", str(REFERENCE))
    return REFERENCE


def _mod(tmp_path, recipe, name="thing", tag_files=None):
    root = tmp_path / "mod"
    files = {f"data/examplemod/recipes/{name}.json": recipe, **(tag_files or {})}
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body))
    return SourceMod(root=root, namespace="examplemod", loader="forge", minecraft="1.20.1")


def _item(name):
    ident = f"examplemod:{name}"
    return {ident: ("item", f"items/{name}.json",
                    {"format_version": "1.20.10", "minecraft:item": {"description": {"identifier": ident}}})}


def _u(source, kind, reason="why"):
    return Unhandled(source=source, kind=kind, reason=reason)


def _shaped(pattern, key, result="examplemod:thing"):
    return {"type": "minecraft:crafting_shaped", "pattern": list(pattern), "key": key,
            "result": {"item": result}}


# -- the explained kind -----------------------------------------------------------
def test_recipe_over_cap_is_an_explained_kind():
    assert recipes.OVER_CAP == "recipe_over_cap" in SKIP_KINDS


def test_a_vanilla_tag_over_several_slots_past_the_cap_is_explained(tmp_path, reference):
    """forge:chests/wooden (chest, trapped chest) over 8 slots: 2^8 = 256 mixes."""
    recipe = _shaped(["GGG", "GSG", "GGG"], {"G": {"tag": "forge:chests/wooden"}, "S": {"item": "minecraft:stick"}})
    result = recipes.convert(_mod(tmp_path, recipe), emitted=_item("thing"))
    assert not [k for k in result.files if k.startswith("recipes/")]
    (u,) = result.unhandled
    assert u.kind == recipes.OVER_CAP
    assert "'forge:chests/wooden' (2 members) in 8 grid slots (2^8 mixes)" in u.reason
    assert "256 recipes" in u.reason and "over the 16" in u.reason
    assert "covers 2 items" in u.reason  # the ingredient's own reason is kept


def test_an_item_list_over_several_slots_stays_recipe(tmp_path, reference):
    """A list over several slots has no capped form (#302 pick 1 takes vanilla-only
    tags, not lists), so the cap isn't what refuses it."""
    dirt = [{"item": "minecraft:dirt"}, {"item": "minecraft:coarse_dirt"}, {"item": "minecraft:podzol"}]
    recipe = _shaped(["MMM", "M M", "MMM"], {"M": dirt})
    result = recipes.convert(_mod(tmp_path, recipe), emitted=_item("thing"))
    (u,) = result.unhandled
    assert u.kind == "recipe" and "filling 8 grid slots" in u.reason


def test_a_member_that_did_not_convert_keeps_it_recipe(tmp_path, reference):
    tag = {"data/examplemod/tags/items/rods.json": {"values": [f"examplemod:rod_{i}" for i in range(17)]}}
    recipe = {"type": "minecraft:crafting_shapeless", "ingredients": [{"tag": "examplemod:rods"}],
              "result": {"item": "examplemod:thing"}}
    emitted = {**_item("thing")}
    for i in range(16):  # rod_16 didn't convert
        emitted.update(_item(f"rod_{i}"))
    result = recipes.convert(_mod(tmp_path, recipe, tag_files=tag), emitted=emitted)
    (u,) = result.unhandled
    assert u.kind == "recipe" and "examplemod:rod_16" in u.reason


def test_at_the_cap_it_still_converts(tmp_path, reference):
    recipe = _shaped(["GG", "GG"], {"G": {"tag": "forge:chests/wooden"}})
    result = recipes.convert(_mod(tmp_path, recipe), emitted=_item("thing"))
    assert result.unhandled == []


# -- the result is residue ----------------------------------------------------------
def test_convert_records_every_recipes_result(tmp_path, reference):
    recipe = _shaped(["GGG", "GSG", "GGG"], {"G": {"tag": "forge:chests/wooden"}, "S": {"item": "minecraft:stick"}},
                     result="examplemod:iron_chest")
    result = recipes.convert(_mod(tmp_path, recipe), emitted={})
    (u,) = result.unhandled
    assert result.recipe_results[u.source] == "examplemod:iron_chest"


@pytest.mark.parametrize("spec, want", [
    ({"item": "examplemod:a"}, "examplemod:a"),
    ({"id": "examplemod:a", "count": 2}, "examplemod:a"),
    ("examplemod:a", "examplemod:a"),
    ({"item": "stick"}, "minecraft:stick"),
    ({"item": "#examplemod:rods"}, None),
    ({"count": 2}, None),
    (None, None),
])
def test_result_id_reads_every_java_shape(spec, want):
    assert recipes._result_id({"result": spec} if spec is not None else {}) == want


def test_a_refused_recipe_whose_result_is_residue_is_owned():
    unhandled = [
        _u("assets/ex/blockstates/iron_chest.json", "code_drawn_block", "only a particle texture"),
        _u("assets/ex/models/item/compass.json", "item", "a live reading"),
        _u("data/ex/recipes/chest.json", "recipe", "ingredient is a list of 3 items filling 8 grid slots"),
        _u("data/ex/recipes/upgrade.json", recipes.OVER_CAP, "18^4 mixes"),
        _u("data/ex/recipes/compass.json", "recipe", "ingredient uses tag 'saplings'"),
    ]
    results = {"data/ex/recipes/chest.json": "ex:iron_chest",
               "data/ex/recipes/upgrade.json": "ex:iron_chest",
               "data/ex/recipes/compass.json": "ex:compass"}
    out = {u.source: u for u in recipes.refine_owned(unhandled, {}, results)}
    for source in results:
        assert out[source].kind == "owned_by_residue", source
    assert "ex:iron_chest (assets/ex/blockstates/iron_chest.json: code_drawn_block)" in out["data/ex/recipes/chest.json"].reason
    # the original kind and reason are kept
    assert "recipe_over_cap: 18^4 mixes" in out["data/ex/recipes/upgrade.json"].reason
    assert "item" in out["data/ex/recipes/compass.json"].reason


def test_a_result_with_no_entry_of_its_own_or_a_vanilla_result_stays():
    unhandled = [
        _u("assets/ex/blockstates/iron_chest.json", "unowned"),  # not an owner
        _u("assets/minecraft/blockstates/chest.json", "block"),  # never counts
        _u("data/ex/recipes/a.json", "recipe"),
        _u("data/ex/recipes/b.json", "recipe"),
        _u("data/ex/recipes/c.json", recipes.OVER_CAP),
        _u("data/ex/recipes/d.json", "conditional_recipe"),  # Java doesn't load it: not ours
    ]
    results = {"data/ex/recipes/a.json": "ex:iron_chest", "data/ex/recipes/b.json": "minecraft:chest",
               "data/ex/recipes/c.json": "ex:shipped", "data/ex/recipes/d.json": "ex:iron_chest"}
    out = {u.source: u.kind for u in recipes.refine_owned(unhandled, {}, results)}
    assert out["data/ex/recipes/a.json"] == "recipe"
    assert out["data/ex/recipes/b.json"] == "recipe"
    assert out["data/ex/recipes/c.json"] == recipes.OVER_CAP
    assert out["data/ex/recipes/d.json"] == "conditional_recipe"


def test_a_result_the_pack_ships_under_that_id_stays():
    """A block refused while an item of the same id converted: Bedrock knows the result."""
    unhandled = [_u("assets/ex/blockstates/lamp.json", "block"), _u("data/ex/recipes/lamp.json", "recipe")]
    results = {"data/ex/recipes/lamp.json": "ex:lamp"}
    assert [u.kind for u in recipes.refine_owned(unhandled, {}, results, {"ex:lamp"})] == ["block", "recipe"]
    assert [u.kind for u in recipes.refine_owned(unhandled, {}, results, set())] == ["block", "owned_by_residue"]


def test_without_results_refine_owned_is_as_before():
    unhandled = [_u("assets/ex/blockstates/a.json", "block"), _u("data/ex/recipes/a.json", "recipe")]
    assert [u.kind for u in recipes.refine_owned(unhandled, {})] == ["block", "recipe"]


def test_merge_keeps_recipe_results():
    a, b = ConversionResult(), ConversionResult()
    a.recipe_results["x"] = "ex:a"
    b.recipe_results["y"] = "ex:b"
    assert a.merge(b).recipe_results == {"x": "ex:a", "y": "ex:b"}
