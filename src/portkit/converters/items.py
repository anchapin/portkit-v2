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

An item model alone is not an item (#158). A 1.12 mod ships one model per
metadata variant (``upgrade_storage_obsidian``) and a modern mod ships override
models (``twinbound_feather_brushing_0``), while Java registers one item and
picks the look by metadata, NBT or a model override. So an item is emitted
only when its id is one the source registers, by the same test the residue
agent's item guard uses (:func:`portkit.registry.registered_ids`, under
:func:`bedrock_identifier`). A skipped variant's model is claimed and
explained in a note rather than sent to the residue: the agent may not write
the item either. Its texture is not dropped: the textures converter ships it
like every other item texture, and the note names it as a variant texture of
the registered item it belongs to. Nothing in the pack switches to it, since
the switch lives in Java code.
"""
from __future__ import annotations

import json

from ..model import ConversionResult, SourceMod, Unhandled
from ..registry import registered_ids, variant_of
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


def bedrock_identifier(namespace: str, name: str) -> str:
    """The Bedrock id the converter gives a Java item or block ``namespace:name``.

    Identity on purpose: Bedrock keeps the Java id. The residue agent's item
    guard (``portkit.agent.items``) maps Java ids through this same function,
    so a deterministic mapping always passes it.
    """
    return f"{namespace}:{name}"


def _block_names(mod: SourceMod) -> set[str]:
    """Names that already exist as blocks, so their item is Bedrock's to make."""
    states = mod.assets / "blockstates"
    if not states.is_dir():
        return set()
    return {p.stem for p in states.glob("*.json")}


def _layer0(path) -> str | None:
    """The single icon texture a flat item model names, if it is one."""
    try:
        model = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    textures = model.get("textures") if isinstance(model, dict) else None
    layer = textures.get("layer0") if isinstance(textures, dict) else None
    return layer if isinstance(layer, str) else None


def _texture_file(mod: SourceMod, reference: str) -> bool:
    """Whether the texture a model names is a png in this mod's textures."""
    path = reference.rpartition(":")[2]
    return (mod.assets / "textures" / f"{path}.png").is_file()


def _variant_notes(mod: SourceMod, src, variants: list[tuple[str, str]], java: set[str]) -> list[str]:
    """One note per registered item whose unregistered variant models were skipped."""
    groups: dict[str | None, list[tuple[str, str]]] = {}
    for name, reference in variants:
        parent = variant_of(f"{mod.namespace}:{name}", java)
        groups.setdefault(parent, []).append((name, reference))
    notes = []
    for parent, members in sorted(groups.items(), key=lambda kv: (kv[0] is None, kv[0] or "")):
        names = ", ".join(n for n, _ in members)
        them = "them" if len(members) > 1 else "it"
        what = (
            f"item models {names} are not registered items" if len(members) > 1
            else f"item model {names} is not a registered item"
        )
        note = (
            f"{parent or mod.namespace}: {what} (no blockstate, lang key, recipe, tag or "
            f"loot table names {them}), so no Bedrock item was written for {them}."
        )
        if parent:
            note += (
                f" The source registers {parent}; Java picks the variant look by metadata, "
                f"NBT or an item model override, so nothing in the pack switches to {them}."
            )
        own = _layer0(src / f"{parent.split(':', 1)[1]}.json") if parent else None
        kept = sorted({ref for _, ref in members if ref != own and _texture_file(mod, ref)})
        if kept:
            many = len(kept) > 1
            role = ("variant texture" if parent else "texture") + ("s" if many else "")
            role += f" of {parent}" if parent else ""
            note += (
                f" {'These' if many else 'The'} {role} ({', '.join(kept)}) "
                f"{'are' if many else 'is'} not dropped: the textures converter ships "
                f"{'them' if many else 'it'} like any other texture, or lists "
                f"{'them' if many else 'it'} in the residue with the reason it could not."
            )
        notes.append(note)
    return notes


def convert(mod: SourceMod) -> ConversionResult:
    result = ConversionResult()
    src = mod.assets / "models" / "item"
    if not src.is_dir():
        return result

    blocks = _block_names(mod)
    java: set[str] | None = None  # registered Java ids, read on the first item that needs them
    registered: set[str] = set()  # ...and their Bedrock ids under the converter's mapping
    variants: list[tuple[str, str]] = []  # (model name, texture) of skipped variants
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
        if java is None:
            java = registered_ids(mod.root)
            registered = {bedrock_identifier(*i.split(":", 1)) for i in java}
        if bedrock_identifier(mod.namespace, name) not in registered:
            # Only the item model names it: a per-variant look, not an item.
            variants.append((name, reference))
            continue
        result.files[f"items/{name}.json"] = {
            "format_version": "1.20.10",
            "minecraft:item": {
                "description": {
                    "identifier": bedrock_identifier(mod.namespace, name),
                    "menu_category": {"category": _MENU_CATEGORY},
                },
                "components": {
                    "minecraft:icon": icon,
                    "minecraft:max_stack_size": _DEFAULT_STACK_SIZE,
                },
            },
        }
    if variants:
        result.notes.extend(_variant_notes(mod, src, variants, java or set()))
    return result
