"""Sounds.

Java declares sound events in assets/<ns>/sounds.json and ships the audio under
assets/<ns>/sounds/. Bedrock says the same thing in sound_definitions.json with
a different spelling: a category, a list of sounds, and paths that drop the file
extension.

The audio itself is a straight copy. The event map is a rename. What is not a
rename is a sound Java plays through a vanilla event name (block.stone.break and
its kin): Bedrock has its own event names for those, and a mod overriding one is
asking for behavior we would have to guess at, so it goes to the residue with
the event named.

Bedrock only plays .ogg here too, so a mod shipping .wav is reported rather than
copied into a pack where it stays silent.

No entry may name audio the player won't have (#116). A Java sound name with
no namespace is vanilla (``minecraft:``), not the mod's: it is kept only when
Bedrock's own vanilla pack has a file at the same path, which then plays.
Otherwise it is dropped, as is a mod-namespaced name whose audio the jar
doesn't ship. An event that keeps at least one sound converts with a note
naming what it lost; one left with none is withdrawn to the residue.
"""
from __future__ import annotations

import json

from ..data import bedrock_vanilla_sounds
from ..model import ConversionResult, SourceMod, Unhandled

# Java category -> Bedrock category. Bedrock's set is smaller; anything not
# here is reported rather than silently filed under "neutral".
_CATEGORIES = {
    "master": "master",
    "music": "music",
    "record": "record",
    "weather": "weather",
    "block": "block",
    "hostile": "hostile",
    "neutral": "neutral",
    "player": "player",
    "ambient": "ambient",
    "voice": "voice",
    "blocks": "block",
}
_DEFAULT_CATEGORY = "neutral"

_AUDIO_SUFFIXES = {".ogg"}


class _Drop(str):
    """Why one sound in an event was dropped; the rest of the event survives."""


def _sound_entry(
    sound, namespace: str, shipped: frozenset[str] | set[str] = frozenset()
) -> tuple[dict | None, str | None]:
    """One entry of a Java event's "sounds" list -> a Bedrock sound path.

    Returns (entry, None), or (None, reason). A reason that is a ``_Drop``
    costs only this sound; any other reason refuses the whole event.
    ``shipped`` is the mod's converted audio, as paths under sounds/ with no
    extension.
    """
    if isinstance(sound, str):
        name, volume, pitch, stream = sound, None, None, False
    elif isinstance(sound, dict):
        if sound.get("type") == "event":
            return None, "the event plays another event, which Bedrock cannot reference"
        name = sound.get("name")
        volume = sound.get("volume")
        pitch = sound.get("pitch")
        stream = bool(sound.get("stream", False))
        if not isinstance(name, str):
            return None, f"sound entry names {name!r}, which is not a sound path"
    else:
        return None, f"sound entry {sound!r} is neither a path nor an object"

    ns, _, path = name.rpartition(":")
    if ns in ("", "minecraft"):
        # Java resolves a bare name to minecraft:, so this is vanilla audio.
        # Bedrock files many vanilla sounds at the same path (random/bow,
        # mob/slime/big1); those play from the vanilla pack. The rest are
        # filed elsewhere or don't exist, and guessing the new path would be
        # a guess.
        if f"sounds/{path}" not in bedrock_vanilla_sounds():
            return None, _Drop(
                f"{name!r} is a vanilla Java sound with no Bedrock vanilla file at sounds/{path}"
            )
    elif ns != namespace:
        return None, f"sound {name!r} belongs to another namespace"
    elif path not in shipped:
        return None, _Drop(
            f"{name!r} names assets/{namespace}/sounds/{path}.ogg, which the mod does not ship"
        )

    entry: dict = {"name": f"sounds/{path}"}
    if isinstance(volume, (int, float)) and float(volume) != 1.0:
        entry["volume"] = round(float(volume), 4)
    if isinstance(pitch, (int, float)) and float(pitch) != 1.0:
        entry["pitch"] = round(float(pitch), 4)
    if stream:
        entry["stream"] = True
    return entry, None


def convert(mod: SourceMod) -> ConversionResult:
    result = ConversionResult()

    audio_root = mod.assets / "sounds"
    shipped: set[str] = set()
    if audio_root.is_dir():
        for path in sorted(audio_root.rglob("*")):
            if not path.is_file():
                continue
            rel = result.claim(mod, path)
            if path.suffix.lower() not in _AUDIO_SUFFIXES:
                result.unhandled.append(
                    Unhandled(
                        rel,
                        "sound",
                        f"Bedrock plays .ogg only, and this is {path.suffix or 'extensionless'}",
                    )
                )
                continue
            inner = path.relative_to(audio_root).as_posix()
            result.files[f"sounds/{inner}"] = path.read_bytes()
            shipped.add(inner[: -len(path.suffix)])

    index = mod.assets / "sounds.json"
    if not index.is_file():
        return result

    rel = result.claim(mod, index)
    try:
        events = json.loads(index.read_text())
    except json.JSONDecodeError as exc:
        result.unhandled.append(Unhandled(rel, "sound", f"sounds.json is invalid JSON: {exc}"))
        return result

    definitions: dict[str, dict] = {}
    for event, body in sorted(events.items()):
        if not isinstance(body, dict):
            result.unhandled.append(
                Unhandled(rel, "sound", f"event {event!r} is not an object", count=0)
            )
            continue

        if body.get("replace"):
            result.unhandled.append(
                Unhandled(
                    rel,
                    "sound",
                    f"event {event!r} replaces a vanilla sound event, "
                    "which Bedrock names differently",
                    count=0,
                )
            )
            continue

        java_category = body.get("category", _DEFAULT_CATEGORY)
        category = _CATEGORIES.get(java_category)
        if category is None:
            result.unhandled.append(
                Unhandled(
                    rel,
                    "sound",
                    f"event {event!r} uses sound category {java_category!r}, "
                    "which has no Bedrock equivalent",
                    count=0,
                )
            )
            continue

        sounds = body.get("sounds") or []
        if not sounds:
            result.unhandled.append(
                Unhandled(rel, "sound", f"event {event!r} lists no sounds", count=0)
            )
            continue

        entries = []
        dropped: list[str] = []
        refused: str | None = None
        for sound in sounds:
            entry, reason = _sound_entry(sound, mod.namespace, shipped)
            if entry is not None:
                entries.append(entry)
            elif isinstance(reason, _Drop):
                if reason not in dropped:
                    dropped.append(reason)
            else:
                refused = reason
                break
        if refused:
            result.unhandled.append(
                Unhandled(rel, "sound", f"event {event!r}: {refused}", count=0)
            )
            continue
        if not entries:
            result.unhandled.append(
                Unhandled(
                    rel,
                    "sound",
                    f"event {event!r} has no sound Bedrock can play: {'; '.join(dropped)}",
                    count=0,
                )
            )
            continue
        if dropped:
            result.notes.append(
                f"sound event {mod.namespace}:{event} dropped {len(dropped)} sound(s) "
                f"with no audio in the pack: {'; '.join(dropped)}"
            )

        definitions[f"{mod.namespace}:{event}"] = {"category": category, "sounds": entries}

    if definitions:
        result.files["sounds/sound_definitions.json"] = {
            "format_version": "1.14.0",
            "sound_definitions": definitions,
        }
    return result
