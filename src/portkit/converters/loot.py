"""Block drops.

Java loot tables are a small programming language: nested pools, weighted
entries, alternatives, number providers, enchantment bonuses. Bedrock's are a
flatter version of the same idea and do not have most of it.

The shape that carries almost every modded decorative block is: one pool, one
roll, one item entry, drops itself, survives explosions. That converts. A table
that reaches for fortune, silk touch, alternatives or a random count is refused
with the condition or function that defeated it named in the reason, because a
block that silently drops the wrong thing is worse than one the report tells you
to finish by hand.
"""
from __future__ import annotations

import json
import re

from ..conditions import LoadContext
from ..model import ConversionResult, SourceMod, Unhandled

# Java put block tables under data/<ns>/loot_tables/blocks/ up to 1.20 and
# moved to the singular loot_table/ in 1.21. Both are the same content.
_TABLE_DIRS = ("loot_tables", "loot_table")

# Java condition -> what to do with it. Bedrock block tables express
# "survives_explosion" as the explosion_decay function, which is how the vanilla
# Bedrock packs write it.
_EXPLOSION = "minecraft:survives_explosion"

# Conditions and functions we refuse, with the reason said in the mod author's
# terms rather than ours.
_REFUSED_CONDITIONS = {
    "minecraft:match_tool": "the drop depends on the tool used (silk touch or a tool tier)",
    "minecraft:table_bonus": "the drop chance depends on an enchantment level",
    "minecraft:random_chance": "the drop is random",
    "minecraft:random_chance_with_looting": "the drop chance depends on looting",
    "minecraft:killed_by_player": "the drop depends on who broke the block",
    "minecraft:block_state_property": "the drop depends on the block state",
    "minecraft:location_check": "the drop depends on where the block is",
    "minecraft:weather_check": "the drop depends on the weather",
    "minecraft:entity_properties": "the drop depends on the entity involved",
}
_REFUSED_FUNCTIONS = {
    "minecraft:apply_bonus": "the count is increased by fortune",
    "minecraft:limit_count": "the count is clamped after other functions",
    "minecraft:copy_name": "the drop copies the block's custom name",
    "minecraft:copy_nbt": "the drop copies block entity data",
    "minecraft:copy_components": "the drop copies block components",
    "minecraft:set_contents": "the drop carries the block's inventory",
    "minecraft:enchant_randomly": "the drop is randomly enchanted",
    "minecraft:enchant_with_levels": "the drop is enchanted by level",
    "minecraft:set_damage": "the drop has a damage value applied",
    "minecraft:furnace_smelt": "the drop is smelted when the block burns",
}

_SUPPORTED_ENTRY_TYPES = {"minecraft:item", "item"}


def _reason_for_condition(condition: dict) -> str:
    name = condition.get("condition")
    known = _REFUSED_CONDITIONS.get(name)
    if known:
        return f"{known} ({name})"
    return f"condition {name!r} has no Bedrock equivalent"


def _reason_for_function(function: dict) -> str:
    name = function.get("function")
    known = _REFUSED_FUNCTIONS.get(name)
    if known:
        return f"{known} ({name})"
    return f"function {name!r} has no Bedrock equivalent"


def _constant_count(function: dict) -> int | None:
    """A set_count we can honour: a constant, not a range or a binomial."""
    count = function.get("count")
    if isinstance(count, (int, float)) and float(count).is_integer():
        return int(count)
    if isinstance(count, dict):
        kind = count.get("type")
        if kind in (None, "minecraft:constant", "constant"):
            value = count.get("value")
            if isinstance(value, (int, float)) and float(value).is_integer():
                return int(value)
    return None


def _convert_table(data: dict) -> tuple[dict | None, str | None]:
    """Return (bedrock table, None) or (None, reason it was refused)."""
    pools = data.get("pools")
    if not isinstance(pools, list) or not pools:
        return None, "table has no pools, so it drops nothing"
    if len(pools) > 1:
        return None, f"table has {len(pools)} pools; Bedrock block drops are a single pool"

    pool = pools[0]
    rolls = pool.get("rolls", 1)
    if not isinstance(rolls, (int, float)) or int(rolls) != 1:
        return None, "the pool rolls a variable number of times"

    entries = pool.get("entries") or []
    if len(entries) != 1:
        return None, f"the pool has {len(entries)} entries; only a single drop is unambiguous"

    entry = entries[0]
    entry_type = entry.get("type")
    if entry_type not in _SUPPORTED_ENTRY_TYPES:
        if entry_type in ("minecraft:alternatives", "alternatives"):
            return None, "the drop picks between alternatives (usually silk touch)"
        return None, f"entry type {entry_type!r} is not a plain item drop"

    name = entry.get("name")
    if not isinstance(name, str) or ":" not in name:
        return None, f"entry names {name!r}, which is not a namespaced item"

    explosion_decay = False
    for condition in list(pool.get("conditions") or []) + list(entry.get("conditions") or []):
        if condition.get("condition") == _EXPLOSION:
            explosion_decay = True
            continue
        return None, _reason_for_condition(condition)

    count = None
    for function in list(pool.get("functions") or []) + list(entry.get("functions") or []):
        fname = function.get("function")
        if fname in ("minecraft:set_count", "set_count"):
            count = _constant_count(function)
            if count is None:
                return None, "the drop count is a range rather than a fixed number"
            continue
        if fname in ("minecraft:explosion_decay", "explosion_decay"):
            explosion_decay = True
            continue
        return None, _reason_for_function(function)

    functions: list[dict] = []
    if count is not None:
        functions.append({"function": "set_count", "count": count})
    if explosion_decay:
        functions.append({"function": "explosion_decay"})

    bedrock_entry: dict = {"type": "item", "name": name}
    if functions:
        bedrock_entry["functions"] = functions

    return {"pools": [{"rolls": 1, "entries": [bedrock_entry]}]}, None


def convert(mod: SourceMod, context: LoadContext | None = None, deferred: list | None = None,
            station_tables: set[str] | None = None) -> ConversionResult:
    """Convert the mod's block loot tables.

    A table whose own load conditions (``neoforge:conditions``,
    ``fabric:load_conditions``; never the pool and entry ``conditions``, which
    are loot predicates) are false or undecidable here is
    ``conditional_loot_table`` residue (#183).

    A table named in ``station_tables`` (a block a station runtime reads the
    table of, #177 feasts) whose load conditions pass is appended to
    ``deferred`` as (source path, table) for that station instead.
    """
    result = ConversionResult()
    own_context = context is None
    if context is None:
        context = LoadContext(mod)
    for dirname in _TABLE_DIRS:
        src = mod.data / dirname / "blocks"
        if not src.is_dir():
            continue
        for path in sorted(src.rglob("*.json")):
            rel = result.claim(mod, path)
            try:
                data = json.loads(path.read_text())
            except json.JSONDecodeError as exc:
                result.unhandled.append(Unhandled(rel, "loot", f"invalid JSON: {exc}"))
                continue
            if not isinstance(data, dict):
                result.unhandled.append(Unhandled(rel, "loot", "loot table is not a JSON object"))
                continue
            verdict = context.gate(data, "loot")
            if verdict.passes is not True:
                result.unhandled.append(Unhandled(rel, "conditional_loot_table", verdict.reason()))
                continue

            name = path.relative_to(src).with_suffix("").as_posix()
            if station_tables and deferred is not None and name in station_tables:
                deferred.append((rel, data))
                continue
            table, reason = _convert_table(data)
            if table is None:
                result.unhandled.append(Unhandled(rel, "loot", reason or "unsupported loot table"))
                continue

            result.files[f"loot_tables/blocks/{name}.json"] = table
    note = context.note() if own_context else None
    if note:
        result.notes.append(note)
    return result


OWNED = "owned_by_residue"
_BLOCK_TABLE = re.compile(r"^data/([^/]+)/(?:loot_tables|loot_table)/blocks/(.+)\.json$")


def refine_owned(unhandled: list[Unhandled], shipped_blocks: set[str]) -> list[Unhandled]:
    """Re-file a refused block loot table whose block is itself residue (#299).

    A ``loot`` entry for ``data/<ns>/loot_table[s]/blocks/<path>.json`` names
    the block ``<ns>:<path>``. When the pack doesn't ship that block and its
    blockstate ``assets/<ns>/blockstates/<path>.json`` has a residue entry of
    its own (the block converter refused it, or it is a ``code_drawn_block``),
    the table has no block to drop from (its item may still ship: a Java
    block's item shares the block's id, so only the pack's blocks count here): it becomes ``owned_by_residue``, the
    explained kind models and textures of refused blocks already use (#292),
    keeping why the table itself was refused. It goes with its block when that
    converts. A table whose block shipped, or has no blockstate, stays ``loot``.
    """
    residue = {u.source: u.kind for u in unhandled if u.kind not in ("loot", OWNED)}
    out: list[Unhandled] = []
    for u in unhandled:
        match = _BLOCK_TABLE.match(u.source) if u.kind == "loot" else None
        if match:
            ns, path = match.groups()
            blockstate = f"assets/{ns}/blockstates/{path}.json"
            if f"{ns}:{path}" not in shipped_blocks and blockstate in residue:
                out.append(Unhandled(
                    source=u.source, kind=OWNED, count=u.count,
                    reason=(f"the loot table of block {ns}:{path}, which the pack doesn't ship: its blockstate "
                            f"{blockstate} is residue ({residue[blockstate]}) with its own entry, so the table "
                            f"goes with the block when it converts (the table itself: {u.reason})")))
                continue
        out.append(u)
    return out
