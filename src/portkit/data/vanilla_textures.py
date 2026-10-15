"""Bedrock's vanilla texture atlases, fetched on demand: which texture files
the vanilla resource pack has and the short names its atlases give them.

A mod's model often borrows a vanilla texture (``minecraft:block/stone``,
``minecraft:item/stick``). The Bedrock pack must not carry Mojang's art, and it
doesn't need to: every pack sits on top of the vanilla resource pack, whose
``terrain_texture.json`` and ``item_texture.json`` are merged with the pack's
own, so a block's material instance or an item's icon can name a vanilla short
name directly (bedrock-wiki concepts/overwriting-assets; Mojang's own
``minecraft:red_shrub`` block names the vanilla short name ``red_shrub``). What
the converter needs is the index: which file (``textures/blocks/stone``) each
short name points at.

That index is derived from Mojang/bedrock-samples (``(c) Mojang AB``, subject to
the Minecraft EULA, #24), so like the vanilla sound list (#124) it is never
vendored: ``portkit reference fetch`` downloads the vanilla
``terrain_texture.json``, ``item_texture.json`` and ``flipbook_textures.json``
at the pinned commit, keeps only short names and file paths (no art, nothing
else), checks the result against :data:`SHA256` and caches it.

Without it, :func:`index` returns None and vanilla texture references stay
residue, saying to run the fetch. ``PORTKIT_VANILLA_TEXTURES`` names an index
file to use instead, unverified: it is how the tests run offline against a tiny
index of their own.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from functools import lru_cache
from pathlib import Path

from . import COMMIT, FETCH_COMMAND, REPO, ReferenceDataError, _USER_AGENT, cache_dir

_ENV_FILE = "PORTKIT_VANILLA_TEXTURES"

SET_ID = "vanilla-textures"
SOURCES = {
    "terrain": "resource_pack/textures/terrain_texture.json",
    "item": "resource_pack/textures/item_texture.json",
    "flipbook": "resource_pack/textures/flipbook_textures.json",
}
URLS = {key: f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/{path}" for key, path in SOURCES.items()}
LABEL = f"Bedrock vanilla texture atlases, {REPO}@{COMMIT[:12]} ((c) Mojang AB)"

# sha256 of the derived JSON (see derive). `python -m portkit.data.vanilla_textures --pin`
# prints it; bump it together with portkit.data.COMMIT.
SHA256 = "2793293a635381110f54e0dea2991c04b42980658e97749c433b836687f824e7"


def _json(raw: bytes):
    """bedrock-samples' atlases open with a // comment line; json takes none."""
    text = raw.decode("utf-8-sig")
    lines = [line for line in text.splitlines() if not line.lstrip().startswith("//")]
    return json.loads("\n".join(lines))


def _atlas(raw: bytes) -> dict[str, dict]:
    """One atlas -> {short name: {"paths": [...distinct files...], "plain": bool}}.

    ``plain`` is False when the entry dresses its file (an overlay or tint
    colour, a quad flag): naming that short name brings the dressing along."""
    data = _json(raw).get("texture_data") or {}
    out: dict[str, dict] = {}
    for short, entry in data.items():
        if not isinstance(entry, dict):
            continue
        textures = entry.get("textures")
        items = textures if isinstance(textures, list) else [textures]
        paths: list[str] = []
        plain = set(entry) == {"textures"}
        for item in items:
            if isinstance(item, dict):
                path = item.get("path")
                plain = plain and set(item) == {"path"}
            else:
                path = item
            if isinstance(path, str) and path not in paths:
                paths.append(path)
        if paths:
            out[short] = {"paths": paths, "plain": plain}
    return out


def derive(terrain: bytes, item: bytes, flipbook: bytes) -> bytes:
    """The three vanilla atlases -> the index: short names and file paths only."""
    animated: dict[str, list[str]] = {}
    for entry in _json(flipbook):
        if isinstance(entry, dict) and isinstance(entry.get("flipbook_texture"), str):
            tiles = animated.setdefault(entry["flipbook_texture"], [])
            if isinstance(entry.get("atlas_tile"), str) and entry["atlas_tile"] not in tiles:
                tiles.append(entry["atlas_tile"])
    out = {
        "set": SET_ID,
        "source": {key: URLS[key] for key in SOURCES},
        "label": LABEL,
        "terrain": _atlas(terrain),
        "item": _atlas(item),
        "flipbook": {path: sorted(tiles) for path, tiles in animated.items()},
    }
    return (json.dumps(out, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def set_path(cache: Path | None = None) -> Path:
    return Path(cache or cache_dir()) / f"{SET_ID}-{SHA256[:12]}.json"


def cached(cache: Path | None = None) -> Path | None:
    """The verified cached index, or None when it is missing or doesn't match the pin."""
    path = set_path(cache)
    return path if path.is_file() and _sha256(path.read_bytes()) == SHA256 else None


def download(opener=urllib.request.urlopen) -> bytes:
    """The derived index, straight from upstream (unverified)."""
    raw: dict[str, bytes] = {}
    for key, url in URLS.items():
        request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with opener(request, timeout=120) as response:
                raw[key] = response.read()
        except (OSError, ValueError, AttributeError) as exc:
            raise ReferenceDataError(f"{SET_ID}: download failed from {url}: {exc}") from exc
    try:
        return derive(raw["terrain"], raw["item"], raw["flipbook"])
    except (ValueError, AttributeError, TypeError) as exc:
        raise ReferenceDataError(f"{SET_ID}: could not read the atlases: {exc}") from exc


def fetch(cache: Path | None = None, opener=urllib.request.urlopen) -> tuple[Path, bool]:
    """Return (cached path, downloaded?). Raises ReferenceDataError on failure or a hash mismatch."""
    cache = Path(cache or cache_dir())
    hit = cached(cache)
    if hit:
        return hit, False
    data = download(opener)
    digest = _sha256(data)
    if digest != SHA256:
        raise ReferenceDataError(
            f"{SET_ID}: sha256 mismatch for {REPO}@{COMMIT[:12]} (got {digest[:16]}..., "
            f"pinned {SHA256[:16]}...); re-pin it on purpose"
        )
    cache.mkdir(parents=True, exist_ok=True)
    target = set_path(cache)
    partial = target.with_suffix(".part")
    partial.write_bytes(data)
    partial.replace(target)
    _read.cache_clear()
    return target, True


class Index:
    """The fetched atlases, looked up by file and by short name."""

    def __init__(self, data: dict):
        self.atlases: dict[str, dict[str, dict]] = {
            lane: dict(data.get(lane) or {}) for lane in ("terrain", "item")
        }
        self.animated: dict[str, list[str]] = dict(data.get("flipbook") or {})
        # file -> the plain one-file short names that show exactly that file
        self.sole: dict[str, dict[str, list[str]]] = {}
        # every file an atlas names, in any entry
        self.files: dict[str, set[str]] = {}
        for lane, atlas in self.atlases.items():
            sole: dict[str, list[str]] = {}
            files: set[str] = set()
            for short, entry in atlas.items():
                files.update(entry["paths"])
                if len(entry["paths"]) == 1 and entry.get("plain"):
                    sole.setdefault(entry["paths"][0], []).append(short)
            self.sole[lane] = {path: sorted(names) for path, names in sole.items()}
            self.files[lane] = files
        self._all = frozenset(f for files in self.files.values() for f in files)

    def short_names(self, lane: str) -> frozenset[str]:
        return frozenset(self.atlases.get(lane) or {})

    def all_files(self) -> frozenset[str]:
        return self._all


@lru_cache(maxsize=4)
def _read(path: str, mtime_ns: int, size: int, verify: bool) -> Index | None:
    data = Path(path).read_bytes()
    if verify and _sha256(data) != SHA256:
        return None
    try:
        found = json.loads(data)
    except ValueError:
        return None
    return Index(found) if isinstance(found, dict) else None


def index() -> Index | None:
    """The vanilla atlas index, or None when it isn't cached (run ``portkit reference fetch``)."""
    override = os.environ.get(_ENV_FILE)
    path = Path(override).expanduser() if override else set_path()
    try:
        stat = path.stat()
    except OSError:
        return None
    return _read(str(path), stat.st_mtime_ns, stat.st_size, not override)


if __name__ == "__main__":  # pragma: no cover - maintenance helper
    if sys.argv[1:] == ["--pin"]:
        digest = _sha256(download())
        print(f"{SET_ID} {digest} {'ok' if digest == SHA256 else 'CHANGED'}")
        sys.exit(0)
    print(f"usage: python -m portkit.data.vanilla_textures --pin   (fetch with `{FETCH_COMMAND}`)")
    sys.exit(2)
