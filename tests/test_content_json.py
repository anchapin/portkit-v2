"""write_output takes the file as JSON text, ``content_json`` (#142).

Gemini 3.8 Flash, given ``content: {"type": "object"}`` with no properties,
sent stubs such as ``{"format_version": "1.20.80", "minecraft": "item"}`` in
Alex's live rerun. Gemini's function schemas are an OpenAPI subset with no way
to say "any object", so the file now travels as a string for every provider.
"""
import json
from pathlib import Path

import pytest

from portkit.agent.fake import FakeLLM, tool_call
from portkit.agent.gemini import to_gemini_tool
from portkit.agent.loop import Message
from portkit.agent.openai import to_openai_tool
from portkit.agent.residue import ResidueAgent
from portkit.agent.tools import ToolBox
from portkit.pipeline import convert

from test_agent_stats import AGENT_MOD, SWORD, SWORD_PATH, _script_for_sword, _sword

ITEM = {
    "format_version": "1.21.40",
    "minecraft:item": {
        "description": {"identifier": "t:gem"},
        "components": {"minecraft:icon": "t:gem", "minecraft:max_stack_size": 64},
    },
}
# What Flash's object-valued calls looked like on arrival.
MANGLED = {"format_version": "1.20.80", "minecraft": "item"}


@pytest.fixture
def box(tmp_path):
    (tmp_path / "src").mkdir()
    return ToolBox(tmp_path / "src", tmp_path / "out")


def _written(box, rel):
    return json.loads((box.out_tree / rel).read_text())


def _free_form_objects(schema, where="", top=True):
    """Object schemas below the top level that name no properties."""
    found = []
    if isinstance(schema, dict):
        if schema.get("type") == "object" and not schema.get("properties") and not top:
            found.append(where)
        for key, value in schema.items():
            found += _free_form_objects(value, f"{where}/{key}", top=False) if isinstance(value, (dict, list)) else []
    elif isinstance(schema, list):
        for i, value in enumerate(schema):
            found += _free_form_objects(value, f"{where}/{i}", top=False)
    return found


def test_no_tool_schema_has_a_free_form_object(box):
    for schema in box.schemas():
        params = schema.get("parameters") or {}
        assert _free_form_objects(params) == [], schema["name"]
        assert "additionalProperties" not in json.dumps(params)


def test_write_output_advertises_a_string(box):
    schema = next(s for s in box.schemas() if s["name"] == "write_output")
    params = schema["parameters"]
    assert params["properties"]["content_json"]["type"] == "string"
    assert params["required"] == ["path", "content_json"]
    assert "content" not in params["properties"]
    # Both wire formats carry it unchanged: OpenAI-style (OpenRouter, Gemini's
    # compat endpoint) and native Gemini functionDeclarations.
    assert to_openai_tool(schema)["function"]["parameters"] == params
    assert to_gemini_tool(schema)["parameters"] == params


def test_namespaced_keys_survive_as_text(box):
    result = box.invoke("write_output", {"path": "behavior_pack/items/gem.json", "content_json": json.dumps(ITEM)})
    assert result["written"] == "behavior_pack/items/gem.json" and "note" not in result
    assert _written(box, "behavior_pack/items/gem.json") == ITEM
    assert box.format_error("write_output", {"path": "p", "content_json": "{}"}) is None


def test_a_parse_error_names_line_and_column(box):
    text = '{\n  "format_version": "1.21.40",\n  "minecraft:item": {"description": }\n}'
    result = box.invoke("write_output", {"path": "behavior_pack/items/gem.json", "content_json": text})
    assert result["line"] == 3 and result["column"] == 37
    assert "line 3 column 37" in result["error"]
    assert '"description": }' in result["near"]
    assert not (box.out_tree / "behavior_pack/items/gem.json").exists()
    assert not box.wrote_anything


@pytest.mark.parametrize("text", ['"just text"', "[1, 2]", "null", "3"])
def test_json_text_that_is_not_an_object_is_refused(box, text):
    result = box.invoke("write_output", {"path": "behavior_pack/items/gem.json", "content_json": text})
    assert "must hold a JSON object" in result["error"]
    assert not box.wrote_anything


def test_content_json_must_be_text(box):
    result = box.invoke("write_output", {"path": "behavior_pack/items/gem.json", "content_json": 7})
    assert "must be JSON text" in result["error"]


def test_an_object_in_content_json_is_taken_as_is(box):
    box.invoke("write_output", {"path": "behavior_pack/items/gem.json", "content_json": ITEM})
    assert _written(box, "behavior_pack/items/gem.json") == ITEM


def test_exactly_one_of_the_two_forms(box):
    neither = box.invoke("write_output", {"path": "behavior_pack/items/gem.json"})
    both = box.invoke("write_output", {"path": "behavior_pack/items/gem.json",
                                       "content_json": json.dumps(ITEM), "content": ITEM})
    assert "content_json" in neither["error"] and "not both" in both["error"]
    assert not box.wrote_anything
    assert box.format_error("write_output", {"path": "p"}) == "write_output: missing required argument(s) content_json"


def test_the_object_form_still_works_and_is_not_a_format_failure(box):
    # Recorded transcripts and models that ignore the schema still send it.
    assert box.format_error("write_output", {"path": "p", "content": ITEM}) is None
    result = box.invoke("write_output", {"path": "behavior_pack/items/gem.json", "content": ITEM})
    assert result["written"] and _written(box, "behavior_pack/items/gem.json") == ITEM
    assert box.format_error("write_output", {"path": "p", "content_json": "{}", "contents": ITEM}) == "write_output: unknown argument(s) contents"


def test_the_colon_mangle_is_named_on_write_and_on_validate(box):
    """The shape Flash's calls arrived in: ``minecraft:item`` cut at the colon."""
    result = box.invoke("write_output", {"path": "behavior_pack/items/gem.json", "content": MANGLED})
    assert "bare 'minecraft' key" in result["note"] and "content_json" in result["note"]
    report = box.invoke("validate", {})
    shape = [f for f in report["findings"] if f["rule"] == "doc.unknown_shape"]
    assert report["ok"] is False and len(shape) == 1
    assert "cut at the colon" in shape[0]["message"]


def test_a_flash_run_that_switches_to_text_resolves(tmp_path):
    """Mangled object first, then the same item as JSON text: rolled forward, resolved."""
    steps = [
        tool_call("write_output", path=SWORD_PATH, content=MANGLED),
        tool_call("validate"),
        tool_call("write_output", path=SWORD_PATH, content_json=json.dumps(_sword())),
        tool_call("validate"),
        Message("assistant", "Wrote the sword; the source gives no damage or durability, so I left them out."),
    ]
    result = convert(AGENT_MOD, tmp_path / "out", agent=ResidueAgent(FakeLLM(_script_for_sword(tmp_path, steps))))
    sword = {o.key: o for o in result.agent.outcomes}[SWORD]
    assert sword.status == "resolved"
    assert json.loads((tmp_path / "out" / SWORD_PATH).read_text()) == _sword()
