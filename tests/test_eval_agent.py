"""Agent eval matrix (issue #77): pass/fail/unscored scoring and format-failure counts.

These run entirely against FakeLLM through the cli and the residue agent, so
no key or socket is needed. The point is to lock down the three behaviours
the issue calls out:

1. A run that finishes clean is ``pass`` (resolved groups, no unscored).
2. A run that dies on a provider error during the loop is ``unscored``,
   NOT ``fail`` — a broken harness should not look like a worse model.
3. Tool calls whose name or arguments do not match the toolbox are counted
   per provider, separate from the pass/fail verdict.
"""
from __future__ import annotations

import argparse
import json

from portkit import cli
from portkit.agent.fake import FakeLLM, tool_call
from portkit.agent.loop import Message
from portkit.agent.residue import ResidueAgent
from portkit.agent.tools import ToolBox
from portkit.cli import (
    _cmd_eval_agent,
    _format_eval_matrix,
    _format_target_totals,
    _parse_target,
    _per_target_totals,
    _score_residue_outcomes,
)
from portkit.pipeline import convert

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
AGENT_FIXTURE = ROOT / "fixtures" / "agent_mod" / "input"

BEDROCK_TRIM = {
    "format_version": "1.20.10",
    "minecraft:recipe_shapeless": {
        "description": {"identifier": "examplemod:steel_trim"},
        "tags": ["smithing_table"],
        "ingredients": [{"item": "examplemod:steel_ingot"}],
        "result": {"item": "examplemod:steel_smithing_template"},
    },
}

BEDROCK_ALLOY = {
    "format_version": "1.20.10",
    "minecraft:recipe_shaped": {
        "description": {"identifier": "examplemod:alloy_block"},
        "tags": ["crafting_table"],
        "pattern": ["iii", "iii", "iii"],
        "key": {"i": {"item": "examplemod:steel_ingot"}},
        "result": {"item": "examplemod:alloy_block"},
    },
}

BEDROCK_SWORD = {
    "format_version": "1.21.0",
    "minecraft:item": {
        "description": {
            "identifier": "examplemod:steel_sword",
            "menu_category": {"category": "equipment"},
        },
        "components": {"minecraft:max_damage": 250},
    },
}


def _good_script():
    """Resolve all three residue groups: item, alloy recipe, trim recipe."""
    return [
        # group 1: held sword item
        tool_call("read_source", path="assets/examplemod/models/item/steel_sword.json"),
        tool_call("write_output", path="behavior_pack/items/steel_sword.json", content=BEDROCK_SWORD),
        tool_call("validate"),
        Message("assistant", "ok"),
        # group 2: 3x3 alloy recipe
        tool_call("read_source", path="data/examplemod/recipes/alloy_block.json"),
        tool_call("write_output", path="behavior_pack/recipes/alloy_block.json", content=BEDROCK_ALLOY),
        tool_call("validate"),
        Message("assistant", "ok"),
        # group 3: smithing trim
        tool_call("read_source", path="data/examplemod/recipes/steel_trim.json"),
        tool_call("write_output", path="behavior_pack/recipes/steel_trim.json", content=BEDROCK_TRIM),
        tool_call("validate"),
        Message("assistant", "ok"),
    ]


def _bad_format_script():
    """Same groups, but the second group calls a tool that does not exist."""
    return [
        # group 1: ok
        tool_call("read_source", path="assets/examplemod/models/item/steel_sword.json"),
        tool_call("write_output", path="behavior_pack/items/steel_sword.json", content=BEDROCK_SWORD),
        tool_call("validate"),
        Message("assistant", "ok"),
        # group 2: writes the recipe OK, but the *next* call is a bogus tool
        tool_call("read_source", path="data/examplemod/recipes/alloy_block.json"),
        tool_call("write_output", path="behavior_pack/recipes/alloy_block.json", content=BEDROCK_ALLOY),
        tool_call("bogus_tool_name", anything="goes"),
        tool_call("validate"),
        Message("assistant", "ok"),
        # group 3: ok
        tool_call("read_source", path="data/examplemod/recipes/steel_trim.json"),
        tool_call("write_output", path="behavior_pack/recipes/steel_trim.json", content=BEDROCK_TRIM),
        tool_call("validate"),
        Message("assistant", "ok"),
    ]


def _crashing_script():
    """Provider raises mid-session: scored as unscored, not fail."""
    return [
        # group 1: ok
        tool_call("read_source", path="assets/examplemod/models/item/steel_sword.json"),
        tool_call("write_output", path="behavior_pack/items/steel_sword.json", content=BEDROCK_SWORD),
        tool_call("validate"),
        Message("assistant", "ok"),
        # group 2: provider blows up before we even reply
        _Boom(),
    ]


class _Boom(FakeLLM):
    """A scripted client whose first call raises. Used by the unscored path."""

    def __init__(self):
        self.script = []

    def complete(self, messages, tools):
        raise RuntimeError("provider unavailable: simulated outage")


# ---- direct scoring helpers ------------------------------------------------


def test_parse_target_accepts_provider_model():
    assert _parse_target("anthropic:claude-haiku-4.5") == (
        "anthropic", "claude-haiku-4.5", None,
    )
    assert _parse_target("gemini_native:gemini-flash-latest") == (
        "gemini_native", "gemini-flash-latest", None,
    )


def test_parse_target_accepts_optional_base_url():
    assert _parse_target("openai:anthropic/claude-haiku-4.5@https://openrouter.ai/api/v1") == (
        "openai", "anthropic/claude-haiku-4.5", "https://openrouter.ai/api/v1",
    )


def test_parse_target_rejects_malformed():
    import pytest

    # No colon at all -> no provider:model. Empty halves also rejected.
    for bad in ("anthropic", ":claude-x", "anthropic:"):
        with pytest.raises(ValueError):
            _parse_target(bad)
    # But model names may contain colons (e.g. "gemini-3.1:pro-preview")
    # so we don't reject extra colons inside the model part.
    assert _parse_target("anthropic:claude:haiku") == (
        "anthropic", "claude:haiku", None,
    )


def test_score_counts_resolved_skipped_and_other():
    from portkit.agent.residue import GroupOutcome

    outcomes = [
        GroupOutcome(key="a", kind="recipe", source="x", status="resolved"),
        GroupOutcome(key="b", kind="recipe", source="y", status="resolved"),
        GroupOutcome(key="c", kind="recipe", source="z", status="skipped"),
        GroupOutcome(key="d", kind="recipe", source="q", status="error"),
        GroupOutcome(key="e", kind="recipe", source="r", status="unresolved"),
        GroupOutcome(key="f", kind="recipe", source="s", status="rolled_back"),
    ]
    p, f, u = _score_residue_outcomes(outcomes)
    assert p == 2 and f == 2 and u == 2


# ---- format-failure counter -------------------------------------------------


def test_toolbox_counts_unknown_tool_as_format_failure(tmp_path):
    box = ToolBox(tmp_path, tmp_path / "out")
    out = box.invoke("no_such_tool", {})
    assert "error" in out and box.format_failures == 1


def test_toolbox_counts_bad_arguments_as_format_failure(tmp_path):
    box = ToolBox(tmp_path, tmp_path / "out")
    out = box.invoke("read_source", {"wrong": "x"})  # required `path` missing
    assert "error" in out
    assert box.format_failures == 1


def test_toolbox_does_not_count_successful_tool_calls(tmp_path):
    box = ToolBox(tmp_path, tmp_path / "out")
    box.invoke("list_source", {})
    box.invoke("validate", {})
    assert box.format_failures == 0


# ---- end-to-end through convert() + the matrix formatters -------------------


def test_clean_run_scores_pass_with_no_format_failures(tmp_path):
    client = FakeLLM(_good_script())
    result = convert(AGENT_FIXTURE, tmp_path / "out", agent=ResidueAgent(client))
    assert result.report.ok
    assert result.agent is not None
    p, f, u = _score_residue_outcomes(result.agent.outcomes)
    assert p == 3 and f == 0 and u == 0
    assert result.agent.format_failures == 0


def test_bad_tool_call_keeps_the_group_resolved_but_counts_format_failure(tmp_path):
    client = FakeLLM(_bad_format_script())
    result = convert(AGENT_FIXTURE, tmp_path / "out", agent=ResidueAgent(client))
    assert result.report.ok, [f.message for f in result.report.errors]
    assert result.agent is not None
    p, f, u = _score_residue_outcomes(result.agent.outcomes)
    assert p == 3 and f == 0 and u == 0
    # one bogus_tool_name invocation -> counted on the group that issued it
    assert result.agent.format_failures == 1


def test_provider_error_is_unscored_not_failed(tmp_path):
    """Every group ends in 'error' status when the provider blows up; the
    scoring rule keeps them out of the pass rate."""
    client = _Boom()
    result = convert(AGENT_FIXTURE, tmp_path / "out", agent=ResidueAgent(client))
    assert result.agent is not None
    statuses = [o.status for o in result.agent.outcomes]
    assert statuses  # at least one group ran
    assert all(s == "error" for s in statuses), statuses
    p, f, u = _score_residue_outcomes(result.agent.outcomes)
    assert p == 0 and f == 0 and u == len(statuses)
    # Per the issue, unscored tasks are reported separately. The pass rate
    # here is n/a, not 0.0, because there were no scored tasks.
    totals = _per_target_totals([{
        "fixture": "agent_mod", "provider": "fake", "model": "boom",
        "outcome": "unscored", "pass": p, "fail": f, "unscored": u,
        "groups": len(statuses), "steps": 0, "tokens": 0,
        "cost_usd": None, "stopped_by": None, "format_failures": 0,
    }])
    assert totals[0]["pass_rate"] is None


# ---- the matrix formatters and the CLI dispatch ----------------------------


def test_matrix_formatters_aggregate_per_target():
    rows = [
        {"fixture": "a", "provider": "anthropic", "model": "x",
         "outcome": "pass", "pass": 3, "fail": 0, "unscored": 0,
         "groups": 3, "steps": 7, "tokens": 1000, "cost_usd": 0.02,
         "stopped_by": None, "format_failures": 0},
        {"fixture": "b", "provider": "anthropic", "model": "x",
         "outcome": "pass", "pass": 2, "fail": 1, "unscored": 0,
         "groups": 3, "steps": 9, "tokens": 1500, "cost_usd": 0.03,
         "stopped_by": None, "format_failures": 1},
        {"fixture": "a", "provider": "gemini_native", "model": "y",
         "outcome": "unscored", "pass": 0, "fail": 0, "unscored": 3,
         "groups": 3, "steps": 1, "tokens": 0, "cost_usd": None,
         "stopped_by": None, "format_failures": 0},
    ]
    matrix = _format_eval_matrix(rows)
    assert "anthropic:x" in matrix and "gemini_native:y" in matrix
    assert "3/0/0" in matrix  # a/anthropic
    assert "2/1/0" in matrix  # b/anthropic
    assert "0/0/3" in matrix  # a/gemini_native

    totals = _per_target_totals(rows)
    by_target = {(t["provider"], t["model"]): t for t in totals}
    anth = by_target[("anthropic", "x")]
    assert anth["pass"] == 5 and anth["fail"] == 1 and anth["unscored"] == 0
    assert anth["pass_rate"] == 5 / 6  # 5 pass out of 6 scored, not 7
    assert anth["format_failures"] == 1
    gem = by_target[("gemini_native", "y")]
    assert gem["unscored"] == 3 and gem["pass_rate"] is None  # nothing was scored

    rendered = _format_target_totals(totals)
    assert "anthropic:x" in rendered
    assert "gemini_native:y" in rendered
    # Unscored make pass rate n/a, not 0.0
    assert "n/a" in rendered


def test_cli_eval_agent_requires_targets():
    args = argparse.Namespace(
        target=[], fixtures=None, agent_fixture=None,
        agent_max_steps=12, agent_max_tokens=None, agent_max_cost=None,
        matrix_out=None,
    )
    rc = _cmd_eval_agent(args)
    assert rc == 2


def test_cli_eval_agent_uses_factory_env_and_restores_it(tmp_path, monkeypatch):
    """The dispatcher must overwrite PORTKIT_LLM_* env vars per target and
    restore them on the way out, so a second provider sees a clean factory."""
    calls: list[tuple[str, str]] = []

    def _fake_make_client(provider=None, model=None, **kwargs):
        # The cli reads provider/model from PORTKIT_LLM_* env vars and passes
        # them positionally here. Empty/None means the dispatcher failed to
        # set them; that's a test failure we want to surface.
        import os as _os_inside
        calls.append((_os_inside.environ.get("PORTKIT_LLM_PROVIDER", ""),
                      _os_inside.environ.get("PORTKIT_LLM_MODEL", "")))
        # The factory returns a FakeLLM that always says "no residue here".
        # That makes every residue group "unresolved" -> counted as fail.
        return FakeLLM([Message("assistant", "no residue here")])

    # cli.py imports make_client into its module namespace, so that's the
    # binding the runtime code uses.
    monkeypatch.setattr(cli, "make_client", _fake_make_client)

    args = argparse.Namespace(
        target=["openai:fake-model-1", "anthropic:fake-model-2"],
        fixtures=str(ROOT / "fixtures"),
        agent_fixture="agent_mod",
        agent_max_steps=4,
        agent_max_tokens=None,
        agent_max_cost=None,
        matrix_out=str(tmp_path / "matrix.json"),
    )

    # Snapshot the env vars we expect to be restored.
    import os as _os_mod
    saved = {k: _os_mod.environ.get(k) for k in (
        "PORTKIT_LLM_PROVIDER", "PORTKIT_LLM_MODEL", "PORTKIT_LLM_BASE_URL",
    )}
    try:
        rc = _cmd_eval_agent(args)
        assert rc == 0
        assert calls == [("openai", "fake-model-1"), ("anthropic", "fake-model-2")]
        # Env is back to what it was before the run.
        for k, v in saved.items():
            assert _os_mod.environ.get(k) == v
        # Matrix file exists, has both rows.
        matrix = json.loads((tmp_path / "matrix.json").read_text())
        providers = {(r["provider"], r["model"]) for r in matrix["rows"]}
        assert providers == {("openai", "fake-model-1"), ("anthropic", "fake-model-2")}
    finally:
        for k, v in saved.items():
            if v is None:
                _os_mod.environ.pop(k, None)
            else:
                _os_mod.environ[k] = v