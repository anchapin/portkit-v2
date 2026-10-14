"""Waystones: waystone blocks + a fixed Script API teleport runtime (#178).

The converter writes the ten waystone blocks (facing x a custom ``half`` state,
a box per half, minecraft:loot on the lower half only), their Bedrock loot
tables, scripts/portkit/data/waystones_waystone.js (the warpRequirements
default decided for this runtime, the texts, sounds and rules) and ships the
fixed runtime (portkit/runtime/waystone*.js), with a @minecraft/server-ui
dependency in the behavior pack manifest.

Offline: a Waystones-shaped Fabric mod with two waystones, an orange
sharestone, a white "sharestone" (Waystones registers none: white is the
one dye colour without a SharestoneBlock), and a white and an orange
portstone.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from portkit.converters import waystones
from portkit.converters.waystones import requirements
from portkit.pipeline import convert

from test_stations import PNG, ROOT, _write

NS = "waystones"
DATA = "behavior_pack/scripts/portkit/data/waystones_waystone.js"
TURNS = (("north", 0), ("east", 90), ("south", 180), ("west", 270))
FACES = ("north", "east", "south", "west", "up", "down")
DEFAULTS = [
    "[is_not_interdimensional] scaled_add_xp_cost(distance, 0.01)",
    "[is_interdimensional] add_xp_cost(27)",
    "[source_is_warp_plate] multiply_xp_cost(0)",
    "[source_is_scroll] multiply_xp_cost(0)",
    "[target_is_global] multiply_xp_cost(0)",
    "[target_is_fleeting_memorial] multiply_xp_cost(0)",
    "min_xp_cost(0)",
    "max_xp_cost(27)",
    "[source_is_inventory_button] add_cooldown(inventory_button, 300)",
]


def _element(name, y0, y1, inset):
    return {"name": name, "from": [inset, y0, inset], "to": [16 - inset, y1, 16 - inset],
            "faces": {f: {"uv": [0, 0, 4, 4], "texture": "#texture"} for f in FACES}}


def _loot(block, extra_function=None):
    functions = [{"conditions": [{"condition": "minecraft:match_tool", "predicate": {"predicates": {
        "minecraft:enchantments": [{"enchantments": "minecraft:silk_touch", "levels": {"min": 1}}]}}}],
        "function": "minecraft:copy_components", "source": "block_entity"}]
    if extra_function:
        functions.append(extra_function)
    return {"type": "minecraft:block", "pools": [{
        "bonus_rolls": 0.0,
        "conditions": [{"block": f"{NS}:{block}", "condition": "minecraft:block_state_property",
                        "properties": {"half": "lower"}}, {"condition": "minecraft:survives_explosion"}],
        "entries": [{"type": "minecraft:item", "name": f"{NS}:{block}"}],
        "functions": functions, "rolls": 1.0}]}


LANG = {
    "block.waystones.waystone": "Waystone",
    "block.waystones.mossy_waystone": "Mossy Waystone",
    "block.waystones.white_sharestone": "White Sharestone",
    "chat.waystones.waystone_activated": "Activated Waystone: %s",
    "chat.waystones.not_enough_xp": "You do not have enough experience to teleport.",
    "chat.waystones.source_waystone_out_of_range": "You moved too far away from the waystone.",
    "chat.waystones.waystone_missing": "The waystone you tried to teleport to is currently being moved or has gone missing.",
    "chat.waystones.only_owner_can_edit": "Only the owner may edit this waystone.",
    "chat.waystones.scroll_bound": "Scroll bound: %s",
    "container.waystones.waystone_selection": "Select your destination",
    "gui.waystones.waystone_selection.current_location": "Current Location: %s",
    "gui.waystones.waystone_selection.unnamed_waystone": "<unnamed>",
    "gui.waystones.waystone_selection.no_waystones_activated": "You have not activated any waystones yet.",
    "gui.waystones.waystone_selection.xp_requirement": "Experience Cost: %d",
    "container.waystones.waystone_settings": "Edit %s",
    "gui.waystones.waystone_settings.save": "Save",
    "waystones.untitled_waystone": "Untitled Waystone",
    "container.waystones.waystone": "Waystone",
    "container.waystones.sharestone": "Sharestone",
    "gui.waystones.waystone_selection.no_sharestones_available": "There are no matching Sharestones to teleport to.",
    "block.waystones.orange_sharestone": "Orange Sharestone",
    "block.waystones.white_portstone": "Portstone",
    "block.waystones.orange_portstone": "Orange Portstone",
    "container.waystones.white_portstone": "Portstone",
    "container.waystones.orange_portstone": "Orange Portstone",
    "tooltip.waystones.portstone": "Can not be teleported to.",
}
# PortstoneBlock's north shapes (L66-74 / L97-101), drawn by its models.
PORTSTONE_BOTTOM = [([0, 0, 0], [16, 3, 16]), ([1, 3, 1], [15, 7, 15]), ([2, 7, 2], [14, 9, 14]),
                    ([3, 9, 9], [13, 16, 13]), ([4, 9, 6], [12, 16, 9]), ([4, 9, 4], [12, 12, 6])]
PORTSTONE_TOP = [([3, 0, 9], [13, 7, 13]), ([4, 0, 7], [12, 2, 9])]


def _box_model(boxes):
    return {"textures": {"particle": "block/andesite", "texture": f"{NS}:block/andesite_waystone"},
            "elements": [{"from": a, "to": b, "faces": {f: {"uv": [0, 0, 4, 4], "texture": "#texture"}
                                                         for f in FACES}} for a, b in boxes]}


def _waystones_mod(tmp_path, version="21.1.46", loot=None, lang=None) -> Path:
    root = tmp_path / "ws"
    png = PNG.read_bytes()
    _write(root, "fabric.mod.json", {"schemaVersion": 1, "id": NS, "version": version,
                                     "depends": {"minecraft": "1.21.1", "fabricloader": ">=0.15"}})
    blocks = {"waystone": "andesite_waystone", "mossy_waystone": "mossy_andesite_waystone",
              "white_sharestone": "andesite_waystone", "orange_sharestone": "andesite_waystone",
              "white_portstone": "andesite_waystone", "orange_portstone": "andesite_waystone"}
    _write(root, f"assets/{NS}/models/block/portstone_bottom.json", _box_model(PORTSTONE_BOTTOM))
    _write(root, f"assets/{NS}/models/block/portstone_top.json", _box_model(PORTSTONE_TOP))
    _write(root, f"assets/{NS}/models/block/waystone_bottom.json", {
        "textures": {"particle": "block/polished_andesite", "texture": f"{NS}:block/andesite_waystone"},
        "elements": [_element("base", 0, 3, 0), _element("pillar", 3, 16, 3)]})
    _write(root, f"assets/{NS}/models/block/waystone_top.json", {
        "textures": {"particle": "block/polished_andesite", "texture": f"{NS}:block/andesite_waystone"},
        "elements": [_element("pillar", 0, 12, 3), _element("cap", 12, 16, 4)]})
    for name, texture in blocks.items():
        stem = ("sharestone" if name.endswith("_sharestone") else
                "portstone" if name.endswith("_portstone") else name)
        if name == "mossy_waystone":
            for half in ("bottom", "top"):
                _write(root, f"assets/{NS}/models/block/mossy_waystone_{half}.json", {
                    "parent": f"{NS}:block/waystone_{half}",
                    "textures": {"particle": f"{NS}:block/{texture}", "texture": f"{NS}:block/{texture}"}})
        if name == "orange_sharestone":
            for half in ("bottom", "top"):
                _write(root, f"assets/{NS}/models/block/sharestone_{half}.json",
                       {"parent": f"{NS}:block/waystone_{half}"})
        _write(root, f"assets/{NS}/blockstates/{name}.json", {"variants": {
            f"facing={d},half={h}": {"model": f"{NS}:block/{stem}_{'bottom' if h == 'lower' else 'top'}",
                                     **({"y": y} if y else {})}
            for d, y in TURNS for h in ("lower", "upper")}})
        _write(root, f"assets/{NS}/textures/block/{texture}.png", png)
        _write(root, f"data/{NS}/loot_table/blocks/{name}.json", (loot or {}).get(name, _loot(name)))
    _write(root, f"assets/{NS}/lang/en_us.json", lang if lang is not None else LANG)
    _write(root, f"assets/{NS}/lang/de_de.json", {"chat.waystones.waystone_activated": "Wegstein aktiviert: %s",
                                                  "block.waystones.waystone": "Wegstein"})
    _write(root, f"data/{NS}/tags/block/waystones.json", {"values": [f"{NS}:waystone", f"{NS}:mossy_waystone"]})
    _write(root, f"data/{NS}/tags/block/sharestones.json", {"values": [
        f"{NS}:white_sharestone", f"{NS}:orange_sharestone"]})
    _write(root, f"data/{NS}/tags/block/portstones.json", {"values": [
        f"{NS}:white_portstone", f"{NS}:orange_portstone"]})
    return root


def _table(tree: Path) -> dict:
    return json.loads((tree / DATA).read_text().split("export default ", 1)[1].rstrip().rstrip(";"))


def _block(tree: Path, name: str) -> dict:
    return json.loads((tree / f"behavior_pack/blocks/{name}.json").read_text())["minecraft:block"]


@pytest.fixture
def converted(tmp_path):
    result = convert(_waystones_mod(tmp_path), tmp_path / "out", emit_addon=False)
    return result, tmp_path / "out"


def test_table_holds_the_requirements_decided_for_this_runtime(converted):
    result, tree = converted
    table = _table(tree)
    assert table["blocks"] == ["waystones:mossy_waystone", "waystones:orange_portstone",
                               "waystones:orange_sharestone", "waystones:waystone", "waystones:white_portstone"]
    assert table["block_types"] == {"waystones:mossy_waystone": "waystones:waystone",
                                    "waystones:orange_sharestone": "waystones:orange_sharestone",
                                    "waystones:waystone": "waystones:waystone"}
    assert table["default_type"] == "waystones:waystone"
    assert set(table["networks"]) == {"waystones:waystone", "waystones:orange_sharestone"}
    assert table["networks"]["waystones:waystone"]["shared"] is False
    assert table["networks"]["waystones:orange_sharestone"]["shared"] is True
    assert table["networks"]["waystones:orange_sharestone"]["none"] == "none_shared"
    # The defaults have no sharestone rule: a sharestone pays what a waystone does.
    assert (table["networks"]["waystones:orange_sharestone"]["requirements"]
            == table["networks"]["waystones:waystone"]["requirements"])
    assert table["networks"]["waystones:waystone"]["requirements"] == [
        {"args": ["distance", 0.01], "fn": "scaled_add_xp_cost", "when": {"is_interdimensional": False}},
        {"args": [27], "fn": "add_xp_cost", "when": {"is_interdimensional": True}},
        {"args": [0], "fn": "min_xp_cost", "when": {}},
        {"args": [27], "fn": "max_xp_cost", "when": {}},
    ]
    assert table["restricted_origins"] == ["PLAYER"]
    assert table["name_max_length"] == 128
    assert table["range_sq"] == 64
    assert table["messages"] == {**waystones.MESSAGES, **waystones.SHARESTONE_MESSAGES}
    assert table["sounds"]["activate"] == {"id": "random.levelup", "volume": 0.2, "pitch": 1.0}
    text = (tree / DATA).read_text()
    assert "WaystonesConfigData.java#L17-L26" in text
    assert "left out: [source_is_inventory_button] add_cooldown(inventory_button, 300) (never applies here)" in text
    assert result.stations["waystones:waystones"]["converted"] == 2
    assert result.stations["waystones:sharestones"] == {
        "converted": 1, "residue": 0, "data": "scripts/portkit/data/waystones_waystone.js",
        "block": "waystones:orange_sharestone"}


def test_block_has_facing_and_half_with_a_box_and_loot_per_half(converted):
    result, tree = converted
    block = _block(tree, "waystone")
    assert block["description"]["states"] == {"waystones:half": ["lower", "upper"]}
    assert block["description"]["traits"]["minecraft:placement_direction"]["y_rotation_offset"] == 180
    comps = block["components"]
    assert comps["waystones:portkit_waystone"] == {}
    assert comps["minecraft:loot"] == "loot_tables/blocks/waystone.json"
    perms = block["permutations"]
    assert len(perms) == 8
    for perm in perms:
        lower = "== 'lower'" in perm["condition"]
        c = perm["components"]
        assert c["minecraft:loot"] == ("loot_tables/blocks/waystone.json" if lower else "loot_tables/empty.json")
        assert c["minecraft:collision_box"] == (waystones.LOWER_BOX if lower else waystones.UPPER_BOX)
        assert "minecraft:transformation" in c
    assert not any(u.source.endswith("blockstates/waystone.json") for u in result.unhandled)
    assert json.loads((tree / "behavior_pack/blocks/waystone.json").read_text())["format_version"] == "1.21.90"


def test_loot_drops_the_block_from_the_lower_half_only(converted):
    result, tree = converted
    loot = json.loads((tree / "behavior_pack/loot_tables/blocks/waystone.json").read_text())
    assert loot == {"pools": [{"rolls": 1, "entries": [{"type": "item", "name": "waystones:waystone",
                                                         "functions": [{"function": "explosion_decay"}]}]}]}
    assert not any(u.source.endswith("loot_table/blocks/waystone.json") for u in result.unhandled)
    assert any("Silk touch drops a plain waystone" in n for n in result.notes)


def test_other_waystones_blocks_keep_their_residue(converted):
    result, tree = converted
    assert not (tree / "behavior_pack/blocks/white_sharestone.json").exists()
    assert any(u.source.endswith("blockstates/white_sharestone.json") and u.kind == "block" for u in result.unhandled)
    assert any(u.source.endswith("loot_table/blocks/white_sharestone.json") and u.kind == "loot"
               for u in result.unhandled)


def test_runtime_texts_ship_under_their_java_key_in_every_locale(converted):
    result, tree = converted
    en = (tree / "resource_pack/texts/en_US.lang").read_text()
    for key in waystones.MESSAGES.values():
        assert f"\n{key}=" in f"\n{en}"
    assert "chat.waystones.scroll_bound" not in en
    # Java fills %d like %s; Bedrock documents %s slots, so the slot is written as one.
    assert "gui.waystones.waystone_selection.xp_requirement=Experience Cost: %s" in en
    de = (tree / "resource_pack/texts/de_DE.lang").read_text()
    assert "chat.waystones.waystone_activated=Wegstein aktiviert: %s" in de


def test_manifest_declares_server_ui_and_main_wires_the_table(converted):
    _, tree = converted
    manifest = json.loads((tree / "behavior_pack/manifest.json").read_text())
    deps = [d.get("module_name") for d in manifest["dependencies"]]
    assert "@minecraft/server" in deps and "@minecraft/server-ui" in deps
    assert {"module_name": "@minecraft/server-ui", "version": "2.0.0"} in manifest["dependencies"]
    main = (tree / "behavior_pack/scripts/portkit/main.js").read_text()
    assert 'import { registerWaystones } from "./waystone.js";' in main
    for name in ("waystone.js", "waystone_core.js", "station_storage.js"):
        assert (tree / "behavior_pack/scripts/portkit" / name).is_file()


def test_another_version_gets_no_runtime(tmp_path):
    result = convert(_waystones_mod(tmp_path, version="21.1.45"), tmp_path / "out", emit_addon=False)
    tree = tmp_path / "out"
    assert not (tree / DATA).exists()
    assert not (tree / "behavior_pack/blocks/waystone.json").exists()
    assert any(u.source.endswith("blockstates/waystone.json") and u.kind == "block" for u in result.unhandled)
    assert "chat.waystones.waystone_activated" not in (tree / "resource_pack/texts/en_US.lang").read_text()


def test_unreadable_loot_leaves_that_waystone_inert(tmp_path):
    loot = {"mossy_waystone": _loot("mossy_waystone", {"function": "minecraft:set_count", "count": 2})}
    result = convert(_waystones_mod(tmp_path, loot=loot), tmp_path / "out", emit_addon=False)
    table = _table(tmp_path / "out")
    assert table["blocks"] == ["waystones:orange_portstone", "waystones:orange_sharestone", "waystones:waystone",
                               "waystones:white_portstone"]
    residue = [u for u in result.unhandled if u.kind == waystones.RESIDUE_KIND]
    assert len(residue) == 1 and residue[0].source.endswith("mossy_waystone.json")
    assert "silk-touch copy" in residue[0].reason
    assert any("waystones:mossy_waystone: places but does nothing" in n for n in result.notes)


def test_missing_lang_key_means_no_runtime(tmp_path):
    lang = {k: v for k, v in LANG.items() if k != "chat.waystones.not_enough_xp"}
    result = convert(_waystones_mod(tmp_path, lang=lang), tmp_path / "out", emit_addon=False)
    assert not (tmp_path / "out" / DATA).exists()
    reasons = [u.reason for u in result.unhandled if u.kind == waystones.RESIDUE_KIND]
    assert len(reasons) == 5 and all("chat.waystones.not_enough_xp" in r for r in reasons)


def test_requirements_parse_like_waystones():
    kept, dropped = requirements(DEFAULTS, True, True)
    assert [m["fn"] for m in kept] == ["scaled_add_xp_cost", "add_xp_cost", "min_xp_cost", "max_xp_cost"]
    assert len(dropped) == 5
    # enableCosts off: no xp modifier at all.
    kept, dropped = requirements(DEFAULTS, False, True)
    assert kept == [] and len(dropped) == 9
    # A line that can never apply here is left out whatever it does.
    kept, dropped = requirements(["[source_is_scroll] add_level_cost(5)"], True, True)
    assert kept == [] and dropped == ["[source_is_scroll] add_level_cost(5) (never applies here)"]
    # Namespaced ids and negations of fixed conditions.
    kept, _ = requirements(["[waystones:source_is_not_warp_plate] waystones:add_xp_cost(3)"], True, True)
    assert kept == [{"when": {}, "fn": "add_xp_cost", "args": [3]}]
    # Contradictory dynamic conditions never apply.
    kept, dropped = requirements(["[is_interdimensional, is_not_interdimensional] add_xp_cost(3)"], True, True)
    assert kept == [] and dropped


@pytest.mark.parametrize("line, why", [
    ("[is_with_pets] add_xp_cost(3)", "condition"),
    ("add_level_cost(3)", "function"),
    ("add_cooldown(warp, 10)", "cooldowns have no runtime"),
    ("scaled_add_xp_cost(leashed, 1)", "variable"),
    ("[source_name_equals(Home)] add_xp_cost(3)", "takes arguments"),
    ("othermod:add_xp_cost(3)", "not a Waystones requirement id"),
])
def test_requirements_without_a_runtime_refuse(line, why):
    with pytest.raises(waystones._Refuse, match=why):
        requirements([line], True, True)


def test_output_is_deterministic(tmp_path):
    convert(_waystones_mod(tmp_path), tmp_path / "a", emit_addon=False)
    convert(_waystones_mod(tmp_path), tmp_path / "b", emit_addon=False)
    assert (tmp_path / "a" / DATA).read_bytes() == (tmp_path / "b" / DATA).read_bytes()


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_runtime_under_node(converted):
    _, tree = converted
    js = ROOT / "tests" / "js"
    for env in ({}, {"PORTKIT_WAYSTONE_TABLE": str(tree / DATA)}):
        proc = subprocess.run(
            ["node", "--import", str(js / "register.mjs"), "--test", str(js / "waystone.test.mjs")],
            capture_output=True, text=True, timeout=120, env={"PATH": os.environ["PATH"], **env},
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr


def test_agent_skips_waystone_residue():
    from portkit.agent.residue import SKIP_KINDS

    assert waystones.RESIDUE_KIND in SKIP_KINDS


# -- sharestones --------------------------------------------------------------


def test_sharestone_block_is_full_box_per_half_with_loot_on_the_lower(converted):
    result, tree = converted
    block = _block(tree, "orange_sharestone")
    assert block["description"]["states"] == {"waystones:half": ["lower", "upper"]}
    assert block["components"]["waystones:portkit_waystone"] == {}
    for perm in block["permutations"]:
        lower = "== 'lower'" in perm["condition"]
        c = perm["components"]
        assert c["minecraft:collision_box"] == waystones.SHARESTONE_BOX
        assert c["minecraft:loot"] == ("loot_tables/blocks/orange_sharestone.json" if lower
                                       else "loot_tables/empty.json")
    loot = json.loads((tree / "behavior_pack/loot_tables/blocks/orange_sharestone.json").read_text())
    assert loot["pools"][0]["entries"][0]["name"] == "waystones:orange_sharestone"
    assert not any("orange_sharestone" in u.source for u in result.unhandled)
    assert any("sharestone block(s) work through the same runtime" in n for n in result.notes)
    assert "SharestoneBlock.java#L40-L52" in (tree / DATA).read_text()


def test_sharestone_texts_ship(converted):
    _, tree = converted
    en = (tree / "resource_pack/texts/en_US.lang").read_text()
    for key in waystones.SHARESTONE_MESSAGES.values():
        assert f"\n{key}=" in f"\n{en}"


def test_a_missing_sharestone_text_leaves_only_the_sharestones_inert(tmp_path):
    lang = {k: v for k, v in LANG.items() if k != "container.waystones.sharestone"}
    result = convert(_waystones_mod(tmp_path, lang=lang), tmp_path / "out", emit_addon=False)
    table = _table(tmp_path / "out")
    assert table["blocks"] == ["waystones:mossy_waystone", "waystones:waystone", "waystones:white_portstone"]
    assert set(table["networks"]) == {"waystones:waystone"}
    assert "none_shared" not in table["messages"]
    residue = {u.source.rsplit("/", 1)[-1]: u.reason for u in result.unhandled if u.kind == waystones.RESIDUE_KIND}
    assert set(residue) == {"orange_sharestone.json", "orange_portstone.json"}
    assert "which a sharestone shows" in residue["orange_sharestone.json"]
    # The orange portstone lists orange sharestones: with none working, it has nothing to list.
    assert "no waystones:orange_sharestone block works here" in residue["orange_portstone.json"]
    assert "waystones:sharestones" in result.stations and result.stations["waystones:sharestones"]["residue"] == 1


def test_only_registered_sharestones_convert():
    # White is the one dye colour ModBlocks registers no SharestoneBlock for.
    assert len(waystones.SHARESTONE_BLOCKS) == 15 and "white_sharestone" not in waystones.SHARESTONE_BLOCKS
    assert waystones.waystone_type("orange_sharestone") == "waystones:orange_sharestone"
    assert waystones.waystone_type("mossy_waystone") == "waystones:waystone"


def test_sharestone_conditions_are_decided_for_its_colour():
    fixed = waystones.fixed_conditions("waystones:orange_sharestone")
    assert fixed["source_is_sharestone"] and fixed["target_is_sharestone"]
    assert fixed["source_is_orange_sharestone"] and fixed["target_is_orange_sharestone"]
    assert not fixed["source_is_red_sharestone"] and not fixed["target_is_waystone"]
    assert not fixed["target_is_global"]
    plain = waystones.fixed_conditions("waystones:waystone")
    assert not plain["source_is_sharestone"] and not plain["target_is_orange_sharestone"]
    lines = ["[source_is_sharestone] multiply_xp_cost(0)", "[target_is_not_orange_sharestone] add_xp_cost(5)"]
    kept, dropped = requirements(lines, True, True, "waystones:orange_sharestone")
    assert kept == [{"when": {}, "fn": "multiply_xp_cost", "args": [0.0]}]
    assert dropped == ["[target_is_not_orange_sharestone] add_xp_cost(5) (never applies here)"]
    kept, _ = requirements(lines, True, True, "waystones:red_sharestone")
    assert [m["fn"] for m in kept] == ["multiply_xp_cost", "add_xp_cost"]
    kept, _ = requirements(lines, True, True)
    assert kept == [{"when": {}, "fn": "add_xp_cost", "args": [5]}]
    with pytest.raises(waystones._Refuse):
        waystones.fixed_conditions("waystones:white_sharestone")


def test_lines_left_out_for_every_type_are_listed_once():
    from types import SimpleNamespace

    from portkit.converters.waystones import _plan

    mod = SimpleNamespace(mods={NS: "21.1.46"})
    plan = _plan(mod, ["waystones:orange_sharestone", "waystones:waystone"])
    assert plan.dropped.count("[source_is_scroll] multiply_xp_cost(0) (never applies here)") == 1
    assert not any("(from " in d for d in plan.dropped)
    assert set(plan.modifiers) == {"waystones:orange_sharestone", "waystones:waystone"}


# -- sharestone runes -----------------------------------------------------------

RUNE_FACES = ("north", "east", "south", "west")


def _rune_element(name, y0, y1, v):
    return {"name": name, "from": [0.9, y0, 0.9], "to": [15.1, y1, 15.1],
            "faces": {f: {"uv": [3.5 * i, v, 3.5 * (i + 1), v + 6.75], "texture": "#3", "tintindex": 0}
                      for i, f in enumerate(RUNE_FACES)}}


def _rune_png() -> bytes:
    from portkit.png import encode_png

    # 4x2: white, transparent, mid grey, white / transparent row.
    pixels = bytes((255, 255, 255, 255, 0, 0, 0, 0, 128, 128, 128, 255, 255, 255, 255, 255) + (0, 0, 0, 0) * 4)
    return encode_png(4, 2, pixels)


def _la_png() -> bytes:
    """A 2x1 grey+alpha PNG (colour type 4, as the jar's portstone_runes.png):
    white opaque, then grey 128 half transparent."""
    import struct
    import zlib

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = bytes((0, 255, 255, 128, 128))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 1, 8, 4, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


# Waystones 21.1.46's block/waystone_runes element (one band from 12 to 21.5
# pixels, across into the upper block; a 0-degree rotation) and
# block/portstone_runes element (lower block only).
WAYSTONE_RUNE_ELEMENT = {
    "name": "runes", "from": [2.75, 12, 2.75], "to": [13.25, 21.5, 13.25],
    "rotation": {"angle": 0, "axis": "y", "origin": [0, -0.5, 0]},
    "faces": {"north": {"uv": [2.5, 3.5, 5, 13], "texture": "#runes", "tintindex": 0},
              "east": {"uv": [5, 3.5, 7.5, 13], "texture": "#runes", "tintindex": 0},
              "south": {"uv": [7.5, 3.5, 10, 13], "texture": "#runes", "tintindex": 0},
              "west": {"uv": [0, 3.5, 2.5, 13], "texture": "#runes", "tintindex": 0}}}
PORTSTONE_RUNE_ELEMENT = {
    "name": "runes", "from": [0.9, 2.9, 0.9], "to": [15.1, 7.1, 15.1],
    "faces": {"north": {"uv": [0, 0.25, 16, 4.25], "texture": "#3", "tintindex": 0},
              "east": {"uv": [0, 4.25, 16, 8.25], "texture": "#3", "tintindex": 0},
              "south": {"uv": [0, 8.25, 16, 12.25], "texture": "#3", "tintindex": 0},
              "west": {"uv": [0, 11.75, 16, 15.75], "texture": "#3", "tintindex": 0}}}


def _with_runes(root: Path, top=(24.9, 29.1), stones=False) -> Path:
    """The sharestone rune model and texture; with ``stones`` also the
    waystone's and portstone's."""
    _write(root, f"assets/{NS}/models/block/sharestone_runes.json", {
        "textures": {"3": f"{NS}:block/sharestone_runes", "particle": f"{NS}:block/sharestone_runes"},
        "elements": [_rune_element("bottom_runes", 2.9, 7.1, 7), _rune_element("top_runes", *top, 0)]})
    _write(root, f"assets/{NS}/textures/block/sharestone_runes.png", _rune_png())
    if stones:
        _write(root, f"assets/{NS}/models/block/waystone_runes.json", {
            "ambientocclusion": False, "texture_size": [128, 32],
            "textures": {"particle": f"{NS}:block/waystone_runes", "runes": f"{NS}:block/waystone_runes"},
            "elements": [WAYSTONE_RUNE_ELEMENT]})
        _write(root, f"assets/{NS}/textures/block/waystone_runes.png", _rune_png())
        _write(root, f"assets/{NS}/models/block/portstone_runes.json", {
            "textures": {"3": f"{NS}:block/portstone_runes", "particle": f"{NS}:block/portstone_runes"},
            "elements": [PORTSTONE_RUNE_ELEMENT]})
        _write(root, f"assets/{NS}/textures/block/portstone_runes.png", _la_png())
    return root


@pytest.fixture
def runed(tmp_path):
    result = convert(_with_runes(_waystones_mod(tmp_path)), tmp_path / "out", emit_addon=False)
    return result, tmp_path / "out"


def _pixels(path: Path) -> list[tuple]:
    from portkit.png import decode_rgba

    _, _, data = decode_rgba(path.read_bytes())
    return [tuple(data[i:i + 4]) for i in range(0, len(data), 4)]


def test_dye_colours_are_cited_for_every_sharestone():
    assert set(waystones.SHARESTONE_COLORS) <= set(waystones.DYE_COLORS)
    # DyeColor.ORANGE: textureDiffuseColor 16351261, textColor 16738335 (1.21.1).
    assert waystones.DYE_COLORS["orange"] == (16351261, 16738335)
    assert waystones.DYE_COLORS["red"] == (0xB02E26, 0xFF0000)


def test_tint_multiplies_each_channel_and_keeps_alpha():
    from portkit.converters.textures import tint

    pixels = _pixels_from(tint(_rune_png(), 0xF9801D))
    assert pixels[0] == (0xF9, 0x80, 0x1D, 255)
    assert pixels[1][3] == 0
    assert pixels[2] == ((128 * 0xF9 + 127) // 255, (128 * 0x80 + 127) // 255, (128 * 0x1D + 127) // 255, 255)


def _pixels_from(data: bytes) -> list[tuple]:
    from portkit.png import decode_rgba

    _, _, raw = decode_rgba(data)
    return [tuple(raw[i:i + 4]) for i in range(0, len(raw), 4)]


def test_sharestone_runes_are_baked_in_its_dye_colours(runed):
    _, tree = runed
    textures = tree / "resource_pack/textures/blocks"
    assert _pixels(textures / "orange_sharestone_runes.png")[0] == (0xF9, 0x80, 0x1D, 255)
    assert _pixels(textures / "orange_sharestone_runes_item.png")[0] == (0xFF, 0x68, 0x1F, 255)
    terrain = json.loads((tree / "resource_pack/textures/terrain_texture.json").read_text())["texture_data"]
    assert terrain["waystones:orange_sharestone_runes"] == {"textures": "textures/blocks/orange_sharestone_runes"}
    assert "waystones:orange_sharestone_runes_item" in terrain
    # Only registered sharestones get runes (white has no SharestoneBlock).
    assert not (textures / "white_sharestone_runes.png").exists()


def test_sharestone_wears_its_runes_as_part_of_the_block(runed):
    result, tree = runed
    block = _block(tree, "orange_sharestone")
    instances = block["components"]["minecraft:material_instances"]
    assert instances["runes"] == {"texture": "waystones:orange_sharestone_runes", "render_method": "alpha_test",
                                  "face_dimming": False, "ambient_occlusion": False}
    # "*" (particles and anything unnamed) stays the stone, not the runes.
    assert instances["*"]["texture"] == "waystones:andesite_waystone"
    geo = json.loads((tree / "resource_pack/models/blocks/orange_sharestone.geo.json").read_text())
    bones = {b["name"]: b["cubes"] for b in geo["minecraft:geometry"][0]["bones"]}
    assert {"lower_runes_0", "lower_runes_180", "upper_runes_0", "upper_runes_180"} <= set(bones)
    # The top band (24.9-29.1 above the lower block) lies in the upper block.
    assert bones["upper_runes_0"][0]["origin"][1] == pytest.approx(8.9)
    assert bones["lower_runes_0"][0]["origin"][1] == pytest.approx(2.9)
    assert all(f["material_instance"] == "runes" for f in bones["lower_runes_0"][0]["uv"].values())
    # Turned half way round, the north band's texture is on the south face.
    assert bones["lower_runes_180"][0]["uv"]["south"]["uv"] == bones["lower_runes_0"][0]["uv"]["north"]["uv"]
    visibility = block["components"]["minecraft:geometry"]["bone_visibility"]
    assert "'north'" in visibility["lower_runes_180"] and "'south'" in visibility["lower_runes_180"]
    assert "'east'" in visibility["lower_runes_0"] and "'west'" in visibility["lower_runes_0"]
    assert "== 'upper'" in visibility["upper_runes_0"]
    assert any("coloured runes are drawn as Java draws them" in n for n in result.notes)
    # Without their own rune models, waystones keep their plain look.
    assert "runes" not in _block(tree, "waystone")["components"]["minecraft:material_instances"]


def test_runes_turn_as_the_java_renderer_turns_them(tmp_path):
    from portkit.model import SourceMod

    root = _waystones_mod(tmp_path)
    mod = SourceMod(root=root, namespace=NS)
    # SharestoneRenderer turns by FACING.toYRot() anticlockwise; the
    # blockstate turns north 0, east 90, south 180, west 270 clockwise.
    assert waystones._rune_turns(mod, "orange_sharestone") == {"north": 180, "east": 0, "south": 180, "west": 0}


def test_sharestone_item_shows_its_runes_in_the_item_colour(runed):
    _, tree = runed
    raw = json.loads((tree / "behavior_pack/blocks/orange_sharestone.json").read_text())
    assert tuple(int(v) for v in raw["format_version"].split(".")) >= (1, 21, 60)
    visual = raw["minecraft:block"]["components"]["minecraft:item_visual"]
    assert visual["geometry"]["identifier"] == "geometry.waystones.orange_sharestone"
    shown = {b for b, v in visual["geometry"]["bone_visibility"].items() if v == "1.0"}
    assert shown == {"lower", "lower_runes_0"}
    assert visual["material_instances"]["runes"] == {"texture": "waystones:orange_sharestone_runes_item",
                                                     "render_method": "alpha_test"}
    assert visual["material_instances"]["*"]["texture"] == "waystones:andesite_waystone"


def test_without_the_rune_model_sharestones_keep_the_plain_look(converted):
    result, tree = converted
    block = _block(tree, "orange_sharestone")
    assert "runes" not in block["components"]["minecraft:material_instances"]
    assert "minecraft:item_visual" not in block["components"]
    assert not (tree / "resource_pack/textures/blocks/orange_sharestone_runes.png").exists()
    assert any("no readable waystones:block/sharestone_runes model" in n for n in result.notes)


def _rotated_top(root: Path) -> Path:
    """The sharestone rune model with its top band across both blocks and turned."""
    path = root / f"assets/{NS}/models/block/sharestone_runes.json"
    model = json.loads(path.read_text())
    model["elements"][1]["rotation"] = {"angle": 22.5, "axis": "y", "origin": [8, 16, 8]}
    path.write_text(json.dumps(model))
    return root


def test_a_rune_band_across_two_blocks_is_cut_between_them(tmp_path):
    root = _with_runes(_waystones_mod(tmp_path), top=(14.0, 18.0))
    convert(root, tmp_path / "out", emit_addon=False)
    block = _block(tmp_path / "out", "orange_sharestone")
    assert "runes" in block["components"]["minecraft:material_instances"]
    geo = json.loads((tmp_path / "out/resource_pack/models/blocks/orange_sharestone.geo.json").read_text())
    bones = {b["name"]: b["cubes"] for b in geo["minecraft:geometry"][0]["bones"]}
    # 14-16 in the lower block (beside the bottom band), 16-18 -> 0-2 in the upper.
    assert sorted(c["origin"][1] for c in bones["lower_runes_0"]) == pytest.approx([2.9, 14.0])
    assert [c["origin"][1] for c in bones["upper_runes_0"]] == pytest.approx([0.0])
    assert [c["size"][1] for c in bones["upper_runes_0"]] == pytest.approx([2.0])


def test_a_turned_rune_band_across_two_blocks_is_not_guessed(tmp_path):
    root = _rotated_top(_with_runes(_waystones_mod(tmp_path), top=(14.0, 18.0)))
    result = convert(root, tmp_path / "out", emit_addon=False)
    block = _block(tmp_path / "out", "orange_sharestone")
    assert "runes" not in block["components"]["minecraft:material_instances"]
    assert not (tmp_path / "out/resource_pack/textures/blocks/orange_sharestone_runes.png").exists()
    assert any("every colour looks the same" in n and "top_runes lies across two blocks and cannot be cut" in n
               for n in result.notes)


def test_block_converter_refuses_an_overlay_it_cannot_place(tmp_path):
    from portkit.converters.blocks import _overlay_parts
    from portkit.model import ConversionResult, SourceMod

    root = _rotated_top(_with_runes(_waystones_mod(tmp_path), top=(14.0, 18.0)))
    mod = SourceMod(root=root, namespace=NS)
    overlay = waystones._rune_overlay(SourceMod(root=_with_runes(_waystones_mod(tmp_path / "ok")), namespace=NS),
                                      "orange_sharestone")
    parts, why = _overlay_parts(mod, ConversionResult(), overlay, ("lower", "upper"), False, {})
    assert parts is None and "top_runes lies across two blocks and cannot be cut (element is rotated)" in why
    parts, why = _overlay_parts(mod, ConversionResult(), overlay, ("lower", "upper"), True, {})
    assert parts is None and "uvlocked" in why
    parts, why = _overlay_parts(mod, ConversionResult(), overlay, ("lower", "upper"), False, {"runes": "x"})
    assert parts is None and "already has a 'runes' texture" in why


# -- waystone and portstone runes ---------------------------------------------


@pytest.fixture
def stoned(tmp_path):
    result = convert(_with_runes(_waystones_mod(tmp_path), stones=True), tmp_path / "out", emit_addon=False)
    return result, tmp_path / "out"


def _bones(tree: Path, name: str) -> dict:
    geo = json.loads((tree / f"resource_pack/models/blocks/{name}.geo.json").read_text())
    return {b["name"]: b["cubes"] for b in geo["minecraft:geometry"][0]["bones"]}


def test_waystone_rune_colours_are_its_styles():
    # WaystoneStyles L19/L21; every other style keeps WaystoneStyle's 0xFFFFFFFF.
    assert waystones.rune_colors("blackstone_waystone") == (0x993333, None)
    assert waystones.rune_colors("end_stone_waystone") == (0x7200FF, None)
    for name in waystones.WAYSTONE_BLOCKS:
        if name not in ("blackstone_waystone", "end_stone_waystone"):
            assert waystones.rune_colors(name) == (0xFFFFFF, None)
    # Portstones: DyeColor's diffuse colour on the block, text colour on the item.
    assert waystones.rune_colors("white_portstone") == (0xF9FFFE, 0xFFFFFF)
    assert waystones.rune_colors("orange_portstone") == waystones.DYE_COLORS["orange"]
    assert set(waystones.PORTSTONE_COLORS) <= set(waystones.DYE_COLORS)


def test_split_y_cuts_a_band_and_its_side_uvs():
    from portkit.converters.models import split_y

    halves, why = split_y(WAYSTONE_RUNE_ELEMENT, 16)
    assert why == ""
    below, above = halves
    assert below["from"][1] == 12 and below["to"][1] == 16
    assert above["from"][1] == 16 and above["to"][1] == 21.5
    assert "rotation" not in below and "rotation" not in above
    # v runs 3.5 (top, y 21.5) to 13 (bottom, y 12): y 16 is v 9.
    assert above["faces"]["north"]["uv"] == [2.5, 3.5, 5, 9]
    assert below["faces"]["north"]["uv"] == [2.5, 9, 5, 13]
    turned = {**WAYSTONE_RUNE_ELEMENT, "rotation": {"angle": 22.5, "axis": "y", "origin": [8, 8, 8]}}
    assert split_y(turned, 16) == (None, "element is rotated")
    assert split_y(WAYSTONE_RUNE_ELEMENT, 30)[0] is None


def test_waystone_runes_cross_into_the_upper_half_shown_by_a_state(stoned):
    result, tree = stoned
    block = _block(tree, "waystone")
    assert block["description"]["states"]["waystones:runes"] == [False, True]
    instances = block["components"]["minecraft:material_instances"]
    # White: the jar's own texture, no baked copy.
    assert instances["runes"] == {"texture": "waystones:waystone_runes", "render_method": "alpha_test",
                                  "face_dimming": False, "ambient_occlusion": False}
    assert not (tree / "resource_pack/textures/blocks/waystone_runes_item.png").exists()
    terrain = json.loads((tree / "resource_pack/textures/terrain_texture.json").read_text())["texture_data"]
    assert "waystones:waystone_runes" in terrain
    bones = _bones(tree, "waystone")
    assert [(c["origin"][1], c["size"][1]) for c in bones["lower_runes_0"]] == [(12.0, 4.0)]
    assert [(c["origin"][1], c["size"][1]) for c in bones["upper_runes_0"]] == [(0.0, 5.5)]
    visibility = block["components"]["minecraft:geometry"]["bone_visibility"]
    for bone in ("lower_runes_0", "lower_runes_180", "upper_runes_0", "upper_runes_180"):
        assert visibility[bone].endswith("&& q.block_state('waystones:runes')")
    assert "'north'" in visibility["upper_runes_180"]
    # Java's waystone item has no runes: the item is the block's default look.
    assert "minecraft:item_visual" not in block["components"]
    table = _table(tree)
    assert table["rune_state"] == "waystones:runes"
    assert table["rune_blocks"] == ["waystones:mossy_waystone", "waystones:waystone"]
    assert any("Java shows them only to a player who has activated that waystone" in n for n in result.notes)


def test_without_waystone_runes_the_table_lists_none(converted):
    result, tree = converted
    assert _table(tree)["rune_blocks"] == []
    assert "waystones:runes" not in _block(tree, "waystone")["description"]["states"]
    assert any("no readable waystones:block/waystone_runes model" in n for n in result.notes)


def test_a_coloured_waystone_style_bakes_its_runes(tmp_path):
    root = _with_runes(_waystones_mod(tmp_path), stones=True)
    _write(root, f"assets/{NS}/blockstates/blackstone_waystone.json", json.loads(
        (root / f"assets/{NS}/blockstates/waystone.json").read_text()))
    _write(root, f"data/{NS}/loot_table/blocks/blackstone_waystone.json", _loot("blackstone_waystone"))
    _write(root, f"data/{NS}/tags/block/waystones.json", {"values": [
        f"{NS}:waystone", f"{NS}:mossy_waystone", f"{NS}:blackstone_waystone"]})
    convert(root, tmp_path / "out", emit_addon=False)
    tree = tmp_path / "out"
    instances = _block(tree, "blackstone_waystone")["components"]["minecraft:material_instances"]
    assert instances["runes"]["texture"] == "waystones:blackstone_waystone_runes"
    assert _pixels(tree / "resource_pack/textures/blocks/blackstone_waystone_runes.png")[0] == (0x99, 0x33, 0x33, 255)
    assert "waystones:blackstone_waystone" in _table(tree)["rune_blocks"]


def test_portstone_runes_are_baked_in_its_dye_colours_with_the_item(stoned):
    result, tree = stoned
    textures = tree / "resource_pack/textures/blocks"
    # The jar's grey+alpha texture: white opaque, then grey 128 at alpha 128.
    pixels = _pixels(textures / "orange_portstone_runes.png")
    assert pixels[0] == (0xF9, 0x80, 0x1D, 255)
    assert pixels[1] == ((128 * 0xF9 + 127) // 255, (128 * 0x80 + 127) // 255, (128 * 0x1D + 127) // 255, 128)
    assert _pixels(textures / "orange_portstone_runes_item.png")[0] == (0xFF, 0x68, 0x1F, 255)
    assert _pixels(textures / "white_portstone_runes.png")[0] == (0xF9, 0xFF, 0xFE, 255)
    block = _block(tree, "orange_portstone")
    assert "waystones:runes" not in block["description"]["states"]
    assert block["components"]["minecraft:material_instances"]["runes"]["texture"] == "waystones:orange_portstone_runes"
    bones = _bones(tree, "orange_portstone")
    assert {"lower_runes_0", "lower_runes_180"} <= set(bones)
    assert not any(b.startswith("upper_runes") for b in bones)
    visual = block["components"]["minecraft:item_visual"]
    assert visual["material_instances"]["runes"]["texture"] == "waystones:orange_portstone_runes_item"
    assert {b for b, v in visual["geometry"]["bone_visibility"].items() if v == "1.0"} == {"lower", "lower_runes_0"}
    assert any("portstone" in n and "coloured runes are drawn as Java draws them" in n for n in result.notes)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_runtime_under_node_with_waystone_runes(stoned):
    _, tree = stoned
    js = ROOT / "tests" / "js"
    proc = subprocess.run(
        ["node", "--import", str(js / "register.mjs"), "--test", str(js / "waystone.test.mjs")],
        capture_output=True, text=True, timeout=120,
        env={"PATH": os.environ["PATH"], "PORTKIT_WAYSTONE_TABLE": str(tree / DATA)},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "# skipped 0" in proc.stdout


# -- portstones ---------------------------------------------------------------


def test_portstones_list_their_colours_network_or_the_waystones(converted):
    result, tree = converted
    table = _table(tree)
    # A portstone is no waystone: no type, never a target.
    assert "waystones:white_portstone" not in table["block_types"]
    assert table["portstones"] == {
        "waystones:orange_portstone": {
            "requirements": table["networks"]["waystones:orange_sharestone"]["requirements"],
            "target": "waystones:orange_sharestone", "title": "container.waystones.orange_portstone"},
        "waystones:white_portstone": {
            "requirements": table["networks"]["waystones:waystone"]["requirements"],
            "target": "waystones:waystone", "title": "container.waystones.white_portstone"},
    }
    assert result.stations["waystones:portstones"] == {
        "converted": 2, "residue": 0, "data": "scripts/portkit/data/waystones_waystone.js",
        "block": "waystones:orange_portstone, waystones:white_portstone"}
    assert any("portstone block(s) work through the same runtime" in n for n in result.notes)
    text = (tree / DATA).read_text()
    assert "PortstoneBlock.java#L133-L147" in text and "PortstoneBlock.java#L47-L107" in text


def test_portstone_boxes_follow_the_north_shapes_turned_with_the_block(converted):
    result, tree = converted
    block = _block(tree, "orange_portstone")
    assert block["description"]["states"] == {"waystones:half": ["lower", "upper"]}
    assert block["components"]["waystones:portkit_waystone"] == {}
    turns = {"north": 0, "east": -90, "south": 180, "west": 90}
    assert len(block["permutations"]) == 8
    for perm in block["permutations"]:
        lower = "== 'lower'" in perm["condition"]
        c = perm["components"]
        facing = perm["condition"].split("== '", 1)[1].split("'", 1)[0]
        assert c["minecraft:transformation"] == {"rotation": [0, turns[facing], 0]}
        box = waystones.PORTSTONE_LOWER_BOX if lower else waystones.PORTSTONE_UPPER_BOX
        assert c["minecraft:collision_box"] == box and c["minecraft:selection_box"] == box
        assert c["minecraft:loot"] == ("loot_tables/blocks/orange_portstone.json" if lower
                                       else "loot_tables/empty.json")
    # North UPPER_SHAPES: x 3-13, y 0-7, z 7-13, centred on x and z.
    assert waystones.PORTSTONE_UPPER_BOX == {"origin": [-5, 0, -1], "size": [10, 7, 6]}
    loot = json.loads((tree / "behavior_pack/loot_tables/blocks/white_portstone.json").read_text())
    assert loot["pools"][0]["entries"][0]["name"] == "waystones:white_portstone"
    assert not any("portstone" in u.source and not u.source.endswith("models/item/portstone.json")
                   for u in result.unhandled)


def test_portstone_texts_ship_but_not_the_tooltip(converted):
    _, tree = converted
    en = (tree / "resource_pack/texts/en_US.lang").read_text()
    assert "\ncontainer.waystones.white_portstone=Portstone" in f"\n{en}"
    assert "\ncontainer.waystones.orange_portstone=Orange Portstone" in f"\n{en}"
    assert "tooltip.waystones.portstone" not in en


def test_a_missing_portstone_title_leaves_only_that_portstone_inert(tmp_path):
    lang = {k: v for k, v in LANG.items() if k != "container.waystones.white_portstone"}
    result = convert(_waystones_mod(tmp_path, lang=lang), tmp_path / "out", emit_addon=False)
    table = _table(tmp_path / "out")
    assert list(table["portstones"]) == ["waystones:orange_portstone"]
    residue = [u for u in result.unhandled if u.kind == waystones.RESIDUE_KIND]
    assert len(residue) == 1 and residue[0].source.endswith("white_portstone.json")
    assert "container.waystones.white_portstone" in residue[0].reason
    assert result.stations["waystones:portstones"]["residue"] == 1


def test_only_registered_portstones_and_their_targets():
    assert len(waystones.PORTSTONE_BLOCKS) == 16 and waystones.PORTSTONE_BLOCKS[0] == "white_portstone"
    assert waystones.portstone_target("white_portstone") == "waystones:waystone"
    assert waystones.portstone_target("light_blue_portstone") == "waystones:light_blue_sharestone"
    assert waystones.portstone_keys("white_portstone") == {
        "container.waystones.white_portstone", "gui.waystones.waystone_selection.no_waystones_activated"}
    assert waystones.portstone_keys("red_portstone") == {
        "container.waystones.red_portstone", "gui.waystones.waystone_selection.no_sharestones_available"}


def test_portstone_conditions_have_no_source_waystone():
    fixed = waystones.fixed_conditions("waystones:waystone", portstone=True)
    assert fixed["source_is_portstone"] and fixed["target_is_waystone"]
    assert not fixed["source_is_waystone"] and not fixed["source_is_sharestone"]
    shared = waystones.fixed_conditions("waystones:orange_sharestone", portstone=True)
    assert shared["source_is_portstone"] and shared["target_is_orange_sharestone"]
    assert not shared["source_is_orange_sharestone"] and not shared["source_is_sharestone"]
    lines = ["[source_is_portstone] add_xp_cost(5)", "[source_is_waystone] add_xp_cost(7)"]
    kept, dropped = requirements(lines, True, True, "waystones:waystone", portstone=True)
    assert kept == [{"when": {}, "fn": "add_xp_cost", "args": [5]}]
    assert dropped == ["[source_is_waystone] add_xp_cost(7) (never applies here)"]
    # The defaults have no portstone line: a portstone pays what a waystone does.
    assert requirements(DEFAULTS, True, True, portstone=True)[0] == requirements(DEFAULTS, True, True)[0]


def test_a_portstone_only_line_is_listed_per_variant():
    from types import SimpleNamespace

    from portkit.converters.waystones import _plan

    mod = SimpleNamespace(mods={NS: "21.1.46"})
    plan = _plan(mod, ["waystones:waystone"], ["waystones:waystone"])
    assert plan.portstone_modifiers["waystones:waystone"] == plan.modifiers["waystones:waystone"]
    assert plan.dropped.count("[source_is_scroll] multiply_xp_cost(0) (never applies here)") == 1


# -- warp plates --------------------------------------------------------------

PLATE_LANG = {
    "block.waystones.warp_plate": "Warp Plate",
    "chat.waystones.warp_plate_has_no_target": "This warp plate is not bound to another warp plate yet.",
    "chat.waystones.warp_plate_has_invalid_target": "The shard inside this warp plate has lost its attunement.",
    "item.waystones.dormant_shard": "Dormant Shard",
    "item.waystones.attuned_shard": "Attuned Shard",
    "item.waystones.crumbling_attuned_shard": "Crumbling Attuned Shard",
    "item.waystones.deepslate_shard": "Deepslate Shard",
}
SHARDS = ("dormant_shard", "attuned_shard", "crumbling_attuned_shard", "deepslate_shard")
PLATE_STATUSES = ("attuning", "empty", "idle", "locked", "redstone_disabled", "warping", "warping_invalid")


def _plate_face(texture, tint=False):
    return {"uv": [0, 0, 10, 10], "texture": texture, **({"tintindex": 1} if tint else {})}


def _plate_loot(extra_condition=None):
    silk = [{"condition": "minecraft:match_tool", "predicate": {"predicates": {"minecraft:enchantments": [
        {"enchantments": "minecraft:silk_touch", "levels": {"min": 1}}]}}}]
    conditions = [{"condition": "minecraft:survives_explosion"}]
    if extra_condition:
        conditions.append(extra_condition)
    return {"type": "minecraft:block", "pools": [{
        "bonus_rolls": 0.0, "conditions": conditions,
        "entries": [{"type": "minecraft:item", "name": f"{NS}:warp_plate"}],
        "functions": [{"conditions": silk, "function": "minecraft:copy_components", "source": "block_entity"},
                      {"conditions": silk, "function": "minecraft:copy_name", "source": "block_entity"}],
        "rolls": 1.0}]}


def _with_warp_plate(root: Path, lang_drop=(), shards=SHARDS, loot=None) -> Path:
    """Waystones' warp plate as the jar has it (WarpPlateBlock; models
    warp_plate/_empty/_locked, the tinted rune element in warp_plate), its
    shard items and item tags."""
    png = PNG.read_bytes()
    base = {"name": "base", "from": [0, 0, 0], "to": [16, 1, 16],
            "faces": {f: _plate_face("#base") for f in FACES}}
    border = {"name": "border", "from": [3, 1, 3], "to": [13, 2, 13],
              "faces": {f: _plate_face("#texture") for f in FACES}}
    tinted = {"name": "tinted", "from": [5, 2.01, 5], "to": [11, 2.02, 11],
              "faces": {"up": _plate_face("#3", tint=True)}}
    lock = {"name": "lock", "from": [5, 2.01, 5], "to": [11, 2.02, 11], "faces": {"up": _plate_face("#3")}}
    textures = {"particle": f"{NS}:block/warp_plate", "texture": f"{NS}:block/warp_plate",
                "base": f"{NS}:block/warp_plate_base"}
    _write(root, f"assets/{NS}/models/block/warp_plate.json", {
        "parent": "block/block", "textures": {**textures, "3": f"{NS}:block/warp_plate_runes"},
        "elements": [base, border, tinted]})
    _write(root, f"assets/{NS}/models/block/warp_plate_empty.json", {
        "parent": "block/block", "textures": textures, "elements": [base]})
    _write(root, f"assets/{NS}/models/block/warp_plate_locked.json", {
        "parent": "block/block", "textures": {**textures, "3": f"{NS}:block/warp_plate_lock"},
        "elements": [base, border, lock]})
    models = {"attuning": "warp_plate", "empty": "warp_plate_empty", "idle": "warp_plate", "locked": "warp_plate_locked",
              "redstone_disabled": "warp_plate", "warping": "warp_plate", "warping_invalid": "warp_plate"}
    _write(root, f"assets/{NS}/blockstates/warp_plate.json", {"variants": {
        f"status={k}": {"model": f"{NS}:block/{v}"} for k, v in models.items()}})
    for texture in ("warp_plate", "warp_plate_base", "warp_plate_lock", "warp_plate_runes"):
        _write(root, f"assets/{NS}/textures/block/{texture}.png", png)
    _write(root, f"data/{NS}/loot_table/blocks/warp_plate.json", loot or _plate_loot())
    for name in shards:
        _write(root, f"assets/{NS}/models/item/{name}.json",
               {"parent": "minecraft:item/generated", "textures": {"layer0": f"{NS}:item/{name}"}})
        _write(root, f"assets/{NS}/textures/item/{name}.png", png)
    _write(root, f"data/{NS}/tags/item/warp_shards.json", {"values": [f"{NS}:{n}" for n in SHARDS]})
    _write(root, f"data/{NS}/tags/item/single_use_warp_shards.json",
           {"values": [f"{NS}:crumbling_attuned_shard"]})
    lang = json.loads((root / f"assets/{NS}/lang/en_us.json").read_text())
    lang.update({k: v for k, v in PLATE_LANG.items() if k not in lang_drop})
    _write(root, f"assets/{NS}/lang/en_us.json", lang)
    return root


@pytest.fixture
def plated(tmp_path):
    root = _with_warp_plate(_waystones_mod(tmp_path))
    result = convert(root, tmp_path / "out", emit_addon=False)
    return result, tmp_path / "out"


def test_warp_plate_block_has_the_status_state_and_one_bone_per_model(plated):
    _, tree = plated
    block = _block(tree, "warp_plate")
    assert block["description"]["states"] == {"waystones:status": list(waystones.WARP_PLATE_STATUSES)}
    assert block["description"]["states"]["waystones:status"][0] == "empty"  # Java's default
    assert "traits" not in block["description"]  # no facing
    bones = block["components"]["minecraft:geometry"]["bone_visibility"]
    assert set(bones) == {"warp_plate", "warp_plate_empty", "warp_plate_locked"}
    assert bones["warp_plate_empty"] == "q.block_state('waystones:status') == 'empty'"
    assert bones["warp_plate_locked"] == "q.block_state('waystones:status') == 'locked'"
    for status in ("idle", "attuning", "warping", "warping_invalid", "redstone_disabled"):
        assert f"== '{status}'" in bones["warp_plate"]
    box = {"origin": [-8, 0, -8], "size": [16, 2, 16]}
    assert block["components"]["minecraft:collision_box"] == box
    assert block["components"]["minecraft:selection_box"] == box
    assert block["components"]["minecraft:tick"] == {"interval_range": [1, 1], "looping": True}
    assert block["components"][waystones.WARP_PLATE_COMPONENT] == {}
    assert waystones.COMPONENT not in block["components"]
    assert block["components"]["minecraft:loot"] == "loot_tables/blocks/warp_plate.json"
    assert "permutations" not in block


def test_warp_plate_leaves_out_the_tinted_rune_element(plated):
    result, tree = plated
    geo = json.loads((tree / "resource_pack/models/blocks/warp_plate.geo.json").read_text())
    bones = {b["name"]: b for b in geo["minecraft:geometry"][0]["bones"]}
    # base + border; the tinted element (tintindex 1) is not drawn, the lock is.
    assert len(bones["warp_plate"]["cubes"]) == 2
    assert len(bones["warp_plate_locked"]["cubes"]) == 3
    assert len(bones["warp_plate_empty"]["cubes"]) == 1
    assert any("drawn without tinted" in n for n in result.notes)


def test_warp_plate_loot_drops_the_plate_without_the_silk_copies(plated):
    _, tree = plated
    loot = json.loads((tree / "behavior_pack/loot_tables/blocks/warp_plate.json").read_text())
    assert loot == {"pools": [{"rolls": 1, "entries": [{"type": "item", "name": "waystones:warp_plate",
                                                        "functions": [{"function": "explosion_decay"}]}]}]}


def test_a_warp_plate_loot_gated_on_a_half_is_refused():
    with pytest.raises(waystones._Refuse):
        waystones._loot("x", _plate_loot({"block": "waystones:warp_plate", "condition": "minecraft:block_state_property",
                                          "properties": {"half": "lower"}}), "waystones:warp_plate", [], single=True)
    with pytest.raises(waystones._Refuse):
        # copy_name is only read for the one-block table.
        waystones._loot("x", _plate_loot(), "waystones:warp_plate", [])


def test_warp_plate_table_holds_the_cited_rules(plated):
    _, tree = plated
    table = _table(tree)
    plate = table["warp_plates"]
    assert plate["blocks"] == ["waystones:warp_plate"]
    assert "waystones:warp_plate" not in table["blocks"] and "waystones:warp_plate" not in table["block_types"]
    assert "waystones:warp_plate" not in table["networks"]
    assert plate["use_time"] == 15 and plate["cooldown"] == 20 and plate["attunement_ticks"] == 30
    assert plate["deny"] == ["minecraft:wither"]
    assert plate["shards"] == {
        "accepted": sorted(f"waystones:{n}" for n in SHARDS), "attuned": "waystones:attuned_shard",
        "dormant": "waystones:dormant_shard", "locked": "waystones:deepslate_shard",
        "single_use": ["waystones:crumbling_attuned_shard"]}
    # source_is_warp_plate multiplies the cost by 0 unconditionally.
    assert {"args": [0.0], "fn": "multiply_xp_cost", "when": {}} in plate["requirements"]
    assert table["messages"]["no_target"] == "chat.waystones.warp_plate_has_no_target"
    assert table["messages"]["invalid_target"] == "chat.waystones.warp_plate_has_invalid_target"
    assert table["sounds"]["eject"] == {"id": "mob.chicken.plop", "pitch": 1.0, "volume": 1.0}
    assert plate["error_style"] == "\u00a74"
    text = (tree / DATA).read_text()
    assert "WaystonesConfigData.java#L75" in text and "WaystonesConfigData.java#L114" in text


def test_without_a_warp_plate_the_table_has_no_plate_rules(converted):
    _, tree = converted
    table = _table(tree)
    assert "warp_plates" not in table
    assert "WaystonesConfigData.java#L75" not in (tree / DATA).read_text()


def test_shard_items_take_their_classes_stack_sizes(plated):
    _, tree = plated

    def size(name):
        body = json.loads((tree / f"behavior_pack/items/{name}.json").read_text())
        return body["minecraft:item"]["components"]["minecraft:max_stack_size"]

    assert size("attuned_shard") == 1
    assert size("crumbling_attuned_shard") == 4
    assert size("dormant_shard") == 64


def test_warp_plate_conditions_are_decided_for_a_plate_to_plate_teleport():
    fixed = waystones.fixed_conditions(waystones.WARP_PLATE_TYPE)
    assert fixed["source_is_warp_plate"] is True and fixed["target_is_warp_plate"] is True
    assert fixed["source_is_waystone"] is False and fixed["target_is_waystone"] is False
    assert fixed["target_is_global"] is False
    kept, _ = requirements(DEFAULTS, True, True, waystones.WARP_PLATE_TYPE)
    assert [m["fn"] for m in kept] == [
        "scaled_add_xp_cost", "add_xp_cost", "multiply_xp_cost", "min_xp_cost", "max_xp_cost"]


def test_a_missing_warp_plate_text_leaves_only_the_plate_inert(tmp_path):
    root = _with_warp_plate(_waystones_mod(tmp_path), lang_drop=("chat.waystones.warp_plate_has_no_target",))
    result = convert(root, tmp_path / "out", emit_addon=False)
    table = _table(tmp_path / "out")
    assert "warp_plates" not in table and table["blocks"]
    assert any(u.kind == "waystone" and u.source.endswith("warp_plate.json") and "warp_plate_has_no_target" in u.reason
               for u in result.unhandled)


def test_a_warp_plate_without_its_dormant_shard_item_stays_residue(tmp_path):
    root = _with_warp_plate(_waystones_mod(tmp_path), shards=("attuned_shard", "deepslate_shard"))
    result = convert(root, tmp_path / "out", emit_addon=False)
    assert "warp_plates" not in _table(tmp_path / "out")
    assert any(u.source.endswith("warp_plate.json") and "dormant_shard" in u.reason for u in result.unhandled)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_warp_plate_runtime_under_node(plated):
    _, tree = plated
    js = ROOT / "tests" / "js"
    for test in ("warp_plate.test.mjs", "waystone.test.mjs"):
        for env in ({}, {"PORTKIT_WAYSTONE_TABLE": str(tree / DATA)}):
            proc = subprocess.run(
                ["node", "--import", str(js / "register.mjs"), "--test", str(js / test)],
                capture_output=True, text=True, timeout=120, env={"PATH": os.environ["PATH"], **env},
            )
            assert proc.returncode == 0, test + str(env) + proc.stdout + proc.stderr


def test_a_line_only_the_warp_plate_keeps_is_listed_once():
    from types import SimpleNamespace

    from portkit.converters.waystones import _plan

    mod = SimpleNamespace(mods={NS: "21.1.46"})
    plan = _plan(mod, ["waystones:orange_sharestone", "waystones:warp_plate", "waystones:waystone"])
    plate_lines = [d for d in plan.dropped if d.startswith("[source_is_warp_plate]")]
    assert plate_lines == ["[source_is_warp_plate] multiply_xp_cost(0) (never applies here) "
                           "(from all but waystones:warp_plate)"]


# -- warp portals ---------------------------------------------------------------

PORTAL_LANG = {
    "block.waystones.warp_portal": "Warp Portal",
    "item.waystones.portal_scroll": "Portal Scroll",
    "chat.waystones.warp_portal_no_space": "There is no space to open a Warp Portal here.",
    "chat.waystones.warp_portal_attunement_lost": "This portal has closed because its target was destroyed.",
    "gui.waystones.waystone_selection.return_to_portal": "Return to Portal",
}
PORTAL_FRAMES = 2


def _portal_strip(frames=PORTAL_FRAMES, width=16, frame_height=32) -> bytes:
    """An animation strip whose every pixel says where it is: red = frame,
    green = row in the frame, blue = column, alpha 200 (translucent)."""
    from portkit.png import encode_png

    pixels = bytearray()
    for frame in range(frames):
        for row in range(frame_height):
            for col in range(width):
                pixels += bytes((frame, row, col, 200))
    return encode_png(width, frames * frame_height, bytes(pixels))


def _portal_model(uv):
    return {"render_type": "translucent", "texture_size": [16, 32],
            "textures": {"0": f"{NS}:block/warp_portal", "particle": f"{NS}:block/warp_portal"},
            "elements": [{"from": [0, 0, 7.5], "to": [16, 16, 7.5],
                          "rotation": {"angle": 0, "axis": "y", "origin": [8, 8, 7.5]},
                          "faces": {"north": {"uv": uv, "texture": "#0"}, "south": {"uv": uv, "texture": "#0"}}}]}


def _with_warp_portal(root: Path, lang_drop=(), scroll=True, meta=None, strip=None) -> Path:
    """Waystones' warp portal as the jar has it (WarpPortalBlock; models
    warp_portal_bottom/_top drawing halves of one 16 x 32 animation frame), and
    the portal scroll item."""
    _write(root, f"assets/{NS}/models/block/warp_portal_bottom.json", _portal_model([0, 8, 16, 16]))
    _write(root, f"assets/{NS}/models/block/warp_portal_top.json", _portal_model([0, 0, 16, 8]))
    _write(root, f"assets/{NS}/blockstates/warp_portal.json", {"variants": {
        f"facing={d},half={h}": {"model": f"{NS}:block/warp_portal_{'bottom' if h == 'lower' else 'top'}",
                                 **({"y": y} if y else {})}
        for d, y in TURNS for h in ("lower", "upper")}})
    tex = root / f"assets/{NS}/textures/block/warp_portal.png"
    tex.parent.mkdir(parents=True, exist_ok=True)
    tex.write_bytes(strip if strip is not None else _portal_strip())
    _write(root, f"assets/{NS}/textures/block/warp_portal.png.mcmeta",
           meta if meta is not None else {"animation": {"frametime": 3, "width": 16, "height": 32}})
    if scroll:
        _write(root, f"assets/{NS}/models/item/portal_scroll.json",
               {"parent": "minecraft:item/handheld", "textures": {"layer0": f"{NS}:item/portal_scroll"}})
        (root / f"assets/{NS}/textures/item").mkdir(parents=True, exist_ok=True)
        (root / f"assets/{NS}/textures/item/portal_scroll.png").write_bytes(PNG.read_bytes())
    lang = json.loads((root / f"assets/{NS}/lang/en_us.json").read_text())
    lang.update({k: v for k, v in PORTAL_LANG.items() if k not in lang_drop})
    _write(root, f"assets/{NS}/lang/en_us.json", lang)
    return root


@pytest.fixture
def portaled(tmp_path):
    root = _with_warp_portal(_waystones_mod(tmp_path))
    result = convert(root, tmp_path / "out", emit_addon=False)
    return result, tmp_path / "out"


def test_warp_portal_block_has_no_shape_glows_and_cannot_be_broken(portaled):
    _, tree = portaled
    block = _block(tree, "warp_portal")
    assert block["description"]["states"] == {"waystones:half": ["lower", "upper"]}
    assert block["description"]["traits"]["minecraft:placement_direction"]["y_rotation_offset"] == 180
    assert block["description"]["menu_category"] == {"category": "none"}
    components = block["components"]
    assert components["minecraft:collision_box"] is False
    assert components["minecraft:selection_box"] is False
    assert components["minecraft:light_emission"] == 10
    assert components["minecraft:destructible_by_mining"] is False
    assert components["minecraft:destructible_by_explosion"] is False
    assert components["minecraft:loot"] == "loot_tables/empty.json"
    assert components["minecraft:tick"] == {"interval_range": [1, 1], "looping": True}
    assert components[waystones.WARP_PORTAL_COMPONENT] == {}
    assert waystones.COMPONENT not in components
    # Translucent (ModRenderers L35) and each half its own flipbook.
    instances = components["minecraft:material_instances"]
    assert {spec["render_method"] for spec in instances.values()} == {"blend"}
    assert {spec["texture"] for spec in instances.values()} == {"waystones:warp_portal_bottom",
                                                                "waystones:warp_portal_top"}
    assert not (tree / "behavior_pack/loot_tables/blocks/warp_portal.json").exists()


def test_warp_portal_halves_draw_their_whole_flipbook_frame(portaled):
    _, tree = portaled
    geo = json.loads((tree / "resource_pack/models/blocks/warp_portal.geo.json").read_text())
    bones = {b["name"]: b for b in geo["minecraft:geometry"][0]["bones"]}
    instances = _block(tree, "warp_portal")["components"]["minecraft:material_instances"]
    for bone, texture in (("lower", "waystones:warp_portal_bottom"), ("upper", "waystones:warp_portal_top")):
        (cube,) = bones[bone]["cubes"]
        assert cube["size"] == [16.0, 16.0, 0.0]
        for face in ("north", "south"):
            spec = cube["uv"][face]
            assert spec["uv"] == [0.0, 0.0] and spec["uv_size"] == [16.0, 16.0]
            assert instances[spec["material_instance"]]["texture"] == texture


def test_warp_portal_texture_is_cut_into_two_flipbooks(portaled):
    from portkit.png import decode_rgba

    result, tree = portaled
    flipbooks = json.loads((tree / "resource_pack/textures/flipbook_textures.json").read_text())
    assert flipbooks == [
        {"flipbook_texture": "textures/blocks/warp_portal_bottom", "atlas_tile": "waystones:warp_portal_bottom",
         "ticks_per_frame": 3, "blend_frames": False},
        {"flipbook_texture": "textures/blocks/warp_portal_top", "atlas_tile": "waystones:warp_portal_top",
         "ticks_per_frame": 3, "blend_frames": False},
    ]
    terrain = json.loads((tree / "resource_pack/textures/terrain_texture.json").read_text())["texture_data"]
    assert terrain["waystones:warp_portal_bottom"] == {"textures": "textures/blocks/warp_portal_bottom"}
    assert "waystones:warp_portal" not in terrain
    assert not (tree / "resource_pack/textures/blocks/warp_portal.png").exists()
    for name, first_row in (("warp_portal_bottom", 16), ("warp_portal_top", 0)):
        width, height, pixels = decode_rgba((tree / f"resource_pack/textures/blocks/{name}.png").read_bytes())
        assert (width, height) == (16, 16 * PORTAL_FRAMES)
        for frame in range(PORTAL_FRAMES):
            for row in range(16):
                at = ((frame * 16 + row) * 16 + 5) * 4
                assert tuple(pixels[at:at + 4]) == (frame, first_row + row, 5, 200)
    assert not any("warp_portal" in u.source and u.kind == "texture_animation" for u in result.unhandled)


def test_warp_portal_table_holds_the_cited_rules(portaled):
    result, tree = portaled
    table = _table(tree)
    portal = table["warp_portals"]
    assert portal["blocks"] == ["waystones:warp_portal"]
    assert "waystones:warp_portal" not in table["blocks"] and "waystones:warp_portal" not in table["block_types"]
    assert portal["lifetime"] == 6000 and portal["cooldown"] == 20
    assert portal["deny"] == ["minecraft:wither"]
    assert portal["scroll"]["items"] == ["waystones:portal_scroll"]
    assert portal["scroll"]["use_time"] == 32
    assert portal["scroll"]["network"] == "waystones:waystone"
    assert portal["scroll"]["title"] == "container.waystones.waystone_selection"
    zero = {"args": [0.0], "fn": "multiply_xp_cost", "when": {}}
    # The scroll's menu: source_is_scroll multiplies by 0; through the portal it does not apply.
    assert zero in portal["scroll"]["requirements"]
    assert zero not in portal["requirements"]
    assert portal["requirements"] == table["networks"]["waystones:waystone"]["requirements"]
    assert set(portal["return_requirements"]) == {"waystones:waystone", "waystones:orange_sharestone"}
    assert portal["return_property"] == "waystones:portkit_return_portal"
    for role, key in waystones.WARP_PORTAL_MESSAGES.items():
        assert table["messages"][role] == key
    assert table["sounds"]["portal_close"] == {"id": "random.fizz", "volume": 0.5, "pitch": 1.2}
    assert table["sounds"]["portal_open"] == {"id": "portal.travel", "volume": 0.25, "pitch": 1.4}
    assert table["sounds"]["scroll_start"] == {"id": "portal.trigger", "volume": 0.1, "pitch": 2.0}
    text = (tree / DATA).read_text()
    assert "WaystonesConfigData.java#L83" in text and "WaystonesConfigData.java#L114" in text
    assert "block/entity/WarpPortalBlockEntity.java#L38" in text
    assert result.stations["waystones:warp_portals"]["converted"] == 1
    assert any("warp portal block(s) work" in n for n in result.notes)


def test_portal_scroll_has_the_glint(portaled):
    _, tree = portaled
    body = json.loads((tree / "behavior_pack/items/portal_scroll.json").read_text())
    assert body["minecraft:item"]["components"]["minecraft:glint"] is True


def test_warp_portal_texts_ship_under_their_java_keys(portaled):
    _, tree = portaled
    lang = (tree / "resource_pack/texts/en_US.lang").read_text()
    for key, text in PORTAL_LANG.items():
        if key.startswith(("chat.", "gui.")):
            assert f"{key}={text}" in lang


def test_without_a_warp_portal_the_table_has_no_portal_rules(converted):
    _, tree = converted
    assert "warp_portals" not in _table(tree)
    text = (tree / DATA).read_text()
    assert "WaystonesConfigData.java#L83" not in text and "WaystonesConfigData.java#L114" not in text


def test_a_portal_without_the_portal_scroll_stays_residue(tmp_path):
    root = _with_warp_portal(_waystones_mod(tmp_path), scroll=False)
    result = convert(root, tmp_path / "out", emit_addon=False)
    assert "warp_portals" not in _table(tmp_path / "out")
    assert any(u.kind == "waystone" and u.source.endswith("blockstates/warp_portal.json")
               and "portal_scroll" in u.reason for u in result.unhandled)


def test_a_missing_portal_text_leaves_only_the_portal_inert(tmp_path):
    root = _with_warp_portal(_waystones_mod(tmp_path), lang_drop=("chat.waystones.warp_portal_no_space",))
    result = convert(root, tmp_path / "out", emit_addon=False)
    table = _table(tmp_path / "out")
    assert "warp_portals" not in table and table["blocks"]
    assert any(u.source.endswith("blockstates/warp_portal.json") and "warp_portal_no_space" in u.reason
               for u in result.unhandled)


def test_a_portal_strip_of_another_shape_is_not_converted(tmp_path):
    root = _with_warp_portal(_waystones_mod(tmp_path), meta={"animation": {"frametime": 3}},
                             strip=_portal_strip(frames=4, frame_height=16))
    result = convert(root, tmp_path / "out", emit_addon=False)
    assert "warp_portals" not in _table(tmp_path / "out")
    assert not (tmp_path / "out/behavior_pack/blocks/warp_portal.json").exists()
    assert any(u.source.endswith("blockstates/warp_portal.json") for u in result.unhandled)


def test_portal_conditions_are_decided_per_teleport():
    through = waystones.fixed_conditions(waystones.WARP_PORTAL_TYPE)
    assert through["source_is_waystone"] is False and through["source_is_scroll"] is False
    assert through["target_is_waystone"] is True and through["target_is_warp_portal"] is False
    scroll = waystones.fixed_conditions(waystones.WAYSTONE_TYPE, scroll=True)
    assert scroll["source_is_scroll"] is True and scroll["source_is_waystone"] is False
    back = waystones.fixed_conditions("waystones:orange_sharestone", to_portal=True)
    assert back["target_is_warp_portal"] is True and back["target_is_sharestone"] is False
    assert back["target_is_orange_sharestone"] is False and back["source_is_orange_sharestone"] is True
    assert back["target_is_global"] is False
    kept, _ = requirements(DEFAULTS, True, True, waystones.WAYSTONE_TYPE, scroll=True)
    assert {"args": [0.0], "fn": "multiply_xp_cost", "when": {}} in kept


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_warp_portal_runtime_under_node(portaled):
    _, tree = portaled
    js = ROOT / "tests" / "js"
    for test in ("warp_portal.test.mjs", "waystone.test.mjs"):
        for env in ({}, {"PORTKIT_WAYSTONE_TABLE": str(tree / DATA)}):
            proc = subprocess.run(
                ["node", "--import", str(js / "register.mjs"), "--test", str(js / test)],
                capture_output=True, text=True, timeout=120, env={"PATH": os.environ["PATH"], **env},
            )
            assert proc.returncode == 0, test + str(env) + proc.stdout + proc.stderr
