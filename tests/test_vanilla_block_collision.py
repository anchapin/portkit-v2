"""Whether each vanilla block's Properties collide (#296,
portkit.data.vanilla_block_collision).

tests/data/vanillablockcollision/classes are javac 21 output (build.sh): stand-ins
for vanilla ``Blocks`` and ``BlockBehaviour.Properties`` in the shapes the client
jar uses for ``hasCollision`` (left set, cleared by noCollission inline or inside a
``Blocks`` helper, copied from a block read before, copied then cleared, copied from
a helper's parameter, set from a value, cleared on a branch).
"""
from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from portkit.bytecode import ClassIndex
from portkit.data import ReferenceDataError, vanilla_block_collision, vanilla_blocks

DATA = Path(__file__).parent / "data" / "vanillablockcollision" / "classes"
FIELDS = ("STONE", "WHEAT", "TALL_GRASS", "STONE_SLAB", "WHEAT_COPY", "STONE_GHOST", "STONE_STAIRS", "ODD", "MAYBE")


def _client_txt() -> bytes:
    """Mojang's client.txt format, every name mapped to itself (the stand-ins aren't obfuscated)."""
    block = "net.minecraft.world.level.block.Block"
    lines = ["# test mappings"]
    for cls, fields in {
        "net.minecraft.world.level.block.Blocks": [f"{block} {f}" for f in FIELDS],
        block: [],
        "net.minecraft.world.level.block.state.BlockBehaviour": [],
        "net.minecraft.world.level.block.state.BlockBehaviour$Properties": [
            "boolean hasCollision", "boolean canOcclude", "float destroyTime"],
        "net.minecraft.resources.ResourceKey": [],
    }.items():
        lines.append(f"{cls} -> {cls}:")
        lines += [f"    {f} -> {f.split(' ')[1]}" for f in fields]
    return ("\n".join(lines) + "\n").encode()


def _jar() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for p in sorted(DATA.rglob("*.class")):
            zf.writestr(p.relative_to(DATA).as_posix(), p.read_bytes())
    return buf.getvalue()


BLOCKS = vanilla_blocks.BlockIdSet("vanilla-blocks-test", "1.21.1", "0" * 40, "0" * 40, "0" * 64)
SET = vanilla_block_collision.CollisionSet("vanilla-block-collision-test", BLOCKS, "0" * 64)


def test_derive_reads_the_flag_from_each_registration():
    table = json.loads(vanilla_block_collision.derive(SET, _jar(), _client_txt()))
    assert table["has_collision"] == {
        "stone": True,         # Properties.of(): the constructor sets it
        "wheat": False,        # noCollission() inline
        "tall_grass": False,   # inside a Blocks helper
        "stone_slab": True,    # ofFullCopy(STONE): copies through ofLegacyCopy
        "wheat_copy": False,   # ofLegacyCopy(WHEAT)
        "stone_ghost": False,  # a copy, then noCollission()
    }
    # A copy of a helper's parameter, a flag set from a value and one cleared
    # on a branch are unread, not guessed.
    assert table["unread"] == ["maybe_block", "odd_block", "stone_stairs"]
    assert table["sources"] == [BLOCKS.jar_url, BLOCKS.mojang_url]
    assert "never vendored" in table["notice"]


def test_derive_is_deterministic():
    assert vanilla_block_collision.derive(SET, _jar(), _client_txt()) == \
        vanilla_block_collision.derive(SET, _jar(), _client_txt())


def test_a_jar_without_the_flag_field_is_refused():
    txt = _client_txt().replace(b"    boolean hasCollision -> hasCollision\n", b"")
    with pytest.raises(ValueError, match="hasCollision"):
        vanilla_block_collision.derive(SET, _jar(), txt)


def test_download_checks_the_pins(tmp_path):
    jar, txt = _jar(), _client_txt()
    blocks = vanilla_blocks.BlockIdSet("vanilla-blocks-test", "1.21.1", hashlib.sha1(jar).hexdigest(),
                                       hashlib.sha1(txt).hexdigest(), "")
    unpinned = vanilla_block_collision.CollisionSet("vanilla-block-collision-test", blocks, "")
    derived = vanilla_block_collision.derive(unpinned, jar, txt)
    pinned = dataclasses.replace(unpinned, sha256=hashlib.sha256(derived).hexdigest())
    files = {blocks.jar_url: jar, blocks.mojang_url: txt}

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def opener(request, timeout=None):
        return Response(files[request.full_url])

    path, downloaded = vanilla_block_collision.fetch(pinned, tmp_path, opener)
    assert downloaded and path.read_bytes() == derived
    assert vanilla_block_collision.fetch(pinned, tmp_path, opener) == (path, False)
    assert vanilla_block_collision.cached(pinned, tmp_path) == path
    vanilla_blocks._last_inputs.clear()
    files[blocks.jar_url] = jar + b"x"
    with pytest.raises(ReferenceDataError, match="sha1 mismatch"):
        vanilla_block_collision.download(pinned, opener)
    vanilla_blocks._last_inputs.clear()
    wrong = dataclasses.replace(pinned, sha256="0" * 64)
    files[blocks.jar_url] = jar
    with pytest.raises(ReferenceDataError, match="re-pin"):
        vanilla_block_collision.fetch(wrong, tmp_path / "other", opener)
    vanilla_blocks._last_inputs.clear()


def test_one_set_per_vanilla_blocks_set():
    assert [s.blocks for s in vanilla_block_collision.SETS] == list(vanilla_blocks.SETS)
    assert all(len(s.sha256) == 64 for s in vanilla_block_collision.SETS)
    assert vanilla_block_collision.select("1.21.0").minecraft == "1.21"
    assert vanilla_block_collision.select("1.20.4") is None


def test_attach_reads_the_cached_table_or_leaves_none(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTKIT_VANILLA_BLOCK_COLLISION", str(tmp_path))
    s = vanilla_block_collision.select("1.21.1")
    classes = ClassIndex({})
    vanilla_block_collision.attach(classes, "1.21.1")
    assert classes.vanilla_collision is None  # not cached
    (tmp_path / f"{s.id}.json").write_text(json.dumps({"has_collision": {"wheat": False, "stone": True, "x": 1}}))
    vanilla_block_collision.attach(classes, "1.21.1")
    assert classes.vanilla_collision == {"wheat": False, "stone": True}  # a non-bool value is dropped
    other = ClassIndex({})
    vanilla_block_collision.attach(other, "1.20.4")  # no pinned set
    assert other.vanilla_collision is None
