"""Loot a mod adds to vanilla tables through NeoForge loot modifiers (#280).

Java mods add to vanilla loot without replacing vanilla's tables. NeoForge's
data-driven way (1.21.1, read from NeoForge's own source,
github.com/neoforged/NeoForge branch 1.21.1):

- ``LootModifierManager#prepare`` reads every
  ``data/neoforge/loot_modifiers/global_loot_modifiers.json`` (``"replace"``
  clears the list gathered so far; ``"entries"`` appends modifier ids) and
  loads **only the modifiers that list names**, from
  ``data/<ns>/loot_modifiers/<path>.json``. A modifier file nobody lists is
  never loaded.
- ``neoforge:add_table`` (``AddTableLootModifier``: ``conditions``, ``table``)
  rolls ``table`` with the loot context of the table being generated
  (``getRandomItemsRaw``) and adds what it gives to that table's drops, when
  every condition holds. ``neoforge:loot_table_id`` (``loot_table_id``) holds
  when the table being generated is that id.
- The added table is an ordinary loot table: its own load conditions
  (``neoforge:conditions``) decide whether it exists at all; a table that
  isn't loaded adds nothing.

Bedrock has no loot-table injection. The one target this module carries is a
vanilla **block** table (``minecraft:blocks/<name>``): Bedrock fires
``world.afterEvents.playerBreakBlock`` for vanilla blocks, so the fixed
runtime ``portkit/runtime/block_drops.js`` adds the converted drop when a
player breaks that block (never replacing or shipping a vanilla table). What
converts is the shape :mod:`block_drops_core.js` rolls; anything else is
residue naming what defeated it. Explosions and other non-player breaks add
nothing on Bedrock: fewer drops than Java, never more, and said in a note.

Every other target (a chest, gameplay or entity table) would need Bedrock's
own vanilla table overridden with the injected pool added, which is a
separate decision; those modifiers and their tables stay residue saying so.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..conditions import LoadContext
from ..model import ConversionResult, SourceMod, Unhandled
from ..data import vanilla_items
from .station_kit import js_module, runtime_source

GLOBAL = "data/neoforge/loot_modifiers/global_loot_modifiers.json"
ADD_TABLE = ("neoforge:add_table",)
TABLE_ID = ("neoforge:loot_table_id",)
RUNTIME = "scripts/portkit/block_drops.js"
CORE = "scripts/portkit/block_drops_core.js"
_TABLE_DIRS = ("loot_table", "loot_tables")


def table_path(namespace: str) -> str:
    return f"scripts/portkit/data/{namespace}_block_drops.js"


def _rid(value) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value if ":" in value else f"minecraft:{value}"


def listed(root: Path) -> tuple[list[str], str | None]:
    """The modifier ids NeoForge loads from this jar, in order, or why the
    list can't be read. Only this jar's own list is seen: another mod's list
    can't remove these (``replace`` clears only what came before it)."""
    path = root / GLOBAL
    if not path.is_file():
        return [], None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return [], f"{GLOBAL} is not valid JSON: {exc}"
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not all(isinstance(e, str) for e in entries):
        return [], f"{GLOBAL} has no readable entries list"
    return [_rid(e) for e in entries], None


def _int(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and float(value).is_integer():
        return int(value)
    return None


def _number(provider) -> tuple[int, int] | None:
    """A count provider as (min, max) integers: a constant or ``minecraft:uniform``
    with integer constant bounds."""
    n = _int(provider)
    if n is not None:
        return n, n
    if not isinstance(provider, dict):
        return None
    kind = provider.get("type")
    if kind in (None, "minecraft:constant", "constant"):
        n = _int(provider.get("value"))
        return (n, n) if n is not None else None
    if kind in ("minecraft:uniform", "uniform"):
        lo, hi = _number(provider.get("min")), _number(provider.get("max"))
        if lo and hi and lo[0] == lo[1] and hi[0] == hi[1]:
            return lo[0], hi[0]
    return None


def _silk_touch_absent(condition) -> bool:
    """``inverted(match_tool: the tool has silk_touch at level >= 1)``, either
    1.21 predicate form (``predicates.minecraft:enchantments``) or 1.20's."""
    if not isinstance(condition, dict) or condition.get("condition") not in ("minecraft:inverted", "inverted"):
        return False
    term = condition.get("term")
    if not isinstance(term, dict) or term.get("condition") not in ("minecraft:match_tool", "match_tool"):
        return False
    predicate = term.get("predicate")
    if not isinstance(predicate, dict):
        return False
    inner = predicate.get("predicates") if "predicates" in predicate else predicate
    if not isinstance(inner, dict) or set(predicate) - {"predicates", "enchantments"}:
        return False
    enchants = inner.get("minecraft:enchantments", inner.get("enchantments"))
    if set(inner) - {"minecraft:enchantments", "enchantments"} or not isinstance(enchants, list) or len(enchants) != 1:
        return False
    e = enchants[0]
    if not isinstance(e, dict):
        return False
    which = e.get("enchantments", e.get("enchantment"))
    levels = e.get("levels")
    if which not in ("minecraft:silk_touch", "silk_touch") or set(e) - {"enchantments", "enchantment", "levels"}:
        return False
    return isinstance(levels, dict) and _int(levels.get("min")) == 1 and set(levels) == {"min"}


_EXPLOSION_ONLY = ("minecraft:explosion_decay", "explosion_decay")
_SURVIVES = ("minecraft:survives_explosion", "survives_explosion")


def _steps(functions, steps: list[dict]) -> str | None:
    for f in functions or []:
        if not isinstance(f, dict):
            return "a function that isn't an object"
        name = f.get("function")
        if f.get("conditions"):
            return f"function {name} has its own conditions"
        if name in _EXPLOSION_ONLY:
            continue  # acts only when an explosion broke the block
        if name in ("minecraft:set_count", "set_count"):
            if f.get("add"):
                return "set_count with add: true"
            got = _number(f.get("count"))
            if got is None:
                return f"set_count count {json.dumps(f.get('count'))} isn't a constant or an integer uniform range"
            steps.append({"op": "set", "min": got[0], "max": got[1]})
        elif name in ("minecraft:apply_bonus", "apply_bonus"):
            params = f.get("parameters") or {}
            mult = _int(params.get("bonusMultiplier")) if isinstance(params, dict) else None
            if f.get("enchantment") not in ("minecraft:fortune", "fortune") \
                    or f.get("formula") not in ("minecraft:uniform_bonus_count", "uniform_bonus_count") \
                    or mult is None or set(params) != {"bonusMultiplier"}:
                return f"apply_bonus {f.get('enchantment')} {f.get('formula')} isn't Fortune's uniform_bonus_count"
            steps.append({"op": "fortune_uniform", "multiplier": mult})
        elif name in ("minecraft:limit_count", "limit_count"):
            limit = f.get("limit")
            if not isinstance(limit, dict) or set(limit) - {"min", "max"}:
                return f"limit_count limit {json.dumps(limit)} isn't an integer range"
            lo = _int(limit["min"]) if "min" in limit else None
            hi = _int(limit["max"]) if "max" in limit else None
            if ("min" in limit and lo is None) or ("max" in limit and hi is None):
                return f"limit_count limit {json.dumps(limit)} isn't an integer range"
            steps.append({"op": "limit", "min": lo, "max": hi})
        else:
            return f"function {name} isn't carried by the block drop runtime"
    return None


def rows(table: dict) -> tuple[list[dict] | None, str]:
    """The block drop runtime's rows for an added table, or why it can't be one."""
    if table.get("type") not in (None, "minecraft:block", "block"):
        return None, f"the added table is a {table.get('type')} table, not a block table"
    if table.get("functions"):
        return None, "the added table has table-level functions"
    pools = table.get("pools")
    if not isinstance(pools, list) or not pools:
        return None, "the added table has no pools"
    out: list[dict] = []
    for pool in pools:
        if not isinstance(pool, dict):
            return None, "a pool that isn't an object"
        if _int(pool.get("rolls")) != 1 or _int(pool.get("bonus_rolls", 0)) != 0:
            return None, f"a pool rolls {json.dumps(pool.get('rolls'))} times (only one roll is carried)"
        if any(c.get("condition") not in _SURVIVES for c in pool.get("conditions") or [] if isinstance(c, dict)):
            return None, "a pool has conditions other than survives_explosion"
        entries = pool.get("entries")
        if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
            return None, "a pool has more than one entry (weighted choice isn't carried)"
        entry = entries[0]
        if entry.get("type") not in ("minecraft:item", "item"):
            return None, f"a pool's entry is a {entry.get('type')} entry, not an item"
        item = _rid(entry.get("name"))
        if item is None:
            return None, "a pool's item entry names no item"
        no_silk = False
        for c in entry.get("conditions") or []:
            if isinstance(c, dict) and c.get("condition") in _SURVIVES:
                continue
            if _silk_touch_absent(c):
                no_silk = True
                continue
            return None, f"the entry for {item} has a condition {json.dumps(c)[:120]} that isn't carried"
        steps: list[dict] = []
        why = _steps(entry.get("functions"), steps) or _steps(pool.get("functions"), steps)
        if why:
            return None, f"the entry for {item}: {why}"
        out.append({"item": item, "no_silk_touch": no_silk, "steps": steps})
    return out, ""


def _shipped_items(files: dict) -> set[str]:
    out = set()
    for body in files.values():
        if isinstance(body, dict):
            for key in ("minecraft:item", "minecraft:block"):
                ident = ((body.get(key) or {}).get("description") or {}).get("identifier") \
                    if isinstance(body.get(key), dict) else None
                if isinstance(ident, str):
                    out.add(ident)
    return out


def _bedrock_vanilla(java_id: str) -> tuple[str | None, str]:
    """The Bedrock id of a vanilla block a Java id names, read from GeyserMC's
    item mapping and checked against Bedrock's vanilla item list (a placeable
    block's item shares its block's id on Bedrock)."""
    from .recipes import bedrock_item

    got = bedrock_item(java_id)
    if isinstance(got, str):
        return None, got
    ident, data = got
    if data is not None:
        return None, f"Java {java_id} is Bedrock {ident} with data {data}, a block the runtime can't tell apart"
    vanilla = vanilla_items.ids()
    if vanilla is None:
        return None, "Bedrock's vanilla item list isn't cached (run `portkit reference fetch`)"
    if ident not in vanilla:
        return None, f"Java {java_id} has no Bedrock vanilla block of that id"
    return ident, ""


def convert(mod: SourceMod, context: LoadContext | None = None, files: dict | None = None) -> ConversionResult:
    """The namespace's loot modifiers and the tables they add (see the module doc)."""
    result = ConversionResult()
    src = mod.data / "loot_modifiers"
    if not src.is_dir():
        return result
    context = context or LoadContext(mod)
    loaded, problem = listed(mod.root)
    if (mod.root / GLOBAL).is_file():
        result.consumed.add(GLOBAL)
    shipped = _shipped_items(files or {})
    by_block: dict[str, list[dict]] = {}
    carried: list[str] = []
    for path in sorted(src.rglob("*.json")):
        rel = result.claim(mod, path)
        mid = f"{mod.namespace}:{path.relative_to(src).with_suffix('').as_posix()}"
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            result.unhandled.append(Unhandled(rel, "loot", f"loot modifier {mid}: invalid JSON: {exc}"))
            continue
        target_table = _rid(data.get("table")) if isinstance(data, dict) else None
        table_rel = None
        table_data = None
        if target_table and target_table.startswith(f"{mod.namespace}:"):
            for d in _TABLE_DIRS:
                cand = mod.data / d / f"{target_table.split(':', 1)[1]}.json"
                if cand.is_file():
                    table_rel = result.claim(mod, cand)
                    try:
                        table_data = json.loads(cand.read_text())
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        table_data = None
                    break

        def refuse(reason: str, kind: str = "loot") -> None:
            result.unhandled.append(Unhandled(rel, kind, f"loot modifier {mid}: {reason}"))
            if table_rel:
                result.unhandled.append(Unhandled(table_rel, kind, (
                    f"the table loot modifier {mid} adds ({target_table}): {reason}")))

        if problem:
            refuse(problem)
            continue
        if mid not in loaded:
            refuse("NeoForge never loads it: it isn't listed in the jar's " + GLOBAL
                   + " (LootModifierManager#prepare loads only listed modifiers), so in Java it adds nothing")
            continue
        if not isinstance(data, dict) or data.get("type") not in ADD_TABLE:
            refuse(f"modifier type {data.get('type') if isinstance(data, dict) else None} isn't carried "
                   "(only neoforge:add_table is)")
            continue
        verdict = context.gate(data, "loot")
        if verdict.passes is not True:
            refuse(verdict.reason(), "conditional_loot_table")
            continue
        conds = data.get("conditions")
        targets = [c.get("loot_table_id") for c in conds or [] if isinstance(c, dict)
                   and c.get("condition") in TABLE_ID]
        if not isinstance(conds, list) or len(conds) != 1 or len(targets) != 1:
            refuse("its conditions aren't exactly one neoforge:loot_table_id (only an addition to one named "
                   "table is carried)")
            continue
        target = _rid(targets[0])
        if table_data is None:
            refuse(f"the table it adds ({target_table}) isn't in this jar or isn't valid JSON")
            continue
        if not isinstance(table_data, dict):
            refuse("the table it adds isn't a JSON object")
            continue
        tverdict = context.gate(table_data, "loot")
        if tverdict.passes is not True:
            refuse(f"the table it adds isn't loaded: {tverdict.reason()}", "conditional_loot_table")
            continue
        if not target or not target.startswith("minecraft:blocks/"):
            refuse(f"it adds to {target}, a vanilla table that isn't a block's; Bedrock has no loot "
                   "injection, and carrying it would mean overriding Bedrock's own vanilla table with the "
                   "added pool, which portkit doesn't do (#280)")
            continue
        block_java = "minecraft:" + target.split("/", 1)[1]
        block, why = _bedrock_vanilla(block_java)
        if block is None:
            refuse(f"it adds to {target}: {why}")
            continue
        got, why = rows(table_data)
        if got is None:
            refuse(f"it adds to {target}: {why}")
            continue
        missing = [r["item"] for r in got if not r["item"].startswith("minecraft:") and r["item"] not in shipped]
        missing += [r["item"] for r in got if r["item"].startswith("minecraft:")
                    and _bedrock_vanilla(r["item"])[0] != r["item"]]
        if missing:
            refuse(f"it adds {', '.join(sorted(set(missing)))}, which the pack doesn't ship under that id")
            continue
        by_block.setdefault(block, []).extend(got)
        carried.append(f"{mid} -> {block}")
        for r in got:
            result.notes.append(_note(table_rel or rel, mid, block, r))
    if by_block:
        header = ("// Read by the fixed runtime scripts/portkit/block_drops.js (portkit/runtime): per Bedrock vanilla "
                  "block, the drops this mod's NeoForge loot modifiers add to it in Java (see the notes).")
        result.files[table_path(mod.namespace)] = js_module(header, {"blocks": by_block})
        result.files[RUNTIME] = runtime_source("block_drops.js")
        result.files[CORE] = runtime_source("block_drops_core.js")
        result.notes.append(
            f"{len(carried)} loot modifier(s) add a drop to a vanilla block (#280), carried by the block drop "
            "runtime on a player's break, e.g. " + ", ".join(carried[:3]))
    return result


def _note(source: str, mid: str, block: str, row: dict) -> str:
    parts = []
    for s in row["steps"]:
        if s["op"] == "set":
            parts.append(f"{s['min']}" if s["min"] == s["max"] else f"{s['min']}-{s['max']}")
        elif s["op"] == "fortune_uniform":
            parts.append(f"+0..{s['multiplier']}x Fortune level")
        elif s["op"] == "limit":
            parts.append(f"clamped to {s['min'] if s['min'] is not None else ''}..{s['max'] if s['max'] is not None else ''}")
    how = ", ".join(parts) or "1"
    silk = "; none with Silk Touch" if row["no_silk_touch"] else ""
    return (f"{source}: approximated loot (#280): loot modifier {mid} adds {row['item']} ({how}{silk}) when a "
            f"player breaks vanilla {block} (Bedrock playerBreakBlock, not in Creative or with doTileDrops off); "
            "Java also adds it when an explosion or another entity breaks the block, Bedrock adds nothing then, "
            "so never more than Java")
