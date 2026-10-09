"""Record and replay agent transcripts (#20). No key, no network, deterministic."""
import json
from pathlib import Path

import pytest

from portkit import cli
from portkit.agent import Budget, RecordingClient, ReplayClient, ReplayMismatch, ResidueAgent, Usage
from portkit.agent.fake import FakeLLM, tool_call
from portkit.agent.loop import Message
from portkit.agent.transcript import load, message_from_dict, message_to_dict
from portkit.pipeline import convert

ROOT = Path(__file__).resolve().parents[1]
RESIDUE = ROOT / "fixtures" / "residue_mod" / "input"
TRANSCRIPT = ROOT / "fixtures" / "transcripts" / "residue_mod.jsonl"
TAG = "recipe:data/examplemod/recipes/steel_block.json"
SMITHING = "recipe:data/examplemod/recipes/steel_smithing.json"


def _replay(tmp_path, client):
    return convert(RESIDUE, tmp_path / "out", agent=ResidueAgent(client))


def test_committed_transcript_replays_deterministically(tmp_path):
    client = ReplayClient(TRANSCRIPT)
    result = _replay(tmp_path, client)
    assert client.remaining == 0
    assert {o.key: o.status for o in result.agent.outcomes} == {TAG: "resolved", SMITHING: "unresolved"}
    assert result.report.ok and result.addon is not None
    assert (tmp_path / "out" / "behavior_pack" / "recipes" / "steel_block.json").is_file()
    # Usage is part of the recording, so the spend report replays too.
    assert result.agent.spend.tokens == 9600 and result.agent.spend.steps == 5

    again = _replay(tmp_path / "second", ReplayClient(TRANSCRIPT))
    assert again.agent.summary() == result.agent.summary()
    first = (tmp_path / "out" / "behavior_pack" / "recipes" / "steel_block.json").read_bytes()
    second = (tmp_path / "second" / "out" / "behavior_pack" / "recipes" / "steel_block.json").read_bytes()
    assert first == second


def test_a_changed_prompt_fails_the_replay_at_the_step_that_differs(tmp_path):
    with pytest.raises(ReplayMismatch, match="session 0 step 1 diverged"):
        ReplayClient(TRANSCRIPT).complete(
            [Message("system", "A different system prompt."), Message("user", "go")], []
        )
    # Inside a run, the mismatch ends the group as an error rather than passing quietly.
    agent = ResidueAgent(ReplayClient(TRANSCRIPT), system="A different system prompt.")
    result = convert(RESIDUE, tmp_path / "out", agent=agent)
    assert [o.status for o in result.agent.outcomes][0] == "error"
    assert "diverged from the recording" in result.agent.outcomes[0].note


def test_running_past_the_tape_is_a_mismatch(tmp_path):
    path = tmp_path / "t.jsonl"
    lines = TRANSCRIPT.read_text().splitlines()
    path.write_text(lines[0] + "\n")
    client = ReplayClient(path, strict=False)
    client.complete([], [])
    with pytest.raises(ReplayMismatch, match="only 1 were recorded"):
        client.complete([], [])


def test_recording_then_replaying_round_trips(tmp_path):
    script = [
        tool_call("validate"),
        Message("assistant", "Nothing to convert faithfully."),
        Message("assistant", "Same for the smithing recipe."),
    ]
    path = tmp_path / "run.jsonl"
    recorder = RecordingClient(FakeLLM(script, usage=Usage(10, 2)), path)
    recorded = _replay(tmp_path / "rec", recorder)

    entries = load(path)
    assert [(e["session"], e["step"]) for e in entries] == [(0, 1), (0, 2), (1, 1)]
    assert entries[0]["reply"]["tool_calls"][0]["name"] == "validate"

    replayed = _replay(tmp_path / "rep", ReplayClient(path))
    assert replayed.agent.summary() == recorded.agent.summary()


def test_recording_keeps_every_line_written_before_a_failure(tmp_path):
    class DiesOnSecondCall:
        calls = 0

        def complete(self, messages, tools):
            DiesOnSecondCall.calls += 1
            if DiesOnSecondCall.calls == 2:
                raise RuntimeError("connection reset")
            return tool_call("validate")

    path = tmp_path / "run.jsonl"
    _replay(tmp_path, RecordingClient(DiesOnSecondCall(), path))
    assert len(load(path)) >= 1


def test_message_round_trip():
    m = tool_call("write_output", path="a.json", content={"x": 1})
    m.usage = Usage(3, 4)
    assert message_from_dict(json.loads(json.dumps(message_to_dict(m)))) == m


def test_load_rejects_bad_transcripts(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text("not json\n")
    with pytest.raises(ValueError, match="line 1 is not JSON"):
        load(bad)
    bad.write_text(json.dumps({"v": 99, "request": "x", "reply": {}}) + "\n")
    with pytest.raises(ValueError, match="version"):
        load(bad)


def test_budgets_apply_to_a_replay(tmp_path):
    agent = ResidueAgent(ReplayClient(TRANSCRIPT), budget=Budget(max_tokens=3000))
    run = convert(RESIDUE, tmp_path / "out", agent=agent).agent
    assert run.limit == "tokens" and run.outcomes[0].status == "partial"


def test_cli_replay_needs_no_provider(tmp_path, monkeypatch, capsys):
    for var in ("PORTKIT_LLM_PROVIDER", "PORTKIT_LLM_MODEL", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    code = cli.main(["convert", str(RESIDUE), str(tmp_path / "out"), "--agent-replay", str(TRANSCRIPT)])
    out = capsys.readouterr().out
    assert code == 0
    assert f"resolved: {TAG}" in out


def test_cli_record_writes_a_transcript(tmp_path):
    path = tmp_path / "rec.jsonl"
    code = cli.main([
        "convert", str(RESIDUE), str(tmp_path / "out"),
        "--agent-replay", str(TRANSCRIPT), "--agent-record", str(path),
    ])
    assert code == 0
    # Re-recording a replay reproduces the committed transcript byte for byte.
    assert path.read_text() == TRANSCRIPT.read_text()


def test_cli_replay_of_a_missing_file_exits_cleanly(tmp_path, capsys):
    code = cli.main(["convert", str(RESIDUE), str(tmp_path / "out"), "--agent-replay", str(tmp_path / "nope.jsonl")])
    assert code == 2
    assert "cannot start the residue agent" in capsys.readouterr().err
