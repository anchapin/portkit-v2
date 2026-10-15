"""Guide books whose pages are data in the jar (#182, first slice: Citadel books).

Citadel's ``GuiBasicBook`` is the book screen Alex's Mobs' Animal Dictionary
(and other Citadel mods' books) is drawn with. Everything that varies is data
in the jar, under ``assets/<ns>/book/<book>/``:

* ``root.json`` and one JSON file per page (``BookPage``): the page's
  ``title`` (a translation key), ``text`` (the name of its text file),
  ``parent`` (the page the previous-page arrow goes back to from the first
  sheet), ``linked_page_buttons`` (``linked_page`` + ``text`` key) and
  ``entity_buttons`` (``linked_page`` + ``hover_text`` key) that open other
  pages, and pictures: ``images``, ``item_renders``, ``recipes``,
  ``entity_renders``, ``tabula_renders``.
* ``<locale>/<text>``: the page's text, one file per Java locale. Citadel
  reads the file for the game's language and falls back to ``en_us`` when
  that file is missing (``GuiBasicBook.refreshSpacing``).

The screen itself is Java, so the conversion splits it the way the station
runtimes do (docs/decisions.md, 2026-10-15 guide books):

* **Text, generated.** Each page's text becomes one Bedrock ``.lang`` entry
  per locale the pack ships (``portkit.book.<ns>.<book>.<page>``), read the
  way Citadel reads it (``GuiBasicBook.readInPageText``): every line of the
  file split on spaces into one run of words (a line break in the file is
  not a break on the page); the word ``<NEWLINE>`` ends the line and leaves
  a blank one. The words are kept verbatim; only the layout is the form's:
  runs of ``<NEWLINE>`` (Citadel's room around pictures) become one blank
  line, and empty words (double spaces) are dropped. Nothing is summarised
  or rewritten (#87). A Bedrock locale with no text file of its own gets the
  ``en_us`` text, Citadel's fallback.
* **Pages, generated.** A data module (``scripts/portkit/data/<ns>_books.js``)
  lists every page reachable from ``root.json`` (through its buttons and
  parents): title key, text key, parent and buttons in the order Java creates
  them (``linked_page_buttons`` then ``entity_buttons``, file order).
* **Viewer, fixed.** ``portkit/runtime/book.js`` (``@minecraft/server`` 2.0.0
  ``world.afterEvents.itemUse``, ``@minecraft/server-ui`` ``ActionFormData``)
  shows a page as a form: the title, the text as its body, one button per
  link labelled with the link's own translation key, and a back button (the
  vanilla ``gui.back`` string) to the page's parent.
* **Which item opens it, from bytecode.** A class extending ``GuiBasicBook``
  names its book in ``getRootPage``; the item whose ``use`` builds that screen
  with its one-argument ``(ItemStack)`` constructor (directly, or through a
  proxy method whose override does) is found in the classes, and its
  registered name read with :mod:`portkit.blockcode`'s registration reader.
  Without an answer from the classes, the book is bound to the item named
  like the book directory, labelled DEFAULT in the note.

Not carried, and said so per book: pictures (images, item, entity and Tabula
model renders, recipe grids), entity pictures on index buttons and their
hover tooltips, Java's two-page spread and pagination (a form scrolls), and
whatever else the item's Java code does on use (statistics, the advancement
trigger, opening a mob's page when used on it). Locales Bedrock has no
counterpart for, pages no button reaches, and files that aren't pages or
text stay residue.

Sources: Citadel 1.20 @8c09dce (AlexModGuy/Citadel), GuiBasicBook.java
(refreshSpacing L311-331, readInPageText L605-690, onSwitchPage L262-280,
addLinkButtons L222-260) and BookPage.java (Deserializer L101-136).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..model import ConversionResult, SourceMod, Unhandled
from .lang import _LOCALES, _LINEBREAK, _translate_key

CITADEL = ("https://github.com/AlexModGuy/Citadel", "8c09dce8a1574d210de72eb0bf5874fe1dc6532e")
SOURCES = (
    f"{CITADEL[0]}/blob/{CITADEL[1]}/src/main/java/com/github/alexthe666/citadel/client/gui/"
    "GuiBasicBook.java#L311-L331 (refreshSpacing: language file, en_us fallback)",
    f"{CITADEL[0]}/blob/{CITADEL[1]}/src/main/java/com/github/alexthe666/citadel/client/gui/"
    "GuiBasicBook.java#L605-L690 (readInPageText: words split on spaces, <NEWLINE>)",
    f"{CITADEL[0]}/blob/{CITADEL[1]}/src/main/java/com/github/alexthe666/citadel/client/gui/"
    "GuiBasicBook.java#L262-L280 (onSwitchPage: back to parent from the first sheet)",
    f"{CITADEL[0]}/blob/{CITADEL[1]}/src/main/java/com/github/alexthe666/citadel/client/gui/"
    "BookPage.java#L101-L136 (page JSON keys)",
)

SCREEN = "com/github/alexthe666/citadel/client/gui/GuiBasicBook"
_ROOT_PAGE = ("getRootPage", "()Lnet/minecraft/resources/ResourceLocation;")
# Item#use(Level, Player, InteractionHand), Mojang names (Forge/NeoForge); the
# return type changed in 1.21.2, so only the arguments are matched.
_USE_ARGS = ("(Lnet/minecraft/world/level/Level;Lnet/minecraft/world/entity/player/Player;"
             "Lnet/minecraft/world/InteractionHand;)")
# The screen constructor that opens the book at its root page.
_STACK_CTOR = "(Lnet/minecraft/world/item/ItemStack;)V"
_INVOKES = (0xB6, 0xB7, 0xB8, 0xB9)

NEWLINE = "<NEWLINE>"
BACK_KEY = "gui.back"  # vanilla Bedrock: gui.back=Back (bedrock-samples v1.26.50.4 texts/en_US.lang)
RESIDUE_KIND = "book"
RUNTIME_DIR = "scripts/portkit"
_PRIMARY = "en_us"
_PAGE_KEYS = frozenset({"parent", "text", "title", "linked_page_buttons", "entity_buttons"})
_PICTURES = ("images", "item_renders", "recipes", "entity_renders", "tabula_renders")
_JAVA_LINES = re.compile(r"\r\n|\r|\n")  # BufferedReader.readLine's line ends
_KEY_SAFE = re.compile(r"^[^\s=#]+$")


def data_path(namespace: str) -> str:
    return f"{RUNTIME_DIR}/data/{namespace}_books.js"


def text_key(namespace: str, book: str, page: str) -> str:
    return f"portkit.book.{namespace}.{book}.{page}"


def page_text(raw: str) -> str:
    """A text file as Citadel lays it out, as one .lang value.

    readInPageText splits every line on " " into one list of words; the word
    ``<NEWLINE>`` (exactly) ends the line and skips one more, anything else is
    printed in order. Here a run of ``<NEWLINE>`` is one blank line, empty
    words are dropped, and the text is trimmed; the words are untouched.
    """
    paragraphs: list[str] = []
    words: list[str] = []
    for line in _JAVA_LINES.split(raw):
        for word in line.split(" "):
            if word == NEWLINE:
                if words:
                    paragraphs.append(" ".join(words))
                    words = []
            elif word:
                words.append(word)
    if words:
        paragraphs.append(" ".join(words))
    return (_LINEBREAK * 2).join(paragraphs)


@dataclass
class Page:
    name: str
    title: str
    parent: str | None
    text: str
    links: list[tuple[str, str]]
    pictures: dict[str, int]


@dataclass
class Book:
    """One Citadel book directory, read."""

    name: str
    rel: str
    pages: dict[str, Page] = field(default_factory=dict)
    # Java locale -> page -> .lang value, for the reachable pages' text files.
    texts: dict[str, dict[str, str]] = field(default_factory=dict)
    consumed: set[str] = field(default_factory=set)
    unhandled: list[Unhandled] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    dropped_links: list[str] = field(default_factory=list)


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _is_citadel_page(body) -> bool:
    return isinstance(body, dict) and bool(_PAGE_KEYS & set(body))


def _stem(file_name: str) -> str | None:
    """A linked page's name: Citadel resolves it below the book directory."""
    if not isinstance(file_name, str) or not file_name.endswith(".json") or "/" in file_name:
        return None
    stem = file_name[:-5]
    # The stem is part of a .lang key: no whitespace, "=" or "#" (one key=value line).
    return stem if _KEY_SAFE.match(stem) else None


def _links(body: dict) -> list[tuple[str, str]]:
    out = []
    for kind, label in (("linked_page_buttons", "text"), ("entity_buttons", "hover_text")):
        for button in body.get(kind) or []:
            if isinstance(button, dict):
                out.append((button.get("linked_page"), button.get(label) or ""))
    return out


def book_dirs(mod: SourceMod) -> list[Path]:
    """Directories under assets/<ns>/book/ whose root.json is a Citadel page."""
    base = mod.assets / "book"
    if not base.is_dir():
        return []
    return [d for d in sorted(base.iterdir())
            if d.is_dir() and _is_citadel_page(_load(d / "root.json"))]


def read_book(mod: SourceMod, directory: Path) -> Book:
    book = Book(name=directory.name, rel=str(directory.relative_to(mod.root)))
    queue = ["root"]
    while queue:
        name = queue.pop(0)
        if name in book.pages:
            continue
        path = directory / f"{name}.json"
        body = _load(path)
        if not _is_citadel_page(body):
            continue
        book.consumed.add(str(path.relative_to(mod.root)))
        links = []
        for target, label in _links(body):
            stem = _stem(target)
            if stem is None or not _is_citadel_page(_load(directory / f"{stem}.json")):
                book.dropped_links.append(f"{name}.json -> {target}")
                continue
            links.append((stem, label if isinstance(label, str) else ""))
            queue.append(stem)
        parent = _stem(body.get("parent") or "") if body.get("parent") else None
        if parent is not None and _is_citadel_page(_load(directory / f"{parent}.json")):
            queue.append(parent)
        else:
            parent = None
        text = body.get("text") if isinstance(body.get("text"), str) else ""
        if "/" in text or "\\" in text or text in (".", ".."):
            text = ""  # a text file name, below each locale folder; nothing else is read
        book.pages[name] = Page(
            name=name, title=body.get("title") if isinstance(body.get("title"), str) else "",
            parent=parent, text=text, links=links,
            pictures={kind: len(body.get(kind) or []) for kind in _PICTURES if isinstance(body.get(kind), list)},
        )

    # Text files of the reachable pages, per locale folder.
    for sub in sorted(p for p in directory.iterdir() if p.is_dir()):
        locale = sub.name.lower()
        for name, page in book.pages.items():
            if not page.text:
                continue
            path = sub / page.text
            if not path.is_file():
                continue
            book.consumed.add(str(path.relative_to(mod.root)))
            try:
                raw = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                book.unhandled.append(Unhandled(str(path.relative_to(mod.root)), RESIDUE_KIND,
                                                f"page text can't be read as UTF-8 ({exc})"))
                continue
            book.texts.setdefault(locale, {})[name] = page_text(raw)
    return book


def _leftovers(mod: SourceMod, book: Book, directory: Path) -> None:
    """Every file of the book directory the viewer doesn't carry, as residue."""
    unmapped: dict[str, int] = {}
    unreachable, other = [], []
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        rel = str(path.relative_to(mod.root))
        inside = path.relative_to(directory).parts
        if len(inside) == 2 and inside[0].lower() not in _LOCALES and rel in book.consumed:
            unmapped[inside[0]] = unmapped.get(inside[0], 0) + 1
            continue
        if rel in book.consumed:
            continue
        if len(inside) == 1 and path.suffix == ".json" and _is_citadel_page(_load(path)):
            unreachable.append(rel)
        else:
            other.append(rel)
    # An unreachable page's own text files are reported with it.
    texts_of = {}
    for rel in unreachable:
        body = _load(mod.root / rel) or {}
        text = body.get("text") if isinstance(body.get("text"), str) else None
        texts_of[rel] = [o for o in other if text and o.endswith(f"/{text}")
                         and len(Path(o).relative_to(book.rel).parts) == 2]
        other = [o for o in other if o not in texts_of[rel]]
    for locale, count in sorted(unmapped.items()):
        book.unhandled.append(Unhandled(
            f"{book.rel}/{locale}/", RESIDUE_KIND,
            f"Bedrock has no locale matching {locale.lower()!r}, so this book text can't ship for it "
            "(players in a Bedrock language get its own folder's text or en_us)", count))
    for rel in unreachable:
        book.consumed.add(rel)
        book.consumed |= set(texts_of[rel])
        book.unhandled.append(Unhandled(rel, RESIDUE_KIND, (
            "no button or parent reaches this page from root.json, in Java either"
            + (f" (with its text in {len(texts_of[rel])} locale folder(s))" if texts_of[rel] else "")),
            1 + len(texts_of[rel])))
    for rel in other:
        book.consumed.add(rel)
        book.unhandled.append(Unhandled(rel, RESIDUE_KIND, (
            "not a page or a reachable page's text file; the book viewer carries text only "
            "(pictures and other assets stay residue)")))


# -- which item opens the book ------------------------------------------------------

def _chain(classes, name: str) -> list[str]:
    out, seen = [], set()
    while name and name not in seen:
        seen.add(name)
        out.append(name)
        cf = classes.get(name)
        if cf is None:
            break
        name = cf.super_name
    return out


def _code(classes, cf, method):
    from ..bytecode import instructions
    try:
        return instructions(cf, method.code) if method.code else []
    except Exception:  # an undecodable method answers nothing
        return []


def book_screens(classes) -> dict[str, str]:
    """Each GuiBasicBook subclass in the classes -> the root page its
    getRootPage names (``ns:book/<book>/root.json``), when that is one string."""
    out = {}
    for cname in classes.names():
        if SCREEN not in _chain(classes, cname)[1:]:
            continue
        cf = classes.get(cname)
        method = cf.method(*_ROOT_PAGE) if cf else None
        if method is None:
            continue
        code = _code(classes, cf, method)
        strings = [i.arg for i in code if i.op in (0x12, 0x13) and isinstance(i.arg, str)]
        fields = [i.arg for i in code if i.op == 0xB2 and getattr(i.arg, "owner", None) == cname]
        if not strings and len(fields) == 1:
            # return ROOT, a static final set in <clinit> from one string
            strings = _static_strings(classes, cf, fields[0].name)
        if len(strings) == 1:
            out[cname] = strings[0]
    return out


def _static_strings(classes, cf, name: str) -> list[str]:
    """The string constant last loaded before each ``putstatic name`` in the
    class initializer (``new ResourceLocation("...")``)."""
    init = cf.method("<clinit>")
    found, last = [], None
    for insn in _code(classes, cf, init) if init else []:
        if insn.op in (0x12, 0x13) and isinstance(insn.arg, str):
            last = insn.arg
        elif insn.op == 0xB3 and getattr(insn.arg, "name", None) == name and insn.arg.owner == cf.name:
            if last is not None:
                found.append(last)
            last = None
    return found


def _builds(classes, cf, method, screens) -> set[str]:
    """Screens ``method`` builds with their (ItemStack) constructor."""
    return {i.arg.owner for i in _code(classes, cf, method)
            if i.op == 0xB7 and getattr(i.arg, "name", None) == "<init>"
            and i.arg.owner in screens and i.arg.desc == _STACK_CTOR}


def book_items(classes, screens: dict[str, str]) -> dict[str, tuple[str, str]]:
    """Item classes whose use opens a book screen at its root -> (screen, how)."""
    openers: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for cname in classes.names():
        cf = classes.get(cname)
        if cf is None:
            continue
        for method in cf.methods:
            for screen in _builds(classes, cf, method, screens):
                openers.setdefault((method.name, method.desc), []).append((cname, screen))
    out = {}
    for cname in classes.names():
        cf = classes.get(cname)
        if cf is None or not cf.super_name:
            continue
        found: set[tuple[str, str]] = set()
        for owner in _chain(classes, cname):
            ocf = classes.get(owner)
            if ocf is None:
                break
            for method in ocf.methods:
                if not method.desc.startswith(_USE_ARGS):
                    continue
                where = f"{owner.replace('/', '.')}#{method.name}"
                for screen in _builds(classes, ocf, method, screens):
                    found.add((screen, where))
                for insn in _code(classes, ocf, method):
                    ref = insn.arg
                    if insn.op not in _INVOKES or not hasattr(ref, "desc"):
                        continue
                    for opener_cls, screen in openers.get((ref.name, ref.desc), []):
                        if ref.owner in _chain(classes, opener_cls):
                            found.add((screen, f"{where} -> {opener_cls.replace('/', '.')}#{ref.name}"))
            if found:
                break
        if len({s for s, _ in found}) == 1:
            screen, how = sorted(found)[0]
            out[cname] = (screen, how)
    return out


def _registered_items(classes, item_names: list[str], wanted: set[str]) -> dict[str, list[str]]:
    """Item class -> the registered names that build it (portkit.blockcode)."""
    from ..blockcode import Lam, Machine, Obj, Unreadable, _wanted_classes

    machine = Machine(classes)
    machine.registrations = []
    for cname in _wanted_classes(classes, set(item_names)):
        machine.steps = 0
        try:
            machine.init_class(cname)
        except Unreadable:
            continue
    regs = list(machine.registrations)
    machine.registrations = None
    out: dict[str, list[str]] = {}
    for reg in regs:
        if reg.value is None or reg.name not in item_names:
            continue
        machine.steps = 0
        machine.new_epoch()
        try:
            built = machine.call_lambda(reg.value, []) if isinstance(reg.value, Lam) else [reg.value]
        except Unreadable:
            continue
        for obj in built:
            if isinstance(obj, Obj) and obj.cls in wanted:
                out.setdefault(obj.cls, []).append(reg.name)
    return out


def bind_items(mod: SourceMod, books: list[Book], item_ids: set[str]) -> dict[str, tuple[list[str], str]]:
    """Book name -> (item ids that open it, how that was decided)."""
    ns = mod.namespace
    root_of = {f"{ns}:book/{b.name}/root.json": b.name for b in books}
    out: dict[str, tuple[list[str], str]] = {}
    classes = mod.classes
    if classes is not None and len(classes):
        screens = {c: root_of[r] for c, r in book_screens(classes).items() if r in root_of}
        if screens:
            items = book_items(classes, screens)
            names = sorted(i.split(":", 1)[1] for i in item_ids if i.startswith(f"{ns}:"))
            registered = _registered_items(classes, names, set(items)) if items else {}
            for item_cls, (screen, how) in sorted(items.items()):
                book = screens[screen]
                for name in sorted(set(registered.get(item_cls, []))):
                    ids, hows = out.get(book, ([], ""))
                    out[book] = (sorted({*ids, f"{ns}:{name}"}),
                                 "; ".join(filter(None, [hows, f"{ns}:{name} ({how}, builds "
                                                          f"{screen.replace('/', '.')}; read from bytecode)"])))
    for book in books:
        if book.name in out:
            continue
        guess = f"{ns}:{book.name}"
        if guess in item_ids:
            out[book.name] = ([guess], (
                f"{guess} (DEFAULT: named like the book directory; no item class whose use opens this "
                "book's screen was found in the mod's classes)"))
    return out


# -- conversion -----------------------------------------------------------------------

def _shipped_key(entries: dict, ns: str, java_key: str) -> str:
    """The .lang key for a Java key: its Bedrock name when the jar's en_us
    defines it and the lang converter translates it, else the Java key as-is
    (what Java's I18n shows for a missing key too)."""
    if java_key in entries:
        translated = _translate_key(java_key, ns)
        if translated is not None:
            return translated
    return java_key


@dataclass
class Plan:
    """A mod's Citadel books, read, with the items that open each."""

    books: list[Book]
    items: dict[str, tuple[list[str], str]]


def plan(mod: SourceMod, files: dict) -> Plan | None:
    """Read every Citadel book of the mod and bind it to its items; ``files``
    is what the namespace's converters wrote so far (the items must be in it).
    None when the mod has no Citadel book."""
    directories = book_dirs(mod)
    if not directories:
        return None
    item_ids = {(((body.get("minecraft:item") or {}).get("description") or {}).get("identifier"))
                for path, body in files.items() if path.startswith("items/") and isinstance(body, dict)}
    item_ids.discard(None)
    books = []
    for directory in directories:
        book = read_book(mod, directory)
        _leftovers(mod, book, directory)
        books.append(book)
    return Plan(books=books, items=bind_items(mod, books, item_ids))


def lang_text(mod: SourceMod, book_plan: Plan | None) -> dict[str, dict[str, str]]:
    """Java locale -> {.lang key: page text} for every book an item opens
    (the lang converter writes them into each Bedrock locale it ships)."""
    out: dict[str, dict[str, str]] = {}
    for book in book_plan.books if book_plan else []:
        if not book_plan.items.get(book.name, ([], ""))[0]:
            continue
        for locale, pages in book.texts.items():
            for page, text in pages.items():
                if text:
                    out.setdefault(locale, {})[text_key(mod.namespace, book.name, page)] = text
    return out


def convert(mod: SourceMod, book_plan: Plan | None) -> tuple[ConversionResult, str]:
    """Each Citadel book's page table and the fixed viewer, plus the entry line
    that wires them (stations.convert writes it into scripts/portkit/main.js)."""
    from .station_kit import FORMS, runtime_source

    result = ConversionResult()
    if book_plan is None:
        return result, ""
    ns = mod.namespace
    entries = _load(mod.assets / "lang" / "en_us.json") or {}
    table = {"back": BACK_KEY, "books": {}, "items": {}}
    for book in book_plan.books:
        book_id = f"{ns}:{book.name}"
        items, how = book_plan.items.get(book.name, ([], ""))
        if not items:
            files_in = sum(1 for p in (mod.root / book.rel).rglob("*") if p.is_file())
            result.consumed |= {str(p.relative_to(mod.root)) for p in (mod.root / book.rel).rglob("*")
                                if p.is_file()}
            result.unhandled.append(Unhandled(f"{book.rel}/", RESIDUE_KIND, (
                f"no converted item opens this book: no item class whose use builds its screen was found "
                f"in the mod's classes, and no item is named {book_id}"), files_in))
            continue
        result.consumed |= book.consumed
        result.unhandled.extend(book.unhandled)
        has_text = {page for pages in book.texts.values() for page, text in pages.items() if text}
        pages = {}
        for name, page in sorted(book.pages.items()):
            pages[name] = {
                "title": _shipped_key(entries, ns, page.title) if page.title else None,
                "body": text_key(ns, book.name, name) if name in has_text else None,
                "parent": page.parent,
                "links": [[stem, _shipped_key(entries, ns, label) if label else stem]
                          for stem, label in page.links],
            }
        table["books"][book_id] = {"root": "root", "pages": pages}
        for item in items:
            table["items"][item] = book_id
        pictures: dict[str, int] = {}
        for page in book.pages.values():
            for kind, count in page.pictures.items():
                pictures[kind] = pictures.get(kind, 0) + count
        lost = ", ".join(f"{count} {kind.replace('_', ' ')}" for kind, count in sorted(pictures.items()) if count)
        locales = sorted(book.texts)
        note = (
            f"{book_id}: Citadel book shown by a Script API form viewer ({data_path(ns)}, "
            f"portkit/runtime/book.js) when {', '.join(items)} is used; opened by {how}. "
            f"{len(pages)} pages, text from {len(locales)} locale folder(s) ({', '.join(locales)}) as "
            f".lang entries (a Bedrock locale without its own text gets en_us, Citadel's fallback). "
            "Text is Citadel's words verbatim; runs of <NEWLINE> become one blank line and Java's "
            "two-page spread becomes one scrolling form. Not carried: "
            + (f"pictures ({lost}), " if lost else "")
            + "entity pictures and hover tooltips on index buttons, and what else the item's Java use does "
            "(statistics, the advancement trigger, opening a mob's page when used on it)."
        )
        if book.dropped_links:
            note += (f" {len(book.dropped_links)} button(s) name a page that isn't in the jar and are left out "
                     f"(Java draws them but opens nothing): {', '.join(book.dropped_links[:5])}.")
        result.notes.append(note)

    if not table["books"]:
        return result, ""
    header = (
        f"// Generated by portkit from {ns}'s Citadel book pages (assets/{ns}/book/); do not edit.\n"
        f"// Read by the fixed runtime {RUNTIME_DIR}/book.js (portkit/runtime). Page text lives in the\n"
        "// resource pack's texts/*.lang under each page's body key. Sources:\n"
        + "".join(f"//   {s}\n" for s in SOURCES)
    ).rstrip("\n")
    body = json.dumps(table, indent=1, sort_keys=True, ensure_ascii=False)
    result.files[data_path(ns)] = f"{header}\nexport default {body};\n"
    result.files[f"{RUNTIME_DIR}/book.js"] = runtime_source("book.js")
    result.files[f"{RUNTIME_DIR}/book_core.js"] = runtime_source("book_core.js")
    result.files[f"{RUNTIME_DIR}/{FORMS}"] = runtime_source(FORMS)
    entry = (
        'import { registerBooks } from "./book.js";\n'
        f'import booksTable from "./data/{ns}_books.js";\n'
        "registerBooks(booksTable);\n"
    )
    return result, entry
