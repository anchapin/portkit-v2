"""Leftover advancements (#340, part of #277): owned by residue or explained, never converted.

A Java advancement (``data/<ns>/advancement[s]/**.json``) no converter claimed
is ``unowned`` residue (:func:`portkit.pipeline.unowned`). The recipe converter
already reads one kind of advancement: a recipe advancement (``rewards.recipes``)
whose crafting recipe ships gives that recipe its Bedrock ``unlock`` and is
claimed (#260, :mod:`portkit.converters.recipe_unlock`). This module re-files the
rest from what each file says (design PR for #340; ``docs/decisions.md``):

* ``owned_by_residue``: a recipe advancement every one of whose rewarded recipes
  is a recipe file of the jar with a residue entry of its own. Its one effect is
  unlocking those recipes, so it goes with them and is read for their ``unlock``
  when they convert (the #299 / #302 pattern).
* ``no_bedrock_advancement``, an explained kind. Bedrock has no data-driven
  advancements: its achievements are a fixed list tracked per account
  (minecraft.wiki, "Achievement"), and the add-on JSON reference defines no
  advancement or achievement (learn.microsoft.com, Bedrock add-on reference).
  Filed here:

  - ``story``: an advancement with no recipe reward (a story, challenge or
    hidden advancement). Nothing in a pack can track or show it. Its
    ``experience``, ``loot`` or ``function`` rewards are not given; the reason
    names them, so the pack never gives more than Java does.
  - ``furnace``: a recipe advancement whose rewarded recipes all ship as
    ``minecraft:recipe_furnace`` (Java smelting, blasting, smoking, campfire).
    Bedrock's furnace recipe has no ``unlock`` field (learn.microsoft.com,
    "minecraft:recipe_furnace"; unlock data is a crafting-recipe field,
    "Recipe Introduction - Recipe Unlocking"), so the shipped recipe works with
    nothing to carry.
  - ``absent``: a recipe advancement whose rewarded recipes no data file of the
    jar defines (a datagen namespace slip, or another mod's recipe). There is no
    converted recipe whose ``unlock`` could carry it.

Anything else stays ``unowned``: a file Java's reader would reject or that this
module can't read (not an object, criteria not an object, rewards of a shape or
key Java doesn't define), a recipe advancement with other rewards too, or one
whose recipes are a mix of the cases above. Nothing here names a mod.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .model import Unhandled

OWNED = "owned_by_residue"
NO_BEDROCK = "no_bedrock_advancement"
KINDS = frozenset({NO_BEDROCK})

_ADVANCEMENT = re.compile(r"^data/([^/]+)/(advancement|advancements)/(.+)\.json$")
# Java's AdvancementRewards fields (minecraft.wiki, "Advancement definition":
# rewards.experience, rewards.loot, rewards.recipes, rewards.function).
_REWARDS = frozenset({"experience", "loot", "recipes", "function"})
# Bedrock recipe bodies that take unlock data (crafting, #260).
_UNLOCKED_BODIES = frozenset({"minecraft:recipe_shaped", "minecraft:recipe_shapeless"})
_FURNACE = "minecraft:recipe_furnace"
_MAX_SHOWN = 3

_ACHIEVEMENTS = ("Bedrock has no data-driven advancements: its achievements are a fixed list tracked per "
                 "account (minecraft.wiki, Achievement) and the add-on JSON reference defines no advancement")


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def _norm(ident: str) -> str:
    return ident if ":" in ident else f"minecraft:{ident}"


def recipe_file(root: Path, recipe_id: str) -> str | None:
    """The jar's data file defining recipe ``recipe_id`` (1.21 ``recipe/`` or
    1.20 ``recipes/``), or None."""
    ns, _, path = _norm(recipe_id).partition(":")
    if not re.fullmatch(r"[a-z0-9_.\-]+", ns) or not re.fullmatch(r"[a-z0-9_./\-]+", path):
        return None
    for lane in ("recipe", "recipes"):
        rel = f"data/{ns}/{lane}/{path}.json"
        if (root / rel).is_file():
            return rel
    return None


def recipe_bodies(files: dict, sources: dict[str, str], renames: dict[str, str] | None = None) -> dict[str, set[str]]:
    """Java recipe file -> the Bedrock recipe body keys the pack holds for it."""
    renames = renames or {}
    out: dict[str, set[str]] = {}
    for path, src in sources.items():
        body = files.get(renames.get(path, path))
        if not isinstance(body, dict):
            continue
        keys = {k for k in body if k.startswith("minecraft:recipe_")}
        if keys:
            out.setdefault(src, set()).update(keys)
    return out


def _rewards_phrase(rewards: dict) -> str:
    parts = []
    if "experience" in rewards:
        parts.append(f"experience {rewards['experience']}")
    if "loot" in rewards:
        loot = rewards["loot"]
        parts.append("loot " + ", ".join(str(x) for x in (loot if isinstance(loot, list) else [loot])))
    if "function" in rewards:
        parts.append(f"function {rewards['function']}")
    return "; ".join(parts)


def classify(root: Path, files: list[str], residue: dict[str, str],
             bodies: dict[str, set[str]]) -> dict[str, tuple[str, str, str]]:
    """file -> (kind, category, detail) for the leftover advancements this module
    explains; a file it can't is left out (it stays ``unowned``).

    ``residue``: source -> kind of every residue entry for one file.
    ``bodies``: Java recipe file -> Bedrock recipe body keys shipped for it."""
    root = Path(root)
    out: dict[str, tuple[str, str, str]] = {}
    for rel in files:
        if not _ADVANCEMENT.match(rel):
            continue
        adv = _read(root / rel)
        if not isinstance(adv, dict) or not isinstance(adv.get("criteria"), dict) or not adv["criteria"]:
            continue
        rewards = adv.get("rewards", {})
        if not isinstance(rewards, dict) or set(rewards) - _REWARDS:
            continue
        recipes = rewards.get("recipes", [])
        if not isinstance(recipes, list) or not all(isinstance(r, str) and r for r in recipes):
            continue
        others = {k: v for k, v in rewards.items() if k != "recipes"}
        if not recipes:
            triggers = sorted({c.get("trigger") for c in adv["criteria"].values()
                               if isinstance(c, dict) and isinstance(c.get("trigger"), str)})
            out[rel] = (NO_BEDROCK, "story", json.dumps({"triggers": triggers, "rewards": _rewards_phrase(others)}))
            continue
        if others:
            continue  # a recipe reward and others too: not one of the shapes read here
        states = []
        for rid in recipes:
            src = recipe_file(root, rid)
            if src is None:
                states.append(("absent", _norm(rid)))
            elif residue.get(src) not in (None, "unowned"):
                states.append(("residue", src))
            elif src in bodies and bodies[src] and not (bodies[src] & _UNLOCKED_BODIES) \
                    and bodies[src] <= {_FURNACE}:
                states.append(("furnace", src))
            else:
                states.append(("other", src))
        cases = {s for s, _ in states}
        if cases == {"residue"}:
            owners = [src for _, src in states]
            out[rel] = (OWNED, "recipe", json.dumps({"owners": owners,
                                                    "kinds": sorted({residue[o] for o in owners})}))
        elif cases == {"furnace"}:
            out[rel] = (NO_BEDROCK, "furnace", json.dumps({"recipes": [s for _, s in states]}))
        elif cases == {"absent"}:
            out[rel] = (NO_BEDROCK, "absent", json.dumps({"recipes": [s for _, s in states]}))
    return out


def _group(rel: str) -> str:
    parts = rel.split("/")
    return "/".join(parts[:4]) + "/" if len(parts) > 4 else "/".join(parts[:3]) + "/"


def _shown(items: list[str]) -> str:
    items = sorted(dict.fromkeys(items))
    text = ", ".join(items[:_MAX_SHOWN])
    return text + (f" and {len(items) - _MAX_SHOWN} more" if len(items) > _MAX_SHOWN else "")


def _reason(kind: str, category: str, members: list[tuple[str, dict]]) -> str:
    n = len(members)
    names = [r.rsplit("/", 1)[-1] for r, _ in members]
    if kind == OWNED:
        owners = [o for _, d in members for o in d["owners"]]
        kinds = sorted({k for _, d in members for k in d["kinds"]})
        return (f"{n} recipe advancement(s) whose rewarded recipes are residue with entries of their own "
                f"({_shown(owners)}; {', '.join(kinds)}): their one effect is unlocking those recipes in the "
                f"recipe book, so they go with their recipes; when one converts, the recipe converter reads "
                f"them again (a crafting recipe's Bedrock `unlock`, #260)")
    if category == "story":
        triggers = sorted({t for _, d in members for t in d["triggers"]})
        rewarded = [(r.rsplit("/", 1)[-1], d["rewards"]) for r, d in members if d["rewards"]]
        text = (f"{n} advancement(s) with no recipe reward, tracked by their own criteria "
                f"({_shown(triggers)}; e.g. {_shown(names)}): {_ACHIEVEMENTS}, so nothing in a pack can "
                f"track or show them")
        if rewarded:
            shown = "; ".join(f"{name}: {what}" for name, what in rewarded[:_MAX_SHOWN])
            more = f" and {len(rewarded) - _MAX_SHOWN} more" if len(rewarded) > _MAX_SHOWN else ""
            text += (f". {len(rewarded)} of them give rewards ({shown}{more}) that are not given on "
                     f"Bedrock, so the pack never gives more than Java")
        return text
    recipes = [s for _, d in members for s in d["recipes"]]
    if category == "furnace":
        return (f"{n} recipe advancement(s) whose rewarded recipes ship as Bedrock furnace recipes "
                f"({_shown(recipes)}): their one effect is unlocking the recipe in Java's recipe book, and "
                f"minecraft:recipe_furnace has no `unlock` field (learn.microsoft.com, recipe_furnace "
                f"reference; unlock data is a crafting-recipe field), so the shipped recipe needs nothing "
                f"from them; {_ACHIEVEMENTS}")
    return (f"{n} recipe advancement(s) whose rewarded recipes no data file of the jar defines "
            f"({_shown(recipes)}; e.g. {_shown(names)}): no recipe of this jar is unlocked by them, so "
            f"there is no converted recipe whose `unlock` could carry them; {_ACHIEVEMENTS}")


def refine(unhandled: list[Unhandled], root: Path, consumed: set[str],
           bodies: dict[str, set[str]]) -> list[Unhandled]:
    """Re-file the unowned advancements the jar explains; the rest of the
    residue is returned unchanged."""
    groups = [u for u in unhandled if u.kind == "unowned"
              and re.match(r"^data/[^/]+/(advancement|advancements)/", u.source)]
    if not groups:
        return unhandled
    root = Path(root)
    leftover: list[str] = []
    for u in groups:
        base = root / u.source.rstrip("/")
        if base.is_dir():
            leftover += [p.relative_to(root).as_posix() for p in sorted(base.rglob("*"))
                         if p.is_file() and p.relative_to(root).as_posix() not in consumed]
    residue = {u.source: u.kind for u in unhandled if not u.source.endswith("/")}
    found = classify(root, leftover, residue, bodies)

    entries: dict[tuple[str, str, str], list[tuple[str, dict]]] = {}
    for rel, (kind, category, detail) in sorted(found.items()):
        entries.setdefault((kind, _group(rel), category), []).append((rel, json.loads(detail)))
    refiled = [Unhandled(source=group, kind=kind, reason=_reason(kind, category, members), count=len(members))
               for (kind, group, category), members in sorted(entries.items())]

    out: list[Unhandled] = []
    for u in unhandled:
        if u not in groups:
            out.append(u)
            continue
        left = u.count - sum(1 for f in found if f.startswith(u.source))
        if left:
            out.append(Unhandled(source=u.source, kind="unowned",
                                 reason=f"{left} file(s) no converter claims yet", count=left))
    return out + refiled
