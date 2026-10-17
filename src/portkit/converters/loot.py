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

import itertools
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


_BLOCK_STATE = ("minecraft:block_state_property", "block_state_property")

# Java's drop of air is a drop of nothing. Whether a block that drops nothing
# gets an empty Bedrock table is open on #299, so such a table is never wired
# onto its block (see wire).
AIR = ("minecraft:air", "air")

_NEVER = "\0never"


def _state_value(value) -> str | None:
    """A block_state_property value as Java compares it: the state value's name."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int)):
        return str(value)
    return None


def _function_guard(function: dict, block: str | None,
                    states: dict | None) -> tuple[dict[str, str] | None, str | None]:
    """The block state a function's own ``conditions`` ask for, as {property: value},
    or why they can't be decided for the converted block (#299).

    Java applies a function only when every condition in its ``conditions``
    holds (a slab's ``set_count 2`` only when it is ``type=double``). The one
    kind portkit translates is ``block_state_property`` on the table's own
    block, read against ``states``: the converted block's Bedrock state test
    for each Java property value, as the block converter recorded it
    (``ConversionResult.java_states``; None for a value Bedrock can't reach).
    """
    fname = function.get("function")
    conditions = function.get("conditions") or []
    if not isinstance(conditions, list):
        return None, f"function {fname!r} has unreadable conditions"
    wanted: dict[str, str] = {}
    for condition in conditions:
        cname = condition.get("condition") if isinstance(condition, dict) else None
        if cname not in _BLOCK_STATE:
            return None, (f"function {fname} applies only when {cname} holds; only block-state "
                          f"conditions on a function are translated, and it is never applied unconditionally")
        if block is not None and condition.get("block") not in (None, block):
            return None, f"function {fname} tests the state of another block ({condition.get('block')})"
        properties = condition.get("properties")
        if not isinstance(properties, dict) or not properties:
            return None, f"function {fname}'s block-state condition names no state"
        for prop, raw in properties.items():
            value = _state_value(raw)
            if value is None:
                return None, (f"function {fname} applies only for a range of {prop} states "
                              f"({json.dumps(raw)}), which isn't translated")
            shown = f"{prop}={value}"
            if block is None or states is None:
                return None, (f"function {fname} applies only when the block state is {shown}, and "
                              f"there is no converted block whose Bedrock states could be tested")
            mapped = states.get(prop)
            if mapped is None:
                return None, (f"function {fname} applies only when the block state is {shown}, and "
                              f"the converted block {block} carries no Bedrock state for {prop}")
            if value not in mapped:
                return None, (f"function {fname} applies only when the block state is {shown}, which "
                              f"isn't one of the {prop} values the converted block {block} maps")
            if wanted.get(prop, value) != value:
                # Two values of one property at once: the function never applies.
                wanted[prop] = _NEVER
                continue
            wanted[prop] = value
    return wanted, None


def _table_for(name: str, functions: list[dict], explosion_decay: bool) -> tuple[dict | None, str | None]:
    """The Bedrock table for one item entry and the functions that apply to it, in order."""
    count = None
    for function in functions:
        fname = function.get("function")
        if fname in ("minecraft:set_count", "set_count"):
            value = _constant_count(function)
            if value is None:
                return None, "the drop count is a range rather than a fixed number"
            if function.get("add") is True:
                return None, "the drop count is added to (set_count add) rather than set"
            count = value
            continue
        if fname in ("minecraft:explosion_decay", "explosion_decay"):
            explosion_decay = True
            continue
        return None, _reason_for_function(function)

    out: list[dict] = []
    if count is not None:
        out.append({"function": "set_count", "count": count})
    if explosion_decay:
        out.append({"function": "explosion_decay"})
    bedrock_entry: dict = {"type": "item", "name": name}
    if out:
        bedrock_entry["functions"] = out
    return {"pools": [{"rolls": 1, "entries": [bedrock_entry]}]}, None


def convert_table(data: dict, block: str | None = None,
                  states: dict | None = None) -> tuple[list[tuple[str | None, dict]] | None, str | None]:
    """Return ([(permutation condition or None, Bedrock table), ...], None), or
    (None, why the table is refused).

    One table (condition None) is the usual answer. A function whose own
    ``conditions`` test the block's state (#299) is decided per Bedrock state
    of the converted block ``block`` (``states``, see :func:`_function_guard`):
    a state Bedrock can't reach (Java's double slab) never applies it, and when
    the states it can reach give different tables, each gets its own, with the
    ``q.block_state`` test of the permutation that uses it. A function
    condition that can't be decided refuses the table: it is never applied
    unconditionally, and never dropped silently.
    """
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

    guarded: list[tuple[dict, dict[str, str]]] = []
    for function in list(pool.get("functions") or []) + list(entry.get("functions") or []):
        wanted: dict[str, str] | None = {}
        if function.get("conditions"):
            wanted, why = _function_guard(function, block, states)
            if wanted is None:
                return None, why
        guarded.append((function, wanted))

    # Every Bedrock state of the properties the functions test; the Java values
    # Bedrock can't reach (None) are left out.
    props = sorted({p for _, wanted in guarded for p in wanted})
    choices = []
    for prop in props:
        reachable = [(prop, v) for v, test in (states or {}).get(prop, {}).items() if test is not None]
        if not reachable:
            return None, f"no Bedrock state of the converted block {block} has a {prop} value to test"
        choices.append(reachable)
    tables: dict[str, tuple[dict, list[str]]] = {}
    for case in itertools.product(*choices):
        state = dict(case)
        active = [f for f, wanted in guarded if all(state.get(p) == v for p, v in wanted.items())]
        table, why = _table_for(name, active, explosion_decay)
        if table is None:
            return None, why
        test = " && ".join(states[p][v] for p, v in case)
        tables.setdefault(json.dumps(table, sort_keys=True), (table, []))[1].append(test)
    if len(tables) == 1:
        return [(None, next(iter(tables.values()))[0])], None
    return [(" || ".join(f"({t})" for t in tests) if len(tests) > 1 else tests[0], table)
            for table, tests in tables.values()], None


def _drops_itself(table: dict, block: str) -> bool:
    """The table is Bedrock's default for a block: one of itself (explosion decay aside)."""
    entry = table["pools"][0]["entries"][0]
    if entry.get("name") != block:
        return False
    for function in entry.get("functions") or []:
        if function.get("function") == "explosion_decay":
            continue
        if function.get("function") == "set_count" and function.get("count") == 1:
            continue
        return False
    return True


def _bedrock_names(cases: list[tuple[str | None, dict]]) -> tuple[list | None, str | None]:
    """Each table's drop under its Bedrock id (#299): Java vanilla ids Bedrock
    spells differently are rewritten the way recipes are (#261), with
    ``set_data`` when Bedrock's id stands for several Java items."""
    from .recipes import bedrock_item

    out = []
    for condition, table in cases:
        entry = dict(table["pools"][0]["entries"][0])
        got = bedrock_item(entry["name"])
        if isinstance(got, str):
            return None, f"the drop can't be written for Bedrock: {got}"
        ident, data = got
        entry["name"] = ident
        if data is not None:
            functions = [f for f in entry.get("functions") or [] if f.get("function") != "explosion_decay"]
            functions.append({"function": "set_data", "data": data})
            functions += [f for f in entry.get("functions") or [] if f.get("function") == "explosion_decay"]
            entry["functions"] = functions
        out.append((condition, {"pools": [{"rolls": 1, "entries": [entry]}]}))
    return out, None


def _has_loot(block: dict) -> bool:
    body = block.get("minecraft:block") or {}
    if "minecraft:loot" in (body.get("components") or {}):
        return True
    return any("minecraft:loot" in (p.get("components") or {})
               for p in body.get("permutations") or [] if isinstance(p, dict))


def _definitions(files: dict) -> tuple[dict[str, str], set[str]]:
    """(block id -> its definition path, every block and item id) among ``files``."""
    blocks: dict[str, str] = {}
    obtainable: set[str] = set()
    for path, body in files.items():
        if not isinstance(body, dict):
            continue
        for key in ("minecraft:block", "minecraft:item"):
            ident = ((body.get(key) or {}).get("description") or {}).get("identifier")
            if isinstance(ident, str):
                obtainable.add(ident)
                if key == "minecraft:block" and path.startswith("blocks/"):
                    blocks[ident] = path
    return blocks, obtainable


def _wire_refusal(cases: list[tuple[str | None, dict]], obtainable: set[str]) -> str | None:
    """Why a table can't be put on its block, or None."""
    for _, table in cases:
        name = table["pools"][0]["entries"][0]["name"]
        if name in AIR:
            return ("the table drops minecraft:air, i.e. the block drops nothing; whether such a block "
                    "gets an empty Bedrock table is an open pick on #299, so it isn't wired")
        if not name.startswith("minecraft:") and name not in obtainable:
            return (f"the block drops {name}, which this pack doesn't define (see that identifier's own "
                    f"residue entry), so the table can't be wired onto the block")
    return None


def _wire(block: dict, name: str, cases: list[tuple[str | None, dict]], files: dict) -> dict:
    """``block`` with ``minecraft:loot`` naming its table(s); the tables go in ``files``.

    One table: the block's base component. Several (a function decided per
    Bedrock state): the first on the base, each other one on a permutation
    with the state test it was decided for (permutations can override
    minecraft:loot, as the #177 feast stations do)."""
    block = json.loads(json.dumps(block))
    body = block["minecraft:block"]
    paths = []
    for i, (condition, table) in enumerate(cases):
        path = f"loot_tables/blocks/{name}.json" if i == 0 else f"loot_tables/blocks/{name}.state{i}.json"
        files[path] = table
        paths.append((condition, path))
    body.setdefault("components", {})["minecraft:loot"] = paths[0][1]
    if len(paths) > 1:
        body.setdefault("permutations", [])
        body["permutations"] += [{"condition": c, "components": {"minecraft:loot": p}} for c, p in paths[1:]]
    return block


def convert(mod: SourceMod, context: LoadContext | None = None, deferred: list | None = None,
            station_tables: set[str] | None = None, blocks: dict | None = None,
            java_states: dict | None = None) -> ConversionResult:
    """Convert the mod's block loot tables.

    A table whose own load conditions (``neoforge:conditions``,
    ``fabric:load_conditions``; never the pool and entry ``conditions``, which
    are loot predicates) are false or undecidable here is
    ``conditional_loot_table`` residue (#183).

    A table named in ``station_tables`` (a block a station runtime reads the
    table of, #177 feasts) whose load conditions pass is appended to
    ``deferred`` as (source path, table) for that station instead.

    ``blocks`` are the namespace's converted files so far (blocks and items)
    and ``java_states`` their Java state map (``ConversionResult.java_states``).
    A table whose block converted is put on it with ``minecraft:loot`` (#299),
    unless the table is Bedrock's default for a block (one of itself), which
    stays the default: a custom block without ``minecraft:loot`` drops itself
    (learn.microsoft.com minecraft:loot). The block definition is re-emitted
    under its own path, so it replaces the earlier one when merged.
    """
    result = ConversionResult()
    own_context = context is None
    if context is None:
        context = LoadContext(mod)
    by_id, obtainable = _definitions(blocks or {})
    wired: list[str] = []
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
            block_id = f"{mod.namespace}:{name}"
            block_path = by_id.get(block_id)
            cases, reason = convert_table(data, block_id if block_path else None,
                                          (java_states or {}).get(block_id, {}) if block_path else None)
            if cases is not None:
                cases, reason = _bedrock_names(cases)
            if cases is None:
                result.unhandled.append(Unhandled(rel, "loot", reason or "unsupported loot table"))
                continue

            if block_path is None or (len(cases) == 1 and _drops_itself(cases[0][1], block_id)):
                result.files[f"loot_tables/blocks/{name}.json"] = cases[0][1]
                continue
            block = (blocks or {}).get(block_path)
            if _has_loot(block):
                # An adapter or station already decided this block's drops.
                result.files[f"loot_tables/blocks/{name}.json"] = cases[0][1]
                continue
            why = _wire_refusal(cases, obtainable)
            if why:
                result.unhandled.append(Unhandled(rel, "loot", why))
                continue
            result.files[block_path] = _wire(block, name, cases, result.files)
            wired.append(block_id)
    if wired:
        result.notes.append(
            f"{len(wired)} block(s) drop what their Java loot table gives through minecraft:loot (#299; "
            f"another item, a count, or a drop decided per block state), e.g. {', '.join(wired[:3])}; "
            "a block whose table drops itself keeps Bedrock's default, which is the same drop")
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
