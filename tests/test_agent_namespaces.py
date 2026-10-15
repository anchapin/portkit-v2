"""Agent-written files may only name ids in namespaces the mod has (#147).

On real-mod residue GLM 5.3 wrote storage drawers blocks naming ``sd:`` ids, a
typo for the mod's ``storagedrawers`` namespace, and every guard passed them:
the recipe ref check (#132) only reads recipes.
"""
import json
import shutil
import zipfile
from pathlib import Path

import pytest

from portkit import corpus
from portkit.agent.fake import FakeLLM, tool_call
from portkit.agent.loop import Message
from portkit.agent.refs import (
    document_ids,
    lang_ids,
    source_namespaces,
    unknown_namespace_refs,
    valid_namespaces,
)
from portkit.agent.residue import ResidueAgent, _TrackingToolBox, group_residue
from portkit.pipeline import convert

ROOT = Path(__file__).resolve().parents[1]
AGENT_MOD = ROOT / "fixtures" / "agent_mod" / "input"
SWORD = "item:assets/examplemod/models/item/steel_sword.json"
SWORD_PATH = "behavior_pack/items/steel_sword.json"
RECIPE_PATH = "behavior_pack/recipes/alloy_block.json"


def _sword(repair="examplemod:steel_ingot", icon="examplemod:steel_sword"):
    return {
        "format_version": "1.21.40",
        "minecraft:item": {
            "description": {"identifier": "examplemod:steel_sword", "menu_category": {"category": "equipment"}},
            "components": {
                "minecraft:icon": icon,
                "minecraft:display_name": {"value": "item.examplemod:steel_sword.name"},
                "minecraft:hand_equipped": True,
                "minecraft:max_stack_size": 1,
                "minecraft:repairable": {"repair_items": [{"items": [repair]}]},
                "minecraft:tags": {"tags": ["minecraft:is_sword"]},
            },
        },
    }


def _tree(tmp_path, source=AGENT_MOD):
    out = tmp_path / "out"
    convert(source, out)
    return out


def _put(out, rel, doc):
    target = out / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(doc) if not isinstance(doc, str) else doc)


# -- what counts as an id -----------------------------------------------

def test_document_ids_reads_values_keys_molang_and_tag_components():
    doc = {
        "minecraft:block": {
            "description": {"identifier": "sd:drawer", "states": {"sd:facing": ["north", "south"]}},
            "components": {"tag:sd:storage": {}, "minecraft:loot": "loot_tables/blocks/drawer.json"},
            "permutations": [{"condition": "q.block_state('sd:facing') == 'north'", "components": {}}],
        },
        "aux": "minecraft:dye:4",
    }
    found = sorted(ident for _, ident in document_ids(doc))
    assert found == sorted([
        "minecraft:block", "sd:drawer", "sd:facing", "sd:storage", "minecraft:loot", "sd:facing",
        "minecraft:dye",
    ])


def test_times_urls_and_translation_keys_are_not_mistaken_for_ids():
    doc = {"time": "12:30", "url": "https://example.com/x", "name": "item.examplemod:steel_sword.name",
           "format_version": "1.21.40", "geometry": "geometry.examplemod.drawer"}
    assert [ident for _, ident in document_ids(doc)] == ["examplemod:steel_sword"]


def test_lang_keys_carry_their_id():
    text = "tile.sd:drawer.name=Drawer\nitem.examplemod:steel_sword=Steel Sword\n## comment\nitemGroup.name.x=X\n"
    assert [ident for _, ident in lang_ids(text)] == ["sd:drawer", "examplemod:steel_sword"]


def test_valid_namespaces_are_vanilla_the_mods_folders_and_the_conversion(tmp_path):
    assert source_namespaces(AGENT_MOD) == {"examplemod"}
    assert valid_namespaces(AGENT_MOD, "packid") == {"minecraft", "examplemod", "packid"}


# -- the check -----------------------------------------------------------

def test_a_typo_namespace_is_flagged_and_named(tmp_path):
    out = _tree(tmp_path)
    _put(out, SWORD_PATH, _sword(repair="ex:steel_ingot"))
    bad = unknown_namespace_refs(out, [SWORD_PATH], AGENT_MOD, "examplemod")
    assert [r.describe() for r in bad] == [
        f"{SWORD_PATH} minecraft:item.components.minecraft:repairable.repair_items[0].items[0]: id 'ex:steel_ingot'"
    ]


def test_vanilla_mod_and_conversion_namespaces_pass(tmp_path):
    out = _tree(tmp_path)
    _put(out, SWORD_PATH, _sword(repair="minecraft:iron_ingot"))
    _put(out, "behavior_pack/items/other.json", _sword(repair="packid:thing"))
    _put(out, "resource_pack/texts/en_US.lang", "tile.examplemod:alloy_block.name=Alloy Block\n")
    written = [SWORD_PATH, "behavior_pack/items/other.json", "resource_pack/texts/en_US.lang"]
    assert unknown_namespace_refs(out, written, AGENT_MOD, "packid") == []


def test_an_id_the_file_already_held_is_not_the_sessions(tmp_path):
    out = _tree(tmp_path)
    original = json.dumps(_sword(repair="othermod:gear")).encode()
    _put(out, SWORD_PATH, _sword(repair="othermod:gear", icon="othermod:icon"))
    bad = unknown_namespace_refs(out, [SWORD_PATH], AGENT_MOD, "examplemod", {SWORD_PATH: original})
    assert [r.ident for r in bad] == ["othermod:icon"]


def test_a_foreign_id_the_source_names_passes(tmp_path):
    source = tmp_path / "src"
    shutil.copytree(AGENT_MOD, source)
    compat = source / "data" / "examplemod" / "recipes" / "compat_gear.json"
    compat.write_text(json.dumps({"type": "minecraft:crafting_shapeless",
                                  "ingredients": [{"item": "othermod:gear"}],
                                  "result": {"item": "examplemod:steel_ingot"}}))
    out = _tree(tmp_path, source)
    _put(out, SWORD_PATH, _sword(repair="othermod:gear"))
    assert unknown_namespace_refs(out, [SWORD_PATH], source, "examplemod") == []
    _put(out, SWORD_PATH, _sword(repair="othermod:sprocket"))
    assert [r.ident for r in unknown_namespace_refs(out, [SWORD_PATH], source, "examplemod")] == ["othermod:sprocket"]


def test_a_lang_line_in_a_typo_namespace_is_flagged(tmp_path):
    out = _tree(tmp_path)
    box = _TrackingToolBox(AGENT_MOD, out, "examplemod")
    box.set_lang_entries("resource_pack/texts/en_US.lang", ["tile.sd:alloy_block.name=Alloy Block"])
    assert [r.ident for r in box.unknown_namespaces()] == ["sd:alloy_block"]


def test_validate_names_the_bad_id_and_the_valid_namespaces(tmp_path):
    out = _tree(tmp_path)
    box = _TrackingToolBox(AGENT_MOD, out, "examplemod")
    box.write_output(SWORD_PATH, _sword(repair="ex:steel_ingot"))
    report = box.validate()
    found = [f for f in report["findings"] if f["rule"] == "agent.unknown_namespace"]
    assert report["ok"] is False and len(found) == 1
    assert "'ex:steel_ingot'" in found[0]["message"]
    assert "Valid namespaces: minecraft, examplemod" in found[0]["message"]


def test_a_recipe_ref_is_reported_once_by_the_recipe_check(tmp_path):
    out = _tree(tmp_path)
    box = _TrackingToolBox(AGENT_MOD, out, "examplemod")
    box.write_output(RECIPE_PATH, {
        "format_version": "1.20.10",
        "minecraft:recipe_shapeless": {
            "description": {"identifier": "examplemod:alloy_block"},
            "tags": ["crafting_table"],
            "ingredients": [{"item": "ex:steel_ingot"}],
            "result": {"item": "examplemod:alloy_block"},
        },
    })
    rules = [f["rule"] for f in box.validate()["findings"] if f["rule"].startswith("agent.")]
    assert rules == ["agent.unresolved_ref"]


# -- the group -----------------------------------------------------------

def _script_for_sword(tmp_path, sword_steps):
    probe = convert(AGENT_MOD, tmp_path / "probe")
    script = []
    for group in group_residue(probe.unhandled):
        script += sword_steps if group.key == SWORD else [Message("assistant", "No Bedrock form.")]
    return script


def _run(tmp_path, script):
    result = convert(AGENT_MOD, tmp_path / "out", agent=ResidueAgent(FakeLLM(script)))
    return result, {o.key: o for o in result.agent.outcomes}


def test_a_group_that_keeps_a_typo_namespace_is_rolled_back(tmp_path):
    script = _script_for_sword(tmp_path, [
        tool_call("write_output", path=SWORD_PATH, content=_sword(repair="ex:steel_ingot")),
        tool_call("validate"),
        Message("assistant", "Converted the steel sword."),
    ])
    result, by_key = _run(tmp_path, script)
    sword = by_key[SWORD]
    assert sword.status == "rolled_back"
    assert sword.unknown_namespaces == [
        f"{SWORD_PATH} minecraft:item.components.minecraft:repairable.repair_items[0].items[0]: id 'ex:steel_ingot'"
    ]
    assert sword.note.startswith("rolled back: unknown namespace(s):")
    assert sword.to_dict()["unknown_namespaces"] == sword.unknown_namespaces
    assert not (tmp_path / "out" / SWORD_PATH).exists()
    assert result.report.ok


def test_fixing_the_namespace_resolves(tmp_path):
    script = _script_for_sword(tmp_path, [
        tool_call("write_output", path=SWORD_PATH, content=_sword(repair="ex:steel_ingot")),
        tool_call("validate"),
        tool_call("write_output", path=SWORD_PATH, content=_sword()),
        tool_call("validate"),
        Message("assistant", "Wrote the sword."),
    ])
    _, by_key = _run(tmp_path, script)
    assert by_key[SWORD].status == "resolved", by_key[SWORD].note
    assert by_key[SWORD].unknown_namespaces == []


# -- real mod ------------------------------------------------------------

@pytest.mark.realmods
def test_storage_drawers_sd_typos_are_caught(tmp_path):
    """The GLM 5.3 shape from #86's real-mod run, on the real storage drawers jar."""
    mod = next(m for m in corpus.load() if m.name == "storage_drawers_1122")
    jar = corpus.cached(mod)
    if jar is None:
        pytest.skip("storage_drawers_1122 not cached (portkit corpus fetch)")
    source = tmp_path / "src"
    with zipfile.ZipFile(jar) as archive:
        archive.extractall(source)
    out = tmp_path / "out"
    result = convert(jar, out)
    assert result.namespace == "storagedrawers"
    block = {
        "format_version": "1.21.40",
        "minecraft:block": {
            "description": {"identifier": "storagedrawers:basicdrawers"},
            "components": {"minecraft:loot": "loot_tables/blocks/basicdrawers.json",
                           "minecraft:display_name": "tile.storagedrawers:basicdrawers.name"},
        },
    }
    rel = "behavior_pack/blocks/basicdrawers.json"
    _put(out, rel, block)
    assert unknown_namespace_refs(out, [rel], source, result.namespace) == []
    block["minecraft:block"]["description"]["identifier"] = "sd:basicdrawers"
    _put(out, rel, block)
    assert [r.ident for r in unknown_namespace_refs(out, [rel], source, result.namespace)] == ["sd:basicdrawers"]
