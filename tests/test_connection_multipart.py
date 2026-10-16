"""Multiparts keyed only on north/east/south/west booleans (#56): panes, bars,
hedges, lattices. One bone per part, shown through the connection trait."""
import json

from portkit.converters import blocks, models
from portkit.data import models as model_data
from portkit.model import SourceMod

CONN = "q.block_state('minecraft:connection_{}')"


def _box(start, end, texture="#pane"):
    return {"from": start, "to": end,
            "faces": {f: {"texture": texture, "uv": models.auto_uv(f, start, end)}
                      for f in ("down", "up", "north", "south", "west", "east")}}


POST = {"textures": {"pane": "examplemod:block/glass", "edge": "examplemod:block/edge"},
        "elements": [_box([7, 0, 7], [9, 16, 9], "#edge")]}
SIDE = {"textures": {"pane": "examplemod:block/glass", "edge": "examplemod:block/edge"},
        "elements": [_box([7, 0, 0], [9, 16, 7])]}
NOSIDE = {"textures": {"pane": "examplemod:block/glass"},
          "elements": [{"from": [7, 0, 7], "to": [9, 16, 9], "faces": {"north": {"texture": "#pane", "uv": [7, 0, 9, 16]}}}]}


def _pane():
    """Vanilla's glass pane multipart shape: post, side per true, noside per false."""
    parts = [{"apply": {"model": "examplemod:block/post"}}]
    for d, y in (("north", 0), ("east", 90), ("south", 180), ("west", 270)):
        parts.append({"apply": {"model": "examplemod:block/side", "y": y}, "when": {d: "true"}})
        parts.append({"apply": {"model": "examplemod:block/noside", "y": y}, "when": {d: "false"}})
    return {"multipart": parts}


def _mod(tmp_path, blockstate, models):
    assets = tmp_path / "assets" / "examplemod"
    for sub in ("blockstates", "models/block", "textures/block"):
        (assets / sub).mkdir(parents=True, exist_ok=True)
    (assets / "blockstates" / "pane.json").write_text(json.dumps(blockstate))
    for name, body in models.items():
        (assets / "models" / "block" / f"{name}.json").write_text(json.dumps(body))
    for name in ("glass", "edge", "leaf"):
        (assets / "textures" / "block" / f"{name}.png").write_bytes(b"png")
    return SourceMod(root=tmp_path, namespace="examplemod")


def test_a_pane_multipart_reads_as_connection_parts():
    parts, why = blocks._connection_parts(_pane())
    assert why == ""
    assert len(parts) == 9
    assert parts[0]["test"] is None
    assert parts[1] == {"model": "examplemod:block/side", "x": 0, "y": 0, "uvlock": False,
                        "test": CONN.format("north"), "random": []}
    assert parts[2]["test"] == "!" + CONN.format("north")


def test_and_or_and_either_value_clauses():
    state = {"multipart": [
        {"apply": {"model": "m:a"}, "when": {"east": "false", "north": "false", "west": "false"}},
        {"apply": {"model": "m:b"}, "when": {"OR": [{"north": "true"}, {"south": True}]}},
        {"apply": {"model": "m:c"}, "when": {"AND": [{"north": "true"}, {"east": "false"}]}},
        {"apply": {"model": "m:d"}, "when": {"west": "true|false"}},
    ]}
    parts, _ = blocks._connection_parts(state)
    assert parts[0]["test"] == " && ".join("!" + CONN.format(d) for d in ("east", "north", "west"))
    assert parts[1]["test"] == f"({CONN.format('north')}) || ({CONN.format('south')})"
    assert parts[2]["test"] == f"{CONN.format('north')} && !{CONN.format('east')}"
    # Both values named: the part is always drawn.
    assert parts[3]["test"] is None


def test_other_states_are_not_this_shape():
    for when in ({"up": "true"}, {"north": "low"}, {"facing": "north"},
                 {"OR": [{"north": "true"}, {"up": "true"}]}):
        state = {"multipart": [{"apply": {"model": "m:a"}},
                               {"apply": {"model": "m:b"}, "when": when}]}
        assert blocks._connection_parts(state) == (None, "")
    # Nothing keyed on a direction at all is not a connection block either.
    assert blocks._connection_parts({"multipart": [{"apply": {"model": "m:a"}}]}) == (None, "")


def test_a_random_part_ships_its_first_model():
    state = {"multipart": [
        {"apply": [{"model": "m:a1"}, {"model": "m:a2"}]},
        {"apply": [{"model": "m:s1", "y": 90}, {"model": "m:s2", "y": 90}], "when": {"east": "true"}},
    ]}
    parts, _ = blocks._connection_parts(state)
    assert [p["model"] for p in parts] == ["m:a1", "m:s1"]
    assert parts[1]["y"] == 90 and parts[1]["random"] == ["m:s2"]


def test_a_pane_converts_with_one_bone_per_part(tmp_path):
    mod = _mod(tmp_path, _pane(), {"post": POST, "side": SIDE, "noside": NOSIDE})
    result = blocks.convert(mod)
    assert result.unhandled == []
    block = result.files["blocks/pane.json"]
    assert block["format_version"] == "1.26.0"
    body = block["minecraft:block"]
    assert body["description"]["traits"] == {
        "minecraft:connection": {"enabled_states": ["minecraft:cardinal_connections"]}}
    geometry = body["components"]["minecraft:geometry"]
    assert geometry["identifier"] == "geometry.examplemod.pane"
    assert "part_0" not in geometry["bone_visibility"]
    assert geometry["bone_visibility"]["part_3"] == CONN.format("east")
    assert geometry["bone_visibility"]["part_4"] == "!" + CONN.format("east")
    bones = result.files["models/blocks/pane.geo.json"]["minecraft:geometry"][0]["bones"]
    assert [b["name"] for b in bones] == [f"part_{i}" for i in range(9)]
    # The east side is the north side turned a quarter: it reaches the east edge.
    # (Bedrock mirrors x, so Java's east, x 9..16, is Bedrock x -8..-1.)
    east = bones[3]["cubes"][0]
    assert east["origin"][0] == -8 and east["size"][0] == 7
    assert any("connection trait" in n and "full block" in n for n in result.notes)
    assert "multipart" not in " ".join(u.reason for u in result.unhandled)


def test_clashing_texture_keys_get_their_own_names(tmp_path):
    leafy = {"textures": {"pane": "examplemod:block/leaf"},
             "elements": [_box([7, 0, 0], [9, 16, 7])]}
    state = {"multipart": [
        {"apply": {"model": "examplemod:block/post"}},
        {"apply": {"model": "examplemod:block/leafy"}, "when": {"north": "true"}},
    ]}
    result = blocks.convert(_mod(tmp_path, state, {"post": POST, "leafy": leafy}))
    assert result.unhandled == []
    instances = result.files["blocks/pane.json"]["minecraft:block"]["components"][
        "minecraft:material_instances"]
    # The post's "pane" is glass, the leafy side's is leaf: the side's key is renamed.
    assert instances["pane_p1"]["texture"] == "examplemod:leaf"
    assert instances["edge"]["texture"] == "examplemod:edge"


def test_a_part_that_cannot_turn_is_residue_naming_it(tmp_path):
    rotated = {**SIDE, "elements": [{**SIDE["elements"][0], "faces": {
        "up": {"texture": "#pane", "uv": [1, 0, 0, 1]}}}]}
    state = {"multipart": [
        {"apply": {"model": "examplemod:block/post"}},
        {"apply": {"model": "examplemod:block/side", "y": 90, "uvlock": True}, "when": {"east": "true"}},
    ]}
    result = blocks.convert(_mod(tmp_path, state, {"post": POST, "side": rotated}))
    assert "blocks/pane.json" not in result.files
    reason = result.unhandled[-1].reason
    assert reason.startswith("connection multipart part 2 (examplemod:block/side)")
    assert "uvlock re-maps the uv on the up face differently before MC 1.21.5" in reason


def test_pane_and_bars_templates_are_read():
    for name in ("template_glass_pane_post", "template_glass_pane_side",
                 "template_glass_pane_side_alt", "template_glass_pane_noside",
                 "template_glass_pane_noside_alt", "iron_bars_post", "iron_bars_post_ends",
                 "iron_bars_cap", "iron_bars_cap_alt", "iron_bars_side", "iron_bars_side_alt"):
        assert f"block/{name}" in model_data.TEMPLATES


def test_a_renamed_key_does_not_drag_a_chained_one_along():
    merged = {"all": "m:block/glass"}
    flat = {"textures": {"all": "m:block/leaf", "pane": "#all"},
            "elements": [{"faces": {"north": {"texture": "#pane"}, "up": {"texture": "#all"}}}]}
    out = blocks._keyed_textures(flat, 2, merged)
    # "pane" means leaf in this part, wherever "all" ends up.
    assert merged["pane"] == "m:block/leaf" and merged["all_p2"] == "m:block/leaf"
    assert out["elements"][0]["faces"]["up"]["texture"] == "#all_p2"
    assert out["elements"][0]["faces"]["north"]["texture"] == "#pane"
