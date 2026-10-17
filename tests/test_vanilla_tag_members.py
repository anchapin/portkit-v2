"""A mod's own members of a vanilla tag Bedrock also has (minecraft:planks).

Bedrock's ``minecraft:planks`` holds vanilla's planks only. Passing a Java
recipe's ``minecraft:planks`` straight through dropped the planks the mod adds
to that tag (Silent Gear's netherwood planks, Tinkers' four woods). Now each of
the mod's members carries Bedrock's tag: an item in ``minecraft:tags``, a block
through an item that replaces the block's own item and carries the tag (the
pattern vanilla's shelf_mushroom uses for ``minecraft:mushrooms_for_stew``).
When a member can't, a single-slot ingredient keeps the tag recipe and gets one
recipe per mod member; anything else stays residue. Never narrowed (#87).

Runs offline against tests/data/tag_reference, whose vanilla-1.20.1
``minecraft:planks`` is oak and spruce planks.
"""
import json
import shutil
from pathlib import Path

import pytest

from portkit.converters import recipes
from portkit.model import ConversionResult, SourceMod
from portkit.pipeline import convert, drop_untextured
from portkit.validate import validate_tree

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "tests" / "data" / "tag_reference"
PLANKS = "data/minecraft/tags/items/planks.json"
TOML = '[[mods]]\nmodId="examplemod"\n[[dependencies.examplemod]]\nmodId="minecraft"\nversionRange="[1.20.1,1.20.2)"\n'


@pytest.fixture
def reference(monkeypatch):
    monkeypatch.setenv("PORTKIT_TAG_REFERENCE", str(REFERENCE))
    return REFERENCE


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body) if not isinstance(body, str) else body)


def _mod(tmp_path, recipe, *, items=(), blocks=(), planks=None, loader="forge", minecraft="1.20.1"):
    root = tmp_path / "mod"
    _write(root, "data/examplemod/recipes/thing.json", recipe)
    for item in items:
        _write(root, f"assets/examplemod/models/item/{item}.json", {"parent": "minecraft:item/generated"})
    for block in blocks:
        _write(root, f"assets/examplemod/blockstates/{block}.json",
               {"variants": {"": {"model": f"examplemod:block/{block}"}}})
    if planks is not None:
        _write(root, PLANKS, planks if isinstance(planks, dict) else {"values": planks})
    return SourceMod(root=root, namespace="examplemod", loader=loader, minecraft=minecraft)


def _emitted(*, items=(), blocks=(), both=()):
    found = {}
    for name in items:
        ident = f"examplemod:{name}"
        found[ident] = ("item", f"items/{name}.json",
                        {"format_version": "1.20.10",
                         "minecraft:item": {"description": {"identifier": ident}, "components": {}}})
    for name in blocks:
        ident = f"examplemod:{name}"
        found[ident] = ("block", f"blocks/{name}.json", {"minecraft:block": {"description": {"identifier": ident}}})
    for name in both:
        ident = f"examplemod:{name}"
        # emitted_definitions gives a block with its own item file the item file (#302 pick 2).
        found[ident] = ("block_and_item", f"items/{name}.json",
                        {"format_version": "1.20.10",
                         "minecraft:item": {"description": {"identifier": ident}, "components": {}}})
    return found


def _shapeless(tag="minecraft:planks"):
    return {"type": "minecraft:crafting_shapeless", "ingredients": [{"tag": tag}, {"item": "minecraft:stick"}],
            "result": {"item": "examplemod:thing"}}


def _shaped(tag="minecraft:planks", pattern=("PPP",)):
    return {"type": "minecraft:crafting_shaped", "pattern": list(pattern), "key": {"P": {"tag": tag}},
            "result": {"item": "examplemod:thing"}}


def _recipe_files(result):
    return {k: v for k, v in result.files.items() if k.startswith("recipes/")}


def _ingredients(body):
    recipe = body.get("minecraft:recipe_shapeless") or body.get("minecraft:recipe_shaped")
    return [*recipe.get("ingredients", []), *(recipe.get("key") or {}).values()]


def test_a_mod_item_in_the_tag_carries_bedrocks_tag(tmp_path, reference):
    mod = _mod(tmp_path, _shapeless(), items=["odd_planks"], planks=["examplemod:odd_planks"])
    result = recipes.convert(mod, emitted=_emitted(items=["odd_planks"]))
    assert result.unhandled == []
    assert list(_recipe_files(result)) == ["recipes/thing.json"]
    assert {"tag": "minecraft:planks"} in _ingredients(result.files["recipes/thing.json"])
    item = result.files["items/odd_planks.json"]
    assert item["minecraft:item"]["components"]["minecraft:tags"] == {"tags": ["minecraft:planks"]}
    assert item["format_version"] == "1.20.50"
    assert PLANKS in result.consumed


def test_a_mod_block_in_the_tag_gets_an_item_form_carrying_it(tmp_path, reference):
    mod = _mod(tmp_path, _shapeless(), blocks=["netherwood_planks"], planks=["examplemod:netherwood_planks"])
    result = recipes.convert(mod, emitted=_emitted(blocks=["netherwood_planks"]))
    assert result.unhandled == []
    assert {"tag": "minecraft:planks"} in _ingredients(result.files["recipes/thing.json"])
    assert result.files["items/netherwood_planks.json"] == {
        "format_version": "1.21.50",
        "minecraft:item": {
            "description": {"identifier": "examplemod:netherwood_planks"},
            "components": {
                "minecraft:block_placer": {"block": "examplemod:netherwood_planks", "replace_block_item": True},
                "minecraft:display_name": {"value": "tile.examplemod:netherwood_planks.name"},
                "minecraft:tags": {"tags": ["minecraft:planks"]},
            },
        },
    }
    assert any("netherwood_planks from this mod" in n for n in result.notes)


def test_a_tag_filling_several_slots_works_once_members_carry_it(tmp_path, reference):
    """The tag form lets the player mix planks, so several slots are fine."""
    mod = _mod(tmp_path, _shaped(pattern=("PPP", "P P")), blocks=["netherwood_planks"],
               planks=["examplemod:netherwood_planks"])
    result = recipes.convert(mod, emitted=_emitted(blocks=["netherwood_planks"]))
    recipe = result.files["recipes/thing.json"]["minecraft:recipe_shaped"]
    assert recipe["key"] == {"P": {"tag": "minecraft:planks"}}
    assert "items/netherwood_planks.json" in result.files


def test_only_members_the_java_tag_names_are_tagged(tmp_path, reference):
    """A block called *_planks that the jar's tag file doesn't list gets nothing."""
    mod = _mod(tmp_path, _shapeless(), blocks=["netherwood_planks", "fake_planks"], items=["odd_planks"],
               planks=["examplemod:netherwood_planks"])
    result = recipes.convert(mod, emitted=_emitted(blocks=["netherwood_planks", "fake_planks"],
                                                   items=["odd_planks"]))
    assert "items/netherwood_planks.json" in result.files
    assert "items/fake_planks.json" not in result.files
    assert "items/odd_planks.json" not in result.files


def test_without_a_jar_file_the_tag_passes_through_untouched(tmp_path, reference):
    mod = _mod(tmp_path, _shapeless(), blocks=["netherwood_planks"])
    result = recipes.convert(mod, emitted=_emitted(blocks=["netherwood_planks"]))
    assert {"tag": "minecraft:planks"} in _ingredients(result.files["recipes/thing.json"])
    assert not [k for k in result.files if k.startswith("items/")]


def test_a_jar_file_adding_only_vanilla_still_passes_through(tmp_path, reference):
    mod = _mod(tmp_path, _shaped(), planks=["minecraft:oak_planks", "othermod:teak_planks"])
    result = recipes.convert(mod, emitted={})
    assert result.files["recipes/thing.json"]["minecraft:recipe_shaped"]["key"] == {"P": {"tag": "minecraft:planks"}}
    assert not [k for k in result.files if k.startswith("items/")]


def test_a_member_with_its_own_item_file_carries_the_tag_on_it(tmp_path, reference):
    """#302 pick 2: a block that already has an item file carries the tag on
    that item file, so the recipe takes the tag once."""
    mod = _mod(tmp_path, _shapeless(), blocks=["netherwood_planks"], planks=["examplemod:netherwood_planks"])
    result = recipes.convert(mod, emitted=_emitted(both=["netherwood_planks"]))
    assert result.unhandled == []
    files = _recipe_files(result)
    assert set(files) == {"recipes/thing.json"}
    assert {"tag": "minecraft:planks"} in _ingredients(files["recipes/thing.json"])
    item = result.files["items/netherwood_planks.json"]
    assert item["minecraft:item"]["components"]["minecraft:tags"] == {"tags": ["minecraft:planks"]}
    assert item["format_version"] == "1.20.50"
    assert "minecraft:block_placer" not in item["minecraft:item"]["components"]  # the mod's own item file


def test_a_multi_slot_tag_with_a_block_and_item_member_converts(tmp_path, reference):
    """With the tag on the item file, mixing members across slots is the tag's job."""
    mod = _mod(tmp_path, _shaped(pattern=("PP",)), blocks=["netherwood_planks"],
               planks=["examplemod:netherwood_planks"])
    result = recipes.convert(mod, emitted=_emitted(both=["netherwood_planks"]))
    files = _recipe_files(result)
    assert list(files) == ["recipes/thing.json"]
    assert files["recipes/thing.json"]["minecraft:recipe_shaped"]["key"] == {"P": {"tag": "minecraft:planks"}}
    assert "minecraft:planks" in result.files["items/netherwood_planks.json"]["minecraft:item"][
        "components"]["minecraft:tags"]["tags"]


def test_a_member_this_conversion_did_not_emit_is_residue_not_dropped(tmp_path, reference):
    mod = _mod(tmp_path, _shapeless(), planks=["examplemod:netherwood_planks"], blocks=["netherwood_planks"])
    result = recipes.convert(mod, emitted={})
    assert _recipe_files(result) == {}
    assert result.unhandled[0].reason.endswith("not converted: examplemod:netherwood_planks")


def test_without_reference_data_a_jar_addition_is_residue(tmp_path):
    mod = _mod(tmp_path, _shapeless(), blocks=["netherwood_planks"], planks=["examplemod:netherwood_planks"])
    result = recipes.convert(mod, emitted=_emitted(blocks=["netherwood_planks"]))
    assert _recipe_files(result) == {}
    assert "portkit reference fetch" in result.unhandled[0].reason


def test_replace_true_does_not_pass_through(tmp_path, reference):
    """A file that replaces minecraft:planks may hold fewer than Bedrock's tag."""
    mod = _mod(tmp_path, _shapeless(), planks={"replace": True, "values": ["minecraft:oak_planks",
                                                                           "minecraft:birch_planks"]})
    result = recipes.convert(mod, emitted={})
    files = _recipe_files(result)
    assert set(files) == {"recipes/thing__minecraft_oak_planks.json", "recipes/thing__minecraft_birch_planks.json"}


def test_the_blocking_ingredient_is_the_one_named(tmp_path, reference):
    """When planks would convert but another tag can't, the reason names the other."""
    # forge:chests/wooden over five slots: 2^5 = 32 combinations, over the cap (#302 pick 1).
    recipe = {"type": "minecraft:crafting_shaped", "pattern": ["PSS", "SSS"],
              "key": {"P": {"tag": "minecraft:planks"}, "S": {"tag": "forge:chests/wooden"}},
              "result": {"item": "examplemod:thing"}}
    mod = _mod(tmp_path, recipe, blocks=["netherwood_planks"], planks=["examplemod:netherwood_planks"])
    result = recipes.convert(mod, emitted=_emitted(blocks=["netherwood_planks"]))
    assert _recipe_files(result) == {}
    assert "forge:chests/wooden" in result.unhandled[0].reason


def test_end_to_end_the_pack_is_valid_and_quiet(tmp_path, fixtures_dir, reference):
    src = tmp_path / "src"
    shutil.copytree(fixtures_dir / "agent_mod" / "input", src)
    _write(src, "META-INF/mods.toml", TOML)
    _write(src, PLANKS, {"values": ["examplemod:alloy_block"]})
    _write(src, "data/examplemod/recipes/plank_thing.json", {
        "type": "minecraft:crafting_shaped", "pattern": ["PP"], "key": {"P": {"tag": "minecraft:planks"}},
        "result": {"item": "examplemod:steel_ingot"}})
    result = convert(src, tmp_path / "out", emit_addon=False)
    assert result.report.ok, result.report.errors
    bp = result.tree / "behavior_pack"
    item = json.loads((bp / "items" / "alloy_block.json").read_text())
    assert item["minecraft:item"]["components"]["minecraft:tags"] == {"tags": ["minecraft:planks"]}
    recipe = json.loads((bp / "recipes" / "plank_thing.json").read_text())
    assert recipe["minecraft:recipe_shaped"]["key"] == {"P": {"tag": "minecraft:planks"}}
    rules = {f.rule for f in result.report.findings}
    assert "identifier.block_and_item" not in rules  # declared on purpose by replace_block_item
    assert "xref.block_placer" not in rules


def test_the_validator_checks_block_placers(tmp_path, fixtures_dir):
    src = tmp_path / "src"
    shutil.copytree(fixtures_dir / "agent_mod" / "input", src)
    result = convert(src, tmp_path / "out", emit_addon=False)
    items = result.tree / "behavior_pack" / "items"
    _write(items, "ghost.json", {"format_version": "1.21.50", "minecraft:item": {
        "description": {"identifier": "examplemod:ghost"},
        "components": {"minecraft:block_placer": {"block": "examplemod:ghost", "replace_block_item": True}}}})
    _write(items, "wrong.json", {"format_version": "1.21.50", "minecraft:item": {
        "description": {"identifier": "examplemod:wrong"},
        "components": {"minecraft:block_placer": {"block": "examplemod:alloy_block", "replace_block_item": True}}}})
    report = validate_tree(result.tree)
    found = {(f.path.rsplit("/", 1)[-1], f.rule, f.severity) for f in report.findings if f.rule == "xref.block_placer"}
    assert found == {("ghost.json", "xref.block_placer", "error"), ("wrong.json", "xref.block_placer", "error")}
    assert any(f.rule == "identifier.block_and_item" for f in report.findings) is False


def test_an_item_form_leaves_with_its_withdrawn_block(tmp_path):
    result = ConversionResult()
    result.files["blocks/odd.json"] = {"format_version": "1.20.20", "minecraft:block": {
        "description": {"identifier": "examplemod:odd"},
        "components": {"minecraft:material_instances": {"*": {"texture": "examplemod:missing"}}}}}
    result.files["items/odd.json"] = {"format_version": "1.21.50", "minecraft:item": {
        "description": {"identifier": "examplemod:odd"},
        "components": {"minecraft:block_placer": {"block": "examplemod:odd", "replace_block_item": True}}}}
    drop_untextured(result, "examplemod")
    assert "blocks/odd.json" not in result.files and "items/odd.json" not in result.files
    assert [u.kind for u in result.unhandled] == ["block"]


def test_emitted_definitions_marks_a_block_with_its_own_item():
    files = {
        "blocks/door.json": {"minecraft:block": {"description": {"identifier": "examplemod:door"}}},
        "items/door.json": {"minecraft:item": {"description": {"identifier": "examplemod:door"}}},
        "items/key.json": {"minecraft:item": {"description": {"identifier": "examplemod:key"}}},
    }
    found = recipes.emitted_definitions(files)
    assert found["examplemod:door"][0] == "block_and_item"
    assert found["examplemod:key"][0] == "item"


def test_a_malformed_item_does_not_crash_the_collision_check(tmp_path, fixtures_dir):
    src = tmp_path / "src"
    shutil.copytree(fixtures_dir / "agent_mod" / "input", src)
    result = convert(src, tmp_path / "out", emit_addon=False)
    items = result.tree / "behavior_pack" / "items"
    _write(items, "junk.json", {"format_version": "1.21.50",
                                "minecraft:item": {"description": "x", "components": ["y"]}})
    validate_tree(result.tree)  # no exception
