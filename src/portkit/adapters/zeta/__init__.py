"""Zeta (#280): the library under Quark, as a library adapter.

Zeta registers the load-condition type ``zeta:flag`` its mods' recipes and
loot tables carry (Quark 4.1-487: 1490 recipes, 18 loot tables). A flag is a
module's own (on while the module is enabled), a module's
``@Config(flag = ...)`` option, or one a module's ``ZGatherAdditionalFlags``
handler puts. Its default is read from the bytecode of the mod and of the
Zeta library jar (:mod:`.flags`), never from a hand table (#220): a flag on
by default passes and a flag off by default fails ("disabled by default
config"), as the cited config flags do (docs/decisions.md, 2026-10-13); a
flag set with ``portkit convert --config zeta.<flag>=true|false`` is decided
by that setting; a flag whose default can't be read stays undecided
("unknown load condition"), never guessed.
"""
from __future__ import annotations

import weakref

from ...conditions import FlagDefault, LoadContext, Verdict
from .. import Adapter
from . import flags as _flags

KIND = "zeta:flag"

_READINGS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def reading(context: LoadContext) -> _flags.Reading:
    """The Zeta flags of the conversion's jar, read once per class index."""
    index = getattr(context.mod, "classes", None)
    if index is None:
        return _flags.read(None)
    found = _READINGS.get(index)
    if found is None:
        found = _READINGS[index] = _flags.read(index)
    return found


def _module_enabled(context: LoadContext, found: _flags.Reading,
                    module: _flags.Module) -> tuple[bool | None, str, list[str], bool]:
    """(whether the module is enabled, why, mods whose absence turns it off,
    whether the user's config decided it)."""
    key = (KIND, module.name)
    if key in context.overrides:
        on = bool(context.overrides[key])
        return on, f"module {module.name} {'on' if on else 'off'}, set by user config", [], True
    if not found.module_default_read:
        return None, "the module option's default isn't read from Zeta's ConfigManager", [], False
    required = found.categories.get(module.category, False)
    if required is False:
        return None, f"category {module.category!r} of module {module.name} isn't read", [], False
    if required is None:
        return None, (f"category {module.category!r} of module {module.name} requires a mod chosen at "
                      "run time"), [], False
    if required:
        loaded = context.loaded(required)
        if loaded is None:
            return None, f"whether {required} (category {module.category}) is loaded isn't known", [], False
        if not loaded:
            return False, f"category {module.category} requires {required}", [required], False
    if found.category_default is None:
        return None, "the category option's default isn't read from Zeta's ConfigManager", [], False
    if not found.category_default:
        return False, f"category {module.category} is off by default", [], False
    for mod in module.anti_overlap:
        loaded = context.loaded(mod)
        if loaded is not False:
            # Loaded (Zeta turns the module off unless its "Ignore Anti
            # Overlap" option is set) or unknown: not decided here.
            return None, f"module {module.name} turns itself off when {mod} is loaded", [], False
    if not module.enabled_by_default:
        return False, f"module {module.name} is off by default (@ZetaLoadModule enabledByDefault=false)", [], False
    return True, f"module {module.name} is on by default", [], False


def flag(context: LoadContext, kind: str, cond: dict) -> Verdict:
    """``zeta:flag``: Zeta FlagCondition#test, decided at the defaults read
    from bytecode or at the user's setting."""
    args = {k: v for k, v in cond.items() if k not in ("type", "condition")}
    name = args.pop("flag", None)
    extra = args.pop("extraCondition", True)
    if not isinstance(name, str) or not name or args or not isinstance(extra, bool):
        label = f"{kind}/{name if isinstance(name, str) else '?'}"
        return Verdict(None, f"{label}: not a flag name with an optional boolean extraCondition",
                       unknown=[label])
    label = f"{kind}/{name}"
    if "%" in name:
        return Verdict(None, f"{label}: Zeta throws on a flag containing %", unknown=[label])
    owner = context.mod.namespace
    version = (context.mod.mods or {}).get(owner, "")
    if (kind, name) in context.overrides:
        on = bool(context.overrides[(kind, name)])
        found = FlagDefault(owner, version, kind, name, on, "", user=True)
        value, why, user = on, f"{label} ({'on' if on else 'off'}, set by user config)", True
        absent: list[str] = []
    else:
        found_reading = reading(context)
        if found_reading.problem:
            return Verdict(None, f"{label}: {found_reading.problem}", unknown=[label])
        entries = found_reading.flags.get(name)
        if not entries:
            return Verdict(None, f"{label}: no Zeta module of this jar registers the flag", unknown=[label])
        results = []
        for entry in entries:
            if entry.value is None:
                return Verdict(None, f"{label}: {entry.origin}: {entry.why}", unknown=[label])
            enabled, why, absent, user_module = _module_enabled(context, found_reading, entry.module)
            if enabled is None:
                return Verdict(None, f"{label}: {why}", unknown=[label])
            results.append((entry.value and enabled, entry, why, absent, user_module))
        if len({r[0] for r in results}) > 1:
            return Verdict(None, f"{label}: registered more than once with different values", unknown=[label])
        value, entry, module_why, absent, user = results[0]
        where = entry.module.cls.replace("/", ".")
        source = (f"read from bytecode: {where} ({entry.origin}"
                  + ("" if entry.origin == "module" else f" = {str(entry.value).lower()}")
                  + f"; {module_why}); {found_reading.source}")
        url = source
        found = FlagDefault(owner, version, kind, name, value, url, user=user, read=True)
        if user:
            why = f"{label} ({'on' if value else 'off'}: {module_why})"
        else:
            why = f"{label} ({'on' if value else 'off'} by default: {module_why})"
    if not extra:
        return Verdict(False, f"{label}: extraCondition is false", assumed=[found])
    if value:
        return Verdict(True, why, assumed=[found])
    if absent:
        return Verdict(False, why, absent=absent, assumed=[found])
    if user:
        return Verdict(False, why, user_disabled=[label], assumed=[found])
    return Verdict(False, why, disabled=[label], assumed=[found])


ADAPTER = Adapter(
    name="zeta",
    namespaces=frozenset({"zeta"}),
    library=True,
    conditions={KIND: flag},
)
