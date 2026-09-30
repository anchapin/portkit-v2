"""Sounds: the event map is a rename, anything vanilla-facing is residue."""
import json

from portkit.converters import sounds
from portkit.model import SourceMod

OGG = b"OggS\x00\x02"


def build(tmp_path, index=None, audio=("block/brazier/crackle1.ogg",)):
    assets = tmp_path / "assets" / "examplemod"
    for rel in audio:
        path = assets / "sounds" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(OGG)
    if index is not None:
        assets.mkdir(parents=True, exist_ok=True)
        (assets / "sounds.json").write_text(json.dumps(index))
    return SourceMod(root=tmp_path, namespace="examplemod")


EVENT = {"category": "block", "sounds": ["examplemod:block/brazier/crackle1"]}


def test_ogg_files_are_copied_under_sounds(tmp_path):
    result = sounds.convert(build(tmp_path))
    assert result.files["sounds/block/brazier/crackle1.ogg"] == OGG


def test_an_event_becomes_a_namespaced_sound_definition(tmp_path):
    result = sounds.convert(build(tmp_path, {"block.brazier.crackle": EVENT}))
    definitions = result.files["sounds/sound_definitions.json"]["sound_definitions"]
    assert definitions["examplemod:block.brazier.crackle"] == {
        "category": "block",
        "sounds": [{"name": "sounds/block/brazier/crackle1"}],
    }


def test_volume_pitch_and_stream_survive(tmp_path):
    event = {"category": "block", "sounds": [
        {"name": "examplemod:block/brazier/crackle1", "volume": 0.6, "pitch": 1.2, "stream": True}]}
    result = sounds.convert(build(tmp_path, {"block.brazier.crackle": event}))
    entry = result.files["sounds/sound_definitions.json"]["sound_definitions"][
        "examplemod:block.brazier.crackle"]["sounds"][0]
    assert entry == {"name": "sounds/block/brazier/crackle1", "volume": 0.6,
                     "pitch": 1.2, "stream": True}


def test_a_vanilla_event_override_is_reported_not_guessed(tmp_path):
    result = sounds.convert(build(tmp_path, {"block.stone.break": {**EVENT, "replace": True}}))
    assert "sounds/sound_definitions.json" not in result.files
    assert "replaces a vanilla sound event" in result.unhandled[0].reason


def test_an_unknown_category_is_reported(tmp_path):
    result = sounds.convert(build(tmp_path, {"music.theme": {**EVENT, "category": "jukebox"}}))
    reason = result.unhandled[0].reason
    assert "jukebox" in reason and "no Bedrock equivalent" in reason


def test_a_non_ogg_file_is_reported_rather_than_copied_silent(tmp_path):
    result = sounds.convert(build(tmp_path, audio=("block/old_loop.wav",)))
    assert result.files == {}
    assert ".ogg only" in result.unhandled[0].reason


def test_an_event_referring_to_another_event_is_refused(tmp_path):
    event = {"category": "block", "sounds": [{"type": "event", "name": "minecraft:block.fire.ambient"}]}
    result = sounds.convert(build(tmp_path, {"block.brazier.crackle": event}))
    assert "plays another event" in result.unhandled[0].reason


def test_a_sound_from_another_namespace_is_refused(tmp_path):
    event = {"category": "block", "sounds": ["minecraft:block/fire/fire1"]}
    result = sounds.convert(build(tmp_path, {"block.brazier.crackle": event}))
    assert "another namespace" in result.unhandled[0].reason


def test_event_level_refusals_do_not_inflate_the_file_count(tmp_path):
    """sounds.json is one file, however many of its events we refuse."""
    index = {"a": {**EVENT, "replace": True}, "b": {**EVENT, "category": "jukebox"}}
    result = sounds.convert(build(tmp_path, index))
    assert len(result.unhandled) == 2
    assert result.residue_count == 0


def test_the_fixture_converts_the_custom_events(tmp_path, fixtures_dir):
    from portkit.pipeline import convert

    out = convert(fixtures_dir / "sounds_mod" / "input", tmp_path / "out")
    assert out.report.ok, out.report.to_dict()
    body = json.loads(
        (out.tree / "resource_pack" / "sounds" / "sound_definitions.json").read_text()
    )
    assert sorted(body["sound_definitions"]) == [
        "examplemod:block.brazier.crackle",
        "examplemod:block.brazier.light",
    ]
    reasons = " ".join(u.reason for u in out.unhandled)
    assert "replaces a vanilla sound event" in reasons
    assert "jukebox" in reasons
    assert ".ogg only" in reasons
