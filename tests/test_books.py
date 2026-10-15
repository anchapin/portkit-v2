"""Citadel guide books (#182): page text, the page table, which item opens the
book (bytecode, DEFAULT by name), and the form viewer under node.

The class files under tests/data/citadel_book/classes are javac 21 output of
the example mod in tests/data/citadel_book/src against signature-only stubs
(Citadel's GuiBasicBook among them, absent from the classes as it is from a
real mod's jar). Rebuild with build.sh.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from portkit.bytecode import ClassIndex
from portkit.converters import books, convert_all, lang
from portkit.model import SourceMod

ROOT = Path(__file__).resolve().parents[1]
CLASSES = Path(__file__).parent / "data" / "citadel_book" / "classes"
NS = "examplemod"
LB = "~LINEBREAK~"


# -- text, as Citadel reads it ------------------------------------------------------

def test_file_lines_are_spaces_and_newline_words_are_breaks():
    raw = "<NEWLINE>\r\n<NEWLINE>\r\nFirst line\r\ncontinues here.\r\n<NEWLINE>\r\nSecond  para.\r\n<NEWLINE>\r\n<NEWLINE>\r\n"
    assert books.page_text(raw) == f"First line continues here.{LB}{LB}Second para."


def test_a_glued_newline_is_a_word_as_in_java():
    # readInPageText compares whole words: "end.<NEWLINE>" is printed as written.
    assert books.page_text("end.<NEWLINE>\nnext") == "end.<NEWLINE> next"


def test_runs_of_newlines_collapse_and_words_are_untouched():
    raw = "Ａｂ\tc  d\n<NEWLINE>\n<NEWLINE>\n<NEWLINE>\n1~3 %s"
    assert books.page_text(raw) == f"Ａｂ\tc d{LB}{LB}1~3 %s"


# -- the example book -------------------------------------------------------------------

def _write(path: Path, body) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body if isinstance(body, str) else json.dumps(body), encoding="utf-8")


def _page(text, title, parent="root.json", **extra):
    return {"parent": parent, "text": text, "title": title, "linked_page_buttons": [], "images": [],
            "item_renders": [], "recipes": [], "tabula_renders": [], "entity_renders": [], **extra}


def _mod(tmp_path: Path, classes: bool = True, book: str = "guide") -> SourceMod:
    a = tmp_path / "assets" / NS
    d = a / "book" / book
    _write(d / "root.json", {
        "parent": "", "text": "root.txt", "title": f"item.{NS}.field_guide",
        "entity_buttons": [
            {"entity": f"{NS}:owl", "x": 230, "y": 10, "page": 0, "linked_page": "owl.json",
             "hover_text": f"entity.{NS}.owl"},
            {"entity": f"{NS}:ghost", "x": 260, "y": 10, "page": 0, "linked_page": "ghost.json",
             "hover_text": f"entity.{NS}.ghost"},
        ],
        "linked_page_buttons": [{"linked_page": "about.json", "text": f"{NS}.book.about", "x": 1, "y": 1,
                                 "page": 0},
                                # a page name that can't be part of a .lang key
                                {"linked_page": "two words.json", "text": "x", "x": 1, "y": 1, "page": 0}],
        "item_renders": [{"item": f"{NS}:field_guide", "x": 25, "y": 14, "page": 0, "scale": 2}],
    })
    _write(d / "owl.json", _page("owl.txt", f"entity.{NS}.owl",
                                 entity_renders=[{"entity": f"{NS}:owl", "x": 1, "y": 1, "page": 0}],
                                 recipes=[{"recipe": f"{NS}:owl_feather", "x": 1, "y": 1, "page": 1}]))
    _write(d / "about.json", _page("about.txt", ""))
    _write(d / "two words.json", _page("about.txt", ""))
    _write(d / "hidden.json", _page("hidden.txt", f"entity.{NS}.hidden"))
    _write(d / "en_us" / "root.txt", "<NEWLINE>\nA guide to\nthe creatures.\n<NEWLINE>\nRead on.")
    _write(d / "en_us" / "owl.txt", "Owls hoot.\n<NEWLINE>\nAt night.")
    _write(d / "en_us" / "about.txt", "About this book.")
    _write(d / "en_us" / "hidden.txt", "Never shown.")
    _write(d / "de_de" / "root.txt", "Ein Führer.")
    _write(d / "es_ar" / "root.txt", "Una guía.")
    _write(d / "pictures" / "owl.png", "not really a png")
    _write(a / "lang" / "en_us.json", {f"item.{NS}.field_guide": "Field Guide", f"entity.{NS}.owl": "Owl"})
    _write(a / "lang" / "de_de.json", {f"item.{NS}.field_guide": "Feldführer"})
    return SourceMod(root=tmp_path, namespace=NS, classes=ClassIndex.from_source(CLASSES) if classes else None)


def _item(ident: str) -> dict:
    return {"format_version": "1.20.10", "minecraft:item": {"description": {"identifier": ident},
                                                            "components": {}}}


def _items(*names) -> dict:
    return {f"items/{n}.json": _item(f"{NS}:{n}") for n in names}


@pytest.fixture
def converted(tmp_path):
    mod = _mod(tmp_path)
    files = _items("field_guide", "pocket_book", "paged_item")
    plan = books.plan(mod, files)
    langs = lang.convert(mod, book_text=books.lang_text(mod, plan))
    result, entry = books.convert(mod, plan)
    return mod, plan, langs, result, entry


def test_pages_reachable_from_root_with_buttons_in_java_order(converted):
    _, _, _, result, entry = converted
    js = result.files[books.data_path(NS)]
    table = json.loads(js.split("export default ", 1)[1].rstrip().rstrip(";"))
    book = table["books"][f"{NS}:guide"]
    assert sorted(book["pages"]) == ["about", "owl", "root"]
    root = book["pages"]["root"]
    # linked_page_buttons, then entity_buttons (addLinkButtons); ghost.json isn't in the jar.
    assert root["links"] == [["about", f"{NS}.book.about"], ["owl", f"entity.{NS}:owl.name"]]
    assert root["title"] == f"item.{NS}:field_guide.name" and root["parent"] is None
    assert book["pages"]["owl"] == {"title": f"entity.{NS}:owl.name",
                                    "body": f"portkit.book.{NS}.guide.owl", "parent": "root", "links": []}
    # an empty title stays empty; a title key en_us lacks is kept as the Java key
    assert book["pages"]["about"]["title"] is None
    assert table["back"] == "gui.back"
    assert table["items"] == {f"{NS}:field_guide": f"{NS}:guide"}
    assert 'registerBooks(booksTable)' in entry and f"./data/{NS}_books.js" in entry
    assert result.files["scripts/portkit/book.js"] == books_runtime("book.js")


def books_runtime(name):
    return (ROOT / "src" / "portkit" / "runtime" / name).read_text(encoding="utf-8")


def test_text_ships_per_locale_with_the_en_us_fallback(converted):
    _, _, langs, _, _ = converted
    en = langs.files["texts/en_US.lang"].splitlines()
    de = langs.files["texts/de_DE.lang"].splitlines()
    key = f"portkit.book.{NS}.guide"
    assert f"{key}.root=A guide to the creatures.{LB}{LB}Read on." in en
    assert f"{key}.owl=Owls hoot.{LB}{LB}At night." in en
    # de_de has its own root text; its other pages fall back to en_us (refreshSpacing)
    assert f"{key}.root=Ein Führer." in de and f"{key}.owl=Owls hoot.{LB}{LB}At night." in de
    # the mod's own strings are still there; an unreachable page's text never ships
    assert f"item.{NS}:field_guide.name=Feldführer" in de
    assert not any("hidden" in line for line in en)
    # es_ar has no Bedrock locale; no file appears for it
    assert langs.files["texts/languages.json"] == ["en_US", "de_DE"]


def test_what_the_viewer_does_not_carry_is_residue_or_noted(converted):
    mod, _, _, result, _ = converted
    reasons = {u.source: (u.reason, u.count) for u in result.unhandled}
    base = f"assets/{NS}/book/guide"
    assert reasons[f"{base}/es_ar/"][1] == 1 and "no locale matching 'es_ar'" in reasons[f"{base}/es_ar/"][0]
    assert reasons[f"{base}/hidden.json"] == (
        "no button or parent reaches this page from root.json, in Java either (with its text in 1 locale "
        "folder(s))", 2)
    assert "pictures and other assets stay residue" in reasons[f"{base}/pictures/owl.png"][0]
    # every file of the book is accounted for
    every = {str(p.relative_to(mod.root)) for p in (mod.root / base).rglob("*") if p.is_file()}
    assert every <= result.consumed
    note = next(n for n in result.notes if n.startswith(f"{NS}:guide:"))
    assert "1 entity renders, 1 item renders, 1 recipes" in note
    assert "ghost.json" in note and "two words.json" in note and "read from bytecode" in note
    assert f"{base}/two words.json" in reasons  # unreachable once its button is dropped


# -- which item opens the book ----------------------------------------------------------

def test_screens_name_their_root_page():
    screens = books.book_screens(ClassIndex.from_source(CLASSES))
    assert screens == {
        "com/example/books/GuideScreen": f"{NS}:book/guide/root.json",   # static field in <clinit>
        "com/example/books/PocketScreen": f"{NS}:book/pocket/root.json",  # built in the method
        "com/example/books/PagedScreen": f"{NS}:book/paged/root.json",
    }


def test_items_whose_use_builds_the_screen_at_its_root():
    classes = ClassIndex.from_source(CLASSES)
    found = books.book_items(classes, books.book_screens(classes))
    assert found["com/example/books/GuideItem"] == (
        "com/example/books/GuideScreen",
        "com.example.books.GuideItem#use -> com.example.books.ClientProxy#openGuide")
    assert found["com/example/books/PocketItem"] == ("com/example/books/PocketScreen",
                                                     "com.example.books.PocketItem#use")
    # opened at a named page through the (ItemStack, String) constructor: not the book's opener
    assert "com/example/books/PagedItem" not in found


def test_binding_reads_the_registered_name_and_labels_the_default(tmp_path):
    mod = _mod(tmp_path)
    for name in ("pocket", "paged"):
        shutil.copytree(mod.assets / "book" / "guide", mod.assets / "book" / name)
    plan = books.plan(mod, _items("field_guide", "pocket_book", "paged_item", "paged"))
    assert plan.items["guide"][0] == [f"{NS}:field_guide"]
    assert plan.items["pocket"][0] == [f"{NS}:pocket_book"]
    ids, how = plan.items["paged"]
    assert ids == [f"{NS}:paged"] and how.startswith(f"{NS}:paged (DEFAULT: named like the book directory")


def test_without_classes_the_default_binding_needs_an_item_of_that_name(tmp_path):
    mod = _mod(tmp_path, classes=False)
    plan = books.plan(mod, _items("field_guide"))
    result, entry = books.convert(mod, plan)
    assert entry == "" and books.data_path(NS) not in result.files
    (residue,) = [u for u in result.unhandled if u.kind == "book"]
    assert residue.source == f"assets/{NS}/book/guide/" and "no converted item opens this book" in residue.reason
    assert residue.count == 12
    assert books.lang_text(mod, plan) == {}
    plan = books.plan(mod, _items("guide"))
    assert plan.items["guide"][0] == [f"{NS}:guide"] and "DEFAULT" in plan.items["guide"][1]


def test_a_non_citadel_book_directory_is_left_alone(tmp_path):
    # Mantle (Tinkers') books have no root.json page: nothing claims them here.
    _write(tmp_path / "assets" / NS / "book" / "encyclopedia" / "index.json", {"sections": []})
    mod = SourceMod(root=tmp_path, namespace=NS)
    assert books.plan(mod, {}) is None


def test_convert_all_wires_the_viewer_into_main(tmp_path):
    mod = _mod(tmp_path)
    a = mod.assets
    _write(a / "models" / "item" / "field_guide.json",
           {"parent": "minecraft:item/generated", "textures": {"layer0": f"{NS}:item/field_guide"}})
    result = convert_all(mod)
    assert f"items/field_guide.json" in result.files
    main = result.files["scripts/portkit/main.js"]
    assert "registerBooks(booksTable);" in main
    assert "scripts/portkit/station_storage.js" not in result.files
    assert any(line.startswith(f"portkit.book.{NS}.guide.root=") for line in
               result.files["texts/en_US.lang"].splitlines())


# -- the viewer, under node ---------------------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_viewer_runs_under_node_on_the_generated_table(converted, tmp_path):
    _, _, _, result, _ = converted
    table = tmp_path / "books.js"
    table.write_text(result.files[books.data_path(NS)], encoding="utf-8")
    env = dict(os.environ, PORTKIT_BOOK_TABLE=str(table))
    run = subprocess.run(["node", "--import", "./tests/js/register.mjs", "--test", "tests/js/book.test.mjs"],
                         cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stdout + run.stderr
