"""The in-game check pack and its runner (#238), without a server."""
from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from portkit.ingame import nbt, server, testpack


def _block(path: Path, ident: str, components=None, traits=None):
    desc = {"identifier": ident}
    if traits:
        desc["traits"] = traits
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"format_version": "1.26.0", "minecraft:block": {
        "description": desc, "components": components or {}}}))


@pytest.fixture
def tree(tmp_path):
    bp = tmp_path / "tree" / "behavior_pack"
    _block(bp / "blocks" / "b.json", "demo:b")
    _block(bp / "blocks" / "a.json", "demo:a", components={
        "minecraft:block_entity": {"container": {"slot_count": 27}}})
    _block(bp / "blocks" / "pane.json", "demo:pane", traits={
        "minecraft:connection": {"enabled_states": ["minecraft:cardinal_connections"]}})
    # A block whose drop the loot converter wired (#299): four of another item.
    _block(bp / "blocks" / "root.json", "demo:root", components={
        "minecraft:loot": "loot_tables/blocks/root.json"})
    (bp / "loot_tables" / "blocks").mkdir(parents=True)
    (bp / "loot_tables" / "blocks" / "root.json").write_text(json.dumps({"pools": [{"rolls": 1, "entries": [
        {"type": "item", "name": "demo:living_root",
         "functions": [{"function": "set_count", "count": 4}, {"function": "explosion_decay"}]}]}]}))
    (bp / "blocks" / "broken.json").write_text("{not json")
    (bp / "items").mkdir()
    (bp / "items" / "i.json").write_text(json.dumps(
        {"format_version": "1.21.0", "minecraft:item": {"description": {"identifier": "demo:i"}}}))
    (bp / "manifest.json").write_text(json.dumps({"header": {"uuid": "u-bp", "version": [1, 0, 0]}}))
    rp = tmp_path / "tree" / "resource_pack"
    rp.mkdir(parents=True)
    (rp / "manifest.json").write_text(json.dumps({"header": {"uuid": "u-rp", "version": [1, 0, 0]}}))
    return tmp_path / "tree"


def test_read_checks(tree):
    checks = testpack.read_checks(tree / "behavior_pack")
    assert checks.blocks == ["demo:a", "demo:b", "demo:pane", "demo:root"]
    assert checks.items == ["demo:i"]
    assert checks.containers == {"demo:a": 27}
    assert checks.connections == ["demo:pane"]
    assert checks.drops == [{"id": "demo:root", "table": "loot_tables/blocks/root.json",
                             "expect": [{"item": "demo:living_root", "count": 4}]}]


def test_drop_checks(tmp_path):
    bp = tmp_path / "bp"
    tables = bp / "loot_tables" / "blocks"
    tables.mkdir(parents=True)

    def table(name, body):
        (tables / f"{name}.json").write_text(json.dumps(body))
        return f"loot_tables/blocks/{name}.json"

    one = lambda entry, **pool: {"pools": [{"rolls": 1, "entries": [entry], **pool}]}
    # Bedrock's vanilla empty table, named without being shipped: drops nothing.
    _block(bp / "blocks" / "a.json", "demo:a", components={"minecraft:loot": "loot_tables/empty.json"})
    # set_data keeps the id; the count defaults to 1.
    _block(bp / "blocks" / "b.json", "demo:b", components={"minecraft:loot": table("b", one(
        {"type": "item", "name": "minecraft:dirt", "functions": [{"function": "set_data", "data": 0}]}))})
    # Per-state tables (a permutation overrides minecraft:loot): not checked.
    body = {"description": {"identifier": "demo:c"}, "components": {"minecraft:loot": table("c", one(
        {"type": "item", "name": "demo:c"}))}, "permutations": [
        {"condition": "q.block_state('x') == 1", "components": {"minecraft:loot": "loot_tables/blocks/c.json"}}]}
    (bp / "blocks" / "c.json").write_text(json.dumps({"format_version": "1.26.0", "minecraft:block": body}))
    # A ranged count or two entries has no exact expectation: not checked.
    _block(bp / "blocks" / "d.json", "demo:d", components={"minecraft:loot": table("d", one(
        {"type": "item", "name": "demo:d", "functions": [{"function": "set_count", "count": {"min": 1, "max": 2}}]}))})
    _block(bp / "blocks" / "e.json", "demo:e", components={"minecraft:loot": table("e", {"pools": [
        {"rolls": 1, "entries": [{"type": "item", "name": "demo:e"}, {"type": "item", "name": "demo:x"}]}]})})
    # A table the pack doesn't ship (the validator's block.loot): not checked.
    _block(bp / "blocks" / "f.json", "demo:f", components={"minecraft:loot": "loot_tables/blocks/gone.json"})
    checks = testpack.read_checks(bp)
    assert checks.drops == [
        {"id": "demo:a", "table": "loot_tables/empty.json", "expect": []},
        {"id": "demo:b", "table": "loot_tables/blocks/b.json", "expect": [{"item": "minecraft:dirt", "count": 1}]},
    ]
    assert testpack.expected_drops({"pools": []}) == []
    assert testpack.expected_drops(one({"type": "item", "name": "x"}, conditions=[{"condition": "c"}])) is None


def test_tool_drop_checks(tmp_path):
    """#299: a match_tool-gated table is checked per tool that tells the gate apart."""
    bp = tmp_path / "bp"
    tables = bp / "loot_tables" / "blocks"
    tables.mkdir(parents=True)
    shears = {"condition": "match_tool", "minecraft:match_tool_filter_any": ["minecraft:is_shears"]}
    tier = {"condition": "match_tool", "minecraft:match_tool_filter_all": ["minecraft:is_tool", "minecraft:is_pickaxe"],
            "minecraft:match_tool_filter_any": ["minecraft:iron_tier", "minecraft:diamond_tier",
                                                "minecraft:netherite_tier"]}
    (tables / "bush.json").write_text(json.dumps({"pools": [{"rolls": 1, "entries": [
        {"type": "item", "name": "demo:bush", "conditions": [shears]}]}]}))
    (tables / "ore.json").write_text(json.dumps({"pools": [{"rolls": 1, "entries": [
        {"type": "item", "name": "demo:ore", "functions": [{"function": "explosion_decay"}], "conditions": [tier]}]}]}))
    _block(bp / "blocks" / "bush.json", "demo:bush", components={"minecraft:loot": "loot_tables/blocks/bush.json"})
    _block(bp / "blocks" / "ore.json", "demo:ore", components={"minecraft:loot": "loot_tables/blocks/ore.json"})
    checks = testpack.read_checks(bp)
    # A bare hand (and setblock's destroy, which holds no tool) gets nothing.
    assert checks.drops == [{"id": "demo:bush", "table": "loot_tables/blocks/bush.json", "expect": []},
                            {"id": "demo:ore", "table": "loot_tables/blocks/ore.json", "expect": []}]
    got = {(d["id"], d["tool"]): d["expect"] for d in checks.tool_drops}
    assert got == {
        ("demo:bush", None): [],
        ("demo:bush", "minecraft:shears"): [{"item": "demo:bush", "count": 1}],
        ("demo:ore", None): [],
        ("demo:ore", "minecraft:stone_pickaxe"): [],
        ("demo:ore", "minecraft:iron_pickaxe"): [{"item": "demo:ore", "count": 1}],
    }
    assert testpack.read_checks(bp).as_json()["tool_drops"] == checks.tool_drops


def test_write_test_pack(tree, tmp_path):
    out = tmp_path / "checks"
    testpack.write_test_pack(tree / "behavior_pack", out, "demo")
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["modules"][0]["entry"] == "scripts/ingame.js"
    assert manifest["dependencies"] == [{"module_name": "@minecraft/server", "version": "2.2.0"}]
    # Stable uuids: the same name gives the same pack.
    assert manifest == testpack.manifest("demo")
    assert manifest["header"]["uuid"] != testpack.manifest("other")["header"]["uuid"]
    data = (out / "scripts" / "data.js").read_text()
    body = json.loads(data.split("=", 1)[1].strip().rstrip(";"))
    assert body["containers"] == {"demo:a": 27}
    assert [d["id"] for d in body["drops"]] == ["demo:root"]
    for name in testpack.SCRIPT_FILES:
        assert (out / "scripts" / name).read_bytes() == (testpack.RUNTIME / name).read_bytes()


def test_fetch_needs_the_eula(tmp_path):
    with pytest.raises(server.EulaNotAccepted, match="minecraft.net/eula"):
        server.fetch(tmp_path / "bds", accept_eula=False)
    assert not (tmp_path / "bds").exists()


def test_pin_is_a_linux_release():
    assert server.BDS_URL.startswith("https://www.minecraft.net/bedrockdedicatedserver/bin-linux/")
    assert server.BDS_VERSION in server.BDS_URL


def test_set_properties():
    text = "# comment\nlevel-name=Bedrock level\ngamemode=survival\n"
    out = server.set_properties(text, {"level-name": "portkit", "allow-cheats": "true"})
    assert out == "# comment\nlevel-name=portkit\ngamemode=survival\nallow-cheats=true\n"


def test_prepare(tree, tmp_path):
    bds = tmp_path / "bds"
    bds.mkdir()
    (bds / "server.properties").write_text("level-name=Bedrock level\n")
    prepared = server.prepare(bds, tmp_path / "work", tree, "demo")
    world = prepared.root / "worlds" / server.LEVEL
    bps = json.loads((world / "world_behavior_packs.json").read_text())
    rps = json.loads((world / "world_resource_packs.json").read_text())
    assert [p["pack_id"] for p in bps] == ["u-bp", testpack.manifest("demo")["header"]["uuid"]]
    assert rps == [{"pack_id": "u-rp", "version": [1, 0, 0]}]
    assert "level-type=FLAT" in (prepared.root / "server.properties").read_text()
    assert (bds / "server.properties").read_text() == "level-name=Bedrock level\n"
    generated = server.prepare(bds, tmp_path / "work2", tree, "demo", world="default")
    assert "level-type=DEFAULT" in (generated.root / "server.properties").read_text()


LOG = """\
[2026-10-15 12:00:00:001 INFO] Starting Server
[2026-10-15 12:00:01:002 ERROR] [Blocks][error]-demo:b | minecraft:geometry | bad thing
[2026-10-15 12:00:01:003 WARN] [Json][warning]-something soft
[2026-10-15 12:00:02:004 WARN] [Scripting] PORTKIT-INGAME START {"blocks": 3, "items": 1}
[2026-10-15 12:00:02:005 WARN] [Scripting] PORTKIT-INGAME DROP {"id": "demo:root", "expect": [{"item": "demo:living_root", "count": 4}], "got": [{"item": "demo:living_root", "count": 4}]}
[2026-10-15 12:00:02:005 WARN] [Scripting] PORTKIT-INGAME FAIL {"check": "container", "id": "demo:a", "detail": "no minecraft:inventory component"}
[2026-10-15 12:00:02:006 WARN] [Scripting] PORTKIT-INGAME SUMMARY {"checks": {"place": {"run": 3, "failed": 0}}, "failed": 1}
[2026-10-15 12:00:02:007 WARN] [Scripting] PORTKIT-INGAME DONE {}
"""


def test_parse_and_verdict():
    report = server.parse(LOG.splitlines())
    assert report["done"] is True
    assert report["start"] == {"blocks": 3, "items": 1}
    assert report["failures"] == [{"check": "container", "id": "demo:a", "detail": "no minecraft:inventory component"}]
    assert report["summary"]["checks"]["place"] == {"run": 3, "failed": 0}
    assert report["drops"] == [{"id": "demo:root", "expect": [{"item": "demo:living_root", "count": 4}],
                                "got": [{"item": "demo:living_root", "count": 4}]}]
    assert len(report["content_errors"]) == 1 and "demo:b" in report["content_errors"][0]
    assert len(report["content_warnings"]) == 1  # tagged lines are not counted
    assert server.verdict(report) == ["1 failed check(s)", "1 content-log error(s)"]


def test_verdict_unfinished():
    assert server.verdict(server.parse(["[x INFO] Starting Server"])) == ["the check script never finished"]


def _level(root: dict) -> bytes:
    return nbt.write_level(10, "", root)


def test_nbt_round_trip():
    root = {
        "LevelName": (nbt.STRING, "portkit"),
        "RandomSeed": (nbt.LONG, 238),
        "abilities": (nbt.COMPOUND, {"flySpeed": (nbt.FLOAT, 0.5), "op": (nbt.BYTE, 0)}),
        "lastOpenedWithVersion": (nbt.LIST, (nbt.INT, [1, 26, 52, 3, 0])),
        "arr": (nbt.INT_ARRAY, [1, -2]),
        "longs": (nbt.LONG_ARRAY, [3]),
        "bytes": (nbt.BYTE_ARRAY, b"\x01\x02"),
        "d": (nbt.DOUBLE, 1.5),
        "s": (nbt.SHORT, -3),
    }
    data = _level(root)
    assert struct.unpack_from("<ii", data) == (10, len(data) - 8)
    assert nbt.read_level(data) == (10, "", root)
    assert _level(nbt.read_level(data)[2]) == data


def test_with_experiments_keeps_everything_else():
    root = {"LevelName": (nbt.STRING, "portkit"),
            "experiments": (nbt.COMPOUND, {"gametest": (nbt.BYTE, 0)})}
    _, _, out = nbt.read_level(nbt.with_experiments(_level(root), ["upcoming_creator_features"]))
    assert out["LevelName"] == (nbt.STRING, "portkit")
    exp = out["experiments"][1]
    assert exp["upcoming_creator_features"] == (nbt.BYTE, 1)
    assert exp["gametest"] == (nbt.BYTE, 0)
    assert exp["experiments_ever_used"] == (nbt.BYTE, 1)
    assert exp["saved_with_toggled_experiments"] == (nbt.BYTE, 1)


def test_bad_level_header():
    with pytest.raises(ValueError, match="header"):
        nbt.read_level(struct.pack("<ii", 10, 99) + b"\x0a")


def test_cli(tree, tmp_path, capsys):
    from portkit.cli import main

    assert main(["ingame", "fetch-server", "--dir", str(tmp_path / "bds")]) == 2
    assert "--accept-eula" in capsys.readouterr().err
    assert main(["ingame", "pack", "--tree", str(tmp_path / "nowhere")]) == 2
    assert main(["ingame", "run", "--tree", str(tree)]) == 2
    out = tmp_path / "checks"
    assert main(["ingame", "pack", "--tree", str(tree), "--out", str(out), "--name", "demo"]) == 0
    assert "4 blocks, 1 items, 1 containers, 1 connection blocks, 1 drops, 0 tool drops" in capsys.readouterr().out
    assert (out / "scripts" / "data.js").exists()


def test_paired_checks(tmp_path):
    """#296: blocks on the multi_block trait; a door names its open/powered states."""
    bp = tmp_path / "bp"
    multi = {"minecraft:multi_block": {"enabled_states": ["minecraft:multi_block_part"], "direction": "up", "parts": 2}}
    door = {"format_version": "1.26.40", "minecraft:block": {
        "description": {"identifier": "demo:door", "traits": multi,
                        "states": {"demo:hinge": ["left", "right"], "demo:open": [False, True],
                                   "demo:powered": [False, True]}},
        "components": {"demo:portkit_door": {}, "minecraft:redstone_consumer": {"min_power": 0}}}}
    (bp / "blocks").mkdir(parents=True)
    (bp / "blocks" / "door.json").write_text(json.dumps(door))
    _block(bp / "blocks" / "plant.json", "demo:plant", traits=multi)
    _block(bp / "blocks" / "lootless.json", "demo:odd", traits=multi,
           components={"minecraft:loot": "loot_tables/blocks/gone.json"})
    _block(bp / "blocks" / "down.json", "demo:down", traits={"minecraft:multi_block": {"direction": "down", "parts": 2}})
    _block(bp / "blocks" / "plain.json", "demo:plain")
    checks = testpack.read_checks(bp)
    assert checks.paired == [
        {"id": "demo:door", "parts": 2, "expect": [{"item": "demo:door", "count": 1}],
         "door": {"open": "demo:open", "powered": "demo:powered"}},
        {"id": "demo:odd", "parts": 2, "expect": None, "door": None},
        {"id": "demo:plant", "parts": 2, "expect": [{"item": "demo:plant", "count": 1}], "door": None},
    ]
    assert testpack.read_checks(bp).as_json()["paired"] == checks.paired
    report = server.parse(['[x] PORTKIT-INGAME PAIRED {"id": "demo:door", "lower_only": {}}'])
    assert report["paired"] == [{"id": "demo:door", "lower_only": {}}]


def test_trapdoor_checks(tmp_path):
    """#296: a block carrying the portkit trapdoor component names its open/powered states."""
    bp = tmp_path / "bp"
    states = {"demo:open": [False, True], "demo:powered": [False, True]}
    (bp / "blocks").mkdir(parents=True)
    for name, components in (("trap", {"demo:portkit_trapdoor": {}}),
                             ("lost", {"demo:portkit_trapdoor": {}, "minecraft:loot": "loot_tables/blocks/gone.json"})):
        (bp / "blocks" / f"{name}.json").write_text(json.dumps({"format_version": "1.26.0", "minecraft:block": {
            "description": {"identifier": f"demo:{name}", "states": states},
            "components": {**components, "minecraft:redstone_consumer": {"min_power": 0}}}}))
    (bp / "blocks" / "stateless.json").write_text(json.dumps({"format_version": "1.26.0", "minecraft:block": {
        "description": {"identifier": "demo:stateless"}, "components": {"demo:portkit_trapdoor": {}}}}))
    _block(bp / "blocks" / "plain.json", "demo:plain")
    checks = testpack.read_checks(bp)
    want = {"open": "demo:open", "powered": "demo:powered"}
    assert checks.trapdoors == [
        {"id": "demo:lost", "states": want, "expect": None},
        {"id": "demo:trap", "states": want, "expect": [{"item": "demo:trap", "count": 1}]},
    ]
    assert checks.as_json()["trapdoors"] == checks.trapdoors
    report = server.parse(['[x] PORTKIT-INGAME TRAPDOOR {"id": "demo:trap", "drop": []}'])
    assert report["trapdoors"] == [{"id": "demo:trap", "drop": []}]


def test_plate_checks(tmp_path):
    """#296: a block carrying the portkit pressure plate component, with its table entry."""
    bp = tmp_path / "bp"
    (bp / "blocks").mkdir(parents=True)
    for name in ("plate", "stray"):
        (bp / "blocks" / f"{name}.json").write_text(json.dumps({"format_version": "1.21.130", "minecraft:block": {
            "description": {"identifier": f"demo:{name}", "states": {"demo:powered": [False, True]}},
            "components": {"demo:portkit_pressure_plate": {}}}}))
    data = bp / "scripts" / "portkit" / "data"
    data.mkdir(parents=True)
    (data / "demo_pressure_plates.js").write_text(
        "// table\nexport default " + json.dumps({"plates": {"demo:plate": {"mobs_only": True}}}) + ";\n")
    _block(bp / "blocks" / "plain.json", "demo:plain")
    checks = testpack.read_checks(bp)
    assert checks.plates == [{"id": "demo:plate", "powered": "demo:powered", "mobs_only": True,
                              "expect": [{"item": "demo:plate", "count": 1}]}]
    assert checks.as_json()["plates"] == checks.plates
    report = server.parse(['[x] PORTKIT-INGAME PLATE {"id": "demo:plate", "drop": []}'])
    assert report["plates"] == [{"id": "demo:plate", "drop": []}]
