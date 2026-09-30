"""Every locale the mod ships, not just English."""
import json

from portkit.converters import lang
from portkit.model import SourceMod


def build(tmp_path, files):
    src = tmp_path / "assets" / "examplemod" / "lang"
    src.mkdir(parents=True)
    for name, entries in files.items():
        (src / f"{name}.json").write_text(json.dumps(entries), encoding="utf-8")
    return SourceMod(root=tmp_path, namespace="examplemod")


CONTENT = {"block.examplemod.steel_block": "Steel Block"}


def test_each_locale_becomes_its_own_bedrock_file(tmp_path):
    mod = build(tmp_path, {"en_us": CONTENT, "fr_fr": CONTENT, "ja_jp": CONTENT})
    files = lang.convert(mod).files
    assert set(files) == {
        "texts/en_US.lang",
        "texts/fr_FR.lang",
        "texts/ja_JP.lang",
        "texts/languages.json",
    }


def test_languages_json_lists_what_actually_converted(tmp_path):
    mod = build(tmp_path, {"en_us": CONTENT, "ja_jp": CONTENT, "fr_fr": CONTENT})
    listed = lang.convert(mod).files["texts/languages.json"]
    assert listed == ["en_US", "fr_FR", "ja_JP"]


def test_a_locale_with_nothing_translatable_stays_out_of_the_list(tmp_path):
    mod = build(tmp_path, {"en_us": CONTENT, "fr_fr": {"gui.examplemod.title": "Titre"}})
    result = lang.convert(mod)
    assert result.files["texts/languages.json"] == ["en_US"]
    assert "texts/fr_FR.lang" not in result.files


def test_norwegian_is_renamed_rather_than_dropped(tmp_path):
    mod = build(tmp_path, {"en_us": CONTENT, "no_no": CONTENT})
    result = lang.convert(mod)
    assert "texts/nb_NO.lang" in result.files
    assert result.unhandled == []


def test_a_locale_bedrock_has_no_slot_for_is_named_in_the_residue(tmp_path):
    mod = build(tmp_path, {"en_us": CONTENT, "es_ar": CONTENT})
    result = lang.convert(mod)
    assert "es_ar" in result.unhandled[0].reason
    assert not any(k.startswith("texts/es") for k in result.files)


def test_untranslatable_keys_are_reported_once_not_once_per_locale(tmp_path):
    entries = {**CONTENT, "gui.examplemod.title": "Title", "wiki.examplemod.page": "Page"}
    mod = build(tmp_path, {loc: entries for loc in ("en_us", "fr_fr", "ja_jp", "de_de")})
    result = lang.convert(mod)
    code = [u for u in result.unhandled if u.kind == "lang_code_string"]
    assert len(code) == 1
    assert "en_us" in code[0].source


def test_a_key_only_a_translation_has_is_still_reported(tmp_path):
    mod = build(tmp_path, {
        "en_us": CONTENT,
        "fr_fr": {**CONTENT, "somemod.stray.key": "Perdu"},
    })
    reasons = [u.reason for u in lang.convert(mod).unhandled]
    assert any("fr_fr" in r and "somemod.stray.key" in r for r in reasons)


def test_every_locale_file_is_claimed(tmp_path):
    mod = build(tmp_path, {"en_us": CONTENT, "fr_fr": CONTENT, "es_ar": CONTENT})
    consumed = lang.convert(mod).consumed
    assert len(consumed) == 3
    assert all(c.endswith(".json") for c in consumed)


def test_the_fixture_converts(tmp_path, fixtures_dir):
    from portkit.pipeline import convert

    result = convert(fixtures_dir / "locales_mod" / "input", tmp_path / "out")
    assert result.report.ok, result.report.to_dict()
    listed = json.loads((tmp_path / "out" / "resource_pack" / "texts" / "languages.json").read_text())
    assert listed == ["en_US", "fr_FR", "ja_JP", "nb_NO"]
    assert [u.reason for u in result.unhandled if "es_ar" in u.reason]
