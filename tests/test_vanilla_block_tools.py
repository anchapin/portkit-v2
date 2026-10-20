"""Which vanilla blocks need the correct tool for drops (#280 pick 6a,
portkit.data.vanilla_block_tools).

tests/data/vanillablocktools/classes are javac 21 output (build.sh): stand-ins for
vanilla ``Blocks`` and ``BlockBehaviour.Properties`` in the shapes 1.21.1's client jar
uses (the flag set inline, inside a ``Blocks`` helper, copied from a block read before,
copied from a helper's parameter, set from a value).
"""
from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from portkit.data import ReferenceDataError, vanilla_block_tools, vanilla_blocks

DATA = Path(__file__).parent / "data" / "vanillablocktools" / "classes"


def _client_txt() -> bytes:
    """Mojang's client.txt format, every name mapped to itself (the stand-ins aren't obfuscated)."""
    block = "net.minecraft.world.level.block.Block"
    lines = ["# test mappings"]
    for cls, fields in {
        "net.minecraft.world.level.block.Blocks": [f"{block} {f}" for f in (
            "STONE", "GLASS", "RED_STAINED_GLASS", "IRON_ORE", "STONE_SLAB", "GLASS_PANE", "STONE_STAIRS", "ODD")],
        block: [],
        "net.minecraft.world.level.block.state.BlockBehaviour": [],
        "net.minecraft.world.level.block.state.BlockBehaviour$Properties": [
            "boolean requiresCorrectToolForDrops", "float destroyTime"],
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
SET = vanilla_block_tools.ToolSet("vanilla-block-tools-test", BLOCKS, "0" * 64)


def test_derive_reads_the_flag_from_each_registration():
    table = json.loads(vanilla_block_tools.derive(SET, _jar(), _client_txt()))
    assert table["requires_correct_tool"] == {
        "stone": True,               # Properties.of().requiresCorrectToolForDrops()
        "glass": False,              # never called
        "red_stained_glass": False,  # a Blocks helper that doesn't call it
        "iron_ore": True,            # a Blocks helper that does
        "stone_slab": True,          # ofFullCopy(STONE): copies through ofLegacyCopy
        "glass_pane": False,         # ofLegacyCopy(GLASS)
    }
    # A copy of a helper's parameter and a flag set from a value are unread, not guessed.
    assert table["unread"] == ["odd_block", "stone_stairs"]
    assert table["sources"] == [BLOCKS.jar_url, BLOCKS.mojang_url]
    assert "never vendored" in table["notice"]


def test_derive_is_deterministic():
    assert vanilla_block_tools.derive(SET, _jar(), _client_txt()) == \
        vanilla_block_tools.derive(SET, _jar(), _client_txt())


def test_a_jar_without_the_flag_field_is_refused():
    txt = _client_txt().replace(b"    boolean requiresCorrectToolForDrops -> requiresCorrectToolForDrops\n", b"")
    with pytest.raises(ValueError, match="requiresCorrectToolForDrops"):
        vanilla_block_tools.derive(SET, _jar(), txt)


def test_download_checks_the_pins_and_reuses_a_kept_jar(tmp_path):
    jar, txt = _jar(), _client_txt()
    blocks = vanilla_blocks.BlockIdSet("vanilla-blocks-test", "1.21.1", hashlib.sha1(jar).hexdigest(),
                                       hashlib.sha1(txt).hexdigest(), "")
    unpinned = vanilla_block_tools.ToolSet("vanilla-block-tools-test", blocks, "")
    derived = vanilla_block_tools.derive(unpinned, jar, txt)
    pinned = dataclasses.replace(unpinned, sha256=hashlib.sha256(derived).hexdigest())
    files = {blocks.jar_url: jar, blocks.mojang_url: txt}
    calls = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def opener(request, timeout=None):
        calls.append(request.full_url)
        return Response(files[request.full_url])

    # `portkit reference fetch` keeps the jar the Blocks table was derived from.
    vanilla_blocks.inputs(blocks, opener, keep=True)
    path, downloaded = vanilla_block_tools.fetch(pinned, tmp_path, opener)
    assert downloaded and path.read_bytes() == derived and len(calls) == 2
    assert vanilla_block_tools.fetch(pinned, tmp_path, opener) == (path, False)
    assert vanilla_blocks._last_inputs == {}
    files[blocks.jar_url] = jar + b"x"
    with pytest.raises(ReferenceDataError, match="sha1 mismatch"):
        vanilla_block_tools.download(pinned, opener)
    wrong = dataclasses.replace(pinned, sha256="0" * 64)
    files[blocks.jar_url] = jar
    with pytest.raises(ReferenceDataError, match="re-pin"):
        vanilla_block_tools.fetch(wrong, tmp_path / "other", opener)


def test_one_set_per_vanilla_blocks_set():
    assert [s.blocks for s in vanilla_block_tools.SETS] == list(vanilla_blocks.SETS)
    assert all(len(s.sha256) == 64 for s in vanilla_block_tools.SETS)
    assert vanilla_block_tools.select("1.21.0").minecraft == "1.21"
    assert vanilla_block_tools.select("1.20.4") is None


def test_needs_correct_tool_reads_the_table_or_says_why_not(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTKIT_VANILLA_BLOCK_TOOLS", str(tmp_path))
    s = vanilla_block_tools.select("1.21.1")
    got, why = vanilla_block_tools.needs_correct_tool("1.21.1", "minecraft:glass")
    assert got is None and "isn't cached" in why
    (tmp_path / f"{s.id}.json").write_text(json.dumps({"requires_correct_tool": {"glass": False, "stone": True}}))
    assert vanilla_block_tools.needs_correct_tool("1.21.1", "minecraft:glass") == (False, "")
    assert vanilla_block_tools.needs_correct_tool("1.21.1", "minecraft:stone") == (True, "")
    got, why = vanilla_block_tools.needs_correct_tool("1.21.1", "minecraft:stone_stairs")
    assert got is None and "isn't read" in why
    got, why = vanilla_block_tools.needs_correct_tool("1.20.4", "minecraft:glass")
    assert got is None and "1.20.4" in why
    got, why = vanilla_block_tools.needs_correct_tool(None, "minecraft:glass")
    assert got is None and "no Minecraft version" in why
