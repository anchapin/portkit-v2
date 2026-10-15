"""Mekanism (#245): its load-condition type and its recipe types.

Its machine recipes and ``mek_data`` crafting stay residue for the reasons in
:mod:`.recipes`. Its load-condition type:

``mekanism:mod_version_loaded`` (Mekanism's ModVersionLoadedCondition: the
mod ``modid`` is loaded at ``version`` or newer). An absent mod decides it
false, as ``mod_loaded`` does; on a loaded mod it stays undecidable, since
Maven version ordering isn't reimplemented here. Moved here unchanged from
``conditions.py`` (#245 migration step 2).
"""
from __future__ import annotations

from ...conditions import LoadContext, Verdict
from .. import Adapter
from .recipes import RECIPE_REASONS


def mod_version_loaded(context: LoadContext, kind: str, cond: dict) -> Verdict:
    """``mekanism:mod_version_loaded``."""
    loaded = context.loaded(cond.get("modid"))
    if loaded is False:
        return Verdict(False, f"{kind} {cond.get('modid')}", absent=[cond.get("modid")])
    # mekanism ModVersionLoadedCondition: a loaded mod at least as new;
    # Maven version ordering isn't reimplemented here.
    return Verdict(None, f"{kind} {cond.get('modid')} >= {cond.get('version')} on a loaded mod")


ADAPTER = Adapter(
    name="mekanism",
    namespaces=frozenset({"mekanism"}),
    conditions={"mekanism:mod_version_loaded": mod_version_loaded},
    recipe_reasons=RECIPE_REASONS,
)
