"""Create's copper diving gear: durability read from Create's own code (#268).

The copper diving helmet and boots are the bases of Create's netherite diving
gear smithing upgrades, and Bedrock's smithing table takes a base only when
it is armor or a tool (``minecraft:durability``, #263). Create mc1.20.1-6.0.8
registers each with Registrate, ``REGISTRATE.item("copper_diving_helmet",
p -> new DivingHelmetItem(AllArmorMaterials.COPPER, p, ...))``
(``AllItems.<clinit>``, lambdas ``lambda$static$26``/``29`` in the jar), the item
class's ``TYPE`` is ``ArmorItem.Type.HELMET``/``BOOTS``, and
``BaseArmorItem`` passes them to vanilla ``ArmorItem`` with only ``stacksTo(1)``
added. Vanilla 1.20.1 ``ArmorItem`` takes its durability from
``material.getDurabilityForType(type)`` (:data:`portkit.itemcode.VANILLA_SOURCES`),
which ``AllArmorMaterials`` computes as ``MAX_DAMAGE_ARRAY[type.ordinal()] *
maxDamageFactor``. All of that is read from the jar at conversion time
(:func:`portkit.itemcode.armor_type_durability`), nothing is copied here.
"""
from __future__ import annotations

from ... import itemcode
from ...model import SourceMod

ALL_ITEMS = "com/simibubi/create/AllItems"
CITE = ("Create mc1.20.1-6.0.8 jar: AllItems.<clinit> registers {name} as {cls}({material}); "
        "{cls}.TYPE {type}; getDurabilityForType = MAX_DAMAGE_ARRAY[type.ordinal()] "
        "* maxDamageFactor ({material}); " + itemcode.VANILLA_SOURCES["armor_item_1_20"])


def item_durability(mod: SourceMod, names: frozenset) -> dict[str, tuple[int, str]]:
    """Each wanted Create item registered as an armor item on an
    ``ArmorMaterial`` enum constant -> its durability and source."""
    index = mod.classes
    if mod.namespace != "create" or index is None:
        return {}
    registry = index.get(ALL_ITEMS)
    if registry is None:
        return {}
    found = {}
    for name in sorted(names):
        lam = itemcode.registration_lambda(registry, name)
        built = itemcode.constructed(registry, lam) if lam else None
        if built is None:
            continue
        cls, statics = built
        materials = [s for s in statics if itemcode.armor_type_durability(index, s.owner)]
        if len(materials) != 1 or itemcode.sets_durability(index, cls) is not False:
            continue
        material = materials[0]
        kind = itemcode.static_values(index.get(cls)).get("TYPE") if index.get(cls) else None
        if not isinstance(kind, itemcode.Static) or kind.owner != itemcode.ARMOR_TYPE:
            continue
        durability = itemcode.armor_type_durability(index, material.owner).get(material.name, {}).get(kind.name)
        if durability:
            found[name] = (durability, CITE.format(
                name=name, cls=cls.rsplit("/", 1)[-1], material=f"{material.owner.rsplit('/', 1)[-1]}.{material.name}",
                type=kind.name))
    return found
