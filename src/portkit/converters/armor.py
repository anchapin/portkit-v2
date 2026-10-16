"""Mod armor: ``minecraft:wearable``, durability and enchantability read from the mod's code (#274).

A Java armor item is an ``ArmorItem`` built on an armor material: its slot,
armor points (protection), toughness, knockback resistance, durability and
enchantability are numbers in the mod's code, not in its data. Each adapter's
``item_armor`` hook reads them from the jar's bytecode with the shared readers
of :mod:`portkit.itemcode` and cites where each came from; this converter
writes what Bedrock has a component for, on the item definition the item
converter wrote:

* ``minecraft:wearable`` ``{"slot", "protection"}``: the slot from the piece's
  ``ArmorItem.Type`` (helmet ``slot.armor.head``, chestplate
  ``slot.armor.chest``, leggings ``slot.armor.legs``, boots
  ``slot.armor.feet``), protection = the Java armor points;
* ``minecraft:durability`` ``{"max_durability"}`` = the Java max damage;
* ``minecraft:enchantable`` ``{"slot", "value"}``: ``armor_head`` /
  ``armor_torso`` / ``armor_legs`` / ``armor_feet``, value = the Java
  enchantability;
* ``minecraft:max_stack_size`` 1 (Java armor stacks to one; Bedrock sets it for
  any non-hand wearable slot too).

Bedrock's side is :data:`BEDROCK_SOURCES`. Java's armor toughness and
knockback resistance have no Bedrock item component: they are read (an
unreadable one leaves the piece unwritten like any other stat) and named in a
note, never approximated.

A mod item Java's own data marks as armor (its ``#minecraft:head_armor``,
``chest_armor``, ``leg_armor``, ``foot_armor`` or ``trimmable_armor``
membership) that no adapter can read is left as the plain item it converted
to, and is residue (kind ``armor``) with the reason (Alex, 2026-10-16, #268:
no invented stats, #87).

Worn rendering: a wearable piece whose texture the adapter read from the mod's
code (:class:`portkit.itemcode.ArmorLook`, :mod:`portkit.armorlook`) gets an
attachable in the shape of Mojang's own armor attachables
(:data:`ATTACHABLE_SOURCES`): the ``armor`` / ``armor_enchanted`` materials,
the enchant glint, ``controller.render.armor`` and vanilla's
``geometry.humanoid.armor.helmet`` / ``chestplate`` / ``leggings`` /
``boots``, wearing the mod's own layer texture (layer 2 for leggings, layer 1
otherwise, as Java's ``usesInnerModel``). Java's 64x32 armor layer UVs are the
same as that geometry's (:data:`UV_SOURCES`), so the texture is copied
unchanged to ``textures/models/armor/<namespace>/``. When no reader could say
where the texture is, the DEFAULT name ``<material>_layer_<n>.png`` (the
material constant lowercased, in the item's namespace) is tried, only if that
file is in the jar, and labelled DEFAULT in the notes. A piece the mod draws
its own way (its own model, a tinted or multi-layer texture) or whose texture
isn't a single 64x32 png in the jar ships without one, and a note says why;
the source textures stay where they are.
"""
from __future__ import annotations

import copy
import json

from .. import png
from ..itemcode import VANILLA_SOURCES, ArmorLook, ArmorPiece
from ..model import ConversionResult, SourceMod, Unhandled
from .tags import TagResolver

# ArmorItem.Type -> (minecraft:wearable slot, minecraft:enchantable slot).
SLOTS = {
    "HELMET": ("slot.armor.head", "armor_head"),
    "CHESTPLATE": ("slot.armor.chest", "armor_torso"),
    "LEGGINGS": ("slot.armor.legs", "armor_legs"),
    "BOOTS": ("slot.armor.feet", "armor_feet"),
}
# minecraft:wearable and minecraft:enchantable need item format 1.20.30.
WEARABLE_FORMAT = "1.20.30"
BEDROCK_SOURCES = (
    "MicrosoftDocs/minecraft-creator@4186dc4ec84c ItemComponents/minecraft_wearable.md (slot: slot.armor.head, "
    "slot.armor.chest, slot.armor.legs, slot.armor.feet; protection: integer; needs format 1.20.30), "
    "minecraft_enchantable.md (slot: armor_head, armor_torso, armor_legs, armor_feet; value: integer >= 0), "
    "minecraft_durability.md (max_durability); Mojang bedrock-samples@46ba6ea9 "
    "behavior_pack/items/diamond_spear.json (max_stack_size 1 with durability and enchantable)"
)
# Java tags that say an item is armor (vanilla 1.21's slot tags, and the trim base tag).
JAVA_ARMOR_TAGS = (
    "minecraft:head_armor", "minecraft:chest_armor", "minecraft:leg_armor", "minecraft:foot_armor",
    "minecraft:trimmable_armor",
)
RESIDUE_KIND = "armor"

# ArmorItem.Type -> (vanilla Bedrock armor geometry, the parent_setup variable
# that hides the wearer's own layer under it), as Mojang's diamond armor attachables.
ATTACHABLE_SLOTS = {
    "HELMET": ("geometry.humanoid.armor.helmet", "helmet_layer_visible"),
    "CHESTPLATE": ("geometry.humanoid.armor.chestplate", "chest_layer_visible"),
    "LEGGINGS": ("geometry.humanoid.armor.leggings", "leg_layer_visible"),
    "BOOTS": ("geometry.humanoid.armor.boots", "boot_layer_visible"),
}
ATTACHABLE_FORMAT = "1.8.0"
ARMOR_TEXTURE_DIR = "textures/models/armor"
ATTACHABLE_SOURCES = (
    "Mojang bedrock-samples@46ba6ea9 resource_pack/attachables/diamond_helmet.json (and _chestplate, _leggings, "
    "_boots): format 1.8.0, materials armor / armor_enchanted, textures textures/models/armor/diamond_1 (_2 for "
    "leggings) + textures/misc/enchanted_actor_glint, geometry geometry.humanoid.armor.<piece>, parent_setup "
    "variable.<helmet|chest|leg|boot>_layer_visible = 0.0, render_controllers controller.render.armor "
    "(render_controllers/armor.render_controllers.json)"
)
UV_SOURCES = (
    "Java: 1.20.1, 1.21.1 and 1.21.4 LayerDefinitions build the armor layers as HumanoidArmorModel.createBodyLayer"
    "(OUTER 1.0 / INNER 0.5) on a 64x32 texture: HumanoidModel.createMesh head texOffs(0,0) 8x8x8, hat (32,0) "
    "8x8x8, body (16,16) 8x12x4, right_arm (40,16) 4x12x4, left_arm (40,16) mirrored, legs (0,16) 4x12x4 (left "
    "mirrored, deformation -0.1) (client jars sha1 0c3ec587, 30c73b1c, a7e5a602, Mojang client.txt); Bedrock: "
    "bedrock-samples@46ba6ea9 models/mobs.json geometry.humanoid.armor.* on geometry.humanoid.armor1/armor2 on "
    "geometry.zombie (models/entity/zombie.v1.0.geo.json, texture 64x32): the same boxes and uv offsets, legs "
    "and left arm mirrored"
)
EQUIPMENT_SOURCE = ("minecraft.wiki Equipment (oldid 3837905): assets/<ns>/equipment/<id>.json (1.21.4+; "
                    "models/equipment/ in 1.21.2-1.21.3), layers.humanoid / humanoid_leggings, texture ns:path -> "
                    "assets/<ns>/textures/entity/equipment/<layer_type>/<path>.png")


def _version(text) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in str(text).split("."))
    except ValueError:
        return ()


def java_armor(mod: SourceMod, tags: TagResolver) -> dict[str, list[str]]:
    """This namespace's items Java's armor tags hold -> the tags."""
    out: dict[str, list[str]] = {}
    for tag in JAVA_ARMOR_TAGS:
        found = tags.members(tag)
        members = found.members if found is not None else tags.own_share(tag)
        for member in members:
            if member.startswith(f"{mod.namespace}:"):
                out.setdefault(member, []).append(tag)
    return out


def valid(piece: object) -> bool:
    return (isinstance(piece, ArmorPiece) and piece.kind in SLOTS
            and isinstance(piece.protection, int) and not isinstance(piece.protection, bool) and piece.protection >= 0
            and isinstance(piece.durability, int) and piece.durability > 0
            and isinstance(piece.enchantability, int) and piece.enchantability >= 0
            and isinstance(piece.toughness, float) and isinstance(piece.knockback, float))


def wear(body: dict, piece: ArmorPiece) -> dict:
    """``body`` (an emitted item definition) as the armor ``piece``."""
    item = copy.deepcopy(body)
    if _version(item.get("format_version")) < _version(WEARABLE_FORMAT):
        item["format_version"] = WEARABLE_FORMAT
    wearable, enchantable = SLOTS[piece.kind]
    components = item["minecraft:item"].setdefault("components", {})
    components["minecraft:max_stack_size"] = 1
    components["minecraft:wearable"] = {"slot": wearable, "protection": piece.protection}
    components["minecraft:durability"] = {"max_durability": piece.durability}
    components["minecraft:enchantable"] = {"slot": enchantable, "value": piece.enchantability}
    return item


def _png(mod: SourceMod, rel: str) -> tuple[bytes | None, str]:
    """The jar's png at ``rel`` if it is a 64x32 armor layer texture, else why not."""
    path = mod.root / rel
    if not path.is_file():
        return None, f"its texture {rel} isn't in the jar"
    data = path.read_bytes()
    size = png.dimensions(data)
    if size is None:
        return None, f"its texture {rel} isn't a png that can be read"
    width, height = size
    if (width, height) != (64, 32):
        return None, (f"its texture {rel} is {width}x{height}, not the 64x32 layout Java's and Bedrock's armor "
                      "geometry share (another size isn't checked to map the same way)")
    return data, ""


def _equipment_texture(mod: SourceMod, look: ArmorLook, kind: str) -> tuple[str | None, str]:
    """A 1.21.2+ equipment asset -> the jar path of the texture it draws for ``kind``."""
    layer = "humanoid_leggings" if kind == "LEGGINGS" else "humanoid"
    for folder in ("equipment", "models/equipment"):
        rel = f"assets/{look.namespace}/{folder}/{look.path}.json"
        if (mod.root / rel).is_file():
            break
    else:
        return None, f"its equipment asset {look.namespace}:{look.path} isn't in the jar"
    try:
        body = json.loads((mod.root / rel).read_text())
    except (OSError, ValueError):
        return None, f"its equipment asset {rel} isn't valid JSON"
    layers = ((body.get("layers") if isinstance(body, dict) else None) or {}).get(layer)
    if not isinstance(layers, list) or not layers:
        return None, f"its equipment asset {rel} has no {layer} layer, so Java draws nothing in that slot"
    if len(layers) != 1:
        return None, f"its equipment asset {rel} has {len(layers)} {layer} layers; one attachable maps one texture"
    entry = layers[0]
    texture = entry.get("texture") if isinstance(entry, dict) else None
    if not isinstance(texture, str):
        return None, f"its equipment asset {rel} names no {layer} texture"
    if "dyeable" in entry:
        return None, f"its equipment asset {rel} tints the {layer} layer (dyeable), which isn't carried yet"
    ns, _, path = texture.rpartition(":")
    return f"assets/{ns or 'minecraft'}/textures/entity/equipment/{layer}/{path}.png", rel


def _layer_texture(look: ArmorLook, kind: str) -> str:
    layer = 2 if kind == "LEGGINGS" else 1
    return f"assets/{look.namespace}/textures/models/armor/{look.path}_layer_{layer}{look.suffix}.png"


def attachable(mod: SourceMod, ident: str, piece: ArmorPiece) -> tuple[dict, str, str]:
    """(``{pack path: body}`` for the piece's worn look, the jar texture it
    wears, how its path was found), or ({}, "", why not)."""
    look = piece.look
    how = ""
    if look is None and piece.material:
        # DEFAULT: the material constant's name, used only when the file is there.
        look = ArmorLook("layer", mod.namespace, piece.material.lower(), "", "DEFAULT")
        if not (mod.root / _layer_texture(look, piece.kind)).is_file():
            return {}, "", ("no reader could say which texture it wears, and the DEFAULT name "
                            f"{_layer_texture(look, piece.kind)} isn't in the jar")
        how = (f"DEFAULT texture name {piece.material.lower()}_layer_N.png (material {piece.material}; no reader "
               "could say which texture it wears)")
    if not isinstance(look, ArmorLook):
        return {}, "", look if isinstance(look, str) else "no reader could say which texture it wears"
    if look.kind == "equipment":
        rel, where = _equipment_texture(mod, look, piece.kind)
        if rel is None:
            return {}, "", where
        how = f"{look.source}; {where}; {EQUIPMENT_SOURCE}"
    else:
        rel = _layer_texture(look, piece.kind)
        how = how or look.source
    data, why = _png(mod, rel)
    if data is None:
        return {}, "", why
    geometry, visible = ATTACHABLE_SLOTS[piece.kind]
    name = ident.split(":", 1)[1]
    namespace, _, inner = rel[len("assets/"):-len(".png")].partition("/")
    for lane in ("textures/models/armor/", "textures/entity/equipment/"):
        inner = inner[len(lane):] if inner.startswith(lane) else inner
    texture = f"{ARMOR_TEXTURE_DIR}/{namespace}/{inner}"
    return {
        f"attachables/{name}.json": {
            "format_version": ATTACHABLE_FORMAT,
            "minecraft:attachable": {
                "description": {
                    "identifier": ident,
                    "materials": {"default": "armor", "enchanted": "armor_enchanted"},
                    "textures": {"default": texture, "enchanted": "textures/misc/enchanted_actor_glint"},
                    "geometry": {"default": geometry},
                    "scripts": {"parent_setup": f"variable.{visible} = 0.0;"},
                    "render_controllers": ["controller.render.armor"],
                },
            },
        },
        f"{texture}.png": data,
    }, rel, how


def _shown(names: list[str], limit: int = 6) -> str:
    return ", ".join(names[:limit]) + (f" and {len(names) - limit} more" if len(names) > limit else "")


def convert(mod: SourceMod, files: dict, tags: TagResolver | None = None) -> ConversionResult:
    """Make this namespace's armor items wearable, from what the adapters read."""
    result = ConversionResult()
    prefix = f"{mod.namespace}:"
    items: dict[str, tuple[str, dict]] = {}
    for path, body in files.items():
        if not (path.startswith("items/") and path.endswith(".json")) or not isinstance(body, dict):
            continue
        item = body.get("minecraft:item")
        ident = ((item or {}).get("description") or {}).get("identifier") if isinstance(item, dict) else None
        if isinstance(ident, str) and ident.startswith(prefix):
            items[ident[len(prefix):]] = (path, body)
    if not items:
        return result
    from ..adapters import item_armors

    answers = item_armors(mod, frozenset(items))
    marked = java_armor(mod, tags if tags is not None else TagResolver(mod))
    worn: dict[str, list[str]] = {}
    dropped, extras = [], {}
    drawn: dict[str, list[str]] = {}
    undrawn: dict[str, list[str]] = {}
    defaults: list[str] = []
    held = {((b.get("minecraft:attachable") or {}).get("description") or {}).get("identifier")
            for p, b in files.items() if p.startswith("attachables/") and isinstance(b, dict)}
    for name in sorted(items):
        path, body = items[name]
        ident = prefix + name
        answer = answers.get(name)
        if valid(answer):
            result.files[path] = wear(body, answer)
            worn.setdefault(answer.source, []).append(
                f"{ident} {answer.kind.lower()} protection {answer.protection}, durability {answer.durability}, "
                f"enchantability {answer.enchantability}")
            lost = []
            if answer.toughness:
                lost.append(f"toughness {answer.toughness:g}")
            if answer.knockback:
                lost.append(f"knockback resistance {answer.knockback:g}")
            if lost:
                dropped.append(f"{ident} ({', '.join(lost)})")
            for what in answer.not_carried:
                extras.setdefault(what, []).append(ident)
            if ident in held:
                undrawn.setdefault("it already has an attachable for its held 3D model, and an item has one "
                                   "attachable", []).append(ident)
                continue
            built, texture, how = attachable(mod, ident, answer)
            if not built:
                undrawn.setdefault(how, []).append(ident)
                continue
            result.files.update(built)
            result.claim(mod, mod.root / texture)
            drawn.setdefault(how, []).append(f"{ident} ({texture})")
            if how.startswith("DEFAULT"):
                defaults.append(ident)
            continue
        if ident not in marked and not isinstance(answer, str):
            continue
        why = answer if isinstance(answer, str) else (
            "no reader for this mod's armor could state its slot, armor points, toughness, knockback "
            "resistance, durability and enchantability from the mod's code")
        where = ", ".join(f"#{t}" for t in marked.get(ident, [])) or "its code builds it as an ArmorItem"
        model = f"assets/{mod.namespace}/models/item/{name}.json"
        source = model if (mod.root / model).is_file() else path
        result.unhandled.append(Unhandled(source, RESIDUE_KIND, (
            f"{ident} is armor in Java ({where}), but {why}; it converts as a plain item that can't be worn, "
            "since Bedrock's minecraft:wearable takes a slot and protection and no stat is invented (#274, #87)")))
    if worn:
        # The vanilla code every citation leans on is named once, not per source.
        vanilla = sorted({text for text in VANILLA_SOURCES.values() if any(text in source for source in worn)})
        parts = []
        for source, pieces in sorted(worn.items()):
            for text in vanilla:
                source = source.replace("; " + text, "").replace(text, "")
            parts.append(f"{'; '.join(pieces)} ({source.strip('; ')})")
        count = sum(len(p) for p in worn.values())
        result.notes.append(
            f"{count} armor item(s) carry minecraft:wearable, minecraft:durability, minecraft:enchantable and a "
            f"stack of one, from the numbers the mod's code gives them (#274; Bedrock: {BEDROCK_SOURCES}; "
            f"vanilla: {'; '.join(vanilla)}): "
            + " | ".join(parts) + ".")
    if drawn:
        count = sum(len(v) for v in drawn.values())
        result.notes.append(
            f"{count} armor item(s) get a worn look: an attachable on Bedrock's vanilla armor geometry wearing "
            f"the mod's own armor layer texture, copied unchanged (#274; {ATTACHABLE_SOURCES}; UV layout: "
            f"{UV_SOURCES}): " + " | ".join(f"{'; '.join(v)} ({k})" for k, v in sorted(drawn.items()))
            + ". Unverified in game (the server doesn't draw). Not matched: Java's armor trims, and the 0.01-0.1 "
            "differences in how far Java and Bedrock inflate the armor boxes.")
    if defaults:
        result.notes.append(
            f"DEFAULT armor texture name used for {len(defaults)} item(s) ({_shown(defaults)}): no reader could "
            "say which texture they wear, so <material>_layer_N.png was taken because that file is in the jar "
            "(#274).")
    for why, idents in sorted(undrawn.items()):
        result.notes.append(
            f"{len(idents)} wearable armor item(s) ({_shown(idents)}) have no worn look on Bedrock (no attachable, "
            f"so nothing is drawn on the wearer): {why} (#274).")
    if dropped:
        result.notes.append(
            "Java armor toughness and knockback resistance have no Bedrock item component, so they aren't "
            f"written (the armor points are): {_shown(dropped, 12)} (#274).")
    for what, idents in sorted(extras.items()):
        result.notes.append(f"Not carried on {len(idents)} armor item(s) ({_shown(idents)}): {what} (#274).")
    return result
