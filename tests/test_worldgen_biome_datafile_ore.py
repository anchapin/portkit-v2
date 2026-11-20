"""#281 pick C.1 (first slice, ore from data files): a Java biome file lists
its placed features per generation step; an ore named only there is decided
by the features converter. A Java biome *id* has no Bedrock biome map (pick
A.6a), so the ore is explained ``worldgen_feature`` residue naming the biome,
and the biome/placed/configured files are consumed, not ``unowned``.
Offline, ``examplemod`` only (fixture: fixtures/worldgen_biome_mod/input).
"""
import json
from pathlib import Path

from portkit.converters import features

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/worldgen_biome_mod/input"
BLOCKS = {"blocks/deep_ore.json": {"format_version": "1.20.20",
                                   "minecraft:block": {"description": {"identifier": "examplemod:deep_ore"}}}}

BIOME_REL = "data/examplemod/worldgen/biome/cave.json"
PLACED_REL = "data/examplemod/worldgen/placed_feature/deep_ore.json"
CONFIGURED_REL = "data/examplemod/worldgen/configured_feature/deep_ore.json"


def _convert_fixture():
    return features.convert(FIXTURE, dict(BLOCKS), {"examplemod"})


def test_biome_file_ore_is_explained_residue_not_unowned():
    out = _convert_fixture()
    assert out.files == {}
    kinds = {(u.source, u.kind) for u in out.unhandled}
    assert (PLACED_REL, features.KIND) in kinds
    assert (BIOME_REL, features.KIND) in kinds
    placed = next(u for u in out.unhandled if u.source == PLACED_REL)
    assert "examplemod:cave" in placed.reason
    assert "pick A.6a" in placed.reason
    biome = next(u for u in out.unhandled if u.source == BIOME_REL)
    assert "examplemod:cave" in biome.reason


def test_biome_path_consumes_the_worldgen_files_it_reads():
    out = _convert_fixture()
    assert {BIOME_REL, PLACED_REL, CONFIGURED_REL} <= out.consumed


def test_vanilla_features_listed_by_a_biome_are_left_alone(tmp_path):
    # The fixture biome also lists minecraft:ore_diamond at the ore step:
    # vanilla features are not the jar's, so nothing is filed for them.
    out = _convert_fixture()
    assert not any("ore_diamond" in u.source for u in out.unhandled)


def test_a_biome_with_no_own_features_is_not_claimed(tmp_path):
    root = tmp_path
    biome = root / "data/examplemod/worldgen/biome"
    biome.mkdir(parents=True)
    (biome / "plain.json").write_text(json.dumps({"features": [[], [], [], [], [], [], ["minecraft:ore_iron"]]}))
    out = features.convert(root, dict(BLOCKS), {"examplemod"})
    assert out.unhandled == []
    assert out.consumed == set()
