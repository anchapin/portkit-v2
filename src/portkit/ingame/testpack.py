"""The generated check behavior pack for one converted tree (#238).

Reads the converted behavior pack's blocks and items and writes a small
behavior pack: the fixed check script (``runtime/ingame.js``, its pure core
``runtime/ingame_core.js``) and the one generated file, ``scripts/data.js``,
listing what to check. Nothing here reads the mod jar: the ids are the ones the
converter wrote, so the checks test the pack as shipped.

- ``blocks``: every ``minecraft:block`` identifier.
- ``items``: every ``minecraft:item`` identifier.
- ``containers``: block id -> ``minecraft:block_entity.container.slot_count``
  (the #226 storage blocks, only present under the experiment).
- ``connections``: blocks whose description enables the
  ``minecraft:connection`` trait's ``minecraft:cardinal_connections`` (the #221
  multiparts, palisades and walls).
- ``drops``: blocks whose ``minecraft:loot`` (on the block's own components,
  with no permutation overriding it) names a table this check can read to an
  exact expectation: one pool, one roll, one item entry with a fixed
  ``set_count`` (``set_data`` and ``explosion_decay`` allowed), or Bedrock's
  vanilla ``loot_tables/empty.json`` (drops nothing). Each is
  ``{"id": block, "table": path, "expect": [{"item": id, "count": n}]}``; the
  check breaks the block and counts the item entities it leaves (#299).
- ``tool_drops``: blocks whose wired table gates its drop on Bedrock's
  ``match_tool`` (#299: shears, tool and tier tags). Each is
  ``{"id", "table", "tool": vanilla item id or None (bare hand), "expect"}``
  for the tools that tell the gate apart: shears, the lowest tier of the tool
  the table names and the tier below it, and no tool. The check asks the
  server's ``LootTableManager.generateLootFromBlockPermutation`` (stable since
  @minecraft/server 2.2.0, MicrosoftDocs/minecraft-creator ScriptAPI
  changelog) what the block drops for that tool.
- ``paired``: blocks on Bedrock's ``minecraft:multi_block`` trait (#296:
  doors and two-tall plants). Each is ``{"id", "parts", "expect", "door"}``;
  the check places the block three ways (the lower part alone, the
  ``setblock`` command, every part set by script), reports what each leaves
  above it, breaks the upper part and counts the drop against ``expect``
  (the item list its own table gives, the block itself when it has no
  ``minecraft:loot``, None when neither is exact). For a door (``door`` names
  its ``open`` and ``powered`` states: a block carrying the portkit door
  component) a redstone block is set beside the lower half and removed, and
  both halves are read after each.
"""
from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

RUNTIME = Path(__file__).with_name("runtime")
SCRIPT_FILES = ("ingame.js", "ingame_core.js")
# The Script API version the check script is written against: the stable
# module the converted station runtimes already use (no experiment needed).
# 2.2.0 is the first stable version with world.getLootTableManager() (the tool
# drop check); the server ships 2.x up to 2.10.0 (MicrosoftDocs/minecraft-creator,
# ScriptAPI/minecraft/server changelog).
SERVER_MODULE = "2.2.0"
_NS = uuid.UUID("5f0b8a64-6d1e-4c38-9a7e-1d2b2a6c2380")


@dataclass
class Checks:
    blocks: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)
    containers: dict[str, int] = field(default_factory=dict)
    connections: list[str] = field(default_factory=list)
    drops: list[dict] = field(default_factory=list)
    tool_drops: list[dict] = field(default_factory=list)
    paired: list[dict] = field(default_factory=list)

    def as_json(self) -> dict:
        return {
            "blocks": self.blocks,
            "items": self.items,
            "containers": self.containers,
            "connections": self.connections,
            "drops": self.drops,
            "tool_drops": self.tool_drops,
            "paired": self.paired,
        }


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# Bedrock's vanilla drop-nothing table (Mojang/bedrock-samples@46ba6ea9
# behavior_pack/loot_tables/empty.json): a block may name it without shipping it.
EMPTY_TABLE = "loot_tables/empty.json"
_FIXED = {"set_data", "minecraft:set_data", "explosion_decay", "minecraft:explosion_decay"}


# Vanilla tools the tool drop check holds and the Bedrock item tags each
# carries (learn.microsoft.com, Vanilla Item Tags: Tool tags, Tier tags;
# wiki.bedrock.dev Vanilla Item Tags, "Tags per Item"). Tiers in Java's order
# (golden and copper aren't used by the converter's tier gates).
TIERS = ("wooden", "stone", "iron", "diamond", "netherite")
SHEARS = ("minecraft:shears", frozenset({"minecraft:is_shears"}))


def tool(kind: str, tier: str) -> tuple[str, frozenset]:
    """A vanilla ``<tier>_<kind>`` (pickaxe, axe, shovel, hoe) and its tags."""
    return (f"minecraft:{tier}_{kind}",
            frozenset({"minecraft:is_tool", f"minecraft:is_{kind}", f"minecraft:{tier}_tier"}))


def _holds(condition, held) -> bool | None:
    """Whether a Bedrock loot condition holds for ``held`` ((id, tags) or None
    for no tool); None when this check can't tell."""
    if not isinstance(condition, dict) or condition.get("condition") != "match_tool":
        return None
    if set(condition) - {"condition", "item", "minecraft:match_tool_filter_any",
                         "minecraft:match_tool_filter_all", "minecraft:match_tool_filter_none"}:
        return None
    if held is None:
        return False
    ident, tags = held
    if "item" in condition and condition["item"] != ident:
        return False
    if not set(condition.get("minecraft:match_tool_filter_all") or []) <= tags:
        return False
    any_of = condition.get("minecraft:match_tool_filter_any")
    if any_of is not None and not set(any_of) & tags:
        return False
    return not set(condition.get("minecraft:match_tool_filter_none") or []) & tags


def expected_drops(table, held=None) -> list[dict] | None:
    """What breaking a block with ``table`` leaves, when that is exact: a list of
    {"item", "count"}; None when the table is outside the shapes the converter
    writes (more pools, rolls other than 1, pool conditions, a ranged count, or
    more than one entry that could drop). Entry ``match_tool`` conditions are
    decided for ``held`` ((id, tags), or None for a bare hand)."""
    if not isinstance(table, dict):
        return None
    pools = table.get("pools")
    if pools == []:
        return []
    if not isinstance(pools, list) or len(pools) != 1 or not isinstance(pools[0], dict):
        return None
    pool = pools[0]
    if pool.get("rolls", 1) != 1 or pool.get("conditions") or pool.get("bonus_rolls"):
        return None
    entries = pool.get("entries")
    if not isinstance(entries, list) or not entries or not all(isinstance(e, dict) for e in entries):
        return None
    passing = []
    for entry in entries:
        if entry.get("type") != "item" or not isinstance(entry.get("name"), str):
            return None
        verdicts = [_holds(c, held) for c in entry.get("conditions") or []]
        if None in verdicts:
            return None
        if all(verdicts):
            passing.append(entry)
    if not passing:
        return []
    if len(passing) > 1:
        return None
    entry = passing[0]
    count = 1
    for function in entry.get("functions") or []:
        name = function.get("function") if isinstance(function, dict) else None
        if name in ("set_count", "minecraft:set_count"):
            if not isinstance(function.get("count"), int) or function.get("conditions"):
                return None
            count = function["count"]
        elif name not in _FIXED or function.get("conditions"):
            return None
    return [{"item": entry["name"], "count": count}] if count > 0 else []


def _tools_for(table) -> list:
    """The tools that tell a table's match_tool gates apart, None (a bare hand) first."""
    out: list = [None]
    for pool in (table or {}).get("pools") or []:
        for entry in (pool or {}).get("entries") or []:
            for condition in entry.get("conditions") or []:
                if not isinstance(condition, dict):
                    continue
                any_of = set(condition.get("minecraft:match_tool_filter_any") or [])
                all_of = set(condition.get("minecraft:match_tool_filter_all") or [])
                if "minecraft:is_shears" in any_of and SHEARS not in out:
                    out.append(SHEARS)
                kinds = [t.removeprefix("minecraft:is_") for t in all_of
                         if t.removeprefix("minecraft:is_") in ("pickaxe", "axe", "shovel", "hoe")]
                tiers = [i for i, t in enumerate(TIERS) if f"minecraft:{t}_tier" in any_of]
                for kind in kinds:
                    if not tiers:
                        continue
                    for i in sorted({min(tiers) - 1, min(tiers)}):
                        if i >= 0 and tool(kind, TIERS[i]) not in out:
                            out.append(tool(kind, TIERS[i]))
    return out


def _tool_drop_checks(behavior_pack: Path, ident: str, block: dict) -> list[dict]:
    loot = (block.get("components") or {}).get("minecraft:loot")
    if not isinstance(loot, str) or loot == EMPTY_TABLE:
        return []
    for perm in block.get("permutations") or []:
        if isinstance(perm, dict) and "minecraft:loot" in (perm.get("components") or {}):
            return []
    table = _read_json(behavior_pack / loot)
    if "match_tool" not in json.dumps(table):
        return []
    out = []
    for held in _tools_for(table):
        expect = expected_drops(table, held)
        if expect is not None:
            out.append({"id": ident, "table": loot, "tool": held[0] if held else None, "expect": expect})
    return out


def _drop_check(behavior_pack: Path, ident: str, block: dict) -> dict | None:
    loot = (block.get("components") or {}).get("minecraft:loot")
    if not isinstance(loot, str):
        return None
    for perm in block.get("permutations") or []:
        if isinstance(perm, dict) and "minecraft:loot" in (perm.get("components") or {}):
            return None  # the drop depends on the state it's placed in
    if loot == EMPTY_TABLE and not (behavior_pack / loot).is_file():
        expect = []
    else:
        expect = expected_drops(_read_json(behavior_pack / loot))
    if expect is None:
        return None
    return {"id": ident, "table": loot, "expect": expect}


DOOR_COMPONENT = ":portkit_door"


def _paired_check(behavior_pack: Path, ident: str, block: dict) -> dict | None:
    desc = block.get("description") or {}
    trait = (desc.get("traits") or {}).get("minecraft:multi_block")
    if not isinstance(trait, dict) or trait.get("direction", "up") != "up":
        return None
    parts = trait.get("parts")
    if not isinstance(parts, int) or parts < 2:
        return None
    components = block.get("components") or {}
    door = None
    if any(isinstance(k, str) and k.endswith(DOOR_COMPONENT) for k in components):
        states = [s for s in (desc.get("states") or {}) if isinstance(s, str)]
        opened = [s for s in states if s.endswith(":open")]
        powered = [s for s in states if s.endswith(":powered")]
        if len(opened) == 1 and len(powered) == 1:
            door = {"open": opened[0], "powered": powered[0]}
    per_state = any(isinstance(p, dict) and "minecraft:loot" in (p.get("components") or {})
                    for p in block.get("permutations") or [])
    if "minecraft:loot" not in components and not per_state:
        # No minecraft:loot: a custom block drops itself (learn.microsoft.com minecraft:loot).
        expect = [{"item": ident, "count": 1}]
    else:
        drop = _drop_check(behavior_pack, ident, block)
        expect = drop["expect"] if drop else None
    return {"id": ident, "parts": parts, "expect": expect, "door": door}


def read_checks(behavior_pack: Path) -> Checks:
    """What to check in a converted behavior pack, in a stable (sorted) order."""
    checks = Checks()
    for path in sorted((behavior_pack / "blocks").rglob("*.json")):
        doc = _read_json(path)
        block = (doc or {}).get("minecraft:block") if isinstance(doc, dict) else None
        if not isinstance(block, dict):
            continue
        desc = block.get("description") or {}
        ident = desc.get("identifier")
        if not isinstance(ident, str):
            continue
        checks.blocks.append(ident)
        trait = (desc.get("traits") or {}).get("minecraft:connection") or {}
        if "minecraft:cardinal_connections" in (trait.get("enabled_states") or []):
            checks.connections.append(ident)
        entity = (block.get("components") or {}).get("minecraft:block_entity") or {}
        slots = (entity.get("container") or {}).get("slot_count") if isinstance(entity, dict) else None
        if isinstance(slots, int):
            checks.containers[ident] = slots
        drop = _drop_check(behavior_pack, ident, block)
        if drop is not None:
            checks.drops.append(drop)
        checks.tool_drops += _tool_drop_checks(behavior_pack, ident, block)
        paired = _paired_check(behavior_pack, ident, block)
        if paired is not None:
            checks.paired.append(paired)
    for path in sorted((behavior_pack / "items").rglob("*.json")):
        doc = _read_json(path)
        item = (doc or {}).get("minecraft:item") if isinstance(doc, dict) else None
        if isinstance(item, dict):
            ident = (item.get("description") or {}).get("identifier")
            if isinstance(ident, str):
                checks.items.append(ident)
    checks.blocks.sort()
    checks.items.sort()
    checks.connections.sort()
    checks.drops.sort(key=lambda d: d["id"])
    checks.tool_drops.sort(key=lambda d: (d["id"], d["tool"] or ""))
    checks.paired.sort(key=lambda d: d["id"])
    return checks


def manifest(name: str) -> dict:
    """The check pack's manifest: uuids derived from its name, so reruns match."""
    def uid(part: str) -> str:
        return str(uuid.uuid5(_NS, f"{name}/{part}"))

    return {
        "format_version": 2,
        "header": {
            "name": f"portkit in-game checks ({name})",
            "description": "Generated by portkit (#238). Test-only; not part of the conversion.",
            "uuid": uid("header"),
            "version": [1, 0, 0],
            "min_engine_version": [1, 21, 80],
        },
        "modules": [
            {
                "type": "script",
                "language": "javascript",
                "uuid": uid("script"),
                "version": [1, 0, 0],
                "entry": "scripts/ingame.js",
            }
        ],
        "dependencies": [{"module_name": "@minecraft/server", "version": SERVER_MODULE}],
    }


def write_test_pack(behavior_pack: Path, out: Path, name: str) -> Checks:
    """Write the check pack for ``behavior_pack`` into ``out``; return its checks."""
    checks = read_checks(behavior_pack)
    if out.exists():
        shutil.rmtree(out)
    scripts = out / "scripts"
    scripts.mkdir(parents=True)
    (out / "manifest.json").write_text(json.dumps(manifest(name), indent=2) + "\n")
    for file in SCRIPT_FILES:
        shutil.copyfile(RUNTIME / file, scripts / file)
    (scripts / "data.js").write_text(
        "// Generated by portkit.ingame.testpack (#238): what the checks cover.\n"
        f"export const CHECKS = {json.dumps(checks.as_json(), indent=1, sort_keys=True)};\n"
    )
    return checks
