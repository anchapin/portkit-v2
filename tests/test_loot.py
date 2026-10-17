"""Block drops: the plain shape converts, everything conditional stays residue."""
import json

import pytest

from portkit.converters import loot
from portkit.model import SourceMod


def build(tmp_path, tables, dirname="loot_tables"):
    root = tmp_path / "data" / "examplemod" / dirname / "blocks"
    root.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        (root / f"{name}.json").write_text(json.dumps(table))
    return SourceMod(root=tmp_path, namespace="examplemod")


def pool(entry, conditions=None, functions=None, rolls=1):
    p = {"rolls": rolls, "entries": [entry]}
    if conditions:
        p["conditions"] = conditions
    if functions:
        p["functions"] = functions
    return {"type": "minecraft:block", "pools": [p]}


ITEM = {"type": "minecraft:item", "name": "examplemod:steel_block"}
SURVIVES = [{"condition": "minecraft:survives_explosion"}]


def test_a_block_that_drops_itself_converts(tmp_path):
    result = loot.convert(build(tmp_path, {"steel_block": pool(ITEM, SURVIVES)}))
    assert result.unhandled == []
    table = result.files["loot_tables/blocks/steel_block.json"]
    entry = table["pools"][0]["entries"][0]
    assert entry == {
        "type": "item",
        "name": "examplemod:steel_block",
        "functions": [{"function": "explosion_decay"}],
    }


def test_a_constant_set_count_is_kept(tmp_path):
    table = pool(ITEM, SURVIVES, functions=[{"function": "minecraft:set_count", "count": 4}])
    result = loot.convert(build(tmp_path, {"thatch": table}))
    functions = result.files["loot_tables/blocks/thatch.json"]["pools"][0]["entries"][0]["functions"]
    assert {"function": "set_count", "count": 4} in functions


def test_a_range_count_is_refused_rather_than_averaged(tmp_path):
    table = pool(ITEM, SURVIVES, functions=[{
        "function": "minecraft:set_count",
        "count": {"type": "minecraft:uniform", "min": 1, "max": 3}}])
    result = loot.convert(build(tmp_path, {"leaf_pile": table}))
    assert result.files == {}
    assert "range rather than a fixed number" in result.unhandled[0].reason


def test_fortune_is_refused_and_says_so(tmp_path):
    table = pool(ITEM, SURVIVES, functions=[{
        "function": "minecraft:apply_bonus", "enchantment": "minecraft:fortune"}])
    result = loot.convert(build(tmp_path, {"steel_ore": table}))
    assert result.files == {}
    reason = result.unhandled[0].reason
    assert "fortune" in reason and "apply_bonus" in reason


def test_alternatives_with_no_children_drop_nothing(tmp_path):
    table = {"pools": [{"rolls": 1, "entries": [{"type": "minecraft:alternatives", "children": []}]}]}
    result = loot.convert(build(tmp_path, {"glass_pane": table}))
    assert "drops nothing" in result.unhandled[0].reason


def test_a_tool_condition_names_the_condition(tmp_path):
    table = pool(ITEM, [{"condition": "minecraft:match_tool", "predicate": {}}])
    result = loot.convert(build(tmp_path, {"ore": table}))
    reason = result.unhandled[0].reason
    assert "tool used" in reason and "match_tool" in reason


@pytest.mark.parametrize("rolls", [2, {"type": "minecraft:uniform", "min": 1, "max": 2}])
def test_a_variable_roll_count_is_refused(tmp_path, rolls):
    result = loot.convert(build(tmp_path, {"x": pool(ITEM, SURVIVES, rolls=rolls)}))
    assert "rolls" in result.unhandled[0].reason


def test_two_pools_are_refused(tmp_path):
    table = {"pools": [{"rolls": 1, "entries": [ITEM]}, {"rolls": 1, "entries": [ITEM]}]}
    result = loot.convert(build(tmp_path, {"x": table}))
    assert "2 pools" in result.unhandled[0].reason


def _residue(source, kind, reason="r"):
    from portkit.model import Unhandled
    return Unhandled(source=source, kind=kind, reason=reason)


def test_a_refused_table_whose_block_is_residue_is_owned_by_residue():
    unhandled = [
        _residue("assets/ex/blockstates/chest.json", "code_drawn_block"),
        _residue("data/ex/loot_table/blocks/chest.json", "loot", "the drop copies the block's custom name"),
        _residue("data/ex/loot_tables/blocks/lamp.json", "loot", "the drop depends on the block state"),
        _residue("data/ex/loot_table/blocks/ore.json", "loot", "the drop depends on the tool used"),
        _residue("assets/ex/blockstates/lamp.json", "block"),
    ]
    out = loot.refine_owned(unhandled, shipped_blocks={"ex:ore"})
    kinds = {u.source: u.kind for u in out}
    assert kinds["data/ex/loot_table/blocks/chest.json"] == "owned_by_residue"
    assert kinds["data/ex/loot_tables/blocks/lamp.json"] == "owned_by_residue"
    # The block shipped: the table is still a converter gap.
    assert kinds["data/ex/loot_table/blocks/ore.json"] == "loot"
    chest = next(u for u in out if u.source.endswith("blocks/chest.json"))
    assert "code_drawn_block" in chest.reason and "custom name" in chest.reason
    assert len(out) == len(unhandled)


def test_a_table_with_no_residue_blockstate_stays_loot():
    unhandled = [_residue("data/ex/loot_table/blocks/ghost.json", "loot")]
    assert loot.refine_owned(unhandled, shipped_blocks=set())[0].kind == "loot"


def test_the_1_21_singular_directory_is_read_too(tmp_path):
    mod = build(tmp_path, {"steel_block": pool(ITEM, SURVIVES)}, dirname="loot_table")
    result = loot.convert(mod)
    assert "loot_tables/blocks/steel_block.json" in result.files


def test_every_table_is_claimed_even_when_refused(tmp_path):
    mod = build(tmp_path, {"a": pool(ITEM, SURVIVES), "b": {"pools": []}})
    result = loot.convert(mod)
    assert len(result.consumed) == 2


def test_the_fixture_converts_the_plain_drops_and_reports_the_rest(tmp_path, fixtures_dir):
    from portkit.pipeline import convert

    out = convert(fixtures_dir / "loot_mod" / "input", tmp_path / "out")
    assert out.report.ok, out.report.to_dict()
    produced = sorted(
        p.name for p in (out.tree / "behavior_pack" / "loot_tables" / "blocks").glob("*.json")
    )
    assert produced == ["steel_block.json", "thatch.json"]
    reasons = " ".join(u.reason for u in out.unhandled)
    assert "fortune" in reasons
    assert "Silk Touch" in reasons


def test_the_validator_actually_runs_on_loot_tables(tmp_path):
    """The loot rules have to be reachable from validate_pack, not just exist."""
    from portkit.validate.rules import validate_pack

    pack = tmp_path / "behavior_pack"
    (pack / "loot_tables" / "blocks").mkdir(parents=True)
    (pack / "loot_tables" / "blocks" / "broken.json").write_text(
        json.dumps({"pools": [{"rolls": 1, "entries": [{"type": "item", "name": "not an id"}]}]})
    )
    report = validate_pack(pack)
    assert not report.ok
    assert any(f.rule == "loot.name" for f in report.findings)
    assert any("loot_tables/blocks/broken.json" in f.path for f in report.findings)


def test_a_pack_with_both_a_flipbook_and_loot_tables_validates(tmp_path):
    """Regression: the loot loop once sat inside the flipbook check."""
    from portkit.validate.rules import validate_pack

    pack = tmp_path / "resource_pack"
    (pack / "textures").mkdir(parents=True)
    (pack / "loot_tables" / "blocks").mkdir(parents=True)
    (pack / "textures" / "flipbook_textures.json").write_text(json.dumps([]))
    (pack / "loot_tables" / "blocks" / "ok.json").write_text(
        json.dumps({"pools": [{"rolls": 1, "entries": [{"type": "item", "name": "ex:steel"}]}]})
    )
    report = validate_pack(pack)
    assert [f for f in report.findings if f.rule.startswith("loot.")] == []
def test_the_pipeline_files_a_code_drawn_blocks_table_with_its_block(tmp_path):
    from portkit.agent.residue import SKIP_KINDS
    from portkit.pipeline import convert

    src = tmp_path / "src"
    assets = src / "assets" / "examplemod"
    (assets / "blockstates").mkdir(parents=True)
    (assets / "blockstates" / "chest.json").write_text(
        json.dumps({"variants": {"": {"model": "examplemod:block/chest"}}}))
    (assets / "models" / "block").mkdir(parents=True)
    (assets / "models" / "block" / "chest.json").write_text(
        json.dumps({"textures": {"particle": "examplemod:block/planks"}}))
    chest = {"type": "minecraft:item", "name": "examplemod:chest",
             "functions": [{"function": "minecraft:copy_name", "source": "block_entity"}]}
    build(src, {"chest": pool(chest, SURVIVES), "steel_block": pool(ITEM, SURVIVES)}, dirname="loot_table")
    out = convert(src, tmp_path / "out")
    kinds = {u.source: u.kind for u in out.unhandled}
    assert kinds["assets/examplemod/blockstates/chest.json"] == "code_drawn_block"
    assert kinds["data/examplemod/loot_table/blocks/chest.json"] == "owned_by_residue"
    assert "owned_by_residue" in SKIP_KINDS


# --- #299: function-level conditions and minecraft:loot on the block ---------

SLAB = "examplemod:steel_slab"
SLAB_STATES = {"type": {
    "bottom": "q.block_state('minecraft:vertical_half') == 'bottom'",
    "top": "q.block_state('minecraft:vertical_half') == 'top'",
    "double": None,
}}


def _block(ident, components=None):
    return {"format_version": "1.20.20", "minecraft:block": {
        "description": {"identifier": ident}, "components": dict(components or {"minecraft:friction": 0.6})}}


def _slab_table(block=SLAB):
    return pool({"type": "minecraft:item", "name": block}, SURVIVES, functions=[
        {"function": "minecraft:set_count", "add": False, "count": 2.0,
         "conditions": [{"condition": "minecraft:block_state_property", "block": block,
                         "properties": {"type": "double"}}]},
        {"function": "minecraft:explosion_decay"}])


def test_a_slab_count_for_a_double_slab_bedrock_cannot_have_never_applies(tmp_path):
    """Java's set_count 2 only applies when type=double; the converted slab is
    never double, so it drops one, and that is the default: nothing to wire."""
    blocks = {"blocks/steel_slab.json": _block(SLAB)}
    result = loot.convert(build(tmp_path, {"steel_slab": _slab_table()}), blocks=blocks,
                          java_states={SLAB: SLAB_STATES})
    assert result.unhandled == []
    entry = result.files["loot_tables/blocks/steel_slab.json"]["pools"][0]["entries"][0]
    assert entry == {"type": "item", "name": SLAB, "functions": [{"function": "explosion_decay"}]}
    assert "blocks/steel_slab.json" not in result.files


def test_a_conditioned_function_is_never_applied_unconditionally(tmp_path):
    # No converted block to test the state of: refused, not set_count 2.
    result = loot.convert(build(tmp_path, {"steel_slab": _slab_table()}))
    assert result.files == {}
    reason = result.unhandled[0].reason
    assert "type=double" in reason and "set_count" in reason


def test_a_block_without_that_state_refuses_the_table(tmp_path):
    blocks = {"blocks/steel_slab.json": _block(SLAB)}
    result = loot.convert(build(tmp_path, {"steel_slab": _slab_table()}), blocks=blocks, java_states={})
    assert result.files == {}
    assert "carries no Bedrock state for type" in result.unhandled[0].reason


def test_a_function_condition_other_than_block_state_is_refused(tmp_path):
    table = pool(ITEM, SURVIVES, functions=[{"function": "minecraft:set_count", "count": 3,
                                             "conditions": [{"condition": "minecraft:random_chance", "chance": 0.5}]}])
    blocks = {"blocks/steel_block.json": _block("examplemod:steel_block")}
    result = loot.convert(build(tmp_path, {"steel_block": table}), blocks=blocks)
    assert result.files == {}
    assert "random_chance" in result.unhandled[0].reason


def test_counts_per_reachable_state_go_on_permutations(tmp_path):
    petals = "examplemod:petals"
    states = {"amount": {"1": "q.block_state('examplemod:amount') == 1",
                         "2": "q.block_state('examplemod:amount') == 2"}}
    table = pool({"type": "minecraft:item", "name": petals}, SURVIVES, functions=[
        {"function": "minecraft:set_count", "count": n,
         "conditions": [{"condition": "minecraft:block_state_property", "block": petals,
                         "properties": {"amount": str(n)}}]} for n in (1, 2)])
    blocks = {"blocks/petals.json": _block(petals)}
    result = loot.convert(build(tmp_path, {"petals": table}), blocks=blocks, java_states={petals: states})
    assert result.unhandled == []
    block = result.files["blocks/petals.json"]["minecraft:block"]
    assert block["components"]["minecraft:loot"] == "loot_tables/blocks/petals.json"
    assert block["permutations"] == [{"condition": "q.block_state('examplemod:amount') == 2",
                                      "components": {"minecraft:loot": "loot_tables/blocks/petals.state1.json"}}]
    counts = [result.files[p]["pools"][0]["entries"][0]["functions"][0]
              for p in ("loot_tables/blocks/petals.json", "loot_tables/blocks/petals.state1.json")]
    assert counts == [{"function": "set_count", "count": 1}, {"function": "set_count", "count": 2}]


def test_a_block_that_drops_another_item_names_its_table(tmp_path):
    table = pool({"type": "minecraft:item", "name": "examplemod:root"}, SURVIVES,
                 functions=[{"function": "minecraft:set_count", "count": 4}])
    blocks = {"blocks/root_block.json": _block("examplemod:root_block"),
              "items/root.json": {"minecraft:item": {"description": {"identifier": "examplemod:root"}}}}
    result = loot.convert(build(tmp_path, {"root_block": table}), blocks=blocks)
    assert result.unhandled == []
    block = result.files["blocks/root_block.json"]
    assert block["minecraft:block"]["components"]["minecraft:loot"] == "loot_tables/blocks/root_block.json"
    assert block["minecraft:block"]["components"]["minecraft:friction"] == 0.6
    assert result.files["loot_tables/blocks/root_block.json"]["pools"][0]["entries"][0] == {
        "type": "item", "name": "examplemod:root",
        "functions": [{"function": "set_count", "count": 4}, {"function": "explosion_decay"}]}
    # The input is not changed in place.
    assert "minecraft:loot" not in blocks["blocks/root_block.json"]["minecraft:block"]["components"]
    assert any("minecraft:loot" in n for n in result.notes)


def test_a_drop_of_an_item_the_pack_lacks_is_not_wired(tmp_path):
    table = pool({"type": "minecraft:item", "name": "examplemod:gone"}, SURVIVES)
    blocks = {"blocks/box.json": _block("examplemod:box")}
    result = loot.convert(build(tmp_path, {"box": table}), blocks=blocks)
    assert result.files == {}
    assert "examplemod:gone" in result.unhandled[0].reason


def test_a_drop_of_air_names_bedrocks_empty_table(tmp_path):
    table = pool({"type": "minecraft:item", "name": "minecraft:air"}, SURVIVES)
    blocks = {"blocks/pot.json": _block("examplemod:pot")}
    result = loot.convert(build(tmp_path, {"pot": table}), blocks=blocks)
    assert result.unhandled == []
    assert result.files == {"blocks/pot.json": _block("examplemod:pot", {
        "minecraft:friction": 0.6, "minecraft:loot": "loot_tables/empty.json"})}
    assert any("loot_tables/empty.json" in n for n in result.notes)


def test_a_block_that_already_has_minecraft_loot_is_left_alone(tmp_path):
    table = pool({"type": "minecraft:item", "name": "minecraft:dirt"}, SURVIVES)
    blocks = {"blocks/soil.json": _block("examplemod:soil", {"minecraft:loot": "loot_tables/empty.json"})}
    result = loot.convert(build(tmp_path, {"soil": table}), blocks=blocks)
    assert "blocks/soil.json" not in result.files
    assert "loot_tables/blocks/soil.json" in result.files


def test_vanilla_drops_use_bedrock_ids(tmp_path, monkeypatch):
    from portkit.converters import recipes

    monkeypatch.setattr(recipes, "bedrock_item",
                        lambda ident: ("minecraft:noteblock", None) if ident == "minecraft:note_block" else (ident, None))
    table = pool({"type": "minecraft:item", "name": "minecraft:note_block"}, SURVIVES)
    blocks = {"blocks/horn.json": _block("examplemod:horn")}
    result = loot.convert(build(tmp_path, {"horn": table}), blocks=blocks)
    assert result.files["loot_tables/blocks/horn.json"]["pools"][0]["entries"][0]["name"] == "minecraft:noteblock"
    assert result.files["blocks/horn.json"]["minecraft:block"]["components"]["minecraft:loot"] == (
        "loot_tables/blocks/horn.json")


def test_a_vanilla_drop_bedrock_spells_with_data_gets_set_data(tmp_path, monkeypatch):
    from portkit.converters import recipes

    monkeypatch.setattr(recipes, "bedrock_item", lambda ident: ("minecraft:banner", 15)
                        if ident == "minecraft:white_banner" else (ident, None))
    table = pool({"type": "minecraft:item", "name": "minecraft:white_banner"}, SURVIVES)
    blocks = {"blocks/flag.json": _block("examplemod:flag")}
    result = loot.convert(build(tmp_path, {"flag": table}), blocks=blocks)
    entry = result.files["loot_tables/blocks/flag.json"]["pools"][0]["entries"][0]
    assert entry["functions"] == [{"function": "set_data", "data": 15}, {"function": "explosion_decay"}]


def test_a_vanilla_drop_bedrock_has_no_id_for_is_refused(tmp_path, monkeypatch):
    from portkit.converters import recipes

    monkeypatch.setattr(recipes, "bedrock_item", lambda ident: "no Bedrock id of its own")
    table = pool({"type": "minecraft:item", "name": "minecraft:tipped_arrow"}, SURVIVES)
    result = loot.convert(build(tmp_path, {"quiver": table}))
    assert result.files == {}
    assert "no Bedrock id" in result.unhandled[0].reason


def test_the_validator_wants_a_block_loot_table_to_exist(tmp_path):
    from portkit.validate.rules import validate_pack

    pack = tmp_path / "behavior_pack"
    (pack / "blocks").mkdir(parents=True)
    (pack / "blocks" / "a.json").write_text(json.dumps(_block("ex:a", {"minecraft:loot": "loot_tables/blocks/a.json"})))
    (pack / "blocks" / "b.json").write_text(json.dumps(_block("ex:b", {"minecraft:loot": "loot_tables/empty.json"})))
    report = validate_pack(pack)
    loot_findings = [f for f in report.findings if f.rule == "block.loot"]
    assert [f.path for f in loot_findings] == ["behavior_pack/blocks/a.json"]
    (pack / "loot_tables" / "blocks").mkdir(parents=True)
    (pack / "loot_tables" / "blocks" / "a.json").write_text(
        json.dumps({"pools": [{"rolls": 1, "entries": [{"type": "item", "name": "ex:a"}]}]}))
    assert [f for f in validate_pack(pack).findings if f.rule == "block.loot"] == []


def test_a_shortened_table_path_moves_the_blocks_reference():
    from portkit.model import ConversionResult
    from portkit.paths import shorten_paths

    long = "loot_tables/blocks/" + "x" * 120 + ".json"
    result = ConversionResult(files={long: {"pools": []},
                                     "blocks/x.json": _block("ex:x", {"minecraft:loot": long})})
    renames = shorten_paths(result)
    assert result.files["blocks/x.json"]["minecraft:block"]["components"]["minecraft:loot"] == renames[long]


# -- tools (#299, Alex's picks 2026-10-16) ------------------------------------

SILK_121 = {"condition": "minecraft:match_tool", "predicate": {"predicates": {"minecraft:enchantments": [
    {"enchantments": "minecraft:silk_touch", "levels": {"min": 1}}]}}}
SILK_120 = {"condition": "minecraft:match_tool", "predicate": {"enchantments": [
    {"enchantment": "minecraft:silk_touch", "levels": {"min": 1}}]}}
SHEARS = {"condition": "minecraft:match_tool", "predicate": {"items": "minecraft:shears"}}
SHEARS_TAG = {"condition": "minecraft:match_tool", "predicate": {"tag": "forge:shears"}}
IS_SHEARS = {"condition": "match_tool", "minecraft:match_tool_filter_any": ["minecraft:is_shears"]}


def _alternatives(*children):
    return {"type": "minecraft:block", "pools": [{"rolls": 1, "conditions": SURVIVES, "entries": [
        {"type": "minecraft:alternatives", "children": list(children)}]}]}


def _wired(result, name):
    block = result.files[f"blocks/{name}.json"]["minecraft:block"]["components"]["minecraft:loot"]
    return block, result.files.get(block)


@pytest.mark.parametrize("silk", [SILK_120, SILK_121])
def test_silk_touch_self_or_another_drop_is_the_other_drop_on_bedrock(tmp_path, silk):
    """Bedrock drops the block itself under Silk Touch, so the table only needs the other branch: exact."""
    table = _alternatives({"type": "minecraft:item", "name": "examplemod:ore", "conditions": [silk]},
                          {"type": "minecraft:item", "name": "minecraft:diamond"})
    blocks = {"blocks/ore.json": _block("examplemod:ore")}
    result = loot.convert(build(tmp_path, {"ore": table}), blocks=blocks)
    assert result.unhandled == []
    path, wired = _wired(result, "ore")
    assert wired == {"pools": [{"rolls": 1, "entries": [{
        "type": "item", "name": "minecraft:diamond", "functions": [{"function": "explosion_decay"}]}]}]}
    assert not any("approximated" in n for n in result.notes)


def test_a_drop_only_under_silk_touch_is_bedrocks_empty_table(tmp_path):
    table = pool({"type": "minecraft:item", "name": "examplemod:pane"}, [SILK_121])
    blocks = {"blocks/pane.json": _block("examplemod:pane")}
    result = loot.convert(build(tmp_path, {"pane": table}), blocks=blocks)
    assert result.unhandled == []
    assert result.files["blocks/pane.json"]["minecraft:block"]["components"]["minecraft:loot"] == (
        "loot_tables/empty.json")
    assert not any("approximated" in n for n in result.notes)


def test_a_shears_drop_becomes_a_match_tool_on_bedrocks_shears_tag(tmp_path):
    table = pool({"type": "minecraft:item", "name": "examplemod:bush"}, [SHEARS])
    blocks = {"blocks/bush.json": _block("examplemod:bush")}
    result = loot.convert(build(tmp_path, {"bush": table}), blocks=blocks)
    assert result.unhandled == []
    _, wired = _wired(result, "bush")
    assert wired["pools"][0]["entries"] == [{"type": "item", "name": "examplemod:bush", "conditions": [IS_SHEARS]}]
    note = next(n for n in result.notes if "approximated" in n)
    # Java's Silk Touch drop is nothing here; Bedrock's is the block itself.
    assert note.startswith("data/examplemod/loot_tables/blocks/bush.json: approximated loot (#299)")
    assert "Silk Touch" in note and "nothing" in note


def test_a_java_shears_tag_says_mod_shears_dont_count(tmp_path):
    table = pool({"type": "minecraft:item", "name": "examplemod:bush"}, [SHEARS_TAG])
    result = loot.convert(build(tmp_path, {"bush": table}))
    assert result.files["loot_tables/blocks/bush.json"]["pools"][0]["entries"][0]["conditions"] == [IS_SHEARS]
    assert any("forge:shears" in n and "minecraft:is_shears" in n for n in result.notes)


def test_shears_or_silk_touch_is_shears_on_bedrock(tmp_path):
    table = pool({"type": "minecraft:item", "name": "examplemod:vine"}, [
        {"condition": "minecraft:any_of", "terms": [SHEARS, SILK_121]}])
    result = loot.convert(build(tmp_path, {"vine": table}))
    assert result.files["loot_tables/blocks/vine.json"]["pools"][0]["entries"][0]["conditions"] == [IS_SHEARS]


def test_not_silk_touch_always_holds_on_bedrock(tmp_path):
    table = pool({"type": "minecraft:item", "name": "minecraft:stick"}, [
        {"condition": "minecraft:inverted", "term": SILK_120}])
    result = loot.convert(build(tmp_path, {"twig": table}))
    assert result.files["loot_tables/blocks/twig.json"]["pools"][0]["entries"][0] == {
        "type": "item", "name": "minecraft:stick"}


def test_a_shears_branch_before_another_drop_is_refused(tmp_path):
    """Bedrock can't say 'not shears', so the second branch can't be written."""
    table = _alternatives({"type": "minecraft:item", "name": "examplemod:grass", "conditions": [SHEARS]},
                          {"type": "minecraft:item", "name": "minecraft:wheat_seeds"})
    result = loot.convert(build(tmp_path, {"grass": table}))
    assert result.files == {}
    assert "tool is absent" in result.unhandled[0].reason


def test_not_shears_is_refused(tmp_path):
    table = pool({"type": "minecraft:item", "name": "minecraft:stick"}, [
        {"condition": "minecraft:inverted", "term": SHEARS}])
    result = loot.convert(build(tmp_path, {"twig": table}))
    assert "absent" in result.unhandled[0].reason


def test_a_tool_test_bedrock_cant_read_is_refused(tmp_path):
    table = pool(ITEM, [{"condition": "minecraft:match_tool", "predicate": {"tag": "examplemod:knives"}}])
    result = loot.convert(build(tmp_path, {"steel_block": table}))
    assert "examplemod:knives" in result.unhandled[0].reason


def test_two_pools_only_under_silk_touch_drop_nothing(tmp_path):
    table = {"pools": [
        {"rolls": 1, "conditions": [SILK_121], "entries": [{"type": "minecraft:item", "name": "examplemod:grass"}]},
        {"rolls": 1, "conditions": [SILK_121], "entries": [{"type": "minecraft:item", "name": "minecraft:stick"}]}]}
    blocks = {"blocks/grass.json": _block("examplemod:grass")}
    result = loot.convert(build(tmp_path, {"grass": table}), blocks=blocks)
    assert result.files["blocks/grass.json"]["minecraft:block"]["components"]["minecraft:loot"] == (
        "loot_tables/empty.json")


def test_an_empty_table_names_bedrocks_empty_table_only_on_a_converted_block(tmp_path):
    blocks = {"blocks/cake.json": _block("examplemod:cake")}
    result = loot.convert(build(tmp_path, {"cake": {"type": "minecraft:block"}, "gone": {"pools": []}}),
                          blocks=blocks)
    assert result.files["blocks/cake.json"]["minecraft:block"]["components"]["minecraft:loot"] == (
        "loot_tables/empty.json")
    [left] = result.unhandled
    assert left.source.endswith("gone.json") and "drops nothing" in left.reason


def _tier_mod(tmp_path, tables):
    mod = build(tmp_path, tables)
    tags = tmp_path / "data" / "minecraft" / "tags" / "blocks"
    (tags / "mineable").mkdir(parents=True)
    (tags / "needs_iron_tool.json").write_text(json.dumps({"values": ["examplemod:steel_block"]}))
    (tags / "mineable" / "pickaxe.json").write_text(json.dumps({"values": ["examplemod:steel_block"]}))
    return mod


def test_a_tier_tagged_block_drops_only_for_its_tool_of_that_tier(tmp_path):
    mod = _tier_mod(tmp_path, {"steel_block": pool(ITEM, SURVIVES)})
    blocks = {"blocks/steel_block.json": _block("examplemod:steel_block")}
    result = loot.convert(mod, blocks=blocks)
    assert result.unhandled == []
    _, wired = _wired(result, "steel_block")
    assert wired["pools"][0]["entries"] == [{
        "type": "item", "name": "examplemod:steel_block", "functions": [{"function": "explosion_decay"}],
        "conditions": [{"condition": "match_tool",
                        "minecraft:match_tool_filter_all": ["minecraft:is_tool", "minecraft:is_pickaxe"],
                        "minecraft:match_tool_filter_any": ["minecraft:iron_tier", "minecraft:diamond_tier",
                                                            "minecraft:netherite_tier"]}]}]
    note = next(n for n in result.notes if "approximated" in n)
    assert "needs_iron_tool" in note and "pickaxe" in note and "Silk Touch" in note


def test_a_tier_tagged_block_in_no_mineable_tag_is_residue(tmp_path):
    mod = build(tmp_path, {"steel_block": pool(ITEM, SURVIVES)})
    tags = tmp_path / "data" / "minecraft" / "tags" / "blocks"
    tags.mkdir(parents=True)
    (tags / "needs_stone_tool.json").write_text(json.dumps({"values": ["examplemod:steel_block"]}))
    result = loot.convert(mod, blocks={"blocks/steel_block.json": _block("examplemod:steel_block")})
    assert "no mineable tag" in result.unhandled[0].reason


def test_java_silk_touch_drop_is_read():
    block = "examplemod:steel_block"
    assert loot._java_silk_drop(pool(ITEM, [SILK_121]), block) is None
    assert loot._java_silk_drop(pool(ITEM, [SHEARS]), block) == "nothing"
    assert loot._java_silk_drop(pool({"type": "minecraft:item", "name": "minecraft:air"}), block) == "nothing"
    assert loot._java_silk_drop(pool(ITEM, functions=[{"function": "minecraft:set_count", "count": 4}]),
                                block) == "4 examplemod:steel_block"
    assert loot._java_silk_drop(_alternatives(
        {"type": "minecraft:item", "name": "examplemod:steel_block", "conditions": [SILK_120]},
        {"type": "minecraft:item", "name": "minecraft:diamond"}), block) is None


def test_the_validator_reads_match_tool_conditions(tmp_path):
    from portkit.validate.rules import validate_pack

    pack = tmp_path / "behavior_pack"
    (pack / "loot_tables" / "blocks").mkdir(parents=True)
    good = {"type": "item", "name": "ex:bush", "conditions": [IS_SHEARS]}
    bad = [{"type": "item", "name": "ex:a", "conditions": [{"condition": "random_chance", "chance": 0.5}]},
           {"type": "item", "name": "ex:b", "conditions": [{"condition": "match_tool", "predicate": {}}]},
           {"type": "item", "name": "ex:c", "conditions": [
               {"condition": "match_tool", "minecraft:match_tool_filter_any": []}]}]
    (pack / "loot_tables" / "blocks" / "ok.json").write_text(json.dumps({"pools": [{"rolls": 1, "entries": [good]}]}))
    for i, entry in enumerate(bad):
        (pack / "loot_tables" / "blocks" / f"bad{i}.json").write_text(
            json.dumps({"pools": [{"rolls": 1, "entries": [entry]}]}))
    report = validate_pack(pack)
    found = {f.path.rsplit("/", 1)[-1] for f in report.findings if f.rule == "loot.condition"}
    assert found == {"bad0.json", "bad1.json", "bad2.json"}
