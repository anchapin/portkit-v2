"""Step, token and cost budgets with accounting (#19).

hard_residue_mod is three tag recipes the deterministic path refuses. A scripted
client that never quite finishes drives the run into each ceiling; the run has
to stop cleanly, keep what still validates, and say what every group spent.
"""
from pathlib import Path

import pytest

from portkit import cli
from portkit.agent import Budget, Pricing, Spend, Usage
from portkit.agent.anthropic import from_anthropic_reply
from portkit.agent.fake import FakeLLM, tool_call
from portkit.agent.loop import AgentSession, Message
from portkit.agent.openai import from_openai_reply
from portkit.agent.residue import ResidueAgent
from portkit.agent.tools import SYSTEM_PROMPT, ToolBox
from portkit.pipeline import convert

ROOT = Path(__file__).resolve().parents[1]
HARD = ROOT / "fixtures" / "hard_residue_mod" / "input"
BRONZE = "recipe:data/examplemod/recipes/bronze_block.json"
STEEL = "recipe:data/examplemod/recipes/steel_block.json"
TIN = "recipe:data/examplemod/recipes/tin_block.json"
PER_CALL = Usage(input_tokens=1000, output_tokens=200)  # 1,200 tokens a completion


def _recipe(name):
    return {
        "format_version": "1.20.10",
        "minecraft:recipe_shapeless": {
            "description": {"identifier": f"examplemod:{name}_block"},
            "tags": ["crafting_table"],
            "ingredients": [{"item": f"examplemod:{name}_ingot", "count": 9}],
            "result": {"item": f"examplemod:{name}_block"},
        },
    }


def _write(name):
    return tool_call("write_output", path=f"behavior_pack/recipes/{name}_block.json", content=_recipe(name))


def test_token_ceiling_stops_the_run_and_keeps_partial_output(tmp_path):
    client = FakeLLM(
        [
            _write("bronze"),  # 1,200
            Message("assistant", "Bronze done."),  # 2,400: resolved
            _write("steel"),  # 3,600
            tool_call("validate"),  # 4,800: past the ceiling, steel stops here
            Message("assistant", "never reached"),
        ],
        usage=PER_CALL,
    )
    out = tmp_path / "out"
    result = convert(HARD, out, agent=ResidueAgent(client, budget=Budget(max_tokens=4000)))
    run = result.agent

    by_key = {o.key: o for o in run.outcomes}
    assert by_key[BRONZE].status == "resolved"
    assert by_key[STEEL].status == "partial" and by_key[STEEL].limit == "tokens"
    assert by_key[TIN].status == "skipped" and by_key[TIN].limit == "tokens"
    assert len(client.seen) == 4  # nothing called after the ceiling

    # Partial output kept, tree still valid and installable.
    assert (out / "behavior_pack/recipes/bronze_block.json").is_file()
    assert (out / "behavior_pack/recipes/steel_block.json").is_file()
    assert result.report.ok and result.addon is not None
    assert sorted(u.source for u in result.unhandled) == [
        "data/examplemod/recipes/steel_block.json",
        "data/examplemod/recipes/tin_block.json",
    ]

    # Spend reported per group and for the run.
    assert by_key[BRONZE].spend.to_dict() == {
        "steps": 2, "input_tokens": 2000, "output_tokens": 400, "cost_usd": None,
    }
    assert by_key[STEEL].spend.tokens == 2400 and by_key[TIN].spend.steps == 0
    assert run.spend.tokens == 4800 and run.limit == "tokens"
    summary = result.summary()["agent"]
    assert summary["stopped_by"] == "tokens"
    assert summary["files_written"] == 1 and summary["partial_files"] == 1
    assert [o["spend"]["steps"] for o in summary["outcomes"]] == [2, 2, 0]


def test_cost_ceiling_uses_configured_prices(tmp_path):
    pricing = Pricing(input_per_mtok=3.0, output_per_mtok=15.0)  # $0.006 a completion
    client = FakeLLM([tool_call("validate") for _ in range(10)], usage=PER_CALL)
    budget = Budget(max_cost=0.01, pricing=pricing)
    result = convert(HARD, tmp_path / "out", agent=ResidueAgent(client, budget=budget))
    run = result.agent

    first = run.outcomes[0]
    assert first.stopped == "budget" and first.limit == "cost" and first.status == "unresolved"
    assert first.spend.steps == 2
    assert run.spend.cost == pytest.approx(0.012)
    assert run.summary()["spend"]["cost_usd"] == 0.012
    assert [o.status for o in run.outcomes[1:]] == ["skipped", "skipped"]
    assert result.report.ok and len(result.unhandled) == 3


def test_step_ceiling_is_per_group_and_named(tmp_path):
    # No usage reported at all: only the step ceiling can stop it, per group.
    client = FakeLLM([tool_call("validate") for _ in range(10)])
    result = convert(HARD, tmp_path / "out", agent=ResidueAgent(client, budget=Budget(max_steps=2)))
    assert [(o.stopped, o.limit, o.steps) for o in result.agent.outcomes] == [("budget", "steps", 2)] * 3
    assert result.agent.limit is None  # no run ceiling was involved
    assert result.agent.spend.unreported == 6  # and the missing usage is said out loud


def test_finishing_exactly_at_the_ceiling_is_not_a_cut(tmp_path):
    script = [_write("bronze"), Message("assistant", "done")]
    script += [Message("assistant", "No faithful equivalent.")] * 2
    client = FakeLLM(script, usage=Usage(500, 100))  # 600 a call
    run = convert(HARD, tmp_path / "out", agent=ResidueAgent(client, budget=Budget(max_tokens=2400))).agent
    assert run.spend.tokens == 2400 and run.limit is None
    assert [o.status for o in run.outcomes] == ["resolved", "unresolved", "unresolved"]


def test_session_budget_overrides_max_steps(tmp_path):
    client = FakeLLM([tool_call("validate") for _ in range(10)])
    session = AgentSession(client, ToolBox(HARD, tmp_path), SYSTEM_PROMPT, max_steps=9, budget=Budget(max_steps=1))
    assert session.run("go").steps == 1


def test_dollar_ceiling_without_prices_is_refused():
    with pytest.raises(ValueError, match="PORTKIT_LLM_INPUT_PRICE"):
        Budget(max_cost=1.0)
    with pytest.raises(ValueError):
        Budget(max_steps=0)


def test_pricing_from_env():
    assert Pricing.from_env({}) is None
    p = Pricing.from_env({"PORTKIT_LLM_INPUT_PRICE": "3", "PORTKIT_LLM_OUTPUT_PRICE": "15"})
    assert p.cost(Usage(1_000_000, 100_000)) == pytest.approx(4.5)
    with pytest.raises(ValueError):
        Pricing.from_env({"PORTKIT_LLM_INPUT_PRICE": "three"})


def test_spend_adds_up():
    total = Spend()
    a = Spend()
    a.record(Usage(10, 5), Pricing(1, 1))
    b = Spend()
    b.record(None, None)
    total.add(a)
    total.add(b)
    assert (total.steps, total.tokens, total.unreported) == (2, 15, 1)
    assert total.cost == pytest.approx(15 / 1_000_000)


def test_clients_read_usage_from_replies():
    oa = from_openai_reply(
        {"choices": [{"message": {"content": "hi"}}], "usage": {"prompt_tokens": 12, "completion_tokens": 3}}
    )
    assert oa.usage == Usage(12, 3)
    assert from_openai_reply({"choices": [{"message": {"content": "hi"}}]}).usage is None

    an = from_anthropic_reply(
        {
            "content": [{"type": "text", "text": "hi"}],
            "usage": {
                "input_tokens": 10,
                "cache_read_input_tokens": 90,
                "cache_creation_input_tokens": 5,
                "output_tokens": 4,
            },
        }
    )
    assert an.usage == Usage(105, 4)


def test_cli_reports_spend_and_the_ceiling(tmp_path, monkeypatch, capsys):
    client = FakeLLM([tool_call("validate") for _ in range(10)], usage=PER_CALL)
    monkeypatch.setattr(
        cli, "_residue_agent", lambda args: ResidueAgent(client, budget=Budget(max_tokens=2000))
    )
    code = cli.main(["convert", str(HARD), str(tmp_path / "out"), "--agent", "--agent-max-tokens", "2000"])
    out = capsys.readouterr().out
    assert code == 0
    assert f"unresolved: {BRONZE} [2 step(s), 2,400 tokens]" in out
    assert "spent: 2 step(s), 2,400 tokens" in out
    assert "stopped at the run's tokens ceiling" in out


def test_cli_cost_ceiling_without_prices_exits_cleanly(tmp_path, monkeypatch, capsys):
    for var in ("PORTKIT_LLM_INPUT_PRICE", "PORTKIT_LLM_OUTPUT_PRICE"):
        monkeypatch.delenv(var, raising=False)
    code = cli.main(["convert", str(HARD), str(tmp_path / "out"), "--agent", "--agent-max-cost", "0.5"])
    assert code == 2
    assert "PORTKIT_LLM_INPUT_PRICE" in capsys.readouterr().err
