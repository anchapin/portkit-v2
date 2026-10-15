"""Citadel (#245): the library behind Alex's Mobs' Animal Dictionary, as a library adapter.

Citadel draws guide books (``GuiBasicBook``) whose pages are data in the jar
of the mod that uses it (``assets/<ns>/book/<book>/``), and the item that
opens one is found from that mod's bytecode. The format reader is
:mod:`portkit.adapters.citadel.books` (#182), moved unchanged from
``converters/books.py`` (migration step 6); the core reaches it through the
``books`` hook (:class:`portkit.adapters.BookReader`). The fixed viewer
(``portkit/runtime/book.js``, ``book_core.js``, ``forms.js``) stays core: it
names no mod and is the form viewer #239's templates build on.
"""
from __future__ import annotations

from .. import Adapter, BookReader
from . import books

ADAPTER = Adapter(
    name="citadel",
    namespaces=frozenset({"citadel"}),
    library=True,
    books=BookReader(plan=books.plan, lang_text=books.lang_text, convert=books.convert),
)
