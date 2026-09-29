"""The loop is testable with no API key. That is the point of FakeLLM."""
from pathlib import Path

from portkit.agent.fake import FakeLLM, tool_call
from portkit.agent.loop import AgentSession, Message
from portkit.agent.tools import SYSTEM_PROMPT, ToolBox

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "fixtures" / "residue_mod" / "input"


def _manifest(uid_suffix):
    return {
        "format_version": 2,
        "header": {
            "name": "t",
            "uuid": f"1111111{uid_suffix}-1111-1111-1111-111111111111",
            "version": [1, 0, 0],
            "min_engine_version": [1, 20, 10],
        },
        "modules": [
            {"type": "data", "uuid": f"2222222{uid_suffix}-2222-2222-2222-222222222222", "version": [1, 0, 0]}
        ],
    }


def test_loop_stops_when_the_validator_says_ok(tmp_path):
    box = ToolBox(SOURCE, tmp_path)
    client = FakeLLM(
        [
            tool_call("list_source"),
            tool_call("read_source", path="data/examplemod/recipes/steel_block.json"),
            tool_call("write_output", path="behavior_pack/manifest.json", content=_manifest("1")),
            tool_call("validate"),
            Message("assistant", "Converted the shapeless recipe; validator is clean."),
        ]
    )
    session = AgentSession(client, box, SYSTEM_PROMPT, max_steps=10)
    result = session.run("Convert the residue.")

    assert result.stopped == "done"
    assert (tmp_path / "behavior_pack" / "manifest.json").is_file()
    tool_outputs = [m.content for m in result.messages if m.role == "tool"]
    assert any('"ok": true' in out for out in tool_outputs)


def test_tool_errors_come_back_as_data_not_crashes(tmp_path):
    box = ToolBox(SOURCE, tmp_path)
    client = FakeLLM(
        [
            tool_call("read_source", path="../../etc/passwd"),
            Message("assistant", "That path is outside the mod."),
        ]
    )
    result = AgentSession(client, box, SYSTEM_PROMPT).run("go")
    assert result.stopped == "done"
    assert "escapes the sandbox" in result.messages[-2].content


def test_budget_is_enforced(tmp_path):
    box = ToolBox(SOURCE, tmp_path)
    client = FakeLLM([tool_call("validate") for _ in range(20)])
    result = AgentSession(client, box, SYSTEM_PROMPT, max_steps=3).run("go")
    assert result.stopped == "budget"
    assert result.steps == 3
