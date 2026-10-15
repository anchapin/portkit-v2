"""The generic station kit (#245): what every scripted station shares.

A station is a block whose behaviour is Java code, carried to Bedrock as a
generated data table read by a fixed, hand-written runtime script
(:mod:`portkit.converters.stations` says how; docs/decisions.md 2026-10-13).
This module holds the parts of that pattern that name no mod, so any adapter
can build a station from them (#239's scripted-machine and form-GUI
templates start here):

* the Script API pins and the entry script's path (:data:`ENTRY`);
* the block specs a station hands :mod:`portkit.converters.blocks`:
  :class:`FacingBlock`, its tinted :class:`Overlay` and the
  :class:`DerivedTexture` baked for it;
* vanilla lookups station recipes need (:data:`BEDROCK_TOOL_TAGS`,
  :data:`VANILLA_SOUNDS`);
* :func:`runtime_source` and :func:`js_module` (fixed script, generated
  table), and :data:`KIT_FILES`, the namespace-free runtime helpers
  (``portkit/runtime/station_core.js``, ``station_storage.js``) shipped beside
  every station runtime, and :data:`FORMS`, the form helper a runtime that
  shows ``@minecraft/server-ui`` forms ships.

Moved out of ``stations.py`` unchanged (the names stay importable from there).
"""
from __future__ import annotations

import json
import posixpath
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import PurePosixPath
from typing import Mapping

SCRIPT_MODULE = "@minecraft/server"
SCRIPT_VERSION = "2.0.0"
# Block JSON format that reads a namespaced custom component key (custom
# components v2): 1.21.90 (minecraft.net 1.21.90 Bedrock changelog, "Custom
# components v2 is available in JSON versions 1.21.90 and higher").
SCRIPT_FORMAT = "1.21.90"
ENGINE_FLOOR = (1, 21, 90)
ENTRY = "scripts/portkit/main.js"
RUNTIME_DIR = "scripts/portkit"

# The kit's runtime helpers, shipped (verbatim) whenever a station runtime is:
# station_core.js is pure (storage keys, the side step, the heat rule, the
# destroy command, the held-item use timer), station_storage.js the Bedrock
# side (stored stacks, giving and dropping, sounds, block views, records).
KIT_FILES = ("station_core.js", "station_storage.js")
# The form helper (show with the UserBusy retry), shipped by a runtime that
# shows forms.
FORMS = "forms.js"


@dataclass(frozen=True)
class Overlay:
    """A model the mod's client code draws over a station block, tinted
    (Waystones' waystone, sharestone and portstone runes, #178): Java renders
    it from a block entity renderer, so no blockstate names it; Bedrock gets it
    as extra bones of the block's own geometry wearing a texture baked at
    convert time (:class:`DerivedTexture`) in the colour the code multiplies it
    by (or the jar's own texture, for a colour of white).

    ``model`` is the Java model and ``texture`` the one texture reference all
    its faces must draw. ``offsets`` maps each value of the station's state to
    that block's height in the model (pixels: the upper half of a two-block
    model is 16), so each element lands in the block it lies in. ``turns`` is
    the extra Java y turn (degrees, clockwise from above) the overlay takes in
    the block model's frame at each facing, where the renderer's rotation
    differs from the blockstate's. ``block_texture`` is the Bedrock texture key
    of the placed block's overlay, ``block_material`` its other material
    fields; ``item_texture`` (with ``item_value`` and ``item_turn``) is the
    item's, shown through ``minecraft:item_visual``, or None to leave the item
    as the block draws it.
    """

    name: str
    model: str
    texture: str
    offsets: dict
    turns: dict
    block_texture: str
    block_material: dict
    item_texture: str | None
    item_material: dict
    item_value: str
    item_turn: int
    sources: tuple[str, ...]
    # A boolean Bedrock state (default false) the overlay shows only when on,
    # set by the station's runtime (a waystone's runes once it is activated),
    # or None for an overlay always drawn.
    shown_by: str | None = None


@dataclass(frozen=True)
class DerivedTexture:
    """A block texture made at convert time from one of the jar's own: every
    pixel's red, green and blue multiplied by ``rgb`` (0xRRGGBB), as Java's
    renderer multiplies a tinted quad's texture by its vertex colour; alpha
    kept. ``source`` is the PNG's path below the mod root and ``subpath`` the
    Bedrock path below textures/blocks/ (its index key follows from it)."""

    source: str
    subpath: str
    rgb: int
    # An animation strip cut down (Waystones' warp portal, #178): the jar's
    # frames are ``frame[0]`` pixels tall and each is cut to its rows
    # ``frame[1]``..``frame[2]`` (one Bedrock flipbook frame), stacked in order.
    # None keeps the image as it is.
    frame: tuple[int, int, int] | None = None
    # A Bedrock flipbook for the result (textures/flipbook_textures.json):
    # Java's frametime in ticks. None for a still texture.
    ticks_per_frame: int | None = None


@dataclass(frozen=True)
class FacingBlock:
    """A station block whose facing and shape the mod's block code sets.

    ``placement_offset`` is the y_rotation_offset of Bedrock's
    placement_direction trait that makes ``minecraft:cardinal_direction`` equal
    Java's ``facing``: Bedrock's state is the player's facing at offset 0, so a
    block that faces the player (``getHorizontalDirection().getOpposite()``)
    takes 180 (vendored block_placement_direction schema, y_rotation_offset).
    ``box`` is the block's Java ``SHAPE`` as a Bedrock collision and selection
    box (origin/size in pixels, centred on x and z).
    """

    name: str
    placement_offset: int
    box: dict
    sources: tuple[str, ...]
    # A second state the mod's code sets beside facing (the cooking pot's
    # ``support``): its Java name, its values (Java's default first) and the
    # Bedrock custom state that carries it. None for a facing-only block.
    java_state: str | None = None
    values: tuple[str, ...] = ()
    state: str | None = None
    # Block components the mod's code gives one value of that state (the
    # stove's light level while lit), by value. None when there are none.
    value_components: dict | None = None
    # Whether the Java state is an IntegerProperty (a feast's ``servings``):
    # Bedrock then gets an integer state, as vanilla's cake ``bite_counter``.
    int_state: bool = False
    # A tinted model the mod's renderer draws over the block (Overlay), or None.
    overlay: Overlay | None = None
    # False for a block with no facing at all (Waystones' warp plate: its
    # blockstate is ``status`` alone): no placement trait, one bone per model.
    facing: bool = True
    # Leave out model elements with a tinted face (``tintindex``): their colour
    # is the mod's colour handler's, which the block can't carry. A note names them.
    drop_tinted: bool = False
    # Per Java value, faces drawing one part of a texture redrawn from a
    # derived texture (:class:`DerivedTexture` with ``frame``): value ->
    # (the Java texture, the derived texture's Java-style reference, the face
    # uv drawn, the uv it becomes). The warp portal's halves each draw half of
    # one 16 x 32 animation frame.
    slices: dict | None = None
    # Fields every material instance of the block takes (the warp portal's
    # translucent render layer, set in the mod's client code). None for none.
    material: dict | None = None
    # Per Java facing, the collision and selection box (origin/size in
    # pixels) when Java's shape differs by facing and the block has no other
    # state to turn it with (Waystones' fleeting memorial: a thin slab off the
    # centre). None when ``box`` holds for every facing.
    facing_boxes: dict | None = None


# Bedrock's own item tag with the same meaning as a Java tool tag
# (learn.microsoft.com, Vanilla Item Tags - Tool tags). The runtime also
# accepts any item carrying it, as Java accepts any mod's axe in
# minecraft:axes.
BEDROCK_TOOL_TAGS = {
    "minecraft:axes": "minecraft:is_axe",
    "minecraft:hoes": "minecraft:is_hoe",
    "minecraft:pickaxes": "minecraft:is_pickaxe",
    "minecraft:shovels": "minecraft:is_shovel",
    "minecraft:swords": "minecraft:is_sword",
    "c:tools/shear": "minecraft:is_shears",
}

# Java vanilla sound event -> the Bedrock vanilla sound event that plays exactly
# the same audio files: Java's from misode/mcmeta 1.21.1-assets
# (451045f2, assets/minecraft/sounds.json; same files in 26.1.2-assets),
# Bedrock's from Mojang/bedrock-samples (46ba6ea9,
# resource_pack/sounds/sound_definitions.json). Where several Bedrock events
# share the files, the one with the same verb (break -> dig., place -> place.,
# hit -> hit.). Java's per-file volume/pitch variants (item.axe.strip plays at
# 0.9, some at pitch 0.85) are not in Bedrock's event.
VANILLA_SOUNDS = {
    "minecraft:item.axe.strip": "use.wood",
    "minecraft:block.metal.break": "dig.stone",
    "minecraft:entity.sheep.shear": "mob.sheep.shear",
    "minecraft:block.wood.break": "dig.wood",
    "minecraft:block.wood.place": "place.wood",
    "minecraft:block.wood.hit": "hit.wood",
    "minecraft:entity.item.break": "random.break",
    # Cooking pot (#177): the handle toggle and serving a portion.
    "minecraft:block.lantern.place": "block.lantern.place",
    "minecraft:item.armor.equip_generic": "armor.equip_generic",
}


def runtime_source(name: str) -> str:
    """A fixed runtime script, verbatim from the package."""
    return resources.files("portkit.runtime").joinpath(name).read_text(encoding="utf-8")


def js_module(header: str, table: dict) -> str:
    """A generated data table as a JavaScript module: ``header`` comment lines, then the table as JSON."""
    body = json.dumps(table, indent=1, sort_keys=True, ensure_ascii=False)
    return f"{header}\nexport default {body};\n"


_RELATIVE_IMPORT = re.compile(r'^\s*import\s[^;]*?\sfrom\s+"(\./[^"]+)";?\s*$|^\s*import\s+"(\./[^"]+)";?\s*$',
                              re.MULTILINE)


def unresolved_imports(files: Mapping[str, object]) -> list[str]:
    """Relative script imports a pack's files don't satisfy: ``"<script> -> <path>"``
    for each ``import ... from "./x.js"`` in a shipped ``scripts/**.js`` whose
    target path is not shipped. ``files`` maps behavior-pack paths to content."""
    missing = []
    for path in sorted(files):
        text = files[path]
        if not (path.startswith("scripts/") and path.endswith(".js") and isinstance(text, str)):
            continue
        base = PurePosixPath(path).parent
        for m in _RELATIVE_IMPORT.finditer(text):
            target = posixpath.normpath(str(base / (m.group(1) or m.group(2))))
            if target not in files:
                missing.append(f"{path} -> {target}")
    return missing
