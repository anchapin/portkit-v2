"""Non-boolean mod config values: ``portkit convert --config <mod>.<option>=<number>`` (#190).

A config option that isn't a load condition but a number a converter reads,
such as Farmer's Delight's ``cuttingBoardFortuneBonus``, is cited (type,
default, the range the mod's config accepts) in the ``values`` list of
``portkit/data/config_flag_defaults.json``. The user's setting replaces the
default; a number outside the range is an error, never clamped or reset
(docs/decisions.md, 2026-10-15).
"""
import json
import re

import pytest

from portkit import conditions, pipeline, report
from portkit.conditions import (VALUE_KEY, ConfigError, ConfigRequest, LoadContext, config_note,
                                known_flags, known_values, load_config_file, parse_config_arg,
                                resolve_config)
from portkit.adapters.farmersdelight import cutting_board as stations
from portkit.model import SourceMod

from test_stations import DATA, _fd_mod, _table, reference  # noqa: F401  (fixture)

TABLE = {
    "entries": [
        {"mod": "examplemod", "version": "1.2.3", "condition": "examplemod:flag", "argument": "flag",
         "flags": {"on_thing": {"default": True, "url": "https://example.invalid/C#L1"}}},
    ],
    "values": [
        {"mod": "examplemod", "version": "1.2.3",
         "options": {"bonus": {"type": "double", "default": 0.1, "min": 0.0, "max": 1.0,
                               "url": "https://example.invalid/C#L9"}}},
    ],
}
KEY = (VALUE_KEY, "examplemod.bonus")
FORTUNE = (VALUE_KEY, "farmersdelight.cuttingBoardFortuneBonus")


def _mod(tmp_path, version="1.2.3") -> SourceMod:
    root = tmp_path / "mod"
    root.mkdir(exist_ok=True)
    return SourceMod(root=root, namespace="examplemod", loader="forge", minecraft="1.20.1",
                     mods={"examplemod": version}, requires=frozenset())


def _resolve(mod, *texts):
    known = known_flags(mod.root, mod.mods, [mod.namespace], table=TABLE)
    values = known_values(mod.mods, [mod.namespace], table=TABLE)
    return resolve_config([parse_config_arg(t) for t in texts], known, values)


# -- parsing ---------------------------------------------------------------------

def test_a_number_parses_and_the_written_text_is_kept():
    req = parse_config_arg("farmersdelight.cuttingBoardFortuneBonus=0.25")
    assert req.value == 0.25 and req.written == "0.25"
    # "1" spells true for a flag; the written text lets a value option read it as 1.
    one = parse_config_arg("examplemod.bonus=1")
    assert one.value is True and one.written == "1"
    assert parse_config_arg("examplemod.bonus= .5 ").value == 0.5
    for bad in ("examplemod.bonus=lots", "examplemod.bonus=nan", "examplemod.bonus=inf", "examplemod.bonus="):
        with pytest.raises(ConfigError):
            parse_config_arg(bad)


def test_config_file_numbers(tmp_path):
    js = tmp_path / "c.json"
    js.write_text(json.dumps({"examplemod": {"bonus": 0}, "examplemod.on_thing": True}))
    got = {(r.name, r.value) for r in load_config_file(js)}
    assert got == {("bonus", 0.0), ("on_thing", True)}
    tm = tmp_path / "c.toml"
    tm.write_text("[examplemod]\nbonus = 0.3\n")
    assert [(r.name, r.value) for r in load_config_file(tm)] == [("bonus", 0.3)]


# -- resolving -------------------------------------------------------------------

def test_value_setting_resolves_with_its_cited_default(tmp_path):
    mod = _mod(tmp_path)
    overrides, records = _resolve(mod, "examplemod.bonus=0.25")
    assert overrides == {KEY: 0.25}
    assert records == [{
        "mod": "examplemod", "flag": "bonus", "condition": None, "value": 0.25,
        "as_written": "examplemod.bonus", "config_key": "bonus", "cited_default": 0.1,
        "default_source": "https://example.invalid/C#L9", "origin": "--config", "range": [0.0, 1.0]}]
    # =1 and =0 are numbers here, not true/false; names fold case like flags do.
    assert _resolve(mod, "examplemod.bonus=1")[0] == {KEY: 1.0}
    assert _resolve(mod, "examplemod.BONUS=0")[0] == {KEY: 0.0}
    # Flags and values mix; the later setting of one option wins.
    overrides, _ = _resolve(mod, "examplemod.bonus=0.2", "examplemod.on_thing=false", "examplemod.bonus=0.4")
    assert overrides == {KEY: 0.4, ("examplemod:flag", "on_thing"): False}


def test_out_of_range_and_non_numbers_fail_loudly(tmp_path):
    mod = _mod(tmp_path)
    for text in ("examplemod.bonus=1.5", "examplemod.bonus=-0.1"):
        with pytest.raises(ConfigError, match=r"outside 0 to 1, the range examplemod's config accepts for bonus"):
            _resolve(mod, text)
    with pytest.raises(ConfigError, match="is not a number"):
        _resolve(mod, "examplemod.bonus=true")
    # A number for a flag is not a flag setting.
    with pytest.raises(ConfigError, match="is not true or false"):
        _resolve(mod, "examplemod.on_thing=0.5")
    # Unknown names list the value options too.
    with pytest.raises(ConfigError, match=r"valid flags: on_thing, bonus \(a number, 0 to 1\)"):
        _resolve(mod, "examplemod.bonsu=0.5")


def test_uncited_version_takes_a_setting_but_has_no_default(tmp_path):
    mod = _mod(tmp_path, version="9.9")
    overrides, records = _resolve(mod, "examplemod.bonus=0.5")
    assert overrides == {KEY: 0.5} and records[0]["cited_default"] is None
    assert LoadContext(mod, table=TABLE).config_value("examplemod", "bonus") is None
    got = LoadContext(mod, table=TABLE, overrides=overrides).config_value("examplemod", "bonus")
    assert (got.value, got.default, got.user) == (0.5, None, True)


def test_context_reads_the_cited_default_or_the_setting(tmp_path):
    mod = _mod(tmp_path)
    default = LoadContext(mod, table=TABLE).config_value("examplemod", "bonus")
    assert (default.value, default.default, default.user, default.url) == (
        0.1, 0.1, False, "https://example.invalid/C#L9")
    set_ = LoadContext(mod, table=TABLE, overrides={KEY: 0.3}).config_value("examplemod", "bonus")
    assert (set_.value, set_.default, set_.user) == (0.3, 0.1, True)
    assert LoadContext(mod, table=TABLE).config_value("examplemod", "nothing") is None


def test_note_reads_the_number(tmp_path):
    _, records = _resolve(_mod(tmp_path), "examplemod.BONUS=0.25", "examplemod.on_thing=off")
    note = config_note(records)
    assert "examplemod.bonus=0.25 (default 0.1 via examplemod.BONUS)" in note
    assert "examplemod:flag/on_thing=off (default on)" in note


# -- the shipped data ------------------------------------------------------------

def test_fortune_bonus_is_cited_for_both_fd_builds():
    by = {(e["mod"], e["version"]): e for e in conditions.value_entries()}
    for loader, version in stations._FD_VERSIONS.items():
        entry = by[("farmersdelight", version)]
        assert entry["loader"] == loader
        option = entry["options"]["cuttingBoardFortuneBonus"]
        assert (option["type"], option["default"], option["min"], option["max"]) == ("double", 0.1, 0.0, 1.0)
        assert entry["commit"] in option["url"] and option["url"].endswith("Configuration.java#L84-L85")
        assert option["out_of_range"] and option["used_by"]
        # The station's own copy of the default agrees with the citation.
        assert stations._cutting_spec(loader).fortune_bonus == option["default"]
    for entry in conditions.value_entries():
        for option in entry["options"].values():
            assert re.search(r"#L\d+(-L\d+)?$", option["url"])
            assert option["min"] <= option["default"] <= option["max"]


# -- end to end: the cutting board -----------------------------------------------

def test_fd_conversion_runs_the_users_fortune_bonus(tmp_path, reference):  # noqa: F811
    src = _fd_mod(tmp_path)
    run = pipeline.convert(src, tmp_path / "out", emit_addon=False,
                           config=[parse_config_arg("farmersdelight.cuttingBoardFortuneBonus=0.25")])
    assert _table(tmp_path / "out")["fortune_bonus"] == 0.25
    summary = run.summary()
    assert summary["config"] == {"farmersdelight": {"cuttingBoardFortuneBonus": 0.25}}
    notes = summary["notes"]
    assert any("farmersdelight.cuttingBoardFortuneBonus=0.25 (default 0.1)" in n for n in notes)
    assert any("Fortune adds 0.25 per level" in n and "set by user config; cited default 0.1" in n
               for n in notes)
    record = json.loads((tmp_path / "out" / pipeline.CONFIG_RECORD).read_text())
    assert record["farmersdelight"] == {"cuttingBoardFortuneBonus": 0.25}
    assert "Configuration.java#L84-L85" in record["_settings"][0]["default_source"]
    assert "| `farmersdelight.cuttingBoardFortuneBonus` | 0.25 | 0.1 |" in report.render(run.tree)
    # The record reads back as a --config-file and reproduces the run.
    again = pipeline.convert(src, tmp_path / "again", emit_addon=False,
                             config=load_config_file(tmp_path / "out" / pipeline.CONFIG_RECORD))
    assert (again.tree / DATA).read_text() == (run.tree / DATA).read_text()


def test_fd_default_conversion_says_how_to_change_it(tmp_path, reference):  # noqa: F811
    run = pipeline.convert(_fd_mod(tmp_path), tmp_path / "out", emit_addon=False)
    assert _table(tmp_path / "out")["fortune_bonus"] == 0.1
    assert any("Fortune adds 0.1 per level to each chance result (the cited default of "
               "cuttingBoardFortuneBonus; portkit convert --config "
               "farmersdelight.cuttingBoardFortuneBonus=<number> changes it)" in n
               for n in run.summary()["notes"])
    assert not (tmp_path / "out" / pipeline.CONFIG_RECORD).exists()


def test_fd_out_of_range_stops_before_writing(tmp_path, reference):  # noqa: F811
    with pytest.raises(ConfigError, match="outside 0 to 1"):
        pipeline.convert(_fd_mod(tmp_path), tmp_path / "out", emit_addon=False,
                         config=[ConfigRequest("farmersdelight", "cuttingBoardFortuneBonus", 2.0, "--config")])
    assert not (tmp_path / "out").exists() or not any((tmp_path / "out").iterdir())
