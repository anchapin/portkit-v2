"""Which Bedrock vanilla items a smithing recipe can take as its base (#270).

Bedrock's ``recipe_smithing_transform`` takes "only armor and tools" as the
base (Mojang bedrock-samples ``documentation/Recipes.html``), and BDS refuses a
recipe whose base isn't one when it loads the pack (#263, #268). A mod item is
checked by its ``minecraft:durability`` (see
:func:`portkit.converters.recipes.equip_smithing_bases`). A vanilla item can't
be given anything, so the question is only whether Bedrock's own data shows it
is armor or a tool:

* :data:`MOJANG`: the bases Mojang's vanilla pack itself uses in a
  ``recipe_smithing_transform`` (``behavior_pack/recipes/smithing_netherite_*.json``,
  which includes horse and nautilus armor, items with no durability), and the
  vanilla items whose data-driven definition in ``behavior_pack/items`` carries
  ``minecraft:durability`` (the spears), at :data:`portkit.data.COMMIT`.
* :data:`WIKI`: every other armor piece and tool that has durability in
  Bedrock Edition, from minecraft.wiki's Durability page (armor table, "Tool &
  weapon durability" materials and specific tools, and the wolf armor section
  it transcludes) at revision :data:`WIKI_REVISION`. Bedrock hard-codes these,
  so bedrock-samples has no definition for them. The education-only sparkler
  and glow stick are left out (not in the vanilla item list).

Every id here is a Bedrock id in bedrock-samples
``metadata/vanilladata_modules/mojang-items.json`` at the same commit (checked
by the tests when that list is cached). A vanilla item in neither set, like
``minecraft:stick``, is not armor or a tool to Bedrock, so a smithing recipe
taking it as the base is withdrawn to the residue.

Only the item ids are kept (a short excerpt; bedrock-samples is (c) Mojang AB,
used under the Minecraft EULA, #24).
"""
from __future__ import annotations

from . import COMMIT, REPO

MOJANG_SOURCE = f"{REPO}@{COMMIT[:12]}"
WIKI_REVISION = 3790798
WIKI_SOURCE = f"minecraft.wiki Durability (oldid={WIKI_REVISION})"

# Bases of Mojang's own vanilla smithing transform recipes, behavior_pack/recipes.
_MOJANG_RECIPE_BASES = (
    "minecraft:diamond_axe", "minecraft:diamond_boots", "minecraft:diamond_chestplate",
    "minecraft:diamond_helmet", "minecraft:diamond_hoe", "minecraft:diamond_horse_armor",
    "minecraft:diamond_leggings", "minecraft:diamond_nautilus_armor", "minecraft:diamond_pickaxe",
    "minecraft:diamond_shovel", "minecraft:diamond_spear", "minecraft:diamond_sword",
)
# Vanilla definitions in behavior_pack/items carrying minecraft:durability.
_MOJANG_DURABLE_ITEMS = tuple(
    f"minecraft:{tier}_spear" for tier in ("wooden", "stone", "copper", "golden", "iron", "diamond", "netherite")
)

MOJANG: dict[str, str] = {
    **{ident: f"{MOJANG_SOURCE} behavior_pack/recipes (a vanilla smithing base)" for ident in _MOJANG_RECIPE_BASES},
    **{ident: f"{MOJANG_SOURCE} behavior_pack/items/{ident.split(':')[1]}.json (minecraft:durability)"
       for ident in _MOJANG_DURABLE_ITEMS},
}

_ARMOR = ("minecraft:turtle_helmet", *(
    f"minecraft:{material}_{piece}"
    for material in ("leather", "golden", "copper", "chainmail", "iron", "diamond", "netherite")
    for piece in ("helmet", "chestplate", "leggings", "boots")
))
_TOOLS = tuple(
    f"minecraft:{material}_{tool}"
    for material in ("wooden", "stone", "copper", "golden", "iron", "diamond", "netherite")
    for tool in ("sword", "pickaxe", "axe", "shovel", "hoe")
)
_SPECIFIC = (
    "minecraft:flint_and_steel", "minecraft:brush", "minecraft:fishing_rod", "minecraft:carrot_on_a_stick",
    "minecraft:warped_fungus_on_a_stick", "minecraft:shears", "minecraft:shield", "minecraft:bow",
    "minecraft:trident", "minecraft:elytra", "minecraft:crossbow", "minecraft:mace", "minecraft:wolf_armor",
)

WIKI: dict[str, str] = {
    ident: f"{WIKI_SOURCE}: Bedrock armor or tool with durability"
    for ident in (*_ARMOR, *_TOOLS, *_SPECIFIC) if ident not in MOJANG
}

# Every vanilla item Bedrock takes as a smithing base, with where that comes from.
VANILLA_SMITHING_BASES: dict[str, str] = {**WIKI, **MOJANG}


def vanilla_base_refusal(ident: str) -> str | None:
    """Why Bedrock won't take vanilla ``ident`` as a smithing base, or None if it will."""
    if ident in VANILLA_SMITHING_BASES:
        return None
    return (f"{ident} is not armor or a tool to Bedrock (no vanilla smithing recipe of Mojang's "
            f"takes it as the base, {MOJANG_SOURCE}, and it has no durability, {WIKI_SOURCE})")


# The template and addition slots (#305). learn.microsoft.com, Recipe
# Documentation - Smithing Transform Recipe: the addition's items "must have the
# minecraft:transform_materials tag", the template's "must have the
# minecraft:transform_templates tag", to be accepted into the slot (Mojang
# bedrock-samples documentation/Recipes.html says the same). BDS 1.26.52.3
# refuses the recipe otherwise ("addition item must have the
# 'minecraft:transform_materials' tag", ingame run 38996897674). The pack's own
# item carries the tag its recipe puts it under (portkit.converters.recipes);
# a vanilla item can't be given one, so only Bedrock's own members are taken:
# minecraft.wiki Item tag (Bedrock Edition), which lists exactly one member of
# each (MS Learn: the addition's "only accepted item is minecraft:netherite_ingot").
MS_LEARN_SOURCE = "learn.microsoft.com, Recipe Documentation - Smithing Transform Recipe"
TAG_WIKI_REVISION = 3758407
TAG_WIKI_SOURCE = f"minecraft.wiki Item tag (Bedrock Edition) (oldid={TAG_WIKI_REVISION})"

# Bedrock slot -> the item tag that slot takes.
TRANSFORM_SLOT_TAGS = {
    "template": "minecraft:transform_templates",
    "base": "minecraft:transformable_items",
    "addition": "minecraft:transform_materials",
}

# Bedrock slot -> {vanilla id carrying that slot's tag: where that comes from}.
VANILLA_TRANSFORM_ITEMS: dict[str, dict[str, str]] = {
    "template": {"minecraft:netherite_upgrade_smithing_template": f"{TAG_WIKI_SOURCE}: minecraft:transform_templates"},
    "addition": {"minecraft:netherite_ingot": f"{TAG_WIKI_SOURCE}: minecraft:transform_materials"},
}


def vanilla_slot_refusal(slot: str, ident: str) -> str | None:
    """Why Bedrock won't take vanilla ``ident`` as a smithing transform's
    ``slot`` ("template" or "addition"), or None if it will."""
    if ident in VANILLA_TRANSFORM_ITEMS[slot]:
        return None
    tag = TRANSFORM_SLOT_TAGS[slot]
    return (f"{slot} {ident} does not carry {tag} in Bedrock (its only member is "
            f"{next(iter(VANILLA_TRANSFORM_ITEMS[slot]))}, {TAG_WIKI_SOURCE}), and the {slot} slot takes only "
            f"items with that tag ({MS_LEARN_SOURCE})")


def addon_slot_refusal(slot: str, ident: str, kind: str, components: dict | None) -> str | None:
    """Why the pack's own ``ident`` can't fill a smithing transform's ``slot``
    ("template" or "addition"), or None. ``kind`` is its definition kind
    ("item", "block" or "block_and_item"; an item's ``components`` given)."""
    tag = TRANSFORM_SLOT_TAGS[slot]
    if kind == "block":
        return (f"{slot} {ident} is a block with no item definition, so it can't carry {tag}, which the "
                f"{slot} slot takes ({MS_LEARN_SOURCE})")
    found = components.get("minecraft:tags") if isinstance(components, dict) else None
    tags = found.get("tags") if isinstance(found, dict) else None
    if isinstance(tags, list) and tag in tags:
        return None
    return f"{slot} {ident} does not carry {tag}, which the {slot} slot takes ({MS_LEARN_SOURCE})"
