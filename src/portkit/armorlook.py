"""Where a mod armor piece's worn texture comes from, read from the mod's code (#274).

Java draws worn armor with the humanoid armor model and one texture per layer,
and which texture is code, not data. These readers find it in the jar's
bytecode the same way for every mod; each returns an
:class:`portkit.itemcode.ArmorLook`, a reason the piece can't be drawn from its
textures (it has its own model, or a tint), or None when the shape isn't one
they recognize. Vanilla's side, read from Mojang's client jars with client.txt
(:data:`VANILLA_LOOK_SOURCES`):

* 1.20.1 ``HumanoidArmorLayer#getArmorLocation``: ``"textures/models/armor/" +
  material.getName() + "_layer_" + (inner ? 2 : 1) + (suffix == null ? "" :
  "_" + suffix) + ".png"``, read as a ``ResourceLocation`` (so a bare name is
  in ``minecraft``); ``usesInnerModel(slot)`` is ``slot == LEGS``.
  Forge 1.20.1 replaces it with ``getArmorResource``, which splits a
  ``namespace:`` off the material name (default ``minecraft``) and then asks
  the item's ``getArmorTexture`` (``ForgeHooksClient.getArmorTexture``: the
  item's answer, when not null, wins).
* 1.21.1 ``ArmorMaterial.Layer(ResourceLocation)`` is ``Layer(id, "", false)``
  and ``texture(inner)`` is ``id.withPath("textures/models/armor/" + path +
  "_layer_" + (inner ? 2 : 1) + suffix + ".png")``; ``HumanoidArmorLayer``
  draws every layer of the material, tinting the dyeable ones.

Mod loaders let a mod draw armor its own way, and such a piece is not read:
Fabric API's ``ArmorRenderer.register`` (its ``ArmorFeatureRendererMixin``
cancels the vanilla draw for a registered item), Forge's
``IClientItemExtensions#getHumanoidArmorModel`` / ``getGenericArmorModel``
handed over in ``Item#initializeClient``, and a ``getArmorTexture`` override
that isn't the plain ``namespace:textures/models/armor/<path>_layer_N.png``
format.
"""
from __future__ import annotations

from .bytecode import ClassIndex, Indy, instructions
from .itemcode import (
    RETURNED, ArmorLook, Call, New, Static, _per_constant, _run, arg_types, static_values,
)

RESOURCE_LOCATION = "net/minecraft/resources/ResourceLocation"
LAYER = "net/minecraft/world/item/ArmorMaterial$Layer"
LAYER_1 = f"(L{RESOURCE_LOCATION};)V"
LAYER_3 = f"(L{RESOURCE_LOCATION};Ljava/lang/String;Z)V"
EQUIPMENT_SLOT = "net/minecraft/world/entity/EquipmentSlot"
FABRIC_ARMOR_RENDERER = "net/fabricmc/fabric/api/client/rendering/v1/ArmorRenderer"
CLIENT_EXTENSIONS = (
    "net/minecraftforge/client/extensions/common/IClientItemExtensions",
    "net/neoforged/neoforge/client/extensions/common/IClientItemExtensions",
)
# IClientItemExtensions methods that hand the armor layer a model of the mod's own.
CLIENT_MODEL_METHODS = frozenset({"getHumanoidArmorModel", "getGenericArmorModel"})
# The one getArmorTexture body read: Forge's own format on a ResourceLocation field.
FORGE_TEXTURE_FORMAT = "%s:textures/models/armor/%s_layer_%d%s.png"

VANILLA_LOOK_SOURCES = {
    "layer_1_20": ("Minecraft 1.20.1 HumanoidArmorLayer#getArmorLocation(ArmorItem, inner, suffix) = "
                   "\"textures/models/armor/\" + material.getName() + \"_layer_\" + (inner ? 2 : 1) + suffix + "
                   "\".png\", usesInnerModel(slot) = slot == LEGS (client jar sha1 "
                   "0c3ec587af28e5a785c0b4a7b8a30f9a8f78f838, Mojang client.txt)"),
    "forge_1_20": ("Forge 1.20.1 @d13dd327 HumanoidArmorLayer.java.patch getArmorResource: "
                   "\"%s:textures/models/armor/%s_layer_%d%s.png\" from material.getName() split at ':' "
                   "(default minecraft), then ForgeHooksClient.getArmorTexture: the item's getArmorTexture "
                   "wins when not null"),
    "layer_1_21": ("Minecraft 1.21.1 ArmorMaterial.Layer(ResourceLocation) = Layer(id, \"\", false), "
                   "texture(inner) = id.withPath(\"textures/models/armor/\" + path + \"_layer_\" + (inner ? 2 : 1) "
                   "+ suffix + \".png\"); HumanoidArmorLayer draws every layer, usesInnerModel(slot) = "
                   "slot == LEGS, dyeable layers tinted (client jar sha1 "
                   "30c73b1c5da787909b2f73340419fdf13b9def88, Mojang client.txt)"),
    "fabric_renderer": ("Fabric API 1.21.1 @83c07162 ArmorFeatureRendererMixin#renderArmor: an item with a "
                        "registered ArmorRenderer is drawn by it and the vanilla armor draw is cancelled"),
}


def _modded(owner: str) -> bool:
    return not owner.startswith(("net/minecraft/", "java/", "com/mojang/", "net/fabricmc/", "net/minecraftforge/",
                                 "net/neoforged/"))


def _string_static(index: ClassIndex, value):
    if isinstance(value, Static) and _modded(value.owner):
        cf = index.get(value.owner)
        held = static_values(cf).get(value.name) if cf else None
        if isinstance(held, str):
            return held
    return value


def inline(index: ClassIndex, value, _depth: int = 0):
    """``value`` with each call to a mod's own static method (a helper like
    ``RegistryHelper.id("kyber")``) replaced by what its branch-free body
    returns, and a mod's string constants filled in; anything else unchanged."""
    if _depth > 6:
        return value
    if isinstance(value, Static):
        return _string_static(index, value)
    if isinstance(value, New):
        return New(value.cls, value.desc, [inline(index, a, _depth + 1) for a in value.args])
    if not isinstance(value, Call):
        return value
    args = [inline(index, a, _depth + 1) for a in value.args]
    if value.receiver is None and _modded(value.owner):
        cf = index.get(value.owner)
        methods = [m for m in (cf.methods if cf else ()) if m.name == value.name and m.access & 0x0008
                   and len(arg_types(m.desc)) == len(args)]
        if len(methods) == 1:
            found, _ = _run(cf, methods[0], args, lambda *a: None)
            if found is not None and found is not RETURNED:
                return inline(index, found, _depth + 1)
    return Call(value.owner, value.name, args, value.receiver)


def resource_location(value) -> tuple[str, str] | None:
    """A ``ResourceLocation`` built from constants -> (namespace, path)."""
    def split(text):
        if not isinstance(text, str):
            return None
        ns, _, path = text.rpartition(":")
        return (ns or "minecraft", path) if path else None

    if isinstance(value, Call) and value.owner == RESOURCE_LOCATION and value.receiver is None:
        if value.name in ("fromNamespaceAndPath", "tryBuild") and len(value.args) == 2 \
                and all(isinstance(a, str) for a in value.args):
            return value.args[0], value.args[1]
        if value.name == "withDefaultNamespace" and len(value.args) == 1 and isinstance(value.args[0], str):
            return "minecraft", value.args[0]
        if value.name in ("parse", "tryParse", "of") and len(value.args) == 1:
            return split(value.args[0])
    if isinstance(value, New) and value.cls == RESOURCE_LOCATION:
        if len(value.args) == 2 and all(isinstance(a, str) for a in value.args):
            return value.args[0], value.args[1]
        if len(value.args) == 1:
            return split(value.args[0])
    return None


def material_layers(index: ClassIndex, layers) -> list[tuple[str, str, str, bool]] | str | None:
    """A 1.21.1 ``ArmorMaterial`` record's ``layers`` argument -> each layer's
    (namespace, path, suffix, dyeable), or None when it can't be read."""
    value = inline(index, layers)
    if not isinstance(value, Call) or value.owner != "java/util/List" or value.name != "of":
        return None
    out = []
    for item in value.args:
        if not isinstance(item, New) or item.cls != LAYER:
            return None
        where = resource_location(item.args[0]) if item.args else None
        if where is None:
            return None
        if item.desc == LAYER_1 and len(item.args) == 1:
            out.append((*where, "", False))
        elif item.desc == LAYER_3 and len(item.args) == 3 and isinstance(item.args[1], str) \
                and item.args[2] in (0, 1):
            out.append((*where, item.args[1], bool(item.args[2])))
        else:
            return None
    return out


def layers_look(layers, source: str) -> ArmorLook | str | None:
    """:func:`material_layers`' answer -> the piece's look, or why it isn't one texture."""
    if not isinstance(layers, list):
        return layers
    if len(layers) != 1:
        return (f"its material has {len(layers)} texture layers, drawn on top of each other in Java; one "
                "Bedrock armor attachable maps one texture")
    namespace, path, suffix, dyeable = layers[0]
    if dyeable:
        return "its armor layer is dyeable (tinted by the item's dye colour in Java), which isn't carried yet"
    return ArmorLook("layer", namespace, path, suffix, f"{source}; {VANILLA_LOOK_SOURCES['layer_1_21']}")


def material_names(index: ClassIndex, owner: str) -> dict[str, str]:
    """A 1.20-style ``ArmorMaterial`` enum constant -> what ``getName()``
    returns for it, when that is ``return this.field`` set from a constructor
    parameter, or a constant."""
    cf = index.get(owner)
    method = cf.method("getName", "()Ljava/lang/String;") if cf else None
    if method is None or method.code is None:
        return {}
    ops = instructions(cf, method.code)
    if [i.name for i in ops] == ["aload_0", "getfield", "areturn"] and ops[1].arg.owner == cf.name:
        found = _per_constant(cf, ops[1].arg.name)
    elif len(ops) == 2 and ops[0].op in (0x12, 0x13) and ops[1].name == "areturn":
        found = {k: ops[0].arg for k, v in static_values(cf).items() if isinstance(v, New) and v.cls == cf.name}
    else:
        return {}
    return {k: v for k, v in found.items() if isinstance(v, str)}


def name_look(name: str, forge: bool, source: str) -> ArmorLook | str:
    """A 1.20 material name -> its texture (Forge's or vanilla's reading)."""
    ns, colon, path = name.partition(":")
    if not colon:
        ns, path = "minecraft", name
    elif not forge:
        return (f"its material name {name!r} has a namespace, which vanilla 1.20's armor texture path "
                "can't parse")
    key = "forge_1_20" if forge else "layer_1_20"
    return ArmorLook("layer", ns, path, "", f"{source}; {VANILLA_LOOK_SOURCES[key]}")


def constructor_fields(index: ClassIndex, cls: str, desc: str, args: list, _depth: int = 0) -> dict | None:
    """The fields ``new cls(args)`` sets on itself, its mod superclasses'
    constructors included (theirs first), or None when a constructor can't be
    followed."""
    if not _modded(cls) or _depth > 8:
        return {}
    cf = index.get(cls)
    method = cf.method("<init>", desc) if cf else None
    if method is None:
        return None
    fields: dict = {}
    failed = []

    def on_init(owner, init_desc, call_args):
        if owner in (cf.super_name, cls):
            got = constructor_fields(index, owner, init_desc, call_args, _depth + 1)
            if got is None:
                failed.append(owner)
            else:
                fields.update(got)
        return None

    value, _ = _run(cf, method, list(args), on_init, fields=fields, past_init=True)
    if value is not RETURNED or failed:
        return None
    return fields


def _chain(index: ClassIndex, owner: str):
    seen, cls = set(), owner
    while cls and _modded(cls) and cls not in seen:
        seen.add(cls)
        cf = index.get(cls)
        if cf is None:
            yield cls, None
            return
        yield cls, cf
        cls = cf.super_name


def _forge_format_field(cf, method) -> str | None:
    """The ResourceLocation field a getArmorTexture body formats with Forge's
    own ``%s:textures/models/armor/%s_layer_%d%s.png`` (namespace, path,
    LEGS ? 2 : 1, the type suffix), else None."""
    ops = instructions(cf, method.code)
    names = [i.name for i in ops]
    consts = [i.arg for i in ops if i.op in (0x12, 0x13)]
    fields = [i.arg for i in ops if i.op == 0xB4]
    calls = [(i.arg.owner, i.arg.name) for i in ops if i.op in (0xB6, 0xB8, 0xB9)]
    if FORGE_TEXTURE_FORMAT not in consts or len(fields) != 2 or fields[0] != fields[1] \
            or fields[0].desc != f"L{RESOURCE_LOCATION};":
        return None
    if calls[:2] != [(RESOURCE_LOCATION, "getNamespace"), (RESOURCE_LOCATION, "getPath")]:
        return None
    legs = [i for i in ops if i.op == 0xB2 and i.arg.owner == EQUIPMENT_SLOT]
    if [i.arg.name for i in legs] != ["LEGS"] or "if_acmpne" not in names or "_%s" not in consts:
        return None
    return fields[0].name


def forge_look(index: ClassIndex, cls: str, desc: str, args: list, material: Static | None) -> ArmorLook | str | None:
    """A Forge 1.20.1 armor piece built as ``new cls(args)`` (constructor
    ``desc``) on the 1.20 material enum constant ``material`` -> its look."""
    override = None
    for owner, cf in _chain(index, cls):
        if cf is None:
            return (f"its class chain reaches {owner.rsplit('/', 1)[-1]}, which isn't in the jar, so whether it "
                    "draws the piece its own way can't be read")
        for method in cf.methods:
            if method.name == "getArmorTexture" and method.code is not None and override is None:
                override = (cf, method)
            if method.name == "initializeClient" and method.code is not None:
                why = _client_model(index, cf, method)
                if why:
                    return why
    if override is not None:
        cf, method = override
        name = cf.name.rsplit("/", 1)[-1]
        field = _forge_format_field(cf, method)
        if field is None:
            return f"its class {name} decides its armor texture in code (getArmorTexture)"
        fields = constructor_fields(index, cls, desc, args)
        where = resource_location(inline(index, (fields or {}).get(field)))
        if where is None:
            return (f"its class {name} formats its armor texture from this.{field}, whose value the constructor "
                    "chain doesn't give as a constant")
        return ArmorLook("layer", where[0], where[1], "", (
            f"{name}.getArmorTexture formats \"{FORGE_TEXTURE_FORMAT}\" with this.{field} = "
            f"{where[0]}:{where[1]} (set by the constructor chain of {cls.rsplit('/', 1)[-1]}); "
            f"{VANILLA_LOOK_SOURCES['forge_1_20']}"))
    if material is None:
        return None
    name = material_names(index, material.owner).get(material.name)
    if name is None:
        return None
    return name_look(name, True, f"{material.owner.rsplit('/', 1)[-1]}.{material.name}.getName() = {name!r}")


def _client_model(index: ClassIndex, cf, method) -> str | None:
    """Why an ``initializeClient`` body hands the armor layer a model of its
    own (or might), else None."""
    name = cf.name.rsplit("/", 1)[-1]
    for insn in instructions(cf, method.code):
        if insn.op == 0xBB:
            made = index.get(insn.arg[1])
            if made is None:
                if insn.arg[1].startswith(("java/", "net/minecraft/")):
                    continue
                return f"its class {name} hands Forge client extensions it can't read ({insn.arg[1]})"
            own = {m.name for m in made.methods} & CLIENT_MODEL_METHODS
            if own:
                return (f"its class {name} draws it with a model of its own "
                        f"({made.name.rsplit('/', 1)[-1]}.{', '.join(sorted(own))})")
        elif insn.op == 0xBA and isinstance(insn.arg, Indy) \
                and any(insn.arg.desc.endswith(f")L{c};") for c in CLIENT_EXTENSIONS):
            return f"its class {name} hands Forge client extensions as a lambda, which isn't read"
    return None


def fabric_renderers(index: ClassIndex) -> tuple[frozenset[str], frozenset[Static], bool]:
    """What the jar registers a Fabric ``ArmorRenderer`` for: the classes its
    item filters test with ``instanceof``, the item statics it names, and
    whether every registration was read that way."""
    classes: set[str] = set()
    statics: set[Static] = set()
    understood = True
    for name in index.names():
        cf = index.get(name)
        if cf is None:
            continue
        for method in cf.methods:
            if method.code is None:
                continue
            ops = instructions(cf, method.code)
            if not any(i.op == 0xB8 and i.arg.owner == FABRIC_ARMOR_RENDERER and i.arg.name == "register"
                       for i in ops):
                continue
            found_here = False
            bodies = [(cf, method)]
            for insn in ops:
                if insn.op == 0xBA and isinstance(insn.arg, Indy):
                    for arg in insn.arg.args:
                        ref = getattr(arg, "ref", None)
                        if ref is not None and ref.owner == cf.name:
                            target = cf.method(ref.name, ref.desc)
                            if target is not None and target.code is not None:
                                bodies.append((cf, target))
            for owner, body in bodies:
                for insn in instructions(owner, body.code):
                    if insn.op == 0xC1 and _modded(insn.arg[1]):  # instanceof
                        classes.add(insn.arg[1])
                        found_here = True
                    elif insn.op == 0xB2 and _modded(insn.arg.owner) and body is method:
                        statics.add(Static(insn.arg.owner, insn.arg.name))
                        found_here = True
            understood = understood and found_here
    return frozenset(classes), frozenset(statics), understood


def subclass_of(index: ClassIndex, cls: str, parents: frozenset[str]) -> str | None:
    """The first of ``parents`` that ``cls`` is or extends."""
    for owner, _ in _chain(index, cls):
        if owner in parents:
            return owner
    return None
