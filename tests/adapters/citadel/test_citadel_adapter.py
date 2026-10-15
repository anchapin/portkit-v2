"""The Citadel library adapter (#245, migration step 6) and the ``books`` hook.

Citadel's guide-book reader (tests in ``test_books.py`` beside this file)
reaches the core only through :class:`portkit.adapters.BookReader`. These
tests pin its registration and that :func:`portkit.converters.convert_all`
asks every book reader in registry order: page text into the lang converter,
files into the pack, entry lines into ``scripts/portkit/main.js``.
"""
import json

from portkit import adapters
from portkit.adapters import Adapter, BookReader, citadel
from portkit.adapters.citadel import books
from portkit.converters import convert_all
from portkit.converters.station_kit import ENTRY
from portkit.model import ConversionResult, SourceMod


def test_citadel_is_a_registered_library_adapter():
    assert citadel.ADAPTER in adapters.ADAPTERS
    assert citadel.ADAPTER.library
    assert citadel.ADAPTER.namespaces == frozenset({"citadel"})
    assert adapters.book_readers() == [citadel.ADAPTER.books]
    reader = citadel.ADAPTER.books
    assert (reader.plan, reader.lang_text, reader.convert) == (books.plan, books.lang_text, books.convert)


def _mod(tmp_path):
    (tmp_path / "assets" / "examplemod" / "lang").mkdir(parents=True)
    (tmp_path / "assets" / "examplemod" / "lang" / "en_us.json").write_text(json.dumps({"item.examplemod.x": "X"}))
    return SourceMod(root=tmp_path, namespace="examplemod", loader="forge",
                     mods={"examplemod": "1.0"}, requires=frozenset())


def _reader(tag, seen):
    def plan(mod, files):
        seen.append((tag, "plan"))
        return tag

    def lang_text(mod, plan_):
        assert plan_ == tag
        return {"en_us": {f"portkit.book.examplemod.{tag}.root": f"{tag} text"}}

    def convert(mod, plan_):
        assert plan_ == tag
        seen.append((tag, "convert"))
        result = ConversionResult()
        result.files[f"scripts/portkit/data/examplemod_{tag}.js"] = "export default {};\n"
        return result, f'import "./data/examplemod_{tag}.js";\n'

    return BookReader(plan=plan, lang_text=lang_text, convert=convert)


def test_every_book_reader_runs_in_convert_all_in_registry_order(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(adapters, "ADAPTERS", (
        Adapter("a", frozenset({"a"}), books=_reader("first", seen)),
        Adapter("b", frozenset({"b"}), books=_reader("second", seen)),
    ))
    result = convert_all(_mod(tmp_path))
    assert seen == [("first", "plan"), ("second", "plan"), ("first", "convert"), ("second", "convert")]
    assert "scripts/portkit/data/examplemod_first.js" in result.files
    assert "scripts/portkit/data/examplemod_second.js" in result.files
    main = result.files[ENTRY]
    assert main.index("examplemod_first.js") < main.index("examplemod_second.js")
    lang = result.files["texts/en_US.lang"]
    assert "portkit.book.examplemod.first.root=first text" in lang
    assert "portkit.book.examplemod.second.root=second text" in lang


def test_no_book_reader_ships_no_book_files(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "ADAPTERS", ())
    result = convert_all(_mod(tmp_path))
    assert ENTRY not in result.files
    assert not any(p.startswith("scripts/") for p in result.files)
