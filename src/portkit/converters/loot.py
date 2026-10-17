"""Block drops.

Java loot tables are a small programming language: nested pools, weighted
entries, alternatives, number providers, enchantment bonuses. Bedrock's are a
flatter version of the same idea and do not have most of it.

The shape that carries almost every modded decorative block is: one pool, one
roll, one item entry, drops itself, survives explosions. That converts. A table
that reaches for fortune, a random count or a condition Bedrock can't test is
refused with the condition or function that defeated it named in the reason.
Silk Touch, shears and tool tier are approximated with Bedrock's match_tool
and each approximation is a report note (#299, see the tools section below).
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

# Java's drop of air is a drop of nothing: a converted block whose table drops
# nothing names Bedrock's vanilla empty table (Alex, #299 pick 2).
AIR = ("minecraft:air", "air")
# Bedrock's vanilla drop-nothing table (Mojang/bedrock-samples@46ba6ea9
# behavior_pack/loot_tables/empty.json): a block may name it without shipping it.
EMPTY_TABLE = "loot_tables/empty.json"

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


# -- tools (#299) -----------------------------------------------------------
#
# Java branches block drops on the tool: Silk Touch, shears, a tool type. Alex
# decided (2026-10-16, #299) to approximate these rather than refuse them,
# because a block that mostly drops the right thing beats one that drops itself:
#
# * Silk Touch. Bedrock never reads a block's minecraft:loot when it is broken
#   with Silk Touch: the block drops itself (wiki.bedrock.dev Tool-Based
#   Destruction, "It is impossible to prevent a block from dropping itself when
#   mined using an item with the Silk Touch enchantment"; Ore Loot Tables,
#   "Won't be dropped if using Silk Touch"). So the table only ever runs
#   without Silk Touch: a Java Silk Touch test is false there, its negation
#   true. When Java's Silk Touch drop is the block itself that is exact; when
#   it isn't, the table says so in an approximation note.
# * Shears and tool types become Bedrock's ``match_tool`` condition with
#   ``minecraft:match_tool_filter_any`` on Bedrock's own item tags
#   (learn.microsoft.com, Loot and Trade Table Conditions, match_tool;
#   Vanilla Item Tags, Tool tags: minecraft:is_shears, is_pickaxe, ...). A Java
#   tag or tool ability also takes other mods' tools; on Bedrock only items
#   carrying the Bedrock tag (the vanilla ones) count, which is noted.
# * Tool tier: a block in Java's needs_<tier>_tool tags drops (in vanilla's
#   requiresCorrectToolForDrops blocks) only for its mineable tool of that tier
#   or better. Bedrock custom blocks have no such rule (Tool-Based Destruction,
#   "There is no proper way to specify which tools are required"), so the
#   table gets a match_tool test on the tool and tier tags. It never gives more
#   than Java: copper and golden tiers, mod tools and explosions get nothing.

SILK = "silk"
# Java tool tests -> Bedrock item tag (learn.microsoft.com, Vanilla Item Tags).
_SHEARS = "minecraft:is_shears"
_JAVA_TOOL_TAGS = {
    "forge:shears": _SHEARS, "c:shears": _SHEARS, "c:tools/shears": _SHEARS, "c:tools/shear": _SHEARS,
    "minecraft:pickaxes": "minecraft:is_pickaxe", "minecraft:axes": "minecraft:is_axe",
    "minecraft:shovels": "minecraft:is_shovel", "minecraft:hoes": "minecraft:is_hoe",
    "minecraft:swords": "minecraft:is_sword",
}
# Loader tool abilities that only shears perform among vanilla items
# (NeoForge ItemAbilities.SHEARS_*, Forge ToolActions.SHEARS_*).
_SHEAR_ABILITIES = {"shears_dig", "shears_harvest", "shears_carve", "shears_disarm", "shears_trim"}
_ABILITY_CONDITIONS = {"forge:can_tool_perform_action": "action", "neoforge:can_item_perform_ability": "ability"}

# A tool test: None never holds, [] always holds, otherwise every set in the
# list holds for some tag in it (an AND of ORs over Bedrock item tags).
_ALWAYS: list = []


class _Refused(Exception):
    pass


def _silk(predicate: dict) -> bool:
    """The predicate is exactly 'has Silk Touch' (any level from 1)."""
    rest = {k: v for k, v in predicate.items() if k not in ("enchantments", "predicates")}
    if rest:
        return False
    found = []
    for e in predicate.get("enchantments") or []:
        found.append((e.get("enchantment"), e.get("levels")))
    for key, value in (predicate.get("predicates") or {}).items():
        if key != "minecraft:enchantments":
            return False
        for e in value if isinstance(value, list) else [value]:
            found.append((e.get("enchantments"), e.get("levels")))
    if len(found) != 1:
        return False
    name, levels = found[0]
    if name not in ("minecraft:silk_touch", "silk_touch"):
        return False
    if levels is None:
        return True
    if isinstance(levels, int):
        return levels == 1
    return isinstance(levels, dict) and levels.get("min", 1) <= 1 and "max" not in levels


def _tool_tags(predicate: dict, approx: list[str]) -> frozenset:
    if set(predicate) - {"items", "tag"}:
        raise _Refused(f"the drop depends on the tool used, in a way Bedrock's match_tool can't test "
                       f"({json.dumps(predicate, sort_keys=True)})")
    refs = []
    items = predicate.get("items")
    refs += items if isinstance(items, list) else ([items] if items else [])
    if predicate.get("tag"):
        refs.append("#" + predicate["tag"])
    tags = set()
    for ref in refs:
        if ref in ("minecraft:shears", "shears"):
            tags.add(_SHEARS)
            continue
        bedrock = _JAVA_TOOL_TAGS.get(ref[1:]) if isinstance(ref, str) and ref.startswith("#") else None
        if bedrock is None:
            raise _Refused(f"the drop depends on the tool {ref!r}, which has no Bedrock item tag to test")
        tags.add(bedrock)
        approx.append(f"Java's tool tag {ref} also takes other mods' tools; on Bedrock only items tagged "
                      f"{bedrock} (the vanilla ones) count")
    if not tags:
        raise _Refused("the drop depends on the tool used, but the match_tool test names no tool")
    return frozenset(tags)


def _tool_test(condition: dict, silk_world: bool, approx: list[str]):
    """A Java loot condition as a tool test (see _ALWAYS), in Bedrock's table
    (``silk_world`` False: the table never runs under Silk Touch) or in
    Java's world under a Silk Touch tool that is no other tool tested."""
    name = condition.get("condition")
    if name in ("minecraft:match_tool", "match_tool"):
        predicate = condition.get("predicate") or {}
        if _silk(predicate):
            return _ALWAYS if silk_world else None
        tags = _tool_tags(predicate, approx)
        return None if silk_world else [tags]
    if name in _ABILITY_CONDITIONS:
        if condition.get(_ABILITY_CONDITIONS[name]) not in _SHEAR_ABILITIES:
            raise _Refused(f"the drop depends on a tool ability ({name} "
                           f"{condition.get(_ABILITY_CONDITIONS[name])!r}) with no Bedrock item tag to test")
        approx.append(f"Java's {name} shears test also takes other mods' shears; on Bedrock only items "
                      f"tagged {_SHEARS} (vanilla shears) count")
        return None if silk_world else [frozenset({_SHEARS})]
    if name in ("minecraft:inverted", "inverted"):
        inner = _tool_test(condition.get("term") or {}, silk_world, approx)
        if inner is None:
            return _ALWAYS
        if inner == _ALWAYS:
            return None
        raise _Refused("the drop depends on NOT using a tool (an inverted match_tool); "
                       "Bedrock can't test that a tool is absent")
    if name in ("minecraft:any_of", "any_of", "minecraft:alternative", "alternative"):
        terms = [_tool_test(t, silk_world, approx) for t in condition.get("terms") or []]
        if any(t == _ALWAYS for t in terms):
            return _ALWAYS
        held = [t for t in terms if t is not None]
        if not held:
            return None
        if any(len(t) != 1 for t in held):
            raise _Refused("the drop depends on a mix of tool tests Bedrock's match_tool can't combine")
        return [frozenset().union(*(t[0] for t in held))]
    if name in ("minecraft:all_of", "all_of"):
        out: list = []
        for t in condition.get("terms") or []:
            test = _tool_test(t, silk_world, approx)
            if test is None:
                return None
            out += [s for s in test if s not in out]
        return out
    raise _Refused(_reason_for_condition(condition))


def _and(a, b):
    if a is None or b is None:
        return None
    return a + [s for s in b if s not in a]


def _conditions(conditions: list, silk_world: bool, approx: list[str]):
    """(tool test, explosion decay) for a pool's or entry's conditions."""
    test, decay = _ALWAYS, False
    for condition in conditions or []:
        if condition.get("condition") in (_EXPLOSION, "survives_explosion"):
            decay = True
            continue
        test = _and(test, _tool_test(condition, silk_world, approx))
    return test, decay


def _drop(data: dict, silk_world: bool, approx: list[str]):
    """The table's one drop as (tool test, item entry, pool functions,
    explosion decay), None when it drops nothing (every pool's tool test fails
    or there are no pools); raises _Refused otherwise."""
    pools = data.get("pools")
    if pools is not None and not isinstance(pools, list):
        raise _Refused("the table's pools are unreadable")
    found = []
    for pool in pools or []:
        rolls = pool.get("rolls", 1)
        if not isinstance(rolls, (int, float)) or int(rolls) != 1:
            raise _Refused("the pool rolls a variable number of times")
        test, decay = _conditions(pool.get("conditions"), silk_world, approx)
        if test is None:
            continue
        drops = []
        entries = pool.get("entries") or []
        for entry in entries:
            try:
                drops += _entry_drops(entry, test, decay, silk_world, approx)
            except _Refused:
                if len(entries) > 1:
                    raise _Refused(f"the pool has {len(entries)} entries; only a single drop is unambiguous")
                raise
        if len(drops) > 1:
            raise _Refused(f"the pool has {len(pool.get('entries') or [])} entries; only a single drop is unambiguous")
        found += [(t, e, pool.get("functions") or [], d) for t, e, d in drops]
    if len(found) > 1:
        raise _Refused(f"table has {len(pools)} pools; Bedrock block drops are a single pool")
    return found[0] if found else None


def _entry_drops(entry: dict, test, decay: bool, silk_world: bool, approx: list[str]) -> list:
    entry_type = entry.get("type")
    if entry_type in ("minecraft:alternatives", "alternatives"):
        own, own_decay = _conditions(entry.get("conditions"), silk_world, approx)
        test = _and(test, own)
        if test is None:
            return []
        # The first child whose conditions hold. A child that may or may not
        # hold (a tool test) can only be the last one Bedrock reaches: the
        # ones after it would need "and not that tool".
        children = entry.get("children") or []
        for i, child in enumerate(children):
            if child.get("type") not in _SUPPORTED_ENTRY_TYPES:
                raise _Refused("the drop picks between alternatives (usually silk touch) that aren't plain item drops")
            child_test, child_decay = _conditions(child.get("conditions"), silk_world, approx)
            if child_test is None:
                continue
            if child_test != _ALWAYS and any(
                    _conditions(c.get("conditions"), silk_world, [])[0] is not None
                    for c in children[i + 1:]):
                raise _Refused("the drop picks between alternatives (usually silk touch): a tool-specific drop "
                               "and another one, and Bedrock can't test that a tool is absent")
            return [(_and(test, child_test), child, decay or own_decay or child_decay)]
        return []
    if entry_type not in _SUPPORTED_ENTRY_TYPES:
        raise _Refused(f"entry type {entry_type!r} is not a plain item drop")
    own, own_decay = _conditions(entry.get("conditions"), silk_world, approx)
    test = _and(test, own)
    return [] if test is None else [(test, entry, decay or own_decay)]


def _match_tool(tags: frozenset) -> dict:
    return {"condition": "match_tool", "minecraft:match_tool_filter_any": sorted(tags)}


def _java_silk_drop(data: dict, block_id: str) -> str | None:
    """None when Java drops the block itself, once, under Silk Touch (a tool
    no other test names); otherwise what it drops there, in words."""
    try:
        drop = _drop(data, True, [])
    except _Refused:
        return "what its table gives there (not read)"
    if drop is None:
        return "nothing"
    _, entry, functions, _ = drop
    name = entry.get("name")
    if name in AIR:
        return "nothing"
    count = 1
    for function in list(functions) + list(entry.get("functions") or []):
        fname = function.get("function")
        if fname in ("minecraft:explosion_decay", "explosion_decay"):
            continue
        if fname in ("minecraft:set_count", "set_count") and not function.get("conditions") \
                and _constant_count(function) is not None and not function.get("add"):
            count = _constant_count(function)
            continue
        return f"{name} (with {fname})"
    if name == block_id and count == 1:
        return None
    return name if count == 1 else f"{count} {name}"


def _paired_test(condition, block: str, prop: str) -> bool:
    """The condition is ``block_state_property`` ``{prop: "lower"}`` on ``block``."""
    return (isinstance(condition, dict) and condition.get("condition") in _BLOCK_STATE
            and condition.get("block") in (None, block)
            and condition.get("properties") == {prop: "lower"})


def fold_paired_half(data: dict, block: str, prop: str) -> dict:
    """``data`` with its ``{prop: "lower"}`` block-state conditions dropped, for a
    block written on Bedrock's two-part multi_block trait (#296).

    Java runs the lower half's table whichever half the player breaks (the
    upper half's break takes the lower half with drops: ``updateShape``
    answers air and ``Block#updateOrDestroy`` destroys it dropping), so a pool
    or entry gated on half=lower drops once per broken door. Bedrock runs only
    the broken part's table (wiki.bedrock.dev Multi-Blocks, Destruction), so
    for whichever part is broken the test holds. Any other half test is left
    for convert_table to refuse."""
    def entry(e):
        if not isinstance(e, dict):
            return e
        e = dict(e)
        if isinstance(e.get("conditions"), list):
            e["conditions"] = [c for c in e["conditions"] if not _paired_test(c, block, prop)]
        if isinstance(e.get("children"), list):
            e["children"] = [entry(c) for c in e["children"]]
        return e

    out = dict(data)
    pools = []
    for pool in data.get("pools") or []:
        if isinstance(pool, dict):
            pool = dict(pool)
            if isinstance(pool.get("conditions"), list):
                pool["conditions"] = [c for c in pool["conditions"] if not _paired_test(c, block, prop)]
            if isinstance(pool.get("entries"), list):
                pool["entries"] = [entry(e) for e in pool["entries"]]
        pools.append(pool)
    if "pools" in data:
        out["pools"] = pools
    return out


def convert_table(data: dict, block: str | None = None,
                  states: dict | None = None,
                  approx: list[str] | None = None) -> tuple[list[tuple[str | None, dict]] | None, str | None]:
    """Return ([(permutation condition or None, Bedrock table), ...], None), or
    (None, why the table is refused). ``[]`` is a table that drops nothing.

    One table (condition None) is the usual answer. A function whose own
    ``conditions`` test the block's state (#299) is decided per Bedrock state
    of the converted block ``block`` (``states``, see :func:`_function_guard`):
    a state Bedrock can't reach (Java's double slab) never applies it, and when
    the states it can reach give different tables, each gets its own, with the
    ``q.block_state`` test of the permutation that uses it. A function
    condition that can't be decided refuses the table: it is never applied
    unconditionally, and never dropped silently.

    Tool tests (Silk Touch, shears, tool tags) are translated as the comment
    above says; each approximation is appended to ``approx``.
    """
    approx = [] if approx is None else approx
    pools = data.get("pools")
    if not isinstance(pools, list) or not pools:
        return [], None
    live = 0
    for pool in pools:
        try:
            live += _conditions(pool.get("conditions") if isinstance(pool, dict) else None, False, []) [0] is not None
        except _Refused:
            live += 1
    if live > 1:
        return None, f"table has {len(pools)} pools; Bedrock block drops are a single pool"
    try:
        drop = _drop(data, False, approx)
    except _Refused as exc:
        return None, str(exc)
    if drop is None:
        return [], None
    test, entry, pool_functions, explosion_decay = drop

    name = entry.get("name")
    if not isinstance(name, str) or ":" not in name:
        return None, f"entry names {name!r}, which is not a namespaced item"
    if name in AIR:
        # Java's drop of air is a drop of nothing (#299 pick 2).
        return [], None

    guarded: list[tuple[dict, dict[str, str]]] = []
    for function in list(pool_functions) + list(entry.get("functions") or []):
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
        reachable = [(prop, v) for v, test_ in (states or {}).get(prop, {}).items() if test_ is not None]
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
        if test:
            table["pools"][0]["entries"][0]["conditions"] = [_match_tool(tags) for tags in test]
        key = " && ".join(states[p][v] for p, v in case)
        tables.setdefault(json.dumps(table, sort_keys=True), (table, []))[1].append(key)
    if len(tables) == 1:
        return [(None, next(iter(tables.values()))[0])], None
    return [(" || ".join(f"({t})" for t in tests) if len(tests) > 1 else tests[0], table)
            for table, tests in tables.values()], None


def _drops_itself(table: dict, block: str) -> bool:
    """The table is Bedrock's default for a block: one of itself (explosion decay aside)."""
    entries = table["pools"][0]["entries"]
    if len(entries) != 1:
        return False
    entry = entries[0]
    if entry.get("name") != block or entry.get("conditions"):
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
        entries = []
        for entry in table["pools"][0]["entries"]:
            entry = dict(entry)
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
            entries.append(entry)
        out.append((condition, {"pools": [{"rolls": 1, "entries": entries}]}))
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
        for entry in table["pools"][0]["entries"]:
            name = entry["name"]
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


# Java tier tag -> the Bedrock tier tags of that tier or better (Java's order
# stone < iron < diamond < netherite; minecraft.wiki "Tag (Java Edition)",
# needs_*_tool; Forge 1.20.1 forge:needs_netherite_tool). Bedrock's golden and
# copper tiers are left out: Java's golden tools are wood level, and leaving
# copper out can only give less (learn.microsoft.com, Vanilla Item Tags, Tier tags).
_TIERS = {
    "minecraft:needs_stone_tool": ("minecraft:stone_tier", "minecraft:iron_tier",
                                   "minecraft:diamond_tier", "minecraft:netherite_tier"),
    "minecraft:needs_iron_tool": ("minecraft:iron_tier", "minecraft:diamond_tier", "minecraft:netherite_tier"),
    "minecraft:needs_diamond_tool": ("minecraft:diamond_tier", "minecraft:netherite_tier"),
    "forge:needs_netherite_tool": ("minecraft:netherite_tier",),
}
# Java mineable tag -> Bedrock tool item tag (Vanilla Item Tags, Tool tags).
_MINEABLE = {
    "minecraft:mineable/pickaxe": "minecraft:is_pickaxe",
    "minecraft:mineable/axe": "minecraft:is_axe",
    "minecraft:mineable/shovel": "minecraft:is_shovel",
    "minecraft:mineable/hoe": "minecraft:is_hoe",
}


def _tier_index(mod: SourceMod) -> dict[str, tuple[str, list[str], tuple[str, ...]]]:
    """block id -> (Java tier tag, Bedrock tool tags of its mineable tags, Bedrock
    tiers that drop it), from the jar's own block tags (#293's reader)."""
    from ..datatags import jar_members

    dirs = ("blocks", "block")
    loader = getattr(mod, "loader", None)
    tools: dict[str, list[str]] = {}
    for java, bedrock in _MINEABLE.items():
        for member in jar_members(mod.root, java, dirs, loader) or []:
            tools.setdefault(member, []).append(bedrock)
    out: dict[str, tuple[str, list[str], tuple[str, ...]]] = {}
    for java, tiers in _TIERS.items():
        for member in jar_members(mod.root, java, dirs, loader) or []:
            have = out.get(member)
            if have is None or len(tiers) < len(have[2]):
                out[member] = (java, sorted(tools.get(member, [])), tiers)
    return out


def _gate(cases: list[tuple[str | None, dict]], tools: list[str],
          tiers: tuple[str, ...]) -> list[tuple[str | None, dict]]:
    """Each table's drop only for one of ``tools`` of one of ``tiers`` (an
    entry per tool: a vanilla tool is one type, so at most one holds)."""
    out = []
    for condition, table in cases:
        entries = []
        for entry in table["pools"][0]["entries"]:
            for tool in tools:
                gated = json.loads(json.dumps(entry))
                gated["conditions"] = list(gated.get("conditions") or []) + [{
                    "condition": "match_tool",
                    "minecraft:match_tool_filter_all": ["minecraft:is_tool", tool],
                    "minecraft:match_tool_filter_any": list(tiers)}]
                entries.append(gated)
        out.append((condition, {"pools": [{"rolls": 1, "entries": entries}]}))
    return out


def _silk_note(java: str | None) -> str | None:
    """The approximation a wired table has under Silk Touch (Java's drop there
    from :func:`_java_silk_drop`), or None when Java drops the block itself too."""
    if java is None:
        return None
    return (f"with Silk Touch Bedrock drops the block itself (it ignores minecraft:loot under Silk Touch), "
            f"where Java drops {java}")


def convert(mod: SourceMod, context: LoadContext | None = None, deferred: list | None = None,
            station_tables: set[str] | None = None, blocks: dict | None = None,
            java_states: dict | None = None, paired: dict | None = None) -> ConversionResult:
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
    tiers = _tier_index(mod) if by_id else {}
    wired: list[str] = []
    emptied: list[str] = []
    approximated: list[str] = []
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
            approx: list[str] = []
            if block_path and block_id in (paired or {}):
                data = fold_paired_half(data, block_id, paired[block_id])
            cases, reason = convert_table(data, block_id if block_path else None,
                                          (java_states or {}).get(block_id, {}) if block_path else None,
                                          approx)
            if cases:
                cases, reason = _bedrock_names(cases)
            if cases is None:
                result.unhandled.append(Unhandled(rel, "loot", reason or "unsupported loot table"))
                continue
            block = (blocks or {}).get(block_path) if block_path else None

            if cases == []:
                # Java drops nothing here (no pools, a drop of air, or only
                # under Silk Touch): the converted block names Bedrock's
                # vanilla empty table (#299 pick 2).
                if block_path is None:
                    result.unhandled.append(Unhandled(rel, "loot", (
                        "the table drops nothing (no pools, a drop of minecraft:air, or a drop only under "
                        "Silk Touch) and the pack has no converted block to point at Bedrock's empty table")))
                    continue
                if not _has_loot(block):
                    wired_block = json.loads(json.dumps(block))
                    wired_block["minecraft:block"].setdefault("components", {})["minecraft:loot"] = EMPTY_TABLE
                    result.files[block_path] = wired_block
                    emptied.append(block_id)
                    note = _silk_note(_java_silk_drop(data, block_id))
                    if note:
                        approx.append(note)
                if approx:
                    approximated.append(block_id)
                    result.notes.append(f"{rel}: approximated loot (#299): " + "; ".join(dict.fromkeys(approx)))
                continue

            gate = tiers.get(block_id) if block_path else None
            if gate is not None:
                java_tier, tools, tier_tags = gate
                if not tools:
                    result.unhandled.append(Unhandled(rel, "loot", (
                        f"the block is in {java_tier} but in no mineable tag, so no tool drops it in Java; "
                        f"Bedrock can't gate a drop on that (#299)")))
                    continue
                cases = _gate(cases, tools, tier_tags)
                approx.append(
                    f"{java_tier}: drops only for a vanilla {'/'.join(t.split('_', 1)[1] for t in tools)} of "
                    f"{'/'.join(t.split(':')[1].removesuffix('_tier') for t in tier_tags)} tier "
                    f"(Bedrock tool and tier item tags); mod tools, copper tools and explosions get nothing, and with "
                    f"Silk Touch any tool drops the block itself (Bedrock ignores minecraft:loot under Silk Touch)")

            if block_path is None or (len(cases) == 1 and _drops_itself(cases[0][1], block_id)):
                result.files[f"loot_tables/blocks/{name}.json"] = cases[0][1]
            elif _has_loot(block):
                # An adapter or station already decided this block's drops.
                result.files[f"loot_tables/blocks/{name}.json"] = cases[0][1]
            else:
                why = _wire_refusal(cases, obtainable)
                if why:
                    result.unhandled.append(Unhandled(rel, "loot", why))
                    continue
                result.files[block_path] = _wire(block, name, cases, result.files)
                wired.append(block_id)
                note = _silk_note(_java_silk_drop(data, block_id))
                if note:
                    approx.append(note)
            if approx:
                approximated.append(block_id)
                result.notes.append(f"{rel}: approximated loot (#299): " + "; ".join(dict.fromkeys(approx)))
    if wired:
        result.notes.append(
            f"{len(wired)} block(s) drop what their Java loot table gives through minecraft:loot (#299; "
            f"another item, a count, a tool test, or a drop decided per block state), e.g. {', '.join(wired[:3])}; "
            "a block whose table drops itself keeps Bedrock's default, which is the same drop")
    if emptied:
        result.notes.append(
            f"{len(emptied)} block(s) drop nothing, as in Java, through Bedrock's vanilla {EMPTY_TABLE} "
            f"(#299), e.g. {', '.join(emptied[:3])}")
    if approximated:
        result.notes.append(
            f"{len(approximated)} block loot table(s) are approximated (#299; each has its own note above): "
            f"e.g. {', '.join(approximated[:3])}")
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
