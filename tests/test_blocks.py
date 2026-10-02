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


AXIS = {
    "variants": {
        "axis=x": {"model": "examplemod:block/beam_x"},
        "axis=y": {"model": "examplemod:block/beam_y"},
        "axis=z": {"model": "examplemod:block/beam_z"},
    }
}


def build_axis(tmp_path, blockstate=None, boxes=None, textures=None):
    assets = tmp_path / "assets" / "examplemod"
    (assets / "blockstates").mkdir(parents=True, exist_ok=True)
    (assets / "models" / "block").mkdir(parents=True, exist_ok=True)
    (assets / "textures" / "block").mkdir(parents=True, exist_ok=True)
    (assets / "blockstates" / "beam.json").write_text(
        json.dumps(blockstate if blockstate is not None else AXIS)
    )
    boxes = boxes or {
        "y": ([6, 0, 6], [10, 16, 10]),
        "x": ([0, 6, 6], [16, 10, 10]),
        "z": ([6, 6, 0], [10, 10, 16]),
    }
    faces = {f: {"texture": "#all"} for f in ("down", "up", "north", "south", "west", "east")}
    for axis, (start, stop) in boxes.items():
        texture = (textures or {}).get(axis, "examplemod:block/beam")
        (assets / "models" / "block" / f"beam_{axis}.json").write_text(
            json.dumps(
                {
                    "textures": {"all": texture},
                    "elements": [{"from": start, "to": stop, "faces": faces}],
                }
            )
        )
    for name in ("beam", "other"):
        (assets / "textures" / "block" / f"{name}.png").write_bytes(b"png")
    return SourceMod(root=tmp_path, namespace="examplemod")


def test_a_pillar_converts_with_one_geometry_per_axis(tmp_path):
    result = blocks.convert(build_axis(tmp_path))
    assert result.unhandled == []
    for axis in ("x", "y", "z"):
        assert f"models/blocks/beam_{axis}.geo.json" in result.files
    body = result.files["blocks/beam.json"]["minecraft:block"]
    assert body["description"]["traits"] == {
        "minecraft:placement_position": {"enabled_states": ["minecraft:block_face"]}
    }
    assert body["components"]["minecraft:geometry"] == "geometry.examplemod.beam_y"


def test_the_pillar_permutations_cover_the_four_horizontal_faces(tmp_path):
    result = blocks.convert(build_axis(tmp_path))
    permutations = result.files["blocks/beam.json"]["minecraft:block"]["permutations"]
    by_geometry = {
        p["components"]["minecraft:geometry"]: p["condition"] for p in permutations
    }
    assert set(by_geometry) == {"geometry.examplemod.beam_x", "geometry.examplemod.beam_z"}
    assert "'east'" in by_geometry["geometry.examplemod.beam_x"]
    assert "'west'" in by_geometry["geometry.examplemod.beam_x"]
    assert "'north'" in by_geometry["geometry.examplemod.beam_z"]
    assert "'south'" in by_geometry["geometry.examplemod.beam_z"]
    # Up and down stay with the default components, which carry the y geometry.
    for condition in by_geometry.values():
        assert "'up'" not in condition and "'down'" not in condition


def test_a_pillar_missing_an_axis_is_refused(tmp_path):
    partial = {"variants": {k: v for k, v in AXIS["variants"].items() if k != "axis=z"}}
    result = blocks.convert(build_axis(tmp_path, blockstate=partial))
    assert "blocks/beam.json" not in result.files
    assert any("only ['x', 'y']" in item.reason for item in result.unhandled)


def test_a_pillar_that_turns_one_shared_model_gets_a_geometry_per_axis(tmp_path):
    shared = {
        "variants": {
            "axis=x": {"model": "examplemod:block/beam_y", "x": 90, "y": 90},
            "axis=y": {"model": "examplemod:block/beam_y"},
            "axis=z": {"model": "examplemod:block/beam_y", "x": 90},
        }
    }
    result = blocks.convert(build_axis(tmp_path, blockstate=shared))
    assert "blocks/beam.json" in result.files
    assert not [i for i in result.unhandled if "beam" in i.source]
    for axis in ("x", "y", "z"):
        assert f"models/blocks/beam_{axis}.geo.json" in result.files


def test_a_shared_model_turned_with_uvlock_is_still_refused(tmp_path):
    shared = {
        "variants": {
            "axis=x": {"model": "examplemod:block/beam_y", "x": 90, "y": 90, "uvlock": True},
            "axis=y": {"model": "examplemod:block/beam_y"},
            "axis=z": {"model": "examplemod:block/beam_y", "x": 90, "uvlock": True},
        }
    }
    result = blocks.convert(build_axis(tmp_path, blockstate=shared))
    assert "blocks/beam.json" not in result.files
    assert any("uvlock" in i.reason for i in result.unhandled)


def test_each_axis_carries_its_own_materials(tmp_path):
    # A beam's caps face up/down when it stands and west/east when it lies along
    # x, so the three models legitimately differ and materials ride along with
    # the geometry rather than having to agree.
    mod = build_axis(tmp_path, textures={"x": "examplemod:block/other"})
    result = blocks.convert(mod)
    assert result.unhandled == []
    body = result.files["blocks/beam.json"]["minecraft:block"]

    def textures(instances):
        # Render method follows the png's own alpha (see portkit.png); this test
        # is only about which texture rides with which axis.
        return {face: spec["texture"] for face, spec in instances.items()}

    assert textures(body["components"]["minecraft:material_instances"]) == {
        "*": "examplemod:beam"
    }
    by_geometry = {
        p["components"]["minecraft:geometry"]: textures(p["components"]["minecraft:material_instances"])
        for p in body["permutations"]
    }
    assert by_geometry["geometry.examplemod.beam_x"] == {"*": "examplemod:other"}
    assert by_geometry["geometry.examplemod.beam_z"] == {"*": "examplemod:beam"}


def test_a_pillar_names_the_axis_that_failed(tmp_path):
    mod = build_axis(tmp_path, textures={"z": "minecraft:block/stone"})
    result = blocks.convert(mod)
    assert any(item.reason.startswith("axis=z:") for item in result.unhandled)


def test_random_models_ship_the_first_with_a_note(tmp_path):
    """Java picks between two models; Bedrock gets the first and says so."""
    blockstate = {
        "variants": {
            "": [
                {"model": "examplemod:block/steel_block"},
                {"model": "examplemod:block/steel_block_alt"},
            ]
        }
    }
    result = blocks.convert(build(tmp_path, blockstate, CUBE_ALL))

    assert result.unhandled == []
    components = result.files["blocks/steel_block.json"]["minecraft:block"]["components"]
    assert components["minecraft:material_instances"]["*"]["texture"] == (
        "examplemod:steel_block"
    )
    note = "".join(result.notes)
    assert "steel_block_alt" in note
    assert "at random" in note


def test_random_turns_of_one_model_ship_one_facing(tmp_path):
    """Four random y turns of a single model converge on the unturned one."""
    blockstate = {
        "variants": {
            "": [
                {"model": "examplemod:block/steel_block"},
                {"model": "examplemod:block/steel_block", "y": 90},
                {"model": "examplemod:block/steel_block", "y": 180},
                {"model": "examplemod:block/steel_block", "y": 270},
            ]
        }
    }
    result = blocks.convert(build(tmp_path, blockstate, CUBE_ALL))

    assert result.unhandled == []
    assert "blocks/steel_block.json" in result.files
    note = "".join(result.notes)
    assert "4 random rotations" in note
    assert "same way" in note


def test_a_random_first_model_that_is_rotated_is_still_refused(tmp_path):
    """Nothing here says which way the unrotated block should face."""
    blockstate = {
        "variants": {
            "": [
                {"model": "examplemod:block/steel_block", "x": 90},
                {"model": "examplemod:block/steel_block"},
            ]
        }
    }
    result = blocks.convert(build(tmp_path, blockstate, CUBE_ALL))

    assert result.files == {}
    assert "rotated" in result.unhandled[0].reason


def test_random_entries_naming_no_model_are_refused(tmp_path):
    blockstate = {"variants": {"": [{"y": 90}, {"y": 180}]}}
    result = blocks.convert(build(tmp_path, blockstate, CUBE_ALL))

    assert result.files == {}
    assert "name no model" in result.unhandled[0].reason
