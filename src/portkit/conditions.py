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

A false condition and an undecidable one both make the file residue: the first
because Java doesn't load it, the second because shipping it would be a guess.

``conditions`` keys inside loot tables, loot modifiers and other mods' data
(Silent Gear traits) are loot predicates or the mod's own logic, not load
conditions; only the keys above, at the top level of a recipe or loot table,
are read here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .converters.tags import TagResolver
    from .model import SourceMod

FLAG_DATA = "config_flag_defaults.json"

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
    default: bool
    url: str


@lru_cache(maxsize=1)
def _flag_table() -> dict:
    text = resources.files("portkit.data").joinpath(FLAG_DATA).read_text(encoding="utf-8")
    return json.loads(text)


def flag_entries(table: dict | None = None) -> list[dict]:
    return list((table if table is not None else _flag_table()).get("entries") or [])


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

    def reason(self) -> str:
        """The residue reason for a verdict that isn't True."""
        if self.passes is False:
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
                 table: dict | None = None):
        self.mod = mod
        self._tags = tags
        self._table = table
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
            if flags and inner.passes:
                why = f"loads only when {', '.join(flags)} is off, and it is on by default"
            elif flags:
                why = f"loads when {', '.join(flags)} is off, as it is by default"
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
        return None, out

    def remember(self, verdict: Verdict) -> None:
        for found in verdict.assumed:
            self.assumed[(found.condition, found.flag)] = found

    def note(self) -> str | None:
        """One line naming every flag the conversion assumed at its cited default."""
        if not self.assumed:
            return None
        by_mod: dict[str, dict[bool, list[str]]] = {}
        for (kind, flag), found in sorted(self.assumed.items()):
            by_mod.setdefault(f"{found.mod} {found.version}", {}).setdefault(found.default, []).append(
                f"{kind}/{flag}" if flag else kind)
        parts = []
        for mod, flags in sorted(by_mod.items()):
            said = [f"{'on' if on else 'off'}: {', '.join(flags[on])}" for on in (True, False) if on in flags]
            parts.append(f"{mod} ({'; '.join(said)})")
        return ("files gated on mod config flags were decided at each flag's default, cited from "
                "the mod's own source (portkit/data/config_flag_defaults.json); a pack that changes "
                "these options would load a different set. Assumed " + "; ".join(parts))

