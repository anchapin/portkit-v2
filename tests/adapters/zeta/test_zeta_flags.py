"""Zeta ``zeta:flag`` load conditions decided from bytecode defaults (#280).

The class files under tests/data/zetacode are javac 21 output (build.sh):
stand-ins for the Zeta 1.1-40 classes the reader reads (library/: the
``@ZetaLoadModule`` and ``@Config`` annotations with Zeta's defaults, the
option builders of ``ConfigManager``, ``TentativeModule#from``'s naming,
``ZetaCategory``) and an example mod (classes/: modules on and off by
default, ``@Config(flag)`` options, a ``ZGatherAdditionalFlags`` handler,
categories with a constant and a run-time required mod, an anti-overlap
module), Quark 4.1-487's shapes.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from portkit.adapters import zeta
from portkit.adapters.zeta import flags
from portkit.bytecode import ClassIndex, parse
from portkit.conditions import LoadContext, resolve_config, KnownFlag, ConfigRequest
from portkit.model import SourceMod

DATA = Path(__file__).parents[2] / "data" / "zetacode"


def _entries(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix()[:-6]: p.read_bytes() for p in root.rglob("*.class")}


def _mod(tmp_path, with_library=True, mods=None) -> SourceMod:
    index = ClassIndex(_entries(DATA / "classes"), _entries(DATA / "library") if with_library else None)
    return SourceMod(root=tmp_path, namespace="zmod", loader="neoforge", minecraft="1.21.1",
                     mods=mods if mods is not None else {"zmod": "1.0"}, requires=frozenset({"zeta"}),
                     classes=index)


def _verdict(ctx: LoadContext, flag: str, **extra):
    return ctx.evaluate([{"type": "zeta:flag", "flag": flag, **extra}])


# --- the class file reader -------------------------------------------------

def test_annotation_defaults_and_member_annotations_are_parsed():
    ann = parse((DATA / "library/org/violetmoon/zeta/module/ZetaLoadModule.class").read_bytes())
    defaults = {m.name: m.default for m in ann.methods if m.has_default}
    assert defaults == {"category": "", "name": "", "description": "", "antiOverlap": (),
                        "enabledByDefault": 1, "clientReplacement": 0, "loadPhase": 0}
    crates = parse((DATA / "classes/com/example/zmod/CratesModule.class").read_bytes())
    assert crates.field_annotations["enableApple"] == {"Lorg/violetmoon/zeta/config/Config;": {"flag": "apple_crate"}}
    stones = parse((DATA / "classes/com/example/zmod/StonesModule.class").read_bytes())
    assert "Lorg/violetmoon/zeta/event/bus/LoadEvent;" in stones.method("moreFlags").annotations
    assert stones.method("notSubscribed").annotations == {}


def test_module_names_follow_zeta_naming():
    assert flags.module_name("VerticalSlabsModule", "") == "vertical_slabs"
    assert flags.module_name("GlassModule", "Fancy Glass") == "fancy_glass"
    assert flags.module_name("MoreStoneVariantsModule", "") == "more_stone_variants"


def test_reading_lists_every_flag_source(tmp_path):
    reading = flags.read(_mod(tmp_path).classes)
    assert reading.problem == ""
    assert reading.category_default is True and reading.module_default_read
    assert reading.categories == {"building": "", "addons": "othermod", "oddities": None}
    got = {name: [(f.origin.split(" ")[0], f.value) for f in found] for name, found in reading.flags.items()}
    assert got["slabs"] == [("module", True)]
    assert "client" not in got  # a client replacement adds no flag
    assert got["fancy_glass"] == [("module", True)]
    assert got["apple_crate"] == [("config", True)]
    assert got["pre_end"] == [("config", False)]
    assert got["sack"] == [("config", False)]  # never stored: false (JVMS 2.3)
    assert got["computed"] == [("config", None)]
    assert got["inst_flag"] == [("config", True)]
    assert got["granite"] == [("load", True)] and got["tuff"] == [("load", False)]
    assert got["pillar"] == [("load", True)]
    assert "ghost" not in got  # no @LoadEvent: never called


# --- the condition ------------------------------------------------------------

def test_flags_on_by_default_pass_and_off_by_default_fail(tmp_path):
    ctx = LoadContext(_mod(tmp_path))
    for name in ("slabs", "fancy_glass", "apple_crate", "inst_flag", "granite", "pillar", "overlap"):
        assert _verdict(ctx, name).passes is True, name
    for name in ("pre_end", "sack", "tuff", "legacy", "legacy_extra"):
        v = _verdict(ctx, name)
        assert v.passes is False, name
        assert v.reason() == f"disabled by default config: zeta:flag/{name}"
    v = _verdict(ctx, "slabs")
    assert v.assumed[0].read and "SlabsModule" in v.assumed[0].url


def test_a_config_flag_needs_its_module_enabled(tmp_path):
    # LegacyModule is off by default, so its option's flag is too (putFlag
    # stores value && module.isEnabled()), though the option itself is true.
    v = _verdict(LoadContext(_mod(tmp_path)), "legacy_extra")
    assert v.passes is False and "module legacy is off by default" in v.why


def test_undecidable_flags_stay_residue(tmp_path):
    ctx = LoadContext(_mod(tmp_path))
    for name in ("computed", "odd", "ghost", "nonexistent"):
        v = _verdict(ctx, name)
        assert v.passes is None, name
        assert v.reason() == f"unknown load condition zeta:flag/{name}"
    assert _verdict(ctx, "bad%flag").passes is None
    assert ctx.evaluate([{"type": "zeta:flag", "flag": "slabs", "other": 1}]).passes is None


def test_without_the_zeta_library_nothing_is_decided(tmp_path):
    v = _verdict(LoadContext(_mod(tmp_path, with_library=False)), "slabs")
    assert v.passes is None and "isn't in the jar or its library" in v.why


def test_a_category_requiring_an_absent_mod_is_compat(tmp_path):
    v = _verdict(LoadContext(_mod(tmp_path)), "addon")
    assert v.passes is False and v.absent == ["othermod"]


def test_anti_overlap_with_a_loaded_mod_is_undecided(tmp_path):
    ctx = LoadContext(_mod(tmp_path, mods={"zmod": "1.0", "othermod": "2.0"}))
    assert _verdict(ctx, "overlap").passes is None
    assert _verdict(ctx, "addon").passes is True  # its category's mod is now there


def test_extra_condition_and_not(tmp_path):
    ctx = LoadContext(_mod(tmp_path))
    assert _verdict(ctx, "slabs", extraCondition=False).passes is False
    assert _verdict(ctx, "slabs", extraCondition=True).passes is True
    v = ctx.evaluate([{"type": "neoforge:not", "value": {"type": "zeta:flag", "flag": "slabs"}}])
    assert v.passes is False


def test_user_config_decides_both_ways_and_cascades_to_module_flags(tmp_path):
    mod = _mod(tmp_path)
    ctx = LoadContext(mod, overrides={("zeta:flag", "slabs"): False, ("zeta:flag", "legacy"): True,
                                      ("zeta:flag", "pre_end"): True})
    v = _verdict(ctx, "slabs")
    assert v.passes is False and v.reason() == "disabled by user config: zeta:flag/slabs"
    assert _verdict(ctx, "pre_end").passes is True
    # The module turned on by the user turns on its option's flag (true by default).
    v = _verdict(ctx, "legacy_extra")
    assert v.passes is True and v.assumed[0].user


def test_user_config_names_zeta_flags(tmp_path):
    known = [KnownFlag("zeta:flag", "slabs", {"zeta"})]
    overrides, records = resolve_config([ConfigRequest("zeta", "slabs", False, "--config")], known)
    assert overrides == {("zeta:flag", "slabs"): False}


def test_note_names_flags_read_from_bytecode(tmp_path):
    ctx = LoadContext(_mod(tmp_path))
    assert ctx.gate({"neoforge:conditions": [{"type": "zeta:flag", "flag": "slabs"}]}).passes
    note = ctx.note()
    assert "read from the bytecode of the mod and its library jars" in note
    assert "zmod 1.0 (on: zeta:flag/slabs)" in note
    assert "config_flag_defaults.json" not in note


@pytest.mark.parametrize("flag", ["slabs", "pre_end"])
def test_reading_is_cached_per_class_index(tmp_path, flag):
    mod = _mod(tmp_path)
    ctx = LoadContext(mod)
    _verdict(ctx, flag)
    assert zeta.reading(ctx) is zeta.reading(LoadContext(mod))
