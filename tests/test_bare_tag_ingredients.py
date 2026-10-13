"""1.21.2+ bare-string ingredients (#194).

Since Minecraft 1.21.2 a recipe ingredient may be a bare string: ``"#c:crops/wheat"``
names a tag, ``"minecraft:stick"`` an item. The converter used to write every
string as ``{"item": spec}``, so a tag string became ``{"item": "#c:crops/wheat"}``:
neither a Bedrock tag ingredient nor an item, a recipe that ships and never
matches (66 Farmer's Delight Refabricated + 33 BetterEnd recipes).

A tag string now takes exactly the path ``{"tag": ...}`` takes, so each case is
checked as "the bare form converts the same as the object form". Runs offline
against tests/data/tag_reference (PORTKIT_TAG_REFERENCE).
"""
import json
import shutil
from pathlib import Path

import pytest

from portkit.conditions import LoadContext
from portkit.converters import recipes
from portkit.model import SourceMod
from portkit.pipeline import convert
from portkit.validate import validate_tree

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "tests" / "data" / "tag_reference"


@pytest.fixture
def reference(monkeypatch):
    monkeypatch.setenv("PORTKIT_TAG_REFERENCE", str(REFERENCE))
    return REFERENCE


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body))


def _mod(root: Path, recipe, *, loader="forge", minecraft="1.20.1", tag_files=None, name="thing",
         mods=None):
    lane = "recipe" if loader in ("neoforge", "fabric") else "recipes"
    _write(root, f"data/examplemod/{lane}/{name}.json", recipe)
    for rel, values in (tag_files or {}).items():
        _write(root, rel, {"values": values})
    return SourceMod(root=root, namespace="examplemod", loader=loader, minecraft=minecraft,
                     mods=None if mods is None else {m: "1.0" for m in mods},
                     requires=None if mods is None else frozenset())


def _emitted(*items):
    found = {}
    for name in items:
        ident = f"examplemod:{name}"
        body = {"format_version": "1.20.10",
                "minecraft:item": {"description": {"identifier": ident}, "components": {}}}
        found[ident] = ("item", f"items/{name}.json", body)
    return found


def _bare(spec):
    """The recipe with every ``{"tag": t}`` ingredient written as ``"#t"``."""
    if isinstance(spec, dict) and set(spec) == {"tag"}:
        return "#" + spec["tag"]
    if isinstance(spec, dict):
        return {k: _bare(v) for k, v in spec.items()}
    if isinstance(spec, list):
        return [_bare(v) for v in spec]
    return spec


def _outcome(result):
    return (result.files,
            [(u.source.rsplit("/", 1)[-1], u.kind, u.reason) for u in result.unhandled],
            result.notes)


def _both(tmp_path, recipe, emitted=None, **kw):
    """(object-form result, bare-form result) for the same recipe."""
    obj = recipes.convert(_mod(tmp_path / "obj", recipe, **kw), emitted=emitted)
    bare = recipes.convert(_mod(tmp_path / "bare", _bare(recipe), **kw), emitted=emitted)
    return obj, bare


def _no_hash_items(files):
    text = json.dumps(files)
    assert '"item": "#' not in text
    for slot in ("input", "template", "base", "addition"):
        assert f'"{slot}": "#' not in text


def _shaped(key, pattern=("GGG",), result="examplemod:thing"):
    return {"type": "minecraft:crafting_shaped", "pattern": list(pattern), "key": key,
            "result": {"id": result}}


def _shapeless(*ingredients, result="examplemod:thing"):
    return {"type": "minecraft:crafting_shapeless", "ingredients": list(ingredients),
            "result": {"id": result}}


# -- every tag path: bare == object ---------------------------------------------

CASES = {
    # Bedrock has minecraft:planks itself and the mod adds nothing: pass-through.
    "pass_through": dict(recipe=_shaped({"G": {"tag": "minecraft:planks"}})),
    # A loader tag with one vanilla member resolves to that item.
    "single_member": dict(recipe=_shapeless({"tag": "forge:rods/wooden"})),
    # A 1.21 convention tag, as FD Refabricated's apple pie uses it.
    "single_member_neoforge": dict(recipe=_shaped({"#": {"tag": "c:crops/wheat"}}, ("###",)),
                                   loader="neoforge", minecraft="1.21.1"),
    # Two vanilla members in one slot: one recipe per member.
    "per_member": dict(recipe=_shapeless({"tag": "forge:chests/wooden"}, "minecraft:stick")),
    "per_member_furnace": dict(recipe={"type": "minecraft:smelting",
                                       "ingredient": {"tag": "forge:chests/wooden"},
                                       "result": "examplemod:thing", "experience": 0.1}),
    # Same members as Bedrock's planks: the recipe takes Bedrock's tag.
    "bedrock_equivalent": dict(recipe=_shaped({"G": {"tag": "forge:planks_alias"}})),
    # Every member is an emitted item: a native tag the items carry.
    "native_tag": dict(recipe=_shaped({"G": {"tag": "examplemod:alloys"}}, ("GGG", "GGG", "GGG")),
                       tag_files={"data/examplemod/tags/items/alloys.json":
                                  ["examplemod:bronze", "examplemod:steel"]},
                       emitted=_emitted("bronze", "steel")),
    # A vanilla member beside the mod's own: tag recipe + one per vanilla member.
    "native_with_extras": dict(recipe=_shapeless({"tag": "examplemod:rods"}),
                               tag_files={"data/examplemod/tags/items/rods.json":
                                          ["examplemod:a", "examplemod:b", "minecraft:stick"]},
                               emitted=_emitted("a", "b")),
    # Residue: a member this conversion did not emit, named in the reason.
    "member_not_emitted": dict(recipe=_shaped({"G": {"tag": "examplemod:alloys"}}),
                               tag_files={"data/examplemod/tags/items/alloys.json":
                                          ["examplemod:bronze", "examplemod:tin"]},
                               emitted=_emitted("bronze")),
    # Residue: a multi-member tag filling several slots.
    "several_slots": dict(recipe=_shaped({"G": {"tag": "forge:chests/wooden"}}, ("G G",))),
    # Residue: a tag nobody defines.
    "unknown_tag": dict(recipe=_shapeless({"tag": "wover:water_bottles"})),
    # Smithing: a multi-member addition has no Bedrock form (residue); a
    # one-member one resolves to its item.
    "smithing_multi": dict(recipe={"type": "minecraft:smithing_transform",
                                   "template": "minecraft:netherite_upgrade_smithing_template",
                                   "base": "minecraft:diamond_boots",
                                   "addition": {"tag": "forge:chests/wooden"},
                                   "result": {"id": "examplemod:boots"}}),
    "smithing_single": dict(recipe={"type": "minecraft:smithing_transform",
                                    "template": "minecraft:netherite_upgrade_smithing_template",
                                    "base": "minecraft:diamond_boots",
                                    "addition": {"tag": "forge:dyes/red"},
                                    "result": {"id": "examplemod:boots"}}),
    # Lists: a tag entry keeps a list residue either way.
    "list_with_tag": dict(recipe=_shapeless([{"tag": "forge:rods/wooden"}, "minecraft:blaze_rod"])),
    "one_entry_tag_list": dict(recipe=_shapeless([{"tag": "forge:rods/wooden"}])),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_bare_tag_converts_like_the_object_form(tmp_path, reference, case):
    spec = dict(CASES[case])
    obj, bare = _both(tmp_path, spec.pop("recipe"), emitted=spec.pop("emitted", {}), **spec)
    assert _outcome(bare) == _outcome(obj)
    _no_hash_items(bare.files)


def test_apple_pie_takes_wheat_not_a_hash_item(tmp_path, reference):
    """FD Refabricated data/farmersdelight/recipe/apple_pie.json, trimmed."""
    recipe = {"type": "minecraft:crafting_shaped", "pattern": ["###", "aaa", "xOx"],
              "key": {"#": "#c:crops/wheat", "a": "minecraft:apple", "x": "minecraft:sugar",
                      "O": "examplemod:pie_crust"},
              "result": {"id": "examplemod:apple_pie"}}
    mod = _mod(tmp_path, recipe, loader="neoforge", minecraft="1.21.1", name="apple_pie")
    result = recipes.convert(mod, emitted=_emitted("pie_crust", "apple_pie"))
    key = result.files["recipes/apple_pie.json"]["minecraft:recipe_shaped"]["key"]
    assert key == {"#": {"item": "minecraft:wheat"}, "a": {"item": "minecraft:apple"},
                   "x": {"item": "minecraft:sugar"}, "O": {"item": "examplemod:pie_crust"}}


def test_bare_items_and_tags_mixed_in_one_recipe(tmp_path, reference):
    recipe = _shapeless("minecraft:bowl", "#c:foods/vegetable", "examplemod:rice")
    mod = _mod(tmp_path, recipe, loader="neoforge", minecraft="1.21.1")
    result = recipes.convert(mod, emitted=_emitted("rice", "thing"))
    files = {k: v["minecraft:recipe_shapeless"]["ingredients"] for k, v in result.files.items()
             if k.startswith("recipes/")}
    assert files == {
        "recipes/thing__minecraft_carrot.json":
            [{"item": "minecraft:bowl"}, {"item": "minecraft:carrot"}, {"item": "examplemod:rice"}],
        "recipes/thing__minecraft_potato.json":
            [{"item": "minecraft:bowl"}, {"item": "minecraft:potato"}, {"item": "examplemod:rice"}],
    }


def test_a_bare_item_string_is_the_item(tmp_path):
    result = recipes.convert(_mod(tmp_path, _shapeless("minecraft:stick", "examplemod:gem")), emitted={})
    body = result.files["recipes/thing.json"]["minecraft:recipe_shapeless"]
    assert body["ingredients"] == [{"item": "minecraft:stick"}, {"item": "examplemod:gem"}]


def test_a_bare_item_list_still_expands(tmp_path):
    result = recipes.convert(_mod(tmp_path, _shapeless(["minecraft:coal", "minecraft:charcoal"])), emitted={})
    assert sorted(k for k in result.files if k.startswith("recipes/")) == [
        "recipes/thing__minecraft_charcoal.json", "recipes/thing__minecraft_coal.json"]


def test_a_bare_furnace_tag_is_never_an_input_id(tmp_path):
    """Without tag data the furnace recipe is residue, not ``"input": "#..."``."""
    recipe = {"type": "minecraft:smelting", "ingredient": "#minecraft:eggs",
              "result": "examplemod:fried_egg"}
    result = recipes.convert(_mod(tmp_path, recipe, loader="neoforge", minecraft="1.21.1"), emitted={})
    assert not [k for k in result.files if k.startswith("recipes/")]
    (reason,) = [u.reason for u in result.unhandled if u.kind == "recipe"]
    assert "minecraft:eggs" in reason


# -- load conditions decide first, then the tag path ----------------------------

def test_load_conditions_gate_a_bare_tag_recipe(tmp_path, reference):
    recipe = {**_shaped({"#": "#c:crops/wheat"}, ("###",)),
              "neoforge:conditions": [{"type": "neoforge:mod_loaded", "modid": "create"}]}
    absent = _mod(tmp_path / "a", recipe, loader="neoforge", minecraft="1.21.1", mods=["examplemod"])
    result = recipes.convert(absent, context=LoadContext(absent))
    assert "recipes/thing.json" not in result.files
    assert [u.reason for u in result.unhandled if u.kind == "conditional_recipe"][0].startswith(
        "compat for create:")

    loaded = _mod(tmp_path / "b", recipe, loader="neoforge", minecraft="1.21.1",
                  mods=["examplemod", "create"])
    result = recipes.convert(loaded, context=LoadContext(loaded))
    key = result.files["recipes/thing.json"]["minecraft:recipe_shaped"]["key"]
    assert key == {"#": {"item": "minecraft:wheat"}}


# -- the validator never lets a '#' item through ---------------------------------

def test_the_validator_flags_a_hash_item(tmp_path, fixtures_dir):
    src = tmp_path / "src"
    shutil.copytree(fixtures_dir / "agent_mod" / "input", src)
    result = convert(src, tmp_path / "out", emit_addon=False)
    path = next((result.tree / "behavior_pack" / "recipes").glob("*.json"))
    body = json.loads(path.read_text())
    (key,) = [k for k in body if k.startswith("minecraft:recipe_")]
    recipe = body[key]
    if "key" in recipe:
        recipe["key"][next(iter(recipe["key"]))] = {"item": "#c:crops/wheat"}
    else:
        recipe["ingredients"] = [{"item": "#c:crops/wheat"}]
    path.write_text(json.dumps(body))
    report = validate_tree(result.tree)
    found = [f for f in report.findings if f.rule == "xref.item_tag"]
    assert found and found[0].severity == "error"
    assert "c:crops/wheat" in found[0].message
    assert not [f for f in report.findings if f.rule == "xref.item" and "#c:" in f.message]
