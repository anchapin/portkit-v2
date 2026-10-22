"""Dependency jars a mod is converted with, read-only (#280).

Many mods register their blocks through a library mod (the #280 list): the
block's class subclasses the library's base class, or the library's
constructor registers the block it builds. Read alone, such a jar's blocks end at a class
that isn't in the jar, so the bytecode readers (``portkit.blockcode``) can't
tell what vanilla class they reach or follow their registration.

A library jar given with ``portkit convert --library JAR`` (repeatable), or
pinned for a corpus or gauntlet mod in ``fixtures/real/libraries.toml``, is
read for its classes only: they are added to the mod's
:class:`portkit.bytecode.ClassIndex` as library classes, visible to a lookup
by name and never listed, counted, scanned or converted as the mod's own. A
library's assets, data, lang and models are not read and nothing of it is
shipped: only the target mod's content is in the pack. Jars a library bundles
in ``META-INF/jars/`` (Fabric jar-in-jar) or lists in
``META-INF/jarjar/metadata.json`` (Forge/NeoForge, #368) are read as part of
it, and so are the ``META-INF/services/`` files of each (#368). A class the mod itself has wins over a library's, and
an earlier library's over a later one's.

Library jars are fetched like the corpus jars (pinned url and sha512, cached,
never committed or vendored).
"""
from __future__ import annotations

import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import nested_jars
from .corpus import ROOT as REPO_ROOT
from .corpus import CorpusError, Mod

MANIFEST = REPO_ROOT / "fixtures" / "real" / "libraries.toml"
# The same bounds ingest uses for the mod's own jar.
_MAX_CLASS_BYTES = nested_jars.MAX_CLASS_BYTES
_MAX_CLASSES = 200_000
# A nested jar is read into memory whole; larger ones are skipped rather than
# read (PR #321 review).
_MAX_NESTED_JAR_BYTES = nested_jars.MAX_NESTED_JAR_BYTES
_REQUIRED = ("name", "project", "version_id", "version", "url", "sha512", "license", "for")


class LibraryError(Exception):
    """A library jar that can't be read."""


def _contents(jar: Path) -> list[nested_jars.JarContents]:
    """``jar`` and the jars it nests (one level): ``META-INF/jars/`` (Fabric
    jar-in-jar, each at most _MAX_NESTED_JAR_BYTES) and the jars its
    ``META-INF/jarjar/metadata.json`` lists (Forge/NeoForge, #368), in that
    order after the jar itself."""
    jar = Path(jar)
    if not jar.is_file() or not zipfile.is_zipfile(jar):
        raise LibraryError(f"{jar} is not a jar (zip) archive")
    with zipfile.ZipFile(jar) as zf:
        return [nested_jars.read(zf, jar.name), *nested_jars.fabric_jars(zf), *nested_jars.jarjar(zf)]


def classes(jar: Path) -> dict[str, bytes]:
    """Every class file of ``jar`` and of the jars it nests (see
    :func:`_contents`), by internal name; the first copy of a name wins."""
    out: dict[str, bytes] = {}
    for part in _contents(jar):
        for name, raw in part.classes.items():
            if name not in out:
                if len(out) >= _MAX_CLASSES:
                    raise LibraryError(f"more than {_MAX_CLASSES} library classes; refusing")
                out[name] = raw
    return out


def services(jar: Path) -> list[dict[str, bytes]]:
    """The ``META-INF/services/<service>`` files of ``jar`` and of each jar it
    nests, one ``{path: bytes}`` per jar that has any (#368)."""
    return [part.services for part in _contents(jar) if part.services]


def metadata(jar: Path) -> list[dict[str, bytes]]:
    """The loader metadata files of ``jar`` and of each jar it nests (as
    :func:`classes`), one ``{path: bytes}`` per jar that has any: which
    classes each loader constructs itself (:mod:`portkit.entrypoints`)."""
    return [dict(part.metadata) for part in _contents(jar) if part.metadata]


def attach(index, jars) -> list[str]:
    """Add each library jar's classes to ``index`` (a ClassIndex) in order,
    its loader metadata, and its service files after the ones already read
    (#368); returns one conversion note per jar."""
    notes = []
    for jar in jars or ():
        found = classes(Path(jar))
        added = index.add_libraries(found)
        if hasattr(index, "entry_meta"):
            index.entry_meta.extend(metadata(Path(jar)))
        if hasattr(index, "add_services"):
            for files in services(Path(jar)):
                index.add_services(files)
        notes.append(f"Read with library jar {Path(jar).name} ({added} classes, read-only for "
                     "registrations and base classes; nothing of it is shipped) (#280).")
    return notes


@dataclass(frozen=True)
class Library(Mod):
    """A pinned library jar and the corpus/gauntlet mods it is read with."""

    used_by: tuple = ()


def load(manifest: Path = MANIFEST) -> list[Library]:
    """The pinned library jars (``[[library]]`` tables). A missing file is no
    libraries."""
    manifest = Path(manifest)
    if not manifest.is_file():
        return []
    data = tomllib.loads(manifest.read_text())
    out, seen = [], set()
    for entry in data.get("library", []):
        missing = [k for k in _REQUIRED if not entry.get(k)]
        if missing:
            raise CorpusError(f"{manifest}: library {entry.get('name', '?')!r} lacks {', '.join(missing)}")
        if len(entry["sha512"]) != 128:
            raise CorpusError(f"{manifest}: library {entry['name']!r} sha512 must be 128 hex chars")
        if entry["name"] in seen:
            raise CorpusError(f"{manifest}: library {entry['name']!r} pinned twice")
        seen.add(entry["name"])
        used_by = entry["for"]
        if isinstance(used_by, str):
            used_by = [used_by]
        out.append(Library(name=entry["name"], project=entry["project"], version_id=entry["version_id"],
                           url=entry["url"], sha512=entry["sha512"], license=entry["license"],
                           version=entry["version"], loader=entry.get("loader", ""),
                           minecraft=entry.get("minecraft", ""), source=entry.get("source", ""),
                           notes=entry.get("notes", ""), used_by=tuple(used_by)))
    return out


def for_mod(name: str, libraries: list[Library]) -> list[Library]:
    """The libraries pinned for corpus/gauntlet mod ``name``, in manifest order."""
    return [lib for lib in libraries if name in lib.used_by]
