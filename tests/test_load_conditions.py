"""Recipe and loot-table load conditions (#183).

Java loads a data file only when its load conditions hold: ``conditions``
(Forge), ``neoforge:conditions`` (NeoForge), ``fabric:load_conditions``
(Fabric). The conversion holds this mod, the mods it requires, and the platform;
a condition is decided against that, a mod config flag at its default cited
from the mod's source (``portkit/data/config_flag_defaults.json``), and
anything undecidable is residue, never a guess.
"""
import json
import re
import zipfile
from pathlib import Path

import pytest

from portkit import conditions, corpus, meta, pipeline
from portkit.conditions import LoadContext
from portkit.converters import convert_all, loot, recipes
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
     "flags": {"on_thing": {"default": True, "url": "https://example.invalid/Config.java#L1"},
               "off_thing": {"default": False, "url": "https://example.invalid/Config.java#L2"}}},
    {"mod": "examplemod", "version": "1.2.3", "condition": "examplemod:dust_enabled", "argument": None,
     "flags": {"": {"default": False, "url": "https://example.invalid/Config.java#L3"}}},
]}


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body))


def _mod(tmp_path, files: dict, loader="forge", mods=("examplemod",), requires=("mantle",),
         minecraft="1.20.1") -> SourceMod:
    root = tmp_path / "mod"
    for rel, body in files.items():
        _write(root, rel, body)
    return SourceMod(root=root, namespace="examplemod", loader=loader, minecraft=minecraft,
                     mods=None if mods is None else {m: "1.2.3" for m in mods},
                     requires=None if requires is None else frozenset(requires))


def _convert(mod, table=TABLE):
    context = LoadContext(mod, table=table)
    result = recipes.convert(mod, context=context)
    note = context.note()  # what convert_all adds, once per namespace
    if note:
        result.notes.append(note)
    return result, context


def _recipe(tmp_path, conds, key="conditions", loader="forge", lane="recipes", **kw):
    body = {**SHAPED, key: conds}
    mod = _mod(tmp_path, {f"data/examplemod/{lane}/thing.json": body}, loader=loader, **kw)
    return _convert(mod)


def _residue(result, kind="conditional_recipe"):
    return [u.reason for u in result.unhandled if u.kind == kind]


# -- each loader's format -----------------------------------------------------

def test_forge_mod_loaded_on_an_absent_mod_is_compat_residue(tmp_path):
    result, _ = _recipe(tmp_path, [{"type": "forge:mod_loaded", "modid": "quark"}])
    assert "recipes/thing.json" not in result.files
    [reason] = _residue(result)
    assert reason.startswith("compat for quark:")


def test_forge_mod_loaded_on_itself_or_a_required_mod_converts(tmp_path):
    result, _ = _recipe(tmp_path, [{"type": "forge:mod_loaded", "modid": "examplemod"},
                                   {"type": "forge:mod_loaded", "modid": "mantle"},
                                   {"type": "forge:mod_loaded", "modid": "minecraft"}])
    assert "recipes/thing.json" in result.files
    assert _residue(result) == []
    # The load condition is Java's business; the Bedrock recipe doesn't carry it.
    body = result.files["recipes/thing.json"]["minecraft:recipe_shaped"]
    assert "conditions" not in body


def test_neoforge_conditions(tmp_path):
    absent, _ = _recipe(tmp_path / "a", [{"type": "neoforge:mod_loaded", "modid": "create"}],
                        key="neoforge:conditions", loader="neoforge", lane="recipe")
    assert _residue(absent)[0].startswith("compat for create:")
    negated, _ = _recipe(tmp_path / "b", [{"type": "neoforge:not", "value": {"type": "neoforge:mod_loaded",
                                                                             "modid": "create"}}],
                         key="neoforge:conditions", loader="neoforge", lane="recipe")
    assert "recipes/thing.json" in negated.files


def test_fabric_load_conditions(tmp_path):
    all_of, _ = _recipe(tmp_path / "a", [{"condition": "fabric:all_mods_loaded",
                                          "values": ["examplemod", "spectrum"]}],
                        key="fabric:load_conditions", loader="fabric", lane="recipe")
    assert _residue(all_of)[0].startswith("compat for spectrum:")
    any_of, _ = _recipe(tmp_path / "b", [{"condition": "fabric:any_mods_loaded",
                                          "values": ["examplemod", "spectrum"]}],
                        key="fabric:load_conditions", loader="fabric", lane="recipe")
    assert "recipes/thing.json" in any_of.files


def test_a_key_the_jars_loader_does_not_read_is_left_alone(tmp_path):
    # fabric:load_conditions in a Forge jar: Forge never reads it, so neither do we.
    result, _ = _recipe(tmp_path, [{"condition": "fabric:all_mods_loaded", "values": ["spectrum"]}],
                        key="fabric:load_conditions")
    assert "recipes/thing.json" in result.files


# -- nested logic ---------------------------------------------------------------

def test_nested_and_or_not(tmp_path):
    conds = [{"type": "forge:or", "values": [
        {"type": "forge:mod_loaded", "modid": "quark"},
        {"type": "forge:and", "values": [
            {"type": "forge:not", "value": {"type": "forge:mod_loaded", "modid": "quark"}},
            {"type": "forge:true"},
        ]},
    ]}]
    passing, _ = _recipe(tmp_path / "a", conds)
    assert "recipes/thing.json" in passing.files
    failing, _ = _recipe(tmp_path / "b", [{"type": "forge:and", "values": [
        {"type": "forge:mod_loaded", "modid": "examplemod"},
        {"type": "forge:or", "values": [{"type": "forge:mod_loaded", "modid": "quark"},
                                        {"type": "forge:mod_loaded", "modid": "create"}]},
    ]}])
    [reason] = _residue(failing)
    assert reason.startswith("compat for quark, create:")


def test_false_beats_undecidable_under_and_and_true_beats_it_under_or(tmp_path):
    unknown = {"type": "othermod:whatever"}
    absent = {"type": "forge:mod_loaded", "modid": "quark"}
    result, _ = _recipe(tmp_path / "a", [unknown, absent])
    assert _residue(result)[0].startswith("compat for quark:")
    result, _ = _recipe(tmp_path / "b", [{"type": "forge:or", "values": [unknown, {"type": "forge:true"}]}])
    assert "recipes/thing.json" in result.files
    result, _ = _recipe(tmp_path / "c", [unknown])
    assert _residue(result) == ["unknown load condition othermod:whatever"]


# -- config flags ---------------------------------------------------------------

def test_flag_on_by_default_converts_with_one_note(tmp_path):
    mod = _mod(tmp_path, {
        "data/examplemod/recipes/a.json": {**SHAPED, "conditions": [{"type": "examplemod:flag", "flag": "on_thing"}]},
        "data/examplemod/recipes/b.json": {**SHAPED, "result": {"item": "minecraft:chest"},
                                           "conditions": [{"type": "examplemod:flag", "flag": "on_thing"}]},
    })
    result, context = _convert(mod)
    assert {"recipes/a.json", "recipes/b.json"} <= set(result.files)
    notes = [n for n in result.notes if "config_flag_defaults.json" in n]
    assert len(notes) == 1
    assert "examplemod 1.2.3 (on: examplemod:flag/on_thing)" in notes[0]


def test_flag_off_by_default_is_residue(tmp_path):
    result, _ = _recipe(tmp_path / "a", [{"type": "examplemod:flag", "flag": "off_thing"}])
    assert _residue(result) == ["disabled by default config: examplemod:flag/off_thing"]
    result, _ = _recipe(tmp_path / "b", [{"type": "examplemod:dust_enabled"}])
    assert _residue(result) == ["disabled by default config: examplemod:dust_enabled"]


def test_negated_flag_follows_the_default(tmp_path):
    # supplementaries' awning_*_2: loads only when flax is OFF.
    result, _ = _recipe(tmp_path / "a", [{"type": "forge:not", "value": {"type": "examplemod:flag",
                                                                         "flag": "on_thing"}}])
    assert "on_thing is off, and it is on by default" in _residue(result)[0]
    result, _ = _recipe(tmp_path / "b", [{"type": "forge:not", "value": {"type": "examplemod:flag",
                                                                         "flag": "off_thing"}}])
    assert "recipes/thing.json" in result.files
    assert any("(off: examplemod:flag/off_thing)" in n for n in result.notes)


def test_uncited_flag_and_uncited_version_are_unknown(tmp_path):
    result, _ = _recipe(tmp_path / "a", [{"type": "examplemod:flag", "flag": "never_cited"}])
    assert _residue(result) == ["unknown load condition examplemod:flag/never_cited"]
    other = {"mods": ("examplemod",)}
    root = tmp_path / "b"
    mod = _mod(root, {"data/examplemod/recipes/thing.json": {**SHAPED, "conditions": [
        {"type": "examplemod:flag", "flag": "on_thing"}]}}, **other)
    mod.mods = {"examplemod": "1.2.4"}  # a version nobody cited
    result, _ = _convert(mod)
    assert _residue(result) == ["unknown load condition examplemod:flag/on_thing"]


def test_another_mods_condition_type_is_unknown_not_guessed(tmp_path):
    result, _ = _recipe(tmp_path, [{"type": "inspirations:config", "prop": "cauldron_dyeing"}])
    assert _residue(result) == ["unknown load condition inspirations:config/cauldron_dyeing"]


# -- tags and items ---------------------------------------------------------------

def test_tag_conditions_against_the_conversion(tmp_path):
    files = {
        "data/examplemod/tags/items/filled.json": {"values": ["examplemod:tin_ingot"]},
        "data/examplemod/tags/items/others.json": {"values": [{"id": "othermod:x", "required": False}]},
    }
    for tag, expect in (("examplemod:filled", True), ("examplemod:others", False)):
        for cond in ({"type": "forge:not", "value": {"type": "forge:tag_empty", "tag": tag}},
                     {"type": "mantle:tag_filled", "tag": tag}):
            body = {**SHAPED, "conditions": [cond]}
            mod = _mod(tmp_path / f"{tag.split(':')[1]}{cond['type'].split(':')[1]}",
                       {**files, "data/examplemod/recipes/thing.json": body})
            result, _ = _convert(mod)
            assert ("recipes/thing.json" in result.files) is expect, (tag, cond)


def test_shared_tag_without_reference_data_is_undecidable(tmp_path):
    result, _ = _recipe(tmp_path, [{"type": "forge:not", "value": {"type": "forge:tag_empty",
                                                                   "tag": "forge:ingots/silver"}}])
    [reason] = _residue(result)
    assert reason.startswith("load condition can't be decided here: forge:tag_empty")


def test_tag_combination_filled(tmp_path):
    files = {
        "data/examplemod/tags/items/ores.json": {"values": ["examplemod:tin_ore", "examplemod:dense_ore"]},
        "data/examplemod/tags/items/dense.json": {"values": ["examplemod:dense_ore"]},
    }
    hit = {"type": "mantle:tag_combination_filled", "match": ["examplemod:ores", "examplemod:dense"]}
    miss = {"type": "mantle:tag_combination_filled", "match": "examplemod:dense", "ignore": "examplemod:ores"}
    for name, cond, expect in (("hit", hit, True), ("miss", miss, False)):
        mod = _mod(tmp_path / name, {**files, "data/examplemod/recipes/thing.json": {**SHAPED, "conditions": [cond]}})
        result, _ = _convert(mod)
        assert ("recipes/thing.json" in result.files) is expect


def test_item_exists(tmp_path):
    result, _ = _recipe(tmp_path / "a", [{"type": "forge:item_exists", "item": "twilightforest:fiery_blood"}])
    assert _residue(result)[0].startswith("compat for twilightforest:")
    result, _ = _recipe(tmp_path / "b", [{"type": "forge:item_exists", "item": "examplemod:thing"}])
    assert _residue(result)[0].startswith("load condition can't be decided here")


def test_without_metadata_another_mod_is_undecidable(tmp_path):
    result, _ = _recipe(tmp_path, [{"type": "forge:mod_loaded", "modid": "quark"}], mods=None, requires=None)
    assert _residue(result)[0].startswith("load condition can't be decided here")


# -- conditional wrapper files ----------------------------------------------------

def _wrapper(*entries):
    return {"type": "forge:conditional", "recipes": [{"conditions": c, "recipe": r} for c, r in entries]}


def test_wrapper_converts_the_entry_java_loads(tmp_path):
    blasting = {"type": "minecraft:blasting", "ingredient": {"item": "minecraft:clay_ball"},
                "result": "minecraft:brick", "cookingtime": 100}
    body = _wrapper(([{"type": "forge:mod_loaded", "modid": "ceramics"}], {"type": "ceramics:kiln"}),
                    ([{"type": "forge:true"}], blasting))
    mod = _mod(tmp_path, {"data/examplemod/recipes/kiln.json": body})
    result, _ = _convert(mod)
    out = result.files["recipes/kiln.json"]["minecraft:recipe_furnace"]
    assert out["input"] == "minecraft:clay_ball" and out["output"] == "minecraft:brick"
    assert out["description"]["identifier"] == "examplemod:kiln"
    assert any("forge:conditional wrapper" in n for n in result.notes)


def test_wrapper_with_no_loading_entry_is_compat_residue(tmp_path):
    body = _wrapper(([{"type": "forge:mod_loaded", "modid": "inspirations"}], SHAPED))
    result, _ = _convert(_mod(tmp_path, {"data/examplemod/recipes/w.json": body}))
    assert "recipes/w.json" not in result.files
    assert _residue(result)[0].startswith("compat for inspirations:")


def test_wrapper_with_an_undecidable_entry_first_is_residue(tmp_path):
    body = _wrapper(([{"type": "othermod:config", "prop": "x"}], {"type": "othermod:thing"}),
                    ([{"type": "forge:true"}], SHAPED))
    result, _ = _convert(_mod(tmp_path, {"data/examplemod/recipes/w.json": body}))
    assert "recipes/w.json" not in result.files
    assert _residue(result) == ["unknown load condition othermod:config/x"]


# -- loot tables, and conditions that are not load conditions ---------------------

TABLE_SELF = {"type": "minecraft:block", "pools": [{"rolls": 1, "entries": [
    {"type": "minecraft:item", "name": "examplemod:anvil"}],
    "conditions": [{"condition": "minecraft:survives_explosion"}]}]}


def test_loot_table_load_conditions(tmp_path):
    rel = "data/examplemod/loot_table/blocks/anvil.json"
    off = _mod(tmp_path / "off", {rel: {**TABLE_SELF, "fabric:load_conditions": [
        {"condition": "examplemod:dust_enabled"}]}}, loader="fabric")
    result = loot.convert(off, context=LoadContext(off, table=TABLE))
    assert result.files == {}
    assert _residue(result, "conditional_loot_table") == ["disabled by default config: examplemod:dust_enabled"]
    on = _mod(tmp_path / "on", {rel: {**TABLE_SELF, "fabric:load_conditions": [
        {"condition": "fabric:all_mods_loaded", "values": ["examplemod"]}]}}, loader="fabric")
    assert "loot_tables/blocks/anvil.json" in loot.convert(on, context=LoadContext(on, table=TABLE)).files


def test_loot_predicates_are_not_load_conditions(tmp_path):
    # Pool "conditions" are loot predicates (survives_explosion converts as
    # explosion_decay); a top-level "conditions" in a Forge loot table is no
    # load condition either, since Forge 1.20.1 reads none on loot tables.
    rel = "data/examplemod/loot_tables/blocks/anvil.json"
    mod = _mod(tmp_path, {rel: {**TABLE_SELF, "conditions": [{"type": "forge:mod_loaded", "modid": "quark"}]}})
    result = loot.convert(mod, context=LoadContext(mod, table=TABLE))
    assert "loot_tables/blocks/anvil.json" in result.files
    assert _residue(result, "conditional_loot_table") == []
    context = LoadContext(mod, table=TABLE)
    modifier = {"type": "moonlight:add_item", "conditions": [
        {"condition": "minecraft:match_tool", "predicate": {}},
        {"condition": "moonlight:iconditions", "values": [{"type": "examplemod:flag", "flag": "off_thing"}]}]}
    assert context.gate(modifier, "loot").passes is True
    assert context.assumed == {}


def test_loot_modifiers_and_trait_data_are_not_read(tmp_path):
    # Silent Gear trait and loot-modifier "conditions" live outside recipes/ and
    # loot_table*/blocks/; no converter decides them, so nothing changes.
    files = {
        "data/examplemod/loot_modifiers/x.json": {"type": "forge:add", "conditions": [{"condition": "x:y"}]},
        "data/examplemod/silentgear_traits/t.json": {"conditions": [{"type": "silentgear:material_ratio"}]},
    }
    mod = _mod(tmp_path, files)
    result = convert_all(mod)
    assert not [u for u in result.unhandled if u.kind.startswith("conditional")]


# -- metadata and the pipeline ---------------------------------------------------

def test_metadata_declares_mods_and_requirements():
    forge = meta.parse({"META-INF/mods.toml": b'''
[[mods]]
modId="tconstruct"
version="3.12.1.231"
[[dependencies.tconstruct]]
modId="mantle"
mandatory=true
[[dependencies.tconstruct]]
modId="jei"
mandatory=false
'''}, "tconstruct")
    assert forge.mods == {"tconstruct": "3.12.1.231"}
    assert forge.requires == ["mantle"]
    neo = meta.parse({"META-INF/neoforge.mods.toml": b'''
[[mods]]
modId="farmersdelight"
version="1.3.4"
[[dependencies.farmersdelight]]
modId="neoforge"
type="required"
[[dependencies.farmersdelight]]
modId="crafttweaker"
type="optional"
'''}, "farmersdelight")
    assert neo.requires == ["neoforge"]
    fabric = meta.parse({"fabric.mod.json": json.dumps({
        "id": "mythicmetals", "version": "0.24.6+1.21", "depends": {"owo": "*", "minecraft": "1.21.1"},
        "suggests": {"spectrum": "*"}}).encode()}, "mythicmetals")
    assert fabric.mods == {"mythicmetals": "0.24.6+1.21"}
    assert fabric.requires == ["minecraft", "owo"]


def test_pipeline_reads_metadata_and_notes_flags_once(tmp_path):
    src = tmp_path / "src"
    _write(src, "META-INF/mods.toml", None)
    (src / "META-INF/mods.toml").write_text('[[mods]]\nmodId="examplemod"\nversion="1.2.3"\n')
    _write(src, "data/examplemod/recipes/gated.json",
           {**SHAPED, "conditions": [{"type": "forge:mod_loaded", "modid": "quark"}]})
    _write(src, "data/examplemod/recipes/plain.json", {**SHAPED, "result": {"item": "minecraft:chest"}})
    run = pipeline.convert(src, tmp_path / "out", emit_addon=False)
    assert [u.kind for u in run.unhandled if u.source.endswith("gated.json")] == ["conditional_recipe"]
    assert (run.tree / "behavior_pack" / "recipes" / "plain.json").exists()
    assert not (run.tree / "behavior_pack" / "recipes" / "gated.json").exists()


# -- the shipped flag table -------------------------------------------------------

def test_shipped_flag_defaults_are_cited_and_version_keyed():
    entries = conditions.flag_entries()
    assert entries
    for entry in entries:
        assert entry["mod"] and entry["version"] and entry["condition"]
        assert re.fullmatch(r"[0-9a-f]{40}", entry["commit"]), entry["mod"]
        for flag, found in entry["flags"].items():
            assert isinstance(found["default"], bool), (entry["condition"], flag)
            assert entry["commit"] in found["url"] and re.search(r"#L\d+$", found["url"]), flag
    by = {(e["mod"], e["version"], e["condition"]): e for e in entries}
    supp = by[("supplementaries", "1.20-3.1.43", "supplementaries:flag")]["flags"]
    assert len(supp) >= 98 and all(f["default"] for f in supp.values())
    assert by[("mythicmetals", "0.24.6+1.21", "mythicmetals:dust_enabled")]["flags"][""]["default"] is False
    assert by[("mythicmetals", "0.24.6+1.21", "mythicmetals:nuggets_enabled")]["flags"][""]["default"] is True
    tinkers = by[("tconstruct", "3.12.1.231", "tconstruct:config")]["flags"]
    assert tinkers["force_integration_materials"]["default"] is False
    assert tinkers["gravel_to_flint"]["default"] is True
    for version in ("1.3.4", "26.1-3.6.28+refabricated"):
        assert by[("farmersdelight", version, "farmersdelight:vanilla_crates_enabled")]["flags"][""]["default"]


# -- the corpus: what used to ship and shouldn't ----------------------------------

_VANILLA = set(recipes._SUPPORTED) | {"minecraft:smithing_transform"}


def _absent_gated(jar: Path, declared: set[str]) -> list[str]:
    """Vanilla-type recipes the jar gates on a forge:mod_loaded of an absent mod."""
    found = []
    with zipfile.ZipFile(jar) as archive:
        for name in archive.namelist():
            parts = name.split("/")
            if len(parts) < 4 or parts[0] != "data" or parts[2] != "recipes" or not name.endswith(".json"):
                continue
            body = json.loads(archive.read(name))
            if not isinstance(body, dict) or body.get("type") not in _VANILLA:
                continue
            if _required_mods(body.get("conditions", [])) - declared:
                found.append(name)
    return found


def _required_mods(cond, negated=False) -> set[str]:
    """Mods a forge:mod_loaded asks for outside any forge:not (and/or walked)."""
    if isinstance(cond, list):
        return set().union(*(_required_mods(c, negated) for c in cond)) if cond else set()
    if not isinstance(cond, dict):
        return set()
    kind = cond.get("type")
    if kind == "forge:mod_loaded":
        return set() if negated else {cond.get("modid")}
    if kind == "forge:not":
        return _required_mods(cond.get("value"), not negated)
    if kind == "forge:and" and not negated:
        return _required_mods(cond.get("values", []), negated)
    return set()


@pytest.mark.realmods
@pytest.mark.parametrize("name, mod_id, expected, shipped", [
    # 43 vanilla-type recipes gated on absent mods; the 42 smelting/blasting
    # compat ones shipped before #183 (crafting/tree_fertilizer was already
    # residue for its upgrade_aquatic tag).
    ("create", "create", 43, ["data/create/recipes/blasting/ingot_aluminium_compat_ic2.json",
                              "data/create/recipes/smelting/tin_ingot_compat_thermal.json"]),
    # 18 shipped before #183 (the survey's count of 14 missed the 4 sconces
    # gated through forge:and).
    ("supplementaries", "supplementaries", 18, ["data/supplementaries/recipes/sconce_ender.json",
                                                "data/supplementaries/recipes/sack_3.json",
                                                "data/supplementaries/recipes/soap/dirty_glass.json"]),
])
def test_corpus_recipes_gated_on_absent_mods_no_longer_ship(tmp_path, name, mod_id, expected, shipped):
    mod = next(m for m in corpus.load() if m.name == name)
    jar = corpus.cached(mod)
    if jar is None:
        pytest.skip(f"{name} not cached (portkit corpus fetch)")
    gated = _absent_gated(jar, {mod_id, "minecraft", "forge"})
    assert len(gated) == expected
    assert set(shipped) <= set(gated)
    run = pipeline.convert(jar, tmp_path / "out", emit_addon=False)
    residue = {u.source: u for u in run.unhandled}
    for source in gated:
        assert residue[source].kind == "conditional_recipe", source
        assert residue[source].reason.startswith("compat for "), source
        stem = Path(source).stem
        assert not (run.tree / "behavior_pack" / "recipes" / f"{stem}.json").exists(), source
