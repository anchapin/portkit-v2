"""Residue task builder (#18): Unhandled items in, one agent session per group out.

Everything runs against FakeLLM, so none of this needs a key or a socket.
"""
import json
from pathlib import Path

from portkit import cli
from portkit.agent.fake import FakeLLM, tool_call
from portkit.agent.loop import Message
from portkit.agent.residue import ResidueAgent, build_task, group_residue
from portkit.model import Unhandled
from portkit.pipeline import convert

ROOT = Path(__file__).resolve().parents[1]
RESIDUE = ROOT / "fixtures" / "residue_mod" / "input"
TAG_RECIPE = "data/examplemod/recipes/steel_block.json"
SMITHING = "data/examplemod/recipes/steel_smithing.json"

# What a model should write for the tag recipe: the tag names one modded item.
BEDROCK_RECIPE = {
    "format_version": "1.20.10",
    "minecraft:recipe_shapeless": {
        "description": {"identifier": "examplemod:steel_block"},
        "tags": ["crafting_table"],
        "ingredients": [{"item": "examplemod:steel_ingot"}],
        "result": {"item": "examplemod:steel_block"},
    },
}


def _good_script():
    """Session 1 converts the tag recipe; session 2 declines the smithing one."""
    return [
        tool_call("read_source", path=TAG_RECIPE),
        tool_call("write_output", path="behavior_pack/recipes/steel_block.json", content=BEDROCK_RECIPE),
        tool_call("validate"),
        Message("assistant", "Converted the tag recipe; the validator is clean."),
        Message("assistant", "Bedrock smithing needs a template item this recipe does not name."),
    ]


def test_groups_fold_by_kind_and_source():
    items = [
        Unhandled("assets/m/sounds.json", "sound", "event a replaces vanilla"),
        Unhandled("assets/m/sounds/x.wav", "sound", "wav, not ogg"),
        Unhandled("assets/m/sounds.json", "sound", "category jukebox"),
        Unhandled("assets/m/sounds.json", "lang", "same file, other kind"),
    ]
    groups = group_residue(items)
    assert [g.key for g in groups] == [
        "sound:assets/m/sounds.json",
        "sound:assets/m/sounds/x.wav",
        "lang:assets/m/sounds.json",
    ]
    assert groups[0].reasons == ["event a replaces vanilla", "category jukebox"]
    assert groups[0].count == 1


def test_task_carries_the_source_and_the_specific_reason(tmp_path):
    item = Unhandled(TAG_RECIPE, "recipe", "ingredient uses tag 'c:ingots/steel', which covers more than one item")
    task = build_task(group_residue([item])[0], RESIDUE, tmp_path, "examplemod")
    assert "c:ingots/steel', which covers more than one item" in task
    assert '"tag": "c:ingots/steel"' in task  # the file content itself
    assert "behavior_pack/recipes/" in task  # where this kind lives in Bedrock


def test_task_lists_a_directory_source_instead_of_inlining_it(tmp_path):
    item = Unhandled("data/examplemod/recipes/", "unowned", "2 file(s) no converter claims yet", 2)
    task = build_task(group_residue([item])[0], RESIDUE, tmp_path, "examplemod")
    assert "holds 2 file(s)" in task and SMITHING in task


def test_convert_with_agent_resolves_residue_and_still_validates(tmp_path):
    client = FakeLLM(_good_script())
    out = tmp_path / "out"
    result = convert(RESIDUE, out, agent=ResidueAgent(client))

    assert result.report.ok, [f.message for f in result.report.errors]
    assert (out / "behavior_pack" / "recipes" / "steel_block.json").is_file()
    # The scaffolded behavior pack depends on the resource pack that shipped.
    bp = json.loads((out / "behavior_pack" / "manifest.json").read_text())
    rp = json.loads((out / "resource_pack" / "manifest.json").read_text())
    assert bp["dependencies"][0]["uuid"] == rp["header"]["uuid"]

    statuses = {o.source: o.status for o in result.agent.outcomes}
    assert statuses == {TAG_RECIPE: "resolved", SMITHING: "unresolved"}
    assert [u.source for u in result.unhandled] == [SMITHING]
    assert result.file_count == 5 and result.residue_count == 1
    assert result.addon is not None and result.addon.is_file()
    assert json.loads((out / "unhandled.json").read_text())[0]["source"] == SMITHING
    assert result.summary()["agent"]["resolved"] == 1

    # Each session saw only its own group's task.
    first_task = client.seen[0][1].content
    assert TAG_RECIPE in first_task and SMITHING not in first_task


def test_a_group_that_breaks_the_tree_is_rolled_back(tmp_path):
    broken = {"format_version": "1.20.10", "minecraft:recipe_shapeless": {"tags": ["crafting_table"]}}
    client = FakeLLM(
        [
            tool_call("write_output", path="behavior_pack/recipes/steel_block.json", content=broken),
            Message("assistant", "Done."),
            Message("assistant", "No Bedrock equivalent."),
        ]
    )
    out = tmp_path / "out"
    result = convert(RESIDUE, out, agent=ResidueAgent(client))

    assert result.agent.outcomes[0].status == "rolled_back"
    assert not (out / "behavior_pack").exists()  # the empty scaffold went too
    assert result.report.ok and len(result.unhandled) == 2


def test_a_provider_failure_ends_the_group_not_the_run(tmp_path):
    class Flaky:
        calls = 0

        def complete(self, messages, tools):
            Flaky.calls += 1
            if Flaky.calls == 1:
                raise RuntimeError("HTTP 529 overloaded")
            return Message("assistant", "No Bedrock equivalent.")

    result = convert(RESIDUE, tmp_path / "out", agent=ResidueAgent(Flaky()))
    assert [o.status for o in result.agent.outcomes] == ["error", "unresolved"]
    assert "overloaded" in result.agent.outcomes[0].note
    assert len(result.unhandled) == 2 and result.report.ok


def test_kinds_no_tool_can_read_are_skipped_without_a_session(tmp_path):
    client = FakeLLM([])
    run = ResidueAgent(client).run(
        RESIDUE, tmp_path, [Unhandled("12 compiled class file(s)", "java_code", "bytecode", 12)], "examplemod"
    )
    assert run.outcomes[0].status == "skipped" and client.seen == []
    assert len(run.remaining) == 1
    assert not any(tmp_path.iterdir())  # scaffolds cleaned up


def test_cli_convert_agent(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_residue_agent", lambda args: ResidueAgent(FakeLLM(_good_script())))
    code = cli.main(["convert", str(RESIDUE), str(tmp_path / "out"), "--agent"])
    out = capsys.readouterr().out
    assert code == 0
    assert "agent resolved 1 of 2 residue group(s)" in out
    assert f"resolved: recipe:{TAG_RECIPE}" in out
    assert (tmp_path / "out" / "behavior_pack" / "recipes" / "steel_block.json").is_file()


def test_cli_convert_agent_without_a_provider_says_so(tmp_path, monkeypatch, capsys):
    for var in ("PORTKIT_LLM_PROVIDER", "PORTKIT_LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    code = cli.main(["convert", str(RESIDUE), str(tmp_path / "out"), "--agent"])
    assert code == 2
    assert "PORTKIT_LLM_PROVIDER" in capsys.readouterr().err


def test_write_output_rejects_string_content(tmp_path):
    """A model that passes a JSON-string instead of a dict would otherwise
    produce a JSON-encoded string file — valid JSON, useless as a Bedrock
    file. The tool should return an error the loop can show the model.

    Discovered by the model sweep: deepseek-v4.1-flash passed ``content`` as
    a string and the resulting file made the validator crash later.
    """
    src = tmp_path / "src"
    out = tmp_path / "out"
    src.mkdir()
    from portkit.agent.tools import ToolBox
    box = ToolBox(src, out)
    result = box.invoke("write_output", {"path": "behavior_pack/recipes/x.json", "content": "oops"})
    assert "error" in result
    assert "object" in result["error"].lower() or "dict" in result["error"].lower()
    # The file must NOT have been written.
    assert not (out / "behavior_pack" / "recipes" / "x.json").exists()


def test_write_output_accepts_dict_content(tmp_path):
    """Companion to the above — the happy path still works."""
    src = tmp_path / "src"
    out = tmp_path / "out"
    src.mkdir()
    from portkit.agent.tools import ToolBox
    box = ToolBox(src, out)
    payload = {"format_version": "1.20.10", "minecraft:item": {"description": {"identifier": "t:x"}}}
    result = box.invoke("write_output", {"path": "behavior_pack/items/x.json", "content": payload})
    assert result.get("written") == "behavior_pack/items/x.json"
    assert (out / "behavior_pack" / "items" / "x.json").is_file()


def test_convert_with_agent_on_enriched_fixture(tmp_path):
    """The deterministic path emits items + blocks for ``residue_mod_enriched``
    so the agent's residue list shortens. The tag recipe becomes resolvable
    (steel_ingot / steel_block exist behind it); the smithing one still has
    no template/addition and stays residue.

    The deliverable is the same shape as ``test_convert_with_agent_resolves_residue_and_still_validates``
    but against the enriched fixture.
    """
    enriched = ROOT / "fixtures" / "residue_mod_enriched" / "input"
    client = FakeLLM(_good_script())
    out = tmp_path / "out"
    result = convert(enriched, out, agent=ResidueAgent(client))

    assert result.report.ok, [f.message for f in result.report.errors]
    assert (out / "behavior_pack" / "recipes" / "steel_block.json").is_file()
    # The agent also sees a populated tree with steel_ingot and steel_block.
    assert (out / "behavior_pack" / "items" / "steel_ingot.json").is_file()
    assert (out / "behavior_pack" / "blocks" / "steel_block.json").is_file()

    statuses = {o.source: o.status for o in result.agent.outcomes}
    assert statuses == {TAG_RECIPE: "resolved", SMITHING: "unresolved"}
    # smithing is the only remaining residue item post-agent.
    assert [u.source for u in result.unhandled] == [SMITHING]



def _empty_reply_outcomes(tmp_path, reply):
    from portkit.agent.budget import Usage

    reply.usage = Usage(729, 273)
    client = FakeLLM([reply, Message("assistant", "Smithing needs a template item.")])
    result = convert(RESIDUE, tmp_path / "out", agent=ResidueAgent(client))
    return {o.key: o for o in result.agent.outcomes}


def test_an_empty_final_reply_says_why_in_the_note(tmp_path):
    """#85: gemini-pro-latest ended both groups on an empty reply and the note was ""."""
    outcomes = _empty_reply_outcomes(tmp_path, Message("assistant", "", finish_reason="length"))
    note = outcomes[f"recipe:{TAG_RECIPE}"].note
    assert note == "model ended with an empty reply (finish_reason=length, 273 output tokens)"
    assert outcomes[f"recipe:{TAG_RECIPE}"].status != "resolved"


def test_a_refusal_lands_in_the_note(tmp_path):
    outcomes = _empty_reply_outcomes(
        tmp_path, Message("assistant", "", finish_reason="stop", refusal="I can't help with that.")
    )
    assert outcomes[f"recipe:{TAG_RECIPE}"].note == "model refused: I can't help with that."
