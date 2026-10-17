"""Recipes name only items the pack ships, in Bedrock's own ids (#261)."""
import json

import pytest

from portkit.converters import recipes
from portkit.converters.recipe_unlock import ALWAYS_UNLOCKED
from portkit.data import java_items
from portkit.model import ConversionResult, SourceMod, Unhandled

# A slice of GeyserMC/mappings items.json, in its own shape.
GEYSER = {
    "minecraft:bricks": {"bedrock_identifier": "minecraft:brick_block", "is_block": True},
    "minecraft:stone": {"bedrock_identifier": "minecraft:stone", "is_block": True},
    "minecraft:spruce_planks": {"bedrock_identifier": "minecraft:spruce_planks", "bedrock_data": 1},
    "minecraft:white_bed": {"bedrock_identifier": "minecraft:bed", "is_block": True},
    "minecraft:red_bed": {"bedrock_identifier": "minecraft:bed", "bedrock_data": 14, "is_block": True},
    "minecraft:arrow": {"bedrock_identifier": "minecraft:arrow"},
    "minecraft:tipped_arrow": {"bedrock_identifier": "minecraft:arrow"},
    "minecraft:oak_trapdoor": {"bedrock_identifier": "minecraft:trapdoor"},
    "minecraft:nether_brick": {"bedrock_identifier": "minecraft:netherbrick"},
    "minecraft:nether_bricks": {"bedrock_identifier": "minecraft:nether_brick"},
    "minecraft:light": {"bedrock_identifier": "minecraft:light_block"},
}
BEDROCK = ["minecraft:arrow", "minecraft:bed", "minecraft:brick_block", "minecraft:nether_brick",
           "minecraft:netherbrick", "minecraft:spruce_planks", "minecraft:stick", "minecraft:stone",
           "minecraft:trapdoor"]


@pytest.fixture
def tables(tmp_path, monkeypatch):
    items = tmp_path / "vanilla-items.txt"
    items.write_text("# test\n" + "".join(f"{i}\n" for i in BEDROCK))
    monkeypatch.setenv("PORTKIT_VANILLA_ITEMS", str(items))
    table = tmp_path / "java-items.json"
    table.write_bytes(java_items.derive(json.dumps(GEYSER).encode()))
    monkeypatch.setenv("PORTKIT_JAVA_ITEMS", str(table))


def build(tmp_path, recipes_by_name, advancements=None):
    src = tmp_path / "mod" / "data" / "examplemod" / "recipe"
    src.mkdir(parents=True, exist_ok=True)
    for name, body in recipes_by_name.items():
        (src / f"{name}.json").write_text(json.dumps(body))
    for name, body in (advancements or {}).items():
        path = tmp_path / "mod" / "data" / "examplemod" / "advancement" / "recipes" / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body))
    return SourceMod(root=tmp_path / "mod", namespace="examplemod")


EMITTED = {"examplemod:frame": ("item", "items/frame.json", {})}


# -- the table ---------------------------------------------------------------

def test_derive_keeps_renames_data_on_shared_ids_and_the_ambiguous():
    table = json.loads(java_items.derive(json.dumps(GEYSER).encode()))
    renamed = table["renamed"]
    assert renamed["minecraft:bricks"] == {"id": "minecraft:brick_block"}
    # one Bedrock id for several Java items: the data value tells them apart
    assert renamed["minecraft:white_bed"] == {"id": "minecraft:bed", "data": 0}
    assert renamed["minecraft:red_bed"] == {"id": "minecraft:bed", "data": 14}
    # same id on both sides: not a rename, Geyser's legacy data isn't kept
    assert "minecraft:spruce_planks" not in renamed and "minecraft:stone" not in renamed
    # Java's tipped arrow is Bedrock's plain arrow: no id of its own
    assert table["ambiguous"] == {"minecraft:tipped_arrow": ["minecraft:arrow"]}
    assert "minecraft:arrow" not in renamed
    assert table["source"].startswith("GeyserMC/mappings@")


def test_fetch_checks_the_pin(tmp_path, monkeypatch):
    from portkit.data import ReferenceDataError

    raw = json.dumps(GEYSER).encode()

    class Response:
        def __init__(self, data):
            self.data = data

        def read(self):
            return self.data

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    with pytest.raises(ReferenceDataError, match="sha256 mismatch"):
        java_items.fetch(tmp_path, opener=lambda request, timeout: Response(raw))
    monkeypatch.setattr(java_items, "SHA256", java_items._sha256(java_items.derive(raw)))
    path, downloaded = java_items.fetch(tmp_path, opener=lambda request, timeout: Response(raw))
    assert downloaded and java_items.cached(tmp_path) == path
    monkeypatch.setenv("PORTKIT_REFERENCE_CACHE", str(tmp_path))
    assert java_items.table().lookup("minecraft:red_bed") == ("minecraft:bed", 14)


def test_without_the_table_ids_stay_as_written(tmp_path):
    assert java_items.table() is None
    assert recipes.bedrock_item("minecraft:bricks") == ("minecraft:bricks", None)
    assert recipes.bedrock_item("black_dye") == ("minecraft:black_dye", None)


def test_bedrock_item(tables):
    assert recipes.bedrock_item("minecraft:bricks") == ("minecraft:brick_block", None)
    assert recipes.bedrock_item("bricks") == ("minecraft:brick_block", None)  # Java's default namespace
    assert recipes.bedrock_item("minecraft:white_bed") == ("minecraft:bed", 0)
    assert recipes.bedrock_item("minecraft:stone") == ("minecraft:stone", None)
    assert recipes.bedrock_item("examplemod:frame") == ("examplemod:frame", None)
    # Java's item nether_brick is Bedrock's netherbrick, never Bedrock's block nether_brick
    assert recipes.bedrock_item("minecraft:nether_brick") == ("minecraft:netherbrick", None)
    assert "same as minecraft:arrow" in recipes.bedrock_item("minecraft:tipped_arrow")
    assert "isn't in Bedrock's vanilla item list" in recipes.bedrock_item("minecraft:light")


# -- the recipe converter ----------------------------------------------------

def test_crafting_takes_bedrock_ids_and_data(tmp_path, tables):
    mod = build(tmp_path, {
        "frame": {"type": "minecraft:crafting_shaped", "pattern": ["BB", "TT"],
                  "key": {"B": {"item": "minecraft:bricks"}, "T": "minecraft:oak_trapdoor"},
                  "result": {"item": "examplemod:frame", "count": 2}},
        "bed": {"type": "minecraft:crafting_shapeless",
                "ingredients": [{"item": "examplemod:frame"}, {"item": "red_bed"}],
                "result": {"item": "minecraft:white_bed"}},
    })
    result = recipes.convert(mod, emitted=EMITTED)
    assert result.unhandled == []
    shaped = result.files["recipes/frame.json"]["minecraft:recipe_shaped"]
    assert shaped["key"] == {"B": {"item": "minecraft:brick_block"}, "T": {"item": "minecraft:trapdoor"}}
    assert shaped["result"] == {"item": "examplemod:frame", "count": 2}
    shapeless = result.files["recipes/bed.json"]["minecraft:recipe_shapeless"]
    assert shapeless["ingredients"] == [{"item": "examplemod:frame"}, {"item": "minecraft:bed", "data": 14}]
    assert shapeless["result"] == {"item": "minecraft:bed", "data": 0}
    assert result.recipe_sources == {"recipes/frame.json": "data/examplemod/recipe/frame.json",
                                     "recipes/bed.json": "data/examplemod/recipe/bed.json"}


def test_furnace_ids_are_mapped_and_a_data_value_there_is_residue(tmp_path, tables):
    mod = build(tmp_path, {
        "fire": {"type": "minecraft:smelting", "ingredient": {"item": "minecraft:nether_bricks"},
                 "result": "minecraft:bricks"},
        "bed": {"type": "minecraft:smelting", "ingredient": {"item": "minecraft:red_bed"},
                "result": "minecraft:stone"},
    })
    result = recipes.convert(mod, emitted=EMITTED)
    furnace = result.files["recipes/fire.json"]["minecraft:recipe_furnace"]
    assert (furnace["input"], furnace["output"]) == ("minecraft:nether_brick", "minecraft:brick_block")
    assert "recipes/bed.json" not in result.files
    (entry,) = result.unhandled
    assert entry.source.endswith("bed.json") and entry.kind == "recipe"
    assert "data 14" in entry.reason


def test_an_ambiguous_id_is_residue_and_an_unknown_one_is_kept_with_a_note(tmp_path, tables):
    mod = build(tmp_path, {
        "tipped": {"type": "minecraft:crafting_shapeless", "ingredients": ["examplemod:frame"],
                   "result": {"item": "minecraft:tipped_arrow"}},
        "chain": {"type": "minecraft:crafting_shapeless", "ingredients": ["minecraft:chain"],
                  "result": {"item": "examplemod:frame"}},
    })
    result = recipes.convert(mod, emitted=EMITTED)
    assert [u.source for u in result.unhandled] == ["data/examplemod/recipe/tipped.json"]
    assert "no Bedrock id of its own" in result.unhandled[0].reason
    body = result.files["recipes/chain.json"]["minecraft:recipe_shapeless"]
    assert body["ingredients"] == [{"item": "minecraft:chain"}]
    assert any("minecraft:chain" in n and "kept as written" in n for n in result.notes)


def test_smithing_slots_are_mapped(tmp_path, tables):
    mod = build(tmp_path, {
        "up": {"type": "minecraft:smithing_transform", "template": {"item": "minecraft:stone"},
               "base": {"item": "minecraft:bricks"}, "addition": {"item": "examplemod:frame"},
               "result": {"item": "minecraft:oak_trapdoor"}},
    })
    result = recipes.convert(mod, emitted=EMITTED)
    body = result.files["recipes/up.json"]["minecraft:recipe_smithing_transform"]
    assert (body["base"], body["result"]) == ("minecraft:brick_block", "minecraft:trapdoor")


def test_unlock_items_are_bedrock_ids(tmp_path, tables):
    def has(item):
        return {"trigger": "minecraft:inventory_changed", "conditions": {"items": [{"items": [item]}]}}

    mod = build(tmp_path, {
        "frame": {"type": "minecraft:crafting_shapeless",
                  "ingredients": ["minecraft:oak_trapdoor", "minecraft:nether_brick"],
                  "result": {"item": "examplemod:frame"}},
    }, advancements={"frame": {
        "criteria": {"has_trapdoor": has("minecraft:oak_trapdoor"), "has_brick": has("minecraft:nether_brick")},
        "requirements": [["has_trapdoor", "has_brick"]],
        "rewards": {"recipes": ["examplemod:frame"]},
    }})
    result = recipes.convert(mod, emitted=EMITTED)
    body = result.files["recipes/frame.json"]["minecraft:recipe_shapeless"]
    assert body["unlock"] == [{"item": "minecraft:trapdoor"}, {"item": "minecraft:netherbrick"}]
    assert body["ingredients"] == [{"item": "minecraft:trapdoor"}, {"item": "minecraft:netherbrick"}]


# -- what the pack ships -----------------------------------------------------

def _recipe(ident, ingredients, result, unlock=None):
    return {"format_version": "1.20.10", "minecraft:recipe_shapeless": {
        "description": {"identifier": ident}, "tags": ["crafting_table"],
        "ingredients": [{"item": i} for i in ingredients],
        "unlock": unlock if unlock is not None else ALWAYS_UNLOCKED,
        "result": {"item": result}}}


def _item(ident):
    return {"format_version": "1.21.40", "minecraft:item": {"description": {"identifier": ident}}}


def test_a_recipe_naming_an_item_the_pack_lacks_goes_back_to_residue():
    result = ConversionResult(files={
        "items/frame.json": _item("examplemod:frame"),
        "items/gear.json": _item("othermod:gear"),  # another namespace of the jar
        "recipes/ok.json": _recipe("examplemod:ok", ["othermod:gear", "minecraft:stick"], "examplemod:frame"),
        "recipes/cake.json": _recipe("examplemod:cake", ["examplemod:frame"], "examplemod:cake"),
        "recipes/pick__a.json": _recipe("examplemod:pick__a", ["examplemod:frame"], "examplemod:frame"),
        "recipes/pick__b.json": _recipe("examplemod:pick__b", ["examplemod:gone"], "examplemod:frame"),
    }, recipe_sources={
        "recipes/ok.json": "data/examplemod/recipe/ok.json",
        "recipes/cake.json": "data/examplemod/recipe/cake.json",
        "recipes/pick__a.json": "data/examplemod/recipe/pick.json",
        "recipes/pick__b.json": "data/examplemod/recipe/pick.json",
    })
    recipes.drop_unshipped_recipes(result)
    assert sorted(p for p in result.files if p.startswith("recipes/")) == ["recipes/ok.json"]
    assert [(u.source, u.kind) for u in result.unhandled] == [
        ("data/examplemod/recipe/cake.json", "recipe"), ("data/examplemod/recipe/pick.json", "recipe")]
    assert result.unhandled[0].reason.startswith("names examplemod:cake, which the pack doesn't ship")
    # every file written from one source goes: a recipe is never narrowed
    assert "examplemod:gone" in result.unhandled[1].reason


def test_an_unlock_entry_the_pack_lacks_is_dropped():
    result = ConversionResult(files={
        "items/frame.json": _item("examplemod:frame"),
        "recipes/a.json": _recipe("examplemod:a", ["minecraft:stick"], "examplemod:frame",
                                  unlock=[{"item": "examplemod:gone"}, {"item": "minecraft:stick"}]),
        "recipes/b.json": _recipe("examplemod:b", ["minecraft:stick"], "examplemod:frame",
                                  unlock=[{"item": "examplemod:gone"}]),
    })
    recipes.drop_unshipped_recipes(result)
    assert result.unhandled == []
    assert result.files["recipes/a.json"]["minecraft:recipe_shapeless"]["unlock"] == [{"item": "minecraft:stick"}]
    assert result.files["recipes/b.json"]["minecraft:recipe_shapeless"]["unlock"] == ALWAYS_UNLOCKED
    assert any("recipes/b.json" in n and "AlwaysUnlocked" in n for n in result.notes)


def test_a_source_already_residue_gets_a_note_not_a_second_entry():
    entry = Unhandled("data/examplemod/recipe/root.json", "station_recipe", "ingredient examplemod:root is not converted")
    result = ConversionResult(files={
        "recipes/root.json": _recipe("examplemod:root", ["examplemod:root"], "minecraft:stick"),
    }, unhandled=[entry], recipe_sources={"recipes/root.json": "data/examplemod/recipe/root.json"})
    recipes.drop_unshipped_recipes(result)
    assert result.unhandled == [entry] and "recipes/root.json" not in result.files
    assert any(n.startswith("data/examplemod/recipe/root.json: crafting form names examplemod:root")
               for n in result.notes)


def test_a_block_withdrawn_for_its_texture_takes_its_recipes(tmp_path):
    """The pipeline checks after drop_untextured (tconstruct:blazewood, #260 side finding)."""
    from portkit.pipeline import convert

    root = tmp_path / "mod"
    a = root / "assets" / "examplemod"
    (a / "blockstates").mkdir(parents=True)
    (a / "models" / "block").mkdir(parents=True)
    (a / "blockstates" / "wood.json").write_text(json.dumps({"variants": {"": {"model": "examplemod:block/wood"}}}))
    # the texture file is missing, so the block is withdrawn after it converted
    (a / "models" / "block" / "wood.json").write_text(json.dumps(
        {"parent": "minecraft:block/cube_all", "textures": {"all": "examplemod:block/wood"}}))
    r = root / "data" / "examplemod" / "recipes"
    r.mkdir(parents=True)
    (r / "planks.json").write_text(json.dumps({
        "type": "minecraft:crafting_shapeless", "ingredients": [{"item": "examplemod:wood"}],
        "result": {"item": "minecraft:stick"}}))
    out = convert(root, tmp_path / "out", emit_addon=False)
    assert not (out.tree / "behavior_pack" / "recipes" / "planks.json").exists()
    reasons = {u.source: u.reason for u in out.unhandled}
    assert "names examplemod:wood, which the pack doesn't ship" in reasons["data/examplemod/recipes/planks.json"]
    # the block is residue of its own (no texture), so the recipe goes with it (#302)
    kinds = {u.source: u.kind for u in out.unhandled}
    assert kinds["assets/examplemod/blockstates/wood.json"] not in ("recipe", "unowned")
    assert kinds["data/examplemod/recipes/planks.json"] == "owned_by_residue"
