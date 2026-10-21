"""Vanilla Java sound events, fetched on demand (#356).

A mod's sounds.json can play another event instead of a file:
``{"name": "minecraft:block.grindstone.use", "type": "event"}``. Bedrock's
sound_definitions.json has no such reference, so the sound converter inlines
the target event's sounds (``converters/sounds.py``). When the target is a
vanilla event, its sounds are listed in vanilla's own
``assets/minecraft/sounds.json``, which the mod jar doesn't carry. That file is
Mojang's, so, like the Bedrock vanilla sound list (#124), the item tags (#160)
and the model templates, it is never vendored: ``portkit reference fetch``
downloads misode/mcmeta's sound summary (``sounds/data.json``, the vanilla
sounds.json of that game version) for each version in :data:`SETS`, at the
summary commits the vanilla item tag sets pin (data/tags.py), keeps each
event's ``sounds`` list as written (subtitles and ``replace`` are dropped),
checks the result against the pinned sha256 and caches it beside the other
reference data.

Which Bedrock file a vanilla Java sound plays is not decided here: the sound
converter keeps the existing same-path rule (#116/#124), so a vanilla sound is
kept only when Bedrock's own vanilla pack has a file at ``sounds/<path>``. No
hand table (#220), no guessed path (#87).

At conversion time :func:`vanilla_events` picks the set nearest the game
version the jar declares (the same rule as the tag and campfire recipe sets)
and reads it from the cache only. Without it, it returns None and a vanilla
target is dropped with a note saying to run the fetch.
``PORTKIT_JAVA_SOUND_REFERENCE`` names a JSON file (``{"events": {...}}``) to
use instead, unverified: it is how the tests run offline.

``python -m portkit.data.java_sounds --pins`` downloads every set and prints
the sha256 to pin.
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

_ENV_FILE = "PORTKIT_JAVA_SOUND_REFERENCE"
_MCMETA = "https://raw.githubusercontent.com/misode/mcmeta"


@dataclass(frozen=True)
class SoundSet:
    id: str
    minecraft: str
    url: str
    sha256: str  # of the derived JSON (see derive); bump with the commit
    label: str


# The same mcmeta summary commits the vanilla item tag sets pin (data/tags.py).
SETS: tuple[SoundSet, ...] = tuple(
    SoundSet(
        f"sounds-java-vanilla-{mc}", mc, f"{_MCMETA}/{commit}/sounds/data.json", sha256,
        f"vanilla {mc} sounds.json, misode/mcmeta {mc}-summary@{commit[:12]} ((c) Mojang AB)",
    )
    for mc, commit, sha256 in (
        ("1.16.5", "a563df91ebca25cbc0f4d8425e292f96898f67f2",
         "ee463f23c19d5873f8906b489e6263c9c89e019134648511cfbe4f0584093867"),
        ("1.19.2", "46c4aad97f832bce252038b737a3c3e448f5c69f",
         "c2e6eb7817aceaacd040ae02d40d75fdbbca65f018f9cccb9576e810fb3822a1"),
        ("1.20.1", "15f05b54846b0cc5adebe63b245c7045ba105709",
         "9b078a91f135eff0b23212514d92d0efd29ea7839ef9ed71da3d69368d4c89f9"),
        ("1.21.1", "7cffbcdad5fa36f22acef6bd4b869ecad4ca3fd9",
         "ea2d5a3a9fde0ab31d5e8fbfc2b738afa89f069ddb5e48021f71c7ad82504974"),
        ("1.21.8", "eb65724be139c7a80f5074725537f76c27633d44",
         "39f20e7caecb75e76f2c4eb53310364a7d0bea98273f7823d4d6362354f5db85"),
        ("26.1", "e7068326fb23dcdff9fff17c7eabcd59f46e7460",
         "32ddbfa39df902774092d4bbd7ef9c99738a3350c96c302a0b36877e224a5100"),
    )
)


def derive(sound_set: SoundSet, summary: bytes) -> bytes:
    """mcmeta's sound summary -> {"minecraft:<event>": [sound, ...]}, each list as written."""
    data = json.loads(summary)
    kept = {
        f"minecraft:{name}": body["sounds"]
        for name, body in sorted(data.items())
        if isinstance(body, dict) and isinstance(body.get("sounds"), list)
    }
    if not kept:
        raise ValueError("no sound event in the summary")
    out = {"set": sound_set.id, "source": sound_set.url, "label": sound_set.label, "events": kept}
    return (json.dumps(out, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def set_path(sound_set: SoundSet, cache: Path | None = None) -> Path:
    return Path(cache or cache_dir()) / f"{sound_set.id}-{sound_set.sha256[:12]}.json"


def cached(sound_set: SoundSet, cache: Path | None = None) -> Path | None:
    path = set_path(sound_set, cache)
    return path if path.is_file() and _sha256(path.read_bytes()) == sound_set.sha256 else None


def download(sound_set: SoundSet, opener=urllib.request.urlopen) -> bytes:
    request = urllib.request.Request(sound_set.url, headers={"User-Agent": _USER_AGENT})
    try:
        with opener(request, timeout=300) as response:
            raw = response.read()
        return derive(sound_set, raw)
    except (OSError, ValueError, AttributeError) as exc:
        raise ReferenceDataError(f"{sound_set.id}: download failed from {sound_set.url}: {exc}") from exc


def fetch(sound_set: SoundSet, cache: Path | None = None,
          opener=urllib.request.urlopen) -> tuple[Path, bool]:
    """Return (cached path, downloaded?). Raises ReferenceDataError on failure or a hash mismatch."""
    cache = Path(cache or cache_dir())
    hit = cached(sound_set, cache)
    if hit:
        return hit, False
    data = download(sound_set, opener)
    digest = _sha256(data)
    if digest != sound_set.sha256:
        raise ReferenceDataError(
            f"{sound_set.id}: sha256 mismatch for {sound_set.url} (got {digest[:16]}..., "
            f"pinned {sound_set.sha256[:16]}...); re-pin it on purpose"
        )
    cache.mkdir(parents=True, exist_ok=True)
    target = set_path(sound_set, cache)
    partial = target.with_suffix(".part")
    partial.write_bytes(data)
    partial.replace(target)
    _read.cache_clear()
    return target, True


@lru_cache(maxsize=4)
def _read(path: str, mtime_ns: int, size: int, sha256: str | None) -> dict[str, list] | None:
    data = Path(path).read_bytes()
    if sha256 is not None and _sha256(data) != sha256:
        return None
    try:
        found = json.loads(data).get("events")
    except (ValueError, AttributeError):
        return None
    return found if isinstance(found, dict) else None


def select(minecraft: str | None) -> SoundSet | None:
    """The set nearest the jar's game version (on a tie the older), or None."""
    from .tags import version_key

    want = version_key(minecraft)
    if want is None:
        return None
    return min(SETS, key=lambda s: (abs(version_key(s.minecraft) - want), version_key(s.minecraft)))


def vanilla_events(minecraft: str | None) -> tuple[dict[str, list] | None, SoundSet | None]:
    """(vanilla sound events -> their sounds lists, the set read) for a jar's game
    version; the events are None when the set isn't cached (run ``portkit reference
    fetch``) or the jar declares no game version."""
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
    for sound_set in SETS:
        try:
            digest = _sha256(download(sound_set))
        except ReferenceDataError as exc:
            print(f"FAILED {exc}", file=sys.stderr)
            failed += 1
            continue
        print(f"{sound_set.id:34} {digest} {'ok' if digest == sound_set.sha256 else 'CHANGED'}")
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover - maintenance helper
    if sys.argv[1:] == ["--pins"]:
        sys.exit(_print_pins())
    print(f"usage: python -m portkit.data.java_sounds --pins   (fetch with `{FETCH_COMMAND}`)")
    sys.exit(2)
