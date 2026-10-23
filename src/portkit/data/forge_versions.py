"""Which Minecraft version a Forge release is built for, read from Forge's own
release list (#364).

A Forge jar can declare no ``minecraft`` dependency at all and only require
``forge`` at some version (Botania 1.20.1-456 asks ``forge [47.1.3,)``). Forge
publishes every release on its maven as ``<minecraft>-<forge>``
(``1.20.1-47.1.3``) in
``https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml``,
so the game version a Forge dependency's lower bound is built for can be read
from Forge's own file instead of guessed.

The derived table is Forge major -> game version, for the majors 25 (Minecraft
1.13.2, the first of Forge's one-major-per-game-version line) to
:data:`LAST_MAJOR` whose every listed release names the same game version.
A major that spans two game versions (49: 1.20.3 and 1.20.4) is left out and
listed under ``ambiguous``, never picked. Majors are frozen once released, so
the table doesn't move when Forge publishes more releases of a listed major;
``LAST_MAJOR`` keeps it from moving when Forge starts a new one.

``portkit reference fetch`` downloads the file, derives the table, checks its
sha256 pin and caches it. Only the version number pairs are kept (no Forge
code). ``PORTKIT_FORGE_VERSIONS`` names a table file to use instead,
unverified: it is how the tests run offline.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
from functools import lru_cache
from pathlib import Path

from . import ReferenceDataError, _USER_AGENT, cache_dir

SET_ID = "forge-game-versions"
URL = "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml"
LABEL = "Forge release -> Minecraft version, from Forge's maven-metadata.xml"
FIRST_MAJOR = 25
# The newest Forge major in Forge's maven-metadata.xml on 2026-10-23 (26.3).
LAST_MAJOR = 66
# sha256 of the derived table: `python -m portkit.data.forge_versions --pin` prints it.
SHA256 = "e540be8f13b510ff6a37df44f6fcb84398bfe180e4da87628f0ec20e3c42179f"
_ENV_FILE = "PORTKIT_FORGE_VERSIONS"
_VERSION = re.compile(r"<version>\s*([^<\s]+)\s*</version>")
_RELEASE = re.compile(r"^(\d+\.\d+(?:\.\d+)?)-(\d+)\.\d+")


def derive(metadata: bytes) -> bytes:
    """The table from Forge's maven-metadata.xml."""
    seen: dict[int, set[str]] = {}
    for raw in _VERSION.findall(metadata.decode("utf-8", "replace")):
        match = _RELEASE.match(raw)
        if match and FIRST_MAJOR <= int(match.group(2)) <= LAST_MAJOR:
            seen.setdefault(int(match.group(2)), set()).add(match.group(1))
    if not seen:
        raise ValueError("no Forge releases found")
    majors = {str(k): next(iter(v)) for k, v in sorted(seen.items()) if len(v) == 1}
    ambiguous = {str(k): sorted(v) for k, v in sorted(seen.items()) if len(v) > 1}
    out = {"source": URL, "first_major": FIRST_MAJOR, "last_major": LAST_MAJOR,
           "majors": majors, "ambiguous": ambiguous}
    return (json.dumps(out, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def set_path(cache: Path | None = None) -> Path:
    return Path(cache or cache_dir()) / f"{SET_ID}-{SHA256[:12]}.json"


def cached(cache: Path | None = None) -> Path | None:
    path = set_path(cache)
    return path if path.is_file() and _sha256(path.read_bytes()) == SHA256 else None


def download(opener=urllib.request.urlopen) -> bytes:
    request = urllib.request.Request(URL, headers={"User-Agent": _USER_AGENT})
    try:
        with opener(request, timeout=120) as response:
            metadata = response.read()
    except (OSError, ValueError, AttributeError) as exc:
        raise ReferenceDataError(f"{SET_ID}: download failed: {exc}") from exc
    try:
        return derive(metadata)
    except ValueError as exc:
        raise ReferenceDataError(f"{SET_ID}: can't derive the table: {exc}") from exc


def fetch(cache: Path | None = None, opener=urllib.request.urlopen) -> tuple[Path, bool]:
    """Return (cached path, downloaded?). Raises ReferenceDataError on failure or a hash mismatch."""
    cache = Path(cache or cache_dir())
    hit = cached(cache)
    if hit:
        return hit, False
    data = download(opener)
    digest = _sha256(data)
    if digest != SHA256:
        raise ReferenceDataError(f"{SET_ID}: derived table sha256 {digest[:16]}... isn't the "
                                 f"pinned {SHA256[:16]}...; re-pin it on purpose")
    cache.mkdir(parents=True, exist_ok=True)
    target = set_path(cache)
    partial = target.with_suffix(".part")
    partial.write_bytes(data)
    partial.replace(target)
    _read.cache_clear()
    return target, True


@lru_cache(maxsize=2)
def _read(path: str, mtime_ns: int, size: int, expected: str | None) -> dict[str, str] | None:
    data = Path(path).read_bytes()
    if expected is not None and _sha256(data) != expected:
        return None
    try:
        majors = json.loads(data).get("majors")
    except (ValueError, AttributeError):
        return None
    if not isinstance(majors, dict):
        return None
    return {k: v for k, v in majors.items() if isinstance(k, str) and isinstance(v, str)}


def table() -> dict[str, str] | None:
    """Forge major -> game version, or None when it isn't cached (run ``portkit reference fetch``)."""
    override = os.environ.get(_ENV_FILE)
    path = Path(override).expanduser() if override else set_path()
    try:
        stat = path.stat()
    except OSError:
        return None
    return _read(str(path), stat.st_mtime_ns, stat.st_size, None if override else SHA256)


_LOWER = re.compile(r"^\s*(?:\[\s*)?(\d+)(?:\.\d+)*\s*(?:[,\]]|$)")


def minecraft_for(version_range: str | None) -> str | None:
    """The game version a ``forge`` dependency's versionRange lower bound is built
    for: its major looked up in Forge's release list. None for an open lower
    bound (``(,48)``, ``*``), a major outside the table or spanning two game
    versions, or when the table isn't cached."""
    match = _LOWER.match(version_range) if isinstance(version_range, str) else None
    if not match:
        return None
    found = table()
    return found.get(match.group(1)) if found else None


if __name__ == "__main__":  # pragma: no cover - maintenance helper
    import sys

    if sys.argv[1:] == ["--pin"]:
        data = download()
        digest = _sha256(data)
        print(f"{SET_ID} {digest} {'ok' if digest == SHA256 else 'CHANGED'} {data.decode().strip()}")
        sys.exit(0)
    print("usage: python -m portkit.data.forge_versions --pin")
    sys.exit(2)
