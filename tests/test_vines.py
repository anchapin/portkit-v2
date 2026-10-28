"""Vines placed by vanilla VineBlock's code (#296), and blockstates under an
id the mod's code aliases to another namespace's block.

A blockstate drawing vanilla VineBlock's five faces (``up``, ``north``,
``south``, ``west``, ``east``, every combination) converts through the
directional reader's ``vine`` kind when the block's class is a VineBlock
whose placement it inherits: one face per placement (the clicked face's
opposite; a clicked top face gives the player's facing), the box from
VineBlock#calculateShape, the other 27 variants held out. A vine whose own
placement replaces VineBlock's, or a class that isn't a VineBlock, stays
residue.

The class files under tests/data/vine/classes are javac 21 output of
tests/data/vine/src (rebuild with build.sh) against
tests/data/blockcode/stubs; tests/data/quarkalias/classes have the shape of
Quark 4.1's QuarkRemapHandler (build.sh there): real compiler patterns, no
Minecraft or Quark code.
"""
from __future__ import annotations

import itertools
import json
import struct
import zlib
from pathlib import Path

import pytest

from portkit import blockcode
from portkit.adapters import quark
from portkit.bytecode import ClassIndex
from portkit.converters import blocks
from portkit.model import SourceMod

DATA = Path(__file__).parent / "data"
CLASSES = DATA / "vine" / "classes"
ALIAS = DATA / "quarkalias" / "classes"
NS = "examplemod"
FACES = ("east", "north", "south", "up", "west")
SIDE_Y = {"south": 0, "west": 90, "north": 180, "east": 270}


def _png() -> bytes:
    raw = b"".join(b"\x00" + b"\x40\x80\x40\xff" * 16 for _ in range(16))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _plane(ns: str, stem: str, frm, to, faces) -> dict:
    return {"textures": {"vine": f"{ns}:block/{stem}", "particle": f"{ns}:block/{stem}"},
            "elements": [{"from": frm, "to": to, "shade": False,
                          "faces": {f: {"uv": [0, 0, 16, 16], "texture": "#vine", "tintindex": 0} for f in faces}}]}


def _vine_blockstate(ns: str, stem: str) -> dict:
    variants = {}
    for values in itertools.product(("false", "true"), repeat=5):
        cell = dict(zip(FACES, values))
        key = ",".join(f"{f}={cell[f]}" for f in FACES)
        on = [f for f in FACES if cell[f] == "true"]
        if on == ["up"]:
            variants[key] = {"model": f"{ns}:block/{stem}_u"}
        elif len(on) == 1:
            variants[key] = {"model": f"{ns}:block/{stem}_1", **({"y": SIDE_Y[on[0]]} if SIDE_Y[on[0]] else {})}
        elif not on:
            variants[key] = {"model": f"{ns}:block/{stem}_1"}
        else:
            variants[key] = {"model": f"{ns}:block/{stem}_{min(len(on), 4)}"}
    return {"variants": variants}


def _write_vine(root: Path, ns: str, stem: str) -> None:
    (root / f"assets/{ns}/textures/block/{stem}.png").write_bytes(_png())
    models = root / f"assets/{ns}/models/block"
    (models / f"{stem}_1.json").write_text(json.dumps(_plane(ns, stem, [0, 0, 15.2], [16, 16, 15.2], ("north", "south"))))
    (models / f"{stem}_u.json").write_text(json.dumps(_plane(ns, stem, [0, 15.2, 0], [16, 15.2, 16], ("up", "down"))))
    for n in (2, 3, 4):
        (models / f"{stem}_{n}.json").write_text(json.dumps(
            _plane(ns, stem, [0, 0, 15.2], [16, 16, 15.2], ("north", "south"))))
    (root / f"assets/{ns}/blockstates/{stem}.json").write_text(json.dumps(_vine_blockstate(ns, stem)))


def _dirs(root: Path, ns: str) -> None:
    for sub in ("textures/block", "models/block", "blockstates"):
        (root / f"assets/{ns}/{sub}").mkdir(parents=True, exist_ok=True)


def _mod(tmp_path: Path) -> SourceMod:
    root = tmp_path / "mod"
    _dirs(root, NS)
    for stem in ("cut_vine", "plain_vine", "own_vine", "fake_vine"):
        _write_vine(root, NS, stem)
    tags = root / "data/minecraft/tags/block"
    tags.mkdir(parents=True)
    (tags / "climbable.json").write_text(json.dumps({"values": [f"{NS}:cut_vine"]}))
    return SourceMod(root=root, namespace=NS, classes=ClassIndex.from_source(CLASSES))


@pytest.fixture()
def converted(tmp_path):
    return blocks.convert(_mod(tmp_path))


def _reason(result, stem: str) -> str:
    return next(u.reason for u in result.unhandled if u.source.endswith(f"blockstates/{stem}.json"))


def test_vine_placement_read_from_vanilla_vine_block():
    got = blockcode.read_directional(ClassIndex.from_source(CLASSES),
                                     {s: "vine" for s in ("cut_vine", "plain_vine", "own_vine", "fake_vine")})
    rule = {"down": ("", ("dir", "up")), "up": ("", ("player", 0)), "north": ("", ("dir", "south")),
            "south": ("", ("dir", "north")), "west": ("", ("dir", "east")), "east": ("", ("dir", "west"))}
    for stem in ("cut_vine", "plain_vine"):
        r = got[stem]
        assert r.rule == rule
        assert r.rule_from.startswith("net.minecraft.world.level.block.VineBlock#getStateForPlacement L315-329")
        assert r.support_assumed
        # VineBlock#calculateShape, one face's box per key.
        assert r.shapes_by == {("", "up"): ((0.0, 15.0, 0.0, 16.0, 16.0, 16.0),),
                               ("", "north"): ((0.0, 0.0, 0.0, 16.0, 16.0, 1.0),),
                               ("", "south"): ((0.0, 0.0, 15.0, 16.0, 16.0, 16.0),),
                               ("", "west"): ((0.0, 0.0, 0.0, 1.0, 16.0, 16.0),),
                               ("", "east"): ((15.0, 0.0, 0.0, 16.0, 16.0, 16.0),)}
        assert r.collision is False
    assert got["own_vine"].rule is None
    assert "replaces vanilla VineBlock's" in got["own_vine"].rule_why
    assert got["fake_vine"].rule is None
    assert "isn't a vanilla VineBlock" in got["fake_vine"].rule_why


def test_vine_converts_with_one_face_per_placement(converted):
    for stem in ("cut_vine", "plain_vine"):
        assert f"blocks/{stem}.json" in converted.files
        assert f"models/blocks/{stem}.geo.json" in converted.files
        assert not [u for u in converted.unhandled if u.source.endswith(f"blockstates/{stem}.json")]
    block = converted.files["blocks/cut_vine.json"]["minecraft:block"]
    traits = block["description"]["traits"]
    assert traits["minecraft:placement_position"]["enabled_states"] == ["minecraft:block_face"]
    assert traits["minecraft:placement_direction"]["enabled_states"] == ["minecraft:cardinal_direction"]
    assert "states" not in block["description"]
    perms = {p["condition"]: p["components"] for p in block["permutations"]}
    # Clicked bottom face: the vine hangs from the block above (up=true).
    up = perms["q.block_state('minecraft:block_face') == 'down'"]
    assert up["minecraft:selection_box"] == {"origin": [-8, 15, -8], "size": [16, 1, 16]}
    assert up["minecraft:collision_box"] is False
    # Clicked south face (the block north of it holds it): north=true, the
    # side model turned y=180, as is a clicked top face with the player
    # facing north.
    north = perms["(q.block_state('minecraft:block_face') == 'south') || "
                  "(q.block_state('minecraft:block_face') == 'up' && "
                  "q.block_state('minecraft:cardinal_direction') == 'north')"]
    assert north["minecraft:transformation"] == {"rotation": [0, 180, 0]}
    # Only the single-face models are drawn; the others were read and passed over.
    geo = json.dumps(converted.files["models/blocks/cut_vine.geo.json"])
    assert geo.count('"name": "m') == 2
    for n in (2, 3, 4):
        assert any(c.endswith(f"models/block/cut_vine_{n}.json") for c in converted.consumed)


def test_vine_notes_say_what_is_held_out_and_lost(converted):
    notes = "\n".join(converted.notes)
    assert "Vines (#296)" in notes and "27 variant(s): cut_vine, plain_vine" in notes
    climb = next(n for n in converted.notes if n.startswith("Not climbable"))
    assert climb.endswith("- cut_vine.")  # only the jar's tag lists it
    tint = next(n for n in converted.notes if n.startswith("The model's faces carry a tintindex"))
    assert "cut_vine" in tint and "plain_vine" in tint
    rule = next(n for n in converted.notes if n.startswith("Placement rule read from bytecode"))
    assert "clicked up: the face set is the player's facing" in rule


def test_vines_not_placed_by_vine_block_stay_residue(converted):
    for stem in ("own_vine", "fake_vine"):
        assert f"blocks/{stem}.json" not in converted.files
        assert _reason(converted, stem).startswith("vine faces: placement isn't read (")
        assert _reason(converted, stem).endswith("and no DEFAULT covers a vine's faces")
    assert "replaces vanilla VineBlock's" in _reason(converted, "own_vine")


def test_quark_aliases_read_in_shape():
    idx = ClassIndex.from_source(ALIAS)
    assert quark.read_aliases(idx) == {"quark:crafter": "minecraft:crafter",
                                       "quark:polished_tuff": "minecraft:polished_tuff",
                                       "quark:egg_parrot_grey": "quark:egg_parrot_gray"}
    # Without the subscription (no other class names the handler), nothing.
    raw = {n: idx.raw(n) for n in idx.names() if not n.endswith("CommonProxy")}
    assert quark.read_aliases(ClassIndex(raw)) == {}
    mod = SourceMod(root=Path("."), namespace="quark", classes=idx)
    got = quark.block_aliases(mod)
    assert set(got) == {"crafter", "polished_tuff", "egg_parrot_grey"}
    from portkit.adapters import block_aliases
    # An alias inside the mod's own namespace isn't another block.
    assert set(block_aliases(mod)) == {"crafter", "polished_tuff"}
    # Another namespace's jar: the adapter reads nothing.
    assert quark.block_aliases(SourceMod(root=Path("."), namespace=NS, classes=idx)) == {}


def test_aliased_blockstate_named_for_its_alias(tmp_path):
    root = tmp_path / "quark"
    _dirs(root, "quark")
    (root / "assets/quark/textures/block/crafter.png").write_bytes(_png())
    cube = {"textures": {"all": "quark:block/crafter", "particle": "quark:block/crafter"},
            "elements": [{"from": [0, 0, 0], "to": [16, 16, 16],
                          "faces": {f: {"texture": "#all", "uv": [0, 0, 16, 16]}
                                    for f in ("north", "south", "east", "west", "up", "down")}}]}
    for stem in ("crafter", "crafter_on", "polished_tuff"):
        (root / f"assets/quark/models/block/{stem}.json").write_text(json.dumps(cube))
    (root / "assets/quark/textures/block/polished_tuff.png").write_bytes(_png())
    (root / "assets/quark/blockstates/crafter.json").write_text(json.dumps({"variants": {
        f"facing={d},power={p}": {"model": "quark:block/crafter" + ("_on" if p == "on" else "")}
        for d in ("north", "south", "east", "west", "up", "down") for p in ("off", "on", "triggered")}}))
    (root / "assets/quark/blockstates/polished_tuff.json").write_text(json.dumps(
        {"variants": {"": {"model": "quark:block/polished_tuff"}}}))
    result = blocks.convert(SourceMod(root=root, namespace="quark", classes=ClassIndex.from_source(ALIAS)))
    why = _reason(result, "crafter")
    assert why.startswith("the mod's code aliases quark:crafter to minecraft:crafter "
                          "(org.violetmoon.quark.base.handler.QuarkRemapHandler#onRemapBlocks")
    assert "no registration of crafter was found in the mod's classes" in why
    # A blockstate another path converts is left as it was.
    assert "blocks/polished_tuff.json" in result.files


def _alias_jar(tmp_path):
    root = tmp_path / "quark"
    _dirs(root, "quark")
    cube = {"textures": {"all": "quark:block/polished_tuff", "particle": "quark:block/polished_tuff"},
            "elements": [{"from": [0, 0, 0], "to": [16, 16, 16],
                          "faces": {f: {"texture": "#all", "uv": [0, 0, 16, 16]}
                                    for f in ("north", "south", "east", "west", "up", "down")}}]}
    (root / "assets/quark/models/block/polished_tuff.json").write_text(json.dumps(cube))
    (root / "assets/quark/models/block/crafter.json").write_text(json.dumps(cube))
    (root / "assets/quark/textures/block/polished_tuff.png").write_bytes(_png())
    (root / "assets/quark/blockstates/polished_tuff.json").write_text(json.dumps(
        {"variants": {"": {"model": "quark:block/polished_tuff"}}}))
    (root / "assets/quark/blockstates/crafter.json").write_text(json.dumps({"variants": {
        f"facing={d}": {"model": "quark:block/crafter"} for d in ("north", "south")}}))
    return root


def _alias_index(table):
    idx = ClassIndex.from_source(ALIAS)
    idx.vanilla_blocks = table
    return idx


def _kind(result, stem: str) -> str:
    return next(u.kind for u in result.unhandled if u.source.endswith(f"blockstates/{stem}.json"))


def test_id_aliased_to_a_vanilla_block_is_residue(tmp_path):
    # Quark 4.1: quark:polished_tuff -> minecraft:polished_tuff, which Mojang's
    # Blocks table registers, and no block of Quark's own under the name.
    root = _alias_jar(tmp_path)
    idx = _alias_index({"POLISHED_TUFF": "polished_tuff", "CRAFTER": "crafter"})
    result = blocks.convert(SourceMod(root=root, namespace="quark", classes=idx))
    assert "blocks/polished_tuff.json" not in result.files
    assert _kind(result, "polished_tuff") == blocks.ALIASED_BLOCKSTATE
    why = _reason(result, "polished_tuff")
    assert why.startswith("the mod's code aliases quark:polished_tuff to minecraft:polished_tuff "
                          "(org.violetmoon.quark.base.handler.QuarkRemapHandler#onRemapBlocks")
    assert "no registration of polished_tuff was found in the mod's classes" in why
    assert why.endswith("minecraft:polished_tuff is a vanilla block (Mojang's Blocks table for the game "
                        "version the mod declares), so the id loads vanilla's block and no block of the mod's own")
    # The crafter, residue before for its states, now says the same up front.
    assert _kind(result, "crafter") == blocks.ALIASED_BLOCKSTATE
    from portkit.agent.residue import SKIP_KINDS
    assert blocks.ALIASED_BLOCKSTATE in SKIP_KINDS


def test_alias_needs_the_vanilla_table_and_a_vanilla_target(tmp_path):
    root = _alias_jar(tmp_path)
    # No table (reference not fetched): nothing is said, polished_tuff converts.
    plain = blocks.convert(SourceMod(root=root, namespace="quark", classes=_alias_index(None)))
    assert "blocks/polished_tuff.json" in plain.files
    assert _kind(plain, "crafter") == "block"
    # A target the table doesn't register is no vanilla block: polished_tuff
    # converts and the crafter keeps its reason from the states path.
    other = blocks.convert(SourceMod(root=root, namespace="quark",
                                     classes=_alias_index({"STONE": "stone"})))
    assert "blocks/polished_tuff.json" in other.files
    assert _kind(other, "crafter") == "block"


def test_alias_with_a_registered_block_converts(tmp_path, monkeypatch):
    # A block the mod's code registers under the name wins over the alias
    # (NeoForge resolves an alias only while no block has the id).
    root = _alias_jar(tmp_path)
    idx = _alias_index({"POLISHED_TUFF": "polished_tuff", "CRAFTER": "crafter"})
    # _aliased_reason hands back the reason it had when the registration run
    # finds a block under the name.
    monkeypatch.setattr(blocks, "_aliased_reason", lambda mod, name, alias, why, shared: why)
    result = blocks.convert(SourceMod(root=root, namespace="quark", classes=idx))
    assert "blocks/polished_tuff.json" in result.files
    assert not any(u.kind == blocks.ALIASED_BLOCKSTATE for u in result.unhandled)
