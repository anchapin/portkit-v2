"""Bedrock reference data the converters read at runtime, fetched on demand (#124).

The one piece today is the list of audio paths Bedrock's vanilla resource pack
names in its ``sound_definitions.json``. It is derived from Mojang/bedrock-samples,
which is (c) Mojang AB, all rights reserved, so the repository and the wheel
don't carry it: ``portkit reference fetch`` downloads the file at the pinned
commit, derives the list, checks it against a pinned sha256 and caches it, the
same way ``portkit corpus fetch`` caches the real-mod jars.

The cache lives in ``$PORTKIT_REFERENCE_CACHE``, else
``$XDG_CACHE_HOME/portkit/reference``, else ``~/.cache/portkit/reference``. Its
file name carries the sha256 prefix, so bumping the pin never reuses a stale
list, and a cached file whose hash is wrong counts as missing.

Without the list, :func:`bedrock_vanilla_sounds` returns ``None`` and callers
fall back to treating every vanilla sound as unknown (the converter drops it,
saying to run the fetch). Output is deterministic for a given cache state.

``PORTKIT_VANILLA_SOUNDS`` names a list file to use instead, unverified: it is
how the test suite runs offline against a tiny list of its own.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from functools import lru_cache
from pathlib import Path

REPO = "Mojang/bedrock-samples"
# The commit pinned for the agent reference (see portkit/agent/reference/NOTICE.md).
COMMIT = "46ba6ea985fb5a92d79a9419198f10dda14c199d"
SOURCE = "resource_pack/sounds/sound_definitions.json"
URL = f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/{SOURCE}"
# sha256 of the derived list (header + one path per line, utf-8) at COMMIT.
# scripts/build_vanilla_sounds.py prints it; bump it together with COMMIT.
SOUNDS_SHA256 = "39bfe21a67e761f686ada00f1e7f4457ab0d4f8cfd2ec52c7e03db877bba5f54"

FETCH_COMMAND = "portkit reference fetch"
_ENV_CACHE = "PORTKIT_REFERENCE_CACHE"
_ENV_LIST = "PORTKIT_VANILLA_SOUNDS"
_USER_AGENT = "anchapin/portkit-v2 reference fetch (github.com/anchapin/portkit-v2)"


class ReferenceDataError(Exception):
    """The reference could not be fetched, or it isn't what the pin says."""


def cache_dir() -> Path:
    env = os.environ.get(_ENV_CACHE)
    if env:
        return Path(env).expanduser()
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "portkit" / "reference"


def sounds_path(cache: Path | None = None) -> Path:
    return Path(cache or cache_dir()) / f"bedrock_vanilla_sounds-{SOUNDS_SHA256[:12]}.txt"


def derive_sounds(definitions_json: bytes) -> str:
    """bedrock-samples' sound_definitions.json -> the sorted path list, as text."""
    data = json.loads(definitions_json)
    definitions = data.get("sound_definitions", data)
    names: set[str] = set()
    for body in definitions.values():
        if not isinstance(body, dict):
            continue
        for sound in body.get("sounds") or []:
            name = sound.get("name") if isinstance(sound, dict) else sound
            if isinstance(name, str) and name.startswith("sounds/"):
                names.add(name)
    header = (
        f"# Bedrock vanilla audio paths, from {REPO}@{COMMIT} {SOURCE}.\n"
        f"# Derived by `{FETCH_COMMAND}`; (c) Mojang AB, not for redistribution.\n"
    )
    return header + "".join(f"{n}\n" for n in sorted(names))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cached_sounds(cache: Path | None = None) -> Path | None:
    """The verified cached list, or None when it is missing or doesn't match the pin."""
    path = sounds_path(cache)
    return path if path.is_file() and _sha256(path.read_bytes()) == SOUNDS_SHA256 else None


def fetch_sounds(cache: Path | None = None, opener=urllib.request.urlopen) -> tuple[Path, bool]:
    """Return (list path, downloaded?). Raises ReferenceDataError on failure or a hash mismatch."""
    cache = Path(cache or cache_dir())
    hit = cached_sounds(cache)
    if hit:
        return hit, False
    request = urllib.request.Request(URL, headers={"User-Agent": _USER_AGENT})
    try:
        with opener(request, timeout=120) as response:
            raw = response.read()
        text = derive_sounds(raw)
    except (OSError, ValueError, AttributeError) as exc:
        raise ReferenceDataError(f"vanilla sound list: download failed from {URL}: {exc}") from exc
    data = text.encode("utf-8")
    digest = _sha256(data)
    if digest != SOUNDS_SHA256:
        raise ReferenceDataError(
            f"vanilla sound list: sha256 mismatch for {URL} (got {digest[:16]}..., "
            f"pinned {SOUNDS_SHA256[:16]}...); re-pin it on purpose"
        )
    cache.mkdir(parents=True, exist_ok=True)
    target = sounds_path(cache)
    partial = target.with_suffix(".part")
    partial.write_bytes(data)
    partial.replace(target)
    _read.cache_clear()
    return target, True


@lru_cache(maxsize=4)
def _read(path: str, mtime_ns: int, size: int, verify: bool) -> frozenset[str] | None:
    data = Path(path).read_bytes()
    if verify and _sha256(data) != SOUNDS_SHA256:
        return None
    return frozenset(
        line for line in data.decode("utf-8").splitlines() if line and not line.startswith("#")
    )


def bedrock_vanilla_sounds() -> frozenset[str] | None:
    """Every audio path (``sounds/...``, no extension) Bedrock's vanilla pack names,
    or None when the list isn't cached (run ``portkit reference fetch``).

    A sound_definitions.json entry naming one of these plays the vanilla file,
    so it is not a dangling reference even though the pack doesn't ship it.
    """
    override = os.environ.get(_ENV_LIST)
    path = Path(override).expanduser() if override else sounds_path()
    try:
        stat = path.stat()
    except OSError:
        return None
    return _read(str(path), stat.st_mtime_ns, stat.st_size, not override)
