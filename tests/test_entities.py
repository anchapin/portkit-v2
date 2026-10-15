"""Entities don't convert (#176); their spawn eggs and default loot tables are
``entity`` residue whose reasons carry what the bytecode says.

The class files under tests/data/entitycode/classes are javac 21 output of
the example mod in tests/data/entitycode/src against signature-only stubs
(rebuild with build.sh): real compiler patterns, no Minecraft code. The
realmods test reads Alex's Mobs 1.22.9 (optional corpus) and checks values
against its own bytecode, as javap shows it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from portkit import corpus, entities
from portkit.agent.residue import SKIP_KINDS
from portkit.bytecode import ClassIndex
from portkit.converters import convert_all
from portkit.converters import entities as entity_loot
from portkit.model import SourceMod

CLASSES = Path(__file__).parent / "data" / "entitycode" / "classes"
NS = "mobs"


@pytest.fixture(scope="module")
def code():
    return entities.read(ClassIndex.from_source(CLASSES))


# --- reading the bytecode -------------------------------------------------------

def test_entity_types_with_category_and_hitbox(code):
    assert set(code.entities) == {"bear", "moth", "ghost", "slime"}
    bear = code.entities["bear"]
    assert (bear.category, bear.source) == ("CREATURE", "com.example.mobs.ModEntities")
    # float32 constants print at float32 precision
    assert bear.facts() == ("registered as 'bear' in com.example.mobs.ModEntities, MobCategory CREATURE, "
                            "hitbox 1.4 x 1.4 blocks")
    # Built through a helper in the lambda (Alex's Mobs' registerEntity).
    assert (code.entities["moth"].category, code.entities["moth"].size) == ("AMBIENT", (0.5, 0.25))
    # A lambda returning the Builder (a Mantle-style helper).
    assert (code.entities["slime"].category, code.entities["slime"].size) == ("MONSTER", (2.0, 1.0))


def test_a_hitbox_from_a_field_is_unread(code):
    ghost = code.entities["ghost"]
    assert (ghost.category, ghost.size) == ("MONSTER", None)
    assert "hitbox" not in ghost.facts()


def test_spawn_eggs_name_their_entity_and_colours(code):
    bear = code.eggs["bear_spawn_egg"]
    assert (bear.kind, bear.entity, bear.colours) == ("ForgeSpawnEggItem", "bear", (0x693A2C, 0x976144))
    assert bear.source == "com.example.mobs.ModItems#lambda$static$0"
    # Vanilla SpawnEggItem takes the type (RegistryObject#get); iconst_5 and sipush.
    moth = code.eggs["moth_spawn_egg"]
    assert (moth.kind, moth.entity, moth.colours) == ("SpawnEggItem", "moth", (5, 200))
    assert entities.colour(0x693A2C) == "#693A2C" and entities.colour(5) == "#000005"


def test_unread_parts_of_an_egg_stay_unread(code):
    # A colour read from a field: no colours, the entity is still read.
    assert (code.eggs["ghost_spawn_egg"].entity, code.eggs["ghost_spawn_egg"].colours) == ("ghost", None)
    # An entity field no registration stored: no entity, the colours are still read.
    stray = code.eggs["stray_spawn_egg"]
    assert (stray.entity, stray.colours) == (None, (0x101010, 0x202020))
    # An item that isn't a spawn egg is not one.
    assert "plain" not in code.eggs


def test_no_classes_reads_nothing():
    assert entities.read(None) == entities.EntityCode()
    assert entities.entity_code(None) == entities.EntityCode()


# --- the residue ----------------------------------------------------------------

def _write(path: Path, body) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body), encoding="utf-8")


def _mod(tmp_path: Path, classes: bool = True) -> SourceMod:
    a, d = tmp_path / "assets" / NS, tmp_path / "data" / NS
    for egg in ("bear", "moth", "ghost", "stray", "nocode"):
        _write(a / "models" / "item" / f"{egg}_spawn_egg.json", {"parent": "minecraft:item/template_spawn_egg"})
    # The short spelling of the same vanilla parent, through a mod parent.
    _write(a / "models" / "item" / "egg_base.json", {"parent": "item/template_spawn_egg"})
    _write(a / "models" / "item" / "slime_spawn_egg.json", {"parent": f"{NS}:item/egg_base"})
    table = {"type": "minecraft:entity", "pools": [{"rolls": 1, "entries": [
        {"type": "minecraft:item", "name": "minecraft:leather"}]}]}
    _write(d / "loot_tables" / "entities" / "bear.json", table)
    _write(d / "loot_table" / "entities" / "moth.json", table)  # 1.21's directory
    _write(d / "loot_tables" / "entities" / "bear_variant.json", table)  # named after no entity
    _write(d / "loot_tables" / "blocks" / "x.json", {"type": "minecraft:block", "pools": []})
    return SourceMod(root=tmp_path, namespace=NS, classes=ClassIndex.from_source(CLASSES) if classes else None)


def _residue(result) -> dict[str, tuple[str, str]]:
    return {u.source: (u.kind, u.reason) for u in result.unhandled}


def test_spawn_eggs_and_entity_loot_tables_are_entity_residue(tmp_path):
    result = convert_all(_mod(tmp_path))
    res = _residue(result)
    egg = f"assets/{NS}/models/item/bear_spawn_egg.json"
    assert res[egg] == ("entity", (
        "spawn egg (model parent item/template_spawn_egg) for the entity registered as 'bear' in "
        "com.example.mobs.ModEntities, MobCategory CREATURE, hitbox 1.4 x 1.4 blocks; built as "
        "ForgeSpawnEggItem in com.example.mobs.ModItems#lambda$static$0 with colours #693A2C / #976144. "
        "A Bedrock spawn egg is the spawn_egg entry of its entity's client definition, and the entity "
        "doesn't convert: a Java entity's geometry, animations and AI are code, and a Bedrock entity "
        "written without them would invent them (#176, #87)"))
    assert res[f"assets/{NS}/models/item/slime_spawn_egg.json"][0] == "entity"
    assert "which entity it spawns was not read (colours #101010 / #202020)" in \
        res[f"assets/{NS}/models/item/stray_spawn_egg.json"][1]
    ghost = res[f"assets/{NS}/models/item/ghost_spawn_egg.json"][1]
    assert "registered as 'ghost'" in ghost and "colours" not in ghost.split(".")[0]
    assert "were not read from this jar's bytecode" in res[f"assets/{NS}/models/item/nocode_spawn_egg.json"][1]

    loot = res[f"data/{NS}/loot_tables/entities/bear.json"]
    assert loot[0] == "entity"
    assert loot[1].startswith("loot table of the entity registered as 'bear' in com.example.mobs.ModEntities, "
                              "MobCategory CREATURE, hitbox 1.4 x 1.4 blocks (Java's default table "
                              "entities/<name>, EntityType#getDefaultLootTable)")
    assert res[f"data/{NS}/loot_table/entities/moth.json"][0] == "entity"
    # Nothing ships for any of it.
    assert not [p for p in result.files if "spawn_egg" in p or "loot_tables/entities" in p]
    # A table named after no registered entity is not claimed: it stays unowned.
    assert f"data/{NS}/loot_tables/entities/bear_variant.json" not in result.consumed
    assert f"data/{NS}/loot_tables/entities/bear_variant.json" not in res


def test_without_classes_eggs_are_still_entity_residue_and_loot_tables_unclaimed(tmp_path):
    result = convert_all(_mod(tmp_path, classes=False))
    res = _residue(result)
    assert res[f"assets/{NS}/models/item/bear_spawn_egg.json"][0] == "entity"
    assert f"data/{NS}/loot_tables/entities/bear.json" not in result.consumed


def test_vanilla_entity_tables_in_the_jar_are_not_claimed(tmp_path):
    _write(tmp_path / "data" / "minecraft" / "loot_tables" / "entities" / "bear.json", {"pools": []})
    mod = SourceMod(root=tmp_path, namespace="minecraft", classes=ClassIndex.from_source(CLASSES))
    result = entity_loot.convert(mod)
    assert (result.unhandled, result.consumed) == ([], set())


def test_the_agent_skips_entity_residue():
    assert "entity" in SKIP_KINDS


# --- Alex's Mobs (optional corpus) ---------------------------------------------

@pytest.mark.realmods
def test_alexs_mobs_entities_and_eggs_read_from_its_bytecode(tmp_path):
    mod = next(m for m in corpus.load() if m.name == "alexs_mobs")
    jar = corpus.cached(mod)
    if jar is None:
        pytest.skip("alexs_mobs not cached (portkit corpus fetch)")
    code = entities.read(ClassIndex.from_source(jar))
    # javap -c AMEntityRegistry: 116 DEF_REG.register calls in <clinit>, each
    # lambda `EntityType$Builder.m_20704_(factory, MobCategory.X).m_20699_(w, h)`.
    assert len(code.entities) == 116
    assert all(e.category and e.size for e in code.entities.values())
    grizzly = code.entities["grizzly_bear"]  # lambda$static$0: CREATURE, 1.6f, 1.8f
    assert (grizzly.category, grizzly.size) == ("CREATURE", pytest.approx((1.6, 1.8)))
    # javap -c AMItemRegistry: 89 `new ForgeSpawnEggItem(AMEntityRegistry.X, int, int, ...)`
    # in initSpawnEggs lambdas, every one read.
    assert len(code.eggs) == 89
    assert all(e.entity in code.entities and e.colours for e in code.eggs.values())
    egg = code.eggs["spawn_egg_grizzly_bear"]
    assert (egg.entity, egg.colours) == ("grizzly_bear", (6896172, 9920836))  # ldc int 6896172 / 9920836
    triops = code.eggs["spawn_egg_triops"]  # lambda$initSpawnEggs$238: 9861460 / 13267280
    assert (triops.entity, triops.colours) == ("triops", (9861460, 13267280))
