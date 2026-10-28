"""A model without a loader that extends a composite model draws the
composite (#296): Forge 1.20.1 / NeoForge 1.21.1
``BlockGeometryBakingContext#getCustomGeometry`` falls back to the parent's
geometry, ``#isComponentVisible`` takes the nearest model naming a part, and
each composite child is baked as a model of its own, so the extending
model's textures reach only ``particle``. The models here are written for
the test (not taken from any jar)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from portkit.converters import models
from portkit.model import SourceMod

NS = "examplemod"
_CUBE = {"from": [4, 0, 4], "to": [12, 8, 12],
         "faces": {f: {"texture": "#0", "uv": [0, 0, 8, 8]} for f in ("north", "south", "east", "west", "up", "down")}}
_TOP = {"from": [4, 8, 4], "to": [12, 12, 12],
        "faces": {f: {"texture": "#0", "uv": [0, 0, 8, 4]} for f in ("north", "south", "east", "west", "up")}}


@pytest.fixture()
def mod(tmp_path) -> SourceMod:
    base = tmp_path / "assets" / NS / "models" / "block"
    (base / "lamp").mkdir(parents=True)
    composite = {"loader": "forge:composite", "parent": "block/block",
                 "textures": {"particle": f"{NS}:block/lamp"},
                 "children": {"base": {"textures": {"0": f"{NS}:block/lamp"}, "elements": [_CUBE]},
                              "cap": {"textures": {"0": f"{NS}:block/lamp"}, "elements": [_TOP]}}}
    (base / "lamp" / "block.json").write_text(json.dumps(composite))
    return SourceMod(root=tmp_path, namespace=NS)


def _resolve(mod, leaf):
    return models.resolve(mod, leaf)


def test_extending_model_draws_the_composite(mod):
    out, _, why = _resolve(mod, {"parent": f"{NS}:block/lamp/block"})
    assert why == ""
    assert len(out["elements"]) == 2


def test_extending_model_visibility_hides_a_child(mod):
    out, _, why = _resolve(mod, {"parent": f"{NS}:block/lamp/block", "visibility": {"cap": False}})
    assert why == ""
    assert len(out["elements"]) == 1 and out["elements"][0]["to"] == [12, 8, 12]


def test_extending_model_textures_reach_only_particle(mod):
    out, _, why = _resolve(mod, {"parent": f"{NS}:block/lamp/block",
                                 "textures": {"0": f"{NS}:block/other", "particle": f"{NS}:block/dot"}})
    assert why == ""
    assert out["textures"]["particle"] == f"{NS}:block/dot"
    assert f"{NS}:block/other" not in out["textures"].values()


@pytest.mark.parametrize("extra", [{"elements": [_CUBE]}, {"render_type": "minecraft:cutout"}])
def test_extending_model_that_sets_more_is_refused(mod, extra):
    out, _, why = _resolve(mod, {"parent": f"{NS}:block/lamp/block", **extra})
    assert out == {}
    assert "extends a composite model" in why
