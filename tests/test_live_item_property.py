"""#344 (part of #277): items whose look switches on an item property the mod's
own code registers are the explained ``live_item_property`` residue.

The class files under tests/data/propcode/classes are javac 21 output of the
example mod in tests/data/propcode/src against signature-only stubs (rebuild
with tests/data/propcode/build.sh). ExampleClient registers ``examplemod:angle``
(a ResourceLocation from two strings), ``examplemod:pressure`` and
``examplemod:level`` (through the mod's one- and two-level helpers),
``examplemod:fill`` (a static field), ``examplemod:phase`` (the two-string
constructor) and vanilla's ``time`` on its own item; Unrelated builds
``examplemod:decoy`` but handles no item property function.
"""
import json
from pathlib import Path

import pytest

from portkit.agent.residue import SKIP_KINDS
from portkit.bytecode import ClassIndex
from portkit.converters import items
from portkit.itemprops import code_registered, full_name
from portkit.model import SourceMod

CLASSES = Path(__file__).parent / "data" / "propcode" / "classes"


@pytest.fixture(scope="module")
def index():
    return ClassIndex.from_source(CLASSES)


def build(tmp_path, models, classes):
    assets = tmp_path / "assets" / "examplemod"
    (assets / "models" / "item").mkdir(parents=True, exist_ok=True)
    for name, model in models.items():
        (assets / "models" / "item" / f"{name}.json").write_text(json.dumps(model))
    (assets / "lang").mkdir(parents=True, exist_ok=True)
    (assets / "lang" / "en_us.json").write_text(json.dumps({f"item.examplemod.{n}": n for n in models}))
    return SourceMod(root=tmp_path, namespace="examplemod", classes=classes)


def flat(name, *predicates):
    return {"parent": "item/generated", "textures": {"layer0": f"examplemod:item/{name}"},
            "overrides": [{"predicate": p, "model": f"examplemod:item/{name}_{i}"}
                          for i, p in enumerate(predicates)]}


def test_names_read_from_the_registering_class(index):
    found = code_registered(index, [
        "examplemod:angle", "examplemod:pressure", "examplemod:level", "examplemod:fill",
        "examplemod:phase", "time", "examplemod:decoy", "examplemod:nope"])
    assert sorted(found) == ["examplemod:angle", "examplemod:fill", "examplemod:level",
                             "examplemod:phase", "examplemod:pressure", "time"]
    assert set(found.values()) == {"com/example/pmod/ExampleClient"}


def test_a_name_built_outside_a_property_class_is_not_a_registration(index):
    assert code_registered(index, ["examplemod:decoy"]) == {}


def test_no_classes_reads_nothing():
    assert code_registered(None, ["examplemod:angle"]) == {}


def test_full_name():
    assert full_name("angle") == "minecraft:angle"
    assert full_name("examplemod:angle") == "examplemod:angle"


def test_the_kind_is_explained():
    assert items.LIVE_ITEM_PROPERTY == "live_item_property"
    assert "live_item_property" in SKIP_KINDS


def test_a_compass_on_a_registered_readout_is_explained_residue(tmp_path, index):
    """Nature's Compass' shape: a needle frame per angle, registered in code."""
    mod = build(tmp_path, {"compass": flat("compass", {"examplemod:angle": 0.0}, {"examplemod:angle": 0.5})},
                index)
    result = items.convert(mod)
    assert result.files == {}
    [u] = result.unhandled
    assert u.kind == "live_item_property"
    assert u.source == "assets/examplemod/models/item/compass.json"
    assert "'examplemod:angle' (built in com.example.pmod.ExampleClient)" in u.reason
    assert "static texture" in u.reason and "#169" in u.reason


def test_an_unknown_property_registered_in_code_is_explained(tmp_path, index):
    mod = build(tmp_path, {"gauge": flat("gauge", {"examplemod:pressure": 0.5}, {"examplemod:level": 1})},
                index)
    [u] = items.convert(mod).unhandled
    assert u.kind == "live_item_property"
    assert "item properties 'examplemod:pressure'" in u.reason and "'examplemod:level'" in u.reason


def test_resting_predicates_beside_a_registered_one_do_not_block_it(tmp_path, index):
    mod = build(tmp_path, {"pouch": flat("pouch", {"damaged": 1}, {"examplemod:fill": 0.5})}, index)
    [u] = items.convert(mod).unhandled
    assert u.kind == "live_item_property"
    assert "damaged" not in u.reason


def test_an_unregistered_property_keeps_the_item_plain_residue(tmp_path, index):
    mod = build(tmp_path, {"gauge": flat("gauge", {"examplemod:pressure": 0.5}, {"examplemod:nope": 1})},
                index)
    [u] = items.convert(mod).unhandled
    assert u.kind == "item"  # the reason is the existing one, unchanged


def test_a_decoy_name_is_plain_residue(tmp_path, index):
    [u] = items.convert(build(tmp_path, {"decoy": flat("decoy", {"examplemod:decoy": 1})}, index)).unhandled
    assert u.kind == "item"


@pytest.mark.parametrize("key", ["time", "minecraft:time"])
def test_a_vanilla_name_stays_plain_residue_even_when_the_mod_builds_it(tmp_path, index, key):
    """Pick 2a: the mod may build vanilla's name only to read vanilla's own property."""
    [u] = items.convert(build(tmp_path, {"watch": flat("watch", {key: 0.5})}, index)).unhandled
    assert u.kind == "item" and "live reading" in u.reason


def test_a_mix_with_a_vanilla_readout_stays_plain_residue(tmp_path, index):
    mod = build(tmp_path, {"watch": flat("watch", {"examplemod:phase": 0.5}, {"time": 0.5})}, index)
    [u] = items.convert(mod).unhandled
    assert u.kind == "item"


def test_without_classes_the_item_stays_plain_residue(tmp_path):
    mod = build(tmp_path, {"compass": flat("compass", {"examplemod:angle": 0.0})}, None)
    [u] = items.convert(mod).unhandled
    assert u.kind == "item" and "live reading" in u.reason


def test_resting_overrides_still_convert(tmp_path, index):
    """Nothing that converts today changes: a resting look still ships."""
    mod = build(tmp_path, {"slingshot": flat("slingshot", {"examplemod:pulling": 1})}, index)
    result = items.convert(mod)
    assert result.unhandled == []
    assert "items/slingshot.json" in result.files


def test_malformed_overrides_stay_plain_residue(tmp_path, index):
    model = {"parent": "item/generated", "textures": {"layer0": "examplemod:item/x"},
             "overrides": [{"model": "examplemod:item/a"}]}
    [u] = items.convert(build(tmp_path, {"x": model}, index)).unhandled
    assert u.kind == "item" and "no predicate" in u.reason


def test_a_3d_model_with_a_registered_property_keeps_its_own_reason(tmp_path, index):
    model = {"parent": "item/generated", "textures": {"layer0": "examplemod:item/x"},
             "elements": [{"from": [0, 0, 0], "to": [16, 16, 1], "faces": {}}],
             "overrides": [{"predicate": {"examplemod:angle": 0.5}, "model": "examplemod:item/a"}]}
    [u] = items.convert(build(tmp_path, {"x": model}, index)).unhandled
    assert u.kind == "item" and "elements" in u.reason
