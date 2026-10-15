"""Do the gameplay numbers on an agent-written item come from the source mod? (#135; policy #87)

In a live spot-check after #132, DeepSeek wrote agent_mod's steel sword as a
Bedrock item with ``minecraft:damage`` 5, ``minecraft:durability`` 250 and an
enchantable slot. The fixture carries no stats at all (a model, a texture, a
lang line and a crafting recipe), so every one of those numbers was made up.
The structural validator has no way to know that, and the recipe ref check in
``refs.py`` only looks at recipes.

So the residue agent holds the items it writes to a deterministic rule, in the
spirit of ``refs.py``: a *stat* on an agent-written item must be a number the
source mod states for that item, or one derived from such a number by a fixed
rule. A stat is one of the gameplay values listed in :data:`STAT_FIELDS`
(damage, durability, mining speed, armour protection, food nutrition and
saturation, cooldowns, the enchantability value, fuel duration, use duration).
Visual and descriptive components (icon, display name, ``hand_equipped``,
``max_stack_size``, tags, ``repairable`` naming items that exist, an
enchantable *slot*) are not stats and are never checked here.

Where a number counts as stated for an item: any text file in the source mod
that is not client-side art or a recipe-like list, and whose path or content
names the item. ``assets/`` (models, blockstates, lang, sounds, textures) is
skipped because Java never keeps gameplay values there, and item models are full
of display numbers (rotations, scales) that would otherwise excuse an invented
stat. Recipes, tags, advancements and loot tables are skipped for the same
reason (counts, chances). Everything else (a data-driven stats file, a mod
config, Java 1.20.5+ item components in data) is read, and every number in it
is a candidate. The one derivation: Java's ``attack_damage`` modifier is added
to a base of 1, so a Bedrock damage of n is also supported by a source n - 1.

This is deliberately conservative in the direction that cannot invent
anything: a stat defined per material in a file that never names the item is
treated as absent, and the agent is told to omit it and say so.

Blocks (#152)
-------------
On real-mod residue GLM 5.3 wrote ``minecraft:map_color`` on storage drawers
and waystones blocks; Java sets map colour, hardness, blast resistance, light
and friction in block code, never in JSON, so none of it had a source. Agent-
written blocks are held to the same rule, over their base components and every
permutation's: the numbers in :data:`BLOCK_STAT_FIELDS` must be stated for the
block in the same kind of file as above, and a ``minecraft:map_color`` (hex
string, ``[r, g, b]`` or ``{"color": ...}``) must appear in such a file as
``#rrggbb``/``rrggbb`` or as its decimal RGB integer. One more derivation:
``seconds_to_destroy`` may be a stated Java hardness x 1.5 (the rule the
lookup reference gives). A value equal to what Bedrock uses when the component
is omitted (:data:`OMITTED_DEFAULTS`) claims nothing and passes; the ``true``/
``false`` forms of a component carry no number and are not checked.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

# component -> the fields in it that are gameplay numbers ("" = the component
# value itself, when it is a bare number).
STAT_FIELDS: dict[str, tuple[str, ...]] = {
    "minecraft:damage": ("", "value"),
    "minecraft:durability": ("max_durability",),
    "minecraft:digger": ("destroy_speeds[].speed",),
    "minecraft:mining_speed": ("", "value"),
    "minecraft:wearable": ("protection",),
    "minecraft:armor": ("protection",),
    "minecraft:food": ("nutrition", "saturation_modifier"),
    "minecraft:cooldown": ("duration",),
    "minecraft:enchantable": ("value",),
    "minecraft:fuel": ("duration",),
    "minecraft:use_modifiers": ("use_duration",),
    "minecraft:use_duration": ("", "value"),
}

# Block components -> their gameplay numbers (#152), same spec format. The bare
# legacy forms (destroy_time, explosion_resistance, block_light_*) are older
# format versions of the same properties.
BLOCK_STAT_FIELDS: dict[str, tuple[str, ...]] = {
    "minecraft:light_emission": ("",),
    "minecraft:light_dampening": ("",),
    "minecraft:friction": ("",),
    "minecraft:destructible_by_mining": ("seconds_to_destroy",),
    "minecraft:destructible_by_explosion": ("explosion_resistance",),
    "minecraft:flammable": ("catch_chance_modifier", "destroy_chance_modifier"),
    "minecraft:destroy_time": ("", "value"),
    "minecraft:explosion_resistance": ("", "value"),
    "minecraft:block_light_emission": ("", "emission"),
    "minecraft:block_light_filter": ("", "light_filter"),
}

# A component whose value is a colour rather than a number (#152).
MAP_COLOR = "minecraft:map_color"

# What Bedrock uses when the component is left out, so writing it states
# nothing new: no light, fully opaque, and the friction most blocks have
# (0.4 is the documented default; see lookup_bedrock('minecraft:friction')).
OMITTED_DEFAULTS: dict[tuple[str, str], float] = {
    ("minecraft:light_emission", ""): 0.0,
    ("minecraft:light_dampening", ""): 15.0,
    ("minecraft:friction", ""): 0.4,
}

_SKIP_TOP = {"assets"}
_SKIP_DATA = {
    "recipes", "recipe", "tags", "advancements", "advancement", "loot_tables", "loot_table",
}
_TEXT_SUFFIXES = {".json", ".json5", ".toml", ".cfg", ".properties", ".yml", ".yaml", ".txt", ".mcmeta"}
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")
_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")
_MAX_FILE_BYTES = 2_000_000


@dataclass(frozen=True)
class Stat:
    path: str  # the pack file, relative to the output tree
    item: str  # the item or block identifier
    component: str
    field: str  # e.g. "max_durability", "destroy_speeds[0].speed", "" for a bare value
    value: float | str  # a number, or "#rrggbb" for a map colour
    scope: str = ""  # "permutations[2]" for a block permutation's components
    kind: str = "item"  # item | block

    @property
    def where(self) -> str:
        where = f"{self.component}.{self.field}" if self.field else self.component
        return f"{self.scope}.{where}" if self.scope else where

    def describe(self) -> str:
        return f"{self.path} {self.where} = {_fmt(self.value)} ({self.item})"


def _fmt(value: float | str) -> str:
    if isinstance(value, str):
        return value
    return str(int(value)) if float(value).is_integer() else repr(value)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


# -- what an item claims -------------------------------------------------

def _field_values(component, spec: str) -> Iterator[tuple[str, float]]:
    if spec == "":
        if _is_number(component):
            yield "", float(component)
        return
    if not isinstance(component, dict):
        return
    if spec.endswith("].speed"):  # destroy_speeds[].speed
        listed = component.get("destroy_speeds")
        for i, entry in enumerate(listed if isinstance(listed, list) else []):
            if isinstance(entry, dict) and _is_number(entry.get("speed")):
                yield f"destroy_speeds[{i}].speed", float(entry["speed"])
        return
    if _is_number(component.get(spec)):
        yield spec, float(component[spec])


def map_color_hex(value) -> str | None:
    """A ``minecraft:map_color`` value as ``#rrggbb``, or None if unreadable."""
    if isinstance(value, dict):
        value = value.get("color")
    if isinstance(value, str):
        match = _HEX.match(value.strip())
        return f"#{match.group(1).lower()}" if match else None
    if isinstance(value, list) and len(value) == 3 and all(_is_number(v) for v in value):
        if all(float(v).is_integer() and 0 <= v <= 255 for v in value):
            r, g, b = (int(v) for v in value)
            return f"#{r:02x}{g:02x}{b:02x}"
    return None


def _component_stats(
    rel: str, ident: str, components: dict, fields: dict[str, tuple[str, ...]], scope: str, kind: str,
) -> Iterator[Stat]:
    for component, specs in fields.items():
        if component not in components:
            continue
        for spec in specs:
            for field, value in _field_values(components[component], spec):
                if OMITTED_DEFAULTS.get((component, field)) == value:
                    continue  # the value Bedrock uses anyway; it claims nothing
                yield Stat(rel, ident, component, field, value, scope, kind)
    if kind == "block" and MAP_COLOR in components:
        raw = components[MAP_COLOR]
        hex_value = map_color_hex(raw)
        yield Stat(rel, ident, MAP_COLOR, "", hex_value or json.dumps(raw), scope, kind)


def document_stats(out_tree: Path, rel: str) -> list[Stat]:
    """Every stat value one pack item or block file sets (#135, #152)."""
    data = _load(out_tree / rel)
    if not isinstance(data, dict):
        return []
    for key, kind, fields in (("minecraft:item", "item", STAT_FIELDS), ("minecraft:block", "block", BLOCK_STAT_FIELDS)):
        body = data.get(key)
        if not isinstance(body, dict):
            continue
        description = body.get("description") if isinstance(body.get("description"), dict) else {}
        ident = description.get("identifier")
        if not isinstance(ident, str):
            return []
        stats: list[Stat] = []
        if isinstance(body.get("components"), dict):
            stats.extend(_component_stats(rel, ident, body["components"], fields, "", kind))
        if kind == "block" and isinstance(body.get("permutations"), list):
            for i, permutation in enumerate(body["permutations"]):
                if isinstance(permutation, dict) and isinstance(permutation.get("components"), dict):
                    stats.extend(_component_stats(
                        rel, ident, permutation["components"], fields, f"permutations[{i}]", kind
                    ))
        return stats
    return []


def item_stats(out_tree: Path, rel: str) -> list[Stat]:
    """Every stat value one pack item file sets."""
    return [stat for stat in document_stats(out_tree, rel) if stat.kind == "item"]


# -- what the source states -----------------------------------------------

def _stat_source_files(source_root: Path) -> Iterator[Path]:
    for path in sorted(source_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        parts = path.relative_to(source_root).parts
        if parts and parts[0] in _SKIP_TOP:
            continue
        if len(parts) >= 3 and parts[0] == "data" and parts[2] in _SKIP_DATA:
            continue
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield path


def _numbers(node) -> Iterator[float]:
    if _is_number(node):
        yield float(node)
    elif isinstance(node, dict):
        for value in node.values():
            yield from _numbers(value)
    elif isinstance(node, list):
        for value in node:
            yield from _numbers(value)


def source_numbers(source_root: Path, item: str) -> set[float]:
    """Numbers in source files (outside art and recipe-like data) that name ``item``."""
    return source_evidence(source_root, item)[0]


_HEX_IN_TEXT = re.compile(r"(?<![0-9a-zA-Z])#?([0-9a-fA-F]{6})(?![0-9a-zA-Z])")


def source_evidence(source_root: Path, item: str) -> tuple[set[float], set[str]]:
    """(numbers, ``#rrggbb`` colours) in source files outside art and
    recipe-like data that name ``item``. A colour counts written as hex, with
    or without ``#``; its decimal RGB form is among the numbers."""
    name = item.split(":", 1)[-1]
    if not name:
        return set(), set()
    pattern = re.compile(rf"(?<![a-z0-9_]){re.escape(name)}(?![a-z0-9_])")
    found: set[float] = set()
    colours: set[str] = set()
    for path in _stat_source_files(source_root):
        rel = path.relative_to(source_root).as_posix()
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        if not (pattern.search(rel) or pattern.search(text)):
            continue
        colours.update(f"#{m.lower()}" for m in _HEX_IN_TEXT.findall(text))
        parsed = None
        if path.suffix.lower() == ".json":
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
        if parsed is not None:
            found.update(_numbers(parsed))
        else:
            found.update(float(m) for m in _NUMBER.findall(text))
    return found, colours


def _supported(stat: Stat, numbers: set[float], colours: set[str] = frozenset()) -> bool:
    if stat.component == MAP_COLOR:
        if not isinstance(stat.value, str) or not _HEX.match(stat.value):
            return False  # an unreadable colour can't be traced to anything
        return stat.value in colours or float(int(stat.value[1:], 16)) in numbers
    candidates = {stat.value}
    if stat.component == "minecraft:damage":
        candidates.add(stat.value - 1)  # Java attack_damage is added to a base of 1
    if stat.field == "seconds_to_destroy":
        candidates.add(stat.value / 1.5)  # Bedrock seconds ~ Java hardness x 1.5
    return any(math.isclose(c, n, rel_tol=1e-9, abs_tol=1e-9) for c in candidates for n in numbers)


# -- the check ---------------------------------------------------------

def fabricated_stats(out_tree: Path, written: list[str], source_root: Path) -> list[Stat]:
    """Stats on the items and blocks listed in ``written`` that the source never states."""
    normalised = sorted({rel.replace("\\", "/") for rel in written})
    bad: list[Stat] = []
    cache: dict[str, tuple[set[float], set[str]]] = {}
    for rel in normalised:
        if not rel.endswith(".json") or not (out_tree / rel).is_file():
            continue
        for stat in document_stats(out_tree, rel):
            if stat.item not in cache:
                cache[stat.item] = source_evidence(source_root, stat.item)
            if not _supported(stat, *cache[stat.item]):
                bad.append(stat)
    return bad


def finding(stat: Stat) -> dict:
    """The validate-tool finding for one unsupported stat, as the agent sees it."""
    if stat.component == MAP_COLOR:
        what = "map colour"
    else:
        what = "value"
    message = (
        f"{stat.where} = {_fmt(stat.value)} on {stat.item}, but the source mod states no such "
        f"{what} for this {stat.kind}. Gameplay numbers and block properties must come from the "
        f"source, never guessed: remove the {stat.component} component "
        "and say in your final message which stats were left out because the source does not give them."
    )
    return {"path": stat.path, "rule": "agent.fabricated_stat", "message": message, "severity": "error"}
