"""Mod armor: ``minecraft:wearable``, durability and enchantability read from the mod's code (#274).

A Java armor item is an ``ArmorItem`` built on an armor material: its slot,
armor points (protection), toughness, knockback resistance, durability and
enchantability are numbers in the mod's code, not in its data. Each adapter's
``item_armor`` hook reads them from the jar's bytecode with the shared readers
of :mod:`portkit.itemcode` and cites where each came from; this converter
writes what Bedrock has a component for, on the item definition the item
converter wrote:

* ``minecraft:wearable`` ``{"slot", "protection"}``: the slot from the piece's
  ``ArmorItem.Type`` (helmet ``slot.armor.head``, chestplate
  ``slot.armor.chest``, leggings ``slot.armor.legs``, boots
  ``slot.armor.feet``), protection = the Java armor points;
* ``minecraft:durability`` ``{"max_durability"}`` = the Java max damage;
* ``minecraft:enchantable`` ``{"slot", "value"}``: ``armor_head`` /
  ``armor_torso`` / ``armor_legs`` / ``armor_feet``, value = the Java
  enchantability;
* ``minecraft:max_stack_size`` 1 (Java armor stacks to one; Bedrock sets it for
  any non-hand wearable slot too).

Bedrock's side is :data:`BEDROCK_SOURCES`. Java's armor toughness and
knockback resistance have no Bedrock item component: they are read (an
unreadable one leaves the piece unwritten like any other stat) and named in a
note, never approximated.

A mod item Java's own data marks as armor (its ``#minecraft:head_armor``,
``chest_armor``, ``leg_armor``, ``foot_armor`` or ``trimmable_armor``
membership) that no adapter can read is left as the plain item it converted
to, and is residue (kind ``armor``) with the reason (Alex, 2026-10-16, #268:
no invented stats, #87). Worn rendering (attachables and the armor layer
textures) is not written yet: the source textures stay where they are.
"""
from __future__ import annotations

import copy

from ..itemcode import VANILLA_SOURCES, ArmorPiece
from ..model import ConversionResult, SourceMod, Unhandled
from .tags import TagResolver

# ArmorItem.Type -> (minecraft:wearable slot, minecraft:enchantable slot).
SLOTS = {
    "HELMET": ("slot.armor.head", "armor_head"),
    "CHESTPLATE": ("slot.armor.chest", "armor_torso"),
    "LEGGINGS": ("slot.armor.legs", "armor_legs"),
    "BOOTS": ("slot.armor.feet", "armor_feet"),
}
# minecraft:wearable and minecraft:enchantable need item format 1.20.30.
WEARABLE_FORMAT = "1.20.30"
BEDROCK_SOURCES = (
    "MicrosoftDocs/minecraft-creator@4186dc4ec84c ItemComponents/minecraft_wearable.md (slot: slot.armor.head, "
    "slot.armor.chest, slot.armor.legs, slot.armor.feet; protection: integer; needs format 1.20.30), "
    "minecraft_enchantable.md (slot: armor_head, armor_torso, armor_legs, armor_feet; value: integer >= 0), "
    "minecraft_durability.md (max_durability); Mojang bedrock-samples@46ba6ea9 "
    "behavior_pack/items/diamond_spear.json (max_stack_size 1 with durability and enchantable)"
)
# Java tags that say an item is armor (vanilla 1.21's slot tags, and the trim base tag).
JAVA_ARMOR_TAGS = (
    "minecraft:head_armor", "minecraft:chest_armor", "minecraft:leg_armor", "minecraft:foot_armor",
    "minecraft:trimmable_armor",
)
RESIDUE_KIND = "armor"


def _version(text) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in str(text).split("."))
    except ValueError:
        return ()


def java_armor(mod: SourceMod, tags: TagResolver) -> dict[str, list[str]]:
    """This namespace's items Java's armor tags hold -> the tags."""
    out: dict[str, list[str]] = {}
    for tag in JAVA_ARMOR_TAGS:
        found = tags.members(tag)
        members = found.members if found is not None else tags.own_share(tag)
        for member in members:
            if member.startswith(f"{mod.namespace}:"):
                out.setdefault(member, []).append(tag)
    return out


def valid(piece: object) -> bool:
    return (isinstance(piece, ArmorPiece) and piece.kind in SLOTS
            and isinstance(piece.protection, int) and not isinstance(piece.protection, bool) and piece.protection >= 0
            and isinstance(piece.durability, int) and piece.durability > 0
            and isinstance(piece.enchantability, int) and piece.enchantability >= 0
            and isinstance(piece.toughness, float) and isinstance(piece.knockback, float))


def wear(body: dict, piece: ArmorPiece) -> dict:
    """``body`` (an emitted item definition) as the armor ``piece``."""
    item = copy.deepcopy(body)
    if _version(item.get("format_version")) < _version(WEARABLE_FORMAT):
        item["format_version"] = WEARABLE_FORMAT
    wearable, enchantable = SLOTS[piece.kind]
    components = item["minecraft:item"].setdefault("components", {})
    components["minecraft:max_stack_size"] = 1
    components["minecraft:wearable"] = {"slot": wearable, "protection": piece.protection}
    components["minecraft:durability"] = {"max_durability": piece.durability}
    components["minecraft:enchantable"] = {"slot": enchantable, "value": piece.enchantability}
    return item


def _shown(names: list[str], limit: int = 6) -> str:
    return ", ".join(names[:limit]) + (f" and {len(names) - limit} more" if len(names) > limit else "")


def convert(mod: SourceMod, files: dict, tags: TagResolver | None = None) -> ConversionResult:
    """Make this namespace's armor items wearable, from what the adapters read."""
    result = ConversionResult()
    prefix = f"{mod.namespace}:"
    items: dict[str, tuple[str, dict]] = {}
    for path, body in files.items():
        if not (path.startswith("items/") and path.endswith(".json")) or not isinstance(body, dict):
            continue
        item = body.get("minecraft:item")
        ident = ((item or {}).get("description") or {}).get("identifier") if isinstance(item, dict) else None
        if isinstance(ident, str) and ident.startswith(prefix):
            items[ident[len(prefix):]] = (path, body)
    if not items:
        return result
    from ..adapters import item_armors

    answers = item_armors(mod, frozenset(items))
    marked = java_armor(mod, tags if tags is not None else TagResolver(mod))
    worn: dict[str, list[str]] = {}
    dropped, extras = [], {}
    for name in sorted(items):
        path, body = items[name]
        ident = prefix + name
        answer = answers.get(name)
        if valid(answer):
            result.files[path] = wear(body, answer)
            worn.setdefault(answer.source, []).append(
                f"{ident} {answer.kind.lower()} protection {answer.protection}, durability {answer.durability}, "
                f"enchantability {answer.enchantability}")
            lost = []
            if answer.toughness:
                lost.append(f"toughness {answer.toughness:g}")
            if answer.knockback:
                lost.append(f"knockback resistance {answer.knockback:g}")
            if lost:
                dropped.append(f"{ident} ({', '.join(lost)})")
            for what in answer.not_carried:
                extras.setdefault(what, []).append(ident)
            continue
        if ident not in marked and not isinstance(answer, str):
            continue
        why = answer if isinstance(answer, str) else (
            "no reader for this mod's armor could state its slot, armor points, toughness, knockback "
            "resistance, durability and enchantability from the mod's code")
        where = ", ".join(f"#{t}" for t in marked.get(ident, [])) or "its code builds it as an ArmorItem"
        model = f"assets/{mod.namespace}/models/item/{name}.json"
        source = model if (mod.root / model).is_file() else path
        result.unhandled.append(Unhandled(source, RESIDUE_KIND, (
            f"{ident} is armor in Java ({where}), but {why}; it converts as a plain item that can't be worn, "
            "since Bedrock's minecraft:wearable takes a slot and protection and no stat is invented (#274, #87)")))
    if worn:
        # The vanilla code every citation leans on is named once, not per source.
        vanilla = sorted({text for text in VANILLA_SOURCES.values() if any(text in source for source in worn)})
        parts = []
        for source, pieces in sorted(worn.items()):
            for text in vanilla:
                source = source.replace("; " + text, "").replace(text, "")
            parts.append(f"{'; '.join(pieces)} ({source.strip('; ')})")
        count = sum(len(p) for p in worn.values())
        result.notes.append(
            f"{count} armor item(s) carry minecraft:wearable, minecraft:durability, minecraft:enchantable and a "
            f"stack of one, from the numbers the mod's code gives them (#274; Bedrock: {BEDROCK_SOURCES}; "
            f"vanilla: {'; '.join(vanilla)}): "
            + " | ".join(parts)
            + ". Worn rendering (attachables, armor layer textures) is not written yet: worn, they don't show "
            "on the player.")
    if dropped:
        result.notes.append(
            "Java armor toughness and knockback resistance have no Bedrock item component, so they aren't "
            f"written (the armor points are): {_shown(dropped, 12)} (#274).")
    for what, idents in sorted(extras.items()):
        result.notes.append(f"Not carried on {len(idents)} armor item(s) ({_shown(idents)}): {what} (#274).")
    return result
