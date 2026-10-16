"""The real-mod corpus (#21): pinned Modrinth jars, downloaded, never committed.

Hand-built fixtures prove the harness; real mods show where the converters
break. Their jars are not ours to redistribute, so the repository holds only a
manifest (``fixtures/real/mods.toml``) pinning each one by Modrinth version id
and sha512. ``portkit corpus fetch`` downloads them into a local cache and
refuses any file whose hash differs, so a re-uploaded or deleted jar fails
loudly instead of quietly changing what the corpus measures.

Some mods are pinned but *optional* (``optional = true`` in the manifest):
measured on request, left out of the default ``corpus fetch``, ``eval
--corpus`` and the realmods gate. ``select`` decides which mods a run covers.

The cache is content-addressed (``<name>-<sha512 prefix>.jar``), so bumping a
pin never reuses a stale download. Set ``PORTKIT_CORPUS_CACHE`` to move it.
"""
from __future__ import annotations

import hashlib
import os
import tomllib
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "fixtures" / "real" / "mods.toml"
_REQUIRED = ("name", "project", "version_id", "url", "sha512", "license")
_REQUIRED_UNFETCHABLE = ("name", "project", "license")
_USER_AGENT = "anchapin/portkit-v2 corpus fetch (github.com/anchapin/portkit-v2)"


class CorpusError(Exception):
    """The manifest is wrong, or a jar could not be fetched or verified."""


@dataclass(frozen=True)
class Mod:
    name: str
    project: str
    version_id: str
    url: str
    sha512: str
    license: str
    version: str = ""
    loader: str = ""
    minecraft: str = ""
    source: str = ""
    notes: str = ""
    optional: bool = False  # pinned, but only run when asked for (--include-optional, --fixture)
    # The top-50 gauntlet (#278, fixtures/real/gauntlet.toml) adds these:
    rank: int = 0  # #277's order
    title: str = ""
    host: str = ""  # modrinth | curseforge
    rule: str = ""  # which branch of the version rule picked the build
    redistribution: str = ""  # how the jar is fetched and whether it may be cached/redistributed
    listed_lib: bool = False  # #277 marks it [lib]
    unfetchable: str = ""  # the reason, when the jar can't be fetched (then url/sha512/version_id may be empty)

    def path(self, cache: Path) -> Path:
        return Path(cache) / f"{self.name}-{self.sha512[:12]}.jar"


def cache_dir() -> Path:
    env = os.environ.get("PORTKIT_CORPUS_CACHE")
    if env:
        return Path(env).expanduser()
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "portkit" / "mods"


def load(manifest: Path = MANIFEST) -> list[Mod]:
    data = tomllib.loads(Path(manifest).read_text())
    entries = data.get("mod")
    if not isinstance(entries, list) or not entries:
        raise CorpusError(f"{manifest}: no [[mod]] entries")
    mods, seen = [], set()
    fields = set(Mod.__dataclass_fields__)
    for i, entry in enumerate(entries):
        required = _REQUIRED_UNFETCHABLE if entry.get("unfetchable") else _REQUIRED
        missing = [k for k in required if not entry.get(k)]
        if missing:
            raise CorpusError(f"{manifest}: mod #{i + 1} is missing {', '.join(missing)}")
        unknown = sorted(set(entry) - fields)
        if unknown:
            raise CorpusError(f"{manifest}: mod {entry['name']!r} has unknown key(s) {', '.join(unknown)}")
        if entry["name"] in seen:
            raise CorpusError(f"{manifest}: duplicate mod name {entry['name']!r}")
        if not isinstance(entry.get("optional", False), bool):
            raise CorpusError(f"{manifest}: mod {entry['name']!r} optional must be true or false")
        for key in ("listed_lib",):
            if not isinstance(entry.get(key, False), bool):
                raise CorpusError(f"{manifest}: mod {entry['name']!r} {key} must be true or false")
        if not isinstance(entry.get("rank", 0), int):
            raise CorpusError(f"{manifest}: mod {entry['name']!r} rank must be an integer")
        entry = {"version_id": "", "url": "", "sha512": "", **entry}
        if not entry.get("unfetchable") and len(entry["sha512"]) != 128:
            raise CorpusError(f"{manifest}: mod {entry['name']!r} sha512 must be 128 hex chars")
        seen.add(entry["name"])
        mods.append(Mod(**entry))
    return mods


def select(mods: list[Mod], names=(), include_optional: bool = False) -> list[Mod]:
    """The mods a run covers. Named mods are taken whether optional or not (an
    unknown name is an error); otherwise the default set, plus the optional mods
    when asked for. Manifest order is kept."""
    if names:
        wanted = set(names)
        unknown = sorted(wanted - {m.name for m in mods})
        if unknown:
            raise CorpusError(f"not in the corpus manifest: {', '.join(unknown)}")
        return [m for m in mods if m.name in wanted]
    return [m for m in mods if include_optional or not m.optional]


def _sha512(path: Path) -> str:
    h = hashlib.sha512()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cached(mod: Mod, cache: Path | None = None) -> Path | None:
    """The verified jar if it is already in the cache, else None."""
    path = mod.path(cache or cache_dir())
    return path if path.is_file() and _sha512(path) == mod.sha512 else None


def fetch(mod: Mod, cache: Path | None = None, opener=urllib.request.urlopen) -> tuple[Path, bool]:
    """Return (jar path, downloaded?). Raises CorpusError on a hash mismatch."""
    if mod.unfetchable:
        raise CorpusError(f"{mod.name}: unfetchable: {mod.unfetchable}")
    cache = Path(cache or cache_dir())
    hit = cached(mod, cache)
    if hit:
        return hit, False
    cache.mkdir(parents=True, exist_ok=True)
    target = mod.path(cache)
    partial = target.with_suffix(".part")
    request = urllib.request.Request(mod.url, headers={"User-Agent": _USER_AGENT})
    try:
        with opener(request, timeout=120) as response, open(partial, "wb") as out:
            while chunk := response.read(1 << 20):
                out.write(chunk)
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise CorpusError(f"{mod.name}: download failed: {exc}") from exc
    digest = _sha512(partial)
    if digest != mod.sha512:
        partial.unlink(missing_ok=True)
        raise CorpusError(
            f"{mod.name}: sha512 mismatch for {mod.url} (got {digest[:16]}..., "
            f"pinned {mod.sha512[:16]}...); the file changed upstream, so re-pin it on purpose"
        )
    partial.replace(target)
    return target, True
