"""#236: the vanilla parents random mods name most (orientable, cross, carpet,
button, fence gate, cube_top, ...), read from the fetched template set.

These run offline against hand-written shapes of the same form as the fetched
set (PORTKIT_MODEL_REFERENCE), never a copy of Mojang's models.
"""
import json
import math

import pytest

from portkit.converters import blocks, models
from portkit.data import models as model_data
from portkit.model import SourceMod

# Hand-written shapes in the fetched set's form ("minecraft:block/<name>":
# parent, textures, elements). The numbers are the test's own.
SHAPES = {
    "minecraft:block/block": {},
    "minecraft:block/cube": {
        "parent": "minecraft:block/block",
        "elements": [{"from": [0, 0, 0], "to": [16, 16, 16], "faces": {
            f: {"texture": f"#{f}"} for f in ("down", "up", "north", "south", "west", "east")}}],
    },
    "minecraft:block/orientable_with_bottom": {
        "parent": "minecraft:block/cube",
        "textures": {"down": "#bottom", "up": "#top", "north": "#front",
                     "east": "#side", "south": "#side", "west": "#side"},
    },
    "minecraft:block/orientable": {"parent": "minecraft:block/orientable_with_bottom",
                                   "textures": {"bottom": "#top"}},
    "minecraft:block/cube_top": {
        "parent": "minecraft:block/cube",
        "textures": {"down": "#side", "up": "#top", "north": "#side",
                     "east": "#side", "south": "#side", "west": "#side"},
    },
    "minecraft:block/carpet": {
        "parent": "minecraft:block/block",
        "elements": [{"from": [0, 0, 0], "to": [16, 2, 16], "faces": {
            "down": {"uv": [0, 0, 16, 16], "texture": "#wool"},
            "up": {"uv": [0, 0, 16, 16], "texture": "#wool"},
            "north": {"uv": [0, 14, 16, 16], "texture": "#wool"},
            "south": {"uv": [0, 14, 16, 16], "texture": "#wool"},
            "west": {"uv": [0, 14, 16, 16], "texture": "#wool"},
            "east": {"uv": [0, 14, 16, 16], "texture": "#wool"}}}],
    },
    "minecraft:block/cross": {
        "elements": [
            {"from": [2, 0, 8], "to": [14, 16, 8],
             "rotation": {"origin": [8, 8, 8], "axis": "y", "angle": 45, "rescale": True},
             "faces": {"north": {"uv": [0, 0, 16, 16], "texture": "#cross"},
                       "south": {"uv": [0, 0, 16, 16], "texture": "#cross"}}},
            {"from": [8, 0, 2], "to": [8, 16, 14],
             "rotation": {"origin": [8, 8, 8], "axis": "y", "angle": 45, "rescale": True},
             "faces": {"west": {"uv": [0, 0, 16, 16], "texture": "#cross"},
                       "east": {"uv": [0, 0, 16, 16], "texture": "#cross"}}},
        ],
    },
    "minecraft:block/button": {
        "elements": [{"from": [4, 0, 5], "to": [12, 2, 11], "faces": {
            f: {"texture": "#texture"} for f in ("down", "up", "north", "south", "west", "east")}}],
    },
    "minecraft:block/tinted_thing": {
        "elements": [{"from": [0, 0, 0], "to": [16, 16, 16], "faces": {
            "up": {"texture": "#all", "tintindex": 0}}}],
    },
}


@pytest.fixture
def shapes(tmp_path, monkeypatch):
    path = tmp_path / "shapes.json"
    path.write_text(json.dumps({"label": "hand-written test shapes", "models": SHAPES}))
    monkeypatch.setenv("PORTKIT_MODEL_REFERENCE", str(path))
    return path


def _mod(tmp_path, model, *, blockstate=None, textures=("wool",), minecraft=None):
    root = tmp_path / "src"
    assets = root / "assets" / "examplemod"
    for sub in ("blockstates", "models/block", "textures/block"):
        (assets / sub).mkdir(parents=True, exist_ok=True)
    state = blockstate or {"variants": {"": {"model": "examplemod:block/thing"}}}
    (assets / "blockstates" / "thing.json").write_text(json.dumps(state))
    (assets / "models" / "block" / "thing.json").write_text(json.dumps(model))
    for name in textures:
        (assets / "textures" / "block" / f"{name}.png").write_bytes(b"png")
    return SourceMod(root=root, namespace="examplemod", minecraft=minecraft)


# -- the fetched set ---------------------------------------------------------

def test_the_issue_parents_are_in_the_fetched_set():
    for name in ("orientable", "orientable_with_bottom", "cross", "button", "cube_top",
                 "template_fence_gate", "template_fence_gate_open", "template_fence_gate_wall",
                 "template_fence_gate_wall_open", "carpet", "flower_pot_cross", "cube_bottom_top"):
        assert f"block/{name}" in model_data.TEMPLATES


def test_version_gated_templates_are_in_the_set():
    for parent, since in model_data.SINCE.items():
        assert parent.partition(":")[2] in model_data.TEMPLATES
        assert since[0].isdigit()


def test_no_tinted_template_is_fetched():
    """Tinted faces take their colour from code (biome or colour handler)."""
    for name in ("block/tinted_cross", "block/leaves", "block/lily_pad"):
        assert name not in model_data.TEMPLATES


def test_is_template_names_only_the_fetched_parents():
    assert models.is_template("minecraft:block/cross")
    assert not models.is_template("minecraft:block/block")  # a chain parent, not fetched by name
    assert not models.is_template("minecraft:block/tinted_cross")
    assert not models.is_template("examplemod:block/cross")


# -- rescale -------------------------------------------------------------------

def test_rescale_stretches_the_box_about_the_origin_on_the_turned_axes():
    element = {"from": [2, 0, 8], "to": [14, 16, 8],
               "rotation": {"origin": [8, 8, 8], "axis": "y", "angle": 45, "rescale": True}}
    assert models._apply_rescale(element)
    k = 1 / math.cos(math.radians(45))
    assert element["from"] == [round(8 - 6 * k, 4), 0, 8]
    assert element["to"] == [round(8 + 6 * k, 4), 16, 8]
    assert element["rotation"] == {"origin": [8, 8, 8], "axis": "y", "angle": 45}


def test_rescale_at_22_5_degrees_about_x_leaves_x_alone():
    element = {"from": [0, 4, 4], "to": [16, 12, 12],
               "rotation": {"origin": [8, 8, 8], "axis": "x", "angle": -22.5, "rescale": True}}
    assert models._apply_rescale(element)
    k = 1 / math.cos(math.radians(22.5))
    assert element["from"] == [0, round(8 - 4 * k, 4), round(8 - 4 * k, 4)]
    assert element["to"] == [16, round(8 + 4 * k, 4), round(8 + 4 * k, 4)]


def test_an_element_without_rescale_is_untouched():
    element = {"from": [0, 0, 0], "to": [16, 16, 16],
               "rotation": {"origin": [8, 8, 8], "axis": "z", "angle": 22.5}}
    before = json.loads(json.dumps(element))
    assert models._apply_rescale(element)
    assert element == before


# -- expanding ---------------------------------------------------------------

def test_a_cross_expands_with_its_planes_stretched_and_uvs_kept(shapes):
    flat, why = models.expand_template({"parent": "minecraft:block/cross",
                                         "textures": {"cross": "examplemod:block/rose"}})
    assert why == ""
    first = flat["elements"][0]
    assert first["from"][0] < 2 and first["to"][0] > 14  # stretched by 1/cos 45
    assert "rescale" not in first["rotation"]
    assert first["faces"]["north"]["uv"] == [0, 0, 16, 16]
    assert flat["textures"]["cross"] == "examplemod:block/rose"


def test_a_template_with_a_tinted_face_is_refused(shapes):
    flat, why = models.expand_template({"parent": "minecraft:block/tinted_thing",
                                         "textures": {"all": "examplemod:block/x"}})
    assert flat is None
    assert "tints" in why


@pytest.mark.parametrize("minecraft", [None, "1.16.5", "1.19.4"])
def test_a_version_gated_template_is_refused_for_older_or_undeclared_mods(shapes, minecraft):
    flat, why = models.expand_template({"parent": "minecraft:block/button",
                                         "textures": {"texture": "examplemod:block/x"}}, minecraft)
    assert flat is None
    assert "changed its boxes in 1.20" in why


@pytest.mark.parametrize("minecraft", ["1.20", "1.20.1", "1.21.1", "26.1", "1.21,1.21.1"])
def test_a_version_gated_template_reads_for_its_versions(shapes, minecraft):
    flat, why = models.expand_template({"parent": "minecraft:block/button",
                                         "textures": {"texture": "examplemod:block/x"}}, minecraft)
    assert why == ""
    assert flat["elements"][0]["from"] == [4, 0, 5]


# -- converting --------------------------------------------------------------

def test_a_carpet_parent_becomes_a_custom_shape(tmp_path, shapes):
    mod = _mod(tmp_path, {"parent": "minecraft:block/carpet",
                          "textures": {"wool": "examplemod:block/wool"}})
    result = blocks.convert(mod)
    assert result.unhandled == []
    block = result.files["blocks/thing.json"]["minecraft:block"]
    assert block["components"]["minecraft:geometry"] == "geometry.examplemod.thing"
    assert block["components"]["minecraft:material_instances"]["*"]["texture"] == "examplemod:wool"
    geo = result.files["geometry/thing.geo.json"] if "geometry/thing.geo.json" in result.files else None
    if geo is None:
        geo = next(v for k, v in result.files.items() if k.endswith(".geo.json"))
    cube = geo["minecraft:geometry"][0]["bones"][0]["cubes"][0]
    assert cube["size"] == [16.0, 2.0, 16.0]


def test_a_cross_parent_becomes_two_stretched_planes(tmp_path, shapes):
    mod = _mod(tmp_path, {"parent": "minecraft:block/cross",
                          "textures": {"cross": "examplemod:block/rose"}}, textures=("rose",))
    result = blocks.convert(mod)
    assert result.unhandled == []
    geo = next(v for k, v in result.files.items() if k.endswith(".geo.json"))
    cubes = geo["minecraft:geometry"][0]["bones"][0]["cubes"]
    assert len(cubes) == 2
    k = 1 / math.cos(math.radians(45))
    assert cubes[0]["size"][0] == pytest.approx(12 * k, abs=1e-3)
    assert cubes[0]["rotation"] == [0.0, -45.0, 0.0]  # ROTATION_SIGN y = -1


def test_cube_top_is_a_full_block(tmp_path, shapes):
    mod = _mod(tmp_path, {"parent": "minecraft:block/cube_top",
                          "textures": {"top": "examplemod:block/top", "side": "examplemod:block/side"}},
               textures=("top", "side"))
    result = blocks.convert(mod)
    assert result.unhandled == []
    comps = result.files["blocks/thing.json"]["minecraft:block"]["components"]
    assert comps["minecraft:geometry"] == "minecraft:geometry.full_block"
    assert comps["minecraft:material_instances"]["up"] == {"texture": "examplemod:top"}
    assert comps["minecraft:material_instances"]["*"] == {"texture": "examplemod:side"}


def test_a_turned_orientable_reads_its_box_from_the_templates(tmp_path, shapes):
    """Before #236 orientable was only a stateless full cube; turned, its box
    was unknown."""
    model = {"parent": "minecraft:block/orientable",
             "textures": {"front": "examplemod:block/front", "side": "examplemod:block/side",
                          "top": "examplemod:block/top"}}
    flat, why = models.expand_template(model)
    assert why == ""
    assert flat["elements"][0]["faces"]["north"]["texture"] == "#north"
    textures = flat["textures"]
    assert textures["north"] == "examplemod:block/front"
    assert textures["down"] == "examplemod:block/top"  # orientable: bottom is #top
    assert textures["east"] == "examplemod:block/side"


def test_an_old_mods_button_stays_residue_saying_why(tmp_path, shapes):
    mod = _mod(tmp_path, {"parent": "minecraft:block/button",
                          "textures": {"texture": "examplemod:block/wool"}}, minecraft="1.19.2")
    result = blocks.convert(mod)
    assert "blocks/thing.json" not in result.files
    assert "changed its boxes in 1.20" in result.unhandled[0].reason


def test_a_parent_outside_the_set_keeps_the_old_refusal(tmp_path, shapes):
    mod = _mod(tmp_path, {"parent": "minecraft:block/template_wall_sign",
                          "textures": {"texture": "examplemod:block/wool"}})
    result = blocks.convert(mod)
    assert result.files == {}
    assert "is not a full cube" in result.unhandled[0].reason
