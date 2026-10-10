"""--repeat N (#86): one model, one fixture, N samples, and the spread between them."""
import json
from pathlib import Path

from portkit import cli
from portkit.agent import make_client
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
        Message("assistant", "smithing declined"),
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
