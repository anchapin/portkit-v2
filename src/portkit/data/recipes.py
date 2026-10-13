"""Vanilla campfire recipes, fetched on demand (#177, the Farmer's Delight stove).

Farmer's Delight's stove cooks whatever ``minecraft:campfire_cooking`` recipe
matches the item put on it (StoveBlockEntity passes RecipeType.CAMPFIRE_COOKING
to AbstractStoveBlockEntity's recipe lookup), so its data table needs vanilla's
own campfire recipes beside the ones in the mod jar. Those recipe files are
Mojang's, so, like the vanilla sound list (#124), item tags (#160) and block
model templates, they are never vendored: ``portkit reference fetch``
downloads misode/mcmeta's recipe summary (``data/recipe/data.json``) for each
game version in :data:`SETS` at a pinned commit, keeps only the
``minecraft:campfire_cooking`` recipes (recipe id -> recipe JSON), checks the
result against the pinned sha256 and caches it beside the other reference data.

At conversion time :func:`campfire_recipes` picks the set nearest the game
version the jar declares (the same rule as the tag sets) and reads it from the
cache only. Without it, it returns None and the stove's table holds only the
jar's own campfire recipes, with a note saying to run the fetch.
``PORTKIT_RECIPE_REFERENCE`` names a JSON file (``{"recipes": {...}}``) to use
instead, unverified: it is how the tests run offline.

``python -m portkit.data.recipes --pins`` downloads every set and prints the
sha256 to pin.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import FETCH_COMMAND, ReferenceDataError, _USER_AGENT, cache_dir

_ENV_FILE = "PORTKIT_RECIPE_REFERENCE"
_MCMETA = "https://raw.githubusercontent.com/misode/mcmeta"
RECIPE_TYPE = "minecraft:campfire_cooking"


@dataclass(frozen=True)
class RecipeSet:
    id: str
    minecraft: str
    url: str
    sha256: str  # of the derived JSON (see derive); bump with the commit
    label: str


# The same mcmeta summary commits the vanilla item tag sets pin (data/tags.py).
SETS: tuple[RecipeSet, ...] = tuple(
    RecipeSet(
        f"recipes-vanilla-campfire-{mc}", mc, f"{_MCMETA}/{commit}/data/recipe/data.json", sha256,
        f"vanilla {mc} campfire recipes, misode/mcmeta {mc}-summary@{commit[:12]} ((c) Mojang AB)",
    )
    for mc, commit, sha256 in (
        ("1.21.1", "7cffbcdad5fa36f22acef6bd4b869ecad4ca3fd9",
         "6ef260c0de0dbda1a344ae3fc728b8d6acdeed7b2ad7cdc5ced942a54d57a392"),
        ("26.1", "e7068326fb23dcdff9fff17c7eabcd59f46e7460",
         "174b2e1aae9bcca5419779af954a317c9caf69fed38847db434d2a3f3becfa1a"),
    )
)


def derive(recipe_set: RecipeSet, summary: bytes) -> bytes:
    """mcmeta's recipe summary -> {"minecraft:<name>": recipe} for campfire recipes only."""
    data = json.loads(summary)
    kept = {
        f"minecraft:{name}": body
        for name, body in sorted(data.items())
        if isinstance(body, dict) and body.get("type") == RECIPE_TYPE
    }
    if not kept:
        raise ValueError("no campfire_cooking recipe in the summary")
    out = {"set": recipe_set.id, "source": recipe_set.url, "label": recipe_set.label, "recipes": kept}
    return (json.dumps(out, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def set_path(recipe_set: RecipeSet, cache: Path | None = None) -> Path:
    return Path(cache or cache_dir()) / f"{recipe_set.id}-{recipe_set.sha256[:12]}.json"


def cached(recipe_set: RecipeSet, cache: Path | None = None) -> Path | None:
    path = set_path(recipe_set, cache)
    return path if path.is_file() and _sha256(path.read_bytes()) == recipe_set.sha256 else None


def download(recipe_set: RecipeSet, opener=urllib.request.urlopen) -> bytes:
    request = urllib.request.Request(recipe_set.url, headers={"User-Agent": _USER_AGENT})
    try:
        with opener(request, timeout=300) as response:
            raw = response.read()
        return derive(recipe_set, raw)
    except (OSError, ValueError, AttributeError) as exc:
        raise ReferenceDataError(f"{recipe_set.id}: download failed from {recipe_set.url}: {exc}") from exc


def fetch(recipe_set: RecipeSet, cache: Path | None = None,
          opener=urllib.request.urlopen) -> tuple[Path, bool]:
    """Return (cached path, downloaded?). Raises ReferenceDataError on failure or a hash mismatch."""
    cache = Path(cache or cache_dir())
    hit = cached(recipe_set, cache)
    if hit:
        return hit, False
    data = download(recipe_set, opener)
    digest = _sha256(data)
    if digest != recipe_set.sha256:
        raise ReferenceDataError(
            f"{recipe_set.id}: sha256 mismatch for {recipe_set.url} (got {digest[:16]}..., "
            f"pinned {recipe_set.sha256[:16]}...); re-pin it on purpose"
        )
    cache.mkdir(parents=True, exist_ok=True)
    target = set_path(recipe_set, cache)
    partial = target.with_suffix(".part")
    partial.write_bytes(data)
    partial.replace(target)
    _read.cache_clear()
    return target, True


@lru_cache(maxsize=4)
def _read(path: str, mtime_ns: int, size: int, sha256: str | None) -> dict[str, dict] | None:
    data = Path(path).read_bytes()
    if sha256 is not None and _sha256(data) != sha256:
        return None
    try:
        found = json.loads(data).get("recipes")
    except (ValueError, AttributeError):
        return None
    return found if isinstance(found, dict) else None


def select(minecraft: str | None) -> RecipeSet | None:
    """The set nearest the jar's game version (on a tie the older), or None."""
    from .tags import version_key

    want = version_key(minecraft)
    if want is None:
        return None
    return min(SETS, key=lambda s: (abs(version_key(s.minecraft) - want), version_key(s.minecraft)))


def campfire_recipes(minecraft: str | None) -> tuple[dict[str, dict] | None, RecipeSet | None]:
    """(vanilla campfire recipes by id, the set read) for a jar's game version;
    the recipes are None when the set isn't cached (run ``portkit reference fetch``)."""
    override = os.environ.get(_ENV_FILE)
    chosen = select(minecraft)
    if override:
        path, verify = Path(override).expanduser(), None
    elif chosen is None:
        return None, None
    else:
        path, verify = set_path(chosen), chosen.sha256
    try:
        stat = path.stat()
    except OSError:
        return None, chosen
    return _read(str(path), stat.st_mtime_ns, stat.st_size, verify), chosen


def _print_pins() -> int:
    failed = 0
    for recipe_set in SETS:
        try:
            digest = _sha256(download(recipe_set))
        except ReferenceDataError as exc:
            print(f"FAILED {exc}", file=sys.stderr)
            failed += 1
            continue
        print(f"{recipe_set.id:34} {digest} {'ok' if digest == recipe_set.sha256 else 'CHANGED'}")
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover - maintenance helper
    if sys.argv[1:] == ["--pins"]:
        sys.exit(_print_pins())
    print(f"usage: python -m portkit.data.recipes --pins   (fetch with `{FETCH_COMMAND}`)")
    sys.exit(2)
