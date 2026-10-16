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
    assert checks.blocks == ["demo:a", "demo:b", "demo:pane"]
    assert checks.items == ["demo:i"]
    assert checks.containers == {"demo:a": 27}
    assert checks.connections == ["demo:pane"]


def test_write_test_pack(tree, tmp_path):
    out = tmp_path / "checks"
    testpack.write_test_pack(tree / "behavior_pack", out, "demo")
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["modules"][0]["entry"] == "scripts/ingame.js"
    assert manifest["dependencies"] == [{"module_name": "@minecraft/server", "version": "2.0.0"}]
    # Stable uuids: the same name gives the same pack.
    assert manifest == testpack.manifest("demo")
    assert manifest["header"]["uuid"] != testpack.manifest("other")["header"]["uuid"]
    data = (out / "scripts" / "data.js").read_text()
    body = json.loads(data.split("=", 1)[1].strip().rstrip(";"))
    assert body["containers"] == {"demo:a": 27}
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


LOG = """\
[2026-10-15 12:00:00:001 INFO] Starting Server
[2026-10-15 12:00:01:002 ERROR] [Blocks][error]-demo:b | minecraft:geometry | bad thing
[2026-10-15 12:00:01:003 WARN] [Json][warning]-something soft
[2026-10-15 12:00:02:004 WARN] [Scripting] PORTKIT-INGAME START {"blocks": 3, "items": 1}
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
