"""#293: leftover data tags go where Bedrock reads them, or are explained from the jar."""
import json
import shutil
from pathlib import Path

from portkit import datatags
from portkit.converters.tags import TagResolver
from portkit.model import SourceMod
from portkit.pipeline import convert
from portkit.validate import validate_tree


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body))


# -- Forge / NeoForge "remove" -------------------------------------------------
def _gears(tmp_path, loader):
    root = tmp_path / loader if loader else tmp_path / "none"
    for name in ("brass_gear", "iron_gear", "tin_gear"):
        _write(root, f"assets/m/models/item/{name}.json", {"parent": "item/generated"})
    _write(root, "data/m/tags/items/gears.json",
           {"values": ["m:brass_gear", "m:iron_gear", "#m:metal_gears"], "remove": ["m:iron_gear", "#m:tin"]})
    _write(root, "data/m/tags/items/metal_gears.json", {"values": ["m:tin_gear"]})
    _write(root, "data/m/tags/items/tin.json", {"values": ["m:tin_gear"]})
    return TagResolver(SourceMod(root=root, namespace="m", loader=loader, minecraft="1.21.1"))


def test_neoforge_and_forge_apply_remove_entries_and_removed_tags(tmp_path):
    for loader in ("neoforge", "forge"):
        found = _gears(tmp_path, loader).resolve("m:gears")
        assert found.item == "m:brass_gear", (loader, found)


def test_fabric_ignores_remove(tmp_path):
    found = _gears(tmp_path, "fabric").resolve("m:gears")
    assert found.item is None and "3 items" in found.reason


def test_remove_without_a_declared_loader_is_unknown(tmp_path):
    resolver = _gears(tmp_path, None)
    assert resolver.members("m:gears") is None
    assert "remove" in resolver.unknown_reason("m:gears")


def test_jar_members_applies_remove(tmp_path):
    root = tmp_path / "jar"
    _write(root, "data/minecraft/tags/blocks/mineable/axe.json",
           {"values": ["m:log", "m:chest", "#m:woods"], "remove": ["m:chest"]})
    _write(root, "data/m/tags/blocks/woods.json", {"values": ["m:plank"]})
    read = []
    assert datatags.jar_members(root, "minecraft:mineable/axe", ("blocks", "block"), "forge", read) == [
        "m:log", "m:plank"]
    assert sorted(read) == ["data/m/tags/blocks/woods.json", "data/minecraft/tags/blocks/mineable/axe.json"]
    assert datatags.jar_members(root, "minecraft:mineable/axe", ("blocks", "block"), "fabric") == [
        "m:log", "m:chest", "m:plank"]
    assert datatags.jar_members(root, "minecraft:mineable/axe", ("blocks", "block"), None) is None


# -- tool and tier tags on blocks ----------------------------------------------
def _block(ident, fmt="1.20.20"):
    return {"format_version": fmt, "minecraft:block": {"description": {"identifier": ident},
                                                       "components": {"minecraft:geometry": "x"}}}


def test_tool_tags_go_on_shipped_blocks_and_claim_the_files(tmp_path):
    root = tmp_path / "jar"
    _write(root, "data/minecraft/tags/block/mineable/pickaxe.json", {"values": ["m:ore", "m:gone"]})
    _write(root, "data/minecraft/tags/block/needs_iron_tool.json", {"values": ["m:ore"]})
    _write(root, "data/minecraft/tags/block/mineable/shovel.json", {"values": ["m:gone"]})
    _write(root, "data/forge/tags/blocks/needs_wood_tool.json", {"values": ["m:ore"]})
    files = {"blocks/ore.json": _block("m:ore"), "blocks/new.json": _block("m:new", "1.26.50")}
    _write(root, "data/minecraft/tags/block/mineable/axe.json", {"values": ["m:new"]})
    claimed, notes = datatags.tool_tags(root, files, "neoforge")
    comps = files["blocks/ore.json"]["minecraft:block"]["components"]
    assert comps["tag:minecraft:is_pickaxe_item_destructible"] == {}
    assert comps["tag:minecraft:iron_tier_destructible"] == {}
    assert claimed == {"data/minecraft/tags/block/mineable/pickaxe.json",
                       "data/minecraft/tags/block/needs_iron_tool.json",
                       "data/minecraft/tags/block/mineable/axe.json"}
    # Block format 1.26.20 removed tag:* components: that block is left alone.
    assert not any(k.startswith("tag:") for k in files["blocks/new.json"]["minecraft:block"]["components"])
    assert any("1.26.20" in n for n in notes)


def test_the_validator_takes_tag_components_up_to_1_26_20(tmp_path):
    tree = tmp_path / "tree"
    body = _block("m:ore")
    body["minecraft:block"]["components"]["tag:minecraft:is_pickaxe_item_destructible"] = {}
    _write(tree, "behavior_pack/blocks/ore.json", body)
    report = validate_tree(tree)
    assert not [f for f in report.findings if f.rule in ("block.custom_component", "block.tag_component")]
    body["format_version"] = "1.26.20"
    _write(tree, "behavior_pack/blocks/ore.json", body)
    report = validate_tree(tree)
    assert [f for f in report.findings if f.rule == "block.tag_component"]


# -- explaining what's left ----------------------------------------------------
def test_classify_reads_registry_users_and_members(tmp_path):
    root = tmp_path / "jar"
    files = {
        "data/m/tags/fluid/oil.json": {"values": ["m:oil"]},
        "data/m/tags/worldgen/biome/has_ruin.json": {"values": ["#minecraft:is_overworld"]},
        "data/m/tags/item/machine_inputs.json": {"values": ["m:dust"]},
        "data/m/tags/item/shipped_unread.json": {"values": ["m:ingot"]},
        "data/m/tags/item/residue_members.json": {"values": ["m:sword"]},
        "data/m/tags/item/vanilla_only.json": {"values": ["minecraft:stick", "other:thing"]},
        "data/m/tags/item/loot_tool.json": {"values": ["m:ingot"]},
        "data/m/recipe/crusher.json": {"type": "m:crushing", "input": {"tag": "m:machine_inputs"}},
        "data/m/loot_table/blocks/ore.json": {"pools": [{"conditions": [{"predicate": {"items": "#m:loot_tool"}}]}]},
    }
    for rel, body in files.items():
        _write(root, rel, body)
    tags = [r for r in files if "/tags/" in r]
    found = datatags.classify(
        root, tags, consumed={"data/m/recipe/crusher.json", "data/m/loot_table/blocks/ore.json"},
        residue_sources={"data/m/recipe/crusher.json"}, shipped={"m:ingot", "m:dust"},
        namespaces={"m"}, loader="neoforge")
    kinds = {r.rsplit("/", 1)[-1]: v[0] for r, v in found.items()}
    assert kinds == {
        "oil.json": "tag_unshipped_registry",
        "has_ruin.json": "tag_unshipped_registry",
        "machine_inputs.json": "owned_by_residue",
        "shipped_unread.json": "tag_unread",
        "residue_members.json": "owned_by_residue",
        "vanilla_only.json": "tag_unread",
    }
    # loot_tool.json is named by a shipped loot table and still unclaimed: a gap.
    assert found["data/m/tags/worldgen/biome/has_ruin.json"][1] == "worldgen/biome"


def test_pipeline_files_every_tag_and_tags_the_block(tmp_path, fixtures_dir):
    src = tmp_path / "src"
    shutil.copytree(fixtures_dir / "agent_mod" / "input", src)
    _write(src, "data/minecraft/tags/blocks/mineable/pickaxe.json", {"values": ["examplemod:alloy_block"]})
    _write(src, "data/minecraft/tags/items/planks.json", {"values": ["examplemod:bronze_ingot"]})
    _write(src, "data/examplemod/tags/fluids/molten.json", {"values": ["examplemod:molten_alloy"]})
    _write(src, "data/examplemod/tags/items/unread.json", {"values": ["examplemod:steel_ingot"]})
    _write(src, "data/examplemod/tags/items/swords.json", {"values": ["examplemod:steel_sword"]})
    result = convert(src, tmp_path / "out", emit_addon=False)
    assert result.report.ok, result.report.errors
    kinds = {(u.kind, u.source) for u in result.unhandled if "/tags/" in u.source}
    assert ("unowned", "data/examplemod/tags/") not in {(k, s) for k, s in kinds}
    assert not [u for u in result.unhandled if u.kind == "unowned" and "/tags/" in u.source]
    assert ("tag_unshipped_registry", "data/examplemod/tags/fluids/") in kinds
    assert ("tag_unread", "data/examplemod/tags/items/") in kinds
    assert ("owned_by_residue", "data/examplemod/tags/items/") in kinds
    bp = result.tree / "behavior_pack"
    block = json.loads((bp / "blocks" / "alloy_block.json").read_text())
    assert "tag:minecraft:is_pickaxe_item_destructible" in block["minecraft:block"]["components"]
    bronze = json.loads((bp / "items" / "bronze_ingot.json").read_text())
    assert "minecraft:planks" in bronze["minecraft:item"]["components"]["minecraft:tags"]["tags"]
