"""The agent eval matrix (#77): pass / fail / unscored, format failures, one row per target."""
import json
from pathlib import Path

from portkit import cli
from portkit.agent import Budget
from portkit.agent.fake import FakeLLM, tool_call
from portkit.agent.loop import AgentSession, Message, ToolCall
from portkit.agent.matrix import MatrixRow, agent_fixtures, render, run_matrix, score
from portkit.agent.residue import GroupOutcome
from portkit.agent.tools import ToolBox

from test_residue_agent import BEDROCK_RECIPE, TAG_RECIPE, _good_script

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
RESIDUE_MOD = FIXTURES / "residue_mod"


def test_scoring_has_three_outcomes_and_ignores_non_tasks():
    assert score(GroupOutcome("k", "recipe", "s", "resolved", "done")) == "pass"
    for status, stopped in [("unresolved", "done"), ("rolled_back", "done"), ("partial", "budget"),
                            ("unresolved", "budget")]:
        assert score(GroupOutcome("k", "recipe", "s", status, stopped)) == "fail"
    # The validator never judged these: provider error, or the run ceiling hit first.
    assert score(GroupOutcome("k", "recipe", "s", "error", "error")) == "unscored"
    assert score(GroupOutcome("k", "recipe", "s", "rolled_back", "error")) == "unscored"
    assert score(GroupOutcome("k", "recipe", "s", "skipped", "budget")) == "unscored"
    # Bytecode and the like are not tasks at all.
    assert score(GroupOutcome("k", "java_code", "s", "skipped")) is None


def test_unscored_stays_out_of_the_pass_rate():
    row = MatrixRow("t")
    row.add("f", GroupOutcome("a", "recipe", "s", "resolved", "done", tool_calls=3))
    row.add("f", GroupOutcome("b", "recipe", "s", "unresolved", "done", tool_calls=1))
    row.add("f", GroupOutcome("c", "recipe", "s", "error", "error"))
    row.add("f", GroupOutcome("d", "java_code", "s", "skipped"))
    assert (row.passed, row.failed, row.unscored) == (1, 1, 1)
    assert row.pass_rate == 0.5
    assert row.calls_per_success == 4.0
    assert row.stops == {"done": 2, "error": 1}


def test_format_failures_are_counted_but_the_call_still_runs(tmp_path):
    box = ToolBox(tmp_path, tmp_path)
    assert box.format_error("read_source", {"path": "x"}) is None
    assert box.format_error("validate", {}) is None
    assert "unknown tool" in box.format_error("read_file", {"path": "x"})
    assert "missing required" in box.format_error("read_source", {})
    assert "unknown argument" in box.format_error("read_source", {"path": "x", "mode": "r"})
    assert "not an object" in box.format_error("read_source", ["x"])

    client = FakeLLM([
        Message("assistant", tool_calls=[
            ToolCall("1", "read_file", {"path": "x"}),
            ToolCall("2", "read_source", {"file": "x"}),
            ToolCall("3", "validate", {}),
        ]),
        Message("assistant", "done"),
    ])
    result = AgentSession(client, box, "sys").run("go")
    assert (result.tool_calls, result.format_failures) == (3, 2)
    tool_replies = [json.loads(m.content) for m in result.messages if m.role == "tool"]
    assert "unknown tool" in tool_replies[0]["error"]  # behaviour unchanged: errors are data
    assert "TypeError" in tool_replies[1]["error"]


def test_matrix_runs_two_targets_on_the_same_budget():
    flaky_calls = []

    class Flaky:
        def complete(self, messages, tools):
            flaky_calls.append(1)
            raise ConnectionError("provider down")

    def sloppy(_name):
        # Calls a tool that doesn't exist, then gives up: a format failure and a fail.
        return FakeLLM([tool_call("read_file", path=TAG_RECIPE), Message("assistant", "cannot"),
                        Message("assistant", "cannot")])

    targets = [
        ("scripted:good", lambda _name: FakeLLM(_good_script())),
        ("scripted:sloppy", sloppy),
        ("scripted:down", lambda _name: Flaky()),
    ]
    rows = run_matrix(targets, [RESIDUE_MOD], Budget(max_steps=6))
    good, bad, down = rows
    assert (good.passed, good.failed, good.unscored, good.format_failures) == (1, 1, 0, 0)
    assert (bad.passed, bad.failed, bad.unscored, bad.format_failures) == (0, 2, 0, 1)
    assert (down.passed, down.failed, down.unscored) == (0, 0, 2)
    assert down.pass_rate is None  # nothing scored, so no rate, not 0%
    table = render(rows)
    assert "scripted:good" in table and "50%" in table and "format fail" in table


def test_agent_fixtures_are_the_ones_with_residue():
    names = [c.name for c in agent_fixtures(FIXTURES)]
    assert "residue_mod" in names and "agent_mod" in names
    assert "simple_block_mod" not in names
    assert [c.name for c in agent_fixtures(FIXTURES, ["simple_block_mod"])] == ["simple_block_mod"]


def test_a_recorded_row_replays_offline(tmp_path, capsys):
    """The CI row: residue_mod's transcript, no key, no network."""
    out = tmp_path / "rows.json"
    code = cli.main(["eval", "--agent", "--agent-replay", str(FIXTURES / "transcripts"), "--json", str(out)])
    assert code == 0
    printed = capsys.readouterr().out
    assert "replay:transcripts" in printed
    [row] = json.loads(out.read_text())
    assert (row["pass"], row["fail"], row["unscored"], row["format_failures"]) == (1, 1, 0, 0)
    assert row["stops"] == {"done": 2}


def test_eval_agent_needs_a_target(capsys):
    assert cli.main(["eval", "--agent"]) == 2
    assert "--target" in capsys.readouterr().err


def test_replay_and_live_targets_do_not_mix(capsys):
    code = cli.main(["eval", "--agent", "--agent-replay", str(FIXTURES / "transcripts"), "--target", "openai:x"])
    assert code == 2


def test_a_target_that_cannot_build_a_client_is_a_setup_error(capsys):
    assert cli.main(["eval", "--agent", "--target", "nosuchprovider:m"]) == 2
    assert "nosuchprovider:m" in capsys.readouterr().err


def test_a_target_can_carry_its_own_base_url():
    from portkit.agent.matrix import parse_target, target_label

    assert parse_target("anthropic:claude-haiku-4.5") == ("anthropic", "claude-haiku-4.5", None)
    spec = "openai:anthropic/claude-haiku-4.5@https://openrouter.ai/api/v1"
    assert parse_target(spec) == ("openai", "anthropic/claude-haiku-4.5", "https://openrouter.ai/api/v1")
    # An @ inside a model name is not a URL.
    assert parse_target("anthropic:claude-x@20250101") == ("anthropic", "claude-x@20250101", None)
    assert parse_target(":m") == (None, "m", None)
    assert target_label(*parse_target(spec)) == "openai:anthropic/claude-haiku-4.5@openrouter.ai"
    assert target_label("gemini_native", "g", None) == "gemini_native:g"


def test_the_base_url_reaches_the_client_and_not_the_environment(monkeypatch, tmp_path, capsys):
    built = []

    def fake_make_client(provider, model, *, config=None, **_):
        built.append((provider, model, config))
        return FakeLLM([Message("assistant", "cannot")] * 20)

    monkeypatch.setattr("portkit.agent.make_client", fake_make_client)
    monkeypatch.setenv("PORTKIT_LLM_BASE_URL", "https://shell.example/v1")
    out = tmp_path / "nested" / "matrix.json"
    code = cli.main(["eval", "--agent", "--agent-fixture", "residue_mod", "--matrix-out", str(out),
                     "--target", "openai:a/b@https://openrouter.ai/api/v1",
                     "--target", "gemini_native:g"])
    assert code == 0
    assert ("openai", "a/b", {"base_url": "https://openrouter.ai/api/v1"}) in built
    assert ("gemini_native", "g", None) in built
    import os
    assert os.environ["PORTKIT_LLM_BASE_URL"] == "https://shell.example/v1"  # untouched
    rows = json.loads(out.read_text())
    assert [r["target"] for r in rows] == ["openai:a/b@openrouter.ai", "gemini_native:g"]
    assert rows[0]["fixtures"] == {"residue_mod": {"pass": 0, "fail": 2, "unscored": 0}}
