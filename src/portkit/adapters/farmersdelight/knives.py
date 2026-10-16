"""Farmer's Delight knives: durability from their tool tier (#263).

Bedrock's smithing table takes only armor and tools as the base of a
``recipe_smithing_transform`` (Mojang bedrock-samples documentation/Recipes.html:
"The only accepted items are armor and tools"), and BDS 1.26.52.3 rejects FD's
netherite knife upgrade ("base item is not a piece of armor or equipment")
while the diamond knife has no ``minecraft:durability``. An in-game run with the
diamond knife given its durability and one-per-stack passed (ingame run
38858470689); the tag alone did not (38858468149).

A knife is a tiered tool in FD's code: NeoForge ``KnifeItem extends DiggerItem``
built with a ``Tier`` (ModItems L230-L239), Refabricated ``knifeItem(material)``
calling ``.durability(material.durability())`` (ModItems L89-L92, L314-L325). So
each knife's Bedrock item gets its tier's durability and a stack of one (Java:
``max_damage`` and ``max_stack_size`` above 1 can't be put together, minecraft.wiki
Data component format, 24w12a). Vanilla tiers are cited from minecraft.wiki
"Tiers" (the skillet's revision); FD's flint tier from FD's own code. The
copper knife (Refabricated, ``ToolMaterial.COPPER``) is left as it was: the
cited Tiers table doesn't state copper's durability unambiguously.

Only durability and the stack size are written: attack damage, mining speed,
enchantability and repair are left for a later slice (the note says so).
The ``minecraft:transformable_items`` tag the smithing slot needs comes from
the recipe converter (recipes._SMITHING_SLOT_TAGS) and is kept here.
"""
from __future__ import annotations

from ...model import ConversionResult, SourceMod
from .cutting_board import FD_FAB, FD_NEO, _src, _unsupported
from .skillet import TIER_SOURCE

STACK_SOURCE = ("https://minecraft.wiki/w/Data_component_format?oldid=3840908 "
                "(24w12a: max_damage and max_stack_size can no longer be put together)")
FLINT_NEO = _src(FD_NEO, "common/registry/ModMaterials.java", "13-L18")
FLINT_FAB = _src(FD_FAB, "common/registry/ModToolMaterials.java", "10")

# blockstate-free item name -> (tier as FD's code names it, durability, source).
# Vanilla durabilities: minecraft.wiki Tiers (TIER_SOURCE): gold 32, iron 250,
# diamond 1561, netherite 2031. FD flint: getUses() 131 / ToolMaterial(..., 131, ...).
KNIVES = {
    "neoforge": {
        "flint_knife": ("ModMaterials.FLINT", 131, FLINT_NEO),
        "iron_knife": ("Tiers.IRON", 250, TIER_SOURCE),
        "diamond_knife": ("Tiers.DIAMOND", 1561, TIER_SOURCE),
        "netherite_knife": ("Tiers.NETHERITE", 2031, TIER_SOURCE),
        "golden_knife": ("Tiers.GOLD", 32, TIER_SOURCE),
    },
    "fabric": {
        "flint_knife": ("ModToolMaterials.FLINT", 131, FLINT_FAB),
        "iron_knife": ("ToolMaterial.IRON", 250, TIER_SOURCE),
        "diamond_knife": ("ToolMaterial.DIAMOND", 1561, TIER_SOURCE),
        "netherite_knife": ("ToolMaterial.NETHERITE", 2031, TIER_SOURCE),
        "golden_knife": ("ToolMaterial.GOLD", 32, TIER_SOURCE),
    },
}
REGISTRY = {
    "neoforge": _src(FD_NEO, "common/registry/ModItems.java", "230-L239"),
    "fabric": _src(FD_FAB, "common/registry/ModItems.java", "314-L325"),
}


def convert(mod: SourceMod, files: dict) -> ConversionResult:
    """Each converted FD knife item with its tier's durability, one per stack."""
    result = ConversionResult()
    table = KNIVES.get(mod.loader or "")
    if table is None or _unsupported(mod, "knife", "knife") is not None:
        return result
    done = []
    for name, (tier, durability, _source) in sorted(table.items()):
        path = f"items/{name}.json"
        body = files.get(path)
        identifier = f"{mod.namespace}:{name}"
        item = body.get("minecraft:item") if isinstance(body, dict) else None
        if not isinstance(item, dict) or item.get("description", {}).get("identifier") != identifier:
            continue
        components = dict(item.get("components") or {})
        components["minecraft:max_stack_size"] = 1
        components["minecraft:durability"] = {"max_durability": durability}
        result.files[path] = {**body, "minecraft:item": {**item, "components": components}}
        done.append(f"{name} {durability} ({tier})")
    if done:
        result.notes.append(
            "Farmer's Delight knives carry their tool tier's durability, one per stack "
            f"({', '.join(done)}; {REGISTRY[mod.loader]}), so Bedrock's smithing table takes the "
            "diamond knife as the netherite upgrade's base. Attack damage, mining speed, "
            "enchantability and repair are not written yet.")
    return result
