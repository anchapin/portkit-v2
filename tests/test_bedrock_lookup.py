"""lookup_bedrock / list_bedrock_topics (#114): a deterministic Bedrock reference."""
import importlib.util
import json
from pathlib import Path

import pytest

from portkit.agent import RecordingClient, ReplayClient, ResidueAgent
from portkit.agent import reference
from portkit.agent.fake import FakeLLM, tool_call
from portkit.agent.loop import Message
from portkit.agent.tools import SYSTEM_PROMPT, ToolBox
from portkit.agent.transcript import load
from portkit.pipeline import convert

ROOT = Path(__file__).resolve().parents[1]
RESIDUE = ROOT / "fixtures" / "residue_mod" / "input"
REF_DIR = ROOT / "src" / "portkit" / "agent" / "reference"
SCHEMA = ROOT / "src" / "portkit" / "validate" / "schemas" / "1.26.60" / "bp" / "blocks" / "block_components.schema.json"


def _builder():
    spec = importlib.util.spec_from_file_location("build_ref", ROOT / "scripts" / "build_bedrock_reference.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _dump(value):
    return json.dumps(value, sort_keys=True)


# -- determinism -------------------------------------------------------
def test_the_same_topic_gives_the_same_bytes_even_after_a_reload():
    first = [_dump(reference.lookup(t)) for t in reference.topics()]
    reference._load.cache_clear()
    reference._aliases.cache_clear()
    reference._schema_file.cache_clear()
    second = [_dump(reference.lookup(t)) for t in reference.topics()]
    assert first == second
    assert _dump(reference.list_topics()) == _dump(reference.list_topics())
    assert reference.suggestions("destructable") == reference.suggestions("destructable")


def test_the_committed_reference_is_in_the_generator_format_with_its_pins():
    builder = _builder()
    text = (REF_DIR / "bedrock_reference.json").read_text(encoding="utf-8")
    data = json.loads(text)
    # Hand edits that skip the generator show up as a format difference.
    assert builder.render(data) == text
    assert data["pins"] == {
        repo: {"repo": slug, "commit": sha} for repo, (slug, sha) in builder.PINS.items()
    }
    for entry in data["topics"].values():
        for source in entry["sources"]:
            assert source.split("@")[0] in {slug for slug, _ in builder.PINS.values()}


def test_the_reference_set_is_small_and_attributed():
    size = sum(p.stat().st_size for p in REF_DIR.iterdir() if p.is_file() and p.suffix in {".json", ".md", ".txt"})
    assert size < 1_000_000
    assert (REF_DIR / "bedrock_reference.json").stat().st_size < 400_000
    notice = (REF_DIR / "NOTICE.md").read_text()
    assert "CC BY 4.0" in notice and "Mojang/bedrock-samples" in notice
    assert (REF_DIR / "LICENSE-CC-BY-4.0.txt").is_file()


# -- known topics --------------------------------------------------------
def test_a_block_component_carries_the_vendored_schema_an_example_and_a_note():
    out = reference.lookup("minecraft:destructible_by_mining")
    assert out["topic"] == "minecraft:destructible_by_mining" and out["kind"] == "block_component"
    assert "seconds_to_destroy" in out["schema"] and "defaultSnippets" not in out["schema"]
    assert "seconds_to_destroy" in out["example"]
    assert "hardness" in out["note"]
    assert any("bedrock-schemas 1.26.60" in s for s in out["sources"])


def test_every_block_component_in_the_vendored_schema_is_a_topic():
    components = json.loads(SCHEMA.read_text())["properties"]
    for name in components:
        out = reference.lookup(name)
        assert out.get("topic") == name, name
        assert out.get("schema"), name


@pytest.mark.parametrize(
    "query, topic, needle",
    [
        ("recipe_smithing_transform", "recipe_smithing_transform", '"minecraft:recipe_smithing_transform"'),
        ("minecraft:recipe_shaped", "recipe_shaped", '"pattern"'),
        ("recipe_smithing_trim", "recipe_smithing_trim", '"template"'),
        ("item_texture.json", "item_texture.json", '"texture_data"'),
        ("resource_pack/textures/terrain_texture.json", "terrain_texture.json", '"atlas.terrain"'),
        ("~LINEBREAK~", "lang", "~LINEBREAK~"),
        ("resource_pack/texts/pt_BR.lang", "lang", "item.apple.name"),
        ("destructible_by_mining", "minecraft:destructible_by_mining", "seconds_to_destroy"),
        ("item:minecraft:icon", "item:minecraft:icon", "minecraft:icon"),
        ("loot_table", "loot_table", '"pools"'),
    ],
)
def test_known_topics_and_their_aliases(query, topic, needle):
    out = reference.lookup(query)
    assert out["topic"] == topic
    assert needle in json.dumps(out, ensure_ascii=False).replace('\\"', '"')
    assert out["sources"]


def test_tag_lists_and_cross_references():
    tags = reference.lookup("recipe_item_tags")
    assert "minecraft:planks" in tags["tags"]
    assert "block_tags" in reference.lookup("minecraft:tags")["see_also"]
    assert "item:minecraft:display_name" in reference.lookup("display_name")["see_also"]


# -- unknown topics --------------------------------------------------------
def test_an_unknown_topic_suggests_the_closest_names_in_a_fixed_order():
    out = reference.lookup("destructable_by_mining")
    assert "error" in out and "list_bedrock_topics" in out["hint"]
    assert out["did_you_mean"][0] == "minecraft:destructible_by_mining"
    assert len(out["did_you_mean"]) <= reference.MAX_SUGGESTIONS
    assert reference.lookup("recipe_shapd")["did_you_mean"][0] == "recipe_shaped"
    assert out == reference.lookup("destructable_by_mining")


def test_nonsense_and_empty_topics_point_at_the_list():
    assert reference.lookup("qqqqzzzz")["did_you_mean"] == []
    assert "list_bedrock_topics" in reference.lookup("  ")["hint"]


# -- length cap -------------------------------------------------------------
def test_every_answer_fits_the_cap():
    for topic in reference.topics():
        assert len(json.dumps(reference.lookup(topic), ensure_ascii=False)) <= reference.MAX_CHARS, topic
    assert len(json.dumps(reference.list_topics())) <= reference.MAX_CHARS


def test_a_long_answer_is_trimmed_and_says_so(monkeypatch):
    monkeypatch.setattr(reference, "MAX_CHARS", 1500)
    out = reference.lookup("loot_table")
    assert out["truncated"] is True and out.get("fields_omitted", 0) > 0
    assert len(json.dumps(out, ensure_ascii=False)) <= 1500
    assert out["topic"] == "loot_table" and out["sources"]


# -- listing ------------------------------------------------------------------
def test_list_topics_filters_by_prefix():
    everything = reference.list_topics()
    assert everything["count"] == len(reference.topics()) >= 80
    recipes = reference.list_topics("recipe")
    assert "recipe_shaped" in recipes["topics"]["recipe"]
    light = reference.list_topics("minecraft:light")["topics"]["block_component"]
    assert light == ["minecraft:light_dampening", "minecraft:light_emission"]
    assert reference.list_topics("light")["topics"]["block_component"] == light
    assert reference.list_topics("nothing_like_this")["count"] == 0


# -- the agent sees it --------------------------------------------------------
def test_the_tools_are_registered_and_in_the_prompt(tmp_path):
    box = ToolBox(tmp_path, tmp_path / "out")
    names = {s["name"] for s in box.schemas()}
    assert {"lookup_bedrock", "list_bedrock_topics"} <= names
    assert box.format_error("lookup_bedrock", {"topic": "recipe_shaped"}) is None
    assert box.format_error("lookup_bedrock", {}) is not None
    assert box.format_error("list_bedrock_topics", {}) is None
    assert box.invoke("lookup_bedrock", {"topic": "recipe_shaped"}) == reference.lookup("recipe_shaped")
    assert box.invoke("list_bedrock_topics", {"prefix": "recipe"}) == reference.list_topics("recipe")
    assert "lookup_bedrock" in SYSTEM_PROMPT and "list_bedrock_topics" in SYSTEM_PROMPT


def test_a_session_that_looks_things_up_replays_strictly(tmp_path):
    script = [
        tool_call("list_bedrock_topics", prefix="recipe"),
        tool_call("lookup_bedrock", topic="recipe_smithing_trim"),
        tool_call("lookup_bedrock", topic="recipe_smithng"),
        Message("assistant", "A tag recipe needs no lookup."),
        Message("assistant", "No faithful Bedrock form for this trim."),
    ]
    path = tmp_path / "lookup.jsonl"
    recorded = convert(RESIDUE, tmp_path / "rec", agent=ResidueAgent(RecordingClient(FakeLLM(script), path)))
    assert [e["reply"]["tool_calls"][0]["name"] for e in load(path)[:3]] == [
        "list_bedrock_topics", "lookup_bedrock", "lookup_bedrock",
    ]
    for run in ("a", "b"):
        client = ReplayClient(path)  # strict: every request digest must match
        replayed = convert(RESIDUE, tmp_path / run, agent=ResidueAgent(client))
        assert client.remaining == 0
        assert replayed.agent.summary() == recorded.agent.summary()


def test_trimming_terminates_under_a_tiny_cap(monkeypatch):
    for cap in (400, 800):
        monkeypatch.setattr(reference, "MAX_CHARS", cap)
        out = reference.lookup("minecraft:destructible_by_mining")
        assert out["truncated"] is True and out["topic"] == "minecraft:destructible_by_mining"
        assert out == reference.lookup("minecraft:destructible_by_mining")
