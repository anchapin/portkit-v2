"""Leftover damage types (#442): Bedrock has no registry to define one in.

A Java damage type (``data/<ns>/damage_type/*.json``) no converter claimed is
``unowned`` residue (:func:`portkit.pipeline.unowned`). Java's damage types are
data-driven: a file defines the type's message, its scaling and its effects
(minecraft.wiki, "Damage type"), and the code that hurts an entity names the
type it hurts with.

Bedrock has no data-driven damage types. The causes a pack can apply are the
fixed ``EntityDamageCause`` enum (@minecraft/server 2.0.0, learn.microsoft.com,
@minecraft/server "EntityDamageCause"): there is no damage-type registry a pack
could define a type in, so a Java damage type has nowhere to go and its
effects (exhaustion, scaling, the death message) are not carried over.

This module re-files the damage types the jar defines under the explained kind
``no_bedrock_damage_type``: the reason names the file count and the Bedrock
side. Only files that read as JSON objects are re-filed, the way
:mod:`portkit.advancements` does it: a file Java's own reader would reject
stays ``unowned``. Files a converter already claimed are left alone. Nothing is
converted and nothing is written (#87). Nothing here names a mod.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .model import Unhandled

NO_BEDROCK = "no_bedrock_damage_type"
KINDS = frozenset({NO_BEDROCK})

# Java's damage type folder (minecraft.wiki, "Damage type": the files of
# data/<ns>/damage_type/ define the registry's entries).
_DAMAGE_TYPE = re.compile(r"^data/[^/]+/damage_type/[^/]+\.json$")

# The Bedrock side: the fixed enum of causes a pack can apply (@minecraft/server
# 2.0.0, EntityDamageCause).
_NO_REGISTRY = ("Bedrock has no data-driven damage types: the causes a pack can apply are the fixed "
                "EntityDamageCause enum (@minecraft/server 2.0.0), so there is no damage-type registry "
                "to define a type in and the type's effects are not carried over")


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def _group(rel: str) -> str:
    parts = rel.split("/")
    return "/".join(parts[:3]) + "/"


def _shown(names: list[str]) -> str:
    names = sorted(dict.fromkeys(names))
    return ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else "")


def classify(root: Path, files: list[str]) -> dict[str, str]:
    """file -> the id of the damage type it defines, for every damage-type file
    of the jar Java's own reader would accept; a file it can't is left out (it
    stays ``unowned``)."""
    root = Path(root)
    out: dict[str, str] = {}
    for rel in files:
        if not _DAMAGE_TYPE.match(rel):
            continue
        doc = _read(root / rel)
        if not isinstance(doc, dict):
            continue
        out[rel] = rel.rsplit("/", 1)[-1][:-5]
    return out


def refine(unhandled: list[Unhandled], root: Path, consumed: set[str]) -> list[Unhandled]:
    """Re-file the unowned damage types the jar explains; the rest of the
    residue is returned unchanged."""
    groups = [u for u in unhandled if u.kind == "unowned"
              and re.match(r"^data/[^/]+/damage_type/", u.source)]
    if not groups:
        return unhandled
    root = Path(root)
    leftover: list[str] = []
    for u in groups:
        base = root / u.source.rstrip("/")
        if base.is_dir():
            leftover += [p.relative_to(root).as_posix() for p in sorted(base.rglob("*"))
                         if p.is_file() and p.relative_to(root).as_posix() not in consumed]
    found = classify(root, leftover)

    entries: dict[str, list[str]] = {}
    for rel, name in sorted(found.items()):
        entries.setdefault(_group(rel), []).append(name)
    refiled: list[Unhandled] = []
    for group, names in sorted(entries.items()):
        refiled.append(Unhandled(source=group, kind=NO_BEDROCK,
                                 reason=f"{len(names)} damage type(s) (e.g. {_shown(names)}): {_NO_REGISTRY}",
                                 count=len(names)))

    gone = set(found)
    out: list[Unhandled] = []
    for u in unhandled:
        if u not in groups:
            out.append(u)
            continue
        left = sum(1 for f in leftover if f.startswith(u.source) and f not in gone)
        if left:
            out.append(Unhandled(source=u.source, kind="unowned",
                                 reason=f"{left} file(s) no converter claims yet", count=left))
    return out + refiled
