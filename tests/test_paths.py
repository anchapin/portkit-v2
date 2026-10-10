"""Pack paths stay within Bedrock's per-device limits (#117)."""
import json

from portkit.model import ConversionResult
from portkit.paths import MAX_PATH, shorten, shorten_paths, too_long
from portkit.pipeline import convert
from portkit.validate import validate_tree

PNG = b"\x89PNG\r\n\x1a\n"
LONG = (
    "textures/items/tool/staff/large_modifiers/"
    "tconstruct_embellishment_tconstruct_slimewood_bloodshroom.png"
)
SIBLING = LONG.replace("bloodshroom", "greenheart")


def test_the_limits_match_mct():
    assert not too_long("a" * 100)
    assert too_long("a" * 101)
    assert not too_long("/".join(["d"] * 8 + ["f.png"]))  # 8 directories
    assert too_long("/".join(["d"] * 9 + ["f.png"]))  # 9 directories


def test_a_long_path_keeps_its_directory_and_prefix_and_is_stable():
    new = shorten(LONG)
    assert len(new) <= MAX_PATH and not too_long(new)
    assert new.startswith("textures/items/tool/staff/large_modifiers/tconstruct_embellishment_")
    assert new.endswith(".png")
    assert shorten(LONG) == new
    # Two paths that share the kept prefix still land on different names.
    assert shorten(SIBLING) != new


def test_a_shortened_name_never_lands_on_a_file_already_there():
    first = shorten(LONG)
    assert shorten(LONG, taken={first}) != first


def test_a_path_too_deep_moves_up_to_its_first_two_directories():
    deep = "textures/items/" + "/".join(f"d{i}" for i in range(9)) + "/leaf.png"
    new = shorten(deep)
    assert new.startswith("textures/items/leaf_") and not too_long(new)


def test_references_move_with_the_file_and_index_keys_do_not():
    key = "tconstruct:tool_staff_large_modifiers_tconstruct_embellishment_tconstruct_slimewood_bloodshroom"
    old_ref = LONG[: -len(".png")]
    long_sound = "sounds/" + "very_long_directory_name/" * 4 + "a_sound_with_a_long_name.ogg"
    result = ConversionResult(files={
        LONG: PNG,
        "textures/items/short.png": PNG,
        long_sound: b"OggS",
        "textures/item_texture.json": {"texture_data": {
            key: {"textures": old_ref}, "m:short": {"textures": "textures/items/short"}}},
        "textures/terrain_texture.json": {"texture_data": {key: {"textures": old_ref}}},
        "textures/flipbook_textures.json": [{"flipbook_texture": old_ref, "atlas_tile": key}],
        "sounds/sound_definitions.json": {"sound_definitions": {"m:e": {"sounds": [
            long_sound[:-4], {"name": long_sound[:-4], "volume": 0.5}]}}},
    })
    renames = shorten_paths(result)
    assert set(renames) == {LONG, long_sound}
    new_ref = renames[LONG][: -len(".png")]
    new_sound = renames[long_sound][: -len(".ogg")]
    assert result.files[renames[LONG]] == PNG and LONG not in result.files
    items = result.files["textures/item_texture.json"]["texture_data"]
    assert items[key] == {"textures": new_ref}  # same key, new path
    assert items["m:short"] == {"textures": "textures/items/short"}
    assert result.files["textures/terrain_texture.json"]["texture_data"][key] == {"textures": new_ref}
    assert result.files["textures/flipbook_textures.json"][0]["flipbook_texture"] == new_ref
    sounds = result.files["sounds/sound_definitions.json"]["sound_definitions"]["m:e"]["sounds"]
    assert sounds == [new_sound, {"name": new_sound, "volume": 0.5}]
    [note] = result.notes
    assert "shortened 2 pack path(s)" in note


def test_nothing_long_means_nothing_changes():
    files = {"textures/items/a.png": PNG, "textures/item_texture.json": {"texture_data": {}}}
    result = ConversionResult(files=dict(files))
    assert shorten_paths(result) == {}
    assert result.files == files and result.notes == []


def _mod_with_a_long_item_texture(tmp_path):
    src = tmp_path / "src"
    sub = "tool/staff/large_modifiers/tconstruct_embellishment_tconstruct_slimewood_bloodshroom"
    tex = src / "assets" / "examplemod" / "textures" / "item" / f"{sub}.png"
    tex.parent.mkdir(parents=True)
    tex.write_bytes(PNG)
    model = src / "assets" / "examplemod" / "models" / "item" / "staff.json"
    model.parent.mkdir(parents=True)
    model.write_text(json.dumps({"parent": "item/generated", "textures": {"layer0": f"examplemod:item/{sub}"}}))
    return src


def test_end_to_end_the_pack_is_within_limits_and_every_reference_resolves(tmp_path):
    result = convert(_mod_with_a_long_item_texture(tmp_path), tmp_path / "out")
    pack = result.tree / "resource_pack"
    rels = [p.relative_to(pack).as_posix() for p in pack.rglob("*") if p.is_file()]
    assert rels and not [r for r in rels if too_long(r)]
    index = json.loads((pack / "textures" / "item_texture.json").read_text())["texture_data"]
    key = "examplemod:tool_staff_large_modifiers_tconstruct_embellishment_tconstruct_slimewood_bloodshroom"
    assert (pack / f"{index[key]['textures']}.png").is_file()
    assert result.report.ok, [f.message for f in result.report.errors]
    assert any("shortened 1 pack path" in n for n in result.notes)


def test_the_validator_errors_on_a_path_over_the_limit(tmp_path):
    result = convert(_mod_with_a_long_item_texture(tmp_path), tmp_path / "out")
    pack = result.tree / "resource_pack"
    target = pack / LONG
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(PNG)
    report = validate_tree(result.tree)
    found = [f for f in report.errors if f.rule == "pack.path_length"]
    assert [f.path for f in found] == [f"resource_pack/{LONG}"]
    assert not report.ok
