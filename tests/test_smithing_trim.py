"""Smithing trim recipes take only what Bedrock takes in each slot (#272).

Java ``minecraft:smithing_trim`` converts to Bedrock's ``recipe_smithing_trim``
when every slot is one Bedrock accepts (Mojang bedrock-samples Recipes.html;
minecraft.wiki's Bedrock item tag lists; BDS 1.26.52.3 probe runs), else it is
residue with the reason: no crafting stand-in, nothing invented (Alex,
2026-10-16, #268). A mod item Java's ``#minecraft:trimmable_armor`` holds gets
Bedrock's ``minecraft:trimmable_armors`` only when it is wearable armor in the
pack: on an item that isn't, the tag makes BDS refuse Mojang's own trim recipe.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from portkit.converters import recipes
from portkit.data import trim_items, vanilla_items
from portkit.model import ConversionResult, SourceMod, Unhandled
from portkit.validate.report import ValidationReport
from portkit.validate.rules import _check_smithing_trims

TEMPLATE = "minecraft:coast_armor_trim_smithing_template"
WEARABLE = {"minecraft:wearable": {"slot": "slot.armor.feet"}}
TAGGED = {"minecraft:tags": {"tags": ["minecraft:trimmable_armors"]}}
TRIMMABLE = "data/minecraft/tags/items/trimmable_armor.json"


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body))


def _trim(template=None, base=None, addition=None, **extra):
    recipe = {"type": "minecraft:smithing_trim",
              "template": template if template is not None else {"item": TEMPLATE},
              "base": base if base is not None else {"tag": "minecraft:trimmable_armor"},
              "addition": addition if addition is not None else {"item": "minecraft:quartz"}}
    recipe.update(extra)
    return recipe


def _mod(root: Path, recipe=None, *, tag_files=None, items=("steel", "boots", "cap")):
    for name in items:  # the mod's items, as the tag resolver finds them
        _write(root, f"assets/toy/models/item/{name}.json", {"parent": "item/generated"})
    _write(root, "data/toy/recipes/trim.json" if recipe is not None else "data/toy/recipes/other.json",
           recipe if recipe is not None else {"type": "minecraft:crafting_transmute"})
    for rel, values in (tag_files or {}).items():
        _write(root, rel, {"values": values})
    return SourceMod(root=root, namespace="toy", loader="forge", minecraft="1.20.1")


def _body(ident, **components):
    return {"format_version": "1.20.10", "minecraft:item": {
        "description": {"identifier": ident}, "components": {"minecraft:max_stack_size": 1, **components}}}


def _emitted(**bodies):
    return {f"toy:{name}": ("item", f"items/{name}.json", body) for name, body in bodies.items()}


def _convert(tmp_path, recipe=None, emitted=None, **kw):
    result = recipes.convert(_mod(tmp_path, recipe, **kw), emitted=emitted)
    return result, [u.reason for u in result.unhandled]


@pytest.fixture(autouse=True)
def _no_reference(tmp_path, monkeypatch):
    # Tag data only from the jar (and each test's own reference dir).
    monkeypatch.setenv("PORTKIT_TAG_REFERENCE", str(tmp_path / "no-reference"))


# --- the data -----------------------------------------------------------------------

def test_the_lists_are_the_cited_ones():
    table = trim_items.VANILLA_TRIM_ITEMS
    assert (len(table["template"]), len(table["base"]), len(table["addition"])) == (18, 25, 11)
    assert table["addition"]["minecraft:resin_brick"].startswith("minecraft.wiki Resin Brick (oldid=3734929)")
    assert table["base"]["minecraft:turtle_helmet"].startswith(
        "minecraft.wiki Item tag (Bedrock Edition) (oldid=3758407)")
    for items in table.values():
        for ident, source in items.items():
            assert ident.startswith("minecraft:") and source


@pytest.mark.parametrize("slot,ident", [
    ("base", "minecraft:stick"), ("base", "minecraft:netherite_sword"), ("base", "minecraft:wolf_armor"),
    ("base", "minecraft:diamond_horse_armor"), ("base", "minecraft:elytra"),
    ("base", "minecraft:copper_boots"),  # not in the cited tag list (BDS loads it; the slot needs the tag)
    ("template", "minecraft:stick"), ("template", "minecraft:netherite_upgrade_smithing_template"),
    ("addition", "minecraft:stick"), ("addition", "minecraft:coal"),
])
def test_vanilla_items_outside_the_slot_tag_are_refused(slot, ident):
    why = trim_items.vanilla_refusal(slot, "item", ident)
    assert why.startswith(f"{slot} {ident} is not") and trim_items.WIKI_SOURCE in why


def test_a_tag_must_be_the_slots_own():
    for slot, tag in trim_items.TRIM_SLOT_TAGS.items():
        assert trim_items.vanilla_refusal(slot, "tag", tag) is None
    assert trim_items.vanilla_refusal("base", "tag", "minecraft:planks").startswith(
        "base tag minecraft:planks is not minecraft:trimmable_armors")
    assert trim_items.vanilla_refusal("base", "tag", "minecraft:trim_materials") is not None


@pytest.mark.realmods
def test_every_listed_item_is_a_bedrock_vanilla_item(monkeypatch):
    """Checked against bedrock-samples mojang-items.json in the real reference cache."""
    known = vanilla_items.ids()
    if known is None:
        pytest.skip("Bedrock vanilla item list not cached (portkit reference fetch)")
    for items in trim_items.VANILLA_TRIM_ITEMS.values():
        assert set(items) <= known


# --- the converter ------------------------------------------------------------------

def test_vanilla_slot_tags_convert_to_bedrocks(tmp_path):
    result, why = _convert(tmp_path, _trim({"tag": "minecraft:trim_templates"}, {"tag": "minecraft:trimmable_armor"},
                                           {"tag": "minecraft:trim_materials"}))
    assert why == []
    body = result.files["recipes/trim.json"][recipes.TRIM]
    assert body == {"description": {"identifier": "toy:trim"}, "tags": ["smithing_table"],
                    "template": {"tag": "minecraft:trim_templates"}, "base": {"tag": "minecraft:trimmable_armors"},
                    "addition": {"tag": "minecraft:trim_materials"}}
    assert result.recipe_sources["recipes/trim.json"] == "data/toy/recipes/trim.json"


def test_bare_string_tags_convert_the_same(tmp_path):
    result, why = _convert(tmp_path, _trim("#minecraft:trim_templates", "#minecraft:trimmable_armor",
                                           "#minecraft:trim_materials"))
    assert why == [] and result.files["recipes/trim.json"][recipes.TRIM]["base"] == {"tag": "minecraft:trimmable_armors"}


def test_vanilla_items_convert(tmp_path):
    result, why = _convert(tmp_path, _trim(base={"item": "minecraft:diamond_boots"},
                                           addition="minecraft:resin_brick"))
    assert why == []
    body = result.files["recipes/trim.json"][recipes.TRIM]
    assert (body["template"], body["base"], body["addition"]) == (TEMPLATE, "minecraft:diamond_boots",
                                                                 "minecraft:resin_brick")


@pytest.mark.parametrize("recipe,start", [
    (_trim(base={"item": "minecraft:stick"}), "trim base minecraft:stick is not trimmable armor in Bedrock"),
    (_trim(template={"item": "minecraft:stick"}), "trim template minecraft:stick is not a trim template"),
    (_trim(addition={"item": "toy:steel"}),
     "trim addition toy:steel is this pack's own item, and a Bedrock add-on can't register a trim material"),
    (_trim(template={"item": "toy:pattern"}),
     "trim template toy:pattern is this pack's own item, and a Bedrock add-on can't register a trim pattern"),
    (_trim(pattern="toy:stripes"), "trim pattern 'toy:stripes' is not a vanilla trim pattern"),
    (_trim(pattern="minecraft:bolt"), "trim pattern minecraft:bolt is fixed by the recipe"),
])
def test_what_bedrock_refuses_is_residue_with_the_reason(tmp_path, recipe, start):
    result, why = _convert(tmp_path, recipe)
    assert "recipes/trim.json" not in result.files
    assert len(why) == 1 and why[0].startswith(start), why
    assert why[0].endswith("not written, and not rewritten as another recipe")


def test_another_tag_in_a_slot_is_residue(tmp_path):
    result, why = _convert(tmp_path, _trim(base={"tag": "minecraft:planks"}))
    assert "recipes/trim.json" not in result.files
    assert why[0].startswith("trim base tag minecraft:planks is not minecraft:trimmable_armor and means more "
                             "than one item")


def test_a_jar_replacing_the_java_tag_is_residue(tmp_path):
    root = tmp_path / "mod"
    mod = _mod(root, _trim())
    _write(root, TRIMMABLE, {"replace": True, "values": ["toy:boots"]})
    result = recipes.convert(mod)
    assert "recipes/trim.json" not in result.files
    assert result.unhandled[0].reason.startswith("trim base tag minecraft:trimmable_armor: the jar's own file "
                                                 "replaces Java's tag")


def test_a_pattern_matching_its_template_converts(tmp_path):
    result, why = _convert(tmp_path, _trim(pattern="minecraft:coast"))
    assert why == [] and "pattern" not in result.files["recipes/trim.json"][recipes.TRIM]


def test_a_missing_slot_is_residue(tmp_path):
    recipe = _trim()
    del recipe["addition"]
    result, why = _convert(tmp_path, recipe)
    assert result.files == {} and why[0].startswith("trim recipe has no addition")


def test_the_mods_share_of_a_material_tag_is_noted(tmp_path):
    result, why = _convert(tmp_path, _trim(addition={"tag": "minecraft:trim_materials"}),
                           tag_files={"data/minecraft/tags/items/trim_materials.json": ["toy:steel"]})
    assert why == []
    assert any("toy:steel from this mod can't be a trim material" in n for n in result.notes)
    assert not [p for p in result.files if p.startswith("items/")]  # never tagged trim_materials


def test_a_wearable_base_named_by_the_recipe_carries_the_tag(tmp_path):
    emitted = _emitted(boots=_body("toy:boots", **WEARABLE))
    result, why = _convert(tmp_path, _trim(base={"item": "toy:boots"}), emitted=emitted)
    assert why == []
    item = result.files["items/boots.json"]
    assert item["minecraft:item"]["components"]["minecraft:tags"]["tags"] == ["minecraft:trimmable_armors"]
    assert item["format_version"] == "1.20.50"


# --- Java's #minecraft:trimmable_armor --------------------------------------------------

def test_java_trimmable_armor_tags_wearable_items_only(tmp_path):
    emitted = _emitted(boots=_body("toy:boots", **WEARABLE), cap=_body("toy:cap"))
    result, _ = _convert(tmp_path, emitted=emitted,
                         tag_files={TRIMMABLE: ["toy:boots", "toy:cap", "other:hat"]})
    boots = result.files["items/boots.json"]["minecraft:item"]["components"]["minecraft:tags"]["tags"]
    assert boots == ["minecraft:trimmable_armors"]
    assert "items/cap.json" not in result.files  # not armor: untouched
    assert TRIMMABLE in result.consumed
    notes = " | ".join(result.notes)
    assert f"1 item(s) Java's #minecraft:trimmable_armor holds ({TRIMMABLE}) carry" in notes
    assert f"({TRIMMABLE}: toy:cap) aren't armor in this pack" in notes


def test_no_wearable_member_leaves_the_items_and_the_tag_file_alone(tmp_path):
    result, _ = _convert(tmp_path, emitted=_emitted(cap=_body("toy:cap")), tag_files={TRIMMABLE: ["toy:cap"]})
    assert not [p for p in result.files if p.startswith("items/")]
    assert TRIMMABLE not in result.consumed
    assert any("aren't armor in this pack" in n for n in result.notes)


def test_java_1_21_nesting_counts(tmp_path, monkeypatch):
    ref = tmp_path / "ref"
    _write(ref, "vanilla-1.21.1.json", {"set": "vanilla-1.21.1", "tags": {
        "minecraft:trimmable_armor": ["#minecraft:foot_armor"],
        "minecraft:foot_armor": ["minecraft:iron_boots"]}})
    _write(ref, "neoforge-1.21.1.json", {"set": "neoforge-1.21.1", "tags": {}})
    monkeypatch.setenv("PORTKIT_TAG_REFERENCE", str(ref))
    root = tmp_path / "mod"
    _write(root, "assets/toy/models/item/boots.json", {"parent": "item/generated"})
    _write(root, "data/minecraft/tags/item/foot_armor.json", {"values": ["toy:boots"]})
    _write(root, "data/toy/recipe/other.json", {"type": "minecraft:crafting_transmute"})
    mod = SourceMod(root=root, namespace="toy", loader="neoforge", minecraft="1.21.1")
    result = recipes.convert(mod, emitted=_emitted(boots=_body("toy:boots", **WEARABLE)))
    assert result.files["items/boots.json"]["minecraft:item"]["components"]["minecraft:tags"]["tags"] == [
        "minecraft:trimmable_armors"]
    assert "data/minecraft/tags/item/foot_armor.json" in result.consumed


# --- the withdraw pass --------------------------------------------------------------

def _pack_recipe(base, ident="toy:trim"):
    return {"format_version": "1.20.10", recipes.TRIM: {
        "description": {"identifier": ident}, "tags": ["smithing_table"],
        "template": TEMPLATE, "base": base, "addition": "minecraft:quartz"}}


def test_withdraw_refuses_a_base_that_isnt_armor_with_the_tag():
    result = ConversionResult(files={
        "items/cap.json": _body("toy:cap"),
        "items/sock.json": _body("toy:sock", **WEARABLE),
        "items/boots.json": _body("toy:boots", **WEARABLE, **TAGGED),
        "recipes/cap.json": _pack_recipe("toy:cap", "toy:cap_trim"),
        "recipes/sock.json": _pack_recipe("toy:sock", "toy:sock_trim"),
        "recipes/boots.json": _pack_recipe("toy:boots", "toy:boots_trim"),
        "recipes/vanilla.json": _pack_recipe({"tag": "minecraft:trimmable_armors"}, "toy:vanilla"),
        "recipes/elsewhere.json": _pack_recipe("other:boots", "toy:elsewhere"),
    })
    result.recipe_sources = {"recipes/cap.json": "data/toy/recipes/cap.json"}
    recipes.withdraw_unacceptable_trims(result)
    assert sorted(p for p in result.files if p.startswith("recipes/")) == [
        "recipes/boots.json", "recipes/elsewhere.json", "recipes/vanilla.json"]
    reasons = {u.source: u.reason for u in result.unhandled}
    assert reasons["data/toy/recipes/cap.json"].startswith("trim base toy:cap has no minecraft:wearable")
    assert reasons["recipes/sock.json"].startswith("trim base toy:sock doesn't carry minecraft:trimmable_armors")
    assert "items/cap.json" in result.files  # the item stays; only the recipe goes


def test_withdraw_notes_a_source_already_residue():
    result = ConversionResult(files={"items/cap.json": _body("toy:cap"), "recipes/cap.json": _pack_recipe("toy:cap")})
    result.recipe_sources = {"recipes/cap.json": "data/toy/recipes/cap.json"}
    result.unhandled.append(Unhandled("data/toy/recipes/cap.json", "recipe", "already"))
    recipes.withdraw_unacceptable_trims(result)
    assert len(result.unhandled) == 1 and "recipes/cap.json" not in result.files
    assert any(n.startswith("data/toy/recipes/cap.json: trim base toy:cap") for n in result.notes)


# --- the validator ------------------------------------------------------------------

def _validate(tmp_path, files):
    pack = tmp_path / "behavior_pack"
    for rel, body in files.items():
        _write(pack, rel, body)
    report = ValidationReport()
    _check_smithing_trims(report, pack, "behavior_pack")
    return sorted((f.path, f.rule, f.severity, f.message) for f in report.findings)


def test_validator_checks_every_slot(tmp_path):
    found = _validate(tmp_path, {
        "items/boots.json": _body("toy:boots", **WEARABLE, **TAGGED),
        "items/steel.json": _body("toy:steel"),
        "blocks/anvil.json": {"format_version": "1.21.40", "minecraft:block": {
            "description": {"identifier": "toy:anvil"}, "components": {}}},
        "recipes/ok.json": _pack_recipe("toy:boots"),
        "recipes/vanilla.json": _pack_recipe("minecraft:diamond_boots"),
        "recipes/objects.json": {"format_version": "1.20.10", recipes.TRIM: {
            "template": {"item": TEMPLATE}, "base": {"tag": "minecraft:trimmable_armors"},
            "addition": {"item": "minecraft:resin_brick"}}},
        "recipes/stick.json": _pack_recipe("minecraft:stick"),
        "recipes/block.json": _pack_recipe("toy:anvil"),
        "recipes/notarmor.json": _pack_recipe("toy:steel"),
        "recipes/elsewhere.json": _pack_recipe("other:boots"),  # not this pack's: other rules
        "recipes/material.json": {"format_version": "1.20.10", recipes.TRIM: {
            "template": {"tag": "minecraft:trim_materials"}, "base": "minecraft:iron_boots",
            "addition": "toy:steel"}},
    })
    expected = [
        ("block.json", "trim base toy:anvil is a block, and the base must be armor"),
        ("material.json", "trim addition toy:steel is this pack's own item, and a Bedrock add-on can't register "
                          "a trim material"),
        ("material.json", "trim template tag minecraft:trim_materials is not minecraft:trim_templates"),
        ("notarmor.json", "trim base toy:steel has no minecraft:wearable, so it isn't armor in Bedrock"),
        ("stick.json", "trim base minecraft:stick is not trimmable armor in Bedrock"),
    ]
    assert len(found) == len(expected), found
    for (path, rule, severity, message), (name, start) in zip(found, expected):
        assert (path, rule, severity) == (f"behavior_pack/recipes/{name}", "recipe.smithing_trim", "error")
        assert message.startswith(start), message


def test_validator_refuses_trim_tags_that_break_mojangs_recipe(tmp_path):
    found = _validate(tmp_path, {
        "items/pattern.json": _body("toy:pattern", **{"minecraft:tags": {"tags": ["minecraft:trim_templates"]}}),
        "items/steel.json": _body("toy:steel", **{"minecraft:tags": {"tags": ["minecraft:trim_materials"]}}),
        "items/cap.json": _body("toy:cap", **TAGGED),
        "items/boots.json": _body("toy:boots", **WEARABLE, **TAGGED),
        "items/plain.json": _body("toy:plain", **{"minecraft:tags": {"tags": ["toy:shiny"]}}),
    })
    assert [(f[0], f[1], f[3].split(" ")[0]) for f in found] == [
        ("behavior_pack/items/cap.json", "item.trim_tag", "toy:cap"),
        ("behavior_pack/items/pattern.json", "item.trim_tag", "toy:pattern"),
        ("behavior_pack/items/steel.json", "item.trim_tag", "toy:steel")]
    assert all(f[2] == "error" for f in found)
