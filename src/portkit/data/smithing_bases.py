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
