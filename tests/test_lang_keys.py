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
        "string.examplemod.searching": "Searching",
    })
    result = lang.convert(mod)
    assert len(result.unhandled) == 1
    item = result.unhandled[0]
    assert item.kind == "lang_code_string"
    assert "4 string(s)" in item.reason
    assert "no Bedrock" in item.reason
    # the real content still converts
    assert "tile.examplemod:copper_block.name=Copper Block" in result.files["texts/en_US.lang"]


def test_any_key_no_registry_owns_is_a_code_string(tmp_path):
    # #277 lang: "<ns>.config.x", "desc.<ns>.x", "waila.<ns>.x", "_comment": no
    # block, item, entity or creative tab owns them, so only Java code shows
    # them. One explained entry, not one per key.
    mod = build(tmp_path, {
        "block.examplemod.copper_block": "Copper Block",
        "sorcery.examplemod.rune": "Rune",
        "examplemod.config.speed": "Speed",
        "twoparts.only": "Nope",
        "_comment": "translators: keep it short",
    })
    result = lang.convert(mod)
    assert [u.kind for u in result.unhandled] == ["lang_code_string"]
    assert "4 string(s)" in result.unhandled[0].reason


def test_registry_entries_portkit_ships_none_of_are_unshipped(tmp_path):
    mod = build(tmp_path, {
        "effect.examplemod.glow": "Glow",
        "biome.examplemod.marsh": "Marsh",
        "fluid_type.examplemod.thatch": "Thatch",
        "block.minecraft.banner.examplemod.rune.black": "Black Rune",
        "itemGroup.examplemod": "Example Mod",
    })
    result = lang.convert(mod)
    assert [u.kind for u in result.unhandled] == ["lang_unshipped"]
    reason = result.unhandled[0].reason
    assert "5 key(s)" in reason
    for label in ("mob effect 1", "biome 1", "fluid 1", "vanilla minecraft: entry 1", "creative tab 1"):
        assert label in reason
    assert "texts/en_US.lang" not in result.files


def test_another_namespace_s_content_key_is_a_line_settled_later(tmp_path):
    # Whether block.someothermod.thing ships is decided on the final pack.
    mod = build(tmp_path, {"block.someothermod.thing": "Thing"})
    result = lang.convert(mod)
    assert result.unhandled == []
    assert "tile.someothermod:thing.name=Thing" in result.files["texts/en_US.lang"]


def _settled(files, consumed=("assets/examplemod/lang/en_us.json",)):
    from portkit.model import ConversionResult

    result = ConversionResult(files=dict(files), consumed=set(consumed))
    lang.settle(result)
    return result


_BLOCK = {"minecraft:block": {"description": {"identifier": "examplemod:copper_block"}}}


def test_settle_keeps_lines_for_what_ships_and_explains_the_rest(tmp_path):
    result = _settled({
        "blocks/copper_block.json": _BLOCK,
        "texts/en_US.lang": ("tile.examplemod:copper_block.name=Copper Block\n"
                             "tile.examplemod:tin_block.name=Tin Block\n"
                             "item.examplemod:copper_block.tooltip.name=Shiny\n"
                             "itemGroup.name.main=Example Mod\n"
                             "gui.examplemod.title=Title\n"),
        "texts/languages.json": ["en_US"],
    })
    assert result.files["texts/en_US.lang"] == ("tile.examplemod:copper_block.name=Copper Block\n"
                                                "gui.examplemod.title=Title\n")
    kinds = {u.kind: u for u in result.unhandled}
    assert set(kinds) == {"lang_unshipped", "lang_code_string"}
    assert "examplemod:tin_block" in kinds["lang_unshipped"].reason
    assert "creative tab 1" in kinds["lang_unshipped"].reason
    assert "tooltip" in kinds["lang_code_string"].reason
    assert all(u.source == "assets/examplemod/lang/en_us.json" for u in result.unhandled)


def test_settle_keeps_a_key_the_pack_names_and_drops_an_empty_locale(tmp_path):
    item = {"minecraft:item": {"description": {"identifier": "examplemod:gear"},
                               "components": {"minecraft:display_name": {"value": "tile.examplemod:gear_block.name"}}}}
    result = _settled({
        "items/gear.json": item,
        "texts/en_US.lang": "tile.examplemod:gear_block.name=Gear\n",
        "texts/fr_FR.lang": "tile.examplemod:tin_block.name=Bloc d'étain\n",
        "texts/languages.json": ["en_US", "fr_FR"],
    }, consumed=("assets/examplemod/lang/en_us.json", "assets/examplemod/lang/fr_fr.json"))
    assert result.files["texts/en_US.lang"] == "tile.examplemod:gear_block.name=Gear\n"
    assert "texts/fr_FR.lang" not in result.files
    assert result.files["texts/languages.json"] == ["en_US"]
    assert [u.source for u in result.unhandled] == ["assets/examplemod/lang/fr_fr.json"]
    assert "only in fr_FR" in result.unhandled[0].reason


def test_a_byte_order_mark_loads_as_java_reads_it(tmp_path):
    src = tmp_path / "assets" / "examplemod" / "lang"
    src.mkdir(parents=True)
    (src / "en_us.json").write_bytes("\ufeff".encode() + json.dumps({"item.examplemod.gear": "Gear"}).encode())
    result = lang.convert(SourceMod(root=tmp_path, namespace="examplemod"))
    assert result.unhandled == []
    assert "item.examplemod:gear.name=Gear" in result.files["texts/en_US.lang"]


@pytest.mark.parametrize("text, kind", [
    ('{"a.b.c": "x",, "d.e.f": "y"}', "lang_unreadable"),   # Gson: Expected name
    ('{"a.b.c": "x",\n}', "lang_unreadable"),               # trailing comma in an object
    ('{"a.b.c": "x" "d.e.f": "y"}', "lang"),                 # not claimed: left as invalid JSON
])
def test_a_file_java_rejects_too_is_explained(tmp_path, text, kind):
    src = tmp_path / "assets" / "examplemod" / "lang"
    src.mkdir(parents=True)
    (src / "de_de.json").write_text(text)
    result = lang.convert(SourceMod(root=tmp_path, namespace="examplemod"))
    assert [u.kind for u in result.unhandled] == [kind]


def test_other_locales_report_only_what_the_primary_lacks(tmp_path):
    # de_de sorts before en_us; it must still be compared against en_us.
    src = tmp_path / "assets" / "examplemod" / "lang"
    src.mkdir(parents=True)
    keys = {"gui.examplemod.a": "A", "gui.examplemod.b": "B"}
    (src / "en_us.json").write_text(json.dumps(keys))
    (src / "de_de.json").write_text(json.dumps({**keys, "gui.examplemod.c": "C"}))
    result = lang.convert(SourceMod(root=tmp_path, namespace="examplemod"))
    de = [u for u in result.unhandled if u.source.endswith("de_de.json")]
    assert len(de) == 1 and de[0].reason.startswith("1 string(s) present in de_de")


@pytest.mark.parametrize("sep", ["\n", "\r\n", "\r"])
def test_newlines_in_a_value_become_linebreak_tokens(tmp_path, sep):
    # Storage Drawers and Tinkers' Construct ship multi-line names (#108).
    mod = build(tmp_path, {
        "block.examplemod.drawer": f"Drawer{sep}Hold in off-hand to lock",
        "item.examplemod.key": "Key",
    })
    text = lang.convert(mod).files["texts/en_US.lang"]
    lines = text.splitlines()
    assert "tile.examplemod:drawer.name=Drawer~LINEBREAK~Hold in off-hand to lock" in lines
    assert all("=" in line for line in lines)
