"""Mythic Metals' tool and armor sets: durability read from the mod's code (#268).

Mythic Metals' smithing upgrades (kyber -> carmot, banglum -> legendary banglum,
mythril pickaxe -> drill, palladium/hallowed sword -> aegis swords, ...) take a
Mythic Metals tool or armor piece as the base, and Bedrock's smithing table
takes a base only when it is armor or a tool (``minecraft:durability``, #263).
Mythic Metals 0.24.6+1.21 (jar bytecode, intermediary names read as Mojang's,
#235) builds them in sets registered by owo's field registration
(``MythicTools`` / ``MythicArmor`` implement ``SimpleFieldProcessingSubject``,
which registers each static field under its lower-cased name):

* tools: ``MythicTools.<clinit>`` sets ``KYBER = new ToolSet(MythicToolMaterials.KYBER, ...)``;
  ``ToolSet.register(name)`` registers ``name + "_sword"``/``"_axe"``/``"_pickaxe"``/
  ``"_shovel"``/``"_hoe"`` from the fields ``ToolSet.<init>`` fills with
  ``makeSword``/``makeAxe``/... (vanilla ``SwordItem``/``AxeItem``/..., or a
  set's own subclass of them), each built on the set's tier. Vanilla 1.21.1
  ``TieredItem`` gives such an item ``tier.getUses()`` as its durability
  (:data:`portkit.itemcode.VANILLA_SOURCES`), read per tier from
  ``MythicToolMaterials`` by :func:`portkit.itemcode.tier_uses`.
* armor: ``MythicArmor.<clinit>`` sets ``KYBER = new ArmorSet(MythicArmorMaterials.KYBER, 21)``;
  ``ArmorSet.baseArmorItem`` builds each piece with
  ``Item.Properties#durability(BASE_DURABILITY.get(type) * multiplier)``, with
  ``ArmorSet.BASE_DURABILITY`` = ``Map.of(HELMET, 12, CHESTPLATE, 16, LEGGINGS, 15,
  BOOTS, 13)`` in this jar (read, not copied), and ``ArmorSet.register(name)``
  registers ``name + "_helmet"``/... from the fields ``ArmorSet.<init>`` fills
  per ``ArmorItem.Type``. Vanilla 1.21.1 ``ArmorItem`` adds no durability of its own.

A set built by a subclass that overrides how a piece is made, a set whose
customizing lambda calls ``durability`` itself, or a piece class that sets
durability itself is not answered (its recipe is withdrawn by the core).
"""
from __future__ import annotations

from ... import itemcode
from ...bytecode import ClassIndex, Handle, Indy, Ref, instructions
from ...model import SourceMod

TOOLS = "com/mythicmetals/item/tools/MythicTools"
TOOL_SET = "com/mythicmetals/item/tools/ToolSet"
TOOL_MATERIALS = "com/mythicmetals/item/tools/MythicToolMaterials"
ARMOR = "com/mythicmetals/armor/MythicArmor"
ARMOR_SET = "com/mythicmetals/armor/ArmorSet"
TOOL_CITE = ("Mythic Metals 0.24.6+1.21 jar: MythicTools.{field} = new {cls}(MythicToolMaterials.{tier}), "
             "ToolSet.register -> {name}; MythicToolMaterials.{tier} getUses() = {uses}; "
             + itemcode.VANILLA_SOURCES["tiered_item"])
ARMOR_CITE = ("Mythic Metals 0.24.6+1.21 jar: MythicArmor.{field} = new ArmorSet(MythicArmorMaterials.{field}, "
              "{mult}), ArmorSet.register -> {name}; ArmorSet.baseArmorItem: Item.Properties#durability("
              "BASE_DURABILITY {type} {base} * {mult}); " + itemcode.VANILLA_SOURCES["armor_item_1_21"])


def _suffix_fields(cf) -> dict[str, str]:
    """``register(String)``'s ``name + suffix`` call sites -> the field each registers."""
    method = cf.method("register", "(Ljava/lang/String;)V")
    out, suffix = {}, None
    if method is None or method.code is None:
        return out
    for insn in instructions(cf, method.code):
        if isinstance(insn.arg, Indy) and insn.arg.name == "makeConcatWithConstants":
            recipe = next((a for a in insn.arg.args if isinstance(a, str)), "")
            suffix = recipe[1:] if recipe.startswith("\x01") and recipe.count("\x01") == 1 else None
        elif insn.op == 0xB4 and suffix and isinstance(insn.arg, Ref) and insn.arg.owner == cf.name:
            out[suffix] = insn.arg.name
            suffix = None
    return out


def _field_makers(cf, maker_desc_prefix: str) -> dict[str, list]:
    """``<init>``'s ``this.field = this.makeX(...)`` / ``baseArmorItem(.., Type.T, ..)``:
    field -> the instructions since the previous field store."""
    out = {}
    for method in cf.methods:
        if method.name != "<init>" or method.code is None:
            continue
        run = []
        for insn in instructions(cf, method.code):
            run.append(insn)
            if insn.op == 0xB5 and isinstance(insn.arg, Ref) and insn.arg.owner == cf.name:
                out.setdefault(insn.arg.name, run)
                run = []
    return out


def _lambda_sets_durability(index: ClassIndex, indy) -> bool:
    """Whether a customizing lambda (``Consumer<Item.Properties>``) calls
    ``durability``; a method reference to another Properties call doesn't."""
    for arg in getattr(indy, "args", ()):
        if isinstance(arg, Handle):
            ref = arg.ref
            if ref.owner == itemcode.PROPERTIES:
                return ref.name in itemcode.DURABILITY_CALLS
            cf = index.get(ref.owner)
            method = cf.method(ref.name, ref.desc) if cf else None
            if method is None or method.code is None:
                return True  # unreadable: treat as setting it
            return any(isinstance(i.arg, Ref) and i.arg.owner == itemcode.PROPERTIES
                       and i.arg.name in itemcode.DURABILITY_CALLS for i in instructions(cf, method.code))
    return False


def _tools(index: ClassIndex, names: frozenset) -> dict[str, tuple[int, str]]:
    tools, base = index.get(TOOLS), index.get(TOOL_SET)
    if tools is None or base is None:
        return {}
    uses = itemcode.tier_uses(index, TOOL_MATERIALS)
    suffixes = _suffix_fields(base)
    makers = _field_makers(base, "make")
    found = {}
    for field, value in itemcode.static_values(tools).items():
        if not isinstance(value, itemcode.New) or not value.args:
            continue
        tier = value.args[0]
        if not isinstance(tier, itemcode.Static) or tier.owner != TOOL_MATERIALS or tier.name not in uses:
            continue
        set_cf = index.get(value.cls)
        if set_cf is None or (value.cls != TOOL_SET and set_cf.super_name != TOOL_SET):
            continue
        if any(isinstance(a, Indy) and _lambda_sets_durability(index, a) for a in value.args):
            continue
        for suffix, slot in suffixes.items():
            name = field.lower() + suffix
            if name not in names:
                continue
            call = next((i.arg for i in reversed(makers.get(slot, [])) if i.op == 0xB6
                         and isinstance(i.arg, Ref) and i.arg.name.startswith("make")), None)
            if call is None:
                continue
            maker_owner = value.cls if set_cf.method(call.name, call.desc) else TOOL_SET
            maker_cf = index.get(maker_owner)
            maker = maker_cf.method(call.name, call.desc) if maker_cf else None
            built = [i.arg[1] for i in instructions(maker_cf, maker.code) if i.op == 0xBB] if maker and maker.code else []
            items = [c for c in built if c != itemcode.PROPERTIES and "attribute" not in c.lower()]
            if len(items) != 1 or itemcode.sets_durability(index, items[0]) is not False:
                continue
            found[name] = (uses[tier.name], TOOL_CITE.format(
                field=field, cls=value.cls.rsplit("/", 1)[-1], tier=tier.name, name=name, uses=uses[tier.name]))
    return found


def _armor(index: ClassIndex, names: frozenset) -> dict[str, tuple[int, str]]:
    armor, base = index.get(ARMOR), index.get(ARMOR_SET)
    if armor is None or base is None:
        return {}
    table = itemcode.static_values(base).get("BASE_DURABILITY")
    if not isinstance(table, itemcode.Call) or table.owner != "java/util/Map" or table.name != "of":
        return {}
    per_type = {}
    for key, value in zip(table.args[::2], table.args[1::2]):
        if isinstance(key, itemcode.Static) and key.owner == itemcode.ARMOR_TYPE and isinstance(value, itemcode.Call) \
                and value.name == "valueOf" and value.args and isinstance(value.args[0], int):
            per_type[key.name] = value.args[0]
    maker = base.method("baseArmorItem")
    if maker is None or maker.code is None or not any(
            isinstance(i.arg, Ref) and i.arg.owner == itemcode.PROPERTIES and i.arg.name == "durability"
            for i in instructions(base, maker.code)):
        return {}
    suffixes = _suffix_fields(base)
    types = {}
    for field, run in _field_makers(base, "").items():
        kinds = [i.arg.name for i in run if i.op == 0xB2 and i.arg.owner == itemcode.ARMOR_TYPE]
        if len(kinds) == 1:
            types[field] = kinds[0]
    found = {}
    for field, value in itemcode.static_values(armor).items():
        if not isinstance(value, itemcode.New) or value.cls != ARMOR_SET or len(value.args) < 2:
            continue  # a subclass may build its pieces its own way
        mult = value.args[1]
        if not isinstance(mult, int) or mult <= 0:
            continue
        if any(isinstance(a, Indy) and _lambda_sets_durability(index, a) for a in value.args):
            continue
        for suffix, slot in suffixes.items():
            name = field.lower() + suffix
            kind = types.get(slot)
            if name not in names or kind not in per_type:
                continue
            found[name] = (per_type[kind] * mult, ARMOR_CITE.format(
                field=field, mult=mult, name=name, type=kind, base=per_type[kind]))
    return found


def item_durability(mod: SourceMod, names: frozenset) -> dict[str, tuple[int, str]]:
    """Each wanted Mythic Metals tool or armor piece -> its durability and source."""
    index = mod.classes
    if mod.namespace != "mythicmetals" or index is None:
        return {}
    return {**_armor(index, names), **_tools(index, names)}
