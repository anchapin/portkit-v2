"""Who owns a leftover model or texture (#277: unowned textures and models).

A file no converter claimed is ``unowned`` residue (:func:`portkit.pipeline.unowned`).
For the models and textures under ``assets/<ns>/``, the jar itself says who would
use them: a blockstate or item definition names models, a model names its
parent, its textures and its override models, a particle definition names its
sprites. Following those references back gives one of three answers:

* every user is residue on its own account (a block whose blockstate the block
  converter refused, a particle definition no converter reads): the file is
  ``owned_by_residue``, and ships with its owner when the owner converts;
* nothing in the jar's JSON names it, or only files that are themselves read
  only by Java code: it is a ``java_only_asset``, drawn by the mod's code
  (screens, entity and block-entity renderers, effect icons, armor layers,
  custom model loaders) and nothing a Bedrock pack has would draw it. An
  ``atlases/`` file is one too: it lists textures for Java's texture stitcher,
  and Bedrock packs have no atlas;
* a user shipped and the file still wasn't claimed: a converter missed it, and
  it stays ``unowned``.

Only the first two are re-filed; both are explained kinds (the residue agent's
SKIP_KINDS). Nothing here is mod-specific: the answers come from the jar's own
references.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .model import Unhandled

OWNED = "owned_by_residue"
JAVA_ONLY = "java_only_asset"
KINDS = frozenset({OWNED, JAVA_ONLY})

_ASSET_DIRS = ("models", "textures", "atlases")
_REFERRERS = re.compile(r"^assets/([^/]+)/(blockstates|models|items|particles)/(.+)\.json$")
# Keys of a model whose string values are not resource locations of a model
# or texture.
_NOT_REFS = frozenset({"loader", "type", "render_type", "gui_light", "name", "comment", "__comment"})

_SHIPPED, _GAP = "shipped", "gap"


def _location(value: str, default_ns: str = "minecraft") -> tuple[str, str] | None:
    value = value.split("#", 1)[0].strip()
    if not value or value.startswith("#") or " " in value:
        return None
    ns, _, path = value.rpartition(":")
    if not re.fullmatch(r"[a-z0-9_.\-]*", ns) or not re.fullmatch(r"[a-z0-9_./\-]+", path):
        return None
    return (ns or default_ns, path)


def _strings(value, key: str = ""):
    if isinstance(value, str):
        if key not in _NOT_REFS:
            yield key, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _strings(v, str(k))
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v, key)


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def references(root: Path) -> dict[str, set[str]]:
    """file -> the files that name it, for every model and texture a
    blockstate, item definition, model or particle definition of the jar names."""
    root = Path(root)
    users: dict[str, set[str]] = {}

    def add(target: str, user: str) -> None:
        if target != user and (root / target).is_file():
            users.setdefault(target, set()).add(user)

    assets = root / "assets"
    if not assets.is_dir():
        return users
    for path in sorted(assets.rglob("*.json")):
        rel = str(path.relative_to(root))
        m = _REFERRERS.match(rel)
        if not m:
            continue
        lane = m.group(2)
        doc = _read(path)
        if doc is None:
            continue
        # A model's "textures" map names textures, never models: Java reads
        # its values only as texture locations (or #variables). Elsewhere in a
        # model, which one a string is shows on disk (#350: a texture named
        # like a Java-only model is not that model's user).
        if lane == "models" and isinstance(doc, dict) and isinstance(doc.get("textures"), dict):
            for value in doc["textures"].values():
                if isinstance(value, dict):  # 1.21.5+: {"sprite": ..., ...}
                    value = value.get("sprite")
                loc = _location(value) if isinstance(value, str) else None
                if loc is not None:
                    add(f"assets/{loc[0]}/textures/{loc[1]}.png", rel)
            doc = {k: v for k, v in doc.items() if k != "textures"}
        for key, value in _strings(doc):
            loc = _location(value)
            if loc is None:
                continue
            ns, p = loc
            if lane in ("blockstates", "items"):
                if key == "model":
                    add(f"assets/{ns}/models/{p}.json", rel)
            elif lane == "particles":
                add(f"assets/{ns}/textures/particle/{p}.png", rel)
            else:
                # A model names models (parent, overrides, a loader's parts)
                # and textures; which one a string is shows on disk. A name
                # with its own extension is a file under assets/<ns>/ (an OBJ
                # model loader's "ns:models/block/x.obj").
                add(f"assets/{ns}/models/{p}.json", rel)
                add(f"assets/{ns}/textures/{p}.png", rel)
                if "." in p.rsplit("/", 1)[-1]:
                    add(f"assets/{ns}/{p}", rel)
    # A Wavefront model names its material library ("mtllib x.mtl"), a file
    # next to it.
    for path in sorted(assets.glob("*/models/**/*")):
        if not path.is_file() or path.suffix == ".json":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(path.relative_to(root))
        for line in text.splitlines():
            if line.startswith("mtllib "):
                add(str(path.parent.relative_to(root) / line.split(None, 1)[1].strip()), rel)
    return users


def _subject(rel: str) -> str | None:
    parts = rel.split("/")
    if len(parts) < 4 or parts[0] != "assets" or parts[2] not in _ASSET_DIRS:
        return None
    return parts[2]


def classify(root: Path, files: list[str], consumed: set[str],
             residue_sources: set[str], shipped: set[str] | None = None) -> dict[str, tuple[str, str]]:
    """file -> (kind, owner) for the leftover files that are owned by residue
    or Java-only; a file a converter should have claimed is left out.

    ``shipped``: the identifiers the pack defines. An item model the items
    converter read (``models/item/<name>.json``) for an item the pack doesn't
    ship, whose blockstate of the same name is residue, is the refused block's
    item: what it names goes with that block's residue."""
    users = references(root)
    memo: dict[str, tuple[str, str]] = {}

    def status(rel: str, seen: frozenset) -> tuple[str, str]:
        if rel in memo:
            return memo[rel]
        if rel in residue_sources:
            return (OWNED, rel)
        if rel in consumed:
            parts = rel.split("/")
            if (shipped is not None and len(parts) == 5 and parts[2:4] == ["models", "item"]
                    and f"{parts[1]}:{parts[4][:-5]}" not in shipped):
                block = f"assets/{parts[1]}/blockstates/{parts[4]}"
                if block in residue_sources:
                    return (OWNED, block)
            return (_SHIPPED, rel)
        if rel in seen:  # a reference cycle adds nothing
            return (JAVA_ONLY, "")
        lane = rel.split("/")[2] if rel.count("/") >= 2 else ""
        if lane in ("blockstates", "items"):
            # Neither claimed nor residue: a converter skipped it, so whatever
            # it names is skipped with it, not explained.
            return (_GAP, rel)
        if lane == "particles":
            # Particle definitions are unowned residue of their own (no
            # converter reads them yet); their sprites go with them.
            return (OWNED, rel)
        answers = [status(u, seen | {rel}) for u in sorted(users.get(rel, ()))]
        if lane == "atlases":
            got = (JAVA_ONLY, "atlas")
        elif not answers:
            got = (JAVA_ONLY, "")
        elif any(a[0] in (_SHIPPED, _GAP) for a in answers):
            got = (_GAP, "")
        elif any(a[0] == OWNED for a in answers):
            got = next(a for a in answers if a[0] == OWNED)
        else:
            got = (JAVA_ONLY, "user")
        memo[rel] = got
        return got

    out: dict[str, tuple[str, str]] = {}
    for rel in files:
        if _subject(rel) is None:
            continue
        target = rel[:-len(".mcmeta")] if rel.endswith(".png.mcmeta") else rel
        if not target.endswith((".json", ".png")) and target.split("/")[2] != "models":
            continue
        parts = target.split("/")
        if parts[2] == "models" and len(parts) == 5 and parts[3] == "item" and not users.get(target):
            # Java loads models/item/<id>.json for every registered item by
            # name, so an unclaimed one may be an item's own model: not ours
            # to explain.
            continue
        kind, owner = status(target, frozenset())
        if kind in KINDS:
            out[rel] = (kind, owner)
    return out


def _group(rel: str) -> str:
    parts = rel.split("/")
    return "/".join(parts[:4]) + "/" if len(parts) > 4 else "/".join(parts[:3]) + "/"


def refine(unhandled: list[Unhandled], root: Path, consumed: set[str],
           shipped: set[str] | None = None) -> list[Unhandled]:
    """Re-file the unowned models, textures and atlases the jar's references
    explain; the rest of the residue is returned unchanged."""
    groups = [u for u in unhandled if u.kind == "unowned" and _subject(u.source.rstrip("/") + "/x") is not None]
    if not groups:
        return unhandled
    root = Path(root)
    leftover: list[str] = []
    for u in groups:
        base = root / u.source.rstrip("/")
        if base.is_dir():
            leftover += [str(p.relative_to(root)) for p in sorted(base.rglob("*"))
                         if p.is_file() and str(p.relative_to(root)) not in consumed]
    sources = {u.source for u in unhandled if u.kind != "unowned"}
    # An unowned particle definition is residue too; its sprites point at it.
    sources |= {f for f in (str(p.relative_to(root)) for p in (root / "assets").glob("*/particles/*.json"))
                if f not in consumed} if (root / "assets").is_dir() else set()
    found = classify(root, leftover, consumed, sources, shipped)

    entries: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for rel, (kind, owner) in sorted(found.items()):
        entries.setdefault((kind, _group(rel)), []).append((rel, owner))
    refiled: list[Unhandled] = []
    for (kind, group), members in sorted(entries.items()):
        n = len(members)
        if kind == OWNED:
            owners = sorted({o for _, o in members})
            shown = ", ".join(owners[:3]) + (f" and {len(owners) - 3} more" if len(owners) > 3 else "")
            reason = (f"{n} file(s) used only by residue that has its own entry ({shown}); they ship with "
                      f"their owner when it converts")
        elif all(o == "atlas" for _, o in members):
            reason = (f"{n} texture atlas source list(s): they tell Java's texture stitcher what to load, "
                      f"and a Bedrock pack has no atlas (its textures are indexed by the textures converter)")
        else:
            sample = ", ".join(r.rsplit("/", 1)[-1] for r, _ in members[:3])
            reason = (f"{n} file(s) no blockstate, item definition, model or particle definition of the jar "
                      f"names (or only Java-only models do), so only the mod's Java code draws them "
                      f"(screens, entity and block-entity renderers, effect icons, armor layers, custom "
                      f"model loaders); nothing in a Bedrock pack would draw them (e.g. {sample})")
        refiled.append(Unhandled(source=group, kind=kind, reason=reason, count=n))

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
