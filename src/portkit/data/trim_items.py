"""What Bedrock takes in each slot of a smithing *trim* recipe (#272).

Mojang bedrock-samples ``documentation/Recipes.html``, Smithing Trim Recipe
(at :data:`portkit.data.COMMIT`):

* ``base``: "The only accepted items are armors. Items must have the
  ``minecraft:trimmable_armors`` tag to be accepted into the respective UI slot."
* ``template``: items "must have the ``minecraft:trim_templates`` tag".
* ``addition``: items "must have the ``minecraft:trim_materials`` tag".

Mojang's own ``behavior_pack/recipes/smithing_armor_trim.json`` takes exactly
those three tags. bedrock-samples has no tag-membership files, so the vanilla
members are minecraft.wiki's Item tag (Bedrock Edition) lists at revision
:data:`WIKI_REVISION`, plus resin brick, which minecraft.wiki's Resin Brick page
(:data:`RESIN_REVISION`) gives as a trim material.

BDS 1.26.52.3 checks the same things when it loads a pack (#272 probe, ingame
runs :data:`PROBE_RUNS` on a throwaway branch). These all fail with a
content-log ERROR:

* a base that isn't armor: ``minecraft:stick``, ``minecraft:netherite_sword``,
  ``minecraft:wolf_armor``, ``minecraft:diamond_horse_armor``,
  ``minecraft:carved_pumpkin``, or an add-on item without ``minecraft:wearable``,
  even one tagged ``minecraft:trimmable_armors`` ("should be an armor, but
  isn't");
* an add-on item as the addition, even tagged ``minecraft:trim_materials``
  ("should be a valid trim material");
* an add-on item as the template, even tagged ``minecraft:trim_templates``
  ("should be a valid trim pattern ... Did you register it in the Trim Pattern
  Registry?").

An add-on item that carries ``minecraft:trim_templates``, or
``minecraft:trimmable_armors`` without being wearable, also breaks Mojang's own
``minecraft:smithing_armor_trim``, which takes those tags (same runs). One
carrying ``minecraft:trim_materials`` puts an item BDS refuses as an addition
into that recipe too; the probe didn't isolate that case (BDS reported the
earlier slot first). So an add-on item can only ever be a trim *base*, and
only when it is wearable armor that carries the tag.

Only item ids and where they come from are kept here: a short excerpt, no file
content (bedrock-samples is (c) Mojang AB, used under the Minecraft EULA, #24;
minecraft.wiki is CC BY-NC-SA 3.0).
"""
from __future__ import annotations

from . import COMMIT, REPO

MOJANG_SOURCE = f"{REPO}@{COMMIT[:12]} documentation/Recipes.html (Smithing Trim Recipe)"
WIKI_REVISION = 3758407
WIKI_SOURCE = f"minecraft.wiki Item tag (Bedrock Edition) (oldid={WIKI_REVISION})"
RESIN_REVISION = 3734929
RESIN_SOURCE = f"minecraft.wiki Resin Brick (oldid={RESIN_REVISION}), Smithing ingredient"
PROBE_RUNS = (38936397375, 38937251687)
PROBE_SOURCE = "BDS 1.26.52.3 content log (#272 probe, ingame runs 38936397375 and 38937251687)"

# Bedrock slot -> the item tag that slot takes.
TRIM_SLOT_TAGS = {
    "template": "minecraft:trim_templates",
    "base": "minecraft:trimmable_armors",
    "addition": "minecraft:trim_materials",
}
# Java's name for each slot's tag (Java's is trimmable_armor, singular; the
# other two are spelt the same).
JAVA_SLOT_TAGS = {
    "template": "minecraft:trim_templates",
    "base": "minecraft:trimmable_armor",
    "addition": "minecraft:trim_materials",
}

_TRIMMABLE_ARMORS = ("minecraft:turtle_helmet", *(
    f"minecraft:{material}_{piece}"
    for material in ("netherite", "diamond", "golden", "iron", "chainmail", "leather")
    for piece in ("helmet", "chestplate", "leggings", "boots")
))
_TRIM_MATERIALS = (
    "minecraft:iron_ingot", "minecraft:copper_ingot", "minecraft:gold_ingot", "minecraft:lapis_lazuli",
    "minecraft:emerald", "minecraft:diamond", "minecraft:netherite_ingot", "minecraft:redstone",
    "minecraft:quartz", "minecraft:amethyst_shard",
)
_TRIM_TEMPLATES = tuple(
    f"minecraft:{pattern}_armor_trim_smithing_template"
    for pattern in ("ward", "spire", "coast", "eye", "dune", "wild", "rib", "tide", "sentry", "vex",
                    "snout", "wayfinder", "shaper", "silence", "raiser", "host", "flow", "bolt")
)

# Bedrock slot -> {vanilla id: where that comes from}.
VANILLA_TRIM_ITEMS: dict[str, dict[str, str]] = {
    "template": {ident: f"{WIKI_SOURCE}: minecraft:trim_templates" for ident in _TRIM_TEMPLATES},
    "base": {ident: f"{WIKI_SOURCE}: minecraft:trimmable_armors" for ident in _TRIMMABLE_ARMORS},
    "addition": {
        **{ident: f"{WIKI_SOURCE}: minecraft:trim_materials" for ident in _TRIM_MATERIALS},
        "minecraft:resin_brick": RESIN_SOURCE,
    },
}

_WHAT = {"template": "a trim template", "base": "trimmable armor", "addition": "a trim material"}


def slot_value(value) -> tuple[str, str] | None:
    """``("item" | "tag", id)`` for one trim slot as Bedrock writes it, else None."""
    if isinstance(value, str) and value:
        return "item", value
    if isinstance(value, dict):
        for kind in ("tag", "item"):
            if isinstance(value.get(kind), str) and value[kind]:
                return kind, value[kind]
    return None


def vanilla_refusal(slot: str, kind: str, ident: str) -> str | None:
    """Why Bedrock won't take vanilla ``ident`` (an item, or a tag) in trim ``slot``, or None."""
    if kind == "tag":
        if ident == TRIM_SLOT_TAGS[slot]:
            return None
        return (f"{slot} tag {ident} is not {TRIM_SLOT_TAGS[slot]}, the tag Bedrock's {slot} slot takes "
                f"({MOJANG_SOURCE}); its members can't be checked here")
    if ident in VANILLA_TRIM_ITEMS[slot]:
        return None
    return (f"{slot} {ident} is not {_WHAT[slot]} in Bedrock: it is not in Bedrock's "
            f"{TRIM_SLOT_TAGS[slot]} ({WIKI_SOURCE}), and the {slot} slot takes only items with that tag "
            f"({MOJANG_SOURCE})")


def addon_refusal(slot: str, ident: str) -> str:
    """Why an add-on's own item can't be the template or addition of a trim."""
    what = "trim pattern" if slot == "template" else "trim material"
    return (f"{slot} {ident} is this pack's own item, and a Bedrock add-on can't register a {what}: "
            f"BDS refuses it even when it carries {TRIM_SLOT_TAGS[slot]} (\"should be a valid {what}\", "
            f"{PROBE_SOURCE})")


def _tags(components: dict) -> list | None:
    found = components.get("minecraft:tags")
    found = found.get("tags") if isinstance(found, dict) else None
    return found if isinstance(found, list) else None


def addon_base_refusal(ident: str, components: dict | None) -> str | None:
    """Why the pack's own ``ident`` can't be a trim base (``components`` of its
    item definition, None for a block), or None."""
    if components is None:
        return f"base {ident} is a block, and the base must be armor ({MOJANG_SOURCE})"
    if not isinstance(components.get("minecraft:wearable"), dict):
        return (f"base {ident} has no minecraft:wearable, so it isn't armor in Bedrock, and the base must be "
                f"armor (\"should be an armor, but isn't\", {PROBE_SOURCE}; {MOJANG_SOURCE})")
    if TRIM_SLOT_TAGS["base"] not in (_tags(components) or []):
        return (f"base {ident} doesn't carry {TRIM_SLOT_TAGS['base']}, which the base slot needs "
                f"({MOJANG_SOURCE})")
    return None


def item_tag_refusal(ident: str, components: dict) -> str | None:
    """Why an add-on item's trim tag puts an item Bedrock refuses into Mojang's
    own trim recipe, or None."""
    tags = _tags(components)
    if not tags:
        return None
    if TRIM_SLOT_TAGS["template"] in tags:
        return (f"{ident} carries {TRIM_SLOT_TAGS['template']}, but an add-on can't register a trim pattern, "
                f"and the tag makes BDS refuse Mojang's own minecraft:smithing_armor_trim ({PROBE_SOURCE})")
    if TRIM_SLOT_TAGS["addition"] in tags:
        return (f"{ident} carries {TRIM_SLOT_TAGS['addition']}, but an add-on can't register a trim material: "
                f"BDS refuses an add-on item as a trim addition even with the tag ({PROBE_SOURCE}), so the "
                "tag puts an item Bedrock refuses into Mojang's own minecraft:smithing_armor_trim")
    if TRIM_SLOT_TAGS["base"] in tags and not isinstance(components.get("minecraft:wearable"), dict):
        return (f"{ident} carries {TRIM_SLOT_TAGS['base']} without minecraft:wearable, so it isn't armor, and "
                f"the tag makes BDS refuse Mojang's own minecraft:smithing_armor_trim (\"should be an armor, "
                f"but isn't\", {PROBE_SOURCE})")
    return None
