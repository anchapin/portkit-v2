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
- ``item_armor``: ``(SourceMod, names) -> {name: ArmorPiece | reason}``, for
  the namespace's emitted item names: each armor item's
  :class:`portkit.itemcode.ArmorPiece` (type, armor points, durability,
  enchantability, toughness, knockback resistance and the citation), read from
  the mod's bytecode with :mod:`portkit.itemcode`, or a string saying why an
  item the adapter knows is armor can't be read. Asked by
  :func:`portkit.converters.armor.convert` (#274) right after the item
  converter, so the recipe converter sees which items are wearable.
- ``block_variations``: ``SourceMod -> {blockstate name: VariationSet}``,
  for a mod whose code registers a block per named variant of one
  blockstate (Chisel's builder chains, #296): which variants its code
  registers, the translation key of each one's name and why Java may not
  register it. Asked by :func:`portkit.converters.blocks.convert`, which
  converts each registered variant from the blockstate's defaults and its
  own textures.
- ``orientations``: ``(SourceMod, {blockstate name: block class}) ->
  {blockstate name: Orientation}``, for a mod whose blocks take ``facing``
  and a second orientation state (AE2's ``spin``) from a placement rule of
  the mod's own that the core's interpreter can't follow (#296): which
  Bedrock placement states give which Java orientation, read from the
  mod's code, and what the blockstate's own variant keys turn. Asked by
  :func:`portkit.converters.blocks.convert` for blockstates drawing a
  six-way ``facing`` beside another state no reader takes.

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


@dataclass(frozen=True)
class Variation:
    """One variant of a blockstate that the mod's code registers as a block
    (the ``block_variations`` hook): its variant key, the translation key of
    the block's name ("" when not read), why Java may not register it (a
    required mod, a branch the reading can't decide; "" when it always
    does) and where it was read."""

    name: str
    lang_key: str = ""
    gate: str = ""
    source: str = ""


@dataclass(frozen=True)
class VariationSet:
    """The variants of one blockstate the mod's code registers, in
    registration order, why the reading of some is incomplete ("" when it
    isn't), and where it was read."""

    variations: tuple = ()
    why: str = ""
    source: str = ""


@dataclass(frozen=True)
class BlockRegistry:
    """Every blockstate name the mod's code registers a block under (the
    ``block_registry`` hook, #296), why the reading may have missed one
    ("" when it read every registration path it knows of), and where it was
    read. A blockstate is said to be one Java never loads only from a
    reading with no ``why``."""

    names: frozenset = frozenset()
    why: str = ""
    source: str = ""


@dataclass(frozen=True)
class Orientation:
    """How a block's code places its orientation states (the
    ``orientations`` hook, #296).

    ``states``: the orientation states, ``facing`` first (``("facing",
    "spin")``). ``turns``: blockstate variant keys of the mod's own that turn
    a model, each to the axis it turns about (``{"ae2:z": "z"}``: a quarter
    turn applied before x and y, as vanilla composes x and y). ``placed``:
    ``(conditions, values)`` per Bedrock placement, ``conditions`` ``(state,
    value)`` pairs of ``minecraft:facing_direction`` /
    ``minecraft:cardinal_direction`` and ``values`` ``(state, value)`` pairs
    of the Java orientation states that placement gives. Every state not in
    ``states`` or ``sets`` starts where the registered default has it.
    ``sets``: other states placement sets (``waterlogged``). ``text``: the
    rule in words; ``source``: where it was read; ``default``: the DEFAULT
    the Bedrock mapping leans on ("" when none); ``turned_by``: what turns
    the block to the orientations placement never gives; ``why``: why the
    rule isn't read ("" when it is).
    """

    states: tuple = ()
    turns: Mapping = field(default_factory=dict)
    placed: tuple = ()
    sets: tuple = ()
    text: str = ""
    source: str = ""
    default: str = ""
    turned_by: str = ""
    why: str = ""


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
    item_armor: Callable[["SourceMod", frozenset], Mapping[str, object]] | None = None
    # (ClassIndex) -> [portkit.rendershape.Binding]: block-entity renderer
    # bindings a library makes from its own code for a factory the mod hands
    # its builder (#362), asked by portkit.rendershape.bindings after the
    # core's own registration calls.
    renderer_bindings: Callable[[object], list] | None = None
    # (portkit.rendershape._Types) -> (a blockcode.Machine.call_hook, the
    # mod's classes whose initializers to run again under it): reads the
    # block entity types a library builds for the mod (its builder chain and
    # the entry object the chain registers) while a block's own no-argument
    # method returning its type is run (#366), asked by
    # portkit.rendershape.typed_entities. The hook gives a type the core
    # reads as a built one (an ``__betype`` object with its factory).
    block_entity_types: Callable[[object], tuple] | None = None
    # (SourceMod) -> {blockstate name: VariationSet} (#296), see the module
    # docstring.
    block_variations: Callable[["SourceMod"], Mapping[str, VariationSet]] | None = None
    # (SourceMod) -> BlockRegistry, or None for a jar the adapter doesn't
    # read (#296): the blockstate names the mod's code registers blocks under.
    block_registry: Callable[["SourceMod"], "BlockRegistry | None"] | None = None
    # (SourceMod, {blockstate name: block class}) -> {blockstate name:
    # Orientation} (#296), see the module docstring.
    orientations: Callable[["SourceMod", Mapping[str, str]], Mapping[str, Orientation]] | None = None


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


def item_armors(mod: "SourceMod", names: frozenset) -> dict[str, object]:
    """``{item name: ArmorPiece | reason}`` the adapters' ``item_armor`` hooks
    read for ``mod``'s ``names``; the first adapter (registry order) to give a
    piece wins over a reason, and the first reason over none."""
    from ..itemcode import ArmorPiece

    found: dict[str, object] = {}
    for a in ADAPTERS:
        if a.item_armor is not None:
            for name, answer in a.item_armor(mod, names).items():
                if name not in names:
                    continue
                if isinstance(answer, ArmorPiece) and not isinstance(found.get(name), ArmorPiece):
                    found[name] = answer
                elif isinstance(answer, str):
                    found.setdefault(name, answer)
    return found


def renderer_bindings(classes) -> list:
    """Every adapter's ``renderer_bindings`` for ``classes``, in registry order."""
    return [b for a in ADAPTERS if a.renderer_bindings is not None for b in a.renderer_bindings(classes)]


def block_entity_types(types) -> tuple:
    """(one Machine.call_hook asking every adapter's ``block_entity_types``
    hook in registry order, the first that answers deciding, or None when no
    adapter has one; every class an adapter names to initialize again)."""
    made = [a.block_entity_types(types) for a in ADAPTERS if a.block_entity_types is not None]
    hooks = [h for h, _ in made if h is not None]
    again = {c for _, cs in made for c in cs}
    if not hooks:
        return None, again

    def hook(owner, name, desc, args, static):
        for h in hooks:
            got = h(owner, name, desc, args, static)
            if got is not None:
                return got
        return None

    return hook, again


def block_variations(mod: "SourceMod") -> dict[str, VariationSet]:
    """Every adapter's ``block_variations`` for ``mod``; the first adapter
    (registry order) to answer a blockstate wins."""
    found: dict[str, VariationSet] = {}
    for a in ADAPTERS:
        if a.block_variations is not None:
            for name, vset in a.block_variations(mod).items():
                found.setdefault(name, vset)
    return found


def unregistered_blockstates(mod: "SourceMod", names) -> dict[str, str]:
    """Blockstate name -> where the reading was made, for each of ``names``
    the mod's code registers no block under: only when at least one adapter
    reads ``mod``'s registrations and every adapter that does read them read
    them completely (``BlockRegistry.why`` empty); a name any reading has is
    registered. Empty otherwise (#87: never said from a partial reading)."""
    found = [r for a in ADAPTERS if a.block_registry is not None
             for r in [a.block_registry(mod)] if r is not None]
    if not found or any(r.why for r in found):
        return {}
    known = frozenset().union(*(r.names for r in found))
    where = "; ".join(dict.fromkeys(r.source for r in found if r.source))
    return {n: where for n in names if n not in known}


def reads_orientations(mod: "SourceMod") -> bool:
    """Whether an adapter with an ``orientations`` hook serves ``mod``'s
    namespace (the core reads candidates' classes only then)."""
    return any(a.orientations is not None and getattr(mod, "namespace", None) in a.namespaces for a in ADAPTERS)


def orientations(mod: "SourceMod", classes_by_name: Mapping[str, str]) -> dict[str, Orientation]:
    """Every adapter's ``orientations`` for ``mod``'s blockstates in
    ``classes_by_name`` (name -> block class); the first adapter (registry
    order) to answer a blockstate wins."""
    found: dict[str, Orientation] = {}
    for a in ADAPTERS:
        if a.orientations is not None:
            for name, orientation in a.orientations(mod, classes_by_name).items():
                if name in classes_by_name:
                    found.setdefault(name, orientation)
    return found


def station_hooks() -> list[StationHooks]:
    """The adapters' ``station`` hooks, in registry order."""
    return [a.station for a in ADAPTERS if a.station is not None]


from . import (  # noqa: E402  (each imports Adapter above)
    ae2, alloy_forgery, bclib, betterend, chisel, citadel, create, farmersdelight, mantle, mekanism, mythicmetals, registrate,
    silentgear, supplementaries, tconstruct, waystones, zeta,
)

ADAPTERS = (
    ae2.ADAPTER,
    alloy_forgery.ADAPTER,
    bclib.ADAPTER,
    betterend.ADAPTER,
    chisel.ADAPTER,
    citadel.ADAPTER,
    create.ADAPTER,
    farmersdelight.ADAPTER,
    mantle.ADAPTER,
    mekanism.ADAPTER,
    mythicmetals.ADAPTER,
    registrate.ADAPTER,
    silentgear.ADAPTER,
    supplementaries.ADAPTER,
    tconstruct.ADAPTER,
    waystones.ADAPTER,
    zeta.ADAPTER,
)
