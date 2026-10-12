"""Agent-written items must be ones the Java source registers (#86).

On real-mod residue GLM 5.3 wrote per-variant item duplicates
(``items/basicdrawers_full2_jungle.json`` for storage drawers 1.12.2, nine
per-variant items for waystones). Java registers one item and keeps the
variant in block state, metadata or NBT; the per-variant names come from item
*model* files, which are not registrations.
"""
import json
from pathlib import Path

from portkit.agent.fake import FakeLLM, tool_call
from portkit.agent.items import (
    bedrock_ids,
    closest_id,
    finding,
    registered_ids,
    unknown_items,
)
from portkit.agent.loop import Message
from portkit.agent.residue import ResidueAgent, group_residue
from portkit.converters.items import bedrock_identifier
from portkit.pipeline import convert

ROOT = Path(__file__).resolve().parents[1]
AGENT_MOD = ROOT / "fixtures" / "agent_mod" / "input"
SWORD = "item:assets/examplemod/models/item/steel_sword.json"


def _item(ident: str) -> dict:
    return {
        "format_version": "1.21.40",
        "minecraft:item": {
            "description": {"identifier": ident, "menu_category": {"category": "equipment"}},
            "components": {"minecraft:icon": "examplemod:steel_sword", "minecraft:max_stack_size": 1},
        },
    }


def _write(out: Path, rel: str, ident: str) -> str:
    target = out / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(_item(ident)))
    return rel


def _converted(tmp_path, source=AGENT_MOD):
    out = tmp_path / "out"
    convert(source, out)
    return out


def _copy_agent_mod(tmp_path):
    src = tmp_path / "src"
    for path in AGENT_MOD.rglob("*"):
        if path.is_file():
            dest = src / path.relative_to(AGENT_MOD)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(path.read_bytes())
    return src


def _legacy_drawers(tmp_path):
    """A 1.12-style mod: one block, per-variant item models, a .lang file."""
    src = tmp_path / "legacy"
    ns = src / "assets" / "storagedrawers"
    (ns / "blockstates").mkdir(parents=True)
    (ns / "blockstates" / "basicdrawers.json").write_text(json.dumps({"variants": {"normal": {"model": "storagedrawers:basicdrawers"}}}))
    (ns / "models" / "item").mkdir(parents=True)
    for variant in ("full2_jungle", "full2_oak"):
        (ns / "models" / "item" / f"basicdrawers_{variant}.json").write_text(
            json.dumps({"parent": f"storagedrawers:block/basicDrawers_{variant}"})
        )
    (ns / "models" / "item" / "upgrade_template.json").write_text(json.dumps({"parent": "item/generated"}))
    (ns / "lang").mkdir()
    (ns / "lang" / "en_us.lang").write_text(
        "item.storagedrawers.upgradeTemplate.name=Upgrade Template\n"
        "tile.storagedrawers.basicDrawers.fulldrawers2.name=Basic Drawers 1x2\n"
    )
    return src


# -- what Java registers -------------------------------------------------


def test_item_models_alone_are_not_registrations(tmp_path):
    src = _legacy_drawers(tmp_path)
    ids = registered_ids(src)
    assert "storagedrawers:basicdrawers" in ids  # blockstate
    assert "storagedrawers:upgrade_template" in ids  # 1.12 .lang key, snake cased
    assert "storagedrawers:basicdrawers_full2_jungle" not in ids  # model only


def test_the_mapping_is_the_converters(tmp_path):
    """The guard maps Java ids through the converter's own function, so every
    item the deterministic path emits is a mapped id."""
    out = _converted(tmp_path)
    emitted = json.loads((out / "behavior_pack/items/bronze_ingot.json").read_text())
    ident = emitted["minecraft:item"]["description"]["identifier"]
    assert ident == bedrock_identifier("examplemod", "bronze_ingot")
    assert ident in bedrock_ids(registered_ids(AGENT_MOD), "examplemod")


# -- unit tests ----------------------------------------------------------


def test_an_invented_per_variant_item_fails(tmp_path):
    src = _legacy_drawers(tmp_path)
    out = tmp_path / "out"
    rel = _write(out, "behavior_pack/items/basicdrawers_full2_jungle.json", "storagedrawers:basicdrawers_full2_jungle")
    bad = unknown_items(out, [rel], src, "storagedrawers")
    assert [(b.path, b.ident, b.closest) for b in bad] == [
        (rel, "storagedrawers:basicdrawers_full2_jungle", "storagedrawers:basicdrawers")
    ]


def test_an_invented_item_in_the_mod_namespace_fails(tmp_path):
    out = _converted(tmp_path)
    rel = _write(out, "behavior_pack/items/steel_sword_diamond.json", "examplemod:steel_sword_diamond")
    bad = unknown_items(out, [rel], AGENT_MOD, "examplemod")
    assert [(b.ident, b.closest) for b in bad] == [("examplemod:steel_sword_diamond", "examplemod:steel_sword")]


def test_a_real_java_item_passes(tmp_path):
    out = _converted(tmp_path)
    rel = _write(out, "behavior_pack/items/steel_sword.json", "examplemod:steel_sword")
    assert unknown_items(out, [rel], AGENT_MOD, "examplemod") == []


def test_a_block_item_passes(tmp_path):
    out = _converted(tmp_path)
    rel = _write(out, "behavior_pack/items/alloy_block.json", "examplemod:alloy_block")
    assert unknown_items(out, [rel], AGENT_MOD, "examplemod") == []


def test_a_deterministically_mapped_id_passes(tmp_path):
    """The conversion namespace with a registered Java path is the converter's
    mapping under the pack's namespace."""
    out = _converted(tmp_path)
    ident = bedrock_identifier("convpack", "steel_ingot")
    rel = _write(out, "behavior_pack/items/steel_ingot_conv.json", ident)
    assert unknown_items(out, [rel], AGENT_MOD, "convpack") == []
    # ...but the conversion namespace is held to the same registered paths.
    rel = _write(out, "behavior_pack/items/made_up.json", "convpack:made_up")
    assert [b.ident for b in unknown_items(out, [rel], AGENT_MOD, "convpack")] == ["convpack:made_up"]


def test_vanilla_and_foreign_namespaces_are_out_of_scope(tmp_path):
    out = _converted(tmp_path)
    vanilla = _write(out, "behavior_pack/items/v.json", "minecraft:made_up_thing")
    foreign = _write(out, "behavior_pack/items/f.json", "sd:basicdrawers_full2_jungle")
    assert unknown_items(out, [vanilla, foreign], AGENT_MOD, "examplemod") == []


def test_an_identifier_the_file_already_had_is_not_the_sessions(tmp_path):
    out = _converted(tmp_path)
    rel = _write(out, "behavior_pack/items/old.json", "examplemod:legacy_thing")
    original = (out / rel).read_bytes()
    assert unknown_items(out, [rel], AGENT_MOD, "examplemod", {rel: original}) == []
    assert unknown_items(out, [rel], AGENT_MOD, "examplemod", {rel: None}) != []


def test_an_item_model_only_variant_in_a_modern_mod_fails(tmp_path):
    src = _copy_agent_mod(tmp_path)
    (src / "assets/examplemod/models/item/steel_sword_brushing_0.json").write_text(
        json.dumps({"parent": "item/handheld", "textures": {"layer0": "examplemod:item/steel_sword"}})
    )
    out = _converted(tmp_path, src)
    rel = _write(out, "behavior_pack/items/steel_sword_brushing_0.json", "examplemod:steel_sword_brushing_0")
    assert [b.closest for b in unknown_items(out, [rel], src, "examplemod")] == ["examplemod:steel_sword"]


def test_closest_falls_back_to_similarity():
    ids = {"examplemod:steel_ingot", "examplemod:bronze_ingot", "other:steel_ingots"}
    assert closest_id("examplemod:steal_ingot", ids) == "examplemod:steel_ingot"


def test_finding_names_the_rule_and_the_closest_id(tmp_path):
    src = _legacy_drawers(tmp_path)
    out = tmp_path / "out"
    rel = _write(out, "behavior_pack/items/basicdrawers_full2_jungle.json", "storagedrawers:basicdrawers_full2_jungle")
    found = finding(unknown_items(out, [rel], src, "storagedrawers")[0])
    assert found["rule"] == "agent.unknown_item"
    assert found["severity"] == "error"
    assert found["path"] == rel
    assert "storagedrawers:basicdrawers_full2_jungle" in found["message"]
    assert "'storagedrawers:basicdrawers'" in found["message"]


# -- end-to-end ----------------------------------------------------------


def _script(tmp_path, sword_steps):
    probe = convert(AGENT_MOD, tmp_path / "probe")
    script = []
    for group in group_residue(probe.unhandled):
        script += sword_steps if group.key == SWORD else [Message("assistant", "No Bedrock form.")]
    return script


def _run(tmp_path, script, client=None):
    result = convert(AGENT_MOD, tmp_path / "out", agent=ResidueAgent(client or FakeLLM(script)))
    return result, {o.key: o for o in result.agent.outcomes}


def test_an_invented_item_rolls_the_group_back(tmp_path):
    rel = "behavior_pack/items/steel_sword_diamond.json"
    script = _script(tmp_path, [
        tool_call("write_output", path=rel, content=_item("examplemod:steel_sword_diamond")),
        tool_call("validate"),
        Message("assistant", "Wrote the sword variant."),
    ])
    client = FakeLLM(list(script))
    result, by_key = _run(tmp_path, script, client)
    sword = by_key[SWORD]
    assert sword.status == "rolled_back", sword.note
    assert sword.written == []
    assert not (tmp_path / "out" / rel).exists()
    assert sword.unknown_items and "examplemod:steel_sword_diamond" in sword.unknown_items[0]
    assert "item(s) the Java source does not register" in sword.note
    assert sword.to_dict()["unknown_items"] == sword.unknown_items
    assert result.report.ok

    tool_reply = next(
        m for request in client.seen for m in request
        if m.role == "tool" and m.tool_call_id == "call_validate"
    )
    seen = json.loads(tool_reply.content)
    assert any(f["rule"] == "agent.unknown_item" for f in seen["findings"])


def test_the_real_item_written_by_the_agent_is_not_flagged(tmp_path):
    rel = "behavior_pack/items/steel_sword.json"
    script = _script(tmp_path, [
        tool_call("write_output", path=rel, content=_item("examplemod:steel_sword")),
        tool_call("validate"),
        Message("assistant", "Wrote the sword."),
    ])
    _, by_key = _run(tmp_path, script)
    assert by_key[SWORD].unknown_items == []
