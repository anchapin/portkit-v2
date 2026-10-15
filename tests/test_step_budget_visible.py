"""The step budget is visible to the model, and it is nudged before it runs out (#139).

In Alex's Gemini 3.8 Flash spot-check steel_sword hit the 12-step ceiling in
3/3 runs, every step spent on list/read/lookup research, never writing; and
alloy_block wrote at step 7, then rewrote the same file five times in a row
without validating.
"""
import json
from pathlib import Path

from portkit.agent.fake import FakeLLM, tool_call
from portkit.agent.loop import NUDGE, AgentSession, Message
from portkit.agent.residue import ResidueAgent, group_residue
from portkit.agent.tools import ToolBox
from portkit.pipeline import convert

ROOT = Path(__file__).resolve().parents[1]
AGENT_MOD = ROOT / "fixtures" / "agent_mod" / "input"
RECIPE = "behavior_pack/recipes/alloy_block.json"


def _results(session):
    return [json.loads(m.content) for m in session.messages if m.role == "tool"]


def _box(tmp_path):
    out = tmp_path / "out"
    (out / "behavior_pack").mkdir(parents=True)
    return ToolBox(AGENT_MOD, out)


def test_every_tool_result_says_how_many_steps_are_left(tmp_path):
    script = [tool_call("list_source"), tool_call("read_source", path="assets/examplemod/lang/en_us.json"),
              Message("assistant", "No Bedrock form.")]
    session = AgentSession(FakeLLM(script), _box(tmp_path), "s", max_steps=12)
    session.run("go")
    assert [r["steps_left"] for r in _results(session)] == ["steps left: 11 of 12", "steps left: 10 of 12"]
    assert all("nudge" not in r for r in _results(session))


def test_research_to_the_ceiling_is_nudged_in_the_last_three_steps(tmp_path):
    script = [tool_call("lookup_bedrock", topic=f"topic{i}") for i in range(12)]
    session = AgentSession(FakeLLM(script), _box(tmp_path), "s", max_steps=12)
    result = session.run("go")
    assert result.stopped == "budget"
    results = _results(session)
    nudged = [r["steps_left"] for r in results if r.get("nudge") == NUDGE]
    # Not on the last result: there is no next call to act on it.
    assert nudged == ["steps left: 3 of 12", "steps left: 2 of 12", "steps left: 1 of 12"]
    assert "nudge" not in results[7]


def test_no_nudge_once_something_is_written(tmp_path):
    script = [tool_call("lookup_bedrock", topic="x") for _ in range(8)]
    script += [tool_call("set_lang_entries", path="resource_pack/texts/en_US.lang", lines=["a.b=c"])]
    script += [tool_call("lookup_bedrock", topic="x") for _ in range(3)]
    session = AgentSession(FakeLLM(script), _box(tmp_path), "s", max_steps=12)
    session.run("go")
    results = _results(session)
    assert results[8]["written"] and "nudge" not in results[8]  # step 9: 3 left, but it wrote
    assert all("nudge" not in r for r in results[8:])


def test_a_failed_write_does_not_count_as_written(tmp_path):
    script = [tool_call("write_output", path=RECIPE, content="not an object") for _ in range(10)]
    session = AgentSession(FakeLLM(script), _box(tmp_path), "s", max_steps=10)
    session.run("go")
    assert _results(session)[-2]["nudge"] == NUDGE


def test_overwriting_without_validating_is_pointed_out(tmp_path):
    body = {"format_version": "1.20.10", "minecraft:recipe_shaped": {}}
    script = [
        tool_call("write_output", path=RECIPE, content=body),
        tool_call("write_output", path=RECIPE, content=body),
        tool_call("validate"),
        tool_call("write_output", path=RECIPE, content=body),
        tool_call("write_output", path="behavior_pack/recipes/other.json", content=body),
        Message("assistant", "done"),
    ]
    session = AgentSession(FakeLLM(script), _box(tmp_path), "s", max_steps=12)
    session.run("go")
    notes = [r.get("note") for r in _results(session)]
    overwrote = "overwrote your previous version without validating it; run validate"
    # first write: none; second: overwrote; validate; third (after validate): none; other path: none
    assert notes == [None, overwrote, None, None, None]


def test_tool_errors_and_non_dict_results_are_stamped_too(tmp_path):
    class Odd(ToolBox):
        def invoke(self, name, arguments):
            if name == "boom":
                raise RuntimeError("bad")
            return ["a", "b"]

    script = [tool_call("boom"), tool_call("anything"), Message("assistant", "ok")]
    session = AgentSession(FakeLLM(script), Odd(AGENT_MOD, tmp_path), "s", max_steps=10)
    session.run("go")
    first, second = _results(session)
    assert first["error"] == "RuntimeError: bad" and first["steps_left"] == "steps left: 9 of 10"
    assert second == {"result": ["a", "b"], "steps_left": "steps left: 8 of 10"}


def test_the_stamp_is_deterministic_across_runs(tmp_path):
    def run(sub):
        probe = convert(AGENT_MOD, tmp_path / sub / "probe")
        script = []
        for group in group_residue(probe.unhandled):
            script += [tool_call("list_source"), Message("assistant", "No Bedrock form.")]
        client = FakeLLM(script)
        convert(AGENT_MOD, tmp_path / sub / "out", agent=ResidueAgent(client))
        return [[m.content for m in seen] for seen in client.seen]

    assert run("a") == run("b")
