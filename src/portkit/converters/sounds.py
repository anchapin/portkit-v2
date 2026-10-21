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
doesn't ship. The vanilla list is fetched on demand (``portkit reference
fetch``, #124); without it every vanilla name is dropped, each saying to run
the fetch to keep it. An event that keeps at least one sound converts with a note
naming what it lost; one left with none is withdrawn to the residue.

A Java sound entry can also play another event (``{"name": ..., "type":
"event"}``, #356). Bedrock's sound_definitions has no such reference, so the
target's sounds are inlined, resolved the way Java resolves them at play time.
``SoundManager.Preparations#handleRegistration``'s ``SOUND_EVENT`` case
(identical in the 1.16.5, 1.18.1 and 1.21.11 decompiled client sources) wraps
the target in a Weighted whose weight is the target event's total weight and
whose sound is the target's pick with volume and pitch multiplied by the
referencing entry's, stream OR-ed, and preload and attenuation taken from the
target. So a flattened sound keeps its own weight within the target (the
referencing entry's own ``weight`` is ignored, as Java ignores it), its volume
and pitch are the products down the chain, and stream is set if any link sets
it. The target is the mod's own event, a vanilla event (vanilla's own
sounds.json for the jar's game version, fetched on demand by
``portkit.data.java_sounds``; its files then take the same-path rule above),
or another mod's, whose sounds.json the jar doesn't carry, which refuses the
event. A chain that comes back to itself (Java would recurse without end)
refuses the event; a target that no sounds.json defines plays nothing in Java
(weight 0), so only that entry is dropped. ``weight`` is carried on every
sound, since Bedrock picks by the same relative weight (default 1).
"""
from __future__ import annotations

import json

from ..data import FETCH_COMMAND, bedrock_vanilla_sounds
from ..data import java_sounds
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
    sound,
    namespace: str,
    shipped: frozenset[str] | set[str] = frozenset(),
    vanilla: frozenset[str] | None = frozenset(),
) -> tuple[dict | None, str | None]:
    """One file entry of a Java event's "sounds" list -> a Bedrock sound path.

    Returns (entry, None), or (None, reason). A reason that is a ``_Drop``
    costs only this sound; any other reason refuses the whole event.
    ``shipped`` is the mod's converted audio, as paths under sounds/ with no
    extension. ``vanilla`` is Bedrock's vanilla audio paths, or None when that
    list isn't cached. The entry keeps Java's raw ``volume``, ``pitch`` and
    ``weight`` (floats, 1 when absent) and ``stream``; :func:`_emit` writes it.
    Entries of type ``event`` are :func:`_flatten`'s.
    """
    if isinstance(sound, str):
        name, volume, pitch, weight, stream = sound, None, None, None, False
    elif isinstance(sound, dict):
        name = sound.get("name")
        volume = sound.get("volume")
        pitch = sound.get("pitch")
        weight = sound.get("weight")
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
        if vanilla is None:
            return None, _Drop(
                f"{name!r} is a vanilla Java sound and the Bedrock vanilla sound list "
                f"isn't cached; run `{FETCH_COMMAND}` to keep it if Bedrock has sounds/{path}"
            )
        if f"sounds/{path}" not in vanilla:
            return None, _Drop(
                f"{name!r} is a vanilla Java sound with no Bedrock vanilla file at sounds/{path}"
            )
    elif ns != namespace:
        return None, f"sound {name!r} belongs to another namespace"
    elif path not in shipped:
        return None, _Drop(
            f"{name!r} names assets/{namespace}/sounds/{path}.ogg, which the mod does not ship"
        )

    weight = float(weight) if isinstance(weight, (int, float)) and not isinstance(weight, bool) else 1.0
    if weight <= 0:
        # Java's WeighedSoundEvents never picks a weight-0 entry.
        return None, _Drop(f"{name!r} has weight {weight:g}, which Java never plays")
    return {
        "name": f"sounds/{path}",
        "volume": float(volume) if isinstance(volume, (int, float)) else 1.0,
        "pitch": float(pitch) if isinstance(pitch, (int, float)) else 1.0,
        "weight": weight,
        "stream": stream,
    }, None


def _emit(entry: dict) -> dict:
    """A resolved entry -> its Bedrock form; attributes at their default are left out."""
    out: dict = {"name": entry["name"]}
    if entry["volume"] != 1.0:
        out["volume"] = round(entry["volume"], 4)
    if entry["pitch"] != 1.0:
        out["pitch"] = round(entry["pitch"], 4)
    if entry["weight"] != 1.0:
        weight = entry["weight"]
        out["weight"] = int(weight) if float(weight).is_integer() else round(weight, 4)
    if entry["stream"]:
        out["stream"] = True
    return out


class _Events:
    """Where an event reference finds its target's sounds list (#356)."""

    def __init__(self, namespace: str, own: dict, vanilla: dict | None, vanilla_label: str | None):
        self.namespace = namespace
        self.own = own
        self.vanilla = vanilla
        self.vanilla_label = vanilla_label

    def lookup(self, target: str) -> tuple[list | None, str | None]:
        """(sounds list, None), or (None, reason): a ``_Drop`` costs that entry only."""
        ns, _, path = target.partition(":")
        if ns == self.namespace:
            body = self.own.get(path)
            if not isinstance(body, dict):
                return None, _Drop(
                    f"plays event {target!r}, which the mod's sounds.json doesn't define "
                    "(Java plays nothing for it)"
                )
            return list(body.get("sounds") or []), None
        if ns == "minecraft":
            if self.vanilla is None:
                return None, _Drop(
                    f"plays vanilla event {target!r} and vanilla's sounds.json for this game "
                    f"version isn't cached; run `{FETCH_COMMAND}` to keep it"
                )
            found = self.vanilla.get(target)
            if not isinstance(found, list):
                return None, _Drop(
                    f"plays vanilla event {target!r}, which {self.vanilla_label} doesn't define "
                    "(Java plays nothing for it)"
                )
            return list(found), None
        return None, (
            f"plays event {target!r} of another mod, whose sounds.json isn't in this jar"
        )


def _flatten(
    sounds: list,
    namespace: str,
    shipped,
    vanilla,
    events: _Events,
    chain: tuple[str, ...],
) -> tuple[list[dict], list[str], str | None]:
    """A Java sounds list -> (resolved entries, drop reasons, refusal or None).

    An ``event`` entry is replaced by its target's sounds, resolved
    recursively: volume and pitch multiply, stream ORs, each sound keeps its
    own weight (Java's SOUND_EVENT Weighted, see the module docstring).
    ``chain`` is the events being resolved, outermost first.
    """
    entries: list[dict] = []
    dropped: list[str] = []
    for sound in sounds:
        if isinstance(sound, dict) and sound.get("type") == "event":
            name = sound.get("name")
            if not isinstance(name, str):
                return [], dropped, f"event entry names {name!r}, which is not an event id"
            target = name if ":" in name else f"minecraft:{name}"
            if target in chain:
                loop = " -> ".join((*chain[chain.index(target):], target))
                return [], dropped, f"its event references loop ({loop}), which Java cannot resolve"
            body, reason = events.lookup(target)
            if body is None:
                if isinstance(reason, _Drop):
                    if reason not in dropped:
                        dropped.append(reason)
                    continue
                return [], dropped, reason
            inner, inner_dropped, refused = _flatten(
                body, namespace, shipped, vanilla, events, (*chain, target))
            for reason in inner_dropped:
                reason = _Drop(f"via {target}: {reason}")
                if reason not in dropped:
                    dropped.append(reason)
            if refused:
                return [], dropped, f"via {target}: {refused}"
            if not inner and not inner_dropped:
                reason = _Drop(f"plays event {target!r}, which lists no sounds (Java plays nothing for it)")
                if reason not in dropped:
                    dropped.append(reason)
            volume = sound.get("volume")
            pitch = sound.get("pitch")
            scale_v = float(volume) if isinstance(volume, (int, float)) else 1.0
            scale_p = float(pitch) if isinstance(pitch, (int, float)) else 1.0
            stream = bool(sound.get("stream", False))
            for entry in inner:
                entries.append({
                    **entry,
                    "volume": entry["volume"] * scale_v,
                    "pitch": entry["pitch"] * scale_p,
                    "stream": entry["stream"] or stream,
                })
            continue
        entry, reason = _sound_entry(sound, namespace, shipped, vanilla)
        if entry is not None:
            entries.append(entry)
        elif isinstance(reason, _Drop):
            if reason not in dropped:
                dropped.append(reason)
        else:
            return [], dropped, reason
    return entries, dropped, None


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

    vanilla = bedrock_vanilla_sounds()
    java_vanilla, java_set = java_sounds.vanilla_events(mod.minecraft or mod.loader_minecraft)
    refs = _Events(
        mod.namespace,
        events if isinstance(events, dict) else {},
        java_vanilla,
        java_set.label if java_set is not None else "vanilla's sounds.json",
    )
    definitions: dict[str, dict] = {}
    inlined: list[str] = []
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

        entries, dropped, refused = _flatten(
            sounds, mod.namespace, shipped, vanilla, refs, (f"{mod.namespace}:{event}",))
        if not refused and any(isinstance(s, dict) and s.get("type") == "event" for s in sounds):
            inlined.append(event)
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

        definitions[f"{mod.namespace}:{event}"] = {
            "category": category, "sounds": [_emit(e) for e in entries]}

    inlined = [e for e in inlined if f"{mod.namespace}:{e}" in definitions]
    if inlined:
        source = java_set.label if java_set is not None and java_vanilla is not None else None
        result.notes.append(
            f"{len(inlined)} sound event(s) play another event; Bedrock can't reference one, so "
            "each target's sounds are inlined as Java resolves them (SoundManager SOUND_EVENT: "
            "volume and pitch multiply, stream ORs, each sound keeps its own weight)"
            + (f"; vanilla targets read from {source}" if source else "")
        )

    if definitions:
        result.files["sounds/sound_definitions.json"] = {
            "format_version": "1.14.0",
            "sound_definitions": definitions,
        }
    return result
