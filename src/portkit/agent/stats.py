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

_SKIP_TOP = {"assets"}
_SKIP_DATA = {
    "recipes", "recipe", "tags", "advancements", "advancement", "loot_tables", "loot_table",
}
_TEXT_SUFFIXES = {".json", ".json5", ".toml", ".cfg", ".properties", ".yml", ".yaml", ".txt", ".mcmeta"}
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")
_MAX_FILE_BYTES = 2_000_000


@dataclass(frozen=True)
class Stat:
    path: str  # the pack file, relative to the output tree
    item: str  # the item identifier
    component: str
    field: str  # e.g. "max_durability", "destroy_speeds[0].speed", "" for a bare value
    value: float

    @property
    def where(self) -> str:
        return f"{self.component}.{self.field}" if self.field else self.component

    def describe(self) -> str:
        return f"{self.path} {self.where} = {_fmt(self.value)} ({self.item})"


def _fmt(value: float) -> str:
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


def item_stats(out_tree: Path, rel: str) -> list[Stat]:
    """Every stat value one pack item file sets."""
    data = _load(out_tree / rel)
    if not isinstance(data, dict) or not isinstance(data.get("minecraft:item"), dict):
        return []
    body = data["minecraft:item"]
    ident = (body.get("description") or {}).get("identifier")
    components = body.get("components")
    if not isinstance(ident, str) or not isinstance(components, dict):
        return []
    stats: list[Stat] = []
    for component, specs in STAT_FIELDS.items():
        if component not in components:
            continue
        for spec in specs:
            for field, value in _field_values(components[component], spec):
                stats.append(Stat(rel, ident, component, field, value))
    return stats


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
    name = item.split(":", 1)[-1]
    if not name:
        return set()
    pattern = re.compile(rf"(?<![a-z0-9_]){re.escape(name)}(?![a-z0-9_])")
    found: set[float] = set()
    for path in _stat_source_files(source_root):
        rel = path.relative_to(source_root).as_posix()
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        if not (pattern.search(rel) or pattern.search(text)):
            continue
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
    return found


def _supported(stat: Stat, numbers: set[float]) -> bool:
    candidates = {stat.value}
    if stat.component == "minecraft:damage":
        candidates.add(stat.value - 1)  # Java attack_damage is added to a base of 1
    return any(math.isclose(c, n, rel_tol=1e-9, abs_tol=1e-9) for c in candidates for n in numbers)


# -- the check ---------------------------------------------------------

def fabricated_stats(out_tree: Path, written: list[str], source_root: Path) -> list[Stat]:
    """Stats on the items listed in ``written`` that the source never states."""
    normalised = sorted({rel.replace("\\", "/") for rel in written})
    bad: list[Stat] = []
    cache: dict[str, set[float]] = {}
    for rel in normalised:
        if not rel.endswith(".json") or not (out_tree / rel).is_file():
            continue
        for stat in item_stats(out_tree, rel):
            if stat.item not in cache:
                cache[stat.item] = source_numbers(source_root, stat.item)
            if not _supported(stat, cache[stat.item]):
                bad.append(stat)
    return bad


def finding(stat: Stat) -> dict:
    """The validate-tool finding for one unsupported stat, as the agent sees it."""
    message = (
        f"{stat.where} = {_fmt(stat.value)} on {stat.item}, but the source mod states no such "
        "value for this item. Gameplay numbers must come from the source, never guessed: "
        f"remove the {stat.component} component "
        "and say in your final message which stats were left out because the source does not give them."
    )
    return {"path": stat.path, "rule": "agent.fabricated_stat", "message": message, "severity": "error"}
