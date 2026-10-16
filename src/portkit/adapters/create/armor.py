"""Create's armor: slot, armor points, durability and enchantability read from Create's own code (#274).

Create mc1.20.1-6.0.8 registers its armor with Registrate in ``AllItems.<clinit>``,
``REGISTRATE.item("cardboard_helmet", p -> new CardboardHelmetItem(ArmorItem.Type.HELMET, p))``
and ``item("copper_diving_helmet", p -> new DivingHelmetItem(AllArmorMaterials.COPPER, p,
Create.asResource("copper_diving")))``. The item classes pass a material and an
``ArmorItem.Type`` (``CardboardArmorItem``: ``AllArmorMaterials.CARDBOARD``;
``DivingHelmetItem``/``DivingBootsItem``: their ``TYPE``) through
``BaseArmorItem`` to vanilla 1.20.1 ``ArmorItem`` with only ``stacksTo(1)``
added, and ``AllArmorMaterials`` is an ``ArmorMaterial`` enum whose getters
return constructor fields. Vanilla 1.20.1 ``ArmorItem`` takes its armor points,
toughness, knockback resistance, durability and enchantability from the
material (:data:`portkit.itemcode.VANILLA_SOURCES`). All of it is read from the
jar at conversion time with :mod:`portkit.itemcode`; nothing is copied here.

Not answered (so the core leaves them non-wearable, as residue when Java's tags
call them armor): an item class that decides a number in code
(``BacktankItem`` overrides ``canBeDepleted``/``isEnchantable``; the backtanks
ship as blocks anyway), and armor built on vanilla's ``ArmorMaterials``
(``netherite_diving_helmet``/``_boots``), whose numbers are vanilla code that
isn't in Create's jar.
"""
from __future__ import annotations

from ... import itemcode
from ...model import SourceMod

ALL_ITEMS = "com/simibubi/create/AllItems"
CITE = ("Create mc1.20.1-6.0.8 jar: AllItems.<clinit> registers {name} as new {cls}(...), which builds "
        "ArmorItem({material}, {type}); {material}: getDefenseForType = damageReductionAmountArray"
        "[type.ordinal()], getEnchantmentValue/getToughness/getKnockbackResistance = constructor fields, "
        "getDurabilityForType = MAX_DAMAGE_ARRAY[type.ordinal()] * maxDamageFactor; "
        + itemcode.VANILLA_SOURCES["armor_stats_1_20"] + "; " + itemcode.VANILLA_SOURCES["armor_item_1_20"])
# Registrate builder calls that could change an item's properties after its factory.
_PROPERTY_BUILDERS = frozenset({"properties", "initialProperties"})


def item_armor(mod: SourceMod, names: frozenset) -> dict[str, object]:
    """Each Create item registered as an armor item on an ``ArmorMaterial``
    enum constant of Create's -> its :class:`portkit.itemcode.ArmorPiece`."""
    index = mod.classes
    if mod.namespace != "create" or index is None:
        return {}
    registry = index.get(ALL_ITEMS)
    if registry is None:
        return {}
    found: dict[str, object] = {}
    for name in sorted(names):
        lam = itemcode.registration_lambda(registry, name)
        built, made = itemcode.factory(registry, lam) if lam else (None, [])
        if built is None:
            continue
        chain = itemcode.armor_item_args(index, built.cls, built.desc, built.args)
        if chain is None:
            continue
        material, kind, props, desc = chain
        calls = itemcode.registration_calls(registry, name) or []
        if desc != itemcode.ARMOR_ITEM_1_20 or not isinstance(material, itemcode.Static):
            continue
        if material.owner.startswith("net/minecraft/"):
            found[name] = (f"it is built on vanilla's {material.owner.rsplit('/', 1)[-1]}.{material.name}, "
                           "whose numbers are Minecraft's code, not in Create's jar")
            continue
        if itemcode.decides_armor_in_code(index, built.cls) is not False:
            found[name] = (f"its class {built.cls.rsplit('/', 1)[-1]} decides some of its numbers in code "
                           f"({', '.join(itemcode.armor_overrides(index, built.cls)) or 'a superclass not in the jar'})")
            continue
        if set(props + made) & itemcode.ARMOR_PROPERTY_CALLS or set(calls) & _PROPERTY_BUILDERS:
            continue
        stats = itemcode.armor_material_enum(index, material.owner).get(material.name)
        cls = built.cls.rsplit("/", 1)[-1]
        rules = itemcode.enchantment_overrides(index, built.cls)
        extra = (f"which enchantments it takes, decided by {cls} in code ({', '.join(rules)})",) if rules else ()
        piece = itemcode.armor_piece(stats, kind, None, CITE.format(
            name=name, cls=cls, material=f"{material.owner.rsplit('/', 1)[-1]}.{material.name}",
            type=getattr(kind, "name", kind)), extra) if stats else None
        if piece is not None:
            found[name] = piece
    return found
