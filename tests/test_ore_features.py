"""#281 first slice: Java ores from Forge/NeoForge biome modifiers -> Bedrock
ore features and feature rules. Offline, ``examplemod`` only."""
import json
from pathlib import Path

from portkit.converters import features
from portkit.ingame import testpack
from portkit.pack import _is_behavior
from portkit.validate.report import ValidationReport
from portkit.validate.xrefs import check_cross_pack

BLOCKS = {"blocks/ore.json": {"format_version": "1.20.20",
                              "minecraft:block": {"description": {"identifier": "examplemod:ore"}}},
          "blocks/deep_ore.json": {"format_version": "1.20.20",
                                   "minecraft:block": {"description": {"identifier": "examplemod:deep_ore"}}}}


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body))


def _ore(root, name, targets, size=6, discard=None):
    config = {"size": size, "targets": targets}
    if discard is not None:
        config["discard_chance_on_air_exposure"] = discard
    _write(root, f"data/examplemod/worldgen/configured_feature/{name}.json", {"type": "minecraft:ore", "config": config})


def _placed(root, name, placement, feature=None):
    _write(root, f"data/examplemod/worldgen/placed_feature/{name}.json",
           {"feature": feature or f"examplemod:{name}", "placement": placement})


def _modifier(root, name, feats, biomes="#minecraft:is_nether", step="underground_ores", kind="forge:add_features",
              loader="forge"):
    _write(root, f"data/examplemod/{loader}/biome_modifier/{name}.json",
           {"type": kind, "biomes": biomes, "features": feats, "step": step})


NETHERRACK = [{"state": {"Name": "examplemod:ore"},
               "target": {"predicate_type": "minecraft:block_match", "block": "minecraft:netherrack"}}]
TRAPEZOID = {"type": "minecraft:height_range",
             "height": {"type": "minecraft:trapezoid", "min_inclusive": {"absolute": 8},
                        "max_inclusive": {"absolute": 32}}}


def _standard(count=3, height=TRAPEZOID):
    return [{"type": "minecraft:count", "count": count}, {"type": "minecraft:in_square"}, height,
            {"type": "minecraft:biome"}]


def _convert(root):
    return features.convert(root, dict(BLOCKS), {"examplemod"})


def test_a_nether_ore_converts_to_a_feature_and_a_rule(tmp_path):
    _ore(tmp_path, "ore_large", NETHERRACK)
    _placed(tmp_path, "ore_large", _standard())
    _modifier(tmp_path, "ores", ["examplemod:ore_large"], step="underground_decoration")
    out = _convert(tmp_path)
    assert out.unhandled == []
    assert out.files["features/ore_large.json"] == {
        "format_version": "1.13.0",
        "minecraft:ore_feature": {
            "description": {"identifier": "examplemod:ore_large"}, "count": 6,
            "replace_rules": [{"places_block": "examplemod:ore", "may_replace": ["minecraft:netherrack"]}]}}
    rule = out.files["feature_rules/ore_large_feature_rules.json"]["minecraft:feature_rules"]
    assert rule["description"] == {"identifier": "examplemod:ore_large_feature_rules",
                                   "places_feature": "examplemod:ore_large"}
    assert rule["conditions"] == {"placement_pass": "underground_pass", "minecraft:biome_filter": [
        {"test": "has_biome_tag", "operator": "==", "value": "nether"}]}
    square = {"distribution": "uniform", "extent": [0, 15]}
    assert rule["distribution"] == {"iterations": 3, "x": square, "z": square,
                                    "y": {"distribution": "triangle", "extent": [8, 32]}}
    assert out.consumed == {"data/examplemod/forge/biome_modifier/ores.json",
                            "data/examplemod/worldgen/placed_feature/ore_large.json",
                            "data/examplemod/worldgen/configured_feature/ore_large.json"}
    assert any("pick 2" in n for n in out.notes)
    assert out.ores == [{"rule": "examplemod:ore_large_feature_rules", "feature": "examplemod:ore_large",
                         "dimension": "nether", "blocks": ["examplemod:ore"],
                         "replaces": ["minecraft:netherrack"], "y": [8, 32]}]


def test_overworld_tags_and_ore_replaceables(tmp_path):
    _ore(tmp_path, "ore", [
        {"state": {"Name": "examplemod:ore"},
         "target": {"predicate_type": "minecraft:tag_match", "tag": "minecraft:stone_ore_replaceables"}},
        {"state": {"Name": "examplemod:deep_ore"},
         "target": {"predicate_type": "minecraft:tag_match", "tag": "minecraft:deepslate_ore_replaceables"}},
    ], size=9, discard=0.5)
    height = {"type": "minecraft:height_range",
              "height": {"type": "minecraft:uniform", "min_inclusive": {"above_bottom": 4},
                         "max_inclusive": {"below_top": 19}}}
    _placed(tmp_path, "ore", _standard(count=7, height=height))
    _modifier(tmp_path, "ores", "examplemod:ore", biomes="#minecraft:is_overworld", loader="neoforge",
              kind="neoforge:add_features")
    out = _convert(tmp_path)
    assert out.unhandled == []
    body = out.files["features/ore.json"]["minecraft:ore_feature"]
    assert body["count"] == 9 and body["discard_chance_on_air_exposure"] == 0.5
    assert body["replace_rules"] == [
        {"places_block": "examplemod:ore", "may_replace": ["minecraft:stone", "minecraft:granite",
                                                           "minecraft:diorite", "minecraft:andesite"]},
        {"places_block": "examplemod:deep_ore", "may_replace": ["minecraft:deepslate", "minecraft:tuff"]}]
    rule = out.files["feature_rules/ore_feature_rules.json"]["minecraft:feature_rules"]
    assert rule["distribution"]["y"] == {"distribution": "uniform", "extent": [-60, 300]}
    assert rule["conditions"]["minecraft:biome_filter"] == [{"any_of": [
        {"test": "has_biome_tag", "operator": "==", "value": "overworld"},
        {"test": "has_biome_tag", "operator": "==", "value": "overworld_generation"}]}]


def test_the_nethers_top_differs_so_below_top_there_is_residue(tmp_path):
    _ore(tmp_path, "ore_small", NETHERRACK)
    _ore(tmp_path, "ore_large", NETHERRACK)
    height = {"type": "minecraft:height_range",
              "height": {"type": "minecraft:uniform", "min_inclusive": {"above_bottom": 8},
                         "max_inclusive": {"below_top": 8}}}
    _placed(tmp_path, "ore_small", _standard(count=5, height=height))
    _placed(tmp_path, "ore_large", _standard())
    _modifier(tmp_path, "ores", ["examplemod:ore_small", "examplemod:ore_large"])
    out = _convert(tmp_path)
    assert "features/ore_large.json" in out.files and "features/ore_small.json" not in out.files
    [u] = out.unhandled
    assert (u.source, u.kind, u.count) == ("data/examplemod/worldgen/placed_feature/ore_small.json",
                                           "worldgen_feature", 2)
    assert "below_top 8 in the nether" in u.reason and "pick 4" in u.reason
    # The modifier converted (one of its ores did), so it is not residue.
    assert "data/examplemod/forge/biome_modifier/ores.json" in out.consumed


def test_a_modifier_whose_ores_all_refuse_is_residue_too(tmp_path):
    _ore(tmp_path, "ore", NETHERRACK)
    _placed(tmp_path, "ore", _standard())
    _modifier(tmp_path, "ores", ["examplemod:ore"], biomes="#examplemod:has_ore")
    out = _convert(tmp_path)
    assert out.files == {}
    assert sorted((u.source, u.count) for u in out.unhandled) == [
        ("data/examplemod/forge/biome_modifier/ores.json", 1),
        ("data/examplemod/worldgen/placed_feature/ore.json", 2)]
    assert sum(u.count for u in out.unhandled) == len(out.consumed)


def test_modifiers_with_anything_but_vanilla_ores_are_left_alone(tmp_path):
    _ore(tmp_path, "ore", NETHERRACK)
    _placed(tmp_path, "ore", _standard())
    _placed(tmp_path, "coded", [{"type": "examplemod:config_filter"}, *_standard()], feature="examplemod:ore")
    _write(tmp_path, "data/examplemod/worldgen/configured_feature/geode.json", {"type": "minecraft:geode", "config": {}})
    _placed(tmp_path, "geode", _standard())
    _modifier(tmp_path, "coded", ["examplemod:coded"])
    _modifier(tmp_path, "mixed", ["examplemod:ore", "examplemod:geode"])
    out = _convert(tmp_path)
    assert out.files == {} and out.unhandled == [] and out.consumed == set()


def test_fabric_ores_have_no_modifier_and_stay_unread(tmp_path):
    _ore(tmp_path, "ore", NETHERRACK)
    _placed(tmp_path, "ore", _standard())
    out = _convert(tmp_path)
    assert out.files == {} and out.consumed == set()


def test_refusals_name_their_reason(tmp_path):
    cases = {
        "unshipped": ([{"state": {"Name": "examplemod:missing"}, "target": NETHERRACK[0]["target"]}], _standard(),
                      "isn't a block the pack ships"),
        "props": ([{"state": {"Name": "examplemod:ore", "Properties": {"lit": "true"}},
                    "target": NETHERRACK[0]["target"]}], _standard(), "block-state properties"),
        "rarity_after": (NETHERRACK, _standard() + [{"type": "minecraft:rarity_filter", "chance": 4}],
                         "after a count above 1"),
        "plateau": (NETHERRACK, _standard(height={"type": "minecraft:height_range", "height": {
            "type": "minecraft:trapezoid", "plateau": 4, "min_inclusive": {"absolute": 8},
            "max_inclusive": {"absolute": 32}}}), "pick 2"),
        "random_count": (NETHERRACK, [{"type": "minecraft:count", "count": {"type": "minecraft:uniform"}},
                                      TRAPEZOID], "not a constant whole number"),
        "too_high": (NETHERRACK, _standard(height={"type": "minecraft:height_range", "height": {
            "type": "minecraft:uniform", "min_inclusive": {"absolute": 100},
            "max_inclusive": {"absolute": 200}}}), "outside Bedrock's nether"),
        "tag_target": ([{"state": {"Name": "examplemod:ore"},
                         "target": {"predicate_type": "minecraft:tag_match", "tag": "examplemod:rocks"}}],
                       _standard(), "ore target test"),
    }
    for name, (targets, placement, _) in cases.items():
        _ore(tmp_path, name, targets)
        _placed(tmp_path, name, placement)
    _modifier(tmp_path, "all", [f"examplemod:{n}" for n in cases])
    out = _convert(tmp_path)
    assert out.files == {}
    reasons = {Path(u.source).stem: u.reason for u in out.unhandled}
    for name, (_, _, expect) in cases.items():
        assert expect in reasons[name], (name, reasons[name])


def test_rarity_first_is_one_scatter_chance(tmp_path):
    _ore(tmp_path, "rare", NETHERRACK)
    _placed(tmp_path, "rare", [{"type": "minecraft:rarity_filter", "chance": 7}, *_standard(count=2)])
    _modifier(tmp_path, "ores", ["examplemod:rare"])
    dist = _convert(tmp_path).files["feature_rules/rare_feature_rules.json"]["minecraft:feature_rules"]["distribution"]
    assert dist["scatter_chance"] == {"numerator": 1, "denominator": 7} and dist["iterations"] == 2


def test_a_removed_feature_is_residue(tmp_path):
    _ore(tmp_path, "ore", NETHERRACK)
    _placed(tmp_path, "ore", _standard())
    _modifier(tmp_path, "add", ["examplemod:ore"])
    _write(tmp_path, "data/examplemod/forge/biome_modifier/remove.json",
           {"type": "forge:remove_features", "biomes": "#minecraft:is_nether", "features": "examplemod:ore"})
    out = _convert(tmp_path)
    assert out.files == {}
    assert any("pick 6" in u.reason for u in out.unhandled)


def test_one_feature_added_twice_gets_two_rules(tmp_path):
    _ore(tmp_path, "ore", NETHERRACK)
    _placed(tmp_path, "ore", _standard())
    _modifier(tmp_path, "a", ["examplemod:ore"])
    _modifier(tmp_path, "b", ["examplemod:ore"], biomes="#minecraft:is_end")
    out = _convert(tmp_path)
    assert sorted(out.files) == ["feature_rules/ore__a_feature_rules.json", "feature_rules/ore__b_feature_rules.json",
                                 "features/ore.json"]


def test_feature_files_go_to_the_behavior_pack():
    assert _is_behavior("features/ore.json") and _is_behavior("feature_rules/ore_feature_rules.json")


def _tree(tmp_path, feature_files):
    bp = tmp_path / "tree" / "behavior_pack"
    for rel, body in {**BLOCKS, **feature_files}.items():
        _write(bp, rel, body)
    return tmp_path / "tree"


def test_xrefs_check_feature_names_rules_and_blocks(tmp_path):
    good = {"features/ore.json": {"format_version": "1.13.0", "minecraft:ore_feature": {
                "description": {"identifier": "examplemod:ore"}, "count": 3,
                "replace_rules": [{"places_block": "examplemod:ore", "may_replace": ["minecraft:stone"]}]}},
            "feature_rules/ore_feature_rules.json": {"format_version": "1.13.0", "minecraft:feature_rules": {
                "description": {"identifier": "examplemod:ore_feature_rules", "places_feature": "examplemod:ore"},
                "conditions": {"placement_pass": "underground_pass"}}}}
    report = ValidationReport()
    check_cross_pack(report, _tree(tmp_path / "a", good))
    assert [f for f in report.findings if f.rule == "xref.feature"] == []
    bad = {"features/wrong_name.json": {"format_version": "1.13.0", "minecraft:ore_feature": {
                "description": {"identifier": "examplemod:ore"}, "count": 3,
                "replace_rules": [{"places_block": "examplemod:gone"}]}},
           "feature_rules/r.json": {"format_version": "1.13.0", "minecraft:feature_rules": {
                "description": {"identifier": "examplemod:r", "places_feature": "examplemod:nothing"},
                "conditions": {"placement_pass": "underground_pass"}}}}
    report = ValidationReport()
    check_cross_pack(report, _tree(tmp_path / "b", bad))
    messages = [f.message for f in report.findings if f.rule == "xref.feature"]
    assert len(messages) == 3
    assert any("doesn't match the file name" in m for m in messages)
    assert any("examplemod:gone" in m for m in messages)
    assert any("examplemod:nothing" in m for m in messages)


def test_the_check_pack_lists_each_ore_rule(tmp_path):
    _ore(tmp_path, "ore", NETHERRACK)
    _placed(tmp_path, "ore", _standard())
    _modifier(tmp_path, "ores", ["examplemod:ore"])
    out = _convert(tmp_path)
    tree = _tree(tmp_path, out.files)
    checks = testpack.read_checks(tree / "behavior_pack")
    assert checks.ores == [{"rule": "examplemod:ore_feature_rules", "feature": "examplemod:ore",
                            "blocks": ["examplemod:ore"], "replaces": ["minecraft:netherrack"],
                            "hosts": ["minecraft:netherrack"], "dimension": "nether", "y": [8, 32]}]
    assert checks.as_json()["ores"] == checks.ores
    assert "world" not in checks.as_json()


def test_a_generated_world_check_pack_holds_only_the_ores(tmp_path):
    _ore(tmp_path, "ore", NETHERRACK)
    _placed(tmp_path, "ore", _standard())
    _modifier(tmp_path, "ores", ["examplemod:ore"])
    out = _convert(tmp_path)
    tree = _tree(tmp_path, out.files)
    checks = testpack.write_test_pack(tree / "behavior_pack", tmp_path / "pack", "demo", world="default")
    assert checks.blocks == [] and len(checks.ores) == 1
    data = (tmp_path / "pack" / "scripts" / "data.js").read_text()
    assert '"world": "default"' in data


def test_constant_providers_written_out_read_as_their_value(tmp_path):
    _ore(tmp_path, "ore", NETHERRACK)
    _placed(tmp_path, "ore", [{"type": "minecraft:count", "count": {"type": "minecraft:constant", "value": 4}},
                              {"type": "minecraft:height_range", "height": {"absolute": 20}}])
    _modifier(tmp_path, "ores", ["examplemod:ore"])
    dist = _convert(tmp_path).files["feature_rules/ore_feature_rules.json"]["minecraft:feature_rules"]["distribution"]
    assert dist == {"iterations": 4, "x": 0, "y": 20, "z": 0}


def test_refused_ores_are_explained_residue():
    from portkit.agent.residue import SKIP_KINDS
    assert features.KIND in SKIP_KINDS
