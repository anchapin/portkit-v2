"""Keep every pack path short enough for every device (#117).

Bedrock on some platforms (consoles, mobile) fails to load a file whose path
inside its pack is longer than 100 characters, or sits under more than eight
directories. Mojang's validator (mct PATHLENGTH) makes both an error. Java has
no such limit, and a mod with generated material variants (Tinkers' Construct
writes ``tool/staff/large_modifiers/tconstruct_embellishment_tconstruct_slimewood_bloodshroom``)
goes past it.

Such a path is shortened deterministically: its leaf is cut and given a hash
of the original path, so the same mod always produces the same names and two
long paths never meet. If the directory alone leaves no room, or is too deep,
the file moves up to its first two directories (``textures/items``). Every
reference to the old path moves with it: texture index entries, flipbook
entries and sound definitions name files by path (without the extension).
Index keys (``tconstruct:tool_staff_...``) are not paths and don't change, so
blocks, items and models that use them need nothing rewritten.
"""
from __future__ import annotations

import hashlib
from pathlib import PurePosixPath

from .model import ConversionResult

MAX_PATH = 100  # characters, pack-relative, as mct counts them
MAX_SEGMENTS = 9  # directories + file; mct errors on more
_HASH = 8

_INDEXES = ("textures/terrain_texture.json", "textures/item_texture.json")
_FLIPBOOK = "textures/flipbook_textures.json"
_SOUNDS = "sounds/sound_definitions.json"


def too_long(path: str) -> bool:
    return len(path) > MAX_PATH or len(path.split("/")) > MAX_SEGMENTS


def shorten(path: str, taken: set[str] | frozenset[str] = frozenset()) -> str:
    """A path within the limits for ``path``, stable for the same input.

    ``taken`` holds paths already in the pack, so a shortened name never lands
    on another file.
    """
    pure = PurePosixPath(path)
    suffix = pure.suffix
    stem = pure.stem
    directory = pure.parent.as_posix()
    if directory == "." or len(pure.parts) > MAX_SEGMENTS or (
        len(directory) + 1 + 1 + _HASH + len(suffix) + 8 > MAX_PATH
    ):
        directory = "/".join(pure.parts[:2]) if len(pure.parts) > 2 else pure.parent.as_posix()
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()
    for width in range(_HASH, len(digest) + 1, 4):
        tag = digest[:width]
        room = MAX_PATH - len(directory) - 1 - len(suffix) - 1 - width
        leaf = f"{stem[: max(room, 0)].rstrip('_-.')}_{tag}{suffix}" if room > 0 else f"{tag}{suffix}"
        candidate = f"{directory}/{leaf}" if directory not in ("", ".") else leaf
        if candidate not in taken and not too_long(candidate):
            return candidate
    raise ValueError(f"cannot shorten {path!r} below {MAX_PATH} characters")


def _strip(path: str) -> str:
    """A path as references spell it: no extension."""
    pure = PurePosixPath(path)
    return pure.with_suffix("").as_posix() if pure.suffix else path


def shorten_paths(result: ConversionResult) -> dict[str, str]:
    """Rename every over-long output path in ``result`` and fix its references.

    Returns {old: new}. A note in ``result.notes`` says how many moved, so the
    renamed files are visible in the summary rather than a surprise in the pack.
    """
    renames: dict[str, str] = {}
    taken = set(result.files)
    for path in sorted(result.files):
        if too_long(path):
            new = shorten(path, taken)
            renames[path] = new
            taken.add(new)
    if not renames:
        return renames

    for old, new in renames.items():
        result.files[new] = result.files.pop(old)

    # References spell the path without its extension.
    moved = {_strip(old): _strip(new) for old, new in renames.items()}

    for index in _INDEXES:
        body = result.files.get(index)
        if not isinstance(body, dict) or not isinstance(body.get("texture_data"), dict):
            continue
        data = {}
        for key, entry in body["texture_data"].items():
            if isinstance(entry, dict) and isinstance(entry.get("textures"), str):
                entry = {**entry, "textures": moved.get(entry["textures"], entry["textures"])}
            data[key] = entry
        result.files[index] = {**body, "texture_data": data}

    flipbook = result.files.get(_FLIPBOOK)
    if isinstance(flipbook, list):
        result.files[_FLIPBOOK] = [
            {**e, "flipbook_texture": moved.get(e.get("flipbook_texture"), e.get("flipbook_texture"))}
            if isinstance(e, dict) and "flipbook_texture" in e else e
            for e in flipbook
        ]

    sounds = result.files.get(_SOUNDS)
    if isinstance(sounds, dict) and isinstance(sounds.get("sound_definitions"), dict):
        definitions = {}
        for event, body in sounds["sound_definitions"].items():
            if isinstance(body, dict) and isinstance(body.get("sounds"), list):
                entries = []
                for s in body["sounds"]:
                    if isinstance(s, str):
                        s = moved.get(s, s)
                    elif isinstance(s, dict) and isinstance(s.get("name"), str):
                        s = {**s, "name": moved.get(s["name"], s["name"])}
                    entries.append(s)
                body = {**body, "sounds": entries}
            definitions[event] = body
        result.files[_SOUNDS] = {**sounds, "sound_definitions": definitions}

    examples = ", ".join(f"{o} -> {n}" for o, n in list(renames.items())[:3])
    more = f" (and {len(renames) - 3} more)" if len(renames) > 3 else ""
    result.notes.append(
        f"shortened {len(renames)} pack path(s) over {MAX_PATH} characters or "
        f"{MAX_SEGMENTS - 1} directories, which some devices cannot load: {examples}{more}"
    )
    return renames
