"""Vanilla Java block tags, fetched on demand (#298).

Java says which tool mines a block and which tier it needs to drop it only
through block tags, and vanilla's own tags nest: ``minecraft:mineable/axe``
holds ``#minecraft:logs``, ``#minecraft:planks``, ``#minecraft:wooden_slabs``
and the other wooden things, so a mod block that only sits in
``#minecraft:logs`` (the usual way to make a log axe-mineable) is axe-mineable
in Java. The mod's own jar files never spell that nesting out, so reading only
them leaves such a block with no tool tag at all (#293's recorded gap).

The data is misode/mcmeta's, at the same per-version summary commits the
vanilla item tag sets pin (:mod:`portkit.data.tags`): the block tag summary of
that game version (``data/tag/block/data.json``) or, when a version ships no
summary, vanilla's own tag files under ``data/minecraft/tags/block(s)/``. It is
generated from the game, so (c) Mojang AB, used under the Minecraft EULA: it
is never vendored, and the repository and the wheel don't carry it.

``portkit reference fetch`` downloads each set, keeps every block tag's values
as written (nested ``#tag`` entries included, so the nesting can be expanded),
checks the result against the pinned sha256 and caches it beside the other
reference data. Without the network the pins are still empty: run
``python -m portkit.data.vanilla_block_tags --pins`` to print the sha256 of
each set and paste it in.

At conversion time :func:`vanilla_tags` picks the set nearest the game version
the jar declares and reads it from the cache only, never the network. Without
it, it returns None and the converter reads the mod's own tag files only, as
before (#298), saying to run the fetch.

``PORTKIT_VANILLA_BLOCK_TAGS`` names a derived file to use instead,
unverified: it is how the tests run offline.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import FETCH_COMMAND, ReferenceDataError, _USER_AGENT, cache_dir
from .tags import SETS as _ITEM_SETS, version_key

_ENV_FILE = "PORTKIT_VANILLA_BLOCK_TAGS"
_MCMETA = "https://raw.githubusercontent.com/misode/mcmeta"
_MCMETA_API = "https://api.github.com/repos/misode/mcmeta"
_COMMIT = re.compile(r"/mcmeta/([0-9a-f]{40})/")
# Vanilla's own block tag files (pre-1.21 "blocks", 1.21 "block").
_RAW_DIRS = ("data/minecraft/tags/blocks/", "data/minecraft/tags/block/")


@dataclass(frozen=True)
class BlockTagSet:
    """One pinned source of vanilla block tags."""

    id: str
    minecraft: str
    commit: str
    url: str  # the block tag summary of that version
    tree_url: str  # the git tree of the same commit (the raw tag files)
    raw_url: str  # the raw file base of the same commit
    sha256: str  # of the derived JSON; empty until it is pinned
    label: str  # what it is, for `portkit reference list` and notes


def _commits() -> dict[str, str]:
    """The mcmeta summary commit of every pinned vanilla game version (the
    vanilla item tag sets pin them, data/tags.py)."""
    found: dict[str, str] = {}
    for tag_set in _ITEM_SETS:
        if tag_set.family != "vanilla":
            continue
        match = _COMMIT.search(tag_set.url)
        if match:
            found[tag_set.minecraft] = match.group(1)
    return found


SETS: tuple[BlockTagSet, ...] = tuple(
    BlockTagSet(
        f"vanilla-block-tags-{mc}", mc, commit,
        f"{_MCMETA}/{commit}/data/tag/block/data.json",
        f"{_MCMETA_API}/git/trees/{commit}?recursive=1",
        f"{_MCMETA}/{commit}",
        "",
        f"vanilla {mc} block tags, misode/mcmeta {mc}-summary@{commit[:12]} ((c) Mojang AB)",
    )
    for mc, commit in sorted(_commits().items(), key=lambda kv: version_key(kv[0]))
)
BY_ID = {s.id: s for s in SETS}


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


def _dump(tag_set: BlockTagSet, tags: dict[str, list], source: str) -> bytes:
    body = {"set": tag_set.id, "source": source, "label": tag_set.label, "tags": tags}
    return (json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def derive(tag_set: BlockTagSet, summary: bytes, source: str | None = None) -> bytes:
    """mcmeta's block tag summary -> {minecraft:<tag>: values}, values as written."""
    data = json.loads(summary)
    if not isinstance(data, dict):
        raise ValueError("the block tag summary is not an object")
    tags: dict[str, list] = {}
    for name, body in data.items():
        if not isinstance(body, dict):
            continue
        values = body.get("values")
        if not isinstance(values, list):
            continue
        tags[f"minecraft:{name}"] = _entries(values)
    if not tags:
        raise ValueError("no block tag in the summary")
    return _dump(tag_set, tags, source or tag_set.url)


def _tag_id(path: str) -> str | None:
    """The tag id of a vanilla tag file path, or None when it isn't one."""
    for folder in _RAW_DIRS:
        if path.startswith(folder) and path.endswith(".json"):
            rest = path[len(folder):-len(".json")]
            return f"minecraft:{rest}" if rest else None
    return None


def derive_raw(tag_set: BlockTagSet, files: dict[str, bytes], source: str) -> bytes:
    """Vanilla's own block tag files -> {minecraft:<tag>: values}, values as written."""
    tags: dict[str, list] = {}
    for path, raw in files.items():
        tag = _tag_id(path)
        if tag is None:
            continue
        body = json.loads(raw)
        values = body.get("values") if isinstance(body, dict) else None
        tags[tag] = _entries(values) if isinstance(values, list) else []
    if not tags:
        raise ValueError("no vanilla block tag file")
    return _dump(tag_set, tags, source)


# -- cache -------------------------------------------------------------------
def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def set_path(tag_set: BlockTagSet, cache: Path | None = None) -> Path:
    suffix = tag_set.sha256[:12] if tag_set.sha256 else "unpinned"
    return Path(cache or cache_dir()) / f"{tag_set.id}-{suffix}.json"


def cached(tag_set: BlockTagSet, cache: Path | None = None) -> Path | None:
    """The cached set, or None when it is missing or doesn't match the pin."""
    path = set_path(tag_set, cache)
    if not path.is_file():
        return None
    if tag_set.sha256 and _sha256(path.read_bytes()) != tag_set.sha256:
        return None
    return path


def _read_url(url: str, opener) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": _USER_AGENT, "Accept": "application/vnd.github+json"})
    with opener(request, timeout=300) as response:
        return response.read()


def _download_raw(tag_set: BlockTagSet, opener) -> bytes:
    """Vanilla's own block tag files of that commit, through the git tree."""
    tree = json.loads(_read_url(tag_set.tree_url, opener))
    paths = sorted(p for p in (entry.get("path", "") for entry in tree.get("tree", []))
                   if _tag_id(p) is not None)
    if not paths:
        raise ValueError("the commit's tree holds no vanilla block tag file")
    files = {path: _read_url(f"{tag_set.raw_url}/{path}", opener) for path in paths}
    return derive_raw(tag_set, files, tag_set.tree_url)


def download(tag_set: BlockTagSet, opener=urllib.request.urlopen) -> bytes:
    """The derived set, straight from upstream (unverified)."""
    try:
        raw = _read_url(tag_set.url, opener)
        return derive(tag_set, raw)
    except (OSError, ValueError, AttributeError) as exc:
        summary_error = exc
    try:
        return _download_raw(tag_set, opener)
    except (OSError, ValueError, AttributeError, KeyError, TypeError) as exc:
        raise ReferenceDataError(
            f"{tag_set.id}: download failed from {tag_set.url} ({summary_error}) and from the "
            f"vanilla tag files of {tag_set.commit} ({exc})") from exc


def fetch(tag_set: BlockTagSet, cache: Path | None = None,
          opener=urllib.request.urlopen) -> tuple[Path, bool]:
    """Return (cached path, downloaded?). Raises ReferenceDataError on failure or a hash mismatch."""
    cache = Path(cache or cache_dir())
    hit = cached(tag_set, cache)
    if hit:
        return hit, False
    data = download(tag_set, opener)
    digest = _sha256(data)
    if tag_set.sha256 and digest != tag_set.sha256:
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


def select(minecraft: str | None) -> BlockTagSet | None:
    """The set nearest the jar's game version (on a tie the older), or None."""
    want = version_key(minecraft)
    if want is None:
        return None
    return min(SETS, key=lambda s: (abs(version_key(s.minecraft) - want), version_key(s.minecraft)))


def vanilla_tags(minecraft: str | None) -> dict[str, list] | None:
    """Vanilla's own block tag values (tag id -> its values as written) for the
    game version nearest the one the jar declares, or None when they aren't
    cached (run ``portkit reference fetch``).

    The values keep their nested ``#tag`` entries, so the caller can expand
    vanilla's nesting of a tag the way the mod's own files are expanded.
    """
    override = os.environ.get(_ENV_FILE)
    chosen = select(minecraft)
    if override:
        path, verify = Path(override).expanduser(), None
    elif chosen is None:
        return None
    else:
        path, verify = set_path(chosen), (chosen.sha256 or None)
    try:
        stat = path.stat()
    except OSError:
        return None
    return _read(str(path), stat.st_mtime_ns, stat.st_size, verify)


def _print_pins() -> int:
    """Download every set and print its derived sha256 (for pinning)."""
    failed = 0
    for tag_set in SETS:
        try:
            digest = _sha256(download(tag_set))
        except ReferenceDataError as exc:
            print(f"FAILED {exc}", file=sys.stderr)
            failed += 1
            continue
        state = "ok" if digest == tag_set.sha256 else ("CHANGED" if tag_set.sha256 else "NEW")
        print(f"{tag_set.id:28} {digest} {state}")
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover - maintenance helper
    if sys.argv[1:] == ["--pins"]:
        sys.exit(_print_pins())
    print(f"usage: python -m portkit.data.vanilla_block_tags --pins   (fetch with `{FETCH_COMMAND}`)")
    sys.exit(2)
