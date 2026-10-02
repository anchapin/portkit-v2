"""The uv_rotation probe pack (#68)."""
from portkit.harness import axis_probe


def _uv(files, key):
    geo = files[f"models/blocks/turn_{key}.geo.json"]
    assert geo["format_version"] == "1.21.0"
    return geo["minecraft:geometry"][0]["bones"][0]["cubes"][0]["uv"]


def test_three_blocks_differ_only_in_uv_rotation():
    files = axis_probe.turn_pack_files("probe")
    assert "uv_rotation" not in _uv(files, "control")["up"]
    assert _uv(files, "cw90")["up"]["uv_rotation"] == 90
    assert _uv(files, "cw270")["down"]["uv_rotation"] == 270


def test_the_arrow_texture_is_a_real_png():
    png = axis_probe._arrow_png()
    assert png.startswith(b"\x89PNG") and len(png) > 60
