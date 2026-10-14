"""Waystones: waystone blocks + a fixed Script API teleport runtime (#178).

The converter writes the ten waystone blocks (facing x a custom ``half`` state,
a box per half, minecraft:loot on the lower half only), their Bedrock loot
tables, scripts/portkit/data/waystones_waystone.js (the warpRequirements
default decided for this runtime, the texts, sounds and rules) and ships the
fixed runtime (portkit/runtime/waystone*.js), with a @minecraft/server-ui
dependency in the behavior pack manifest.

Offline: a Waystones-shaped Fabric mod with two waystones, an orange
sharestone and a white "sharestone" (Waystones registers none: white is the
one dye colour without a SharestoneBlock).
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
}


def _waystones_mod(tmp_path, version="21.1.46", loot=None, lang=None) -> Path:
    root = tmp_path / "ws"
    png = PNG.read_bytes()
    _write(root, "fabric.mod.json", {"schemaVersion": 1, "id": NS, "version": version,
                                     "depends": {"minecraft": "1.21.1", "fabricloader": ">=0.15"}})
    blocks = {"waystone": "andesite_waystone", "mossy_waystone": "mossy_andesite_waystone",
              "white_sharestone": "andesite_waystone", "orange_sharestone": "andesite_waystone"}
    _write(root, f"assets/{NS}/models/block/waystone_bottom.json", {
        "textures": {"particle": "block/polished_andesite", "texture": f"{NS}:block/andesite_waystone"},
        "elements": [_element("base", 0, 3, 0), _element("pillar", 3, 16, 3)]})
    _write(root, f"assets/{NS}/models/block/waystone_top.json", {
        "textures": {"particle": "block/polished_andesite", "texture": f"{NS}:block/andesite_waystone"},
        "elements": [_element("pillar", 0, 12, 3), _element("cap", 12, 16, 4)]})
    for name, texture in blocks.items():
        stem = "sharestone" if name.endswith("_sharestone") else name
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
    assert table["blocks"] == ["waystones:mossy_waystone", "waystones:orange_sharestone", "waystones:waystone"]
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
    assert table["blocks"] == ["waystones:orange_sharestone", "waystones:waystone"]
    residue = [u for u in result.unhandled if u.kind == waystones.RESIDUE_KIND]
    assert len(residue) == 1 and residue[0].source.endswith("mossy_waystone.json")
    assert "silk-touch copy" in residue[0].reason
    assert any("waystones:mossy_waystone: places but does nothing" in n for n in result.notes)


def test_missing_lang_key_means_no_runtime(tmp_path):
    lang = {k: v for k, v in LANG.items() if k != "chat.waystones.not_enough_xp"}
    result = convert(_waystones_mod(tmp_path, lang=lang), tmp_path / "out", emit_addon=False)
    assert not (tmp_path / "out" / DATA).exists()
    reasons = [u.reason for u in result.unhandled if u.kind == waystones.RESIDUE_KIND]
    assert len(reasons) == 3 and all("chat.waystones.not_enough_xp" in r for r in reasons)


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
    assert table["blocks"] == ["waystones:mossy_waystone", "waystones:waystone"]
    assert set(table["networks"]) == {"waystones:waystone"}
    assert "none_shared" not in table["messages"]
    residue = [u for u in result.unhandled if u.kind == waystones.RESIDUE_KIND]
    assert len(residue) == 1 and residue[0].source.endswith("orange_sharestone.json")
    assert "which a sharestone shows" in residue[0].reason
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
