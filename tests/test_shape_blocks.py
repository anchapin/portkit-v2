"""Stairs, slabs, walls and turned pillars, built from vanilla's model templates.

A mod's stairs model only names ``minecraft:block/stairs`` and its textures; the
boxes are vanilla's. The block converter reads them from the fetched template
set (portkit.data.models, never vendored). These tests run offline against
tests/data/model_templates.json, hand-written shapes of the same form
(PORTKIT_MODEL_REFERENCE).
"""
import io
import json
from pathlib import Path

import pytest

from portkit import pack
from portkit.converters import blocks, models
from portkit.data import ReferenceDataError
from portkit.data import models as model_data
from portkit.model import SourceMod
from portkit.pipeline import convert

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "tests" / "data" / "model_templates.json"
PNG = ROOT / "fixtures" / "agent_mod" / "input" / "assets" / "examplemod" / "textures" / "block" / "alloy_block.png"
FACINGS = ("north", "east", "south", "west")
SHAPES = ("straight", "inner_left", "inner_right", "outer_left", "outer_right")


@pytest.fixture
def templates(monkeypatch):
    monkeypatch.setenv("PORTKIT_MODEL_REFERENCE", str(TEMPLATES))
    return TEMPLATES


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(body, bytes):
        path.write_bytes(body)
    else:
        path.write_text(json.dumps(body) if not isinstance(body, str) else body)


# Java's own stairs blockstate layout (as datagen writes it for every stairs
# block): the turn for each facing, and the extra quarter for left corners.
_FACING_Y = {"east": 0, "south": 90, "west": 180, "north": 270}


def _stairs_blockstate(ns="examplemod", name="stone_stairs"):
    variants = {}
    for facing in FACINGS:
        for half in ("bottom", "top"):
            for shape in SHAPES:
                model = {"straight": name}.get(shape, f"{name}_{shape.split('_')[0]}")
                y = _FACING_Y[facing]
                if shape in ("inner_left", "outer_left") and half == "bottom":
                    y -= 90
                if shape in ("inner_right", "outer_right") and half == "top":
                    y += 90
                entry = {"model": f"{ns}:block/{model}"}
                if half == "top":
                    entry["x"] = 180
                if y % 360:
                    entry["y"] = y % 360
                if "x" in entry or "y" in entry:
                    entry["uvlock"] = True
                variants[f"facing={facing},half={half},shape={shape}"] = entry
    return {"variants": variants}


def _shape_mod(tmp_path, *, stairs=True, slab=True, wall=True, pillar=True):
    root = tmp_path / "src"
    tex = {"bottom": "examplemod:block/stone", "side": "examplemod:block/stone", "top": "examplemod:block/stone"}
    _write(root, "assets/examplemod/textures/block/stone.png", PNG.read_bytes())
    _write(root, "assets/examplemod/textures/block/stone_end.png", PNG.read_bytes())
    _write(root, "assets/examplemod/models/block/stone.json",
           {"parent": "minecraft:block/cube_all", "textures": {"all": "examplemod:block/stone"}})
    if stairs:
        _write(root, "assets/examplemod/blockstates/stone_stairs.json", _stairs_blockstate())
        for model, parent in (("stone_stairs", "stairs"), ("stone_stairs_inner", "inner_stairs"),
                              ("stone_stairs_outer", "outer_stairs")):
            _write(root, f"assets/examplemod/models/block/{model}.json",
                   {"parent": f"minecraft:block/{parent}", "textures": tex})
    if slab:
        _write(root, "assets/examplemod/blockstates/stone_slab.json", {"variants": {
            "type=bottom": {"model": "examplemod:block/stone_slab"},
            "type=top": {"model": "examplemod:block/stone_slab_top"},
            "type=double": {"model": "examplemod:block/stone"},
        }})
        _write(root, "assets/examplemod/models/block/stone_slab.json", {"parent": "minecraft:block/slab", "textures": tex})
        _write(root, "assets/examplemod/models/block/stone_slab_top.json",
               {"parent": "minecraft:block/slab_top", "textures": tex})
    if wall:
        parts = [{"apply": {"model": "examplemod:block/stone_wall_post"}, "when": {"up": "true"}}]
        for d, y in (("north", 0), ("east", 90), ("south", 180), ("west", 270)):
            for height, model in (("low", "stone_wall_side"), ("tall", "stone_wall_side_tall")):
                apply = {"model": f"examplemod:block/{model}", "uvlock": True}
                if y:
                    apply["y"] = y
                parts.append({"apply": apply, "when": {d: height}})
        _write(root, "assets/examplemod/blockstates/stone_wall.json", {"multipart": parts})
        for model, parent in (("stone_wall_post", "template_wall_post"), ("stone_wall_side", "template_wall_side"),
                              ("stone_wall_side_tall", "template_wall_side_tall")):
            _write(root, f"assets/examplemod/models/block/{model}.json",
                   {"parent": f"minecraft:block/{parent}", "textures": {"wall": "examplemod:block/stone"}})
    if pillar:
        _write(root, "assets/examplemod/blockstates/stone_pillar.json", {"variants": {
            "axis=x": {"model": "examplemod:block/stone_pillar_horizontal", "x": 90, "y": 90},
            "axis=y": {"model": "examplemod:block/stone_pillar"},
            "axis=z": {"model": "examplemod:block/stone_pillar_horizontal", "x": 90},
        }})
        pillar_tex = {"end": "examplemod:block/stone_end", "side": "examplemod:block/stone"}
        _write(root, "assets/examplemod/models/block/stone_pillar.json",
               {"parent": "minecraft:block/cube_column", "textures": pillar_tex})
        _write(root, "assets/examplemod/models/block/stone_pillar_horizontal.json",
               {"parent": "minecraft:block/cube_column_horizontal", "textures": pillar_tex})
    return root


def _blocks(root: Path):
    return blocks.convert(SourceMod(root=root, namespace="examplemod"))


def _bones(geo: dict) -> dict:
    return {b["name"]: b["cubes"] for b in geo["minecraft:geometry"][0]["bones"]}


# -- the reference set -------------------------------------------------------
def test_derive_keeps_the_templates_and_their_parents_only():
    summary = {name: {"parent": "block/block", "elements": [{"from": [0, 0, 0], "to": [1, 1, 1],
                                                             "faces": {}, "__comment": "x"}],
                      "display": {"gui": {}}} for name in model_data.TEMPLATES}
    summary["block/block"] = {"display": {"gui": {}}, "gui_light": "side"}
    summary["block/acacia_button"] = {"parent": "block/button"}
    derived = json.loads(model_data.derive(json.dumps(summary).encode()))
    kept = derived["models"]
    assert set(kept) == {f"minecraft:{n}" for n in model_data.TEMPLATES} | {"minecraft:block/block"}
    assert kept["minecraft:block/block"] == {}
    stairs = kept["minecraft:block/stairs"]
    assert stairs["parent"] == "minecraft:block/block" and "display" not in stairs
    assert "__comment" not in stairs["elements"][0]


def test_a_summary_missing_a_template_is_refused():
    with pytest.raises(ValueError, match="is not in the summary"):
        model_data.derive(json.dumps({"block/slab": {}}).encode())


def test_fetch_checks_the_pin(tmp_path, monkeypatch):
    summary = {name: {} for name in model_data.TEMPLATES}
    summary["block/block"] = {}

    def opener(request, timeout):
        return io.BytesIO(json.dumps(summary).encode())

    with pytest.raises(ReferenceDataError, match="sha256 mismatch"):
        model_data.fetch(tmp_path, opener=opener)
    assert not any(tmp_path.iterdir())


def test_without_the_set_nothing_is_read(monkeypatch):
    monkeypatch.delenv("PORTKIT_MODEL_REFERENCE", raising=False)
    assert model_data.templates() is None


# -- templates and turns -----------------------------------------------------
def test_a_template_fills_in_boxes_and_resolves_texture_variables(templates):
    flat = {"parent": "minecraft:block/cube_column",
            "textures": {"end": "examplemod:block/stone_end", "side": "examplemod:block/stone"}}
    expanded, why = models.expand_template(flat)
    assert why == ""
    assert expanded["elements"][0]["faces"]["up"]["texture"] == "#up"
    # Java's position-derived uv, written down.
    assert expanded["elements"][0]["faces"]["up"]["uv"] == [0, 0, 16, 16]
    assert expanded["textures"]["up"] == "examplemod:block/stone_end"
    assert expanded["textures"]["north"] == "examplemod:block/stone"


def test_a_model_with_its_own_elements_is_left_alone(templates):
    flat = {"parent": "minecraft:block/stairs", "elements": [{"from": [0, 0, 0], "to": [1, 1, 1]}]}
    assert models.expand_template(flat) == (flat, "")


def test_offline_a_template_says_to_fetch():
    expanded, why = models.expand_template({"parent": "minecraft:block/stairs"})
    assert expanded is None and "portkit reference fetch" in why


def test_an_unknown_vanilla_parent_is_refused(templates):
    expanded, why = models.expand_template({"parent": "minecraft:block/button"})
    assert expanded is None and "not one of the vanilla templates" in why


def test_uvlock_flip_keeps_textures_fixed_to_the_world():
    step = {"from": [8, 8, 0], "to": [16, 16, 16], "faces": {
        "up": {"texture": "#top"}, "west": {"texture": "#side", "uv": [0, 0, 16, 8]}}}
    turned, why = models.turn_locked(step, 180, 0)
    assert why == ""
    # x=180 turns (y, z) to (16 - y, 16 - z): the step drops to the bottom half.
    assert turned["from"] == [8, 0, 0] and turned["to"] == [16, 8, 16]
    assert set(turned["faces"]) == {"down", "west"}
    assert turned["faces"]["west"]["uv"] == models.auto_uv("west", [8, 0, 0], [16, 8, 16])
    assert "rotation" not in turned["faces"]["down"]


def test_uvlock_maps_a_hand_set_uv_as_java_does():
    # #236: FaceBakery#recomputeUVs; north [0,0,4,4] turned y=90 lands on east
    # with the same uv (MC 1.21.1 and 1.21.8 client jars agree).
    element = {"from": [0, 0, 0], "to": [16, 8, 16], "faces": {"north": {"texture": "#s", "uv": [0, 0, 4, 4]}}}
    turned, why = models.turn_locked(element, 0, 90)
    assert why == "" and turned["faces"]["east"]["uv"] == [0, 0, 4, 4]


def test_uvlock_refuses_a_uv_java_versions_bake_differently():
    element = {"from": [0, 0, 0], "to": [16, 8, 16], "faces": {"up": {"texture": "#s", "uv": [1, 0, 0, 1]}}}
    turned, why = models.turn_locked(element, 0, 90)
    assert turned is None and "declares no game version" in why


# -- recognising the shapes --------------------------------------------------
def test_stairs_are_recognised_by_their_state_set():
    found, why = blocks._stairs_variants(_stairs_blockstate())
    assert why == "" and len(found) == 40
    assert found[("north", "bottom", "straight")] == ("examplemod:block/stone_stairs", 0, 270, True)


def test_a_missing_stairs_variant_is_not_stairs():
    state = _stairs_blockstate()
    del state["variants"]["facing=east,half=top,shape=outer_left"]
    assert blocks._stairs_variants(state) == (None, "")


def test_a_slab_is_recognised_by_its_type_variants():
    state = {"variants": {"type=bottom": {"model": "m:a"}, "type=top": {"model": "m:b"},
                          "type=double": {"model": "m:c"}}}
    found, why = blocks._slab_variants(state)
    assert why == "" and found["double"] == ("m:c", 0, 0, False)


def test_a_turned_slab_half_is_refused():
    state = {"variants": {"type=bottom": {"model": "m:a", "y": 90}, "type=top": {"model": "m:b"},
                          "type=double": {"model": "m:c"}}}
    found, why = blocks._slab_variants(state)
    assert found is None and "turns its model" in why


def test_a_wall_is_recognised_by_its_parts():
    assert blocks._wall_parts({"multipart": []}) is None
    parts = [{"apply": {"model": "m:post"}, "when": {"up": "true"}}]
    for d, y in (("north", 0), ("east", 90), ("south", 180), ("west", 270)):
        parts.append({"apply": {"model": "m:side", "y": y, "uvlock": True}, "when": {d: "low"}})
        parts.append({"apply": {"model": "m:tall", "y": y, "uvlock": True}, "when": {d: "tall"}})
    assert blocks._wall_parts({"multipart": parts}) == ("m:post", "m:side", "m:tall", True)
    parts[1]["apply"]["y"] = 90  # north side turned east: not a wall
    assert blocks._wall_parts({"multipart": parts}) is None


# -- converting them ---------------------------------------------------------
def test_stairs_convert_with_placement_traits_and_one_bone_per_variant(tmp_path, templates):
    result = _blocks(_shape_mod(tmp_path, slab=False, wall=False, pillar=False))
    assert [u for u in result.unhandled if "stairs" in u.source] == []
    block = result.files["blocks/stone_stairs.json"]
    assert block["format_version"] == "1.26.0"
    traits = block["minecraft:block"]["description"]["traits"]
    assert traits["minecraft:placement_direction"]["enabled_states"] == ["minecraft:corner_and_cardinal_direction"]
    assert traits["minecraft:placement_position"]["enabled_states"] == ["minecraft:vertical_half"]
    components = block["minecraft:block"]["components"]
    assert components["minecraft:support"] == {"shape": "stair"}
    assert "tag:minecraft:cornerable_stairs" in components
    assert components["minecraft:geometry"] == "geometry.examplemod.stone_stairs.south_bottom_straight"
    perms = {p["condition"]: p["components"] for p in block["minecraft:block"]["permutations"]}
    assert len(perms) == 40
    east_top = perms[
        "q.block_state('minecraft:cardinal_direction') == 'east' && "
        "q.block_state('minecraft:vertical_half') == 'top' && "
        "q.block_state('minecraft:corner') == 'none'"]
    assert east_top["minecraft:geometry"] == "geometry.examplemod.stone_stairs.east_top_straight"
    assert any("== 'inner_left'" in c and v["minecraft:geometry"].endswith("west_bottom_inner_left")
               for c, v in perms.items())

    geo = result.files["models/blocks/stone_stairs.geo.json"]
    bones = {g["description"]["identifier"].rsplit(".", 1)[-1]: g["bones"][0]["cubes"]
             for g in geo["minecraft:geometry"]}
    assert len(bones) == 40
    assert all(len(g["bones"]) == 1 for g in geo["minecraft:geometry"])
    # facing=east is vanilla's own orientation: the step on Java x 8..16, which
    # the mirrored X axis puts at Bedrock origin x = 8 - 16 = -8.
    east = bones["east_bottom_straight"]
    assert [(c["origin"], c["size"]) for c in east] == [
        ([-8.0, 0.0, -8.0], [16.0, 8.0, 16.0]), ([-8.0, 8.0, -8.0], [8.0, 8.0, 16.0])]
    # facing=north (y=270): the step runs along Java z 0..8, the north half.
    north = bones["north_bottom_straight"]
    assert (north[1]["origin"], north[1]["size"]) == ([-8.0, 8.0, -8.0], [16.0, 8.0, 8.0])
    # half=top (x=180): upside down, the slab on top and the step below.
    top = bones["east_top_straight"]
    assert top[0]["origin"][1] == 8.0 and top[1]["origin"][1] == 0.0


def test_stairs_collision_follows_each_variants_boxes(tmp_path, templates):
    result = _blocks(_shape_mod(tmp_path, slab=False, wall=False, pillar=False))
    perms = result.files["blocks/stone_stairs.json"]["minecraft:block"]["permutations"]
    by_condition = {p["condition"]: p["components"]["minecraft:collision_box"] for p in perms}
    outer = next(v for k, v in by_condition.items() if "'east'" in k and "'bottom'" in k and "outer_right" in k)
    assert outer == [{"origin": [-8.0, 0.0, -8.0], "size": [16.0, 8.0, 16.0]},
                     {"origin": [-8.0, 8.0, 0.0], "size": [8.0, 8.0, 8.0]}]


def test_a_model_that_is_not_a_stairs_template_stays_residue(tmp_path, templates):
    root = _shape_mod(tmp_path, slab=False, wall=False, pillar=False)
    _write(root, "assets/examplemod/models/block/stone_stairs_outer.json",
           {"parent": "minecraft:block/cube_all", "textures": {"all": "examplemod:block/stone"}})
    result = _blocks(root)
    assert "blocks/stone_stairs.json" not in result.files
    reason = next(u.reason for u in result.unhandled if u.source.endswith("stone_stairs.json"))
    assert "not the vanilla" in reason and "stairs" in reason


def test_offline_shapes_stay_residue_saying_to_fetch(tmp_path):
    result = _blocks(_shape_mod(tmp_path))
    for name in ("stone_stairs", "stone_slab", "stone_wall", "stone_pillar"):
        assert f"blocks/{name}.json" not in result.files
        reason = next(u.reason for u in result.unhandled if u.source.endswith(f"/{name}.json"))
        assert "portkit reference fetch" in reason, (name, reason)


def test_slabs_convert_with_vertical_half_and_half_height_boxes(tmp_path, templates):
    result = _blocks(_shape_mod(tmp_path, stairs=False, wall=False, pillar=False))
    block = result.files["blocks/stone_slab.json"]["minecraft:block"]
    assert block["description"]["traits"] == {
        "minecraft:placement_position": {"enabled_states": ["minecraft:vertical_half"]}}
    visibility = block["components"]["minecraft:geometry"]["bone_visibility"]
    assert visibility == {"bottom": "q.block_state('minecraft:vertical_half') == 'bottom'",
                          "top": "q.block_state('minecraft:vertical_half') == 'top'"}
    perms = {p["condition"]: p["components"] for p in block["permutations"]}
    top = perms["q.block_state('minecraft:vertical_half') == 'top'"]
    assert top["minecraft:collision_box"] == [{"origin": [-8.0, 8.0, -8.0], "size": [16.0, 8.0, 16.0]}]
    assert top["minecraft:selection_box"] == {"origin": [-8.0, 8.0, -8.0], "size": [16.0, 8.0, 16.0]}
    assert any("double slab" in note and "stone_slab" in note for note in result.notes)
    # The double slab's model was read and set aside, not left looking unconverted.
    assert "assets/examplemod/models/block/stone.json" in result.consumed


def test_walls_convert_with_the_connection_trait_and_javas_post_rule(tmp_path, templates):
    result = _blocks(_shape_mod(tmp_path, stairs=False, slab=False, pillar=False))
    block = result.files["blocks/stone_wall.json"]
    assert block["format_version"] == "1.26.0"
    desc = block["minecraft:block"]["description"]
    assert desc["traits"] == {"minecraft:connection": {"enabled_states": ["minecraft:cardinal_connections"]}}
    visibility = block["minecraft:block"]["components"]["minecraft:geometry"]["bone_visibility"]
    assert visibility["east"] == "q.block_state('minecraft:connection_east')"
    assert "!=" in visibility["post"]
    bones = _bones(result.files["models/blocks/stone_wall.geo.json"])
    assert set(bones) == {"post", "north", "east", "south", "west"}
    # The east side is the low side turned a quarter: Java x 8..16, z 5..11.
    assert bones["east"][0]["size"] == [8.0, 14.0, 6.0]
    assert any("tall sides" in note for note in result.notes)


@pytest.mark.parametrize("connected, post", [
    ((), True), (("north",), True), (("north", "south"), False), (("east", "west"), False),
    (("north", "east"), True), (("north", "east", "south"), True), (("north", "east", "south", "west"), False),
])
def test_the_post_rule_matches_javas_wall(connected, post):
    expression = blocks._wall_definition("m", "w", "g", {})["minecraft:block"]["components"][
        "minecraft:geometry"]["bone_visibility"]["post"]
    for d in FACINGS:
        expression = expression.replace(f"q.block_state('minecraft:connection_{d}')", str(d in connected))
    expression = expression.replace("!", " not ").replace(" not =", "!=").replace("&&", " and ").replace("||", " or ")
    assert eval(expression) is post  # noqa: S307 - our own expression, booleans only


def test_a_turned_pillar_gets_its_template_box(tmp_path, templates):
    result = _blocks(_shape_mod(tmp_path, stairs=False, slab=False, wall=False))
    assert [u for u in result.unhandled if "pillar" in u.source] == []
    block = result.files["blocks/stone_pillar.json"]["minecraft:block"]
    assert block["description"]["traits"] == {
        "minecraft:placement_position": {"enabled_states": ["minecraft:block_face"]}}
    x_axis = next(p for p in block["permutations"] if "'east'" in p["condition"])
    instances = x_axis["components"]["minecraft:material_instances"]
    # Lying along x, the caps face east and west.
    assert instances["east"]["texture"] == instances["west"]["texture"] == "examplemod:stone_end"
    assert instances["up"]["texture"] == "examplemod:stone"
    assert "models/blocks/stone_pillar_x.geo.json" in result.files


def test_the_converted_pack_is_valid_and_needs_1_26(tmp_path, templates):
    root = _shape_mod(tmp_path)
    out = convert(root, tmp_path / "out", emit_addon=False)
    assert out.report.ok, out.report.errors
    files = {f"blocks/{n}.json": json.loads((out.tree / "behavior_pack" / "blocks" / f"{n}.json").read_text())
             for n in ("stone_stairs", "stone_slab", "stone_wall")}
    assert pack.engine_floor(files) == (1, 26, 0)
    left = {u.source for u in out.unhandled if u.kind == "block"}
    assert not left, left


def test_end_to_end_the_shapes_leave_no_model_unowned(tmp_path, templates):
    root = _shape_mod(tmp_path)
    out = convert(root, tmp_path / "out", emit_addon=False)
    unowned = [u for u in out.unhandled if u.kind == "unowned"]
    assert not any("models" in u.source for u in unowned), unowned

