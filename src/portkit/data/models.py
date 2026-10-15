"""Vanilla Java block model templates, fetched on demand (stairs, slabs, walls, panes, bars).

A mod's stairs model is usually three lines: ``"parent": "minecraft:block/stairs"``
and the three textures it wears. The boxes themselves live in vanilla's
``block/stairs.json``, which the mod jar doesn't carry. So to give a stair, a
slab, a wall or a turned pillar its geometry, the converter needs the elements
of a handful of vanilla parent models. Those files are Mojang's, so, like the
vanilla sound list (#124) and the vanilla item tags (#160), they are never
vendored: ``portkit reference fetch`` downloads misode/mcmeta's model summary
for 1.20.1 at a pinned commit, keeps only the templates in :data:`TEMPLATES`
and their parent chains (``parent``, ``textures`` and ``elements``; display
transforms and comments are dropped), checks the result against
:data:`SHA256` and caches it beside the other reference data.

These templates are byte-identical (after that derivation) in mcmeta's
1.16.5, 1.19.2, 1.20.1, 1.21.1, 1.21.8 and 26.1 summaries, the versions the tag
data is pinned for, so one set serves every mod. Checked on 2026-10-12.
The glass pane and iron bars templates (#56) were added on 2026-10-14 and
checked the same way: the panes are identical in all six; 26.1 moves the
iron_bars_* models onto new template_bars_* parents, whose resolved elements
and texture variable names are identical to 1.20.1's.

Without the set, :func:`templates` returns None and the block converter keeps
these shapes as residue, saying to run the fetch. ``PORTKIT_MODEL_REFERENCE``
names a JSON file of templates to use instead, unverified: it is how the tests
run offline against small hand-written shapes of their own.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from functools import lru_cache
from pathlib import Path

from . import FETCH_COMMAND, ReferenceDataError, _USER_AGENT, cache_dir

_ENV_FILE = "PORTKIT_MODEL_REFERENCE"

# misode/mcmeta 1.20.1-summary, the commit the vanilla-1.20.1 tag set pins.
COMMIT = "15f05b54846b0cc5adebe63b245c7045ba105709"
URL = f"https://raw.githubusercontent.com/misode/mcmeta/{COMMIT}/assets/model/data.json"
LABEL = f"vanilla 1.20.1 block model templates, misode/mcmeta 1.20.1-summary@{COMMIT[:12]} ((c) Mojang AB)"
SET_ID = "models-vanilla-1.20.1"

# The vanilla parents whose elements the block converter reads. Their parent
# chains (block/cube, block/block) come along.
TEMPLATES = (
    "block/stairs", "block/inner_stairs", "block/outer_stairs",
    "block/slab", "block/slab_top",
    "block/template_wall_post", "block/template_wall_side", "block/template_wall_side_tall",
    "block/fence_post", "block/fence_side",
    "block/template_glass_pane_post", "block/template_glass_pane_side",
    "block/template_glass_pane_side_alt", "block/template_glass_pane_noside",
    "block/template_glass_pane_noside_alt",
    "block/iron_bars_post", "block/iron_bars_post_ends", "block/iron_bars_cap",
    "block/iron_bars_cap_alt", "block/iron_bars_side", "block/iron_bars_side_alt",
    "block/cube", "block/cube_all", "block/cube_column", "block/cube_column_horizontal",
)

# sha256 of the derived JSON (see derive). `python -m portkit.data.models --pin`
# prints it; bump it together with COMMIT.
SHA256 = "5b2d3fff3b1536e00e2f92b9951941f987f3d4a6c5a4f6dbac27791d8cfbcb49"


def derive(summary: bytes) -> bytes:
    """mcmeta's model summary -> {"minecraft:block/<name>": {parent, textures, elements}}."""
    data = json.loads(summary)
    kept: dict[str, dict] = {}
    todo = list(TEMPLATES)
    while todo:
        name = todo.pop()
        key = f"minecraft:{name}"
        if key in kept:
            continue
        model = data.get(name)
        if not isinstance(model, dict):
            raise ValueError(f"model {name!r} is not in the summary")
        body = {k: model[k] for k in ("parent", "textures", "elements") if k in model}
        for element in body.get("elements") or []:
            if isinstance(element, dict):
                element.pop("__comment", None)
        if isinstance(body.get("parent"), str):
            parent = body["parent"]
            body["parent"] = parent if ":" in parent else f"minecraft:{parent}"
            todo.append(body["parent"].partition(":")[2])
        kept[key] = body
    out = {"set": SET_ID, "source": URL, "label": LABEL, "models": kept}
    return (json.dumps(out, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def set_path(cache: Path | None = None) -> Path:
    return Path(cache or cache_dir()) / f"{SET_ID}-{SHA256[:12]}.json"


def cached(cache: Path | None = None) -> Path | None:
    """The verified cached set, or None when it is missing or doesn't match the pin."""
    path = set_path(cache)
    return path if path.is_file() and _sha256(path.read_bytes()) == SHA256 else None


def download(opener=urllib.request.urlopen) -> bytes:
    """The derived set, straight from upstream (unverified)."""
    request = urllib.request.Request(URL, headers={"User-Agent": _USER_AGENT})
    try:
        with opener(request, timeout=300) as response:
            raw = response.read()
        return derive(raw)
    except (OSError, ValueError, AttributeError) as exc:
        raise ReferenceDataError(f"{SET_ID}: download failed from {URL}: {exc}") from exc


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
def _read(path: str, mtime_ns: int, size: int, verify: bool) -> dict[str, dict] | None:
    data = Path(path).read_bytes()
    if verify and _sha256(data) != SHA256:
        return None
    try:
        found = json.loads(data).get("models")
    except (ValueError, AttributeError):
        return None
    return found if isinstance(found, dict) else None


def templates() -> dict[str, dict] | None:
    """The vanilla templates by full id (``minecraft:block/stairs``), or None
    when they aren't cached (run ``portkit reference fetch``)."""
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
    print(f"usage: python -m portkit.data.models --pin   (fetch with `{FETCH_COMMAND}`)")
    sys.exit(2)
