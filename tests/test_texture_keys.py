"""A texture whose Java path has a hyphen still gets a valid Bedrock key (Mythic Metals dura-chan)."""
import json

from portkit.converters import models, textures
from portkit.model import SourceMod
from portkit.pipeline import convert
from portkit.validate.rules import _TEXTURE_KEY

PNG = b"\x89PNG\r\n\x1a\n"


def put(root, rel, body=PNG):
    path = root / "assets" / "examplemod" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body) if isinstance(body, bytes) else path.write_text(json.dumps(body))


def test_a_hyphen_becomes_an_underscore_in_the_key():
    assert textures.shortname("dura-chan", "examplemod") == "examplemod:dura_chan"
    assert textures.shortname("tools/dura-chan", "examplemod") == "examplemod:tools_dura_chan"


def test_every_legal_java_path_character_gives_a_valid_identifier():
    # Java resource-location paths are [a-z0-9/._-].
    key = textures.shortname("a-b/c.d_e9", "examplemod")
    assert _TEXTURE_KEY.match(key), key


def test_the_hyphenated_texture_keeps_its_file_path(tmp_path):
    put(tmp_path, "textures/item/dura-chan.png")
    result = textures.convert(SourceMod(root=tmp_path, namespace="examplemod"))
    assert "textures/items/dura-chan.png" in result.files
    index = result.files["textures/item_texture.json"]["texture_data"]
    assert index == {"examplemod:dura_chan": {"textures": "textures/items/dura-chan"}}
    assert result.unhandled == []


def test_the_model_reference_resolves_to_the_same_key(tmp_path):
    put(tmp_path, "textures/item/dura-chan.png")
    result = textures.convert(SourceMod(root=tmp_path, namespace="examplemod"))
    key, why = models.texture_shortname("examplemod:item/dura-chan", "examplemod")
    assert why == ""
    assert key in result.files["textures/item_texture.json"]["texture_data"]


def test_a_hyphen_and_an_underscore_that_collide_are_both_residue(tmp_path):
    put(tmp_path, "textures/item/a-b.png")
    put(tmp_path, "textures/item/a_b.png")
    put(tmp_path, "textures/item/fine.png")
    result = textures.convert(SourceMod(root=tmp_path, namespace="examplemod"))
    assert sorted(u.source for u in result.unhandled) == [
        "assets/examplemod/textures/item/a-b.png",
        "assets/examplemod/textures/item/a_b.png",
    ]
    assert all("examplemod:a_b" in u.reason for u in result.unhandled)
    assert list(result.files["textures/item_texture.json"]["texture_data"]) == ["examplemod:fine"]
    assert "textures/items/a-b.png" not in result.files


def test_end_to_end_a_hyphenated_item_validates(tmp_path):
    put(tmp_path, "textures/item/dura-chan.png")
    put(tmp_path, "models/item/dura-chan.json", {
        "parent": "minecraft:item/generated",
        "textures": {"layer0": "examplemod:item/dura-chan"},
    })
    out = convert(tmp_path, tmp_path / "out", emit_addon=False)
    assert out.report.ok, [f.message for f in out.report.errors]
    atlas = json.loads((out.tree / "resource_pack/textures/item_texture.json").read_text())
    assert "examplemod:dura_chan" in atlas["texture_data"]
