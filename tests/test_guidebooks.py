"""#182 (pending Alex, picks 1a-3a): a guide book no converter reads is the explained ``guidebook``.

1a. Detected from the file layout of an ``assets/<ns>/<dir>/`` folder Minecraft's
    client doesn't read: documents (and the pictures and structures pages show)
    in per-language folders (``en_us``, or two or more locale folders), or
    markdown pages; plus the same-named ``data/<ns>/<dir>/`` JSON half. The
    reader is named from the jar (classes naming the folder as a path, the
    required dependencies they call or whose id begins the folder name).
2a. Nothing is converted (the pack is byte-identical).
3a. Each file counts once, as it did while ``unowned``.

Offline, ``examplemod`` only; no mod names (#220).
"""
import json
from pathlib import Path

from portkit import guidebooks, worldgen
from portkit.agent.residue import SKIP_KINDS
from portkit.model import Unhandled
from portkit.pipeline import unowned


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(body, bytes):
        path.write_bytes(body)
    elif isinstance(body, str):
        path.write_text(body)
    else:
        path.write_text(json.dumps(body))


class _CF:
    def __init__(self, strings):
        self.pool = [None] + [("utf8", s) for s in strings]
        self._strings = [None] + list(strings)
        self.super_name = "java/lang/Object"

    def constant(self, i):
        return self._strings[i]


class _Classes:
    def __init__(self, classes):
        self._c = classes

    def names(self):
        return sorted(self._c)

    def get(self, name, remap=True):
        return self._c.get(name)


_NONE = _Classes({"com/example/Mod": _CF(["examplemod"])})


def _refine(root, classes=_NONE, requires=None, consumed=frozenset()):
    return guidebooks.refine(unowned(root, set(consumed)), root, set(consumed), classes, requires)


def _entry(out, source):
    return next(u for u in out if u.source == source)


def _book(root, folder="guide"):
    _write(root, f"assets/examplemod/{folder}/book/en_us/entries/intro.json", {"name": "Intro", "pages": []})
    _write(root, f"assets/examplemod/{folder}/book/en_us/categories/basics.json", {"name": "Basics"})
    _write(root, f"assets/examplemod/{folder}/book/de_de/entries/intro.json", {"name": "Einleitung"})
    _write(root, f"assets/examplemod/{folder}/book/images/diagram.png", b"\x89PNG\r\n\x1a\n")


def test_kind_is_explained():
    assert guidebooks.GUIDEBOOK == "guidebook"
    assert "guidebook" in SKIP_KINDS


def test_per_language_pages_are_a_guidebook(tmp_path):
    _book(tmp_path)
    out, files = _refine(tmp_path)
    entry = _entry(out, "assets/examplemod/guide/")
    assert entry.kind == "guidebook"
    assert entry.count == 4  # every file, pictures included (3a)
    assert len(files) == 4
    assert "3 page document(s) in per-language folders (2 language(s): de_de, en_us)" in entry.reason
    assert "1 other file(s) its pages use (json, png)" in entry.reason
    assert "no class of the jar names `guide` as a path" in entry.reason
    assert "Java may never open these pages" in entry.reason
    assert "#87" in entry.reason
    assert not [u for u in out if u.kind == "unowned"]


def test_two_locale_folders_without_en_us(tmp_path):
    _write(tmp_path, "assets/examplemod/manual_old/de_de/intro.txt", "Hallo")
    _write(tmp_path, "assets/examplemod/manual_old/fr_fr/intro.txt", "Bonjour")
    out, _ = _refine(tmp_path)
    assert _entry(out, "assets/examplemod/manual_old/").kind == "guidebook"


def test_one_foreign_locale_alone_is_not_enough(tmp_path):
    _write(tmp_path, "assets/examplemod/notes/de_de/intro.txt", "Hallo")
    out, files = _refine(tmp_path)
    assert _entry(out, "assets/examplemod/notes/").kind == "unowned"
    assert not files


def test_markdown_pages_are_a_guidebook(tmp_path):
    _write(tmp_path, "assets/examplemod/docs/index.md", "---\nnavigation:\n  title: Index\n---\n# Hi\n")
    _write(tmp_path, "assets/examplemod/docs/machines/press.md", "# Press\n")
    _write(tmp_path, "assets/examplemod/docs/assets/press.snbt", "{}")
    out, _ = _refine(tmp_path)
    entry = _entry(out, "assets/examplemod/docs/")
    assert entry.kind == "guidebook" and entry.count == 3
    assert "2 markdown page(s), a format no part of Minecraft reads" in entry.reason


def test_other_file_types_keep_the_folder_unowned(tmp_path):
    _book(tmp_path)
    _write(tmp_path, "assets/examplemod/guide/book/sound.ogg", b"OggS")
    out, files = _refine(tmp_path)
    assert _entry(out, "assets/examplemod/guide/").kind == "unowned"
    assert not files


def test_json_without_a_layout_is_not_a_guide(tmp_path):
    _write(tmp_path, "assets/examplemod/connect_rules/bed.json", {"blocks": []})
    out, _ = _refine(tmp_path)
    assert _entry(out, "assets/examplemod/connect_rules/").kind == "unowned"


def test_client_folders_are_never_guides(tmp_path):
    # lang/ and texts/ are Minecraft's own per-language folders.
    _write(tmp_path, "assets/examplemod/texts/en_us/end.txt", "words")
    out, files = _refine(tmp_path)
    assert not files
    assert _entry(out, "assets/examplemod/texts/").kind == "unowned"


def test_a_folder_a_converter_read_is_left_alone(tmp_path):
    # A converter (a book reader) read part of it: its leftovers are its business.
    _book(tmp_path)
    consumed = {"assets/examplemod/guide/book/en_us/entries/intro.json"}
    out, files = _refine(tmp_path, consumed=consumed)
    assert not files
    assert _entry(out, "assets/examplemod/guide/").kind == "unowned"


def test_reader_classes_and_dependencies_are_named(tmp_path):
    _book(tmp_path)
    classes = _Classes({
        "com/example/client/GuideLoader": _CF(["guide/book/", "examplemod:guide/book/index",
                                               "org/booklib/api/BookScreen"]),
        "com/example/items/GuideItem": _CF(["guide"]),
        "com/example/Unrelated": _CF(["guidebook", "guides/x"]),
    })
    out, _ = _refine(tmp_path, classes, requires=["minecraft", "neoforge", "booklib"])
    reason = _entry(out, "assets/examplemod/guide/").reason
    assert ("the jar's classes naming `guide` as a path: com/example/client/GuideLoader, "
            "com/example/items/GuideItem") in reason
    assert "Unrelated" not in reason
    assert "calling into the required dependency `booklib`" in reason
    assert "never open" not in reason


def test_folder_named_after_a_dependency(tmp_path):
    _book(tmp_path, folder="booklib_books")
    out, _ = _refine(tmp_path, requires=["forge", "booklib"])
    reason = _entry(out, "assets/examplemod/booklib_books/").reason
    assert "the folder is named after the required dependency `booklib`, which reads it" in reason
    assert "never open" not in reason


def test_data_half_goes_with_the_guide(tmp_path):
    _book(tmp_path, folder="booklib_books")
    _write(tmp_path, "data/examplemod/booklib_books/book/book.json", {"name": "item.examplemod.guide"})
    out, files = _refine(tmp_path, requires=["booklib"])
    data = _entry(out, "data/examplemod/booklib_books/")
    assert data.kind == "guidebook" and data.count == 1
    assert "the data half of the guide book in assets/examplemod/booklib_books/" in data.reason
    assert "data/examplemod/booklib_books/book/book.json" in files


def test_a_data_folder_without_a_guide_is_untouched(tmp_path):
    _write(tmp_path, "data/examplemod/booklib_books/book/book.json", {"name": "x"})
    out, files = _refine(tmp_path)
    assert not files
    assert _entry(out, "data/examplemod/booklib_books/").kind == "unowned"


def test_guidebook_wins_over_other_mod_data(tmp_path):
    # An all-JSON guide folder no class names would otherwise be #346's
    # other_mod_data; the pipeline runs this pass first and hands worldgen
    # the re-filed paths.
    _write(tmp_path, "assets/examplemod/booklib_books/book/en_us/entries/a.json", {"name": "A"})
    _write(tmp_path, "assets/examplemod/booklib_books/book/en_us/entries/b.json", {"name": "B"})
    _write(tmp_path, "assets/examplemod/connect_rules/bed.json", {"blocks": []})
    out, files = _refine(tmp_path, requires=["booklib"])
    out = worldgen.refine(out, tmp_path, set() | files, {"examplemod"}, _NONE)
    kinds = {(u.source, u.kind, u.count) for u in out}
    assert ("assets/examplemod/booklib_books/", "guidebook", 2) in kinds
    assert ("assets/examplemod/connect_rules/", "other_mod_data", 1) in kinds
    assert not any(u.kind == "other_mod_data" and "booklib_books" in u.source for u in out)


def test_counts_are_kept(tmp_path):
    # Re-filing only (3a): the residue file total doesn't move.
    _book(tmp_path)
    _write(tmp_path, "assets/examplemod/other/thing.bin", b"x")
    before = unowned(tmp_path, set())
    out, _ = guidebooks.refine(before, tmp_path, set(), _NONE, None)
    assert sum(u.count for u in out) == sum(u.count for u in before)


def test_nothing_to_do_returns_input(tmp_path):
    entries = [Unhandled("data/examplemod/recipes/a.json", "recipe", "refused", 1)]
    out, files = guidebooks.refine(entries, tmp_path, set(), None, None)
    assert out == entries and files == set()


def test_pipeline_ships_nothing_from_a_guide(tmp_path):
    from portkit.pipeline import convert

    src = tmp_path / "src"
    _write(src, "assets/examplemod/lang/en_us.json", {"item.examplemod.thing": "Thing"})
    _book(src)
    _write(src, "META-INF/mods.toml",
           'modLoader="javafml"\nloaderVersion="[47,)"\nlicense="MIT"\n[[mods]]\nmodId="examplemod"\n'
           'version="1.0"\ndisplayName="Example"\n')
    res = convert(src, tmp_path / "out", emit_addon=False)
    guide = [u for u in res.unhandled if u.kind == "guidebook"]
    assert [(u.source, u.count) for u in guide] == [("assets/examplemod/guide/", 4)]
    shipped = [p for p in (tmp_path / "out").rglob("*") if p.is_file() and "guide" in p.as_posix()]
    assert not shipped
