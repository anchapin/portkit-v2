"""One render method per block (#262).

Bedrock: a block's material instances must all use the same render_method
(Mojang bedrock-samples documentation/Blocks.html, minecraft:material_instances:
"must be the same for each"); BDS 1.26.52.3 logs "MaterialInstances can't mix
and match opaque and transparent materials" as an error. The method comes
from the Java model's render_type when it names one, else from the textures'
alpha, never invented.
"""
import json
import struct
import zlib

import pytest

from portkit.converters import blocks, models
from portkit.model import SourceMod
from portkit.validate.report import ValidationReport
from portkit.validate.rules import _check_render_methods

NS = "examplemod"


def _png(alpha: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    raw = b"".join(b"\x00" + bytes((0x80, 0x60, 0x40, alpha)) * 16 for _ in range(16))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _model(render_type=None, parent="minecraft:block/block", lattice="lattice"):
    face = {"uv": [0, 0, 16, 16], "texture": "#plank"}
    model = {
        "parent": parent,
        "textures": {"plank": f"{NS}:block/plank", "lattice": f"{NS}:block/{lattice}"},
        "elements": [{
            "from": [0, 0, 0], "to": [16, 8, 16],
            "faces": {**{d: dict(face) for d in ("down", "east", "south", "west", "up")},
                      "north": {"uv": [0, 0, 16, 8], "texture": "#lattice"}},
        }],
    }
    if render_type is not None:
        model["render_type"] = render_type
    return model


def _build(tmp_path, model, base=None):
    assets = tmp_path / "assets" / NS
    for sub in ("blockstates", "models/block", "textures/block"):
        (assets / sub).mkdir(parents=True, exist_ok=True)
    (assets / "blockstates" / "rack.json").write_text(
        json.dumps({"variants": {"": {"model": f"{NS}:block/rack"}}}))
    (assets / "models/block/rack.json").write_text(json.dumps(model))
    if base is not None:
        (assets / "models/block/rack_base.json").write_text(json.dumps(base))
    (assets / "textures/block/plank.png").write_bytes(_png(0xFF))
    (assets / "textures/block/lattice.png").write_bytes(_png(0x00))
    return SourceMod(root=tmp_path, namespace=NS)


def _methods(result):
    instances = result.files["blocks/rack.json"]["minecraft:block"]["components"]["minecraft:material_instances"]
    return {face: spec.get("render_method", "opaque") for face, spec in instances.items()}


def test_a_holey_face_beside_opaque_ones_makes_every_face_alpha_test(tmp_path):
    # No render_type: the lattice texture's holes are the evidence, and
    # alpha_test draws the opaque plank faces the same.
    result = blocks.convert(_build(tmp_path, _model()))
    assert result.unhandled == []
    assert set(_methods(result).values()) == {"alpha_test"}
    assert any("every face draws alpha_test (from the texture alpha)" in n for n in result.notes)


def test_the_java_render_type_picks_the_method(tmp_path):
    result = blocks.convert(_build(tmp_path, _model("minecraft:translucent")))
    assert set(_methods(result).values()) == {"blend"}
    assert any("Java render_type minecraft:translucent" in n for n in result.notes)


def test_an_unprefixed_render_type_inherited_from_a_parent_counts(tmp_path):
    base = _model("cutout")
    leaf = {"parent": f"{NS}:block/rack_base", "textures": base["textures"]}
    result = blocks.convert(_build(tmp_path, leaf, base))
    assert set(_methods(result).values()) == {"alpha_test"}
    assert any("Java render_type minecraft:cutout" in n for n in result.notes)


def test_solid_draws_every_face_opaque(tmp_path):
    result = blocks.convert(_build(tmp_path, _model("solid")))
    instances = result.files["blocks/rack.json"]["minecraft:block"]["components"]["minecraft:material_instances"]
    assert all("render_method" not in spec for spec in instances.values())


def test_a_render_type_with_no_stated_counterpart_falls_back_to_the_textures(tmp_path):
    result = blocks.convert(_build(tmp_path, _model("minecraft:tripwire")))
    assert set(_methods(result).values()) == {"alpha_test"}


def test_a_block_whose_faces_already_agree_is_untouched(tmp_path):
    # Uniform instances keep what they had, render_type or not (#262 only
    # resolves a mix).
    result = blocks.convert(_build(tmp_path, _model("cutout", lattice="plank")))
    instances = result.files["blocks/rack.json"]["minecraft:block"]["components"]["minecraft:material_instances"]
    assert instances == {"*": {"texture": f"{NS}:plank"}}
    assert not any("render method" in n for n in result.notes)


def test_resolve_keeps_the_nearest_render_type(tmp_path):
    mod = _build(tmp_path, _model(), {"parent": "minecraft:block/block", "render_type": "cutout"})
    child = {"parent": f"{NS}:block/rack_base", "render_type": "translucent"}
    flat, _, why = models.resolve(mod, child)
    assert why == "" and flat["render_type"] == "translucent"
    flat, _, _ = models.resolve(mod, {"parent": f"{NS}:block/rack_base"})
    assert flat["render_type"] == "cutout"


@pytest.mark.parametrize("instances,render_types,expected", [
    ({"a": {}, "b": {"render_method": "alpha_test"}}, {None}, "alpha_test"),
    ({"a": {}, "b": {"render_method": "blend"}}, set(), "blend"),
    ({"a": {"render_method": "alpha_test"}, "b": {"render_method": "blend"}}, {None}, "blend"),
    ({"a": {}, "b": {"render_method": "alpha_test"}}, {"minecraft:cutout_mipped"}, "alpha_test"),
    # Two models naming different types: no single Java answer, use alpha.
    ({"a": {}, "b": {"render_method": "alpha_test"}}, {"cutout", "translucent"}, "alpha_test"),
    # One model names a type and one leaves it to code: unread.
    ({"a": {}, "b": {"render_method": "blend"}}, {"cutout", None}, "blend"),
    ({"a": {"render_method": "double_sided"}, "b": {"render_method": "alpha_test"}}, {None}, None),
])
def test_shared_method(instances, render_types, expected):
    method, _ = blocks._shared_method(instances, render_types)
    assert method == expected


def _report(body):
    report = ValidationReport()
    _check_render_methods(report, "blocks/x.json", body)
    return [(f.rule, f.severity) for f in report.findings]


def test_the_validator_rejects_a_mix_anywhere_in_the_block():
    mixed = {"*": {"texture": "a"}, "up": {"texture": "b", "render_method": "alpha_test"}}
    same = {"*": {"texture": "a", "render_method": "blend"}, "up": {"texture": "b", "render_method": "blend"}}
    assert _report({"components": {"minecraft:material_instances": mixed}}) == [("block.render_method", "error")]
    assert _report({"components": {"minecraft:material_instances": same}}) == []
    assert _report({"components": {}, "permutations": [
        {"condition": "1", "components": {"minecraft:material_instances": mixed}}]}) == [("block.render_method", "error")]
    assert _report({"components": {"minecraft:item_visual": {"geometry": "g", "material_instances": mixed}}}) == [
        ("block.render_method", "error")]
    # Explicit opaque and an unset one are the same method (opaque is the default).
    assert _report({"components": {"minecraft:material_instances": {
        "*": {"texture": "a"}, "up": {"texture": "b", "render_method": "opaque"}}}}) == []
