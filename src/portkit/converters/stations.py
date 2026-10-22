"""Station runtimes: recipe data tables driven by a fixed Bedrock script (#177).

Some mod recipes run on a block whose behaviour is Java code: Farmer's
Delight's cutting board takes an item, is hit with the right tool, and drops
several outputs, some by chance. The recipe JSON carries everything that
varies (ingredient, tool, results, chances, sound); what doesn't vary is the
interaction, and that is the same for every recipe of the type.

So the converter splits it the same way (docs/decisions.md, 2026-10-13):

* **Data table, generated.** Every recipe of the type becomes one entry in a
  JavaScript data module in the behavior pack
  (``scripts/portkit/data/<namespace>_<station>.js``), written from the recipe
  JSON deterministically: items and tags resolved through the same machinery
  the crafting recipes use (:class:`portkit.converters.tags.TagResolver`, load
  conditions decided by :mod:`portkit.conditions` before a recipe gets here).
  A recipe that names anything this conversion can't state exactly stays
  residue (``station_recipe``) with the reason; nothing is narrowed or guessed.
* **Runtime, fixed.** A hand-written script, checked into the package under
  ``portkit/runtime/`` and copied verbatim, registers a block custom component
  that implements the interaction as the mod's own code does (cited per line
  in the script). It is the same file for every mod; only the table differs.
* **Block, from the jar.** The station block is the mod's own blockstate and
  model, converted by :mod:`portkit.converters.blocks` with the placement rule
  and shape read from the mod's block code, and given the runtime's custom
  component by its station converter.

Every station belongs to an adapter (#245): Farmer's Delight's
(:mod:`portkit.adapters.farmersdelight`) and Waystones'
(:mod:`portkit.adapters.waystones`) register a ``station`` hook
(:class:`portkit.adapters.StationHooks`), and each seam here asks every hook in
registry order. What stays core is that loop, the shared helpers, and the
entry script :data:`ENTRY` that wires every station that shipped.

Script API: ``@minecraft/server`` 2.0.0, released with Bedrock 1.21.90, the
release that made custom components v2 (a namespaced component key in the
block JSON, registered in ``system.beforeEvents.startup``) available from block
format 1.21.90 (minecraft.net, "Minecraft 1.21.90 Bedrock Changelog";
learn.microsoft.com, Scripting V2 Overview and Introducing Custom Components).
A block carrying the component is written at that format, so the pack's engine
floor (:func:`portkit.pack.engine_floor`) rises to 1.21.90 with it, and
:func:`portkit.pack.write_tree` adds the script module and the dependency only
when a pack ships :data:`ENTRY`.
"""
from __future__ import annotations

import json

from ..conditions import LoadContext
from ..model import ConversionResult, SourceMod
from .lang import _translate_key
from .station_kit import (  # noqa: F401  (re-exported: the station converters import them from here)
    BEDROCK_TOOL_TAGS,
    ENGINE_FLOOR,
    ENTRY,
    FORMS,
    KIT_FILES,
    RUNTIME_DIR,
    SCRIPT_FORMAT,
    SCRIPT_MODULE,
    SCRIPT_VERSION,
    VANILLA_SOUNDS,
    DerivedTexture,
    FacingBlock,
    Overlay,
    js_module,
    runtime_source,
)

_RUNTIME_DIR = RUNTIME_DIR
_js_module = js_module


def _adapter_stations() -> list:
    """The adapters' station hooks (#245), in registry order."""
    from ..adapters import station_hooks

    return station_hooks()


def station_recipe_types() -> tuple[frozenset, frozenset]:
    """Recipe types a station writes into its data table, and recipe types a
    station also reads while they convert as usual (the stove's campfire
    recipes), over every adapter's hook (:func:`portkit.converters.recipes.convert`
    defers both)."""
    own: frozenset = frozenset()
    shared: frozenset = frozenset()
    for hooks in _adapter_stations():
        own |= hooks.recipe_types
        shared |= hooks.shared_types
    return own, shared


def station_blocks(mod: SourceMod) -> dict[str, FacingBlock]:
    """Blocks of ``mod`` that a station runtime makes work, by blockstate name,
    each adapter's in registry order."""
    blocks: dict[str, FacingBlock] = {}
    for hooks in _adapter_stations():
        blocks.update(hooks.blocks(mod))
    return blocks


def station_loot(mod: SourceMod) -> set[str]:
    """Block loot tables (names under loot_table/blocks/) a station reads."""
    names: set[str] = set()
    for hooks in _adapter_stations():
        names = names | hooks.loot_names(mod)
    return names


def station_textures(mod: SourceMod) -> list[DerivedTexture]:
    """Block textures a station's overlay wears, made from the jar's own
    (the sharestones' tinted runes, #178)."""
    return [t for hooks in _adapter_stations() for t in hooks.derived_textures(mod)]


def station_lang_keys(mod: SourceMod) -> set[str]:
    """Java lang keys a station runtime shows itself (#178 waystone menu)."""
    keys: set[str] = set()
    for hooks in _adapter_stations():
        keys |= hooks.lang_keys(mod)
    return keys


def _loot_name(rel: str) -> str:
    return rel.rsplit("/", 1)[-1][:-len(".json")]


def _lang_key(mod: SourceMod, java_key: str) -> str | None:
    """The Bedrock .lang key for a Java key the jar's en_us.json defines, else None."""
    path = mod.assets / "lang" / "en_us.json"
    try:
        entries = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (json.JSONDecodeError, OSError):
        return None
    if java_key not in entries:
        return None
    return _translate_key(java_key, mod.namespace)


def convert(mod: SourceMod, deferred: list[tuple[str, dict]], files: dict,
            context: LoadContext, loot: list[tuple[str, dict]] | None = None,
            extra_entries: list[str] | None = None) -> ConversionResult:
    """Each station's data table and runtime for the recipes ``deferred`` holds.

    ``deferred`` is (source path, recipe) for every recipe of a station type
    (:func:`station_recipe_types`) whose load conditions passed; ``loot`` is
    (source path, table) for the block loot tables the loot converter left to
    a station (:func:`station_loot`). Each adapter's hook, in registry order,
    gets the recipes of its own types and the loot tables it named, and
    returns its files and its line of the entry. The entry :data:`ENTRY`
    imports every station that shipped, then ``extra_entries`` (the guide
    book viewer's wiring, :func:`portkit.adapters.citadel.books.convert`).
    """
    result = ConversionResult()
    entries: list[str] = []
    for hooks in _adapter_stations():
        types = hooks.recipe_types | hooks.shared_types
        own = [d for d in deferred if d[1].get("type") in types]
        names = hooks.loot_names(mod)
        own_loot = [d for d in loot or [] if _loot_name(d[0]) in names]
        converted, entry = hooks.convert(mod, own, own_loot, files, context)
        result = result.merge(converted)
        if entry:
            entries.append(entry)
    if entries:
        for name in KIT_FILES:
            result.files[f"{_RUNTIME_DIR}/{name}"] = runtime_source(name)
    # Facing-and-boolean blocks whose use flips a state (blocks.convert wrote
    # the table and the fixed runtime) join the same entry.
    from .blocks import toggle_table_path
    if toggle_table_path(mod.namespace) in files:
        entries.append(
            'import { registerToggles } from "./toggle.js";\n'
            f'import toggleTable from "./data/{mod.namespace}_toggle.js";\n'
            "registerToggles(toggleTable);\n"
        )
    # Doors (#296: blocks.convert wrote the table and the fixed runtime).
    from .doors import door_table_path
    if door_table_path(mod.namespace) in files:
        entries.append(
            'import { registerDoors } from "./door.js";\n'
            f'import doorTable from "./data/{mod.namespace}_doors.js";\n'
            "registerDoors(doorTable);\n"
        )
    # Trapdoors (#296: blocks.convert wrote the table and the fixed runtime).
    from .trapdoors import table_path as trapdoor_table_path
    if trapdoor_table_path(mod.namespace) in files:
        entries.append(
            'import { registerTrapdoors } from "./trapdoor.js";\n'
            f'import trapdoorTable from "./data/{mod.namespace}_trapdoors.js";\n'
            "registerTrapdoors(trapdoorTable);\n"
        )
    # Pressure plates (#296: blocks.convert wrote the table and the fixed runtime).
    from .plates import table_path as plate_table_path
    if plate_table_path(mod.namespace) in files:
        entries.append(
            'import { registerPressurePlates } from "./pressure_plate.js";\n'
            f'import plateTable from "./data/{mod.namespace}_pressure_plates.js";\n'
            "registerPressurePlates(plateTable);\n"
        )
    # Fence gates (#367: blocks.convert wrote the table and the fixed runtime).
    from .fence_gates import table_path as gate_table_path
    if gate_table_path(mod.namespace) in files:
        entries.append(
            'import { registerFenceGates } from "./fence_gate.js";\n'
            f'import gateTable from "./data/{mod.namespace}_fence_gates.js";\n'
            "registerFenceGates(gateTable);\n"
        )
    # Buttons (#280: blocks.convert wrote the table and the fixed runtime).
    from .buttons import table_path as button_table_path
    if button_table_path(mod.namespace) in files:
        entries.append(
            'import { registerButtons } from "./button.js";\n'
            f'import buttonTable from "./data/{mod.namespace}_buttons.js";\n'
            "registerButtons(buttonTable);\n"
        )
    # Drops a loot modifier adds to vanilla blocks (#280: loot_modifiers.convert
    # wrote the table and the fixed runtime).
    from .loot_modifiers import table_path as drops_table_path
    if drops_table_path(mod.namespace) in files:
        entries.append(
            'import { registerBlockDrops } from "./block_drops.js";\n'
            f'import blockDropsTable from "./data/{mod.namespace}_block_drops.js";\n'
            "registerBlockDrops(blockDropsTable);\n"
        )
    entries.extend(extra_entries or [])
    if entries:
        result.files[ENTRY] = (
            "// Generated by portkit: wires each station's data table to its fixed runtime.\n"
            + "".join(entries)
        )
    return result


def _shipped_sounds(files: dict) -> set[str]:
    """Sound events this pack's sound_definitions.json defines."""
    defs = files.get("sounds/sound_definitions.json")
    if not isinstance(defs, dict):
        return set()
    return set(defs.get("sound_definitions") or {})
