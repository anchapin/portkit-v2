"""Leftover worldgen and other mods' data (#277): explained from the jar, not converted.

A file under ``data/<ns>/`` that no converter read is ``unowned`` residue
(:func:`portkit.pipeline.unowned`). Worldgen proper is #281's; this module only
re-files the leftovers the jar itself explains (Alex's picks 1a, 2a and 3a on
PR #316, 2026-10-17, ``docs/decisions.md``):

* ``code_worldgen``: a worldgen file whose ``type`` is the mod's own Java class.
  Minecraft's feature, placement-modifier and pool-element types are registry
  entries only code registers, so a type in one of the jar's own namespaces is
  the mod's code (#87: the reason names the type and the jar's classes that
  name its path). Read here:

  - ``worldgen/configured_feature/``: ``"type": "<ns>:<feature>"``;
  - ``worldgen/placed_feature/``: a ``placement`` modifier ``"type": "<ns>:..."``;
  - ``worldgen/template_pool/``: an element whose ``element_type`` is ``<ns>:...``.

  Worldgen built from ``minecraft:`` types only stays ``unowned`` (a real #281
  gap). A placed feature with only vanilla placements stays ``unowned`` too,
  even when the feature it places is code.

* ``other_mod_data``: ``data/<ns>/<dir>/`` where ``<dir>`` is not a folder
  Minecraft or a mod loader reads, and every file in it is a JSON object whose
  top-level ``type`` or ``target_*`` names a namespace that is not the jar's own,
  vanilla's or a loader's. Only that other mod reads it.

* A structure template (``data/<ns>/structure[s]/<path>.nbt``) named only by
  data files that are residue of these two kinds goes with them: ``code_worldgen``
  when one of them is, else ``other_mod_data``. A template no data file names
  stays ``unowned``.

Adapters may file more of either kind with their own citations (Waystones'
village pools and its Unbreakables rules, :mod:`portkit.adapters.waystones.worldgen`);
their entries count as residue of the kind here. Nothing here names a mod.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .model import Unhandled

CODE_WORLDGEN = "code_worldgen"
OTHER_MOD_DATA = "other_mod_data"
KINDS = frozenset({CODE_WORLDGEN, OTHER_MOD_DATA})

# Namespaces that are not another mod's: vanilla's, the common tag namespace
# and the loaders'.
_SHARED = frozenset({"minecraft", "c", "forge", "neoforge", "fabric", "quilt"})

# Folders of data/<ns>/ that Minecraft (1.16 to 1.21.x, plural and singular
# names) or a mod loader reads. Anything else is a mod's own reloader's.
_VANILLA_DIRS = frozenset({
    "advancement", "advancements", "recipe", "recipes", "loot_table", "loot_tables",
    "item_modifier", "item_modifiers", "predicate", "predicates", "function", "functions",
    "tags", "structure", "structures", "worldgen", "dimension", "dimension_type",
    "damage_type", "chat_type", "trim_material", "trim_pattern", "banner_pattern",
    "enchantment", "enchantment_provider", "jukebox_song", "painting_variant", "wolf_variant",
    "wolf_sound_variant", "cat_variant", "chicken_variant", "cow_variant", "frog_variant",
    "pig_variant", "instrument", "trial_spawner", "test_instance", "test_environment",
    "dialog", "datapacks",
    # Loader folders: NeoForge data maps, Forge/NeoForge loot modifiers and
    # the loaders' own sub-folders (biome modifiers, ...).
    "neoforge", "forge", "fabric", "quilt", "data_maps", "loot_modifiers",
})

_WORLDGEN = re.compile(r"^data/([^/]+)/worldgen/(configured_feature|placed_feature|template_pool)/(.+)\.json$")
_STRUCTURE = re.compile(r"^data/([^/]+)/(structure|structures)/(.+)\.nbt$")
_DATA_DIR = re.compile(r"^data/([^/]+)/([^/]+)/")

_MAX_CITED = 2


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def _ns(value) -> str | None:
    if isinstance(value, str) and ":" in value:
        ns = value.split(":", 1)[0]
        if re.fullmatch(r"[a-z0-9_.-]+", ns):
            return ns
    return None


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def _element_types(value):
    """Every ``element_type`` in a template pool, delegates included."""
    if isinstance(value, dict):
        for k, v in value.items():
            if k == "element_type" and isinstance(v, str):
                yield v
            else:
                yield from _element_types(v)
    elif isinstance(value, list):
        for v in value:
            yield from _element_types(v)


# Minecraft's packages for what a worldgen type is an instance of, by folder
# (Mojang names: NeoForge jars, or Forge/Fabric jars read through mappings).
_BASES = {
    "configured_feature": "net/minecraft/world/level/levelgen/feature/",
    "placed_feature": "net/minecraft/world/level/levelgen/placement/",
    "template_pool": "net/minecraft/world/level/levelgen/structure/pools/",
}


class _Citations:
    """Which of the jar's classes name a string, read once on demand."""

    def __init__(self, classes):
        self.classes = classes
        self._pools: dict[str, frozenset[str]] | None = None
        self._impl: dict[str, list[tuple[str, str]]] = {}

    def _load(self) -> dict[str, frozenset[str]]:
        if self._pools is None:
            self._pools = {}
            if self.classes is not None:
                for name in self.classes.names():
                    cf = self.classes.get(name)
                    if cf is None:
                        continue
                    found: set[str] = set()
                    for i, entry in enumerate(cf.pool):
                        if not isinstance(entry, tuple) or not entry:
                            continue
                        try:
                            value = cf.constant(i)
                        except Exception:  # noqa: BLE001 - an odd pool entry is skipped
                            continue
                        if isinstance(value, str):
                            found.add(value)
                    self._pools[name] = frozenset(found)
        return self._pools

    def implementors(self, folder: str | None) -> list[tuple[str, str]]:
        """(class, Minecraft superclass) for the jar's classes that extend a
        class of the folder's Minecraft package."""
        base = _BASES.get(folder or "")
        if base is None or self.classes is None:
            return []
        if folder not in self._impl:
            from .codeonly import _supers

            out = []
            for name in self._load():
                for sup in _supers(self.classes, name):
                    if sup.startswith(base):
                        out.append((name, sup))
                        break
            self._impl[folder] = out
        return self._impl[folder]

    def phrase(self, text: str, rank: list[str] = (), folder: str | None = None) -> str:
        """The jar's classes whose constant pool holds ``text`` exactly: first
        those naming one of the jar's own subclasses of the folder's Minecraft
        type (the registering class), then those naming most of ``rank``."""
        if self.classes is None:
            return f"the source has no classes to name `{text}`"
        pools = self._load()
        impl = dict(self.implementors(folder))
        hits = [n for n, s in pools.items() if text in s]
        if not hits:
            return f"no class of the jar names `{text}` as a string"

        def names_impl(n: str) -> list[str]:
            return sorted(c for c in impl if c != n and c in pools[n])

        hits.sort(key=lambda n: (-len(names_impl(n)), -sum(1 for r in rank if r in pools[n]), n))
        shown = []
        for n in hits[:_MAX_CITED]:
            subs = names_impl(n)
            shown.append(n + (f" (names {subs[0]}, a subclass of {impl[subs[0]]})" if subs else ""))
        return f"the jar's classes naming `{text}`: " + ", ".join(shown)


def _leftover(root: Path, groups: list[Unhandled], consumed: set[str]) -> list[str]:
    out: list[str] = []
    for u in groups:
        base = root / u.source.rstrip("/")
        if base.is_dir():
            out += [p.relative_to(root).as_posix() for p in sorted(base.rglob("*"))
                    if p.is_file() and p.relative_to(root).as_posix() not in consumed]
    return out


def _code_worldgen(rel: str, root: Path, own: set[str], cite: _Citations, rank: list[str]) -> str | None:
    m = _WORLDGEN.match(rel)
    if not m:
        return None
    doc = _read(root / rel)
    if not isinstance(doc, dict):
        return None
    folder = m.group(2)
    if folder == "configured_feature":
        kind = doc.get("type")
        if _ns(kind) in own:
            return (f"a configured feature of type `{kind}`, a feature the mod's Java code registers, so "
                    f"what it places and how is code ({cite.phrase(kind.split(':', 1)[1], rank, folder)})")
        return None
    if folder == "placed_feature":
        placement = doc.get("placement")
        types = sorted({p["type"] for p in placement if isinstance(p, dict) and _ns(p.get("type")) in own}) \
            if isinstance(placement, list) else []
        if types:
            feature = doc.get("feature") if isinstance(doc.get("feature"), str) else "an inline feature"
            return (f"a placed feature of `{feature}` whose placement modifier "
                    + ", ".join(f"`{t}`" for t in types)
                    + f" is the mod's Java code, so where and how often it places is code "
                    f"({cite.phrase(types[0].split(':', 1)[1], rank, folder)})")
        return None
    types = sorted({t for t in _element_types(doc.get("elements")) if _ns(t) in own})
    if types:
        return (f"a template pool whose element type " + ", ".join(f"`{t}`" for t in types)
                + f" is the mod's Java code ({cite.phrase(types[0].split(':', 1)[1], rank, folder)})")
    return None


def _other_mod_dirs(root: Path, files: list[str], own: set[str], cite: _Citations) -> dict[str, str]:
    """rel -> reason for every file of a non-vanilla data folder whose files all
    name another mod's namespace in ``type`` or ``target_*``."""
    by_dir: dict[str, list[str]] = {}
    for rel in files:
        m = _DATA_DIR.match(rel)
        if m and m.group(2) not in _VANILLA_DIRS:
            by_dir.setdefault(f"data/{m.group(1)}/{m.group(2)}/", []).append(rel)
    out: dict[str, str] = {}
    for folder, members in sorted(by_dir.items()):
        named: dict[str, set[str]] = {}
        ok = True
        for rel in members:
            doc = _read(root / rel) if rel.endswith(".json") else None
            if not isinstance(doc, dict):
                ok = False
                break
            values = [doc.get("type")] + [v for k, v in doc.items() if k.startswith("target_")]
            foreign = {_ns(v): v for v in values if _ns(v) and _ns(v) not in own and _ns(v) not in _SHARED}
            if not foreign:
                ok = False
                break
            for ns, value in foreign.items():
                named.setdefault(ns, set()).add(value)
        if not ok:
            continue
        mods = ", ".join(f"`{ns}` (e.g. `{sorted(v)[0]}`)" for ns, v in sorted(named.items()))
        cited = "; ".join(cite.phrase(ns) for ns in sorted(named))
        reason = (f"`{folder.split('/')[2]}/` is not a data folder Minecraft or the mod loader reads, and each "
                  f"of its {len(members)} file(s) is typed or targeted at another mod's namespace, {mods}, so "
                  f"only that mod reads it and it isn't converted with this jar ({cited})")
        for rel in members:
            out[rel] = reason
    return out


def _structure_owners(root: Path, structures: list[str], explained: dict[str, str]) -> dict[str, tuple[str, str]]:
    """rel -> (kind, reason) for each structure template every data file naming
    it is explained residue of these kinds."""
    ids = {}
    for rel in structures:
        m = _STRUCTURE.match(rel)
        if m:
            ids[f"{m.group(1)}:{m.group(3)}"] = rel
    if not ids:
        return {}
    users: dict[str, set[str]] = {}
    data = root / "data"
    for path in sorted(data.rglob("*.json")) if data.is_dir() else []:
        doc = _read(path)
        if doc is None:
            continue
        rel = path.relative_to(root).as_posix()
        for s in set(_strings(doc)):
            if s in ids:
                users.setdefault(s, set()).add(rel)
    out: dict[str, tuple[str, str]] = {}
    for ident, rel in sorted(ids.items()):
        named_by = users.get(ident)
        if not named_by or any(u not in explained for u in named_by):
            continue
        kinds = {explained[u] for u in named_by}
        kind = CODE_WORLDGEN if CODE_WORLDGEN in kinds else OTHER_MOD_DATA
        # The code_worldgen users first: they say why the template generates at all.
        shown = sorted(named_by, key=lambda u: (explained[u] != CODE_WORLDGEN, u))
        listed = ", ".join(f"{u.split('/', 2)[2]} ({explained[u]})" for u in shown[:3])
        more = f" and {len(shown) - 3} more" if len(shown) > 3 else ""
        out[rel] = (kind, f"a structure template (`{ident}`) only {len(shown)} data file(s) name, all "
                          f"residue of their own: {listed}{more}; it goes with them")
    return out


def _group(rel: str) -> str:
    parts = rel.split("/")
    if len(parts) > 4 and parts[2] == "worldgen":
        return "/".join(parts[:4]) + "/"
    return "/".join(parts[:3]) + "/"


def refine(unhandled: list[Unhandled], root: Path, consumed: set[str], namespaces: set[str],
           classes=None) -> list[Unhandled]:
    """Re-file the unowned worldgen, structure and other-mod data files the jar
    explains; the rest of the residue is returned unchanged."""
    groups = [u for u in unhandled if u.kind == "unowned" and u.source.startswith("data/")]
    if not groups:
        return unhandled
    root = Path(root)
    own = set(namespaces)
    leftover = _leftover(root, groups, consumed)
    cite = _Citations(classes)
    # Paths of the jar's own worldgen types, to rank the registering class first.
    rank: list[str] = []
    for rel in leftover:
        if _WORLDGEN.match(rel):
            doc = _read(root / rel)
            for s in _strings(doc) if doc is not None else ():
                if _ns(s) in own:
                    rank.append(s.split(":", 1)[1])
    rank = sorted(set(rank))

    found: dict[str, tuple[str, str]] = {}
    for rel in leftover:
        reason = _code_worldgen(rel, root, own, cite, rank)
        if reason:
            found[rel] = (CODE_WORLDGEN, reason)
    for rel, reason in _other_mod_dirs(root, [r for r in leftover if r not in found], own, cite).items():
        found[rel] = (OTHER_MOD_DATA, reason)
    # Explained residue that names a structure: this pass's and any entry of
    # these kinds an adapter filed per file.
    explained = {rel: kind for rel, (kind, _) in found.items()}
    for u in unhandled:
        if u.kind in KINDS and not u.source.endswith("/"):
            explained[u.source] = u.kind
    structures = [r for r in leftover if _STRUCTURE.match(r) and r not in found]
    for rel, (kind, reason) in _structure_owners(root, structures, explained).items():
        path = _STRUCTURE.match(rel).group(3)
        found[rel] = (kind, reason + f" ({cite.phrase(path)})")

    entries: dict[tuple[str, str, str], int] = {}
    for rel, (kind, reason) in sorted(found.items()):
        if kind == OTHER_MOD_DATA and _STRUCTURE.match(rel) is None:
            key = (kind, _group(rel), reason)
        else:
            key = (kind, rel, reason)
        entries[key] = entries.get(key, 0) + 1
    refiled = [Unhandled(source=src, kind=kind, reason=reason, count=n)
               for (kind, src, reason), n in sorted(entries.items())]

    out: list[Unhandled] = []
    for u in unhandled:
        if u not in groups:
            out.append(u)
            continue
        left = sum(1 for f in leftover if f.startswith(u.source) and f not in found)
        if left:
            out.append(Unhandled(source=u.source, kind="unowned",
                                 reason=f"{left} file(s) no converter claims yet", count=left))
    return out + refiled
