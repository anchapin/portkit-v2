"""Item definitions.

Java describes an item's appearance in a model file and everything else about
it, stack size, food, durability, tool tier, in compiled code. Bedrock wants a
behavior pack item with components.

So the honest mapping is narrow: a plain generated item becomes a Bedrock item
with its icon. A tool, a piece of armor, or anything whose model says it is
held in the hand is refused, because converting the icon and losing the
behavior gives a player an item that looks like a pickaxe and mines nothing.

Block items are skipped rather than refused: Bedrock registers an item for a
custom block automatically, so emitting one here would fight the block.
"""
from __future__ import annotations

import json

from ..model import ConversionResult, SourceMod, Unhandled
from . import models

# The only Java item model parents whose meaning is fully in the JSON.
_FLAT_PARENTS = ("minecraft:item/generated", "item/generated")

# Parents that mean behavior lives in code. Named separately so the residue can
# say what the item actually is instead of "unsupported parent".
_BEHAVIOR_PARENTS = {
    "minecraft:item/handheld": "a held tool, whose mining behavior lives in compiled code",
    "minecraft:item/handheld_rod": "a held tool, whose behavior lives in compiled code",
    "minecraft:item/handheld_mace": "a held weapon, whose behavior lives in compiled code",
    "minecraft:item/template_bow": "a bow, whose draw behavior lives in compiled code",
}

_MENU_CATEGORY = "items"
_DEFAULT_STACK_SIZE = 64


def _block_names(mod: SourceMod) -> set[str]:
    """Names that already exist as blocks, so their item is Bedrock's to make."""
    states = mod.assets / "blockstates"
    if not states.is_dir():
        return set()
    return {p.stem for p in states.glob("*.json")}


def convert(mod: SourceMod) -> ConversionResult:
    result = ConversionResult()
    src = mod.assets / "models" / "item"
    if not src.is_dir():
        return result

    blocks = _block_names(mod)
    for path in sorted(src.glob("*.json")):
        name = path.stem
        if name in blocks:
            # The block converter owns this one; claiming it keeps it off the
            # unowned list without producing a competing definition.
            result.claim(mod, path)
            continue

        rel = result.claim(mod, path)
        try:
            model = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            result.unhandled.append(Unhandled(rel, "item", f"invalid JSON: {exc}"))
            continue

        parent = model.get("parent")
        if parent in _BEHAVIOR_PARENTS:
            result.unhandled.append(Unhandled(rel, "item", _BEHAVIOR_PARENTS[parent]))
            continue
        if parent not in _FLAT_PARENTS:
            result.unhandled.append(
                Unhandled(rel, "item", f"item model parent {parent!r} is not a flat icon")
            )
            continue
        if model.get("overrides"):
            result.unhandled.append(
                Unhandled(
                    rel,
                    "item",
                    "model swaps texture on item properties (damage, pulling), "
                    "which Bedrock expresses in code",
                )
            )
            continue

        textures = model.get("textures") or {}
        layers = sorted(k for k in textures if k.startswith("layer"))
        if not layers:
            result.unhandled.append(Unhandled(rel, "item", "model has no layer0 texture"))
            continue
        if len(layers) > 1:
            result.unhandled.append(
                Unhandled(
                    rel,
                    "item",
                    f"model stacks {len(layers)} texture layers; Bedrock icons are one texture",
                )
            )
            continue

        reference = textures[layers[0]]
        ref_ns, _, rel_path = reference.rpartition(":")
        if ref_ns and ref_ns != mod.namespace:
            result.unhandled.append(
                Unhandled(rel, "item", f"icon {reference!r} is a texture from another namespace")
            )
            continue

        icon, why = models.texture_shortname(reference, mod.namespace)
        if icon is None:
            result.unhandled.append(Unhandled(rel, "item", why))
            continue
        result.files[f"items/{name}.json"] = {
            "format_version": "1.20.10",
            "minecraft:item": {
                "description": {
                    "identifier": f"{mod.namespace}:{name}",
                    "menu_category": {"category": _MENU_CATEGORY},
                },
                "components": {
                    "minecraft:icon": icon,
                    "minecraft:max_stack_size": _DEFAULT_STACK_SIZE,
                },
            },
        }
    return result
