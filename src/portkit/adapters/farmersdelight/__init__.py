"""Farmer's Delight (#245): its station runtimes (#177) as an adapter.

The cutting board (:mod:`.cutting_board`, the Farmer's Delight part of
:mod:`portkit.converters.stations`), the cooking pot, the stove, the skillet
and the feasts moved here unchanged from ``portkit/converters/`` (migration
step 8), with their fixed runtimes (``runtime/``, shipped at
``scripts/portkit/`` beside the core station kit they import, pick 6a). The
core reaches them only through the ``station`` hook
(:class:`portkit.adapters.StationHooks`), asked by
:mod:`portkit.converters.stations`, and the recipe converter defers the
station recipe types the hook declares.
"""
from __future__ import annotations

from ...model import ConversionResult
from .. import Adapter, StationHooks
from . import cooking_pot, cutting_board, feasts, skillet, stove
from .cutting_board import CAMPFIRE, COOKING, CUTTING, CUTTING_BOARD_BLOCKS, RECIPE_TYPES, SHARED_TYPES


def station_blocks(mod) -> dict:
    """Blocks of ``mod`` that FD's station runtimes make work, by blockstate
    name: none unless the jar is Farmer's Delight at a version they follow."""
    if cutting_board._unsupported(mod) is not None:
        return {}
    blocks = {}
    for block in (CUTTING_BOARD_BLOCKS[mod.loader], cooking_pot.COOKING_POT_BLOCKS[mod.loader],
                  stove.STOVE_BLOCKS[mod.loader], skillet.SKILLET_BLOCKS[mod.loader],
                  *feasts.feast_blocks(mod).values()):
        blocks[block.name] = block
    return blocks


def convert(mod, deferred, loot, files, context) -> tuple[ConversionResult, str]:
    """Each FD station's table and runtime: the cutting board, the cooking pot,
    the stove (whenever its block converted: vanilla's campfire recipes fill
    its table too), the skillet (the same table) and the feasts (the loot
    tables they asked for), in that order; their entry lines joined."""
    cutting = [d for d in deferred if d[1].get("type") == CUTTING]
    cooking = [d for d in deferred if d[1].get("type") == COOKING]
    campfire = [d for d in deferred if d[1].get("type") == CAMPFIRE]
    result = ConversionResult()
    entries: list[str] = []
    for converted, entry in (cutting_board.convert(mod, cutting, files, context),
                             cooking_pot.convert(mod, cooking, files, context),
                             stove.convert(mod, campfire, files, context),
                             skillet.convert(mod, campfire, files, context),
                             feasts.convert(mod, loot, files, context)):
        result = result.merge(converted)
        if entry:
            entries.append(entry)
    return result, "".join(entries)


ADAPTER = Adapter(
    name="farmersdelight",
    namespaces=frozenset({"farmersdelight"}),
    station=StationHooks(
        blocks=station_blocks,
        loot_names=feasts.loot_names,
        derived_textures=lambda mod: [],
        lang_keys=lambda mod: set(),
        convert=convert,
        recipe_types=RECIPE_TYPES,
        shared_types=SHARED_TYPES,
    ),
)
