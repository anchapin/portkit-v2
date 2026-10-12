"""Crafting recipes.

Java recipe JSON and Bedrock recipe JSON are both declarative, so this is a
mapping table, not an inference problem. Anything not in the table becomes an
Unhandled item rather than a plausible-looking guess.

Ingredients that are tags with several members (#160) convert only when the
tag's whole membership is known (see :mod:`portkit.converters.tags`: a shared
``c:``/``forge:``/``neoforge:``/``fabric:``/``minecraft:`` tag needs the fetched
loader and vanilla data) and every member is either vanilla or a block or item
this conversion emits (``emitted``, filled by
:func:`portkit.converters.convert_all`). Three forms, in order:

1. Bedrock vanilla tag. When the membership is exactly that of one of the
   vanilla tags Bedrock's own recipes take under the same name and meaning
   (:data:`_BEDROCK_VANILLA_TAGS`, membership from the vanilla reference data),
   the recipe takes that tag. When the Java tag *is* one of those and the mod
   adds its own members to it (Silent Gear's netherwood planks in
   ``minecraft:planks``), the recipe takes Bedrock's tag and each of the mod's
   members carries it: an item in its ``minecraft:tags``, a block through an
   item that replaces the block's own item and carries the tag (see
   :func:`_block_item`). If one of them can't (a block that already has an
   item file), a single-slot ingredient keeps the tag recipe and gets one more
   recipe per mod member beside it (``<recipe>__<member>.json``); anything
   else stays residue. Bedrock's tag on its own would drop the mod's members.
2. Native tag. When the mod's members are items or blocks this conversion
   emits, the recipe keeps ``{"tag": "<java tag id>"}``: each member item gets
   the tag in its ``minecraft:tags`` component, and each member block gets an
   item form carrying it (see :func:`_block_item`; a block's own
   ``minecraft:tags`` are block tags, which recipes don't read). A vanilla item
   can't be given a tag by an add-on, nor can a block with its own item file;
   when the tag holds such members and at least two of the mod's own, a
   single-slot ingredient keeps the tag recipe and gets one recipe per such
   member beside it (``<recipe>__<member>.json``, at most
   :data:`EXPANSION_CAP`). Create's ``stone_types`` tags (14 blocks and one
   vanilla stone) take this form.
3. One recipe per member. Otherwise, when the recipe has exactly one such
   ingredient left, it fills exactly one grid slot, and the tag has at most
   :data:`EXPANSION_CAP` members, each member gets its own recipe. One slot
   only, because a tag filling several slots lets the player mix members, and
   per-member recipes would forbid that. Furnace recipes always take this
   form, since Bedrock's furnace input is one item id.

Anything else stays residue, and the reason names any members this conversion
did not emit. A recipe is never narrowed to part of a tag.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass

from ..model import ConversionResult, SourceMod, Unhandled
from ..data import FETCH_COMMAND
from .tags import MultiMembers, TagResolver

# Most members a single-slot tag ingredient is expanded into, one recipe each.
# 16 covers a full dye-colour set; a bigger tag is a family (every drawer, every
# cast) whose recipe would flood the recipe book, so it stays residue.
EXPANSION_CAP = 16

# minecraft:tags on an item needs item format_version 1.20.50 or later
# (learn.microsoft.com, Items Documentation - minecraft:tags).
_ITEM_TAGS_FORMAT = "1.20.50"
# minecraft:block_placer's replace_block_item needs item format_version 1.21.50
# or later (learn.microsoft.com, Items Documentation - minecraft:block_placer).
_BLOCK_ITEM_FORMAT = "1.21.50"

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
    "minecraft:smithing_trim": (
        "an armour trim; Bedrock has minecraft:recipe_smithing_trim, but its slots only "
        "accept items carrying the trim_templates, trimmable_armors and trim_materials "
        "tags, and a custom item tagged trim_materials has no effect, so whether this "
        "trim can work on Bedrock is a judgment call"
    ),
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


def _item(spec, tags: TagResolver | None = None) -> dict | None:
    """Java item specs come in several shapes. Only translate the unambiguous ones."""
    if isinstance(spec, str):
        return {"item": spec}
    if isinstance(spec, dict):
        if "item" in spec:
            return {"item": spec["item"]}
        if "id" in spec:
            return {"item": spec["id"]}
        if "tag" in spec:
            if _passes_through(str(spec["tag"]), tags):
                return {"tag": str(spec["tag"])}
            resolved = resolve_tag(str(spec["tag"]))
            if resolved and not (tags is not None and tags.own_share(str(spec["tag"]))):
                # The table names the loader's one vanilla member; a mod that adds
                # its own item to the tag goes through the full membership instead,
                # so the recipe doesn't lose that item (#160).
                return {"item": resolved}
            if tags is not None:
                found = tags.resolve(str(spec["tag"])).item
                return {"item": found} if found else None
            return None
    # multi-item tags and weighted lists have no clean 1:1 Bedrock form
    return None


def _passes_through(tag: str, tags: TagResolver | None) -> bool:
    """Whether Bedrock's own tag of this name is the whole Java tag.

    True for a :data:`_BEDROCK_VANILLA_TAGS` tag the mod adds nothing to. When
    the mod adds its own members (Silent Gear's netherwood planks in
    ``minecraft:planks``), Bedrock's tag alone would drop them, so the recipe
    goes through the full membership instead (see :func:`convert`).
    """
    if tag not in _BEDROCK_VANILLA_TAGS:
        return False
    return tags is None or tags.mod_additions(tag) == []


def _tag_reason(spec, tags: TagResolver | None = None) -> str:
    if isinstance(spec, dict) and "tag" in spec and tags is not None:
        tag = str(spec["tag"])
        nested = tags.unknown_nested(tag) if tag in _BEDROCK_VANILLA_TAGS else []
        if nested and tags.mod_additions(tag) is None:
            # Bedrock has this tag, but without the vanilla tag data it can't be
            # told whether the jar's own share of a nested tag belongs in it.
            shown = ", ".join(nested[:3]) + (f" and {len(nested) - 3} more" if len(nested) > 3 else "")
            return (
                f"ingredient uses tag {tag!r}, which Bedrock also has, but this jar adds to "
                f"{shown}, which vanilla may nest in it, and without the vanilla tag data "
                f"(run `{FETCH_COMMAND}`) Bedrock's tag alone could drop those members"
            )
        return tags.resolve(tag).reason
    if isinstance(spec, dict) and "tag" in spec:
        return f"ingredient uses tag {spec['tag']!r}, which covers more than one item"
    return "ingredient uses a tag or item list"


def _smithing_item(spec, tags: TagResolver | None = None) -> str | None:
    """Bedrock smithing slots take a bare item id; a multi-item tag has no form."""
    mapped = _item(spec, tags)
    return mapped.get("item") if mapped else None


def _smithing(recipe: dict, identifier: str, rel: str, result: ConversionResult, tags=None):
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
        item = _smithing_item(spec, tags)
        if item is None:
            result.unhandled.append(Unhandled(rel, "recipe", f"smithing {slot}: {_tag_reason(spec, tags)}"))
            return None
        slots[slot] = item
    out = _smithing_item(recipe.get("result"), tags)
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


def emitted_definitions(files: dict) -> dict[str, tuple[str, str, dict]]:
    """identifier -> (kind, path, body) for every block and item definition in ``files``.

    kind is ``"item"``, ``"block"``, or ``"block_and_item"`` for a block that
    also has its own item file (path and body are then the first one seen).
    """
    found: dict[str, tuple[str, str, dict]] = {}
    for path, body in files.items():
        if not isinstance(body, dict):
            continue
        for key, kind in (("minecraft:item", "item"), ("minecraft:block", "block")):
            root = body.get(key)
            ident = ((root or {}).get("description") or {}).get("identifier") if isinstance(root, dict) else None
            if not isinstance(ident, str):
                continue
            if ident in found and found[ident][0] != kind:
                # A block with its own item file: which one a recipe slot sees
                # depends on how the player got it, so neither can be tagged alone.
                found[ident] = ("block_and_item", *found[ident][1:])
            else:
                found.setdefault(ident, (kind, path, body))
    return found


@dataclass
class _Multi:
    """A tag ingredient whose every member this addon holds."""

    spec: dict
    found: MultiMembers
    # Every member of this mod can carry the Java tag as a native tag: an
    # emitted item in its minecraft:tags, an emitted block through a replacing
    # block_placer item (see _block_item). Members that can't (vanilla items,
    # a block that has its own item file) are in ``extras``.
    taggable: bool
    vanilla_tag: str | None = None  # a Bedrock vanilla tag with the same membership
    # A Bedrock vanilla tag of the same name whose every member this mod adds
    # can carry it: an emitted item, or an emitted block given an item form.
    bedrock_tag: bool = False
    # Members a native tag can't hold, each needing its own recipe beside the
    # tag recipe: vanilla items, and blocks that already have an item file.
    extras: list = None  # type: ignore[assignment]


def _bedrock_equivalent(found: MultiMembers, tags: TagResolver) -> str | None:
    """A Bedrock vanilla tag whose Java twin has exactly this membership, or None.

    Only the tags in :data:`_BEDROCK_VANILLA_TAGS`, whose Bedrock meaning matches
    Java's, and only when the vanilla reference data gives the twin's full
    membership: then ``{"tag": "minecraft:planks"}`` accepts the same items the
    Java tag does.
    """
    wanted = set(found.members)
    for candidate in sorted(_BEDROCK_VANILLA_TAGS):
        if candidate == found.tag:
            continue
        twin = tags.members(candidate)
        if (twin is not None and not twin.dropped and set(twin.members) == wanted
                and all(m.startswith("minecraft:") for m in twin.members)):
            # Bedrock's own tag holds only vanilla items, so a twin the mod
            # adds to is not the same set on Bedrock.
            return candidate
    return None


def _multi_tag(spec, tags: TagResolver, emitted: dict | None) -> _Multi | None:
    """The tag ingredient as a known, fully emitted membership, or None."""
    if emitted is None or not isinstance(spec, dict) or not isinstance(spec.get("tag"), str):
        return None
    found = tags.members(spec["tag"])
    if found is None or len(found.members) < 2:
        return None
    kinds = []
    for member in found.members:
        if member.startswith("minecraft:"):
            kinds.append("vanilla")
        elif member in emitted:
            kinds.append(emitted[member][0])
        else:
            return None  # a member this conversion did not emit: not ours to drop
    own = [k for k in kinds if k != "vanilla"]
    taggable = (not found.tag.startswith("minecraft:")
                and any(k in ("item", "block") for k in own))
    extras = [m for m, k in zip(found.members, kinds) if k in ("vanilla", "block_and_item")]
    # Bedrock's tag holds vanilla's whole share, so only when the jar's file
    # doesn't replace the tag (mod_additions is None then).
    bedrock_tag = (found.tag in _BEDROCK_VANILLA_TAGS and tags.mod_additions(found.tag) is not None
                   and all(k in ("vanilla", "item", "block") for k in kinds))
    return _Multi(spec=spec, found=found, taggable=taggable, vanilla_tag=_bedrock_equivalent(found, tags),
                  bedrock_tag=bedrock_tag, extras=extras)


def _not_emitted(spec, tags: TagResolver, emitted: dict | None) -> list[str]:
    """Members of a known tag ingredient that this conversion did not emit."""
    if emitted is None or not isinstance(spec, dict) or not isinstance(spec.get("tag"), str):
        return []
    found = tags.members(spec["tag"])
    if found is None:
        return []
    return [m for m in found.members if not m.startswith("minecraft:") and m not in emitted]


def _max_format(current, minimum: str) -> str:
    """The later of two dotted format versions."""
    def parse(text):
        try:
            return tuple(int(p) for p in str(text).split("."))
        except ValueError:
            return ()
    return current if isinstance(current, str) and parse(current) >= parse(minimum) else minimum


def _block_item(identifier: str, block_path: str) -> tuple[str, dict]:
    """(path, body) of an item standing in as a block's own item, to carry tags.

    A block's ``minecraft:tags`` are block tags; recipes match item tags. Since
    format 1.21.50 an item whose identifier is the block's and whose
    ``minecraft:block_placer`` sets ``replace_block_item`` becomes the block's
    item (what breaking or picking the block gives), and that item can carry
    ``minecraft:tags``. Vanilla does exactly this: bedrock-samples'
    ``items/shelf_mushroom.json`` replaces the block's item and tags it
    ``minecraft:mushrooms_for_stew``, which ``recipes/mushroom_stew.json`` takes
    as a tag (learn.microsoft.com, Items Documentation - minecraft:block_placer).
    No icon: a block placer without ``minecraft:icon`` renders the block. The
    display name is the block's lang key, as the vanilla samples do.
    """
    stem = block_path.rsplit("/", 1)[-1]
    return f"items/{stem}", {
        "format_version": _BLOCK_ITEM_FORMAT,
        "minecraft:item": {
            "description": {"identifier": identifier},
            "components": {
                "minecraft:block_placer": {"block": identifier, "replace_block_item": True},
                "minecraft:display_name": {"value": f"tile.{identifier}.name"},
            },
        },
    }


def _member_suffix(member: str) -> str:
    return member.replace(":", "_").replace("/", "_")


def convert(mod: SourceMod, emitted: dict | None = None) -> ConversionResult:
    """Convert the mod's recipes.

    ``emitted`` maps identifier -> (kind, path, body) for the blocks and items the
    earlier converters wrote (see :func:`emitted_definitions`). Without it a
    multi-member tag ingredient stays residue, as before #160.
    """
    result = ConversionResult()
    for lane in ("recipes", "recipe"):
        src = mod.data / lane
        if src.is_dir():
            break
    else:
        return result

    tag_resolver = TagResolver(mod)
    item_tags: dict[str, set[str]] = {}  # emitted item id -> native tags it must carry
    multi_used: dict[str, MultiMembers] = {}  # tags a converted recipe kept or expanded
    for path in sorted(src.rglob("*.json")):
        rel = result.claim(mod, path)
        try:
            recipe = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            result.unhandled.append(Unhandled(rel, "recipe", f"invalid JSON: {exc}"))
            continue

        java_type = recipe.get("type")
        if java_type == "minecraft:smithing_transform":
            converted = _smithing(recipe, f"{mod.namespace}:{path.stem}", rel, result, tag_resolver)
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

        # Ingredient positions as (spec, grid slots it fills). A shaped key
        # entry fills one slot per use in the pattern; everything else one.
        if java_type == "minecraft:crafting_shaped":
            pattern = recipe.get("pattern", [])
            used = "".join(row for row in pattern if isinstance(row, str))
            key_specs = list((recipe.get("key") or {}).items())
            positions = [(spec, used.count(symbol)) for symbol, spec in key_specs]
        elif java_type == "minecraft:crafting_shapeless":
            positions = [(spec, 1) for spec in recipe.get("ingredients", [])]
        else:  # stonecutting and the furnace family: one input
            positions = [(recipe.get("ingredient"), 1)]
        furnace = java_type in _FURNACE_TYPES

        mapped = [_item(spec, tag_resolver) for spec, _ in positions]
        failing = [i for i, m in enumerate(mapped) if m is None]
        multis = {i: _multi_tag(positions[i][0], tag_resolver, emitted) for i in failing}
        variants: list[tuple[str, list]] = [("", mapped)]  # (file suffix, ingredients)
        native: set[int] = set()  # ingredients written as this addon's own tag
        partly: list[int] = []  # native-tag candidates with members that can't carry it
        with_extras: int | None = None  # the native tag ingredient with extra recipes
        expanded: int | None = None  # the ingredient written once per member
        rest: list[int] = []  # tag ingredients only a per-member expansion could write
        if failing and all(multis.values()):
            ingredients = list(mapped)
            for i in failing:
                multi = multis[i]
                if not furnace and multi.vanilla_tag:
                    ingredients[i] = {"tag": multi.vanilla_tag}
                elif not furnace and multi.bedrock_tag:
                    # Bedrock's own tag, with this mod's members tagged into it.
                    ingredients[i] = {"tag": multi.found.tag}
                    native.add(i)
                elif not furnace and multi.taggable and not multi.extras:
                    ingredients[i] = {"tag": multi.found.tag}
                    native.add(i)
                elif not furnace and multi.taggable and len(multi.found.members) - len(multi.extras) >= 2:
                    # Worth it only when it writes fewer recipes than one per
                    # member: two or more of the mod's members share the tag.
                    partly.append(i)
                else:
                    rest.append(i)
            if (
                len(partly) == 1
                and not rest
                and positions[partly[0]][1] == 1
                and len(multis[partly[0]].extras) <= EXPANSION_CAP
            ):
                # The mod's members carry the tag; each member that can't (a
                # vanilla item, a block with its own item) gets its own recipe
                # beside the tag recipe. One slot only, as for every expansion.
                with_extras = partly[0]
                ingredients[with_extras] = {"tag": multis[with_extras].found.tag}
                native.add(with_extras)
            else:
                rest.extend(partly)
            own = ([m for m in multis[rest[0]].found.members if not m.startswith("minecraft:")]
                   if len(rest) == 1 else [])
            if not rest and with_extras is not None:
                variants = [("", ingredients)]
                for member in multis[with_extras].extras:
                    one = list(ingredients)
                    one[with_extras] = {"item": member}
                    variants.append((f"__{_member_suffix(member)}", one))
            elif not rest:
                variants = [("", ingredients)]
            elif (
                not furnace
                and len(rest) == 1
                and multis[rest[0]].found.tag in _BEDROCK_VANILLA_TAGS
                and tag_resolver.mod_additions(multis[rest[0]].found.tag) is not None
                and positions[rest[0]][1] == 1
                and len(own) <= EXPANSION_CAP
            ):
                # Bedrock's tag keeps the vanilla members; a member of this mod
                # that can't carry the tag gets its own recipe beside it.
                expanded = rest[0]
                ingredients[expanded] = {"tag": multis[expanded].found.tag}
                variants = [("", ingredients)]
                for member in own:
                    one = list(ingredients)
                    one[expanded] = {"item": member}
                    variants.append((f"__{_member_suffix(member)}", one))
            elif (
                len(rest) == 1
                and positions[rest[0]][1] == 1
                and len(multis[rest[0]].found.members) <= EXPANSION_CAP
            ):
                expanded = rest[0]
                variants = []
                for member in multis[expanded].found.members:
                    one = list(ingredients)
                    one[expanded] = {"item": member}
                    variants.append((f"__{_member_suffix(member)}", one))
            else:
                native = set()
        if any(m is None for _, ms in variants for m in ms):
            # Not expressible (or not fully known): the reason is the one the
            # first failing ingredient always had, plus which members this
            # conversion didn't emit when that is what blocks it.
            # A tag this conversion could have written isn't what blocks it.
            bad = positions[next((i for i in failing if multis[i] is None), (rest or failing)[0])][0]
            reason = _tag_reason(bad, tag_resolver)
            missing = _not_emitted(bad, tag_resolver, emitted)
            if missing:
                reason += f"; not converted: {', '.join(missing)}"
            result.unhandled.append(Unhandled(rel, "recipe", reason))
            continue

        if furnace:
            first = variants[0][1][0]
            if "item" not in first:
                # Bedrock's furnace input is one item id; a tag has no place there.
                result.unhandled.append(Unhandled(
                    rel, "recipe",
                    f"furnace input is tag {first.get('tag')!r}; Bedrock's furnace "
                    "recipe takes a single item id, not a tag",
                ))
                continue

        out = _item(recipe.get("result"), tag_resolver)
        if out is None:
            result.unhandled.append(Unhandled(rel, "recipe", "unreadable result item"))
            continue
        count = 1
        if isinstance(recipe.get("result"), dict):
            count = recipe["result"].get("count", 1)
        elif "count" in recipe:
            # stonecutting keeps the count beside the result, not inside it
            count = recipe["count"]
        if bedrock_type == "minecraft:recipe_furnace":
            # Bedrock names the product "output", a bare item id with no count
            # (learn.microsoft.com recipe_furnace reference). See #90.
            if "item" not in out:
                result.unhandled.append(Unhandled(rel, "recipe", "furnace result is a tag, not an item"))
                continue
            body["output"] = out["item"]
            if count != 1:
                result.notes.append(
                    f"{rel}: furnace result count {count} dropped; Bedrock's furnace "
                    "recipe output is a single item id and always yields one"
                )
        else:
            body["result"] = {**out, "count": count} if count != 1 else out

        if len(variants) > 1 and any(
            f"recipes/{path.stem}{suffix}.json" in result.files for suffix, _ in variants
        ):
            # A per-member file name another recipe already took: refuse rather
            # than overwrite either one.
            result.unhandled.append(Unhandled(rel, "recipe", _tag_reason(positions[failing[0]][0], tag_resolver)))
            continue

        for suffix, ingredients in variants:
            variant = copy.deepcopy(body)
            variant["description"]["identifier"] = f"{identifier}{suffix}"
            if java_type == "minecraft:crafting_shaped":
                variant["pattern"] = recipe.get("pattern", [])
                variant["key"] = {symbol: ing for (symbol, _), ing in zip(key_specs, ingredients)}
                # keep the field order the single-recipe form always had
                variant["result"] = variant.pop("result")
            elif furnace:
                variant["input"] = ingredients[0]["item"]
                variant["output"] = variant.pop("output")
            else:
                variant["ingredients"] = ingredients
                variant["result"] = variant.pop("result")
            result.files[f"recipes/{path.stem}{suffix}.json"] = {
                "format_version": "1.20.10",
                bedrock_type: variant,
            }
        for i, multi in multis.items():
            if multi is None:
                continue
            multi_used[multi.found.tag] = multi.found
            if i in native:
                for member in multi.found.members:
                    if not member.startswith("minecraft:") and member not in (multi.extras or []):
                        item_tags.setdefault(member, set()).add(multi.found.tag)
                if multi.found.tag in _BEDROCK_VANILLA_TAGS:
                    own = [m for m in multi.found.members if not m.startswith("minecraft:")]
                    result.notes.append(
                        f"{rel}: tag {multi.found.tag!r} also holds {', '.join(own)} from this mod, "
                        "so they carry Bedrock's tag of that name and the recipe takes it"
                    )
            elif multi.vanilla_tag and i != expanded:
                result.notes.append(
                    f"{rel}: tag {multi.found.tag!r} has the same members as Bedrock's "
                    f"{multi.vanilla_tag!r}, so the recipe takes that tag"
                )
        if with_extras is not None and with_extras in native:
            multi = multis[with_extras]
            result.notes.append(
                f"{rel}: tag {multi.found.tag!r} is carried by this mod's members, and "
                f"{', '.join(multi.extras)} (which can't carry it) got their own recipe "
                f"({path.stem}__<member>) beside the one taking the tag"
            )
        if expanded is not None and variants[0][0] == "":
            member_tag = multis[expanded].found.tag
            result.notes.append(
                f"{rel}: tag {member_tag!r} also holds {len(variants) - 1} of this mod's members "
                f"that can't carry Bedrock's tag of that name, so each got its own recipe "
                f"({path.stem}__<member>) beside the one taking the tag"
            )
        elif expanded is not None:
            member_tag = multis[expanded].found.tag
            result.notes.append(
                f"{rel}: tag {member_tag!r} has {len(variants)} members, which Bedrock "
                f"can't group under one tag here, so the recipe was written once per member "
                f"({path.stem}__<member>)"
            )

    for member, member_tags in sorted(item_tags.items()):
        kind, item_path, source_body = emitted[member]
        if kind == "block":
            item_path, item = _block_item(member, item_path)
            item["minecraft:item"]["components"]["minecraft:tags"] = {"tags": sorted(member_tags)}
            result.files[item_path] = item
            continue
        item = copy.deepcopy(source_body)
        components = item["minecraft:item"].setdefault("components", {})
        existing = components.get("minecraft:tags") or {}
        merged_tags = sorted(set(existing.get("tags") or []) | member_tags)
        components["minecraft:tags"] = {"tags": merged_tags}
        item["format_version"] = _max_format(item.get("format_version"), _ITEM_TAGS_FORMAT)
        result.files[item_path] = item
    for tag, found in sorted(multi_used.items()):
        for source in found.sources:
            result.consumed.add(source)
        if found.dropped:
            result.notes.append(
                f"tag {tag!r}: dropped {', '.join(found.dropped)}, which this addon cannot contain"
            )
    for tag, found in sorted(tag_resolver.resolved().items()):
        for source in found.sources:
            result.consumed.add(source)  # the tag files were read, so they are owned
        if found.note:
            result.notes.append(found.note)
    return result
