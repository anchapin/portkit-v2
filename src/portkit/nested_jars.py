"""Jars a jar bundles inside itself, read as libraries (#368, part of #277).

A mod jar can ship library code nested in it rather than as a separate mod:

* Forge / NeoForge jar-in-jar: ``META-INF/jarjar/metadata.json`` lists the
  jars the loader loads, each by its ``path`` inside the jar (MinecraftForge
  JarJar ``Metadata.jars`` / ``ContainedJarMetadata.path``; NeoForge's fork
  keeps the format). A jar under ``META-INF/jarjar/`` the file doesn't list is
  not loaded by the loader, so it isn't read here either; a missing or
  unreadable metadata file reads none.
* Fabric jar-in-jar: ``META-INF/jars/*.jar``. Only a *library* jar's are read
  (:mod:`portkit.libraries`, since #321); a mod jar's own Fabric nested jars
  are not attached by ingest (not part of #368).

A nested jar is read one level deep, each at most ``MAX_NESTED_JAR_BYTES``,
for its classes, its ``META-INF/services/`` files and its loader metadata. They
are attached to the mod's :class:`portkit.bytecode.ClassIndex` as *library*
classes (``add_libraries``): found by a lookup by name, never listed, counted,
scanned or converted as the mod's own, so ownership rules don't widen. The
nested jar itself stays ``nested_jar`` residue: its resources are not staged.
"""
from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field

JARJAR_METADATA = "META-INF/jarjar/metadata.json"
# A nested jar is read into memory whole; larger ones are skipped rather than
# read (PR #321 review).
MAX_NESTED_JAR_BYTES = 64 * 1024 * 1024
MAX_CLASS_BYTES = 4 * 1024 * 1024
# The member bound ingest uses for the mod's own jar; a nested jar with more
# is skipped (its contents are never staged, but a zip bomb isn't read).
MAX_MEMBERS = 50_000
LOADER_METADATA = ("META-INF/neoforge.mods.toml", "META-INF/mods.toml", "fabric.mod.json", "quilt.mod.json")


@dataclass
class JarContents:
    """What one jar holds for the class index: classes by internal name,
    ``META-INF/services/<service>`` files and loader metadata ({path: bytes})."""

    name: str
    classes: dict[str, bytes] = field(default_factory=dict)
    services: dict[str, bytes] = field(default_factory=dict)
    metadata: dict[str, bytes] = field(default_factory=dict)


def jarjar_paths(metadata_json: bytes | None) -> list[str]:
    """The nested jar paths ``META-INF/jarjar/metadata.json`` lists, in file
    order, once each; [] when the file is missing or isn't that shape."""
    if not metadata_json:
        return []
    try:
        doc = json.loads(metadata_json.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return []
    jars = doc.get("jars") if isinstance(doc, dict) else None
    out: list[str] = []
    for entry in jars if isinstance(jars, list) else ():
        path = entry.get("path") if isinstance(entry, dict) else None
        if isinstance(path, str) and path.endswith(".jar") and _safe(path) and path not in out:
            out.append(path)
    return out


def _safe(name: str) -> bool:
    return not name.startswith(("/", "\\")) and ".." not in name.replace("\\", "/").split("/")


def read(zf: zipfile.ZipFile, name: str) -> JarContents:
    """The classes, service files and loader metadata of an open jar."""
    out = JarContents(name)
    names = set()
    for info in zf.infolist():
        member = info.filename
        names.add(member)
        if info.is_dir() or info.file_size > MAX_CLASS_BYTES:
            continue
        if member.endswith(".class") and not member.startswith("META-INF/"):
            out.classes.setdefault(member[:-6], zf.read(info))
        elif member.startswith("META-INF/services/") and member.count("/") == 2:
            out.services[member] = zf.read(info)
    out.metadata = {n: zf.read(n) for n in LOADER_METADATA if n in names}
    return out


def jarjar(zf: zipfile.ZipFile, cap: int = MAX_NESTED_JAR_BYTES) -> list[JarContents]:
    """Each jar ``zf``'s ``META-INF/jarjar/metadata.json`` lists, read (one
    level; a missing, oversized or unreadable one is skipped)."""
    try:
        listed = jarjar_paths(zf.read(JARJAR_METADATA))
    except KeyError:
        return []
    return _open_each(zf, listed, cap)


def fabric_jars(zf: zipfile.ZipFile, cap: int = MAX_NESTED_JAR_BYTES) -> list[JarContents]:
    """Each ``META-INF/jars/*.jar`` of ``zf``, read (one level)."""
    listed = [i.filename for i in zf.infolist()
              if i.filename.startswith("META-INF/jars/") and i.filename.endswith(".jar")]
    return _open_each(zf, listed, cap)


def _open_each(zf: zipfile.ZipFile, paths: list[str], cap: int) -> list[JarContents]:
    out = []
    for path in paths:
        try:
            info = zf.getinfo(path)
        except KeyError:
            continue
        if info.file_size > cap:
            continue
        try:
            with zipfile.ZipFile(io.BytesIO(zf.read(info))) as inner:
                if len(inner.infolist()) > MAX_MEMBERS:
                    continue
                out.append(read(inner, path))
        except (zipfile.BadZipFile, OSError, ValueError):
            continue
    return out


def attach(index, jars: list[JarContents]) -> int:
    """Add each nested jar's classes to ``index`` as library classes, its
    service files after the ones already read, and its loader metadata to
    ``index.entry_meta``, in order. Returns how many classes were added."""
    added = 0
    for jar in jars:
        added += index.add_libraries(jar.classes)
        index.add_services(jar.services)
        if jar.metadata and hasattr(index, "entry_meta"):
            index.entry_meta.append(dict(jar.metadata))
    return added
