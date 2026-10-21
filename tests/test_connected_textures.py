"""#348 (part of #277): pre-1.11 texture paths get valid index keys, and a
Connected Textures Mod sidecar is the explained ``connected_texture`` residue.

1. Keys: lowercased, anything outside [a-z0-9_.] becomes "_" (as "/" and "-"
   always did); the file keeps its path; two textures on one key stay residue.
2. A ``.png.mcmeta`` with a ``"ctm"`` section and no ``animation`` is
   ``connected_texture`` (pick 1a), skipped by the residue agent (pick 5a); the
   texture still goes with it (pick 3a). Invalid JSON stays ``texture_animation``
   (pick 2a); an animation beside a ctm section still converts (pick 4a).

Offline, ``examplemod`` only; no mod names (#220).
"""
import json

import pytest

from portkit.agent.residue import SKIP_KINDS
from portkit.converters import models, textures
from portkit.model import SourceMod
from portkit.validate.rules import _TEXTURE_KEY

from test_animated_textures import png_bytes


def _mod(tmp_path, files):
    for rel, body in files.items():
        path = tmp_path / "assets" / "examplemod" / "textures" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(body, bytes):
            path.write_bytes(body)
        elif isinstance(body, str):
            path.write_text(body)
        else:
            path.write_text(json.dumps(body))
    return SourceMod(root=tmp_path, namespace="examplemod")


@pytest.mark.parametrize("subpath, key", [
    ("palettes/andesite", "examplemod:palettes_andesite"),       # unchanged
    ("dura-chan", "examplemod:dura_chan"),                        # unchanged
    ("glow.v2", "examplemod:glow.v2"),                            # "." is legal, kept
    ("hexPlating/hexbase", "examplemod:hexplating_hexbase"),
    ("redstoneLamp/square-on", "examplemod:redstonelamp_square_on"),
    ("dirt/bricks+dirt2-ctmv", "examplemod:dirt_bricks_dirt2_ctmv"),
    ("odd name/x@y", "examplemod:odd_name_x_y"),
])
def test_shortname_is_a_valid_key(subpath, key):
    assert textures.shortname(subpath, "examplemod") == key
    assert _TEXTURE_KEY.match(key)


def test_legacy_path_keeps_its_file_and_gets_a_valid_key(tmp_path):
    mod = _mod(tmp_path, {"blocks/hexPlating/hexbase.png": png_bytes(16, 16),
                          "blocks/dirt/bricks+dirt2-ctmv.png": png_bytes(16, 16)})
    result = textures.convert(mod)
    assert result.unhandled == []
    index = result.files["textures/terrain_texture.json"]["texture_data"]
    assert index == {
        "examplemod:hexplating_hexbase": {"textures": "textures/blocks/hexPlating/hexbase"},
        "examplemod:dirt_bricks_dirt2_ctmv": {"textures": "textures/blocks/dirt/bricks+dirt2-ctmv"},
    }
    # every index entry names a file the pack ships
    for entry in index.values():
        assert f"{entry['textures']}.png" in result.files
    assert all(_TEXTURE_KEY.match(k) for k in index)


def test_model_reference_resolves_to_the_same_key(tmp_path):
    key, why = models.texture_shortname("examplemod:blocks/hexPlating/hexbase", "examplemod")
    assert (key, why) == ("examplemod:hexplating_hexbase", "")


def test_keys_that_meet_after_sanitising_are_both_residue(tmp_path):
    mod = _mod(tmp_path, {"block/Lamp.png": png_bytes(16, 16), "block/lamp.png": png_bytes(16, 16)})
    result = textures.convert(mod)
    assert sorted(u.kind for u in result.unhandled) == ["texture", "texture"]
    assert "textures/terrain_texture.json" not in result.files
    assert result.files == {}


@pytest.mark.parametrize("section, named", [
    ({"ctm_version": 1, "type": "ctm"}, "CTM type ctm"),
    ({"ctm_version": 1, "type": "pattern", "extra": {"size": 3}}, "CTM type pattern"),
    ({"ctm_version": 1, "type": "R"}, "CTM type r"),
    ({"ctm_version": 1, "layer": "CUTOUT"}, "CTM type normal (no type)"),
])
def test_ctm_sidecar_is_connected_texture(tmp_path, section, named):
    mod = _mod(tmp_path, {"block/plate.png": png_bytes(48, 48),
                          "block/plate.png.mcmeta": {"ctm": section}})
    result = textures.convert(mod)
    assert [(u.source, u.kind) for u in result.unhandled] == [
        ("assets/examplemod/textures/block/plate.png.mcmeta", "connected_texture")]
    assert named in result.unhandled[0].reason
    # pick 3a: not converted, the texture goes with its sidecar
    assert result.files == {}


def test_kind_is_explained():
    assert textures.CONNECTED_TEXTURE == "connected_texture"
    assert "connected_texture" in SKIP_KINDS


def test_animation_beside_a_ctm_section_still_converts(tmp_path):
    # pick 4a: unchanged by #348
    mod = _mod(tmp_path, {"block/fan.png": png_bytes(16, 32),
                          "block/fan.png.mcmeta": {"animation": {"frametime": 2},
                                                   "ctm": {"ctm_version": 1, "type": "ctm"}}})
    result = textures.convert(mod)
    assert result.unhandled == []
    assert result.files["textures/flipbook_textures.json"][0]["atlas_tile"] == "examplemod:fan"


@pytest.mark.parametrize("text", [
    '{"animation": {"interpolate": true "frames": [0, 1]}}',   # missing comma
    '{"animation": {"frames": [0, 1, ]}}',                     # trailing comma
    '{"ctm": {"ctm_version": 1, }}',                           # even with a ctm section
])
def test_invalid_json_stays_texture_animation(tmp_path, text):
    # pick 2a: an unreadable sidecar isn't known to be CTM's
    mod = _mod(tmp_path, {"block/strobe.png": png_bytes(16, 32), "block/strobe.png.mcmeta": text})
    result = textures.convert(mod)
    assert [u.kind for u in result.unhandled] == ["texture_animation"]
    assert result.unhandled[0].reason.startswith("invalid JSON")
    assert result.files == {}


def test_other_sections_stay_texture_animation(tmp_path):
    mod = _mod(tmp_path, {"block/x.png": png_bytes(16, 16),
                          "block/x.png.mcmeta": {"texture": {"blur": True}}})
    result = textures.convert(mod)
    assert [u.kind for u in result.unhandled] == ["texture_animation"]
