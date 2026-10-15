"""Entity loot tables (#176): ``entity`` residue until entities convert.

A table at ``loot_tables/entities/<name>.json`` (``loot_table/`` from 1.21)
named after an entity type the mod's bytecode registers is that entity's
default loot table (see :mod:`portkit.entities`). Bedrock reads an entity's
loot table only through the entity's ``minecraft:loot`` component, and the
entity doesn't convert, so the table is claimed as ``entity`` residue whose
reason names the entity and what the bytecode says about it. Tables named
after no registered entity are left alone (unowned): which entity code
picks them is not read.
"""
from __future__ import annotations

from ..entities import ENTITY, entity_code, loot_reason
from ..model import ConversionResult, SourceMod, Unhandled

_TABLE_DIRS = ("loot_tables", "loot_table")


def convert(mod: SourceMod) -> ConversionResult:
    result = ConversionResult()
    if mod.classes is None or mod.namespace == "minecraft":
        # A jar's minecraft/ tables override vanilla mobs' drops; the mod's
        # own entities are registered under its namespace.
        return result
    entities = None
    for dirname in _TABLE_DIRS:
        src = mod.data / dirname / "entities"
        if not src.is_dir():
            continue
        if entities is None:
            entities = entity_code(mod.classes).entities
        for path in sorted(src.glob("*.json")):
            entity = entities.get(path.stem)
            if entity is None:
                continue
            rel = result.claim(mod, path)
            result.unhandled.append(Unhandled(rel, ENTITY, loot_reason(entity)))
    return result
