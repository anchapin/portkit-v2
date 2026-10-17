"""Tags whose members are mostly this mod's blocks (Create's stone_types).

``create:stone_types/granite`` holds 14 Create blocks (cut granite, its stairs,
walls, pillar, ...) and ``minecraft:granite``. Once those blocks convert, its 19
stonecutting recipes would each be written once per member (15 files each)
under #161's expansion. Instead the mod's blocks carry the tag through their
replacing block_placer item (the #162 pattern), the recipe takes the tag once,
and only the member that can't carry it (the vanilla item) gets its own recipe.

Also the offline nested-tag fix: without vanilla tag data, a mod that adds to a
vanilla tag (its own ``minecraft:oak_logs``) may be adding to one Bedrock's
``minecraft:logs`` holds, so ``minecraft:logs`` doesn't pass straight through.
"""
import json
from pathlib import Path

from portkit.converters import recipes
from portkit.model import SourceMod

TAG = "examplemod:stone_types/granite"
BLOCKS = ("cut_granite", "cut_granite_stairs", "cut_granite_wall")


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body))


def _mod(tmp_path, recipe, members, *, extra_files=()):
    root = tmp_path / "mod"
    _write(root, "data/examplemod/recipes/cut_granite_slab_from_stone_types.json", recipe)
    _write(root, "data/examplemod/tags/items/stone_types/granite.json", {"values": list(members)})
    for name in BLOCKS + ("cut_granite_slab",):
        _write(root, f"assets/examplemod/blockstates/{name}.json",
               {"variants": {"": {"model": f"examplemod:block/{name}"}}})
    for rel, body in extra_files:
        _write(root, rel, body)
    return SourceMod(root=root, namespace="examplemod", loader="forge", minecraft="1.20.1")


def _emitted(blocks=BLOCKS + ("cut_granite_slab",), both=()):
    found = {}
    for name in blocks:
        ident = f"examplemod:{name}"
        found[ident] = ("block", f"blocks/{name}.json", {"minecraft:block": {"description": {"identifier": ident}}})
    for name in both:
        ident = f"examplemod:{name}"
        # emitted_definitions gives a block with its own item file the item file (#302 pick 2).
        found[ident] = ("block_and_item", f"items/{name}.json",
                        {"format_version": "1.20.10",
                         "minecraft:item": {"description": {"identifier": ident}, "components": {}}})
    return found


def _stonecutting(tag=TAG):
    return {"type": "minecraft:stonecutting", "ingredient": {"tag": tag},
            "result": "examplemod:cut_granite_slab", "count": 2}


def _recipes(result):
    return {k: v for k, v in result.files.items() if k.startswith("recipes/")}


MEMBERS = [f"examplemod:{b}" for b in BLOCKS] + ["minecraft:granite"]


def test_the_blocks_carry_the_tag_and_the_vanilla_member_gets_one_recipe(tmp_path):
    result = recipes.convert(_mod(tmp_path, _stonecutting(), MEMBERS), emitted=_emitted())
    files = _recipes(result)
    assert set(files) == {"recipes/cut_granite_slab_from_stone_types.json",
                          "recipes/cut_granite_slab_from_stone_types__minecraft_granite.json"}
    body = files["recipes/cut_granite_slab_from_stone_types.json"]["minecraft:recipe_shapeless"]
    assert body["tags"] == ["stonecutter"]
    assert body["ingredients"] == [{"tag": TAG}]
    assert body["result"] == {"item": "examplemod:cut_granite_slab", "count": 2}
    granite = files["recipes/cut_granite_slab_from_stone_types__minecraft_granite.json"]["minecraft:recipe_shapeless"]
    assert granite["ingredients"] == [{"item": "minecraft:granite"}]
    for name in BLOCKS:
        item = result.files[f"items/{name}.json"]["minecraft:item"]
        assert item["components"]["minecraft:block_placer"] == {
            "block": f"examplemod:{name}", "replace_block_item": True}
        assert item["components"]["minecraft:tags"] == {"tags": [TAG]}
    assert result.unhandled == []
    assert any("got their own recipe" in note for note in result.notes)


def test_without_a_vanilla_member_one_recipe_takes_the_tag(tmp_path):
    members = [f"examplemod:{b}" for b in BLOCKS]
    result = recipes.convert(_mod(tmp_path, _stonecutting(), members), emitted=_emitted())
    assert set(_recipes(result)) == {"recipes/cut_granite_slab_from_stone_types.json"}


def test_a_block_with_its_own_item_carries_the_tag_on_its_item_file(tmp_path):
    """#302 pick 2: the item file of a block that has one carries the tag."""
    result = recipes.convert(_mod(tmp_path, _stonecutting(), MEMBERS),
                             emitted=_emitted(blocks=("cut_granite", "cut_granite_stairs", "cut_granite_slab"),
                                              both=("cut_granite_wall",)))
    assert set(_recipes(result)) == {
        "recipes/cut_granite_slab_from_stone_types.json",
        "recipes/cut_granite_slab_from_stone_types__minecraft_granite.json"}
    wall = result.files["items/cut_granite_wall.json"]["minecraft:item"]
    assert wall["components"]["minecraft:tags"] == {"tags": [TAG]}
    assert "minecraft:block_placer" not in wall["components"]


def test_one_mod_member_and_a_vanilla_one_keep_one_recipe_each(tmp_path):
    """No fewer files with a tag, so the per-member form stays."""
    members = ["examplemod:cut_granite", "minecraft:granite"]
    result = recipes.convert(_mod(tmp_path, _stonecutting(), members), emitted=_emitted())
    assert set(_recipes(result)) == {
        "recipes/cut_granite_slab_from_stone_types__examplemod_cut_granite.json",
        "recipes/cut_granite_slab_from_stone_types__minecraft_granite.json"}
    assert not any(k.startswith("items/") for k in result.files)


def test_a_multi_slot_tag_with_a_vanilla_member_stays_residue(tmp_path):
    recipe = {"type": "minecraft:crafting_shaped", "pattern": ["GG"], "key": {"G": {"tag": TAG}},
              "result": {"item": "examplemod:cut_granite_slab"}}
    result = recipes.convert(_mod(tmp_path, recipe, MEMBERS), emitted=_emitted())
    assert _recipes(result) == {}
    assert TAG in result.unhandled[0].reason


def test_a_member_not_converted_keeps_the_recipe_residue(tmp_path):
    result = recipes.convert(_mod(tmp_path, _stonecutting(), MEMBERS),
                             emitted=_emitted(blocks=("cut_granite", "cut_granite_slab")))
    assert _recipes(result) == {}
    assert "not converted: examplemod:cut_granite_stairs, examplemod:cut_granite_wall" in result.unhandled[0].reason


# -- offline nested vanilla tags (#162 follow-up) ----------------------------
def _logs_mod(tmp_path, *extra_files):
    root = tmp_path / "logs"
    _write(root, "data/examplemod/recipes/thing.json", {
        "type": "minecraft:crafting_shapeless", "ingredients": [{"tag": "minecraft:logs"}],
        "result": {"item": "minecraft:stick"}})
    _write(root, "assets/examplemod/blockstates/my_log.json", {"variants": {"": {"model": "examplemod:block/my_log"}}})
    for rel, body in extra_files:
        _write(root, rel, body)
    return SourceMod(root=root, namespace="examplemod", loader="forge", minecraft="1.20.1")


def test_offline_a_jar_share_of_a_nested_vanilla_tag_blocks_the_pass_through(tmp_path):
    mod = _logs_mod(tmp_path, ("data/minecraft/tags/items/oak_logs.json", {"values": ["examplemod:my_log"]}))
    result = recipes.convert(mod, emitted=_emitted(blocks=("my_log",)))
    assert _recipes(result) == {}
    reason = result.unhandled[0].reason
    assert "minecraft:logs" in reason and "minecraft:oak_logs" in reason
    assert "portkit reference fetch" in reason


def test_offline_without_any_vanilla_tag_file_the_tag_still_passes_through(tmp_path):
    result = recipes.convert(_logs_mod(tmp_path), emitted=_emitted(blocks=("my_log",)))
    body = _recipes(result)["recipes/thing.json"]["minecraft:recipe_shapeless"]
    assert body["ingredients"] == [{"tag": "minecraft:logs"}]
