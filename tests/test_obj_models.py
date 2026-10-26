"""NeoForge/Forge OBJ block models (#296): a mesh that is boxes is read as
Java elements; anything else stays residue with the reason.

tests/data/obj is hand-written (not taken from any jar): ``post.obj`` is two
boxes (``base`` by a material naming its texture location, ``cap`` through
the model's ``#cap``), ``inward.obj`` the same base wound inwards,
``mesh.obj`` a ramp of triangles and a slanted quad, ``glow.obj`` one face
lit by its material's ``Ka``.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from portkit.converters import blocks, models, objmodel
from portkit.model import SourceMod

DATA = Path(__file__).parent / "data" / "obj"
NS = "examplemod"


@pytest.fixture()
def mod(tmp_path) -> SourceMod:
    shutil.copytree(DATA, tmp_path / "mod")
    return SourceMod(root=tmp_path / "mod", namespace=NS)


def _model(mod: SourceMod, name: str) -> dict:
    return json.loads((mod.assets / "models" / "block" / f"{name}.json").read_text())


def _reason(result, name: str) -> str | None:
    return next((u.reason for u in result.unhandled if u.source.endswith(f"blockstates/{name}.json")), None)


def test_boxes_read_as_elements(mod):
    out, files, why = objmodel.read(mod, _model(mod, "post"))
    assert why == "" and out is not None
    assert sorted(p.name for p in files) == ["post.mtl", "post.obj"]
    assert "loader" not in out and "model" not in out
    base, cap = out["elements"]
    assert (base["from"], base["to"]) == ([4, 0, 4], [12, 8, 12])
    assert (cap["from"], cap["to"]) == ([6, 8, 6], [10, 10, 10])
    # The uv each face was written with comes back, mirrored ones included.
    assert base["faces"]["north"]["uv"] == [0, 8, 8, 12]
    assert base["faces"]["east"]["uv"] == [16, 12, 8, 16]
    assert set(cap["faces"]) == {"up", "north"}
    # A location in map_Kd gets its own slot; #cap is the model's.
    assert base["faces"]["up"]["texture"] == "#obj_post"
    assert cap["faces"]["up"]["texture"] == "#cap"
    assert out["textures"]["obj_post"] == f"{NS}:block/post"
    # automatic_culling: only the face on the block's boundary, facing out.
    assert base["faces"]["down"]["cullface"] == "down"
    assert "cullface" not in base["faces"]["up"]


def test_every_face_baked_as_java_does(mod):
    out, _, _ = objmodel.read(mod, _model(mod, "post"))
    pos, tex = [], []
    for line in (mod.assets / "models/block/post.obj").read_text().splitlines():
        if line.startswith("v "):
            pos.append(tuple(float(c) * 16 for c in line.split()[1:]))
        elif line.startswith("vt "):
            u, v = (float(c) for c in line.split()[1:])
            tex.append((u * 16, (1 - v) * 16))
    written = [[(pos[int(t.split("/")[0]) - 1], tex[int(t.split("/")[1]) - 1]) for t in line.split()[1:]]
               for line in (mod.assets / "models/block/post.obj").read_text().splitlines() if line.startswith("f ")]
    baked = [models.baked_quad(face, e["from"], e["to"], spec["uv"], spec.get("rotation", 0))
             for e in out["elements"] for face, spec in e["faces"].items()]
    assert len(baked) == len(written) == 8
    for quad in written:
        assert any(models._same_quad(quad, b) for b in baked)


def test_settings_and_parents(mod):
    out, _, why = objmodel.read(mod, _model(mod, "post_base"))
    assert why == ""
    (base,) = out["elements"]  # visibility hides the cap
    assert base["shade"] is False
    assert all("cullface" not in f for f in base["faces"].values())
    # A child of an OBJ model: the parent's mesh with the child's textures.
    flat, read, why = models.resolve(mod, _model(mod, "post_child"))
    assert why == "" and len(flat["elements"]) == 2
    assert flat["textures"]["cap"] == f"{NS}:block/cap_red"
    assert {p.name for p in read} >= {"post.json", "post.obj", "post.mtl"}


@pytest.mark.parametrize("name, words", [
    ("ramp", "a face has 3 corners"),
    ("inward", "wound or lit inwards"),
    ("glow", "Ka bakes light"),
    ("legacy", "sets flip-v, which the OBJ reader doesn't read"),
])
def test_not_boxes_named(mod, name, words):
    out, files, why = objmodel.read(mod, _model(mod, name))
    assert out is None and words in why


def test_blocks_convert(mod):
    result = blocks.convert(mod)
    for name in ("post", "post_child", "post_base"):
        assert f"blocks/{name}.json" in result.files, name
        assert _reason(result, name) is None
    assert f"assets/{NS}/models/block/post.obj" in result.consumed
    geo = result.files["models/blocks/post.geo.json"]
    assert len(geo["minecraft:geometry"][0]["bones"][0]["cubes"]) == 2
    assert "poly_mesh" not in json.dumps(geo)
    for name, words in (("ramp", "not an axis-aligned box"), ("inward", "wound or lit inwards"),
                        ("glow", "emissive_ambient")):
        why = _reason(result, name)
        assert why is not None and "Java model loader" in why and words in why, name
        assert f"blocks/{name}.json" not in result.files
    assert "GEOFMT101" in _reason(result, "ramp")
    # A mesh that isn't drawn claims nothing.
    assert f"assets/{NS}/models/block/mesh.obj" not in result.consumed
