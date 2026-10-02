"""The side-face uv_rotation probe pack (#71)."""
from portkit.harness import axis_probe


def _cube(files, key):
    geo = files[f"models/blocks/side_turn_{key}.geo.json"]
    assert geo["format_version"] == "1.21.0"
    return geo["minecraft:geometry"][0]["bones"][0]["cubes"][0]


def test_only_side_faces_turn():
    files = axis_probe.side_turn_pack_files("probe")
    control, a, b = (_cube(files, k)["uv"] for k in ("control", "cw90", "cw270"))
    assert all("uv_rotation" not in control[f] for f in control)
    for face in axis_probe.SIDE_FACES:
        assert a[face]["uv_rotation"] == 90
        assert b[face]["uv_rotation"] == 270
    assert "uv_rotation" not in a["up"] and "uv_rotation" not in b["down"]


def test_each_side_wears_its_own_colour():
    files = axis_probe.side_turn_pack_files("probe")
    block = files["blocks/side_turn_cw90.json"]["minecraft:block"]
    instances = block["components"]["minecraft:material_instances"]
    textures = {instances[f]["texture"] for f in axis_probe.SIDE_FACES}
    assert len(textures) == 4
    data = files["textures/terrain_texture.json"]["texture_data"]
    assert all(t in data for t in textures)
    for colour, _ in axis_probe.SIDE_GROUNDS.values():
        assert files[f"textures/blocks/arrow_{colour}.png"].startswith(b"\x89PNG")
