"""Agent-written items may only carry gameplay numbers the source states (#135).

After #132 DeepSeek wrote agent_mod's steel sword with damage 5, durability 250
and an enchantable value, and the fixture has no stats anywhere: a model, a
texture, a lang line and a crafting recipe.
"""
import json
from pathlib import Path

from portkit.agent.fake import FakeLLM, tool_call
from portkit.agent.loop import Message
from portkit.agent.residue import ResidueAgent, group_residue
from portkit.agent.stats import fabricated_stats, item_stats, source_numbers
from portkit.pipeline import convert

ROOT = Path(__file__).resolve().parents[1]
AGENT_MOD = ROOT / "fixtures" / "agent_mod" / "input"
SWORD = "item:assets/examplemod/models/item/steel_sword.json"
SWORD_PATH = "behavior_pack/items/steel_sword.json"


def _sword(**stats):
    components = {
        "minecraft:icon": "examplemod:steel_sword",
        "minecraft:display_name": {"value": "item.examplemod:steel_sword.name"},
        "minecraft:hand_equipped": True,
        "minecraft:max_stack_size": 1,
        "minecraft:repairable": {"repair_items": [{"items": ["examplemod:steel_ingot"]}]},
        "minecraft:tags": {"tags": ["minecraft:is_sword"]},
        **stats,
    }
    return {
        "format_version": "1.21.40",
        "minecraft:item": {
            "description": {"identifier": "examplemod:steel_sword", "menu_category": {"category": "equipment"}},
            "components": components,
        },
    }


DEEPSEEK = {
    "minecraft:damage": 5,
    "minecraft:durability": {"max_durability": 250},
    "minecraft:enchantable": {"slot": "sword", "value": 10},
}


def _write(tmp_path, item):
    out = tmp_path / "out"
    convert(AGENT_MOD, out)
    target = out / SWORD_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(item))
    return out


def _script_for_sword(tmp_path, sword_steps):
    probe = convert(AGENT_MOD, tmp_path / "probe")
    script = []
    for group in group_residue(probe.unhandled):
        script += sword_steps if group.key == SWORD else [Message("assistant", "No Bedrock form.")]
    return script


def _run(tmp_path, script):
    result = convert(AGENT_MOD, tmp_path / "out", agent=ResidueAgent(FakeLLM(script)))
    return result, {o.key: o for o in result.agent.outcomes}


def test_the_deepseek_sword_is_flagged(tmp_path):
    out = _write(tmp_path, _sword(**DEEPSEEK))
    bad = fabricated_stats(out, [SWORD_PATH], AGENT_MOD)
    assert sorted(s.where for s in bad) == [
        "minecraft:damage",
        "minecraft:durability.max_durability",
        "minecraft:enchantable.value",
    ]
    assert {s.value for s in bad} == {5.0, 250.0, 10.0}


def test_descriptive_components_are_not_stats(tmp_path):
    out = _write(tmp_path, _sword())
    assert item_stats(out, SWORD_PATH) == []
    assert fabricated_stats(out, [SWORD_PATH], AGENT_MOD) == []


def test_numbers_in_models_and_recipes_do_not_count(tmp_path):
    # The sword's recipe has no numbers, but a model's display transform would;
    # neither is where Java keeps gameplay values.
    assert source_numbers(AGENT_MOD, "examplemod:steel_sword") == set()


def _mod_with(tmp_path, rel, text):
    src = tmp_path / "src"
    for path in AGENT_MOD.rglob("*"):
        if path.is_file():
            dest = src / path.relative_to(AGENT_MOD)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(path.read_bytes())
    target = src / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    return src


def test_a_stat_the_source_states_for_the_item_is_kept(tmp_path):
    src = _mod_with(
        tmp_path,
        "data/examplemod/stats/steel_sword.json",
        json.dumps({"durability": 250, "attack_damage": 4, "enchantability": 10}),
    )
    out = _write(tmp_path, _sword(**DEEPSEEK))
    # 250 and 10 are stated; damage 5 = Java attack_damage 4 + the base of 1.
    assert fabricated_stats(out, [SWORD_PATH], src) == []


def test_a_config_naming_the_item_counts_but_one_naming_another_does_not(tmp_path):
    src = _mod_with(tmp_path, "config/examplemod.toml", "[steel_axe]\ndurability = 250\n")
    out = _write(tmp_path, _sword(**{"minecraft:durability": {"max_durability": 250}}))
    assert [s.where for s in fabricated_stats(out, [SWORD_PATH], src)] == ["minecraft:durability.max_durability"]
    src2 = _mod_with(tmp_path / "b", "config/examplemod.toml", "[steel_sword]\ndurability = 250\n")
    assert fabricated_stats(out, [SWORD_PATH], src2) == []


def test_digger_food_and_fuel_are_checked(tmp_path):
    item = _sword(**{
        "minecraft:digger": {"destroy_speeds": [{"block": "minecraft:stone", "speed": 6}]},
        "minecraft:food": {"nutrition": 4, "saturation_modifier": 0.3},
        "minecraft:fuel": {"duration": 10},
    })
    out = _write(tmp_path, item)
    wheres = sorted(s.where for s in fabricated_stats(out, [SWORD_PATH], AGENT_MOD))
    assert wheres == [
        "minecraft:digger.destroy_speeds[0].speed",
        "minecraft:food.nutrition",
        "minecraft:food.saturation_modifier",
        "minecraft:fuel.duration",
    ]


def test_validate_tells_the_agent_and_removing_the_stats_resolves(tmp_path):
    script = _script_for_sword(tmp_path, [
        tool_call("write_output", path=SWORD_PATH, content=_sword(**DEEPSEEK)),
        tool_call("validate"),
        tool_call("write_output", path=SWORD_PATH, content=_sword()),
        tool_call("validate"),
        Message("assistant", "Wrote the sword; left out damage and durability, which the source does not give."),
    ])
    client = FakeLLM(script)
    result = convert(AGENT_MOD, tmp_path / "out", agent=ResidueAgent(client))
    sword = {o.key: o for o in result.agent.outcomes}[SWORD]
    assert sword.status == "resolved" and sword.fabricated_stats == []
    # The first validate answer named each fabricated stat; the second was clean.
    last = max(client.seen, key=lambda seen: sum(m.role == "tool" for m in seen))
    answers = [json.loads(m.content) for m in last if m.role == "tool" and '"findings"' in m.content]
    flagged = [answer for answer in answers if any(f["rule"] == "agent.fabricated_stat" for f in answer["findings"])]
    assert answers and len(flagged) == 1


def test_validate_reports_agent_fabricated_stat(tmp_path):
    from portkit.agent.residue import _TrackingToolBox

    out = tmp_path / "out"
    convert(AGENT_MOD, out)
    box = _TrackingToolBox(AGENT_MOD, out)
    box.write_output(SWORD_PATH, _sword(**DEEPSEEK))
    report = box.validate()
    rules = [f["rule"] for f in report["findings"] if f["rule"] == "agent.fabricated_stat"]
    assert len(rules) == 3 and report["ok"] is False
    message = next(f["message"] for f in report["findings"] if f["rule"] == "agent.fabricated_stat")
    assert "never guessed" in message and "final message" in message


def test_a_group_that_keeps_a_fabricated_stat_is_rolled_back(tmp_path):
    script = _script_for_sword(tmp_path, [
        tool_call("write_output", path=SWORD_PATH, content=_sword(**DEEPSEEK)),
        tool_call("validate"),
        Message("assistant", "Converted the steel sword."),
    ])
    result, by_key = _run(tmp_path, script)
    sword = by_key[SWORD]
    assert sword.status == "rolled_back"
    assert sword.fabricated_stats == [
        f"{SWORD_PATH} minecraft:damage = 5 (examplemod:steel_sword)",
        f"{SWORD_PATH} minecraft:durability.max_durability = 250 (examplemod:steel_sword)",
        f"{SWORD_PATH} minecraft:enchantable.value = 10 (examplemod:steel_sword)",
    ]
    assert sword.note.startswith("rolled back: stat(s) the source does not state:")
    assert not (tmp_path / "out" / SWORD_PATH).exists()
    assert result.report.ok
    assert sword.to_dict()["fabricated_stats"] == sword.fabricated_stats
