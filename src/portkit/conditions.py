"""Load conditions: whether Java loads a data file at all (#183).

Forge, NeoForge and Fabric let a data file carry conditions that decide whether
it is loaded: ``conditions`` (Forge), ``neoforge:conditions`` (NeoForge) and
``fabric:load_conditions`` (Fabric). A recipe that loads only with another mod
installed, or only when a config option is on, is not part of the mod a player
gets without them, so converting it unconditionally ships content Java would
not load. This module decides each file against the conversion context:

- **Loaded mods.** The mods the jar declares, the mods it declares as required
  (Java can't load it without them) and the platform (minecraft and the
  loader). Anything else is absent: a ``mod_loaded`` on it is false, which is
  what Java decides when that mod isn't installed. Without loader metadata the
  required mods are unknown, so only the jar's own namespace and the platform
  are decided.
- **Tags** (``tag_empty``, Fabric ``tags_populated``, Mantle ``tag_filled`` and
  ``tag_combination_filled``): an item tag's membership in that context, from
  the jar's tag files and the fetched loader and vanilla tag data
  (:class:`portkit.converters.tags.TagResolver`). Unknown membership, or a
  registry other than items, is undecidable.
- **Items** (``item_exists``, Fabric ``registry_contains``): an item of an
  absent mod doesn't exist. Whether this mod or vanilla registers an id is
  decided in Java code, so that is undecidable.
- **Config flags** of the mod itself (``supplementaries:flag``,
  ``mythicmetals:dust_enabled``, ``tconstruct:config``...): the flag's default,
  read from the mod's own source at the version the jar declares and recorded
  with a citation in ``portkit/data/config_flag_defaults.json``. A cited
  ``true`` passes (the conversion assumes the default config, and says so in
  one note per mod); a cited ``false`` fails ("disabled by default config");
  a flag or version with no citation is undecidable ("unknown load condition"),
  never guessed. See docs/decisions.md, 2026-10-13.
- **User config** (``portkit convert --config <mod>.<flag>=<true|false>``,
  ``--config-file``): the conversion-time stand-in for a Java player editing
  the mod's config file. A flag the user sets is decided by that setting instead
  of its cited default, both ways, cited or not ("set by user config"); a file
  it turns off is residue "disabled by user config: <flag>". Names are the flag
  as the conditions spell it or the option's own config key where the data file
  cites one (``mythicmetals.enableDusts``); an unknown mod or flag is a
  :class:`ConfigError` listing the valid ones, never a silent ignore. See
  docs/decisions.md, 2026-10-13 (config overrides).
- **Config values** (non-boolean options a converter reads, not load
  conditions, such as Farmer's Delight's ``cuttingBoardFortuneBonus``): the
  ``values`` list of the same data file cites each option's type, default and
  the range the mod's config accepts; :meth:`LoadContext.config_value` gives a
  converter the cited default or the user's ``--config <mod>.<key>=<number>``.
  A number outside the cited range is a :class:`ConfigError` (Java would clamp
  or reset it, differently per loader, so the user hears about it instead).
  docs/decisions.md, 2026-10-15.
- **Gated registrations**: ids the mod's code registers only while a flag is on
  (``registers`` in the data file, cited), such as Mythic Metals' ``*_dust``
  items under ``enableDusts``; :meth:`LoadContext.gated_item` decides them the
  same way, so the item converter leaves them out when the flag is off.

A false condition and an undecidable one both make the file residue: the first
because Java doesn't load it, the second because shipping it would be a guess.

``conditions`` keys inside loot tables, loot modifiers and other mods' data
(Silent Gear traits) are loot predicates or the mod's own logic, not load
conditions; only the keys above, at the top level of a recipe or loot table,
are read here.
"""
from __future__ import annotations

import fnmatch
import json
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .converters.tags import TagResolver
    from .model import SourceMod

FLAG_DATA = "config_flag_defaults.json"
# Key of a config value setting in a LoadContext's overrides: (VALUE_KEY,
# "<mod>.<option>"). Condition types always carry a namespace colon and this
# one is portkit's own, so it never meets a load condition's (type, flag).
VALUE_KEY = "portkit:config_value"

# Top-level keys Java reads as load conditions, per loader. A key the jar's
# loader doesn't read is left alone; with no known loader every key counts.
_RECIPE_KEYS = {
    "forge": ("conditions", "forge:conditions"),
    "forge-legacy": ("conditions",),
    "neoforge": ("neoforge:conditions", "conditions"),
    "fabric": ("fabric:load_conditions",),
    "quilt": ("fabric:load_conditions",),
}
_ALL_KEYS = ("conditions", "forge:conditions", "neoforge:conditions", "fabric:load_conditions")
# Loot tables: Forge 1.20.1 reads no load conditions on them, so a top-level
# "conditions" there is never one (pool and entry "conditions" are loot
# predicates in every version).
_LOOT_KEYS = {
    "neoforge": ("neoforge:conditions",),
    "fabric": ("fabric:load_conditions",),
    "quilt": ("fabric:load_conditions",),
}
_LOOT_ALL = ("neoforge:conditions", "fabric:load_conditions")

# Mods present whenever the jar loads at all.
_PLATFORM = {
    "forge": {"minecraft", "forge"},
    "forge-legacy": {"minecraft", "forge"},
    "neoforge": {"minecraft", "neoforge"},
    "fabric": {"minecraft", "fabricloader", "java"},
    "quilt": {"minecraft", "fabricloader", "quilt_loader", "java"},
}

_ITEM_REGISTRY = ("minecraft:item", "item", None)

# Wrapper recipe types: a list of {conditions, recipe}, the first entry whose
# conditions hold is the recipe (Forge 1.20.1 ConditionalRecipe).
CONDITIONAL_TYPES = ("forge:conditional", "neoforge:conditional")


def condition_keys(loader: str | None, kind: str = "recipe") -> tuple[str, ...]:
    if kind == "loot":
        return _LOOT_KEYS.get(loader or "", _LOOT_ALL)
    return _RECIPE_KEYS.get(loader or "", _ALL_KEYS)


@dataclass(frozen=True)
class FlagDefault:
    mod: str
    version: str
    condition: str
    flag: str  # "" for a condition with no argument
    default: bool  # the value the verdict used: the cited default, or the user's setting
    url: str
    user: bool = False  # set by user config rather than read from the cited default


@lru_cache(maxsize=1)
def _flag_table() -> dict:
    text = resources.files("portkit.data").joinpath(FLAG_DATA).read_text(encoding="utf-8")
    return json.loads(text)


def flag_entries(table: dict | None = None) -> list[dict]:
    return list((table if table is not None else _flag_table()).get("entries") or [])


def value_entries(table: dict | None = None) -> list[dict]:
    """The cited non-boolean config options (``values`` in the data file)."""
    return list((table if table is not None else _flag_table()).get("values") or [])


@dataclass(frozen=True)
class ConfigValue:
    """A non-boolean config option as a converter reads it."""

    mod: str
    option: str
    value: float  # the cited default, or the user's setting
    default: float | None  # the cited default for this jar's version
    url: str
    user: bool = False  # set by user config rather than the cited default

    @property
    def label(self) -> str:
        return f"{self.mod}.{self.option}"


@dataclass
class Verdict:
    """Whether a condition (or a list of them) holds in this conversion.

    ``passes`` is True, False, or None when it can't be decided here.
    """

    passes: bool | None
    why: str = ""
    absent: list[str] = field(default_factory=list)  # absent mods a false verdict rests on
    disabled: list[str] = field(default_factory=list)  # flags off by default that make it false
    unknown: list[str] = field(default_factory=list)  # "<type>/<flag>" with no cited default
    assumed: list[FlagDefault] = field(default_factory=list)  # cited defaults a true verdict uses
    user_disabled: list[str] = field(default_factory=list)  # flags the user's config turned off
    # For a gated registration (:meth:`LoadContext.gated_item`): the flag that
    # decides it ("<condition>" or "<condition>/<flag>"), and the
    # ``portkit convert --config`` setting that turns it on, e.g.
    # "mythicmetals.enableDusts=true" (the cited config key when there is one).
    gate: str = ""
    enable: str = ""

    def reason(self) -> str:
        """The residue reason for a verdict that isn't True."""
        if self.passes is False:
            if self.user_disabled:
                return f"disabled by user config: {', '.join(dict.fromkeys(self.user_disabled))}"
            if self.disabled:
                return f"disabled by default config: {', '.join(dict.fromkeys(self.disabled))}"
            if self.absent:
                mods = ", ".join(dict.fromkeys(self.absent))
                return (f"compat for {mods}: loads only when {mods} "
                        f"{'is' if len(set(self.absent)) == 1 else 'are'} installed, and this "
                        f"conversion holds only this mod ({self.why})")
            return f"load condition is false here: {self.why}"
        if self.unknown:
            return f"unknown load condition {', '.join(dict.fromkeys(self.unknown))}"
        return f"load condition can't be decided here: {self.why}"


def _kind(cond: dict) -> str | None:
    kind = cond.get("type") if isinstance(cond.get("type"), str) else cond.get("condition")
    return kind if isinstance(kind, str) else None


def _local(kind: str) -> str:
    return kind.split(":", 1)[-1]


class LoadContext:
    """What is loaded alongside this mod in Java, for deciding conditions.

    Shared by the converters of one namespace, so the flags assumed at their
    defaults add up to one note (:meth:`note`).
    """

    def __init__(self, mod: "SourceMod", tags: "TagResolver | None" = None,
                 table: dict | None = None, overrides: dict[tuple[str, str], bool | float] | None = None):
        self.mod = mod
        self._tags = tags
        self._table = table
        # (condition type, flag) -> the user's setting (``--config``), which
        # replaces the cited default; see :func:`resolve_config`. Config value
        # settings sit under (VALUE_KEY, "<mod>.<option>").
        self.overrides = dict(overrides or {})
        self.assumed: dict[tuple[str, str], FlagDefault] = {}

    # -- the conversion context --------------------------------------------
    @property
    def tags(self) -> "TagResolver":
        if self._tags is None:
            from .converters.tags import TagResolver
            self._tags = TagResolver(self.mod)
        return self._tags

    def _known_mods(self) -> set[str] | None:
        if self.mod.mods is None:
            return None
        return (set(self.mod.mods) | set(self.mod.requires or ())
                | _PLATFORM.get(self.mod.loader or "", {"minecraft"}))

    def loaded(self, modid: str) -> bool | None:
        if not isinstance(modid, str) or not modid:
            return None
        known = self._known_mods()
        if known is None:
            platform = _PLATFORM.get(self.mod.loader or "", {"minecraft"})
            return True if modid in platform or modid == self.mod.namespace else None
        return modid in known

    def _present(self, ident: str) -> bool | None:
        """Whether an item id exists in Java alongside this mod (None: can't say)."""
        tag = ident.startswith("#")
        ident = ident[1:] if tag else ident
        ns = ident.partition(":")[0] if ":" in ident else "minecraft"
        if (ns == "minecraft" or ns == self.mod.namespace) and not tag:
            # Vanilla, or the namespace being converted (which need not be a
            # declared mod id: the jar ships its files either way).
            return True
        loaded = self.loaded(ns)
        if loaded is False:
            return False
        if tag:
            return None  # a loaded mod's tag this jar doesn't spell out
        return True if loaded and ns in set(self.mod.mods or ()) | {self.mod.namespace} else None

    def tag_filled(self, tag: str, registry=None) -> tuple[bool | None, str]:
        """(whether the item tag has a member here, why) - None when unknown."""
        if registry not in _ITEM_REGISTRY:
            return None, f"tag {tag} is a {registry} tag, whose membership isn't read"
        tag = tag[1:] if isinstance(tag, str) and tag.startswith("#") else tag
        if not isinstance(tag, str) or ":" not in tag:
            return None, f"tag {tag!r} is not a namespaced id"
        members = self.tags.context_members(tag)
        if members is None:
            return None, (f"tag {tag}'s membership isn't known"
                          f" ({self.tags.unknown_reason(tag) or 'no tag data'})")
        undecided = False
        for member in members:
            here = self._present(member)
            if here:
                return True, f"tag {tag} holds {member}"
            if here is None:
                undecided = True
        if undecided:
            return None, f"whether tag {tag}'s members are registered isn't known"
        return False, f"tag {tag} is empty with only this mod, the loader and vanilla"

    def flag(self, kind: str, flag: str) -> FlagDefault | str:
        """The cited default of a mod config flag, or why there is none (a str)."""
        owner_versions = []
        for entry in flag_entries(self._table):
            if entry.get("condition") != kind:
                continue
            version = (self.mod.mods or {}).get(entry.get("mod"))
            owner_versions.append(str(entry.get("version")))
            if version is None or str(entry.get("version")) != version:
                continue
            found = (entry.get("flags") or {}).get(flag)
            if not isinstance(found, dict) or not isinstance(found.get("default"), bool):
                return f"no cited default for this flag in {entry.get('mod')} {version}"
            return FlagDefault(entry["mod"], version, kind, flag, found["default"], str(found.get("url", "")))
        if owner_versions:
            return f"defaults are cited for version {', '.join(sorted(set(owner_versions)))} only"
        return "no cited default for this condition type"

    def config_value(self, mod: str, option: str) -> ConfigValue | None:
        """A non-boolean config option: the user's setting, else the cited default.

        None when neither is there (an uncited mod version and no setting):
        the caller decides what an unread option means, never a guess here.
        """
        version = (self.mod.mods or {}).get(mod)
        default, url = None, ""
        for entry in value_entries(self._table):
            if entry.get("mod") != mod or version is None or str(entry.get("version")) != version:
                continue
            found = (entry.get("options") or {}).get(option)
            if isinstance(found, dict) and _is_number(found.get("default")):
                default, url = float(found["default"]), str(found.get("url", ""))
                break
        key = (VALUE_KEY, f"{mod}.{option}")
        if key in self.overrides:
            return ConfigValue(mod, option, float(self.overrides[key]), default, url, user=True)
        if default is None:
            return None
        return ConfigValue(mod, option, default, default, url)

    # -- evaluation --------------------------------------------------------
    def evaluate(self, conditions) -> Verdict:
        """All of ``conditions`` (a list, or one condition) must hold."""
        if isinstance(conditions, dict):
            conditions = [conditions]
        if not isinstance(conditions, list):
            return Verdict(None, f"conditions are {type(conditions).__name__}, not a list")
        return self._all([self._one(c) for c in conditions], "and")

    def _all(self, parts: list[Verdict], how: str) -> Verdict:
        if not parts:
            return Verdict(True, "no conditions")
        decisive = [p for p in parts if p.passes is (how == "or")]
        if decisive:
            # and: any false is false; or: any true is true.
            out = Verdict(how == "or", decisive[0].why if how == "or"
                          else "; ".join(dict.fromkeys(p.why for p in decisive)))
            for p in decisive:
                out.absent += p.absent
                out.disabled += p.disabled
                out.user_disabled += p.user_disabled
                out.assumed += p.assumed
            return out
        unknown = [p for p in parts if p.passes is None]
        if unknown:
            out = Verdict(None, unknown[0].why)
            for p in unknown:
                out.unknown += p.unknown
            return out
        out = Verdict(how != "or", parts[0].why if len(parts) == 1 else
                      (" and " if how == "and" else " or ").join(p.why for p in parts))
        for p in parts:
            out.absent += p.absent
            out.disabled += p.disabled
            out.user_disabled += p.user_disabled
            out.assumed += p.assumed
        return out

    def _one(self, cond) -> Verdict:
        if not isinstance(cond, dict):
            return Verdict(None, f"condition {cond!r} is not an object")
        kind = _kind(cond)
        if kind is None:
            return Verdict(None, "condition has no type", unknown=["<no type>"])
        ns, local = kind.partition(":")[0], _local(kind)
        builtin = ns in ("forge", "neoforge", "fabric", "minecraft")
        if builtin and local in ("true", "false"):
            return Verdict(local == "true", kind)
        if builtin and local == "not":
            inner = self._one(cond.get("value"))
            if inner.passes is None:
                return inner
            flags = [f"{f.condition}/{f.flag}" if f.flag else f.condition for f in inner.assumed]
            how = "set by user config" if any(f.user for f in inner.assumed) else "by default"
            if flags and inner.passes:
                why = f"loads only when {', '.join(flags)} is off, and it is on {how}"
            elif flags:
                why = f"loads when {', '.join(flags)} is off, as it is {how}"
            else:
                why = f"not ({inner.why})"
            # not(...) of an absent mod passes; not(...) of a present one rests
            # on nothing absent, so neither carries ``absent`` on.
            return Verdict(not inner.passes, why, assumed=inner.assumed)
        if builtin and local in ("and", "or"):
            values = cond.get("values")
            if not isinstance(values, list):
                return Verdict(None, f"{kind} has no values list")
            return self._all([self._one(v) for v in values], local)
        if builtin and local == "mod_loaded":
            return self._mods(kind, [cond.get("modid")], every=True)
        if builtin and local in ("all_mods_loaded", "any_mods_loaded"):
            values = cond.get("values")
            if not isinstance(values, list):
                return Verdict(None, f"{kind} has no values list")
            return self._mods(kind, values, every=local == "all_mods_loaded")
        if kind == "mekanism:mod_version_loaded":
            loaded = self.loaded(cond.get("modid"))
            if loaded is False:
                return Verdict(False, f"{kind} {cond.get('modid')}", absent=[cond.get("modid")])
            # mekanism ModVersionLoadedCondition: a loaded mod at least as new;
            # Maven version ordering isn't reimplemented here.
            return Verdict(None, f"{kind} {cond.get('modid')} >= {cond.get('version')} on a loaded mod")
        if builtin and local == "tag_empty":
            filled, why = self.tag_filled(cond.get("tag"), cond.get("registry"))
            return Verdict(None if filled is None else not filled, f"{kind}: {why}")
        if kind == "fabric:tags_populated":
            values = cond.get("values")
            if not isinstance(values, list):
                return Verdict(None, f"{kind} has no values list")
            return self._all([self._tag(kind, v, cond.get("registry")) for v in values], "and")
        if kind == "mantle:tag_filled":
            return self._tag(kind, cond.get("tag"), cond.get("registry"))
        if kind == "mantle:tag_combination_filled":
            return self._combination(cond)
        if builtin and local == "item_exists":
            return self._items(kind, [cond.get("item")])
        if kind == "fabric:registry_contains":
            if cond.get("registry") not in _ITEM_REGISTRY:
                return Verdict(None, f"{kind} on registry {cond.get('registry')}")
            values = cond.get("values")
            return self._items(kind, values if isinstance(values, list) else [None])
        if builtin:
            return Verdict(None, f"{kind} isn't evaluated", unknown=[kind])
        return self._flag(kind, cond)

    def _mods(self, kind: str, mods: list, every: bool) -> Verdict:
        parts = []
        for modid in mods:
            loaded = self.loaded(modid)
            if loaded is None:
                parts.append(Verdict(None, f"{kind} {modid}: whether it is loaded with this mod "
                                           "isn't known (no loader metadata)"))
            elif loaded:
                parts.append(Verdict(True, f"{kind} {modid}"))
            else:
                parts.append(Verdict(False, f"{kind} {modid}", absent=[modid]))
        return self._all(parts, "and" if every else "or")

    def _tag(self, kind: str, tag, registry) -> Verdict:
        filled, why = self.tag_filled(tag, registry)
        return Verdict(filled, f"{kind}: {why}")

    def _combination(self, cond: dict) -> Verdict:
        # Mantle TagCombinationCondition.test: some entry of the first match tag
        # (not in ignore) is in every other match tag.
        kind = "mantle:tag_combination_filled"
        registry = cond.get("registry")
        match = cond.get("match")
        match = [match] if isinstance(match, str) else match
        if not isinstance(match, list) or not match or registry not in _ITEM_REGISTRY:
            return Verdict(None, f"{kind}: unreadable match list or a non-item registry")
        sets = []
        for tag in match + ([cond["ignore"]] if isinstance(cond.get("ignore"), str) else []):
            members = self.tags.context_members(tag) if isinstance(tag, str) else None
            if members is None:
                return Verdict(None, f"{kind}: tag {tag}'s membership isn't known")
            present = []
            for m in members:
                here = self._present(m)
                if here is None:
                    return Verdict(None, f"{kind}: whether tag {tag}'s members are registered isn't known")
                if here:
                    present.append(m)
            sets.append(set(present))
        ignore = sets[len(match)] if len(sets) > len(match) else set()
        hit = sorted(m for m in sets[0] - ignore if all(m in s for s in sets[1:len(match)]))
        if hit:
            return Verdict(True, f"{kind}: {hit[0]} is in {', '.join(match)}")
        return Verdict(False, f"{kind}: no item is in all of {', '.join(match)}"
                              + (f" outside {cond['ignore']}" if cond.get("ignore") else "")
                              + " with only this mod, the loader and vanilla")

    def _items(self, kind: str, items: list) -> Verdict:
        parts = []
        for item in items:
            if not isinstance(item, str) or not item:
                parts.append(Verdict(None, f"{kind}: unreadable item {item!r}"))
                continue
            ns = item.partition(":")[0] if ":" in item else "minecraft"
            loaded = self.loaded(ns) if ns != "minecraft" else True
            if loaded is False:
                parts.append(Verdict(False, f"{kind} {item}", absent=[ns]))
            else:
                parts.append(Verdict(None, f"{kind} {item}: whether it is registered is decided "
                                           "in Java code"))
        return self._all(parts, "and")

    def _flag(self, kind: str, cond: dict) -> Verdict:
        args = {k: v for k, v in cond.items() if k not in ("type", "condition")}
        if len(args) > 1 or (args and not all(isinstance(v, str) for v in args.values())):
            label = f"{kind}/{json.dumps(args, sort_keys=True)}"
            return Verdict(None, f"{label}: not a single named flag", unknown=[label])
        flag = next(iter(args.values()), "") if args else ""
        label = f"{kind}/{flag}" if flag else kind
        if (kind, flag) in self.overrides:
            # The user's config decides it, cited default or not.
            on = self.overrides[(kind, flag)]
            found = FlagDefault(kind.partition(":")[0], (self.mod.mods or {}).get(kind.partition(":")[0], ""),
                                kind, flag, on, "", user=True)
            if on:
                return Verdict(True, f"{label} (on, set by user config)", assumed=[found])
            return Verdict(False, f"{label} (off, set by user config)", user_disabled=[label],
                           assumed=[found])
        found = self.flag(kind, flag)
        if isinstance(found, str):
            return Verdict(None, f"{label}: {found}", unknown=[label])
        if found.default:
            return Verdict(True, f"{label} (on by default)", assumed=[found])
        return Verdict(False, f"{label} (off by default)", disabled=[label], assumed=[found])

    # -- for converters ----------------------------------------------------
    def gate(self, data: dict, kind: str = "recipe") -> Verdict:
        """The verdict on a data file's own load conditions (True when it has none)."""
        parts = [self.evaluate(data[key]) for key in condition_keys(self.mod.loader, kind)
                 if key in data]
        verdict = self._all(parts, "and")
        if verdict.passes:
            self.remember(verdict)
        return verdict

    def choose(self, data: dict) -> tuple[dict | None, Verdict]:
        """The recipe a conditional wrapper loads, and the verdict that picked it.

        Entries are tried in order, like Forge's ConditionalRecipe: the first
        whose conditions hold is the recipe. An undecidable entry before it
        leaves the choice undecidable; none holding means nothing loads.
        """
        entries = data.get("recipes")
        if not isinstance(entries, list) or not entries:
            return None, Verdict(None, f"{data.get('type')} has no recipes list")
        failed: list[Verdict] = []
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("recipe"), dict):
                return None, Verdict(None, f"{data.get('type')} entry without a recipe")
            verdict = self.evaluate(entry.get("conditions", []))
            if verdict.passes is None:
                return None, verdict
            if verdict.passes:
                inner = self.gate(entry["recipe"])
                if inner.passes:
                    self.remember(verdict)
                    return entry["recipe"], verdict
                return None, inner
            failed.append(verdict)
        out = Verdict(False, "no entry's conditions hold: " + "; ".join(v.why for v in failed))
        for v in failed:
            out.absent += v.absent
            out.disabled += v.disabled
            out.user_disabled += v.user_disabled
        return None, out

    def gated_item(self, ident: str) -> Verdict | None:
        """Whether the mod's code registers ``ident``, when a config flag decides it.

        None when no cited ``registers`` pattern for this mod version names the
        id; otherwise the flag's verdict (the user's setting or the cited
        default), with ``passes`` False when Java doesn't register the item.
        """
        for entry in flag_entries(self._table):
            version = (self.mod.mods or {}).get(entry.get("mod"))
            if version is None or str(entry.get("version")) != version:
                continue
            kind = entry.get("condition")
            gates = []
            if isinstance(entry.get("registers"), dict) and entry.get("argument") is None:
                gates.append(("", entry["registers"]))
            for flag, found in (entry.get("flags") or {}).items():
                if isinstance(found, dict) and isinstance(found.get("registers"), dict):
                    gates.append((flag, found["registers"]))
            for flag, registers in gates:
                patterns = [p for p in registers.get("items") or [] if isinstance(p, str)]
                if not any(fnmatch.fnmatchcase(ident, p) for p in patterns):
                    continue
                cond = {"type": kind, **({entry["argument"]: flag} if flag and entry.get("argument") else {})}
                verdict = self._flag(kind, cond)
                label = f"{kind}/{flag}" if flag else kind
                verdict.why = f"Java registers {ident} only while {label} is on: {verdict.why}"
                cited = (entry.get("flags") or {}).get(flag)
                key = cited.get("config_key") if isinstance(cited, dict) else None
                verdict.gate = label
                verdict.enable = f"{entry['mod']}.{key if isinstance(key, str) else flag or _local(kind)}=true"
                if verdict.passes:
                    self.remember(verdict)
                return verdict
        return None

    def remember(self, verdict: Verdict) -> None:
        for found in verdict.assumed:
            self.assumed[(found.condition, found.flag)] = found

    def note(self) -> str | None:
        """One line naming every flag the conversion assumed at its cited default."""
        assumed = {k: f for k, f in self.assumed.items() if not f.user}
        if not assumed:
            return None
        by_mod: dict[str, dict[bool, list[str]]] = {}
        for (kind, flag), found in sorted(assumed.items()):
            by_mod.setdefault(f"{found.mod} {found.version}", {}).setdefault(found.default, []).append(
                f"{kind}/{flag}" if flag else kind)
        parts = []
        for mod, flags in sorted(by_mod.items()):
            said = [f"{'on' if on else 'off'}: {', '.join(flags[on])}" for on in (True, False) if on in flags]
            parts.append(f"{mod} ({'; '.join(said)})")
        return ("files gated on mod config flags were decided at each flag's default, cited from "
                "the mod's own source (portkit/data/config_flag_defaults.json); a pack that changes "
                "these options would load a different set. Assumed " + "; ".join(parts))


    def user_note(self) -> str | None:
        """One line naming the user-config flags that decided a file here."""
        used = sorted((k, f) for k, f in self.assumed.items() if f.user)
        if not used:
            return None
        said = ", ".join(f"{kind}/{flag}={'on' if f.default else 'off'}" if flag
                         else f"{kind}={'on' if f.default else 'off'}" for (kind, flag), f in used)
        return ("files gated on mod config flags set by user config (portkit convert --config) were "
                f"decided by that setting, not the cited default: {said}")


# -- user config (``portkit convert --config``) ------------------------------------

class ConfigError(ValueError):
    """A ``--config`` setting that is malformed or names no known flag."""


_TRUE = {"true", "on", "yes", "1"}
_FALSE = {"false", "off", "no", "0"}


@dataclass(frozen=True)
class ConfigRequest:
    """One setting as the user wrote it: ``<mod>.<name>=<value>``.

    ``value`` is the setting read as a flag (a bool) when it spells one, else
    as a number; ``raw`` keeps what was written, so a value option reads
    ``=1`` as the number 1 rather than ``true``.
    """

    mod: str
    name: str
    value: bool | float
    origin: str  # "--config" or the --config-file path
    raw: object = field(default=None, compare=False)

    @property
    def written(self):
        return self.value if self.raw is None else self.raw


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _bool(value, where: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in _TRUE | _FALSE:
        return value.strip().lower() in _TRUE
    raise ConfigError(f"{where}: value {value!r} is not true or false")


def _number(value, where: str) -> float:
    """A finite number, from a JSON/TOML number or its text (never a bool)."""
    out = None
    if _is_number(value):
        out = float(value)
    elif isinstance(value, str):
        try:
            out = float(value.strip())
        except ValueError:
            out = None
    if out is None or out != out or out in (float("inf"), float("-inf")):
        raise ConfigError(f"{where}: value {value!r} is not a number")
    return out


def _scalar(value, where: str) -> bool | float:
    """A setting as written: true/false (or on/off, yes/no, 1/0), else a number."""
    try:
        return _bool(value, where)
    except ConfigError:
        pass
    try:
        return _number(value, where)
    except ConfigError:
        raise ConfigError(f"{where}: value {value!r} is not true, false or a number") from None


def _split_key(key: str, where: str) -> tuple[str, str]:
    mod, dot, name = key.strip().partition(".")
    if not dot or not mod or not name:
        raise ConfigError(f"{where}: expected <mod>.<flag>, e.g. mythicmetals.enableDusts, not {key!r}")
    return mod, name


def parse_config_arg(text: str) -> ConfigRequest:
    """``<mod>.<flag>=<true|false>`` or ``<mod>.<option>=<number>`` from the command line."""
    key, sep, value = text.partition("=")
    where = f"--config {text!r}"
    if not sep:
        raise ConfigError(f"{where}: expected <mod>.<flag>=<true|false> or <mod>.<option>=<number>")
    mod, name = _split_key(key, where)
    return ConfigRequest(mod, name, _scalar(value, where), "--config", raw=value.strip())


def load_config_file(path: Path | str) -> list[ConfigRequest]:
    """Settings from a JSON or TOML file.

    Either nested (``{"mythicmetals": {"enableDusts": true}}``; in TOML a
    ``[mythicmetals]`` table) or flat (``{"mythicmetals.enableDusts": true}``).
    A ``.toml`` suffix reads TOML, anything else JSON. Top-level keys starting
    with ``_`` are ignored, so the ``config-overrides.json`` a run writes (its
    ``_settings`` key records what each setting replaced) reads back as is.
    """
    path = Path(path)
    where = f"--config-file {path}"
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ConfigError(f"{where}: {exc.strerror or exc}") from None
    try:
        data = tomllib.loads(text) if path.suffix.lower() == ".toml" else json.loads(text)
    except (tomllib.TOMLDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"{where}: not valid {'TOML' if path.suffix.lower() == '.toml' else 'JSON'}: {exc}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{where}: expected a mapping of <mod> to {{<flag>: true|false, <option>: number}}")
    out = []
    for key, value in data.items():
        if str(key).startswith("_"):
            continue
        if isinstance(value, dict):
            if "." in key:
                raise ConfigError(f"{where}: {key!r} holds a table; use a mod id as the table name")
            for name, setting in value.items():
                out.append(ConfigRequest(key, str(name), _scalar(setting, f"{where} {key}.{name}"), str(path),
                                         raw=setting))
        else:
            mod, name = _split_key(key, where)
            out.append(ConfigRequest(mod, name, _scalar(value, f"{where} {key}"), str(path), raw=value))
    return out


@dataclass
class KnownFlag:
    """A config flag this conversion can be told about."""

    condition: str
    flag: str  # "" for a condition with no argument
    mods: set[str]  # names accepted before the dot: the mod id and the condition namespace
    config_key: str | None = None  # the option's name in the mod's config file, cited
    default: bool | None = None  # cited default for this jar's version, when there is one
    url: str = ""

    @property
    def name(self) -> str:
        """The canonical name: the flag, or the condition's own name when it takes none."""
        return self.flag or _local(self.condition)

    @property
    def label(self) -> str:
        return f"{self.condition}/{self.flag}" if self.flag else self.condition


_BUILTIN_NS = ("forge", "neoforge", "fabric", "minecraft")


def _walk_conditions(cond, found: dict) -> None:
    if isinstance(cond, list):
        for c in cond:
            _walk_conditions(c, found)
        return
    if not isinstance(cond, dict):
        return
    kind = _kind(cond)
    if kind is None or ":" not in kind:
        return
    ns, local = kind.split(":", 1)
    if ns in _BUILTIN_NS:
        if local == "not":
            _walk_conditions(cond.get("value"), found)
        elif local in ("and", "or"):
            _walk_conditions(cond.get("values"), found)
        return
    args = {k: v for k, v in cond.items() if k not in ("type", "condition")}
    if not args:
        found.setdefault((kind, ""), True)
    elif len(args) == 1 and isinstance(next(iter(args.values())), str):
        found.setdefault((kind, next(iter(args.values()))), True)


def referenced_flags(root: Path) -> set[tuple[str, str]]:
    """(condition, flag) of every mod config condition the jar's recipes and loot tables use."""
    found: dict = {}
    data = Path(root) / "data"
    for ns_dir in sorted(p for p in data.iterdir() if p.is_dir()) if data.is_dir() else []:
        for lane in ("recipes", "recipe", "loot_tables", "loot_table"):
            # A loot table's top-level "conditions" is never a load condition.
            keys = _LOOT_ALL if lane.startswith("loot") else _ALL_KEYS
            base = ns_dir / lane
            for path in sorted(base.rglob("*.json")) if base.is_dir() else []:
                try:
                    body = json.loads(path.read_text(encoding="utf-8-sig"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if not isinstance(body, dict):
                    continue
                for key in keys:
                    if key in body:
                        _walk_conditions(body[key], found)
                if body.get("type") in CONDITIONAL_TYPES and isinstance(body.get("recipes"), list):
                    for entry in body["recipes"]:
                        if isinstance(entry, dict):
                            _walk_conditions(entry.get("conditions"), found)
                            inner = entry.get("recipe")
                            for key in _ALL_KEYS:
                                if isinstance(inner, dict) and key in inner:
                                    _walk_conditions(inner[key], found)
    return set(found)


def known_flags(root: Path, mods: dict[str, str] | None, namespaces=(),
                table: dict | None = None) -> list[KnownFlag]:
    """The flags a ``--config`` setting may name for this jar.

    Every flag the data file cites for a mod the jar declares (or ships a
    namespace for), at any version, with its config-key alias; plus every mod
    config condition the jar's own files use, cited or not.
    """
    owners = set(mods or ()) | set(namespaces)
    known: dict[tuple[str, str], KnownFlag] = {}
    for entry in flag_entries(table):
        if entry.get("mod") not in owners:
            continue
        kind = str(entry.get("condition"))
        version_matches = str(entry.get("version")) == (mods or {}).get(entry.get("mod"))
        for flag, found in (entry.get("flags") or {}).items():
            if not isinstance(found, dict):
                continue
            k = known.setdefault((kind, flag), KnownFlag(kind, flag, {entry["mod"], kind.partition(":")[0]}))
            if isinstance(found.get("config_key"), str):
                k.config_key = k.config_key or found["config_key"]
            if version_matches and isinstance(found.get("default"), bool):
                k.default, k.url = found["default"], str(found.get("url", ""))
    for kind, flag in referenced_flags(root):
        known.setdefault((kind, flag), KnownFlag(kind, flag, {kind.partition(":")[0]}))
    return [known[k] for k in sorted(known)]


@dataclass
class KnownValue:
    """A non-boolean config option this conversion can be told about."""

    mod: str
    option: str
    kind: str  # "double"
    minimum: float
    maximum: float
    default: float | None = None  # cited default for this jar's version
    url: str = ""

    @property
    def mods(self) -> set[str]:
        return {self.mod}


def known_values(mods: dict[str, str] | None, namespaces=(), table: dict | None = None) -> list[KnownValue]:
    """The value options a ``--config`` setting may name for this jar.

    Every option the data file cites for a mod the jar declares (or ships a
    namespace for), at any version; its default only where the version matches.
    """
    owners = set(mods or ()) | set(namespaces)
    known: dict[tuple[str, str], KnownValue] = {}
    for entry in value_entries(table):
        mod = entry.get("mod")
        if mod not in owners:
            continue
        version_matches = str(entry.get("version")) == (mods or {}).get(mod)
        for option, found in (entry.get("options") or {}).items():
            if not isinstance(found, dict) or not (_is_number(found.get("min")) and _is_number(found.get("max"))):
                continue
            k = known.setdefault((mod, option), KnownValue(mod, option, str(found.get("type", "double")),
                                                           float(found["min"]), float(found["max"])))
            if version_matches and _is_number(found.get("default")):
                k.default, k.url = float(found["default"]), str(found.get("url", ""))
                k.minimum, k.maximum = float(found["min"]), float(found["max"])
    return [known[k] for k in sorted(known)]


def _value_match(req: ConfigRequest, values: list[KnownValue]) -> KnownValue | None:
    mine = [v for v in values if v.mod == req.mod]
    exact = [v for v in mine if v.option == req.name]
    folded = [v for v in mine if v.option.lower() == req.name.lower()]
    found = exact or folded
    return found[0] if found else None


def _range(v: KnownValue) -> str:
    return f"{v.minimum:g} to {v.maximum:g}"


def resolve_config(requests: list[ConfigRequest], known: list[KnownFlag],
                   values: list[KnownValue] | None = None) -> tuple[dict, list[dict]]:
    """The settings as ``{(condition, flag): bool}``, and one record per flag set.

    Later requests win (``--config`` after ``--config-file``). A name matches a
    flag's canonical name or its cited config key (one key can stand for
    several flags, as Tinkers' ``glassRecipeFix`` does); an unknown mod or flag
    raises :class:`ConfigError` naming the valid ones. A name matching a cited
    value option (``values``) sets that option instead, as
    ``{(VALUE_KEY, "<mod>.<option>"): number}``; the number must lie in the
    range the mod's config accepts.
    """
    values = list(values or [])
    overrides: dict[tuple[str, str], bool | float] = {}
    records: dict[tuple[str, str], dict] = {}
    mods_with_flags = sorted({m for k in [*known, *values] for m in k.mods})
    for req in requests:
        where = f"{req.origin} {req.mod}.{req.name}"
        option = _value_match(req, values)
        if option is not None:
            number = _number(req.written, where)
            if not option.minimum <= number <= option.maximum:
                raise ConfigError(f"{where}: {number:g} is outside {_range(option)}, the range "
                                  f"{option.mod}'s config accepts for {option.option}")
            key = (VALUE_KEY, f"{option.mod}.{option.option}")
            overrides[key] = number
            records[key] = {
                "mod": req.mod,
                "flag": option.option,
                "condition": None,
                "value": number,
                "as_written": f"{req.mod}.{req.name}",
                "config_key": option.option,
                "cited_default": option.default,
                "default_source": option.url or None,
                "origin": req.origin,
                "range": [option.minimum, option.maximum],
            }
            continue
        if not isinstance(req.value, bool):
            flagish = [k for k in known if req.mod in k.mods and req.name.lower() in
                       (k.name.lower(), (k.config_key or "").lower())]
            if flagish:
                raise ConfigError(f"{where}: value {req.written!r} is not true or false")
        candidates = [k for k in known if req.mod in k.mods]
        mine_values = [v for v in values if v.mod == req.mod]
        if not candidates and not mine_values:
            have = (f"mods with config flags here: {', '.join(mods_with_flags)}" if mods_with_flags
                    else "this jar has no known mod config flags")
            raise ConfigError(f"{where}: no config flags are known for mod {req.mod!r} ({have})")
        matches = [k for k in candidates if req.name in (k.name, k.config_key)]
        if not matches:
            folded = req.name.lower()
            matches = [k for k in candidates
                       if folded in (k.name.lower(), (k.config_key or "").lower())]
        if not matches:
            valid = ", ".join([f"{k.name} ({k.config_key})" if k.config_key and k.config_key != k.name
                               else k.name for k in candidates]
                              + [f"{v.option} (a number, {_range(v)})" for v in mine_values])
            raise ConfigError(f"{where}: unknown config flag for {req.mod}; valid flags: {valid}")
        for k in matches:
            overrides[(k.condition, k.flag)] = req.value
            records[(k.condition, k.flag)] = {
                "mod": req.mod,
                "flag": k.name,
                "condition": k.label,
                "value": req.value,
                "as_written": f"{req.mod}.{req.name}",
                "config_key": k.config_key,
                "cited_default": k.default,
                "default_source": k.url or None,
                "origin": req.origin,
            }
    return overrides, [records[k] for k in sorted(records)]


def config_record(records: list[dict]) -> dict:
    """The settings as a ``--config-file`` mapping, canonical names: reproduces the run."""
    out: dict[str, dict[str, bool | float]] = {}
    for r in records:
        out.setdefault(r["mod"], {})[r["flag"]] = r["value"]
    return out


def config_note(records: list[dict]) -> str | None:
    """One line for the conversion notes listing every user config setting."""
    if not records:
        return None
    parts = []
    for r in records:
        alias = f" via {r['as_written']}" if r["as_written"] != f"{r['mod']}.{r['flag']}" else ""
        if r.get("condition") is None:  # a config value, not a flag
            default = ("uncited default" if r["cited_default"] is None
                       else f"default {r['cited_default']:g}")
            parts.append(f"{r['mod']}.{r['flag']}={r['value']:g} ({default}{alias})")
            continue
        default = ("uncited default" if r["cited_default"] is None
                   else f"default {'on' if r['cited_default'] else 'off'}")
        parts.append(f"{r['condition']}={'on' if r['value'] else 'off'} ({default}{alias})")
    return ("converted with mod config set by user config, which replaces the cited defaults "
            "(written to config-overrides.json; pass it back with --config-file to reproduce "
            "this output): " + "; ".join(parts))
