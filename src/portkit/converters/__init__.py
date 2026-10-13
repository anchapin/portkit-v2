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


def convert_all(mod: SourceMod, overrides: dict[tuple[str, str], bool] | None = None) -> ConversionResult:
    """Every converter on one namespace.

    ``overrides`` are the user's mod config settings (``portkit convert
    --config``), keyed by (condition type, flag); they replace the cited
    defaults wherever a load condition or a gated registration reads the flag.
    """
    result = ConversionResult()
    # One load-condition context for the namespace (#183), so the config flags
    # assumed at their defaults add up to a single note.
    context = LoadContext(mod, overrides=overrides)
    for fn in CONVERTERS:
        if fn is items.convert:
            converted = fn(mod, context=context)
        elif fn is recipes.convert:
            # Recipes run after blocks and items so a multi-member tag can be
            # checked against what this conversion actually emits (#160).
            converted = fn(mod, emitted=recipes.emitted_definitions(result.files), context=context)
        elif fn is loot.convert:
            converted = fn(mod, context=context)
        else:
            converted = fn(mod)
        result = result.merge(converted)
    for note in (context.note(), context.user_note()):
        if note:
            result.notes.append(note)
    return result
