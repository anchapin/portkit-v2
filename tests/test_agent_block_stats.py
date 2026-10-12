"""Agent-written blocks may only carry properties the source states (#152).

On real-mod residue GLM 5.3 wrote ``minecraft:map_color`` on storage drawers
and waystones blocks. Java sets map colour, hardness, blast resistance, light
and friction in block code, never in JSON, so none of it had a source.
"""
import json
import shutil
import zipfile
from pathlib import Path

import pytest

from portkit import corpus
from portkit.agent.fake import FakeLLM, tool_call
from portkit.agent.loop import Message
from portkit.agent.residue import ResidueAgent, _TrackingToolBox, group_residue
from portkit.agent.stats import document_stats, fabricated_stats, map_color_hex
from portkit.pipeline import convert

ROOT = Path(__file__).resolve().parents[1]
BLOCK_DEFS = ROOT / "fixtures" / "block_defs_mod" / "input"
STAIRS = "block:assets/examplemod/blockstates/steel_stairs.json"
STAIRS_PATH = "behavior_pack/blocks/steel_stairs.json"
BASE = {
    "minecraft:geometry": "minecraft:geometry.full_block",
    "minecraft:material_instances": {"*": {"texture": "examplemod:steel_block"}},
}


def _block(ident="examplemod:steel_stairs", permutations=None, **components):
    body = {
        "description": {"identifier": ident, "menu_category": {"category": "construction"}},
        "components": {**BASE, **components},
    }
    if permutations is not None:
        body["permutations"] = permutations
    return {"format_version": "1.21.40", "minecraft:block": body}


def _flagged(tmp_path, source, doc, rel=STAIRS_PATH):
    out = tmp_path / "out"
    (out / rel).parent.mkdir(parents=True, exist_ok=True)
    (out / rel).write_text(json.dumps(doc))
    return [s.describe() for s in fabricated_stats(out, [rel], source)]


def _source_with(tmp_path, rel, text):
    source = tmp_path / "src"
    shutil.copytree(BLOCK_DEFS, source)
    (source / rel).parent.mkdir(parents=True, exist_ok=True)
    (source / rel).write_text(text)
    return source


# -- map colour ----------------------------------------------------------------

def test_map_color_forms_normalise():
    assert map_color_hex("#5F4A2B") == "#5f4a2b"
    assert map_color_hex("5f4a2b") == "#5f4a2b"
    assert map_color_hex([95, 74, 43]) == "#5f4a2b"
    assert map_color_hex({"color": "#5f4a2b", "tint_method": "grass"}) == "#5f4a2b"
    assert map_color_hex("wood") is None and map_color_hex([0.1, 2, 3]) is None


def test_the_glm_map_color_is_flagged(tmp_path):
    """The shape from #86's real-mod run: a map colour the mod never defines."""
    flagged = _flagged(tmp_path, BLOCK_DEFS, _block(**{"minecraft:map_color": "#8f7748"}))
    assert flagged == [f"{STAIRS_PATH} minecraft:map_color = #8f7748 (examplemod:steel_stairs)"]
    # An unreadable colour can't be traced to anything either.
    flagged = _flagged(tmp_path, BLOCK_DEFS, _block(**{"minecraft:map_color": "wood"}))
    assert flagged == [f'{STAIRS_PATH} minecraft:map_color = "wood" (examplemod:steel_stairs)']


def test_a_map_color_the_source_states_for_the_block_passes(tmp_path):
    source = _source_with(tmp_path, "config/examplemod.toml", 'steel_stairs.map_color = "#8F7748"\n')
    assert _flagged(tmp_path, source, _block(**{"minecraft:map_color": [143, 119, 72]})) == []
    decimal = _source_with(tmp_path / "d", "data/examplemod/blocks/steel_stairs.json",
                           json.dumps({"map_color": 0x8F7748}))
    assert _flagged(tmp_path / "d", decimal, _block(**{"minecraft:map_color": "#8f7748"})) == []
    # Named for another block, it doesn't count.
    other = _source_with(tmp_path / "o", "config/examplemod.toml", 'steel_block.map_color = "#8F7748"\n')
    assert len(_flagged(tmp_path / "o", other, _block(**{"minecraft:map_color": "#8f7748"}))) == 1


def test_a_colour_in_a_texture_or_model_does_not_count(tmp_path):
    source = _source_with(tmp_path, "assets/examplemod/models/block/steel_stairs_tint.json",
                          json.dumps({"tint": "#8f7748"}))
    assert len(_flagged(tmp_path, source, _block(**{"minecraft:map_color": "#8f7748"}))) == 1


# -- block numbers --------------------------------------------------------------

def test_invented_block_numbers_are_flagged_in_components_and_permutations(tmp_path):
    doc = _block(
        **{
            "minecraft:light_emission": 15,
            "minecraft:destructible_by_mining": {"seconds_to_destroy": 3},
            "minecraft:destructible_by_explosion": {"explosion_resistance": 6},
            "minecraft:flammable": {"catch_chance_modifier": 5, "destroy_chance_modifier": 20},
        },
        permutations=[{"condition": "true", "components": {"minecraft:friction": 0.6}}],
    )
    assert _flagged(tmp_path, BLOCK_DEFS, doc) == [
        f"{STAIRS_PATH} minecraft:light_emission = 15 (examplemod:steel_stairs)",
        f"{STAIRS_PATH} minecraft:destructible_by_mining.seconds_to_destroy = 3 (examplemod:steel_stairs)",
        f"{STAIRS_PATH} minecraft:destructible_by_explosion.explosion_resistance = 6 (examplemod:steel_stairs)",
        f"{STAIRS_PATH} minecraft:flammable.catch_chance_modifier = 5 (examplemod:steel_stairs)",
        f"{STAIRS_PATH} minecraft:flammable.destroy_chance_modifier = 20 (examplemod:steel_stairs)",
        f"{STAIRS_PATH} permutations[0].minecraft:friction = 0.6 (examplemod:steel_stairs)",
    ]


def test_omitted_defaults_and_booleans_claim_nothing(tmp_path):
    doc = _block(**{
        "minecraft:light_emission": 0,
        "minecraft:light_dampening": 15,
        "minecraft:friction": 0.4,
        "minecraft:destructible_by_mining": False,
        "minecraft:destructible_by_explosion": True,
        "minecraft:flammable": False,
    })
    out = tmp_path / "out"
    (out / STAIRS_PATH).parent.mkdir(parents=True)
    (out / STAIRS_PATH).write_text(json.dumps(doc))
    assert document_stats(out, STAIRS_PATH) == []


def test_a_stated_hardness_supports_seconds_to_destroy(tmp_path):
    source = _source_with(tmp_path, "config/examplemod.toml", "[steel_stairs]\nhardness = 2.0\nlight = 7\n")
    ok = _block(**{"minecraft:destructible_by_mining": {"seconds_to_destroy": 3.0},
                   "minecraft:light_emission": 7})
    assert _flagged(tmp_path, source, ok) == []
    assert _flagged(tmp_path, source, _block(**{"minecraft:destructible_by_mining": {"seconds_to_destroy": 2}})) == []
    bad = _flagged(tmp_path, source, _block(**{"minecraft:destructible_by_mining": {"seconds_to_destroy": 4}}))
    assert len(bad) == 1


def test_validate_tells_the_agent_to_omit_it(tmp_path):
    out = tmp_path / "out"
    convert(BLOCK_DEFS, out)
    box = _TrackingToolBox(BLOCK_DEFS, out, "examplemod")
    box.write_output(STAIRS_PATH, _block(**{"minecraft:map_color": "#8f7748"}))
    report = box.validate()
    found = [f for f in report["findings"] if f["rule"] == "agent.fabricated_stat"]
    assert report["ok"] is False and len(found) == 1
    message = found[0]["message"]
    assert "no such map colour for this block" in message
    assert "remove the minecraft:map_color component" in message and "final message" in message


# -- the group ---------------------------------------------------------------

def _script_for_stairs(tmp_path, steps):
    probe = convert(BLOCK_DEFS, tmp_path / "probe")
    script = []
    for group in group_residue(probe.unhandled):
        script += steps if group.key == STAIRS else [Message("assistant", "No Bedrock form.")]
    return script


def _run(tmp_path, script):
    result = convert(BLOCK_DEFS, tmp_path / "out", agent=ResidueAgent(FakeLLM(script)))
    return result, {o.key: o for o in result.agent.outcomes}


def test_a_group_that_keeps_an_invented_map_color_is_rolled_back(tmp_path):
    script = _script_for_stairs(tmp_path, [
        tool_call("write_output", path=STAIRS_PATH, content=_block(**{"minecraft:map_color": "#8f7748"})),
        tool_call("validate"),
        Message("assistant", "Converted the stairs."),
    ])
    result, by_key = _run(tmp_path, script)
    stairs = by_key[STAIRS]
    assert stairs.status == "rolled_back"
    assert stairs.fabricated_stats == [f"{STAIRS_PATH} minecraft:map_color = #8f7748 (examplemod:steel_stairs)"]
    assert not (tmp_path / "out" / STAIRS_PATH).exists()
    assert result.report.ok


def test_omitting_the_map_color_resolves(tmp_path):
    script = _script_for_stairs(tmp_path, [
        tool_call("write_output", path=STAIRS_PATH, content=_block(**{"minecraft:map_color": "#8f7748"})),
        tool_call("validate"),
        tool_call("write_output", path=STAIRS_PATH, content=_block()),
        tool_call("validate"),
        Message("assistant", "Wrote the stairs; left out map colour, which the source does not give."),
    ])
    _, by_key = _run(tmp_path, script)
    assert by_key[STAIRS].status == "resolved", by_key[STAIRS].note


# -- real mod ------------------------------------------------------------------

@pytest.mark.realmods
def test_storage_drawers_map_color_is_caught(tmp_path):
    """GLM 5.3's map_color on the real storage drawers jar, which defines none."""
    mod = next(m for m in corpus.load() if m.name == "storage_drawers_1122")
    jar = corpus.cached(mod)
    if jar is None:
        pytest.skip("storage_drawers_1122 not cached (portkit corpus fetch)")
    source = tmp_path / "src"
    with zipfile.ZipFile(jar) as archive:
        archive.extractall(source)
    rel = "behavior_pack/blocks/basicdrawers.json"
    doc = _block("storagedrawers:basicdrawers", **{"minecraft:map_color": "#8f7748",
                                                    "minecraft:destructible_by_mining": {"seconds_to_destroy": 4.5}})
    assert _flagged(tmp_path, source, doc, rel) == [
        f"{rel} minecraft:destructible_by_mining.seconds_to_destroy = 4.5 (storagedrawers:basicdrawers)",
        f"{rel} minecraft:map_color = #8f7748 (storagedrawers:basicdrawers)",
    ]
    assert _flagged(tmp_path, source, _block("storagedrawers:basicdrawers"), rel) == []
