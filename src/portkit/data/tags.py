"""Item tag membership the loaders and vanilla define, fetched on demand (#160).

A mod jar's ``c:``, ``forge:``, ``neoforge:``, ``fabric:`` or ``minecraft:`` tag
file is only that mod's share of the tag: vanilla and the loader add their own
members (Forge's ``forge:glass/colorless`` is ``minecraft:glass``; NeoForge's
``c:foods/vegetable`` lists carrot, golden carrot, potato and beetroot). So the
tag resolver needs those shares to know a tag's full membership. They come from
public, pinned artifacts and are cached like the vanilla sound list (#124):

* Forge 1.20.1: the generated ``data/forge/tags/items`` in Forge's universal jar
  (LGPL-2.1), from maven.minecraftforge.net.
* NeoForge 1.21.1: the generated ``data/c/tags/item`` and
  ``data/neoforge/tags/item`` in NeoForge's universal jar (LGPL-2.1), from
  maven.neoforged.net.
* Fabric: ``fabric-convention-tags-v1`` (1.20.1) and ``-v2`` (1.21.1, 1.21.8,
  26.1) module jars of Fabric API (Apache-2.0), from maven.fabricmc.net.
* Vanilla item tags per game version: misode/mcmeta's ``<version>-summary``
  ``data/tag/item/data.json`` at a pinned commit. Generated from the game, so
  (c) Mojang AB, used under the Minecraft EULA; never vendored.

``portkit reference fetch`` downloads each set, keeps only the item tags (tag id
-> its ``values`` list), checks the result against the sha256 pinned in
:data:`SETS` and caches it as ``tags-<set>-<sha12>.json`` next to the sound
list. Nothing here is committed to the repository or shipped in the wheel.

At conversion time :func:`reference_for` picks the set nearest the loader and
Minecraft version the jar declares (META-INF/mods.toml, neoforge.mods.toml,
fabric.mod.json) and reads it from the cache only, never the network. When the
set isn't cached, or the loader or version is unknown, it returns a reference
that covers fewer (or no) namespaces, and tags in an uncovered shared namespace
stay residue. A shared namespace the loader never writes to (Forge 1.20.1 ships
no ``c:`` tags; NeoForge 1.21 dropped ``forge:``) counts as covered with an
empty share: only mods fill it there, and other mods' entries are dropped
anyway (#88). ``PORTKIT_TAG_REFERENCE`` names a directory of ``<set>.json``
files to use instead, unverified: it is how the tests run offline against tiny
fixtures of their own.

``python -m portkit.data.tags --pins`` downloads every set and prints the
sha256 to pin, after bumping a version.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
import urllib.request
import zipfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from . import FETCH_COMMAND, ReferenceDataError, _USER_AGENT, cache_dir

_ENV_DIR = "PORTKIT_TAG_REFERENCE"

# Tag namespaces several datapacks write into: vanilla's and the loaders'. A
# mod's file in one of these is only its share unless it sets "replace": true.
SHARED_NAMESPACES = ("minecraft", "c", "forge", "neoforge", "fabric")

_FORGE = "https://maven.minecraftforge.net/net/minecraftforge/forge"
_NEOFORGE = "https://maven.neoforged.net/releases/net/neoforged/neoforge"
_FABRIC = "https://maven.fabricmc.net/net/fabricmc/fabric-api"
_MCMETA = "https://raw.githubusercontent.com/misode/mcmeta"


@dataclass(frozen=True)
class TagSet:
    """One pinned source of item tags."""

    id: str
    family: str  # forge | neoforge | fabric-v1 | fabric-v2 | vanilla
    minecraft: str
    kind: str  # "jar" (data/<ns>/tags/item[s]/ in a jar) or "mcmeta" (summary JSON)
    url: str
    namespaces: tuple[str, ...]  # tag namespaces this set is the authority for
    # Shared namespaces this loader doesn't write to at all, so only mods fill
    # them there (Forge 1.20.1 ships no c: tags; NeoForge 1.21 dropped forge:).
    foreign: tuple[str, ...]
    sha256: str  # of the derived JSON (see derive_*); bump with the version
    label: str  # what it is, for `portkit reference list` and notes


def _fabric_module(module: str, version: str) -> str:
    return f"{_FABRIC}/{module}/{version}/{module}-{version}.jar"


SETS: tuple[TagSet, ...] = (
    TagSet(
        "forge-1.20.1", "forge", "1.20.1", "jar",
        f"{_FORGE}/1.20.1-47.4.26/forge-1.20.1-47.4.26-universal.jar",
        ("forge",), ("c", "neoforge"),
        "54afc8889188bf68e56e7a15a9103e2ca5dc506ca0541817d6ad543e0595aaa0",
        "Forge 1.20.1-47.4.26 (LGPL-2.1)",
    ),
    TagSet(
        "neoforge-1.21.1", "neoforge", "1.21.1", "jar",
        f"{_NEOFORGE}/21.1.259/neoforge-21.1.259-universal.jar",
        ("c", "neoforge"), ("forge",),
        "6d74361e0e82a761371dd731e53124c6a88644993f6c463ee0e13a80e9b19ce5",
        "NeoForge 21.1.259 (LGPL-2.1)",
    ),
    TagSet(
        "fabric-1.20.1", "fabric-v1", "1.20.1", "jar",
        _fabric_module("fabric-convention-tags-v1", "1.5.6+1802ada577"),
        ("c",), ("forge", "neoforge"),
        "6fb5f65099d501756d58c5a71b947fc025544ba8a35fbe3d66be94cceec7b4b2",
        "fabric-convention-tags-v1 1.5.6+1802ada577, Fabric API 0.92.12+1.20.1 (Apache-2.0)",
    ),
    TagSet(
        "fabric-1.21.1", "fabric-v2", "1.21.1", "jar",
        _fabric_module("fabric-convention-tags-v2", "2.12.0+c3656daa19"),
        ("c",), ("forge", "neoforge"),
        "27c0dad07593e20f254d865136b684758316e498c2517ca0791de155f5624e04",
        "fabric-convention-tags-v2 2.12.0+c3656daa19, Fabric API 0.116.17+1.21.1 (Apache-2.0)",
    ),
    TagSet(
        "fabric-1.21.8", "fabric-v2", "1.21.8", "jar",
        _fabric_module("fabric-convention-tags-v2", "2.15.6+eb5df52f2c"),
        ("c",), ("forge", "neoforge"),
        "5759b3879b3600394e35734d8fe3898ce60bafa065cf29c0baa444379c803407",
        "fabric-convention-tags-v2 2.15.6+eb5df52f2c, Fabric API 0.136.1+1.21.8 (Apache-2.0)",
    ),
    TagSet(
        "fabric-26.1", "fabric-v2", "26.1", "jar",
        _fabric_module("fabric-convention-tags-v2", "4.3.2+c37e6e5f47"),
        ("c",), ("forge", "neoforge"),
        "2ad9000533854911d010e51e34de367e8faf1293d9842d2907ce9a4ac09b3c54",
        "fabric-convention-tags-v2 4.3.2+c37e6e5f47, Fabric API 0.145.1+26.1 (Apache-2.0)",
    ),
    *(
        TagSet(
            f"vanilla-{mc}", "vanilla", mc, "mcmeta",
            f"{_MCMETA}/{commit}/data/tag/item/data.json",
            ("minecraft",), (),
            sha256,
            f"vanilla {mc} item tags, misode/mcmeta {mc}-summary@{commit[:12]} ((c) Mojang AB)",
        )
        for mc, commit, sha256 in (
            ("1.16.5", "a563df91ebca25cbc0f4d8425e292f96898f67f2",
             "db3640c324dd8fe00c3c32ee0c9e7bceb69391548ca652ee722481e4d4f1df3e"),
            ("1.19.2", "46c4aad97f832bce252038b737a3c3e448f5c69f",
             "67d36eba330da8a351f5cca999d6e5f03bac1c604c39035a920aaa47226352b4"),
            ("1.20.1", "15f05b54846b0cc5adebe63b245c7045ba105709",
             "41e09a7d436dcb472766b67ff548709652ed3a95dd491cd5d1db7c751a9bdd12"),
            ("1.21.1", "7cffbcdad5fa36f22acef6bd4b869ecad4ca3fd9",
             "a02b0749ab04a60c1c6b179af2696ee8a72d751f881c678bcfc3fe62da3ac61d"),
            ("1.21.8", "eb65724be139c7a80f5074725537f76c27633d44",
             "35d7cef03dc33e2fa755bc5ee4526fed58e5232ba8bf8adbd954d437d61e38dd"),
            ("26.1", "e7068326fb23dcdff9fff17c7eabcd59f46e7460",
             "1c23c1bbe50e63f7eb4311c7d845da675d34baf701d1b7c216ff2a09d5dd08da"),
        )
    ),
)
BY_ID = {s.id: s for s in SETS}

_TAG_PATH = re.compile(r"^data/([a-z0-9_.-]+)/tags/items?/(.+)\.json$")


# -- versions --------------------------------------------------------------
def version_key(text: str | None) -> int | None:
    """``1.20.1`` -> 12001, ``26.1`` -> 260100; None when it isn't a version."""
    if not text:
        return None
    match = re.match(r"^\s*(\d+)\.(\d+)(?:\.(\d+))?", str(text))
    if not match:
        return None
    major, minor, patch = (int(g or 0) for g in match.groups())
    return major * 10000 + minor * 100 + patch


def _nearest(candidates: list[TagSet], minecraft: str) -> TagSet | None:
    want = version_key(minecraft)
    if want is None or not candidates:
        return None
    # Closest game version; on a tie, the older one (its tags all still exist).
    return min(candidates, key=lambda s: (abs(version_key(s.minecraft) - want), version_key(s.minecraft)))


def select(loader: str | None, minecraft: str | None) -> list[TagSet]:
    """The loader set and the vanilla set for a mod, nearest its declared version.

    Empty when the version is unknown or the loader has no tag data (pre-1.13
    Forge had no tags). Forge and NeoForge before 1.20.5 used ``forge:`` tags,
    so both map to Forge's set; NeoForge from 1.20.5 on uses ``c:``. Fabric
    switched from convention tags v1 (``c:iron_ingots``) to v2
    (``c:ingots/iron``) in 1.20.5.
    """
    key = version_key(minecraft)
    if key is None or key < 11300:
        return []
    chosen: list[TagSet] = []
    family = None
    if loader == "forge" or (loader == "neoforge" and key < 12005):
        family = "forge"
    elif loader == "neoforge":
        family = "neoforge"
    elif loader in ("fabric", "quilt"):
        family = "fabric-v1" if key < 12005 else "fabric-v2"
    if family:
        found = _nearest([s for s in SETS if s.family == family], minecraft)
        if found:
            chosen.append(found)
    vanilla = _nearest([s for s in SETS if s.family == "vanilla"], minecraft)
    if vanilla:
        chosen.append(vanilla)
    return chosen


# -- deriving ----------------------------------------------------------------
def _entries(values) -> list:
    """A tag file's values, kept as written (plain ids, or {"id", "required"})."""
    kept: list = []
    for entry in values if isinstance(values, list) else []:
        if isinstance(entry, str):
            kept.append(entry)
        elif isinstance(entry, dict) and isinstance(entry.get("id"), str):
            item = {"id": entry["id"]}
            if entry.get("required") is False:
                item["required"] = False
            kept.append(item)
    return kept


def _dump(tag_set: TagSet, tags: dict[str, list]) -> bytes:
    body = {"set": tag_set.id, "source": tag_set.url, "label": tag_set.label, "tags": tags}
    return (json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def derive_jar(tag_set: TagSet, jar: bytes) -> bytes:
    """A loader jar -> {tag id: values} for its item tags in the set's namespaces."""
    tags: dict[str, list] = {}
    with zipfile.ZipFile(io.BytesIO(jar)) as zf:
        for name in zf.namelist():
            match = _TAG_PATH.match(name)
            if not match or match.group(1) not in tag_set.namespaces:
                continue
            data = json.loads(zf.read(name))
            if isinstance(data, dict):
                tags[f"{match.group(1)}:{match.group(2)}"] = _entries(data.get("values"))
    return _dump(tag_set, tags)


def derive_mcmeta(tag_set: TagSet, summary: bytes) -> bytes:
    """mcmeta's item tag summary -> {minecraft:<tag>: values}."""
    data = json.loads(summary)
    tags = {
        f"minecraft:{name}": _entries(body.get("values"))
        for name, body in data.items()
        if isinstance(body, dict)
    }
    return _dump(tag_set, tags)


def derive(tag_set: TagSet, raw: bytes) -> bytes:
    return derive_jar(tag_set, raw) if tag_set.kind == "jar" else derive_mcmeta(tag_set, raw)


# -- cache -------------------------------------------------------------------
def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def set_path(tag_set: TagSet, cache: Path | None = None) -> Path:
    return Path(cache or cache_dir()) / f"tags-{tag_set.id}-{tag_set.sha256[:12]}.json"


def cached(tag_set: TagSet, cache: Path | None = None) -> Path | None:
    """The verified cached set, or None when it is missing or doesn't match the pin."""
    path = set_path(tag_set, cache)
    return path if path.is_file() and _sha256(path.read_bytes()) == tag_set.sha256 else None


def download(tag_set: TagSet, opener=urllib.request.urlopen) -> bytes:
    """The derived set, straight from upstream (unverified)."""
    request = urllib.request.Request(tag_set.url, headers={"User-Agent": _USER_AGENT})
    try:
        with opener(request, timeout=300) as response:
            raw = response.read()
        return derive(tag_set, raw)
    except (OSError, ValueError, AttributeError, zipfile.BadZipFile) as exc:
        raise ReferenceDataError(f"{tag_set.id}: download failed from {tag_set.url}: {exc}") from exc


def fetch(tag_set: TagSet, cache: Path | None = None, opener=urllib.request.urlopen) -> tuple[Path, bool]:
    """Return (cached path, downloaded?). Raises ReferenceDataError on failure or a hash mismatch."""
    cache = Path(cache or cache_dir())
    hit = cached(tag_set, cache)
    if hit:
        return hit, False
    data = download(tag_set, opener)
    digest = _sha256(data)
    if digest != tag_set.sha256:
        raise ReferenceDataError(
            f"{tag_set.id}: sha256 mismatch for {tag_set.url} (got {digest[:16]}..., "
            f"pinned {tag_set.sha256[:16]}...); re-pin it on purpose"
        )
    cache.mkdir(parents=True, exist_ok=True)
    target = set_path(tag_set, cache)
    partial = target.with_suffix(".part")
    partial.write_bytes(data)
    partial.replace(target)
    _read.cache_clear()
    return target, True


@lru_cache(maxsize=16)
def _read(path: str, mtime_ns: int, size: int, sha256: str | None) -> dict[str, list] | None:
    data = Path(path).read_bytes()
    if sha256 is not None and _sha256(data) != sha256:
        return None
    try:
        tags = json.loads(data).get("tags")
    except (ValueError, AttributeError):
        return None
    return tags if isinstance(tags, dict) else None


def load(tag_set: TagSet) -> dict[str, list] | None:
    """The set's tags from the cache (or PORTKIT_TAG_REFERENCE), or None."""
    override = os.environ.get(_ENV_DIR)
    if override:
        path, verify = Path(override).expanduser() / f"{tag_set.id}.json", None
    else:
        path, verify = set_path(tag_set), tag_set.sha256
    try:
        stat = path.stat()
    except OSError:
        return None
    return _read(str(path), stat.st_mtime_ns, stat.st_size, verify)


# -- what the resolver reads -------------------------------------------------
@dataclass
class TagReference:
    """Item tags the loader and vanilla define, for one mod's loader and version."""

    tags: dict[str, list] = field(default_factory=dict)
    namespaces: frozenset[str] = frozenset()  # shared namespaces this reference is complete for
    foreign: frozenset[str] = frozenset()  # shared namespaces the loader never writes to
    used: list[TagSet] = field(default_factory=list)  # sets loaded
    missing: list[TagSet] = field(default_factory=list)  # sets selected but not cached

    def covers(self, tag: str) -> bool:
        ns = tag.partition(":")[0]
        return ns in self.namespaces or ns in self.foreign

    def values(self, tag: str) -> list | None:
        """The loader's or vanilla's share of a tag in a covered namespace
        (``[]`` when that authority doesn't define it, or never writes to that
        namespace), else None."""
        ns = tag.partition(":")[0]
        if ns in self.foreign and ns not in self.namespaces:
            return []
        if ns not in self.namespaces:
            return None
        return list(self.tags.get(tag, []))

    def describe(self) -> str:
        return ", ".join(s.label for s in self.used) or "none"


def reference_for(loader: str | None, minecraft: str | None) -> TagReference:
    """The cached reference for a mod; namespaces with no cached data stay uncovered."""
    ref = TagReference()
    covered: set[str] = set()
    foreign: set[str] = set()
    for tag_set in select(loader, minecraft):
        tags = load(tag_set)
        if tags is None:
            ref.missing.append(tag_set)
            continue
        ref.used.append(tag_set)
        ref.tags.update(tags)
        covered |= set(tag_set.namespaces)
        foreign |= set(tag_set.foreign)
    ref.namespaces = frozenset(covered)
    ref.foreign = frozenset(foreign - covered)
    return ref


def _print_pins() -> int:
    """Download every set and print its derived sha256 (for bumping a pin)."""
    failed = 0
    for tag_set in SETS:
        try:
            digest = _sha256(download(tag_set))
        except ReferenceDataError as exc:
            print(f"FAILED {exc}", file=sys.stderr)
            failed += 1
            continue
        state = "ok" if digest == tag_set.sha256 else "CHANGED"
        print(f"{tag_set.id:18} {digest} {state}")
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover - maintenance helper
    if sys.argv[1:] == ["--pins"]:
        sys.exit(_print_pins())
    print(f"usage: python -m portkit.data.tags --pins   (fetch with `{FETCH_COMMAND}`)")
    sys.exit(2)
