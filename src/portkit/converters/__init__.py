"""Deterministic converters.

Every converter is a pure function: SourceMod -> ConversionResult. No network,
no model, no global state. Register it here and it joins the pipeline and the
fixture harness automatically.
"""
from __future__ import annotations

from ..model import ConversionResult, SourceMod
from . import blocks, items, lang, loot, recipes, sounds, textures

CONVERTERS = [
    textures.convert,
    blocks.convert,
    items.convert,
    recipes.convert,
    loot.convert,
    sounds.convert,
    lang.convert,
]


def convert_all(mod: SourceMod) -> ConversionResult:
    result = ConversionResult()
    for fn in CONVERTERS:
        if fn is recipes.convert:
            # Recipes run after blocks and items so a multi-member tag can be
            # checked against what this conversion actually emits (#160).
            converted = fn(mod, emitted=recipes.emitted_definitions(result.files))
        else:
            converted = fn(mod)
        result = result.merge(converted)
    return result
