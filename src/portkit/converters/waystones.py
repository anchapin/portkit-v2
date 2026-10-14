"""Waystones: waystone blocks + a fixed Script API teleport runtime (#178).

The station pattern of #177 (:mod:`portkit.converters.stations`,
docs/decisions.md) applied to Waystones' waystone: the converter writes a
generated data table (``scripts/portkit/data/waystones_waystone.js``) read by a
hand-written runtime (``portkit/runtime/waystone.js`` and its node-tested
logic ``waystone_core.js``) that does what Waystones' Java code does, cited per
line there. This first slice covers the ten waystone blocks (``WaystoneBlock``):
placing one (both halves), activating it, naming it, the menu of the
waystones a player has activated, and the teleport with its experience cost.
Sharestones, portstones, warp plates, warp portals, fleeting memorials and the
warp items keep their residue.

Where each value comes from (no fabrication, #87):

* **Which blocks**: Waystones' own ``waystones:waystones`` block tag (data),
  each a block ``ModBlocks`` registers as a ``WaystoneBlock``
  (:data:`WAYSTONE_BLOCKS`, cited), whose blockstate is ``facing`` x ``half``.
* **Shape, facing, the two halves**: ``WaystoneBlock`` / ``WaystoneBlockBase``
  (shapes, ``getStateForPlacement``, ``setPlacedBy``, ``playerWillDestroy``).
* **Breaking drops**: the jar's loot table (one pool, the lower half only).
* **The experience cost**: the ``warpRequirements`` config default, parsed
  here the way ``RequirementModifierParser`` parses it, with
  ``enableCosts`` / ``enableCooldowns``; values from
  ``portkit/data/waystones_config_defaults.json`` (cited per value). Each
  modifier's conditions are decided for this runtime (:data:`FIXED_CONDITIONS`:
  a teleport here always starts at a waystone and ends at one with the default
  ``ACTIVATION`` visibility); what is left is evaluated by the runtime.
  An unknown condition or function means no runtime (residue), never a guess.
* **Texts**: the jar's own lang keys (:data:`MESSAGES`), shipped under their
  Java key (:func:`portkit.converters.lang.convert` ``runtime_keys``).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources

from ..conditions import LoadContext
from ..model import ConversionResult, SourceMod, Unhandled
from .stations import (
    SCRIPT_FORMAT,
    SCRIPT_MODULE,
    SCRIPT_VERSION,
    FacingBlock,
    _js_module,
    _RUNTIME_DIR,
    runtime_source,
)

NS = "waystones"
STATION = "waystone"
RESIDUE_KIND = "waystone"
HALF_STATE = "waystones:half"
COMPONENT = "waystones:portkit_waystone"
DEFAULTS_DATA = "waystones_config_defaults.json"
TAG = "data/waystones/tags/block/waystones.json"
# Vanilla Bedrock's empty loot table, for the upper half (as the feasts' empty
# serving counts; Mojang/bedrock-samples 46ba6ea9 behavior_pack/loot_tables/empty.json).
EMPTY_LOOT = "loot_tables/empty.json"
UI_MODULE = "@minecraft/server-ui"
UI_VERSION = "2.0.0"

REPO = "https://github.com/TwelveIterations/Waystones"
COMMIT = "9d280c1ac8d036516a2927e3d2cad8054e491074"  # tag v21.1.46
VERSIONS = {"fabric": "21.1.46"}


def _src(path: str, line: str) -> str:
    return f"{REPO}/blob/{COMMIT}/common/src/main/java/net/blay09/mods/waystones/{path}#L{line}"


# The blocks ModBlocks registers as WaystoneBlock (ModBlocks.java L70-L85,
# all with defaultProperties(), L112). Sharestones, portstones, the warp plate,
# the warp portal and the fleeting memorial are other classes.
WAYSTONE_BLOCKS = (
    "waystone", "mossy_waystone", "sandy_waystone", "deepslate_waystone", "blackstone_waystone",
    "end_stone_waystone", "red_nether_bricks_waystone", "purpur_waystone", "prismarine_waystone",
    "mud_bricks_waystone",
)
BLOCK_SOURCES = (
    _src("block/ModBlocks.java", "70-L85"),
    # LOWER_SHAPE / UPPER_SHAPE; getShape by HALF.
    _src("block/WaystoneBlock.java", "44-L57"),
    # FACING = getHorizontalDirection().getOpposite(), needs a replaceable block above.
    _src("block/WaystoneBlockBase.java", "160-L173"),
)

# Java's shapes as one Bedrock box per half (origin/size in pixels, centred on
# x and z): the bounding box of each union, the same at every facing (the
# shapes are centred). LOWER_SHAPE spans 0-16 on every axis; UPPER_SHAPE's
# widest part is box(1, 10, 1, 15, 12, 15), height 0-16.
LOWER_BOX = {"origin": [-8, 0, -8], "size": [16, 16, 16]}
UPPER_BOX = {"origin": [-7, 0, -7], "size": [14, 16, 14]}


def _block(name: str) -> FacingBlock:
    return FacingBlock(
        name, 180, LOWER_BOX, BLOCK_SOURCES,
        java_state="half", values=("lower", "upper"), state=HALF_STATE,
        value_components={
            "lower": {"minecraft:collision_box": dict(LOWER_BOX), "minecraft:selection_box": dict(LOWER_BOX)},
            "upper": {"minecraft:collision_box": dict(UPPER_BOX), "minecraft:selection_box": dict(UPPER_BOX)},
        },
    )


# The Java lang keys the runtime shows, by role. Each is the key Waystones'
# code uses at the cited line; the jar's en_us.json must define it.
MESSAGES = {
    # WaystoneBlock#handleActivation L91-93: "Activated Waystone: %s".
    "activated": "chat.waystones.waystone_activated",
    # WaystoneTeleportError.NotEnoughXp L104-108 (shown on the action bar,
    # SelectWaystoneMessage L64).
    "not_enough_xp": "chat.waystones.not_enough_xp",
    # WaystoneTeleportError.SourceWaystoneOutOfRange / InvalidWaystone.
    "out_of_range": "chat.waystones.source_waystone_out_of_range",
    "missing": "chat.waystones.waystone_missing",
    # WaystoneEditError.NotOwner L22-26.
    "only_owner": "chat.waystones.only_owner_can_edit",
    # WaystoneBlockEntity#getSelectionMenuProvider L40.
    "title": "container.waystones.waystone_selection",
    # WaystoneSelectionScreenBase L384 (header for the waystone used).
    "current_location": "gui.waystones.waystone_selection.current_location",
    # AbstractWaystoneButton L29-32 (an empty name in the list).
    "unnamed": "gui.waystones.waystone_selection.unnamed_waystone",
    # The empty list (gui.waystones.waystone_selection.no_waystones_activated).
    "none": "gui.waystones.waystone_selection.no_waystones_activated",
    # ExperiencePointsRequirement#appendHoverText L36-40 (only when > 0).
    "xp_cost": "gui.waystones.waystone_selection.xp_requirement",
    # WaystoneBlockEntityBase#getSettingsMenuProvider L297 ("Edit %s") and
    # the screen's save button.
    "settings": "container.waystones.waystone_settings",
    "save": "gui.waystones.waystone_settings.save",
    # EditWaystoneMessage#makeNameLegal L84-87: a blank name.
    "untitled": "waystones.untitled_waystone",
}

# Bedrock vanilla sound events playing the same audio as the Java events
# (Java: misode/mcmeta 1.21.1-assets 451045f2 assets/minecraft/sounds.json;
# Bedrock: Mojang/bedrock-samples 46ba6ea9 resource_pack/sounds/sound_definitions.json):
# entity.player.levelup = random/levelup = random.levelup;
# block.portal.travel = portal/travel = portal.travel.
SOUNDS = {
    # WaystoneBlock#handleActivation L97: PLAYER_LEVELUP, 0.2, 1.
    "activate": {"id": "random.levelup", "volume": 0.2, "pitch": 1.0},
    # WaystoneTeleportManager#performTeleport L161-162: PORTAL_TRAVEL at the
    # source (0.01) and the target (0.05), pitch 1.
    "depart": {"id": "portal.travel", "volume": 0.01, "pitch": 1.0},
    "arrive": {"id": "portal.travel", "volume": 0.05, "pitch": 1.0},
}

# How a requirement condition evaluates in this runtime, where every teleport
# starts at a waystone block and targets a waystone the player activated
# (RequirementRegistry L294-L348). Conditions not here, except
# is_interdimensional (decided per teleport), have no runtime.
FIXED_CONDITIONS = {
    "source_is_warp_plate": False,  # L295-L296: the source is a waystone
    "source_is_scroll": False,  # L311: no warp item starts a teleport here
    "source_is_inventory_button": False,  # L308-L310: no inventory button
    "source_is_portstone": False,  # L297-L298
    "source_is_sharestone": False,  # L301-L302
    "source_is_waystone": True,  # L299-L300
    # L335-L337: every waystone keeps the default ACTIVATION visibility
    # (general.defaultVisibility); visibility isn't editable here.
    "target_is_global": False,
    "target_is_fleeting_memorial": False,  # L329-L331: memorials don't convert
    "target_is_warp_plate": False,  # L323-L325
    "target_is_warp_portal": False,  # L326-L328
    "target_is_player": False,  # L332-L334: twinbound feathers don't convert
    "target_is_sharestone": False,  # L338-L340
    "target_is_waystone": True,  # L346-L348
}
DYNAMIC_CONDITIONS = {"is_interdimensional"}  # L294: target dimension != the player's
# Experience-point functions (RequirementRegistry L122-L147) and the parameter
# kinds their arguments parse as (L272-L286).
XP_FUNCTIONS = {
    "add_xp_cost": ("int",),
    "multiply_xp_cost": ("float",),
    "scaled_add_xp_cost": ("variable", "float"),
    "min_xp_cost": ("int",),
    "max_xp_cost": ("int",),
}
COOLDOWN_FUNCTIONS = {"add_cooldown", "multiply_cooldown", "min_cooldown", "max_cooldown",
                      "scaled_add_cooldown", "scaled_multiply_cooldown"}
VARIABLES = {"distance"}  # L434: player to the target's block centre
REQUIREMENT_SOURCES = (
    _src("requirement/RequirementModifierParser.java", "13-L25"),
    _src("requirement/RequirementRegistry.java", "122-L147"),
    _src("requirement/RequirementRegistry.java", "294-L348"),
    _src("requirement/RequirementRegistry.java", "434"),
    _src("requirement/RequirementRegistry.java", "529-L530"),
    _src("requirement/ExperiencePointsRequirement.java", "17-L28"),
    _src("InternalMethodsImpl.java", "244-L259"),
)
RUNTIME_SOURCES = (
    _src("block/WaystoneBlock.java", "81-L123"),
    _src("block/WaystoneBlockBase.java", "96-L137"),
    _src("block/WaystoneBlockBase.java", "196-L205"),
    _src("block/WaystoneBlockBase.java", "286-L339"),
    _src("core/WaystoneTeleportManager.java", "245-L284"),
    _src("core/WaystoneTeleportManager.java", "481-L494"),
    _src("core/WaystoneTeleportManager.java", "523-L532"),
    _src("core/WaystonePermissionManager.java", "35-L53"),
    _src("network/message/EditWaystoneMessage.java", "84-L94"),
    _src("client/gui/screen/WaystoneEditScreen.java", "54"),
    _src("client/gui/widget/WaystoneList.java", "46-L48"),
    _src("core/PersistentPlayerWaystoneData.java", "270-L290"),
)
NAME_MAX_LENGTH = 128  # WaystoneEditScreen L54: nameField.setMaxLength(128)
# WaystoneTeleportManager#canInteractWithWaystone L531: a non-player must be
# within 8 blocks (distanceToSqr <= 64) of the source waystone's centre; a
# player's canInteractWithBlock(pos, 4) test reads the player's reach
# attribute, so the runtime uses the fixed distance for everyone.
RANGE_SQ = 64


class _Refuse(Exception):
    pass


def _defaults(version: str) -> dict | None:
    text = resources.files("portkit.data").joinpath(DEFAULTS_DATA).read_text(encoding="utf-8")
    return (json.loads(text).get("versions") or {}).get(version)


def _unsupported(mod: SourceMod) -> str | None:
    if mod.namespace != NS:
        return f"the waystone runtime is Waystones' (namespace {NS!r}), not {mod.namespace!r}"
    version = (mod.mods or {}).get(NS)
    if mod.loader not in VERSIONS or version != VERSIONS[mod.loader] or _defaults(version) is None:
        known = ", ".join(f"{v} ({k})" for k, v in sorted(VERSIONS.items()))
        return (f"Waystones {version or '(unknown version)'} on {mod.loader or 'an unknown loader'}: the "
                f"waystone runtime follows Waystones' code at the version it was read from ({known})")
    return None


def _tagged(mod: SourceMod) -> list[str]:
    path = mod.root / TAG
    try:
        values = json.loads(path.read_text()).get("values") or []
    except (OSError, json.JSONDecodeError, AttributeError):
        return []
    names = []
    for value in values:
        ident = value if isinstance(value, str) else (value.get("id") if isinstance(value, dict) else None)
        if isinstance(ident, str) and ident.startswith(f"{NS}:"):
            names.append(ident.split(":", 1)[1])
    return names


def waystone_blocks(mod: SourceMod) -> dict[str, FacingBlock]:
    """Waystone blocks of ``mod`` the runtime makes work, by blockstate name."""
    if _unsupported(mod) is not None:
        return {}
    return {name: _block(name) for name in _tagged(mod)
            if name in WAYSTONE_BLOCKS and (mod.assets / "blockstates" / f"{name}.json").is_file()}


def loot_names(mod: SourceMod) -> set[str]:
    """Block loot tables (by name under loot_table/blocks/) this converter reads."""
    return set(waystone_blocks(mod))


def lang_keys(mod: SourceMod) -> set[str]:
    """Java lang keys the runtime shows (shipped under their own name)."""
    return set(MESSAGES.values()) if waystone_blocks(mod) else set()


# -- requirements -------------------------------------------------------------------

_CONDITION = re.compile(r"([\w:]+)(?:\((.*?)\))?")
_FUNCTION = re.compile(r"([\w:]+)\((.*?)\)")


def _local(ident: str) -> str:
    """RequirementModifierParser#waystonesResourceLocation: no namespace is waystones."""
    ns, _, path = ident.rpartition(":")
    if ns not in ("", NS):
        raise _Refuse(f"{ident!r} is not a Waystones requirement id")
    return path


def _negated(name: str) -> tuple[str, bool]:
    """(base condition, negated) for a condition id; Java registers each
    condition's negation as its name with ``not_`` after the first ``is_``
    (RequirementRegistry L529-L530)."""
    index = name.find("is_not_")
    if index != -1:
        return name[:index + 3] + name[index + 7:], True
    if name.startswith("not_"):
        return name[4:], True
    return name, False


def _argument(kind: str, raw: str):
    raw = raw.strip()
    try:
        if kind == "int":
            return int(raw)
        if kind == "float":
            return float(raw)
    except ValueError as exc:
        raise _Refuse(f"argument {raw!r} is not a {kind}") from exc
    variable = _local(raw)
    if variable not in VARIABLES:
        raise _Refuse(f"variable {raw!r} has no runtime")
    return variable


def requirements(lines: list[str], enable_costs: bool, enable_cooldowns: bool) -> tuple[list[dict], list[str]]:
    """The warp requirement modifiers that can apply in this runtime, in order,
    as {"when": {condition: wanted}, "fn": name, "args": [...]}, and the lines
    left out (with why). Raises _Refuse for anything without a runtime."""
    kept: list[dict] = []
    dropped: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        start, end = line.find("["), line.find("]")
        condition_part = line[start + 1:end] if start != -1 and end != -1 else ""
        function_part = line[end + 1:].strip()
        when: dict[str, bool] = {}
        never = False
        for match in _CONDITION.finditer(condition_part):
            base, negated = _negated(_local(match.group(1)))
            if match.group(2):
                raise _Refuse(f"condition {match.group(1)!r} takes arguments; none is read here")
            if base in FIXED_CONDITIONS:
                if FIXED_CONDITIONS[base] == negated:
                    never = True
            elif base in DYNAMIC_CONDITIONS:
                wanted = not negated
                if when.get(base, wanted) != wanted:
                    never = True
                when[base] = wanted
            else:
                raise _Refuse(f"warp requirement condition {match.group(1)!r} has no runtime")
        functions = [(m.group(1), m.group(2)) for m in _FUNCTION.finditer(function_part)]
        if not functions:
            raise _Refuse(f"warp requirement {line!r} names no function")
        for name, args in functions:
            fn = _local(name)
            if fn in COOLDOWN_FUNCTIONS:
                if never or not enable_cooldowns:
                    dropped.append(f"{line} (never applies here)" if never else f"{line} (enableCooldowns off)")
                    continue
                raise _Refuse(f"cooldown requirement {line!r} applies here; cooldowns have no runtime")
            if fn not in XP_FUNCTIONS:
                raise _Refuse(f"warp requirement function {name!r} has no runtime")
            kinds = XP_FUNCTIONS[fn]
            parts = [a for a in args.split(",")] if args.strip() else []
            if len(parts) != len(kinds):
                raise _Refuse(f"{name}({args}) takes {len(kinds)} argument(s)")
            if not enable_costs:
                dropped.append(f"{line} (enableCosts off)")
                continue
            if never:
                dropped.append(f"{line} (never applies here)")
                continue
            kept.append({"when": dict(sorted(when.items())), "fn": fn,
                         "args": [_argument(k, a) for k, a in zip(kinds, parts)]})
    return kept, dropped


# -- loot ---------------------------------------------------------------------------


def _loot(rel: str, table: dict, identifier: str, notes: list[str]) -> dict:
    """The lower half's Bedrock table from the jar's: one pool, gated on
    half=lower, survives_explosion, the block's own item; the silk-touch
    copy_components (the item keeps the waystone's identity) is not carried."""
    pools = table.get("pools")
    if not isinstance(pools, list) or len(pools) != 1 or table.get("functions"):
        raise _Refuse("the table is not one pool")
    pool = pools[0]
    if pool.get("rolls", 1) not in (1, 1.0) or pool.get("bonus_rolls", 0) not in (0, 0.0):
        raise _Refuse("the pool does not roll exactly once")
    entries = pool.get("entries")
    if not isinstance(entries, list) or len(entries) != 1:
        raise _Refuse("the pool does not have one entry")
    entry = entries[0]
    if not isinstance(entry, dict) or entry.get("type") not in ("minecraft:item", "item") \
            or entry.get("name") != identifier or set(entry) - {"type", "name"}:
        raise _Refuse(f"the entry is not a plain {identifier} item")
    lower = explosion = False
    for condition in pool.get("conditions") or []:
        kind = condition.get("condition")
        if kind == "minecraft:survives_explosion":
            explosion = True
        elif (kind == "minecraft:block_state_property" and condition.get("block") == identifier
              and condition.get("properties") == {"half": "lower"}):
            lower = True
        else:
            raise _Refuse(f"pool condition {kind!r} is not half=lower or survives_explosion")
    if not lower:
        raise _Refuse("the pool is not gated on half=lower")
    for function in pool.get("functions") or []:
        silk = function.get("conditions") or []
        if not (function.get("function") == "minecraft:copy_components" and function.get("source") == "block_entity"
                and len(silk) == 1 and silk[0].get("condition") == "minecraft:match_tool"):
            raise _Refuse(f"pool function {function.get('function')!r} is not the silk-touch copy")
        notes.append("silk_touch")
    bedrock_entry: dict = {"type": "item", "name": identifier}
    if explosion:
        bedrock_entry["functions"] = [{"function": "explosion_decay"}]
    return {"pools": [{"rolls": 1, "entries": [bedrock_entry]}]}


def _half(condition: str) -> str | None:
    for value in ("lower", "upper"):
        if f"q.block_state('{HALF_STATE}') == '{value}'" in condition:
            return value
    return None


def _jar_lang(mod: SourceMod) -> dict:
    try:
        return json.loads((mod.assets / "lang" / "en_us.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


# -- the converter ------------------------------------------------------------------


@dataclass(frozen=True)
class _Plan:
    modifiers: list
    dropped: list
    defaults: dict


def _plan(mod: SourceMod) -> _Plan:
    entry = _defaults((mod.mods or {}).get(NS))
    values = {k: v["value"] for k, v in entry["values"].items()}
    modifiers, dropped = requirements(values["teleports.warpRequirements"], values["teleports.enableCosts"],
                                      values["teleports.enableCooldowns"])
    return _Plan(modifiers, dropped, entry)


def convert(mod: SourceMod, deferred: list[tuple[str, dict]], files: dict,
            context: LoadContext) -> tuple[ConversionResult, str]:
    """The waystones' runtime entry, loot tables and block components.

    ``deferred`` is (source path, table) for the waystones' block loot tables,
    which the loot converter left to this one (:func:`loot_names`).
    """
    result = ConversionResult()
    blocks = waystone_blocks(mod)
    tables = {rel.rsplit("/", 1)[-1][:-len(".json")]: (rel, table) for rel, table in deferred}
    if not blocks:
        for rel, _ in deferred:
            result.unhandled.append(Unhandled(rel, RESIDUE_KIND, "no waystone runtime for this jar"))
        return result, ""

    lang = _jar_lang(mod)
    why_all = None
    missing = sorted(k for k in MESSAGES.values() if k not in lang)
    if missing:
        why_all = f"the jar's en_us.json lacks {', '.join(missing)}, which the runtime shows"
    plan = None
    if why_all is None:
        try:
            plan = _plan(mod)
        except _Refuse as refusal:
            why_all = f"warpRequirements: {refusal}"

    notes: list[str] = []
    kept: list[str] = []
    silk = False
    for name in sorted(blocks):
        identifier = f"{NS}:{name}"
        block_path = f"blocks/{name}.json"
        body = files.get(block_path)
        loot = tables.get(name)
        why = why_all
        if why is None and not (isinstance(body, dict) and body.get("minecraft:block", {})
                                .get("description", {}).get("identifier") == identifier):
            why = f"the waystone block {identifier} did not convert"
        bedrock_loot = None
        if why is None:
            if loot is None:
                why = f"no loot table for {identifier} in the jar, so what breaking it drops is unknown"
            else:
                flags: list[str] = []
                try:
                    bedrock_loot = _loot(loot[0], loot[1], identifier, flags)
                except _Refuse as refusal:
                    why = f"loot table {loot[0]}: {refusal}"
                silk = silk or "silk_touch" in flags
        if why is not None:
            if loot is not None:
                result.unhandled.append(Unhandled(loot[0], RESIDUE_KIND, why))
            if isinstance(body, dict):
                notes.append(f"{identifier}: places but does nothing ({why})")
            continue

        loot_path = f"loot_tables/blocks/{name}.json"
        result.files[loot_path] = bedrock_loot
        result.consumed.add(loot[0])
        new = json.loads(json.dumps(body))
        new["format_version"] = SCRIPT_FORMAT
        block = new["minecraft:block"]
        block.setdefault("components", {})[COMPONENT] = {}
        # Only the lower half drops (the pool's half=lower); breaking the
        # upper half takes the lower one with it (the runtime), which drops.
        block["components"]["minecraft:loot"] = loot_path
        for permutation in block.get("permutations") or []:
            half = _half(permutation.get("condition", ""))
            if half is not None:
                permutation.setdefault("components", {})["minecraft:loot"] = (
                    loot_path if half == "lower" else EMPTY_LOOT)
        result.files[block_path] = new
        kept.append(identifier)

    if not kept:
        result.notes.extend(dict.fromkeys(notes))
        return result, ""

    values = {k: v["value"] for k, v in plan.defaults["values"].items()}
    table = {
        "blocks": kept,
        "component": COMPONENT,
        "half_state": HALF_STATE,
        "messages": dict(MESSAGES),
        "name_max_length": NAME_MAX_LENGTH,
        "namespace": NS,
        "range_sq": RANGE_SQ,
        "requirements": plan.modifiers,
        "restricted_origins": sorted(values["general.restrictedWaystones"]),
        "sounds": SOUNDS,
    }
    data_path = f"{_RUNTIME_DIR}/data/{NS}_waystone.js"
    config_sources = [f"{plan.defaults['repo']}/blob/{plan.defaults['commit']}/{v['source']}"
                      for v in plan.defaults["values"].values()]
    header = (
        f"// Generated by portkit from {NS}'s waystone blocks, loot tables, config defaults and Java code;\n"
        f"// do not edit. Read by the fixed runtime {_RUNTIME_DIR}/waystone.js (portkit/runtime). Sources:\n"
        + "".join(f"//   {s}\n" for s in dict.fromkeys(
            (*BLOCK_SOURCES, *config_sources, *REQUIREMENT_SOURCES, *RUNTIME_SOURCES)))
        + "".join(f"// warpRequirements left out: {d}\n" for d in plan.dropped)
    ).rstrip("\n")
    result.files[data_path] = _js_module(header, table)
    for name in ("waystone.js", "waystone_core.js"):
        result.files[f"{_RUNTIME_DIR}/{name}"] = runtime_source(name)
    result.stations[f"{NS}:waystones"] = {
        "converted": len(kept),
        "residue": len(blocks) - len(kept),
        "data": data_path,
        "block": ", ".join(kept),
    }
    result.notes.extend(dict.fromkeys(notes))
    result.notes.append(
        f"{NS}: {len(kept)} waystone block(s) work through a Script API runtime ({SCRIPT_MODULE} {SCRIPT_VERSION} "
        f"and {UI_MODULE} {UI_VERSION}, {data_path}): {', '.join(kept)}. Placing one sets its upper half "
        "(it needs a free block above), activates it for the placer and asks for its name; using a waystone "
        "activates it for that player, or opens a menu of the waystones the player has activated (in "
        "activation order, the one in use left out); choosing one teleports the player beside it and takes "
        "the experience cost of the warpRequirements default (distance x 0.01 points in the same dimension, "
        "27 between dimensions, at most 27; creative players go even when they can't pay). Sneak-using renames it "
        "(only its owner). Breaking either half removes both and the waystone. Not carried over: "
        "visibility (every waystone is visible upon activation), the waystone's modifier slots and warp "
        "modifiers, groups, aliases, favourites, sorting and search in the menu, deleting entries from it, "
        "pets and leashed mobs travelling along, waterlogging, the particles, the comparator signal, "
        "observers, a silk-touched waystone keeping its identity when moved (it is a new waystone), "
        "operator edit permission, teleports into a chunk that is not loaded checking for room (the "
        "player lands on the waystone's front), the 'free space' tests (placing needs air or liquid above, "
        "and only air or liquid count as room beside a target, where Java also accepts replaceable or "
        "non-suffocating blocks like grass), the other half going when one is removed by anything but a "
        "player (an explosion), and config changes "
        "(the cited defaults are used). The item shows the lower half only. Village and wild waystone "
        "generation, sharestones, portstones, warp plates and portals, fleeting memorials and the warp "
        "stone, scrolls, shards and feather are not converted."
        + (" Silk touch drops a plain waystone." if silk else "")
    )
    entry = (
        'import { registerWaystones } from "./waystone.js";\n'
        f'import waystoneTable from "./data/{NS}_waystone.js";\n'
        "registerWaystones(waystoneTable);\n"
    )
    return result, entry
