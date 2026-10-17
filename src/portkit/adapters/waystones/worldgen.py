"""Waystones' village pools and Unbreakables rules (#277, PR #316 picks 2a and 3a).

Two kinds of Waystones data no data file of the jar wires up, and that only its
code (or another mod) reads. Each claim is checked against the jar's classes
(#87): when the class or the strings below are not in the jar, the file stays
``unowned`` for the core to report.

* ``worldgen/template_pool/village/<biome>/waystones.json``: ``code_worldgen``.
  Nothing in the data names these pools; their elements are
  ``minecraft:legacy_single_pool_element`` and their fallback is the vanilla
  ``minecraft:village/<biome>/houses``. The mixin
  ``mixin/JigsawPlacementPlacerMixin`` (``forceWaystonePool``) takes a pool path
  ending in ``/houses``, replaces it with ``/waystones`` under the ``waystones``
  namespace and places that pool while a village generates, reading the config
  ``worldGen.spawnInVillages`` (``FREQUENT``). The structure templates the pools
  name go with them through the core rule (:mod:`portkit.worldgen`).
* ``unbreakables/generated_waystones.json``: ``other_mod_data``. A rule for the
  Unbreakables mod; ``compat/UnbreakablesIntegration`` registers its conditions
  through ``net/blay09/mods/unbreakables/api/UnbreakablesAPI``, and
  ``Waystones#initialize`` loads that class only if ``unbreakables`` is loaded
  (``initializeIfLoaded``). The file names no foreign namespace, so the core
  rule can't see it.

Verified against waystones-neoforge-1.21.1-21.1.46.jar and
waystones-fabric-1.21.1-21.1.46.jar (same classes and strings in both).
"""
from __future__ import annotations

import json
import re

from ...model import ConversionResult, SourceMod, Unhandled
from ...worldgen import CODE_WORLDGEN, OTHER_MOD_DATA

_PKG = "net/blay09/mods/waystones"
_MIXIN = f"{_PKG}/mixin/JigsawPlacementPlacerMixin"
_MIXIN_STRINGS = ("forceWaystonePool", "/houses", "/waystones", "spawnInVillages", "FREQUENT")
_COMPAT = f"{_PKG}/compat/UnbreakablesIntegration"
_UNBREAKABLES_API = "net/blay09/mods/unbreakables/api/UnbreakablesAPI"
_MAIN = f"{_PKG}/Waystones"
_MAIN_STRINGS = ("unbreakables", "net.blay09.mods.waystones.compat.UnbreakablesIntegration", "initializeIfLoaded")

_POOL = re.compile(r"^village/([a-z0-9_]+)/waystones\.json$")


def _strings(classes, name: str) -> set[str] | None:
    cf = classes.get(name) if classes is not None else None
    if cf is None:
        return None
    out: set[str] = set()
    for i, entry in enumerate(cf.pool):
        if not isinstance(entry, tuple) or not entry:
            continue
        try:
            value = cf.constant(i)
        except Exception:  # noqa: BLE001 - an odd pool entry is skipped
            continue
        if isinstance(value, str):
            out.add(value)
    return out


def _read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def convert(mod: SourceMod) -> ConversionResult:
    result = ConversionResult()
    if mod.namespace != "waystones" or not mod.data.is_dir():
        return result
    mixin = _strings(mod.classes, _MIXIN)
    pools = mod.data / "worldgen" / "template_pool"
    if mixin is not None and all(s in mixin for s in _MIXIN_STRINGS) and pools.is_dir():
        for path in sorted(pools.rglob("*.json")):
            m = _POOL.match(path.relative_to(pools).as_posix())
            doc = _read(path)
            if not m or not isinstance(doc, dict):
                continue
            biome = m.group(1)
            if doc.get("fallback") != f"minecraft:village/{biome}/houses":
                continue
            rel = result.claim(mod, path)
            result.unhandled.append(Unhandled(rel, CODE_WORLDGEN, (
                f"a village waystone pool no data file of the jar names: the mod's mixin {_MIXIN} "
                f"(forceWaystonePool) turns a village pool path ending in `/houses` into `/waystones` under "
                f"the `waystones` namespace and places this pool while `minecraft:village/{biome}/houses` "
                f"generates, by the config worldGen.spawnInVillages (FREQUENT), so only that code puts it "
                f"into a village")))
    compat = _strings(mod.classes, _COMPAT)
    main = _strings(mod.classes, _MAIN)
    rules = mod.data / "unbreakables"
    if compat is not None and _UNBREAKABLES_API in compat and main is not None \
            and all(s in main for s in _MAIN_STRINGS) and rules.is_dir():
        for path in sorted(rules.rglob("*.json")):
            rel = result.claim(mod, path)
            result.unhandled.append(Unhandled(rel, OTHER_MOD_DATA, (
                f"rules in the Unbreakables mod's syntax (`unbreakables`): "
                f"the jar's {_COMPAT} registers their conditions through {_UNBREAKABLES_API}, and {_MAIN} "
                f"loads it only if `unbreakables` is loaded (initializeIfLoaded); Minecraft, the loader and "
                f"Waystones alone never read the file, and Unbreakables isn't converted with this jar")))
    return result
