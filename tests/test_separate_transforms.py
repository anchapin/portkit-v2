"""Items whose model picks a look per render context (#181).

Forge's and NeoForge's ``separate_transforms`` loader names a ``base`` model
and per-context ``perspectives``. The gui view is the inventory icon; the
held view, when it draws elements in one texture, ships as an attachable
bound to the holder's item slot (DEFAULT pose: Java's held display transforms
are not carried).
"""
import json

import pytest

from portkit import paths, pipeline
from portkit.converters import items
from portkit.model import ConversionResult, SourceMod

ELEMENT = {
    "from": [7, 0, 7], "to": [9, 14, 9],
    "faces": {f: {"uv": [0, 0, 2, 14], "texture": "#body"}
              for f in ("north", "east", "south", "west", "up", "down")},
}
IN_HAND = {"textures": {"body": "examplemod:item/flute_model"}, "elements": [ELEMENT],
           "display": {"thirdperson_righthand": {"translation": [0, -1, 0]}}}
GUI = {"parent": "item/generated", "textures": {"layer0": "examplemod:item/flute"}}


def separate(loader="forge:separate_transforms", base=None, perspectives=None, **extra):
    return {"loader": loader,
            "base": base if base is not None else {"parent": "examplemod:item/flute_in_hand"},
            "perspectives": perspectives if perspectives is not None else {
                "gui": {"parent": "examplemod:item/flute_gui"},
                "ground": {"parent": "examplemod:item/flute_gui"},
                "fixed": {"parent": "examplemod:item/flute_gui"},
            }, **extra}


def build(tmp_path, models, registered=("flute",), textures=("flute", "flute_model")):
    assets = tmp_path / "assets" / "examplemod"
    (assets / "models" / "item").mkdir(parents=True, exist_ok=True)
    for name, model in models.items():
        (assets / "models" / "item" / f"{name}.json").write_text(json.dumps(model))
    (assets / "lang").mkdir(parents=True, exist_ok=True)
    (assets / "lang" / "en_us.json").write_text(
        json.dumps({f"item.examplemod.{n}": n for n in registered}))
    (assets / "textures" / "item").mkdir(parents=True, exist_ok=True)
    for name in textures:
        (assets / "textures" / "item" / f"{name}.png").write_bytes(b"png")
    return SourceMod(root=tmp_path, namespace="examplemod")


def flute_mod(tmp_path, **kwargs):
    return build(tmp_path, {"flute": separate(**kwargs), "flute_gui": GUI, "flute_in_hand": IN_HAND})


@pytest.mark.parametrize("loader", ["forge:separate_transforms", "neoforge:separate_transforms"])
def test_the_gui_view_is_the_icon_and_the_held_model_an_attachable(tmp_path, loader):
    result = items.convert(flute_mod(tmp_path, loader=loader))
    assert result.unhandled == []
    item = result.files["items/flute.json"]["minecraft:item"]
    assert item["components"]["minecraft:icon"] == "examplemod:flute"
    description = result.files["attachables/flute.json"]["minecraft:attachable"]["description"]
    assert description["identifier"] == "examplemod:flute"
    assert description["textures"]["default"] == "textures/items/flute_model"
    assert description["geometry"]["default"] == "geometry.examplemod.flute.held"
    assert description["render_controllers"] == ["controller.render.item_default"]
    assert description["materials"]["default"] == "entity_alphatest"
    # DEFAULT pose: no animations, so Java's display transforms are not invented onto it.
    assert "animations" not in description and "scripts" not in description
    geo = result.files["models/entity/flute.held.geo.json"]["minecraft:geometry"][0]
    assert geo["description"]["identifier"] == "geometry.examplemod.flute.held"
    [bone] = geo["bones"]
    assert bone["binding"] == "q.item_slot_to_bone_name(c.item_slot)"
    [cube] = bone["cubes"]
    assert cube["origin"] == [-1.0, 0.0, -1.0] and cube["size"] == [2.0, 14.0, 2.0]


def test_the_part_models_are_claimed_not_residue_or_variants(tmp_path):
    result = items.convert(flute_mod(tmp_path))
    assert {"assets/examplemod/models/item/flute_gui.json",
            "assets/examplemod/models/item/flute_in_hand.json"} <= result.consumed
    assert not any("flute_gui" in note and "not a registered item" in note for note in result.notes)
    [note] = [n for n in result.notes if "separate_transforms" in n]
    assert "flute (held 3D model as an attachable (DEFAULT pose" in note
    assert "head" in note  # base drawn on the head in Java, not carried


def test_a_held_model_with_two_textures_holds_the_icon_and_stays_residue(tmp_path):
    two = {**IN_HAND, "textures": {"body": "examplemod:item/flute_model", "band": "examplemod:item/flute"},
           "elements": [ELEMENT, {**ELEMENT, "faces": {"north": {"texture": "#band"}}}]}
    result = items.convert(build(tmp_path, {"flute": separate(), "flute_gui": GUI, "flute_in_hand": two}))
    assert "items/flute.json" in result.files
    assert not any(p.startswith("attachables/") for p in result.files)
    [entry] = result.unhandled
    assert entry.source == "assets/examplemod/models/item/flute_in_hand.json"
    assert entry.reason.startswith("held 3D model of examplemod:flute, not converted")
    assert "one texture" in entry.reason


def test_a_flat_base_with_only_a_head_view_converts_as_its_icon(tmp_path):
    """Supplementaries' confetti popper: flat everywhere but on the head."""
    head = {"textures": {"body": "examplemod:item/flute_model"}, "elements": [ELEMENT]}
    model = separate(base=GUI, perspectives={"head": {"parent": "examplemod:item/flute_head"}})
    result = items.convert(build(tmp_path, {"flute": model, "flute_head": head}))
    assert result.files["items/flute.json"]["minecraft:item"]["components"]["minecraft:icon"] == "examplemod:flute"
    assert not any(p.startswith("attachables/") for p in result.files)
    [entry] = result.unhandled
    assert entry.source.endswith("flute_head.json")
    assert entry.reason.startswith("the head view of examplemod:flute, not carried")
    [note] = [n for n in result.notes if "separate_transforms" in n]
    assert "held as the icon, as in Java" in note


def test_held_views_that_differ_by_hand_hold_the_icon(tmp_path):
    model = separate(perspectives={"gui": GUI, "firstperson_lefthand": GUI})
    result = items.convert(build(tmp_path, {"flute": model, "flute_in_hand": IN_HAND}))
    assert "items/flute.json" in result.files
    assert not any(p.startswith("attachables/") for p in result.files)
    [note] = [n for n in result.notes if "separate_transforms" in n]
    assert "different model per hand" in note


def test_unknown_perspective_keys_are_ignored_as_java_does(tmp_path):
    """Mekanism's meka_tool writes first_person_left_hand, which is no
    ItemDisplayContext serialized name, so Java never reads it."""
    model = separate(perspectives={"gui": GUI, "first_person_left_hand": GUI})
    result = items.convert(build(tmp_path, {"flute": model, "flute_in_hand": IN_HAND}))
    assert "attachables/flute.json" in result.files


def test_the_outer_overrides_decide_and_a_sub_models_are_ignored(tmp_path):
    gui = {**GUI, "overrides": [{"predicate": {"examplemod:mystery": 1}, "model": "examplemod:item/x"}]}
    model = separate(perspectives={"gui": gui},
                     overrides=[{"predicate": {"examplemod:dyed": 1}, "model": "examplemod:item/flute_dyed"}])
    result = items.convert(build(tmp_path, {"flute": model, "flute_in_hand": IN_HAND}))
    assert "items/flute.json" in result.files
    assert any("dyed" in n and "base icon" in n for n in result.notes)


@pytest.mark.parametrize("model, why", [
    ({"loader": "forge:separate_transforms", "perspectives": {}}, "no base model object"),
    ({"loader": "forge:separate_transforms", "base": GUI}, "no perspectives object"),
    ({"loader": "forge:separate_transforms", "base": GUI, "perspectives": {"gui": "x"}}, "not a model object"),
])
def test_a_malformed_separate_transforms_model_stays_residue(tmp_path, model, why):
    result = items.convert(build(tmp_path, {"flute": model}))
    assert result.files == {}
    assert why in result.unhandled[0].reason


def test_an_unregistered_separate_transforms_model_writes_nothing(tmp_path):
    result = items.convert(build(tmp_path, {"flute_dyed": separate(), "flute_gui": GUI,
                                            "flute_in_hand": IN_HAND}, registered=()))
    assert not any(p.startswith(("items/", "attachables/")) for p in result.files)


def test_an_attachable_whose_texture_did_not_convert_is_dropped(tmp_path):
    result = ConversionResult()
    result.files.update(items.convert(flute_mod(tmp_path)).files)
    result.files["textures/item_texture.json"] = {"texture_data": {
        "examplemod:flute": {"textures": "textures/items/flute"}}}
    result.files["textures/items/flute.png"] = b"png"
    pipeline.drop_untextured(result, "examplemod")
    assert "items/flute.json" in result.files
    assert "attachables/flute.json" not in result.files
    assert "models/entity/flute.held.geo.json" not in result.files
    assert any("textures/items/flute_model did not convert" in n for n in result.notes)


def test_an_attachable_goes_with_its_item(tmp_path):
    result = ConversionResult()
    result.files.update(items.convert(flute_mod(tmp_path)).files)
    result.files["textures/items/flute_model.png"] = b"png"
    pipeline.drop_untextured(result, "examplemod")  # the icon texture is missing
    assert "items/flute.json" not in result.files
    assert "attachables/flute.json" not in result.files


def test_a_shortened_texture_path_is_renamed_in_the_attachable(tmp_path):
    long = "textures/items/" + "/".join(["deep"] * 12) + "/flute_model"
    result = ConversionResult()
    result.files[f"{long}.png"] = b"png"
    result.files["attachables/flute.json"] = {"minecraft:attachable": {"description": {
        "identifier": "examplemod:flute", "textures": {"default": long}}}}
    renames = paths.shorten_paths(result)
    new = renames[f"{long}.png"].removesuffix(".png")
    textures = result.files["attachables/flute.json"]["minecraft:attachable"]["description"]["textures"]
    assert textures["default"] == new


def test_dyed_is_a_stored_data_predicate():
    """Supplementaries' quiver registers dyed = hasCustomColor ? 1 : 0."""
    assert items._OVERRIDE_KIND["dyed"] == "state"


def test_a_gui_view_built_by_another_loader_stays_residue(tmp_path):
    """Mekanism's meka_tool: no gui perspective, and the base is an OBJ model."""
    model = separate(base={"loader": "neoforge:obj", "model": "examplemod:models/x.obj"},
                     perspectives={})
    result = items.convert(build(tmp_path, {"flute": model}))
    assert result.files == {}
    assert "model loader 'neoforge:obj'" in result.unhandled[0].reason
