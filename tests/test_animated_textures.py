"""A .mcmeta sidecar becomes a flipbook entry, or becomes residue. Never a static smear."""
import json
import struct
import zlib

import pytest

from portkit.converters import textures
from portkit.model import SourceMod
from portkit.pipeline import convert


def png_bytes(width: int, height: int) -> bytes:
    """A real, minimal RGBA png. The converter copies bytes, so no image library needed."""
    raw = b"".join(b"\x00" + b"\xc8\x5a\x14\xff" * width for _ in range(height))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def build(tmp_path, meta, name="bonfire", frames=2):
    block = tmp_path / "assets" / "examplemod" / "textures" / "block"
    block.mkdir(parents=True, exist_ok=True)
    (block / f"{name}.png").write_bytes(png_bytes(16, 16 * frames))
    if meta is not None:
        (block / f"{name}.png.mcmeta").write_text(json.dumps(meta))
    return SourceMod(root=tmp_path, namespace="examplemod")


def test_sidecar_becomes_a_flipbook_entry(tmp_path):
    mod = build(tmp_path, {"animation": {"frametime": 3, "interpolate": True}})
    result = textures.convert(mod)
    entries = result.files["textures/flipbook_textures.json"]
    assert entries == [
        {
            "flipbook_texture": "textures/blocks/bonfire",
            "atlas_tile": "examplemod:bonfire",
            "ticks_per_frame": 3,
            "blend_frames": True,
        }
    ]
    assert "textures/blocks/bonfire.png" in result.files
    assert result.unhandled == []


def test_frame_order_is_carried_through(tmp_path):
    mod = build(tmp_path, {"animation": {"frametime": 1, "frames": [0, 1, 2, 1]}})
    entry = textures.convert(mod).files["textures/flipbook_textures.json"][0]
    assert entry["frames"] == [0, 1, 2, 1]
    assert entry["ticks_per_frame"] == 1


def test_default_frametime_is_one_tick(tmp_path):
    mod = build(tmp_path, {"animation": {}})
    entry = textures.convert(mod).files["textures/flipbook_textures.json"][0]
    assert entry["ticks_per_frame"] == 1
    assert entry["blend_frames"] is False


@pytest.mark.parametrize(
    "animation, expected",
    [
        ({"frames": [{"index": 0, "time": 5}, 1]}, "per-frame timings"),
        ({"width": 8, "height": 8}, "custom frame size"),
        ({"frametime": 0}, "positive tick count"),
    ],
)
def test_unmappable_animation_drops_the_texture_too(tmp_path, animation, expected):
    mod = build(tmp_path, {"animation": animation})
    result = textures.convert(mod)
    assert [u.kind for u in result.unhandled] == ["texture_animation"]
    assert expected in result.unhandled[0].reason
    # the whole point: no static texture, no index entry, nothing that looks converted
    assert result.files == {}


def test_sidecar_without_an_animation_block_is_residue(tmp_path):
    mod = build(tmp_path, {"villager": {"type": "toolsmith"}})
    result = textures.convert(mod)
    assert [u.kind for u in result.unhandled] == ["texture_animation"]
    assert result.files == {}


def test_plain_textures_are_untouched(tmp_path):
    mod = build(tmp_path, None)
    result = textures.convert(mod)
    assert "textures/flipbook_textures.json" not in result.files
    assert "textures/blocks/bonfire.png" in result.files


def test_sidecars_are_claimed_so_they_are_not_reported_unowned(tmp_path):
    mod = build(tmp_path, {"animation": {"frametime": 2}})
    result = textures.convert(mod)
    assert "assets/examplemod/textures/block/bonfire.png.mcmeta" in result.consumed


def test_animated_fixture_converts_and_validates(tmp_path, fixtures_dir):
    result = convert(fixtures_dir / "animated_block_mod" / "input", tmp_path / "out")
    assert result.report.ok, result.report.to_dict()
    assert result.unhandled == []
    entries = json.loads(
        (result.tree / "resource_pack" / "textures" / "flipbook_textures.json").read_text()
    )
    assert [e["atlas_tile"] for e in entries] == ["examplemod:bonfire"]


def test_validator_catches_a_flipbook_pointing_at_nothing(tmp_path, fixtures_dir):
    from portkit.validate import validate_tree

    result = convert(fixtures_dir / "animated_block_mod" / "input", tmp_path / "out")
    flipbook = result.tree / "resource_pack" / "textures" / "flipbook_textures.json"
    flipbook.write_text(json.dumps([
        {
            "flipbook_texture": "textures/blocks/ghost",
            "atlas_tile": "examplemod:ghost",
            "ticks_per_frame": 2,
        }
    ]))
    report = validate_tree(result.tree)
    rules = {f.rule for f in report.errors}
    assert "flipbook.missing" in rules
    assert "flipbook.atlas_tile" in rules
