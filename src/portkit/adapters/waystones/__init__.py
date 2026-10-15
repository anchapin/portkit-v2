"""Waystones (#245): the waystone station runtime (#178) as an adapter.

The converter (:mod:`portkit.adapters.waystones.convert`), its fixed runtime
(``runtime/waystone.js``, ``runtime/waystone_core.js``, shipped at
``scripts/portkit/`` beside the core station kit they import, pick 6a) and its
cited config defaults (``data/waystones_config_defaults.json``, pick 9a)
moved here unchanged from ``converters/waystones.py``, ``portkit/runtime/``
and ``portkit/data/`` (migration step 7). The core reaches it only through
the ``station`` hook (:class:`portkit.adapters.StationHooks`), asked by
:mod:`portkit.converters.stations`.
"""
from __future__ import annotations

from .. import Adapter, StationHooks
from . import convert


def _convert(mod, deferred, loot, files, context):
    """The ``station`` hook's convert: Waystones' stations read no recipes."""
    return convert.convert(mod, loot, files, context)


ADAPTER = Adapter(
    name="waystones",
    namespaces=frozenset({"waystones"}),
    station=StationHooks(
        blocks=convert.waystone_blocks,
        loot_names=convert.loot_names,
        derived_textures=convert.derived_textures,
        lang_keys=convert.lang_keys,
        convert=_convert,
    ),
)
