"""Recipes that share a file name in different folders (#163).

Every recipe used to be written to ``recipes/<file stem>.json``, so Tinkers'
four ``world/wood/<wood>/planks.json`` all landed on one path and only the last
one shipped, counted as converted. Now a shared stem is named by its path, and
nothing is ever written over another output.
"""
import itertools
import json
from pathlib import PurePosixPath

from portkit.converters import recipes
from portkit.model import ConversionResult, SourceMod, Unhandled


def shaped(result_item):
    return {
        "type": "minecraft:crafting_shaped",
        "pattern": ["#"],
        "key": {"#": {"item": f"{result_item}_log"}},
        "result": {"item": result_item, "count": 4},
    }


def build(tmp_path, files):
    src = tmp_path / "data" / "examplemod" / "recipes"
    for rel, body in files.items():
        path = src / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body))
    return SourceMod(root=tmp_path, namespace="examplemod")


def identifiers(result):
    found = {}
    for path, body in result.files.items():
        ((key, inner),) = [(k, v) for k, v in body.items() if k != "format_version"]
        found[path] = inner["description"]["identifier"]
    return found


def test_same_name_in_two_folders_both_ship_with_unique_identifiers(tmp_path):
    mod = build(tmp_path, {
        "world/wood/greenheart/planks.json": shaped("examplemod:greenheart_planks"),
        "world/wood/skyroot/planks.json": shaped("examplemod:skyroot_planks"),
        "stick.json": shaped("examplemod:stick"),
    })
    result = recipes.convert(mod)
    assert result.unhandled == []
    assert identifiers(result) == {
        "recipes/world_wood_greenheart_planks.json": "examplemod:world_wood_greenheart_planks",
        "recipes/world_wood_skyroot_planks.json": "examplemod:world_wood_skyroot_planks",
        # an unshared stem keeps the name it always had
        "recipes/stick.json": "examplemod:stick",
    }
    ships = {
        path: body["minecraft:recipe_shaped"]["result"]["item"] for path, body in result.files.items()
    }
    assert ships["recipes/world_wood_greenheart_planks.json"] == "examplemod:greenheart_planks"
    assert ships["recipes/world_wood_skyroot_planks.json"] == "examplemod:skyroot_planks"


def test_a_shared_stem_at_the_root_is_qualified_too_and_keeps_its_bare_name(tmp_path):
    # The root file's whole path is its stem, so it keeps "planks"; the other
    # is named by its folder. Neither depends on which was read first.
    mod = build(tmp_path, {
        "planks.json": shaped("examplemod:oak_planks"),
        "compat/planks.json": shaped("examplemod:compat_planks"),
    })
    result = recipes.convert(mod)
    assert result.unhandled == []
    assert sorted(result.files) == ["recipes/compat_planks.json", "recipes/planks.json"]


def test_names_do_not_depend_on_order():
    rels = [PurePosixPath(p) for p in (
        "smeltery/casting/planks.json", "world/planks.json", "planks2.json",
        "a/x.json", "b/x.json", "x.json", "solo/deep/thing.json",
    )]
    expected = recipes.recipe_names(rels)
    for order in itertools.permutations(rels):
        assert recipes.recipe_names(list(order)) == expected
    names, refused = expected
    assert names[PurePosixPath("smeltery/casting/planks.json")] == "smeltery_casting_planks"
    assert names[PurePosixPath("world/planks.json")] == "world_planks"
    assert names[PurePosixPath("solo/deep/thing.json")] == "thing"
    assert names[PurePosixPath("x.json")] == "x"
    assert names[PurePosixPath("a/x.json")] == "a_x"
    assert refused == {}


def test_a_qualified_name_that_meets_an_unshared_one_is_refused_not_written_over(tmp_path):
    mod = build(tmp_path, {
        "x/planks.json": shaped("examplemod:from_folder"),
        "y/planks.json": shaped("examplemod:from_y"),
        "x_planks.json": shaped("examplemod:from_root"),
    })
    result = recipes.convert(mod)
    assert sorted(result.files) == ["recipes/x_planks.json", "recipes/y_planks.json"]
    assert result.files["recipes/x_planks.json"]["minecraft:recipe_shaped"]["result"]["item"] == "examplemod:from_root"
    (refused,) = result.unhandled
    assert refused.source == "data/examplemod/recipes/x/planks.json"
    assert refused.kind == "recipe"
    assert "x_planks.json" in refused.reason and "refused rather than overwrite" in refused.reason


def test_two_qualified_names_that_meet_are_both_refused(tmp_path):
    mod = build(tmp_path, {
        "a/b/c.json": shaped("examplemod:one"),
        "a_b/c.json": shaped("examplemod:two"),
    })
    result = recipes.convert(mod)
    assert result.files == {}
    assert sorted(u.source for u in result.unhandled) == [
        "data/examplemod/recipes/a/b/c.json",
        "data/examplemod/recipes/a_b/c.json",
    ]


def test_smithing_recipes_in_two_folders_both_ship(tmp_path):
    def smithing(base):
        return {
            "type": "minecraft:smithing_transform",
            "template": {"item": "minecraft:netherite_upgrade_smithing_template"},
            "base": {"item": f"examplemod:{base}"},
            "addition": {"item": "minecraft:netherite_ingot"},
            "result": {"item": f"examplemod:{base}_plus"},
        }
    mod = build(tmp_path, {"tools/upgrade.json": smithing("pick"), "armor/upgrade.json": smithing("helm")})
    result = recipes.convert(mod)
    assert result.unhandled == []
    assert identifiers(result) == {
        "recipes/armor_upgrade.json": "examplemod:armor_upgrade",
        "recipes/tools_upgrade.json": "examplemod:tools_upgrade",
    }


def item(identifier, **components):
    return {"format_version": "1.21.0", "minecraft:item": {
        "description": {"identifier": identifier}, "components": components}}


def test_a_later_converter_may_enrich_the_same_definition():
    first = ConversionResult({"items/a.json": item("examplemod:a")})
    later = ConversionResult({"items/a.json": item("examplemod:a", **{"minecraft:tags": {"tags": ["t"]}})})
    merged = first.merge(later)
    assert merged.files["items/a.json"] == later.files["items/a.json"]
    assert merged.unhandled == []


def test_a_later_converter_never_writes_over_a_different_definition():
    first = ConversionResult({"items/a.json": item("examplemod:a")})
    later = ConversionResult(
        {"items/a.json": item("examplemod:b"), "items/c.json": item("examplemod:c")},
        [Unhandled("x", "item", "why")],
    )
    merged = first.merge(later)
    assert merged.files["items/a.json"] == first.files["items/a.json"]
    assert merged.files["items/c.json"] == later.files["items/c.json"]
    (collision,) = [u for u in merged.unhandled if u.kind == "output_collision"]
    assert collision.source == "items/a.json"
    assert "examplemod:a" in collision.reason and "examplemod:b" in collision.reason
    assert len(merged.unhandled) == 2


def test_bytes_written_twice_differently_are_a_collision():
    merged = ConversionResult({"textures/x.png": b"1"}).merge(ConversionResult({"textures/x.png": b"2"}))
    assert merged.files["textures/x.png"] == b"1"
    assert [u.kind for u in merged.unhandled] == ["output_collision"]


# -- per-member expansions (#161/#162) take the qualified name too -------------
REFERENCE = __import__("pathlib").Path(__file__).resolve().parent / "data" / "tag_reference"


def chests(result_item):
    return {"type": "minecraft:crafting_shapeless",
            "ingredients": [{"tag": "forge:chests/wooden"}],
            "result": {"item": result_item}}


def with_loader(mod):
    return SourceMod(root=mod.root, namespace=mod.namespace, loader="forge", minecraft="1.20.1")


def test_per_member_recipes_of_a_shared_stem_are_qualified(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTKIT_TAG_REFERENCE", str(REFERENCE))
    mod = with_loader(build(tmp_path, {"a/thing.json": chests("examplemod:a"),
                                       "b/thing.json": chests("examplemod:b")}))
    result = recipes.convert(mod, emitted={})
    assert result.unhandled == []
    assert identifiers(result) == {
        f"recipes/{p}_thing__minecraft_{c}.json": f"examplemod:{p}_thing__minecraft_{c}"
        for p in ("a", "b") for c in ("chest", "trapped_chest")
    }
    assert any("(a_thing__<member>)" in n for n in result.notes)


def test_a_per_member_name_never_lands_on_another_recipe(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTKIT_TAG_REFERENCE", str(REFERENCE))
    mod = with_loader(build(tmp_path, {
        "thing.json": chests("examplemod:expanded"),
        "thing__minecraft_chest.json": shaped("examplemod:its_own"),
    }))
    result = recipes.convert(mod, emitted={})
    assert list(result.files) == ["recipes/thing__minecraft_chest.json"]
    assert result.files["recipes/thing__minecraft_chest.json"]["minecraft:recipe_shaped"]["result"]["item"] == "examplemod:its_own"
    assert [u.source for u in result.unhandled] == ["data/examplemod/recipes/thing.json"]
