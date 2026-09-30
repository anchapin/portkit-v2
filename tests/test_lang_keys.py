import json

import pytest

from portkit.converters import lang
from portkit.model import SourceMod


def build(tmp_path, entries, namespace="examplemod"):
    src = tmp_path / "assets" / namespace / "lang"
    src.mkdir(parents=True)
    (src / "en_us.json").write_text(json.dumps(entries))
    return SourceMod(root=tmp_path, namespace=namespace)


def test_content_keys_translate(tmp_path):
    mod = build(tmp_path, {
        "block.examplemod.copper_block": "Copper Block",
        "item.examplemod.copper_ingot": "Copper Ingot",
        "entity.examplemod.golem": "Golem",
        "itemGroup.examplemod.main": "Example Mod",
    })
    result = lang.convert(mod)
    lines = result.files["texts/en_US.lang"].splitlines()
    assert "tile.examplemod:copper_block.name=Copper Block" in lines
    assert "item.examplemod:copper_ingot.name=Copper Ingot" in lines
    assert "entity.examplemod:golem.name=Golem" in lines
    assert "itemGroup.name.main=Example Mod" in lines
    assert result.unhandled == []


def test_code_strings_collapse_to_one_entry(tmp_path):
    mod = build(tmp_path, {
        "block.examplemod.copper_block": "Copper Block",
        "wiki.examplemod.thatch": "Thatch is nice",
        "message.examplemod.bad_config": "Bad config",
        "key.examplemod.switch_state": "Switch state",
        "fluid_type.examplemod.thatch": "Thatch",
    })
    result = lang.convert(mod)
    assert len(result.unhandled) == 1
    item = result.unhandled[0]
    assert item.kind == "lang_code_string"
    assert "4 string(s)" in item.reason
    assert "no Bedrock" in item.reason
    # the real content still converts
    assert "tile.examplemod:copper_block.name=Copper Block" in result.files["texts/en_US.lang"]


def test_unrecognised_shapes_still_report_individually(tmp_path):
    mod = build(tmp_path, {
        "block.examplemod.copper_block": "Copper Block",
        "sorcery.examplemod.rune": "Rune",
        "twoparts.only": "Nope",
    })
    result = lang.convert(mod)
    kinds = sorted(u.kind for u in result.unhandled)
    assert kinds == ["lang", "lang"]
    assert all("unrecognised translation key" in u.reason for u in result.unhandled)


def test_other_namespace_is_not_swallowed_as_code(tmp_path):
    mod = build(tmp_path, {"block.someothermod.thing": "Thing"})
    result = lang.convert(mod)
    assert [u.kind for u in result.unhandled] == ["lang"]
