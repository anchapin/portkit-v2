"""Station runtimes: the cutting board's data table and fixed script (#177).

A Farmer's Delight cutting recipe is data the Java block's code interprets.
The converter writes every recipe it can state exactly into one data module
(scripts/portkit/data/<ns>_cutting_board.js) and ships a fixed runtime
(portkit/runtime/cutting_board*.js) that does what FD's code does; a recipe
naming anything it can't state exactly stays ``station_recipe`` residue.

Runs offline: a tiny FD-shaped mod in tmp_path, with its own tag reference
(PORTKIT_TAG_REFERENCE) for the vanilla and loader tags it reads.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from portkit.converters import recipes, stations
from portkit.model import SourceMod
from portkit.pipeline import convert
from portkit.validate import validate_tree

ROOT = Path(__file__).resolve().parents[1]
DATA = "behavior_pack/scripts/portkit/data/farmersdelight_cutting_board.js"
SHOVELS = ["minecraft:wooden_shovel", "minecraft:iron_shovel"]
AXES = ["minecraft:wooden_axe", "minecraft:iron_axe"]
TOML = """modLoader="javafml"
loaderVersion="[4,)"
license="MIT"
[[mods]]
modId="farmersdelight"
version="{version}"
displayName="Farmer's Delight"
[[dependencies.farmersdelight]]
modId="neoforge"
type="required"
versionRange="[21.1.219,)"
[[dependencies.farmersdelight]]
modId="minecraft"
type="required"
versionRange="[1.21.1]"
"""
PNG = next((ROOT / "fixtures" / "simple_block_mod").rglob("*.png"))


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(body, bytes):
        path.write_bytes(body)
    else:
        path.write_text(body if isinstance(body, str) else json.dumps(body))


def _cut(ingredient, tool, results, **extra):
    return {"type": "farmersdelight:cutting", "ingredients": [ingredient], "tool": tool, "result": results, **extra}


def _ability(action, tag):
    return [{"type": "farmersdelight:item_ability", "action": action}, {"tag": tag}]


def _stack(ident, count=1, chance=None):
    entry = {"item": {"count": count, "id": ident}}
    if chance is not None:
        entry["chance"] = chance
    return entry


RECIPES = {
    "cutting/gravel": _cut({"item": "minecraft:gravel"}, _ability("shovel_dig", "minecraft:shovels"),
                           [_stack("minecraft:gravel"), _stack("minecraft:flint", chance=0.1)]),
    "cutting/acacia_log": _cut({"item": "minecraft:acacia_log"}, _ability("axe_strip", "minecraft:axes"),
                               [_stack("minecraft:stripped_acacia_log"), _stack("farmersdelight:tree_bark")],
                               sound={"sound_id": "minecraft:item.axe.strip"}),
    "cutting/cabbage": _cut({"item": "farmersdelight:cabbage"}, _ability("knife_dig", "c:tools/knife"),
                            [_stack("farmersdelight:cabbage_leaf", 2)]),
    "cutting/beetroot": _cut({"item": "minecraft:beetroot"}, {"tag": "c:tools/knife"},
                             [_stack("minecraft:red_dye")], sound={"sound_id": "minecraft:block.note_block.bell"}),
    "salvaging/oak": _cut({"type": "neoforge:compound", "children": [{"item": "minecraft:oak_door"},
                                                                     {"item": "minecraft:oak_fence"}]},
                          _ability("axe_dig", "minecraft:axes"), [_stack("minecraft:oak_planks")]),
    # residue, each for its own reason
    "cutting/pie": _cut({"item": "farmersdelight:apple_pie"}, {"tag": "c:tools/knife"},
                        [_stack("farmersdelight:cabbage_leaf", 4)]),
    "cutting/old_action": _cut({"item": "minecraft:stick"}, {"type": "farmersdelight:tool_action", "action": "axe_dig"},
                               [_stack("minecraft:oak_planks")]),
    "cutting/odd_ability": _cut({"item": "minecraft:bone"}, [{"type": "farmersdelight:item_ability", "action": "brush"}],
                                [_stack("minecraft:bone_meal")]),
    # NeoForge's knives perform sword_dig too (KnifeItem KNIFE_ACTIONS): more than #minecraft:swords.
    "cutting/sword_bone": _cut({"item": "minecraft:bone"}, _ability("sword_dig", "minecraft:swords"),
                               [_stack("minecraft:bone_meal")]),
    "cutting/clay_a": _cut({"item": "minecraft:clay"}, {"tag": "c:tools/knife"}, [_stack("minecraft:clay_ball")]),
    "cutting/clay_b": _cut({"item": "minecraft:clay"}, {"tag": "c:tools/knife"}, [_stack("minecraft:clay_ball", 4)]),
    "integration/compat": {**_cut({"item": "minecraft:stick"}, {"tag": "c:tools/knife"}, [_stack("minecraft:stick")]),
                           "neoforge:conditions": [{"type": "neoforge:mod_loaded", "modid": "silentgear"}]},
}
KNIVES = ["farmersdelight:flint_knife", "farmersdelight:iron_knife"]


@pytest.fixture
def reference(tmp_path, monkeypatch):
    ref = tmp_path / "ref"
    _write(ref, "vanilla-1.21.1.json", {"set": "vanilla-1.21.1", "tags": {
        "minecraft:shovels": SHOVELS, "minecraft:axes": AXES}})
    _write(ref, "neoforge-1.21.1.json", {"set": "neoforge-1.21.1", "tags": {
        "c:tools/shear": ["minecraft:shears"], "c:tools/knife": []}})
    monkeypatch.setenv("PORTKIT_TAG_REFERENCE", str(ref))
    return ref


def _fd_mod(tmp_path, version="1.3.4", recipes_=None, namespace="farmersdelight") -> Path:
    root = tmp_path / "fd"
    png = PNG.read_bytes()
    _write(root, "META-INF/neoforge.mods.toml", TOML.format(version=version))
    ns = namespace
    _write(root, f"assets/{ns}/blockstates/cutting_board.json", {"variants": {
        "facing=north": {"model": f"{ns}:block/cutting_board"},
        "facing=east": {"model": f"{ns}:block/cutting_board", "y": 90},
        "facing=south": {"model": f"{ns}:block/cutting_board", "y": 180},
        "facing=west": {"model": f"{ns}:block/cutting_board", "y": 270},
    }})
    _write(root, f"assets/{ns}/models/block/cutting_board.json", {
        "textures": {"particle": f"{ns}:block/cutting_board", "main": f"{ns}:block/cutting_board"},
        "elements": [{"from": [1, 0, 1], "to": [15, 1, 15], "faces": {
            f: {"uv": [1, 1, 15, 15], "texture": "#main"} for f in ("north", "east", "south", "west", "up", "down")}}],
    })
    _write(root, f"assets/{ns}/textures/block/cutting_board.png", png)
    for item in ("tree_bark", "cabbage", "cabbage_leaf", *(k.split(":")[1] for k in KNIVES)):
        _write(root, f"assets/{ns}/models/item/{item}.json",
               {"parent": "minecraft:item/generated", "textures": {"layer0": f"{ns}:item/{item}"}})
        _write(root, f"assets/{ns}/textures/item/{item}.png", png)
    names = {f"item.{ns}.{item}": item for item in ("tree_bark", "cabbage", "cabbage_leaf",
                                                    *(k.split(":")[1] for k in KNIVES))}
    _write(root, f"assets/{ns}/lang/en_us.json", {
        **names,
        "block.farmersdelight.cutting_board": "Cutting Board",
        "block.farmersdelight.cutting_board.invalid_tool": "Maybe with a different tool...",
        "block.farmersdelight.cutting_board.remaining_items": "%s remaining...",
    })
    _write(root, "data/c/tags/item/tools/knife.json", {"values": KNIVES})
    for name, body in (RECIPES if recipes_ is None else recipes_).items():
        _write(root, f"data/{ns}/recipe/{name}.json", body)
    return root


def _table(tree: Path) -> dict:
    text = (tree / DATA).read_text()
    body = text.split("export default ", 1)[1].rstrip().rstrip(";")
    return json.loads(body)


@pytest.fixture
def converted(tmp_path, reference):
    result = convert(_fd_mod(tmp_path), tmp_path / "out", emit_addon=False)
    return result, tmp_path / "out"


def test_data_table_holds_the_recipes_it_can_state(converted):
    result, tree = converted
    table = _table(tree)
    by_id = {r["id"]: r for r in table["recipes"]}
    assert sorted(by_id) == ["farmersdelight:cutting/acacia_log", "farmersdelight:cutting/beetroot",
                             "farmersdelight:cutting/cabbage", "farmersdelight:cutting/gravel",
                             "farmersdelight:salvaging/oak"]
    gravel = by_id["farmersdelight:cutting/gravel"]
    # The ability reads as its tag; the tag also maps to Bedrock's own tool tag.
    assert gravel["tool"] == {"items": sorted(SHOVELS), "tags": ["minecraft:is_shovel"]}
    assert gravel["results"] == [{"item": "minecraft:gravel", "count": 1, "chance": 1.0},
                                 {"item": "minecraft:flint", "count": 1, "chance": 0.1}]
    assert "sound" not in gravel
    assert by_id["farmersdelight:cutting/acacia_log"]["sound"] == "use.wood"
    # A Java sound with no Bedrock event playing the same audio: silent, said.
    assert by_id["farmersdelight:cutting/beetroot"]["sound"] is None
    assert any("block.note_block.bell" in n for n in result.notes)
    assert by_id["farmersdelight:cutting/cabbage"]["tool"] == {"items": KNIVES, "tags": []}
    assert by_id["farmersdelight:salvaging/oak"]["ingredient"] == ["minecraft:oak_door", "minecraft:oak_fence"]
    assert table["sound_tools"] == {"knife": KNIVES, "shears": ["minecraft:shears"]}
    assert table["messages"] == {"no_recipe": "tile.farmersdelight:cutting_board.invalid_tool.name",
                                 "remaining": "tile.farmersdelight:cutting_board.remaining_items.name"}
    assert table["fortune_bonus"] == 0.1
    assert table["component"] == "farmersdelight:portkit_cutting_board"
    assert result.stations["farmersdelight:cutting"]["converted"] == 5


def test_residue_says_why(converted):
    result, _ = converted
    reasons = {Path(u.source).stem: (u.kind, u.reason) for u in result.unhandled
               if "/recipe/" in u.source}
    assert reasons["pie"] == ("station_recipe", "ingredient farmersdelight:apple_pie is not converted")
    assert reasons["old_action"][0] == "station_recipe" and "item_ability only" in reasons["old_action"][1]
    assert "'brush'" in reasons["odd_ability"][1]
    assert reasons["sword_bone"][0] == "station_recipe" and "knives perform it too" in reasons["sword_bone"][1]
    assert "cutting/clay_b" in reasons["clay_a"][1] and "cutting/clay_a" in reasons["clay_b"][1]
    # Load conditions are decided before the station sees a recipe (#183).
    assert reasons["compat"][0] == "conditional_recipe"
    assert result.stations["farmersdelight:cutting"]["residue"] == 6
    assert not any(u.kind == "recipe" and "farmersdelight:cutting" in u.reason for u in result.unhandled)


def test_block_converts_with_the_runtime_component(converted):
    result, tree = converted
    body = json.loads((tree / "behavior_pack/blocks/cutting_board.json").read_text())
    block = body["minecraft:block"]
    assert body["format_version"] == "1.21.90"
    # FD faces the board toward the player (getHorizontalDirection().getOpposite()).
    assert block["description"]["traits"]["minecraft:placement_direction"] == {
        "enabled_states": ["minecraft:cardinal_direction"], "y_rotation_offset": 180}
    box = {"origin": [-7, 0, -7], "size": [14, 1, 14]}
    assert block["components"]["minecraft:collision_box"] == box
    assert block["components"]["minecraft:selection_box"] == box
    assert block["components"]["farmersdelight:portkit_cutting_board"] == {}
    assert not any(u.source.endswith("blockstates/cutting_board.json") for u in result.unhandled)


def test_manifest_runs_the_script_and_the_tree_validates(converted):
    result, tree = converted
    manifest = json.loads((tree / "behavior_pack/manifest.json").read_text())
    scripts = [m for m in manifest["modules"] if m["type"] == "script"]
    assert scripts and scripts[0]["entry"] == "scripts/portkit/main.js"
    assert scripts[0]["language"] == "javascript"
    assert {"module_name": "@minecraft/server", "version": "2.0.0"} in manifest["dependencies"]
    assert manifest["header"]["min_engine_version"] >= [1, 21, 90]
    assert result.report.ok, result.report.errors
    assert (tree / "behavior_pack/scripts/portkit/cutting_board.js").read_text() == \
        stations.runtime_source("cutting_board.js")


def test_output_is_deterministic(tmp_path, reference):
    first = convert(_fd_mod(tmp_path), tmp_path / "a", emit_addon=False)
    second = convert(_fd_mod(tmp_path), tmp_path / "b", emit_addon=False)
    assert (first.tree / DATA).read_bytes() == (second.tree / DATA).read_bytes()


def test_unread_version_stays_residue(tmp_path, reference):
    result = convert(_fd_mod(tmp_path, version="1.2.9"), tmp_path / "out", emit_addon=False)
    assert not (tmp_path / "out" / DATA).exists()
    cutting = [u for u in result.unhandled if u.kind == "station_recipe"]
    assert cutting and all("1.2.9" in u.reason for u in cutting)
    # No station runtime for this version: the board is a plain facing block
    # now (#212), its placement and box the documented defaults (the fixture
    # ships no class files), and the notes say both are defaults.
    assert not any(u.source.endswith("blockstates/cutting_board.json") for u in result.unhandled)
    assert not (result.tree / "behavior_pack/scripts/portkit/cutting_board.js").exists()
    notes = " ".join(result.notes)
    assert "Facing placement DEFAULT" in notes and "cutting_board" in notes
    assert "Facing box DEFAULT" in notes


def test_other_namespace_stays_residue(tmp_path, reference):
    root = tmp_path / "supp"
    _write(root, "data/examplemod/recipes/cut.json",
           _cut({"item": "minecraft:stick"}, {"tag": "c:tools/knife"}, [_stack("minecraft:stick")]))
    result = convert(root, tmp_path / "out", emit_addon=False)
    entry = next(u for u in result.unhandled if u.source.endswith("cut.json"))
    assert entry.kind == "station_recipe" and "not in this jar" in entry.reason


def test_recipe_converter_alone_still_refuses_cutting(tmp_path):
    root = tmp_path / "m"
    _write(root, "data/examplemod/recipes/cut.json",
           _cut({"item": "minecraft:stick"}, {"tag": "c:tools/knife"}, [_stack("minecraft:stick")]))
    result = recipes.convert(SourceMod(root=root, namespace="examplemod"))
    assert result.unhandled[0].reason == "unsupported recipe type 'farmersdelight:cutting'"


def test_station_type_lists_agree():
    assert recipes.STATION_TYPES == stations.RECIPE_TYPES


# -- validator rules for scripts ------------------------------------------------

def _pack(tmp_path, *, entry="scripts/main.js", deps=None, files=None, block_format=None):
    tree = tmp_path / "tree"
    bp = tree / "behavior_pack"
    manifest = {"format_version": 2,
                "header": {"name": "x", "uuid": "11111111-1111-4111-8111-111111111111",
                           "version": [1, 0, 0], "min_engine_version": [1, 21, 90]},
                "modules": [{"type": "data", "uuid": "22222222-2222-4222-8222-222222222222", "version": [1, 0, 0]},
                            {"type": "script", "language": "javascript", "entry": entry,
                             "uuid": "33333333-3333-4333-8333-333333333333", "version": [1, 0, 0]}],
                "dependencies": deps if deps is not None else [{"module_name": "@minecraft/server", "version": "2.0.0"}]}
    _write(bp, "manifest.json", manifest)
    for rel, text in (files or {"scripts/main.js": 'import { system } from "@minecraft/server";\n'}).items():
        _write(bp, rel, text)
    if block_format:
        _write(bp, "blocks/b.json", {"format_version": block_format, "minecraft:block": {
            "description": {"identifier": "x:b"}, "components": {"x:runtime": {}}}})
    return tree


def _rules(tree):
    return {(f.rule, f.message) for f in validate_tree(tree).errors}


def test_a_script_pack_validates(tmp_path):
    assert _rules(_pack(tmp_path)) == set()


def test_missing_entry_is_an_error(tmp_path):
    rules = _rules(_pack(tmp_path, entry="scripts/nope.js"))
    assert any(r == "manifest.script" and "nope.js" in m for r, m in rules)


def test_undeclared_module_import_is_an_error(tmp_path):
    rules = _rules(_pack(tmp_path, deps=[]))
    assert any(r == "script.import" and "@minecraft/server" in m for r, m in rules)


def test_missing_relative_import_is_an_error(tmp_path):
    rules = _rules(_pack(tmp_path, files={"scripts/main.js": 'import x from "./gone.js";\n'}))
    assert any(r == "script.import" and "gone.js" in m for r, m in rules)


def test_bad_module_version_is_an_error(tmp_path):
    rules = _rules(_pack(tmp_path, deps=[{"module_name": "@minecraft/server", "version": [2, 0, 0]}]))
    assert any(r == "manifest.dependency" for r, _ in rules)


def test_custom_component_needs_format_1_21_90(tmp_path):
    assert any(r == "block.custom_component" for r, _ in _rules(_pack(tmp_path, block_format="1.21.80")))
    assert not any(r == "block.custom_component" for r, _ in _rules(_pack(tmp_path / "ok", block_format="1.21.90")))


# -- the runtime, under node ----------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_runtime_under_node(converted):
    _, tree = converted
    js = ROOT / "tests" / "js"
    proc = subprocess.run(
        ["node", "--import", str(js / "register.mjs"), "--test", str(js / "cutting_board.test.mjs")],
        capture_output=True, text=True, timeout=120,
        env={"PATH": __import__("os").environ["PATH"], "PORTKIT_CUTTING_TABLE": str(tree / DATA)},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
