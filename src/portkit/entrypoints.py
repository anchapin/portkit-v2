"""The classes a mod loader constructs itself: a mod's entry classes (#280).

The bytecode readers (:mod:`portkit.blockcode`) treat the mod's classes and
its library jars as a closed world: code outside it (the game, the loader)
only calls in through what the mod hands it. One more way in is the loader
constructing a mod's entry class by reflection, which no class of the world
calls. Each loader names its entry classes in the mod's own metadata and
constructs each of them itself:

- **NeoForge** (``META-INF/neoforge.mods.toml``) and **Forge**
  (``META-INF/mods.toml``), language loader ``javafml``: the entry point is a
  class annotated ``@Mod`` whose value is one of the mod ids the file's
  ``[[mods]]`` tables declare, and the mod's initialisation happens in its
  constructor; ``@Mod(dist = ...)`` loads the class on the named physical
  side only (NeoForge docs, "Mod Files", "Mod Entrypoints / javafml and
  @Mod", https://docs.neoforged.net/docs/gettingstarted/modfiles#javafml-and-mod).
  The loader constructs each such class once: NeoForge's
  ``FMLModContainer#constructMod`` calls ``constructor.newInstance(..)`` once
  per entry class of the container (FancyModLoader df8b0a5,
  ``loader/src/main/java/net/neoforged/fml/javafmlmod/FMLModContainer.java``),
  and Forge's ``FMLModContainer#constructMod`` sets its one ``modInstance``
  (MinecraftForge 1.20.1,
  ``javafmllanguage/src/main/java/net/minecraftforge/fml/javafmlmod/FMLModContainer.java``).
- **Fabric** (``fabric.mod.json``): an entrypoint that refers to a class (or
  to an instance method of one, ``Class::method``) is "a new instance of the
  class"; the ``main`` entrypoints run on both sides, ``client`` and
  ``server`` on one physical side only, and other names only when some mod
  asks for them; "entrypoint instances are memoized by their name and also
  their type. Using the same code reference for multiple entrypoints will
  result in multiple instances" (Fabric wiki, "Entrypoints",
  https://wiki.fabricmc.net/documentation:entrypoint). A static method or
  field reference constructs nothing.
- **Quilt** (``quilt.mod.json``, ``quilt_loader.entrypoints``): the same JVM
  notation (Quilt RFC 0002, "JVM entrypoint notation",
  https://github.com/QuiltMC/rfcs/blob/main/specification/0002-quilt.mod.json.md);
  ``init`` is taken as Fabric's ``main`` (DEFAULT, see docs/decisions.md
  2026-10-19), and Fabric entrypoints in a Quilt jar's ``fabric.mod.json``
  as Fabric's.

Each :class:`EntryClass` says whether its class is constructed exactly once
on every side (``once``) or at most once per reference on some side only
(client- or server-only, or a name another mod may or may not request).
Only the metadata decides; no mod or library is named here.
"""
from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass

_MOD_ANNOTATIONS = ("Lnet/neoforged/fml/common/Mod;", "Lnet/minecraftforge/fml/common/Mod;")
_TOMLS = ("META-INF/neoforge.mods.toml", "META-INF/mods.toml")
# The entrypoint names whose classes run on both sides (Fabric "main",
# Quilt "init"); every other name runs on one side or on request only.
_EVERY_SIDE = {"fabric.mod.json": ("main",), "quilt.mod.json": ("init",)}


@dataclass(frozen=True)
class EntryClass:
    name: str          # internal name, com/example/ExampleMod
    once: bool         # constructed exactly once, on every side
    source: str        # the metadata file that declares it, and how


def _mod_ids(data: bytes) -> set[str]:
    try:
        parsed = tomllib.loads(data.decode("utf-8", "replace"))
    except (tomllib.TOMLDecodeError, ValueError):
        return set()
    if parsed.get("modLoader", "javafml") != "javafml":
        return set()  # another language loader decides its own entry points
    return {m["modId"] for m in parsed.get("mods", []) if isinstance(m, dict) and isinstance(m.get("modId"), str)}


def _both_sides(dist) -> bool:
    """Whether an ``@Mod(dist = ...)`` value names both physical sides (no
    ``dist`` element at all is both: the annotation's default)."""
    if dist is None:
        return True
    values = dist if isinstance(dist, tuple) else (dist,)
    names = {v[1] for v in values if isinstance(v, tuple) and len(v) == 2}
    return {"CLIENT", "DEDICATED_SERVER"} <= names


def _jvm_class(ref) -> tuple[str | None, bool]:
    """The class a JVM-notation entrypoint value constructs, and whether it
    constructs one: ``Class`` does; ``Class::member`` does only for an
    instance method, which the metadata alone can't tell from a static one
    or a field (None, False: the caller looks at the class)."""
    if isinstance(ref, dict):
        if ref.get("adapter", "default") not in ("default", "java"):
            return None, False  # another language adapter (Kotlin objects ...)
        ref = ref.get("value")
    if not isinstance(ref, str) or not ref:
        return None, False
    if "::" in ref:
        return ref.split("::", 1)[0].replace(".", "/"), False
    return ref.replace(".", "/"), True


def _member_constructs(classes, cls: str, member: str) -> bool | None:
    """Whether ``Class::member`` constructs ``cls``: True for an instance
    method, False for a static method or a field, None when the class isn't
    there or the name is ambiguous (the loader refuses that)."""
    cf = classes.get(cls) if classes is not None else None
    if cf is None:
        return None
    methods = [m for m in cf.methods if m.name == member]
    if member in cf.fields:
        return False if not methods else None
    if len(methods) != 1:
        return None
    return not methods[0].access & 0x0008


def _fabric_like(data: bytes, file: str, classes) -> list[tuple[str, str, bool]]:
    """(class, entrypoint name, constructs) for each reference in a Fabric or
    Quilt metadata file; a reference whose construction can't be told counts
    as constructing."""
    try:
        parsed = json.loads(data.decode("utf-8", "replace"))
    except ValueError:
        return []
    if not isinstance(parsed, dict):
        return []
    points = parsed.get("entrypoints") if file == "fabric.mod.json" \
        else (parsed.get("quilt_loader") or {}).get("entrypoints")
    if not isinstance(points, dict):
        return []
    out = []
    for key, refs in points.items():
        for ref in refs if isinstance(refs, list) else [refs]:
            cls, constructs = _jvm_class(ref)
            if cls is None:
                continue
            if not constructs:
                raw = ref.get("value") if isinstance(ref, dict) else ref
                member = _member_constructs(classes, cls, raw.split("::", 1)[1])
                constructs = member is not False
            if constructs:
                out.append((cls, key, True))
    return out


def entry_classes(metadatas, classes) -> list[EntryClass]:
    """The entry classes each loader metadata set in ``metadatas`` (one
    ``{path: bytes}`` per jar: the mod's, then each library's) declares,
    as found in ``classes`` (a :class:`portkit.bytecode.ClassIndex`)."""
    found: dict[str, list[tuple[bool, str]]] = {}
    for meta in metadatas or ():
        # A jar shipping both a mods.toml and a neoforge.mods.toml (one per
        # loader) has each @Mod class constructed by the one loader running.
        toml = next((t for t in _TOMLS if t in meta), None)
        ids = _mod_ids(meta[toml]) if toml else set()
        for cname in _annotated(classes) if ids else ():
            cf = classes.get(cname)
            for desc in _MOD_ANNOTATIONS:
                ann = cf.annotations.get(desc) if cf is not None else None
                if ann is not None and ann.get("value") in ids:
                    both = _both_sides(ann.get("dist"))
                    found.setdefault(cname, []).append(
                        (both, f"{toml} mod id {ann['value']!r}, @Mod"
                               f"{'' if both else ' on one physical side only'}"))
                    break
        for file in ("fabric.mod.json", "quilt.mod.json"):
            if file not in meta:
                continue
            for cls, key, _ in _fabric_like(meta[file], file, classes):
                found.setdefault(cls, []).append(
                    (key in _EVERY_SIDE[file], f"{file} entrypoint {key!r}"))
    out = []
    for cname, uses in sorted(found.items()):
        # Exactly once only for one reference that runs on every side: two
        # references are two instances (Fabric memoizes per name and type),
        # and a one-side or on-request reference may be none.
        once = len(uses) == 1 and uses[0][0]
        out.append(EntryClass(cname, once, "; ".join(u[1] for u in uses)))
    return out


def _annotated(classes) -> list[str]:
    """Every class, the mod's or a library's, whose bytes mention a ``@Mod``
    annotation type (a cheap scan before parsing)."""
    if classes is None:
        return []
    names = []
    for src in (classes._raw, getattr(classes, "_lib", {})):
        for k, raw in src.items():
            if any(d.encode() in raw for d in _MOD_ANNOTATIONS):
                names.append(k)
    return sorted(set(names))
