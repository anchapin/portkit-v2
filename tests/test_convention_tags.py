"""Loader and vanilla tag membership as reference data (#160), and the
multi-member tag recipes it makes possible.

Everything here runs offline against the tiny hand-written sets in
tests/data/tag_reference (PORTKIT_TAG_REFERENCE), or against fake upstream
payloads built in the test. Nothing from Forge, NeoForge, Fabric or Mojang is
committed.
"""
import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path

import pytest

from portkit import cli, data
from portkit.converters import recipes
from portkit.converters.tags import TagResolver
from portkit.data import tags as tag_data
from portkit.meta import parse as parse_meta
from portkit.model import SourceMod
from portkit.pipeline import convert
from portkit.validate import validate_tree

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "tests" / "data" / "tag_reference"


@pytest.fixture
def reference(monkeypatch):
    monkeypatch.setenv("PORTKIT_TAG_REFERENCE", str(REFERENCE))
    return REFERENCE


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body) if not isinstance(body, str) else body)


def _mod(tmp_path, recipe, *, loader="forge", minecraft="1.20.1", items=(), blocks=(), tag_files=None,
         name="thing"):
    root = tmp_path / "mod"
    _write(root, f"data/examplemod/recipes/{name}.json", recipe)
    for item in items:
        _write(root, f"assets/examplemod/models/item/{item}.json", {"parent": "minecraft:item/generated"})
    for block in blocks:
        _write(root, f"assets/examplemod/blockstates/{block}.json", {"variants": {"": {"model": f"examplemod:block/{block}"}}})
    for rel, body in (tag_files or {}).items():
        _write(root, rel, body if isinstance(body, dict) else {"values": body})
    return SourceMod(root=root, namespace="examplemod", loader=loader, minecraft=minecraft)


def _emitted(*, items=(), blocks=()):
    found = {}
    for name in items:
        ident = f"examplemod:{name}"
        body = {"format_version": "1.20.10", "minecraft:item": {"description": {"identifier": ident}, "components": {}}}
        found[ident] = ("item", f"items/{name}.json", body)
    for name in blocks:
        ident = f"examplemod:{name}"
        found[ident] = ("block", f"blocks/{name}.json", {"minecraft:block": {"description": {"identifier": ident}}})
    return found


def _shapeless(tag, extra=()):
    return {"type": "minecraft:crafting_shapeless",
            "ingredients": [{"tag": tag}, *extra],
            "result": {"item": "examplemod:thing"}}


def _shaped(tag, pattern=("GGG",)):
    return {"type": "minecraft:crafting_shaped", "pattern": list(pattern),
            "key": {"G": {"tag": tag}}, "result": {"item": "examplemod:thing"}}


def _recipe_files(result):
    return {k: v for k, v in result.files.items() if k.startswith("recipes/")}


def _ingredient_items(result):
    found = set()
    for body in _recipe_files(result).values():
        recipe = body.get("minecraft:recipe_shapeless") or body.get("minecraft:recipe_shaped") or {}
        for ing in [*recipe.get("ingredients", []), *(recipe.get("key") or {}).values()]:
            found.add(ing.get("item") or f"#{ing.get('tag')}")
        if "minecraft:recipe_furnace" in body:
            found.add(body["minecraft:recipe_furnace"]["input"])
    return found


# -- #160: a shared tag is never narrowed to the jar's share ------------------
GLASS = "data/forge/tags/items/glass/colorless.json"


def test_forge_glass_is_not_narrowed_to_the_mods_glass(tmp_path, reference):
    """Tinkers' one-line forge:glass/colorless used to resolve to its clear glass alone."""
    mod = _mod(tmp_path, _shaped("forge:glass/colorless"), blocks=["clear_glass"],
               tag_files={GLASS: ["examplemod:clear_glass"]})
    result = recipes.convert(mod, emitted=_emitted(blocks=["clear_glass"]))
    assert _recipe_files(result) == {}  # three slots: mixing members can't be expressed
    reason = result.unhandled[0].reason
    assert "examplemod:clear_glass" in reason and "minecraft:glass" in reason
    assert GLASS in result.consumed


def test_forge_glass_without_reference_data_stays_residue(tmp_path):
    mod = _mod(tmp_path, _shaped("forge:glass/colorless"), blocks=["clear_glass"],
               tag_files={GLASS: ["examplemod:clear_glass"]})
    result = recipes.convert(mod)
    assert _recipe_files(result) == {}
    reason = result.unhandled[0].reason
    assert "full membership isn't known" in reason and "portkit reference fetch" in reason
    assert GLASS in result.consumed


def test_a_single_slot_forge_glass_recipe_keeps_vanilla_glass(tmp_path, reference):
    mod = _mod(tmp_path, _shapeless("forge:glass/colorless"), blocks=["clear_glass"],
               tag_files={GLASS: ["examplemod:clear_glass"]})
    result = recipes.convert(mod, emitted=_emitted(blocks=["clear_glass"]))
    assert result.unhandled == []
    assert set(_recipe_files(result)) == {
        "recipes/thing__examplemod_clear_glass.json", "recipes/thing__minecraft_glass.json"}
    assert _ingredient_items(result) == {"examplemod:clear_glass", "minecraft:glass"}


def test_replace_true_is_the_whole_tag_even_without_data(tmp_path):
    mod = _mod(tmp_path, _shapeless("forge:glass/colorless"), loader=None, minecraft=None,
               blocks=["clear_glass"],
               tag_files={GLASS: {"replace": True, "values": ["examplemod:clear_glass"]}})
    result = recipes.convert(mod)
    assert result.unhandled == []
    assert _ingredient_items(result) == {"examplemod:clear_glass"}


def test_a_one_member_loader_tag_resolves_from_the_reference(tmp_path, reference):
    result = recipes.convert(_mod(tmp_path, _shapeless("forge:dyes/red")))
    assert _ingredient_items(result) == {"minecraft:red_dye"}
    assert any("Forge" in n or "tag data" in n for n in result.notes)


# -- nested tags ----------------------------------------------------------------
def test_nested_tags_resolve_through_jar_and_reference(tmp_path, reference):
    mod = _mod(tmp_path, _shapeless("forge:glass"), blocks=["clear_glass"],
               tag_files={GLASS: ["examplemod:clear_glass"]})
    result = recipes.convert(mod, emitted=_emitted(blocks=["clear_glass"]))
    assert _ingredient_items(result) == {"minecraft:glass", "minecraft:tinted_glass", "examplemod:clear_glass"}


def test_a_nested_optional_tag_nobody_defines_is_empty(tmp_path, reference):
    result = recipes.convert(_mod(tmp_path, _shapeless("forge:stone")), emitted={})
    assert _ingredient_items(result) == {"minecraft:stone", "minecraft:granite"}


def test_a_nested_vanilla_tag_needs_the_vanilla_data(tmp_path, monkeypatch):
    only_forge = tmp_path / "ref"
    only_forge.mkdir()
    shutil.copy(REFERENCE / "forge-1.20.1.json", only_forge)
    monkeypatch.setenv("PORTKIT_TAG_REFERENCE", str(only_forge))
    result = recipes.convert(_mod(tmp_path, _shapeless("forge:sand")), emitted={})
    assert _recipe_files(result) == {}
    assert "#minecraft:sand_like" in result.unhandled[0].reason
    monkeypatch.setenv("PORTKIT_TAG_REFERENCE", str(REFERENCE))
    result = recipes.convert(_mod(tmp_path / "again", _shapeless("forge:sand")), emitted={})
    assert _ingredient_items(result) == {"minecraft:sand", "minecraft:red_sand"}


def test_a_loader_never_writing_a_namespace_leaves_it_to_mods(tmp_path, reference):
    """NeoForge 1.21 dropped forge: tags, so its optional #forge:crops/wheat is
    only other mods' share; Forge 1.20.1 ships no c: tags, so a Forge mod's own
    c: file is everything the addon can hold."""
    neo = recipes.convert(_mod(tmp_path, _shapeless("c:crops/wheat"), loader="neoforge", minecraft="1.21.1"))
    assert _ingredient_items(neo) == {"minecraft:wheat"}
    forge = recipes.convert(_mod(tmp_path / "f", _shapeless("c:ingots/steel"), items=["steel"],
                                 tag_files={"data/c/tags/items/ingots/steel.json": ["examplemod:steel"]}))
    assert _ingredient_items(forge) == {"examplemod:steel"}


# -- offline / unknown version ---------------------------------------------------
def test_offline_the_recipe_stays_residue_and_says_to_fetch(tmp_path):
    result = recipes.convert(_mod(tmp_path, _shapeless("forge:dyes/red")))
    assert _recipe_files(result) == {}
    assert "portkit reference fetch" in result.unhandled[0].reason


def test_an_unknown_game_version_degrades_to_residue(tmp_path, reference):
    mod = _mod(tmp_path, _shapeless("forge:dyes/red"), minecraft=None,
               tag_files={"data/forge/tags/items/dyes/red.json": ["examplemod:red"]}, items=["red"])
    result = recipes.convert(mod)
    assert _recipe_files(result) == {}
    assert "game version" in result.unhandled[0].reason


# -- multi-member forms ------------------------------------------------------------
def test_per_member_recipes_for_a_single_slot_vanilla_tag(tmp_path, reference):
    result = recipes.convert(_mod(tmp_path, _shapeless("forge:chests/wooden")), emitted={})
    files = _recipe_files(result)
    assert set(files) == {"recipes/thing__minecraft_chest.json", "recipes/thing__minecraft_trapped_chest.json"}
    ids = {b["minecraft:recipe_shapeless"]["description"]["identifier"] for b in files.values()}
    assert ids == {"examplemod:thing__minecraft_chest", "examplemod:thing__minecraft_trapped_chest"}
    assert any("once per member" in n for n in result.notes)


def test_a_furnace_recipe_is_written_once_per_member(tmp_path, reference):
    recipe = {"type": "minecraft:smelting", "ingredient": {"tag": "forge:chests/wooden"},
              "result": "examplemod:thing", "experience": 0.1}
    result = recipes.convert(_mod(tmp_path, recipe), emitted={})
    inputs = {b["minecraft:recipe_furnace"]["input"] for b in _recipe_files(result).values()}
    assert inputs == {"minecraft:chest", "minecraft:trapped_chest"}


def test_a_vanilla_only_tag_over_several_slots_is_written_once_per_combination(tmp_path, reference):
    """#302 pick 1: chest + trapped chest over two slots; each mix is its own recipe.
    The two mixed grids are mirror images, which Bedrock's assume_symmetry
    (default true) already matches, so they are one recipe."""
    result = recipes.convert(_mod(tmp_path, _shaped("forge:chests/wooden", ("G G",))), emitted={})
    files = _recipe_files(result)
    assert result.unhandled == []
    assert set(files) == {"recipes/thing__chest__chest.json",
                          "recipes/thing__chest__trapped_chest.json",
                          "recipes/thing__trapped_chest__trapped_chest.json"}
    same = files["recipes/thing__chest__chest.json"]["minecraft:recipe_shaped"]
    assert same["pattern"] == ["G G"] and same["key"] == {"G": {"item": "minecraft:chest"}}
    mixed = files["recipes/thing__chest__trapped_chest.json"]["minecraft:recipe_shaped"]
    (left, _, right) = mixed["pattern"][0]
    assert left != right and " " not in (left, right)
    assert mixed["key"] == {left: {"item": "minecraft:chest"}, right: {"item": "minecraft:trapped_chest"}}
    assert mixed["description"]["identifier"] == "examplemod:thing__chest__trapped_chest"
    assert any("once per combination" in n for n in result.notes)


def test_vanilla_only_combinations_keep_the_other_ingredients(tmp_path, reference):
    recipe = {"type": "minecraft:crafting_shaped", "pattern": ["GSG"],
              "key": {"G": {"tag": "forge:chests/wooden"}, "S": {"item": "minecraft:stick"}},
              "result": {"item": "examplemod:thing"}}
    result = recipes.convert(_mod(tmp_path, recipe), emitted={})
    files = _recipe_files(result)
    assert len(files) == 3  # cc, ct (= tc mirrored), tt
    for body in files.values():
        shaped = body["minecraft:recipe_shaped"]
        assert shaped["key"][shaped["pattern"][0][1]] == {"item": "minecraft:stick"}


def test_shapeless_vanilla_only_combinations_ignore_order(tmp_path, reference):
    recipe = _shapeless("forge:chests/wooden", extra=[{"tag": "forge:chests/wooden"}])
    result = recipes.convert(_mod(tmp_path, recipe), emitted={})
    files = _recipe_files(result)
    assert len(files) == 3  # {c,c}, {c,t}, {t,t}
    assert sorted(sorted(i["item"] for i in b["minecraft:recipe_shapeless"]["ingredients"])
                  for b in files.values()) == [
        ["minecraft:chest", "minecraft:chest"], ["minecraft:chest", "minecraft:trapped_chest"],
        ["minecraft:trapped_chest", "minecraft:trapped_chest"]]


def test_vanilla_only_combinations_over_the_cap_stay_residue(tmp_path, reference):
    """2 members over 5 slots is 32 combinations, over EXPANSION_CAP (16)."""
    result = recipes.convert(_mod(tmp_path, _shaped("forge:chests/wooden", ("GGG", "G G"))), emitted={})
    assert _recipe_files(result) == {}
    (u,) = result.unhandled
    # #342 (pending Alex, pick 2a): still not converted, but explained.
    assert u.kind == recipes.OVER_CAP
    assert "covers 2 items" in u.reason and "(2^5 mixes)" in u.reason and "32 recipes" in u.reason


def test_four_slots_of_two_members_is_at_the_cap(tmp_path, reference):
    result = recipes.convert(_mod(tmp_path, _shaped("forge:chests/wooden", ("GG", "GG"))), emitted={})
    files = _recipe_files(result)
    assert 0 < len(files) <= recipes.EXPANSION_CAP
    grids = set()
    for body in files.values():
        shaped = body["minecraft:recipe_shaped"]
        grid = tuple(tuple(shaped["key"][c]["item"] for c in row) for row in shaped["pattern"])
        assert grid not in grids and tuple(tuple(reversed(r)) for r in grid) not in grids
        grids.add(grid)
    # every one of the 16 grids is a written grid or its mirror image
    import itertools
    members = ("minecraft:chest", "minecraft:trapped_chest")
    for a, b, c, d in itertools.product(members, repeat=4):
        grid = ((a, b), (c, d))
        assert grid in grids or ((b, a), (d, c)) in grids


def test_a_bedrock_vanilla_tag_with_the_same_members_is_used(tmp_path, reference):
    result = recipes.convert(_mod(tmp_path, _shaped("forge:planks_alias")), emitted={})
    files = _recipe_files(result)
    assert list(files) == ["recipes/thing.json"]
    assert files["recipes/thing.json"]["minecraft:recipe_shaped"]["key"] == {"G": {"tag": "minecraft:planks"}}


def test_the_single_item_table_yields_to_the_mods_own_member(tmp_path, reference):
    """forge:rods/wooden used to become minecraft:stick even when the mod adds its own rod."""
    mod = _mod(tmp_path, _shapeless("forge:rods/wooden"), items=["netherwood_stick"],
               tag_files={"data/forge/tags/items/rods/wooden.json": ["examplemod:netherwood_stick"]})
    result = recipes.convert(mod, emitted=_emitted(items=["netherwood_stick"]))
    assert _ingredient_items(result) == {"minecraft:stick", "examplemod:netherwood_stick"}


def test_a_native_tag_when_every_member_is_an_emitted_item(tmp_path, reference):
    mod = _mod(tmp_path, _shaped("examplemod:alloys", ("GGG", "GGG", "GGG")), items=["bronze", "steel"],
               tag_files={"data/examplemod/tags/items/alloys.json": ["examplemod:bronze", "examplemod:steel"]})
    result = recipes.convert(mod, emitted=_emitted(items=["bronze", "steel"]))
    recipe = result.files["recipes/thing.json"]["minecraft:recipe_shaped"]
    assert recipe["key"] == {"G": {"tag": "examplemod:alloys"}}
    for name in ("bronze", "steel"):
        item = result.files[f"items/{name}.json"]
        assert item["minecraft:item"]["components"]["minecraft:tags"] == {"tags": ["examplemod:alloys"]}
        assert item["format_version"] == "1.20.50"


def test_a_member_this_conversion_did_not_emit_blocks_it_and_is_named(tmp_path, reference):
    mod = _mod(tmp_path, _shaped("examplemod:alloys", ("GGG",)), items=["bronze", "steel"],
               tag_files={"data/examplemod/tags/items/alloys.json":
                          ["examplemod:bronze", "examplemod:steel", "examplemod:tin"]})
    result = recipes.convert(mod, emitted=_emitted(items=["bronze", "steel"]))
    assert _recipe_files(result) == {}
    assert result.unhandled[0].reason.endswith("not converted: examplemod:tin")


@pytest.mark.parametrize("count,converts", [(16, True), (17, False)])
def test_the_expansion_cap(tmp_path, reference, count, converts):
    members = [f"minecraft:thing_{i}" for i in range(count)]
    mod = _mod(tmp_path, _shapeless("examplemod:many"),
               tag_files={"data/examplemod/tags/items/many.json": members})
    result = recipes.convert(mod, emitted={})
    assert len(_recipe_files(result)) == (count if converts else 0)
    assert bool(result.unhandled) is not converts


def test_native_tag_output_is_valid_end_to_end(tmp_path, fixtures_dir):
    """agent_mod's alloy recipe minus its unconvertible member: a native tag the validator accepts."""
    src = tmp_path / "src"
    shutil.copytree(fixtures_dir / "agent_mod" / "input", src)
    _write(src, "data/examplemod/tags/items/alloy_ingots.json",
           {"values": ["examplemod:bronze_ingot", "examplemod:steel_ingot"]})
    result = convert(src, tmp_path / "out", emit_addon=False)
    assert result.report.ok, result.report.errors
    assert not [f for f in result.report.findings
                if f.rule in ("xref.tag", "xref.item") and "alloy" in f.path]
    bp = result.tree / "behavior_pack"
    recipe = json.loads((bp / "recipes" / "alloy_block.json").read_text())
    assert recipe["minecraft:recipe_shaped"]["key"] == {"#": {"tag": "examplemod:alloy_ingots"}}
    steel = json.loads((bp / "items" / "steel_ingot.json").read_text())
    assert "examplemod:alloy_ingots" in steel["minecraft:item"]["components"]["minecraft:tags"]["tags"]
    # the sword's recipe waits for the sword (#261), which is residue of its
    # own, so the recipe is owned_by_residue (#302)
    assert sorted(u.source for u in result.unhandled if u.kind == "recipe") == [
        "data/examplemod/recipes/steel_trim.json"]
    assert [u.source for u in result.unhandled if u.kind == "owned_by_residue" and "/recipes/" in u.source] == [
        "data/examplemod/recipes/steel_sword.json"]


def test_the_validator_flags_a_custom_tag_no_item_carries(tmp_path, fixtures_dir):
    src = tmp_path / "src"
    shutil.copytree(fixtures_dir / "agent_mod" / "input", src)
    _write(src, "data/examplemod/tags/items/alloy_ingots.json",
           {"values": ["examplemod:bronze_ingot", "examplemod:steel_ingot"]})
    result = convert(src, tmp_path / "out", emit_addon=False)
    bp = result.tree / "behavior_pack"
    path = bp / "recipes" / "alloy_block.json"
    body = json.loads(path.read_text())
    body["minecraft:recipe_shaped"]["key"]["#"] = {"tag": "examplemod:nobody"}
    body["minecraft:recipe_shaped"]["result"] = {"item": "examplemod:missing"}
    path.write_text(json.dumps(body))
    report = validate_tree(result.tree)
    rules = {(f.rule, f.severity) for f in report.findings if f.path.endswith("alloy_block.json")}
    assert ("xref.tag", "warning") in rules and ("xref.item", "warning") in rules


# -- loader and version detection ---------------------------------------------------
def test_versions_from_each_loaders_metadata():
    toml = b'[[mods]]\nmodId="m"\n[[dependencies.m]]\nmodId="minecraft"\nversionRange="[1.20.1,1.20.2)"\n'
    assert parse_meta({"META-INF/mods.toml": toml}, "m").minecraft == "1.20.1"
    neo = toml.replace(b"[1.20.1,1.20.2)", b"[1.21.1]")
    meta = parse_meta({"META-INF/neoforge.mods.toml": neo}, "m")
    assert (meta.loader, meta.minecraft) == ("neoforge", "1.21.1")
    fabric = json.dumps({"id": "m", "depends": {"minecraft": ["1.21.6", "1.21.8", "1.21.7"]}}).encode()
    assert parse_meta({"fabric.mod.json": fabric}, "m").minecraft == "1.21.8"
    fabric = json.dumps({"id": "m", "depends": {"minecraft": "~26.1"}}).encode()
    assert parse_meta({"fabric.mod.json": fabric}, "m").minecraft == "26.1"
    assert parse_meta({"fabric.mod.json": b'{"id": "m"}'}, "m").minecraft is None


@pytest.mark.parametrize("loader,minecraft,expected", [
    ("forge", "1.20.1", ["forge-1.20.1", "vanilla-1.20.1"]),
    ("forge", "1.16.3", ["forge-1.20.1", "vanilla-1.16.5"]),
    ("neoforge", "1.21.4", ["neoforge-1.21.1", "vanilla-1.21.1"]),
    ("neoforge", "1.20.1", ["forge-1.20.1", "vanilla-1.20.1"]),
    ("fabric", "1.20.1", ["fabric-1.20.1", "vanilla-1.20.1"]),
    ("fabric", "1.21", ["fabric-1.21.1", "vanilla-1.21.1"]),
    ("fabric", "26.1", ["fabric-26.1", "vanilla-26.1"]),
    ("forge-legacy", "1.12.2", []),
    ("forge", None, []),
    (None, "1.20.1", ["vanilla-1.20.1"]),
])
def test_the_nearest_tag_data(loader, minecraft, expected):
    assert [s.id for s in tag_data.select(loader, minecraft)] == expected


# -- fetching ------------------------------------------------------------------------
def _fake_jar() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data/forge/tags/items/glass/colorless.json", json.dumps({"values": ["minecraft:glass"]}))
        zf.writestr("data/forge/tags/blocks/glass.json", json.dumps({"values": ["minecraft:glass"]}))
        zf.writestr("data/minecraft/tags/items/planks.json", json.dumps({"values": ["x:y"]}))
        zf.writestr("net/minecraftforge/Foo.class", b"\0")
    return buf.getvalue()


def _opener(payload, calls=None):
    def opener(request, timeout):
        if calls is not None:
            calls.append(request.full_url)
        return io.BytesIO(payload)
    return opener


@pytest.fixture
def forge_pinned(monkeypatch, tmp_path):
    base = tag_data.BY_ID["forge-1.20.1"]
    digest = hashlib.sha256(tag_data.derive(base, _fake_jar())).hexdigest()
    pinned = tag_data.TagSet(**{**base.__dict__, "sha256": digest})
    cache = tmp_path / "cache"
    monkeypatch.setenv("PORTKIT_REFERENCE_CACHE", str(cache))
    return pinned, cache


def test_nothing_from_the_loaders_or_mojang_is_vendored():
    package = Path(tag_data.__file__).parent
    assert not list(package.glob("tags-*.json")) and not list(package.glob("*.jar"))
    for tag_set in tag_data.SETS:
        assert len(tag_set.sha256) == 64
        assert tag_set.url.startswith(("https://maven.", "https://raw.githubusercontent.com/misode/mcmeta/"))


def test_derive_keeps_only_item_tags_in_the_sets_namespaces(forge_pinned):
    pinned, _ = forge_pinned
    derived = json.loads(tag_data.derive(pinned, _fake_jar()))
    assert derived["tags"] == {"forge:glass/colorless": ["minecraft:glass"]}


def test_fetch_verifies_caches_and_is_then_read(forge_pinned):
    pinned, cache = forge_pinned
    calls = []
    path, downloaded = tag_data.fetch(pinned, opener=_opener(_fake_jar(), calls))
    assert downloaded and path.parent == cache and calls == [pinned.url]
    assert tag_data.fetch(pinned, opener=_opener(b"unused", calls)) == (path, False)
    assert len(calls) == 1
    assert tag_data.load(pinned) == {"forge:glass/colorless": ["minecraft:glass"]}


def test_a_changed_upstream_is_refused(forge_pinned):
    pinned, cache = forge_pinned
    changed = tag_data.TagSet(**{**pinned.__dict__, "sha256": "0" * 64})
    with pytest.raises(data.ReferenceDataError, match="sha256 mismatch"):
        tag_data.fetch(changed, opener=_opener(_fake_jar()))
    assert not cache.exists() or not any(cache.iterdir())


def test_a_download_failure_is_named(forge_pinned):
    pinned, _ = forge_pinned

    def opener(request, timeout):
        raise OSError("no network")
    with pytest.raises(data.ReferenceDataError, match="download failed"):
        tag_data.fetch(pinned, opener=opener)


def test_a_tampered_cache_counts_as_missing(forge_pinned):
    pinned, _ = forge_pinned
    path, _ = tag_data.fetch(pinned, opener=_opener(_fake_jar()))
    path.write_text(path.read_text().replace("minecraft:glass", "minecraft:dirt"))
    assert tag_data.cached(pinned) is None
    assert tag_data.load(pinned) is None


def test_cli_reference_list_and_fetch_for_one_mod(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PORTKIT_REFERENCE_CACHE", str(tmp_path / "cache"))
    mod = tmp_path / "mod"
    _write(mod, "META-INF/mods.toml",
           '[[mods]]\nmodId="examplemod"\n[[dependencies.examplemod]]\nmodId="minecraft"\nversionRange="[1.20.1]"\n')
    _write(mod, "assets/examplemod/lang/en_us.json", {})
    fetched = []
    monkeypatch.setattr(data, "fetch_sounds", lambda cache=None: (Path("sounds"), False))
    monkeypatch.setattr(tag_data, "fetch", lambda s, cache=None: fetched.append(s.id) or (Path(s.id), True))
    assert cli.main(["reference", "fetch", "--mod", str(mod)]) == 0
    assert fetched == ["forge-1.20.1", "vanilla-1.20.1"]
    assert "loader forge, minecraft 1.20.1" in capsys.readouterr().out
    assert cli.main(["reference", "list"]) == 0
    out = capsys.readouterr().out
    assert "tags-neoforge-1.21.1" in out and "missing" in out


def test_resolver_reads_the_reference_for_the_mods_loader(tmp_path, reference):
    mod = SourceMod(root=tmp_path, namespace="examplemod", loader="neoforge", minecraft="1.21.1")
    resolver = TagResolver(mod)
    assert resolver.reference.covers("c:foods/vegetable")
    assert not resolver.reference.covers("fabric:anything")
    assert [m for m in resolver.members("c:foods/vegetable").members] == ["minecraft:carrot", "minecraft:potato"]


# -- #309: combination key symbols don't depend on string hashing ----------------
_MIX_TAG = "data/examplemod/tags/items/mix.json"
_MIX = ["minecraft:oak_planks", "minecraft:spruce_planks", "minecraft:birch_planks", "minecraft:jungle_planks"]


def test_combination_symbols_follow_the_slots_reading_order(tmp_path, reference):
    """A mixed slot's members take fresh symbols in the order their slots
    read, row by row (#309), so the left one is always A."""
    mod = _mod(tmp_path, _shaped("examplemod:mix", ("G G",)), tag_files={_MIX_TAG: _MIX})
    files = _recipe_files(recipes.convert(mod, emitted={}))
    mixed = files["recipes/thing__oak_planks__spruce_planks.json"]["minecraft:recipe_shaped"]
    assert mixed["pattern"] == ["A B"]
    assert mixed["key"] == {"A": {"item": "minecraft:oak_planks"}, "B": {"item": "minecraft:spruce_planks"}}


_SEED_SCRIPT = """
import json, sys
from pathlib import Path
from portkit.converters import recipes
from portkit.model import SourceMod
mod = SourceMod(root=Path(sys.argv[1]), namespace="examplemod", loader="forge", minecraft="1.20.1")
result = recipes.convert(mod, emitted={})
print(json.dumps({k: v for k, v in result.files.items() if k.startswith("recipes/")}, sort_keys=True))
"""


def test_combination_recipes_are_the_same_bytes_under_two_hash_seeds(tmp_path, reference):
    """#309: the same jar converts to the same recipes whatever PYTHONHASHSEED is.
    Seeds 1 and 4 iterate a set of these members in different orders (on
    CPython 3.12 the old set-ordered symbols gave different bytes for them)."""
    import os
    import subprocess
    import sys

    mod = _mod(tmp_path, _shaped("examplemod:mix", ("G G",)), tag_files={_MIX_TAG: _MIX})
    outputs = []
    for seed in ("1", "4"):
        # the child imports the same portkit this test does
        src = str(Path(recipes.__file__).resolve().parents[2])
        env = {**os.environ, "PYTHONHASHSEED": seed,
               "PYTHONPATH": os.pathsep.join(filter(None, (src, os.environ.get("PYTHONPATH"))))}
        run = subprocess.run([sys.executable, "-c", _SEED_SCRIPT, str(mod.root)], env=env,
                             capture_output=True, text=True, check=True)
        outputs.append(run.stdout)
    assert json.loads(outputs[0])  # the combinations were written at all
    assert outputs[0] == outputs[1]
