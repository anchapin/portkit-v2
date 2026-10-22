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
- ``trapdoors``: blocks carrying the portkit trapdoor component (#296). Each
  is ``{"id", "states", "expect"}`` (``states`` names its ``open`` and
  ``powered`` states; ``expect`` as for ``paired``); the check places it, sets
  a redstone block beside it and removes it, reading both states after each,
  then breaks it and counts the drop.
- ``plates``: blocks carrying the portkit pressure plate component (#296).
  Each is ``{"id", "powered", "mobs_only", "expect"}`` (``powered`` names its
  state; ``mobs_only`` from the pack's plate table); the check places it on a
  stone block beside a redstone lamp, spawns an armor stand on it (pressed,
  lamp lit) and removes it (released after the re-check, lamp unlit), drops a
  stick on it (pressed unless mobs only), then breaks it and counts the drop.
- ``buttons``: blocks carrying the portkit button component (#280). Each is
  ``{"id", "powered", "ticks", "arrows", "event", "expect"}`` (``ticks``,
  ``arrows`` and the press scriptevent from the pack's button table); the
  check places it on the floor (on a stone block) beside a redstone lamp,
  presses it with the runtime's scriptevent (powered, lamp lit), reads it
  again a few ticks before its press time is up (still pressed) and after
  (released, lamp unlit), then breaks it and counts the drop. Reported, not
  asserted: what an arrow fired at it does.
- ``gates``: blocks carrying the portkit fence gate component (#367). Each is
  ``{"id", "states", "event", "wall", "expect"}`` (``states`` names its ``open``,
  ``in_wall`` and ``powered`` states; ``event`` the use scriptevent and ``wall`` a
  wall id from the pack's gate table); the check places it (closed, not in a wall),
  uses it with the scriptevent as a player facing the gate (it turns to face away
  and opens) and again (closed), sets a redstone block beside it and removes it
  (open and powered, then closed), breaks it and counts the drop, then places it
  again between a wall and air (in_wall).
- ``ores``: feature rules whose feature is a ``minecraft:ore_feature`` of the
  pack (#281). Each is ``{"rule", "feature", "blocks", "replaces",
  "dimension", "y"}``. Outside the Overworld (the check world is flat) the
  check loads fresh chunks of the rule's dimension and counts the ore blocks
  the world generated in the rule's height range (asserted, at least one,
  when the scanned range holds any block the ore may replace (``hosts``);
  with none there the row is reported as skipped). In a ``world="default"``
  run (a generated Overworld, ore checks only) the Overworld is scanned too.
  It also places the feature into a cube of the first block it may replace
  with ``Dimension.placeFeature`` (stable since @minecraft/server 1.19.0,
  MicrosoftDocs/minecraft-creator ScriptAPI changelog) and reports what that
  left, without asserting it.
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
    trapdoors: list[dict] = field(default_factory=list)
    plates: list[dict] = field(default_factory=list)
    buttons: list[dict] = field(default_factory=list)
    gates: list[dict] = field(default_factory=list)
    ores: list[dict] = field(default_factory=list)
    geodes: list[dict] = field(default_factory=list)
    # "flat" (the default check world) or "default": a generated Overworld,
    # where only the ore checks run and the Overworld's ores are generated too.
    world: str = "flat"

    def as_json(self) -> dict:
        extra = {"world": self.world} if self.world != "flat" else {}
        return {**extra,
            "blocks": self.blocks,
            "items": self.items,
            "containers": self.containers,
            "connections": self.connections,
            "drops": self.drops,
            "tool_drops": self.tool_drops,
            "paired": self.paired,
            "trapdoors": self.trapdoors,
            "plates": self.plates,
            "buttons": self.buttons,
            "gates": self.gates,
            "ores": self.ores,
            "geodes": self.geodes,
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


TRAPDOOR_COMPONENT = ":portkit_trapdoor"


def _block_expect(behavior_pack: Path, ident: str, block: dict) -> list[dict] | None:
    components = block.get("components") or {}
    per_state = any(isinstance(p, dict) and "minecraft:loot" in (p.get("components") or {})
                    for p in block.get("permutations") or [])
    if "minecraft:loot" not in components and not per_state:
        # No minecraft:loot: a custom block drops itself (learn.microsoft.com minecraft:loot).
        return [{"item": ident, "count": 1}]
    drop = _drop_check(behavior_pack, ident, block)
    return drop["expect"] if drop else None


def _trapdoor_check(behavior_pack: Path, ident: str, block: dict) -> dict | None:
    components = block.get("components") or {}
    if not any(isinstance(k, str) and k.endswith(TRAPDOOR_COMPONENT) for k in components):
        return None
    states = [s for s in ((block.get("description") or {}).get("states") or {}) if isinstance(s, str)]
    opened = [s for s in states if s.endswith(":open")]
    powered = [s for s in states if s.endswith(":powered")]
    if len(opened) != 1 or len(powered) != 1:
        return None
    return {"id": ident, "states": {"open": opened[0], "powered": powered[0]},
            "expect": _block_expect(behavior_pack, ident, block)}


# A rule's biome tag -> the dimension it generates in (portkit.data.worldgen.BIOME_TAGS).
_DIMENSION_TAGS = {"nether": "nether", "the_end": "the_end"}


PLATE_COMPONENT = ":portkit_pressure_plate"


def _plate_tables(behavior_pack: Path) -> dict[str, dict]:
    """Every plate entry of the pack's pressure plate tables, by block id."""
    out: dict[str, dict] = {}
    for path in sorted((behavior_pack / "scripts" / "portkit" / "data").glob("*_pressure_plates.js")):
        text = path.read_text(encoding="utf-8")
        _, sep, body = text.partition("export default ")
        if not sep:
            continue
        try:
            table = json.loads(body.strip().rstrip(";"))
        except ValueError:
            continue
        out.update(table.get("plates") or {})
    return out


def _plate_check(behavior_pack: Path, ident: str, block: dict, tables: dict) -> dict | None:
    components = block.get("components") or {}
    if not any(isinstance(k, str) and k.endswith(PLATE_COMPONENT) for k in components):
        return None
    states = [s for s in ((block.get("description") or {}).get("states") or {}) if isinstance(s, str)]
    powered = [s for s in states if s.endswith(":powered")]
    if len(powered) != 1 or ident not in tables:
        return None
    return {"id": ident, "powered": powered[0], "mobs_only": bool(tables[ident].get("mobs_only")),
            "expect": _block_expect(behavior_pack, ident, block)}


BUTTON_COMPONENT = ":portkit_button"


def _button_tables(behavior_pack: Path) -> dict[str, dict]:
    """Every button entry of the pack's button tables, by block id, each with
    its table's press scriptevent."""
    out: dict[str, dict] = {}
    for path in sorted((behavior_pack / "scripts" / "portkit" / "data").glob("*_buttons.js")):
        _, sep, body = path.read_text(encoding="utf-8").partition("export default ")
        if not sep:
            continue
        try:
            table = json.loads(body.strip().rstrip(";"))
        except ValueError:
            continue
        for ident, row in (table.get("buttons") or {}).items():
            out[ident] = {**row, "event": table.get("press_event")}
    return out


def _button_check(behavior_pack: Path, ident: str, block: dict, tables: dict) -> dict | None:
    components = block.get("components") or {}
    if not any(isinstance(k, str) and k.endswith(BUTTON_COMPONENT) for k in components):
        return None
    states = [s for s in ((block.get("description") or {}).get("states") or {}) if isinstance(s, str)]
    powered = [s for s in states if s.endswith(":powered")]
    row = tables.get(ident)
    if len(powered) != 1 or row is None or not isinstance(row.get("ticks"), int) or not row.get("event"):
        return None
    return {"id": ident, "powered": powered[0], "ticks": row["ticks"], "arrows": bool(row.get("arrows")),
            "event": row["event"], "expect": _block_expect(behavior_pack, ident, block)}


GATE_COMPONENT = ":portkit_fence_gate"


def _gate_tables(behavior_pack: Path) -> dict[str, dict]:
    """Every gate of the pack's fence gate tables, by block id, each with its table's use
    scriptevent and the wall the check uses (cobblestone wall when the table lists it)."""
    out: dict[str, dict] = {}
    for path in sorted((behavior_pack / "scripts" / "portkit" / "data").glob("*_fence_gates.js")):
        _, sep, body = path.read_text(encoding="utf-8").partition("export default ")
        if not sep:
            continue
        try:
            table = json.loads(body.strip().rstrip(";"))
        except ValueError:
            continue
        walls = [w for w in table.get("walls") or [] if isinstance(w, str)]
        wall = "minecraft:cobblestone_wall" if "minecraft:cobblestone_wall" in walls else (walls[0] if walls else None)
        for ident in table.get("gates") or {}:
            out[ident] = {"event": table.get("event"), "wall": wall}
    return out


def _gate_check(behavior_pack: Path, ident: str, block: dict, tables: dict) -> dict | None:
    components = block.get("components") or {}
    if not any(isinstance(k, str) and k.endswith(GATE_COMPONENT) for k in components):
        return None
    states = [s for s in ((block.get("description") or {}).get("states") or {}) if isinstance(s, str)]
    named = {k: [s for s in states if s.endswith(f":{k}")] for k in ("open", "in_wall", "powered")}
    row = tables.get(ident)
    if any(len(v) != 1 for v in named.values()) or row is None or not row.get("event") or not row.get("wall"):
        return None
    return {"id": ident, "states": {k: v[0] for k, v in named.items()}, "event": row["event"],
            "wall": row["wall"], "expect": _block_expect(behavior_pack, ident, block)}


def _tags(value) -> set[str]:
    if isinstance(value, dict):
        out = {value["value"]} if value.get("test") == "has_biome_tag" and isinstance(value.get("value"), str) else set()
        for v in value.values():
            out |= _tags(v)
        return out
    if isinstance(value, list):
        return set().union(*(_tags(v) for v in value)) if value else set()
    return set()


def _ore_checks(behavior_pack: Path) -> list[dict]:
    ores: dict[str, dict] = {}
    for path in sorted((behavior_pack / "features").glob("*.json")):
        body = (_read_json(path) or {}).get("minecraft:ore_feature")
        if not isinstance(body, dict):
            continue
        ident = (body.get("description") or {}).get("identifier")
        rules = [r for r in body.get("replace_rules") or [] if isinstance(r, dict)]
        blocks = [r.get("places_block") for r in rules]
        replaces = [(r.get("may_replace") or [None])[0] for r in rules]
        hosts = sorted({h for r in rules for h in r.get("may_replace") or [] if isinstance(h, str)})
        if isinstance(ident, str) and blocks and all(isinstance(b, str) for b in blocks + replaces):
            ores[ident] = {"blocks": blocks, "replaces": replaces, "hosts": hosts}
    out = []
    for path in sorted((behavior_pack / "feature_rules").glob("*.json")):
        rule = (_read_json(path) or {}).get("minecraft:feature_rules")
        if not isinstance(rule, dict):
            continue
        desc = rule.get("description") or {}
        ore = ores.get(desc.get("places_feature"))
        y = (rule.get("distribution") or {}).get("y")
        span = y.get("extent") if isinstance(y, dict) else [y, y] if isinstance(y, int) else None
        if ore is None or not isinstance(desc.get("identifier"), str) or not isinstance(span, list):
            continue
        tags = _tags((rule.get("conditions") or {}).get("minecraft:biome_filter"))
        dims = {_DIMENSION_TAGS.get(t, "overworld") for t in tags} or {"overworld"}
        out.append({"rule": desc["identifier"], "feature": desc["places_feature"], **ore,
                    "dimension": dims.pop() if len(dims) == 1 else None, "y": span})
    return out


_GEODE_LAYERS = ("inner_layer", "alternate_inner_layer")
CHECK_NAMESPACE = "portkit_check"


def _geode_checks(behavior_pack: Path) -> list[dict]:
    """One row per feature rule placing a ``minecraft:geode_feature`` of the
    pack (#281 slice 3): ``blocks`` its inner and alternate inner layer (the
    blocks only a geode lays), ``buds`` its inner placements, ``y`` the rule's
    height range widened by the geode's ``max_radius``, and ``check_rule`` the
    test-only rule :func:`geode_rule_files` writes: the same rule placing the
    same feature in every chunk (no ``scatter_chance``), so a few fresh chunks
    are enough to see the world generate it."""
    geodes: dict[str, dict] = {}
    for path in sorted((behavior_pack / "features").glob("*.json")):
        body = (_read_json(path) or {}).get("minecraft:geode_feature")
        if not isinstance(body, dict):
            continue
        ident = (body.get("description") or {}).get("identifier")
        blocks = [body.get(k) for k in _GEODE_LAYERS]
        buds = [b.get("name") if isinstance(b, dict) else b for b in body.get("inner_placements") or []]
        radius = body.get("max_radius")
        if isinstance(ident, str) and all(isinstance(b, str) for b in blocks + buds) and isinstance(radius, int):
            geodes[ident] = {"blocks": list(dict.fromkeys(blocks)), "buds": list(dict.fromkeys(buds)),
                             "radius": radius}
    out = []
    for path in sorted((behavior_pack / "feature_rules").glob("*.json")):
        rule = (_read_json(path) or {}).get("minecraft:feature_rules")
        if not isinstance(rule, dict):
            continue
        desc = rule.get("description") or {}
        geode = geodes.get(desc.get("places_feature"))
        y = (rule.get("distribution") or {}).get("y")
        span = y.get("extent") if isinstance(y, dict) else [y, y] if isinstance(y, int) else None
        if geode is None or not isinstance(desc.get("identifier"), str) or not isinstance(span, list):
            continue
        tags = _tags((rule.get("conditions") or {}).get("minecraft:biome_filter"))
        dims = {_DIMENSION_TAGS.get(t, "overworld") for t in tags} or {"overworld"}
        r = geode["radius"]
        out.append({"rule": desc["identifier"], "feature": desc["places_feature"],
                    "blocks": geode["blocks"], "buds": geode["buds"],
                    "dimension": dims.pop() if len(dims) == 1 else None,
                    "y": [min(span) - r, max(span) + r],
                    "check_rule": f"{CHECK_NAMESPACE}:{path.stem}"})
    return out


def geode_rule_files(behavior_pack: Path, geodes: list[dict]) -> dict[str, dict]:
    """The check pack's test-only feature rules (#281 slice 3): each geode
    rule of the pack copied under ``portkit_check:``, its ``scatter_chance``
    dropped, so its feature is placed once in every chunk. Test-only: never
    part of the conversion."""
    out = {}
    for row in geodes:
        name = row["check_rule"].split(":", 1)[1]
        rule = (_read_json(behavior_pack / "feature_rules" / f"{name}.json") or {}).get("minecraft:feature_rules")
        if not isinstance(rule, dict):
            continue
        rule = json.loads(json.dumps(rule))
        rule["description"]["identifier"] = row["check_rule"]
        (rule.get("distribution") or {}).pop("scatter_chance", None)
        out[f"feature_rules/{name}.json"] = {"format_version": "1.13.0", "minecraft:feature_rules": rule}
    return out


def read_checks(behavior_pack: Path) -> Checks:
    """What to check in a converted behavior pack, in a stable (sorted) order."""
    checks = Checks()
    plate_tables = _plate_tables(behavior_pack)
    button_tables = _button_tables(behavior_pack)
    gate_tables = _gate_tables(behavior_pack)
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
        trapdoor = _trapdoor_check(behavior_pack, ident, block)
        if trapdoor is not None:
            checks.trapdoors.append(trapdoor)
        plate = _plate_check(behavior_pack, ident, block, plate_tables)
        if plate is not None:
            checks.plates.append(plate)
        button = _button_check(behavior_pack, ident, block, button_tables)
        if button is not None:
            checks.buttons.append(button)
        gate = _gate_check(behavior_pack, ident, block, gate_tables)
        if gate is not None:
            checks.gates.append(gate)
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
    checks.trapdoors.sort(key=lambda d: d["id"])
    checks.plates.sort(key=lambda d: d["id"])
    checks.buttons.sort(key=lambda d: d["id"])
    checks.gates.sort(key=lambda d: d["id"])
    checks.ores = _ore_checks(behavior_pack)
    checks.geodes = _geode_checks(behavior_pack)
    return checks


def manifest(name: str, data: bool = False) -> dict:
    """The check pack's manifest: uuids derived from its name, so reruns match.
    ``data``: the pack also carries data (the test-only geode rules), so it
    gets a ``data`` module too."""
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
        ] + ([{"type": "data", "uuid": uid("data"), "version": [1, 0, 0]}] if data else []),
        "dependencies": [{"module_name": "@minecraft/server", "version": SERVER_MODULE}],
    }


def write_test_pack(behavior_pack: Path, out: Path, name: str, world: str = "flat") -> Checks:
    """Write the check pack for ``behavior_pack`` into ``out``; return its checks.

    ``world="default"``: the run's world is a generated Overworld (#281), so
    only the ore and geode checks go in (the others lay out blocks on the
    flat world)."""
    checks = read_checks(behavior_pack)
    if world != "flat":
        checks = Checks(ores=checks.ores, geodes=checks.geodes, world=world)
    rules = geode_rule_files(behavior_pack, checks.geodes)
    if out.exists():
        shutil.rmtree(out)
    scripts = out / "scripts"
    scripts.mkdir(parents=True)
    (out / "manifest.json").write_text(json.dumps(manifest(name, data=bool(rules)), indent=2) + "\n")
    for rel, body in rules.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_text(json.dumps(body, indent=2) + "\n")
    for file in SCRIPT_FILES:
        shutil.copyfile(RUNTIME / file, scripts / file)
    (scripts / "data.js").write_text(
        "// Generated by portkit.ingame.testpack (#238): what the checks cover.\n"
        f"export const CHECKS = {json.dumps(checks.as_json(), indent=1, sort_keys=True)};\n"
    )
    return checks
