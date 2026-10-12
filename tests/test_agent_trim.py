"""Agent-written ``minecraft:recipe_smithing_trim`` may only name working trim slots (#86).

In the #86 sweep mistral-large-4-0 wrote agent_mod's steel_trim as a Bedrock
``minecraft:recipe_smithing_trim`` whose addition was ``examplemod:steel_ingot``,
a mod id the mod never registered as a ``trim_material``. The structural
validator only checks that the three slots are non-empty, so the recipe
counted as resolved even though the trim did nothing in game.
"""
import json
from pathlib import Path

from portkit.agent.fake import FakeLLM, tool_call
from portkit.agent.loop import Message
from portkit.agent.residue import ResidueAgent, group_residue
from portkit.agent.trim import fabricated_trims, finding
from portkit.pipeline import convert

ROOT = Path(__file__).resolve().parents[1]
AGENT_MOD = ROOT / "fixtures" / "agent_mod" / "input"
TRIM = "recipe:data/examplemod/recipes/steel_trim.json"
TRIM_PATH = "behavior_pack/recipes/steel_trim.json"


def _trim_recipe(template, addition):
    return {
        "format_version": "1.20.10",
        "minecraft:recipe_smithing_trim": {
            "description": {"identifier": "examplemod:steel_trim"},
            "tags": ["smithing_table"],
            "template": template,
            "base": {"tag": "minecraft:trimmable_armors"},
            "addition": addition,
        },
    }


def _vanilla_template():
    return {"item": "minecraft:coast_armor_trim_smithing_template"}


def _vanilla_addition():
    return {"tag": "minecraft:trim_materials"}


def _convert_with_trim(tmp_path, body):
    out = tmp_path / "out"
    convert(AGENT_MOD, out)
    (out / TRIM_PATH).parent.mkdir(parents=True, exist_ok=True)
    (out / TRIM_PATH).write_text(json.dumps(body))
    return out


def _script_for_trim(tmp_path, trim_steps):
    probe = convert(AGENT_MOD, tmp_path / "probe")
    script = []
    for group in group_residue(probe.unhandled):
        script += trim_steps if group.key == TRIM else [Message("assistant", "No Bedrock form.")]
    return script


def _run(tmp_path, script):
    result = convert(AGENT_MOD, tmp_path / "out", agent=ResidueAgent(FakeLLM(script)))
    return result, {o.key: o for o in result.agent.outcomes}


# -- unit tests ----------------------------------------------------------


def test_mod_namespaced_addition_is_rejected(tmp_path):
    out = _convert_with_trim(tmp_path, _trim_recipe(
        _vanilla_template(), {"item": "examplemod:steel_ingot"}
    ))
    bad = fabricated_trims(out, [TRIM_PATH], AGENT_MOD)
    assert [b.where for b in bad] == ["addition"]
    assert bad[0].ident == "examplemod:steel_ingot"


def test_mod_template_is_rejected(tmp_path):
    out = _convert_with_trim(tmp_path, _trim_recipe(
        {"item": "examplemod:custom_template"}, _vanilla_addition()
    ))
    bad = fabricated_trims(out, [TRIM_PATH], AGENT_MOD)
    assert [b.where for b in bad] == ["template"]
    assert bad[0].ident == "examplemod:custom_template"


def test_other_namespace_addition_is_rejected(tmp_path):
    out = _convert_with_trim(tmp_path, _trim_recipe(
        _vanilla_template(), {"item": "someothermod:gold"}
    ))
    bad = fabricated_trims(out, [TRIM_PATH], AGENT_MOD)
    assert [(b.where, b.ident) for b in bad] == [("addition", "someothermod:gold")]


def test_vanilla_only_trim_passes(tmp_path):
    out = _convert_with_trim(tmp_path, _trim_recipe(_vanilla_template(), _vanilla_addition()))
    assert fabricated_trims(out, [TRIM_PATH], AGENT_MOD) == []


def test_all_vanilla_string_slots_pass(tmp_path):
    """Bodies using bare strings (per the validator's accepted shape)."""
    out = _convert_with_trim(tmp_path, _trim_recipe(
        "minecraft:coast_armor_trim_smithing_template",
        "minecraft:iron_ingot",
    ))
    assert fabricated_trims(out, [TRIM_PATH], AGENT_MOD) == []


def test_a_mod_with_a_trim_material_definition_passes(tmp_path):
    """The guard accepts the slot once the mod actually registers the trim (#86)."""
    src = tmp_path / "src"
    for path in AGENT_MOD.rglob("*"):
        if path.is_file():
            dest = src / path.relative_to(AGENT_MOD)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(path.read_bytes())
    material = src / "data/examplemod/trim_material/steel_ingot.json"
    material.parent.mkdir(parents=True, exist_ok=True)
    material.write_text("{}")
    out = _convert_with_trim(tmp_path, _trim_recipe(
        _vanilla_template(), {"item": "examplemod:steel_ingot"}
    ))
    assert fabricated_trims(out, [TRIM_PATH], src) == []


def test_a_mod_with_a_trim_pattern_definition_passes(tmp_path):
    src = tmp_path / "src"
    for path in AGENT_MOD.rglob("*"):
        if path.is_file():
            dest = src / path.relative_to(AGENT_MOD)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(path.read_bytes())
    pattern = src / "data/examplemod/trim_pattern/custom_template.json"
    pattern.parent.mkdir(parents=True, exist_ok=True)
    pattern.write_text("{}")
    out = _convert_with_trim(tmp_path, _trim_recipe(
        {"item": "examplemod:custom_template"}, _vanilla_addition()
    ))
    assert fabricated_trims(out, [TRIM_PATH], src) == []


def test_finding_says_the_slot_and_why(tmp_path):
    out = _convert_with_trim(tmp_path, _trim_recipe(
        _vanilla_template(), {"item": "examplemod:steel_ingot"}
    ))
    bad = fabricated_trims(out, [TRIM_PATH], AGENT_MOD)[0]
    found = finding(bad)
    assert found["path"] == TRIM_PATH
    assert found["rule"] == "agent.unresolved_trim"
    assert found["severity"] == "error"
    assert "addition" in found["message"]
    assert "examplemod:steel_ingot" in found["message"]
    assert "trim_material" in found["message"]
    assert "Write nothing" in found["message"] or "write nothing" in found["message"]


def test_non_trim_recipes_are_ignored(tmp_path):
    out = tmp_path / "out"
    convert(AGENT_MOD, out)
    rel = "behavior_pack/recipes/other.json"
    (out / rel).parent.mkdir(parents=True, exist_ok=True)
    (out / rel).write_text(json.dumps({"minecraft:recipe_shaped": {
        "description": {"identifier": "examplemod:other"},
        "tags": ["crafting_table"],
        "pattern": ["#"], "key": {"#": {"item": "examplemod:steel_ingot"}},
        "result": {"item": "examplemod:steel_block"},
    }}))
    assert fabricated_trims(out, [rel], AGENT_MOD) == []


def test_only_template_and_addition_are_gated(tmp_path):
    """``base`` is descriptive only: a modded base never breaks the trim."""
    out = _convert_with_trim(tmp_path, {
        "format_version": "1.20.10",
        "minecraft:recipe_smithing_trim": {
            "description": {"identifier": "examplemod:steel_trim"},
            "tags": ["smithing_table"],
            "template": _vanilla_template(),
            "base": {"item": "examplemod:custom_armor"},
            "addition": _vanilla_addition(),
        },
    })
    assert fabricated_trims(out, [TRIM_PATH], AGENT_MOD) == []


# -- end-to-end ----------------------------------------------------------


def test_a_written_steel_trim_is_rolled_back_never_resolved(tmp_path):
    """The full #86 scenario: a scripted agent writes agent_mod's steel_trim
    as a Bedrock ``recipe_smithing_trim``. With the guard, the validate tool
    names the slot, the model does not retry, and the group is rolled back
    rather than scoring resolved.
    """
    script = _script_for_trim(tmp_path, [
        tool_call("write_output", path=TRIM_PATH, content=_trim_recipe(
            _vanilla_template(), {"item": "examplemod:steel_ingot"}
        )),
        tool_call("validate"),
        Message("assistant", "Wrote the steel trim."),
    ])
    result, by_key = _run(tmp_path, script)

    trim = by_key[TRIM]
    assert trim.status == "rolled_back", trim.note
    assert trim.written == []
    assert not (tmp_path / "out" / TRIM_PATH).exists()
    assert any("examplemod:steel_ingot" in s and s.endswith("addition: 'examplemod:steel_ingot'") for s in trim.unresolved_trims)
    assert "trim slot(s) with no working form" in trim.note
    assert trim.to_dict()["unresolved_trims"] == trim.unresolved_trims

    # The validate tool told the agent, so it had the chance to fix it.
    client = FakeLLM(script)
    convert(AGENT_MOD, tmp_path / "out2", agent=ResidueAgent(client))
    tool_reply = next(
        m for request in client.seen for m in request
        if m.role == "tool" and m.tool_call_id == "call_validate"
    )
    seen = json.loads(tool_reply.content)
    assert seen["ok"] is False
    assert any(f["rule"] == "agent.unresolved_trim" for f in seen["findings"])

    # The pack still validates; rolling back the trim leaves everything else
    # converted deterministically.
    assert result.report.ok
    assert TRIM.split(":", 1)[1] in [u.source for u in result.unhandled]


def test_a_vanilla_trim_written_by_the_agent_resolves(tmp_path):
    """Vanilla-only trims: the guard does not flag them, so a model can still
    emit one (e.g. when porting a recipe that was already vanilla) and the
    group resolves."""
    script = _script_for_trim(tmp_path, [
        tool_call("write_output", path=TRIM_PATH, content=_trim_recipe(
            _vanilla_template(), _vanilla_addition()
        )),
        tool_call("validate"),
        Message("assistant", "Wrote the trim."),
    ])
    _, by_key = _run(tmp_path, script)
    assert by_key[TRIM].status == "resolved", by_key[TRIM].note
    assert by_key[TRIM].unresolved_trims == []