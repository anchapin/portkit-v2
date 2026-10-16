"""Recipe unlock data, from the Java recipe's own advancement (#260).

Bedrock crafting recipes at ``format_version`` 1.20.10 and later must say how
the recipe book unlocks them: Bedrock Dedicated Server 1.26.52.3 logs "1.20+
Recipes require unlock data" for every ``minecraft:recipe_shaped`` and
``minecraft:recipe_shapeless`` without an ``unlock`` (in-game check, #238; it
did not log it for the furnace or smithing recipes it loaded). ``unlock`` is a
list of entries, any one of which unlocks the recipe: ``{"item": id}``,
``{"tag": tag}``, or ``{"context": ...}`` with ``AlwaysUnlocked``,
``PlayerInWater``, ``PlayerHasManyItems`` or ``None``
(learn.microsoft.com, Recipe Introduction - Recipe Unlocking, and the
recipe_shaped / recipe_shapeless references; Mojang/bedrock-schemas
``forms/recipe/recipe_shaped.form.json``).

Java says the same thing in its data: a recipe is unlocked in the recipe book by
an advancement whose ``rewards.recipes`` names it, normally granted on
``minecraft:inventory_changed`` (``has_<item>``) or on already having the recipe
(``minecraft:recipe_unlocked``, ``has_the_recipe``), in one OR group. Vanilla
Bedrock's own recipes take the same items (bedrock-samples
``behavior_pack/recipes``: 1,706 ``item`` and 19 ``tag`` unlock entries).

Rule, in order:

1. The advancements of the jar (``data/*/advancement[s]/**``) that reward the
   recipe and whose own load conditions hold (an advancement Java doesn't load
   grants nothing). Each one must be one OR group (``requirements`` with a single list,
   or a single criterion); anything else (an AND of criteria, which Bedrock's
   unlock list can't say) is not used. In the group, ``recipe_unlocked``
   criteria are skipped (they are satisfied by the reward itself), and each
   ``inventory_changed`` criterion with exactly one item predicate holding only
   ``items`` / ``item`` / ``tag`` gives its items or tag. A criterion of any
   other trigger, with several predicates (has all of them), or with a count,
   component or NBT condition is dropped, which can only make the unlock
   narrower than Java's, never broader.
2. An item is kept when this conversion emits it, or when it is a vanilla id
   Bedrock has (Mojang's item list, :mod:`portkit.data.vanilla_items`; Java's
   ``minecraft:oak_trapdoor`` is not one, Bedrock calls it
   ``minecraft:trapdoor``). A tag is kept when the converted recipe takes that
   same tag; a tag that means one item (the recipe converter's own rule) is
   that item, under the same check. Anything else is dropped: BDS refuses the
   whole recipe when an unlock names an item it doesn't know ("has an invalid
   unlock ingredient").
3. Every recipe written from one Java recipe (its per-member expansions too)
   takes the same entries.
4. Fallback, labelled: no advancement rewards the recipe, or none of its
   entries survive -> ``{"context": "AlwaysUnlocked"}`` (an object, as
   vanilla writes every context), the vanilla crafting table's own unlock.

``unlock`` decides when the recipe book lists a recipe. The ``dolimitedcrafting``
gamerule, when true, lets players craft only recipes they have unlocked
(learn.microsoft.com, /gamerule); with it off, a recipe crafts from the grid
whether or not it is unlocked. Neither was observed in game here (the Script API
can't list recipes or a player's recipe book).
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path

# A context is written as one object, never in a list: BDS 1.26.52.3 reads a
# list entry as an item ("has an invalid unlock ingredient", #260 ingame run
# 38842744549), and every context unlock in bedrock-samples is an object
# (crafting_table.json, chest.json, the boats).
ALWAYS_UNLOCKED = {"context": "AlwaysUnlocked"}
# Recipe bodies Bedrock wants unlock data on (BDS 1.26.52.3, #238 runs).
NEEDS_UNLOCK = frozenset({"minecraft:recipe_shaped", "minecraft:recipe_shapeless"})
_INVENTORY = "minecraft:inventory_changed"
_RECIPE_UNLOCKED = "minecraft:recipe_unlocked"
_PREDICATE_KEYS = frozenset({"items", "item", "tag"})


def _norm(ident: str) -> str:
    return ident if ":" in ident else f"minecraft:{ident}"


def advancement_index(root: Path) -> dict[str, list[tuple[str, dict]]]:
    """Java recipe id -> [(advancement file, advancement)] for every advancement
    in the jar whose ``rewards.recipes`` names it, in path order."""
    index: dict[str, list[tuple[str, dict]]] = {}
    data = root / "data"
    if not data.is_dir():
        return index
    for ns_dir in sorted(p for p in data.iterdir() if p.is_dir()):
        for lane in ("advancement", "advancements"):
            base = ns_dir / lane
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*.json")):
                try:
                    adv = json.loads(path.read_text())
                except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                    continue
                if not isinstance(adv, dict):
                    continue
                rewards = adv.get("rewards")
                recipes = rewards.get("recipes") if isinstance(rewards, dict) else None
                if not isinstance(recipes, list):
                    continue
                rel = path.relative_to(root).as_posix()
                for rid in recipes:
                    if isinstance(rid, str):
                        index.setdefault(_norm(rid), []).append((rel, adv))
    return index


@dataclass
class Criteria:
    """What a recipe's advancements say unlocks it, before mapping to Bedrock."""
    items: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)  # criteria not expressible, "file#name: why"


def _predicate(pred) -> tuple[list[str], list[str]] | None:
    """(items, tags) one inventory_changed item predicate names, or None."""
    if not isinstance(pred, dict) or not pred or set(pred) - _PREDICATE_KEYS:
        return None
    items: list[str] = []
    tags: list[str] = []
    for key in ("items", "item"):
        value = pred.get(key)
        if value is None:
            continue
        for entry in value if isinstance(value, list) else [value]:
            if not isinstance(entry, str) or not entry:
                return None
            if entry.startswith("#"):
                tags.append(_norm(entry[1:]))
            else:
                items.append(_norm(entry))
    if "tag" in pred:
        if not isinstance(pred["tag"], str):
            return None
        tags.append(_norm(pred["tag"]))
    return (items, tags) if items or tags else None


def criteria(advancements: list[tuple[str, dict]]) -> Criteria:
    """The items and tags of the recipe's advancements' has_<item> criteria."""
    out = Criteria()
    for rel, adv in advancements:
        crit = adv.get("criteria")
        if not isinstance(crit, dict):
            out.dropped.append(f"{rel}: no criteria")
            continue
        req = adv.get("requirements")
        if req is None:
            req = [[name] for name in crit]
        groups = [g for g in req if isinstance(g, list)]
        # Groups made only of recipe_unlocked are met by the reward itself.
        live = [g for g in groups
                if any((crit.get(n) or {}).get("trigger") != _RECIPE_UNLOCKED for n in g)]
        if len(live) != 1 or len(groups) != len(req):
            out.dropped.append(f"{rel}: requirements are not one OR group, which Bedrock's unlock list can't say")
            continue
        for name in live[0]:
            c = crit.get(name)
            trigger = c.get("trigger") if isinstance(c, dict) else None
            if trigger == _RECIPE_UNLOCKED:
                continue
            preds = ((c.get("conditions") or {}).get("items") if isinstance(c, dict) else None)
            if trigger != _INVENTORY or not isinstance(preds, list) or len(preds) != 1:
                out.dropped.append(f"{rel}#{name}: {trigger} criterion is not one held item")
                continue
            got = _predicate(preds[0])
            if got is None:
                out.dropped.append(f"{rel}#{name}: item predicate has conditions beyond the item")
                continue
            for i in got[0]:
                if i not in out.items:
                    out.items.append(i)
            for t in got[1]:
                if t not in out.tags:
                    out.tags.append(t)
    return out


def recipe_refs(body: dict) -> tuple[set[str], set[str]]:
    """(item ids, tags) a converted Bedrock recipe body names in its inputs and result."""
    items: set[str] = set()
    tags: set[str] = set()

    def walk(value):
        if isinstance(value, dict):
            if isinstance(value.get("item"), str):
                items.add(value["item"])
            if isinstance(value.get("tag"), str):
                tags.add(value["tag"])
        elif isinstance(value, list):
            for v in value:
                walk(v)

    for key in ("key", "ingredients", "result"):
        value = body.get(key)
        walk(list(value.values()) if key == "key" and isinstance(value, dict) else value)
    return items, tags


def unlock_entries(found: Criteria, bodies: list[dict], emitted, single_item,
                   vanilla: frozenset[str] | None, to_bedrock=None) -> list[dict]:
    """Bedrock unlock entries for ``found``, given every body written from the
    Java recipe. ``single_item(tag)`` is the one item a tag means, or None;
    ``vanilla`` is Bedrock's vanilla item ids (None: not known, so none kept).
    ``to_bedrock(item)``, when given, is a vanilla Java id's Bedrock (id, data)
    or None (#261): Java ``minecraft:oak_trapdoor`` unlocks as Bedrock
    ``minecraft:trapdoor``, and Java ``minecraft:nether_brick`` (the item) is
    never read as Bedrock's ``minecraft:nether_brick`` (the block)."""
    tags: set[str] = set()
    for body in bodies:
        tags |= recipe_refs(body)[1]
    emitted = emitted or {}
    vanilla = vanilla or frozenset()
    out: list[dict] = []

    def add(entry):
        if entry not in out:
            out.append(entry)

    def entry(item: str) -> dict | None:
        if item in emitted:
            return {"item": item}
        if to_bedrock is not None and item.startswith("minecraft:"):
            got = to_bedrock(item)
            if got is None or got[0] not in vanilla:
                return None
            return {"item": got[0]} if got[1] is None else {"item": got[0], "data": got[1]}
        return {"item": item} if item in vanilla else None

    for item in found.items:
        got = entry(item)
        if got:
            add(got)
    for tag in found.tags:
        if tag in tags:
            add({"tag": tag})
            continue
        one = single_item(tag)
        got = entry(one) if one else None
        if got:
            add(got)
    return out


def with_unlock(body: dict, unlock: list[dict] | dict) -> dict:
    """``body`` with ``unlock`` placed before its result, as vanilla writes it."""
    out = {}
    for key, value in body.items():
        if key == "result":
            out["unlock"] = copy.deepcopy(unlock)
        out[key] = value
    if "unlock" not in out:
        out["unlock"] = copy.deepcopy(unlock)
    return out
