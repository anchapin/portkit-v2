"""Block definitions: cubes convert, real blockstates stay residue."""
import json

import pytest

from portkit.converters import blocks
from portkit.model import SourceMod


def build(tmp_path, blockstate, model=None, textures=("steel_block",)):
    assets = tmp_path / "assets" / "examplemod"
    (assets / "blockstates").mkdir(parents=True, exist_ok=True)
    (assets / "models" / "block").mkdir(parents=True, exist_ok=True)
    (assets / "textures" / "block").mkdir(parents=True, exist_ok=True)
    (assets / "blockstates" / "steel_block.json").write_text(json.dumps(blockstate))
    if model is not None:
        (assets / "models" / "block" / "steel_block.json").write_text(json.dumps(model))
    for name in textures:
        (assets / "textures" / "block" / f"{name}.png").write_bytes(b"png")
    return SourceMod(root=tmp_path, namespace="examplemod")


CUBE = {"variants": {"": {"model": "examplemod:block/steel_block"}}}
CUBE_ALL = {
    "parent": "minecraft:block/cube_all",
    "textures": {"all": "examplemod:block/steel_block"},
}


def test_a_plain_cube_becomes_a_block_definition(tmp_path):
    result = blocks.convert(build(tmp_path, CUBE, CUBE_ALL))
    assert result.unhandled == []
    body = result.files["blocks/steel_block.json"]["minecraft:block"]
    assert body["description"]["identifier"] == "examplemod:steel_block"
    assert body["components"]["minecraft:geometry"] == "minecraft:geometry.full_block"
    assert body["components"]["minecraft:material_instances"] == {
        "*": {"texture": "examplemod:steel_block"}
    }


def test_no_hardness_or_light_is_invented(tmp_path):
    """Java keeps both in compiled code, so a number here would be fiction."""
    result = blocks.convert(build(tmp_path, CUBE, CUBE_ALL))
    components = result.files["blocks/steel_block.json"]["minecraft:block"]["components"]
    assert "minecraft:destructible_by_mining" not in components
    assert "minecraft:light_emission" not in components


def test_a_column_maps_ends_and_sides_separately(tmp_path):
    model = {
        "parent": "minecraft:block/cube_column",
        "textures": {"end": "examplemod:block/top", "side": "examplemod:block/side"},
    }
    result = blocks.convert(build(tmp_path, CUBE, model, textures=("top", "side")))
    instances = result.files["blocks/steel_block.json"]["minecraft:block"][
        "components"
    ]["minecraft:material_instances"]
    assert instances["up"] == {"texture": "examplemod:top"}
    assert instances["down"] == {"texture": "examplemod:top"}
    assert instances["*"] == {"texture": "examplemod:side"}


def test_a_block_with_real_states_is_residue_naming_them(tmp_path):
    blockstate = {"variants": {
        "facing=east": {"model": "examplemod:block/steel_block"},
        "facing=north": {"model": "examplemod:block/steel_block"},
    }}
    result = blocks.convert(build(tmp_path, blockstate, CUBE_ALL))
    assert result.files == {}
    reason = result.unhandled[0].reason
    assert "2 blockstate variant(s)" in reason
    assert "facing=east" in reason


def test_multipart_is_refused(tmp_path):
    result = blocks.convert(build(tmp_path, {"multipart": [{"apply": {"model": "x"}}]}, CUBE_ALL))
    assert "multipart" in result.unhandled[0].reason


def test_a_rotated_variant_is_refused(tmp_path):
    blockstate = {"variants": {"": {"model": "examplemod:block/steel_block", "y": 90}}}
    result = blocks.convert(build(tmp_path, blockstate, CUBE_ALL))
    assert result.files == {}
    assert "rotates" in result.unhandled[0].reason


@pytest.mark.parametrize("parent", ["minecraft:block/cross", "minecraft:block/stairs", "block/slab"])
def test_a_model_that_is_not_a_cube_is_refused(tmp_path, parent):
    model = {"parent": parent, "textures": {"all": "examplemod:block/steel_block"}}
    result = blocks.convert(build(tmp_path, CUBE, model))
    assert result.files == {}
    assert "not a full cube" in result.unhandled[0].reason


def test_a_vanilla_texture_reference_is_refused(tmp_path):
    model = {"parent": "minecraft:block/cube_all", "textures": {"all": "minecraft:block/iron_block"}}
    result = blocks.convert(build(tmp_path, CUBE, model))
    assert result.files == {}
    assert "another namespace" in result.unhandled[0].reason


def test_a_missing_model_is_refused_not_guessed(tmp_path):
    result = blocks.convert(build(tmp_path, CUBE, model=None))
    assert result.files == {}
    assert "not in this mod" in result.unhandled[0].reason


def test_both_the_blockstate_and_the_model_are_claimed(tmp_path):
    result = blocks.convert(build(tmp_path, CUBE, CUBE_ALL))
    assert any(c.endswith("blockstates/steel_block.json") for c in result.consumed)
    assert any(c.endswith("models/block/steel_block.json") for c in result.consumed)


def test_the_fixture_converts_the_cubes_and_refuses_the_rest(tmp_path, fixtures_dir):
    from portkit.pipeline import convert

    out = convert(fixtures_dir / "block_defs_mod" / "input", tmp_path / "out")
    assert out.report.ok, out.report.to_dict()
    produced = sorted(
        p.name for p in (out.tree / "behavior_pack" / "blocks").glob("*.json")
    )
    assert produced == ["steel_block.json", "steel_pillar.json"]
    reasons = " ".join(u.reason for u in out.unhandled)
    assert "blockstate variant" in reasons
    assert "not a full cube" in reasons
    assert "another namespace" in reasons
