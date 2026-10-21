"""Guide books no converter reads (#182, part of #277): explained from the jar, not converted.

In-game guides (manuals, lexicons, encyclopedias) are pages the jar ships as
data, shown by a book screen that is Java: the mod's own, or a library's it
bundles or depends on. #182's first slice converts one format, Citadel's
``GuiBasicBook``, into a form viewer (:mod:`portkit.adapters.citadel.books`).
Every other guide's files were ``unowned`` residue, as if nothing had looked
at them. This pass recognises a guide from its file layout and re-files its
leftover files as the explained ``guidebook`` kind (#182 design PR, pending
Alex, picks 1a-3a). Nothing is converted and nothing is written (#87).

**What a guide folder is (pick 1a).** ``assets/<ns>/<dir>/`` where ``<dir>``
is not a folder Minecraft's client reads (:data:`portkit.worldgen._CLIENT_DIRS`),
no file of it was read by a converter, every leftover file in it is a document
(``.json``, ``.txt``, ``.md``, ``.lang``) or the pictures and structures pages
show (``.png``, ``.nbt``, ``.snbt``), and its pages are prose in one of two
layouts:

* **per language**: documents under a folder named ``en_us`` (any depth below
  ``<dir>``; 1.12's ``en_US`` too). Java's client reads per-language text only
  from ``lang/`` (and ``texts/`` for the credits and splashes), and ``en_us``
  is the language every translation falls back to, so per-language documents
  anywhere else are text the mod's own screen shows (Patchouli's
  ``<book>/en_us/entries/``, Mantle's ``<book>/en_us/``, IE's ``manual/en_us/``);
* **markdown**: ``.md`` pages. No part of Minecraft reads markdown (GuideME's
  ``ae2guide/``).

``data/<ns>/<dir>/`` holding only JSON, beside a guide folder of the same name
in ``assets/<ns>/``, is that guide's data half (Patchouli's ``book.json``).

**Which system shows it, read from the jar, never from a table (#220).** The
reason names the jar's classes that hold the folder's name as a path string
(``<dir>/...``, ``<ns>:<dir>/...``), ranked by how many such strings they
hold, and each required dependency in the jar's metadata that those classes
call into (a class path segment equal to its id) or whose id begins the
folder's name. When neither is found the reason says so: then the jar shows
no reader, and Java may not open the pages at all.

**Counting (pick 3a).** Each source file counts as one residue file, as it
did while ``unowned``: the pages are left out of the pack, so coverage does
not move. A folder is one entry.

Nothing here names a mod or a guide system.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .model import Unhandled
from .worldgen import _CLIENT_DIRS, _Citations

GUIDEBOOK = "guidebook"

_DOCS = frozenset({".json", ".txt", ".md", ".lang"})
_MEDIA = frozenset({".png", ".nbt", ".snbt"})
# A Java locale code as a folder name: en_us, zh_cn, es_ve; 1.12's en_US.
_LOCALE = re.compile(r"^[a-z]{2,3}_[a-z]{2,4}$", re.IGNORECASE)
_FALLBACK = "en_us"
_ASSET = re.compile(r"^assets/([^/]+)/([^/]+)/(.+)$")
_DATA = re.compile(r"^data/([^/]+)/([^/]+)/(.+)$")
# Dependencies every mod has; they show no guide.
_PLATFORM = frozenset({"minecraft", "forge", "neoforge", "fabric", "fabricloader", "fabric-api", "fabric_api",
                       "quilt_loader", "quilted_fabric_api", "java", "mixinextras"})
_MAX_CITED = 2


def _suffix(rel: str) -> str:
    name = rel.rsplit("/", 1)[-1]
    return name[name.rfind("."):].lower() if "." in name else ""


def _layout(members: list[str]) -> tuple[str, list[str], int] | None:
    """(layout, locales, page count) for a folder's leftover files (paths
    below the folder), or None when it isn't a guide's."""
    if not members or any(_suffix(m) not in _DOCS | _MEDIA for m in members):
        return None
    locales: set[str] = set()
    per_language = 0
    for m in members:
        if _suffix(m) not in _DOCS:
            continue
        dirs = m.split("/")[:-1]
        codes = [d for d in dirs if _LOCALE.match(d)]
        if codes:
            locales.add(codes[-1].lower())
            per_language += 1
    if _FALLBACK in locales:
        return "per language", sorted(locales), per_language
    pages = sum(1 for m in members if _suffix(m) == ".md")
    if pages:
        return "markdown", [], pages
    return None


def _path_strings(name: str):
    return re.compile(rf"(?:^|[/:]){re.escape(name)}/")


def _readers(name: str, cite: _Citations, requires: list[str]) -> str:
    """Which of the jar's classes (and required dependencies) read ``name``/."""
    deps = sorted({d for d in (requires or []) if isinstance(d, str) and d.lower() not in _PLATFORM})
    named = [d for d in deps if name.lower().startswith(d.lower())]
    parts: list[str] = []
    if cite.classes is not None:
        pattern = _path_strings(name)
        pools = cite._load()
        hits = []
        for cls, pool in pools.items():
            n = sum(1 for s in pool if pattern.search(s))
            if n:
                hits.append((cls, n))
        hits.sort(key=lambda h: (-h[1], h[0]))
        if hits:
            calls: set[str] = set()
            for cls, _ in hits:
                segments = {seg for s in pools[cls] if "/" in s for seg in re.split(r"[/;$]", s)}
                calls |= {d for d in deps if d in segments}
            shown = ", ".join(c for c, _ in hits[:_MAX_CITED])
            more = f" and {len(hits) - _MAX_CITED} more" if len(hits) > _MAX_CITED else ""
            parts.append(f"the jar's classes naming `{name}/` as a path: {shown}{more}")
            if calls - set(named):
                parts.append("calling into the required dependenc" + ("ies " if len(calls - set(named)) > 1 else "y ")
                             + ", ".join(f"`{d}`" for d in sorted(calls - set(named))))
        else:
            parts.append(f"no class of the jar names `{name}/` as a path")
    else:
        parts.append("the source has no classes to name its reader")
    if named:
        parts.append("the folder is named after the required dependenc" + ("ies " if len(named) > 1 else "y ")
                     + ", ".join(f"`{d}`" for d in named) + ", which reads it")
    if not named and (cite.classes is None or parts[0].startswith("no class")):
        parts.append("so the jar shows no reader and Java may not open these pages at all")
    return "; ".join(parts)


def _reason(name: str, members: list[str], layout: tuple[str, list[str], int], readers: str) -> str:
    kind, locales, pages = layout
    others = len(members) - pages
    suffixes = sorted({_suffix(m).lstrip(".") for m in members})
    if kind == "per language":
        shown = ", ".join(locales[:4]) + (f" and {len(locales) - 4} more" if len(locales) > 4 else "")
        what = (f"{pages} page document(s) in per-language folders ({len(locales)} language(s): {shown}), which "
                f"Minecraft's client reads only from lang/ and texts/")
    else:
        what = f"{pages} markdown page(s), a format no part of Minecraft reads"
    extra = f", and {others} other file(s) its pages use" if others else ""
    return (f"`{name}/` is a guide book: {what}{extra} ({', '.join(suffixes)}); its book screen is Java "
            f"({readers}). A Bedrock add-on has no guide-book screen and portkit's form viewer reads only "
            f"Citadel books, so its text, pictures and recipe or structure renders are not converted, "
            f"and nothing is summarised or rewritten (#87)")


def _files(root: Path, source: str) -> list[str]:
    base = root / source.rstrip("/")
    if not base.is_dir():
        return []
    return [p.relative_to(root).as_posix() for p in sorted(base.rglob("*")) if p.is_file()]


def refine(unhandled: list[Unhandled], root: Path, consumed: set[str], classes=None,
           requires: list[str] | None = None) -> tuple[list[Unhandled], set[str]]:
    """Re-file the leftover files of guide folders as ``guidebook``; returns
    the residue and the re-filed paths (so later passes leave them alone)."""
    root = Path(root)
    groups = {u.source: u for u in unhandled if u.kind == "unowned"}
    if not groups:
        return unhandled, set()
    cite = _Citations(classes)
    found: dict[str, tuple[str, str]] = {}  # rel -> (folder, reason)
    guides: dict[tuple[str, str], str] = {}  # (ns, dir) -> its assets folder
    for source in sorted(groups):
        m = re.match(r"^assets/([^/]+)/([^/]+)/$", source)
        if not m or m.group(2) in _CLIENT_DIRS:
            continue
        everything = _files(root, source)
        if any(rel in consumed for rel in everything):
            continue  # a converter reads this folder; what it left is its own residue
        members = [rel[len(source):] for rel in everything]
        layout = _layout(members)
        if layout is None:
            continue
        reason = _reason(m.group(2), members, layout, _readers(m.group(2), cite, requires or []))
        guides[(m.group(1), m.group(2))] = source
        for rel in everything:
            found[rel] = (source, reason)
    for source in sorted(groups):
        m = re.match(r"^data/([^/]+)/([^/]+)/$", source)
        if not m or (m.group(1), m.group(2)) not in guides:
            continue
        everything = _files(root, source)
        if not everything or any(rel in consumed or not rel.endswith(".json") for rel in everything):
            continue
        reason = (f"`{m.group(2)}/` is the data half of the guide book in {guides[(m.group(1), m.group(2))]} "
                  f"(the same folder name, {len(everything)} JSON file(s): its settings, read with its pages); "
                  f"nothing in Minecraft or the mod loader reads this folder, and the guide isn't converted")
        for rel in everything:
            found[rel] = (source, reason)
    if not found:
        return unhandled, set()

    entries: dict[tuple[str, str], int] = {}
    for rel, key in found.items():
        entries[key] = entries.get(key, 0) + 1
    out: list[Unhandled] = []
    for u in unhandled:
        if u.kind != "unowned" or u.source not in groups:
            out.append(u)
            continue
        left = u.count - sum(1 for rel, (src, _) in found.items() if src == u.source)
        if left == u.count:
            out.append(u)
        elif left > 0:
            out.append(Unhandled(source=u.source, kind="unowned",
                                 reason=f"{left} file(s) no converter claims yet", count=left))
    out += [Unhandled(source=src, kind=GUIDEBOOK, reason=reason, count=n)
            for (src, reason), n in sorted(entries.items())]
    return out, set(found)
