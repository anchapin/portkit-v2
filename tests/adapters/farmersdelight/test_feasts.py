"""Station runtimes: Farmer's Delight feasts (#177).

A feast is a placed meal that serves portions: its ``servings`` state counts
down as players take a serving with the right container, and what it leaves
behind is its loot table per serving count. The converter writes the feast
blocks (facing x an integer servings state, a box per count, minecraft:loot
per count), one Bedrock loot table per distinct drop set, the block's own item,
scripts/portkit/data/<ns>_feast.js, and ships the fixed runtime
(portkit/adapters/farmersdelight/runtime/feast*.js).

Offline: the FD-shaped mod of tests/adapters/farmersdelight/test_stations.py plus two feasts (a
roast chicken that lingers, a stuffed pumpkin that vanishes).
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from portkit.adapters.farmersdelight import feasts
from portkit.adapters.farmersdelight import cutting_board as stations
from portkit.pipeline import convert

from test_stations import PNG, ROOT, _fd_mod, _write, reference  # noqa: F401  (fixture)

DATA = "behavior_pack/scripts/portkit/data/farmersdelight_feast.js"
NS = "farmersdelight"
TURNS = (("north", 0), ("east", 90), ("south", 180), ("west", 270))
FACES = ("north", "east", "south", "west", "up", "down")


def _full(block, top=4):
    return {"block": f"{NS}:{block}", "condition": "minecraft:block_state_property",
            "properties": {"servings": str(top)}}


def _pool(item, condition=None):
    pool = {"bonus_rolls": 0.0, "entries": [{"type": "minecraft:item", "name": item}], "rolls": 1.0}
    if condition is not None:
        pool["conditions"] = [condition]
    return pool


def _feast_loot(block, leftovers=(), top=4):
    pools = [_pool(f"{NS}:{block}", _full(block, top))]
    pools += [_pool(item, {"condition": "minecraft:inverted", "term": _full(block, top)}) for item in leftovers]
    return {"type": "minecraft:block", "pools": pools}


def _feast(root, block, models_by_servings, textures, top=4):
    _write(root, f"assets/{NS}/blockstates/{block}.json", {"variants": {
        f"facing={d},servings={n}": {"model": f"{NS}:block/{models_by_servings[n]}", **({"y": y} if y else {})}
        for d, y in TURNS for n in range(top + 1)}})
    for n, model in models_by_servings.items():
        height = 2 + 2 * n
        _write(root, f"assets/{NS}/models/block/{model}.json", {
            "textures": {**textures(n), "particle": f"{NS}:block/{model}"},
            "elements": [{"name": "dish", "from": [2, 0, 2], "to": [14, height, 14],
                          "faces": {f: {"uv": [0, 0, 16, 16], "texture": "#top" if f == "up" else "#side"}
                                    for f in FACES}}]})
    _write(root, f"assets/{NS}/models/item/{block}.json",
           {"parent": "minecraft:item/generated", "textures": {"layer0": f"{NS}:item/{block}"}})
    _write(root, f"assets/{NS}/textures/item/{block}.png", PNG.read_bytes())


def _feast_mod(tmp_path, version="1.3.4", loot=None, tagged=("roast_chicken_block", "stuffed_pumpkin_block")):
    root = _fd_mod(tmp_path, version=version)
    png = PNG.read_bytes()
    for texture in ("tray", "chicken", "pumpkin_top", "pumpkin_top_eaten", "pumpkin_side"):
        _write(root, f"assets/{NS}/textures/block/{texture}.png", png)
    _feast(root, "roast_chicken_block",
           {0: "roast_chicken_block_leftovers", 1: "roast_chicken_block_stage3", 2: "roast_chicken_block_stage2",
            3: "roast_chicken_block_stage1", 4: "roast_chicken_block_stage0"},
           lambda n: {"top": f"{NS}:block/chicken", "side": f"{NS}:block/tray"})
    # Java's own shape: servings 0 and 1 share a model; the eaten top swaps texture.
    _feast(root, "stuffed_pumpkin_block",
           {0: "stuffed_pumpkin_block_stage3", 1: "stuffed_pumpkin_block_stage3", 2: "stuffed_pumpkin_block_stage2",
            3: "stuffed_pumpkin_block_stage1", 4: "stuffed_pumpkin_block_stage0"},
           lambda n: {"top": f"{NS}:block/pumpkin_top{'' if n == 4 else '_eaten'}",
                      "side": f"{NS}:block/pumpkin_side"})
    for item in ("roast_chicken", "stuffed_pumpkin"):
        _write(root, f"assets/{NS}/models/item/{item}.json",
               {"parent": "minecraft:item/generated", "textures": {"layer0": f"{NS}:item/{item}"}})
        _write(root, f"assets/{NS}/textures/item/{item}.png", png)
    lang = json.loads((root / f"assets/{NS}/lang/en_us.json").read_text())
    lang.update({f"block.{NS}.roast_chicken_block": "Roast Chicken", f"item.{NS}.roast_chicken": "Plate of Roast Chicken",
                 f"block.{NS}.stuffed_pumpkin_block": "Stuffed Pumpkin", f"item.{NS}.stuffed_pumpkin": "Stuffed Pumpkin",
                 f"block.{NS}.feast.use_container": "You need a %s to eat this."})
    _write(root, f"assets/{NS}/lang/en_us.json", lang)
    tables = {"roast_chicken_block": _feast_loot("roast_chicken_block", ("minecraft:bowl", "minecraft:bone_meal")),
              "stuffed_pumpkin_block": _feast_loot("stuffed_pumpkin_block")}
    tables.update(loot or {})
    for name, body in tables.items():
        _write(root, f"data/{NS}/loot_table/blocks/{name}.json", body)
    _write(root, f"data/{NS}/tags/block/feasts.json", {"values": [f"{NS}:{b}" for b in tagged]})
    return root


def _table(tree: Path) -> dict:
    return json.loads((tree / DATA).read_text().split("export default ", 1)[1].rstrip().rstrip(";"))


def _block(tree: Path, name: str) -> dict:
    return json.loads((tree / f"behavior_pack/blocks/{name}.json").read_text())["minecraft:block"]


@pytest.fixture
def converted(tmp_path, reference):  # noqa: F811
    result = convert(_feast_mod(tmp_path), tmp_path / "out", emit_addon=False)
    return result, tmp_path / "out"


def test_table_holds_each_feast_from_code_and_data(converted):
    result, tree = converted
    table = _table(tree)
    assert table["servings_state"] == "farmersdelight:servings"
    assert table["feasts"] == {
        "farmersdelight:roast_chicken_block": {
            "container": "minecraft:bowl", "container_name": "item.bowl.name", "leftovers": True, "max_servings": 4,
            "servings": ["farmersdelight:roast_chicken"] * 4},
        "farmersdelight:stuffed_pumpkin_block": {
            "container": "minecraft:bowl", "container_name": "item.bowl.name", "leftovers": False, "max_servings": 4,
            "servings": ["farmersdelight:stuffed_pumpkin"] * 4},
    }
    assert table["messages"] == {"use_container": "tile.farmersdelight:feast.use_container.name"}
    assert table["sounds"] == {"clear": {"id": "dig.wood", "pitch": 0.8, "volume": 0.8},
                               "serve": {"id": "armor.equip_generic", "pitch": 1.0, "volume": 1.0}}
    assert result.stations["farmersdelight:feasts"]["converted"] == 2
    assert not any(u.kind == feasts.RESIDUE_KIND for u in result.unhandled)


def test_block_has_an_integer_servings_state_full_first(converted):
    result, tree = converted
    block = _block(tree, "roast_chicken_block")
    assert block["description"]["states"] == {"farmersdelight:servings": [4, 3, 2, 1, 0]}
    assert block["description"]["traits"]["minecraft:placement_direction"]["y_rotation_offset"] == 180
    comps = block["components"]
    assert comps["farmersdelight:portkit_feast"] == {}
    assert comps["minecraft:placement_filter"] == {"conditions": [{"allowed_faces": ["up"]}]}
    assert comps["minecraft:geometry"]["bone_visibility"]["4"] == "q.block_state('farmersdelight:servings') == 4"
    assert not any(u.source.endswith("blockstates/roast_chicken_block.json") for u in result.unhandled)


def test_boxes_follow_the_java_shapes_per_serving_count(converted):
    _, tree = converted
    perms = _block(tree, "roast_chicken_block")["permutations"]
    assert len(perms) == 20
    by_count = {}
    for perm in perms:
        count = int(perm["condition"].rsplit("== ", 1)[1])
        by_count.setdefault(count, perm["components"]["minecraft:collision_box"])
    # The tray alone at 0 (1..15 x 0..2); tray + chicken (to y 8) above.
    assert by_count[0] == {"origin": [-7, 0, -7], "size": [14, 2, 14]}
    assert by_count[4] == {"origin": [-7, 0, -7], "size": [14, 8, 14]}
    pumpkin = {int(p["condition"].rsplit("== ", 1)[1]): p["components"]["minecraft:collision_box"]
               for p in _block(tree, "stuffed_pumpkin_block")["permutations"]}
    # FeastBlock.SHAPES: 2..14, heights 2, 2, 4, 6, 8.
    assert [pumpkin[n]["size"][1] for n in range(5)] == [2, 2, 4, 6, 8]
    assert pumpkin[4]["origin"] == [-6, 0, -6]


def test_loot_is_read_per_serving_count(converted):
    _, tree = converted
    loot = tree / "behavior_pack/loot_tables/blocks"
    full = json.loads((loot / "roast_chicken_block.json").read_text())
    assert [p["entries"][0]["name"] for p in full["pools"]] == ["farmersdelight:roast_chicken_block"]
    eaten = json.loads((loot / "roast_chicken_block_servings_0_to_3.json").read_text())
    assert [p["entries"][0]["name"] for p in eaten["pools"]] == ["minecraft:bowl", "minecraft:bone_meal"]
    by_count = {int(p["condition"].rsplit("== ", 1)[1]): p["components"]["minecraft:loot"]
                for p in _block(tree, "stuffed_pumpkin_block")["permutations"]}
    assert by_count[4] == "loot_tables/blocks/stuffed_pumpkin_block.json"
    assert {by_count[n] for n in range(4)} == {feasts.EMPTY_LOOT}
    assert not (loot / "stuffed_pumpkin_block_servings_0_to_3.json").exists()


def test_eaten_texture_gets_its_own_instance(converted):
    _, tree = converted
    instances = _block(tree, "stuffed_pumpkin_block")["components"]["minecraft:material_instances"]
    textures = {spec["texture"] for spec in instances.values()}
    assert {"farmersdelight:pumpkin_top", "farmersdelight:pumpkin_top_eaten"} <= textures
    assert "top_servings_3" in instances and "top_servings_2" not in instances


def test_item_is_the_blocks_own_with_its_icon(converted):
    _, tree = converted
    item = json.loads((tree / "behavior_pack/items/roast_chicken_block.json").read_text())
    comps = item["minecraft:item"]["components"]
    assert comps["minecraft:block_placer"] == {"block": "farmersdelight:roast_chicken_block", "replace_block_item": True}
    assert comps["minecraft:max_stack_size"] == 1
    assert comps["minecraft:icon"] == "farmersdelight:roast_chicken_block"


def test_entry_wires_the_feasts_and_the_tree_validates(converted):
    result, tree = converted
    main = (tree / "behavior_pack/scripts/portkit/main.js").read_text()
    assert "registerFeasts(feastTable)" in main
    for name in ("feast.js", "feast_core.js", "station_storage.js"):
        assert (tree / "behavior_pack/scripts/portkit" / name).read_text() == stations.runtime_source(name)
    assert result.report.ok, result.report.errors
    note = next(n for n in result.notes if "feast(s) serve" in n)
    for words in ("off-hand", "comparator", "particles", "rigid-support"):
        assert words in note


def test_loot_that_disagrees_with_the_code_stays_residue(tmp_path, reference):  # noqa: F811
    # A stuffed pumpkin that drops a bowl at 0 would linger, but FD's code says it vanishes.
    loot = {"stuffed_pumpkin_block": _feast_loot("stuffed_pumpkin_block", ("minecraft:bowl",))}
    result = convert(_feast_mod(tmp_path, loot=loot), tmp_path / "out", emit_addon=False)
    residue = [u for u in result.unhandled if u.kind == feasts.RESIDUE_KIND]
    assert [u.source for u in residue] == [f"data/{NS}/loot_table/blocks/stuffed_pumpkin_block.json"]
    assert "hasLeftovers=false" in residue[0].reason
    assert list(_table(tmp_path / "out")["feasts"]) == ["farmersdelight:roast_chicken_block"]


def test_unreadable_pool_stays_residue(tmp_path, reference):  # noqa: F811
    odd = _feast_loot("roast_chicken_block", ("minecraft:bowl",))
    odd["pools"][1]["conditions"] = [{"condition": "minecraft:random_chance", "chance": 0.5}]
    result = convert(_feast_mod(tmp_path, loot={"roast_chicken_block": odd}), tmp_path / "out", emit_addon=False)
    residue = [u for u in result.unhandled if u.kind == feasts.RESIDUE_KIND]
    assert len(residue) == 1 and "random_chance" in residue[0].reason


def test_untagged_blocks_are_not_feasts(tmp_path, reference):  # noqa: F811
    result = convert(_feast_mod(tmp_path, tagged=("roast_chicken_block",)), tmp_path / "out", emit_addon=False)
    assert list(_table(tmp_path / "out")["feasts"]) == ["farmersdelight:roast_chicken_block"]
    # The untagged one is a plain block with a state its code sets: residue, as before.
    assert any(u.source.endswith("blockstates/stuffed_pumpkin_block.json") and u.kind == "block"
               for u in result.unhandled)


def test_unread_version_leaves_feasts_as_residue(tmp_path, reference):  # noqa: F811
    result = convert(_feast_mod(tmp_path, version="1.2.9"), tmp_path / "out", emit_addon=False)
    assert not (tmp_path / "out" / DATA).exists()
    assert any(u.source.endswith("blockstates/roast_chicken_block.json") for u in result.unhandled)
    assert any(u.source.endswith("loot_table/blocks/roast_chicken_block.json") and u.kind == "loot"
               for u in result.unhandled)


def test_feast_specs_pin_both_loaders():
    for loader in ("neoforge", "fabric"):
        specs = feasts.FEASTS[loader]
        assert set(specs) == {"roast_chicken_block", "stuffed_pumpkin_block", "honey_glazed_ham_block",
                              "shepherds_pie_block", "gleaming_salad_block", "rice_roll_medley_block"}
        assert not specs["stuffed_pumpkin_block"].leftovers
        assert specs["rice_roll_medley_block"].container is None
        assert len(specs["rice_roll_medley_block"].serving) == 8
        salad = feasts._block(specs["gleaming_salad_block"], loader)
        assert [salad.value_components[str(n)]["minecraft:light_emission"] for n in range(5)] == [0, 3, 6, 9, 12]
        assert salad.int_state and salad.values == ("4", "3", "2", "1", "0")


def test_output_is_deterministic(tmp_path, reference):  # noqa: F811
    first = convert(_feast_mod(tmp_path), tmp_path / "a", emit_addon=False)
    second = convert(_feast_mod(tmp_path), tmp_path / "b", emit_addon=False)
    assert (first.tree / DATA).read_bytes() == (second.tree / DATA).read_bytes()


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_runtime_under_node(converted):
    _, tree = converted
    js = ROOT / "tests" / "js"
    for env in ({}, {"PORTKIT_FEAST_TABLE": str(tree / DATA)}):
        proc = subprocess.run(
            ["node", "--import", str(js / "register.mjs"), "--test", str(js / "adapters" / "farmersdelight" / "feast.test.mjs")],
            capture_output=True, text=True, timeout=120, env={"PATH": os.environ["PATH"], **env},
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr


def test_agent_skips_feast_residue():
    from portkit.agent.residue import SKIP_KINDS

    assert feasts.RESIDUE_KIND in SKIP_KINDS


def test_agent_skips_every_runtime_residue_kind():
    """Every converter that owns a runtime declares a RESIDUE_KIND; the agent must skip each one (#199)."""
    import importlib
    import pkgutil

    import portkit.converters as converters
    from portkit.agent.residue import SKIP_KINDS

    import portkit.adapters as adapters

    kinds = {}
    # The core converters and every adapter module (Waystones' moved, #245).
    for package in (converters, adapters):
        for mod in pkgutil.walk_packages(package.__path__, f"{package.__name__}."):
            module = importlib.import_module(mod.name)
            kind = getattr(module, "RESIDUE_KIND", None)
            if isinstance(kind, str):
                kinds[mod.name] = kind
    assert {"station_recipe", "feast", "waystone"} <= set(kinds.values())
    assert {name: kind for name, kind in kinds.items() if kind not in SKIP_KINDS} == {}
