"""#296: a block whose every model bakes no quads is `code_drawn_block` residue.

Java's block model renderer draws a model's elements (or its parent's). A model
with no elements, no vanilla parent, no custom loader and only a particle
texture draws nothing, so what the player sees is the mod's code (a
block-entity renderer, the fluid renderer, a model swapped in at runtime).
"""
import json

from portkit.agent.residue import SKIP_KINDS
from portkit.converters import blocks
from portkit.model import SourceMod


def build(tmp_path, blockstate, models):
    assets = tmp_path / "assets" / "examplemod"
    (assets / "blockstates").mkdir(parents=True, exist_ok=True)
    (assets / "blockstates" / "thing.json").write_text(json.dumps(blockstate))
    for name, model in models.items():
        path = assets / "models" / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(model))
    return SourceMod(root=tmp_path, namespace="examplemod")


ONE = {"variants": {"": {"model": "examplemod:block/thing"}}}
PARTICLE = {"textures": {"particle": "examplemod:block/planks"}}


def kinds(result):
    return [(u.source, u.kind) for u in result.unhandled]


def test_a_particle_only_model_is_code_drawn(tmp_path):
    result = blocks.convert(build(tmp_path, ONE, {"block/thing": PARTICLE}))
    assert kinds(result) == [("assets/examplemod/blockstates/thing.json", "code_drawn_block")]
    (entry,) = result.unhandled
    assert "examplemod:block/planks" in entry.reason
    assert "bakes no quads" in entry.reason
    assert not result.files
    # The model is claimed, as the refusing single-model path claimed it, so
    # moving the entry out of `block` changes no count.
    assert "assets/examplemod/models/block/thing.json" in result.consumed


def test_the_kind_is_explained():
    assert "code_drawn_block" in SKIP_KINDS


def test_a_textureless_model_and_a_comment_count(tmp_path):
    model = {"__comment": "drawn by the fluid renderer", "textures": {}}
    result = blocks.convert(build(tmp_path, ONE, {"block/thing": model}))
    assert kinds(result)[0][1] == "code_drawn_block"


def test_a_mod_parent_chain_of_particle_only_models(tmp_path):
    mod = build(tmp_path, ONE, {
        "block/thing": {"parent": "examplemod:block/empty", "textures": {"particle": "examplemod:block/a"}},
        "block/empty": {"textures": {"particle": "examplemod:block/b"}},
    })
    result = blocks.convert(mod)
    assert kinds(result)[0][1] == "code_drawn_block"
    assert "examplemod:block/a" in result.unhandled[0].reason
    assert "assets/examplemod/models/block/empty.json" in result.consumed


def test_every_variant_and_multipart_model_must_draw_nothing(tmp_path):
    blockstate = {"variants": {"facing=north": {"model": "examplemod:block/thing"},
                               "facing=south": {"model": "examplemod:block/other"}}}
    mod = build(tmp_path, blockstate, {"block/thing": PARTICLE, "block/other": PARTICLE})
    assert kinds(blocks.convert(mod))[0][1] == "code_drawn_block"

    multipart = {"multipart": [{"apply": {"model": "examplemod:block/thing"}},
                               {"when": {"north": "true"}, "apply": [{"model": "examplemod:block/other"}]}]}
    mod = build(tmp_path / "mp", multipart, {"block/thing": PARTICLE, "block/other": PARTICLE})
    assert kinds(blocks.convert(mod))[0][1] == "code_drawn_block"


def test_one_drawing_model_keeps_the_block_on_its_old_path(tmp_path):
    blockstate = {"variants": {"lit=false": {"model": "examplemod:block/thing"},
                               "lit=true": {"model": "examplemod:block/cube"}}}
    cube = {"parent": "minecraft:block/cube_all", "textures": {"all": "examplemod:block/a"}}
    result = blocks.convert(build(tmp_path, blockstate, {"block/thing": PARTICLE, "block/cube": cube}))
    assert all(u.kind != "code_drawn_block" for u in result.unhandled)


def test_elements_loaders_vanilla_parents_and_other_textures_draw(tmp_path):
    drawing = {
        "elements": {"textures": {"particle": "x"}, "elements": [{"from": [0, 0, 0], "to": [16, 16, 16], "faces": {}}]},
        "loader": {"loader": "neoforge:obj", "model": "examplemod:models/block/thing.obj",
                   "textures": {"particle": "x"}},
        "vanilla": {"parent": "minecraft:block/block", "textures": {"particle": "x"}},
        "texture": {"textures": {"particle": "x", "side": "y"}},
        "foreign": {"parent": "othermod:block/empty", "textures": {"particle": "x"}},
        "missing": {"parent": "examplemod:block/nowhere", "textures": {"particle": "x"}},
    }
    for label, model in drawing.items():
        result = blocks.convert(build(tmp_path / label, ONE, {"block/thing": model}))
        assert all(u.kind != "code_drawn_block" for u in result.unhandled), label


def test_a_blockstate_naming_no_model_is_not_code_drawn(tmp_path):
    result = blocks.convert(build(tmp_path, {"variants": {"": {}}}, {}))
    assert all(u.kind != "code_drawn_block" for u in result.unhandled)
