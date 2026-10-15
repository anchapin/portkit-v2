"""The residue agent is held to the conversion's mod config (#187).

Since #186 the item converter leaves out items the mod's code registers only
while a config flag is on (Mythic Metals' ``*_dust`` under ``enableDusts``,
default off), deciding each flag at its cited default or the user's
``--config``. The agent's guards ask the same :class:`LoadContext`, so the
agent can neither define such an item nor name it while the flag is off, and
can do both once ``--config mythicmetals.enableDusts=true`` turns it on.
"""
import json
from pathlib import Path

from portkit import pipeline
from portkit.agent.fake import FakeLLM, tool_call
from portkit.agent.items import (
    finding,
    gated_finding,
    gated_ids,
    gated_refs,
    registered_ids,
    unknown_items,
)
from portkit.agent.loop import Message
from portkit.agent.residue import ResidueAgent, _TrackingToolBox, group_residue
from portkit.conditions import ConfigRequest, LoadContext
from portkit.meta import parse as parse_metadata
from portkit.model import SourceMod

DUST_ON = {("mythicmetals:dust_enabled", ""): True}
FLAG = "mythicmetals:dust_enabled"
ENABLE = "--config mythicmetals.enableDusts=true"


def _write(root: Path, rel: str, body) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body if isinstance(body, str) else json.dumps(body))


def _source(tmp_path) -> Path:
    """A Mythic Metals 0.24.6+1.21 stand-in: the cited enableDusts gate applies to it."""
    src = tmp_path / "src"
    _write(src, "META-INF/mods.toml", '[[mods]]\nmodId="mythicmetals"\nversion="0.24.6+1.21"\n')
    for name in ("tin_dust", "tin_ingot"):
        _write(src, f"assets/mythicmetals/models/item/{name}.json",
               {"parent": "item/generated", "textures": {"layer0": f"mythicmetals:item/{name}"}})
        _write(src, f"assets/mythicmetals/textures/item/{name}.png", "")
    # Residue for the agent: a 3D item model, which the converter refuses.
    _write(src, "assets/mythicmetals/models/item/odd.json",
           {"textures": {"0": "mythicmetals:item/tin_ingot"},
            "elements": [{"from": [0, 0, 0], "to": [16, 16, 16], "faces": {}}]})
    _write(src, "assets/mythicmetals/lang/en_us.json",
           {"item.mythicmetals.tin_dust": "Tin Dust", "item.mythicmetals.tin_ingot": "Tin Ingot",
            "item.mythicmetals.odd": "Odd"})
    return src


def _context(src: Path, overrides=None) -> LoadContext:
    meta = parse_metadata({"META-INF/mods.toml": (src / "META-INF" / "mods.toml").read_bytes()},
                          "mythicmetals")
    return LoadContext(SourceMod.from_metadata(src, "mythicmetals", meta), overrides=overrides)


def _item(ident: str) -> dict:
    return {"format_version": "1.21.40",
            "minecraft:item": {"description": {"identifier": ident}, "components": {}}}


def _recipe(result: str) -> dict:
    return {"format_version": "1.20.10", "minecraft:recipe_shapeless": {
        "description": {"identifier": "mythicmetals:test"}, "tags": ["crafting_table"],
        "ingredients": [{"item": "minecraft:stick"}], "result": {"item": result}}}


def _gated(src: Path, overrides=None) -> dict:
    return gated_ids(registered_ids(src), _context(src, overrides).gated_item, "mythicmetals")


# -- the guard ---------------------------------------------------------------

def test_the_effective_config_comes_from_the_shared_context(tmp_path):
    src = _source(tmp_path)
    context = _context(src)
    assert context.mod.mods == {"mythicmetals": "0.24.6+1.21"}
    verdict = context.gated_item("mythicmetals:tin_dust")
    assert verdict.passes is False and verdict.gate == FLAG
    assert verdict.enable == "mythicmetals.enableDusts=true"
    assert context.gated_item("mythicmetals:tin_ingot") is None


def test_a_gated_item_is_rejected_by_default_and_names_the_flag(tmp_path):
    src, out = _source(tmp_path), tmp_path / "out"
    _write(out, "behavior_pack/items/tin_dust.json", _item("mythicmetals:tin_dust"))
    bad = unknown_items(out, ["behavior_pack/items/tin_dust.json"], src, "mythicmetals",
                        gated=_gated(src))
    assert [b.ident for b in bad] == ["mythicmetals:tin_dust"]
    assert bad[0].gated is not None and bad[0].gated.java == "mythicmetals:tin_dust"
    found = finding(bad[0])
    assert found["rule"] == "agent.unknown_item"
    assert f"item gated off by config flag {FLAG}" in found["message"]
    assert "disabled by default config" in found["message"]
    assert ENABLE in found["message"]
    assert ENABLE in bad[0].describe()


def test_the_override_allows_it(tmp_path):
    src, out = _source(tmp_path), tmp_path / "out"
    _write(out, "behavior_pack/items/tin_dust.json", _item("mythicmetals:tin_dust"))
    assert _gated(src, DUST_ON) == {}
    assert unknown_items(out, ["behavior_pack/items/tin_dust.json"], src, "mythicmetals",
                         gated=_gated(src, DUST_ON)) == []


def test_a_same_path_id_in_another_namespace_does_not_ungate_it(tmp_path):
    src, out = _source(tmp_path), tmp_path / "out"
    # A recipe naming c:tin_dust makes it a "registered" id whose path maps
    # under the conversion namespace to mythicmetals:tin_dust.
    _write(src, "data/mythicmetals/recipes/x.json",
           {"type": "minecraft:crafting_shapeless", "ingredients": [{"item": "c:tin_dust"}],
            "result": {"item": "minecraft:stick"}})
    _write(out, "behavior_pack/items/tin_dust.json", _item("mythicmetals:tin_dust"))
    bad = unknown_items(out, ["behavior_pack/items/tin_dust.json"], src, "mythicmetals",
                        gated=_gated(src))
    assert [b.ident for b in bad] == ["mythicmetals:tin_dust"] and bad[0].gated is not None


def test_a_user_off_setting_says_so(tmp_path):
    src = _source(tmp_path)
    gated = _gated(src, {("mythicmetals:dust_enabled", ""): False})
    assert gated["mythicmetals:tin_dust"].reason == f"disabled by user config: {FLAG}"


def test_ungated_items_are_unaffected(tmp_path):
    src, out = _source(tmp_path), tmp_path / "out"
    _write(out, "behavior_pack/items/tin_ingot.json", _item("mythicmetals:tin_ingot"))
    _write(out, "behavior_pack/items/tin_plate.json", _item("mythicmetals:tin_plate"))
    bad = unknown_items(out, ["behavior_pack/items/tin_ingot.json", "behavior_pack/items/tin_plate.json"],
                        src, "mythicmetals", gated=_gated(src))
    assert [(b.ident, b.gated) for b in bad] == [("mythicmetals:tin_plate", None)]
    assert "gated" not in finding(bad[0])["message"]


def test_a_mod_without_cited_gates_gates_nothing(tmp_path):
    src = tmp_path / "src"
    _write(src, "META-INF/mods.toml", '[[mods]]\nmodId="mythicmetals"\nversion="9.9.9"\n')
    _write(src, "assets/mythicmetals/lang/en_us.json", {"item.mythicmetals.tin_dust": "Tin Dust"})
    assert _gated(src) == {}


def test_references_to_a_gated_item_are_rejected(tmp_path):
    src, out = _source(tmp_path), tmp_path / "out"
    rel = "behavior_pack/recipes/test.json"
    _write(out, rel, _recipe("mythicmetals:tin_dust"))
    gated = _gated(src)
    refs = gated_refs(out, [rel], gated)
    assert [(r.ident, r.where) for r in refs] == [
        ("mythicmetals:tin_dust", "minecraft:recipe_shapeless.result.item")]
    message = gated_finding(refs[0], gated)
    assert message["rule"] == "agent.gated_item" and FLAG in message["message"] and ENABLE in message["message"]
    # ... allowed with the override, and not the session's if the file already held it.
    assert gated_refs(out, [rel], _gated(src, DUST_ON)) == []
    assert gated_refs(out, [rel], gated, {rel: json.dumps(_recipe("mythicmetals:tin_dust")).encode()}) == []
    # A lang key counts too.
    _write(out, "resource_pack/texts/en_US.lang", "item.mythicmetals:tin_dust.name=Tin Dust\n")
    assert [r.ident for r in gated_refs(out, ["resource_pack/texts/en_US.lang"], gated)] == [
        "mythicmetals:tin_dust"]


def test_the_toolbox_reports_both_rules_once(tmp_path):
    src, out = _source(tmp_path), tmp_path / "out"
    box = _TrackingToolBox(src, out, "mythicmetals", _context(src))
    box.write_output("behavior_pack/items/tin_dust.json", json.dumps(_item("mythicmetals:tin_dust")))
    box.write_output("behavior_pack/recipes/test.json", json.dumps(_recipe("mythicmetals:tin_dust")))
    rules = sorted((f["path"], f["rule"]) for f in box.validate()["findings"]
                   if f["rule"].startswith("agent."))
    assert rules == [("behavior_pack/items/tin_dust.json", "agent.unknown_item"),
                     ("behavior_pack/recipes/test.json", "agent.gated_item")]
    # Without a context (a bare toolbox), gating is not checked.
    plain = _TrackingToolBox(src, out, "mythicmetals")
    assert plain.gated() == {}


# -- end-to-end through the pipeline --------------------------------------------

def _run(tmp_path, steps, config=None, name="out"):
    src = _source(tmp_path)
    probe = pipeline.convert(src, tmp_path / f"probe_{name}", emit_addon=False, config=config)
    script = []
    for group in group_residue(probe.unhandled):
        script += steps if group.key.endswith("models/item/odd.json") else [Message("assistant", "No Bedrock form.")]
    result = pipeline.convert(src, tmp_path / name, emit_addon=False, config=config,
                              agent=ResidueAgent(FakeLLM(script)))
    by_key = {o.key: o for o in result.agent.outcomes}
    return result, next(o for k, o in by_key.items() if k.endswith("models/item/odd.json"))


def _steps(*writes):
    return [*(tool_call("write_output", path=p, content=c) for p, c in writes),
            tool_call("validate"), Message("assistant", "Done.")]


def test_pipeline_default_rolls_back_a_gated_item_and_a_recipe_naming_it(tmp_path):
    result, odd = _run(tmp_path, _steps(
        ("behavior_pack/items/tin_dust.json", _item("mythicmetals:tin_dust")),
        ("behavior_pack/recipes/odd.json", _recipe("mythicmetals:tin_dust")),
    ))
    assert not (result.tree / "behavior_pack" / "items" / "tin_dust.json").exists()
    assert odd.status == "rolled_back", odd.note
    assert odd.unknown_items and ENABLE in odd.unknown_items[0]
    assert odd.gated_items and "recipes/odd.json" in odd.gated_items[0] and ENABLE in odd.gated_items[0]
    assert "item(s) gated off by mod config" in odd.note
    assert odd.to_dict()["gated_items"] == odd.gated_items


def test_pipeline_with_the_override_allows_them(tmp_path):
    config = [ConfigRequest("mythicmetals", "enableDusts", True, "--config")]
    result, odd = _run(tmp_path, _steps(
        ("behavior_pack/recipes/odd.json", _recipe("mythicmetals:tin_dust")),
    ), config=config)
    # The converter itself ships the dust item with the flag on, and the agent may use it.
    assert (result.tree / "behavior_pack" / "items" / "tin_dust.json").exists()
    assert odd.gated_items == [] and odd.unknown_items == []
    assert odd.status == "resolved", odd.note


def test_pipeline_ungated_regression(tmp_path):
    _, odd = _run(tmp_path, _steps(
        ("behavior_pack/recipes/odd.json", _recipe("mythicmetals:tin_ingot")),
    ))
    assert odd.status == "resolved", odd.note
    assert odd.gated_items == []
