"""Immersive Engineering's own OBJ loader, ``immersiveengineering:ie_obj`` (#296).

tests/data/ieobj is written for these tests (not from any jar):
``tube.obj.ie`` is two boxes written from two Java elements the way Java
bakes them, with ``v`` flipped as IE reads it (``PolygonUtils#toBakedQuad``:
``getV(1 - v)``); the ``frame`` box gives its normals, the ``post`` box
doesn't (IE recomputes them), and a ``g`` line BlockModelSplitter ignores
sits inside ``post``. ``tube.mtl`` sets ``Kd``/``Ka``, which
BlockModelSplitter doesn't read. ``ramp.obj.ie`` is one triangle.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from portkit import adapters, blockcode
from portkit.adapters.immersiveengineering import ieobj
from portkit.converters import blocks, models, objmodel
from portkit.model import SourceMod

DATA = Path(__file__).parent / "data" / "ieobj"
NS = "immersiveengineering"


@pytest.fixture()
def mod(tmp_path) -> SourceMod:
    shutil.copytree(DATA, tmp_path / "mod")
    return SourceMod(root=tmp_path / "mod", namespace=NS)


def _model(mod: SourceMod, name: str) -> dict:
    return json.loads((mod.assets / "models" / "block" / f"{name}.json").read_text())


def _reason(result, name: str) -> str | None:
    return next((u.reason for u in result.unhandled if u.source.endswith(f"blockstates/{name}.json")), None)


def test_loader_is_claimed_by_the_adapter():
    assert adapters.model_loader(ieobj.LOADER) is ieobj.read
    assert objmodel.reader({"loader": ieobj.LOADER}) is ieobj.read
    assert objmodel.reader({"loader": "neoforge:obj"}) is objmodel.read
    assert objmodel.reader({"loader": "examplemod:other"}) is None
    assert adapters.check() == []


def test_boxes_read_as_ie_reads_them(mod):
    out, files, why = ieobj.read(mod, _model(mod, "tube"))
    assert why == "" and out is not None
    assert sorted(p.name for p in files) == ["tube.mtl", "tube.obj.ie"]
    assert not {"loader", "model", "callbacks"} & set(out)
    frame, post = out["elements"]  # the g line doesn't start a group
    assert (frame["from"], frame["to"]) == ([0, 0, 0], [16, 4, 16])
    assert (post["from"], post["to"]) == ([6, 4, 6], [10, 12, 10])
    # IE's quads answer only for no side: nothing is culled.
    assert all("cullface" not in f for e in out["elements"] for f in e["faces"].values())
    # Kd/Ka aren't read: no tint, no light, shaded.
    assert all("tintindex" not in f for e in out["elements"] for f in e["faces"].values())
    assert "shade" not in frame
    assert frame["faces"]["up"]["texture"] == "#texture"
    # Every face comes back as Java bakes it (v flipped as IE reads it).
    pos, tex, written = [], [], []
    for line in (mod.assets / "models/block/tube.obj.ie").read_text().splitlines():
        if line.startswith("v "):
            pos.append(tuple(float(c) * 16 for c in line.split()[1:]))
        elif line.startswith("vt "):
            u, v = (float(c) for c in line.split()[1:])
            tex.append((u * 16, (1 - v) * 16))
        elif line.startswith("f "):
            written.append([(pos[int(t.split("/")[0]) - 1], tex[int(t.split("/")[1]) - 1])
                            for t in line.split()[1:]])
    baked = [models.baked_quad(face, e["from"], e["to"], spec["uv"], spec.get("rotation", 0))
             for e in out["elements"] for face, spec in e["faces"].items()]
    assert len(baked) == len(written) == 12
    for quad in written:
        assert any(models._same_quad(quad, b) for b in baked)


@pytest.mark.parametrize("name, words", [
    ("tube_cb", "its callback 'immersiveengineering:tube' isn't found registered"),
    ("tube_layers", "render layers ['cutout'], which aren't read"),
    ("tube_extra", "sets flip_v, which the IE OBJ reader doesn't read"),
    ("ramp", "part 'ramp' piece 1 of 1 is not an axis-aligned box: a face has 3 corners"),
])
def test_refusals_named(mod, name, words):
    out, _files, why = ieobj.read(mod, _model(mod, name))
    assert out is None and words in why, why


def test_callback_reason_adds_the_mesh(mod, monkeypatch):
    # A callback that overrides a drawing method is named, and a non-box part
    # of the mesh is named beside it.
    monkeypatch.setattr(ieobj, "_registered", lambda classes: {"immersiveengineering:ramp": "x/RampCallbacks"})
    monkeypatch.setattr(ieobj, "_overrides", lambda classes, cls: ["getIEOBJState", "getRenderColor"])
    mod.classes = object()
    model = {**_model(mod, "ramp"), "callbacks": "immersiveengineering:ramp"}
    out, _files, why = ieobj.read(mod, model)
    assert out is None
    assert "its callback immersiveengineering:ramp (RampCallbacks) overrides getIEOBJState, getRenderColor" in why
    assert "; and its part 'ramp' piece 1 of 1 is not an axis-aligned box" in why


def test_a_callback_that_only_picks_groups_draws_what_the_placed_key_shows(mod, monkeypatch):
    # Pick 1a: a callback whose only drawing method is getIEOBJState draws the
    # groups its key from the block entity placed alone shows.
    monkeypatch.setattr(ieobj, "_registered", lambda classes: {"immersiveengineering:tube": "x/TubeCallbacks"})
    monkeypatch.setattr(ieobj, "_overrides", lambda classes, cls: ["getIEOBJState"])
    asked = []

    def placed(mod_, classes, cb, names):
        asked.append((cb, names))
        return {"frame": True, "post": False}, ""

    monkeypatch.setattr(ieobj, "_placed_alone", placed)
    mod.classes = object()
    out, _files, why = ieobj.read(mod, _model(mod, "tube_cb"))
    assert why == "" and out is not None
    assert asked == [("x/TubeCallbacks", ["frame", "post"])]
    assert [(e["from"], e["to"]) for e in out["elements"]] == [([0, 0, 0], [16, 4, 16])]
    # Unread, the callback is named with why.
    monkeypatch.setattr(ieobj, "_placed_alone", lambda *a: (None, "no placed block is being drawn"))
    out, _files, why = ieobj.read(mod, _model(mod, "tube_cb"))
    assert out is None and "overrides getIEOBJState" in why and "(no placed block is being drawn)" in why


def test_the_placed_key_needs_a_block_being_drawn(mod):
    assert models.BLOCK_DRAWN.get() is None
    assert ieobj._placed_alone(mod, object(), "x/Cb", ["a"]) == (None, "no placed block is being drawn")
    token = models.BLOCK_DRAWN.set(("tube_cb", lambda: None))
    try:
        got, why = ieobj._placed_alone(mod, object(), "x/Cb", ["a"])
    finally:
        models.BLOCK_DRAWN.reset(token)
    assert got is None and "the block tube_cb isn't found registered" in why


def test_overrides_read_from_the_class_chain():
    m = lambda name, code=b"\0": SimpleNamespace(name=name, code=code)
    classes = {
        "a/Cb": SimpleNamespace(methods=[m("extractKey"), m("getDefaultKey"), m("shadeQuads")], super_name="a/Base"),
        "a/Base": SimpleNamespace(methods=[m("getIEOBJState"), m("modifyQuads", None)],
                                  super_name="java/lang/Object"),
    }
    got = ieobj._overrides(SimpleNamespace(get=classes.get), "a/Cb")
    assert got == ["getIEOBJState", "shadeQuads"]  # an abstract method has no code


def test_blocks_convert(mod):
    result = blocks.convert(mod)
    assert "blocks/tube.json" in result.files and _reason(result, "tube") is None
    geo = result.files["models/blocks/tube.geo.json"]
    assert len(geo["minecraft:geometry"][0]["bones"][0]["cubes"]) == 2
    assert f"assets/{NS}/models/block/tube.obj.ie" in result.consumed
    for name, words in (("tube_cb", "isn't found registered"), ("ramp", "GEOFMT101")):
        why = _reason(result, name)
        assert why is not None and "Java model loader" in why and words in why, name
        assert f"blocks/{name}.json" not in result.files
    assert f"assets/{NS}/models/block/ramp.obj.ie" not in result.consumed


def test_guava_copy_of_keeps_known_elements():
    machine = blockcode.Machine(SimpleNamespace())
    lst = blockcode.ListV(["a", "b", "a"])
    got = machine._collections("com/google/common/collect/ImmutableSet", "copyOf",
                               "(Ljava/util/Collection;)Lcom/google/common/collect/ImmutableSet;",
                               None, [lst], True)
    assert got == [blockcode.Coll(("a", "b"))]
    got = machine._collections("com/google/common/collect/ImmutableList", "copyOf",
                               "(Ljava/util/Collection;)Lcom/google/common/collect/ImmutableList;",
                               None, [lst], True)
    assert got == [blockcode.Coll(("a", "b", "a"))]
    lst.havoc = True
    assert machine._collections("com/google/common/collect/ImmutableSet", "copyOf",
                                "(Ljava/util/Collection;)Lcom/google/common/collect/ImmutableSet;",
                                None, [lst], True) == [blockcode.UNKNOWN]
