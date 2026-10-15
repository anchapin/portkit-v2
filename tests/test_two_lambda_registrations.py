"""A block registered with its item in the same call, as two lambdas
(MrCrayfish Framework's RegistryEntry.blockWithItem(id, Supplier<T>,
Function<T, E>)): portkit.blockcode picks the lambda that builds the block by
its dynamicMethodType (takes nothing, returns a block class), and leaves
the block unread when that doesn't single one out.

The class files under tests/data/blockcode/classes are javac 21 output of the
example mod in tests/data/blockcode/src (PairBlocks.java; the registry helper
com.example.registry.Entry is a stub outside the jar, like Framework). Rebuild
with build.sh: real compiler patterns, no Minecraft code.
"""
from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import pytest

from portkit import blockcode
from portkit.bytecode import ClassIndex
from portkit.converters import blocks
from portkit.model import SourceMod

CLASSES = Path(__file__).parent / "data" / "blockcode" / "classes"
CARDINALS = ("north", "east", "south", "west")
PAIRS = ["pair_lamp", "pair_statue", "pair_flipped", "pair_item_supplier", "pair_two_blocks", "pair_erased"]


@pytest.fixture(scope="module")
def index():
    return ClassIndex.from_source(CLASSES)


@pytest.fixture(scope="module")
def readings(index):
    return blockcode.read_blocks(index, [*PAIRS, "lamp", "statue"])


@pytest.fixture(scope="module")
def light(index):
    return blockcode.read_light(index, PAIRS)


# --- which lambda is the block ----------------------------------------------------

def test_supplier_then_item_function_reads_the_supplier(readings, light):
    pair, lamp = readings["pair_lamp"], readings["lamp"]
    assert pair.cls == "com.example.deco.LampBlock"
    # The same block class as `lamp`, so the same facing and box are read...
    assert (pair.placement, pair.shapes) == (lamp.placement, lamp.shapes)
    assert pair.placement == 180
    # ...and the supplier's own Properties: noCollission and lightLevel(s -> 6).
    assert pair.collision is False
    assert (light["pair_lamp"].value, light["pair_lamp"].kind) == (6, "constant")
    assert light["pair_lamp"].source == "com.example.deco.PairBlocks#lambda$static$0"


def test_constructor_and_method_references(readings, light):
    pair, statue = readings["pair_statue"], readings["statue"]
    assert pair.cls == "com.example.deco.StatueBlock"
    assert (pair.placement, pair.shapes, pair.collision) == (statue.placement, statue.shapes, statue.collision)
    assert (light["pair_statue"].value, light["pair_statue"].kind) == (0, "dark")


def test_argument_order_does_not_matter(readings, light):
    # itemThenBlock(id, b -> new BlockItem(b, ..), () -> new Block(..)).
    assert readings["pair_flipped"].cls == "net.minecraft.world.level.block.Block"
    assert light["pair_flipped"].value == 9


def test_a_supplier_of_an_item_is_not_the_block(readings, light):
    # Both take nothing; only one returns a block class.
    assert readings["pair_item_supplier"].cls == "net.minecraft.world.level.block.Block"
    assert light["pair_item_supplier"].value == 4


def test_two_block_suppliers_are_unread(readings, light):
    r = readings["pair_two_blocks"]
    assert r.cls is None and r.placement is None and r.shapes is None and r.collision is None
    assert "passes 2 lambdas and 2 of them take no arguments and return a block class" in r.placement_why
    assert r.placement_why == r.shape_why == r.collision_why
    assert light["pair_two_blocks"].value is None
    assert "can't be told" in light["pair_two_blocks"].why


def test_erased_return_type_is_unread(readings, light):
    # A Supplier<?> lambda's dynamicMethodType is ()Ljava/lang/Object;.
    r = readings["pair_erased"]
    assert r.cls is None
    assert "passes 2 lambdas and 0 of them take no arguments and return a block class" in r.placement_why
    assert light["pair_erased"].value is None


def test_lambdas_carry_their_instantiated_method_type(index):
    machine = blockcode.Machine(index)
    machine.registrations = []
    machine.init_class("com/example/deco/PairBlocks")
    by_name = {r.name: r for r in machine.registrations}
    assert by_name["pair_lamp"].value.itype == "()Lcom/example/deco/LampBlock;"
    assert by_name["pair_statue"].value.handle.kind == 8  # StatueBlock::new
    assert by_name["pair_two_blocks"].value is None


def test_single_lambda_registrations_are_unchanged(index):
    # ModBlocks registers one lambda per call; nothing about those changes.
    r = blockcode.read_blocks(index, ["lamp", "statue", "vase", "odd", "fan", "ghost"])
    assert r["lamp"].cls == "com.example.deco.LampBlock" and r["lamp"].placement == 180
    assert r["statue"].cls == "com.example.deco.StatueBlock"
    assert r["ghost"].cls is None and "no registration" in r["ghost"].placement_why


# --- converting -----------------------------------------------------------------

def _png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    raw = b"".join(b"\x00" + b"\x80\x60\x40\xff" * 16 for _ in range(16))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _mod(tmp_path: Path) -> SourceMod:
    root, ns = tmp_path / "mod", "examplemod"
    (root / f"assets/{ns}/textures/block").mkdir(parents=True)
    (root / f"assets/{ns}/textures/block/wood.png").write_bytes(_png())
    faces = {f: {"texture": "#all"} for f in ("north", "south", "east", "west", "up", "down")}
    model = {"textures": {"all": f"{ns}:block/wood", "particle": f"{ns}:block/wood"}, "elements": [
        {"from": [4, 0, 10], "to": [12, 4, 16], "faces": faces},
        {"from": [5, 4, 11], "to": [11, 12, 15], "faces": faces}]}
    for name in ("pair_lamp", "pair_two_blocks"):
        (root / f"assets/{ns}/models/block").mkdir(parents=True, exist_ok=True)
        (root / f"assets/{ns}/models/block/{name}.json").write_text(json.dumps(model))
        variants = {f"facing={d}": {"model": f"{ns}:block/{name}", **({"y": t} if t else {})}
                    for d, t in zip(CARDINALS, (0, 90, 180, 270))}
        (root / f"assets/{ns}/blockstates").mkdir(parents=True, exist_ok=True)
        (root / f"assets/{ns}/blockstates/{name}.json").write_text(json.dumps({"variants": variants}))
    return SourceMod(root=root, namespace=ns, classes=ClassIndex.from_source(CLASSES))


def test_two_lambda_block_converts_with_read_values(tmp_path):
    result = blocks.convert(_mod(tmp_path))
    lamp = result.files["blocks/pair_lamp.json"]["minecraft:block"]
    traits = lamp["description"]["traits"]["minecraft:placement_direction"]
    assert traits["y_rotation_offset"] == 180
    assert lamp["components"]["minecraft:light_emission"] == 6
    assert lamp["components"]["minecraft:collision_box"] is False
    notes = "\n".join(result.notes)
    assert "pair_lamp" in notes
    # The ambiguous one still converts, on the labelled defaults.
    assert "blocks/pair_two_blocks.json" in result.files
    default = [n for n in result.notes if n.startswith("Facing placement DEFAULT")]
    assert default and "pair_two_blocks" in default[0] and "can't be told" in default[0]
