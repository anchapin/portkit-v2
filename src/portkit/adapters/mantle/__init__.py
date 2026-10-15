"""Mantle (#245): the library behind Tinkers' Construct, as a library adapter.

Mantle registers load-condition types other mods' data uses (in the corpus,
Tinkers' Construct 3.12.1.231 recipes): ``mantle:tag_filled`` (an item tag
has a member) and ``mantle:tag_combination_filled`` (some item is in every
tag of a list). Both are decided against the conversion's tags as the core's
own tag conditions are (:meth:`portkit.conditions.LoadContext.tag_filled`,
docs/decisions.md, 2026-10-13); moved here unchanged from
``conditions.py`` (#245 migration step 2).
"""
from __future__ import annotations

from ...conditions import ITEM_REGISTRY, LoadContext, Verdict
from .. import Adapter


def tag_filled(context: LoadContext, kind: str, cond: dict) -> Verdict:
    """``mantle:tag_filled``: the item tag has a member in this conversion."""
    filled, why = context.tag_filled(cond.get("tag"), cond.get("registry"))
    return Verdict(filled, f"{kind}: {why}")


def tag_combination_filled(context: LoadContext, kind: str, cond: dict) -> Verdict:
    """``mantle:tag_combination_filled``."""
    # Mantle TagCombinationCondition.test: some entry of the first match tag
    # (not in ignore) is in every other match tag.
    registry = cond.get("registry")
    match = cond.get("match")
    match = [match] if isinstance(match, str) else match
    if not isinstance(match, list) or not match or registry not in ITEM_REGISTRY:
        return Verdict(None, f"{kind}: unreadable match list or a non-item registry")
    sets = []
    for tag in match + ([cond["ignore"]] if isinstance(cond.get("ignore"), str) else []):
        members = context.tags.context_members(tag) if isinstance(tag, str) else None
        if members is None:
            return Verdict(None, f"{kind}: tag {tag}'s membership isn't known")
        present = []
        for m in members:
            here = context.present(m)
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


ADAPTER = Adapter(
    name="mantle",
    namespaces=frozenset({"mantle"}),
    library=True,
    conditions={
        "mantle:tag_filled": tag_filled,
        "mantle:tag_combination_filled": tag_combination_filled,
    },
)
