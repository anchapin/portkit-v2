"""#281 Fabric slice: ores a Fabric mod adds to biomes in code
(``BiomeModifications``), read from the bytecode (pick 5a) and converted by the
same ore converter as Forge/NeoForge biome modifiers.

The class files under tests/data/biomecode/classes are javac 21 output of the
example mod in tests/data/biomecode/src (rebuild with build.sh): real compiler
patterns, no Minecraft or Fabric code.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from portkit import biomecode
from portkit.bytecode import ClassIndex
from portkit.conditions import LoadContext, flag_entries
from portkit.converters import features
from portkit.data import worldgen as ref
from portkit.model import SourceMod

CLASSES = Path(__file__).parent / "data" / "biomecode" / "classes"
META = {"fabric.mod.json": json.dumps({"entrypoints": {"main": ["com.example.ores.ExampleMod"]}}).encode()}
CONFIG = "com/example/ores/ModConfig"

# A flag table of our own, so the tests don't move with the shipped one.
TABLE = {"entries": [
    {"mod": "exampleores", "version": "1.0.0", "condition": "exampleores:config", "argument": "option",
     "code_gate": CONFIG,
     "flags": {"silver": {"default": True, "url": "https://example.invalid/Config.java#L1", "config_key": "silver"},
               "tin": {"default": True, "url": "https://example.invalid/Config.java#L2", "config_key": "tin"},
               "ruby": {"default": True, "url": "https://example.invalid/Config.java#L3", "config_key": "ruby"}}},
]}


@pytest.fixture(scope="module")
def reading() -> biomecode.Reading:
    return biomecode.read(ClassIndex.from_source(CLASSES), META)


def _by_feature(reading):
    return {a.feature.split(":")[1]: a for a in reading.attachments}


# -- reading the code ------------------------------------------------------------

def test_every_attachment_the_entrypoint_makes_is_read(reading):
    got = _by_feature(reading)
    assert sorted(got) == ["ore_deep_tin", "ore_end", "ore_gone", "ore_lucky", "ore_nether", "ore_odd",
                           "ore_ruby", "ore_silver", "ore_tin"]
    # Through a helper: the selector, step and key come from the caller.
    silver = got["ore_silver"]
    assert silver.selector == biomecode.Selector("tag", "exampleores:silver_biomes")
    assert silver.step_name == "underground_ores"
    assert silver.site == "com.example.ores.OreHelper.ore"
    # BiomeSelectors.foundInTheNether, and the context form with a lambda.
    assert got["ore_nether"].selector == biomecode.Selector("nether")
    assert got["ore_end"].selector == biomecode.Selector("the_end")
    assert got["ore_end"].step_name == "underground_decoration"
    assert got["ore_gone"].removal is True
    assert got["ore_odd"].selector.kind == "other"


def test_guards_are_the_branches_a_call_depends_on(reading):
    got = _by_feature(reading)
    gate = lambda name: biomecode.Gate(CONFIG, name, "()Z")  # noqa: E731
    assert [(g.gate, g.sense) for g in got["ore_silver"].guards] == [(gate("silver"), True)]
    # Two calls under one if share its guard.
    assert [(g.gate, g.sense) for g in got["ore_deep_tin"].guards] == [(gate("tin"), True)]
    # if (!config.ruby()): attached when ruby() is false.
    assert [(g.gate, g.sense) for g in got["ore_ruby"].guards] == [(gate("ruby"), False)]
    # The development-environment branch before init() rejoins: no guard.
    assert got["ore_nether"].guards == ()
    assert got["ore_end"].guards == ()
    # A branch on a static int is no named gate.
    lucky = got["ore_lucky"].guards
    assert len(lucky) == 1 and lucky[0].gate is None


def test_calls_no_entrypoint_reaches_are_noted_not_read(reading):
    assert "exampleores:ore_unused" not in {a.feature for a in reading.attachments}
    assert any("not reached" in n and "Unused.neverCalled" in n for n in reading.notes)


def test_a_jar_without_fabric_biome_calls_reads_nothing():
    other = Path(__file__).parent / "data" / "blockcode" / "classes"
    assert biomecode.read(ClassIndex.from_source(other), META).attachments == []


def test_control_dependence_of_a_diamond():
    from portkit.bytecode import Insn
    # 0: ifeq 6 / 3: nop / 4: goto 7 / 6: nop / 7: return
    code = [Insn(0, 0x99, 6), Insn(3, 0x00), Insn(4, 0xA7, 7), Insn(6, 0x00), Insn(7, 0xB1)]
    cd = biomecode.control_dependence(code)
    assert cd[3] == [(0, 3)] and cd[4] == [(0, 3)]
    assert cd[6] == [(0, 6)]
    assert 7 not in cd and 0 not in cd


# -- deciding and converting ---------------------------------------------------------

def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body))


STONE = [{"state": {"Name": "exampleores:ore"},
          "target": {"predicate_type": "minecraft:tag_match", "tag": "minecraft:stone_ore_replaceables"}}]
BLOCKS = {"blocks/ore.json": {"format_version": "1.20.20",
                              "minecraft:block": {"description": {"identifier": "exampleores:ore"}}}}
NAMES = ("ore_silver", "ore_tin", "ore_deep_tin", "ore_ruby", "ore_nether", "ore_end", "ore_gone", "ore_odd",
         "ore_lucky")


def _jar_data(root: Path, silver_tags=("#c:is_overworld",)):
    for name in NAMES:
        target = STONE if name != "ore_nether" else [
            {"state": {"Name": "exampleores:ore"},
             "target": {"predicate_type": "minecraft:block_match", "block": "minecraft:netherrack"}}]
        if name == "ore_end":
            target = [{"state": {"Name": "exampleores:ore"},
                       "target": {"predicate_type": "minecraft:block_match", "block": "minecraft:end_stone"}}]
        _write(root, f"data/exampleores/worldgen/configured_feature/{name}.json",
               {"type": "minecraft:ore", "config": {"size": 5, "targets": target}})
        _write(root, f"data/exampleores/worldgen/placed_feature/{name}.json", {
            "feature": f"exampleores:{name}",
            "placement": [{"type": "minecraft:count", "count": 2}, {"type": "minecraft:in_square"},
                          {"type": "minecraft:height_range", "height": {
                              "type": "minecraft:uniform", "min_inclusive": {"absolute": 10},
                              "max_inclusive": {"absolute": 60}}},
                          {"type": "minecraft:biome"}]})
    _write(root, "data/exampleores/tags/worldgen/biome/silver_biomes.json", {"values": list(silver_tags)})
    _write(root, "data/exampleores/tags/worldgen/biome/tin_biomes.json",
           {"values": [{"id": "#exampleores:inner", "required": False}]})
    _write(root, "data/exampleores/tags/worldgen/biome/inner.json", {"values": ["#minecraft:is_overworld"]})


def _context(root, overrides=None):
    mod = SourceMod(root=root, namespace="exampleores", loader="fabric", minecraft="1.21.1",
                    mods={"exampleores": "1.0.0"})
    return LoadContext(mod, table=TABLE, overrides=overrides)


def _convert(root, reading, overrides=None):
    context = _context(root, overrides)
    code = biomecode.decide(reading, root, {"exampleores", "c"}, context,
                            ref.convention_biome_tags("fabric", "1.21.1"), set(ref.BIOME_TAGS))
    return features.convert(root, dict(BLOCKS), {"exampleores"}, code=code), context


def test_code_attached_ores_convert_like_modifier_ores(tmp_path, reading):
    _jar_data(tmp_path)
    out, context = _convert(tmp_path, reading)
    rules = sorted(p for p in out.files if p.startswith("feature_rules/"))
    assert rules == ["feature_rules/ore_deep_tin_feature_rules.json", "feature_rules/ore_end_feature_rules.json",
                     "feature_rules/ore_nether_feature_rules.json", "feature_rules/ore_silver_feature_rules.json",
                     "feature_rules/ore_tin_feature_rules.json"]
    silver = out.files["feature_rules/ore_silver_feature_rules.json"]["minecraft:feature_rules"]
    # #c:is_overworld is exactly #minecraft:is_overworld in Fabric's pinned tags.
    assert silver["conditions"] == {"placement_pass": "underground_pass",
                                    "minecraft:biome_filter": ref.BIOME_TAGS["minecraft:is_overworld"][0]}
    end = out.files["feature_rules/ore_end_feature_rules.json"]["minecraft:feature_rules"]
    assert end["conditions"]["minecraft:biome_filter"] == [
        {"test": "has_biome_tag", "operator": "==", "value": "the_end"}]
    # The jar's biome tags it read went with the ores.
    assert {"data/exampleores/tags/worldgen/biome/silver_biomes.json",
            "data/exampleores/tags/worldgen/biome/tin_biomes.json",
            "data/exampleores/tags/worldgen/biome/inner.json"} <= out.consumed
    # The cited config defaults it assumed are noted.
    assert "exampleores:config/silver" in (context.note() or "")
    reasons = {u.source.rsplit("/", 1)[-1]: u.reason for u in out.unhandled}
    # ore_gone is only removed in code, never added: nothing here places it.
    assert set(reasons) == {"ore_ruby.json", "ore_odd.json", "ore_lucky.json"}
    assert "ModConfig.ruby() is false" in reasons["ore_ruby.json"] and "its cited default" in reasons["ore_ruby.json"]
    assert "Predicate.and" in reasons["ore_odd.json"]
    assert "undecided branch" in reasons["ore_lucky.json"]
    assert all(u.kind == "worldgen_feature" for u in out.unhandled)


def test_a_feature_the_code_removes_is_residue_where_added(tmp_path, reading):
    _jar_data(tmp_path)
    _write(tmp_path, "data/exampleores/forge/biome_modifier/gone.json",
           {"type": "forge:add_features", "biomes": "#minecraft:is_overworld",
            "features": ["exampleores:ore_gone"], "step": "underground_ores"})
    out, _ = _convert(tmp_path, reading)
    reasons = {u.source.rsplit("/", 1)[-1]: u.reason for u in out.unhandled}
    assert "removes it" in reasons["ore_gone.json"] and "pick 6" in reasons["ore_gone.json"]


def test_user_config_turns_an_ore_off(tmp_path, reading):
    _jar_data(tmp_path)
    out, _ = _convert(tmp_path, reading, overrides={("exampleores:config", "tin"): False})
    assert "feature_rules/ore_tin_feature_rules.json" not in out.files
    reasons = {u.source.rsplit("/", 1)[-1]: u.reason for u in out.unhandled}
    assert "set by user config" in reasons["ore_tin.json"]


def test_an_uncited_gate_is_residue(tmp_path, reading):
    _jar_data(tmp_path)
    context = _context(tmp_path)
    context._table = {"entries": []}
    code = biomecode.decide(reading, tmp_path, {"exampleores"}, context, {}, set(ref.BIOME_TAGS))
    silver = next(c for c in code if c.feature == "exampleores:ore_silver")
    assert "no cited config default" in silver.refused


@pytest.mark.parametrize("values, why", [
    (["#c:is_aquatic"], "not the jar's own"),
    (["minecraft:plains"], "names the biome minecraft:plains"),
    (["#exampleores:missing"], "has no file in the jar"),
])
def test_biome_sets_without_an_exact_bedrock_filter_are_refused(tmp_path, reading, values, why):
    _jar_data(tmp_path, silver_tags=values)
    out, _ = _convert(tmp_path, reading)
    reasons = {u.source.rsplit("/", 1)[-1]: u.reason for u in out.unhandled}
    assert why in reasons["ore_silver.json"]


def test_a_jar_adding_to_a_vanilla_dimension_tag_is_refused(tmp_path):
    _write(tmp_path, "data/minecraft/tags/worldgen/biome/is_overworld.json", {"values": ["exampleores:x"]})
    with pytest.raises(biomecode._Refused, match="adds to #minecraft:is_overworld"):
        biomecode.resolve_biomes(tmp_path, "minecraft:is_overworld", {"exampleores"}, {}, set(ref.BIOME_TAGS))


def test_convention_tags_only_for_their_pinned_loader_set():
    assert ref.convention_biome_tags("fabric", "1.21.1")["c:is_nether"] == "minecraft:is_nether"
    assert ref.convention_biome_tags("neoforge", "1.21.1") == {}
    assert ref.convention_biome_tags("fabric", "1.20.1") == {}


# -- the shipped data ------------------------------------------------------------------

def test_shipped_code_gates_are_cited():
    gates = [e for e in flag_entries() if e.get("code_gate")]
    assert gates, "no code_gate entry"
    for entry in gates:
        assert entry["condition"].partition(":")[0] == entry["mod"]
        assert entry["registration"]["url"].startswith("https://github.com/")
        for name, flag in entry["flags"].items():
            assert isinstance(flag["default"], bool), name
            assert flag["url"].startswith(f"{entry['repo']}/blob/{entry['commit']}/"), name
