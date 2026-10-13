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
  and shape read from the mod's block code (:data:`CUTTING_BOARD_BLOCKS`), and
  given the runtime's custom component here.

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
from dataclasses import dataclass
from importlib import resources
from pathlib import PurePosixPath

from ..conditions import LoadContext
from ..model import ConversionResult, SourceMod, Unhandled
from .lang import _translate_key
from .recipes import emitted_definitions
from .tags import TagResolver

SCRIPT_MODULE = "@minecraft/server"
SCRIPT_VERSION = "2.0.0"
# Block JSON format that reads a namespaced custom component key (custom
# components v2): 1.21.90 (minecraft.net 1.21.90 Bedrock changelog, "Custom
# components v2 is available in JSON versions 1.21.90 and higher").
SCRIPT_FORMAT = "1.21.90"
ENGINE_FLOOR = (1, 21, 90)
ENTRY = "scripts/portkit/main.js"
_RUNTIME_DIR = "scripts/portkit"
RESIDUE_KIND = "station_recipe"

CUTTING = "farmersdelight:cutting"
COOKING = "farmersdelight:cooking"
RECIPE_TYPES = frozenset({CUTTING, COOKING})
# Recipe types a station reads while they also convert as ordinary recipes
# (recipes.STATION_SHARED_TYPES): the stove cooks campfire recipes.
CAMPFIRE = "minecraft:campfire_cooking"
SHARED_TYPES = frozenset({CAMPFIRE})

FD_NEO = ("https://github.com/vectorwing/FarmersDelight", "dd8b9b0bfec916a2da88a6d64e3a37f4a02c3259")
FD_FAB = ("https://github.com/MehVahdJukaar/FarmersDelightRefabricated",
          "a8cb49ed05f3ed5ab857dffe64d8c70309b7d7be")


def _src(repo: tuple[str, str], path: str, line: str) -> str:
    return f"{repo[0]}/blob/{repo[1]}/src/main/java/vectorwing/farmersdelight/{path}#L{line}"


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


# Farmer's Delight's cutting board, both corpus builds: FACING is
# getHorizontalDirection().getOpposite() and SHAPE is box(1, 0, 1, 15, 1, 15).
CUTTING_BOARD_BLOCKS = {
    "neoforge": FacingBlock(
        "cutting_board", 180, {"origin": [-7, 0, -7], "size": [14, 1, 14]},
        (_src(FD_NEO, "common/block/CuttingBoardBlock.java", "125"),
         _src(FD_NEO, "common/block/CuttingBoardBlock.java", "52")),
    ),
    "fabric": FacingBlock(
        "cutting_board", 180, {"origin": [-7, 0, -7], "size": [14, 1, 14]},
        (_src(FD_FAB, "common/block/CuttingBoardBlock.java", "121"),
         _src(FD_FAB, "common/block/CuttingBoardBlock.java", "50")),
    ),
}

# Versions whose cutting-board code the runtime was checked against. Another
# version may behave differently, so it stays residue instead of borrowing.
_FD_VERSIONS = {
    "neoforge": "1.3.4",
    "fabric": "26.1-3.6.28+refabricated",
}

# What FD's cutting board means by a tool ability. NeoForge decides
# ``item_ability`` in code (ItemStack.canPerformAction); Farmer's Delight
# Refabricated, the same recipes on Fabric, defines each ability FD uses as
# one item tag (refabricated/ItemAbility.java L37-45). NeoForge's vanilla
# holders are the classes NeoForge gives the matching DEFAULT_*_ACTIONS set
# (neoforge 1.21.1 ItemAbilities.java L152-157), whose vanilla items are that
# tag's vanilla members, and FD's KnifeItem (KNIFE_ACTIONS, KnifeItem.java
# L53) is the five knives FD puts in c:tools/knife; every NeoForge recipe also
# lists the tag itself beside the ability. So the ability reads as its tag on
# both loaders, resolved like any other tag ingredient.
ABILITY_TAGS = {
    "axe_dig": "minecraft:axes",
    "axe_strip": "minecraft:axes",
    "hoe_dig": "minecraft:hoes",
    "pickaxe_dig": "minecraft:pickaxes",
    "shovel_dig": "minecraft:shovels",
    "sword_dig": "minecraft:swords",
    "shears_carve": "c:tools/shear",
    "shears_dig": "c:tools/shear",
    "shears_harvest": "c:tools/shear",
    "knife_dig": "c:tools/knife",
    "knife_harvest": "c:tools/knife",
}
# Abilities NeoForge's FD knives also perform (KnifeItem KNIFE_ACTIONS,
# KnifeItem.java L53: SHEARS_CARVE and SWORD_DIG beside the two knife ones).
# On NeoForge such an ability accepts the knives as well as the tag's members,
# so reading it as the tag alone would narrow the recipe; it stays residue
# there (no 1.3.4 recipe uses either).
NEOFORGE_KNIFE_SHARED = frozenset({"sword_dig", "shears_carve"})
ABILITY_SOURCES = (
    _src(FD_FAB, "refabricated/ItemAbility.java", "37-L45"),
    "https://github.com/neoforged/NeoForge/blob/3cae64530de368936d4c07497d3f0a25e2f9ffec/"
    "src/main/java/net/neoforged/neoforge/common/ItemAbilities.java#L152-L157",
    _src(FD_NEO, "common/item/KnifeItem.java", "53"),
)
_ABILITY_TYPES = ("farmersdelight:item_ability",)

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


@dataclass(frozen=True)
class CuttingBoardSpec:
    """The cutting board's fixed numbers, read from FD's code per loader."""

    loader: str
    sounds: dict
    sound_tags: dict  # role -> Java tag the tool must be in for that default sound
    messages: dict  # role -> Java lang key
    fortune_bonus: float
    sources: tuple[str, ...]


def _cutting_spec(loader: str) -> CuttingBoardSpec:
    repo = FD_NEO if loader == "neoforge" else FD_FAB
    be = "common/block/entity/CuttingBoardBlockEntity.java"
    block = "common/block/CuttingBoardBlock.java"
    neo = loader == "neoforge"
    return CuttingBoardSpec(
        loader=loader,
        # place_item / remove_item are FD events that play block.wood.place /
        # block.wood.hit (assets/farmersdelight/sounds.json); volume and pitch
        # from CuttingBoardBlock.useItemOn; the processing sounds from
        # CuttingBoardBlockEntity.playProcessingSound.
        sounds={
            "place": {"id": VANILLA_SOUNDS["minecraft:block.wood.place"], "volume": 1.0, "pitch": 0.8},
            "remove": {"id": VANILLA_SOUNDS["minecraft:block.wood.hit"], "volume": 0.25, "pitch": 0.5},
            "shears": {"id": VANILLA_SOUNDS["minecraft:entity.sheep.shear"], "volume": 1.0, "pitch": 1.0},
            "knife": {"id": "farmersdelight:block.cutting_board.knife_cut", "volume": 0.8, "pitch": 1.0},
            "other": {"id": VANILLA_SOUNDS["minecraft:block.wood.break"], "volume": 1.0, "pitch": 0.8},
            "recipe": {"volume": 1.0, "pitch": 1.0},
            # ItemStack#hurtAndBreak breaking the tool plays entity.item.break;
            # its volume and pitch are set in Minecraft's own code, not cited
            # here, so Bedrock's defaults.
            "break": {"id": VANILLA_SOUNDS["minecraft:entity.item.break"], "volume": 1.0, "pitch": 1.0},
        },
        sound_tags={"shears": "c:tools/shear", "knife": "c:tools/knife"},
        # No matching recipe: NeoForge says invalid_tool, Refabricated
        # invalid_item (the two builds swap the keys).
        messages={
            "no_recipe": ("block.farmersdelight.cutting_board.invalid_tool" if neo
                          else "block.farmersdelight.cutting_board.invalid_item"),
            "remaining": "block.farmersdelight.cutting_board.remaining_items",
        },
        # Configuration.cuttingBoardFortuneBonus default (a double, not a
        # boolean flag, so --config doesn't reach it yet).
        fortune_bonus=0.1,
        sources=(
            _src(repo, block, "65-L101" if neo else "67-L106"),
            _src(repo, be, "92-L130" if neo else "94-L131"),
            _src(repo, be, "153-L167" if neo else "152-L166"),
            _src(repo, "common/crafting/ingredient/ChanceResult.java", "22-L33" if neo else "30-L41"),
            _src(repo, "common/Configuration.java", "84-L85"),
        ),
    )


def station_blocks(mod: SourceMod) -> dict[str, FacingBlock]:
    """Blocks of ``mod`` that a station runtime makes work, by blockstate name."""
    if _unsupported(mod) is not None:
        return {}
    from .cooking_pot import COOKING_POT_BLOCKS
    from .feasts import feast_blocks
    from .skillet import SKILLET_BLOCKS
    from .stove import STOVE_BLOCKS

    blocks = {}
    for block in (CUTTING_BOARD_BLOCKS[mod.loader], COOKING_POT_BLOCKS[mod.loader], STOVE_BLOCKS[mod.loader],
                  SKILLET_BLOCKS[mod.loader], *feast_blocks(mod).values()):
        blocks[block.name] = block
    return blocks


def station_loot(mod: SourceMod) -> set[str]:
    """Block loot tables (names under loot_table/blocks/) a station reads."""
    from .feasts import loot_names

    return loot_names(mod)


def _unsupported(mod: SourceMod, station: str = "cutting-board", block: str = "cutting board") -> str | None:
    """Why this jar's station has no runtime, or None when it has one."""
    if mod.namespace != "farmersdelight":
        return (f"a Farmer's Delight {station} recipe in namespace {mod.namespace!r}; the "
                f"{block} is Farmer's Delight's block, which is not in this jar")
    version = (mod.mods or {}).get("farmersdelight")
    if mod.loader not in _FD_VERSIONS or version != _FD_VERSIONS[mod.loader]:
        known = ", ".join(f"{v} ({k})" for k, v in sorted(_FD_VERSIONS.items()))
        return (f"Farmer's Delight {version or '(unknown version)'} on {mod.loader or 'an unknown loader'}: "
                f"the {station} runtime follows FD's code at the versions it was read from "
                f"({known}), and this one's wasn't")
    return None


def _strings(value) -> list:
    return value if isinstance(value, list) else [value]


def _kind(entry) -> str | None:
    if not isinstance(entry, dict):
        return None
    kind = entry.get("type") or entry.get("fabric:type")
    return kind if isinstance(kind, str) else None


# Union ingredients: any child matches. NeoForge's neoforge:compound
# (CompoundIngredient, "children" or its alias "ingredients"; neoforge 1.21.1
# CompoundIngredient.java L26, registered as "compound" in NeoForgeMod.java
# L364) and Fabric API's fabric:any ("ingredients").
def _union(entry) -> list | None:
    kind = _kind(entry)
    if kind == "neoforge:compound":
        children = entry.get("children", entry.get("ingredients"))
    elif kind == "fabric:any":
        children = entry.get("ingredients")
    else:
        return None
    return children if isinstance(children, list) and children else None


class _Refuse(Exception):
    """A recipe this conversion can't state exactly; carries the reason."""


class _Resolver:
    """Item and tag references in a cutting recipe, as ids this addon holds."""

    def __init__(self, mod: SourceMod, tags: TagResolver, emitted: dict):
        self.mod = mod
        self.tags = tags
        self.emitted = emitted

    def item(self, ident: str, role: str) -> str:
        ident = ident if ":" in ident else f"minecraft:{ident}"
        if not ident.startswith("minecraft:") and ident not in self.emitted:
            raise _Refuse(f"{role} {ident} is not converted")
        return ident

    def tag(self, tag: str, role: str) -> list[str]:
        found = self.tags.members(tag)
        if found is None:
            raise _Refuse(f"{role} tag {tag!r}: {self.tags.resolve(tag).reason or 'membership unknown'}")
        if not found.members:
            raise _Refuse(f"{role} tag {tag!r} has no member this addon can hold")
        missing = [m for m in found.members if not m.startswith("minecraft:") and m not in self.emitted]
        if missing:
            raise _Refuse(f"{role} tag {tag!r}; not converted: {', '.join(missing)}")
        return list(found.members)

    def ingredient(self, spec, role: str) -> tuple[list[str], list[str]]:
        """(item ids, Java tags read) for one ingredient: an item, a tag, an
        ability (tool only) or any union of them (a JSON list, NeoForge's
        ``neoforge:compound``, Fabric's ``fabric:any``)."""
        items: list[str] = []
        tags: list[str] = []
        for entry in _strings(spec):
            children = _union(entry)
            kind = _kind(entry)
            if children is not None:
                got, read = self.ingredient(children, role)
                items += got
                tags += read
            elif isinstance(entry, str):
                if entry.startswith("#"):
                    tags.append(entry[1:])
                    items += self.tag(entry[1:], role)
                else:
                    items.append(self.item(entry, role))
            elif role == "tool" and kind in _ABILITY_TYPES:
                action = entry.get("action")
                tag = ABILITY_TAGS.get(action)
                if tag is None:
                    raise _Refuse(f"tool ability {action!r} has no tag FD's code reads it as")
                if self.mod.loader == "neoforge" and action in NEOFORGE_KNIFE_SHARED:
                    raise _Refuse(
                        f"tool ability {action!r}: on NeoForge Farmer's Delight's knives perform it too "
                        f"(KnifeItem KNIFE_ACTIONS), so it is more than #{tag}"
                    )
                tags.append(tag)
                items += self.tag(tag, "tool")
            elif kind == "neoforge:difference":
                # NeoForge's DifferenceIngredient: what ``base`` matches and
                # ``subtracted`` doesn't (neoforge 1.21.1
                # common/crafting/DifferenceIngredient.java, "base" and
                # "subtracted"), stated as the item list that leaves.
                if not isinstance(entry.get("base"), (dict, list, str)) or "subtracted" not in entry:
                    raise _Refuse(f"{role} neoforge:difference needs base and subtracted")
                base, read = self.ingredient(entry["base"], role)
                minus, _ = self.ingredient(entry["subtracted"], role)
                left = [i for i in base if i not in set(minus)]
                if not left:
                    raise _Refuse(f"{role} neoforge:difference leaves no item")
                items += left
                tags += read
            elif kind == "farmersdelight:tool_action":
                raise _Refuse(
                    f"{role} ingredient type {kind!r} is not one Farmer's Delight 1.21 registers (it registers "
                    "farmersdelight:item_ability only, ModIngredientTypes.java), so Java doesn't load this recipe"
                )
            elif kind is not None:
                raise _Refuse(f"{role} ingredient type {kind!r} is not one the table can state")
            elif isinstance(entry, dict) and set(entry) <= {"item", "count"} and isinstance(entry.get("item"), str):
                items.append(self.item(entry["item"], role))
            elif isinstance(entry, dict) and set(entry) == {"tag"} and isinstance(entry["tag"], str):
                tags.append(entry["tag"])
                items += self.tag(entry["tag"], role)
            else:
                raise _Refuse(f"{role} {json.dumps(entry, sort_keys=True)} is not an item, a tag or a list of them")
        if not items:
            raise _Refuse(f"{role} names no item")
        return list(dict.fromkeys(items)), tags

    def tool(self, spec) -> dict:
        """The tool as {items, tags}: every item id it accepts, and the Bedrock
        tool tags of the same meaning as the Java tags it reads."""
        items, read = self.ingredient(spec, "tool")
        bedrock = sorted({BEDROCK_TOOL_TAGS[t] for t in read if t in BEDROCK_TOOL_TAGS})
        return {"items": sorted(set(items)), "tags": bedrock}

    def result(self, entry) -> dict:
        if not isinstance(entry, dict) or "item" not in entry:
            raise _Refuse(f"result {json.dumps(entry, sort_keys=True)} has no item")
        stack = entry["item"]
        if isinstance(stack, str):  # pre-1.20.5 form: {"item": id, "count": n}
            ident, count, extra = stack, entry.get("count", 1), set(entry) - {"item", "count", "chance"}
        elif isinstance(stack, dict):
            ident, count, extra = stack.get("id"), stack.get("count", 1), set(stack) - {"id", "count"}
        else:
            raise _Refuse(f"result {json.dumps(entry, sort_keys=True)} has no item")
        if extra:
            raise _Refuse(f"result {ident} carries {', '.join(sorted(extra))}, which the table doesn't hold")
        chance = entry.get("chance", 1.0)
        if not isinstance(ident, str) or not isinstance(count, int) or count < 1:
            raise _Refuse(f"result {json.dumps(entry, sort_keys=True)} has no readable id and count")
        if not isinstance(chance, (int, float)):
            raise _Refuse(f"result {ident} has an unreadable chance")
        return {"item": self.item(ident, "result"), "count": count, "chance": float(chance)}


def _sound(recipe: dict) -> str | None:
    sound = recipe.get("sound")
    if sound is None:
        return None
    if isinstance(sound, dict):
        sound = sound.get("sound_id")
    return sound if isinstance(sound, str) else ""


def _recipe_id(mod: SourceMod, rel: str) -> str:
    path = PurePosixPath(rel)
    parts = path.parts
    # data/<ns>/recipe(s)/<path>.json -> <ns>:<path>
    return f"{parts[1]}:{PurePosixPath(*parts[3:]).with_suffix('').as_posix()}"


def _cutting_entry(mod: SourceMod, rel: str, recipe: dict, resolve: _Resolver, notes: list[str],
                   shipped: set[str]) -> dict:
    ingredients = recipe.get("ingredients")
    if not isinstance(ingredients, list) or len(ingredients) != 1:
        raise _Refuse("a cutting recipe takes exactly one ingredient (CuttingBoardRecipe codec)")
    items, _tags = resolve.ingredient(ingredients[0], "ingredient")
    results = recipe.get("result")
    if not isinstance(results, list) or not results or len(results) > 4:
        raise _Refuse("a cutting recipe has one to four results (CuttingBoardRecipe.MAX_RESULTS)")
    entry = {
        "id": _recipe_id(mod, rel),
        "ingredient": sorted(items),
        "tool": resolve.tool(recipe.get("tool")),
        "results": [resolve.result(r) for r in results],
    }
    sound = _sound(recipe)
    if sound:
        full = sound if ":" in sound else f"minecraft:{sound}"
        bedrock = VANILLA_SOUNDS.get(full) or (full if full in shipped else None)
        if bedrock is None:
            # Java would play this sound instead of the tool's default; play
            # nothing rather than the wrong one.
            notes.append(f"{rel}: recipe sound {sound!r} has no Bedrock event that plays the same "
                         "audio; the cut is silent")
            entry["sound"] = None
        else:
            entry["sound"] = bedrock
    elif sound == "":
        raise _Refuse("unreadable sound")
    return entry


def _overlaps(entries: list[dict]) -> dict[str, list[str]]:
    """Recipes another recipe also matches (same item and a shared tool).

    Java takes the first match in its recipe manager, an order no file states,
    so neither recipe of such a pair is written.
    """
    clash: dict[str, list[str]] = {}
    for i, a in enumerate(entries):
        for b in entries[i + 1:]:
            if not set(a["ingredient"]) & set(b["ingredient"]):
                continue
            if set(a["tool"]["items"]) & set(b["tool"]["items"]) or set(a["tool"]["tags"]) & set(b["tool"]["tags"]):
                clash.setdefault(a["id"], []).append(b["id"])
                clash.setdefault(b["id"], []).append(a["id"])
    return clash


def runtime_source(name: str) -> str:
    """A fixed runtime script, verbatim from the package."""
    return resources.files("portkit.runtime").joinpath(name).read_text(encoding="utf-8")


def _js_module(header: str, table: dict) -> str:
    body = json.dumps(table, indent=1, sort_keys=True, ensure_ascii=False)
    return f"{header}\nexport default {body};\n"


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


def _component(mod: SourceMod) -> str:
    return f"{mod.namespace}:portkit_cutting_board"


def convert(mod: SourceMod, deferred: list[tuple[str, dict]], files: dict,
            context: LoadContext, loot: list[tuple[str, dict]] | None = None) -> ConversionResult:
    """Each station's data table and runtime for the recipes ``deferred`` holds.

    ``deferred`` is (source path, recipe) for every recipe of a
    :data:`RECIPE_TYPES` or :data:`SHARED_TYPES` type whose load conditions
    passed; the recipes are split by type and each station converter writes its
    own table, runtime and block. The stove runs whenever its block converted,
    since vanilla's own campfire recipes fill its table too; the skillet
    cooks the same table. ``loot`` is (source path, table) for the block loot
    tables the loot converter left to a station (the feasts',
    :func:`portkit.converters.feasts.loot_names`). The entry :data:`ENTRY`
    imports every station that shipped.
    """
    from . import cooking_pot, feasts, skillet, stove

    result = ConversionResult()
    entries: list[str] = []
    cutting = [d for d in deferred if d[1].get("type") == CUTTING]
    cooking = [d for d in deferred if d[1].get("type") == COOKING]
    campfire = [d for d in deferred if d[1].get("type") == CAMPFIRE]
    for converted, entry in (_convert_cutting(mod, cutting, files, context),
                             cooking_pot.convert(mod, cooking, files, context),
                             stove.convert(mod, campfire, files, context),
                             skillet.convert(mod, campfire, files, context),
                             feasts.convert(mod, loot or [], files, context)):
        result = result.merge(converted)
        if entry:
            entries.append(entry)
    if entries:
        result.files[f"{_RUNTIME_DIR}/station_storage.js"] = runtime_source("station_storage.js")
        result.files[ENTRY] = (
            "// Generated by portkit: wires each station's data table to its fixed runtime.\n"
            + "".join(entries)
        )
    return result


def _convert_cutting(mod: SourceMod, deferred: list[tuple[str, dict]], files: dict,
                     context: LoadContext) -> tuple[ConversionResult, str]:
    """The cutting board's data table and runtime for the recipes ``deferred`` holds.

    ``deferred`` is (source path, recipe) for every recipe of a
    :data:`RECIPE_TYPES` type whose load conditions passed
    (:func:`portkit.converters.recipes.convert`); ``files`` is what the
    namespace's converters wrote so far, so the block and the items the table
    names can be checked against it.
    """
    result = ConversionResult()
    if not deferred:
        return result, ""
    why = _unsupported(mod)
    block = CUTTING_BOARD_BLOCKS.get(mod.loader or "")
    block_path = f"blocks/{block.name}.json" if block else None
    block_body = files.get(block_path) if block_path else None
    identifier = f"{mod.namespace}:{block.name}" if block else None
    if why is None and not (isinstance(block_body, dict)
                            and block_body.get("minecraft:block", {}).get("description", {})
                            .get("identifier") == identifier):
        why = f"the cutting board block ({identifier}) did not convert, so there is no station to run on"
    if why is not None:
        for rel, _ in deferred:
            result.unhandled.append(Unhandled(rel, RESIDUE_KIND, why))
        return result, ""

    spec = _cutting_spec(mod.loader)
    emitted = emitted_definitions(files)
    resolve = _Resolver(mod, context.tags, emitted)
    notes: list[str] = []
    shipped = _shipped_sounds(files)
    entries: list[tuple[str, dict]] = []
    for rel, recipe in sorted(deferred, key=lambda d: d[0]):
        try:
            entries.append((rel, _cutting_entry(mod, rel, recipe, resolve, notes, shipped)))
        except _Refuse as refusal:
            result.unhandled.append(Unhandled(rel, RESIDUE_KIND, str(refusal)))
    clash = _overlaps([e for _, e in entries])
    kept = []
    for rel, entry in entries:
        if entry["id"] in clash:
            result.unhandled.append(Unhandled(rel, RESIDUE_KIND, (
                f"another cutting recipe ({', '.join(sorted(clash[entry['id']]))}) takes the same item "
                "with the same tool; Java uses whichever its recipe manager finds first, an order no "
                "file states")))
        else:
            kept.append(entry)

    sound_tools = {}
    for role, tag in spec.sound_tags.items():
        found = context.tags.members(tag)
        sound_tools[role] = sorted(found.members) if found is not None else []
    knife_sound = spec.sounds["knife"]["id"]
    sounds = dict(spec.sounds)
    if knife_sound not in shipped:
        sounds["knife"] = None
        notes.append(f"cutting board: knife sound {knife_sound} did not convert; knife cuts are silent")
    messages = {role: _lang_key(mod, key) for role, key in spec.messages.items()}

    table = {
        "block": identifier,
        "component": _component(mod),
        "fortune_bonus": spec.fortune_bonus,
        "messages": messages,
        "recipes": sorted(kept, key=lambda e: e["id"]),
        "sound_tools": sound_tools,
        "sounds": sounds,
    }
    data_path = f"{_RUNTIME_DIR}/data/{mod.namespace}_cutting_board.js"
    header = (
        f"// Generated by portkit from {mod.namespace}'s {CUTTING} recipes; do not edit.\n"
        f"// Read by the fixed runtime {_RUNTIME_DIR}/cutting_board.js (portkit/runtime). Sources:\n"
        + "".join(f"//   {s}\n" for s in (*spec.sources, *block.sources, *ABILITY_SOURCES))
    ).rstrip("\n")
    result.files[data_path] = _js_module(header, table)
    result.files[f"{_RUNTIME_DIR}/cutting_board.js"] = runtime_source("cutting_board.js")
    result.files[f"{_RUNTIME_DIR}/cutting_board_core.js"] = runtime_source("cutting_board_core.js")
    entry = (
        'import { registerCuttingBoard } from "./cutting_board.js";\n'
        f'import cuttingBoardTable from "./data/{mod.namespace}_cutting_board.js";\n'
        "registerCuttingBoard(cuttingBoardTable);\n"
    )

    # The block gets the runtime's custom component (and the format that reads it).
    body = json.loads(json.dumps(block_body))
    body["format_version"] = SCRIPT_FORMAT
    body["minecraft:block"].setdefault("components", {})[_component(mod)] = {}
    result.files[block_path] = body

    for rel, _ in deferred:
        result.consumed.add(rel)
    result.stations[CUTTING] = {
        "converted": len(kept),
        "residue": len(deferred) - len(kept),
        "data": data_path,
        "block": identifier,
    }
    result.notes.extend(notes)
    result.notes.append(
        f"{identifier}: {len(kept)} of {len(deferred)} {CUTTING} recipes run on the cutting board through "
        f"a Script API runtime ({SCRIPT_MODULE} {SCRIPT_VERSION}, {data_path}). Not carried over: the item "
        "drawn on the board (Bedrock has no block renderer for it), sneak-placing a tool on the board, "
        "cutting particles, the comparator signal, waterlogging, dispensers using the board, the "
        "advancement and item-use statistic, the stored item when the board is destroyed by "
        "anything but a player (no break event for that in script API 2.0.0), the stored block's own "
        "break sound as a cut sound (scripts can't read a block's sound type; that cut is silent), and "
        f"cuttingBoardFortuneBonus overrides (the cited default {spec.fortune_bonus} is used). A stored "
        "stack keeps its id, count, name, lore, durability damage and enchantments only."
    )
    return result, entry


def _shipped_sounds(files: dict) -> set[str]:
    """Sound events this pack's sound_definitions.json defines."""
    defs = files.get("sounds/sound_definitions.json")
    if not isinstance(defs, dict):
        return set()
    return set(defs.get("sound_definitions") or {})
