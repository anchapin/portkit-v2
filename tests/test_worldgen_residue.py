"""#277 (PR #316 picks 1a 2a 3a): leftover worldgen and other mods' data the jar explains.

``code_worldgen``: a worldgen file typed with the jar's own namespace (feature,
placement modifier, pool element) is the mod's Java code. ``other_mod_data``: a
non-vanilla data folder whose every file is typed or targeted at another mod's
namespace. A structure template named only by such residue goes with it.
Everything else stays ``unowned``. Offline, ``examplemod`` only.
"""
import json
from pathlib import Path

from portkit import worldgen
from portkit.agent.residue import SKIP_KINDS
from portkit.model import Unhandled
from portkit.pipeline import unowned


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(body, bytes):
        path.write_bytes(body)
    else:
        path.write_text(json.dumps(body))


class _CF:
    def __init__(self, strings, super_name="java/lang/Object"):
        self.pool = [None] + [("utf8", s) for s in strings]
        self._strings = [None] + list(strings)
        self.super_name = super_name

    def constant(self, i):
        return self._strings[i]


class _Classes:
    def __init__(self, classes):
        self._c = classes

    def names(self):
        return sorted(self._c)

    def get(self, name, remap=True):
        return self._c.get(name)


def _refine(root, consumed=frozenset(), extra=(), classes=None):
    residue = list(extra) + unowned(root, set(consumed))
    return worldgen.refine(residue, root, set(consumed), {"examplemod"}, classes)


def _kinds(result):
    return {(u.source, u.kind) for u in result}


def test_both_kinds_are_explained():
    assert {"code_worldgen", "other_mod_data"} <= set(SKIP_KINDS)


def test_a_feature_typed_with_the_mods_namespace_is_code_worldgen(tmp_path):
    _write(tmp_path, "data/examplemod/worldgen/configured_feature/rock.json",
           {"type": "examplemod:rock", "config": {}})
    _write(tmp_path, "data/examplemod/worldgen/configured_feature/ore.json",
           {"type": "minecraft:ore", "config": {"size": 4, "targets": []}})
    classes = _Classes({
        "com/example/RockFeature": _CF(["com/example/RockFeature"],
                                       "net/minecraft/world/level/levelgen/feature/Feature"),
        "com/example/Blocks": _CF(["rock"]),
        "com/example/WorldGen": _CF(["rock", "com/example/RockFeature"]),
    })
    out = _refine(tmp_path, classes=classes)
    rock = next(u for u in out if u.source.endswith("rock.json"))
    assert rock.kind == "code_worldgen"
    assert "`examplemod:rock`" in rock.reason
    # The class naming the type's path and the jar's Feature subclass is cited first.
    cited = rock.reason.split("naming `rock`: ", 1)[1]
    assert cited.startswith("com/example/WorldGen (names com/example/RockFeature, a subclass of "
                            "net/minecraft/world/level/levelgen/feature/Feature)")
    # minecraft: types stay a #281 gap.
    assert ("data/examplemod/worldgen/", "unowned") in _kinds(out)
    left = next(u for u in out if u.kind == "unowned")
    assert left.count == 1


def test_placed_features_need_a_placement_modifier_of_their_own(tmp_path):
    _write(tmp_path, "data/examplemod/worldgen/placed_feature/rock.json",
           {"feature": "examplemod:rock", "placement": [{"type": "examplemod:spaced"}]})
    _write(tmp_path, "data/examplemod/worldgen/placed_feature/plain.json",
           {"feature": "examplemod:rock", "placement": [{"type": "minecraft:in_square"}]})
    out = _refine(tmp_path)
    kinds = _kinds(out)
    assert ("data/examplemod/worldgen/placed_feature/rock.json", "code_worldgen") in kinds
    assert ("data/examplemod/worldgen/", "unowned") in kinds
    rock = next(u for u in out if u.kind == "code_worldgen")
    assert "`examplemod:spaced`" in rock.reason and "the source has no classes" in rock.reason


def test_a_pool_with_an_element_type_of_its_own_is_code_worldgen(tmp_path):
    _write(tmp_path, "data/examplemod/worldgen/template_pool/camp/a.json",
           {"fallback": "minecraft:empty",
            "elements": [{"weight": 1, "element": {"element_type": "examplemod:camp_piece"}}]})
    _write(tmp_path, "data/examplemod/worldgen/template_pool/camp/b.json",
           {"fallback": "minecraft:empty",
            "elements": [{"weight": 1, "element": {"element_type": "minecraft:single_pool_element",
                                                   "location": "examplemod:camp/b"}}]})
    kinds = _kinds(_refine(tmp_path))
    assert ("data/examplemod/worldgen/template_pool/camp/a.json", "code_worldgen") in kinds
    assert ("data/examplemod/worldgen/", "unowned") in kinds


def test_other_mods_data_is_explained_by_its_foreign_namespace(tmp_path):
    _write(tmp_path, "data/examplemod/othermod_additions/a.json",
           {"target_pool": "othermod:villages/houses", "elements": []})
    _write(tmp_path, "data/examplemod/othermod_additions/b.json",
           {"type": "othermod:add_things", "target_structure": "othermod:village"})
    classes = _Classes({"com/example/OtherModCompat": _CF(["othermod"])})
    out = _refine(tmp_path, classes=classes)
    entry = next(u for u in out if u.kind == "other_mod_data")
    assert entry.source == "data/examplemod/othermod_additions/" and entry.count == 2
    assert "`othermod`" in entry.reason and "com/example/OtherModCompat" in entry.reason
    assert not [u for u in out if u.kind == "unowned"]


def test_own_shared_or_vanilla_folders_are_not_other_mod_data(tmp_path):
    # The mod's own reloader data (typed with its namespace), a file that
    # names no foreign namespace, and a loader folder all stay unowned.
    _write(tmp_path, "data/examplemod/machines/a.json", {"type": "examplemod:press"})
    _write(tmp_path, "data/examplemod/mixed/a.json", {"type": "othermod:x"})
    _write(tmp_path, "data/examplemod/mixed/b.json", {"rules": ["no namespace here"]})
    _write(tmp_path, "data/examplemod/shared/a.json", {"type": "c:thing", "target_x": "neoforge:y"})
    _write(tmp_path, "data/examplemod/loot_modifiers/a.json", {"type": "othermod:modifier"})
    out = _refine(tmp_path)
    assert not [u for u in out if u.kind in worldgen.KINDS]
    assert {u.source for u in out} == {"data/examplemod/machines/", "data/examplemod/mixed/",
                                       "data/examplemod/shared/", "data/examplemod/loot_modifiers/"}


def test_a_structure_goes_with_the_explained_residue_that_names_it(tmp_path):
    nbt = b"\x1f\x8b not read"
    # Named by an adapter's code_worldgen pool (filed per file) and other mods' data.
    _write(tmp_path, "data/examplemod/worldgen/template_pool/village/plains/extra.json",
           {"elements": [{"element": {"element_type": "minecraft:legacy_single_pool_element",
                                      "location": "examplemod:village/well"}}],
            "fallback": "minecraft:village/plains/houses"})
    _write(tmp_path, "data/examplemod/othermod_additions/a.json",
           {"target_pool": "othermod:houses", "elements": [{"location": "examplemod:village/well"},
                                                            {"location": "examplemod:village/raft"}]})
    _write(tmp_path, "data/examplemod/structure/village/well.nbt", nbt)
    _write(tmp_path, "data/examplemod/structure/village/raft.nbt", nbt)
    # Named by a file that is still unowned, and named by nothing.
    _write(tmp_path, "data/examplemod/worldgen/template_pool/plain.json",
           {"elements": [{"element": {"element_type": "minecraft:single_pool_element",
                                      "location": "examplemod:village/hut"}}], "fallback": "minecraft:empty"})
    _write(tmp_path, "data/examplemod/structure/village/hut.nbt", nbt)
    _write(tmp_path, "data/examplemod/structure/village/lonely.nbt", nbt)
    pool = "data/examplemod/worldgen/template_pool/village/plains/extra.json"
    adapter = Unhandled(pool, "code_worldgen", "the mod's code places it")
    classes = _Classes({"com/example/WorldGen": _CF(["village/well"])})
    out = _refine(tmp_path, consumed={pool}, extra=[adapter], classes=classes)
    by_source = {u.source: u for u in out}
    well = by_source["data/examplemod/structure/village/well.nbt"]
    assert well.kind == "code_worldgen"
    # The code_worldgen user is listed first, then the other mod's file; the class is cited.
    assert well.reason.index("plains/extra.json (code_worldgen)") < well.reason.index("othermod_additions")
    assert "com/example/WorldGen" in well.reason
    assert by_source["data/examplemod/structure/village/raft.nbt"].kind == "other_mod_data"
    left = by_source["data/examplemod/structure/"]
    assert left.kind == "unowned" and left.count == 2
    assert by_source[pool] is adapter


def test_nothing_to_do_returns_the_residue_unchanged(tmp_path):
    residue = [Unhandled("assets/examplemod/x/", "unowned", "1 file(s) no converter claims yet")]
    assert worldgen.refine(residue, tmp_path, set(), {"examplemod"}) == residue


def test_groups_other_passes_refiled_keep_their_counts(tmp_path):
    # An earlier pass (data tags) re-filed part of a group without claiming
    # the files: this pass neither reads that group nor recounts it.
    _write(tmp_path, "data/c/tags/item/a.json", {"values": []})
    _write(tmp_path, "data/c/tags/item/b.json", {"values": []})
    _write(tmp_path, "data/examplemod/worldgen/configured_feature/rock.json", {"type": "examplemod:rock"})
    _write(tmp_path, "data/examplemod/worldgen/configured_feature/ore.json", {"type": "minecraft:ore"})
    residue = [Unhandled("data/c/tags/", "unowned", "1 file(s) no converter claims yet", count=1),
               Unhandled("data/c/tags/item/", "tag_unread", "read by nothing", count=1),
               Unhandled("data/examplemod/worldgen/", "unowned", "2 file(s) no converter claims yet", count=2)]
    out = worldgen.refine(residue, tmp_path, set(), {"examplemod"})
    by = {(u.source, u.kind): u.count for u in out}
    assert by[("data/c/tags/", "unowned")] == 1
    assert by[("data/examplemod/worldgen/", "unowned")] == 1
    assert sum(u.count for u in out) == sum(u.count for u in residue)
