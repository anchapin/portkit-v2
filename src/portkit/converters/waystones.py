"""Waystones: waystone blocks + a fixed Script API teleport runtime (#178).

The station pattern of #177 (:mod:`portkit.converters.stations`,
docs/decisions.md) applied to Waystones' waystone: the converter writes a
generated data table (``scripts/portkit/data/waystones_waystone.js``) read by a
hand-written runtime (``portkit/runtime/waystone.js`` and its node-tested
logic ``waystone_core.js``) that does what Waystones' Java code does, cited per
line there. It covers the ten waystone blocks (``WaystoneBlock``): placing
one (both halves), activating it, naming it, the menu of the waystones a player
has activated, and the teleport with its experience cost; and the fifteen
coloured sharestones (``SharestoneBlock``), which take the same placement,
naming, breaking and teleport but list every sharestone of their own colour
(one shared network per colour, nothing to activate); and the sixteen
portstones (``PortstoneBlock``), which are no waystone themselves: using one
lists its colour's sharestones (white: the player's activated waystones) and
teleports from wherever the player stands; and the warp plate
(``WarpPlateBlock``), which attunes a dormant shard to itself and teleports
whatever stands on it to the plate its attuned shard names. Warp portals,
fleeting memorials and the warp stone, scrolls and feather keep their residue.

Where each value comes from (no fabrication, #87):

* **Which blocks**: Waystones' own ``waystones:waystones`` block tag (data),
  each a block ``ModBlocks`` registers as a ``WaystoneBlock``
  (:data:`WAYSTONE_BLOCKS`, cited), its ``waystones:sharestones`` tag,
  each a ``SharestoneBlock`` (:data:`SHARESTONE_BLOCKS`, cited), and its
  ``waystones:portstones`` tag, each a ``PortstoneBlock``
  (:data:`PORTSTONE_BLOCKS`, cited); the blockstate is ``facing`` x ``half``.
  The warp plate is the block ``ModBlocks`` registers as ``WarpPlateBlock``
  (:data:`WARP_PLATE_BLOCKS`); its blockstate is ``status`` alone.
* **Which network**: a waystone's type is ``waystones:waystone`` (reached by
  activating it); a sharestone's is its colour's
  (``WaystoneTypes.getSharestone``), and its menu lists every sharestone of
  that type (``PlayerWaystoneManager#getTargetsForWaystoneType``). A
  portstone has no type of its own: it lists the targets of its colour's
  sharestone type, or of the waystone type when its colour has no sharestone
  (``PortstoneBlock#getTargetWaystoneType``).
* **Shape, facing, the two halves**: ``WaystoneBlock`` / ``SharestoneBlock`` /
  ``WaystoneBlockBase`` (shapes, ``getStateForPlacement``, ``setPlacedBy``,
  ``playerWillDestroy``).
* **Breaking drops**: the jar's loot table (one pool, the lower half only).
* **The experience cost**: the ``warpRequirements`` config default, parsed
  here the way ``RequirementModifierParser`` parses it, with
  ``enableCosts`` / ``enableCooldowns``; values from
  ``portkit/data/waystones_config_defaults.json`` (cited per value). Each
  modifier's conditions are decided for this runtime (:data:`FIXED_CONDITIONS`:
  a teleport here always starts at a waystone and ends at one with the default
  ``ACTIVATION`` visibility, or at a sharestone and ends at one of its colour);
  what is left is evaluated by the runtime.
  An unknown condition or function means no runtime (residue), never a guess.
* **Runes**: the jar's ``block/sharestone_runes``, ``block/portstone_runes``
  and ``block/waystone_runes`` models, which Java's renderers draw tinted, as
  extra bones of the block's geometry
  (:class:`portkit.converters.stations.Overlay`), on textures baked at
  convert time: a sharestone's and portstone's with the colour's ``DyeColor``
  values (:data:`DYE_COLORS`, cited; texture diffuse colour for the block,
  text colour for the item through ``minecraft:item_visual``), a waystone's
  with its style's rune colour (:data:`WAYSTONE_RUNE_COLORS`), shown through
  :data:`RUNE_STATE` once a player activates it (the runtime sets it).
* **Texts**: the jar's own lang keys (:data:`MESSAGES`), shipped under their
  Java key (:func:`portkit.converters.lang.convert` ``runtime_keys``).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources

from ..conditions import LoadContext
from ..model import ConversionResult, SourceMod, Unhandled
from ..png import decode_rgba
from .stations import (
    SCRIPT_FORMAT,
    SCRIPT_MODULE,
    SCRIPT_VERSION,
    DerivedTexture,
    FacingBlock,
    Overlay,
    _js_module,
    _RUNTIME_DIR,
    runtime_source,
)
from .textures import shortname

NS = "waystones"
STATION = "waystone"
RESIDUE_KIND = "waystone"
HALF_STATE = "waystones:half"
COMPONENT = "waystones:portkit_waystone"
DEFAULTS_DATA = "waystones_config_defaults.json"
TAG = "data/waystones/tags/block/waystones.json"
# ModBlockTags L12 (SHARESTONES); the jar's tag lists the fifteen sharestones.
SHARESTONE_TAG = "data/waystones/tags/block/sharestones.json"
# Vanilla Bedrock's empty loot table, for the upper half (as the feasts' empty
# serving counts; Mojang/bedrock-samples 46ba6ea9 behavior_pack/loot_tables/empty.json).
EMPTY_LOOT = "loot_tables/empty.json"
UI_MODULE = "@minecraft/server-ui"
UI_VERSION = "2.0.0"

REPO = "https://github.com/TwelveIterations/Waystones"
COMMIT = "9d280c1ac8d036516a2927e3d2cad8054e491074"  # tag v21.1.46
VERSIONS = {"fabric": "21.1.46"}


def _src(path: str, line: str) -> str:
    return f"{REPO}/blob/{COMMIT}/common/src/main/java/net/blay09/mods/waystones/{path}#L{line}"


# The blocks ModBlocks registers as WaystoneBlock (ModBlocks.java L70-L85,
# all with defaultProperties(), L112). Sharestones, portstones, the warp plate,
# the warp portal and the fleeting memorial are other classes.
WAYSTONE_BLOCKS = (
    "waystone", "mossy_waystone", "sandy_waystone", "deepslate_waystone", "blackstone_waystone",
    "end_stone_waystone", "red_nether_bricks_waystone", "purpur_waystone", "prismarine_waystone",
    "mud_bricks_waystone",
)
BLOCK_SOURCES = (
    _src("block/ModBlocks.java", "70-L85"),
    # LOWER_SHAPE / UPPER_SHAPE; getShape by HALF.
    _src("block/WaystoneBlock.java", "44-L57"),
    # FACING = getHorizontalDirection().getOpposite(), needs a replaceable block above.
    _src("block/WaystoneBlockBase.java", "160-L173"),
)

# The colours ModBlocks registers a SharestoneBlock for (sharestoneColors
# L35-51: every dye colour but white), each as <colour>_sharestone (L96-100),
# in that order; WaystoneTypes.SHARESTONES L16-32 lists the same types.
SHARESTONE_COLORS = (
    "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray", "light_gray", "cyan", "purple",
    "blue", "brown", "green", "red", "black",
)
SHARESTONE_BLOCKS = tuple(f"{color}_sharestone" for color in SHARESTONE_COLORS)
SHARESTONE_SOURCES = (
    _src("block/ModBlocks.java", "35-L51"),
    _src("block/ModBlocks.java", "96-L100"),
    # LOWER_SHAPE / UPPER_SHAPE; getShape by HALF.
    _src("block/SharestoneBlock.java", "40-L52"),
    _src("block/SharestoneBlock.java", "69-L72"),
    _src("block/WaystoneBlockBase.java", "160-L173"),
)
# The colours ModBlocks registers a PortstoneBlock for (portstoneColors
# L16-33: every dye colour, white first), each as <colour>_portstone (L90-94).
PORTSTONE_COLORS = ("white", *SHARESTONE_COLORS)
PORTSTONE_BLOCKS = tuple(f"{color}_portstone" for color in PORTSTONE_COLORS)
# ModBlockTags L13 (PORTSTONES); the jar's tag lists the sixteen portstones.
PORTSTONE_TAG = "data/waystones/tags/block/portstones.json"
PORTSTONE_SOURCES = (
    _src("block/ModBlocks.java", "16-L33"),
    _src("block/ModBlocks.java", "90-L94"),
    # LOWER_SHAPES / UPPER_SHAPES by facing; getShape by HALF.
    _src("block/PortstoneBlock.java", "47-L107"),
    _src("block/PortstoneBlock.java", "121-L125"),
    _src("block/WaystoneBlockBase.java", "160-L173"),
)
# A waystone's type (WaystoneTypes.WAYSTONE L10; WaystoneBlockEntity) and a
# sharestone's (WaystoneTypes.getSharestone L34-40 via
# SharestoneBlockEntity#getWaystoneType L30-34).
WAYSTONE_TYPE = f"{NS}:waystone"


def waystone_type(name: str) -> str:
    """The Java waystone type of the block ``name`` (a WAYSTONE_BLOCKS,
    SHARESTONE_BLOCKS or WARP_PLATE_BLOCKS entry)."""
    if name in WARP_PLATE_BLOCKS:
        return WARP_PLATE_TYPE
    return f"{NS}:{name}" if name in SHARESTONE_BLOCKS else WAYSTONE_TYPE


def portstone_target(name: str) -> str:
    """The waystone type a portstone ``name`` lists (PortstoneBlock#getTargetWaystoneType
    L145-147: its colour's sharestone, WaystoneTypes.getSharestone L34-40, which
    white has none of, so a white portstone lists waystones)."""
    color = name[:-len("_portstone")]
    return f"{NS}:{color}_sharestone" if f"{color}_sharestone" in SHARESTONE_BLOCKS else WAYSTONE_TYPE


# The block ModBlocks registers as a WarpPlateBlock (ModBlocks.java L86, with
# defaultProperties(), L112); its waystone type is WaystoneTypes.WARP_PLATE (L11,
# WarpPlateBlockEntity#getWaystoneType L87-89).
WARP_PLATE_BLOCKS = ("warp_plate",)
WARP_PLATE_TYPE = f"{NS}:warp_plate"
# WarpPlateBlock.STATUS (L83): WarpPlateStatus's values in enum order (L61-68),
# serialized lower-case (L70-73); EMPTY is the default state (L87-89).
STATUS_STATE = f"{NS}:status"
WARP_PLATE_STATUSES = ("empty", "idle", "attuning", "warping", "warping_invalid", "redstone_disabled", "locked")
# SHAPE (L78-81): box(0, 0, 0, 16, 1, 16) + box(3, 1, 3, 13, 2, 13), whose
# bounding box is 16 x 2 x 16 pixels (the same at every turn; the block has no facing).
WARP_PLATE_BOX = {"origin": [-8, 0, -8], "size": [16, 2, 16]}
WARP_PLATE_SOURCES = (
    _src("block/ModBlocks.java", "86"),
    _src("block/WarpPlateBlock.java", "61-L106"),
)
WARP_PLATE_COMPONENT = f"{NS}:portkit_warp_plate"
# The warp plate's shard items (ModItems L44-47): which is the dormant shard a
# plate attunes, the attuned shard it makes, and the deepslate shard that locks
# it. The shards a plate takes are the jar's waystones:warp_shards item tag
# (ModItemTags.WARP_SHARDS L16); the single-use ones its
# waystones:single_use_warp_shards tag (L17).
SHARD_ROLES = {"dormant": "dormant_shard", "attuned": "attuned_shard", "locked": "deepslate_shard"}
WARP_SHARDS_TAG = "data/waystones/tags/item/warp_shards.json"
SINGLE_USE_SHARDS_TAG = "data/waystones/tags/item/single_use_warp_shards.json"
# Item stack sizes the shard classes set in code (the item converter reads no
# code, so it writes 64): AttunedShardItem L6 stacksTo(1),
# CrumblingAttunedShardItem L17 stacksTo(4). A non-stackable attuned shard is
# also what lets the runtime keep its attunement on the stack (Script API
# ItemStack.setDynamicProperty works only on non-stackable items).
SHARD_STACK_SIZES = {"attuned_shard": 1, "crumbling_attuned_shard": 4}
SHARD_STACK_SOURCES = (
    _src("item/AttunedShardItem.java", "6"),
    _src("item/CrumblingAttunedShardItem.java", "17"),
)
# WarpPlateBlockEntity#getMaxAttunementTicks L377-379: a dormant shard attunes
# after 30 ticks.
ATTUNEMENT_TICKS = 30
# The item dynamic property holding an attuned shard's waystone (Java's
# ModComponents.attunement data component, AbstractAttunedShardItem L55-66).
ATTUNEMENT_PROPERTY = f"{NS}:portkit_attunement"
# ChatFormatting.DARK_RED, the style of every warp plate message
# (WarpPlateBlockEntity L212-220, L284-290): section-sign code "4" (Minecraft
# 1.21.1 ChatFormatting), the same colour code on Bedrock.
ERROR_STYLE = "\u00a74"
WARP_PLATE_MESSAGES = {
    # WarpPlateBlockEntity#serverTick L212-220 (action bar).
    "no_target": "chat.waystones.warp_plate_has_no_target",
    "invalid_target": "chat.waystones.warp_plate_has_invalid_target",
}
WARP_PLATE_RUNTIME_SOURCES = (
    _src("block/WarpPlateBlock.java", "108-L113"),
    _src("block/WarpPlateBlock.java", "163-L201"),
    _src("block/entity/WarpPlateBlockEntity.java", "60-L89"),
    _src("block/entity/WarpPlateBlockEntity.java", "105-L249"),
    _src("block/entity/WarpPlateBlockEntity.java", "265-L379"),
    _src("block/entity/WarpPlateBlockEntity.java", "381-L434"),
    _src("block/WaystoneBlockBase.java", "128-L133"),
    _src("core/WaystoneTeleportManager.java", "141-L174"),
    _src("core/WaystoneTeleportManager.java", "245-L284"),
    _src("core/WaystonePermissionManager.java", "78-L81"),
    _src("item/ModItems.java", "44-L47"),
    _src("mixin/EntityMixin.java", "17-L28"),
)
# The config values only the warp plate reads.
WARP_PLATE_CONFIG = ("general.warpPlateUseTime", "general.warpPlateCooldownTime", "teleports.entityDenyList")


# -- runes -------------------------------------------------------------------------
# A waystone's, sharestone's and portstone's runes are drawn by code, not by
# their block models (whose faces have no tintindex). Each family's block
# entity renderer draws its own model (ModModels L11-L17:
# block/waystone_runes, block/sharestone_runes, block/portstone_runes) from
# the lower half (WaystoneRenderer L29-31, SharestoneRenderer L34-36,
# PortstoneRenderer L30-32), turned by FACING.toYRot() about the block's
# centre (WaystoneRenderer L39-42, SharestoneRenderer L42-44, PortstoneRenderer
# L36-39), through RuneRenderUtil (L12-19): cutout, a colour multiplied into the
# faces that have a tintindex, at full brightness unless the client config
# disableTextGlow is set (default false, WaystonesConfigData L201).
# * sharestone, portstone: the colour's getTextureDiffuseColor()
#   (SharestoneRenderer L49, PortstoneRenderer L43); their item models
#   (item/sharestone, item/portstone) tint the same runes with getTextColor()
#   (ModRenderers L27-28, L31-32, the item colour handlers).
# * waystone: its WaystoneStyle's rune colour (WaystoneRenderer L43-47:
#   WaystoneStyles.getStyle(block).getRuneColor(), 0xFFFFFFFF without a style),
#   and only while the client's player has activated that waystone
#   (WaystoneRenderer L33-37, PlayerWaystoneManager#isWaystoneActivated). Its
#   item model (item/waystone) has no runes.
RUNE_SOURCES = {
    "sharestone": (
        _src("client/render/SharestoneRenderer.java", "31-L53"),
        _src("client/ModRenderers.java", "25-L28"),
    ),
    "portstone": (
        _src("client/render/PortstoneRenderer.java", "26-L47"),
        _src("client/ModRenderers.java", "29-L32"),
    ),
    "waystone": (
        _src("client/render/WaystoneRenderer.java", "26-L51"),
        _src("api/WaystoneStyle.java", "11-L28"),
        _src("api/WaystoneStyles.java", "16-L25"),
        _src("core/PlayerWaystoneManager.java", "32-L34"),
    ),
}
RUNE_COMMON_SOURCES = (
    _src("client/render/RuneRenderUtil.java", "12-L20"),
    _src("client/ModModels.java", "11-L17"),
    _src("config/WaystonesConfigData.java", "199-L202"),
)
# A waystone style's rune colour (0xAARRGGBB; RuneRenderUtil L13-15 reads only
# red, green and blue): WaystoneStyles L19 BLACKSTONE withRuneColor(0xFF993333),
# L21 END_STONE withRuneColor(0xFF7200FF); every other style keeps
# WaystoneStyle's default 0xFFFFFFFF (WaystoneStyle L11), which multiplies the
# texture by 1, i.e. leaves it as the jar has it.
WAYSTONE_RUNE_COLORS = {"blackstone_waystone": 0x993333, "end_stone_waystone": 0x7200FF}
WAYSTONE_RUNE_DEFAULT = 0xFFFFFF
# The Bedrock state that shows a waystone's runes, turned on by the runtime
# when a player activates the waystone (a Bedrock block looks the same to
# every player, so "activated by the client's player" becomes "activated by
# any player").
RUNE_STATE = f"{NS}:runes"
# DyeColor's (textureDiffuseColor, textColor) per colour, Minecraft 1.21.1 (the
# game Waystones 21.1.46 is built for): the constructor arguments in
# net.minecraft.world.item.DyeColor's static initializer, read from Mojang's
# client jar (piston-data.mojang.com sha1 30c73b1c5da787909b2f73340419fdf13b9def88)
# with Mojang's mappings (client.txt sha1 2244b6f072256667bcd9a73df124d6c58de77992:
# DyeColor -> cti, fields textureDiffuseColor/textColor). The diffuse colours
# match minecraft.wiki "Dye" (color values table).
DYE_COLORS = {
    "white": (0xF9FFFE, 0xFFFFFF),
    "orange": (0xF9801D, 0xFF681F),
    "magenta": (0xC74EBD, 0xFF00FF),
    "light_blue": (0x3AB3DA, 0x9AC0CD),
    "yellow": (0xFED83D, 0xFFFF00),
    "lime": (0x80C71F, 0xBFFF00),
    "pink": (0xF38BAA, 0xFF69B4),
    "gray": (0x474F52, 0x808080),
    "light_gray": (0x9D9D97, 0xD3D3D3),
    "cyan": (0x169C9C, 0x00FFFF),
    "purple": (0x8932B8, 0xA020F0),
    "blue": (0x3C44AA, 0x0000FF),
    "brown": (0x835432, 0x8B4513),
    "green": (0x5E7C16, 0x00FF00),
    "red": (0xB02E26, 0xFF0000),
    "black": (0x1D1D21, 0x000000),
}
DYE_SOURCE = ("Minecraft 1.21.1 client jar (sha1 30c73b1c5da787909b2f73340419fdf13b9def88), "
              "net.minecraft.world.item.DyeColor static initializer (Mojang mappings)")
# Direction#toYRot() is (2D data value & 3) * 90: south 0, west 90, north 180,
# east 270 (Minecraft 1.21.1 Direction, same jar). PoseStack's Axis.YP turn is
# anticlockwise seen from above, a blockstate's y clockwise.
TO_Y_ROT = {"south": 0, "west": 90, "north": 180, "east": 270}
# The placed block's runes: Java draws them through RuneRenderUtil's
# ModelBlockRenderer#renderModel, which puts each quad with brightness 1 (no
# ambient occlusion, no face shading: Minecraft 1.21.1 ModelBlockRenderer
# renderQuadList -> VertexConsumer#putBulkData). The full-brightness glow has no
# Bedrock material field (material_instances: texture, render_method,
# face_dimming, ambient_occlusion, tint_method for biome tints only;
# MicrosoftDocs/minecraft-creator minecraftBlock_material_instances.md).
# The renderers draw from the lower half: the model's upper block is 16 pixels up.
RUNE_OFFSETS = {"lower": 0, "upper": 16}
RUNE_BLOCK_MATERIAL = {"render_method": "alpha_test", "face_dimming": False, "ambient_occlusion": False}
RUNE_ITEM_MATERIAL = {"render_method": "alpha_test"}


def _family(name: str) -> str | None:
    """Which renderer draws ``name``'s runes: "waystone", "sharestone",
    "portstone", or None for a block with none."""
    if name in SHARESTONE_BLOCKS:
        return "sharestone"
    if name in PORTSTONE_BLOCKS:
        return "portstone"
    if name in WAYSTONE_BLOCKS:
        return "waystone"
    return None


def _rune_model(family: str) -> str:
    return f"{NS}:block/{family}_runes"


# Kept for the sharestone note's wording (PR #203).
RUNE_MODEL = _rune_model("sharestone")


def rune_colors(name: str) -> tuple[int, int | None] | None:
    """(the placed block's rune colour, the item's or None) for ``name``, as
    0xRRGGBB, or None for a block whose colour is not known."""
    family = _family(name)
    if family == "waystone":
        return WAYSTONE_RUNE_COLORS.get(name, WAYSTONE_RUNE_DEFAULT), None
    if family is None:
        return None
    color = name[:-len(f"_{family}")]
    return DYE_COLORS.get(color)


def _rune_subpath(name: str, item: bool = False) -> str:
    return f"{name}_runes" + ("_item" if item else "")


def _jar_block_texture_keys(mod: SourceMod) -> set[str]:
    keys = set()
    for lane in ("block", "blocks"):
        base = mod.assets / "textures" / lane
        if base.is_dir():
            keys |= {shortname(p.relative_to(base).with_suffix("").as_posix(), mod.namespace)
                     for p in base.rglob("*.png")}
    return keys


def _derived(name: str) -> list[tuple[str, int]]:
    """(subpath, colour) of each texture baked for ``name``'s runes: the
    block's (none when its colour is white, which leaves the jar's texture as
    it is) and the item's when its item tints them."""
    colors = rune_colors(name)
    if colors is None:
        return []
    block, item = colors
    out = [] if block == 0xFFFFFF else [(_rune_subpath(name), block)]
    if item is not None:
        out.append((_rune_subpath(name, True), item))
    return out


def _runes(mod: SourceMod, family: str = "sharestone") -> tuple[str | None, str]:
    """(the rune texture's path below the mod root, "") when this jar's
    ``family`` blocks can wear their runes, else (None, why)."""
    from .blocks import _overlay_pieces

    ref = _rune_model(family)
    path = mod.assets / "models" / "block" / f"{family}_runes.json"
    try:
        model = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None, f"no readable {ref} model in the jar"
    refs = model.get("textures") or {}
    used = {spec.get("texture", "").lstrip("#") for element in model.get("elements") or []
            for spec in (element.get("faces") or {}).values() if isinstance(spec, dict)}
    for element in model.get("elements") or []:
        pieces, why = _overlay_pieces(element, tuple(RUNE_OFFSETS), RUNE_OFFSETS)
        if pieces is None:
            return None, f"{ref} element {element.get('name') or 'unnamed'} {why}"
    textures = {refs.get(key) for key in used}
    if len(textures) != 1 or not isinstance(next(iter(textures)), str):
        return None, f"{ref} does not draw one texture"
    ns, _, sub = next(iter(textures)).rpartition(":")
    if ns != NS or not sub.startswith("block/"):
        return None, f"{ref}'s texture is not one of the jar's block textures"
    rel = f"assets/{NS}/textures/{sub}.png"
    try:
        readable = decode_rgba((mod.root / rel).read_bytes()) is not None
    except OSError:
        readable = False
    if not readable:
        return None, f"no readable {rel} in the jar"
    taken = _jar_block_texture_keys(mod)
    names = {"sharestone": SHARESTONE_BLOCKS, "portstone": PORTSTONE_BLOCKS, "waystone": WAYSTONE_BLOCKS}[family]
    for name in names:
        for subpath, _ in _derived(name):
            if shortname(subpath, mod.namespace) in taken:
                return None, f"the jar has its own {subpath} texture"
    return rel, ""


def _rune_turns(mod: SourceMod, name: str) -> dict | None:
    """Per facing, the runes' extra y turn (clockwise) in the block model's
    frame: the renderer's turn (anticlockwise toYRot) less the blockstate's."""
    try:
        variants = json.loads((mod.assets / "blockstates" / f"{name}.json").read_text())["variants"]
        state_y = {d: int(variants[f"facing={d},half=lower"].get("y") or 0) for d in TO_Y_ROT}
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError):
        return None
    return {d: ((360 - TO_Y_ROT[d]) - state_y[d]) % 360 for d in ("north", "east", "south", "west")}


def _rune_overlay(mod: SourceMod, name: str) -> Overlay | None:
    family = _family(name)
    colors = rune_colors(name)
    if family is None or colors is None:
        return None
    rel, _ = _runes(mod, family)
    turns = _rune_turns(mod, name)
    if rel is None or turns is None:
        return None
    sub = rel[len(f"assets/{NS}/textures/"):-len(".png")]
    block, item = colors
    # A white rune colour multiplies by 1: the jar's own texture, which the
    # textures converter ships under its own key.
    block_key = shortname(sub[len("block/"):] if block == 0xFFFFFF else _rune_subpath(name), mod.namespace)
    return Overlay(
        name="runes", model=_rune_model(family), texture=f"{NS}:{sub}",
        offsets=dict(RUNE_OFFSETS), turns=turns,
        block_texture=block_key,
        block_material=dict(RUNE_BLOCK_MATERIAL),
        item_texture=shortname(_rune_subpath(name, True), mod.namespace) if item is not None else None,
        item_material=dict(RUNE_ITEM_MATERIAL),
        # The item models (item/sharestone, item/portstone) draw the runes
        # unturned; Bedrock's item shows the lower half (as the waystones' does).
        item_value="lower", item_turn=0,
        sources=RUNE_SOURCES[family] + RUNE_COMMON_SOURCES,
        shown_by=RUNE_STATE if family == "waystone" else None,
    )


def derived_textures(mod: SourceMod) -> list[DerivedTexture]:
    """The runes' tinted textures for every block this jar's runtime converts
    with an overlay: the placed block's (unless white) and the item's (when
    Java's item tints them)."""
    out = []
    rels: dict[str, str | None] = {}
    for name, block in waystone_blocks(mod).items():
        family = _family(name)
        if block.overlay is None or family is None:
            continue
        if family not in rels:
            rels[family] = _runes(mod, family)[0]
        if rels[family] is None:
            continue
        out.extend(DerivedTexture(rels[family], subpath, rgb) for subpath, rgb in _derived(name))
    return out


# Java's shapes as one Bedrock box per half (origin/size in pixels, centred on
# x and z): the bounding box of each union, the same at every facing (the
# shapes are centred). The waystone's LOWER_SHAPE spans 0-16 on every axis; its
# UPPER_SHAPE's widest part is box(1, 10, 1, 15, 12, 15), height 0-16. Both
# sharestone shapes span 0-16 on every axis (LOWER_SHAPE's box(0, 0, 0, 16, 3,
# 16) .. box(3, 9, 3, 13, 16, 13); UPPER_SHAPE's box(3, 0, 3, 13, 7, 13) ..
# box(0, 13, 0, 16, 16, 16)).
LOWER_BOX = {"origin": [-8, 0, -8], "size": [16, 16, 16]}
UPPER_BOX = {"origin": [-7, 0, -7], "size": [14, 16, 14]}
SHARESTONE_BOX = {"origin": [-8, 0, -8], "size": [16, 16, 16]}
# A portstone's shapes depend on its facing (PortstoneBlock L47-107, indexed by
# Direction#get2DDataValue). Each box here is the bounding box of the north
# shape, the facing Java's model is drawn for (the blockstate's facing=north has
# no y turn), and the block's minecraft:transformation turns it with the
# geometry for the other facings (Bedrock-OSS wiki blocks/block-orientation:
# the transformation component turns the collision and selection boxes). North
# LOWER_SHAPES spans 0-16 on every axis (box(0, 0, 0, 16, 3, 16) ..
# box(3, 9, 9, 13, 16, 13)); north UPPER_SHAPES is box(3, 0, 9, 13, 7, 13) +
# box(4, 0, 7, 12, 2, 9): x 3-13, y 0-7, z 7-13.
PORTSTONE_LOWER_BOX = {"origin": [-8, 0, -8], "size": [16, 16, 16]}
PORTSTONE_UPPER_BOX = {"origin": [-5, 0, -1], "size": [10, 7, 6]}


def _block(name: str, overlay: Overlay | None = None) -> FacingBlock:
    if name in WARP_PLATE_BLOCKS:
        # No facing; the model's tinted rune element (tintindex 1, coloured by
        # WarpPlateBlock#getColorForBlock from the plate's galactic name) is
        # left out.
        return FacingBlock(
            name, 0, dict(WARP_PLATE_BOX), WARP_PLATE_SOURCES,
            java_state="status", values=WARP_PLATE_STATUSES, state=STATUS_STATE,
            facing=False, drop_tinted=True,
        )
    share = name in SHARESTONE_BLOCKS
    port = name in PORTSTONE_BLOCKS
    lower = PORTSTONE_LOWER_BOX if port else SHARESTONE_BOX if share else LOWER_BOX
    upper = PORTSTONE_UPPER_BOX if port else SHARESTONE_BOX if share else UPPER_BOX
    sources = PORTSTONE_SOURCES if port else SHARESTONE_SOURCES if share else BLOCK_SOURCES
    return FacingBlock(
        name, 180, lower, sources,
        java_state="half", values=("lower", "upper"), state=HALF_STATE,
        value_components={
            "lower": {"minecraft:collision_box": dict(lower), "minecraft:selection_box": dict(lower)},
            "upper": {"minecraft:collision_box": dict(upper), "minecraft:selection_box": dict(upper)},
        },
        overlay=overlay,
    )


# The Java lang keys the runtime shows, by role. Each is the key Waystones'
# code uses at the cited line; the jar's en_us.json must define it.
MESSAGES = {
    # WaystoneBlock#handleActivation L91-93: "Activated Waystone: %s".
    "activated": "chat.waystones.waystone_activated",
    # WaystoneTeleportError.NotEnoughXp L104-108 (shown on the action bar,
    # SelectWaystoneMessage L64).
    "not_enough_xp": "chat.waystones.not_enough_xp",
    # WaystoneTeleportError.SourceWaystoneOutOfRange / InvalidWaystone.
    "out_of_range": "chat.waystones.source_waystone_out_of_range",
    "missing": "chat.waystones.waystone_missing",
    # WaystoneEditError.NotOwner L22-26.
    "only_owner": "chat.waystones.only_owner_can_edit",
    # WaystoneBlockEntity#getSelectionMenuProvider L40.
    "title": "container.waystones.waystone_selection",
    # WaystoneSelectionScreenBase L384 (header for the waystone used).
    "current_location": "gui.waystones.waystone_selection.current_location",
    # AbstractWaystoneButton L29-32 (an empty name in the list).
    "unnamed": "gui.waystones.waystone_selection.unnamed_waystone",
    # The empty list (gui.waystones.waystone_selection.no_waystones_activated).
    "none": "gui.waystones.waystone_selection.no_waystones_activated",
    # ExperiencePointsRequirement#appendHoverText L36-40 (only when > 0).
    "xp_cost": "gui.waystones.waystone_selection.xp_requirement",
    # WaystoneBlockEntityBase#getSettingsMenuProvider L297 ("Edit %s") and
    # the screen's save button.
    "settings": "container.waystones.waystone_settings",
    "save": "gui.waystones.waystone_settings.save",
    # EditWaystoneMessage#makeNameLegal L84-87: a blank name.
    "untitled": "waystones.untitled_waystone",
    # WaystoneBlockEntity#getName L32-34: the %s of the settings title
    # (WaystoneBlockEntityBase#getSettingsMenuProvider L297).
    "waystone_name": "container.waystones.waystone",
}
# The texts only a sharestone shows; a jar without them keeps its sharestones
# residue (the waystones still work).
SHARESTONE_MESSAGES = {
    # SharestoneBlockEntity#getName L44-46: the %s of its settings title.
    "sharestone_name": "container.waystones.sharestone",
    # WaystoneSelectionScreenBase#getNoWaystonesMessage L349-357: the empty
    # sharestone list.
    "none_shared": "gui.waystones.waystone_selection.no_sharestones_available",
}


def portstone_title(name: str) -> str:
    """The menu title a portstone ``name`` shows (PortstoneBlock#useWithoutItem
    L140: container.waystones.<colour>_portstone)."""
    return f"container.{NS}.{name}"


def portstone_keys(name: str) -> set[str]:
    """The jar texts a portstone shows: its menu title and its target list's
    empty text (WaystoneSelectionScreenBase#getNoWaystonesMessage L349-360: the
    sharestone text for a sharestone target kind, else the waystone one)."""
    none = SHARESTONE_MESSAGES["none_shared"] if portstone_target(name) != WAYSTONE_TYPE else MESSAGES["none"]
    return {portstone_title(name), none}

# Bedrock vanilla sound events playing the same audio as the Java events
# (Java: misode/mcmeta 1.21.1-assets 451045f2 assets/minecraft/sounds.json;
# Bedrock: Mojang/bedrock-samples 46ba6ea9 resource_pack/sounds/sound_definitions.json):
# entity.player.levelup = random/levelup = random.levelup;
# block.portal.travel = portal/travel = portal.travel.
SOUNDS = {
    # WaystoneBlock#handleActivation L97: PLAYER_LEVELUP, 0.2, 1.
    "activate": {"id": "random.levelup", "volume": 0.2, "pitch": 1.0},
    # WaystoneTeleportManager#performTeleport L161-162: PORTAL_TRAVEL at the
    # source (0.01) and the target (0.05), pitch 1.
    "depart": {"id": "portal.travel", "volume": 0.01, "pitch": 1.0},
    "arrive": {"id": "portal.travel", "volume": 0.05, "pitch": 1.0},
}

# The warp plate's sound: WarpPlateBlockEntity#attuneShard L368 plays
# CHICKEN_EGG (volume 1, pitch 1) when it pops out a shard attuned to itself.
# entity.chicken.egg = mob/chicken/plop (mcmeta 1.21.1-assets 451045f2) =
# Bedrock mob.chicken.plop (bedrock-samples 46ba6ea9 sound_definitions).
WARP_PLATE_SOUNDS = {
    "eject": {"id": "mob.chicken.plop", "volume": 1.0, "pitch": 1.0},
}

# How a requirement condition evaluates in this runtime, where every teleport
# from a waystone starts at a waystone block and targets a waystone the player
# activated (RequirementRegistry L294-L348). Conditions not here, except
# is_interdimensional (decided per teleport), have no runtime. A sharestone's
# teleports go sharestone -> sharestone of the same colour
# (:func:`fixed_conditions`).
FIXED_CONDITIONS = {
    "source_is_warp_plate": False,  # L295-L296: the source is a waystone
    "source_is_scroll": False,  # L311: no warp item starts a teleport here
    "source_is_inventory_button": False,  # L308-L310: no inventory button
    "source_is_portstone": False,  # L297-L298
    "source_is_sharestone": False,  # L301-L302
    "source_is_waystone": True,  # L299-L300
    # L335-L337: every waystone keeps the default ACTIVATION visibility
    # (general.defaultVisibility); visibility isn't editable here.
    "target_is_global": False,
    "target_is_fleeting_memorial": False,  # L329-L331: memorials don't convert
    "target_is_warp_plate": False,  # L323-L325
    "target_is_warp_portal": False,  # L326-L328
    "target_is_player": False,  # L332-L334: twinbound feathers don't convert
    "target_is_sharestone": False,  # L338-L340
    "target_is_waystone": True,  # L346-L348
    # L303-L307 / L341-L345: source_is_<colour>_sharestone and
    # target_is_<colour>_sharestone, one per WaystoneTypes.SHARESTONES entry.
    **{f"{side}_is_{name}": False for name in SHARESTONE_BLOCKS for side in ("source", "target")},
}


def fixed_conditions(kind: str, portstone: bool = False) -> dict[str, bool]:
    """The conditions decided for teleports from a waystone of type ``kind``,
    or, with ``portstone``, from a portstone listing targets of type ``kind``.

    From a sharestone the source and the target are sharestones of its type
    (getTargetsForWaystoneType L325-326 lists only that type), never a
    waystone; the target's visibility is its colour's
    (WaystoneVisibility#fromWaystoneType L38-57), so target_is_global stays
    false. A portstone's teleport has no source waystone (its menu carries
    none, WaystoneSelectionListBuilder L69-72, and SelectWaystoneMessage
    L70 passes that null on): every source_is_* condition read from the
    source waystone is false, and source_is_portstone, read from the menu's
    PORTSTONE flag (PortstoneBlock L139, ModMenus L27), is true.
    """
    if kind == WAYSTONE_TYPE:
        fixed = dict(FIXED_CONDITIONS)
    elif kind == WARP_PLATE_TYPE:
        # A warp plate's teleport starts at the plate (setFromWaystone,
        # WarpPlateBlockEntity L135, L267) and ends at the waystone its shard is
        # attuned to, which here is always a warp plate (only a plate attunes a
        # shard, L345-356); a plate's visibility is SHARD_ONLY
        # (WaystoneVisibility#fromWaystoneType L58-59), so target_is_global is
        # false; the warp item is the shard, not a scroll (L268).
        fixed = dict(FIXED_CONDITIONS)
        fixed.update({"source_is_waystone": False, "target_is_waystone": False,
                      "source_is_warp_plate": True, "target_is_warp_plate": True})
    else:
        name = kind.split(":", 1)[1]
        if name not in SHARESTONE_BLOCKS:
            raise _Refuse(f"no fixed conditions for waystone type {kind!r}")
        fixed = dict(FIXED_CONDITIONS)
        fixed.update({"source_is_waystone": False, "target_is_waystone": False,
                      "source_is_sharestone": True, "target_is_sharestone": True,
                      f"source_is_{name}": True, f"target_is_{name}": True})
    if portstone:
        fixed.update({"source_is_waystone": False, "source_is_sharestone": False, "source_is_portstone": True,
                      **{f"source_is_{n}": False for n in SHARESTONE_BLOCKS}})
    return fixed
DYNAMIC_CONDITIONS = {"is_interdimensional"}  # L294: target dimension != the player's
# Experience-point functions (RequirementRegistry L122-L147) and the parameter
# kinds their arguments parse as (L272-L286).
XP_FUNCTIONS = {
    "add_xp_cost": ("int",),
    "multiply_xp_cost": ("float",),
    "scaled_add_xp_cost": ("variable", "float"),
    "min_xp_cost": ("int",),
    "max_xp_cost": ("int",),
}
COOLDOWN_FUNCTIONS = {"add_cooldown", "multiply_cooldown", "min_cooldown", "max_cooldown",
                      "scaled_add_cooldown", "scaled_multiply_cooldown"}
VARIABLES = {"distance"}  # L434: player to the target's block centre
REQUIREMENT_SOURCES = (
    _src("requirement/RequirementModifierParser.java", "13-L25"),
    _src("requirement/RequirementRegistry.java", "122-L147"),
    _src("requirement/RequirementRegistry.java", "294-L348"),
    _src("api/WaystoneVisibility.java", "38-L57"),
    _src("requirement/RequirementRegistry.java", "434"),
    _src("requirement/RequirementRegistry.java", "529-L530"),
    _src("requirement/ExperiencePointsRequirement.java", "17-L28"),
    _src("InternalMethodsImpl.java", "244-L259"),
)
RUNTIME_SOURCES = (
    _src("block/WaystoneBlock.java", "81-L123"),
    _src("block/WaystoneBlockBase.java", "96-L137"),
    _src("block/WaystoneBlockBase.java", "196-L205"),
    _src("block/WaystoneBlockBase.java", "286-L339"),
    _src("core/WaystoneTeleportManager.java", "245-L284"),
    _src("core/WaystoneTeleportManager.java", "481-L494"),
    _src("core/WaystoneTeleportManager.java", "523-L532"),
    _src("core/WaystonePermissionManager.java", "35-L53"),
    _src("network/message/EditWaystoneMessage.java", "84-L94"),
    _src("client/gui/screen/WaystoneEditScreen.java", "54"),
    _src("client/gui/widget/WaystoneList.java", "46-L48"),
    _src("core/PersistentPlayerWaystoneData.java", "270-L290"),
)
SHARESTONE_RUNTIME_SOURCES = (
    _src("block/SharestoneBlock.java", "74-L82"),
    _src("block/entity/SharestoneBlockEntity.java", "30-L53"),
    _src("core/PlayerWaystoneManager.java", "36-L62"),
    _src("core/PlayerWaystoneManager.java", "306-L333"),
    _src("core/WaystoneManagerImpl.java", "96-L99"),
    _src("client/gui/screen/WaystoneSelectionScreenBase.java", "349-L357"),
)
PORTSTONE_RUNTIME_SOURCES = (
    _src("block/PortstoneBlock.java", "133-L147"),
    _src("block/entity/PortstoneBlockEntity.java", "9-L20"),
    _src("menu/WaystoneSelectionListBuilder.java", "69-L72"),
    _src("menu/WaystoneSelectionMenu.java", "79-L86"),
    _src("menu/ModMenus.java", "27"),
    _src("network/message/SelectWaystoneMessage.java", "69-L82"),
    _src("core/WaystoneTeleportManager.java", "523-L528"),
    _src("core/PlayerWaystoneManager.java", "323-L334"),
    _src("client/gui/screen/WaystoneSelectionScreenBase.java", "333-L360"),
)
NAME_MAX_LENGTH = 128  # WaystoneEditScreen L54: nameField.setMaxLength(128)
# WaystoneTeleportManager#canInteractWithWaystone L531: a non-player must be
# within 8 blocks (distanceToSqr <= 64) of the source waystone's centre; a
# player's canInteractWithBlock(pos, 4) test reads the player's reach
# attribute, so the runtime uses the fixed distance for everyone.
RANGE_SQ = 64


class _Refuse(Exception):
    pass


def _defaults(version: str) -> dict | None:
    text = resources.files("portkit.data").joinpath(DEFAULTS_DATA).read_text(encoding="utf-8")
    return (json.loads(text).get("versions") or {}).get(version)


def _unsupported(mod: SourceMod) -> str | None:
    if mod.namespace != NS:
        return f"the waystone runtime is Waystones' (namespace {NS!r}), not {mod.namespace!r}"
    version = (mod.mods or {}).get(NS)
    if mod.loader not in VERSIONS or version != VERSIONS[mod.loader] or _defaults(version) is None:
        known = ", ".join(f"{v} ({k})" for k, v in sorted(VERSIONS.items()))
        return (f"Waystones {version or '(unknown version)'} on {mod.loader or 'an unknown loader'}: the "
                f"waystone runtime follows Waystones' code at the version it was read from ({known})")
    return None


def _tagged(mod: SourceMod, tag: str = TAG) -> list[str]:
    path = mod.root / tag
    try:
        values = json.loads(path.read_text()).get("values") or []
    except (OSError, json.JSONDecodeError, AttributeError):
        return []
    names = []
    for value in values:
        ident = value if isinstance(value, str) else (value.get("id") if isinstance(value, dict) else None)
        if isinstance(ident, str) and ident.startswith(f"{NS}:"):
            names.append(ident.split(":", 1)[1])
    return names


def waystone_blocks(mod: SourceMod) -> dict[str, FacingBlock]:
    """Waystone, sharestone and portstone blocks of ``mod`` the runtime makes work, by blockstate name."""
    if _unsupported(mod) is not None:
        return {}
    names = [n for n in _tagged(mod) if n in WAYSTONE_BLOCKS]
    names += [n for n in _tagged(mod, SHARESTONE_TAG) if n in SHARESTONE_BLOCKS]
    names += [n for n in _tagged(mod, PORTSTONE_TAG) if n in PORTSTONE_BLOCKS]
    # No tag names the warp plate; ModBlocks registers it by name (L86).
    names += list(WARP_PLATE_BLOCKS)
    return {name: _block(name, _rune_overlay(mod, name))
            for name in names if (mod.assets / "blockstates" / f"{name}.json").is_file()}


def loot_names(mod: SourceMod) -> set[str]:
    """Block loot tables (by name under loot_table/blocks/) this converter reads."""
    return set(waystone_blocks(mod))


def lang_keys(mod: SourceMod) -> set[str]:
    """Java lang keys the runtime shows (shipped under their own name)."""
    blocks = waystone_blocks(mod)
    if not blocks:
        return set()
    keys = set(MESSAGES.values())
    if any(name in SHARESTONE_BLOCKS for name in blocks):
        keys |= set(SHARESTONE_MESSAGES.values())
    for name in blocks:
        if name in PORTSTONE_BLOCKS:
            keys |= portstone_keys(name)
    if any(name in WARP_PLATE_BLOCKS for name in blocks):
        keys |= set(WARP_PLATE_MESSAGES.values())
    return keys


# -- requirements -------------------------------------------------------------------

_CONDITION = re.compile(r"([\w:]+)(?:\((.*?)\))?")
_FUNCTION = re.compile(r"([\w:]+)\((.*?)\)")


def _local(ident: str) -> str:
    """RequirementModifierParser#waystonesResourceLocation: no namespace is waystones."""
    ns, _, path = ident.rpartition(":")
    if ns not in ("", NS):
        raise _Refuse(f"{ident!r} is not a Waystones requirement id")
    return path


def _negated(name: str) -> tuple[str, bool]:
    """(base condition, negated) for a condition id; Java registers each
    condition's negation as its name with ``not_`` after the first ``is_``
    (RequirementRegistry L529-L530)."""
    index = name.find("is_not_")
    if index != -1:
        return name[:index + 3] + name[index + 7:], True
    if name.startswith("not_"):
        return name[4:], True
    return name, False


def _argument(kind: str, raw: str):
    raw = raw.strip()
    try:
        if kind == "int":
            return int(raw)
        if kind == "float":
            return float(raw)
    except ValueError as exc:
        raise _Refuse(f"argument {raw!r} is not a {kind}") from exc
    variable = _local(raw)
    if variable not in VARIABLES:
        raise _Refuse(f"variable {raw!r} has no runtime")
    return variable


def requirements(lines: list[str], enable_costs: bool, enable_cooldowns: bool,
                 kind: str = WAYSTONE_TYPE, portstone: bool = False) -> tuple[list[dict], list[str]]:
    """The warp requirement modifiers that can apply in this runtime to a
    teleport from a waystone of type ``kind`` (with ``portstone``: from a
    portstone to a target of type ``kind``), in order, as {"when":
    {condition: wanted}, "fn": name, "args": [...]}, and the lines left out
    (with why). Raises _Refuse for anything without a runtime."""
    fixed_table = fixed_conditions(kind, portstone)
    kept: list[dict] = []
    dropped: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        start, end = line.find("["), line.find("]")
        condition_part = line[start + 1:end] if start != -1 and end != -1 else ""
        function_part = line[end + 1:].strip()
        when: dict[str, bool] = {}
        never = False
        for match in _CONDITION.finditer(condition_part):
            base, negated = _negated(_local(match.group(1)))
            if match.group(2):
                raise _Refuse(f"condition {match.group(1)!r} takes arguments; none is read here")
            if base in fixed_table:
                if fixed_table[base] == negated:
                    never = True
            elif base in DYNAMIC_CONDITIONS:
                wanted = not negated
                if when.get(base, wanted) != wanted:
                    never = True
                when[base] = wanted
            else:
                raise _Refuse(f"warp requirement condition {match.group(1)!r} has no runtime")
        functions = [(m.group(1), m.group(2)) for m in _FUNCTION.finditer(function_part)]
        if not functions:
            raise _Refuse(f"warp requirement {line!r} names no function")
        if never:
            # A condition this runtime decides false: whatever the line does,
            # it never applies to a teleport here.
            dropped.append(f"{line} (never applies here)")
            continue
        for name, args in functions:
            fn = _local(name)
            if fn in COOLDOWN_FUNCTIONS:
                if not enable_cooldowns:
                    dropped.append(f"{line} (enableCooldowns off)")
                    continue
                raise _Refuse(f"cooldown requirement {line!r} applies here; cooldowns have no runtime")
            if fn not in XP_FUNCTIONS:
                raise _Refuse(f"warp requirement function {name!r} has no runtime")
            kinds = XP_FUNCTIONS[fn]
            parts = [a for a in args.split(",")] if args.strip() else []
            if len(parts) != len(kinds):
                raise _Refuse(f"{name}({args}) takes {len(kinds)} argument(s)")
            if not enable_costs:
                dropped.append(f"{line} (enableCosts off)")
                continue
            kept.append({"when": dict(sorted(when.items())), "fn": fn,
                         "args": [_argument(k, a) for k, a in zip(kinds, parts)]})
    return kept, dropped


# -- loot ---------------------------------------------------------------------------


def _loot(rel: str, table: dict, identifier: str, notes: list[str], single: bool = False) -> dict:
    """The lower half's Bedrock table from the jar's: one pool, gated on
    half=lower, survives_explosion, the block's own item; the silk-touch
    copy_components (the item keeps the waystone's identity) is not carried.
    With ``single`` (the warp plate, one block, no halves) the pool has no
    half condition, and the silk-touch copy_name is left out the same way."""
    pools = table.get("pools")
    if not isinstance(pools, list) or len(pools) != 1 or table.get("functions"):
        raise _Refuse("the table is not one pool")
    pool = pools[0]
    if pool.get("rolls", 1) not in (1, 1.0) or pool.get("bonus_rolls", 0) not in (0, 0.0):
        raise _Refuse("the pool does not roll exactly once")
    entries = pool.get("entries")
    if not isinstance(entries, list) or len(entries) != 1:
        raise _Refuse("the pool does not have one entry")
    entry = entries[0]
    if not isinstance(entry, dict) or entry.get("type") not in ("minecraft:item", "item") \
            or entry.get("name") != identifier or set(entry) - {"type", "name"}:
        raise _Refuse(f"the entry is not a plain {identifier} item")
    lower = explosion = False
    for condition in pool.get("conditions") or []:
        kind = condition.get("condition")
        if kind == "minecraft:survives_explosion":
            explosion = True
        elif (kind == "minecraft:block_state_property" and condition.get("block") == identifier
              and condition.get("properties") == {"half": "lower"}):
            lower = True
        else:
            raise _Refuse(f"pool condition {kind!r} is not half=lower or survives_explosion")
    if lower == single:
        raise _Refuse("the pool is gated on half=lower" if single else "the pool is not gated on half=lower")
    silk_copies = {"minecraft:copy_components", "minecraft:copy_name"} if single else {"minecraft:copy_components"}
    for function in pool.get("functions") or []:
        silk = function.get("conditions") or []
        if not (function.get("function") in silk_copies and function.get("source") == "block_entity"
                and len(silk) == 1 and silk[0].get("condition") == "minecraft:match_tool"):
            raise _Refuse(f"pool function {function.get('function')!r} is not the silk-touch copy")
        notes.append("silk_touch")
    bedrock_entry: dict = {"type": "item", "name": identifier}
    if explosion:
        bedrock_entry["functions"] = [{"function": "explosion_decay"}]
    return {"pools": [{"rolls": 1, "entries": [bedrock_entry]}]}


def _half(condition: str) -> str | None:
    for value in ("lower", "upper"):
        if f"q.block_state('{HALF_STATE}') == '{value}'" in condition:
            return value
    return None


def _jar_lang(mod: SourceMod) -> dict:
    try:
        return json.loads((mod.assets / "lang" / "en_us.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


# -- warp plates -------------------------------------------------------------------


def _item_paths(files: dict) -> dict[str, str]:
    """identifier -> behavior pack path of every item definition written so far."""
    from .recipes import emitted_definitions

    return {ident: path for ident, (kind, path, _) in emitted_definitions(files).items() if kind == "item"}


def warp_shards(mod: SourceMod, files: dict) -> tuple[dict | None, str]:
    """The shards a warp plate works with, as the runtime's table holds them,
    or (None, why) when the jar's tag or the converted items don't have them."""
    items = _item_paths(files)
    tagged = _tagged(mod, WARP_SHARDS_TAG)
    if not tagged:
        return None, f"no readable {WARP_SHARDS_TAG} in the jar, so which shards a plate takes is unknown"
    accepted = sorted(f"{NS}:{n}" for n in tagged if f"{NS}:{n}" in items)
    roles = {}
    for role, name in SHARD_ROLES.items():
        ident = f"{NS}:{name}"
        if ident in accepted:
            roles[role] = ident
        elif role != "locked":
            return None, f"the {name} item did not convert (or is not in {WARP_SHARDS_TAG}), which a plate needs"
    single = sorted(f"{NS}:{n}" for n in _tagged(mod, SINGLE_USE_SHARDS_TAG) if f"{NS}:{n}" in accepted)
    return {"accepted": accepted, "attuned": roles["attuned"], "dormant": roles["dormant"],
            "locked": roles.get("locked"), "single_use": single}, ""


def _use_time(configured: int) -> int:
    """WarpPlateBlockEntity#getWarpPlateUseTime L236-249 with no modifier items
    (the multiplier stays 1): Mth.clamp((int) (configured * 1), 1, configured * 2)."""
    return max(1, min(int(configured * 1.0), configured * 2))


# -- the converter ------------------------------------------------------------------


@dataclass(frozen=True)
class _Plan:
    modifiers: dict  # waystone type -> its requirement modifiers
    dropped: list
    defaults: dict
    # target type -> the requirement modifiers of a portstone teleport to it
    portstone_modifiers: dict


def _plan(mod: SourceMod, kinds: list[str], portstone_kinds: list[str] = ()) -> _Plan:
    entry = _defaults((mod.mods or {}).get(NS))
    values = {k: v["value"] for k, v in entry["values"].items()}
    modifiers: dict[str, list] = {}
    portstone_modifiers: dict[str, list] = {}
    left_out: dict[str, list[str]] = {}
    variants = [(kind, False, kind) for kind in kinds]
    variants += [(kind, True, f"a portstone to {kind}") for kind in portstone_kinds]
    for kind, portstone, label in variants:
        kept, left = requirements(values["teleports.warpRequirements"], values["teleports.enableCosts"],
                                  values["teleports.enableCooldowns"], kind, portstone)
        (portstone_modifiers if portstone else modifiers)[kind] = kept
        left_out[label] = left
    # A line left out for every type is listed once; one left out for some
    # types is listed once too, naming them (or, when it is kept for fewer,
    # the ones that keep it: the warp plate keeps source_is_warp_plate).
    labels = list(left_out)
    dropped = [line for line in left_out[labels[0]] if all(line in left for left in left_out.values())]
    partial = list(dict.fromkeys(line for label in labels for line in left_out[label] if line not in dropped))
    for line in partial:
        where = [label for label in labels if line in left_out[label]]
        others = [label for label in labels if line not in left_out[label]]
        dropped.append(f"{line} (from {', '.join(where)})" if len(where) <= len(others)
                       else f"{line} (from all but {', '.join(others)})")
    return _Plan(modifiers, dropped, entry, portstone_modifiers)


def _network(kind: str, modifiers: list) -> dict:
    """How the runtime treats one waystone type: a sharestone's menu lists
    every sharestone of its type and nothing is activated
    (SharestoneBlock#handleActivation L74-82; PlayerWaystoneManager
    #activateWaystone L60 records only WAYSTONE activations); a waystone's
    lists the waystones the player activated."""
    shared = kind != WAYSTONE_TYPE
    return {
        "name": "sharestone_name" if shared else "waystone_name",
        "none": "none_shared" if shared else "none",
        "requirements": modifiers,
        "shared": shared,
    }


def _portstone(name: str, plan: _Plan) -> dict:
    """How the runtime treats one portstone: the network it lists
    (PortstoneBlock#getTargetWaystoneType L145-147), its menu title (L140)
    and the requirements of a teleport from it to that network."""
    target = portstone_target(name)
    return {"requirements": plan.portstone_modifiers[target], "target": target, "title": portstone_title(name)}


def convert(mod: SourceMod, deferred: list[tuple[str, dict]], files: dict,
            context: LoadContext) -> tuple[ConversionResult, str]:
    """The waystones', sharestones' and portstones' runtime entry, loot tables and block components.

    ``deferred`` is (source path, table) for their block loot tables, which
    the loot converter left to this one (:func:`loot_names`).
    """
    result = ConversionResult()
    blocks = waystone_blocks(mod)
    tables = {rel.rsplit("/", 1)[-1][:-len(".json")]: (rel, table) for rel, table in deferred}
    if not blocks:
        for rel, _ in deferred:
            result.unhandled.append(Unhandled(rel, RESIDUE_KIND, "no waystone runtime for this jar"))
        return result, ""

    lang = _jar_lang(mod)
    why_all = None
    why_share = None
    missing = sorted(k for k in MESSAGES.values() if k not in lang)
    if missing:
        why_all = f"the jar's en_us.json lacks {', '.join(missing)}, which the runtime shows"
    missing_share = sorted(k for k in SHARESTONE_MESSAGES.values() if k not in lang)
    if missing_share:
        why_share = f"the jar's en_us.json lacks {', '.join(missing_share)}, which a sharestone shows"
    kinds = sorted({waystone_type(name) for name in blocks if name not in PORTSTONE_BLOCKS})
    port_kinds = sorted({portstone_target(name) for name in blocks if name in PORTSTONE_BLOCKS})
    plan = None
    if why_all is None:
        try:
            plan = _plan(mod, kinds or [WAYSTONE_TYPE], port_kinds)
        except _Refuse as refusal:
            why_all = f"warpRequirements: {refusal}"

    notes: list[str] = []
    kept: list[str] = []
    silk = False
    # Waystones and sharestones first: a portstone works only when the
    # network it lists did.
    for name in sorted(blocks, key=lambda n: (n in PORTSTONE_BLOCKS, n)):
        identifier = f"{NS}:{name}"
        share = name in SHARESTONE_BLOCKS
        port = name in PORTSTONE_BLOCKS
        plate = name in WARP_PLATE_BLOCKS
        block_path = f"blocks/{name}.json"
        body = files.get(block_path)
        loot = tables.get(name)
        why = why_all if why_all is not None else (why_share if share else None)
        if why is None and port:
            missing_port = sorted(k for k in portstone_keys(name) if k not in lang)
            target = portstone_target(name)
            if missing_port:
                why = f"the jar's en_us.json lacks {', '.join(missing_port)}, which this portstone shows"
            elif not any(waystone_type(i.split(":", 1)[1]) == target for i in kept):
                why = f"no {target} block works here, so the portstone has nothing to list"
        if why is None and plate:
            missing_plate = sorted(k for k in WARP_PLATE_MESSAGES.values() if k not in lang)
            if missing_plate:
                why = f"the jar's en_us.json lacks {', '.join(missing_plate)}, which a warp plate shows"
            else:
                shards, why_shards = warp_shards(mod, files)
                why = why_shards or None
        if why is None and not (isinstance(body, dict) and body.get("minecraft:block", {})
                                .get("description", {}).get("identifier") == identifier):
            why = f"the waystone block {identifier} did not convert"
        bedrock_loot = None
        if why is None:
            if loot is None:
                why = f"no loot table for {identifier} in the jar, so what breaking it drops is unknown"
            else:
                flags: list[str] = []
                try:
                    bedrock_loot = _loot(loot[0], loot[1], identifier, flags, single=plate)
                except _Refuse as refusal:
                    why = f"loot table {loot[0]}: {refusal}"
                # A sharestone can't be silk-touched in Java either
                # (WaystoneBlockBase#canSilkTouch L91-93, not overridden):
                # its copied item places a new sharestone. A portstone's
                # block entity holds nothing to copy.
                silk = silk or ("silk_touch" in flags and not share and not port and not plate)
        if why is not None:
            if loot is not None:
                result.unhandled.append(Unhandled(loot[0], RESIDUE_KIND, why))
            if isinstance(body, dict):
                notes.append(f"{identifier}: places but does nothing ({why})")
            continue

        loot_path = f"loot_tables/blocks/{name}.json"
        result.files[loot_path] = bedrock_loot
        result.consumed.add(loot[0])
        new = json.loads(json.dumps(body))
        new["format_version"] = SCRIPT_FORMAT
        block = new["minecraft:block"]
        if plate:
            # WarpPlateBlock#getTicker (L262-272): the block entity ticks every
            # server tick; Bedrock's minecraft:tick sends onTick every tick.
            block.setdefault("components", {})[WARP_PLATE_COMPONENT] = {}
            block["components"]["minecraft:tick"] = {"interval_range": [1, 1], "looping": True}
        else:
            block.setdefault("components", {})[COMPONENT] = {}
        # Only the lower half drops (the pool's half=lower); breaking the
        # upper half takes the lower one with it (the runtime), which drops.
        block["components"]["minecraft:loot"] = loot_path
        for permutation in block.get("permutations") or []:
            half = _half(permutation.get("condition", ""))
            if half is not None:
                permutation.setdefault("components", {})["minecraft:loot"] = (
                    loot_path if half == "lower" else EMPTY_LOOT)
        result.files[block_path] = new
        kept.append(identifier)

    if not kept:
        result.notes.extend(dict.fromkeys(notes))
        return result, ""

    values = {k: v["value"] for k, v in plan.defaults["values"].items()}
    kept.sort()
    kept_port = [i for i in kept if i.split(":", 1)[1] in PORTSTONE_BLOCKS]
    kept_share = [i for i in kept if i.split(":", 1)[1] in SHARESTONE_BLOCKS]
    kept_plate = [i for i in kept if i.split(":", 1)[1] in WARP_PLATE_BLOCKS]
    kept_ways = [i for i in kept if i not in kept_port and i not in kept_share and i not in kept_plate]
    # A warp plate is never in a menu: it has its own table section.
    block_types = {i: waystone_type(i.split(":", 1)[1]) for i in kept if i not in kept_port and i not in kept_plate}
    def _states(ident: str) -> dict:
        return ((files.get(f"blocks/{ident.split(':', 1)[1]}.json") or {}).get("minecraft:block", {})
                .get("description", {}).get("states") or {})

    def _has_runes(ident: str) -> bool:
        return "runes" in ((files.get(f"blocks/{ident.split(':', 1)[1]}.json") or {})
                           .get("minecraft:block", {}).get("components", {})
                           .get("minecraft:material_instances") or {})

    rune_blocks = [i for i in kept_ways if RUNE_STATE in _states(i) and _has_runes(i)]
    messages = dict(MESSAGES)
    if kept_share:
        messages.update(SHARESTONE_MESSAGES)
    sounds = dict(SOUNDS)
    if kept_plate:
        messages.update(WARP_PLATE_MESSAGES)
        sounds.update(WARP_PLATE_SOUNDS)
    table = {
        "block_types": block_types,
        "blocks": [i for i in kept if i not in kept_plate],
        "component": COMPONENT,
        # A record stored before records carried a type (#198) is a waystone's.
        "default_type": WAYSTONE_TYPE,
        "half_state": HALF_STATE,
        "messages": messages,
        "name_max_length": NAME_MAX_LENGTH,
        "namespace": NS,
        "networks": {kind: _network(kind, plan.modifiers[kind]) for kind in sorted(set(block_types.values()))},
        "portstones": {i: _portstone(i.split(":", 1)[1], plan) for i in kept_port},
        "range_sq": RANGE_SQ,
        "restricted_origins": sorted(values["general.restrictedWaystones"]),
        # Waystones whose runes the runtime turns on when a player activates
        # them (WaystoneRenderer L33-37), through this boolean state.
        "rune_blocks": rune_blocks,
        "rune_state": RUNE_STATE,
        "sounds": sounds,
    }
    if kept_plate:
        shards, _ = warp_shards(mod, files)
        table["warp_plates"] = {
            "attunement_property": ATTUNEMENT_PROPERTY,
            "attunement_ticks": ATTUNEMENT_TICKS,
            "blocks": kept_plate,
            "component": WARP_PLATE_COMPONENT,
            # warpPlateCooldownTime: ticks off the target plate before it warps that entity again.
            "cooldown": values["general.warpPlateCooldownTime"],
            # entityDenyList: entities never teleported (Java ids; Bedrock's vanilla ids are the same).
            "deny": sorted(values["teleports.entityDenyList"]),
            "error_style": ERROR_STYLE,
            "requirements": plan.modifiers[WARP_PLATE_TYPE],
            "shards": shards,
            "status_state": STATUS_STATE,
            "type": WARP_PLATE_TYPE,
            "use_time": _use_time(values["general.warpPlateUseTime"]),
        }
        # The shard items' stack sizes from their classes (SHARD_STACK_SIZES).
        items = _item_paths(files)
        for name, size in SHARD_STACK_SIZES.items():
            path = items.get(f"{NS}:{name}")
            if path is None:
                continue
            body = json.loads(json.dumps(files[path]))
            body["minecraft:item"].setdefault("components", {})["minecraft:max_stack_size"] = size
            result.files[path] = body
    data_path = f"{_RUNTIME_DIR}/data/{NS}_waystone.js"
    config_sources = [f"{plan.defaults['repo']}/blob/{plan.defaults['commit']}/{v['source']}"
                      for k, v in plan.defaults["values"].items() if kept_plate or k not in WARP_PLATE_CONFIG]
    header = (
        f"// Generated by portkit from {NS}'s waystone, sharestone and portstone blocks"
        + (", warp plate, shard items" if kept_plate else "") + ", loot tables, config\n"
        f"// defaults and Java code; do not edit. Read by the fixed runtime {_RUNTIME_DIR}/waystone.js (portkit/runtime). Sources:\n"
        + "".join(f"//   {s}\n" for s in dict.fromkeys(
            (*(BLOCK_SOURCES if kept_ways else ()), *(SHARESTONE_SOURCES if kept_share else ()),
             *(PORTSTONE_SOURCES if kept_port else ()),
             *(WARP_PLATE_SOURCES + SHARD_STACK_SOURCES if kept_plate else ()),
             *config_sources, *REQUIREMENT_SOURCES, *RUNTIME_SOURCES,
             *(SHARESTONE_RUNTIME_SOURCES if kept_share else ()),
             *(PORTSTONE_RUNTIME_SOURCES if kept_port else ()),
             *(WARP_PLATE_RUNTIME_SOURCES if kept_plate else ()))))
        + "".join(f"// warpRequirements left out: {d}\n" for d in plan.dropped)
    ).rstrip("\n")
    result.files[data_path] = _js_module(header, table)
    for name in ("waystone.js", "waystone_core.js"):
        result.files[f"{_RUNTIME_DIR}/{name}"] = runtime_source(name)
    blocks_ways = [n for n in blocks if n not in SHARESTONE_BLOCKS and n not in PORTSTONE_BLOCKS]
    blocks_share = [n for n in blocks if n in SHARESTONE_BLOCKS]
    blocks_port = [n for n in blocks if n in PORTSTONE_BLOCKS]
    blocks_plate = [n for n in blocks if n in WARP_PLATE_BLOCKS]
    blocks_ways = [n for n in blocks_ways if n not in WARP_PLATE_BLOCKS]
    if blocks_ways:
        result.stations[f"{NS}:waystones"] = {
            "converted": len(kept_ways),
            "residue": len(blocks_ways) - len(kept_ways),
            "data": data_path,
            "block": ", ".join(kept_ways),
        }
    if blocks_share:
        result.stations[f"{NS}:sharestones"] = {
            "converted": len(kept_share),
            "residue": len(blocks_share) - len(kept_share),
            "data": data_path,
            "block": ", ".join(kept_share),
        }
    if blocks_port:
        result.stations[f"{NS}:portstones"] = {
            "converted": len(kept_port),
            "residue": len(blocks_port) - len(kept_port),
            "data": data_path,
            "block": ", ".join(kept_port),
        }
    if blocks_plate:
        result.stations[f"{NS}:warp_plates"] = {
            "converted": len(kept_plate),
            "residue": len(blocks_plate) - len(kept_plate),
            "data": data_path,
            "block": ", ".join(kept_plate),
        }
    result.notes.extend(dict.fromkeys(notes))
    if rune_blocks:
        coloured = sorted(i for i in rune_blocks if i.split(":", 1)[1] in WAYSTONE_RUNE_COLORS)
        ways_runes = (
            f"Its runes are drawn as Java draws them: the jar's {_rune_model('waystone')} model as part of the "
            "block (the band cut where it crosses into the upper half), turned with the block's facing as the "
            "Java renderer turns them, without face shading or ambient occlusion, in the waystone style's rune "
            "colour (the jar's texture as it is"
            + (f"; tinted at convert time for {', '.join(coloured)}" if coloured else "")
            + "). Java shows them only to a player who has activated that waystone; a Bedrock block looks the "
            f"same to everyone, so the runtime turns them on ({RUNE_STATE}) once any player activates it "
            "(placing activates it for the placer), and from then on every player sees them. Not carried over: "
            "the runes' full-brightness glow and the disableTextGlow client option"
            + ("" if len(rune_blocks) == len(kept_ways) else
               f"; {', '.join(i for i in kept_ways if i not in rune_blocks)} are drawn without runes")
            + ". ")
    else:
        _, why_ways = _runes(mod, "waystone")
        ways_runes = ("Not carried over: the runes a Java client draws on an activated waystone (code-rendered"
                      f"{'; ' + why_ways if why_ways else ''}). ")
    if kept_ways:
        result.notes.append(
            f"{NS}: {len(kept_ways)} waystone block(s) work through a Script API runtime ({SCRIPT_MODULE} "
            f"{SCRIPT_VERSION} and {UI_MODULE} {UI_VERSION}, {data_path}): {', '.join(kept_ways)}. Placing one "
            "sets its upper half (it needs a free block above), activates it for the placer and asks for its name; "
            "using a waystone activates it for that player, or opens a menu of the waystones the player has "
            "activated (in activation order, the one in use left out); choosing one teleports the player beside it "
            "and takes the experience cost of the warpRequirements default (distance x 0.01 points in the same "
            "dimension, 27 between dimensions, at most 27; creative players go even when they can't pay). "
            "Sneak-using renames it (only its owner). Breaking either half removes both and the waystone. Not "
            "carried over: visibility (every waystone is visible upon activation), the waystone's modifier slots "
            "and warp modifiers, groups, aliases, favourites, sorting and search in the menu, deleting entries from "
            "it, pets and leashed mobs travelling along, waterlogging, the particles, the comparator signal, "
            "observers, a silk-touched waystone keeping its identity when moved (it is a new waystone), "
            "operator edit permission, teleports into a chunk that is not loaded checking for room (the "
            "player lands on the waystone's front), the 'free space' tests (placing needs air or liquid above, "
            "and only air or liquid count as room beside a target, where Java also accepts replaceable or "
            "non-suffocating blocks like grass), the other half going when one is removed by anything but a "
            "player (an explosion), and config changes "
            "(the cited defaults are used). The item shows the lower half only. " + ways_runes
            + ("Village and wild waystone generation, warp portals, fleeting memorials and the warp stone, "
               "scrolls and feather are not converted (warp plates have their own note)." if kept_plate else
               "Village and wild waystone "
               "generation, warp plates and portals, fleeting memorials and the warp "
               "stone, scrolls, shards and feather are not converted.")
            + (" Silk touch drops a plain waystone." if silk else "")
        )
    runes_on = [i for i in kept_share if _has_runes(i)]
    if kept_share and runes_on:
        looks = (
            f"Its coloured runes are drawn as Java draws them: the jar's {RUNE_MODEL} model as part of the "
            "block, in the texture tinted at convert time with the colour's DyeColor texture diffuse colour "
            "(block) and text colour (item, through minecraft:item_visual), turned with the block's facing as "
            "the Java renderer turns them, without face shading or ambient occlusion; the item shows the lower "
            "half with its runes"
            + ("" if len(runes_on) == len(kept_share) else
               f" ({', '.join(i for i in kept_share if i not in runes_on)} without runes)")
            + ". Not carried over: the runes' full-brightness glow (Bedrock materials have no emissive "
            "setting), the floating, spinning warp stone a Java client draws above it, ")
    else:
        _, why_runes = _runes(mod, "sharestone")
        looks = ("Not carried over: the coloured runes and the floating warp stone a Java client draws on it "
                 f"(code-rendered{'; ' + why_runes if why_runes else ''}, so every colour looks the same here; "
                 "the colour is in the item's name), ")
    if kept_share:
        result.notes.append(
            f"{NS}: {len(kept_share)} sharestone block(s) work through the same runtime ({data_path}): "
            f"{', '.join(kept_share)}. Placing one sets its upper half, makes the placer its owner and asks for "
            "its name; using one opens a menu of every other sharestone of the same colour in the world (any "
            "dimension, in the order they were placed; nothing to activate), and choosing one teleports the "
            "player beside it for the same warpRequirements experience cost as a waystone (the defaults have no "
            "sharestone rule). Sneak-using renames it (only its owner); breaking either half removes both and "
            "the sharestone. " + looks + "the item tooltip, the menu's sorting, search and deleting (creative "
            "deletion removes a sharestone from the network in Java), and the rest listed for waystones (pets "
            "and leashed mobs, waterlogging, particles, comparator and observers, the free-space tests, an "
            "unloaded target's room check, explosions taking one half, config changes)."
        )
    port_runes = [i for i in kept_port if _has_runes(i)]
    if port_runes:
        port_looks = (
            f"Its coloured runes are drawn as Java draws them: the jar's {_rune_model('portstone')} model as part "
            "of the block, in the texture tinted at convert time with the colour's DyeColor texture diffuse "
            "colour (block) and text colour (item, through minecraft:item_visual), turned with the block's "
            "facing as the Java renderer turns them, without face shading or ambient occlusion; the item shows "
            "the lower half with its runes"
            + ("" if len(port_runes) == len(kept_port) else
               f" ({', '.join(i for i in kept_port if i not in port_runes)} without runes)")
            + ". Not carried over: the runes' full-brightness glow, the warp stone a Java client draws tilted "
            "on top, ")
    else:
        _, why_port = _runes(mod, "portstone")
        port_looks = ("Not carried over: the coloured runes and the floating warp stone a Java client draws on it "
                      f"(code-rendered{'; ' + why_port if why_port else ''}; every colour looks the same here, "
                      "the colour is in the item's name), ")
    if kept_port:
        result.notes.append(
            f"{NS}: {len(kept_port)} portstone block(s) work through the same runtime ({data_path}): "
            f"{', '.join(kept_port)}. A portstone is no waystone: placing one sets its upper half and nothing "
            "else (no owner, no name, nothing activated), and it never appears in a menu. Using one opens a "
            "menu titled with its colour of every sharestone of that colour (any dimension, in placement "
            "order), or, for the white portstone (white has no sharestone), of the waystones the player has "
            "activated; choosing one teleports the player beside it from wherever they stand (Java checks no "
            "distance to a portstone), for the warpRequirements experience cost (the defaults have no "
            "portstone rule: distance x 0.01 points, 27 between dimensions, at most 27). Breaking either half "
            "removes both. " + port_looks
            + "the item tooltip, global and team waystones in the white portstone's list (visibility is not "
            "carried), the menu's sorting, search and deleting, and the rest listed for waystones (pets and "
            "leashed mobs, waterlogging, the free-space tests, an unloaded target's room check, explosions "
            "taking one half, config changes)."
        )
    if kept_plate:
        plate = table["warp_plates"]
        locked = plate["shards"]["locked"]
        result.notes.append(
            f"{NS}: {len(kept_plate)} warp plate block(s) work through the same runtime ({data_path}): "
            f"{', '.join(kept_plate)}. Placing one makes it a warp plate owned by the placer holding a dormant "
            f"shard, which attunes to that plate after {ATTUNEMENT_TICKS} ticks and pops out as an attuned shard "
            "(with the chicken-egg sound); using a plate with a warp shard puts one in when it holds none "
            "(creative keeps the item), and sneak-using it with empty hands pops its shard out. A plate holding "
            "a shard attuned to another plate teleports whatever stands on it (players, mobs, items; not the "
            f"entities on the deny list, {', '.join(plate['deny'])}, nor riders) to that plate after "
            f"{plate['use_time']} ticks (warpPlateUseTime); an entity that arrives may not use that plate again "
            f"until it has been off it for {plate['cooldown']} ticks (warpPlateCooldownTime). The cost is the "
            "warpRequirements default decided for a plate-to-plate teleport (free at the defaults: "
            "source_is_warp_plate multiplies it by 0). A player is told on the action bar when the plate's "
            "shard has no attunement or its plate is gone, or when they can't pay. The block shows Java's "
            "status models (empty, attuning or attuned, "
            + ("locked by a deepslate shard" if locked else "locked") + "). The attuned shard holds at most 1 "
            "and the crumbling attuned shard 4, as in Java; the attunement rides on the attuned shard as "
            "script data. Breaking a plate drops it and, outside creative, its shard. The item shows the empty "
            "plate (Bedrock draws the block's default state; Java's item is the whole plate). Not carried over: "
            "the rune mark tinted with the plate's galactic name colour (left out of the model), the item's tinted "
            "runes, the settings screen (name, visibility, the modifier slots and every warp modifier: effects, "
            "use-time amethyst and slime, quartz round-robin, spider eye, redstone torch), the generated name, "
            "the particles of each status and the eject effect, shard tooltips and glint, pets and leashed "
            "mobs travelling along, a crumbling shard's attunement (a stackable item can't hold script data, "
            "so a crumbling shard warps nowhere), a silk-touched plate keeping its identity, and config "
            "changes (the cited defaults are used). Entities count as on a plate when their position is in "
            "its block (Java tests their bounding box)."
        )
    entry = (
        'import { registerWaystones } from "./waystone.js";\n'
        f'import waystoneTable from "./data/{NS}_waystone.js";\n'
        "registerWaystones(waystoneTable);\n"
    )
    return result, entry
