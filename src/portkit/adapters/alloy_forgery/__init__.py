"""Alloy Forgery (#171, #245): its forge recipes and the forge data other mods ship.

Alloy Forgery is a separate mod that recipe mods (in the corpus, Mythic Metals
0.24.6) add forging recipes, forges and fuels to as data. The logic is
:mod:`.forge`, moved unchanged from ``converters/alloy_forge.py`` (#245
migration step 3): ``alloy_forgery:forging`` recipes are ``machine_recipe``
residue whose reason reads the recipe and names the forges the recipe's own
namespace defines, and the forge data is ``machine_data`` residue
(docs/decisions.md, 2026-10-15).
"""
from __future__ import annotations

from ...converters.recipes import MACHINE_RECIPE
from ...model import SourceMod
from .. import Adapter
from .forge import FORGING, MACHINE_DATA, convert, forge_names, forging_reason

__all__ = ["ADAPTER", "FORGING", "MACHINE_DATA", "convert", "forge_names", "forging_reason", "recipe_reason"]


def recipe_reason(mod: SourceMod, recipe: dict) -> str:
    """The ``machine_recipe`` reason for one forging recipe of ``mod``."""
    return forging_reason(recipe, forge_names(mod))


ADAPTER = Adapter(
    name="alloy_forgery",
    namespaces=frozenset({"alloy_forgery"}),
    recipe_reasons={FORGING: (MACHINE_RECIPE, recipe_reason)},
    convert=convert,
)
