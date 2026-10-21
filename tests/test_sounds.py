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


# --- events that play another event are inlined (#356) ----------------------


def _java_vanilla(monkeypatch, tmp_path, events):
    path = tmp_path / "java_sounds.json"
    path.write_text(json.dumps({"events": events}))
    monkeypatch.setenv("PORTKIT_JAVA_SOUND_REFERENCE", str(path))


def _defs(result):
    return result.files["sounds/sound_definitions.json"]["sound_definitions"]


def test_an_own_event_reference_inlines_the_target_with_multiplied_volume_and_pitch(tmp_path):
    index = {
        "block.brazier.crackle": {"category": "block", "sounds": [
            {"name": "examplemod:block/brazier/crackle1", "volume": 0.5, "pitch": 1.5, "weight": 3}]},
        "block.brazier.loud": {"category": "block", "sounds": [
            {"type": "event", "name": "examplemod:block.brazier.crackle", "volume": 0.6,
             "pitch": 1.2, "stream": True, "weight": 9}]},
    }
    result = sounds.convert(build(tmp_path, index))
    # SoundManager SOUND_EVENT: volume 0.5*0.6, pitch 1.5*1.2, stream ORs, the
    # sound keeps its own weight (the referencing entry's weight is ignored).
    assert _defs(result)["examplemod:block.brazier.loud"] == {"category": "block", "sounds": [
        {"name": "sounds/block/brazier/crackle1", "volume": 0.3, "pitch": 1.8, "weight": 3,
         "stream": True}]}
    assert result.unhandled == []
    assert any("1 sound event(s) play another event" in n for n in result.notes)


def test_a_vanilla_event_reference_inlines_vanillas_sounds_bedrock_has(tmp_path, monkeypatch):
    _java_vanilla(monkeypatch, tmp_path, {
        "minecraft:entity.slime.squish": [
            "mob/slime/big1", {"name": "random/bow", "weight": 2, "volume": 0.5}, "mob/slime/gone"]})
    event = {"category": "neutral", "sounds": [
        {"type": "event", "name": "entity.slime.squish", "pitch": 0.5}]}
    result = sounds.convert(build(tmp_path, {"entity.bug.squish": event}))
    assert _defs(result)["examplemod:entity.bug.squish"]["sounds"] == [
        {"name": "sounds/mob/slime/big1", "pitch": 0.5},
        {"name": "sounds/random/bow", "volume": 0.5, "pitch": 0.5, "weight": 2}]
    # The vanilla file Bedrock doesn't have is dropped by the same-path rule, named.
    assert any("via minecraft:entity.slime.squish" in n and "mob/slime/gone" in n for n in result.notes)


def test_references_resolve_recursively_and_multiply_down_the_chain(tmp_path, monkeypatch):
    _java_vanilla(monkeypatch, tmp_path, {"minecraft:entity.slime.squish": [{"name": "random/bow", "pitch": 2}]})
    index = {
        "a": {"sounds": [{"type": "event", "name": "examplemod:b", "volume": 0.5}]},
        "b": {"sounds": [{"type": "event", "name": "minecraft:entity.slime.squish", "volume": 0.5,
                          "pitch": 0.25}]},
    }
    result = sounds.convert(build(tmp_path, index))
    assert _defs(result)["examplemod:a"]["sounds"] == [
        {"name": "sounds/random/bow", "volume": 0.25, "pitch": 0.5}]


def test_a_reference_loop_refuses_the_event(tmp_path):
    index = {
        "a": {"sounds": [{"type": "event", "name": "examplemod:b"}]},
        "b": {"sounds": ["examplemod:block/brazier/crackle1", {"type": "event", "name": "examplemod:a"}]},
    }
    result = sounds.convert(build(tmp_path, index))
    reasons = sorted(u.reason for u in result.unhandled)
    assert len(reasons) == 2 and all("loop" in r for r in reasons)
    assert "examplemod:a -> examplemod:b -> examplemod:a" in reasons[0]
    assert "sounds/sound_definitions.json" not in result.files
    assert result.residue_count == 0


def test_another_mods_event_is_refused_and_named(tmp_path):
    event = {"category": "block", "sounds": [{"type": "event", "name": "othermod:block.fire.ambient"}]}
    result = sounds.convert(build(tmp_path, {"block.brazier.crackle": event}))
    assert "of another mod" in result.unhandled[0].reason
    assert "othermod:block.fire.ambient" in result.unhandled[0].reason


def test_an_undefined_target_plays_nothing_so_only_that_entry_drops(tmp_path, monkeypatch):
    _java_vanilla(monkeypatch, tmp_path, {})
    event = {"category": "block", "sounds": [
        "examplemod:block/brazier/crackle1",
        {"type": "event", "name": "examplemod:missing"},
        {"type": "event", "name": "minecraft:no.such.event"}]}
    result = sounds.convert(build(tmp_path, {"block.brazier.crackle": event}))
    assert _defs(result)["examplemod:block.brazier.crackle"]["sounds"] == [
        {"name": "sounds/block/brazier/crackle1"}]
    note = next(n for n in result.notes if "dropped 2 sound(s)" in n)
    assert "doesn't define" in note


def test_a_target_with_no_sounds_is_named_when_nothing_is_left(tmp_path):
    index = {"a": {"sounds": [{"type": "event", "name": "examplemod:b"}]}, "b": {"sounds": []}}
    result = sounds.convert(build(tmp_path, index))
    assert any("event 'a' has no sound" in u.reason and "lists no sounds" in u.reason
               for u in result.unhandled)


def test_without_the_java_vanilla_set_a_vanilla_reference_says_how_to_keep_it(tmp_path):
    event = {"category": "block", "sounds": [{"type": "event", "name": "minecraft:block.fire.ambient"}]}
    result = sounds.convert(build(tmp_path, {"block.brazier.crackle": event}))
    assert "sounds/sound_definitions.json" not in result.files
    assert "isn't cached; run `portkit reference fetch`" in result.unhandled[0].reason


def test_a_file_entrys_weight_is_carried(tmp_path):
    event = {"category": "block", "sounds": [{"name": "examplemod:block/brazier/crackle1", "weight": 4},
                                             {"name": "examplemod:block/brazier/crackle1", "weight": 0}]}
    result = sounds.convert(build(tmp_path, {"block.brazier.crackle": event}))
    assert _defs(result)["examplemod:block.brazier.crackle"]["sounds"] == [
        {"name": "sounds/block/brazier/crackle1", "weight": 4}]


def test_the_java_sound_set_follows_the_jars_game_version():
    from portkit.data import java_sounds

    assert java_sounds.select("1.20.1").minecraft == "1.20.1"
    assert java_sounds.select("1.21").minecraft == "1.21.1"
    assert java_sounds.select("1.18.2").minecraft == "1.19.2"
    assert java_sounds.select(None) is None
    assert all(len(s.sha256) == 64 and "/sounds/data.json" in s.url for s in java_sounds.SETS)


def test_the_java_sound_set_derivation_keeps_only_sounds_lists():
    from portkit.data import java_sounds

    summary = json.dumps({"b.x": {"sounds": ["a/b"], "subtitle": "s"}, "a.y": {"replace": True}}).encode()
    out = json.loads(java_sounds.derive(java_sounds.SETS[0], summary))
    assert out["events"] == {"minecraft:b.x": ["a/b"]}


def test_a_sound_from_another_namespace_is_refused(tmp_path):
    event = {"category": "block", "sounds": ["othermod:block/fire/fire1"]}
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


# --- no dangling audio references (#116) ------------------------------------


def _definitions(result):
    return result.files["sounds/sound_definitions.json"]["sound_definitions"]


def test_a_bare_name_is_vanilla_and_kept_when_bedrock_has_that_file(tmp_path):
    # random/bow is sounds/random/bow in Bedrock's vanilla pack.
    event = {"category": "neutral", "sounds": ["random/bow", "minecraft:mob/slime/big1"]}
    result = sounds.convert(build(tmp_path, {"throw": event}))
    assert _definitions(result)["examplemod:throw"]["sounds"] == [
        {"name": "sounds/random/bow"}, {"name": "sounds/mob/slime/big1"}]
    assert not result.unhandled and not result.notes


def test_a_bare_name_bedrock_files_elsewhere_is_never_treated_as_the_mods_own(tmp_path):
    # Java's item/armor/equip_chain1 is sounds/armor/equip_chain1 in Bedrock:
    # no reliable mapping, and the mod doesn't ship it either.
    event = {"category": "player", "sounds": ["item/armor/equip_chain1", "item/armor/equip_chain2"]}
    result = sounds.convert(build(tmp_path, {"equip.travelers": event}))
    assert "sounds/sound_definitions.json" not in result.files
    [entry] = result.unhandled
    assert entry.count == 0
    assert "equip.travelers" in entry.reason and "no sound Bedrock can play" in entry.reason
    assert "vanilla Java sound" in entry.reason and "item/armor/equip_chain1" in entry.reason


def test_a_bare_name_that_happens_to_match_the_mods_own_audio_is_still_vanilla(tmp_path):
    # Java would play minecraft:block/brazier/crackle1, which doesn't exist;
    # the mod's file of the same path is not what that name means.
    event = {"category": "block", "sounds": ["block/brazier/crackle1"]}
    result = sounds.convert(build(tmp_path, {"crackle": event}))
    assert "sounds/sound_definitions.json" not in result.files
    assert "vanilla Java sound" in result.unhandled[0].reason


def test_mod_audio_missing_from_the_jar_is_dropped_and_the_rest_of_the_event_kept(tmp_path):
    event = {"category": "block", "sounds": [
        "examplemod:block/brazier/crackle1", "examplemod:item/awning_bounce_1", "random/bow"]}
    result = sounds.convert(build(tmp_path, {"bounce": event}))
    assert _definitions(result)["examplemod:bounce"]["sounds"] == [
        {"name": "sounds/block/brazier/crackle1"}, {"name": "sounds/random/bow"}]
    assert not result.unhandled
    [note] = result.notes
    assert "examplemod:bounce" in note and "assets/examplemod/sounds/item/awning_bounce_1.ogg" in note


def test_an_event_whose_mod_audio_is_all_missing_is_withdrawn(tmp_path):
    event = {"category": "music", "sounds": [{"name": "examplemod:music/ender_hollow", "stream": True}]}
    result = sounds.convert(build(tmp_path, {"music.ender_hollow": event}))
    assert "sounds/sound_definitions.json" not in result.files
    assert "does not ship" in result.unhandled[0].reason
    assert result.residue_count == 0


def test_a_wav_the_converter_refused_is_not_referenced(tmp_path):
    event = {"category": "block", "sounds": ["examplemod:block/old_loop"]}
    result = sounds.convert(build(tmp_path, {"loop": event}, audio=("block/old_loop.wav",)))
    assert "sounds/sound_definitions.json" not in result.files
    reasons = " ".join(u.reason for u in result.unhandled)
    assert ".ogg only" in reasons and "does not ship" in reasons


def test_the_validator_warns_about_a_dangling_sound(tmp_path):
    from portkit.validate import validate_pack

    pack = tmp_path / "resource_pack"
    (pack / "sounds" / "block").mkdir(parents=True)
    (pack / "sounds" / "block" / "here.ogg").write_bytes(OGG)
    (pack / "sounds" / "sound_definitions.json").write_text(json.dumps({
        "format_version": "1.14.0",
        "sound_definitions": {"m:e": {"category": "block", "sounds": [
            "sounds/block/here", {"name": "sounds/random/bow"}, {"name": "sounds/block/gone"}]}},
    }))
    found = [f for f in validate_pack(pack).findings if f.rule.startswith("sound.")]
    assert [(f.rule, f.severity) for f in found] == [("sound.missing", "warning")]
    assert "sounds/block/gone" in found[0].message


# --- the vanilla list is fetched on demand, not vendored (#124) -------------


def _no_vanilla_list(monkeypatch, tmp_path):
    monkeypatch.delenv("PORTKIT_VANILLA_SOUNDS", raising=False)
    monkeypatch.setenv("PORTKIT_REFERENCE_CACHE", str(tmp_path / "empty-cache"))


def test_without_the_cached_list_vanilla_names_are_dropped_saying_how_to_keep_them(tmp_path, monkeypatch):
    _no_vanilla_list(monkeypatch, tmp_path)
    event = {"category": "block", "sounds": [
        "examplemod:block/brazier/crackle1", "random/bow", "minecraft:mob/slime/big1"]}
    result = sounds.convert(build(tmp_path, {"bounce": event}))
    assert _definitions(result)["examplemod:bounce"]["sounds"] == [
        {"name": "sounds/block/brazier/crackle1"}]
    [note] = result.notes
    assert "dropped 2 sound(s)" in note
    assert note.count("portkit reference fetch") == 2
    assert "sounds/random/bow" in note and "sounds/mob/slime/big1" in note


def test_without_the_cached_list_an_all_vanilla_event_is_withdrawn(tmp_path, monkeypatch):
    _no_vanilla_list(monkeypatch, tmp_path)
    result = sounds.convert(build(tmp_path, {"throw": {"category": "neutral", "sounds": ["random/bow"]}}))
    assert "sounds/sound_definitions.json" not in result.files
    [entry] = result.unhandled
    assert entry.count == 0 and "portkit reference fetch" in entry.reason


def test_the_no_cache_output_is_deterministic(tmp_path, monkeypatch):
    _no_vanilla_list(monkeypatch, tmp_path)
    index = {"a": {"category": "block", "sounds": ["random/bow", "examplemod:block/brazier/crackle1"]},
             "b": {"category": "block", "sounds": ["mob/slime/big1"]}}
    runs = [sounds.convert(build(tmp_path / str(i), index)) for i in range(2)]
    assert runs[0].files == runs[1].files and runs[0].notes == runs[1].notes
    assert [u.reason for u in runs[0].unhandled] == [u.reason for u in runs[1].unhandled]


def test_the_validator_says_when_it_cannot_check_vanilla_audio(tmp_path, monkeypatch):
    from portkit.validate import validate_pack

    _no_vanilla_list(monkeypatch, tmp_path)
    pack = tmp_path / "resource_pack"
    (pack / "sounds").mkdir(parents=True)
    (pack / "sounds" / "sound_definitions.json").write_text(json.dumps({
        "format_version": "1.14.0",
        "sound_definitions": {"m:e": {"category": "block", "sounds": ["sounds/random/bow"]}},
    }))
    [found] = [f for f in validate_pack(pack).findings if f.rule.startswith("sound.")]
    assert found.rule == "sound.missing" and found.severity == "warning"
    assert "portkit reference fetch" in found.message
