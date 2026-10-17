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
SERVER_MODULE = "2.0.0"
_NS = uuid.UUID("5f0b8a64-6d1e-4c38-9a7e-1d2b2a6c2380")


@dataclass
class Checks:
    blocks: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)
    containers: dict[str, int] = field(default_factory=dict)
    connections: list[str] = field(default_factory=list)
    drops: list[dict] = field(default_factory=list)

    def as_json(self) -> dict:
        return {
            "blocks": self.blocks,
            "items": self.items,
            "containers": self.containers,
            "connections": self.connections,
            "drops": self.drops,
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


def expected_drops(table) -> list[dict] | None:
    """What breaking a block with ``table`` leaves, when that is exact: a list of
    {"item", "count"}; None when the table is outside the shapes the converter
    writes (more pools or entries, rolls other than 1, conditions, a ranged count)."""
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
    if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
        return None
    entry = entries[0]
    if entry.get("type") != "item" or not isinstance(entry.get("name"), str) or entry.get("conditions"):
        return None
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
