"""The per-mod recipe residue tables live in their mods' adapters (#245 step 4).

Moved from ``converters/recipes.py`` unchanged: every type keeps its residue
kind and reason (the 2026-10-15 decisions entries for #172-#175 and #180 say
why each kind exists). These checks pin where each table went and that the
core's lookups still answer from them.
"""
import pytest

from portkit import adapters
from portkit.adapters import bclib, betterend, create, mekanism, mythicmetals, silentgear, supplementaries, tconstruct
from portkit.converters import recipes

KINDS = (recipes.FLUID_RECIPE, recipes.MODULAR_TOOL, recipes.MACHINE_RECIPE, recipes.CODE_RECIPE)


def _kinds(adapter):
    out = {}
    for java_type, (kind, _) in adapter.recipe_reasons.items():
        out.setdefault(kind, set()).add(java_type)
    return out


def test_where_each_table_went():
    counts = {a.name: {k: len(v) for k, v in _kinds(a).items()}
              for a in (tconstruct.ADAPTER, silentgear.ADAPTER, create.ADAPTER, mekanism.ADAPTER, betterend.ADAPTER,
                        bclib.ADAPTER, mythicmetals.ADAPTER, supplementaries.ADAPTER)}
    assert counts == {
        "tconstruct": {"fluid_recipe": 30, "modular_tool": 39, "code_recipe": 2},
        "silentgear": {"modular_tool": 9, "code_recipe": 1},
        "create": {"fluid_recipe": 2, "machine_recipe": 11, "code_recipe": 2},
        "mekanism": {"machine_recipe": 26, "code_recipe": 1},
        "betterend": {"code_recipe": 1},
        "bclib": {"code_recipe": 2},
        "mythicmetals": {"code_recipe": 3},
        "supplementaries": {"code_recipe": 1},
    }
    assert bclib.ADAPTER.library and not betterend.ADAPTER.library


def test_registered_and_disjoint():
    for a in (tconstruct, silentgear, create, mekanism, betterend, bclib, mythicmetals, supplementaries):
        assert a.ADAPTER in adapters.ADAPTERS
    assert adapters.check() == []


@pytest.mark.parametrize("kind, lookup", [
    (recipes.FLUID_RECIPE, recipes.fluid_recipe_reason),
    (recipes.MODULAR_TOOL, recipes.modular_tool_reason),
    (recipes.MACHINE_RECIPE, recipes.machine_recipe_reason),
])
def test_core_lookups_answer_from_the_adapters(kind, lookup):
    table = adapters.recipe_reasons(kind)
    assert table and all(lookup(t) == r for t, r in table.items())
    others = set().union(*(adapters.recipe_reasons(k) for k in KINDS if k != kind))
    assert all(lookup(t) is None for t in others)


def test_code_recipe_lookup_answers_from_the_adapters():
    for java_type, reason in adapters.recipe_reasons(recipes.CODE_RECIPE).items():
        assert recipes.code_recipe_reason(java_type, {"type": java_type, "x": 1}) == reason
