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

Hooks for the station adapters (blocks, loot, textures, lang, runtime) are
added with the moves that need them (audit section 7, steps 5-8).
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


# The registry: explicit and ordered. Hooks are asked in this order, and
# check() refuses two adapters claiming the same name, condition type or
# recipe type, so the order never decides between them.
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
