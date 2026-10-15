"""Agent-written block states must come from the Java blockstate (#149).

On storage drawers and waystones residue GLM 5.3 wrote ``facing`` as an
integer enum (``0/1/2``) where Java names its values, and state values the Java
blockstate never lists. No guard read block states.
"""
import json
import shutil
import zipfile
from pathlib import Path

import pytest

from portkit import corpus
from portkit.agent.fake import FakeLLM, tool_call
from portkit.agent.loop import Message
from portkit.agent.residue import ResidueAgent, _TrackingToolBox, group_residue
from portkit.agent.states import blockstate_file, invented_states, java_states
from portkit.pipeline import convert

ROOT = Path(__file__).resolve().parents[1]
BLOCK_DEFS = ROOT / "fixtures" / "block_defs_mod" / "input"
STAIRS = "block:assets/examplemod/blockstates/steel_stairs.json"
STAIRS_PATH = "behavior_pack/blocks/steel_stairs.json"


def _block(ident="examplemod:steel_stairs", states=None, permutations=None, traits=None, components=None):
    description = {"identifier": ident, "menu_category": {"category": "construction"}}
    if states is not None:
        description["states"] = states
    if traits is not None:
        description["traits"] = traits
    body = {"description": description, "components": components or {
        "minecraft:geometry": "minecraft:geometry.full_block",
        "minecraft:material_instances": {"*": {"texture": "examplemod:steel_block"}},
    }}
    if permutations is not None:
        body["permutations"] = permutations
    return {"format_version": "1.21.40", "minecraft:block": body}


def _cond(expr):
    return {"condition": expr, "components": {}}


def _source(tmp_path, blockstates):
    """A minimal mod with the given blockstate files under assets/examplemod."""
    root = tmp_path / "src"
    folder = root / "assets" / "examplemod" / "blockstates"
    folder.mkdir(parents=True)
    for name, data in blockstates.items():
        (folder / f"{name}.json").write_text(json.dumps(data))
    return root


def _check(tmp_path, source, doc, rel="behavior_pack/blocks/b.json"):
    out = tmp_path / "out"
    (out / rel).parent.mkdir(parents=True, exist_ok=True)
    (out / rel).write_text(json.dumps(doc))
    return invented_states(out, [rel], source)


PORTSTONE = {"variants": {
    f"facing={f},half={h}": {"model": f"waystones:block/portstone_{'bottom' if h == 'lower' else 'top'}"}
    for f in ("east", "north", "south", "west") for h in ("lower", "upper")
}}
CAULDRON = {"variants": {f"level={n}": {"model": "examplemod:block/c"} for n in range(4)}}
LAMP = {"multipart": [
    {"apply": {"model": "examplemod:block/lamp"}},
    {"when": {"lit": "true"}, "apply": {"model": "examplemod:block/lamp_on"}},
    {"when": {"OR": [{"north": "side|up"}, {"south": "side"}]}, "apply": {"model": "examplemod:block/wire"}},
]}
FORGE = {"forge_marker": 1, "defaults": {"model": "examplemod:drawer"},
         "variants": {"facing": {"north": {}, "south": {"y": 180}}, "inventory": [{}], "normal": [{}]}}


# -- reading the Java blockstate -------------------------------------------

def test_java_states_read_variants_multipart_and_forge():
    assert java_states(PORTSTONE) == {"facing": {"east", "north", "south", "west"}, "half": {"lower", "upper"}}
    assert java_states(CAULDRON) == {"level": {"0", "1", "2", "3"}}
    # A multipart that only tests lit=true still has a boolean state.
    assert java_states(LAMP) == {"lit": {"true", "false"}, "north": {"side", "up"}, "south": {"side"}}
    assert java_states(FORGE) == {"facing": {"north", "south"}}
    assert java_states({"variants": {"": {"model": "x"}}}) == {}


def test_blockstate_file_matches_the_block_id(tmp_path):
    source = _source(tmp_path, {"portstone": PORTSTONE})
    assert blockstate_file(source, "examplemod:portstone").name == "portstone.json"
    assert blockstate_file(source, "packid:portstone").name == "portstone.json"  # the one there is
    assert blockstate_file(source, "examplemod:other") is None


# -- the check -------------------------------------------------------------

def test_an_integer_enum_for_named_facing_is_flagged(tmp_path):
    """The GLM 5.3 shape: facing=north/east/... written as 0..3."""
    source = _source(tmp_path, {"portstone": PORTSTONE})
    doc = _block("examplemod:portstone", states={"examplemod:facing": [0, 1, 2, 3]},
                 permutations=[_cond("q.block_state('examplemod:facing') == 2")])
    bad = _check(tmp_path, source, doc)
    assert [(b.where, b.value) for b in bad] == [
        ("description.states", "0"), ("description.states", "1"),
        ("description.states", "2"), ("description.states", "3"),
        ("minecraft:block.permutations[0].condition", "2"),
    ]


def test_a_state_or_value_java_does_not_have_is_flagged(tmp_path):
    source = _source(tmp_path, {"portstone": PORTSTONE})
    doc = _block("examplemod:portstone",
                 states={"examplemod:half": ["lower", "upper", "middle"], "examplemod:powered": [False, True]},
                 permutations=[_cond("query.block_state('examplemod:half') == 'top'")])
    bad = [(b.state, b.value) for b in _check(tmp_path, source, doc)]
    assert bad == [("examplemod:half", "middle"), ("examplemod:powered", None), ("examplemod:half", "top")]


def test_java_names_and_values_pass(tmp_path):
    source = _source(tmp_path, {"portstone": PORTSTONE, "cauldron": CAULDRON, "lamp": LAMP})
    portstone = _block("examplemod:portstone",
                       states={"examplemod:facing": ["north", "south", "east", "west"],
                               "examplemod:half": ["lower", "upper"]},
                       permutations=[_cond("q.block_state('examplemod:half') == 'upper' && "
                                           "q.block_state('examplemod:facing') != 'north'")])
    cauldron = _block("examplemod:cauldron", states={"examplemod:level": {"values": {"min": 0, "max": 3}}},
                      permutations=[_cond("q.block_state('examplemod:level') == 3"),
                                    _cond("q.block_state('examplemod:level') > 1")])
    lamp = _block("examplemod:lamp", states={"examplemod:lit": [False, True]},
                  permutations=[_cond("q.block_state('examplemod:lit')"),
                                _cond("q.block_state('examplemod:lit') == true")])
    assert _check(tmp_path, source, portstone, "behavior_pack/blocks/p.json") == []
    assert _check(tmp_path, source, cauldron, "behavior_pack/blocks/c.json") == []
    assert _check(tmp_path, source, lamp, "behavior_pack/blocks/l.json") == []
    # ... but a boolean is not an integer: lit as 0/1 is still invented.
    lamp_ints = _block("examplemod:lamp", states={"examplemod:lit": [0, 1]})
    assert len(_check(tmp_path, source, lamp_ints, "behavior_pack/blocks/l2.json")) == 2


def test_the_deterministic_trait_mapping_is_accepted(tmp_path):
    """What converters/blocks.py emits for facing, axis and connections."""
    source = _source(tmp_path, {"portstone": PORTSTONE})
    doc = _block(
        "examplemod:portstone",
        states={"examplemod:half": ["lower", "upper"]},
        traits={"minecraft:placement_direction": {"enabled_states": ["minecraft:cardinal_direction"]}},
        components={"minecraft:geometry": {"identifier": "geometry.examplemod.portstone", "bone_visibility": {
            "north": "q.block_state('minecraft:cardinal_direction') == 'north'",
            "side": "q.block_state('minecraft:connection_north')",
        }}},
        permutations=[_cond("q.block_state('minecraft:block_face') == 'up' && "
                            "q.block_state('minecraft:some_future_trait') == 7")],
    )
    assert _check(tmp_path, source, doc) == []


def test_an_integer_code_for_a_trait_state_is_flagged(tmp_path):
    source = _source(tmp_path, {"portstone": PORTSTONE})
    doc = _block("examplemod:portstone",
                 permutations=[_cond("q.block_state('minecraft:cardinal_direction') == 2")])
    bad = _check(tmp_path, source, doc)
    assert [(b.state, b.value, b.java) for b in bad] == [("minecraft:cardinal_direction", "2", "Bedrock's trait")]


def test_a_block_without_a_java_blockstate_is_not_checked(tmp_path):
    source = _source(tmp_path, {"portstone": PORTSTONE})
    doc = _block("examplemod:portstone_oak", states={"examplemod:facing": [0, 1]})
    assert _check(tmp_path, source, doc) == []


# -- a renamed state: <prefix>_<javastate> --------------------------------

def test_a_prefixed_rename_with_java_values_passes(tmp_path):
    """The DeepSeek shape: Java's half written as <block>_half with its values."""
    source = _source(tmp_path, {"portstone": PORTSTONE})
    doc = _block("examplemod:portstone",
                 states={"examplemod:portstone_half": ["lower", "upper"],
                         "examplemod:facing": ["north", "south", "east", "west"]},
                 permutations=[_cond("q.block_state('examplemod:portstone_half') == 'upper'"),
                               _cond("q.block_state('examplemod:portstone_half') != 'lower'")])
    assert _check(tmp_path, source, doc) == []
    bare = _block("examplemod:portstone", states={"sharestone_half": ["upper", "lower"]})
    assert _check(tmp_path, source, bare, "behavior_pack/blocks/s.json") == []


def test_a_rename_still_checks_the_values_it_compares(tmp_path):
    source = _source(tmp_path, {"portstone": PORTSTONE})
    doc = _block("examplemod:portstone", states={"examplemod:portstone_half": ["lower", "upper"]},
                 permutations=[_cond("q.block_state('examplemod:portstone_half') == 'top'")])
    assert [(b.state, b.value) for b in _check(tmp_path, source, doc)] == [("examplemod:portstone_half", "top")]


def test_a_rename_with_wrong_values_is_flagged(tmp_path):
    source = _source(tmp_path, {"portstone": PORTSTONE})
    for i, values in enumerate((["lower", "upper", "middle"], ["bottom", "top"], ["lower"])):
        doc = _block("examplemod:portstone", states={"examplemod:portstone_half": values})
        bad = _check(tmp_path, source, doc, f"behavior_pack/blocks/w{i}.json")
        assert [(b.state, b.value, b.alias_of) for b in bad] == [("examplemod:portstone_half", None, ("half",))]


def test_a_rename_with_integer_values_is_flagged(tmp_path):
    source = _source(tmp_path, {"portstone": PORTSTONE, "cauldron": CAULDRON})
    doc = _block("examplemod:portstone", states={"examplemod:portstone_half": [0, 1]},
                 permutations=[_cond("q.block_state('examplemod:portstone_half') == 1")])
    bad = _check(tmp_path, source, doc)
    assert [(b.where, b.state, b.value) for b in bad] == [
        ("description.states", "examplemod:portstone_half", None),
        ("minecraft:block.permutations[0].condition", "examplemod:portstone_half", None),
    ]
    # Even where Java's own values are integers, a rename is not an alias.
    for i, values in enumerate(([0, 1, 2, 3], ["0", "1", "2", "3"], {"values": {"min": 0, "max": 3}})):
        doc = _block("examplemod:cauldron", states={"examplemod:cauldron_level": values})
        bad = _check(tmp_path, source, doc, f"behavior_pack/blocks/c{i}.json")
        assert [(b.state, b.value) for b in bad] == [("examplemod:cauldron_level", None)]


def test_an_ambiguous_rename_is_flagged(tmp_path):
    """``the_top_half`` suffix-matches both ``half`` and ``top_half`` when Java has both."""
    two = {"variants": {f"half={h},top_half={t}": {"model": "examplemod:block/x"}
                        for h in ("lower", "upper") for t in ("lower", "upper")}}
    source = _source(tmp_path, {"twohalf": two})
    doc = _block("examplemod:twohalf", states={"examplemod:the_top_half": ["lower", "upper"]})
    bad = _check(tmp_path, source, doc)
    assert [(b.state, b.value, b.alias_of) for b in bad] == [("examplemod:the_top_half", None, ("half", "top_half"))]


def test_an_invented_name_or_undeclared_rename_is_still_flagged(tmp_path):
    source = _source(tmp_path, {"portstone": PORTSTONE})
    doc = _block("examplemod:portstone",
                 states={"examplemod:portstone_part": ["lower", "upper"], "examplemod:_half": ["lower", "upper"]},
                 permutations=[_cond("q.block_state('examplemod:portstone_half') == 'upper'")])
    bad = _check(tmp_path, source, doc)
    assert [(b.state, b.value, b.alias_of) for b in bad] == [
        ("examplemod:portstone_part", None, ()),
        ("examplemod:_half", None, ()),
        ("examplemod:portstone_half", None, ()),
    ]


def test_validate_explains_a_rejected_rename(tmp_path):
    out = tmp_path / "out"
    convert(BLOCK_DEFS, out)
    box = _TrackingToolBox(BLOCK_DEFS, out, "examplemod")
    box.write_output(STAIRS_PATH, _block(states={"examplemod:stairs_facing": [0, 1, 2, 3]}))
    found = [f for f in box.validate()["findings"] if f["rule"] == "agent.invented_state"]
    assert len(found) == 1
    assert "A renamed 'facing' passes only when it declares exactly facing's values" in found[0]["message"]


def test_validate_names_the_state_and_what_java_has(tmp_path):
    out = tmp_path / "out"
    convert(BLOCK_DEFS, out)
    box = _TrackingToolBox(BLOCK_DEFS, out, "examplemod")
    box.write_output(STAIRS_PATH, _block(states={"examplemod:facing": [0, 1]}))
    report = box.validate()
    found = [f for f in report["findings"] if f["rule"] == "agent.invented_state"]
    assert report["ok"] is False and len(found) == 2
    assert "examplemod:facing = '0'" in found[0]["message"]
    assert "only has east, north" in found[0]["message"]
    assert "no integer codes" in found[0]["message"]


# -- the group -------------------------------------------------------------

def _script_for_stairs(tmp_path, steps):
    probe = convert(BLOCK_DEFS, tmp_path / "probe")
    script = []
    for group in group_residue(probe.unhandled):
        script += steps if group.key == STAIRS else [Message("assistant", "No Bedrock form.")]
    return script


def _run(tmp_path, script):
    result = convert(BLOCK_DEFS, tmp_path / "out", agent=ResidueAgent(FakeLLM(script)))
    return result, {o.key: o for o in result.agent.outcomes}


def test_a_group_that_keeps_an_integer_enum_is_rolled_back(tmp_path):
    script = _script_for_stairs(tmp_path, [
        tool_call("write_output", path=STAIRS_PATH, content=_block(states={"examplemod:facing": [0, 1]})),
        tool_call("validate"),
        Message("assistant", "Converted the stairs."),
    ])
    result, by_key = _run(tmp_path, script)
    stairs = by_key[STAIRS]
    assert stairs.status == "rolled_back"
    assert stairs.invented_states == [
        f"{STAIRS_PATH} description.states: examplemod:facing = 0 (examplemod:steel_stairs)",
        f"{STAIRS_PATH} description.states: examplemod:facing = 1 (examplemod:steel_stairs)",
    ]
    assert stairs.note.startswith("rolled back: block state(s) the Java blockstate does not have:")
    assert stairs.to_dict()["invented_states"] == stairs.invented_states
    assert not (tmp_path / "out" / STAIRS_PATH).exists()
    assert result.report.ok


def test_java_values_resolve(tmp_path):
    script = _script_for_stairs(tmp_path, [
        tool_call("write_output", path=STAIRS_PATH, content=_block(states={"examplemod:facing": [0, 1]})),
        tool_call("validate"),
        tool_call("write_output", path=STAIRS_PATH,
                  content=_block(states={"examplemod:facing": ["north", "east"], "examplemod:half": ["bottom"]})),
        tool_call("validate"),
        Message("assistant", "Wrote the stairs with Java's facing values."),
    ])
    _, by_key = _run(tmp_path, script)
    assert by_key[STAIRS].status == "resolved", by_key[STAIRS].note
    assert by_key[STAIRS].invented_states == []


# -- real mod ----------------------------------------------------------------

@pytest.mark.realmods
def test_waystones_portstone_integer_facing_is_caught(tmp_path):
    """The GLM 5.3 shape from #86's real-mod run, on the real waystones jar."""
    mod = next(m for m in corpus.load() if m.name == "waystones")
    jar = corpus.cached(mod)
    if jar is None:
        pytest.skip("waystones not cached (portkit corpus fetch)")
    source = tmp_path / "src"
    with zipfile.ZipFile(jar) as archive:
        archive.extractall(source)
    ok = _block("waystones:black_portstone",
                states={"waystones:half": ["lower", "upper"]},
                traits={"minecraft:placement_direction": {"enabled_states": ["minecraft:cardinal_direction"]}},
                permutations=[_cond("q.block_state('waystones:half') == 'upper'")])
    assert _check(tmp_path, source, ok) == []
    glm = _block("waystones:black_portstone",
                 states={"waystones:facing": [0, 1, 2, 3], "waystones:half": [0, 1]},
                 permutations=[_cond("q.block_state('waystones:facing') == 0")])
    bad = _check(tmp_path, source, glm)
    assert {b.state for b in bad} == {"waystones:facing", "waystones:half"}
    assert len(bad) == 7
    # The DeepSeek shape: half renamed to <block>_half with Java's own values.
    for block in ("black_portstone", "cyan_portstone", "cyan_sharestone"):
        prefix = block.split("_", 1)[1]
        renamed = _block(f"waystones:{block}",
                         states={f"waystones:{prefix}_half": ["lower", "upper"]},
                         permutations=[_cond(f"q.block_state('waystones:{prefix}_half') == 'upper'")])
        assert _check(tmp_path, source, renamed, f"behavior_pack/blocks/{block}.json") == [], block
