"""The adapter registry (#245): per-mod code reaches the core only through it.

``src/portkit/adapters`` holds an explicit, ordered tuple of
:class:`portkit.adapters.Adapter` (Alex's picks 1-4, 2026-10-15). These tests
pin the registry's rules and that each core seam asks it: load conditions,
recipe residue reasons and per-mod data converters. A made-up ``examplemod``
adapter is patched in; the real adapters have tests of their own under
``tests/adapters/<mod>/``.
"""
import json

import pytest

from portkit import adapters
from portkit.adapters import Adapter
from portkit.conditions import LoadContext, Verdict
from portkit.converters import CONVERTERS, adapter_data, convert_all, recipes
from portkit.model import ConversionResult, SourceMod, Unhandled


def test_registry_is_an_ordered_tuple_without_conflicts():
    assert isinstance(adapters.ADAPTERS, tuple)
    assert all(isinstance(a, Adapter) for a in adapters.ADAPTERS)
    assert adapters.check() == []


def test_check_refuses_duplicates_and_claims_outside_the_namespaces():
    a = Adapter("a", frozenset({"a"}), recipe_reasons={"a:x": ("code_recipe", "r")})
    assert adapters.check((a, a)) == [
        "adapter name 'a' registered twice",
        "recipe type 'a:x' claimed by 'a' and 'a'",
    ]
    b = Adapter("b", frozenset({"b"}), conditions={"a:cond": lambda c, k, d: None})
    assert adapters.check((b,)) == ["'b' claims condition 'a:cond' outside its namespaces"]


def test_hooks_default_to_empty_and_the_adapter_is_frozen():
    a = Adapter("a")
    assert dict(a.conditions) == {} and dict(a.recipe_reasons) == {} and a.convert is None
    assert not a.library
    with pytest.raises(AttributeError):
        a.name = "b"


def test_adapter_data_runs_where_per_mod_data_converters_ran():
    # Right after the entity converter, where alloy_forge.convert ran before
    # it moved into its adapter (#245 step 3).
    names = [fn.__name__ if fn is adapter_data else fn.__module__.rsplit(".", 1)[-1] for fn in CONVERTERS]
    assert names.index("adapter_data") == names.index("entities") + 1


def _mod(tmp_path, recipes_=None):
    for name, body in (recipes_ or {}).items():
        path = tmp_path / "data" / "examplemod" / "recipes" / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body))
    (tmp_path / "data" / "examplemod").mkdir(parents=True, exist_ok=True)
    return SourceMod(root=tmp_path, namespace="examplemod", loader="forge",
                     mods={"examplemod": "1.0"}, requires=frozenset())


def test_a_condition_type_an_adapter_registers_is_evaluated_by_it(tmp_path, monkeypatch):
    seen = []

    def handler(context, kind, cond):
        seen.append((kind, cond.get("value")))
        return Verdict(False, f"{kind}: no")

    cond = {"type": "examplemod:check", "value": "v"}
    before = LoadContext(_mod(tmp_path)).evaluate([cond])
    assert before.passes is None  # an uncited mod flag: unknown
    monkeypatch.setattr(adapters, "ADAPTERS", (
        Adapter("examplemod", frozenset({"examplemod"}), conditions={"examplemod:check": handler}),))
    verdict = LoadContext(_mod(tmp_path)).evaluate([cond])
    assert (verdict.passes, verdict.why) == (False, "examplemod:check: no")
    assert seen == [("examplemod:check", "v")]


def test_builtin_condition_types_never_reach_an_adapter(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "ADAPTERS", (
        Adapter("forge", frozenset({"forge"}), conditions={"forge:true": lambda c, k, d: Verdict(False, "x")}),))
    assert LoadContext(_mod(tmp_path)).evaluate([{"type": "forge:true"}]).passes is True


def test_recipe_reasons_fixed_and_computed(tmp_path, monkeypatch):
    def computed(mod, recipe):
        return f"{mod.namespace} presses for {recipe['time']} ticks"

    monkeypatch.setattr(adapters, "ADAPTERS", (Adapter("examplemod", frozenset({"examplemod"}), recipe_reasons={
        "examplemod:grind": ("machine_recipe", "a grinder recipe"),
        "examplemod:press": ("machine_recipe", computed),
    }),))
    mod = _mod(tmp_path, {
        "g": {"type": "examplemod:grind", "ingredient": {"item": "minecraft:stone"}},
        "p": {"type": "examplemod:press", "time": 40},
        "o": {"type": "examplemod:other", "ingredient": {"item": "minecraft:stone"}},
    })
    found = {u.source.rsplit("/", 1)[-1]: (u.kind, u.reason) for u in recipes.convert(mod).unhandled}
    assert found == {
        "g.json": ("machine_recipe", "a grinder recipe"),
        "p.json": ("machine_recipe", "examplemod presses for 40 ticks"),
        "o.json": ("recipe", "unsupported recipe type 'examplemod:other'"),
    }
    assert adapters.recipe_reasons("machine_recipe") == {"examplemod:grind": "a grinder recipe"}
    assert adapters.recipe_reason(None, {}, mod) is None


def test_an_adapters_convert_hook_runs_in_convert_all(tmp_path, monkeypatch):
    def claim(mod):
        result = ConversionResult()
        result.unhandled.append(Unhandled("data/examplemod/machine/x.json", "machine_data", "read by code"))
        return result

    monkeypatch.setattr(adapters, "ADAPTERS", (Adapter("examplemod", frozenset({"examplemod"}), convert=claim),))
    result = convert_all(_mod(tmp_path))
    assert ("data/examplemod/machine/x.json", "machine_data") in {(u.source, u.kind) for u in result.unhandled}
