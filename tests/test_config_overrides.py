"""User config overrides: ``portkit convert --config <mod>.<flag>=<true|false>``.

Java has the mod's config file; Bedrock doesn't, so the choice happens at
conversion time. A setting replaces the flag's cited default wherever a load
condition or a gated registration reads it, both ways, and the run records
what it set (docs/decisions.md, 2026-10-13: config overrides).
"""
import json
import re
from pathlib import Path

import pytest

from portkit import cli, conditions, corpus, pipeline, report
from portkit.conditions import (ConfigError, ConfigRequest, LoadContext, known_flags,
                                load_config_file, parse_config_arg, resolve_config)
from portkit.converters import items, recipes
from portkit.model import SourceMod

SHAPED = {
    "type": "minecraft:crafting_shaped",
    "pattern": ["##"],
    "key": {"#": {"item": "minecraft:stick"}},
    "result": {"item": "minecraft:ladder"},
}

# A flag table of our own, so the tests don't move with the shipped one.
TABLE = {"entries": [
    {"mod": "examplemod", "version": "1.2.3", "condition": "examplemod:flag", "argument": "flag",
     "flags": {"on_thing": {"default": True, "config_key": "enableOnThing",
                            "url": "https://example.invalid/Config.java#L1"},
               "off_thing": {"default": False, "url": "https://example.invalid/Config.java#L2"},
               "glass_a": {"default": True, "config_key": "glassFix", "url": "https://example.invalid/C#L3"},
               "glass_b": {"default": True, "config_key": "glassFix", "url": "https://example.invalid/C#L3"}}},
    {"mod": "examplemod", "version": "1.2.3", "condition": "examplemod:dust_enabled", "argument": None,
     "flags": {"": {"default": False, "config_key": "enableDusts",
                    "url": "https://example.invalid/Config.java#L4"}},
     "registers": {"items": ["examplemod:*_dust"]}},
]}


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body if isinstance(body, str) else json.dumps(body))


def _mod(tmp_path, files: dict) -> SourceMod:
    root = tmp_path / "mod"
    for rel, body in files.items():
        _write(root, rel, body)
    return SourceMod(root=root, namespace="examplemod", loader="forge", minecraft="1.20.1",
                     mods={"examplemod": "1.2.3"}, requires=frozenset())


def _gated(cond) -> dict:
    return {**SHAPED, "conditions": [cond]}


DUST = {"type": "examplemod:dust_enabled"}
OFF = {"type": "examplemod:flag", "flag": "off_thing"}
ON = {"type": "examplemod:flag", "flag": "on_thing"}


def _recipes(mod, overrides=None):
    context = LoadContext(mod, table=TABLE, overrides=overrides)
    return recipes.convert(mod, context=context), context


def _resolve(mod, *texts):
    known = known_flags(mod.root, mod.mods, [mod.namespace], table=TABLE)
    return resolve_config([parse_config_arg(t) for t in texts], known)


# -- parsing ---------------------------------------------------------------------

def test_parse_config_arg():
    assert parse_config_arg("mythicmetals.enableDusts=true") == ConfigRequest(
        "mythicmetals", "enableDusts", True, "--config")
    assert parse_config_arg(" tconstruct.glass_recipe_fix = OFF ").value is False
    # Only the first dot splits: the rest belongs to the flag.
    assert parse_config_arg("supplementaries.tools.altimeter=0").name == "tools.altimeter"
    for bad in ("mythicmetals.enableDusts", "enableDusts=true", ".x=true", "mm.=true", "mm.x=maybe"):
        with pytest.raises(ConfigError):
            parse_config_arg(bad)


def test_cli_parses_repeatable_config_and_file():
    ns = _parse(["convert", "jar", "out", "--config", "a.b=true", "--config", "a.c=false",
                 "--config-file", "cfg.toml"])
    assert ns.config == ["a.b=true", "a.c=false"] and ns.config_file == "cfg.toml"
    assert _parse(["convert", "jar", "out"]).config is None


def _parse(argv):
    captured = {}

    def grab(args):
        captured["args"] = args
        return 0

    import portkit.cli as module
    original = module._convert_once
    module._convert_once = lambda args: (grab(args), None)
    try:
        module.main(argv)
    finally:
        module._convert_once = original
    return captured["args"]


def test_config_file_json_and_toml_nested_and_flat(tmp_path):
    js = tmp_path / "c.json"
    js.write_text(json.dumps({"examplemod": {"enableDusts": True}, "examplemod.off_thing": "on",
                              "_settings": [{"ignored": True}]}))
    assert [(r.mod, r.name, r.value) for r in load_config_file(js)] == [
        ("examplemod", "enableDusts", True), ("examplemod", "off_thing", True)]
    tm = tmp_path / "c.toml"
    tm.write_text('"examplemod.on_thing" = false\n[examplemod]\nenableDusts = true\n')
    assert {(r.name, r.value) for r in load_config_file(tm)} == {("on_thing", False), ("enableDusts", True)}
    assert all(r.origin == str(tm) for r in load_config_file(tm))
    bad = tmp_path / "bad.json"
    for body in ("[1]", '{"examplemod": {"x": 3}}', "{nope", '{"a.b": {"c": true}}', '{"nodot": true}'):
        bad.write_text(body)
        with pytest.raises(ConfigError):
            load_config_file(bad)
    with pytest.raises(ConfigError):
        load_config_file(tmp_path / "missing.json")


# -- resolving names -------------------------------------------------------------

def test_canonical_names_and_config_key_aliases_resolve(tmp_path):
    mod = _mod(tmp_path, {})
    overrides, records = _resolve(mod, "examplemod.dust_enabled=true", "examplemod.enableOnThing=false",
                                  "examplemod.off_thing=true")
    assert overrides == {("examplemod:dust_enabled", ""): True, ("examplemod:flag", "on_thing"): False,
                         ("examplemod:flag", "off_thing"): True}
    dust = next(r for r in records if r["flag"] == "dust_enabled")
    assert dust["cited_default"] is False and dust["condition"] == "examplemod:dust_enabled"
    assert _resolve(mod, "examplemod.enableDusts=true")[0] == {("examplemod:dust_enabled", ""): True}
    # Case-insensitive fallback, and one config key standing for two flags.
    assert _resolve(mod, "examplemod.ENABLEDUSTS=true")[0] == {("examplemod:dust_enabled", ""): True}
    assert _resolve(mod, "examplemod.glassFix=false")[0] == {("examplemod:flag", "glass_a"): False,
                                                            ("examplemod:flag", "glass_b"): False}


def test_later_settings_win(tmp_path):
    mod = _mod(tmp_path, {})
    assert _resolve(mod, "examplemod.enableDusts=true", "examplemod.dust_enabled=false")[0] == {
        ("examplemod:dust_enabled", ""): False}


def test_unknown_flag_and_unknown_mod_are_errors_listing_the_valid_ones(tmp_path):
    mod = _mod(tmp_path, {})
    with pytest.raises(ConfigError) as err:
        _resolve(mod, "examplemod.enableDust=true")
    message = str(err.value)
    assert "unknown config flag" in message
    assert "dust_enabled (enableDusts)" in message and "on_thing (enableOnThing)" in message
    assert "off_thing" in message
    with pytest.raises(ConfigError) as err:
        _resolve(mod, "quark.anything=true")
    assert "no config flags are known for mod 'quark'" in str(err.value)
    assert "examplemod" in str(err.value)


def test_uncited_flags_the_jar_uses_can_be_set(tmp_path):
    mod = _mod(tmp_path, {
        "data/examplemod/recipes/a.json": _gated({"type": "othermod:feature", "name": "secret"}),
        "data/examplemod/recipes/b.json": {**SHAPED, "conditions": [
            {"type": "forge:not", "value": {"type": "examplemod:bare"}}]},
    })
    known = {(k.condition, k.flag): k for k in known_flags(mod.root, mod.mods, ["examplemod"], table=TABLE)}
    assert ("othermod:feature", "secret") in known and known[("othermod:feature", "secret")].default is None
    assert ("examplemod:bare", "") in known
    overrides, records = _resolve(mod, "othermod.secret=true", "examplemod.bare=false")
    assert overrides == {("othermod:feature", "secret"): True, ("examplemod:bare", ""): False}
    assert all(r["cited_default"] is None for r in records)
    result, _ = _recipes(mod, overrides)
    assert {"recipes/a.json", "recipes/b.json"} <= set(result.files)


# -- the override decides load conditions ---------------------------------------

def test_override_on_converts_a_default_off_recipe(tmp_path):
    mod = _mod(tmp_path, {"data/examplemod/recipes/dust.json": _gated(DUST),
                          "data/examplemod/recipes/off.json": _gated(OFF)})
    default, _ = _recipes(mod)
    assert not default.files
    assert {u.reason for u in default.unhandled} == {
        "disabled by default config: examplemod:dust_enabled",
        "disabled by default config: examplemod:flag/off_thing"}
    on, context = _recipes(mod, {("examplemod:dust_enabled", ""): True, ("examplemod:flag", "off_thing"): True})
    assert set(on.files) == {"recipes/dust.json", "recipes/off.json"}
    assert not on.unhandled
    assert context.note() is None  # nothing was assumed at a default
    assert context.user_note().endswith("examplemod:dust_enabled=on, examplemod:flag/off_thing=on")


def test_override_off_sends_a_default_on_recipe_and_loot_table_to_residue(tmp_path):
    mod = _mod(tmp_path, {
        "data/examplemod/recipes/on.json": _gated(ON),
        "data/examplemod/recipes/negated.json": {**SHAPED, "result": {"item": "minecraft:chest"},
                                                 "conditions": [{"type": "forge:not", "value": ON}]},
        "data/examplemod/loot_tables/blocks/thing.json": {
            "type": "minecraft:block", "neoforge:conditions": [ON],
            "pools": [{"rolls": 1, "entries": [{"type": "minecraft:item", "name": "minecraft:stone"}]}]},
    })
    mod.loader = "neoforge"
    default, _ = _recipes(mod)
    assert set(default.files) == {"recipes/on.json"}
    off = {("examplemod:flag", "on_thing"): False}
    result, context = _recipes(mod, off)
    assert set(result.files) == {"recipes/negated.json"}
    [reason] = [u.reason for u in result.unhandled if u.kind == "conditional_recipe"]
    assert reason == "disabled by user config: examplemod:flag/on_thing"
    from portkit.converters import loot
    tables = loot.convert(mod, context=LoadContext(mod, table=TABLE, overrides=off))
    assert [u.reason for u in tables.unhandled] == ["disabled by user config: examplemod:flag/on_thing"]
    assert "examplemod:flag/on_thing=off" in context.user_note()


def test_default_run_is_unchanged_without_overrides(tmp_path):
    mod = _mod(tmp_path, {"data/examplemod/recipes/on.json": _gated(ON)})
    a, ca = _recipes(mod)
    b, cb = _recipes(mod, {})
    assert a.files == b.files and ca.note() == cb.note() and cb.user_note() is None


# -- gated registrations ---------------------------------------------------------

def _item_model(texture="examplemod:item/x"):
    return {"parent": "minecraft:item/generated", "textures": {"layer0": texture}}


def test_items_registered_only_under_a_flag_follow_it(tmp_path):
    files = {
        "assets/examplemod/models/item/tin_dust.json": _item_model("examplemod:item/tin_dust"),
        "assets/examplemod/models/item/tin_ingot.json": _item_model("examplemod:item/tin_ingot"),
        "assets/examplemod/textures/item/tin_dust.png": "",
        "assets/examplemod/textures/item/tin_ingot.png": "",
        "assets/examplemod/lang/en_us.json": {"item.examplemod.tin_dust": "Tin Dust",
                                              "item.examplemod.tin_ingot": "Tin Ingot"},
    }
    mod = _mod(tmp_path, files)
    default = items.convert(mod, context=LoadContext(mod, table=TABLE))
    assert set(default.files) == {"items/tin_ingot.json"}
    [gated] = [u for u in default.unhandled if u.kind == "conditional_item"]
    assert gated.source.endswith("models/item/tin_dust.json")
    assert gated.reason == "disabled by default config: examplemod:dust_enabled"
    on = items.convert(mod, context=LoadContext(mod, table=TABLE,
                                                overrides={("examplemod:dust_enabled", ""): True}))
    assert set(on.files) == {"items/tin_dust.json", "items/tin_ingot.json"}
    assert not [u for u in on.unhandled if u.kind == "conditional_item"]


def test_gating_needs_the_cited_version(tmp_path):
    mod = _mod(tmp_path, {})
    mod.mods = {"examplemod": "9.9.9"}
    assert LoadContext(mod, table=TABLE).gated_item("examplemod:tin_dust") is None
    mod.mods = {"examplemod": "1.2.3"}
    assert LoadContext(mod, table=TABLE).gated_item("examplemod:tin_ingot") is None
    assert LoadContext(mod, table=TABLE).gated_item("examplemod:tin_dust").passes is False


def test_agent_skips_conditional_items():
    from portkit.agent.residue import SKIP_KINDS
    assert "conditional_item" in SKIP_KINDS


# -- the pipeline records what it set -------------------------------------------

def _source(tmp_path) -> Path:
    src = tmp_path / "src"
    _write(src, "META-INF/mods.toml", '[[mods]]\nmodId="mythicmetals"\nversion="0.24.6+1.21"\n')
    _write(src, "data/mythicmetals/recipes/from_dust.json",
           {**SHAPED, "conditions": [{"type": "mythicmetals:dust_enabled"}]})
    _write(src, "data/mythicmetals/recipes/plain.json", {**SHAPED, "result": {"item": "minecraft:chest"}})
    return src


def test_pipeline_records_overrides_in_notes_summary_file_and_report(tmp_path):
    src = _source(tmp_path)
    run = pipeline.convert(src, tmp_path / "out", emit_addon=False,
                           config=[ConfigRequest("mythicmetals", "enableDusts", True, "--config")])
    assert (run.tree / "behavior_pack" / "recipes" / "from_dust.json").exists()
    summary = run.summary()
    assert summary["config"] == {"mythicmetals": {"dust_enabled": True}}
    assert any(n.startswith("converted with mod config set by user config") and
               "mythicmetals:dust_enabled=on (default off via mythicmetals.enableDusts)" in n
               for n in summary["notes"])
    record = json.loads((tmp_path / "out" / pipeline.CONFIG_RECORD).read_text())
    assert record["mythicmetals"] == {"dust_enabled": True}
    assert record["_settings"][0]["cited_default"] is False
    assert "MythicConfigModel.java#L63" in record["_settings"][0]["default_source"]
    text = report.render(run.tree)
    assert "## Mod config set by user config" in text
    assert "| `mythicmetals:dust_enabled` | on | off | `mythicmetals.enableDusts` |" in text
    # The record reads back as a --config-file and reproduces the run.
    again = pipeline.convert(src, tmp_path / "again", emit_addon=False,
                             config=load_config_file(tmp_path / "out" / pipeline.CONFIG_RECORD))
    assert again.summary()["config"] == summary["config"]
    assert sorted(p.name for p in (again.tree / "behavior_pack" / "recipes").iterdir()) == \
        sorted(p.name for p in (run.tree / "behavior_pack" / "recipes").iterdir())


def test_pipeline_without_overrides_writes_no_record(tmp_path):
    src = _source(tmp_path)
    pipeline.convert(src, tmp_path / "out", emit_addon=False,
                     config=[ConfigRequest("mythicmetals", "dust_enabled", True, "--config")])
    assert (tmp_path / "out" / pipeline.CONFIG_RECORD).exists()
    # A later default run into the same folder doesn't keep the stale record.
    pipeline.convert(src, tmp_path / "out", emit_addon=False)
    assert not (tmp_path / "out" / pipeline.CONFIG_RECORD).exists()
    run = pipeline.convert(src, tmp_path / "fresh", emit_addon=False)
    assert "config" not in run.summary()
    assert not (run.tree / "behavior_pack" / "recipes" / "from_dust.json").exists()
    assert "Mod config set by user config" not in report.render(run.tree)


def test_cli_unknown_flag_exits_2_before_writing(tmp_path, capsys):
    code = cli.main(["convert", str(_source(tmp_path)), str(tmp_path / "out"), "--no-addon",
                     "--config", "mythicmetals.enableDust=true"])
    assert code == 2
    err = capsys.readouterr().err
    assert "unknown config flag" in err and "dust_enabled (enableDusts)" in err
    assert not (tmp_path / "out").exists()


def test_cli_config_file_then_flag(tmp_path, capsys):
    cfg = tmp_path / "cfg.toml"
    cfg.write_text("[mythicmetals]\nenableDusts = false\n")
    code = cli.main(["convert", str(_source(tmp_path)), str(tmp_path / "out"), "--no-addon",
                     "--config-file", str(cfg), "--config", "mythicmetals.dust_enabled=true"])
    assert code == 0
    summary = json.loads(capsys.readouterr().out.split("\n}\n")[0] + "\n}")
    assert summary["config"] == {"mythicmetals": {"dust_enabled": True}}
    assert (tmp_path / "out" / "behavior_pack" / "recipes" / "from_dust.json").exists()


# -- the shipped data ------------------------------------------------------------

def test_shipped_aliases_and_registrations_are_cited():
    by = {(e["mod"], e["version"], e["condition"]): e for e in conditions.flag_entries()}
    mm = "0.24.6+1.21"
    assert by[("mythicmetals", mm, "mythicmetals:dust_enabled")]["flags"][""]["config_key"] == "enableDusts"
    assert by[("mythicmetals", mm, "mythicmetals:nuggets_enabled")]["flags"][""]["config_key"] == "enableNuggets"
    tinkers = by[("tconstruct", "3.12.1.231", "tconstruct:config")]["flags"]
    assert tinkers["force_integration_materials"]["config_key"] == "forceIntegrationMaterials"
    assert tinkers["slime_recipe_fix"]["config_key"] == tinkers["glass_recipe_fix"]["config_key"] == "glassRecipeFix"
    for entry in conditions.flag_entries():
        registers = entry.get("registers")
        if registers:
            assert registers["items"] and registers["why"]
            for source in registers["sources"]:
                assert entry["commit"] in source["url"] and re.search(r"#L\d+$", source["url"])
    assert by[("mythicmetals", mm, "mythicmetals:dust_enabled")]["registers"]["items"] == ["mythicmetals:*_dust"]


# -- the corpus ------------------------------------------------------------------

@pytest.mark.realmods
def test_mythic_metals_with_dusts_enabled(tmp_path):
    mod = next(m for m in corpus.load() if m.name == "mythicmetals")
    jar = corpus.cached(mod)
    if jar is None:
        pytest.skip("mythicmetals not cached (portkit corpus fetch)")
    default = pipeline.convert(jar, tmp_path / "default", emit_addon=False)
    dusts = pipeline.convert(jar, tmp_path / "dusts", emit_addon=False,
                             config=[ConfigRequest("mythicmetals", "enableDusts", True, "--config")])

    def recipes_of(run):
        return {p.name for p in (run.tree / "behavior_pack" / "recipes").iterdir()}

    def dust_items(run):
        return {p.name for p in (run.tree / "behavior_pack" / "items").iterdir() if p.stem.endswith("_dust")}

    added = recipes_of(dusts) - recipes_of(default)
    assert len(added) == 37 and all("from_dust" in name for name in added)
    assert recipes_of(default) <= recipes_of(dusts)
    # Java registers the 27 *_dust items only with enableDusts on.
    assert dust_items(default) == set()
    assert len(dust_items(dusts)) == 27
    gated = [u for u in default.unhandled if u.kind == "conditional_item"]
    assert len(gated) == 27 and {u.reason for u in gated} == {
        "disabled by default config: mythicmetals:dust_enabled"}
    assert not [u for u in dusts.unhandled if u.kind == "conditional_item"]
    assert not [u for u in dusts.unhandled if "dust_enabled" in u.reason]
    assert dusts.report.ok and default.report.ok
    assert dusts.file_count == default.file_count + 37 + 27
    from portkit.validate import mct
    if mct.find_mct():
        assert mct.run(dusts.tree).by_severity.get("error", 0) == 0
