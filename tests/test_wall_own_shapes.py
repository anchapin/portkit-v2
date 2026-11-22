"""Walls whose part models draw the vanilla wall shape themselves (#286).

Botania's wall models (``block/shapes/wall_post`` and the side shapes beside
it) do not extend vanilla's wall templates; they carry the same boxes
directly. Java draws the model's own boxes either way, so a part whose boxes
are exactly the vanilla wall shape's converts like one extending the
template; a part drawn any other way is still refused. These tests run
offline against tests/data/model_templates.json, like test_shape_blocks.
"""
import json
from pathlib import Path

import pytest

from portkit.converters import blocks
from portkit.model import SourceMod

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "tests" / "data" / "model_templates.json"
PNG = ROOT / "fixtures" / "agent_mod" / "input" / "assets" / "examplemod" / "textures" / "block" / "alloy_block.png"


@pytest.fixture
def templates(monkeypatch):
    monkeypatch.setenv("PORTKIT_MODEL_REFERENCE", str(TEMPLATES))
    return TEMPLATES


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(body, bytes):
        path.write_bytes(body)
    else:
        path.write_text(json.dumps(body) if not isinstance(body, str) else body)


def _template_elements(name: str) -> list:
    models = json.loads(TEMPLATES.read_text())["models"]
    return models[f"minecraft:block/{name}"]["elements"]


def _own_shape_wall_mod(tmp_path, *, perturb_post: bool = False):
    root = tmp_path / "src"
    _write(root, "assets/examplemod/textures/block/stone.png", PNG.read_bytes())
    _write(root, "assets/examplemod/models/block/stone.json",
           {"parent": "minecraft:block/cube_all", "textures": {"all": "examplemod:block/stone"}})
    parts = [{"apply": {"model": "examplemod:block/stone_wall_post"}, "when": {"up": "true"}}]
    for d, y in (("north", 0), ("east", 90), ("south", 180), ("west", 270)):
        for height, model in (("low", "stone_wall_side"), ("tall", "stone_wall_side_tall")):
            apply = {"model": f"examplemod:block/{model}", "uvlock": True}
            if y:
                apply["y"] = y
            parts.append({"apply": apply, "when": {d: height}})
    _write(root, "assets/examplemod/blockstates/stone_wall.json", {"multipart": parts})
    for model, template in (("stone_wall_post", "template_wall_post"),
                            ("stone_wall_side", "template_wall_side"),
                            ("stone_wall_side_tall", "template_wall_side_tall")):
        elements = json.loads(json.dumps(_template_elements(template)))
        if perturb_post and model == "stone_wall_post":
            elements[0]["to"][1] = 15  # one box shorter than vanilla's post
        _write(root, f"assets/examplemod/models/block/{model}.json",
               {"textures": {"wall": "examplemod:block/stone"}, "elements": elements})
    return root


def test_a_wall_drawn_with_vanillas_own_boxes_converts(tmp_path, templates):
    result = blocks.convert(SourceMod(root=_own_shape_wall_mod(tmp_path), namespace="examplemod"))
    assert "blocks/stone_wall.json" in result.files
    assert not [u for u in result.unhandled if u.kind == "block"]
    assert any("draw the vanilla wall shape themselves" in note for note in result.notes)


def test_a_wall_drawn_any_other_way_is_still_refused(tmp_path, templates):
    result = blocks.convert(SourceMod(root=_own_shape_wall_mod(tmp_path, perturb_post=True),
                                      namespace="examplemod"))
    assert "blocks/stone_wall.json" not in result.files
    reasons = [u.reason for u in result.unhandled if u.kind == "block"]
    assert any("not the vanilla template_wall_post template" in r for r in reasons)
