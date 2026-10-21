"""Turn ``Unhandled`` items into agent tasks and run one session per group.

The deterministic converters say exactly what they refused and why. This module
is the bridge from that list to the loop:

1. :func:`group_residue` folds the items by kind and source file, so a
   ``sounds.json`` refused for two different events is one task, not two.
2. :func:`build_task` writes the task prompt: the source content and the
   specific reasons the deterministic path gave, never a generic "convert this".
3. :class:`ResidueAgent` runs one :class:`AgentSession` per group against the
   output tree and keeps a group's writes only if the validator finds no error
   the session introduced. A group that breaks the tree is rolled back, so one
   bad session can never cost the player the installable addon.

A group counts as resolved only when its session ended on its own, it wrote at
least one file, the validator found no new error, and every item and tag its
recipes name exists (in the pack, in the source mod, or in vanilla; see
``refs.py``), and every gameplay number on the items and blocks it wrote
(damage, durability, light, hardness, map colour, ...) is one the source mod
states (see ``stats.py``), and
every namespaced id in its files is in ``minecraft``, the conversion's
namespace or one the mod ships (see ``refs.py``, #147), and every block
state it declares or tests is one the Java blockstate has, with a value Java
lists (see ``states.py``, #149), and every trim recipe it wrote names only
vanilla ``minecraft:`` template and addition slots (see ``trim.py``, #86),
and every item it defines in the mod's or the conversion's namespace is one
the Java source registers (see ``items.py``, #86), under the mod config the
conversion holds: an item a config flag gates off (cited default or
``--config``) is neither defined nor named in any file it writes
(``items.py``, #187).
A group that ends
with any kind of fabrication is rolled back, with the reason listed.
Declaring victory in prose is not enough, and neither is a session that wrote nothing because the Java behaviour
has no Bedrock form: that one stays residue, with the agent's reason attached,
and is reported as ``declined`` rather than ``unresolved`` so a sweep can tell
a reasoned "no Bedrock equivalent" from a session that gave up (#86).

The run's ``status`` sums it up: ``complete`` when every group the agent could
work on resolved, ``partial`` when some did, ``failed`` when none did. It is
separate from whether the pack validates: rolling every group back leaves a
valid pack and a failed agent run.

Every group's spend (steps, tokens, dollars when priced) is reported. Token and
dollar ceilings are per run: once one is reached, the session in flight stops
before its next call, keeping whatever it wrote that still validates, and the
groups after it are skipped with the ceiling named.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..conditions import LoadContext
from ..meta import ModMetadata
from ..model import SourceMod, Unhandled
from ..pack import ENGINE_FLOOR, manifest
from ..validate import validate_tree
from .budget import Budget, Spend
from .items import (
    GatedItem,
    UnknownItem,
    gated_finding,
    gated_ids,
    gated_refs,
    registered_ids,
    unknown_items,
)
from .items import finding as item_finding
from .loop import AgentSession, LLMClient
from .refs import (
    Ref,
    finding,
    namespace_finding,
    source_items,
    unknown_namespace_refs,
    unresolved_refs,
    valid_namespaces,
)
from .states import BadState, invented_states
from .states import finding as state_finding
from .stats import Stat, fabricated_stats
from .stats import finding as stat_finding
from .trim import Trim, fabricated_trims
from .trim import finding as trim_finding
from .tools import SYSTEM_PROMPT, ToolBox

# Kinds no session can make progress on with the tools it has: bytecode is not
# readable text, a nested jar is not unpacked, and a namespace or output
# collision is a decision about the pack (or a converter bug), not a file to
# convert. They stay residue, skipped with a reason rather than burning a
# session.
SKIP_KINDS = {
    "java_code": "compiled bytecode; the agent's tools read text files only",
    "armor": ("the item is armor whose slot and numbers are the mod's code (#274), which the agent's tools "
              "can't read; writing minecraft:wearable without them would invent its stats"),
    "nested_jar": "nested jars are not unpacked, so there is nothing to read",
    "namespace_collision": "a collision is a packaging decision, not a file to convert",
    "output_collision": "two converters wrote one output path; a converter bug, not a file to convert",
    "conditional_recipe": ("Java doesn't load this recipe with only this mod (or whether it does "
                           "can't be decided), so converting it would ship content the mod doesn't have"),
    "conditional_loot_table": ("Java doesn't load this loot table with only this mod (or whether it "
                               "does can't be decided), so converting it would ship content the mod doesn't have"),
    "conditional_item": ("Java doesn't register this item with the mod config this conversion holds "
                         "(a config flag gates it), so converting it would ship content the mod doesn't have"),
    "station_recipe": ("a station recipe runs from the station's script data table, which the agent's "
                       "tools don't write; the reason says what the converter could not state exactly"),
    "feast": ("a feast's loot tables are wired per serving count by the feast runtime (#177), which the "
              "agent's tools don't write; the reason says what the converter could not state exactly"),
    "waystone": ("a waystone's loot table is wired by the waystone runtime (#178), which the agent's tools "
                 "don't write; the reason says what the converter could not state exactly"),
    "worldgen_feature": ("an ore placed feature (or its biome modifier) Bedrock's ore feature and feature rule "
                         "can't state exactly (#281), which the agent's tools don't write; the reason says what"),
    "code_recipe": ("the recipe's result or station is the mod's Java code (#180); a Bedrock recipe "
                    "would have to invent or drop part of it, and the reason says which"),
    "fluid_recipe": ("the recipe melts, alloys, casts or fills with fluid measured in mB at a mod station "
                     "(#174); Bedrock add-ons can't define a fluid or store an amount of one, so there is "
                     "no fluid or station to write it for"),
    "modular_tool": ("the recipe builds, changes or takes apart a modular tool, part or material whose stats "
                     "Java computes per stack (#175); a Bedrock item's components are fixed per item type, "
                     "so a stand-in would invent the numbers"),
    "machine_recipe": ("the recipe runs in a mod machine that works over ticks, a Mekanism machine holding "
                       "energy, chemicals or fluid (#172), a Create machine turned by its rotational network "
                       "(#173) or an Alloy Forgery forge burning fuel at a tier (#171); Bedrock blocks have no "
                       "ticking inventory, energy, fuel store or rotation, so there is no "
                       "station to write it for, and the reason names the machine"),
    "custom_fluid": ("the item holds a mod's fluid and its icon is drawn from that fluid at runtime (#174); "
                     "Bedrock add-ons can't define the fluid, and drawing the icon would invent it"),
    "machine_data": ("data a Java machine reads at runtime (Alloy Forgery forge definitions, tiers, fuels and "
                     "its recipe tags, #171); there is no Bedrock machine to read it until a scripted forge "
                     "exists, and the reason says what the data sets"),
    "entity": ("the file only works with a Java entity (its spawn egg or loot table), and entities don't "
               "convert: a mob's geometry, animations and AI are Java code, so a Bedrock entity would invent "
               "them (#176); the reason says what the bytecode read"),
    "code_only": ("the mod ships nothing Bedrock can hold (explained-empty, #279): this lang text or asset is "
                  "only read by its Java code (screens, HUD, renderer), and the reason names the jar's reason "
                  "classes"),
    # #277 lang: what a .lang line can't carry (portkit.converters.lang).
    "lang_code_string": ("no block, item, entity or creative tab owns the string, so only the mod's Java code "
                         "shows it (screens, tooltips, chat, config, integrations); a Bedrock add-on has no "
                         "text surface for it unless a portkit runtime shows it, and those keys already ship"),
    "lang_unshipped": ("the line names something the pack doesn't ship (a block, item or entity that is "
                       "residue on its own account, another mod's or a vanilla entry, or a registry portkit "
                       "converts none of: effects, enchantments, biomes, fluids, ...), so it would name "
                       "nothing; it ships with its owner when that converts"),
    "lang_locale": ("Bedrock loads texts/ only for its own fixed list of languages, and this locale isn't "
                    "one of them"),
    "lang_unreadable": ("Java's own reader (Gson) rejects the file too, so Java never shows its text and "
                        "there is nothing to carry over"),
    # #277 unowned: leftover models and textures the jar's references explain (portkit.ownership);
    # block loot tables of refused blocks (#299), recipes naming refused items (#302) and
    # recipe advancements of residue recipes (#340).
    "owned_by_residue": ("only residue that has its own entry uses these files (a refused block's blockstate, "
                         "a particle definition), or they need such residue (a refused block's loot table, a "
                         "recipe naming refused items, a recipe advancement of a residue recipe): they ship "
                         "with their owner when it converts, not alone"),
    "java_only_asset": ("nothing in the jar's JSON names these files, so only the mod's Java code draws them "
                        "(screens, entity and block-entity renderers, effect icons, armor layers, custom model "
                        "loaders) or, for atlases, Java's texture stitcher reads them; nothing in a Bedrock "
                        "pack would draw them"),
    # #293 leftover data tags (portkit.datatags).
    "tag_unshipped_registry": ("a tag of a registry portkit converts nothing of (fluids, biomes, structures, "
                               "enchantments, damage types, entity types, ...), so the pack holds nothing it "
                               "could group"),
    "tag_unread": ("no data file of the jar reads the tag (only the mod's Java code or other mods would) and "
                   "Bedrock has no tag of that name its own systems read, or it names only vanilla entries an "
                   "add-on can't re-tag; writing it onto items would change nothing"),
    # #296 block residue: a block Java draws only in code (portkit.converters.blocks).
    "code_drawn_block": ("every model the blockstate names bakes no quads (only a particle texture), so the "
                         "block is drawn by the mod's Java code (a block-entity renderer, the fluid renderer or "
                         "a model swapped in at runtime); a Bedrock block definition has no renderer to hand "
                         "that to, and a stand-in geometry would invent the look; or (#352, pending Alex) its "
                         "Java render shape is ENTITYBLOCK_ANIMATED or INVISIBLE for every state, so the "
                         "client never draws its blockstate model in the world"),
    # #352 (pending Alex): a shipped block a block-entity renderer also draws (count 0).
    "renderer_drawn_parts": ("the block shipped as its static blockstate model (Java's render shape is MODEL), "
                             "but a block-entity renderer of the jar also draws its block entity (moving parts "
                             "or contents); no source file is left out, the entry counts 0 files and names "
                             "the renderer"),
    # #277 worldgen and other mods' data the jar explains (portkit.worldgen; PR #316 picks 1a 2a 3a).
    "code_worldgen": ("the worldgen file's type (a feature, placement modifier or pool element) is the mod's "
                      "own Java class, or only the mod's code (or such files) puts it into generation, so what "
                      "it generates and where is code; a Bedrock feature or feature rule would invent it, and "
                      "the reason names the type or the class"),
    "other_mod_data": ("data only another mod reads (its type or target is that mod's namespace, or a compat "
                       "class of this jar registers it; for an assets/ folder, #346 pending Alex: no class of "
                       "this jar names the folder): neither Minecraft, the mod loader nor this mod reads "
                       "it, and that mod isn't converted with this jar; the reason names the mod (or the "
                       "folder) and what the jar shows"),
    # #340 leftover advancements (portkit.advancements).
    "no_bedrock_advancement": ("Bedrock has no data-driven advancements (its achievements are a fixed list, "
                               "minecraft.wiki Achievement): a story or challenge advancement has nothing to "
                               "track or show it and its rewards are not given; a recipe advancement whose "
                               "recipe ships as a furnace recipe (no `unlock` field) or that names no recipe of "
                               "the jar has no converted recipe to carry it; the reason says which"),
    # #342 (Alex, 2026-10-20, pick 2a): a recipe only the #302 expansion cap refuses (portkit.converters.recipes).
    "recipe_over_cap": ("every ingredient is known and converted, but writing every mix Java accepts (one "
                        "recipe per tag member, or per combination of vanilla members across the grid slots, "
                        "#302) takes more recipes than the cap of 16, so it is left unconverted on purpose "
                        "rather than flooding the recipe book; the reason names each tag, its members, its "
                        "slots and the count"),
    # #344 (Alex, 2026-10-20, pick 1a): an item whose look switches on an item property the
    # mod's code registers (portkit.converters.items, portkit.itemprops).
    "live_item_property": ("the item's model swaps its look on an item property the mod's own code "
                           "registers (a compass needle, a gauge, a fill level): Java computes the value "
                           "every frame, and a Bedrock item icon is a static texture with no state "
                           "selection, so nothing in a pack can follow it and a frozen frame could "
                           "state a false reading (#169); the reason names each property and the class "
                           "that builds it"),
    # #346 (pending Alex, pick 2a): a block whose model borrows a vanilla texture outside
    # block/ and item/ (portkit.converters.blocks.refine_outside_atlas).
    "vanilla_texture_outside_atlas": ("the block's model borrows a vanilla texture from outside Java's "
                                      "block/ and item/ folders (an entity skin, misc/ art): Bedrock's block "
                                      "and item atlases list no copy, the pack can't carry Mojang's art (#24) "
                                      "and no same-named Bedrock file is pixel-checked to match, so any "
                                      "texture the agent named would be a stand-in (#87); the reason names "
                                      "the texture"),
    # #348 (pending Alex, pick 1a): a texture sidecar with a Connected Textures Mod "ctm"
    # section and no animation (portkit.converters.textures).
    "connected_texture": ("the texture's .mcmeta carries a \"ctm\" section, which the Connected Textures "
                          "Mod reads, not Minecraft: it picks the texture's look per block from the "
                          "neighbours (ctm, ctmh, ctmv, pillar, sctm, edges), the block's position "
                          "(pattern, random) or only sets its render layer; a Bedrock block texture is "
                          "fixed per face with no neighbour lookup, so a stand-in png would draw a "
                          "pattern sheet or connection layout wrong; the reason names the CTM type"),
    "book": ("a guide book's pages ship through the book viewer's data table and .lang text (#182), which "
             "the agent's tools don't write; the reason says what the viewer can't carry"),
}

# Where Bedrock keeps each kind of content. A hint, not a constraint: the
# validator is still the only thing that decides whether the result is right.
_OUTPUT_HINTS = {
    "recipe": "Bedrock recipes go in behavior_pack/recipes/<name>.json.",
    "loot": "Bedrock loot tables go in behavior_pack/loot_tables/<path>.json.",
    "block": (
        "Bedrock blocks go in behavior_pack/blocks/<name>.json, geometry in "
        "resource_pack/models/blocks/<name>.geo.json."
    ),
    "item": "Bedrock items go in behavior_pack/items/<name>.json.",
    "sound": "Bedrock sounds are declared in resource_pack/sounds/sound_definitions.json.",
    "texture": "Bedrock textures live under resource_pack/textures/.",
    "texture_animation": "Bedrock flipbooks go in resource_pack/textures/flipbook_textures.json.",
    "lang": "Bedrock names go in resource_pack/texts/<Locale>.lang; add them with set_lang_entries.",
}

_BINARY_SUFFIXES = {".png", ".ogg", ".wav", ".class", ".jar", ".nbt"}
_MAX_INLINE_CHARS = 16_000
_MAX_LISTED_FILES = 100


@dataclass
class ResidueGroup:
    """Every Unhandled item that shares a kind and a source."""

    kind: str
    source: str
    items: list[Unhandled] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.source}"

    @property
    def reasons(self) -> list[str]:
        seen: list[str] = []
        for item in self.items:
            if item.reason not in seen:
                seen.append(item.reason)
        return seen

    @property
    def count(self) -> int:
        """Source files this group stands for (an entry per file, not per reason)."""
        return max((item.count for item in self.items), default=0)


def group_residue(unhandled: list[Unhandled]) -> list[ResidueGroup]:
    """Fold residue by (kind, source), keeping first-seen order."""
    groups: dict[tuple[str, str], ResidueGroup] = {}
    for item in unhandled:
        key = (item.kind, item.source)
        if key not in groups:
            groups[key] = ResidueGroup(item.kind, item.source)
        groups[key].items.append(item)
    return list(groups.values())


def _source_block(source_root: Path, source: str) -> str:
    """The source the deterministic path refused, as the task prompt shows it."""
    path = (source_root / source.rstrip("/")).resolve()
    root = source_root.resolve()
    if path != root and root not in path.parents:
        return f"(source {source!r} is not a path inside the mod)"
    if path.is_dir():
        files = sorted(str(p.relative_to(source_root)) for p in path.rglob("*") if p.is_file())
        shown = files[:_MAX_LISTED_FILES]
        more = f"\n... and {len(files) - len(shown)} more" if len(files) > len(shown) else ""
        listing = "\n".join(f"- {f}" for f in shown) or "(empty)"
        return f"Directory {source} holds {len(files)} file(s); read them with read_source:\n{listing}{more}"
    if not path.is_file():
        return f"(no file at {source}; use list_source to look around)"
    if path.suffix.lower() in _BINARY_SUFFIXES:
        return f"{source} is a binary file ({path.stat().st_size:,} bytes); its content is not shown."
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > _MAX_INLINE_CHARS:
        text = text[:_MAX_INLINE_CHARS] + f"\n... (truncated; {len(text):,} chars in total, read_source has the rest)"
    return f"Source file {source}:\n```\n{text}\n```"


def _tree_listing(out_tree: Path) -> str:
    files = sorted(
        str(p.relative_to(out_tree))
        for pack in ("behavior_pack", "resource_pack")
        if (out_tree / pack).is_dir()
        for p in (out_tree / pack).rglob("*")
        if p.is_file()
    )
    shown = files[:_MAX_LISTED_FILES]
    more = f"\n... and {len(files) - len(shown)} more" if len(files) > len(shown) else ""
    return "\n".join(f"- {f}" for f in shown) + more if shown else "(empty)"


def build_task(group: ResidueGroup, source_root: Path, out_tree: Path, namespace: str) -> str:
    """The user message for one session: what was refused, why, and the source."""
    reasons = "\n".join(f"- {r}" for r in group.reasons)
    hint = _OUTPUT_HINTS.get(group.kind, "")
    parts = [
        f"Convert one piece of residue from the Java mod (namespace {namespace!r}) to Bedrock.",
        f"Kind: {group.kind}\nSource: {group.source}",
        f"The deterministic converter refused it because:\n{reasons}",
        _source_block(source_root, group.source),
        f"The output tree already holds:\n{_tree_listing(out_tree)}",
        (
            "Write only the files this residue needs, with paths starting "
            "behavior_pack/ or resource_pack/. Do not rewrite manifests. "
            + hint
        ).strip(),
        (
            "Gameplay numbers (damage, durability, mining speed, armor, food, "
            "cooldowns, enchantability, fuel) and block properties (hardness, blast "
            "resistance, light, friction, flammability, map colour) come only from "
            "the source mod: if it does not state one, omit that component rather "
            "than guess, and say in your final message which ones you left out."
        ),
        (
            "Call validate after writing and fix every finding it names. If this "
            "has no faithful Bedrock equivalent, write nothing and say why in one "
            "sentence; that is a correct answer, not a failure."
        ),
    ]
    return "\n\n".join(parts)


class _TrackingToolBox(ToolBox):
    """A ToolBox that remembers what each write replaced, so a group can roll back."""

    def __init__(self, source: Path, out_tree: Path, namespace: str | None = None,
                 context: LoadContext | None = None):
        super().__init__(source, out_tree)
        self.originals: dict[str, bytes | None] = {}
        self.namespace = namespace
        # The conversion's mod config (cited defaults + --config), for gated
        # items (#187); None checks no gating.
        self.context = context
        self._source_ids: set[str] | None = None  # the source does not change mid-session
        self._registered: set[str] | None = None  # likewise, for the item guard
        self._gated: dict[str, GatedItem] | None = None  # likewise, for gated items

    def _before_write(self, target: Path) -> None:
        rel = str(target.resolve().relative_to(self.out_tree.resolve()))
        if rel not in self.originals:
            self.originals[rel] = target.read_bytes() if target.is_file() else None

    def unresolved(self) -> list[Ref]:
        """Items and tags in this session's recipes that exist nowhere (#86)."""
        return unresolved_refs(self.out_tree, list(self.originals), self.source)

    def unknown_namespaces(self, unresolved: list[Ref] | None = None) -> list[Ref]:
        """Ids in this session's files whose namespace the mod does not have (#147).

        An id the recipe check already reports for the same file is left to it,
        so one bad ingredient is one finding, not two.
        """
        if self._source_ids is None:
            self._source_ids = source_items(self.source)
        if unresolved is None:
            unresolved = self.unresolved()
        reported = {(ref.path, ref.ident) for ref in unresolved}
        return [
            ref for ref in unknown_namespace_refs(
                self.out_tree, list(self.originals), self.source, self.namespace,
                self.originals, _source_ids=self._source_ids,
            )
            if (ref.path, ref.ident) not in reported
        ]

    def valid_namespaces(self) -> set[str]:
        return valid_namespaces(self.source, self.namespace)

    def fabricated(self) -> list[Stat]:
        """Stats on this session's items that the source never states (#135)."""
        return fabricated_stats(self.out_tree, list(self.originals), self.source)

    def invented(self) -> list[BadState]:
        """Block states on this session's blocks that the Java blockstate lacks (#149)."""
        return invented_states(self.out_tree, list(self.originals), self.source)

    def unresolved_trims(self) -> list[Trim]:
        """Written trim recipes whose template or addition is not vanilla (#86)."""
        return fabricated_trims(self.out_tree, list(self.originals), self.source)

    def gated(self) -> dict[str, GatedItem]:
        """Bedrock id -> gated-off Java item under the conversion's config (#187)."""
        if self._gated is None:
            if self.context is None:
                self._gated = {}
            else:
                if self._registered is None:
                    self._registered = registered_ids(self.source)
                if self._source_ids is None:
                    self._source_ids = source_items(self.source)
                self._gated = gated_ids(self._registered | self._source_ids,
                                        self.context.gated_item, self.namespace)
        return self._gated

    def unknown_items(self) -> list[UnknownItem]:
        """Items this session defined that the Java source never registers (#86),
        including ones a config flag gates off here (#187)."""
        if self._registered is None:
            self._registered = registered_ids(self.source)
        return unknown_items(
            self.out_tree, list(self.originals), self.source, self.namespace, self.originals,
            gated=self.gated(), _registered=self._registered,
        )

    def gated_refs(self, items: list[UnknownItem] | None = None) -> list[Ref]:
        """Mentions of a gated-off item in this session's files (#187).

        An item definition the item guard already reports is left to it.
        """
        gated = self.gated()
        if not gated:
            return []
        if items is None:
            items = self.unknown_items()
        return gated_refs(self.out_tree, list(self.originals), gated, self.originals,
                          exclude={(i.path, i.ident) for i in items})

    def validate(self) -> dict:
        # The structural validator only warns on an undeclared item, and does not
        # look at tags at all. What the agent wrote is held to the stricter rule,
        # and it hears about it here so it can fix the reference, not just get
        # rolled back at the end.
        report = super().validate()
        unresolved = self.unresolved()
        extra = [finding(ref) for ref in unresolved]
        valid = self.valid_namespaces()
        extra += [namespace_finding(ref, valid) for ref in self.unknown_namespaces(unresolved)]
        extra += [stat_finding(stat) for stat in self.fabricated()]
        extra += [state_finding(bad) for bad in self.invented()]
        extra += [trim_finding(trim) for trim in self.unresolved_trims()]
        items = self.unknown_items()
        extra += [item_finding(item) for item in items]
        extra += [gated_finding(ref, self.gated()) for ref in self.gated_refs(items)]
        if extra:
            report["findings"] = [*report["findings"], *extra]
            report["error_count"] += len(extra)
            report["ok"] = False
        return report

    def rollback(self) -> None:
        for rel, original in self.originals.items():
            target = self.out_tree / rel
            if original is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(original)


@dataclass
class GroupOutcome:
    key: str
    kind: str
    source: str
    status: str  # resolved | partial | declined | unresolved | rolled_back | skipped | error
    stopped: str = ""  # the session's own stop reason: done | budget | error
    steps: int = 0
    written: list[str] = field(default_factory=list)
    note: str = ""
    limit: str | None = None  # the ceiling that stopped it: steps | tokens | cost
    spend: Spend = field(default_factory=Spend)
    tool_calls: int = 0
    format_failures: int = 0  # tool calls that didn't fit the toolbox (#77)
    # Recipe refs the session wrote that resolve to nothing (#86); a group with
    # any is rolled back.
    unresolved_refs: list[str] = field(default_factory=list)
    # Item stats the session wrote that the source never states (#135); a group
    # with any is rolled back too.
    fabricated_stats: list[str] = field(default_factory=list)
    # Ids in a namespace neither vanilla nor the mod's (#147); rolled back too.
    unknown_namespaces: list[str] = field(default_factory=list)
    # Block states or values the Java blockstate doesn't have (#149); rolled back too.
    invented_states: list[str] = field(default_factory=list)
    # Trim recipes the session wrote whose template or addition is not vanilla
    # (#86); a group with any is rolled back too.
    unresolved_trims: list[str] = field(default_factory=list)
    # Items the session defined whose id the Java source never registers, e.g.
    # a per-variant item (#86); rolled back too.
    unknown_items: list[str] = field(default_factory=list)
    # Mentions of an item a mod config flag gates off here (#187); rolled back too.
    gated_items: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "group": self.key,
            "status": self.status,
            "stopped": self.stopped,
            "limit": self.limit,
            "steps": self.steps,
            "written": self.written,
            "spend": self.spend.to_dict(),
            "tool_calls": self.tool_calls,
            "format_failures": self.format_failures,
            "unresolved_refs": self.unresolved_refs,
            "fabricated_stats": self.fabricated_stats,
            "unknown_namespaces": self.unknown_namespaces,
            "invented_states": self.invented_states,
            "unresolved_trims": self.unresolved_trims,
            "unknown_items": self.unknown_items,
            "gated_items": self.gated_items,
            "note": self.note,
        }


@dataclass
class ResidueRun:
    outcomes: list[GroupOutcome]
    remaining: list[Unhandled]
    spend: Spend = field(default_factory=Spend)
    budget: Budget = field(default_factory=Budget)

    @property
    def limit(self) -> str | None:
        """The run ceiling that cut work short, if one did: tokens | cost.

        Read off the outcomes rather than the totals: a run whose last group
        finished exactly at the ceiling lost nothing, and should not say it did.
        """
        for outcome in self.outcomes:
            if outcome.limit in ("tokens", "cost"):
                return outcome.limit
        return None

    @property
    def resolved(self) -> list[GroupOutcome]:
        return [o for o in self.outcomes if o.status == "resolved"]

    @property
    def declined(self) -> list[GroupOutcome]:
        return [o for o in self.outcomes if o.status == "declined"]

    @property
    def tasks(self) -> list[GroupOutcome]:
        """Groups the agent could work on: everything but the SKIP_KINDS."""
        return [o for o in self.outcomes if not (o.status == "skipped" and o.stopped != "budget")]

    @property
    def status(self) -> str:
        """complete | partial | failed: how much of the agent's work landed.

        Not the same thing as the pack being valid. A run whose every group was
        rolled back leaves the tree exactly as valid as it found it (#86).
        """
        resolved = len(self.resolved)
        if resolved == len(self.tasks):
            return "complete"
        return "partial" if resolved else "failed"

    @property
    def files_written(self) -> int:
        """Files from resolved groups: the ones that count as converted."""
        return sum(len(o.written) for o in self.outcomes if o.status == "resolved")

    @property
    def partial_files(self) -> int:
        """Files kept from groups that did not resolve (out of budget, or a
        provider error after valid writes); their residue stands."""
        return sum(len(o.written) for o in self.outcomes if o.status != "resolved")

    def summary(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "groups": len(self.outcomes),
            "resolved": len(self.resolved),
            "declined": len(self.declined),
            "files_written": self.files_written,
            "partial_files": self.partial_files,
            "spend": self.spend.to_dict(),
            "budget": {
                "max_steps_per_group": self.budget.max_steps,
                "max_tokens": self.budget.max_tokens,
                "max_cost_usd": self.budget.max_cost,
            },
            "stopped_by": self.limit,
            "outcomes": [o.to_dict() for o in self.outcomes],
        }


def _final_text(messages) -> str:
    for message in reversed(messages):
        if message.role == "assistant" and message.content and not message.tool_calls:
            return message.content.strip()
    return ""


def _empty_reply_note(messages) -> str:
    """Say why a session ended on a reply with no text and no tool calls.

    Without this the group's note is just "", which reads like a silent
    refusal (#85). The finish reason tells a token cutoff ("length") from a
    content filter or an explicit refusal, and the output token count shows
    whether the model spent its budget thinking without answering.
    """
    last = next((m for m in reversed(messages) if m.role == "assistant"), None)
    if last is None:
        return ""
    if last.refusal:
        return f"model refused: {last.refusal.strip()}"
    details = [f"finish_reason={last.finish_reason or 'unknown'}"]
    if last.usage is not None:
        details.append(f"{last.usage.output_tokens} output tokens")
    return f"model ended with an empty reply ({', '.join(details)})"


class ResidueAgent:
    """Runs the residue through the loop, one session per group."""

    def __init__(
        self,
        client: LLMClient,
        max_steps: int = 12,
        system: str = SYSTEM_PROMPT,
        budget: Budget | None = None,
    ):
        self.client = client
        self.budget = budget or Budget(max_steps=max_steps)
        self.system = system

    def run(
        self,
        source_root: Path,
        out_tree: Path,
        unhandled: list[Unhandled],
        namespace: str,
        meta: ModMetadata | None = None,
        context: LoadContext | None = None,
    ) -> ResidueRun:
        """``context`` is the conversion's mod config (cited flag defaults plus
        ``--config``), the one the converters decided with; the guards hold the
        agent to it (#187). Without one, the defaults for ``meta``'s mods."""
        meta = meta or ModMetadata()
        if context is None:
            context = LoadContext(SourceMod.from_metadata(source_root, namespace, meta))
        scaffolded = _scaffold_manifests(out_tree, namespace, meta)
        outcomes: list[GroupOutcome] = []
        remaining: list[Unhandled] = []
        spent = Spend()
        try:
            for group in group_residue(unhandled):
                outcome = self._run_group(group, source_root, out_tree, namespace, spent, context)
                outcomes.append(outcome)
                if outcome.status != "resolved":
                    remaining.extend(group.items)
        finally:
            _remove_empty_scaffolds(out_tree, scaffolded)
        return ResidueRun(outcomes, remaining, spent, self.budget)

    def _run_group(
        self,
        group: ResidueGroup,
        source_root: Path,
        out_tree: Path,
        namespace: str,
        spent: Spend,
        context: LoadContext | None = None,
    ) -> GroupOutcome:
        outcome = GroupOutcome(group.key, group.kind, group.source, "skipped")
        model_text = ""
        if group.kind in SKIP_KINDS:
            outcome.note = SKIP_KINDS[group.kind]
            return outcome
        limit = self.budget.exhausted(spent)
        if limit:
            outcome.stopped, outcome.limit = "budget", limit
            outcome.note = f"the run's {limit} ceiling was reached before this group started"
            return outcome

        before = _error_set(out_tree)
        box = _TrackingToolBox(source_root, out_tree, namespace, context)
        session = AgentSession(
            self.client, box, self.system, budget=self.budget, run_spend=spent
        )
        task = build_task(group, source_root, out_tree, namespace)
        try:
            result = session.run(task)
            outcome.stopped, outcome.steps, outcome.limit = result.stopped, result.steps, result.limit
            outcome.tool_calls, outcome.format_failures = result.tool_calls, result.format_failures
            outcome.note = model_text = _final_text(result.messages)
            if result.stopped == "done" and not outcome.note:
                outcome.note = _empty_reply_note(result.messages)
            if result.stopped == "budget" and not outcome.note:
                outcome.note = f"stopped at the {result.limit} ceiling"
        except Exception as exc:  # a provider failure ends this group, not the run
            outcome.stopped = "error"
            outcome.steps = session.spend.steps
            outcome.tool_calls, outcome.format_failures = session.tool_calls, session.format_failures
            outcome.note = f"{type(exc).__name__}: {exc}"
        outcome.spend = session.spend

        outcome.written = sorted(box.originals)
        # A recipe naming an item or tag that exists nowhere is a fabrication,
        # even when the structural validator only warns about it (#86).
        unresolved = box.unresolved() if box.originals else []
        outcome.unresolved_refs = [ref.describe() for ref in unresolved]
        # So is a gameplay number the source never states (#135). Rolled back
        # rather than stripped, like a bad ref: the agent was told by validate
        # and chose to keep it, and editing its file behind its back would
        # leave an item nobody reviewed.
        fabricated = box.fabricated() if box.originals else []
        outcome.fabricated_stats = [stat.describe() for stat in fabricated]
        # And an id in a namespace the mod does not have, e.g. "sd:" for
        # storagedrawers (#147).
        foreign = box.unknown_namespaces(unresolved) if box.originals else []
        outcome.unknown_namespaces = [ref.describe() for ref in foreign]
        # And a block state or value the Java blockstate never has, such as an
        # integer code for facing=north (#149).
        states = box.invented() if box.originals else []
        outcome.invented_states = [bad.describe() for bad in states]
        # So is a trim recipe whose template or addition is not vanilla (#86):
        # a Bedrock add-on can't apply a mod trim pattern or material, so the
        # file would validate and the trim would do nothing in game.
        bad_trims = box.unresolved_trims() if box.originals else []
        outcome.unresolved_trims = [trim.describe() for trim in bad_trims]
        # And an item the Java source never registers, such as a per-variant
        # item for what Java keeps in block state or NBT (#86).
        bad_items = box.unknown_items() if box.originals else []
        outcome.unknown_items = [item.describe() for item in bad_items]
        # And any mention of an item a mod config flag gates off here (#187).
        gated = box.gated_refs(bad_items) if box.originals else []
        outcome.gated_items = [f"{ref.describe()} ({box.gated()[ref.ident].explain()})" for ref in gated]
        # Judged against the tree as the session found it: a group is rolled back
        # for errors it introduced, never for ones the deterministic path left.
        introduced = sorted(_error_set(out_tree) - before) if box.originals else []
        if box.originals and (
            unresolved or fabricated or foreign or states or bad_trims or bad_items
            or gated or introduced
        ):
            box.rollback()
            outcome.status = "rolled_back"
            outcome.written = []
            reasons = []
            if unresolved:
                reasons.append(f"unresolved reference(s): {'; '.join(outcome.unresolved_refs)}")
            if fabricated:
                reasons.append(
                    f"stat(s) the source does not state: {'; '.join(outcome.fabricated_stats)}"
                )
            if foreign:
                reasons.append(
                    f"unknown namespace(s): {'; '.join(outcome.unknown_namespaces)}"
                )
            if states:
                reasons.append(
                    f"block state(s) the Java blockstate does not have: {'; '.join(outcome.invented_states)}"
                )
            if bad_trims:
                reasons.append(
                    f"trim slot(s) with no working form: {'; '.join(outcome.unresolved_trims)}"
                )
            if bad_items:
                reasons.append(
                    f"item(s) the Java source does not register: {'; '.join(outcome.unknown_items)}"
                )
            if gated:
                reasons.append(
                    f"item(s) gated off by mod config: {'; '.join(outcome.gated_items)}"
                )
            if introduced:
                # Name what broke, so a stub that never validated reads as one (#141).
                shown = "; ".join(f"{path}: {rule}" for path, rule, _ in introduced[:3])
                more = f" (+{len(introduced) - 3} more)" if len(introduced) > 3 else ""
                reasons.append(f"validator error(s): {shown}{more}")
            if reasons:
                why = "rolled back: " + "; ".join(reasons)
                outcome.note = f"{why}. {outcome.note}" if outcome.note else why
        elif outcome.stopped == "done" and box.originals:
            outcome.status = "resolved"
        elif outcome.stopped == "budget" and box.originals:
            # Out of budget mid-task: what it wrote validates, so it stays on
            # disk for the next run or a human, but the residue is not cleared.
            outcome.status = "partial"
        elif outcome.stopped == "error":
            outcome.status = "error"
        elif outcome.stopped == "done" and model_text:
            # Wrote nothing and said why: the answer the task asks for when
            # there is no faithful Bedrock form. Still residue, never resolved.
            outcome.status = "declined"
        else:
            outcome.status = "unresolved"
        return outcome


def _error_set(out_tree: Path) -> set[tuple[str, str, str]]:
    return {(f.path, f.rule, f.message) for f in validate_tree(out_tree).errors}


def _scaffold_manifests(out_tree: Path, namespace: str, meta: ModMetadata) -> list[Path]:
    """Give the agent both packs to write into without letting it author manifests.

    Manifest UUIDs are derived deterministically from the mod; a model inventing
    one would break pack updates. A scaffold that ends up holding nothing but
    its manifest is removed again afterwards.
    """
    floor = ENGINE_FLOOR
    for pack in ("resource_pack", "behavior_pack"):
        existing = out_tree / pack / "manifest.json"
        if existing.is_file():
            try:
                version = json.loads(existing.read_text())["header"]["min_engine_version"]
                floor = max(floor, tuple(int(v) for v in version))
            except (KeyError, TypeError, ValueError):
                pass
    had_resource = (out_tree / "resource_pack" / "manifest.json").is_file()
    created: list[Path] = []
    for pack, kind in (("resource_pack", "resource"), ("behavior_pack", "behavior")):
        base = out_tree / pack
        if (base / "manifest.json").is_file():
            continue
        # Only depend on a resource pack that will still be there afterwards.
        depends = ("resource",) if kind == "behavior" and had_resource else ()
        base.mkdir(parents=True, exist_ok=True)
        (base / "manifest.json").write_text(
            json.dumps(manifest(namespace, kind, meta, depends, floor), indent=2) + "\n"
        )
        created.append(base)
    return created


def _remove_empty_scaffolds(out_tree: Path, scaffolded: list[Path]) -> None:
    for base in scaffolded:
        contents = [p for p in base.rglob("*") if p.is_file()]
        if all(p.name == "manifest.json" and p.parent == base for p in contents):
            shutil.rmtree(base)
