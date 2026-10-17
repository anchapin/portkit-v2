"""#281 slice 3: Java geodes and plant patches from Forge/NeoForge biome
modifiers. Geodes -> Bedrock geode features and feature rules (picks 1a 2a
3a); patches -> worldgen_feature residue with the reason (pick 5a). Offline,
``examplemod`` only."""
import json
from pathlib import Path

from portkit.converters import features
from portkit.ingame import testpack
from portkit.validate.report import ValidationReport
from portkit.validate.xrefs import check_cross_pack

BLOCKS = {f"blocks/{n}.json": {"format_version": "1.20.20",
                               "minecraft:block": {"description": {"identifier": f"examplemod:{n}"}}}
          for n in ("crystal_block", "budding_crystal", "small_bud", "cluster", "flower")}


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body))


def _state(name, **props):
    out = {"Name": name}
    if props:
        out["Properties"] = props
    return out


def _provider(name):
    return {"type": "minecraft:simple_state_provider", "state": _state(name)}


def _geode_config(**over):
    config = {
        "blocks": {
            "filling_provider": _provider("minecraft:air"),
            "inner_layer_provider": _provider("examplemod:crystal_block"),
            "alternate_inner_layer_provider": _provider("examplemod:budding_crystal"),
            "middle_layer_provider": _provider("minecraft:calcite"),
            "outer_layer_provider": _provider("minecraft:clay"),
            "inner_placements": [_state("examplemod:small_bud", facing="up", waterlogged="false"),
                                 _state("examplemod:cluster", facing="up", waterlogged="false")],
            "cannot_replace": "#minecraft:features_cannot_replace",
            "invalid_blocks": "#minecraft:geode_invalid_blocks",
        },
        "layers": {"filling": 1.7, "inner_layer": 2.2, "middle_layer": 3.2, "outer_layer": 5.2},
        "crack": {"base_crack_size": 2.0, "crack_point_offset": 2, "generate_crack_chance": 0.95},
        "distribution_points": {"type": "minecraft:uniform", "value": {"min_inclusive": 3, "max_inclusive": 4}},
        "invalid_blocks_threshold": 1,
        "max_gen_offset": 16,
        "min_gen_offset": -16,
        "noise_multiplier": 0.05,
        "outer_wall_distance": {"type": "minecraft:uniform", "value": {"min_inclusive": 6, "max_inclusive": 9}},
        "placements_require_layer0_alternate": True,
        "point_offset": {"type": "minecraft:uniform", "value": {"min_inclusive": 1, "max_inclusive": 2}},
        "use_alternate_layer0_chance": 0.083,
        "use_potential_placements_chance": 0.335,
    }
    config.update(over)
    return config


def _geode(root, name="geode", config=None):
    _write(root, f"data/examplemod/worldgen/configured_feature/{name}.json",
           {"type": "minecraft:geode", "config": config or _geode_config()})


UNIFORM_LOW = {"type": "minecraft:height_range",
               "height": {"type": "minecraft:uniform", "min_inclusive": {"above_bottom": 6},
                          "max_inclusive": {"above_bottom": 54}}}


def _placed(root, name, placement, feature=None):
    _write(root, f"data/examplemod/worldgen/placed_feature/{name}.json",
           {"feature": feature or f"examplemod:{name}", "placement": placement})


def _rare(chance=256, height=UNIFORM_LOW):
    return [{"type": "minecraft:rarity_filter", "chance": chance}, {"type": "minecraft:in_square"}, height,
            {"type": "minecraft:biome"}]


def _modifier(root, name, feats, biomes="#minecraft:is_overworld", step="local_modifications",
              kind="forge:add_features", loader="forge"):
    body = {"type": kind, "biomes": biomes, "features": feats}
    if step is not None:
        body["step"] = step
    _write(root, f"data/examplemod/{loader}/biome_modifier/{name}.json", body)


def _convert(root):
    return features.convert(root, dict(BLOCKS), {"examplemod"})


def _setup_geode(root, **kw):
    _geode(root, **{k: v for k, v in kw.items() if k == "config"})
    _placed(root, "geode", kw.get("placement", _rare()))
    _modifier(root, "geode", ["examplemod:geode"], biomes=kw.get("biomes", "#minecraft:is_overworld"),
              step=kw.get("step", "local_modifications"))


def test_a_geode_converts_to_a_geode_feature_and_a_rule(tmp_path):
    _setup_geode(tmp_path)
    out = _convert(tmp_path)
    assert out.unhandled == []
    body = out.files["features/geode.json"]
    assert body["format_version"] == "1.13.0"
    assert body["minecraft:geode_feature"] == {
        "description": {"identifier": "examplemod:geode"},
        "filler": "minecraft:air", "inner_layer": "examplemod:crystal_block",
        "alternate_inner_layer": "examplemod:budding_crystal", "middle_layer": "minecraft:calcite",
        "outer_layer": "minecraft:clay",
        # pick 2a: the names only; Java turns facing itself, Bedrock places the default state
        "inner_placements": ["examplemod:small_bud", "examplemod:cluster"],
        "min_outer_wall_distance": 6, "max_outer_wall_distance": 9,
        "min_distribution_points": 3, "max_distribution_points": 4,
        "min_point_offset": 1, "max_point_offset": 2, "max_radius": 16,
        "crack_point_offset": 2, "generate_crack_chance": 0.95, "base_crack_size": 2.0,
        "noise_multiplier": 0.05, "use_potential_placements_chance": 0.335,
        "use_alternate_layer0_chance": 0.083, "placements_require_layer0_alternate": True,
        "invalid_blocks_threshold": 1}
    rule = out.files["feature_rules/geode_feature_rules.json"]["minecraft:feature_rules"]
    assert rule["description"] == {"identifier": "examplemod:geode_feature_rules",
                                   "places_feature": "examplemod:geode"}
    # pick 3a: local_modifications runs before the ores' step -> before_underground_pass
    assert rule["conditions"]["placement_pass"] == "before_underground_pass"
    square = {"distribution": "uniform", "extent": [0, 15]}
    assert rule["distribution"] == {"iterations": 1, "scatter_chance": {"numerator": 1, "denominator": 256},
                                    "x": square, "z": square,
                                    "y": {"distribution": "uniform", "extent": [-58, -10]}}
    assert out.consumed == {"data/examplemod/forge/biome_modifier/geode.json",
                            "data/examplemod/worldgen/placed_feature/geode.json",
                            "data/examplemod/worldgen/configured_feature/geode.json"}
    # pick 1a: the fields Bedrock can't carry are named in an "approximated geode" note
    note = next(n for n in out.notes if n.startswith("approximated geode"))
    assert "outer_layer\": 5.2" in note and "max_radius 16" in note and "cannot_replace" in note
    assert "facing" in note
    assert any("before_underground_pass" in n for n in out.notes)
    assert out.geodes == [{"rule": "examplemod:geode_feature_rules", "feature": "examplemod:geode",
                           "dimension": "overworld", "y": [-58, -10]}]


def _reason(out, source="data/examplemod/worldgen/placed_feature/geode.json"):
    return next(u for u in out.unhandled if u.source == source).reason


def test_a_geode_leaving_a_field_to_java_defaults_is_residue(tmp_path):
    config = _geode_config()
    del config["layers"]
    _setup_geode(tmp_path, config=config)
    out = _convert(tmp_path)
    assert out.files == {}
    assert "leaves layers to Java's defaults" in _reason(out)
    assert sum(u.count for u in out.unhandled) == len(out.consumed)


def test_uneven_gen_offsets_have_no_single_radius(tmp_path):
    _setup_geode(tmp_path, config=_geode_config(min_gen_offset=-8, max_gen_offset=16))
    assert "max_radius" in _reason(_convert(tmp_path))


def test_a_layer_of_a_block_the_pack_does_not_ship_is_residue(tmp_path):
    config = _geode_config()
    config["blocks"]["outer_layer_provider"] = _provider("examplemod:missing")
    _setup_geode(tmp_path, config=config)
    assert "examplemod:missing" in _reason(_convert(tmp_path))


def test_a_weighted_layer_or_an_out_of_range_field_is_residue(tmp_path):
    config = _geode_config()
    config["blocks"]["middle_layer_provider"] = {"type": "minecraft:weighted_state_provider", "entries": []}
    _setup_geode(tmp_path, config=config)
    assert "simple_state_provider" in _reason(_convert(tmp_path))
    config = _geode_config(outer_wall_distance={"type": "minecraft:uniform",
                                                "value": {"min_inclusive": 12, "max_inclusive": 14}})
    _setup_geode(tmp_path, config=config)
    assert "outside Bedrock's range 1..10" in _reason(_convert(tmp_path))


def test_a_nether_geode_measured_from_the_top_is_residue(tmp_path):
    top = {"type": "minecraft:height_range",
           "height": {"type": "minecraft:uniform", "min_inclusive": {"below_top": 48},
                      "max_inclusive": {"below_top": 16}}}
    _setup_geode(tmp_path, placement=_rare(52, top), biomes="#minecraft:is_nether")
    out = _convert(tmp_path)
    assert out.files == {}
    assert "below_top 48 in the nether" in _reason(out)
    assert sorted((u.source, u.count) for u in out.unhandled) == [
        ("data/examplemod/forge/biome_modifier/geode.json", 1),
        ("data/examplemod/worldgen/placed_feature/geode.json", 2)]


def test_a_biome_selector_subtracting_biomes_is_residue(tmp_path):
    biomes = {"type": "forge:and", "values": [{"type": "forge:or", "values": ["#minecraft:is_end"]},
                                              {"type": "forge:not", "value": "minecraft:the_end"}]}
    _setup_geode(tmp_path, biomes=biomes)
    assert "only vanilla biome tags" in _reason(_convert(tmp_path))


def test_a_geode_at_a_step_with_no_bedrock_pass_is_residue(tmp_path):
    _setup_geode(tmp_path, step="vegetal_decoration")
    assert "generation step `vegetal_decoration`" in _reason(_convert(tmp_path))


def test_a_geode_placement_with_no_scatter_parameter_is_residue(tmp_path):
    _setup_geode(tmp_path, placement=[*_rare(), {"type": "minecraft:heightmap", "heightmap": "OCEAN_FLOOR"}])
    assert "placement `minecraft:heightmap`" in _reason(_convert(tmp_path))


def test_a_geode_with_a_mod_placement_is_left_for_the_other_passes(tmp_path):
    _setup_geode(tmp_path, placement=[{"type": "examplemod:config_filter"}, *_rare()])
    out = _convert(tmp_path)
    assert out.files == {} and out.unhandled == [] and out.consumed == set()


# -- plant patches: residue with the reason (pick 5a) ------------------------------

def _patch(root, name="flowers", block="examplemod:flower", inner_type="minecraft:simple_block",
           inner_placement=None):
    _write(root, f"data/examplemod/worldgen/configured_feature/{name}.json", {
        "type": "minecraft:random_patch",
        "config": {"tries": 32, "xz_spread": 6, "y_spread": 2, "feature": {
            "feature": {"type": inner_type, "config": {"to_place": _provider(block)}},
            "placement": inner_placement if inner_placement is not None else [
                {"type": "minecraft:block_predicate_filter",
                 "predicate": {"type": "minecraft:matching_blocks", "blocks": "minecraft:air"}}]}}})


SURFACE = [{"type": "minecraft:rarity_filter", "chance": 16}, {"type": "minecraft:in_square"},
           {"type": "minecraft:heightmap", "heightmap": "MOTION_BLOCKING"}, {"type": "minecraft:biome"}]


def test_a_patch_in_a_dimension_tag_is_residue_naming_pick_5(tmp_path):
    _patch(tmp_path)
    _placed(tmp_path, "flowers", SURFACE)
    _modifier(tmp_path, "flowers", ["examplemod:flowers"], step="vegetal_decoration")
    out = _convert(tmp_path)
    assert out.files == {}
    reason = _reason(out, "data/examplemod/worldgen/placed_feature/flowers.json")
    assert reason.startswith("plant patch placed feature") and "pick 5" in reason
    assert sum(u.count for u in out.unhandled) == len(out.consumed) == 3


def test_a_selector_of_patches_counts_every_feature_it_names(tmp_path):
    for colour in ("red", "blue"):
        _patch(tmp_path, f"{colour}_patch")
    _write(tmp_path, "data/examplemod/worldgen/configured_feature/flowers.json", {
        "type": "minecraft:simple_random_selector",
        "config": {"features": [{"feature": "examplemod:red_patch", "placement": []},
                                {"feature": "examplemod:blue_patch", "placement": []}]}})
    _placed(tmp_path, "flowers", SURFACE)
    _modifier(tmp_path, "flowers", ["examplemod:flowers"], step="vegetal_decoration")
    _modifier(tmp_path, "no_flowers", ["examplemod:flowers"], biomes="#examplemod:blocklist", step=None,
              kind="forge:remove_features")
    out = _convert(tmp_path)
    by = {u.source: u for u in out.unhandled}
    pf = by["data/examplemod/worldgen/placed_feature/flowers.json"]
    assert pf.count == 4 and "removes it from some biomes" in pf.reason
    assert "can't subtract" in by["data/examplemod/forge/biome_modifier/no_flowers.json"].reason
    assert sum(u.count for u in out.unhandled) == len(out.consumed) == 6


def test_a_patch_placing_a_mod_feature_type_names_the_code(tmp_path):
    _patch(tmp_path, inner_type="examplemod:mystical_flower")
    _placed(tmp_path, "flowers", SURFACE)
    _modifier(tmp_path, "flowers", ["examplemod:flowers"], step="vegetal_decoration")
    reason = _reason(_convert(tmp_path), "data/examplemod/worldgen/placed_feature/flowers.json")
    assert "examplemod:mystical_flower" in reason and "its code" in reason


def test_a_patch_with_a_mod_placement_on_top_is_left_alone(tmp_path):
    _patch(tmp_path)
    _placed(tmp_path, "flowers", [{"type": "examplemod:below_heightmaps"}, *SURFACE])
    _modifier(tmp_path, "flowers", ["examplemod:flowers"], step="vegetal_decoration")
    out = _convert(tmp_path)
    assert out.unhandled == [] and out.consumed == set()


# -- the validator and the in-game check -------------------------------------------

def _tree(tmp_path, out):
    bp = tmp_path / "tree" / "behavior_pack"
    for rel, body in {**BLOCKS, **out.files}.items():
        _write(bp, rel, body)
    return bp


def test_the_validator_wants_the_geode_blocks_declared(tmp_path):
    src = tmp_path / "src"
    _setup_geode(src)
    out = _convert(src)
    bp = _tree(tmp_path, out)
    report = ValidationReport()
    check_cross_pack(report, tmp_path / "tree")
    assert not [f for f in report.findings if f.rule == "xref.feature"]
    (bp / "blocks/cluster.json").unlink()
    report = ValidationReport()
    check_cross_pack(report, tmp_path / "tree")
    assert [f.message for f in report.findings if f.rule == "xref.feature"] == [
        "inner_placements[1] places 'examplemod:cluster', which no block definition declares"]


def test_the_check_pack_generates_each_geode_in_every_chunk(tmp_path):
    src = tmp_path / "src"
    _setup_geode(src)
    bp = _tree(tmp_path, _convert(src))
    checks = testpack.read_checks(bp)
    assert checks.geodes == [{
        "rule": "examplemod:geode_feature_rules", "feature": "examplemod:geode",
        "blocks": ["examplemod:crystal_block", "examplemod:budding_crystal"],
        "buds": ["examplemod:small_bud", "examplemod:cluster"], "dimension": "overworld",
        "y": [-74, 6], "check_rule": "portkit_check:geode_feature_rules"}]
    out = tmp_path / "check"
    written = testpack.write_test_pack(bp, out, "t", world="default")
    assert written.geodes == checks.geodes and written.blocks == []
    rule = json.loads((out / "feature_rules/geode_feature_rules.json").read_text())["minecraft:feature_rules"]
    assert rule["description"] == {"identifier": "portkit_check:geode_feature_rules",
                                   "places_feature": "examplemod:geode"}
    assert "scatter_chance" not in rule["distribution"]
    modules = json.loads((out / "manifest.json").read_text())["modules"]
    assert [m["type"] for m in modules] == ["script", "data"]
    # A pack without geodes keeps the script-only manifest.
    plain = testpack.write_test_pack(tmp_path / "src", tmp_path / "plain", "p")
    assert plain.geodes == []
    assert [m["type"] for m in json.loads((tmp_path / "plain/manifest.json").read_text())["modules"]] == ["script"]
