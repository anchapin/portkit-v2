"""Item properties a mod's own code registers (#344, part of #277).

An item model's ``overrides`` (and, from 1.21.4, an item model definition's
``range_dispatch``/``select``/``condition`` ``property``) switch looks on a
named item property. Vanilla registers its own (``minecraft:angle`` for the
compass, ``minecraft:time`` for the clock, ...); a mod registers more in its
client code, e.g. ``ItemProperties.register(item, ResourceLocation
.fromNamespaceAndPath("mymod", "angle"), function)``, and the function, which
Java calls every frame, is what computes the value. Nothing in a Bedrock pack
runs it: an item's ``minecraft:icon`` is a static texture
(learn.microsoft.com, "minecraft:icon").

This module answers one question from the jar's bytecode, with no list of
mods or property names (#220): which property names does the mod's code build
in a class that handles item property functions? A class counts when its code
names one of Java's item property function types (``_FUNCTION_TYPES``: the
pre-1.21.4 ``ItemPropertyFunction``/``ClampedItemPropertyFunction`` that
``ItemProperties.register`` takes, and the 1.21.4+ ``RangeSelectItemModel
Property``/``SelectItemModelProperty``/``ConditionalItemModelProperty``
interfaces), which is how every registration path seen on the gauntlet looks
in bytecode: a direct ``ItemProperties.register`` call (Nature's Compass,
Quark, AE2, Tinkers' Construct), a mixin accessor of it (Waystones) and a
consumer the loader-specific code hands ``ItemProperties::register`` to
(Botania's ``TriConsumer``). The name is read where the code builds it as a
``ResourceLocation`` from string constants (``_RL_TWO``, ``_RL_ONE``,
``_RL_DEFAULT``), directly or through a mod helper that prefixes the mod's
namespace (``Quark.asResource("count")``, ``ResourceLocationHelper.prefix``),
followed at most ``_HELPER_DEPTH`` calls deep. A name built any other way is
not read, and the property counts as not registered in code (the caller keeps
its ordinary residue).

Names are read through the class index's remapper (#235), so a Forge SRG or
Fabric intermediary jar reads with Mojang's names.
"""
from __future__ import annotations

from .bytecode import ClassFile, ClassIndex, instructions

_RL = "net/minecraft/resources/ResourceLocation"

# ResourceLocation factories by how many string constants they take
# (Mojang names, 1.20.1 and 1.21.x): two (namespace, path) or one ("ns:path",
# a bare path meaning minecraft:), plus withDefaultNamespace (a path in
# minecraft:).
_RL_TWO = {"fromNamespaceAndPath", "tryBuild"}
_RL_ONE = {"parse", "tryParse"}
_RL_DEFAULT = {"withDefaultNamespace"}
_TWO_STRINGS = "(Ljava/lang/String;Ljava/lang/String;)"
_ONE_STRING = "(Ljava/lang/String;)"

# Java's item property function types. Before 1.21.4 ItemProperties.register
# takes an ItemPropertyFunction (ClampedItemPropertyFunction extends it); from
# 1.21.4 a property is a RangeSelectItemModelProperty, SelectItemModelProperty
# or ConditionalItemModelProperty registered by id (mappings.dev 1.21.4,
# net.minecraft.client.renderer.item.properties.{numeric,select,conditional}).
_FUNCTION_TYPES = (
    "net/minecraft/client/renderer/item/ItemPropertyFunction",
    "net/minecraft/client/renderer/item/ClampedItemPropertyFunction",
    "net/minecraft/client/renderer/item/properties/numeric/RangeSelectItemModelProperty",
    "net/minecraft/client/renderer/item/properties/select/SelectItemModelProperty",
    "net/minecraft/client/renderer/item/properties/conditional/ConditionalItemModelProperty",
)

_HELPER_DEPTH = 2
_LDC = (0x12, 0x13)
_ALOAD0 = 0x2A
_INVOKESTATIC, _INVOKESPECIAL = 0xB8, 0xB7


def _string(insn) -> str | None:
    return insn.arg if insn.op in _LDC and isinstance(insn.arg, str) else None


def _names_function_type(cf: ClassFile) -> bool:
    """Whether the class's code names an item property function type
    (a lambda's or call's descriptor, a class reference, an implemented
    interface)."""
    if any(i in _FUNCTION_TYPES for i in cf.interfaces):
        return True
    for entry in cf.pool:
        text = entry[1] if entry and entry[0] == 1 and isinstance(entry[1], str) else None  # CONSTANT_Utf8
        if text and any(t in text for t in _FUNCTION_TYPES):
            return True
    return False


class _Reader:
    def __init__(self, classes: ClassIndex):
        self.classes = classes
        self._helpers: dict[tuple, str | None] = {}

    def helper_namespace(self, owner: str, name: str, desc: str, depth: int) -> str | None:
        """The namespace a static ``(String) -> ResourceLocation`` helper of the
        mod puts in front of its argument, or None when its body isn't that
        plain pattern (``ldc ns; aload_0; <two-string factory>; areturn``, or
        a call to another such helper)."""
        key = (owner, name, desc)
        if key in self._helpers:
            return self._helpers[key]
        self._helpers[key] = None  # a helper calling itself reads as nothing
        cf = self.classes.get(owner)
        method = cf.method(name, desc) if cf is not None else None
        found = None
        if method is not None and method.code and method.access & 0x0008:
            ins = [i for i in instructions(cf, method.code) if i.name not in ("nop",)]
            ops = [i.name for i in ins]
            if len(ins) >= 3 and ops[-1] == "areturn":
                call = ins[-2]
                ref = call.arg
                if (call.op == _INVOKESTATIC and getattr(ref, "owner", None) == _RL
                        and ref.name in _RL_TWO and ref.desc.startswith(_TWO_STRINGS)
                        and len(ins) == 4 and _string(ins[0]) and ins[1].op == _ALOAD0):
                    found = _string(ins[0])
                elif (call.op == _INVOKESPECIAL and getattr(ref, "owner", None) == _RL
                        and ref.name == "<init>" and ref.desc.startswith(_TWO_STRINGS)
                        and len(ins) == 6 and ops[0] == "new" and ops[1] == "dup"
                        and _string(ins[2]) and ins[3].op == _ALOAD0):
                    found = _string(ins[2])
                elif (call.op == _INVOKESTATIC and depth > 1 and len(ins) == 3
                        and ins[0].op == _ALOAD0 and ref.desc == _ONE_STRING + f"L{_RL};"):
                    found = self.helper_namespace(ref.owner, ref.name, ref.desc, depth - 1)
        self._helpers[key] = found
        return found

    def names(self, cf: ClassFile) -> set[str]:
        """Every ``ns:path`` the class's code builds as a ResourceLocation from
        string constants."""
        out: set[str] = set()
        for method in cf.methods:
            if not method.code:
                continue
            ins = instructions(cf, method.code)
            for k, insn in enumerate(ins):
                ref = insn.arg
                if insn.op not in (_INVOKESTATIC, _INVOKESPECIAL) or not hasattr(ref, "owner"):
                    continue
                prev1 = _string(ins[k - 1]) if k >= 1 else None
                prev2 = _string(ins[k - 2]) if k >= 2 else None
                if ref.owner == _RL:
                    two = ((insn.op == _INVOKESTATIC and ref.name in _RL_TWO)
                           or (insn.op == _INVOKESPECIAL and ref.name == "<init>"))
                    if two and ref.desc.startswith(_TWO_STRINGS) and prev1 and prev2:
                        out.add(f"{prev2}:{prev1}")
                    elif ref.desc.startswith(_ONE_STRING) and prev1 and (
                            (insn.op == _INVOKESTATIC and ref.name in _RL_ONE)
                            or (insn.op == _INVOKESPECIAL and ref.name == "<init>")):
                        out.add(prev1 if ":" in prev1 else f"minecraft:{prev1}")
                    elif insn.op == _INVOKESTATIC and ref.name in _RL_DEFAULT and prev1:
                        out.add(f"minecraft:{prev1}")
                elif (insn.op == _INVOKESTATIC and prev1 and ref.desc == _ONE_STRING + f"L{_RL};"
                        and not self.classes.is_library(ref.owner)
                        and self.classes.get(ref.owner) is not None):
                    ns = self.helper_namespace(ref.owner, ref.name, ref.desc, _HELPER_DEPTH)
                    if ns:
                        out.add(f"{ns}:{prev1}")
        return out


def full_name(key: str) -> str:
    """A property key as Java resolves it: a bare name is ``minecraft:``."""
    return key if ":" in key else f"minecraft:{key}"


def code_registered(classes: ClassIndex | None, keys) -> dict[str, str]:
    """property key -> the class whose code builds its name in a class that
    handles item property functions, for each of ``keys`` the mod's own code
    registers (module docstring). Keys are matched by their full name
    (:func:`full_name`); a key not read is left out."""
    wanted = {full_name(k): k for k in keys if isinstance(k, str) and k}
    if classes is None or not wanted:
        return {}
    paths = {name.split(":", 1)[1].encode() for name in wanted}
    reader = _Reader(classes)
    found: dict[str, str] = {}
    for cname in classes.names():
        raw = classes.raw(cname) or b""
        if not any(p in raw for p in paths):
            continue
        cf = classes.get(cname)
        if cf is None or not _names_function_type(cf):
            continue
        for name in reader.names(cf) & set(wanted):
            found.setdefault(wanted[name], cname)
        if len(found) == len(wanted):
            break
    return found
