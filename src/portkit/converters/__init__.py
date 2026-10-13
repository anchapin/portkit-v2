"""Deterministic converters.

Every converter is a pure function: SourceMod -> ConversionResult. No network,
no model, no global state. Register it here and it joins the pipeline and the
fixture harness automatically.
"""
from __future__ import annotations

from ..conditions import LoadContext
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
    # One load-condition context for the namespace (#183), so the config flags
    # assumed at their defaults add up to a single note.
    context = LoadContext(mod)
    for fn in CONVERTERS:
        if fn is recipes.convert:
            # Recipes run after blocks and items so a multi-member tag can be
            # checked against what this conversion actually emits (#160).
            converted = fn(mod, emitted=recipes.emitted_definitions(result.files), context=context)
        elif fn is loot.convert:
            converted = fn(mod, context=context)
        else:
            converted = fn(mod)
        result = result.merge(converted)
    note = context.note()
    if note:
        result.notes.append(note)
    return result
