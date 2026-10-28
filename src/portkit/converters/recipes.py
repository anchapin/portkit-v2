"""Crafting recipes.

Java recipe JSON and Bedrock recipe JSON are both declarative, so this is a
mapping table, not an inference problem. Anything not in the table becomes an
Unhandled item rather than a plausible-looking guess.

Output names (#163): a recipe is written to ``recipes/<name>.json`` with the
identifier ``<namespace>:<name>``. ``<name>`` is the file's stem when no other
recipe file of the namespace shares it; when several do (Tinkers'
``world/wood/{greenheart,skyroot}/planks.json``), every one of them is named by
its whole path under ``recipes/``, folders joined with ``_``
(``world_wood_greenheart_planks``). See :func:`recipe_names`. No output is
ever written twice: a name another recipe already holds sends the later recipe
to residue saying which one holds it.

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
   :func:`_block_item`), and a block that already has its own item file
   through that item file (#302 pick 2). Bedrock's tag on its own would drop
   the mod's members.
2. Native tag. When the mod's members are items or blocks this conversion
   emits, the recipe keeps ``{"tag": "<java tag id>"}``: each member item gets
   the tag in its ``minecraft:tags`` component, and each member block gets an
   item form carrying it (see :func:`_block_item`; a block's own
   ``minecraft:tags`` are block tags, which recipes don't read). A block that
   already has its own item file carries the tag on that item file (Alex's
   pick 2 on #302, 2026-10-16), so the player holding it matches. A vanilla
   item can't be given a tag by an add-on; when the tag holds such members
   and at least two of the mod's own, a
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
4. One recipe per combination (#302 pick 1). Tags whose members are all
   vanilla items, filling several grid slots between them, are written once
   per combination of members the player can put there, each slot its own
   key symbol, when there are at most :data:`EXPANSION_CAP` combinations
   (nᵏ for n members over k slots); mirror images of a shaped grid and
   reorderings of a shapeless one are written once (see :func:`_combinations`).
   Forge's ``chests/wooden`` over two slots is three recipes.

A recipe refused only for tags none of whose members converted (every member
a mod item this conversion didn't emit) records those members in
``ConversionResult.unshipped_names``; the pipeline files it
``owned_by_residue`` when each has a residue entry of its own (#302 pick 3,
:func:`refine_owned`).

A recipe refused only because writing every mix Java accepts takes more than
:data:`EXPANSION_CAP` recipes (every ingredient's membership known, every
member vanilla or emitted and with a Bedrock id, and a form above fitting but
for the count) is still not converted (#302), but it is the explained kind
:data:`OVER_CAP`, naming each tag, its members, the slots it fills and the
count (#342, pending Alex). The converter records every recipe's result
(``ConversionResult.recipe_results``), so a refused recipe whose result is
itself residue goes with it (:func:`refine_owned`, #342).

An ingredient written as a JSON list of items (Java's "any of these"; Mythic
Metals' ``[{"item": "...:deepslate_adamantite_ore"}, {"item":
"...:adamantite_ore"}]``) is a membership the recipe states outright, so it
takes form 3 under the same conditions: every listed item vanilla or emitted,
the only such ingredient, one slot, at most :data:`EXPANSION_CAP` items. A list
gets no tag of its own (the mod declared none). Vanilla Bedrock writes its
"armour piece -> nugget" furnace recipes the same way, one per piece
(bedrock-samples ``behavior_pack/recipes/furnace_iron_helmet.json``). A list
holding a tag, or anything but plain item ids, stays residue.

Anything else stays residue, and the reason names any members this conversion
did not emit. A recipe is never narrowed to part of a tag.

Item ids (#261): every vanilla id a written recipe names is Bedrock's
(:func:`bedrock_item`, from GeyserMC/mappings: ``minecraft:bricks`` ->
``minecraft:brick_block``, ``minecraft:red_bed`` -> ``minecraft:bed`` data 14),
and once the whole pack is converted a recipe naming a mod item the pack doesn't
ship goes back to residue (:func:`drop_unshipped_recipes`): Bedrock refuses a
recipe naming an item it doesn't know.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from ..conditions import CONDITIONAL_TYPES, LoadContext, condition_keys
from ..model import ConversionResult, SourceMod, Unhandled
from ..data import FETCH_COMMAND
from ..data import java_items, vanilla_items
from ..data import trim_items
from ..data.smithing_bases import addon_slot_refusal, vanilla_base_refusal, vanilla_slot_refusal
from .recipe_unlock import ALWAYS_UNLOCKED, NEEDS_UNLOCK, advancement_index, unlock_entries, with_unlock
from .recipe_unlock import criteria as unlock_criteria
from .tags import MultiMembers, TagResolver


# Most members a single-slot tag ingredient is expanded into, one recipe each.
# 16 covers a full dye-colour set; a bigger tag is a family (every drawer, every
# cast) whose recipe would flood the recipe book, so it stays residue.
EXPANSION_CAP = 16

# The explained kind for a recipe refused only for the cap (#342, pending Alex).
OVER_CAP = "recipe_over_cap"

# minecraft:tags on an item needs item format_version 1.20.50 or later
# (learn.microsoft.com, Items Documentation - minecraft:tags).
_ITEM_TAGS_FORMAT = "1.20.50"
# The item tag each smithing-table slot takes (#263). Mojang bedrock-samples
# documentation/Recipes.html, recipe_smithing_transform: items "must have the
# minecraft:transform_templates / transformable_items / transform_materials
# tag to be accepted into the respective UI slot". A mod item a converted
# smithing recipe names in a slot carries that slot's tag (the Java recipe is
# the evidence that it goes there). The base must also be armor or a tool:
# BDS 1.26.52.3 rejects a base without minecraft:durability ("base item is
# not a piece of armor or equipment"), which only a cited adapter writes.
_SMITHING_SLOT_TAGS = {
    "template": "minecraft:transform_templates",
    "base": "minecraft:transformable_items",
    "addition": "minecraft:transform_materials",
}
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
    # minecraft:smithing_trim converts when Bedrock takes every slot, else it is
    # residue with the slot's reason (_smithing_trim, #272).
    "minecraft:crafting_transmute": "transmute recipes have no Bedrock equivalent",
    # alloy_forgery:forging is machine_recipe residue with a per-recipe reason
    # (its adapter, portkit.adapters.alloy_forgery, #171/#245).
}

# A recipe whose result Java computes in code, or that runs only at a station
# that is Java code, is residue of its own kind (#180): nothing in its JSON
# can become a fixed-result Bedrock recipe without inventing or dropping part
# of what it does (#87), so the residue agent skips it (agent/residue.py
# SKIP_KINDS) instead of writing a stand-in. docs/decisions.md, 2026-10-15.
CODE_RECIPE = "code_recipe"

# Keys any recipe may carry that say nothing about what it takes or makes:
# vanilla's recipe-book fields (group, category, show_notification) and the
# mod's loader's load-condition keys (conditions.condition_keys; decided
# before this point). A
# modded recipe type whose JSON holds nothing else is a "special" recipe: its
# serializer reads no ingredients and no result, so what it matches and what
# it builds are the mod's Java code (vanilla's SimpleCraftingRecipeSerializer
# reads "category" only; Supplementaries 1.20-3.1.43 ModRecipes registers its
# 13 such types through it, Alex's Mobs 1.22.9 AMRecipeRegistry its 2, both
# CustomRecipe subclasses, bytecode).
_NO_DATA_KEYS = frozenset({"type", "group", "category", "show_notification"})

# Modded types that do carry data, but whose station or result is code. Each
# reason is read from the mod's own code at the corpus pin (sources in the
# comments; docs/decisions.md, 2026-10-15). Bedrock side: its recipe types
# are shaped, shapeless, furnace (one input), brewing and smithing (agent
# reference topics, MicrosoftDocs/minecraft-creator @4186dc4), and the only
# block components that open a screen are minecraft:crafting_table and the
# experimental minecraft:block_entity container (vendored
# @minecraft/bedrock-schemas 1.26.60 bp/blocks), so a GUI station has no
# Bedrock screen to land in.
# The per-mod entries (type -> reason, each read from the mod's own code)
# live in each mod's adapter (portkit.adapters, #245) as CODE_RECIPES.


# A recipe that melts items into a mod's fluid, alloys fluids, or casts or
# fills items from a fluid (mostly the mod's own; a few take vanilla lava or
# water, still by the millibucket at a mod station) is residue of its own kind
# (#174). Bedrock add-ons
# can't define a fluid: the custom block component list has no fluid component
# (learn.microsoft.com, Block Components Documentation, updated 2026-08-25),
# and the Script API's only fluid surface is the cauldron-style
# BlockFluidContainerComponent ("used with blocks like cauldrons") whose
# FluidType enumeration is fixed to Water, Lava, PowderSnow and Potion
# (learn.microsoft.com scriptapi/minecraft/server/blockfluidcontainercomponent,
# .../fluidtype). So the molten metals, slimes and soups these recipes make or
# take, measured in millibuckets, have no Bedrock form, and the stations that
# run them (multiblock tanks, faucets, casting blocks, spouts) are block-entity
# code. An item-only stand-in (say, ingot in, cast part out) would drop the
# fluid amounts, temperatures and cooling times and invent an item step the mod
# doesn't have (#87). The residue agent skips the kind (agent/residue.py
# SKIP_KINDS). docs/decisions.md, 2026-10-15.
FLUID_RECIPE = "fluid_recipe"

# What Bedrock lacks, said once at the end of every fluid recipe's reason.
NO_BEDROCK_FLUID = (
    "Bedrock add-ons can't define a fluid or store a measured amount of one (no fluid block "
    "component; the script fluid container holds only water, lava, powder snow or potion, as a "
    "cauldron does), so a mod's fluid has no Bedrock form and the station that measures fluid in mB "
    "has nothing to build on; an item-only stand-in would drop the fluid amounts and invent a step"
)


def _adapter_reason(kind: str, java_type: object) -> str | None:
    """The fixed reason an adapter gives recipe type ``java_type`` under
    residue ``kind`` (#245), or None."""
    from ..adapters import recipe_reasons

    return recipe_reasons(kind).get(java_type) if isinstance(java_type, str) else None


def fluid_recipe_reason(java_type: object) -> str | None:
    """Why a recipe of this type makes, takes or moves a mod's fluid (#174),
    or None if it isn't one an adapter knows: a type an adapter registers as
    ``fluid_recipe`` (Tinkers' Construct's and Create's tables)."""
    return _adapter_reason(FLUID_RECIPE, java_type)


# A recipe that builds, modifies, repairs or takes apart a modular tool, or
# makes a part or material whose identity is stored on the stack, is residue
# of its own kind (#175). In Tinkers' Construct and Silent Gear a tool's
# numbers (durability, mining speed, attack, traits) are computed in Java at
# craft time from the materials of the parts it was built from, plus its
# modifiers, and stored per stack (NBT). A Bedrock item's components are fixed
# per item type in its JSON, so one Bedrock item can't be an iron-headed pick
# and a cobalt-headed pick at once; per-stack stats would need a scripted
# station and runtime (#175's large option), which doesn't exist. A stand-in
# with fixed stats is fabrication (#87, #135). The residue agent skips the
# kind (agent/residue.py SKIP_KINDS). docs/decisions.md, 2026-10-15.
MODULAR_TOOL = "modular_tool"

# What Bedrock lacks, said once at the end of every modular tool reason.
NO_PER_STACK_TOOL = (
    "a Bedrock item's components are fixed per item type, so a tool or part whose materials, stats "
    "and modifiers are computed in Java and stored on each stack has no single Bedrock item to write, "
    "and a stand-in with fixed numbers would invent them"
)


def modular_tool_reason(java_type: object) -> str | None:
    """Why a recipe of this type builds, changes or takes apart a modular tool
    (#175), or None if it isn't one an adapter knows: a type an adapter
    registers as ``modular_tool`` (Tinkers' Construct's and Silent Gear's)."""
    return _adapter_reason(MODULAR_TOOL, java_type)


# A recipe that runs in one of Mekanism's machines (#172) or Create's
# rotation-powered machines (#173) is residue of its own kind. The JSON names
# the inputs and outputs, but the machine is the mod's block-entity code. A
# Mekanism machine holds the inputs, outputs, energy and any chemical or
# fluid in its own slots and tanks, and works the recipe over ticks, faster or
# cheaper with upgrades (TileEntityProgressMachine L73-74 via
# MekanismUtils#getTicks; TileEntityRecipeMachine). A Bedrock custom block has
# no ticking inventory, tank or energy store, and Mekanism's chemicals (gases,
# infuse types, pigments, slurries) have no Bedrock form, so there is no
# Bedrock station to tag these for. A crafting stand-in at the machine block
# would be a gameplay change (instant, free, chance outputs dropped), which #172
# leaves to a decision; a scripted machine runtime doesn't exist yet. The
# residue agent skips the kind (agent/residue.py SKIP_KINDS).
# docs/decisions.md, 2026-10-15. Create's machines turn only while a
# rotational network (shafts and cogwheels from a power source) gives them
# speed, and work faster with more of it. The per-mod tables live in the
# adapters (portkit.adapters.mekanism.recipes, portkit.adapters.create, #245).
MACHINE_RECIPE = "machine_recipe"

# What Bedrock lacks, said once at the end of every machine recipe's reason.
NO_BEDROCK_MACHINE = (
    "a Bedrock custom block has no ticking inventory, tank or energy store, so there is no Bedrock "
    "station to run it (that needs a scripted machine runtime, #172), and an instant crafting "
    "stand-in at the machine block would drop the processing time and what the machine consumes"
)
NO_BEDROCK_MB = "Bedrock can't store a measured amount of fluid (#174)"


def machine_recipe_reason(java_type: object) -> str | None:
    """Why a recipe of this type runs in a Mekanism (#172) or Create (#173)
    machine, or None if it isn't one an adapter knows: a type an adapter
    registers as ``machine_recipe`` with a fixed reason (Alloy Forgery's
    forging reason reads the recipe; see :mod:`portkit.adapters`)."""
    return _adapter_reason(MACHINE_RECIPE, java_type)


def code_recipe_reason(java_type: object, recipe: dict, loader: str | None = None) -> str | None:
    """Why a recipe of this modded type is code (#180), or None if it isn't
    one this module knows to be: a type an adapter registers as
    ``code_recipe``, or a non-vanilla type whose JSON carries nothing but
    recipe-book fields and ``loader``'s load conditions (a "special" recipe)."""
    if not isinstance(java_type, str):
        return None
    known = _adapter_reason(CODE_RECIPE, java_type)
    if known is not None:
        return known
    if java_type.startswith("minecraft:"):
        return None
    if set(recipe) - _NO_DATA_KEYS - set(condition_keys(loader)):
        return None
    return (
        f"a special recipe ({java_type!r}): its JSON holds no ingredient and no result, only its type, "
        "so what it takes and what it makes are the mod's Java code; a Bedrock recipe would have to "
        "invent both"
    )

# A recipe whose type the mod's own code registers (a RecipeSerializer of its
# own, #358, part of #277; pending Alex, picks 1a-3a) is an explained residue
# kind. Java has no data-driven recipe types, so a type in the mod's own
# namespace, or one whose id the mod's code builds next to a recipe
# serializer, is read only by that code; Bedrock's recipe types are a fixed
# list an add-on can't extend. The reason names the type and what the
# bytecode reads (registering class, serializer, recipe class;
# portkit.recipetypes), and for a crafting-like variant (its JSON has the
# vanilla shaped/shapeless/stonecutting shape, or wraps a vanilla recipe)
# what Java does beyond that shape: extra keys, non-vanilla ingredient types,
# and the recipe class's overrides of matches/assemble/getRemainingItems.
# Pick 2a: such a variant converts as its vanilla type only when the recipe
# class read from bytecode extends that vanilla class, overrides none of
# those, and the JSON holds nothing beyond the vanilla shape; pick 3a: any
# extra keeps it residue (never approximated).
MOD_RECIPE_TYPE = "mod_recipe_type"

NO_BEDROCK_RECIPE_TYPE = (
    "Bedrock's recipe types are a fixed list (shaped, shapeless, furnace, brewing, smithing) "
    "that an add-on can't extend"
)

_SHAPES = {
    "minecraft:crafting_shaped": ("pattern", "key", "result"),
    "minecraft:crafting_shapeless": ("ingredients", "result"),
    "minecraft:stonecutting": ("ingredient", "result"),
}
_SHAPE_WORDS = {
    "minecraft:crafting_shaped": "vanilla shaped crafting's pattern, key and result",
    "minecraft:crafting_shapeless": "vanilla shapeless crafting's ingredients and result",
    "minecraft:stonecutting": "vanilla stonecutting's ingredient and result",
}


def _json_shape(recipe: dict) -> str | None:
    """The vanilla type whose shape the recipe's JSON has, or None."""
    if all(k in recipe for k in _SHAPES["minecraft:crafting_shaped"]):
        return "minecraft:crafting_shaped"
    if "pattern" in recipe:
        return None
    for vt in ("minecraft:crafting_shapeless", "minecraft:stonecutting"):
        if all(k in recipe for k in _SHAPES[vt]):
            return vt
    return None


def _ingredient_types(spec, out: set) -> None:
    """Every non-vanilla ingredient ``type`` in ``spec`` (an ingredient, a
    list of them, or a shaped key's values)."""
    if isinstance(spec, list):
        for s in spec:
            _ingredient_types(s, out)
    elif isinstance(spec, dict):
        t = spec.get("type")
        if isinstance(t, str) and not t.startswith("minecraft:"):
            out.add(t)


def mod_recipe_type(java_type: object, recipe: dict, mod, cache: dict | None = None):
    """``(reason, vanilla type to convert as or None)`` for a recipe whose
    type the mod's own code registers (#358), or None when it isn't one:
    a type outside ``minecraft:`` that the jar's code is read registering, or
    one in the mod's own namespace (only code registers recipe types)."""
    from .. import recipetypes

    if not isinstance(java_type, str) or ":" not in java_type or java_type.startswith("minecraft:"):
        return None
    ns = java_type.split(":", 1)[0]
    own = getattr(mod, "namespace", None)
    cache = {} if cache is None else cache
    if java_type not in cache:
        cache[java_type] = recipetypes.read(getattr(mod, "classes", None), java_type, own)
    reading = cache[java_type]
    if reading is None and ns != own:
        return None
    if reading is not None:
        parts = [f"{recipetypes.short(reading.registering)} registers it"]
        if reading.serializer:
            parts.append(f"serializer {recipetypes.short(reading.serializer)}")
        if reading.recipe:
            parts.append(f"recipe class {recipetypes.short(reading.recipe)}")
        who = (f"recipe type {java_type!r} is registered by the mod's own code "
               f"({_dotted(reading.registering)}: " + ", ".join(parts) + ")")
    else:
        who = (f"recipe type {java_type!r} is in the mod's own namespace and only code registers recipe "
               "types (Java has no data-driven ones); no class of the jar was read registering it")
    shape = _json_shape(recipe)
    wrapped = None
    if shape is None:
        for key, value in recipe.items():
            if isinstance(value, dict) and isinstance(value.get("type"), str):
                inner = with_namespaced_type(value).get("type")
                if inner in _SUPPORTED or inner in _SHAPES:
                    wrapped = (key, inner)
                    break
    if shape is None and wrapped is None:
        return f"{who}; {NO_BEDROCK_RECIPE_TYPE}, and its JSON has no vanilla recipe shape", None
    extras: list[str] = []
    if shape is not None:
        known = set(_SHAPES[shape]) | _NO_DATA_KEYS | set(condition_keys(getattr(mod, "loader", None)))
        extra_keys = sorted(set(recipe) - known)
        if extra_keys:
            extras.append("key(s) " + ", ".join(repr(k) for k in extra_keys))
        types: set = set()
        for k in ("key", "ingredients", "ingredient"):
            spec = recipe.get(k)
            _ingredient_types(list(spec.values()) if k == "key" and isinstance(spec, dict) else spec, types)
        if types:
            extras.append("ingredient type(s) " + ", ".join(repr(t) for t in sorted(types)))
        like = f"crafting-like: its JSON has {_SHAPE_WORDS[shape]}"
    else:
        others = sorted(set(recipe) - {wrapped[0]} - _NO_DATA_KEYS)
        extras.append("the wrapper itself" + (" and its key(s) " + ", ".join(repr(k) for k in others) if others else ""))
        like = f"crafting-like: it wraps a vanilla {wrapped[1]!r} recipe under {wrapped[0]!r}"
    if reading is not None and reading.overrides:
        extras.append("code overriding " + ", ".join(reading.overrides))
    unknown = None
    if reading is None or not reading.recipe:
        unknown = "its recipe class isn't read from bytecode, so whether Java does more than that shape can't be told"
    elif shape is not None and reading.base != shape:
        unknown = (f"its recipe class {recipetypes.short(reading.recipe)} isn't read extending vanilla "
                   f"{shape.split(':')[1]}")
    if not extras and unknown is None and shape is not None:
        return None, shape  # pick 2a: vanilla crafting under the mod's type name
    tail = []
    if extras:
        tail.append("Java also reads " + "; ".join(extras) + ", which a vanilla Bedrock recipe would drop (#87)")
    if unknown:
        tail.append(unknown)
    return f"{who}; {like}, but " + "; ".join(tail) + f"; {NO_BEDROCK_RECIPE_TYPE}", None


def _dotted(name: str | None) -> str:
    return (name or "").replace("/", ".")


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


def _ingredient(spec):
    """A 1.21.2+ bare-string ingredient in the older object form (#194).

    Since Minecraft 1.21.2 an ingredient may be a bare string: ``"#ns:path"``
    names a tag, any other string an item. A tag string becomes ``{"tag":
    "ns:path"}`` so it takes the same path as the object form (pass-through,
    single-member resolve, membership, residue reason); an item string stays as
    it is, which :func:`_item` and :func:`_listed_items` already read as the
    item. List entries are normalized the same way.
    """
    if isinstance(spec, str) and spec.startswith("#"):
        return {"tag": spec[1:]}
    if isinstance(spec, list):
        return [_ingredient(entry) for entry in spec]
    return spec


def _result_item(spec, tags: TagResolver | None = None) -> dict | None:
    """A recipe's result as ``{"item": id}``, or None when it isn't one item.

    A result is always an item in Java; a ``#`` name there is a malformed recipe
    Java refuses to load, so it is never read as a tag (or resolved to a member).
    """
    ident = spec.get("id", spec.get("item")) if isinstance(spec, dict) else spec
    if isinstance(ident, str) and ident.startswith("#"):
        return None
    return _item(spec, tags)


def _item(spec, tags: TagResolver | None = None) -> dict | None:
    """Java item specs come in several shapes. Only translate the unambiguous ones."""
    if isinstance(spec, str) and spec.startswith("#"):
        return _item(_ingredient(spec), tags)  # a tag, never an item id (#194)
    if isinstance(spec, str):
        return {"item": spec}
    listed = _listed_items(spec)
    if listed is not None and len(listed) == 1:
        return {"item": listed[0]}  # "any of [x]" is x
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
    listed = _listed_items(spec)
    if listed is not None:
        return (f"ingredient is a list of {len(listed)} items ({', '.join(listed)}); it converts "
                f"as one recipe per item only when every item is converted, it is the "
                f"recipe's only such ingredient, it fills one grid slot, and it has at most "
                f"{EXPANSION_CAP} items")
    if isinstance(spec, list):
        return "ingredient is a list holding a tag or a non-item entry"
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
        spec = _ingredient(recipe.get(slot))
        if spec in (None, "", {}, []):
            continue
        item = _smithing_item(spec, tags)
        if item is None:
            result.unhandled.append(Unhandled(rel, "recipe", f"smithing {slot}: {_tag_reason(spec, tags)}"))
            return None
        slots[slot] = item
    mapped_out = _result_item(recipe.get("result"), tags)
    out = mapped_out.get("item") if mapped_out else None
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


TRIM = "minecraft:recipe_smithing_trim"


def _replaces(tags: TagResolver, tag: str) -> bool:
    """Whether the jar's own file for ``tag`` sets ``"replace": true``."""
    path = tags.tag_file(tag)
    if path is None:
        return False
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and data.get("replace") is True


def _trim_pattern_refusal(recipe: dict, template) -> str | None:
    """Why Java 1.21.5+'s fixed ``pattern`` can't be said on Bedrock, or None.

    Bedrock's trim recipe has no pattern field: the pattern is the template
    item's. A vanilla pattern that is the vanilla template's own (``coast`` for
    ``coast_armor_trim_smithing_template``) says nothing more; any other (a
    mod's pattern, or a pattern fixed for a tag of templates) would change the
    trim the player gets.
    """
    pattern = recipe.get("pattern")
    if pattern is None:
        return None
    if not isinstance(pattern, str) or not pattern.startswith("minecraft:"):
        return (f"pattern {pattern!r} is not a vanilla trim pattern, and a Bedrock add-on can't register "
                f"one ({trim_items.PROBE_SOURCE})")
    if isinstance(template, str) and template == f"{pattern}_armor_trim_smithing_template":
        return None
    return (f"pattern {pattern} is fixed by the recipe, and Bedrock's trim recipe has no pattern field "
            f"(its pattern is the template's, {trim_items.MOJANG_SOURCE}), so it can't be said with "
            f"template {template!r}")


def _smithing_trim(recipe: dict, identifier: str, rel: str, result: ConversionResult,
                   tags: TagResolver | None = None, unknown: set[str] | None = None,
                   seen: set[str] | None = None) -> dict | None:
    """A Java ``minecraft:smithing_trim`` as Bedrock's ``recipe_smithing_trim``, or None (#272).

    Each slot is Java's slot tag (``#minecraft:trim_templates``,
    ``#minecraft:trimmable_armor``, ``#minecraft:trim_materials``), written as
    Bedrock's (``minecraft:trimmable_armors`` for the base), or one item. A
    vanilla item must be in Bedrock's tag for its slot, and a mod item can't
    be a template or an addition (:mod:`portkit.data.trim_items`); a mod base
    is checked once the pack is final (:func:`withdraw_unacceptable_trims`).
    Anything else is residue with the reason: never a crafting stand-in, and
    no slot is invented (Alex, 2026-10-16, #268).
    """
    body: dict = {"description": {"identifier": identifier}, "tags": ["smithing_table"]}
    for slot in ("template", "base", "addition"):
        spec = _ingredient(recipe.get(slot))
        if spec in (None, "", {}, []):
            result.unhandled.append(Unhandled(
                rel, "recipe", f"trim recipe has no {slot}, and Bedrock's smithing table needs all three "
                f"({trim_items.MOJANG_SOURCE})"))
            return None
        if isinstance(spec, dict) and spec.get("tag") == trim_items.JAVA_SLOT_TAGS[slot]:
            if tags is not None and _replaces(tags, spec["tag"]):
                result.unhandled.append(Unhandled(
                    rel, "recipe", f"trim {slot} tag {spec['tag']}: the jar's own file replaces Java's tag "
                    f"(\"replace\": true), so Bedrock's {trim_items.TRIM_SLOT_TAGS[slot]}, which holds vanilla's "
                    "members, would not be the same set: not written, and not rewritten as another recipe"))
                return None
            body[slot] = {"tag": trim_items.TRIM_SLOT_TAGS[slot]}
            own = tags.own_share(spec["tag"]) if slot != "base" and tags is not None else []
            if own:
                result.notes.append(
                    f"{rel}: {slot} tag {spec['tag']} is written as Bedrock's {trim_items.TRIM_SLOT_TAGS[slot]}, "
                    f"which holds vanilla's members only: {', '.join(own)} from this mod can't be a trim "
                    f"{'pattern' if slot == 'template' else 'material'} on Bedrock ({trim_items.PROBE_SOURCE})")
            continue
        item = _smithing_item(spec, tags)
        if item is None:
            if isinstance(spec, dict) and isinstance(spec.get("tag"), str):
                why = (f"trim {slot} tag {spec['tag']} is not {trim_items.JAVA_SLOT_TAGS[slot]} and means more "
                       f"than one item, and Bedrock's {slot} slot takes only items in "
                       f"{trim_items.TRIM_SLOT_TAGS[slot]} ({trim_items.MOJANG_SOURCE})")
            else:
                why = f"trim {slot}: {_tag_reason(spec, tags)}"
            result.unhandled.append(Unhandled(rel, "recipe", why))
            return None
        body[slot] = item
    why = bedrock_ids(body, unknown, seen)
    if why:
        result.unhandled.append(Unhandled(rel, "recipe", why))
        return None
    refused = []
    for slot in ("template", "base", "addition"):
        found = trim_items.slot_value(body[slot])
        if found is None or found[0] == "tag":
            continue
        ident = found[1]
        if ident.startswith("minecraft:"):
            refusal = trim_items.vanilla_refusal(slot, "item", ident)
        elif slot != "base":
            refusal = trim_items.addon_refusal(slot, ident)
        else:
            refusal = None  # checked on the final pack
        if refusal:
            refused.append(refusal)
    pattern = _trim_pattern_refusal(recipe, body["template"])
    if pattern:
        refused.append(pattern)
    if refused:
        result.unhandled.append(Unhandled(
            rel, "recipe", f"trim {'; '.join(refused)}: not written, and not rewritten as another recipe"))
        return None
    return body


def bedrock_item(ident: str) -> tuple[str, int | None] | str:
    """A Java item id as Bedrock writes it: (id, data or None), or why it has none (#261).

    A bare id is Java's ``minecraft:`` one (a ResourceLocation's default
    namespace; Supplementaries writes ``"item": "black_dye"``). A vanilla id the
    Java -> Bedrock table (:mod:`portkit.data.java_items`, GeyserMC/mappings)
    renames becomes Bedrock's: ``minecraft:bricks`` -> ``minecraft:brick_block``,
    ``minecraft:red_bed`` -> ``minecraft:bed`` with data 14. ``data`` is set only
    when Bedrock's id stands for several Java items. A Java id that shares its
    Bedrock id and data with another Java item (``tipped_arrow`` is plain
    ``arrow``) has none: writing it would make or take the other item. Every
    other id (a mod's, or a vanilla id the table doesn't rename) is returned as
    it is, and so is everything when the table isn't cached.
    """
    ident = ident if ":" in ident else f"minecraft:{ident}"
    if not ident.startswith("minecraft:"):
        return ident, None
    table = java_items.table()
    if table is None:
        return ident, None
    if ident in table.ambiguous:
        shared = ", ".join(table.ambiguous[ident])
        return (f"Java {ident} has no Bedrock id of its own: Bedrock writes it the same as "
                f"{shared} ({java_items.REPO}), so a recipe naming it would make or take that "
                f"item instead")
    got = table.lookup(ident)
    if got is None:
        return ident, None
    vanilla = vanilla_items.ids()
    if vanilla is not None and got[0] not in vanilla:
        return (f"Java {ident} is Bedrock {got[0]} ({java_items.REPO}), which isn't in Bedrock's "
                f"vanilla item list")
    return got


# Recipe body keys holding one item, as a bare id string (furnace, smithing) or
# an {"item": id} object (crafting results).
_ITEM_SLOTS = ("input", "output", "template", "base", "addition", "result")


def bedrock_ids(body: dict, unknown: set[str] | None = None,
                seen: set[str] | None = None) -> str | None:
    """Rewrite every item id ``body`` names to Bedrock's (see :func:`bedrock_item`),
    in place. Returns why the recipe can't be written, or None.

    A slot that takes a bare id string (Bedrock's furnace and smithing) can't
    carry a data value, so an item that needs one there is a reason. Vanilla
    ids Bedrock's item list doesn't have and the table doesn't rename are kept
    as written and added to ``unknown``; every vanilla id named is added to
    ``seen``.
    """
    vanilla = vanilla_items.ids()
    table = java_items.table()

    def mapped(ident: str):
        got = bedrock_item(ident)
        if seen is not None and not isinstance(got, str) and got[0].startswith("minecraft:"):
            seen.add(got[0])
        if (unknown is not None and table is not None and not isinstance(got, str) and got[0].startswith("minecraft:")
                and vanilla is not None and got[0] not in vanilla):
            unknown.add(got[0])
        return got

    def one(value):
        if isinstance(value, str):
            got = mapped(value)
            if isinstance(got, str):
                return None, got
            if got[1] is not None:
                return None, (f"{value} is Bedrock {got[0]} with data {got[1]}, which a slot "
                              "holding a bare item id can't say")
            return got[0], None
        if isinstance(value, dict) and isinstance(value.get("item"), str):
            got = mapped(value["item"])
            if isinstance(got, str):
                return None, got
            out = {"item": got[0]}
            if got[1] is not None:
                out["data"] = got[1]
            out.update((k, v) for k, v in value.items() if k != "item" and not (k == "data" and "data" in out))
            return out, None
        return value, None

    def many(values):
        out = []
        for value in values:
            new, why = one(value)
            if why:
                return None, why
            out.append(new)
        return out, None

    key = body.get("key")
    if isinstance(key, dict):
        new, why = many(list(key.values()))
        if why:
            return why
        body["key"] = dict(zip(key, new))
    if isinstance(body.get("ingredients"), list):
        new, why = many(body["ingredients"])
        if why:
            return why
        body["ingredients"] = new
    for slot in _ITEM_SLOTS:
        if slot in body:
            new, why = one(body[slot])
            if why:
                return why
            body[slot] = new
    return None


def emitted_definitions(files: dict) -> dict[str, tuple[str, str, dict]]:
    """identifier -> (kind, path, body) for every block and item definition in ``files``.

    kind is ``"item"``, ``"block"``, or ``"block_and_item"`` for a block that
    also has its own item file; path and body are then the item file's, the
    one a recipe tag goes on (#302 pick 2).
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
                # A block with its own item file. Its item file is where a
                # recipe tag goes (Alex's pick 2 on #302): the player holding
                # that item form matches the tag.
                if found[ident][0] == "item":
                    found[ident] = ("block_and_item", *found[ident][1:])
                elif kind == "item":
                    found[ident] = ("block_and_item", path, body)
                # (block_and_item already: keep the item file it holds.)
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
    # The ingredient is a JSON list of items, not a tag: it can only be written
    # once per member (form 3), and ``found.tag`` is a label, not a tag id.
    listed: bool = False


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


def _listed_items(spec) -> list[str] | None:
    """The item ids of a list ingredient made only of plain items, else None.

    Accepts ``{"item": id}`` entries and bare id strings (the 1.21.2+ form); a
    tag entry (``{"tag": ...}``, ``"#..."``) or anything else gives None.
    """
    if not isinstance(spec, list) or not spec:
        return None
    ids: list[str] = []
    for entry in spec:
        if isinstance(entry, dict) and set(entry) == {"item"} and isinstance(entry["item"], str):
            ids.append(entry["item"])
        elif isinstance(entry, str) and not entry.startswith("#"):
            ids.append(entry)
        else:
            return None
    return [i if ":" in i else f"minecraft:{i}" for i in dict.fromkeys(ids)]


def _list_label(ids: list[str]) -> str:
    return "[" + ", ".join(ids) + "]"


def _list_reason(multi: _Multi, slots: int, others: int) -> str:
    """Why a fully converted item-list ingredient still can't be written."""
    ids = multi.found.members
    head = f"ingredient is a list of {len(ids)} items ({', '.join(ids)})"
    if slots != 1:
        return (f"{head} filling {slots} grid slots; the player may mix items across them, "
                "which one recipe per item would forbid, and the mod declares no tag to take")
    if others > 1:
        return f"{head}, beside another multi-item ingredient; one recipe per item covers only one"
    return f"{head}, more than the {EXPANSION_CAP} recipes one per item is capped at"


def _multi_list(spec, emitted: dict | None) -> _Multi | None:
    """A list-of-items ingredient whose every item this addon holds, or None."""
    ids = _listed_items(spec)
    if emitted is None or ids is None:
        return None
    if any(not i.startswith("minecraft:") and i not in emitted for i in ids):
        return None
    if len(ids) == 1:
        return None  # _item reads a one-entry list as its lone member
    return _Multi(spec=spec, found=MultiMembers(tag=_list_label(ids), members=ids),
                  taggable=False, extras=[], listed=True)


# Emitted definitions a native item tag can go on: an item file, a block
# (through an item form replacing its own, see _block_item), and a block with
# its own item file (on that item file, #302 pick 2).
_TAGGABLE_KINDS = ("item", "block", "block_and_item")


def _multi_tag(spec, tags: TagResolver, emitted: dict | None) -> _Multi | None:
    """The tag (or item-list) ingredient as a known, fully emitted membership, or None."""
    if isinstance(spec, list):
        return _multi_list(spec, emitted)
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
    # A block with its own item file carries the tag on that item file (#302
    # pick 2), so every one of the mod's own members can carry it.
    taggable = (not found.tag.startswith("minecraft:")
                and any(k in _TAGGABLE_KINDS for k in own))
    extras = [m for m, k in zip(found.members, kinds) if k == "vanilla"]
    # Bedrock's tag holds vanilla's whole share, so only when the jar's file
    # doesn't replace the tag (mod_additions is None then).
    bedrock_tag = (found.tag in _BEDROCK_VANILLA_TAGS and tags.mod_additions(found.tag) is not None
                   and all(k == "vanilla" or k in _TAGGABLE_KINDS for k in kinds))
    return _Multi(spec=spec, found=found, taggable=taggable, vanilla_tag=_bedrock_equivalent(found, tags),
                  bedrock_tag=bedrock_tag, extras=extras)


def _not_emitted(spec, tags: TagResolver, emitted: dict | None) -> list[str]:
    """Members of a known tag ingredient that this conversion did not emit."""
    listed = _listed_items(spec)
    if listed is not None:
        if emitted is None:
            return []
        return [m for m in listed if not m.startswith("minecraft:") and m not in emitted]
    if emitted is None or not isinstance(spec, dict) or not isinstance(spec.get("tag"), str):
        return []
    found = tags.members(spec["tag"])
    if found is None:
        return []
    return [m for m in found.members if not m.startswith("minecraft:") and m not in emitted]


def _all_unconverted(failing: list[int], multis: dict, positions: list, mapped: list,
                     tags: TagResolver, emitted: dict | None) -> list[str]:
    """Every mod item a refused recipe needs, when what refuses it is only tags
    whose every member is an unconverted mod item; else [] (#302 pick 3).

    Alex's pick 3 on #302 (comment 6228435148, approved 2026-10-16): a tag
    ingredient none of whose members converted can't match anything on
    Bedrock until they do. When every refused ingredient is such a tag (no
    vanilla member, no member this conversion emitted, membership fully
    known), the recipe's fate is its members': the list (with any other mod
    item it names that wasn't emitted) goes to :func:`refine_owned`, which
    files it ``owned_by_residue`` only if each has a residue entry of its own.
    A tag with any member that converted, or a recipe refused for anything
    else as well, stays ``recipe``.
    """
    if emitted is None or not failing:
        return []
    names: list[str] = []
    for i in failing:
        spec = positions[i][0]
        if multis.get(i) is not None or not isinstance(spec, dict) or not isinstance(spec.get("tag"), str):
            return []
        found = tags.members(spec["tag"])
        if found is None or not found.members:
            return []
        if any(m.startswith("minecraft:") or m in emitted or ":" not in m for m in found.members):
            return []
        names.extend(found.members)
    for m in mapped:
        item = m.get("item") if isinstance(m, dict) else None
        if isinstance(item, str) and ":" in item and not item.startswith("minecraft:") and item not in emitted:
            names.append(item)
    return sorted(set(names))


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


def _qualified(rel: PurePosixPath) -> str:
    """A recipe's whole path under ``recipes/``, folders joined by ``_``."""
    return "_".join(rel.with_suffix("").parts)


def recipe_names(rels: list[PurePosixPath]) -> tuple[dict[PurePosixPath, str], dict[PurePosixPath, str]]:
    """Output name per recipe file (paths relative to ``recipes/``), and the refused ones.

    A stem no other file shares is kept as it is, so a recipe that never
    collided keeps the name (and identifier) it always had. A stem several
    files share is qualified for every one of them by its whole path: none of
    them is picked to keep the bare name, so the outcome depends only on which
    files exist, never on the order they are read in. A qualified name can
    still meet an unshared stem (``x/planks`` and ``x_planks``) or another
    qualified name; the unshared stem keeps its name, and every qualified file
    that lands on a taken name is refused, mapped to the file(s) it met.
    """
    by_stem: dict[str, list[PurePosixPath]] = {}
    for rel in rels:
        by_stem.setdefault(rel.stem, []).append(rel)
    names: dict[PurePosixPath, str] = {}
    for stem, group in by_stem.items():
        if len(group) == 1:
            names[group[0]] = stem
    bare = {name: rel for rel, name in names.items()}
    qualified: dict[str, list[PurePosixPath]] = {}
    for stem, group in by_stem.items():
        if len(group) > 1:
            for rel in group:
                qualified.setdefault(_qualified(rel), []).append(rel)
    refused: dict[PurePosixPath, str] = {}
    for name, group in qualified.items():
        if name in bare or len(group) > 1:
            for rel in group:
                others = sorted({*(r.as_posix() for r in group if r != rel),
                                 *([bare[name].as_posix()] if name in bare else [])})
                refused[rel] = (
                    f"recipe output name {name!r} (its path, because its file name is shared) "
                    f"is also the name of {', '.join(others)}; refused rather than overwrite"
                )
        else:
            names[group[0]] = name
    return names, refused


_KEY_SYMBOLS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


def _vanilla_only(multi: "_Multi | None") -> bool:
    """A tag ingredient whose every member is a vanilla item (none an add-on can tag)."""
    return (multi is not None and not multi.listed and not multi.vanilla_tag
            and all(m.startswith("minecraft:") for m in multi.found.members))


def _result_id(recipe: dict) -> str | None:
    """The namespaced id of the one item a recipe makes, or None (#342).

    Java's ``result`` is ``{"item": id}`` (to 1.20.4), ``{"id": id}`` (1.20.5+)
    or a bare id string; a bare path is ``minecraft:`` (minecraft.wiki,
    Identifier). A ``#`` name is not an item, so it gives None.
    """
    spec = recipe.get("result")
    ident = spec.get("id", spec.get("item")) if isinstance(spec, dict) else spec
    if not isinstance(ident, str) or not ident or ident.startswith("#"):
        return None
    return ident if ":" in ident else f"minecraft:{ident}"


def _over_cap(rest: list[int], multis: dict, positions: list, furnace: bool) -> str | None:
    """Why a recipe whose tags fit no written form is refused only for the cap, else None (#342).

    Called once every refused ingredient is a fully known membership whose
    members are vanilla or emitted (``multis`` all set) and no form fits. Only
    two forms are capped: one tag or list in one slot, one recipe per member
    (n recipes), and vanilla-only tags filling several slots, one recipe per
    combination (nᵏ, multiplied over the tags; #302 pick 1, never for a
    furnace). When the count of the form that fits but for its size is over
    :data:`EXPANSION_CAP` and every vanilla member has a Bedrock id of its own,
    the cap is all that refuses it: the reason names each tag, its member
    count, the slots it fills and the total. Anything else (a mixed tag over
    several slots, a list over several slots, a member with no Bedrock id)
    gives None and the recipe stays ``recipe``.
    """
    if not rest or any(multis.get(i) is None for i in rest):
        return None
    if len(rest) == 1 and positions[rest[0]][1] == 1:
        total = len(multis[rest[0]].found.members)
        form = "one recipe per member"
    elif not furnace and all(_vanilla_only(multis[i]) for i in rest):
        total = 1
        for i in rest:
            total *= len(multis[i].found.members) ** positions[i][1]
        form = "one recipe per combination the player can put in the slots (#302 pick 1)"
    else:
        return None
    if total <= EXPANSION_CAP:
        return None
    for i in rest:
        for member in multis[i].found.members:
            if member.startswith("minecraft:") and isinstance(bedrock_item(member), str):
                return None  # a member Bedrock can't name: not the cap alone
    parts = []
    for i in rest:
        multi = multis[i]
        label = multi.found.tag if multi.listed else repr(multi.found.tag)
        what = "list" if multi.listed else "tag"
        n, k = len(multi.found.members), positions[i][1]
        parts.append(f"{what} {label} ({n} members) in {k} grid slot{'s' if k != 1 else ''}"
                     + (f" ({n}^{k} mixes)" if k != 1 else ""))
    return (f"{'; '.join(parts)}: writing every mix Java accepts takes {form}, {total:,} recipes, "
            f"over the {EXPANSION_CAP} the expansion is capped at (#302: over-cap combinations stay "
            "residue, so the recipe book isn't flooded); nothing else refuses it, so it is not "
            "converted on purpose")


def _combinations(rest: list[int], multis: dict, positions: list, ingredients: list,
                  pattern: list | None, symbols: list | None):
    """Every combination of the vanilla-only tags in ``rest``, one recipe each (#302 pick 1).

    Alex's pick 1 on #302 (comment 6228435148, approved 2026-10-16): a tag
    ingredient whose members are all vanilla items can't be written as a tag
    (an add-on can't tag a vanilla item, and no Bedrock vanilla tag has the
    same members), and when it fills several grid slots the player may put a
    different member in each. Exact only if every such mix is its own recipe,
    so each one is, when there are at most :data:`EXPANSION_CAP` of them
    (n members over k slots: nᵏ; several such tags multiply).

    Shaped: each slot of the tag gets its own key symbol, one per member
    (Bedrock: "The key used in the pattern may be any single character
    except the 'space' character", learn.microsoft.com, Recipe Documentation -
    Shaped Recipe); a slot set all to one member keeps the Java symbol. A
    combination that is another's mirror image is written once: Bedrock's
    ``assume_symmetry`` defaults to true ("Used to automatically assume a
    symmetrical recipe should return the same result", same page), as Java
    matches a shaped recipe mirrored. Shapeless: order doesn't matter, so a
    combination is written once whatever slot each member is in.

    Returns ``(variants, shaped_forms)`` (see the caller), or None when the
    tags aren't all vanilla-only or the count is over the cap.
    """
    import itertools

    if not rest or not all(_vanilla_only(multis[i]) for i in rest):
        return None
    total = 1
    for i in rest:
        total *= len(multis[i].found.members) ** positions[i][1]
    if total > EXPANSION_CAP or (len(rest) == 1 and positions[rest[0]][1] == 1):
        return None
    variants: list[tuple[str, list]] = []
    shaped: dict[str, tuple[list, dict]] = {}
    seen: set = set()
    if pattern is not None and symbols is not None:
        rows = [row for row in pattern if isinstance(row, str)]
        if len(rows) != len(pattern):
            return None
        used = set("".join(rows)) | set(symbols)
        free = iter(c for c in _KEY_SYMBOLS if c not in used)
        cells = [(r, c) for r, row in enumerate(rows) for c, ch in enumerate(row)
                 if ch in {symbols[i] for i in rest}]
        by_cell = {cell: next(i for i in rest if symbols[i] == rows[cell[0]][cell[1]]) for cell in cells}
        fresh: dict[tuple[int, str], str] = {}
        for choice in itertools.product(*(multis[by_cell[cell]].found.members for cell in cells)):
            pick = dict(zip(cells, choice))
            grid = tuple(tuple(pick.get((r, c), ch) for c, ch in enumerate(row)) for r, row in enumerate(rows))
            mirror = tuple(tuple(reversed(row)) for row in grid)
            if mirror in seen:
                continue
            seen.add(grid)
            # Each of the tags' symbols: kept when all its slots hold one member.
            symbol_of: dict[tuple[int, str], str] = {}
            for i in rest:
                # Members in the order their slots read (row by row), so the
                # fresh symbols don't depend on string hashing (#309).
                chosen = list(dict.fromkeys(pick[cell] for cell in cells if by_cell[cell] == i))
                for member in chosen:
                    if len(chosen) == 1:
                        symbol_of[(i, member)] = symbols[i]
                    else:
                        if (i, member) not in fresh:
                            got = next(free, None)
                            if got is None:
                                return None
                            fresh[(i, member)] = got
                        symbol_of[(i, member)] = fresh[(i, member)]
            new_rows = ["".join(symbol_of[(by_cell[(r, c)], pick[(r, c)])] if (r, c) in pick else ch
                                for c, ch in enumerate(row)) for r, row in enumerate(rows)]
            key: dict = {}
            for i, (symbol, ingredient) in enumerate(zip(symbols, ingredients)):
                if i not in rest:
                    key[symbol] = ingredient
                    continue
                for member in dict.fromkeys(pick[cell] for cell in cells if by_cell[cell] == i):
                    key[symbol_of[(i, member)]] = {"item": member}
            suffix = "__" + "__".join(_vanilla_suffix(pick[cell]) for cell in cells)
            shaped[suffix] = (new_rows, key)
            one = list(ingredients)
            for i in rest:
                one[i] = {"item": pick[next(cell for cell in cells if by_cell[cell] == i)]}
            variants.append((suffix, one))
        return variants, shaped
    for choice in itertools.product(*(multis[i].found.members for i in rest)):
        one = list(ingredients)
        for i, member in zip(rest, choice):
            one[i] = {"item": member}
        order = tuple(sorted(json.dumps(x, sort_keys=True) for x in one))
        if order in seen:
            continue
        seen.add(order)
        variants.append(("__" + "__".join(_vanilla_suffix(m) for m in choice), one))
    return variants, shaped


def _vanilla_suffix(member: str) -> str:
    """A vanilla member's path for a combination's name: every member is
    ``minecraft:``, so the namespace adds nothing but length."""
    return _member_suffix(member.removeprefix("minecraft:"))


def _member_suffix(member: str) -> str:
    return member.replace(":", "_").replace("/", "_")


def _wearable(body) -> bool:
    """Whether an emitted item definition is Bedrock armor (``minecraft:wearable``)."""
    item = body.get("minecraft:item") if isinstance(body, dict) else None
    components = item.get("components") if isinstance(item, dict) else None
    return isinstance(components, dict) and isinstance(components.get("minecraft:wearable"), dict)


def _bedrock_vanilla_tags(mod: SourceMod, emitted: dict | None, tags: TagResolver,
                          item_tags: dict[str, set[str]], result: ConversionResult) -> None:
    """The mod's members of a Java tag Bedrock's own recipes also take carry it (#293).

    A Java mod adds its planks to ``#minecraft:planks`` so that vanilla's stick,
    crafting table and chest recipes take them; no recipe of the mod has to name
    the tag. Bedrock's vanilla recipes take the same tag under the same name
    (:data:`_BEDROCK_VANILLA_TAGS`), so each of the mod's members this pack
    emits carries it: an item in its ``minecraft:tags``, a block through an
    item that replaces its own (:func:`_block_item`). Members are the jar's
    share of the tag (from the merged membership when the reference data has
    it, else the jar's own direct entries). A block with its own item file
    can't carry it and is named in a note.
    """
    if emitted is None:
        return
    for java_tag in sorted(_BEDROCK_VANILLA_TAGS):
        if tags.tag_file(java_tag) is None:
            continue
        found = tags.members(java_tag)
        if found is not None:
            members, sources = found.members, list(found.sources)
        else:
            members = tags.own_share(java_tag)
            sources = [tags.tag_file(java_tag).relative_to(mod.root).as_posix()]
        members = [m for m in members if m.startswith(f"{mod.namespace}:")]
        tagged = [m for m in members if (emitted.get(m) or ("",))[0] in _TAGGABLE_KINDS]
        if not tagged:
            continue
        for member in tagged:
            item_tags.setdefault(member, set()).add(java_tag)
        result.consumed.update(sources)
        result.notes.append(
            f"{len(tagged)} of this mod's members of #{java_tag} ({', '.join(sources)}) carry Bedrock's "
            f"tag of that name, which Bedrock's own recipes take (#293)")


def _trimmable_armor_tags(mod: SourceMod, emitted: dict | None, tags: TagResolver,
                          item_tags: dict[str, set[str]], result: ConversionResult) -> None:
    """Tag this mod's Java trimmable armor with Bedrock's ``minecraft:trimmable_armors`` (#272).

    Java's ``#minecraft:trimmable_armor`` (with vanilla's 1.21 nesting of
    ``#minecraft:head_armor`` and the rest, from the reference data; the jar's
    own direct entries when that isn't cached) says which of the mod's items
    vanilla's trim recipe takes. On Bedrock the same recipe takes items tagged
    ``minecraft:trimmable_armors``, but only armor: BDS refuses Mojang's own
    ``minecraft:smithing_armor_trim`` when a tagged item has no
    ``minecraft:wearable`` (:mod:`portkit.data.trim_items`). So only an
    emitted item that is wearable gets the tag; the others are counted in a
    note. (A namespace with no recipe folder never gets here.)
    """
    java_tag = trim_items.JAVA_SLOT_TAGS["base"]
    found = tags.members(java_tag)
    own_file = tags.tag_file(java_tag)
    if found is not None:
        members, sources = found.members, list(found.sources)
    else:
        members = tags.own_share(java_tag)
        sources = [own_file.relative_to(mod.root).as_posix()] if own_file is not None else []
    members = [m for m in members if m.startswith(f"{mod.namespace}:")]
    tagged, not_armor = [], []
    for member in members:
        hit = (emitted or {}).get(member)
        if not hit or hit[0] != "item":
            continue
        if _wearable(hit[2]):
            item_tags.setdefault(member, set()).add(trim_items.TRIM_SLOT_TAGS["base"])
            tagged.append(member)
        else:
            not_armor.append(member)
    where = ", ".join(sources) or java_tag
    if tagged:
        for source in sources:
            result.consumed.add(source)
        result.notes.append(
            f"{len(tagged)} item(s) Java's #{java_tag} holds ({where}) carry Bedrock's "
            f"{trim_items.TRIM_SLOT_TAGS['base']}, so vanilla's trim recipe takes them (#272)")
    if not_armor:
        shown = ", ".join(not_armor[:3]) + (f" and {len(not_armor) - 3} more" if len(not_armor) > 3 else "")
        result.notes.append(
            f"{len(not_armor)} item(s) Java's #{java_tag} holds ({where}: {shown}) aren't armor in this pack "
            f"(no minecraft:wearable), so they don't carry {trim_items.TRIM_SLOT_TAGS['base']}: on an item "
            f"that isn't armor the tag makes BDS refuse Mojang's own trim recipe ({trim_items.PROBE_SOURCE})")


def with_namespaced_type(recipe: dict) -> dict:
    """``recipe`` with its ``type`` as Java reads it (#302).

    Java reads a recipe's ``type`` as a ResourceLocation, whose namespace
    defaults to ``minecraft`` when the string has no ``:`` (minecraft.wiki,
    Identifier, "Conversion from string": "In Java Edition ... when the ``:``
    is absent, ``minecraft`` becomes the namespace and the whole string
    becomes the path"). So Biomes O' Plenty's ``"type": "crafting_shaped"``
    is ``minecraft:crafting_shaped``, the same recipe serializer. Item ids
    already get the same default (:func:`bedrock_item`). A namespaced type, a
    non-string type, or one that isn't a valid path is returned untouched.
    """
    kind = recipe.get("type")
    if isinstance(kind, str) and ":" not in kind and _BARE_PATH.fullmatch(kind):
        return {**recipe, "type": f"minecraft:{kind}"}
    return recipe


# A ResourceLocation path's legal characters (minecraft.wiki, Identifier,
# "Legal characters": digits, lowercase letters, _ - . and /).
_BARE_PATH = re.compile(r"[a-z0-9_.\-/]+")


# Recipe keys whose strings are not item ids: a tag's id, the recipe type, the
# recipe book group, and load conditions (decided as written, before any
# alias, #183).
_NOT_ITEM_KEYS = frozenset({"tag", "type", "group", "conditions", "neoforge:conditions", "forge:conditions",
                            "fabric:load_conditions"})


def alias_items(recipe, aliases: dict[str, str]) -> list[str]:
    """Rewrite, in place, every item id in ``recipe`` that ``aliases`` maps to a
    vanilla id (#296), and return ``"<old> -> <new>"`` for each id rewritten.

    ``aliases`` holds a mod's item ids whose block and item its code aliases
    to a vanilla block's (an adapter's ``block_aliases`` hook, filled by the
    block converter only for a blockstate it filed ``aliased_blockstate``:
    the vanilla ``Blocks`` table registers the target and no block of the
    mod's own is registered under the name). Java resolves such an id to the
    vanilla item when the recipe loads (NeoForge ``BaseMappedRegistry#resolve``),
    so the recipe makes or takes the vanilla item there; writing the vanilla
    id keeps that recipe instead of withdrawing it for an item the pack
    doesn't ship. Only whole string values are compared, never a tag's id
    (``{"tag": ..}``), the recipe type, its group or a load condition.
    """
    done: list[str] = []
    if not aliases:
        return done

    def walk(value):
        if isinstance(value, dict):
            for k, v in value.items():
                if k in _NOT_ITEM_KEYS:
                    continue
                if isinstance(v, str) and v in aliases:
                    value[k] = aliases[v]
                    done.append(f"{v} -> {aliases[v]}")
                else:
                    walk(v)
        elif isinstance(value, list):
            for i, v in enumerate(value):
                if isinstance(v, str) and v in aliases:
                    value[i] = aliases[v]
                    done.append(f"{v} -> {aliases[v]}")
                else:
                    walk(v)

    walk(recipe)
    return done


def convert(mod: SourceMod, emitted: dict | None = None,
            context: LoadContext | None = None,
            deferred: list | None = None,
            aliases: dict[str, str] | None = None) -> ConversionResult:
    """Convert the mod's recipes.

    ``emitted`` maps identifier -> (kind, path, body) for the blocks and items the
    earlier converters wrote (see :func:`emitted_definitions`). Without it a
    multi-member tag ingredient stays residue, as before #160.

    A recipe whose load conditions are false or undecidable in this conversion
    is ``conditional_recipe`` residue, and a ``forge:conditional`` wrapper
    converts the entry Java would load (see :mod:`portkit.conditions`, #183).
    ``context`` is shared with the other converters of the namespace; without
    one the recipes get their own, and the config-flag note with it.

    With a ``deferred`` list, a recipe of a station type (one an adapter's
    ``station`` hook declares, :func:`portkit.converters.stations.station_recipe_types`)
    whose load conditions pass is appended to it as (source path, recipe)
    instead of being refused: the station converter writes it into its data
    table (#177). A recipe of a shared station type (the Farmer's Delight
    stove's campfire recipes) is appended too, and still converts.

    ``aliases`` (mod item id -> vanilla id, :attr:`ConversionResult.vanilla_aliases`)
    rewrites the ids a recipe Java loads names, as :func:`alias_items` says,
    with a note naming each rewrite (#296).
    """
    result = ConversionResult()
    from .stations import station_recipe_types

    station_types, station_shared_types = station_recipe_types()
    for lane in ("recipes", "recipe"):
        src = mod.data / lane
        if src.is_dir():
            break
    else:
        return result

    own_context = context is None
    if context is None:
        context = LoadContext(mod, tags=TagResolver(mod))
    tag_resolver = context.tags
    item_tags: dict[str, set[str]] = {}  # emitted item id -> native tags it must carry
    multi_used: dict[str, MultiMembers] = {}  # tags a converted recipe kept or expanded
    sources = sorted(src.rglob("*.json"))
    names, refused = recipe_names([PurePosixPath(p.relative_to(src).as_posix()) for p in sources])
    reserved = set(names.values())
    owners: dict[str, str] = {}  # output path -> the source recipe that wrote it
    identifiers: dict[str, str] = {}  # recipe identifier -> the source recipe that declared it

    def taken(rel: str, outputs: list[tuple[str, str]]) -> str | None:
        """Why one of ``outputs`` ((path, identifier)) can't be written, if one can't."""
        for out_path, ident in outputs:
            holder = owners.get(out_path) or identifiers.get(ident)
            if holder is not None and holder != rel:
                return (f"output {out_path} ({ident}) was already written by {holder}; "
                        "refused rather than overwrite")
        return None

    def write(rel: str, out_path: str, ident: str, value: dict) -> None:
        owners[out_path] = rel
        identifiers[ident] = rel
        result.files[out_path] = value
        result.recipe_sources[out_path] = rel

    advancements = advancement_index(mod.root)
    type_readings: dict = {}  # recipe type -> recipetypes.read (#358)
    unlocks = {"derived": 0, "no_advancement": 0, "fallback": 0}

    unknown_ids: set[str] = set()  # vanilla ids neither Bedrock's list nor the table knows
    vanilla_seen: set[str] = set()  # every vanilla id a written recipe names

    def unlock_item(item: str) -> tuple[str, int | None] | None:
        got = bedrock_item(item)
        return None if isinstance(got, str) else got

    def single_item(tag: str) -> str | None:
        one = _item({"tag": tag}, tag_resolver)
        return one.get("item") if one else None

    for path in sources:
        rel = result.claim(mod, path)
        key = PurePosixPath(path.relative_to(src).as_posix())
        if key in refused:
            result.unhandled.append(Unhandled(rel, "recipe", refused[key]))
            continue
        name = names[key]
        try:
            recipe = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            result.unhandled.append(Unhandled(rel, "recipe", f"invalid JSON: {exc}"))
            continue
        if not isinstance(recipe, dict):
            result.unhandled.append(Unhandled(rel, "recipe", "recipe file is not a JSON object"))
            continue

        recipe = with_namespaced_type(recipe)
        # Java loads the recipe only when its load conditions hold (#183).
        verdict = context.gate(recipe)
        if verdict.passes is not True:
            result.unhandled.append(Unhandled(rel, "conditional_recipe", verdict.reason()))
            continue
        if recipe.get("type") in CONDITIONAL_TYPES:
            chosen, verdict = context.choose(recipe)
            if chosen is None:
                result.unhandled.append(Unhandled(rel, "conditional_recipe", verdict.reason()))
                continue
            result.notes.append(
                f"{rel}: {recipe['type']} wrapper; converted the entry Java loads with only this "
                f"mod ({verdict.why})"
            )
            recipe = with_namespaced_type(chosen)
        rewritten = alias_items(recipe, aliases or {})
        if rewritten:
            result.notes.append(
                f"{rel}: names {', '.join(sorted(set(rewritten)))}: the mod's code aliases the id's block and "
                "item to the vanilla one, so Java's recipe takes the vanilla item and the converted recipe "
                "names it (#296)")

        java_type = recipe.get("type")
        produced = _result_id(recipe)
        if produced is not None:
            # What the recipe makes, for refine_owned (#342).
            result.recipe_results[rel] = produced
        if deferred is not None and java_type in station_types:
            deferred.append((rel, recipe))
            continue
        if deferred is not None and java_type in station_shared_types:
            deferred.append((rel, recipe))  # and convert it below as well
        if java_type == "minecraft:smithing_transform":
            converted = _smithing(recipe, f"{mod.namespace}:{name}", rel, result, tag_resolver)
            if converted is not None:
                body_key, body = converted
                why = bedrock_ids(body, unknown_ids, vanilla_seen)
                if why:
                    result.unhandled.append(Unhandled(rel, "recipe", why))
                    continue
                out_path, ident = f"recipes/{name}.json", f"{mod.namespace}:{name}"
                clash = taken(rel, [(out_path, ident)])
                if clash:
                    result.unhandled.append(Unhandled(rel, "recipe", clash))
                    continue
                write(rel, out_path, ident, {"format_version": "1.20.10", body_key: body})
                if body_key == "minecraft:recipe_smithing_transform":
                    for slot, slot_tag in _SMITHING_SLOT_TAGS.items():
                        found = (emitted or {}).get(body.get(slot))
                        if not found:
                            continue
                        has_item = isinstance(found[2].get("minecraft:item"), dict)
                        if found[0] == "item" and has_item:
                            item_tags.setdefault(body[slot], set()).add(slot_tag)
                        elif slot != "base" and (found[0] == "block" or found[0] == "block_and_item" and has_item):
                            # A block in the template or addition slot carries
                            # the tag on its item form (its own item file, or
                            # one replacing its item, _block_item), the way
                            # #293's vanilla tags do (#305). Not the base: that
                            # must be armor or a tool, which a block isn't.
                            item_tags.setdefault(body[slot], set()).add(slot_tag)
            continue
        if java_type == "minecraft:smithing_trim":
            body = _smithing_trim(recipe, f"{mod.namespace}:{name}", rel, result, tag_resolver,
                                  unknown_ids, vanilla_seen)
            if body is not None:
                out_path, ident = f"recipes/{name}.json", f"{mod.namespace}:{name}"
                clash = taken(rel, [(out_path, ident)])
                if clash:
                    result.unhandled.append(Unhandled(rel, "recipe", clash))
                    continue
                write(rel, out_path, ident, {"format_version": "1.20.10", TRIM: body})
                base = body.get("base")
                found = (emitted or {}).get(base) if isinstance(base, str) else None
                if found and found[0] == "item" and _wearable(found[2]):
                    # The Java recipe is the evidence it takes the base slot (#263).
                    item_tags.setdefault(base, set()).add(trim_items.TRIM_SLOT_TAGS["base"])
            continue
        mapping = _SUPPORTED.get(java_type)
        if mapping is None:
            # A type one mod's code defines: its adapter says why (#245).
            from ..adapters import recipe_reason
            # (The fluid, modular tool, machine and code tables are all
            # adapters' now, and check() keeps their types disjoint.)
            found = recipe_reason(java_type, recipe, mod)
            if found is not None:
                result.unhandled.append(Unhandled(rel, *found))
                continue
            code = code_recipe_reason(java_type, recipe, mod.loader)
            if code is not None:
                result.unhandled.append(Unhandled(rel, CODE_RECIPE, code))
                continue
            own_type = mod_recipe_type(java_type, recipe, mod, type_readings)
            if own_type is not None and own_type[1] is not None:
                # Pick 2a (#358): vanilla crafting under the mod's type name.
                result.notes.append(f"{rel}: {java_type} read as {own_type[1]} (its recipe class "
                                    "extends it and overrides nothing; #358)")
                java_type = own_type[1]
                recipe = {**recipe, "type": java_type}
                mapping = _SUPPORTED[java_type]
            elif own_type is not None:
                result.unhandled.append(Unhandled(rel, MOD_RECIPE_TYPE, own_type[0]))
                continue
        if mapping is None:
            why = _KNOWN_UNSUPPORTED.get(
                java_type, f"unsupported recipe type {java_type!r}"
            )
            result.unhandled.append(Unhandled(rel, "recipe", why))
            continue
        bedrock_type, tags = mapping

        identifier = f"{mod.namespace}:{name}"
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
            positions = [(_ingredient(spec), used.count(symbol)) for symbol, spec in key_specs]
        elif java_type == "minecraft:crafting_shapeless":
            positions = [(_ingredient(spec), 1) for spec in recipe.get("ingredients", [])]
        else:  # stonecutting and the furnace family: one input
            positions = [(_ingredient(recipe.get("ingredient")), 1)]
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
        combos: list[int] = []  # vanilla-only tags written once per combination (#302 pick 1)
        over_cap: str | None = None  # why only the cap refuses it (#342), else None
        shaped_forms: dict[str, tuple[list, dict]] = {}  # suffix -> (pattern, key) of a combination
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
            elif not furnace and (combined := _combinations(
                    rest, multis, positions, ingredients,
                    (recipe.get("pattern") if java_type == "minecraft:crafting_shaped" else None),
                    [symbol for symbol, _ in key_specs] if java_type == "minecraft:crafting_shaped" else None,
            )) is not None:
                # Vanilla-only tags filling several slots: one recipe per
                # combination the player can make (#302 pick 1).
                variants, shaped_forms = combined
                combos = rest
            else:
                native = set()
                over_cap = _over_cap(rest, multis, positions, furnace)
        if any(m is None for _, ms in variants for m in ms):
            # Not expressible (or not fully known): the reason is the one the
            # first failing ingredient always had, plus which members this
            # conversion didn't emit when that is what blocks it.
            # A tag this conversion could have written isn't what blocks it.
            bad_i = next((i for i in failing if multis[i] is None), (rest or failing)[0])
            bad = positions[bad_i][0]
            reason = _tag_reason(bad, tag_resolver)
            if multis.get(bad_i) is not None and multis[bad_i].listed:
                reason = _list_reason(multis[bad_i], positions[bad_i][1], len(rest))
            missing = _not_emitted(bad, tag_resolver, emitted)
            if missing:
                reason += f"; not converted: {', '.join(missing)}"
            if over_cap is not None and not missing:
                # Nothing but the count stops it (#342, pending Alex).
                result.unhandled.append(Unhandled(rel, OVER_CAP, f"{over_cap} (the ingredient: {reason})"))
                continue
            result.unhandled.append(Unhandled(rel, "recipe", reason))
            unconverted = _all_unconverted(failing, multis, positions, mapped, tag_resolver, emitted)
            if unconverted:
                # Every member of each refused tag is a mod item this pack
                # didn't emit: the pipeline files it owned_by_residue when
                # each has a residue entry of its own (#302 pick 3).
                result.unshipped_names[rel] = unconverted
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

        out = _result_item(recipe.get("result"), tag_resolver)
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

        outputs = [(f"recipes/{name}{suffix}.json", f"{identifier}{suffix}") for suffix, _ in variants]
        if any(suffix for suffix, _ in variants) and any(
            path_ in result.files or (suffix and f"{name}{suffix}" in reserved)
            for (path_, _), (suffix, _) in zip(outputs, variants)
        ):
            # A per-member file name another recipe already took or will take:
            # refuse rather than overwrite either one.
            result.unhandled.append(Unhandled(rel, "recipe", _tag_reason(positions[failing[0]][0], tag_resolver)))
            continue
        clash = taken(rel, outputs)
        if clash:
            # Not reached on the corpus (names are unique by construction); the
            # guard that keeps a future change from overwriting a recipe (#163).
            result.unhandled.append(Unhandled(rel, "recipe", clash))
            continue

        built: list[tuple[str, dict]] = []
        no_id = None
        for suffix, ingredients in variants:
            variant = copy.deepcopy(body)
            variant["description"]["identifier"] = f"{identifier}{suffix}"
            if java_type == "minecraft:crafting_shaped" and suffix in shaped_forms:
                variant["pattern"], variant["key"] = copy.deepcopy(shaped_forms[suffix])
                variant["result"] = variant.pop("result")
            elif java_type == "minecraft:crafting_shaped":
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
            # Java's vanilla ids as Bedrock spells them (#261).
            no_id = bedrock_ids(variant, unknown_ids, vanilla_seen)
            if no_id:
                break
            built.append((suffix, variant))
        if no_id:
            result.unhandled.append(Unhandled(rel, "recipe", no_id))
            continue
        if bedrock_type in NEEDS_UNLOCK:
            # Bedrock 1.20.10+ crafting recipes need unlock data (#260): the
            # Java recipe advancement's has_<item> items, else AlwaysUnlocked.
            java_id = f"{mod.namespace}:{key.with_suffix('').as_posix()}"
            # An advancement Java wouldn't load (its own load conditions) unlocks nothing.
            granting = [(r, a) for r, a in advancements.get(java_id, []) if context.gate(a).passes is True]
            found = unlock_criteria(granting)
            unlock = unlock_entries(found, [v for _, v in built], emitted, single_item,
                                    vanilla_items.ids(), unlock_item)
            if unlock:
                unlocks["derived"] += 1
            else:
                unlock = ALWAYS_UNLOCKED
                unlocks["no_advancement" if not granting else "fallback"] += 1
                if granting:
                    why = "; ".join(found.dropped) or (
                        "its items and tags are neither shipped by this addon nor Bedrock vanilla "
                        "ids nor tags the recipe takes")
                    if vanilla_items.ids() is None:
                        why += f"; the Bedrock vanilla item list isn't cached, run `{FETCH_COMMAND}`"
                    result.notes.append(
                        f"{rel}: unlock AlwaysUnlocked (fallback): the Java advancement gives no "
                        f"Bedrock unlock entry ({why})")
            built = [(suffix, with_unlock(v, unlock)) for suffix, v in built]
            for adv_rel, _ in advancements.get(java_id, []):
                result.consumed.add(adv_rel)  # read (and gated) for the recipe that shipped
        for suffix, variant in built:
            write(rel, f"recipes/{name}{suffix}.json", f"{identifier}{suffix}", {
                "format_version": "1.20.10",
                bedrock_type: variant,
            })
        for i, multi in multis.items():
            if multi is None or multi.listed:
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
                f"({name}__<member>) beside the one taking the tag"
            )
        if combos:
            shown = ", ".join(f"{multis[i].found.tag!r} ({len(multis[i].found.members)} vanilla items, "
                              f"{positions[i][1]} slot{'s' if positions[i][1] != 1 else ''})" for i in combos)
            result.notes.append(
                f"{rel}: tag ingredient(s) {shown} hold only vanilla items, which an add-on can't tag, "
                f"so the recipe was written once per combination of members the player can put in "
                f"those slots ({len(variants)} recipes, {name}__<members>; #302)"
            )
        if expanded is not None and variants[0][0] == "":
            member_tag = multis[expanded].found.tag
            result.notes.append(
                f"{rel}: tag {member_tag!r} also holds {len(variants) - 1} of this mod's members "
                f"that can't carry Bedrock's tag of that name, so each got its own recipe "
                f"({name}__<member>) beside the one taking the tag"
            )
        elif expanded is not None and multis[expanded].listed:
            result.notes.append(
                f"{rel}: ingredient lists {len(variants)} items, which Bedrock can't group "
                f"without a tag the mod never declared, so the recipe was written once per item "
                f"({name}__<item>)"
            )
        elif expanded is not None:
            member_tag = multis[expanded].found.tag
            result.notes.append(
                f"{rel}: tag {member_tag!r} has {len(variants)} members, which Bedrock "
                f"can't group under one tag here, so the recipe was written once per member "
                f"({name}__<member>)"
            )

    _bedrock_vanilla_tags(mod, emitted, tag_resolver, item_tags, result)
    _trimmable_armor_tags(mod, emitted, tag_resolver, item_tags, result)
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
    if unknown_ids:
        result.notes.append(
            f"recipes name vanilla id(s) {', '.join(sorted(unknown_ids))}, which are not in "
            "Bedrock's vanilla item list and which the Java -> Bedrock table doesn't rename "
            "(an id a later Java version renamed, or one Bedrock knows by an alias); kept as "
            "written")
    if java_items.table() is None and vanilla_items.ids() is not None and vanilla_seen:
        # (Without either list the unlock fallback note already says to fetch.)
        result.notes.append(
            f"recipes keep Java's vanilla item ids: the Java -> Bedrock item table isn't "
            f"cached, run `{FETCH_COMMAND}`")
    if unlocks["no_advancement"]:
        result.notes.append(
            f"recipe unlock: {unlocks['no_advancement']} crafting recipe(s) have no Java recipe "
            "advancement, so Bedrock gets unlock AlwaysUnlocked (fallback): the recipe book lists "
            "them from the start"
        )
    note = context.note() if own_context else None
    if note:
        result.notes.append(note)
    return result


def _named_items(body: dict) -> list[str]:
    """Every item id a written Bedrock recipe body names in its inputs and result
    (its unlock entries are checked on their own, see :func:`drop_unshipped_recipes`)."""
    found: list[str] = []

    def walk(value):
        if isinstance(value, str):
            found.append(value)
        elif isinstance(value, dict) and isinstance(value.get("item"), str):
            found.append(value["item"])
        elif isinstance(value, list):
            for v in value:
                walk(v)

    key = body.get("key")
    if isinstance(key, dict):
        walk(list(key.values()))
    for slot in ("ingredients", *_ITEM_SLOTS):
        if slot in body:
            walk(body[slot])
    return found


def _recipe_body(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    for key, body in value.items():
        if key.startswith("minecraft:recipe_") and isinstance(body, dict):
            return body
    return None


def drop_unshipped_recipes(result: ConversionResult) -> None:
    """Withdraw every recipe naming a mod's item the pack doesn't ship (#261).

    Runs on the merged pack, once every namespace converted and blocks whose
    textures didn't convert were withdrawn (:func:`portkit.pipeline.drop_untextured`):
    an item another namespace of the jar ships counts, and one withdrawn
    after the recipes converted doesn't. Bedrock Dedicated Server refuses a
    recipe naming an item it doesn't know ("The Item: cluttered:heart_cake is
    missing or invalid, can't make the recipe" / "Recipe result malformed",
    #238 in-game runs), so shipping it does nothing for the player; it goes
    back to the residue under its source recipe, naming the items, and every
    file written from that source goes with it (a recipe is never narrowed to
    part of a tag). An unlock entry naming such an item (a recipe's own
    inputs all ship) is dropped; with none left the unlock is
    ``AlwaysUnlocked``, labelled in the notes. Vanilla ids are not checked
    here (see :func:`bedrock_ids`).
    """
    shipped = set(emitted_definitions(result.files))
    residue_sources = {u.source for u in result.unhandled}

    def missing(item: str) -> bool:
        return ":" in item and not item.startswith("minecraft:") and item not in shipped

    by_source: dict[str, list[str]] = {}
    for path in sorted(result.files):
        if path.startswith("recipes/") and _recipe_body(result.files[path]) is not None:
            by_source.setdefault(result.recipe_sources.get(path, path), []).append(path)
    for source, paths in by_source.items():
        named = sorted({i for p in paths for i in _named_items(_recipe_body(result.files[p])) if missing(i)})
        if named:
            for path in paths:
                del result.files[path]
            shown = ", ".join(named[:5]) + (f" and {len(named) - 5} more" if len(named) > 5 else "")
            why = (f"names {shown}, which the pack doesn't ship (see {'their' if len(named) > 1 else 'its'} "
                   f"own residue entry); not written, since Bedrock refuses a recipe naming an item "
                   f"it doesn't know")
            if source in residue_sources:
                # Already residue on its own account (a station recipe the
                # stove refused too): one entry per source, the rest in a note.
                result.notes.append(f"{source}: crafting form {why}")
            else:
                result.unhandled.append(Unhandled(source, "recipe", why))
                result.unshipped_names[source] = named
            continue
        for path in paths:
            body = _recipe_body(result.files[path])
            unlock = body.get("unlock")
            if not isinstance(unlock, list):
                continue
            kept = [e for e in unlock
                    if not (isinstance(e, dict) and isinstance(e.get("item"), str) and missing(e["item"]))]
            if len(kept) == len(unlock):
                continue
            dropped = sorted(e["item"] for e in unlock if e not in kept)
            body["unlock"] = kept or copy.deepcopy(ALWAYS_UNLOCKED)
            result.notes.append(
                f"{path}: unlock entry {', '.join(dropped)} dropped, the pack doesn't ship it"
                + ("" if kept else "; unlock AlwaysUnlocked (fallback)"))


OWNED = "owned_by_residue"
# Kinds that don't explain why an item is missing: a file nobody claimed, and
# the recipe entries themselves.
_NOT_AN_OWNER = frozenset({"unowned", "recipe", OVER_CAP})


def _owner_entry(item: str, residue: dict[str, str]) -> str | None:
    """The residue entry that is mod item ``item`` itself, if it has one.

    A Java item ``<ns>:<path>`` is defined, for a pack, by its blockstate
    (``assets/<ns>/blockstates/<path>.json``: the block and its item), its
    item model (``assets/<ns>/models/item/<path>.json``) or, from 1.21.4, its
    item definition (``assets/<ns>/items/<path>.json``). When one of them has
    a residue entry of an explaining kind, the converter that would ship the
    item refused it there, and says why.
    """
    ns, _, path = item.partition(":")
    for candidate in (f"assets/{ns}/blockstates/{path}.json",
                      f"assets/{ns}/models/item/{path}.json",
                      f"assets/{ns}/items/{path}.json"):
        if residue.get(candidate) not in (None, *_NOT_AN_OWNER):
            return candidate
    return None


def refine_owned(unhandled: list[Unhandled], unshipped: dict[str, list[str]],
                 results: dict[str, str] | None = None,
                 shipped: set[str] | None = None) -> list[Unhandled]:
    """Re-file a refused recipe that goes with residue items (#302, #342).

    :func:`drop_unshipped_recipes` withdraws a recipe naming (as its result or
    an ingredient) a mod item the pack doesn't ship, since Bedrock refuses a
    recipe naming an item it doesn't know. When every such item is itself
    residue with its own entry (see :func:`_owner_entry`: its block or item
    was refused, for a reason of its own), nothing is wrong with the recipe:
    it becomes ``owned_by_residue``, the explained kind loot tables of refused
    blocks (#299) and their models and textures (#292) use, keeping why it was
    withdrawn, and it converts when its items do. A recipe naming an item with
    no entry of its own (another mod's, or one the jar never defines) stays
    ``recipe``. Pack bytes don't change.

    #342 (pending Alex, pick 1a): a ``recipe`` or :data:`OVER_CAP` entry whose
    result (``results``: source -> the item it makes, recorded by
    :func:`convert`) is a mod item with a residue entry of its own goes with
    that item too, whatever else refused it: Bedrock refuses a recipe whose
    result it doesn't know, so the recipe can't ship before its result does,
    and when it does the recipe converter reads it again (the original
    reason is kept). A ``minecraft:`` result never counts, and neither does
    one the pack ships under that id (``shipped``: a block refused while an
    item of the same id converted), since Bedrock knows it.
    """
    residue = {u.source: u.kind for u in unhandled}
    results = results or {}
    out: list[Unhandled] = []
    for u in unhandled:
        named = unshipped.get(u.source) if u.kind == "recipe" else None
        owners = [(_owner_entry(i, residue), i) for i in named or []]
        if owners and all(entry for entry, _ in owners):
            shown = ", ".join(f"{i} ({entry}: {residue[entry]})" for entry, i in owners[:5])
            if len(owners) > 5:
                shown += f" and {len(owners) - 5} more"
            out.append(Unhandled(
                source=u.source, kind=OWNED, count=u.count,
                reason=(f"a recipe whose items are residue: {shown}, each refused with an entry of its own, "
                        f"so the recipe goes with them when they convert (the recipe itself: {u.reason})")))
            continue
        made = results.get(u.source) if u.kind in ("recipe", OVER_CAP) else None
        entry = (_owner_entry(made, residue)
                 if made and not made.startswith("minecraft:") and made not in (shipped or ()) else None)
        if entry is not None:
            out.append(Unhandled(
                source=u.source, kind=OWNED, count=u.count,
                reason=(f"a recipe whose result is residue: {made} ({entry}: {residue[entry]}) is refused "
                        f"with an entry of its own, and Bedrock refuses a recipe whose result it doesn't "
                        f"know, so the recipe goes with it when it converts (the recipe itself, "
                        f"{u.kind}: {u.reason})")))
            continue
        out.append(u)
    return out


SMITHING = "minecraft:recipe_smithing_transform"
# Why a smithing base needs minecraft:durability (#263, #268).
_SMITHING_BASE_RULE = (
    "Bedrock's smithing table takes only armor and tools as the base (Mojang bedrock-samples "
    "documentation/Recipes.html, recipe_smithing_transform), and BDS 1.26.52.3 refuses a base "
    "without minecraft:durability (\"base item is not a piece of armor or equipment\", #263)"
)


def _smithing_bases(files: dict) -> set[str]:
    """Identifiers the written smithing recipes in ``files`` take as their base."""
    bases = set()
    for path, value in files.items():
        if path.startswith("recipes/") and isinstance(value, dict):
            body = value.get(SMITHING)
            if isinstance(body, dict) and isinstance(body.get("base"), str):
                bases.add(body["base"])
    return bases


def _durability(body) -> bool:
    item = body.get("minecraft:item") if isinstance(body, dict) else None
    components = (item or {}).get("components") if isinstance(item, dict) else None
    return isinstance(components, dict) and isinstance(components.get("minecraft:durability"), dict)


def equip_smithing_bases(mod: SourceMod, files: dict) -> ConversionResult:
    """Give this namespace's smithing bases the durability its code gives them (#268).

    Runs on the merged pack (``files``), once :func:`drop_unshipped_recipes`
    withdrew what it does, so only recipes that ship count.

    A mod item a written ``recipe_smithing_transform`` takes as its base is a
    tool or armor to Bedrock only with ``minecraft:durability``. Java keeps that
    number in code, so each adapter's ``item_durability`` hook reads it (from
    the mod's bytecode, :mod:`portkit.itemcode`) with its source; such an item
    gets ``minecraft:durability`` and one per stack (Java can't stack an item
    with max_damage either: minecraft.wiki Data component format, 24w12a). An
    item already carrying durability (an adapter wrote it) is left as it is,
    and a base nobody can read is left for :func:`withdraw_unequipped_smithing`.
    """
    result = ConversionResult()
    emitted = emitted_definitions(files)
    wanted: dict[str, tuple[str, dict]] = {}
    prefix = f"{mod.namespace}:"
    for base in sorted(_smithing_bases(files)):
        found = emitted.get(base)
        if not base.startswith(prefix) or not found or found[0] != "item":
            continue
        path, body = found[1], found[2]
        if path.startswith("items/") and not _durability(body):
            wanted[path[len("items/"):-len(".json")]] = (path, body)
    if not wanted:
        return result
    from ..adapters import item_durabilities

    answers = item_durabilities(mod, frozenset(wanted))
    done = []
    for name, (durability, source) in sorted(answers.items()):
        path, body = wanted[name]
        if not isinstance(durability, int) or durability <= 0:
            continue
        item = copy.deepcopy(body)
        components = item["minecraft:item"].setdefault("components", {})
        components["minecraft:max_stack_size"] = 1
        components["minecraft:durability"] = {"max_durability": durability}
        result.files[path] = item
        done.append(f"{mod.namespace}:{name} {durability} ({source})")
    if done:
        result.notes.append(
            "smithing bases carry the durability the mod's code gives them, one per stack, so "
            "Bedrock's smithing table takes them as armor or tools (#268): " + "; ".join(done)
            + ". Attack damage, mining speed, armor points, enchantability and repair are not written.")
    return result


def _slot_refusal(slot: str, ident, emitted: dict) -> str | None:
    """Why Bedrock won't take ``ident`` in a smithing transform's template or
    addition slot, or None (#305).

    The slot takes only items carrying its tag (``_SMITHING_SLOT_TAGS``). A
    vanilla item must be one of Bedrock's own members
    (:func:`portkit.data.smithing_bases.vanilla_slot_refusal`); the pack's own
    item or block must carry the tag on its item definition, which the recipe
    converter gives it. Ids the pack doesn't define are
    :func:`drop_unshipped_recipes`' business."""
    if not isinstance(ident, str) or ":" not in ident:
        return None
    if ident.startswith("minecraft:"):
        return vanilla_slot_refusal(slot, ident)
    found = emitted.get(ident)
    if found is None:
        return None
    item = found[2].get("minecraft:item") if found[0] != "block" else None
    components = item.get("components") if isinstance(item, dict) else None
    return addon_slot_refusal(slot, ident, found[0], components)


def withdraw_unequipped_smithing(result: ConversionResult) -> None:
    """Withdraw every smithing recipe whose base Bedrock won't take (#268).

    Runs on the merged pack after :func:`drop_unshipped_recipes` and
    :func:`equip_smithing_bases`. A
    ``recipe_smithing_transform`` whose base is a mod item without
    ``minecraft:durability`` (no durability could be read from the mod's code)
    or a mod block is refused by Bedrock (see ``_SMITHING_BASE_RULE``), so it
    goes back to the residue under its source recipe with the reason. It is
    not rewritten as a crafting recipe (Alex, 2026-10-16: that would drop the
    smithing table and what the upgrade carries over). A vanilla base is
    checked against Bedrock's vanilla data (:mod:`portkit.data.smithing_bases`,
    #270): one that isn't armor or a tool there (``minecraft:stick``) withdraws
    the recipe the same way. So does a template or addition Bedrock won't take
    (:func:`_slot_refusal`, #305): a vanilla item outside Bedrock's
    ``minecraft:transform_templates`` / ``transform_materials``, or the pack's
    own item or block without the tag. The smithing slot tags an item carried only for a recipe
    that was withdrawn (here or by :func:`drop_unshipped_recipes`) are taken
    off it again.
    """
    emitted = emitted_definitions(result.files)
    residue_sources = {u.source for u in result.unhandled}
    by_source: dict[str, list[str]] = {}
    for path in sorted(result.files):
        value = result.files[path]
        if path.startswith("recipes/") and isinstance(value, dict) and isinstance(value.get(SMITHING), dict):
            by_source.setdefault(result.recipe_sources.get(path, path), []).append(path)
    for source, paths in by_source.items():
        refused, slot_refused = [], []
        for path in paths:
            body = result.files[path][SMITHING]
            for slot in ("template", "addition"):
                refusal = _slot_refusal(slot, body.get(slot), emitted)
                if refusal:
                    slot_refused.append(refusal)
            base = body.get("base")
            if not isinstance(base, str) or ":" not in base:
                continue
            if base.startswith("minecraft:"):
                refusal = vanilla_base_refusal(base)
                if refusal:
                    refused.append(refusal)
                continue
            found = emitted.get(base)
            if found is None:
                continue  # unshipped: drop_unshipped_recipes' business
            if found[0] != "item":
                refused.append(f"{base} is a block")
            elif not _durability(found[2]):
                refused.append(f"{base} has no durability (none could be read from the mod's code)")
        if not refused and not slot_refused:
            continue
        for path in paths:
            del result.files[path]
        reasons = []
        if refused:
            reasons.append(f"smithing base {'; '.join(sorted(set(refused)))}: not written, since "
                           f"{_SMITHING_BASE_RULE}")
        if slot_refused:
            reasons.append(f"smithing {'; '.join(sorted(set(slot_refused)))}: not written (#305)")
        why = ("; ".join(reasons) + "; not rewritten as a crafting recipe, which would drop the smithing "
               "table and what the upgrade carries over")
        if source in residue_sources:
            result.notes.append(f"{source}: {why}")
        else:
            result.unhandled.append(Unhandled(source, "recipe", why))
    # Tags for recipes withdrawn here or by drop_unshipped_recipes.
    _drop_orphan_slot_tags(result)


def withdraw_unacceptable_trims(result: ConversionResult) -> None:
    """Withdraw every trim recipe whose base is the pack's own item but not one
    Bedrock takes (#272).

    Runs on the merged pack after :func:`withdraw_unequipped_smithing`. A
    ``recipe_smithing_trim``'s template, addition and vanilla base were checked
    when it was written (:func:`_smithing_trim`); a base that is the pack's own
    item is checked here, on its final definition: it must be wearable armor
    carrying ``minecraft:trimmable_armors``
    (:func:`portkit.data.trim_items.addon_base_refusal`). Otherwise the recipe
    goes back to the residue under its source recipe with the reason, and is
    not rewritten as any other recipe (Alex, 2026-10-16, #268).
    """
    emitted = emitted_definitions(result.files)
    residue_sources = {u.source for u in result.unhandled}
    by_source: dict[str, list[str]] = {}
    for path in sorted(result.files):
        value = result.files[path]
        if path.startswith("recipes/") and isinstance(value, dict) and isinstance(value.get(TRIM), dict):
            by_source.setdefault(result.recipe_sources.get(path, path), []).append(path)
    for source, paths in by_source.items():
        refused = []
        for path in paths:
            found = trim_items.slot_value(result.files[path][TRIM].get("base"))
            if found is None or found[0] != "item" or ":" not in found[1] or found[1].startswith("minecraft:"):
                continue
            hit = emitted.get(found[1])
            if hit is None:
                continue  # unshipped: drop_unshipped_recipes' business
            item = hit[2].get("minecraft:item") if hit[0] == "item" else None
            components = (item.get("components") or {}) if isinstance(item, dict) else None
            refusal = trim_items.addon_base_refusal(found[1], components)
            if refusal:
                refused.append(refusal)
        if not refused:
            continue
        for path in paths:
            del result.files[path]
        why = f"trim {'; '.join(sorted(set(refused)))}: not written, and not rewritten as another recipe"
        if source in residue_sources:
            result.notes.append(f"{source}: {why}")
        else:
            result.unhandled.append(Unhandled(source, "recipe", why))


def _drop_orphan_slot_tags(result: ConversionResult) -> None:
    """Take a smithing slot tag off every item no written smithing recipe names
    in that slot any more."""
    used: dict[str, set[str]] = {tag: set() for tag in _SMITHING_SLOT_TAGS.values()}
    for path, value in result.files.items():
        if path.startswith("recipes/") and isinstance(value, dict) and isinstance(value.get(SMITHING), dict):
            for slot, tag in _SMITHING_SLOT_TAGS.items():
                if isinstance(value[SMITHING].get(slot), str):
                    used[tag].add(value[SMITHING][slot])
    for path in sorted(result.files):
        body = result.files[path]
        if not path.startswith("items/") or not isinstance(body, dict) or not isinstance(body.get("minecraft:item"), dict):
            continue
        item = body["minecraft:item"]
        ident = (item.get("description") or {}).get("identifier")
        components = item.get("components")
        tags = ((components or {}).get("minecraft:tags") or {}).get("tags") if isinstance(components, dict) else None
        if not isinstance(tags, list):
            continue
        kept = [t for t in tags if t not in used or ident in used[t]]
        if len(kept) == len(tags):
            continue
        item = copy.deepcopy(item)
        if kept:
            item["components"]["minecraft:tags"] = {"tags": kept}
        else:
            del item["components"]["minecraft:tags"]
            if isinstance(ident, str) and item["components"] == _block_item(ident, path)[1]["minecraft:item"]["components"]:
                # An item form written only to carry the tags (_block_item):
                # with none left the block keeps its own item.
                del result.files[path]
                continue
        result.files[path] = {**body, "minecraft:item": item}
