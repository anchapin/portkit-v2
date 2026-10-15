"""Item definitions.

Java describes an item's appearance in a model file and everything else about
it, stack size, food, durability, tool tier, in compiled code. Bedrock wants a
behavior pack item with components.

So the honest mapping is narrow: a plain generated item becomes a Bedrock item
with its icon. A held item (a model whose parent chain ends in vanilla
``item/handheld``, ``item/handheld_rod`` or ``item/handheld_mace``) becomes the
same flat icon plus ``minecraft:hand_equipped: true``, so Bedrock renders it in
the hand like a tool, and a note says that its mining, attack and durability
behavior, which Java keeps in compiled code, is not converted: no damage,
durability or tool tier is written (no fabrication, #87). A bow
(``item/template_bow``) and a model that draws its own ``elements`` stay
residue.

A flat icon with ``overrides`` converts as its base icon. Java draws the base
model whenever no override matches, which for an item at rest (not in use,
undamaged, no special data, no special day) is the item's ordinary look, so
the base icon is a faithful static default; a note lists the alternate looks
dropped and what they showed. That holds only when every override predicate
is a known kind whose no-match state is the resting state (see
``_OVERRIDE_KINDS``). A live readout (``time``, ``angle``, ``radiation``,
``speed``, ``in_chunk``: a clock, compass, gauge or locator whose look *is*
the reading) and a
predicate this module does not know stay residue: a frozen frame of a reading
would state a false one, and an unknown predicate may not have a resting
state at all.

A Forge or NeoForge ``separate_transforms`` model (one look per render
context) converts by its gui view, the inventory icon, which Bedrock also
draws for a dropped item and in an item frame. When every held context shows
one other model that draws elements in a single texture, that model ships as
an attachable (``attachables/<name>.json`` + ``models/entity/<name>.held.geo.json``)
bound to the holder's item slot, in vanilla's trident shape. Its pose is a
DEFAULT: Java's held display transforms are not carried. A held model that
can't be carried is residue saying whose held look it is, and Bedrock holds
the icon; ground, fixed and head views that differ from the gui view are
noted (#181).

The parent chain is followed through the mod's own intermediate models
(``mymod:item/tool_base`` -> ``minecraft:item/handheld``) the way the block
converter follows block models; the leaf's textures win over a parent's.

Block items are skipped rather than refused: Bedrock registers an item for a
custom block automatically, so emitting one here would fight the block. That
holds only for a block the conversion wrote. An item named like a block that
stayed residue (Farmer's Delight's ``rice``, a crop's seed, which Java
registers under the crop block's own id) has no Bedrock item at all, so a flat
icon converts as a plain item. What the Java item does in code, most often
placing that block, is not converted (one note per mod). The item must be
evidenced as an item (an ``item.`` lang key, or a recipe, item tag or loot
entry naming it): a blockstate says only that the block exists, and many
blocks (a portal, a wall sign) have no item even when a generator wrote them
an item model. A block item whose look is the block's model stays with the
block's residue. With no ``item.`` lang key but a ``block.`` one, the item
names itself by the block's line, as Java's ``BlockItem`` does.

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

from ..conditions import LoadContext
from ..model import ConversionResult, SourceMod, Unhandled
from ..registry import registered_ids, variant_of
from . import models

# Java item model parents whose meaning is fully in the JSON: a flat icon.
_FLAT_PARENTS = ("minecraft:item/generated",)

# Vanilla parents that are the same flat icon, drawn in the hand like a tool.
# Their behavior lives in code and is not converted; the icon and the held pose
# are what the JSON says, so those convert (2026-10-12, docs/decisions.md).
_HELD_PARENTS = (
    "minecraft:item/handheld",
    "minecraft:item/handheld_rod",
    "minecraft:item/handheld_mace",
)

# Parents that mean the look itself depends on code. Named separately so the
# residue can say what the item actually is instead of "unsupported parent".
_BEHAVIOR_PARENTS = {
    "minecraft:item/template_bow": "a bow, whose draw behavior lives in compiled code",
}

# A bucket (or other container) whose icon a fluid-container model loader
# draws from a fluid at runtime (#174): Forge's and NeoForge's
# DynamicFluidContainerModel, registered as "fluid_container" (Forge 1.20.x
# ClientForgeMod L32 @243490d7; NeoForge 1.21.x ClientNeoForgeMod L278
# @0753a6a7), and Tinkers' Construct's FluidContainerModel, registered as
# tconstruct:fluid_container (3.12.1.231 FluidClientEvents L43-44 @a5a03249;
# its generated bucket models name forge:item/bucket_drip,
# FluidBucketModelProvider L25-27). The icon is the parent's bucket with the
# named `fluid`'s texture and tint masked in, and the fluid's texture and tint
# are the fluid's client code; the masks and the vanilla bucket are not in the
# mod's jar, and the pack must not carry Mojang's art (#24). The item exists to
# carry a fluid Bedrock can't define (converters/recipes.py FLUID_RECIPE), so
# it is residue of its own kind, which the residue agent skips: drawing its
# icon would mean inventing one (#87). docs/decisions.md, 2026-10-15.
CUSTOM_FLUID = "custom_fluid"


def fluid_container_reason(model: dict) -> str | None:
    """Why an item model drawn by a fluid-container loader isn't converted
    (#174), or None when the model isn't one: its ``loader`` ends in
    ``:fluid_container`` and it names a ``fluid`` outside ``minecraft:`` (a
    vanilla fluid is not a custom one, so that model keeps the ordinary path)."""
    loader, fluid = model.get("loader"), model.get("fluid")
    if not (isinstance(loader, str) and loader.endswith(":fluid_container") and isinstance(fluid, str)):
        return None
    if fluid.startswith("minecraft:"):
        return None
    return (
        f"a fluid container for the custom fluid {fluid!r}: model loader {loader!r} draws the icon at "
        "runtime by masking the fluid's texture and tint into its parent's bucket, whose art and masks "
        "are the loader's and vanilla's, not the jar's, so there is no icon to ship; and Bedrock add-ons "
        "can't define a fluid for it to hold (no fluid block component; the script fluid container "
        "holds only water, lava, powder snow or potion)"
    )


# Item format versions: 1.20.10 for a plain icon item; minecraft:hand_equipped
# needs 1.20.30 or later (learn.microsoft.com, Items Documentation -
# minecraft:hand_equipped).
_ITEM_FORMAT = "1.20.10"
_HELD_FORMAT = "1.20.30"

# Item model override predicates by what Java's base model (no override
# matching) shows, keyed by the predicate's name without its namespace: mods
# register their own (``supplementaries:pull``, ``mekanism:encoded``) and
# Forge-era mods put some under ``minecraft:`` (Alex's Mobs ``silly``). Each
# kind's phrase says what the dropped alternate looks showed. The names are
# vanilla 1.21.1's item properties plus the mod-specific ones the corpus uses
# (2026-10-12, docs/decisions.md); a predicate not listed stays residue.
_OVERRIDE_KINDS = {
    "occasion": ("a special-day or easter-egg look", (
        "funny_day", "silly", "wrapping",
    )),
    "use": ("the look while in use (drawn, charging, cast, blocking, active)", (
        "pull", "pulling", "charged", "firework", "cast", "throwing", "blocking", "tooting",
        "brushing", "cooldown", "using", "active", "is_active",
    )),
    "wear": ("the damaged or broken look", ("broken", "damage", "damaged")),
    "state": ("looks picked by the item's stored data (trim, dye, mode, contents, count)", (
        "custom_model_data", "trim_type", "filled", "dye", "dyed", "encoded", "invalid",
        "mode", "clipboard_type", "midas_gold_count", "is_primed",
    )),
    "context": ("the look in another render context (left hand, placed in the world)", (
        "lefthanded", "in_world",
    )),
}
# ``dyed``: Supplementaries 1.20-3.1.43 registers it on the quiver as 1 when
# DyeableLeatherItem.hasCustomColor(stack), else 0 (ClientRegistry.setup,
# lambda$setup$14, read from the jar's bytecode), so the base model is the
# undyed quiver (2026-10-15, docs/decisions.md).
_OVERRIDE_KIND = {name: kind for kind, (_, names) in _OVERRIDE_KINDS.items() for name in names}

# Predicates whose look is a live reading: the base icon is one frame of a
# dial, so a static icon would show a false reading. These stay residue.
_READOUT_PREDICATES = {
    "time": "a clock face", "angle": "a compass needle", "radiation": "a radiation gauge",
    "speed": "a speed gauge", "in_chunk": "a locator that lights up near its target",
}

# Forge's and NeoForge's ``separate_transforms`` loader: one item model whose
# look is picked per render context. Java bakes ``base`` for every context and
# ``perspectives[<context>]`` where one is given, keyed by
# ItemDisplayContext.getSerializedName(); any other key is ignored, and the
# outer model's own overrides are the item's (SeparateTransformsModel.Loader.read
# and Baked.applyTransform: Forge 1.20.1 @d13dd32 L147-189, NeoForge 1.21.1
# @00c6a3f L135-169). The loader is registered as forge:separate_transforms /
# neoforge:separate_transforms (ClientForgeMod L35).
_SEPARATE_LOADERS = ("forge:separate_transforms", "neoforge:separate_transforms")
_DISPLAY_CONTEXTS = (
    "none", "thirdperson_lefthand", "thirdperson_righthand", "firstperson_lefthand",
    "firstperson_righthand", "head", "gui", "ground", "fixed",
)
# The contexts a Bedrock attachable draws (both hands, first and third person).
_HELD_CONTEXTS = (
    "firstperson_righthand", "firstperson_lefthand", "thirdperson_righthand", "thirdperson_lefthand",
)
# Bedrock draws a dropped item and an item frame with the item's icon.
_ICON_CONTEXTS = ("ground", "fixed")

# A held 3D model ships as an attachable, in the shape of vanilla's own
# trident (bedrock-samples v1.26.50.4 resource_pack/attachables/trident.entity.json
# and models/entity/trident.geo.json): entity_alphatest materials with the
# enchantment glint, controller.render.item_default, and the geometry's root
# bone bound to the holder's item slot. DEFAULT pose: Java's held display
# transforms (rotation, translation, scale per context) are not carried, since
# how they map onto Bedrock's item bones is unverified; the elements sit where
# the block geometry puts them (2026-10-15, docs/decisions.md).
_ATTACHABLE_FORMAT = "1.10.0"
_ITEM_SLOT_BINDING = "q.item_slot_to_bone_name(c.item_slot)"

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


def _chain(mod: SourceMod, model: dict) -> tuple[dict | None, list, str]:
    """Follow an item model's parent chain inside this mod to its vanilla parent.

    Returns ``({"parent", "textures", "elements", "overrides"}, files read,
    refusal)``. ``parent`` is the vanilla parent the chain ends in (``None``
    when no model in it names one), ``textures`` the merged map (a child's
    key wins over its parent's, as in Java), and ``elements``/``overrides``
    whether the chain has elements (the nearest model that has them wins in Java,
    so any of them makes it 3D) and the item's own model's ``overrides`` (falsy
    when it has none; Java does not inherit overrides from a parent).
    """
    textures: dict = {}
    elements = overrides = False
    seen: list = []
    current = model
    for _ in range(models._MAX_PARENT_DEPTH):
        if isinstance(current.get("textures"), dict):
            textures = {**current["textures"], **textures}
        # Java treats an empty elements list as "inherit the parent's".
        elements = elements or bool(current.get("elements"))
        if current is model:
            # Java reads overrides from the item's own model only; a parent's
            # are not inherited (unlike textures and elements).
            overrides = current.get("overrides") or False
        parent = current.get("parent")
        if not isinstance(parent, str):
            return {"parent": None, "textures": textures, "elements": elements,
                    "overrides": overrides}, seen, ""
        parent = models.normalize(parent)
        if parent.startswith("minecraft:"):
            return {"parent": parent, "textures": textures, "elements": elements,
                    "overrides": overrides}, seen, ""
        path = models.model_path(mod, parent)
        if path is None:
            return None, seen, f"item model extends {parent!r}, a model from another namespace"
        if not path.resolve().is_relative_to(mod.root.resolve()) or not path.is_file():
            return None, seen, f"item model extends {parent!r}, which is not in this mod"
        seen.append(path)
        try:
            current = json.loads(path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return None, seen, f"parent model {parent!r} could not be read as JSON: {exc}"
        if not isinstance(current, dict):
            return None, seen, f"parent model {parent!r} is not a JSON object"
    return None, seen, "item model parent chain is deeper than we follow"


def _separate_views(model: dict) -> tuple[dict | None, str]:
    """Split a ``separate_transforms`` item model into what each context shows.

    Returns ``({"icon": model, "held": model, "others": {context: model}},
    "")`` or ``(None, reason)``. ``icon`` is the gui view carrying the outer
    model's overrides (Java resolves overrides on the outer model; a
    sub-model's own are not consulted); ``held`` is the one view every held
    context shows, or ``None`` when they differ; ``others`` the views of
    ground, fixed and head that differ from the icon."""
    base = model.get("base")
    if not isinstance(base, dict):
        return None, "separate_transforms item model has no base model object"
    perspectives = model.get("perspectives")
    if not isinstance(perspectives, dict):
        # GsonHelper.getAsJsonObject throws: Java fails to load the model.
        return None, "separate_transforms item model has no perspectives object"
    views = {}
    for context in _DISPLAY_CONTEXTS:
        view = perspectives.get(context, base)
        if not isinstance(view, dict):
            return None, f"separate_transforms perspective {context!r} is not a model object"
        views[context] = view
    gui = {k: v for k, v in views["gui"].items() if k != "overrides"}
    if model.get("overrides"):
        gui["overrides"] = model["overrides"]
    held = [views[c] for c in _HELD_CONTEXTS]
    others = {c: views[c] for c in (*_ICON_CONTEXTS, "head") if views[c] != views["gui"]}
    return {"icon": gui, "held": held[0] if all(v == held[0] for v in held) else None,
            "others": others}, ""


def _held_shape(mod: SourceMod, view: dict) -> tuple[dict | None, list, str]:
    """The elements and textures a held view draws, through its parent chain.

    Returns ``({"elements", "textures", "parent"}, files read, refusal)``:
    ``elements`` from the nearest model that has any (Java's rule),
    ``textures`` merged child-first, ``parent`` the vanilla parent the chain
    ends in (``None`` when it ends in the mod)."""
    textures: dict = {}
    elements: list = []
    seen: list = []
    current = view
    for _ in range(models._MAX_PARENT_DEPTH):
        if isinstance(current.get("textures"), dict):
            textures = {**current["textures"], **textures}
        if not elements and isinstance(current.get("elements"), list):
            elements = current["elements"]
        parent = current.get("parent")
        if not isinstance(parent, str):
            return {"elements": elements, "textures": textures, "parent": None}, seen, ""
        parent = models.normalize(parent)
        if parent.startswith("minecraft:"):
            return {"elements": elements, "textures": textures, "parent": parent}, seen, ""
        path = models.model_path(mod, parent)
        if path is None:
            return None, seen, f"held model extends {parent!r}, a model from another namespace"
        if not path.resolve().is_relative_to(mod.root.resolve()) or not path.is_file():
            return None, seen, f"held model extends {parent!r}, which is not in this mod"
        seen.append(path)
        try:
            current = json.loads(path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return None, seen, f"held model {parent!r} could not be read as JSON: {exc}"
        if not isinstance(current, dict):
            return None, seen, f"held model {parent!r} is not a JSON object"
    return None, seen, "held model parent chain is deeper than we follow"


def _attachable(mod: SourceMod, name: str, shape: dict) -> tuple[dict | None, str]:
    """``{path: body}`` for a held 3D model's attachable and geometry, or why not.

    Bedrock's attachable maps one texture over its geometry, so every element
    face must wear the same texture, a png of this mod's item or block
    textures."""
    key, why = models.element_texture({"elements": shape["elements"]})
    if key is None:
        return None, why.replace("per-face geometry materials are not mapped yet",
                                 "an attachable maps one texture")
    reference = _resolve_alias(shape["textures"], f"#{key}")
    if not isinstance(reference, str) or reference.startswith("#"):
        return None, f"held model leaves texture {('#' + key)!r} unfilled"
    texture, why = models.texture_file(reference, mod.namespace)
    if texture is None:
        return None, why
    identifier = f"geometry.{mod.namespace}.{name}.held"
    geo, why = models.geometry_bones([("root", shape["elements"])], identifier)
    if geo is None:
        return None, f"held model: {why}"
    for bone in geo["minecraft:geometry"][0]["bones"]:
        bone["binding"] = _ITEM_SLOT_BINDING
    return {
        f"attachables/{name}.json": {
            "format_version": _ATTACHABLE_FORMAT,
            "minecraft:attachable": {
                "description": {
                    "identifier": bedrock_identifier(mod.namespace, name),
                    "materials": {"default": "entity_alphatest", "enchanted": "entity_alphatest_glint"},
                    "textures": {"default": texture, "enchanted": "textures/misc/enchanted_item_glint"},
                    "geometry": {"default": identifier},
                    "render_controllers": ["controller.render.item_default"],
                },
            },
        },
        f"models/entity/{name}.held.geo.json": geo,
    }, ""


def _resolve_alias(textures: dict, reference):
    """Follow ``#name`` texture variables through the merged map, as Java does.

    Returns the concrete reference, or the last ``#`` reference when the
    variable is never filled (``texture_shortname`` then says so)."""
    for _ in range(len(textures) + 1):
        if not (isinstance(reference, str) and reference.startswith("#")):
            return reference
        target = textures.get(reference[1:])
        if target is None:
            return reference
        reference = target
    return reference


def _held_note(namespace: str, names: list[str]) -> str:
    many = len(names) > 1
    return (
        f"{namespace}: {len(names)} held item{'s' if many else ''} ({', '.join(names)}) "
        f"{'convert' if many else 'converts'} as {'icons' if many else 'an icon'} held like a "
        "tool (minecraft:hand_equipped). Mining speed, attack damage, durability and tool "
        "tier live in Java code, not in the model, so none is written: in Bedrock "
        f"{'they behave' if many else 'it behaves'} like a plain item until that is added by hand."
    )


def _override_looks(overrides) -> tuple[list | None, str]:
    """Check an item model's ``overrides`` for a faithful base-icon default.

    Returns ``(looks, "")`` when every predicate is a known kind whose
    no-match state is the item at rest, ``looks`` being ``(kind, predicate,
    model)`` per predicate key, or ``(None, reason)`` for the residue."""
    if not isinstance(overrides, list):
        return None, "item model overrides is not a list"
    looks = []
    for entry in overrides:
        predicate = entry.get("predicate") if isinstance(entry, dict) else None
        if not isinstance(predicate, dict) or not predicate:
            return None, "an item model override has no predicate"
        target = entry.get("model")
        for key in predicate:
            local = key.rpartition(":")[2] if isinstance(key, str) else ""
            if local in _READOUT_PREDICATES:
                return None, (
                    f"model swaps texture on {key!r}, {_READOUT_PREDICATES[local]} whose look is a "
                    "live reading; one frozen frame as a static icon would show a false reading, "
                    "and Bedrock item icons cannot change with it"
                )
            if local not in _OVERRIDE_KIND:
                return None, (
                    f"model swaps texture on item property {key!r}, which portkit does not know; "
                    "without knowing the property it cannot tell whether the base look is the "
                    "item's resting look"
                )
            looks.append((_OVERRIDE_KIND[local], key, target if isinstance(target, str) else None))
    return looks, ""


def _override_note(namespace: str, converted: list[tuple[str, list]]) -> str:
    """One note per mod for the items whose override looks were dropped."""
    parts = []
    kinds: list[str] = []
    for name, looks in converted:
        keys = sorted({key for _, key, _ in looks})
        models_ = sorted({m.rpartition(":")[2].removeprefix("item/") for _, _, m in looks if m})
        alt = f"{len(models_)} alternate look{'s' if len(models_) != 1 else ''}"
        shown = ", ".join(models_[:3]) + (", ..." if len(models_) > 3 else "")
        parts.append(f"{name} ({', '.join(keys)} -> {alt}{': ' + shown if shown else ''})")
        for kind, _, _ in looks:
            if kind not in kinds:
                kinds.append(kind)
    many = len(converted) > 1
    lost = "; ".join(_OVERRIDE_KINDS[k][0] for k in sorted(kinds))
    return (
        f"{namespace}: {len(converted)} item{'s' if many else ''} with model overrides "
        f"{'convert' if many else 'converts'} as {'their' if many else 'its'} base icon, the look "
        f"Java draws when no override applies (the item at rest): {'; '.join(parts)}. Bedrock's "
        "minecraft:icon is one texture per item, so nothing switches to the alternate looks, "
        f"which showed {lost}. Their models and textures are handled as before (variant models "
        "are noted, textures ship); the code that picks them is not converted. An item whose "
        "base icon texture itself did not convert is withdrawn to the residue, naming that texture."
    )


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


def _flat_icon(mod: SourceMod, path) -> bool:
    """Whether an item model is a flat icon this converter would emit: its
    chain ends in a flat or held vanilla parent, draws no elements, and any
    overrides have a resting look."""
    try:
        model = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(model, dict):
        return False
    flat, _, _ = _chain(mod, model)
    if flat is None or flat["elements"]:
        return False
    if flat["parent"] not in _FLAT_PARENTS and flat["parent"] not in _HELD_PARENTS:
        return False
    return not flat["overrides"] or _override_looks(flat["overrides"])[0] is not None


def _lang_keys(mod: SourceMod) -> set[str]:
    """The keys of the mod's ``en_us.json`` (empty when it has none)."""
    path = mod.assets / "lang" / "en_us.json"
    try:
        lang = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return set()
    return set(lang) if isinstance(lang, dict) else set()


def _placer_note(namespace: str, names: list[str]) -> str:
    """One note per mod for items emitted without the block they place."""
    many = len(names) > 1
    return (
        f"{namespace}: {len(names)} item{'s' if many else ''} ({', '.join(names)}) "
        f"{'share their ids' if many else 'shares its id'} with a block that did not convert "
        f"(see {'each' if many else 'its'} block's own residue entry), so Bedrock makes no item "
        f"for {'them' if many else 'it'}; {'each converts' if many else 'it converts'} as a plain "
        "item with its icon, usable in recipes, loot and inventories. Whatever the Java item does "
        "in code is not converted, most often placing that block (a seed, a sign, a door, a "
        f"sapling): in Bedrock {'they place' if many else 'it places'} nothing. Once the block "
        "converts, Bedrock's own item for it takes this item's place."
    )


def _held_look(mod: SourceMod, name: str, views: dict, result: ConversionResult,
               held_parts: dict[str, str]) -> dict:
    """Write the held view of an emitted separate_transforms item.

    Returns ``{"held": "attachable" | "icon" | None, "why": str, "others": [...]}``:
    ``attachable`` when its elements shipped as one, ``icon`` when Java holds
    the gui view itself (Bedrock does the same), ``None`` with the reason when
    a different held look could not be carried."""
    look = {"held": None, "why": "", "others": sorted(views["others"])}
    for context, view in sorted(views["others"].items()):
        # A ground, fixed or head view's own model file is residue naming whose look it is.
        _, files, _ = _held_shape(mod, view)
        where = ("Bedrock draws an item on the head only when it is wearable there, which "
                 "nothing in the source says" if context == "head"
                 else "Bedrock draws the item's icon there")
        for path in files:
            held_parts.setdefault(str(path.relative_to(mod.root)), (
                f"the {context} view of {mod.namespace}:{name}, not carried: {where}; "
                "the item converts with its gui view as its icon"))
    held = views["held"]
    gui = {k: v for k, v in views["icon"].items() if k != "overrides"}
    if held is None:
        look["why"] = "Java shows a different model per hand or per first/third person"
        return look
    if held == gui:
        look["held"] = "icon"
        return look
    shape, files, why = _held_shape(mod, held)
    if shape is not None and not shape["elements"]:
        why = "the held view is another model without elements, not the inventory icon"
        shape = None
    built = None
    if shape is not None:
        built, why = _attachable(mod, name, shape)
    for path in files:
        held_parts[str(path.relative_to(mod.root))] = "" if built else (
            f"held 3D model of {mod.namespace}:{name}, not converted: {why}; the item "
            "converts with its inventory icon, which Bedrock also draws in the hand")
    if built is None:
        look["why"] = why
        return look
    for path in files:
        result.claim(mod, path)
    result.files.update(built)
    look["held"] = "attachable"
    return look


def _separate_note(namespace: str, items: list[tuple[str, dict]]) -> str:
    """One note per mod for items whose model picks a look per render context."""
    parts = []
    for name, look in items:
        if look["held"] == "attachable":
            held = "held 3D model as an attachable (DEFAULT pose: Java's held display transforms not carried)"
        elif look["held"] == "icon":
            held = "held as the icon, as in Java"
        else:
            held = f"held as the icon, not Java's held model ({look['why']})"
        dropped = f"; not carried: the {', '.join(look['others'])} look" if look["others"] else ""
        parts.append(f"{name} ({held}{dropped})")
    many = len(items) > 1
    return (
        f"{namespace}: {len(items)} item{'s' if many else ''} with a separate_transforms model "
        f"{'convert' if many else 'converts'} with the gui view as {'their' if many else 'its'} "
        f"icon, which Bedrock also draws dropped and in item frames: {'; '.join(parts)}. "
        "Java's ground, fixed and head views are not carried when they differ from the gui view "
        "(Bedrock draws the icon on the ground and in frames, and an item on the head only "
        "when it is wearable)."
    )


def convert(mod: SourceMod, context: LoadContext | None = None,
            emitted_blocks: set[str] | None = None) -> ConversionResult:
    """Convert the mod's flat item models.

    An item the mod's code registers only while a config flag is on (a cited
    ``registers`` pattern, such as Mythic Metals' ``*_dust`` under
    ``enableDusts``) is ``conditional_item`` residue when that flag is off,
    by its cited default or by the user's config (:meth:`LoadContext.gated_item`).

    ``emitted_blocks`` holds the Bedrock ids of the blocks this conversion
    wrote. An item model named like a blockstate is the block's item and is
    left to Bedrock, which registers one for every custom block, only when
    that block was emitted; when it is residue, a flat icon of an id
    evidenced as an item converts as a plain item and a note says its
    code (most often placing the block) was not. ``None``, a direct call
    with no block result, keeps the old rule: every blockstate's item is the
    block's.
    """
    result = ConversionResult()
    src = mod.assets / "models" / "item"
    if not src.is_dir():
        return result
    if context is None:
        context = LoadContext(mod)

    blocks = _block_names(mod)
    java: set[str] | None = None  # registered Java ids, read on the first item that needs them
    registered: set[str] = set()  # ...and their Bedrock ids under the converter's mapping
    variants: list[tuple[str, str]] = []  # (model name, texture) of skipped variants
    held_names: list[str] = []  # emitted items held like a tool
    override_items: list[tuple[str, list]] = []  # emitted base icons whose override looks were dropped
    items_known: set[str] | None = None  # ids evidenced as items, read on first need
    lang_keys: set[str] | None = None  # en_us keys, read on first need
    placers: list[str] = []  # emitted plain items whose same-id block did not convert
    separate: list[tuple[str, dict]] = []  # emitted separate_transforms items and their held look
    icon_parts: set[str] = set()  # item model names an emitted item's gui view is built from
    held_parts: dict[str, str] = {}  # source of another view's model -> its residue reason ("" converted)
    for path in sorted(src.glob("*.json")):
        name = path.stem
        unplaced = False
        if name in blocks:
            if emitted_blocks is None or bedrock_identifier(mod.namespace, name) in emitted_blocks:
                # The block converter owns this one; claiming it keeps it off the
                # unowned list without producing a competing definition.
                result.claim(mod, path)
                continue
            # The block is residue, so Bedrock makes no item for it. The Java
            # item still exists (usually the one that places it); a flat icon
            # converts as a plain item, without its code (#177 rice). Any
            # other look (a block model, a 3D shape) is left with the block's
            # residue, as before.
            if items_known is None:
                items_known = registered_ids(mod.root, items_only=True)
            if not _flat_icon(mod, path) or f"{mod.namespace}:{name}" not in items_known:
                # Nothing but the blockstate (and perhaps a generated model)
                # says Java gives this block an item: a portal or a crop with
                # no item of its own. It stays with the block's residue.
                result.claim(mod, path)
                continue
            unplaced = True

        rel = result.claim(mod, path)
        gated = context.gated_item(f"{mod.namespace}:{name}")
        if gated is not None and gated.passes is not True:
            # Java doesn't register this item with the config the conversion holds.
            result.unhandled.append(Unhandled(rel, "conditional_item", gated.reason()))
            continue
        try:
            model = json.loads(path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            result.unhandled.append(Unhandled(rel, "item", f"invalid JSON: {exc}"))
            continue

        if not isinstance(model, dict):
            result.unhandled.append(Unhandled(rel, "item", "item model is not a JSON object"))
            continue
        fluid_why = fluid_container_reason(model)
        if fluid_why is not None:
            result.unhandled.append(Unhandled(rel, CUSTOM_FLUID, fluid_why))
            continue
        views = None
        if model.get("loader") in _SEPARATE_LOADERS:
            # The inventory look is the gui view; the rest of this loop reads
            # that, and the held view is handled once the item converts.
            views, why = _separate_views(model)
            if views is None:
                result.unhandled.append(Unhandled(rel, "item", why))
                continue
            model = views["icon"]
            if isinstance(model.get("loader"), str):
                result.unhandled.append(Unhandled(rel, "item", (
                    f"separate_transforms gui view is built by model loader {model['loader']!r} "
                    "(code, not JSON elements or layers), so it is not a flat icon")))
                continue
        # Intermediate parents are claimed only when the item converts: a
        # refused leaf's residue already names the chain it went through.
        flat, parents, why = _chain(mod, model)
        if flat is None:
            result.unhandled.append(Unhandled(rel, "item", why))
            continue
        parent = flat["parent"]
        if parent in _BEHAVIOR_PARENTS:
            result.unhandled.append(Unhandled(rel, "item", _BEHAVIOR_PARENTS[parent]))
            continue
        if parent is None and flat["elements"]:
            result.unhandled.append(
                Unhandled(rel, "item", "model draws its own elements, a 3D shape rather than a flat icon")
            )
            continue
        if parent is None and parents:
            result.unhandled.append(
                Unhandled(
                    rel,
                    "item",
                    f"item model parent {model.get('parent')!r} names no vanilla parent and no "
                    "elements (a model built in code), so it is not a flat icon",
                )
            )
            continue
        if parent not in _FLAT_PARENTS and parent not in _HELD_PARENTS:
            leaf = model.get("parent")
            via = f" (via {leaf!r})" if parents else ""
            shown = parent if parents else leaf
            result.unhandled.append(
                Unhandled(rel, "item", f"item model parent {shown!r}{via} is not a flat icon")
            )
            continue
        looks: list = []
        if flat["overrides"] and flat["elements"]:
            result.unhandled.append(
                Unhandled(
                    rel,
                    "item",
                    "model draws its own elements and swaps them on item properties "
                    "(overrides), a 3D shape rather than a flat icon",
                )
            )
            continue
        if flat["overrides"]:
            looks, why = _override_looks(flat["overrides"])
            if looks is None:
                result.unhandled.append(Unhandled(rel, "item", why))
                continue
        if flat["elements"]:
            result.unhandled.append(
                Unhandled(
                    rel,
                    "item",
                    "model draws its own elements, a 3D shape rather than a flat icon",
                )
            )
            continue
        held = parent in _HELD_PARENTS

        textures = flat["textures"]
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

        reference = _resolve_alias(textures, textures[layers[0]])
        if not isinstance(reference, str):
            result.unhandled.append(Unhandled(rel, "item", f"{layers[0]} is not a texture reference"))
            continue
        ref_ns, _, rel_path = reference.rpartition(":")
        if models.is_vanilla(reference, mod.namespace):
            # Bedrock's own copy of the vanilla icon (models.vanilla_texture);
            # the pipeline adds the atlas entry a <ns>:vanilla/... key needs.
            icon, _, why = models.vanilla_texture(reference, mod.namespace, "item")
            if icon is None:
                result.unhandled.append(Unhandled(rel, "item", why.replace("model points at", "icon")))
                continue
        elif ref_ns and ref_ns != mod.namespace:
            result.unhandled.append(
                Unhandled(rel, "item", f"icon {reference!r} is a texture from another namespace")
            )
            continue
        else:
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
        components = {
            "minecraft:icon": icon,
            "minecraft:max_stack_size": _DEFAULT_STACK_SIZE,
        }
        if held:
            components["minecraft:hand_equipped"] = True
            held_names.append(name)
        if looks:
            override_items.append((name, looks))
        for parent_file in parents:
            result.claim(mod, parent_file)
            if views is not None and parent_file.parent == src:
                icon_parts.add(parent_file.stem)
        if views is not None:
            separate.append((name, _held_look(mod, name, views, result, held_parts)))
        if unplaced:
            placers.append(name)
            if lang_keys is None:
                lang_keys = _lang_keys(mod)
            if (f"item.{mod.namespace}.{name}" not in lang_keys
                    and f"block.{mod.namespace}.{name}" in lang_keys):
                # Java names a block's item by the block's key when the item
                # has none (BlockItem#getDescriptionId); Bedrock looks up the
                # item's own key, so point it at the block's line.
                components["minecraft:display_name"] = {"value": f"tile.{mod.namespace}:{name}.name"}
        result.files[f"items/{name}.json"] = {
            "format_version": _HELD_FORMAT if held else _ITEM_FORMAT,
            "minecraft:item": {
                "description": {
                    "identifier": bedrock_identifier(mod.namespace, name),
                    "menu_category": {"category": _MENU_CATEGORY},
                },
                "components": components,
            },
        }
    if held_parts:
        # A held view's own model file converted with its item (as an
        # attachable) or is residue saying whose held look it is.
        kept = []
        for entry in result.unhandled:
            reason = held_parts.get(entry.source)
            if reason is None:
                kept.append(entry)
            elif reason:
                kept.append(Unhandled(entry.source, entry.kind, reason))
        result.unhandled[:] = kept
    if icon_parts:
        variants = [(n, ref) for n, ref in variants if n not in icon_parts]
    if separate:
        result.notes.append(_separate_note(mod.namespace, separate))
    if held_names:
        result.notes.append(_held_note(mod.namespace, held_names))
    if override_items:
        result.notes.append(_override_note(mod.namespace, override_items))
    if placers:
        result.notes.append(_placer_note(mod.namespace, placers))
    if variants:
        result.notes.extend(_variant_notes(mod, src, variants, java or set()))
    return result
