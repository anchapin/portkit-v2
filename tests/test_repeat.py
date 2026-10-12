"""--repeat N (#86): one model, one fixture, N samples, and the spread between them."""
import json
from pathlib import Path

from portkit import cli
from portkit.agent import make_client
from portkit.agent.budget import Budget, Pricing, Usage
from portkit.agent.fake import FakeLLM, tool_call
from portkit.agent.loop import Message
from portkit.agent.residue import ResidueAgent

ROOT = Path(__file__).resolve().parents[1]
RESIDUE = ROOT / "fixtures" / "residue_mod" / "input"
TRANSCRIPT = ROOT / "fixtures" / "transcripts" / "residue_mod.jsonl"
TAG = "recipe:data/examplemod/recipes/steel_block.json"

RECIPE = {
    "format_version": "1.20.10",
    "minecraft:recipe_shapeless": {
        "description": {"identifier": "examplemod:steel_block"},
        "tags": ["crafting_table"],
        "ingredients": [{"item": "examplemod:steel_ingot"}],
        "result": {"item": "examplemod:steel_block"},
    },
}


def _writes():
    return [
        tool_call("write_output", path="behavior_pack/recipes/steel_block.json", content=RECIPE),
        Message("assistant", "done"),
        Message("assistant", "trim declined"),
    ]


def _refuses():
    return [Message("assistant", "declined"), Message("assistant", "declined")]


def test_repeat_replay_is_identical_every_run(tmp_path, capsys):
    rec = tmp_path / "rec.jsonl"
    code = cli.main([
        "convert", str(RESIDUE), str(tmp_path / "out"),
        "--agent-replay", str(TRANSCRIPT), "--agent-record", str(rec), "--repeat", "3",
    ])
    assert code == 0
    for run in (1, 2, 3):
        assert (tmp_path / "out" / f"run-{run}").is_dir()
        assert (tmp_path / f"rec-{run}.jsonl").read_text() == TRANSCRIPT.read_text()
    summary = json.loads((tmp_path / "out" / "repeat-summary.json").read_text())
    assert summary["runs"] == 3
    assert summary["resolved"]["stdev"] == 0.0
    assert summary["group_resolved_in"][TAG] == 3
    assert "across 3 run(s)" in capsys.readouterr().out


def test_repeat_reports_the_spread_between_runs(tmp_path, monkeypatch, capsys):
    scripts = iter([_writes(), _refuses(), _writes()])
    monkeypatch.setattr(cli, "_residue_agent", lambda args: ResidueAgent(FakeLLM(next(scripts))))
    cli.main(["convert", str(RESIDUE), str(tmp_path / "out"), "--agent", "--repeat", "3"])
    summary = json.loads((tmp_path / "out" / "repeat-summary.json").read_text())
    assert [r["resolved"] for r in summary["per_run"]] == [1, 0, 1]
    assert summary["resolved"]["min"] == 0 and summary["resolved"]["max"] == 1
    assert summary["resolved"]["stdev"] > 0
    assert summary["group_resolved_in"][TAG] == 2
    assert f"{TAG}: resolved in 2 of 3" in capsys.readouterr().out


def test_repeat_needs_the_agent(tmp_path, capsys):
    assert cli.main(["convert", str(RESIDUE), str(tmp_path / "o"), "--repeat", "2"]) == 2
    assert "--repeat only makes sense with --agent" in capsys.readouterr().err


def test_repeat_must_be_positive(tmp_path, capsys):
    assert cli.main(["convert", str(RESIDUE), str(tmp_path / "o"), "--agent", "--repeat", "0"]) == 2


def test_repeat_one_keeps_the_old_layout(tmp_path):
    code = cli.main(["convert", str(RESIDUE), str(tmp_path / "out"), "--agent-replay", str(TRANSCRIPT)])
    assert code == 0
    assert not (tmp_path / "out" / "run-1").exists()
    assert not (tmp_path / "out" / "repeat-summary.json").exists()


def test_numbered_record_paths():
    assert cli._numbered("/t/rec.jsonl", 2) == "/t/rec-2.jsonl"
    assert cli._numbered("/t/rec", 3) == "/t/rec-3.jsonl"


def test_factory_reads_temperature():
    env = {"PORTKIT_LLM_PROVIDER": "openai", "PORTKIT_LLM_MODEL": "m", "PORTKIT_LLM_TEMPERATURE": "0.7"}
    assert make_client(env=env).extra == {"temperature": 0.7}
    env.pop("PORTKIT_LLM_TEMPERATURE")
    assert make_client(env=env).extra == {}


def test_factory_rejects_a_bad_temperature():
    import pytest

    env = {"PORTKIT_LLM_PROVIDER": "openai", "PORTKIT_LLM_MODEL": "m", "PORTKIT_LLM_TEMPERATURE": "hot"}
    with pytest.raises(ValueError, match="TEMPERATURE"):
        make_client(env=env)


def test_repeat_summary_counts_declines_and_agent_status(tmp_path, monkeypatch, capsys):
    scripts = iter([_writes(), _refuses(), _writes()])
    monkeypatch.setattr(cli, "_residue_agent", lambda args: ResidueAgent(FakeLLM(next(scripts))))
    cli.main(["convert", str(RESIDUE), str(tmp_path / "out"), "--agent", "--repeat", "3"])
    summary = json.loads((tmp_path / "out" / "repeat-summary.json").read_text())
    assert [r["agent_status"] for r in summary["per_run"]] == ["partial", "failed", "partial"]
    assert [r["declined"] for r in summary["per_run"]] == [1, 2, 1]
    assert all(r["valid"] for r in summary["per_run"]) and "ok" not in summary["per_run"][0]
    assert summary["agent_status"] == {"failed": 1, "partial": 2}
    smithing = "recipe:data/examplemod/recipes/steel_trim.json"
    assert summary["group_declined_in"][smithing] == 3
    out = capsys.readouterr().out
    assert "agent runs: failed 1, partial 2" in out
    assert f"{smithing}: resolved in 0 of 3, declined in 3" in out


def test_every_group_out_of_steps_is_a_failed_run_on_a_valid_pack(tmp_path, monkeypatch, capsys):
    # The #86 Gemini Flash shape: every session loops until the step ceiling.
    monkeypatch.setattr(cli, "_residue_agent", lambda args: ResidueAgent(
        FakeLLM([tool_call("validate") for _ in range(10)]), max_steps=2))
    cli.main(["convert", str(RESIDUE), str(tmp_path / "out"), "--agent", "--repeat", "2"])
    summary = json.loads((tmp_path / "out" / "repeat-summary.json").read_text())
    assert summary["agent_status"] == {"failed": 2}
    assert all(r["valid"] and r["resolved"] == 0 for r in summary["per_run"])


# -- --agent-max-total-cost (#143) ---------------------------------------------

# $0.05 a completion: one million input tokens at $0.05 per million.
_PRICE = Pricing(0.05, 0.0)
_STEP = Usage(1_000_000, 0)


def _priced(monkeypatch, scripts, caps):
    def agent(args):
        caps.append(args.agent_max_cost)
        budget = Budget(max_cost=args.agent_max_cost, pricing=_PRICE)
        return ResidueAgent(FakeLLM(next(scripts), usage=_STEP), budget=budget)
    monkeypatch.setattr(cli, "_residue_agent", agent)


def test_the_total_cap_tightens_the_last_run_and_skips_the_rest(tmp_path, monkeypatch, capsys):
    caps: list = []
    _priced(monkeypatch, iter([_writes(), _writes(), _writes()]), caps)
    cli.main(["convert", str(RESIDUE), str(tmp_path / "out"), "--agent", "--repeat", "3",
              "--agent-max-total-cost", "0.25"])
    summary = json.loads((tmp_path / "out" / "repeat-summary.json").read_text())
    # Run 1 spends three completions ($0.15); run 2 may spend only the $0.10
    # left, so it stops after two; run 3 never starts.
    assert caps == [0.25, 0.1]
    assert [r["cost_usd"] for r in summary["per_run"]] == [0.15, 0.1]
    assert summary["runs"] == 2 and summary["runs_requested"] == 3
    assert summary["total_cost_usd"] == 0.25 and summary["max_total_cost_usd"] == 0.25
    assert [s["run"] for s in summary["skipped_runs"]] == [3]
    assert summary["skipped_runs"][0]["status"] == "skipped"
    assert not (tmp_path / "out" / "run-3").exists()
    out = capsys.readouterr().out
    assert "skipping run(s) 3..3" in out and "skipped: 1 of 3 run(s)" in out


def test_the_per_run_cap_still_applies_under_the_total(tmp_path, monkeypatch):
    caps: list = []
    _priced(monkeypatch, iter([_refuses(), _refuses(), _refuses()]), caps)
    cli.main(["convert", str(RESIDUE), str(tmp_path / "out"), "--agent", "--repeat", "3",
              "--agent-max-cost", "0.05", "--agent-max-total-cost", "1"])
    summary = json.loads((tmp_path / "out" / "repeat-summary.json").read_text())
    assert caps == [0.05, 0.05, 0.05]
    assert summary["skipped_runs"] == [] and summary["runs"] == 3


def test_without_a_total_cap_the_summary_is_unchanged(tmp_path, monkeypatch):
    scripts = iter([_refuses(), _refuses()])
    monkeypatch.setattr(cli, "_residue_agent", lambda args: ResidueAgent(FakeLLM(next(scripts))))
    cli.main(["convert", str(RESIDUE), str(tmp_path / "out"), "--agent", "--repeat", "2"])
    summary = json.loads((tmp_path / "out" / "repeat-summary.json").read_text())
    assert "skipped_runs" not in summary and "max_total_cost_usd" not in summary


def test_the_total_cap_must_be_positive_and_needs_prices(tmp_path, monkeypatch, capsys):
    assert cli.main(["convert", str(RESIDUE), str(tmp_path / "o"), "--agent", "--repeat", "2",
                     "--agent-max-total-cost", "0"]) == 2
    assert "must be more than 0" in capsys.readouterr().err
    monkeypatch.delenv("PORTKIT_LLM_INPUT_PRICE", raising=False)
    monkeypatch.delenv("PORTKIT_LLM_OUTPUT_PRICE", raising=False)
    code = cli.main(["convert", str(RESIDUE), str(tmp_path / "o2"), "--agent-replay", str(TRANSCRIPT),
                     "--repeat", "2", "--agent-max-total-cost", "1"])
    assert code == 2 and "needs prices" in capsys.readouterr().err


def test_without_repeat_the_total_cap_is_the_run_cap(tmp_path, monkeypatch):
    caps: list = []
    _priced(monkeypatch, iter([_refuses()]), caps)
    cli.main(["convert", str(RESIDUE), str(tmp_path / "out"), "--agent",
              "--agent-max-cost", "0.5", "--agent-max-total-cost", "0.2"])
    assert caps == [0.2]
