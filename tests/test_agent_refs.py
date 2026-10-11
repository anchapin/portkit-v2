"""Agent-written recipes may only name items and tags that exist (#86).

In the #86 sweep a model wrote ``examplemod:alloy_ingots`` (the Java tag's
name) as a recipe ingredient for agent_mod's alloy block, and the group counted
as resolved because the validator only warns about an undeclared item.
"""
import json
from pathlib import Path

from portkit.agent.fake import FakeLLM, tool_call
from portkit.agent.loop import Message
from portkit.agent.refs import pack_known, recipe_refs, source_items, unresolved_refs
from portkit.agent.residue import ResidueAgent
from portkit.pipeline import convert

ROOT = Path(__file__).resolve().parents[1]
AGENT_MOD = ROOT / "fixtures" / "agent_mod" / "input"
ALLOY = "recipe:data/examplemod/recipes/alloy_block.json"
RECIPE_PATH = "behavior_pack/recipes/alloy_block.json"


def _alloy_recipe(ingredient):
    return {
        "format_version": "1.20.10",
        "minecraft:recipe_shaped": {
            "description": {"identifier": "examplemod:alloy_block"},
            "tags": ["crafting_table"],
            "pattern": ["###", "###", "###"],
            "key": {"#": ingredient},
            "result": {"item": "examplemod:alloy_block"},
        },
    }


def _ingot(name, tags=()):
    components = {"minecraft:icon": f"examplemod:{name}", "minecraft:max_stack_size": 64}
    if tags:
        components["minecraft:tags"] = {"tags": list(tags)}
    return {
        "format_version": "1.20.10",
        "minecraft:item": {
            "description": {"identifier": f"examplemod:{name}", "menu_category": {"category": "items"}},
            "components": components,
        },
    }


def _run(tmp_path, script):
    client = FakeLLM(script)
    result = convert(AGENT_MOD, tmp_path / "out", agent=ResidueAgent(client))
    return result, {o.key: o for o in result.agent.outcomes}, client


def _order(tmp_path):
    """agent_mod's groups in run order, so scripts line up with sessions."""
    result = convert(AGENT_MOD, tmp_path / "probe")
    from portkit.agent.residue import group_residue
    return [g.key for g in group_residue(result.unhandled)]


def _script_for_alloy(tmp_path, alloy_steps):
    order = _order(tmp_path)
    script = []
    for key in order:
        script += alloy_steps if key == ALLOY else [Message("assistant", "No Bedrock form.")]
    return script


def test_a_tag_name_used_as_an_item_is_rolled_back(tmp_path):
    script = _script_for_alloy(tmp_path, [
        tool_call("write_output", path=RECIPE_PATH, content=_alloy_recipe({"item": "examplemod:alloy_ingots"})),
        tool_call("validate"),
        Message("assistant", "Converted the alloy block recipe."),
    ])
    result, by_key, client = _run(tmp_path, script)
    alloy = by_key[ALLOY]
    assert alloy.status == "rolled_back"
    assert alloy.unresolved_refs == [f"{RECIPE_PATH} key['#']: item 'examplemod:alloy_ingots'"]
    assert "unresolved reference" in alloy.note and "examplemod:alloy_ingots" in alloy.note
    assert not (tmp_path / "out" / RECIPE_PATH).exists()
    assert ALLOY.split(":", 1)[1] in [u.source for u in result.unhandled]
    assert result.report.ok

    # The validate tool told the model, so it had the chance to fix it.
    tool_reply = next(
        m for request in client.seen for m in request
        if m.role == "tool" and m.tool_call_id == "call_validate"
    )
    seen = json.loads(tool_reply.content)
    assert seen["ok"] is False
    assert any(f["rule"] == "agent.unresolved_ref" for f in seen["findings"])


def test_a_java_tag_no_pack_item_carries_is_rolled_back(tmp_path):
    script = _script_for_alloy(tmp_path, [
        tool_call("write_output", path=RECIPE_PATH, content=_alloy_recipe({"tag": "examplemod:alloy_ingots"})),
        Message("assistant", "Kept the tag."),
    ])
    _, by_key, _ = _run(tmp_path, script)
    assert by_key[ALLOY].status == "rolled_back"
    assert by_key[ALLOY].unresolved_refs == [f"{RECIPE_PATH} key['#']: tag 'examplemod:alloy_ingots'"]


def test_a_tag_the_pack_items_declare_resolves(tmp_path):
    tag = "examplemod:alloy_ingots"
    script = _script_for_alloy(tmp_path, [
        tool_call("write_output", path="behavior_pack/items/bronze_ingot.json", content=_ingot("bronze_ingot", [tag])),
        tool_call("write_output", path="behavior_pack/items/steel_ingot.json", content=_ingot("steel_ingot", [tag])),
        tool_call("write_output", path=RECIPE_PATH, content=_alloy_recipe({"tag": tag})),
        tool_call("validate"),
        Message("assistant", "Tagged both ingots and kept the tag ingredient."),
    ])
    result, by_key, _ = _run(tmp_path, script)
    assert by_key[ALLOY].status == "resolved", by_key[ALLOY].note
    assert by_key[ALLOY].unresolved_refs == []
    assert result.report.ok


def test_real_items_resolve(tmp_path):
    script = _script_for_alloy(tmp_path, [
        tool_call("write_output", path=RECIPE_PATH, content=_alloy_recipe({"item": "examplemod:steel_ingot"})),
        Message("assistant", "Steel only."),
    ])
    _, by_key, _ = _run(tmp_path, script)
    assert by_key[ALLOY].status == "resolved"


def test_recipe_refs_cover_every_slot():
    body = {
        "key": {"#": {"tag": "a:t"}, "|": "a:stick"},
        "ingredients": [{"item": "a:x"}, "a:y"],
        "result": [{"item": "a:r"}],
        "input": "a:in", "output": "a:out",
        "template": {"item": "a:tpl"}, "base": {"tag": "a:base"}, "addition": "a:add",
    }
    assert sorted((k, i) for _, k, i in recipe_refs(body)) == sorted([
        ("tag", "a:t"), ("item", "a:stick"), ("item", "a:x"), ("item", "a:y"), ("item", "a:r"),
        ("item", "a:in"), ("item", "a:out"), ("item", "a:tpl"), ("tag", "a:base"), ("item", "a:add"),
    ])


def test_source_items_read_definitions_not_tag_names():
    items = source_items(AGENT_MOD)
    assert {"examplemod:steel_ingot", "examplemod:bronze_ingot", "examplemod:steel_sword",
            "examplemod:alloy_block", "minecraft:stick"} <= items
    assert "examplemod:alloy_ingots" not in items  # only ever a tag


def test_vanilla_ids_are_taken_on_faith_and_aux_values_stripped(tmp_path):
    out = tmp_path / "out"
    convert(AGENT_MOD, out)
    rel = "behavior_pack/recipes/x.json"
    (out / rel).write_text(json.dumps({"minecraft:recipe_shapeless": {
        "ingredients": [{"item": "minecraft:dye:4"}, {"tag": "minecraft:planks"}, {"item": "examplemod:steel_ingot:0"}],
        "result": {"item": "othermod:gizmo"},
    }}))
    bad = unresolved_refs(out, [rel], AGENT_MOD)
    assert [(r.kind, r.ident) for r in bad] == [("item", "othermod:gizmo")]
    assert "examplemod:steel_ingot" in pack_known(out).items
