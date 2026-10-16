"""Bedrock's vanilla item ids, fetched on demand (#260).

A converted recipe's ``unlock`` may name a vanilla item (Java's ``has_<item>``
criterion), and Bedrock Dedicated Server refuses a recipe whose unlock names an
item it doesn't know ("has an invalid unlock ingredient"). Java and Bedrock ids
differ for many vanilla items (Java ``minecraft:oak_trapdoor`` /
``minecraft:terracotta`` / ``minecraft:bricks`` are Bedrock
``minecraft:trapdoor`` / ``minecraft:hardened_clay`` /
``minecraft:brick_block``), so the converter needs Bedrock's own list to check
against.

The list comes from Mojang/bedrock-samples
``metadata/vanilladata_modules/mojang-items.json`` (``(c) Mojang AB``, subject
to the Minecraft EULA, #24). Like the vanilla sound list (#124) it is never
vendored: ``portkit reference fetch`` downloads it at the pinned commit, keeps
the item ids only (``data_items[].name``), checks the result against
:data:`SHA256` and caches it.

Without it, :func:`ids` returns None and no vanilla item is written into an
unlock (the recipe falls back as if the criterion named nothing Bedrock has).
``PORTKIT_VANILLA_ITEMS`` names a list file (one id per line) to use instead,
unverified: it is how the tests run offline.

``python -m portkit.data.vanilla_items --pin`` downloads it and prints the sha256.
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

_ENV_FILE = "PORTKIT_VANILLA_ITEMS"

SET_ID = "vanilla-items"
SOURCE = "metadata/vanilladata_modules/mojang-items.json"
URL = f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/{SOURCE}"
LABEL = f"Bedrock vanilla item ids, {REPO}@{COMMIT[:12]} ((c) Mojang AB)"

# sha256 of the derived list (see derive); bump it together with portkit.data.COMMIT.
SHA256 = "f3594540c3b5ba319118a9896665c080d72cd94727c8638f9c6a30969c607279"


def derive(raw: bytes) -> bytes:
    """mojang-items.json -> a header and one item id per line, sorted."""
    data = json.loads(raw)
    names = sorted({
        entry["name"] for entry in data.get("data_items") or []
        if isinstance(entry, dict) and isinstance(entry.get("name"), str) and ":" in entry["name"]
    })
    if not names:
        raise ValueError("no item ids in mojang-items.json")
    header = (
        f"# Bedrock vanilla item ids, from {REPO}@{COMMIT} {SOURCE}.\n"
        f"# Derived by `{FETCH_COMMAND}`; (c) Mojang AB, not for redistribution.\n"
    )
    return (header + "".join(f"{n}\n" for n in names)).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def set_path(cache: Path | None = None) -> Path:
    return Path(cache or cache_dir()) / f"{SET_ID}-{SHA256[:12]}.txt"


def cached(cache: Path | None = None) -> Path | None:
    """The verified cached list, or None when it is missing or doesn't match the pin."""
    path = set_path(cache)
    return path if path.is_file() and _sha256(path.read_bytes()) == SHA256 else None


def download(opener=urllib.request.urlopen) -> bytes:
    """The derived list, straight from upstream (unverified)."""
    request = urllib.request.Request(URL, headers={"User-Agent": _USER_AGENT})
    try:
        with opener(request, timeout=120) as response:
            raw = response.read()
    except (OSError, ValueError, AttributeError) as exc:
        raise ReferenceDataError(f"{SET_ID}: download failed from {URL}: {exc}") from exc
    try:
        return derive(raw)
    except (ValueError, AttributeError, TypeError, KeyError) as exc:
        raise ReferenceDataError(f"{SET_ID}: could not read {SOURCE}: {exc}") from exc


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
            f"{SET_ID}: sha256 mismatch for {URL} (got {digest[:16]}..., "
            f"pinned {SHA256[:16]}...); re-pin it on purpose"
        )
    cache.mkdir(parents=True, exist_ok=True)
    target = set_path(cache)
    partial = target.with_suffix(".part")
    partial.write_bytes(data)
    partial.replace(target)
    _read.cache_clear()
    return target, True


@lru_cache(maxsize=4)
def _read(path: str, mtime_ns: int, size: int, verify: bool) -> frozenset[str] | None:
    data = Path(path).read_bytes()
    if verify and _sha256(data) != SHA256:
        return None
    return frozenset(
        line.strip() for line in data.decode("utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    )


def ids() -> frozenset[str] | None:
    """Every Bedrock vanilla item id, or None when the list isn't cached
    (run ``portkit reference fetch``)."""
    override = os.environ.get(_ENV_FILE)
    path = Path(override).expanduser() if override else set_path()
    try:
        stat = path.stat()
    except OSError:
        return None
    return _read(str(path), stat.st_mtime_ns, stat.st_size, not override)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args != ["--pin"]:
        print("usage: python -m portkit.data.vanilla_items --pin", file=sys.stderr)
        return 2
    print(_sha256(download()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
