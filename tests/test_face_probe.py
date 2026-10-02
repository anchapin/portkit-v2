"""The face probe (#64): one slab, two uv keyings, nothing else different."""
from portkit.harness import axis_probe
from portkit import png


def _cube(files, keying):
    geo = files[f"models/blocks/face_{keying}.geo.json"]["minecraft:geometry"][0]
    return geo["bones"][0]["cubes"][0]


def test_the_two_blocks_differ_only_in_the_face_key():
    files = axis_probe.face_pack_files("examplemod")
    a, b = _cube(files, "mirrored"), _cube(files, "aswritten")
    assert list(a["uv"]) == ["east"] and list(b["uv"]) == ["west"]
    assert a["uv"]["east"] == b["uv"]["west"]
    assert {k: v for k, v in a.items() if k != "uv"} == {k: v for k, v in b.items() if k != "uv"}


def test_the_slab_sits_on_the_mirrored_edge():
    cube = _cube(axis_probe.face_pack_files("examplemod"), "aswritten")
    assert cube["origin"] == [6.0, 0.0, -8.0]
    assert cube["size"] == [2.0, 16.0, 16.0]


def test_the_texture_is_opaque_so_the_face_is_one_sided():
    files = axis_probe.face_pack_files("examplemod")
    assert png.has_transparency(files["textures/blocks/probe.png"]) is False
    for keying in axis_probe.FACE_KEYS:
        body = files[f"blocks/face_{keying}.json"]["minecraft:block"]
        assert body["components"]["minecraft:material_instances"]["*"]["render_method"] == "opaque"
