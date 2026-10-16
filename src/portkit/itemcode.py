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
    out, i, inner = [], 1, desc[1:desc.index(")")]
    i = 0
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
    """The field ``name``'s body returns when it is ``return this.field``."""
    method = cf.method(name, desc)
    if method is None or method.code is None:
        return None
    ops = instructions(cf, method.code)
    if len(ops) == 3 and ops[0].name == "aload_0" and ops[1].op == 0xB4 and ops[2].op == 0xAC \
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
    """The local slot an ``iload``/``aload`` family instruction reads."""
    name = insn.name
    for prefix in ("iload", "aload", "fload"):
        if name == prefix:
            return insn.arg
        if name.startswith(prefix + "_"):
            return int(name[-1])
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
    ``Item.Properties#durability``/``defaultDurability`` anywhere (True), not
    at all (False), or can't be read (None: a superclass missing from the jar
    that isn't Minecraft's)."""
    seen = set()
    cls = owner
    while cls and not cls.startswith(stop) and cls not in seen:
        seen.add(cls)
        cf = index.get(cls)
        if cf is None:
            return None
        for method in cf.methods:
            if method.code is None:
                continue
            for insn in instructions(cf, method.code):
                ref = insn.arg
                if isinstance(ref, Ref) and ref.owner == PROPERTIES and ref.name in DURABILITY_CALLS:
                    return True
        cls = cf.super_name
    return False
