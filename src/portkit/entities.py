"""Java entity types and their spawn eggs, read from a mod's bytecode (#176).

A Java mob is code: its geometry is built by ModelPart or Citadel calls in a
model class, its animations and AI goals are methods, and its spawn rules
are Java config. A Bedrock entity is data (a behavior-pack entity with
components, a client entity with geometry and textures), and writing one
would mean inventing what the code holds (#87, #135). So entities don't
convert, and the files that only work with an entity, its spawn egg and its
loot table, are ``entity`` residue that says so, which the residue agent
skips.

What the bytecode does say is recorded in those reasons, for the entity work
that comes later: the registered name, the ``MobCategory`` and hitbox size
passed to ``EntityType.Builder``, and a spawn egg's two colours. The patterns
matched, and nothing else (a registration that doesn't match is unread and
its reason says so):

- a registration call ``ldc "name"; invokedynamic`` (a lambda) followed by a
  call whose parameters include ``(String, Supplier)``, optionally storing
  the result in a static field (Forge's ``DeferredRegister.register``, and
  helpers shaped like it, such as Mantle's ``EntityTypeDeferredRegister``).
  The lambda decides what is registered: one returning ``EntityType`` or
  ``EntityType.Builder`` is an entity type, read for
  ``EntityType.Builder.of(factory, MobCategory.X)`` and ``.sized(w, h)``
  with constant arguments (Mojang names, and the Forge 1.20.1 SRG names
  ``m_20704_``/``m_20699_``, matched by their descriptors);
- a spawn egg built in a registered lambda as ``new ForgeSpawnEggItem(ENTITY,
  primary, secondary, properties)`` (Forge), ``DeferredSpawnEggItem``
  (NeoForge) or vanilla ``SpawnEggItem`` under Mojang names, where ENTITY is
  a static field a registration above stored and both colours are integer
  constants. Fabric (intermediary) names are not matched.

Java's default entity loot table is ``<namespace>:entities/<path>`` of the
entity's id (``EntityType#getDefaultLootTable``), so a table at
``loot_tables/entities/<name>.json`` (``loot_table/`` from 1.21) named after a
registered entity is that entity's. Tables under ``entities/`` named after no
registered entity stay unowned: which entity code picks them is not read.
Tables under ``minecraft/`` are vanilla overrides and are left alone.
"""
from __future__ import annotations

import weakref
from dataclasses import dataclass, field

from .bytecode import ClassFile, Handle, Indy, Ref, instructions

ENTITY = "entity"

# The vanilla spawn egg item model; its look (two tinted layers) is the
# egg's colours, which Java sets in code.
SPAWN_EGG_PARENT = "minecraft:item/template_spawn_egg"

_ENTITY_TYPE = "net/minecraft/world/entity/EntityType"
_BUILDER = _ENTITY_TYPE + "$Builder"
_MOB_CATEGORY = "net/minecraft/world/entity/MobCategory"
_FACTORY_OF = f"(L{_ENTITY_TYPE}$EntityFactory;L{_MOB_CATEGORY};)L{_BUILDER};"
_SIZED = f"(FF)L{_BUILDER};"
# Builder.of / Builder.sized: Mojang names (NeoForge 1.20.5+ at runtime) and
# Forge 1.20.1's SRG names (checked against Alex's Mobs 1.22.9's
# AMEntityRegistry, whose calls carry the descriptors above).
_OF_NAMES = frozenset({"of", "m_20704_"})
_SIZED_NAMES = frozenset({"sized", "m_20699_"})

_SPAWN_EGGS = {
    "net/minecraftforge/common/ForgeSpawnEggItem": "ForgeSpawnEggItem",
    "net/neoforged/neoforge/common/DeferredSpawnEggItem": "DeferredSpawnEggItem",
    "net/minecraft/world/item/SpawnEggItem": "SpawnEggItem",
}
_REGISTER_PARAMS = "Ljava/lang/String;Ljava/util/function/Supplier;"
_METAFACTORY = "java/lang/invoke/LambdaMetafactory"


@dataclass(frozen=True)
class EntityType:
    """One registered entity type and what its builder lambda says."""

    name: str
    source: str  # the class that registers it (dotted)
    category: str | None = None  # MobCategory constant
    size: tuple[float, float] | None = None  # sized(width, height), blocks

    def facts(self) -> str:
        bits = [f"registered as {self.name!r} in {self.source}"]
        if self.category:
            bits.append(f"MobCategory {self.category}")
        if self.size:
            bits.append(f"hitbox {_num(self.size[0])} x {_num(self.size[1])} blocks")
        return ", ".join(bits)


@dataclass(frozen=True)
class SpawnEgg:
    item: str
    source: str  # the method that builds it (dotted class#method)
    kind: str  # ForgeSpawnEggItem, DeferredSpawnEggItem, SpawnEggItem
    entity: str | None  # the registered entity name, when its field was read
    colours: tuple[int, int] | None  # (primary, secondary) 0xRRGGBB


@dataclass
class EntityCode:
    entities: dict[str, EntityType] = field(default_factory=dict)
    eggs: dict[str, SpawnEgg] = field(default_factory=dict)


def _num(value: float) -> str:
    # Float constants come off the pool as float32 widened to double
    # (1.600000023841858); %.7g is float32's precision and prints 1.6.
    return f"{value:.7g}"


def colour(value: int) -> str:
    """A Java 0xRRGGBB int as Bedrock's ``#RRGGBB`` (spawn_egg base_color)."""
    return f"#{value & 0xFFFFFF:06X}"


def _int_const(insn) -> int | None:
    if 0x02 <= insn.op <= 0x08:  # iconst_m1 .. iconst_5
        return insn.op - 0x03
    if insn.op in (0x10, 0x11):  # bipush, sipush
        return insn.arg
    if insn.op in (0x12, 0x13) and isinstance(insn.arg, int) and not isinstance(insn.arg, bool):
        return insn.arg
    return None


def _float_const(insn) -> float | None:
    if insn.op in (0x0B, 0x0C, 0x0D):  # fconst_0..2
        return float(insn.op - 0x0B)
    if insn.op in (0x12, 0x13) and isinstance(insn.arg, float):
        return insn.arg
    return None


def _lambda(insn) -> Handle | None:
    """The implementation method of an invokedynamic lambda."""
    indy = insn.arg
    if insn.op != 0xBA or not isinstance(indy, Indy) or indy.bootstrap is None:
        return None
    if indy.bootstrap.ref.owner != _METAFACTORY or len(indy.args) < 2:
        return None
    return indy.args[1] if isinstance(indy.args[1], Handle) else None


def _returns(desc: str) -> str:
    return desc[desc.index(")") + 1:]


def _code(classes, ref: Ref):
    cf = classes.get(ref.owner)
    if cf is None:
        return None, None
    method = cf.method(ref.name, ref.desc)
    if method is None or method.code is None:
        return cf, None
    try:
        return cf, instructions(cf, method.code)
    except Exception:  # noqa: BLE001 - an unreadable method is unread
        return cf, None


def _registrations(cf: ClassFile, insns) -> list[tuple[str, Handle, Ref | None]]:
    """(name, lambda, static field stored into) for each registration call."""
    out = []
    for k in range(len(insns) - 2):
        name = insns[k].arg
        if insns[k].op not in (0x12, 0x13) or not isinstance(name, str):
            continue
        handle = _lambda(insns[k + 1])
        if handle is None:
            continue
        j = k + 2
        # A helper may take more constants after the supplier (Mantle's
        # registerWithEgg takes the egg colours); skip constants only.
        while j < len(insns) and _int_const(insns[j]) is not None:
            j += 1
        if j >= len(insns):
            continue
        call = insns[j]
        if call.op not in (0xB6, 0xB8, 0xB9) or not isinstance(call.arg, Ref):
            continue
        if _REGISTER_PARAMS not in call.arg.desc:
            continue
        stored = None
        if j + 1 < len(insns) and insns[j + 1].op == 0xB3 and isinstance(insns[j + 1].arg, Ref):
            stored = insns[j + 1].arg
        out.append((name, handle, stored))
    return out


def _entity_facts(insns) -> tuple[str | None, tuple[float, float] | None]:
    category = size = None
    ofs = [k for k, i in enumerate(insns) if i.op == 0xB8 and isinstance(i.arg, Ref)
           and i.arg.owner == _BUILDER and i.arg.name in _OF_NAMES and i.arg.desc == _FACTORY_OF]
    if len(ofs) == 1 and ofs[0] >= 1:
        prev = insns[ofs[0] - 1]
        if prev.op == 0xB2 and isinstance(prev.arg, Ref) and prev.arg.owner == _MOB_CATEGORY:
            category = prev.arg.name
    sized = [k for k, i in enumerate(insns) if i.op == 0xB6 and isinstance(i.arg, Ref)
             and i.arg.owner == _BUILDER and i.arg.name in _SIZED_NAMES and i.arg.desc == _SIZED]
    if len(sized) == 1 and sized[0] >= 2:
        w, h = _float_const(insns[sized[0] - 2]), _float_const(insns[sized[0] - 1])
        if w is not None and h is not None:
            size = (w, h)
    return category, size


def _egg(insns) -> tuple[str, Ref | None, tuple[int, int] | None] | None:
    """(egg class, entity field, colours) of the one spawn egg the lambda builds."""
    ctors = [k for k, i in enumerate(insns) if i.op == 0xB7 and isinstance(i.arg, Ref)
             and i.arg.owner in _SPAWN_EGGS and i.arg.name == "<init>"]
    if len(ctors) != 1:
        return None
    end = ctors[0]
    kind = _SPAWN_EGGS[insns[end].arg.owner]
    news = [k for k in range(end) if insns[k].op == 0xBB and insns[k].arg == ("class", insns[end].arg.owner)]
    if len(news) != 1:
        return kind, None, None
    k = news[0] + 1
    if k < end and insns[k].op == 0x59:  # dup
        k += 1
    entity = None
    if k < end and insns[k].op == 0xB2 and isinstance(insns[k].arg, Ref):
        entity = insns[k].arg
        k += 1
        # SpawnEggItem takes the EntityType itself: RegistryObject#get, checkcast.
        if k < end and insns[k].op in (0xB6, 0xB9) and isinstance(insns[k].arg, Ref) \
                and insns[k].arg.desc.startswith("()"):
            k += 1
            if k < end and insns[k].op == 0xC0:
                k += 1
    colours = None
    # Only the (entity, int, int, properties) constructors take colours
    # (vanilla 1.21.5+ SpawnEggItem has none).
    if ";IIL" in insns[end].arg.desc and k + 1 < end:
        a, b = _int_const(insns[k]), _int_const(insns[k + 1])
        if a is not None and b is not None:
            colours = (a, b)
    return kind, entity, colours


def read(classes) -> EntityCode:
    """Every entity type and spawn egg the patterns above find in ``classes``."""
    code = EntityCode()
    if classes is None:
        return code
    fields: dict[tuple[str, str], str] = {}
    pending_eggs: list[tuple[str, str, tuple]] = []
    for cname in classes.names():
        cf = classes.get(cname)
        if cf is None:
            continue
        for method in cf.methods:
            if method.code is None:
                continue
            try:
                insns = instructions(cf, method.code)
            except Exception:  # noqa: BLE001
                continue
            for name, handle, stored in _registrations(cf, insns):
                ref = handle.ref
                if not isinstance(ref, Ref):
                    continue
                ret = _returns(ref.desc)
                if ret in (f"L{_ENTITY_TYPE};", f"L{_BUILDER};"):
                    _, body = _code(classes, ref)
                    category, size = _entity_facts(body) if body else (None, None)
                    code.entities.setdefault(name, EntityType(name, cname.replace("/", "."), category, size))
                    if stored is not None:
                        fields[(stored.owner, stored.name)] = name
                    continue
                _, body = _code(classes, ref)
                egg = _egg(body) if body else None
                if egg is not None:
                    pending_eggs.append((name, f"{ref.owner.replace('/', '.')}#{ref.name}", egg))
    for item, source, (kind, field_ref, colours) in pending_eggs:
        entity = fields.get((field_ref.owner, field_ref.name)) if field_ref is not None else None
        code.eggs.setdefault(item, SpawnEgg(item, source, kind, entity, colours))
    return code


_CACHE: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def entity_code(classes) -> EntityCode:
    """:func:`read`, once per class index."""
    if classes is None:
        return EntityCode()
    try:
        return _CACHE[classes]
    except KeyError:
        code = _CACHE[classes] = read(classes)
        return code


_WHY = ("a Java entity's geometry, animations and AI are code, and a Bedrock entity written "
        "without them would invent them (#176, #87)")


def spawn_egg_reason(classes, item: str) -> str:
    """Why the spawn egg item ``item`` (model parent template_spawn_egg) doesn't convert."""
    code = entity_code(classes)
    egg = code.eggs.get(item)
    head = "spawn egg (model parent item/template_spawn_egg)"
    if egg is None:
        read_part = "; which entity it spawns and its colours were not read from this jar's bytecode"
    elif egg.entity is None:
        read_part = f"; built as {egg.kind} in {egg.source}, but which entity it spawns was not read"
        if egg.colours:
            read_part += f" (colours {colour(egg.colours[0])} / {colour(egg.colours[1])})"
    else:
        entity = code.entities.get(egg.entity)
        facts = entity.facts() if entity else f"registered as {egg.entity!r}"
        read_part = f" for the entity {facts}; built as {egg.kind} in {egg.source}"
        if egg.colours:
            read_part += f" with colours {colour(egg.colours[0])} / {colour(egg.colours[1])}"
    return (f"{head}{read_part}. A Bedrock spawn egg is the spawn_egg entry of its entity's client "
            f"definition, and the entity doesn't convert: {_WHY}")


def loot_reason(entity: EntityType) -> str:
    return (f"loot table of the entity {entity.facts()} (Java's default table entities/<name>, "
            "EntityType#getDefaultLootTable). A Bedrock entity's loot table is named by its "
            f"minecraft:loot component, and the entity doesn't convert: {_WHY}")
