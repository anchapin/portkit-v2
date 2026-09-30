"""Crafting recipes.

Java recipe JSON and Bedrock recipe JSON are both declarative, so this is a
mapping table, not an inference problem. Anything not in the table becomes an
Unhandled item rather than a plausible-looking guess.
"""
from __future__ import annotations

import json

from ..model import ConversionResult, SourceMod, Unhandled

_SUPPORTED = {
    "minecraft:crafting_shaped": "minecraft:recipe_shaped",
    "minecraft:crafting_shapeless": "minecraft:recipe_shapeless",
    "minecraft:smelting": "minecraft:recipe_furnace",
}


def _item(spec) -> dict | None:
    """Java item specs come in several shapes. Only translate the unambiguous ones."""
    if isinstance(spec, str):
        return {"item": spec}
    if isinstance(spec, dict):
        if "item" in spec:
            return {"item": spec["item"]}
        if "id" in spec:
            return {"item": spec["id"]}
    # tags and weighted lists have no clean 1:1 Bedrock form
    return None


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
        bedrock_type = _SUPPORTED.get(java_type)
        if bedrock_type is None:
            result.unhandled.append(
                Unhandled(rel, "recipe", f"unsupported recipe type {java_type!r}")
            )
            continue

        identifier = f"{mod.namespace}:{path.stem}"
        body: dict = {
            "description": {"identifier": identifier},
            "tags": ["crafting_table"],
        }

        if java_type == "minecraft:crafting_shaped":
            key = {}
            unmapped = False
            for symbol, spec in (recipe.get("key") or {}).items():
                mapped = _item(spec)
                if mapped is None:
                    unmapped = True
                    break
                key[symbol] = mapped
            if unmapped:
                result.unhandled.append(
                    Unhandled(rel, "recipe", "ingredient uses a tag or item list")
                )
                continue
            body["pattern"] = recipe.get("pattern", [])
            body["key"] = key
        elif java_type == "minecraft:crafting_shapeless":
            ingredients = [_item(i) for i in recipe.get("ingredients", [])]
            if any(i is None for i in ingredients):
                result.unhandled.append(
                    Unhandled(rel, "recipe", "ingredient uses a tag or item list")
                )
                continue
            body["ingredients"] = ingredients
        else:  # smelting
            ingredient = _item(recipe.get("ingredient"))
            if ingredient is None:
                result.unhandled.append(
                    Unhandled(rel, "recipe", "ingredient uses a tag or item list")
                )
                continue
            body["tags"] = ["furnace"]
            body["input"] = ingredient

        out = _item(recipe.get("result"))
        if out is None:
            result.unhandled.append(Unhandled(rel, "recipe", "unreadable result item"))
            continue
        count = 1
        if isinstance(recipe.get("result"), dict):
            count = recipe["result"].get("count", 1)
        body["result"] = {**out, "count": count} if count != 1 else out

        result.files[f"recipes/{path.stem}.json"] = {
            "format_version": "1.20.10",
            bedrock_type: body,
        }
    return result
