"""Per-mod adapters (#245): the one place a mod's namespace may be named.

portkit's core (everything else under ``src/portkit``) converts any Java mod
and must not name one (``tests/test_core_namespace_free.py``). Code that only
serves one mod, or one library many mods share, lives here instead, one
package per mod: ``src/portkit/adapters/<mod>/``. The core reaches it only
through the hooks of :class:`Adapter`, asked in :data:`ADAPTERS` order.

Settled with Alex on 2026-10-15 (``docs/adapter-audit-2026-10-15.md``
section 6, ``docs/decisions.md``): adapters live in this package and ship in
the same wheel; one adapter per Java mod, plus library adapters (``library=
True``) for code many mods share; registration is the explicit ordered tuple
:data:`ADAPTERS`, so output order (and bytes) never depend on import order or
discovery; the interface is a frozen dataclass of optional hooks, most of
them empty for any one adapter; per-mod tables move as Python first.

Hooks, and the core seam that asks each one:

- ``conditions``: load-condition type (``"<ns>:<name>"``) -> handler
  ``(context, kind, condition) -> Verdict``, asked by
  :meth:`portkit.conditions.LoadContext._one` for a condition type the core
  doesn't evaluate itself (the loaders' built-in types stay in core).
- ``recipe_reasons``: Java recipe type -> ``(residue kind, reason)``, the
  reason a string or a function ``(mod, recipe) -> str`` that reads the
  recipe. Asked by :func:`portkit.converters.recipes.convert` for a recipe
  type with no Bedrock mapping, before the generic "special recipe" rule.
- ``convert``: ``SourceMod -> ConversionResult`` for data only this mod's
  code reads (claimed as residue, or converted), run by
  :func:`portkit.converters.convert_all` after the entity converter, in
  registry order.
- ``item_models``: ``SourceMod -> predicate | None``. The predicate takes a
  parsed Java item model and says whether the adapter's ``convert`` hook
  answers for it (turns it into items or reports it); None when the adapter
  has nothing for this mod. Asked by :func:`portkit.converters.items.convert`,
  which leaves such a model alone after claiming it (Tinkers' tool and part
  models, #129).
- ``books``: a :class:`BookReader` for guide books whose pages are data in
  the jar (Citadel's, #182). :func:`portkit.converters.convert_all` asks each
  reader, in registry order, for its plan once the items have converted, its
  page text for the lang converter, and its files plus the
  ``scripts/portkit/main.js`` entry line that wires the core book viewer.
- ``station``: a :class:`StationHooks` for a mod whose blocks a scripted
  station runtime makes work (Farmer's Delight's, #177; Waystones', #178). Each seam of
  :mod:`portkit.converters.stations` (``station_blocks``, ``station_loot``,
  ``station_textures``, ``station_lang_keys``, ``convert``) asks every
  adapter's hook in registry order.
- ``item_durability``: ``(SourceMod, names) -> {name: (durability, source)}``,
  for item names (``items/<name>.json``) a converted smithing recipe takes as
  its base: the durability the mod's code gives each, read from its bytecode
  with :mod:`portkit.itemcode`, and the citation. Asked by
  :func:`portkit.converters.recipes.equip_smithing_bases` (#268); a name with
  no answer is left for the core to withdraw its recipe.

"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Callable, Mapping, Union

if TYPE_CHECKING:  # annotations only: the core imports this package lazily
    from ..conditions import LoadContext, Verdict
    from ..model import ConversionResult, SourceMod

ConditionHandler = Callable[["LoadContext", str, dict], "Verdict"]
RecipeReason = Union[str, Callable[["SourceMod", dict], str]]


@dataclass(frozen=True)
class BookReader:
    """The ``books`` hook: one guide-book format.

    ``plan(mod, files)`` reads the mod's books against what the namespace's
    converters wrote so far (None when it has none); ``lang_text(mod, plan)``
    is Java locale -> {.lang key: text}; ``convert(mod, plan)`` is
    ``(result, main.js entry line or "")``.
    """

    plan: Callable[["SourceMod", dict], object]
    lang_text: Callable[["SourceMod", object], dict]
    convert: Callable[["SourceMod", object], tuple["ConversionResult", str]]


@dataclass(frozen=True)
class StationHooks:
    """The ``station`` hook: one mod's scripted stations, asked for every mod
    (each answers empty for a jar it does not support).

    ``blocks(mod)``: blockstate name -> :class:`portkit.converters.station_kit.FacingBlock`
    the runtime makes work; ``loot_names(mod)``: block loot tables (names
    under ``loot_table/blocks/``) the station reads instead of the loot
    converter; ``derived_textures(mod)``: textures its overlays wear, made
    from the jar's own; ``lang_keys(mod)``: Java lang keys the runtime shows
    itself; ``convert(mod, deferred, loot, files, context)``: ``(result,
    main.js entry lines or "")``, given the recipes of its own types and the
    loot tables it asked for. ``recipe_types``: recipe types the recipe
    converter leaves to this station (its data table); ``shared_types``:
    recipe types it also reads while they convert as usual (#177 stove).
    """

    blocks: Callable[["SourceMod"], dict]
    loot_names: Callable[["SourceMod"], set]
    derived_textures: Callable[["SourceMod"], list]
    lang_keys: Callable[["SourceMod"], set]
    convert: Callable[..., tuple["ConversionResult", str]]
    recipe_types: frozenset = frozenset()
    shared_types: frozenset = frozenset()


def _empty() -> Mapping:
    return MappingProxyType({})


@dataclass(frozen=True)
class Adapter:
    """What one mod (or library) adds to the core. Every hook is optional."""

    name: str
    # Java namespaces the adapter serves (documentation and registry checks;
    # the hooks themselves are keyed by the type strings they claim).
    namespaces: frozenset[str] = frozenset()
    # A library many mods use (Mantle, Citadel), not a mod of its own.
    library: bool = False
    conditions: Mapping[str, ConditionHandler] = field(default_factory=_empty)
    recipe_reasons: Mapping[str, tuple[str, RecipeReason]] = field(default_factory=_empty)
    convert: Callable[["SourceMod"], "ConversionResult"] | None = None
    item_models: Callable[["SourceMod"], Callable[[dict], bool] | None] | None = None
    books: BookReader | None = None
    station: StationHooks | None = None
    item_durability: Callable[["SourceMod", frozenset], Mapping[str, tuple[int, str]]] | None = None


# The registry: explicit and ordered (alphabetical by name unless an order
# matters, which a comment then says). Hooks are asked in this order, and
# check() refuses two adapters claiming the same name, condition type or
# recipe type, so the order never decides between them. Filled at the
# bottom of this module: each adapter module imports Adapter from here.
ADAPTERS: tuple[Adapter, ...] = ()


def check(adapters: tuple[Adapter, ...] | None = None) -> list[str]:
    """Problems with the registry: duplicate adapter names, a condition or
    recipe type claimed twice, a claim outside the adapter's namespaces."""
    adapters = ADAPTERS if adapters is None else adapters
    problems: list[str] = []
    names: set[str] = set()
    owners: dict[tuple[str, str], str] = {}
    for a in adapters:
        if a.name in names:
            problems.append(f"adapter name {a.name!r} registered twice")
        names.add(a.name)
        for hook, keys in (("condition", a.conditions), ("recipe type", a.recipe_reasons)):
            for key in keys:
                if (hook, key) in owners:
                    problems.append(f"{hook} {key!r} claimed by {owners[(hook, key)]!r} and {a.name!r}")
                owners.setdefault((hook, key), a.name)
                if key.partition(":")[0] not in a.namespaces:
                    problems.append(f"{a.name!r} claims {hook} {key!r} outside its namespaces")
    return problems


def condition_handler(kind: str) -> ConditionHandler | None:
    """The handler an adapter registers for load-condition type ``kind``."""
    for a in ADAPTERS:
        handler = a.conditions.get(kind)
        if handler is not None:
            return handler
    return None


def recipe_reason(java_type: object, recipe: dict, mod: "SourceMod") -> tuple[str, str] | None:
    """``(residue kind, reason)`` an adapter gives recipe type ``java_type``,
    or None when no adapter knows the type."""
    if not isinstance(java_type, str):
        return None
    for a in ADAPTERS:
        found = a.recipe_reasons.get(java_type)
        if found is not None:
            kind, reason = found
            return kind, reason if isinstance(reason, str) else reason(mod, recipe)
    return None


def recipe_reasons(kind: str) -> dict[str, str]:
    """Every fixed reason the adapters give, for recipe types of residue
    ``kind`` (computed reasons left out), in registry order."""
    return {t: r for a in ADAPTERS for t, (k, r) in a.recipe_reasons.items() if k == kind and isinstance(r, str)}


def converters() -> list[Callable[["SourceMod"], "ConversionResult"]]:
    """The adapters' ``convert`` hooks, in registry order."""
    return [a.convert for a in ADAPTERS if a.convert is not None]


def item_model_owners(mod: "SourceMod") -> list[Callable[[dict], bool]]:
    """The predicates the adapters' ``item_models`` hooks give for ``mod``,
    in registry order (an adapter with nothing for the mod gives none)."""
    owners = []
    for a in ADAPTERS:
        if a.item_models is not None:
            owns = a.item_models(mod)
            if owns is not None:
                owners.append(owns)
    return owners


def book_readers() -> list[BookReader]:
    """The adapters' ``books`` hooks, in registry order."""
    return [a.books for a in ADAPTERS if a.books is not None]


def item_durabilities(mod: "SourceMod", names: frozenset) -> dict[str, tuple[int, str]]:
    """``{item name: (durability, source)}`` the adapters' ``item_durability``
    hooks read for ``mod``'s ``names``; the first adapter (registry order) to
    answer a name wins."""
    found: dict[str, tuple[int, str]] = {}
    for a in ADAPTERS:
        if a.item_durability is not None:
            for name, answer in a.item_durability(mod, names).items():
                if name in names:
                    found.setdefault(name, answer)
    return found


def station_hooks() -> list[StationHooks]:
    """The adapters' ``station`` hooks, in registry order."""
    return [a.station for a in ADAPTERS if a.station is not None]


from . import (  # noqa: E402  (each imports Adapter above)
    alloy_forgery, bclib, betterend, citadel, create, farmersdelight, mantle, mekanism, mythicmetals, silentgear,
    supplementaries, tconstruct, waystones,
)

ADAPTERS = (
    alloy_forgery.ADAPTER,
    bclib.ADAPTER,
    betterend.ADAPTER,
    citadel.ADAPTER,
    create.ADAPTER,
    farmersdelight.ADAPTER,
    mantle.ADAPTER,
    mekanism.ADAPTER,
    mythicmetals.ADAPTER,
    silentgear.ADAPTER,
    supplementaries.ADAPTER,
    tconstruct.ADAPTER,
    waystones.ADAPTER,
)
