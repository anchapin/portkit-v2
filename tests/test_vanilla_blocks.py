"""The vanilla ``Blocks`` field -> registry id table and the names of variants of vanilla
blocks (#280, portkit.data.vanilla_blocks and portkit.blockcode).

tests/data/vanillablocks/classes are javac 21 output (build.sh): stand-ins for the
vanilla classes the table is derived from (``Blocks#<clinit>`` registering by a string
id, by a 1.21-style ``ResourceKey`` constant, a field whose id isn't its lower-cased name,
a field assigned another way and a non-block static). tests/data/vanillacode/classes
(build.sh) is an example mod in Quark's vertical slab shape, read with the example
library of tests/data/inheritcode.
"""
from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from portkit import blockcode
from portkit.blockcode import UNKNOWN, Arr, Coll, Const, Machine, Obj
from portkit.bytecode import ClassIndex
from portkit.data import ReferenceDataError
from portkit.data import mappings, vanilla_blocks
from portkit.meta import parse as parse_metadata

DATA = Path(__file__).parent / "data"
BLOCKS = "net/minecraft/world/level/block/Blocks"


def _entries(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix()[:-6]: p.read_bytes() for p in root.rglob("*.class")}


# --- deriving the table -----------------------------------------------------

def _client_txt() -> bytes:
    """Mojang's client.txt format, every name mapped to itself (the stand-ins aren't obfuscated)."""
    lines = ["# test mappings"]
    for cls, fields in {
        "net.minecraft.world.level.block.Blocks": ["net.minecraft.world.level.block.Block OAK_PLANKS",
                                                    "net.minecraft.world.level.block.Block POTTED_AZALEA",
                                                    "net.minecraft.world.level.block.Block PUMPKIN",
                                                    "net.minecraft.world.level.block.Block ODD",
                                                    "java.util.function.Predicate NOT_A_BLOCK"],
        "net.minecraft.world.level.block.Block": [],
        "net.minecraft.world.level.block.FlowerPotBlock": [],
        "net.minecraft.resources.ResourceKey": [],
        "net.minecraft.references.Blocks": ["net.minecraft.resources.ResourceKey PUMPKIN"],
    }.items():
        lines.append(f"{cls} -> {cls}:")
        lines += [f"    {f} -> {f.split(' ')[1]}" for f in fields]
    return ("\n".join(lines) + "\n").encode()


def _jar(blockstates=("oak_planks", "potted_azalea_bush")) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in _entries(DATA / "vanillablocks" / "classes").items():
            zf.writestr(name + ".class", data)
        for b in blockstates:
            zf.writestr(f"assets/minecraft/blockstates/{b}.json", "{}")
    return buf.getvalue()


SET = vanilla_blocks.BlockIdSet("vanilla-blocks-test", "1.21.1", "0" * 40, "0" * 40, "0" * 64)


def test_derive_reads_each_block_field_from_the_static_initializer():
    table = json.loads(vanilla_blocks.derive(SET, _jar(), _client_txt()))
    # A string id, an id that isn't the lower-cased field name, and a
    # ResourceKey constant built from an id in another class.
    assert table["blocks"] == {"OAK_PLANKS": "oak_planks", "POTTED_AZALEA": "potted_azalea_bush",
                               "PUMPKIN": "pumpkin"}
    # A block field assigned another way is listed, not guessed; a static
    # that isn't a block is left out.
    assert table["unmatched"] == ["ODD"]
    # Every id is checked against the jar's blockstates.
    assert table["no_blockstate"] == ["pumpkin"]
    assert table["sources"] == [SET.jar_url, SET.mojang_url]
    assert "never vendored" in table["notice"]


def test_derive_is_deterministic():
    assert vanilla_blocks.derive(SET, _jar(), _client_txt()) == vanilla_blocks.derive(SET, _jar(), _client_txt())


def test_download_checks_both_pins_then_the_derived_table(tmp_path):
    jar, txt = _jar(), _client_txt()
    unpinned = vanilla_blocks.BlockIdSet("vanilla-blocks-test", "1.21.1", hashlib.sha1(jar).hexdigest(),
                                        hashlib.sha1(txt).hexdigest(), "")
    derived = vanilla_blocks.derive(unpinned, jar, txt)
    pinned = dataclasses.replace(unpinned, sha256=hashlib.sha256(derived).hexdigest())
    files = {pinned.jar_url: jar, pinned.mojang_url: txt}

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def opener(request, timeout=None):
        return Response(files[request.full_url])

    path, downloaded = vanilla_blocks.fetch(pinned, tmp_path, opener)
    assert downloaded and path.read_bytes() == derived
    assert vanilla_blocks.fetch(pinned, tmp_path, opener) == (path, False)
    files[pinned.jar_url] = jar + b"x"
    with pytest.raises(ReferenceDataError, match="sha1 mismatch"):
        vanilla_blocks.download(pinned, opener)


def test_the_pinned_sets_are_the_mapping_versions_with_mojangs_pins():
    by_version = {m.minecraft: m.mojang_sha1 for m in mappings.SETS}
    assert {s.minecraft for s in vanilla_blocks.SETS} == set(by_version)
    for s in vanilla_blocks.SETS:
        # The same client.txt the name mappings are joined from.
        assert s.mojang_sha1 == by_version[s.minecraft]
        assert len(s.jar_sha1) == 40 and len(s.sha256) == 64
    assert len({s.id for s in vanilla_blocks.SETS}) == len(vanilla_blocks.SETS)


def test_select_takes_exactly_the_declared_version():
    assert vanilla_blocks.select("1.20.1").minecraft == "1.20.1"
    assert vanilla_blocks.select("1.21.0").minecraft == "1.21"
    assert vanilla_blocks.select("1.20.4") is None
    assert vanilla_blocks.select(None) is None


def test_table_override_and_attach(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTKIT_VANILLA_BLOCKS", str(tmp_path))
    s = vanilla_blocks.select("1.21.1")
    assert vanilla_blocks.table(s) is None
    (tmp_path / f"{s.id}.json").write_text(json.dumps({"blocks": {"STONE": "stone"}}))
    assert vanilla_blocks.table(s) == {"STONE": "stone"}
    index = ClassIndex({})
    vanilla_blocks.attach(index, "1.20.4")
    assert index.vanilla_blocks is None
    vanilla_blocks.attach(index, "1.21.1")
    assert index.vanilla_blocks == {"STONE": "stone"}


def test_nothing_derived_from_mojang_is_vendored():
    root = Path(__file__).parent.parent / "src" / "portkit"
    assert not list(root.rglob("vanilla-blocks-*.json"))


# --- the game version of a NeoForge jar that names no minecraft dependency ---

def _neoforge(deps: str) -> bytes:
    return (f'modLoader="javafml"\nloaderVersion="[1,)"\nlicense="MIT"\n[[mods]]\nmodId="x"\n'
            f'version="1"\n{deps}').encode()


@pytest.mark.parametrize("range_, expected", [
    ("[21.1.252,)", "1.21.1"), ("[20.4.80,)", "1.20.4"), ("[21.0.5,)", "1.21"),
    ("[47.1.0,)", None), ("[26.1.0.5,)", None),
])
def test_neoforge_dependency_names_the_game_version(range_, expected):
    meta = parse_metadata({"META-INF/neoforge.mods.toml": _neoforge(
        f'[[dependencies.x]]\nmodId="neoforge"\ntype="required"\nversionRange="{range_}"\n')}, "")
    assert meta.minecraft is None
    assert meta.loader_minecraft == expected


def test_a_declared_minecraft_dependency_wins():
    meta = parse_metadata({"META-INF/neoforge.mods.toml": _neoforge(
        '[[dependencies.x]]\nmodId="neoforge"\nversionRange="[21.1.1,)"\n'
        '[[dependencies.x]]\nmodId="minecraft"\nversionRange="[1.21.1,1.22)"\n')}, "")
    assert meta.minecraft == "1.21.1"
    assert meta.loader_minecraft is None


# --- names of variants of vanilla blocks --------------------------------------

def _inherit_index(table=None) -> ClassIndex:
    index = ClassIndex(_entries(DATA / "inheritcode" / "classes"), _entries(DATA / "inheritcode" / "library"))
    index.vanilla_blocks = table
    return index


def test_a_slab_of_a_vanilla_block_is_named_from_the_table():
    _m, reg = blockcode._registered(_inherit_index({"STONE": "stone"}), ["jade_bricks", "stone_slab"])
    objs, why = reg["stone_slab"]
    assert objs and objs[0].cls == "net/minecraft/world/level/block/SlabBlock", why


@pytest.mark.parametrize("table", [None, {"GLOWSTONE": "glowstone"}])
def test_without_the_field_in_the_table_the_vanilla_variant_stays_unread(table):
    _m, reg = blockcode._registered(_inherit_index(table), ["jade_bricks", "stone_slab"])
    assert reg["stone_slab"][0] == []


def _vertical_index(table) -> ClassIndex:
    index = ClassIndex(_entries(DATA / "vanillacode" / "classes"), _entries(DATA / "inheritcode" / "library"))
    index.vanilla_blocks = table
    return index


def test_vertical_slabs_of_vanilla_blocks_built_in_a_foreach_are_read():
    names = ["stone_vertical_slab", "glowstone_vertical_slab"]
    _m, reg = blockcode._registered(_vertical_index({"STONE": "stone", "GLOWSTONE": "glowstone"}), names)
    for name in names:
        objs, why = reg[name]
        assert objs and objs[0].cls == "com/example/vmod/VerticalSlab", (name, why)
    _m, reg = blockcode._registered(_vertical_index(None), names)
    assert all(reg[n][0] == [] for n in names)


def test_the_constructor_that_writes_after_the_lookup_reads_whole():
    # Each way of Zeta's lookup writes the same module to the block it builds,
    # so the ways join where the constructor returns (tests/test_fork_join.py)
    # and the reading is whole.
    readings = blockcode.read_blocks(_vertical_index({"STONE": "stone", "GLOWSTONE": "glowstone"}),
                                     ["stone_vertical_slab"])
    r = readings["stone_vertical_slab"]
    assert r.cls == "com.example.vmod.VerticalSlab"
    assert r.shape_why == ""
    assert r.shape_from


# --- interpreter pieces ---------------------------------------------------------

def _machine(table=None) -> Machine:
    index = ClassIndex({})
    index.vanilla_blocks = table
    return Machine(index)


def test_get_key_of_a_vanilla_constant():
    m = _machine({"OAK_SLAB": "oak_slab"})
    reg = Const("net/minecraft/core/registries/BuiltInRegistries", "BLOCK")
    desc = "(Ljava/lang/Object;)Lnet/minecraft/resources/ResourceLocation;"
    out = m.call("net/minecraft/core/Registry", "getKey", desc, [reg, Const(BLOCKS, "OAK_SLAB")])
    assert out == [blockcode.RL("minecraft:oak_slab", True)]
    assert m.call("net/minecraft/core/Registry", "getKey", desc, [reg, Const(BLOCKS, "BIRCH_SLAB")]) == [UNKNOWN]


def test_immutable_collections():
    m = _machine()
    a, b = Const(BLOCKS, "A"), Const(BLOCKS, "B")
    guava = "(Ljava/lang/Object;Ljava/lang/Object;[Ljava/lang/Object;)Lcom/google/common/collect/ImmutableSet;"
    out = m.call("com/google/common/collect/ImmutableSet", "of", guava, [a, b, Arr([a, "c"])], static=True)
    assert out == [Coll((a, b, "c"))]  # the first of equal elements, in order
    lst = "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/List;"
    assert m.call("java/util/List", "of", lst, [a, a], static=True) == [Coll((a, a))]
    assert m.call("java/util/List", "of", "([Ljava/lang/Object;)Ljava/util/List;", [UNKNOWN], static=True) == [UNKNOWN]
    # Set.of's iteration order is unspecified.
    st = "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/Set;"
    assert m.call("java/util/Set", "of", st, [a, b], static=True) == [UNKNOWN]
    assert m.call("com/google/common/collect/ImmutableSet", "of", st.replace("java/util/Set",
                  "com/google/common/collect/ImmutableSet"), [a, UNKNOWN], static=True) == [UNKNOWN]


def test_a_vanilla_constant_is_no_instance_of_a_jar_type():
    m = Machine(ClassIndex({"com/x/Mine": b""}))
    m.classes.vanilla_blocks = {"STONE": "stone"}
    m.classes.get = lambda name, remap=True: object() if name == "com/x/Mine" else None
    assert m.instance_of(Const(BLOCKS, "STONE"), "com/x/Mine") == 0
    assert m.instance_of(Const(BLOCKS, "STONE"), "net/minecraft/world/level/block/SlabBlock") is UNKNOWN


def test_a_map_put_registers_nothing():
    m = _machine()
    m.registrations = []
    block = Obj("net/minecraft/world/level/block/Block")
    m.call("java/util/Map", "put", "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;",
           [UNKNOWN, block, "myalite"])
    assert m.registrations == []
    m.call("com/example/Registry", "register", "(Ljava/lang/String;Ljava/lang/Object;)V",
           [UNKNOWN, "myalite", block])
    assert [r.name for r in m.registrations] == ["myalite"]
