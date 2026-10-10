"""set_lang_entries (#105): the residue agent can name what it adds."""
import json
from pathlib import Path

from portkit.agent.residue import _TrackingToolBox
from portkit.agent.tools import ToolBox
from portkit.pipeline import convert
from portkit.validate import validate_tree

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "fixtures" / "locales_mod" / "input"
EN = "resource_pack/texts/en_US.lang"


def _box(tmp_path, cls=ToolBox):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    return cls(src, out), out


def test_lines_are_upserted_and_everything_else_is_kept(tmp_path):
    box, out = _box(tmp_path)
    lang = out / EN
    lang.parent.mkdir(parents=True)
    lang.write_text("## header\ntile.m:a.name=A\nitem.m:b.name=B\n")
    (lang.parent / "languages.json").write_text('["en_US"]\n')

    result = box.invoke("set_lang_entries", {"path": EN, "lines": ["item.m:b.name=Better B", "item.m:c.name = C"]})
    assert result == {"written": EN, "added": ["item.m:c.name"], "replaced": ["item.m:b.name"]}
    assert lang.read_text() == "## header\ntile.m:a.name=A\nitem.m:b.name=Better B\nitem.m:c.name=C\n"
    assert json.loads((lang.parent / "languages.json").read_text()) == ["en_US"]


def test_a_new_locale_is_listed_in_languages_json(tmp_path):
    box, out = _box(tmp_path)
    box.invoke("set_lang_entries", {"path": "resource_pack/texts/de_DE.lang", "lines": ["tile.m:a.name=A"]})
    assert (out / "resource_pack/texts/de_DE.lang").read_text() == "tile.m:a.name=A\n"
    assert json.loads((out / "resource_pack/texts/languages.json").read_text()) == ["de_DE"]


def test_bad_calls_write_nothing(tmp_path):
    box, out = _box(tmp_path)
    for args in [
        {"path": "behavior_pack/texts/en_US.lang", "lines": ["a=b"]},
        {"path": "resource_pack/texts/en_US.json", "lines": ["a=b"]},
        {"path": "resource_pack/texts/../../x/en_US.lang", "lines": ["a=b"]},
        {"path": EN, "lines": []},
        {"path": EN, "lines": "a=b"},
        {"path": EN, "lines": ["a=b", "no equals sign"]},
        {"path": EN, "lines": ["=value"]},
        {"path": EN, "lines": ["a=b\nc=d"]},
        {"path": EN, "lines": ["two words=x"]},
    ]:
        assert "error" in box.invoke("set_lang_entries", args), args
    assert not out.exists()


def test_the_tool_fits_the_toolbox_schema(tmp_path):
    box, _ = _box(tmp_path)
    assert box.format_error("set_lang_entries", {"path": EN, "lines": ["a=b"]}) is None
    assert "missing" in box.format_error("set_lang_entries", {"path": EN})


def test_rollback_restores_the_lang_file_and_the_index(tmp_path):
    box, out = _box(tmp_path, _TrackingToolBox)
    lang = out / EN
    lang.parent.mkdir(parents=True)
    lang.write_text("tile.m:a.name=A\n")
    box.invoke("set_lang_entries", {"path": EN, "lines": ["tile.m:a.name=Changed"]})
    box.invoke("set_lang_entries", {"path": "resource_pack/texts/fr_FR.lang", "lines": ["tile.m:a.name=Un"]})
    assert sorted(box.originals) == [EN, "resource_pack/texts/fr_FR.lang", "resource_pack/texts/languages.json"]
    box.rollback()
    assert lang.read_text() == "tile.m:a.name=A\n"
    assert not (out / "resource_pack/texts/fr_FR.lang").exists()
    assert not (out / "resource_pack/texts/languages.json").exists()


def test_naming_an_added_item_clears_lang_missing(tmp_path):
    out = tmp_path / "out"
    convert(LOCALES, out)
    box = ToolBox(tmp_path, out)
    item = {
        "format_version": "1.20.10",
        "minecraft:item": {"description": {"identifier": "examplemod:agent_gem"}, "components": {}},
    }
    box.invoke("write_output", {"path": "behavior_pack/items/agent_gem.json", "content": item})

    def missing():
        return [f for f in validate_tree(out).findings
                if f.rule == "xref.lang_missing" and "examplemod:agent_gem" in f.message]

    assert missing()
    errors_before = {(f.path, f.rule) for f in validate_tree(out).errors}
    box.invoke("set_lang_entries", {"path": EN, "lines": ["item.examplemod:agent_gem.name=Agent Gem"]})
    assert not missing()
    assert {(f.path, f.rule) for f in validate_tree(out).errors} == errors_before
