"""Mantle's load-condition types, evaluated by the mantle library adapter (#245).

Moved from tests/test_load_conditions.py with the code (``conditions.py`` ->
``src/portkit/adapters/mantle``); the behaviour is unchanged.
"""
import json

from portkit import adapters
from portkit.adapters import mantle
from portkit.conditions import LoadContext
from portkit.converters import recipes
from portkit.model import SourceMod

SHAPED = {
    "type": "minecraft:crafting_shaped",
    "pattern": ["##"],
    "key": {"#": {"item": "minecraft:stick"}},
    "result": {"item": "minecraft:ladder"},
}


def _mod(tmp_path, files: dict, mods=("examplemod",)) -> SourceMod:
    root = tmp_path / "mod"
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body))
    return SourceMod(root=root, namespace="examplemod", loader="forge", minecraft="1.20.1",
                     mods={m: "1.2.3" for m in mods}, requires=frozenset({"mantle"}))


def _converts(mod) -> bool:
    return "recipes/thing.json" in recipes.convert(mod, context=LoadContext(mod)).files


def test_mantle_is_a_registered_library_adapter():
    assert mantle.ADAPTER in adapters.ADAPTERS
    assert mantle.ADAPTER.library
    assert set(mantle.ADAPTER.conditions) == {"mantle:tag_filled", "mantle:tag_combination_filled"}
    assert adapters.condition_handler("mantle:tag_filled") is mantle.tag_filled


def test_tag_filled(tmp_path):
    files = {
        "data/examplemod/tags/items/filled.json": {"values": ["examplemod:tin_ingot"]},
        "data/examplemod/tags/items/others.json": {"values": [{"id": "othermod:x", "required": False}]},
    }
    for tag, expect in (("examplemod:filled", True), ("examplemod:others", False)):
        body = {**SHAPED, "conditions": [{"type": "mantle:tag_filled", "tag": tag}]}
        mod = _mod(tmp_path / tag.split(":")[1], {**files, "data/examplemod/recipes/thing.json": body})
        assert _converts(mod) is expect, tag


def test_own_namespace_members_count_even_when_it_is_not_the_mod_id(tmp_path):
    files = {"data/examplemod/tags/items/filled.json": {"values": ["examplemod:tin_ingot"]},
             "data/examplemod/recipes/thing.json": {**SHAPED, "conditions": [
                 {"type": "mantle:tag_filled", "tag": "examplemod:filled"}]}}
    assert _converts(_mod(tmp_path, files, mods=("example_mod_id",)))


def test_tag_combination_filled(tmp_path):
    files = {
        "data/examplemod/tags/items/ores.json": {"values": ["examplemod:tin_ore", "examplemod:dense_ore"]},
        "data/examplemod/tags/items/dense.json": {"values": ["examplemod:dense_ore"]},
    }
    hit = {"type": "mantle:tag_combination_filled", "match": ["examplemod:ores", "examplemod:dense"]}
    miss = {"type": "mantle:tag_combination_filled", "match": "examplemod:dense", "ignore": "examplemod:ores"}
    for name, cond, expect in (("hit", hit, True), ("miss", miss, False)):
        mod = _mod(tmp_path / name, {**files, "data/examplemod/recipes/thing.json": {**SHAPED, "conditions": [cond]}})
        assert _converts(mod) is expect


def test_tag_combination_reasons(tmp_path):
    context = LoadContext(_mod(tmp_path, {}))
    kind = "mantle:tag_combination_filled"
    bad = context.evaluate([{"type": kind, "match": [], "registry": "minecraft:block"}])
    assert (bad.passes, bad.why) == (None, f"{kind}: unreadable match list or a non-item registry")
    hit = LoadContext(_mod(tmp_path / "h", {"data/examplemod/tags/items/a.json": {"values": ["examplemod:x"]}}))
    verdict = hit.evaluate([{"type": kind, "match": "examplemod:a"}])
    assert (verdict.passes, verdict.why) == (True, f"{kind}: examplemod:x is in examplemod:a")
