"""Deterministic converters.

Every converter is a pure function: SourceMod -> ConversionResult. No network,
no model, no global state. Register it here and it joins the pipeline and the
fixture harness automatically.
"""
from __future__ import annotations

from ..conditions import LoadContext
from ..model import ConversionResult, SourceMod
from . import armor, blocks, entities, items, lang, loot, loot_modifiers, recipes, sounds, stations, textures
from .station_kit import unresolved_imports


def adapter_data(mod: SourceMod) -> ConversionResult:
    """Every adapter's ``convert`` hook on one namespace, in registry order
    (#245): data only one mod's code reads."""
    from ..adapters import converters

    result = ConversionResult()
    for fn in converters():
        result = result.merge(fn(mod))
    return result


CONVERTERS = [
    textures.convert,
    blocks.convert,
    items.convert,
    recipes.convert,
    loot.convert,
    entities.convert,
    adapter_data,
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


def convert_all(mod: SourceMod, overrides: dict[tuple[str, str], bool | float] | None = None,
                experiments: frozenset = frozenset()) -> ConversionResult:
    """Every converter on one namespace.

    ``overrides`` are the user's mod config settings (``portkit convert
    --config``), keyed by (condition type, flag); they replace the cited
    defaults wherever a load condition or a gated registration reads the flag.
    ``experiments`` are the Bedrock experiments the user's world runs
    (``--experiment``), passed to the converters that emit experimental
    content (``blocks.EXPERIMENTS``).
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
    # Guide books (#182; Citadel's through its library adapter, #245): read
    # once the items have converted (which item opens a book is checked
    # against them), shown by stations' entry.
    from ..adapters import book_readers

    readers = book_readers()
    book_plans: list = [None] * len(readers)
    for fn in CONVERTERS:
        if fn is textures.convert:
            # A station overlay's tinted textures (#178 sharestone runes).
            converted = fn(mod, derived=stations.station_textures(mod))
        elif fn is blocks.convert:
            converted = fn(mod, stations=stations.station_blocks(mod), experiments=experiments)
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
            # Blocks and items ran first: a table is put on its converted
            # block, its block-state conditions read against the block's
            # states (#299).
            converted = fn(mod, context=context, deferred=deferred_loot,
                           station_tables=stations.station_loot(mod), blocks=result.files,
                           java_states=result.java_states, paired=result.paired_halves)
        elif fn is lang.convert:
            # Strings a station runtime shows (the waystone menu, #178) ship
            # under their Java key.
            # and the guide books' page text, per locale.
            book_plans = [r.plan(mod, result.files) for r in readers]
            book_text: dict[str, dict[str, str]] = {}
            for reader, book_plan in zip(readers, book_plans):
                for locale, entries in reader.lang_text(mod, book_plan).items():
                    book_text.setdefault(locale, {}).update(entries)
            converted = fn(mod, runtime_keys=stations.station_lang_keys(mod), book_text=book_text)
        else:
            converted = fn(mod)
        result = result.merge(converted)
        if fn is items.convert:
            # Armor items get minecraft:wearable from the numbers the mod's
            # code gives them (#274) before the recipe converter decides
            # which of them carry minecraft:trimmable_armors (#272).
            result = result.merge(armor.convert(mod, result.files))
    # Loot a NeoForge loot modifier adds to a vanilla block (#280): after the
    # items, since an added drop must name an item the pack ships.
    result = result.merge(loot_modifiers.convert(mod, context, result.files))
    book_entries = []
    for reader, book_plan in zip(readers, book_plans):
        book_result, book_entry = reader.convert(mod, book_plan)
        result = result.merge(book_result)
        if book_entry:
            book_entries.append(book_entry)
    result = result.merge(stations.convert(mod, deferred, result.files, context, loot=deferred_loot,
                                           extra_entries=book_entries or None))
    # Every relative import a shipped script makes must be shipped too (the
    # station kit's shared files, #245): a missing one is a converter bug, and
    # Bedrock would refuse the whole script pack, so fail loudly instead.
    missing = unresolved_imports(result.files)
    if missing:
        raise RuntimeError("shipped scripts import files the pack does not ship: " + "; ".join(missing))
    for note in (context.note(), context.user_note()):
        if note:
            result.notes.append(note)
    return result
