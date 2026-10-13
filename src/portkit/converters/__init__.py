"""Deterministic converters.

Every converter is a pure function: SourceMod -> ConversionResult. No network,
no model, no global state. Register it here and it joins the pipeline and the
fixture harness automatically.
"""
from __future__ import annotations

from ..conditions import LoadContext
from ..model import ConversionResult, SourceMod
from . import blocks, items, lang, loot, recipes, sounds, stations, textures

CONVERTERS = [
    textures.convert,
    blocks.convert,
    items.convert,
    recipes.convert,
    loot.convert,
    sounds.convert,
    lang.convert,
]


def emitted_blocks(files: dict) -> set[str]:
    """Identifiers of the blocks among ``files``."""
    ids = set()
    for path, body in files.items():
        if path.startswith("blocks/") and isinstance(body, dict):
            ident = ((body.get("minecraft:block") or {}).get("description") or {}).get("identifier")
            if isinstance(ident, str):
                ids.add(ident)
    return ids


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
    # Station recipes (#177) pass the recipe converter's load-condition gate,
    # then wait for every other converter: the data table checks the block,
    # the items and the sounds it names against what the namespace emitted.
    deferred: list = []
    deferred_loot: list = []
    for fn in CONVERTERS:
        if fn is blocks.convert:
            converted = fn(mod, stations=stations.station_blocks(mod))
        elif fn is items.convert:
            # Blocks ran first: an item named like a block that did not convert
            # is the only form of that item (a crop's seed, #177 rice).
            converted = fn(mod, context=context, emitted_blocks=emitted_blocks(result.files))
        elif fn is recipes.convert:
            # Recipes run after blocks and items so a multi-member tag can be
            # checked against what this conversion actually emits (#160).
            converted = fn(mod, emitted=recipes.emitted_definitions(result.files), context=context,
                           deferred=deferred)
        elif fn is loot.convert:
            # A feast's loot table is read per serving count by its station
            # (#177 feasts), so it waits like a station recipe.
            converted = fn(mod, context=context, deferred=deferred_loot,
                           station_tables=stations.station_loot(mod))
        else:
            converted = fn(mod)
        result = result.merge(converted)
    result = result.merge(stations.convert(mod, deferred, result.files, context, loot=deferred_loot))
    for note in (context.note(), context.user_note()):
        if note:
            result.notes.append(note)
    return result
