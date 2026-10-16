"""Mythic Metals' armor sets: slot, armor points, durability and enchantability from the mod's code (#274).

Mythic Metals 0.24.6+1.21 (jar bytecode, intermediary names read as Mojang's,
#235) builds its armor in sets (see :mod:`.durability` for how they are
registered): ``MythicArmor.<clinit>`` sets ``KYBER = new ArmorSet(MythicArmorMaterials.KYBER, 21)``,
and ``ArmorSet.<init>`` fills ``helmet``/``chestplate``/``leggings``/``boots`` with
``baseArmorItem(material, ArmorItem.Type.X, multiplier, settings)``, which gives
the piece ``Item.Properties#durability(BASE_DURABILITY[type] * multiplier)``
and builds it with ``makeItem(material, type, properties)``:
``new ArmorItem(getEntry(material), type, properties)`` in ``ArmorSet``, or in a
set subclass (``HallowedArmorSet`` and others) its own item class for one
type and ``super.makeItem`` for the rest. Each item class is followed up its
constructors to vanilla ``ArmorItem`` (:func:`portkit.itemcode.armor_item_args`),
which gives the material and type it is really built on.

``MythicArmorMaterials.<clinit>`` builds each material as a vanilla 1.21
``new ArmorMaterial(Map.of(HELMET, 3, ...), enchantability, sound, repair,
layers, toughness, knockbackResistance)`` (:func:`portkit.itemcode.armor_material_record`).
Vanilla 1.21.1 ``ArmorItem`` takes its armor points and enchantability from
that record and adds no durability of its own
(:data:`portkit.itemcode.VANILLA_SOURCES`). Everything is read from the jar at
conversion time; nothing is copied here.

``ArmorItemMixin`` adds attribute bonuses to the armor of some materials
(swim speed, movement speed, attack damage and more): those materials' pieces
name it as not carried. A set whose customizing lambda sets durability or
attributes, a set subclass that builds pieces its own way, or an item class
that decides a number in code is not answered.
"""
from __future__ import annotations

from ... import itemcode
from ...bytecode import ClassIndex, instructions
from ...model import SourceMod
from .durability import ARMOR, ARMOR_SET, _field_makers, _suffix_fields

MATERIALS = "com/mythicmetals/armor/MythicArmorMaterials"
MIXIN = "com/mythicmetals/mixin/ArmorItemMixin"
MAKE_ITEM = f"(L{itemcode.ARMOR_MATERIAL};L{itemcode.ARMOR_TYPE};L{itemcode.PROPERTIES};)L{itemcode.ARMOR_ITEM};"
CITE = ("Mythic Metals 0.24.6+1.21 jar: MythicArmor.{field} = new {set}(MythicArmorMaterials.{field}, {mult}), "
        "ArmorSet.register -> {field_lower}_helmet/_chestplate/_leggings/_boots; {set}.makeItem builds each on "
        "vanilla ArmorItem(MythicArmorMaterials.{material}, type) (item classes followed up their constructors); "
        "MythicArmorMaterials.{material} = new ArmorMaterial(defense {defense}, enchantability {ench}, "
        "..., toughness {tough:g}, knockbackResistance {knock:g}); ArmorSet.baseArmorItem: "
        "Item.Properties#durability(BASE_DURABILITY[type] * {mult}), BASE_DURABILITY {base}; "
        + itemcode.VANILLA_SOURCES["armor_stats_1_21"] + "; " + itemcode.VANILLA_SOURCES["armor_item_1_21"])


def _base_durability(base) -> dict[str, int]:
    table = itemcode.static_values(base).get("BASE_DURABILITY")
    if not isinstance(table, itemcode.Call) or table.owner != "java/util/Map" or table.name != "of":
        return {}
    out = {}
    for key, value in zip(table.args[::2], table.args[1::2]):
        number = itemcode._int(value)
        if isinstance(key, itemcode.Static) and key.owner == itemcode.ARMOR_TYPE and number is not None:
            out[key.name] = number
    return out


def _settings(index: ClassIndex, args: list) -> tuple[str, ...] | None:
    """The mod data components a set's customizing lambdas add, or None when
    one sets durability or attributes (or can't be followed)."""
    components: list[str] = []
    for arg in args:
        if not hasattr(arg, "bootstrap"):
            continue
        calls = itemcode.properties_calls(index, arg)
        if calls is None or set(calls) & itemcode.ARMOR_PROPERTY_CALLS:
            return None
        components += [c.split(" ", 1)[1] for c in calls if c.startswith("component ")]
    return tuple(components)


def _mixin_bonuses(index: ClassIndex) -> dict[str, str]:
    """Material -> the note for armor ``ArmorItemMixin`` adds attribute bonuses to."""
    cf = index.get(MIXIN)
    out: dict[str, str] = {}
    if cf is None:
        return out
    for method in cf.methods:
        if method.code is None:
            continue
        for insn in instructions(cf, method.code):
            if insn.op == 0xB2 and insn.arg.owner == MATERIALS:
                out[insn.arg.name] = ("the attribute bonuses Mythic Metals' ArmorItemMixin adds to "
                                      f"MythicArmorMaterials.{insn.arg.name} armor")
    return out


def _piece_class(index: ClassIndex, set_cls: str, material, kind) -> tuple[str, object, object, tuple] | None:
    """(item class, material, type, mod data components its constructors add)
    the set's ``makeItem`` builds the piece on."""
    owner = set_cls
    while owner and owner != "java/lang/Object":
        cf = index.get(owner)
        if cf is None:
            return None
        method = cf.method("makeItem", MAKE_ITEM)
        if method is not None:
            break
        owner = cf.super_name
    else:
        return None

    def call(cf, m, args, depth=0):
        """Run makeItem; follow a ``super.makeItem`` call."""
        value, _ = itemcode._run(cf, m, args, lambda *a: None)
        return value

    # makeItem returns a New; a super.makeItem call comes back as a Call to re-run on the superclass.
    cf = index.get(owner)
    value = call(cf, cf.method("makeItem", MAKE_ITEM), [material, kind, itemcode.Param(3)])
    depth = 0
    while isinstance(value, itemcode.Call) and value.name == "makeItem" and depth < 4:
        depth += 1
        cf = index.get(value.owner)
        if cf is None or cf.method("makeItem", MAKE_ITEM) is None:
            return None
        value = call(cf, cf.method("makeItem", MAKE_ITEM), list(value.args))
    if not isinstance(value, itemcode.New) or value.desc is None:
        return None
    chain = itemcode.armor_item_args(index, value.cls, value.desc, value.args)
    if chain is None or chain[3] != itemcode.ARMOR_ITEM_1_21:
        return None
    built_material, built_kind, props, _ = chain
    if set(props) & itemcode.ARMOR_PROPERTY_CALLS:
        return None
    return value.cls, built_material, built_kind, tuple(p.split(" ", 1)[1] for p in props if p.startswith("component "))


def item_armor(mod: SourceMod, names: frozenset) -> dict[str, object]:
    """Each wanted Mythic Metals armor piece -> its :class:`portkit.itemcode.ArmorPiece`."""
    index = mod.classes
    if mod.namespace != "mythicmetals" or index is None:
        return {}
    armor, base, materials_cf = index.get(ARMOR), index.get(ARMOR_SET), index.get(MATERIALS)
    if armor is None or base is None or materials_cf is None:
        return {}
    per_type = _base_durability(base)
    materials = itemcode.static_values(materials_cf)
    suffixes = _suffix_fields(base)
    types = {}
    for field, run in _field_makers(base).items():
        kinds = [i.arg for i in run if i.op == 0xB2 and i.arg.owner == itemcode.ARMOR_TYPE]
        if len(kinds) == 1:
            types[field] = itemcode.Static(kinds[0].owner, kinds[0].name)
    bonuses = _mixin_bonuses(index)
    found: dict[str, object] = {}
    for field, value in itemcode.static_values(armor).items():
        if not isinstance(value, itemcode.New) or len(value.args) < 2:
            continue
        set_cf = index.get(value.cls)
        if set_cf is None or (value.cls != ARMOR_SET and set_cf.super_name != ARMOR_SET) \
                or set_cf.method("baseArmorItem") is not None and value.cls != ARMOR_SET:
            continue
        material, mult = value.args[0], value.args[1]
        settings = _settings(index, value.args)
        if not isinstance(material, itemcode.Static) or material.owner != MATERIALS or not isinstance(mult, int) \
                or mult <= 0 or settings is None:
            continue
        for suffix, slot in suffixes.items():
            name = field.lower() + suffix
            kind = types.get(slot)
            if name not in names or kind is None or kind.name not in per_type:
                continue
            piece = _piece_class(index, value.cls, material, kind)
            if piece is None:
                continue
            cls, built_material, built_kind, components = piece
            if not isinstance(built_material, itemcode.Static) or built_material.owner != MATERIALS:
                continue
            if itemcode.decides_armor_in_code(index, cls) is not False:
                found[name] = (f"its class {cls.rsplit('/', 1)[-1]} decides some of its numbers in code "
                               f"({', '.join(itemcode.armor_overrides(index, cls))})")
                continue
            stats = itemcode.armor_material_record(materials.get(built_material.name))
            if stats is None:
                continue
            durability = per_type[getattr(built_kind, "name", "")] * mult if getattr(built_kind, "name", "") in per_type else None
            source = CITE.format(
                field=field, field_lower=field.lower(), set=value.cls.rsplit("/", 1)[-1], mult=mult,
                material=built_material.name,
                defense=" ".join(f"{k} {v}" for k, v in stats.defense.items()), ench=stats.enchantability,
                tough=stats.toughness, knock=stats.knockback,
                base=" ".join(f"{k} {v}" for k, v in per_type.items()))
            extra = tuple(f"the data component {c.rsplit('/', 1)[-1]} its class {cls.rsplit('/', 1)[-1]} adds"
                          for c in components)
            extra += tuple(f"the data component {c.rsplit('/', 1)[-1]} MythicArmor.{field}'s settings add"
                           for c in settings)
            if built_material.name in bonuses:
                extra += (bonuses[built_material.name],)
            got = itemcode.armor_piece(stats, built_kind, durability, source, extra)
            if got is not None:
                found[name] = got
    return found
