"""Waystones' village pools (code_worldgen) and Unbreakables rules (other_mod_data):
claimed only when the jar's classes hold what the reasons cite (#277, PR #316 picks 2a 3a).

Offline: a Waystones-shaped data tree with fake class files carrying the
strings read from waystones-neoforge-1.21.1-21.1.46.jar.
"""
import json
from pathlib import Path

from portkit.adapters.waystones import ADAPTER
from portkit.adapters.waystones import worldgen
from portkit.model import SourceMod

_PKG = "net/blay09/mods/waystones"


def _write(root: Path, rel: str, body) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body))


class _CF:
    def __init__(self, strings):
        self.pool = [None] + [("utf8", s) for s in strings]
        self._strings = [None] + list(strings)
        self.super_name = "java/lang/Object"

    def constant(self, i):
        return self._strings[i]


class _Classes:
    def __init__(self, classes):
        self._c = classes

    def names(self):
        return sorted(self._c)

    def get(self, name, remap=True):
        return self._c.get(name)


_JAR = {
    f"{_PKG}/mixin/JigsawPlacementPlacerMixin": _CF(
        ["forceWaystonePool", "/houses", "/waystones", "spawnInVillages", "FREQUENT"]),
    f"{_PKG}/compat/UnbreakablesIntegration": _CF(["net/blay09/mods/unbreakables/api/UnbreakablesAPI"]),
    f"{_PKG}/Waystones": _CF(["unbreakables", "net.blay09.mods.waystones.compat.UnbreakablesIntegration",
                               "initializeIfLoaded"]),
}


def _tree(root: Path) -> None:
    _write(root, "data/waystones/worldgen/template_pool/village/plains/waystones.json",
           {"elements": [{"element": {"element_type": "minecraft:legacy_single_pool_element",
                                      "location": "waystones:village/common/waystone"}, "weight": 1}],
            "fallback": "minecraft:village/plains/houses"})
    _write(root, "data/waystones/worldgen/template_pool/other.json",
           {"elements": [], "fallback": "minecraft:empty"})
    _write(root, "data/waystones/unbreakables/generated_waystones.json",
           {"rules": ["[is_tag(waystones:waystones)] refuse($chat.waystones.cannot_break_waystone)"]})


def test_the_adapter_registers_the_hook():
    assert ADAPTER.convert is worldgen.convert


def test_village_pools_and_unbreakables_rules_are_claimed_with_the_cited_classes(tmp_path):
    _tree(tmp_path)
    result = worldgen.convert(SourceMod(root=tmp_path, namespace="waystones", classes=_Classes(_JAR)))
    got = {u.source: u for u in result.unhandled}
    pool = got["data/waystones/worldgen/template_pool/village/plains/waystones.json"]
    assert pool.kind == "code_worldgen"
    assert "JigsawPlacementPlacerMixin" in pool.reason and "minecraft:village/plains/houses" in pool.reason
    rules = got["data/waystones/unbreakables/generated_waystones.json"]
    assert rules.kind == "other_mod_data" and "UnbreakablesIntegration" in rules.reason
    # A pool that isn't a village waystone pool is left for the core.
    assert "data/waystones/worldgen/template_pool/other.json" not in got
    assert result.consumed == set(got)


def test_nothing_is_claimed_without_the_classes_the_reasons_cite(tmp_path):
    _tree(tmp_path)
    for classes in (None, _Classes({})):
        result = worldgen.convert(SourceMod(root=tmp_path, namespace="waystones", classes=classes))
        assert not result.unhandled and not result.consumed
    partial = dict(_JAR)
    partial[f"{_PKG}/mixin/JigsawPlacementPlacerMixin"] = _CF(["/houses"])
    result = worldgen.convert(SourceMod(root=tmp_path, namespace="waystones", classes=_Classes(partial)))
    assert [u.kind for u in result.unhandled] == ["other_mod_data"]


def test_another_namespace_is_left_alone(tmp_path):
    _tree(tmp_path)
    assert not worldgen.convert(SourceMod(root=tmp_path, namespace="examplemod",
                                          classes=_Classes(_JAR))).unhandled
