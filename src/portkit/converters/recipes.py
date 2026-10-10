"""Crafting recipes.

Java recipe JSON and Bedrock recipe JSON are both declarative, so this is a
mapping table, not an inference problem. Anything not in the table becomes an
Unhandled item rather than a plausible-looking guess.
"""
from __future__ import annotations

import json

from ..model import ConversionResult, SourceMod, Unhandled

# Java type -> (Bedrock body key, crafting tags).
# Bedrock has no separate stonecutter recipe type: a stonecutter recipe is a
# shapeless one tagged for that block, which is also how the vanilla packs do it.
_SUPPORTED = {
    "minecraft:crafting_shaped": ("minecraft:recipe_shaped", ["crafting_table"]),
    "minecraft:crafting_shapeless": ("minecraft:recipe_shapeless", ["crafting_table"]),
    "minecraft:smelting": ("minecraft:recipe_furnace", ["furnace"]),
    "minecraft:blasting": ("minecraft:recipe_furnace", ["blast_furnace"]),
    "minecraft:smoking": ("minecraft:recipe_furnace", ["smoker"]),
    "minecraft:campfire_cooking": ("minecraft:recipe_furnace", ["campfire", "soul_campfire"]),
    "minecraft:stonecutting": ("minecraft:recipe_shapeless", ["stonecutter"]),
}

_FURNACE_TYPES = {
    "minecraft:smelting",
    "minecraft:blasting",
    "minecraft:smoking",
    "minecraft:campfire_cooking",
}

# Types with a real Bedrock equivalent we deliberately do not attempt yet, so the
# residue says why instead of "unsupported".
_KNOWN_UNSUPPORTED = {
    "minecraft:smithing_trim": "armour trims have no Bedrock recipe form",
    "minecraft:crafting_transmute": "transmute recipes have no Bedrock equivalent",
}

# Convention tags that name exactly one vanilla item. Both loaders ship these
# (Forge under forge:, Fabric and NeoForge under c:) and a mod using one means
# the single vanilla item in practice. Anything not here stays residue: a tag
# covering several items is a choice, and guessing which one is how you ship a
# recipe that crafts the wrong thing.
_SINGLE_ITEM_TAGS = {
    "ingots/iron": "minecraft:iron_ingot",
    "ingots/gold": "minecraft:gold_ingot",
    "ingots/copper": "minecraft:copper_ingot",
    "ingots/netherite": "minecraft:netherite_ingot",
    "ingots/brick": "minecraft:brick",
    "gems/diamond": "minecraft:diamond",
    "gems/emerald": "minecraft:emerald",
    "gems/lapis": "minecraft:lapis_lazuli",
    "gems/quartz": "minecraft:quartz",
    "gems/amethyst": "minecraft:amethyst_shard",
    "gems/prismarine": "minecraft:prismarine_shard",
    "dusts/redstone": "minecraft:redstone",
    "dusts/glowstone": "minecraft:glowstone_dust",
    "rods/wooden": "minecraft:stick",
    "rods/blaze": "minecraft:blaze_rod",
    "nuggets/iron": "minecraft:iron_nugget",
    "nuggets/gold": "minecraft:gold_nugget",
    "leather": "minecraft:leather",
    "string": "minecraft:string",
    "gunpowder": "minecraft:gunpowder",
    "obsidian": "minecraft:obsidian",
    "ender_pearls": "minecraft:ender_pearl",
    "slimeballs": "minecraft:slime_ball",
    "feathers": "minecraft:feather",
    "bones": "minecraft:bone",
    "eggs": "minecraft:egg",
    "netherrack": "minecraft:netherrack",
    "glowstone": "minecraft:glowstone",
}
_TAG_NAMESPACES = ("forge:", "c:", "neoforge:")

# Vanilla tags Bedrock's own recipes take as ingredients, under the same name
# and meaning as Java's. Read from Mojang/bedrock-samples behavior_pack/recipes
# on 2026-10-02 (e.g. torch and campfire take {"tag": "minecraft:coals"}, soul
# campfire takes minecraft:soul_fire_base_blocks). These pass through as tags,
# so the recipe accepts the same set of items it does in Java. Bedrock tags with
# no Java twin of the same name (is_pickaxe, mushrooms_for_stew, metal_nuggets,
# trim_*) are left out on purpose.
_BEDROCK_VANILLA_TAGS = frozenset({
    "minecraft:coals",
    "minecraft:logs",
    "minecraft:logs_that_burn",
    "minecraft:planks",
    "minecraft:soul_fire_base_blocks",
    "minecraft:stone_crafting_materials",
    "minecraft:stone_tool_materials",
    "minecraft:wooden_slabs",
    "minecraft:wool",
})


def resolve_tag(tag: str) -> str | None:
    """A convention tag that unambiguously means one vanilla item, or None."""
    for prefix in _TAG_NAMESPACES:
        if tag.startswith(prefix):
            return _SINGLE_ITEM_TAGS.get(tag[len(prefix):])
    return None


def _item(spec) -> dict | None:
    """Java item specs come in several shapes. Only translate the unambiguous ones."""
    if isinstance(spec, str):
        return {"item": spec}
    if isinstance(spec, dict):
        if "item" in spec:
            return {"item": spec["item"]}
        if "id" in spec:
            return {"item": spec["id"]}
        if "tag" in spec:
            if str(spec["tag"]) in _BEDROCK_VANILLA_TAGS:
                return {"tag": str(spec["tag"])}
            resolved = resolve_tag(str(spec["tag"]))
            return {"item": resolved} if resolved else None
    # multi-item tags and weighted lists have no clean 1:1 Bedrock form
    return None


def _tag_reason(spec) -> str:
    if isinstance(spec, dict) and "tag" in spec:
        return f"ingredient uses tag {spec['tag']!r}, which covers more than one item"
    return "ingredient uses a tag or item list"


def _smithing_item(spec) -> str | None:
    """Bedrock smithing slots take a bare item id; a multi-item tag has no form."""
    mapped = _item(spec)
    return mapped.get("item") if mapped else None


def _smithing(recipe: dict, identifier: str, rel: str, result: ConversionResult):
    """A Java smithing_transform, as Bedrock's smithing or (when incomplete) crafting.

    Complete (template, base and addition all name an item): Bedrock has the
    same recipe, ``minecraft:recipe_smithing_transform`` on the smithing table.

    Incomplete (template or addition missing): Bedrock's smithing recipe needs
    all three, and inventing the missing ones changes what the player has to
    gather (#87). So it becomes a shapeless crafting recipe from the inputs the
    source does name to its result, and the downgrade is said in the notes.
    Returns (body key, body) or None when the recipe went to residue.
    """
    slots = {}
    for slot in ("template", "base", "addition"):
        spec = recipe.get(slot)
        if spec in (None, "", {}, []):
            continue
        item = _smithing_item(spec)
        if item is None:
            result.unhandled.append(Unhandled(rel, "recipe", f"smithing {slot}: {_tag_reason(spec)}"))
            return None
        slots[slot] = item
    out = _smithing_item(recipe.get("result"))
    if out is None or "base" not in slots:
        result.unhandled.append(
            Unhandled(rel, "recipe", "smithing recipe has no readable base or result item")
        )
        return None
    description = {"identifier": identifier}
    if len(slots) == 3:
        return "minecraft:recipe_smithing_transform", {
            "description": description,
            "tags": ["smithing_table"],
            "template": slots["template"],
            "base": slots["base"],
            "addition": slots["addition"],
            "result": out,
        }
    missing = [s for s in ("template", "addition") if s not in slots]
    result.notes.append(
        f"{rel}: smithing recipe has no {' or '.join(missing)}, which Bedrock's smithing "
        "table requires; converted to a shapeless crafting recipe from the inputs it names"
    )
    return "minecraft:recipe_shapeless", {
        "description": description,
        "tags": ["crafting_table"],
        "ingredients": [{"item": slots[s]} for s in ("template", "base", "addition") if s in slots],
        "result": {"item": out},
    }


def convert(mod: SourceMod) -> ConversionResult:
    result = ConversionResult()
    for lane in ("recipes", "recipe"):
        src = mod.data / lane
        if src.is_dir():
            break
    else:
        return result

    for path in sorted(src.rglob("*.json")):
        rel = result.claim(mod, path)
        try:
            recipe = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            result.unhandled.append(Unhandled(rel, "recipe", f"invalid JSON: {exc}"))
            continue

        java_type = recipe.get("type")
        if java_type == "minecraft:smithing_transform":
            converted = _smithing(recipe, f"{mod.namespace}:{path.stem}", rel, result)
            if converted is not None:
                body_key, body = converted
                result.files[f"recipes/{path.stem}.json"] = {
                    "format_version": "1.20.10",
                    body_key: body,
                }
            continue
        mapping = _SUPPORTED.get(java_type)
        if mapping is None:
            why = _KNOWN_UNSUPPORTED.get(
                java_type, f"unsupported recipe type {java_type!r}"
            )
            result.unhandled.append(Unhandled(rel, "recipe", why))
            continue
        bedrock_type, tags = mapping

        identifier = f"{mod.namespace}:{path.stem}"
        body: dict = {
            "description": {"identifier": identifier},
            "tags": list(tags),
        }

        if java_type == "minecraft:crafting_shaped":
            key = {}
            unmapped = ""
            for symbol, spec in (recipe.get("key") or {}).items():
                mapped = _item(spec)
                if mapped is None:
                    unmapped = _tag_reason(spec)
                    break
                key[symbol] = mapped
            if unmapped:
                result.unhandled.append(Unhandled(rel, "recipe", unmapped))
                continue
            body["pattern"] = recipe.get("pattern", [])
            body["key"] = key
        elif java_type == "minecraft:crafting_shapeless":
            specs = recipe.get("ingredients", [])
            ingredients = [_item(i) for i in specs]
            if any(i is None for i in ingredients):
                bad = next(s for s, i in zip(specs, ingredients) if i is None)
                result.unhandled.append(Unhandled(rel, "recipe", _tag_reason(bad)))
                continue
            body["ingredients"] = ingredients
        elif java_type == "minecraft:stonecutting":
            # One input, one output, expressed as a shapeless recipe on the stonecutter.
            ingredient = _item(recipe.get("ingredient"))
            if ingredient is None:
                result.unhandled.append(
                    Unhandled(rel, "recipe", _tag_reason(recipe.get("ingredient")))
                )
                continue
            body["ingredients"] = [ingredient]
        else:  # the furnace family
            ingredient = _item(recipe.get("ingredient"))
            if ingredient is None:
                result.unhandled.append(
                    Unhandled(rel, "recipe", _tag_reason(recipe.get("ingredient")))
                )
                continue
            body["input"] = ingredient

        out = _item(recipe.get("result"))
        if out is None:
            result.unhandled.append(Unhandled(rel, "recipe", "unreadable result item"))
            continue
        count = 1
        if isinstance(recipe.get("result"), dict):
            count = recipe["result"].get("count", 1)
        elif "count" in recipe:
            # stonecutting keeps the count beside the result, not inside it
            count = recipe["count"]
        body["result"] = {**out, "count": count} if count != 1 else out

        result.files[f"recipes/{path.stem}.json"] = {
            "format_version": "1.20.10",
            bedrock_type: body,
        }
    return result
