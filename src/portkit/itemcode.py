"""What an item's compiled code says about its durability (#268).

Bedrock's smithing table takes only armor and tools as a ``recipe_smithing_transform``
base, and an item is a tool or armor to it when it has ``minecraft:durability``
(#263). Java keeps that number in code, so this module reads the pieces of it
that are plain data in a class file, the same way for every mod:

* :func:`static_values` runs a class's static initializer on a tiny stack
  machine and returns what each static field was set to: a constant, a vanilla
  or mod static (:class:`Static`), an object built with ``new`` and the
  arguments its constructor got (:class:`New`), an array, or a call and its
  arguments (:class:`Call`). An enum's constants are its ``New`` values. It stops
  at the first branch, and anything it can't follow is :data:`UNKNOWN`.
* :func:`tier_uses` reads a tool tier's ``getUses()`` (``net.minecraft.world.item.Tier``,
  Mojang names, so a Forge SRG or Fabric intermediary jar read through its
  mapping, #235) for each tier constant of a mod's tier enum: the field the
  getter returns, the constructor parameter that sets it, and the value each
  constant passes.
* :func:`armor_type_durability` reads a 1.20-style ``ArmorMaterial`` enum's
  ``getDurabilityForType(ArmorItem.Type)``, when it is ``ARRAY[type.ordinal()]
  * this.field`` (the shape vanilla's own ``ArmorMaterials`` has), per constant
  and armor piece.
* :func:`registration_lambda` and :func:`constructed` follow a registration
  that names an item by a string and builds it in a lambda (Registrate's
  ``item("name", Factory::new)`` and the like): the lambda's method, then the
  class it constructs and the statics passed to it.

How the vanilla item turns those numbers into its durability is vanilla code,
read from Mojang's client jars with their mappings (client.txt):

* 1.21.1 ``TieredItem(Tier, Properties)`` calls ``properties.durability(tier.getUses())``
  (client jar sha1 30c73b1c5da787909b2f73340419fdf13b9def88), so a tool built on
  a tier has exactly the tier's uses;
* 1.20.1 ``ArmorItem(ArmorMaterial, Type, Properties)`` calls
  ``properties.defaultDurability(material.getDurabilityForType(type))`` (client
  jar sha1 0c3ec587af28e5a785c0b4a7b8a30f9a8f78f838), and ``ArmorItem.Type``'s
  constants are, in order, HELMET, CHESTPLATE, LEGGINGS, BOOTS;
* 1.21.1 ``ArmorItem``'s constructor writes no durability: the item's
  ``Item.Properties#durability`` is the whole of it.

Which item is built on which tier or material is mod code an adapter reads
(the registration differs per mod); the numbers come from here. Nothing is
guessed: every reader returns nothing for a shape it doesn't recognize.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .bytecode import ClassFile, ClassIndex, Handle, Indy, Ref, instructions

TIER = "net/minecraft/world/item/Tier"
ARMOR_MATERIAL = "net/minecraft/world/item/ArmorMaterial"
ARMOR_TYPE = "net/minecraft/world/item/ArmorItem$Type"
PROPERTIES = "net/minecraft/world/item/Item$Properties"
# ArmorItem.Type's constants in ordinal order (1.20.1 client jar, see above).
ARMOR_TYPE_ORDER = ("HELMET", "CHESTPLATE", "LEGGINGS", "BOOTS")
# Item.Properties calls that set an item's durability (Mojang names).
DURABILITY_CALLS = frozenset({"durability", "defaultDurability"})
# Methods an item class may override to decide its durability in code
# (Forge/NeoForge IForgeItem/IItemExtension#getMaxDamage, #isDamageable;
# Item#canBeDepleted): an item class declaring one is not read.
DURABILITY_OVERRIDES = frozenset({"getMaxDamage", "isDamageable", "canBeDepleted"})

VANILLA_SOURCES = {
    "tiered_item": ("Minecraft 1.21.1 net.minecraft.world.item.TieredItem#<init>(Tier, Item.Properties): "
                    "properties.durability(tier.getUses()) (client jar sha1 "
                    "30c73b1c5da787909b2f73340419fdf13b9def88, Mojang client.txt)"),
    "armor_item_1_20": ("Minecraft 1.20.1 net.minecraft.world.item.ArmorItem#<init>(ArmorMaterial, "
                        "ArmorItem.Type, Item.Properties): properties.defaultDurability("
                        "material.getDurabilityForType(type)); ArmorItem.Type order HELMET, CHESTPLATE, "
                        "LEGGINGS, BOOTS (client jar sha1 0c3ec587af28e5a785c0b4a7b8a30f9a8f78f838, "
                        "Mojang client.txt)"),
    "armor_item_1_21": ("Minecraft 1.21.1 net.minecraft.world.item.ArmorItem#<init>: no durability of its "
                        "own, the item's Item.Properties#durability is it (client jar sha1 "
                        "30c73b1c5da787909b2f73340419fdf13b9def88, Mojang client.txt)"),
}


class _Unknown:
    def __repr__(self) -> str:
        return "UNKNOWN"


UNKNOWN = _Unknown()


@dataclass(frozen=True)
class Static:
    """A ``getstatic`` read: another class's (or this one's) static field."""

    owner: str
    name: str


@dataclass
class New:
    """An object built with ``new``; ``args`` once its constructor ran."""

    cls: str
    desc: str | None = None
    args: list = field(default_factory=list)


@dataclass
class Call:
    """A static or instance call's result (``receiver`` is None for a static)."""

    owner: str
    name: str
    args: list
    receiver: object = None


@dataclass
class Array:
    items: list


def arg_types(desc: str) -> list[str]:
    """A method descriptor's parameter types (``(I[ILfoo;)V`` -> ``I``, ``[I``, ``Lfoo;``)."""
    out, i, inner = [], 0, desc[1:desc.index(")")]
    while i < len(inner):
        start = i
        while inner[i] == "[":
            i += 1
        if inner[i] == "L":
            i = inner.index(";", i)
        i += 1
        out.append(inner[start:i])
    return out


def _returns(desc: str) -> bool:
    return not desc.endswith(")V")


_ICONST = {0x02: -1, 0x03: 0, 0x04: 1, 0x05: 2, 0x06: 3, 0x07: 4, 0x08: 5}
_FCONST = {0x0B: 0.0, 0x0C: 1.0, 0x0D: 2.0, 0x09: 0, 0x0A: 1, 0x0E: 0.0, 0x0F: 1.0}
_STORES = {0x4F, 0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56}  # iastore .. sastore
_BRANCHES = {*range(0x99, 0xA9), 0xA9, 0xAA, 0xAB, 0xAC, 0xAD, 0xAE, 0xAF, 0xB0, 0xB1,
             0xBF, 0xC6, 0xC7, 0xC8}


def static_values(cf: ClassFile) -> dict[str, object]:
    """Each static field -> the value the class's static initializer gave it,
    up to its first branch, return or throw (see the module docstring)."""
    method = cf.method("<clinit>", "()V")
    out: dict[str, object] = {}
    if method is None or method.code is None:
        return out
    stack: list = []

    def pop(n: int = 1) -> list:
        if n == 0:
            return []
        if len(stack) < n:
            raise IndexError
        taken = stack[-n:]
        del stack[-n:]
        return taken

    try:
        for insn in instructions(cf, method.code):
            op = insn.op
            if op in _BRANCHES:
                break
            if op == 0x01:  # aconst_null
                stack.append(None)
            elif op in _ICONST:
                stack.append(_ICONST[op])
            elif op in _FCONST:
                stack.append(_FCONST[op])
            elif op in (0x10, 0x11):  # bipush, sipush
                stack.append(insn.arg)
            elif op in (0x12, 0x13, 0x14):  # ldc
                value = insn.arg
                stack.append(value if isinstance(value, (int, float, str)) else UNKNOWN)
            elif op == 0xB2:  # getstatic
                stack.append(Static(insn.arg.owner, insn.arg.name))
            elif op == 0xB3:  # putstatic
                (value,) = pop()
                if insn.arg.owner == cf.name:
                    out[insn.arg.name] = value
            elif op == 0xBB:  # new
                stack.append(New(insn.arg[1]))
            elif op == 0x59:  # dup
                stack.append(stack[-1])
            elif op == 0x57:  # pop
                pop()
            elif op == 0xC0:  # checkcast
                pass
            elif op in (0xBC, 0xBD):  # newarray, anewarray
                (count,) = pop()
                stack.append(Array([UNKNOWN] * count) if isinstance(count, int) and 0 <= count < 4096 else UNKNOWN)
            elif op in _STORES:
                array, index, value = pop(3)
                if isinstance(array, Array) and isinstance(index, int) and 0 <= index < len(array.items):
                    array.items[index] = value
            elif op in (0xB6, 0xB7, 0xB8, 0xB9):  # invokevirtual/special/static/interface
                ref = insn.arg
                args = pop(len(arg_types(ref.desc)))
                if op == 0xB7 and ref.name == "<init>":
                    (target,) = pop()
                    if isinstance(target, New):
                        target.desc, target.args = ref.desc, args
                    continue
                receiver = None if op == 0xB8 else pop()[0]
                if _returns(ref.desc):
                    stack.append(Call(ref.owner, ref.name, args, receiver))
            elif op == 0xBA:  # invokedynamic
                indy = insn.arg
                pop(len(arg_types(indy.desc)))
                stack.append(indy)
            else:
                break  # an instruction this machine doesn't model: stop here
    except (IndexError, ValueError):
        pass
    return out


def _getter_field(cf: ClassFile, name: str, desc: str) -> str | None:
    """The field ``name``'s body returns when it is ``return this.field`` (an int or float)."""
    method = cf.method(name, desc)
    if method is None or method.code is None:
        return None
    ops = instructions(cf, method.code)
    if len(ops) == 3 and ops[0].name == "aload_0" and ops[1].op == 0xB4 and ops[2].op in (0xAC, 0xAE) \
            and ops[1].arg.owner == cf.name:
        return ops[1].arg.name
    return None


def _ctor_param(cf: ClassFile, field_name: str) -> tuple[str, int] | None:
    """(constructor descriptor, parameter index) of the one constructor
    parameter stored straight into ``field_name`` (``this.f = param``)."""
    found = None
    for method in cf.methods:
        if method.name != "<init>" or method.code is None:
            continue
        types = arg_types(method.desc)
        slots, slot = {}, 1
        for index, t in enumerate(types):
            slots[slot] = index
            slot += 2 if t in ("J", "D") else 1
        ops = instructions(cf, method.code)
        for prev, load, put in zip(ops, ops[1:], ops[2:]):
            if put.op == 0xB5 and put.arg.owner == cf.name and put.arg.name == field_name \
                    and prev.name == "aload_0":
                local = _local(load)
                if local is None or local not in slots:
                    continue
                if found is not None and found != (method.desc, slots[local]):
                    return None  # two constructors set it: not one answer
                found = (method.desc, slots[local])
    return found


def _local(insn) -> int | None:
    """The local slot an ``iload``/``fload``/``aload`` family instruction reads."""
    op = insn.op
    if op in (0x15, 0x17, 0x19):  # iload, fload, aload <index>
        return insn.arg
    for first in (0x1A, 0x22, 0x2A):  # iload_0, fload_0, aload_0 .. _3
        if first <= op <= first + 3:
            return op - first
    return None


def _per_constant(cf: ClassFile, field_name: str) -> dict[str, object]:
    """Each static constant of ``cf`` built by its own constructor -> the
    argument that constructor stores in ``field_name``."""
    where = _ctor_param(cf, field_name)
    if where is None:
        return {}
    desc, index = where
    out = {}
    for name, value in static_values(cf).items():
        if isinstance(value, New) and value.cls == cf.name and value.desc == desc and index < len(value.args):
            out[name] = value.args[index]
    return out


def tier_uses(index: ClassIndex, owner: str) -> dict[str, int]:
    """Tier constant -> its ``getUses()``, for a mod class implementing
    ``Tier`` whose getter returns a field its constructor sets."""
    cf = index.get(owner)
    if cf is None or TIER not in cf.interfaces:
        return {}
    field_name = _getter_field(cf, "getUses", "()I")
    if field_name is None:
        return {}
    return {k: v for k, v in _per_constant(cf, field_name).items() if isinstance(v, int) and v > 0}


def armor_type_durability(index: ClassIndex, owner: str) -> dict[str, dict[str, int]]:
    """Material constant -> {armor type: durability} for a 1.20-style
    ``ArmorMaterial`` whose ``getDurabilityForType`` is
    ``ARRAY[type.ordinal()] * this.field``, with ARRAY a static int array."""
    cf = index.get(owner)
    if cf is None or ARMOR_MATERIAL not in cf.interfaces:
        return {}
    method = cf.method("getDurabilityForType", f"(L{ARMOR_TYPE};)I")
    if method is None or method.code is None:
        return {}
    ops = instructions(cf, method.code)
    shape = [i.name for i in ops]
    if shape != ["getstatic", "aload_1", "invokevirtual", "iaload", "aload_0", "getfield", "op_68", "ireturn"] \
            or ops[0].arg.owner != cf.name or ops[2].arg.name != "ordinal" or ops[5].arg.owner != cf.name:
        return {}
    array = static_values(cf).get(ops[0].arg.name)
    if not isinstance(array, Array) or len(array.items) != len(ARMOR_TYPE_ORDER) \
            or not all(isinstance(v, int) for v in array.items):
        return {}
    out = {}
    for name, factor in _per_constant(cf, ops[5].arg.name).items():
        if isinstance(factor, int) and factor > 0:
            out[name] = {t: base * factor for t, base in zip(ARMOR_TYPE_ORDER, array.items)}
    return out


def registration_lambda(cf: ClassFile, name: str, method: str = "<clinit>") -> str | None:
    """The lambda method that builds the entry a registration names ``name``
    (a ``ldc name`` followed by a ``LambdaMetafactory`` call site in ``method``):
    exactly one, or None."""
    m = cf.method(method)
    if m is None or m.code is None:
        return None
    found, armed = [], False
    for insn in instructions(cf, m.code):
        if insn.op in (0x12, 0x13) and insn.arg == name:
            armed = True
        elif armed and insn.op == 0xBA and isinstance(insn.arg, Indy):
            handles = [a for a in insn.arg.args if isinstance(a, Handle) and a.ref.owner == cf.name]
            if handles:
                found.append(handles[0].ref.name)
            armed = False
    return found[0] if len(found) == 1 else None


def constructed(cf: ClassFile, method: str) -> tuple[str, list[Static]] | None:
    """(class, statics passed) for a method that builds one object with
    ``new`` and returns it (a factory lambda): the statics read before its
    constructor call."""
    m = cf.method(method)
    if m is None or m.code is None:
        return None
    ops = instructions(cf, m.code)
    news = [i for i in ops if i.op == 0xBB]
    if len(news) != 1 or ops[-1].op != 0xB0:
        return None
    statics = [Static(i.arg.owner, i.arg.name) for i in ops if i.op == 0xB2]
    return news[0].arg[1], statics


def sets_durability(index: ClassIndex, owner: str, stop: str = "net/minecraft/") -> bool | None:
    """Whether ``owner`` or one of its mod superclasses calls
    ``Item.Properties#durability``/``defaultDurability`` anywhere or declares a
    method that decides durability in code (:data:`DURABILITY_OVERRIDES`)
    (True), does neither (False), or can't be read (None: a superclass
    missing from the jar that isn't Minecraft's)."""
    seen = set()
    cls = owner
    while cls and not cls.startswith(stop) and cls not in seen:
        seen.add(cls)
        cf = index.get(cls)
        if cf is None:
            return None
        for method in cf.methods:
            if method.name in DURABILITY_OVERRIDES:
                return True
            if method.code is None:
                continue
            for insn in instructions(cf, method.code):
                ref = insn.arg
                if isinstance(ref, Ref) and ref.owner == PROPERTIES and ref.name in DURABILITY_CALLS:
                    return True
        cls = cf.super_name
    return False


# --- armor (#274) ---------------------------------------------------------------
#
# What vanilla ArmorItem does with its material, read from Mojang's client jars
# with their mappings (client.txt):
#
# * 1.20.1 ``ArmorItem(ArmorMaterial, Type, Properties)`` sets
#   ``defense = material.getDefenseForType(type)``, ``toughness =
#   material.getToughness()``, ``knockbackResistance =
#   material.getKnockbackResistance()`` and the durability above, and its
#   ``getEnchantmentValue()`` is ``material.getEnchantmentValue()``. (Its armor
#   attribute modifiers add knockback resistance only for
#   ``ArmorMaterials.NETHERITE``.)
# * 1.21.1 ``ArmorItem(Holder<ArmorMaterial>, Type, Properties)``:
#   ``getDefense()`` is ``material.value().getDefense(type)``, read from the
#   record ``ArmorMaterial(Map<Type, Integer> defense, int enchantmentValue,
#   Holder equipSound, Supplier repairIngredient, List layers, float
#   toughness, float knockbackResistance)``, and ``getEnchantmentValue()`` is
#   ``material.value().enchantmentValue()``.

ARMOR_ITEM = "net/minecraft/world/item/ArmorItem"
HOLDER = "net/minecraft/core/Holder"
ARMOR_ITEM_1_20 = f"(L{ARMOR_MATERIAL};L{ARMOR_TYPE};L{PROPERTIES};)V"
ARMOR_ITEM_1_21 = f"(L{HOLDER};L{ARMOR_TYPE};L{PROPERTIES};)V"
ARMOR_MATERIAL_RECORD = "(Ljava/util/Map;ILnet/minecraft/core/Holder;Ljava/util/function/Supplier;Ljava/util/List;FF)V"
# Methods an armor item class may override to decide its armor numbers, slot or
# enchantability in code (vanilla ArmorItem/Item, Forge IForgeItem, NeoForge
# IItemExtension; Mojang names): an item class declaring one is not read.
ARMOR_OVERRIDES = DURABILITY_OVERRIDES | frozenset({
    "getDefense", "getToughness", "getDefaultAttributeModifiers", "getAttributeModifiers",
    "getEnchantmentValue", "isEnchantable", "getEquipmentSlot", "getMaterial", "getType",
})
# Item.Properties calls that set numbers an armor item's material would
# otherwise give (1.21.1 ``attributes`` replaces its modifiers; ``component``
# with a vanilla component type could set any of them; a mod's own component
# type is recorded as ``component <owner>.<field>`` instead).
ARMOR_PROPERTY_CALLS = DURABILITY_CALLS | frozenset({"attributes", "component"})

VANILLA_SOURCES.update({
    "armor_stats_1_20": ("Minecraft 1.20.1 net.minecraft.world.item.ArmorItem#<init>(ArmorMaterial, "
                         "ArmorItem.Type, Item.Properties): defense = material.getDefenseForType(type), "
                         "toughness = material.getToughness(), knockbackResistance = "
                         "material.getKnockbackResistance(); ArmorItem#getEnchantmentValue() = "
                         "material.getEnchantmentValue() (client jar sha1 "
                         "0c3ec587af28e5a785c0b4a7b8a30f9a8f78f838, Mojang client.txt)"),
    "armor_stats_1_21": ("Minecraft 1.21.1 net.minecraft.world.item.ArmorItem: getDefense() = "
                         "material.value().getDefense(type), getEnchantmentValue() = "
                         "material.value().enchantmentValue(), from the record ArmorMaterial(defense, "
                         "enchantmentValue, equipSound, repairIngredient, layers, toughness, "
                         "knockbackResistance) (client jar sha1 30c73b1c5da787909b2f73340419fdf13b9def88, "
                         "Mojang client.txt)"),
})


@dataclass(frozen=True)
class Param:
    """A value an enclosing method got as its parameter ``index``."""

    index: int


@dataclass
class ArmorStats:
    """What an armor material gives an ``ArmorItem``: defense per armor type,
    enchantability, toughness, knockback resistance and (1.20 materials)
    durability per armor type."""

    defense: dict[str, int]
    enchantability: int
    toughness: float
    knockback: float
    durability: dict[str, int] | None = None


def _int(value) -> int | None:
    if isinstance(value, Call) and value.owner == "java/lang/Integer" and value.name == "valueOf" \
            and len(value.args) == 1:
        value = value.args[0]
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _number(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _type_map(value) -> dict[str, int] | None:
    """``Map.of(ArmorItem.Type.HELMET, 3, ...)`` -> {"HELMET": 3, ...}."""
    if not isinstance(value, Call) or value.owner != "java/util/Map" or value.name != "of" or len(value.args) % 2:
        return None
    out = {}
    for key, amount in zip(value.args[::2], value.args[1::2]):
        number = _int(amount)
        if not isinstance(key, Static) or key.owner != ARMOR_TYPE or number is None:
            return None
        out[key.name] = number
    return out or None


def armor_material_record(value) -> ArmorStats | None:
    """A 1.21 ``new ArmorMaterial(Map.of(...), enchantability, sound, repair,
    layers, toughness, knockback)`` (a static initializer's value) -> its
    stats, when every number is a constant."""
    if not isinstance(value, New) or value.cls != ARMOR_MATERIAL or value.desc != ARMOR_MATERIAL_RECORD \
            or len(value.args) != 7:
        return None
    defense, ench = _type_map(value.args[0]), _int(value.args[1])
    tough, knock = _number(value.args[5]), _number(value.args[6])
    if defense is None or ench is None or tough is None or knock is None:
        return None
    return ArmorStats(defense, ench, tough, knock)


def _getter(cf: ClassFile, name: str, desc: str) -> tuple[str, object] | None:
    """("field", f) for ``return this.f``, ("const", v) for ``return v``."""
    field_name = _getter_field(cf, name, desc)
    if field_name is not None:
        return "field", field_name
    method = cf.method(name, desc)
    if method is None or method.code is None:
        return None
    ops = instructions(cf, method.code)
    if len(ops) == 2 and ops[1].op in (0xAC, 0xAE):
        if ops[0].op in _ICONST:
            return "const", _ICONST[ops[0].op]
        if ops[0].op in (0x0B, 0x0C, 0x0D):
            return "const", _FCONST[ops[0].op]
        if ops[0].op in (0x10, 0x11) or (ops[0].op in (0x12, 0x13) and isinstance(ops[0].arg, (int, float))):
            return "const", ops[0].arg
    return None


def _getter_values(cf: ClassFile, name: str, desc: str) -> dict[str, object] | None:
    """Material constant -> what ``name()`` returns for it."""
    found = _getter(cf, name, desc)
    if found is None:
        return None
    kind, what = found
    if kind == "const":
        return {k: what for k, v in static_values(cf).items() if isinstance(v, New) and v.cls == cf.name}
    return _per_constant(cf, what)


def armor_material_enum(index: ClassIndex, owner: str) -> dict[str, ArmorStats]:
    """Material constant -> its stats, for a 1.20-style ``ArmorMaterial`` enum
    whose getters return a constructor-set field (or a constant), with
    ``getDefenseForType`` = ``this.array[type.ordinal()]`` and durability as
    :func:`armor_type_durability` reads it."""
    cf = index.get(owner)
    if cf is None or ARMOR_MATERIAL not in cf.interfaces:
        return {}
    method = cf.method("getDefenseForType", f"(L{ARMOR_TYPE};)I")
    if method is None or method.code is None:
        return {}
    ops = instructions(cf, method.code)
    if [i.name for i in ops] != ["aload_0", "getfield", "aload_1", "invokevirtual", "iaload", "ireturn"] \
            or ops[1].arg.owner != cf.name or ops[3].arg.name != "ordinal":
        return {}
    defenses = _per_constant(cf, ops[1].arg.name)
    ench = _getter_values(cf, "getEnchantmentValue", "()I")
    tough = _getter_values(cf, "getToughness", "()F")
    knock = _getter_values(cf, "getKnockbackResistance", "()F")
    durability = armor_type_durability(index, owner)
    if ench is None or tough is None or knock is None:
        return {}
    out = {}
    for name, array in defenses.items():
        if not isinstance(array, Array) or len(array.items) != len(ARMOR_TYPE_ORDER) \
                or not all(_int(v) is not None for v in array.items):
            continue
        e, t, k = _int(ench.get(name)), _number(tough.get(name)), _number(knock.get(name))
        if e is None or t is None or k is None or name not in durability:
            continue
        out[name] = ArmorStats(dict(zip(ARMOR_TYPE_ORDER, array.items)), e, t, k, durability[name])
    return out


def resolve_static(index: ClassIndex, value):
    """A mod static holding another static (``TYPE = ArmorItem.Type.HELMET``)
    -> that static; anything else unchanged."""
    seen = set()
    while isinstance(value, Static) and not value.owner.startswith("net/minecraft/") and value not in seen:
        seen.add(value)
        cf = index.get(value.owner)
        held = static_values(cf).get(value.name) if cf else None
        if not isinstance(held, Static):
            break
        value = held
    return value


_THIS = Param(-1)


class _Returned:
    def __repr__(self) -> str:
        return "RETURNED"


RETURNED = _Returned()  # what :func:`_run` gives for a void method that ran to its ``return``


def _run(cf: ClassFile, method, args: list, on_init, fields: dict | None = None, past_init: bool = False):
    """Run ``method`` with ``args`` (no branches) on a small stack machine.

    ``on_init(owner, desc, call_args)`` is called for ``invokespecial <init>``
    on ``this`` and its answer returned. Otherwise the value of the first
    ``areturn`` is returned, or :data:`RETURNED` at a void ``return``. None
    when the body does something not modelled.
    Item.Properties calls are recorded in ``props`` (their receiver passes
    through; ``component`` with a mod's own component type is recorded as
    ``component <owner>.<field>``), and a call taking an ``ArmorMaterial`` and returning a
    ``Holder`` (a registry's ``wrapAsHolder``) is that material. An
    ``if_acmpeq``/``if_acmpne`` comparing two known statics is followed.
    With ``past_init`` the constructor body goes on after ``on_init`` (whose
    answer is dropped), and ``fields`` (when given) collects each
    ``this.f = value`` the body makes, by field name.
    """
    if method is None or method.code is None:
        return None, []
    types = arg_types(method.desc)
    is_static = bool(method.access & 0x0008)
    local: dict[int, object] = {}
    slot = 0
    if not is_static:
        local[0] = _THIS
        slot = 1
    for i, t in enumerate(types):
        local[slot] = args[i] if i < len(args) else UNKNOWN
        slot += 2 if t in ("J", "D") else 1
    stack: list = []
    props: list[str] = []
    code = instructions(cf, method.code)
    at = {insn.offset: i for i, insn in enumerate(code)}
    pc, steps = 0, 0
    try:
        while pc < len(code) and steps < 4096:
            insn = code[pc]
            pc += 1
            steps += 1
            op = insn.op
            if op in (0xA5, 0xA6):  # if_acmpeq / if_acmpne on two known statics: follow it
                right, left = stack.pop(), stack.pop()
                if not (isinstance(left, Static) and isinstance(right, Static)) or insn.arg not in at:
                    return None, props
                if (left == right) == (op == 0xA5):
                    pc = at[insn.arg]
                continue
            if op == 0xA7 and insn.arg in at:  # goto
                pc = at[insn.arg]
                continue
            if op in _BRANCHES and op not in (0xB0, 0xB1):
                return None, props
            loaded = _local(insn)
            if loaded is not None:
                stack.append(local.get(loaded, UNKNOWN))
            elif op in _ICONST:
                stack.append(_ICONST[op])
            elif op in _FCONST:
                stack.append(_FCONST[op])
            elif op in (0x10, 0x11):
                stack.append(insn.arg)
            elif op in (0x12, 0x13, 0x14):
                stack.append(insn.arg if isinstance(insn.arg, (int, float, str)) else UNKNOWN)
            elif op == 0x01:
                stack.append(None)
            elif op == 0xB2:
                stack.append(Static(insn.arg.owner, insn.arg.name))
            elif op == 0xBB:
                stack.append(New(insn.arg[1]))
            elif op == 0x59:
                stack.append(stack[-1])
            elif op == 0x57:
                stack.pop()
            elif op == 0xC0:
                pass
            elif op in (0xB6, 0xB7, 0xB8, 0xB9):
                ref = insn.arg
                n = len(arg_types(ref.desc))
                call_args = stack[len(stack) - n:] if n else []
                del stack[len(stack) - n:]
                if op == 0xB7 and ref.name == "<init>":
                    target = stack.pop()
                    if target is _THIS:
                        answer = on_init(ref.owner, ref.desc, call_args)
                        if not past_init:
                            return answer, props
                        continue
                    if isinstance(target, New):
                        target.desc, target.args = ref.desc, call_args
                    continue
                receiver = None if op == 0xB8 else stack.pop()
                if ref.owner == PROPERTIES:
                    tag = call_args[0] if call_args else None
                    if ref.name == "component" and isinstance(tag, Static) and not tag.owner.startswith("net/minecraft/"):
                        props.append(f"component {tag.owner}.{tag.name}")  # a mod's own data component
                    else:
                        props.append(ref.name)
                    stack.append(receiver)
                elif n == 1 and ref.desc.endswith(f")L{HOLDER};") and ref.desc.startswith(f"(L{ARMOR_MATERIAL};"):
                    stack.append(call_args[0])  # wraps a material in its registry holder
                elif _returns(ref.desc):
                    stack.append(Call(ref.owner, ref.name, call_args, receiver))
            elif op == 0xB0:  # areturn
                return stack.pop(), props
            elif op in (0xB5, 0xB1):  # putfield / return
                if op == 0xB5:
                    if fields is not None and len(stack) >= 2 and stack[-2] is _THIS:
                        fields[insn.arg.name] = stack[-1]
                    del stack[-2:]
                else:
                    return RETURNED, props
            else:
                return None, props
    except (IndexError, ValueError):
        return None, props
    return None, props


def factory(cf: ClassFile, method: str, desc: str | None = None) -> tuple[New | None, list[str]]:
    """(the object a factory method (a registration lambda) builds and returns,
    with its constructor arguments, or None; the Item.Properties calls it
    makes on the way). The method's own parameters are :class:`Param` values."""
    m = cf.method(method, desc)
    if m is None:
        return None, []
    n = len(arg_types(m.desc))
    value, props = _run(cf, m, [Param(i) for i in range(n)], lambda *a: None)
    return (value if isinstance(value, New) and value.desc is not None else None), props


def built_object(cf: ClassFile, method: str, desc: str | None = None) -> New | None:
    """The object a factory method builds (see :func:`factory`)."""
    return factory(cf, method, desc)[0]


def armor_item_args(index: ClassIndex, cls: str, desc: str, args: list,
                    _depth: int = 0) -> tuple[object, object, list[str], str] | None:
    """Follow ``new cls(args)`` (constructor ``desc``) up its constructor
    chain to vanilla ``ArmorItem``'s: ``(material, type, Item.Properties
    calls on the way, ArmorItem constructor desc)``, with mod statics that
    hold another static resolved. None when a constructor branches, builds
    on something other than ArmorItem, or isn't in the jar."""
    if _depth > 8:
        return None
    if cls == ARMOR_ITEM:
        if desc not in (ARMOR_ITEM_1_20, ARMOR_ITEM_1_21) or len(args) != 3:
            return None
        return resolve_static(index, args[0]), resolve_static(index, args[1]), [], desc
    if cls.startswith("net/minecraft/"):
        return None
    cf = index.get(cls)
    if cf is None:
        return None

    def on_init(owner, init_desc, call_args):
        if owner not in (cf.super_name, cls):
            return None
        return armor_item_args(index, owner, init_desc, call_args, _depth + 1)

    found, props = _run(cf, cf.method("<init>", desc), list(args), on_init)
    if not isinstance(found, tuple):
        return None
    material, kind, more, item_desc = found
    return material, kind, props + more, item_desc


def armor_overrides(index: ClassIndex, owner: str) -> list[str]:
    """The :data:`ARMOR_OVERRIDES` ``owner`` or a mod superclass declares."""
    found, seen, cls = set(), set(), owner
    while cls and not cls.startswith("net/minecraft/") and cls not in seen:
        seen.add(cls)
        cf = index.get(cls)
        if cf is None:
            break
        found |= {m.name for m in cf.methods if m.name in ARMOR_OVERRIDES}
        cls = cf.super_name
    return sorted(found)


def decides_armor_in_code(index: ClassIndex, owner: str) -> bool | None:
    """Whether ``owner`` or a mod superclass declares a method that decides
    its armor numbers, slot, enchantability or durability in code
    (:data:`ARMOR_OVERRIDES`) (True), none (False), or can't be read (None)."""
    seen = set()
    cls = owner
    while cls and not cls.startswith("net/minecraft/") and cls not in seen:
        seen.add(cls)
        cf = index.get(cls)
        if cf is None:
            return None
        if any(m.name in ARMOR_OVERRIDES for m in cf.methods):
            return True
        cls = cf.super_name
    return False


@dataclass(frozen=True)
class ArmorPiece:
    """One mod armor item as its code builds it (the ``item_armor`` adapter
    hook's answer): its ``ArmorItem.Type``, the numbers vanilla ``ArmorItem``
    gives it, and where each came from. ``not_carried`` lists what else the
    mod's code gives the piece that the converter doesn't write."""

    kind: str
    protection: int
    durability: int
    enchantability: int
    toughness: float
    knockback: float
    source: str
    not_carried: tuple[str, ...] = ()
    # How the piece is drawn when worn (:class:`ArmorLook`, read by
    # :mod:`portkit.armorlook`), a reason it can't be drawn from its textures
    # (a custom model, a tint), or None when no reader could tell.
    look: object = None
    # The material's constant name (``KYBER``), the hint a labelled DEFAULT
    # texture name may be tried with when ``look`` is None.
    material: str = ""


@dataclass(frozen=True)
class ArmorLook:
    """Where a worn armor piece's texture comes from, as the mod's code says.

    ``kind`` ``"layer"``: Java's ``<namespace>:textures/models/armor/<path>_layer_<1|2><suffix>.png``
    (layer 2 for leggings), the 1.20 material name / 1.21.1 ``ArmorMaterial.Layer``
    / Forge ``getArmorTexture`` scheme. ``kind`` ``"equipment"``: a 1.21.2+
    equipment asset ``<namespace>:<path>`` whose JSON names the textures.
    ``source`` cites where it was read."""

    kind: str
    namespace: str
    path: str
    suffix: str = ""
    source: str = ""


def armor_piece(stats: ArmorStats, kind, durability: int | None, source: str,
                not_carried: tuple[str, ...] = (), look: object = None, material: str = "") -> ArmorPiece | None:
    """The piece of armor type ``kind`` (a ``Static`` of ``ArmorItem.Type``)
    built on ``stats``; durability from the material (1.20) unless given."""
    if not isinstance(kind, Static) or kind.owner != ARMOR_TYPE or kind.name not in ARMOR_TYPE_ORDER:
        return None
    protection = stats.defense.get(kind.name)
    if durability is None and stats.durability is not None:
        durability = stats.durability.get(kind.name)
    if not isinstance(protection, int) or protection < 0 or not isinstance(durability, int) or durability <= 0 \
            or stats.enchantability < 0:
        return None
    return ArmorPiece(kind.name, protection, durability, stats.enchantability, stats.toughness, stats.knockback,
                      source, not_carried, look, material)


def registration_calls(cf: ClassFile, name: str, method: str = "<clinit>") -> list[str] | None:
    """The names of the calls a registration chain makes on the entry it names
    ``name`` (from its ``ldc name`` up to the ``putstatic`` that keeps it),
    e.g. Registrate's ``item``, ``properties``, ``tag``, ``register``; None
    when ``name`` isn't registered there exactly once."""
    m = cf.method(method)
    if m is None or m.code is None:
        return None
    runs, run = [], None
    for insn in instructions(cf, m.code):
        if insn.op in (0x12, 0x13) and insn.arg == name:
            run = []
            runs.append(run)
        elif run is not None:
            if insn.op == 0xB3:
                run = None
            elif insn.op in (0xB6, 0xB7, 0xB8, 0xB9) and isinstance(insn.arg, Ref):
                run.append(insn.arg.name)
    return runs[0] if len(runs) == 1 else None


# Methods that decide which enchantments an item takes (or has) in code; the
# numbers are still the material's, so these are named, not refused.
ENCHANTMENT_OVERRIDES = frozenset({
    "canApplyAtEnchantingTable", "isBookEnchantable", "supportsEnchantment", "isPrimaryItemFor",
    "getEnchantmentLevel", "getAllEnchantments",
})


def enchantment_overrides(index: ClassIndex, owner: str) -> list[str]:
    """The :data:`ENCHANTMENT_OVERRIDES` ``owner`` or a mod superclass declares."""
    found, seen, cls = set(), set(), owner
    while cls and not cls.startswith("net/minecraft/") and cls not in seen:
        seen.add(cls)
        cf = index.get(cls)
        if cf is None:
            break
        found |= {m.name for m in cf.methods if m.name in ENCHANTMENT_OVERRIDES}
        cls = cf.super_name
    return sorted(found)


def properties_calls(index: ClassIndex, indy) -> list[str] | None:
    """The Item.Properties calls a customizing lambda (``Consumer<Item.Properties>``,
    an ``invokedynamic`` value) makes, as :func:`_run` records them; None when
    its body can't be followed."""
    for arg in getattr(indy, "args", ()):
        if isinstance(arg, Handle):
            ref = arg.ref
            if ref.owner == PROPERTIES:
                return [ref.name]
            cf = index.get(ref.owner)
            method = cf.method(ref.name, ref.desc) if cf else None
            if method is None:
                return None
            value, props = _run(cf, method, [Param(i) for i in range(len(arg_types(ref.desc)))], lambda *a: None)
            return props if value is RETURNED else None
    return []
