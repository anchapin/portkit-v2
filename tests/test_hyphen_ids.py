"""A Java id with a hyphen stays that id on Bedrock (Wallpapercraft's wallpapercraft:woolblue-0).

Mojang's schemas take a hyphen in a block, item, recipe or loot-entry id, so the
validator does too, and the converter keeps the Java spelling. Texture keys are
the exception: they stay [a-z0-9_] because the texture converter maps "-" to "_"
(#168). See docs/decisions.md, 2026-10-14.
"""
import json

import pytest

from portkit.pipeline import convert
from portkit.validate.rules import _IDENTIFIER, _TEXTURE_KEY, validate_pack, validate_tree

PNG = b"\x89PNG\r\n\x1a\n"


def _write(root, rel, body):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body) if isinstance(body, bytes) else path.write_text(json.dumps(body))


def _rules(report, prefix):
    return sorted({f.rule for f in report.findings if f.rule.startswith(prefix)})


@pytest.mark.parametrize("ident", [
    "wallpapercraft:woolblue-0",
    "wallpapercraft:solidgray-0_clayball",
    "mythicmetals:dura-chan",
    "my-mod:a-b/c-d.e",
])
def test_a_hyphenated_id_is_an_identifier(ident):
    assert _IDENTIFIER.match(ident)


@pytest.mark.parametrize("ident", [
    "lamp-0",                 # no namespace
    "examplemod:Lamp-0",      # uppercase
    "examplemod:lamp 0",      # whitespace
    "examplemod:lamp:0",      # second colon
    "examplemod:",            # empty path
    "a/b:lamp",               # slash in the namespace
])
def test_the_rest_of_the_rule_still_holds(ident):
    assert not _IDENTIFIER.match(ident)


def test_a_texture_key_still_refuses_a_hyphen():
    assert not _TEXTURE_KEY.match("examplemod:dura-chan")
    assert _TEXTURE_KEY.match("examplemod:dura_chan")


def _block(ident):
    return {
        "format_version": "1.20.20",
        "minecraft:block": {
            "description": {"identifier": ident, "menu_category": {"category": "construction"}},
            "components": {"minecraft:geometry": "minecraft:geometry.full_block"},
        },
    }


def _recipe(ident, result):
    return {
        "format_version": "1.20.10",
        "minecraft:recipe_shapeless": {
            "description": {"identifier": ident},
            "tags": ["crafting_table"],
            "ingredients": [{"item": "minecraft:clay_ball"}],
            "result": {"item": result},
        },
    }


def _manifest(kind):
    return {
        "format_version": 2,
        "header": {"name": "t", "description": "t", "uuid": "00000000-0000-4000-8000-00000000000" + ("1" if kind == "data" else "2"),
                   "version": [1, 0, 0], "min_engine_version": [1, 21, 90]},
        "modules": [{"type": kind, "uuid": "00000000-0000-4000-8000-00000000000" + ("3" if kind == "data" else "4"),
                     "version": [1, 0, 0]}],
    }


def test_the_validator_accepts_hyphenated_block_recipe_and_loot_ids(tmp_path):
    pack = tmp_path / "behavior_pack"
    _write(pack, "manifest.json", _manifest("data"))
    _write(pack, "blocks/woolblue-0.json", _block("wallpapercraft:woolblue-0"))
    _write(pack, "recipes/woolblue-0_clayball.json",
           _recipe("wallpapercraft:woolblue-0_clayball", "wallpapercraft:woolblue-0"))
    _write(pack, "loot_tables/blocks/woolblue-0.json",
           {"pools": [{"rolls": 1, "entries": [{"type": "item", "name": "wallpapercraft:woolblue-0"}]}]})
    report = validate_pack(pack)
    assert _rules(report, "block.identifier") == []
    assert _rules(report, "recipe.identifier") == []
    assert _rules(report, "loot.name") == []


def test_the_validator_still_refuses_a_bad_id(tmp_path):
    pack = tmp_path / "behavior_pack"
    _write(pack, "manifest.json", _manifest("data"))
    _write(pack, "blocks/lamp.json", _block("examplemod:Lamp-0"))
    _write(pack, "recipes/lamp.json", _recipe("lamp-0", "examplemod:lamp"))
    report = validate_pack(pack)
    assert _rules(report, "block.identifier") == ["block.identifier"]
    assert _rules(report, "recipe.identifier") == ["recipe.identifier"]


def test_a_hyphenated_texture_key_is_still_an_error(tmp_path):
    pack = tmp_path / "resource_pack"
    _write(pack, "manifest.json", _manifest("resources"))
    _write(pack, "textures/blocks/a-b.png", PNG)
    _write(pack, "textures/terrain_texture.json", {
        "resource_pack_name": "t", "texture_name": "atlas.terrain",
        "texture_data": {"examplemod:a-b": {"textures": "textures/blocks/a-b"}},
    })
    report = validate_pack(pack)
    assert _rules(report, "texture_index.identifier") == ["texture_index.identifier"]


def test_a_hyphenated_block_with_a_name_has_no_lang_warning(tmp_path):
    _write(tmp_path, "behavior_pack/manifest.json", _manifest("data"))
    _write(tmp_path, "behavior_pack/blocks/woolblue-0.json", _block("wallpapercraft:woolblue-0"))
    _write(tmp_path, "resource_pack/manifest.json", _manifest("resources"))
    lang = tmp_path / "resource_pack/texts/en_US.lang"
    lang.parent.mkdir(parents=True, exist_ok=True)
    lang.write_text(
        "tile.wallpapercraft:woolblue-0.name=Wool Blue\n"
        "tile.wallpapercraft:woolblue-0_carpet.name=Wool Blue Carpet\n"
    )
    report = validate_tree(tmp_path)
    missing = [f for f in report.findings if f.rule == "xref.lang_missing"]
    assert missing == []
    # The name for a block that was not converted is now seen as an orphan.
    orphans = [f.message for f in report.findings if f.rule == "xref.lang_orphan"]
    assert len(orphans) == 1 and "wallpapercraft:woolblue-0_carpet" in orphans[0]


def _mod(root):
    ns = "examplemod"
    _write(root, f"assets/{ns}/textures/block/lamp-0.png", PNG)
    _write(root, f"assets/{ns}/models/block/lamp-0.json",
           {"parent": "minecraft:block/cube_all", "textures": {"all": f"{ns}:block/lamp-0"}})
    _write(root, f"assets/{ns}/blockstates/lamp-0.json",
           {"variants": {"": {"model": f"{ns}:block/lamp-0"}}})
    _write(root, f"assets/{ns}/models/item/lamp-0.json", {"parent": f"{ns}:block/lamp-0"})
    _write(root, f"assets/{ns}/lang/en_us.json", {f"block.{ns}.lamp-0": "Lamp Zero"})
    _write(root, f"data/{ns}/recipe/lamp-0_from_clay.json", {
        "type": "minecraft:crafting_shapeless",
        "ingredients": [{"item": "minecraft:clay_ball"}],
        "result": {"id": f"{ns}:lamp-0", "count": 1},
    })


def test_end_to_end_a_hyphenated_block_keeps_its_java_id(tmp_path):
    _mod(tmp_path / "mod")
    out = convert(tmp_path / "mod", tmp_path / "out", emit_addon=False)
    assert out.report.ok, [f.message for f in out.report.errors]
    block = json.loads((out.tree / "behavior_pack/blocks/lamp-0.json").read_text())
    assert block["minecraft:block"]["description"]["identifier"] == "examplemod:lamp-0"
    recipe = json.loads((out.tree / "behavior_pack/recipes/lamp-0_from_clay.json").read_text())
    body = recipe["minecraft:recipe_shapeless"]
    assert body["description"]["identifier"] == "examplemod:lamp-0_from_clay"
    assert body["result"]["item"] == "examplemod:lamp-0"
    lang = (out.tree / "resource_pack/texts/en_US.lang").read_text()
    assert "tile.examplemod:lamp-0.name=Lamp Zero" in lang
    rules = {f.rule for f in out.report.findings}
    assert "xref.lang_missing" not in rules
    # The texture key is still mapped (#168); the block id is not.
    atlas = json.loads((out.tree / "resource_pack/textures/terrain_texture.json").read_text())
    assert any(k.endswith("lamp_0") for k in atlas["texture_data"])
