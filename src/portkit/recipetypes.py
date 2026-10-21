"""Recipe types only the mod's own code registers (#358, part of #277).

Java has no data-driven recipe types: a recipe ``type`` names a
``RecipeSerializer`` some code registered (vanilla's in ``RecipeSerializer``,
a mod's through ``Registry.register``, a ``DeferredRegister`` or its loader's
helper). A recipe whose type is in the mod's own namespace, or whose id the
mod's code builds next to a recipe serializer, can only be read by that code.
Bedrock's recipe types are a fixed list (shaped, shapeless, furnace, brewing,
smithing; agent reference topics, MicrosoftDocs/minecraft-creator @4186dc4),
and an add-on can't register one, so such a recipe either is vanilla crafting
under another name or has nothing to land in.

This module answers, from the jar's bytecode with no list of mods or types
(#220), what the converter needs to explain such a recipe (pick 1a, pending
Alex) and to tell a crafting-like variant from a station recipe (pick 2a):

* :func:`read` finds the **registering class**: a class of the mod (not a
  library) that names ``RecipeSerializer`` or ``RecipeType`` and puts the
  type's path on the stack as a string constant used as a registry name,
  either built into the full ``ns:path`` ``ResourceLocation`` (directly or
  through a namespace helper, :class:`portkit.itemprops._Reader`) or passed
  as the ``String`` argument of a ``register``/``accept`` call (a
  ``DeferredRegister``, a ``BiConsumer``, a mod helper). It also reads the
  **serializer class** the registration hands over between the path and the
  register call, when it is a constructor
  reference, a lambda that constructs it, a ``new`` or a static ``INSTANCE``
  field, and the **recipe class** that serializer's generic signature names
  (``RecipeSerializer<Foo>``).
* :func:`vanilla_base` walks the recipe class's superclasses to vanilla
  ``ShapedRecipe``/``ShapelessRecipe``/``StonecutterRecipe``/``CustomRecipe``
  and lists where the mod's code overrides what Java does with the grid
  (``matches``, ``assemble``, ``getRemainingItems``), in the class chain or
  an interface's default method.

Anything not read stays unread: the caller says so in the reason instead of
guessing (#87).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .bytecode import ClassIndex, instructions

_SERIALIZER = "net/minecraft/world/item/crafting/RecipeSerializer"
_RECIPE_TYPE = "net/minecraft/world/item/crafting/RecipeType"
_RL = "net/minecraft/resources/ResourceLocation"

# Vanilla recipe classes a mod's recipe class may extend (Mojang names,
# 1.20.1 and 1.21.x net.minecraft.world.item.crafting) -> the vanilla shape
# its serializer reads.
VANILLA_BASES = {
    "net/minecraft/world/item/crafting/ShapedRecipe": "minecraft:crafting_shaped",
    "net/minecraft/world/item/crafting/ShapelessRecipe": "minecraft:crafting_shapeless",
    "net/minecraft/world/item/crafting/StonecutterRecipe": "minecraft:stonecutting",
    "net/minecraft/world/item/crafting/CustomRecipe": "special",
}

# What Java does with the crafting grid (Recipe#matches, #assemble,
# CraftingRecipe#getRemainingItems): a mod class overriding one changes what
# the vanilla shape alone would do.
BEHAVIOUR = ("matches", "assemble", "getRemainingItems")

_LDC = (0x12, 0x13)
_INVOKES = (0xB6, 0xB7, 0xB8, 0xB9)  # virtual, special, static, interface
_WINDOW = 6


@dataclass
class TypeReading:
    """What the jar's bytecode says about one recipe type."""

    java_type: str
    registering: str | None = None
    serializer: str | None = None
    recipe: str | None = None
    base: str | None = None  # a VANILLA_BASES value, or None
    overrides: list[str] = field(default_factory=list)  # "Class#method"


def _dotted(name: str | None) -> str:
    return (name or "").replace("/", ".")


def short(name: str | None) -> str:
    return _dotted(name).rsplit(".", 1)[-1]


def _string(insn) -> str | None:
    return insn.arg if insn.op in _LDC and isinstance(insn.arg, str) else None


def _own(classes: ClassIndex, name: str | None) -> bool:
    return bool(name) and classes.get(name) is not None and not classes.is_library(name)


def _constructed(classes: ClassIndex, owner: str, name: str, desc: str, depth: int = 2) -> str | None:
    """The first class a lambda body (``owner.name desc``) constructs, or the
    class its static call returns."""
    cf = classes.get(owner)
    m = cf.method(name, desc) if cf is not None else None
    if m is None or not m.code:
        return None
    for insn in instructions(cf, m.code):
        if insn.name == "new" and isinstance(insn.arg, tuple):
            return insn.arg[1]
        if insn.name == "getstatic" and hasattr(insn.arg, "desc") and insn.arg.desc.startswith("L"):
            cls = insn.arg.desc[1:-1]
            if _own(classes, cls):
                return cls
    ret = desc.rsplit(")", 1)[-1]
    if ret.startswith("L") and _own(classes, ret[1:-1]):
        return ret[1:-1]
    return None


def _serializer_near(classes: ClassIndex, cf, ins, lo: int, hi: int) -> str | None:
    for insn in ins[max(lo, 0):hi]:
        arg = insn.arg
        if insn.name == "invokedynamic" and hasattr(arg, "args"):
            for a in arg.args:
                ref = getattr(a, "ref", None)
                if ref is None:
                    continue
                if ref.name == "<init>" and _own(classes, ref.owner):
                    return ref.owner
                if ref.owner == cf.name:
                    found = _constructed(classes, ref.owner, ref.name, ref.desc)
                    if found:
                        return found
        elif insn.name == "new" and isinstance(arg, tuple) and _own(classes, arg[1]):
            return arg[1]
        elif insn.name == "getstatic" and hasattr(arg, "desc") and arg.desc.startswith("L"):
            cls = arg.desc[1:-1]
            if cls not in (_SERIALIZER, _RL) and _own(classes, cls) and cls != cf.name:
                return cls
    return None


def _recipe_of(classes: ClassIndex, serializer: str | None) -> str | None:
    """The recipe class a serializer's generic signature names
    (``...RecipeSerializer<Lfoo/Bar;>``), when it is the mod's."""
    cf = classes.get(serializer) if serializer else None
    sig = getattr(cf, "signature", None) or ""
    key = _SERIALIZER + "<L"
    at = sig.find(key)
    if at < 0:
        return None
    rest = sig[at + len(key):]
    end = min([i for i in (rest.find(";"), rest.find("<")) if i >= 0] or [-1])
    name = rest[:end] if end > 0 else None
    return name if _own(classes, name) else None


def read(classes: ClassIndex | None, java_type: str, own_namespace: str | None = None) -> TypeReading | None:
    """What the jar's code says about ``java_type`` (module docstring), or
    None when no class of the mod is read registering it. A registration that
    passes only the path (``register("shaped_fluid", ...)``) is accepted for a
    type in ``own_namespace``: the namespace is the register's, which is the
    mod's own when the type is."""
    if classes is None or ":" not in java_type:
        return None
    ns, path = java_type.split(":", 1)
    needle = path.encode()
    from .itemprops import _Reader

    reader = _Reader(classes)
    for cname in classes.names():
        raw = classes.raw(cname) or b""
        if needle not in raw or (_SERIALIZER.encode() not in raw and _RECIPE_TYPE.encode() not in raw):
            continue
        cf = classes.get(cname)
        if cf is None:
            continue
        builds_id = java_type in reader.names(cf)
        for m in cf.methods:
            if not m.code:
                continue
            ins = instructions(cf, m.code)
            for k, insn in enumerate(ins):
                if _string(insn) != path:
                    continue
                hit = False
                j = k
                for j in range(k + 1, min(k + 1 + _WINDOW, len(ins))):
                    call = ins[j]
                    ref = call.arg
                    if call.op not in _INVOKES or not hasattr(ref, "owner"):
                        continue
                    if ref.owner == _RL or (ref.desc.endswith(f"L{_RL};") and ref.desc.startswith("(Ljava/lang/String;)")):
                        hit = builds_id
                    elif ref.name in ("register", "accept") and ns == own_namespace and (
                            ref.desc.startswith("(Ljava/lang/String;") or ref.desc.startswith("(Ljava/lang/Object;")):
                        hit = True
                    if hit:
                        break
                if hit:
                    end = j
                    if ins[j].arg.owner == _RL or ins[j].arg.desc.endswith(f"L{_RL};"):
                        # The id is built first: the serializer sits between it and
                        # the call that registers it (Registry.register(id, INSTANCE)).
                        end = next((i for i in range(j + 1, min(j + 1 + _WINDOW, len(ins)))
                                    if ins[i].op in _INVOKES), j)
                    serializer = _serializer_near(classes, cf, ins, k + 1, end)
                    reading = TypeReading(java_type, cname, serializer, _recipe_of(classes, serializer))
                    reading.base, reading.overrides = vanilla_base(classes, reading.recipe)
                    return reading
    return None


def vanilla_base(classes: ClassIndex, recipe: str | None) -> tuple[str | None, list[str]]:
    """(the VANILLA_BASES shape the recipe class extends, or None; every
    ``Class#method`` of the mod's code below that base that overrides one of
    :data:`BEHAVIOUR`, in a superclass or an interface's default method)."""
    if not recipe:
        return None, []
    overrides: list[str] = []
    seen: set[str] = set()
    todo = [recipe]
    base = None
    while todo:
        name = todo.pop(0)
        if name in seen:
            continue
        seen.add(name)
        if name in VANILLA_BASES:
            base = base or VANILLA_BASES[name]
            continue
        cf = classes.get(name)
        if cf is None or classes.is_library(name) and not name.startswith("net/minecraft/"):
            continue
        if not name.startswith("net/minecraft/"):
            for m in cf.methods:
                if m.name in BEHAVIOUR and m.code and not (m.access & 0x1040):  # skip bridge/synthetic
                    overrides.append(f"{short(name)}#{m.name}")
        if cf.super_name:
            todo.append(cf.super_name)
        todo.extend(cf.interfaces)
    return base, sorted(set(overrides))
