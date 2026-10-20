"""Top-level: source mod in, validated tree out, residue listed."""
from __future__ import annotations

import re

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from . import advancements, biomecode, codeonly, datatags, ownership, worldgen
from .converters import features, lang, loot, recipes
from .conditions import (ConfigRequest, LoadContext, config_note, config_record, known_flags, known_values,
                         resolve_config)
from .converters import convert_all
from .converters.blocks import EXPERIMENTS
from .converters.recipes import (
    drop_unshipped_recipes,
    equip_smithing_bases,
    withdraw_unacceptable_trims,
    withdraw_unequipped_smithing,
)
from .data import worldgen as worldgen_ref
from .data.mappings import attach as attach_mappings
from .data.vanilla_blocks import attach as attach_vanilla_blocks
from .libraries import attach as attach_libraries
from .icon import resolve as resolve_icon
from .ingest import ingest
from .meta import ModMetadata, parse as parse_metadata
from .model import ConversionResult, SourceMod, Unhandled, _declared
from .pack import addon_name, write_mcaddon, write_tree
from .paths import shorten_paths
from .validate import ValidationReport, validate_tree

if TYPE_CHECKING:
    from .agent.residue import ResidueAgent, ResidueRun


# How deep a leftover path is grouped before reporting. assets/<ns>/models/block/x.json
# groups as assets/<ns>/models, which keeps a 300-model mod to one line.
_GROUP_DEPTH = 3

# The user's mod config settings, written next to the tree when there are any.
CONFIG_RECORD = "config-overrides.json"


def unowned(root: Path, consumed: set[str]) -> list[Unhandled]:
    """Every staged resource file no converter looked at, grouped by directory.

    A converter refusing a file it understood is honest work. A file nobody
    opened is the failure mode this project exists to avoid, so it is reported
    with the same weight as any other residue.
    """
    groups: dict[str, int] = {}
    for lane in ("assets", "data"):
        base = root / lane
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if str(rel) in consumed:
                continue
            parts = rel.parts[:_GROUP_DEPTH]
            groups["/".join(parts)] = groups.get("/".join(parts), 0) + 1

    return [
        Unhandled(
            source=f"{group}/",
            kind="unowned",
            reason=f"{count} file(s) no converter claims yet",
            count=count,
        )
        for group, count in sorted(groups.items())
    ]


# Output paths that are indexes rather than content: two namespaces both writing
# one is the normal case, and the right answer is the union, not the last writer.
_LINE_FILES = ("texts/",)
_INDEX_KEYS = {
    "textures/terrain_texture.json": "texture_data",
    "textures/item_texture.json": "texture_data",
}


def _combine(path: str, first, second) -> tuple[object, str | None]:
    """Fold a second namespace's output for the same path into the first.

    Returns the combined value and, when the two genuinely conflict, a reason.
    Namespaces share a pack, so their indexes and locale files have to add up
    rather than overwrite; anything else that lands twice is a collision worth
    saying out loud instead of quietly keeping whichever ran last.
    """
    if first == second:
        return first, None
    if path == "texts/languages.json":
        merged = sorted(set(first) | set(second))
        if "en_US" in merged:
            merged = ["en_US"] + [m for m in merged if m != "en_US"]
        return merged, None
    if path.startswith(_LINE_FILES) and path.endswith(".lang"):
        lines = sorted(set(first.splitlines()) | set(second.splitlines()))
        return "\n".join(lines) + "\n", None
    if path == "textures/flipbook_textures.json":
        combined = list(first) + [e for e in second if e not in first]
        return combined, None
    key = _INDEX_KEYS.get(path)
    if key and isinstance(first, dict) and isinstance(second, dict):
        merged = dict(first)
        data = dict(first.get(key) or {})
        data.update(second.get(key) or {})
        merged[key] = data
        return merged, None
    return first, f"two namespaces both produced {path}; kept the first"


def merge_namespaces(results: dict[str, "ConversionResult"]) -> "ConversionResult":
    """One pack out of per-namespace conversions, with collisions reported."""
    merged = ConversionResult()
    for namespace, result in results.items():
        merged.consumed |= result.consumed
        merged.unhandled.extend(result.unhandled)
        merged.notes.extend(result.notes)
        merged.stations.update(result.stations)
        for path, source in result.recipe_sources.items():
            merged.recipe_sources.setdefault(path, source)
        for source, names in result.unshipped_names.items():
            merged.unshipped_names.setdefault(source, names)
        for path, value in result.files.items():
            if path not in merged.files:
                merged.files[path] = value
                continue
            combined, conflict = _combine(path, merged.files[path], value)
            merged.files[path] = combined
            if conflict:
                merged.unhandled.append(
                    Unhandled(source=namespace, kind="namespace_collision", reason=conflict)
                )
    return merged


def _texture_keys(files: dict, index_path: str) -> dict[str, dict]:
    index = files.get(index_path)
    if not isinstance(index, dict):
        return {}
    return dict(index.get("texture_data") or {})


_VANILLA_KEY = re.compile(r"^[a-z0-9_]+:vanilla/(block|item)/(.+)$")
_VANILLA_FILE_DIR = {"block": "textures/blocks/", "item": "textures/items/"}


def vanilla_entries(result: ConversionResult, namespace: str) -> None:
    """Give each ``<ns>:vanilla/<lane>/<name>`` key the atlas entry it needs.

    models.vanilla_texture names a vanilla short name directly where one shows
    exactly the file; where none does it hands out such a key, which points
    at the vanilla file (``textures/blocks/<name>``) the vanilla pack below
    serves, so no art is copied. A mod's own keys flatten "/" (textures.shortname),
    so these never collide with them. Blocks' keys go in the terrain atlas,
    items' icons in the item atlas."""
    wanted: dict[str, dict[str, str]] = {}
    for path, body in result.files.items():
        if not isinstance(body, dict):
            continue
        keys: list[tuple[str, str]] = []
        if path.startswith("blocks/"):
            components = (body.get("minecraft:block") or {}).get("components") or {}
            for part in [components] + [p.get("components") or {} for p in
                                        (body.get("minecraft:block") or {}).get("permutations") or []
                                        if isinstance(p, dict)]:
                for inst in (part.get("minecraft:material_instances") or {}).values():
                    if isinstance(inst, dict) and isinstance(inst.get("texture"), str):
                        keys.append(("textures/terrain_texture.json", inst["texture"]))
        elif path.startswith("items/"):
            icon = ((body.get("minecraft:item") or {}).get("components") or {}).get("minecraft:icon")
            if isinstance(icon, dict):
                icon = icon.get("texture") or (icon.get("textures") or {}).get("default")
            if isinstance(icon, str):
                keys.append(("textures/item_texture.json", icon))
        for index_path, key in keys:
            match = _VANILLA_KEY.match(key)
            if match:
                wanted.setdefault(index_path, {})[key] = _VANILLA_FILE_DIR[match.group(1)] + match.group(2)
    for index_path, entries in sorted(wanted.items()):
        index = dict(result.files.get(index_path) or {
            "resource_pack_name": namespace,
            "texture_name": "atlas.terrain" if "terrain" in index_path else "atlas.items",
        })
        data = dict(index.get("texture_data") or {})
        for key, file in sorted(entries.items()):
            data.setdefault(key, {"textures": file})
        index["texture_data"] = data
        result.files[index_path] = index


def _vanilla_short_names(lane: str) -> frozenset[str]:
    from .data import vanilla_textures

    index = vanilla_textures.index()
    return index.short_names(lane) if index is not None else frozenset()


def drop_untextured(result: ConversionResult, namespace: str) -> None:
    """Withdraw blocks and items whose textures never made it into the pack.

    A texture can be refused on its own terms (an animation Bedrock can't
    express, two files that flatten to one key) while the block or item that
    uses it converts fine. Shipping that block is a wrong answer that only the
    validator would catch: it renders untextured. So it goes back to the residue
    with the texture named, the same as if the block converter had refused it.

    One case is fixable rather than refused: an item whose icon is a block
    texture. Bedrock's item_texture.json may point anywhere under textures/, so
    the icon gets an entry pointing at the block's file.
    """
    terrain = _texture_keys(result.files, "textures/terrain_texture.json")
    atlas = _texture_keys(result.files, "textures/item_texture.json")
    # Vanilla short names (models.vanilla_texture) are in vanilla's atlases,
    # which Bedrock merges with the pack's.
    vanilla_terrain = _vanilla_short_names("terrain")
    vanilla_items = _vanilla_short_names("item")
    borrowed: dict[str, dict] = {}

    for path in sorted(result.files):
        body = result.files[path]
        if not isinstance(body, dict):
            continue
        # Name the source in the namespace that declared it, not the pack's.
        root = body.get("minecraft:block") or body.get("minecraft:item") or {}
        ident = (root.get("description") or {}).get("identifier")
        ns = ident.split(":", 1)[0] if isinstance(ident, str) and ":" in ident else namespace
        if path.startswith("blocks/"):
            components = (body.get("minecraft:block") or {}).get("components") or {}
            instances = components.get("minecraft:material_instances") or {}
            missing = sorted({
                inst["texture"] for inst in instances.values()
                if isinstance(inst, dict) and isinstance(inst.get("texture"), str)
                and inst["texture"] not in terrain and inst["texture"] not in vanilla_terrain
            })
            kind, source = "block", f"assets/{ns}/blockstates/{Path(path).name}"
        elif path.startswith("items/"):
            icon = ((body.get("minecraft:item") or {}).get("components") or {}).get("minecraft:icon")
            if isinstance(icon, dict):
                icon = icon.get("texture")
            if not isinstance(icon, str) or icon in atlas or icon in vanilla_items:
                continue
            if icon in terrain:
                borrowed[icon] = terrain[icon]
                continue
            missing = [icon]
            kind, source = "item", f"assets/{ns}/models/item/{Path(path).name}"
        else:
            continue
        if not missing:
            continue
        del result.files[path]
        result.unhandled.append(
            Unhandled(
                source=source,
                kind=kind,
                reason=(
                    f"uses texture {', '.join(missing)}, which did not convert "
                    "(see that texture's own residue entry)"
                ),
            )
        )

    # An item form written for a block (recipes._block_item) goes with it.
    blocks = {
        ((body.get("minecraft:block") or {}).get("description") or {}).get("identifier")
        for path, body in result.files.items()
        if path.startswith("blocks/") and isinstance(body, dict)
    }
    for path in sorted(result.files):
        body = result.files[path]
        if not path.startswith("items/") or not isinstance(body, dict):
            continue
        placer = ((body.get("minecraft:item") or {}).get("components") or {}).get("minecraft:block_placer")
        if not isinstance(placer, dict):
            continue
        block = placer.get("block")
        if (placer.get("replace_block_item") is True and isinstance(block, str)
                and not block.startswith("minecraft:") and block not in blocks):
            # The block's own residue entry already covers it.
            del result.files[path]
            result.notes.append(
                f"{path}: dropped with its block {block}, which did not convert"
            )

    # A held model's attachable (items._attachable) goes with its item, and
    # with its texture: an attachable naming a missing file renders untextured.
    items = {
        ((body.get("minecraft:item") or {}).get("description") or {}).get("identifier")
        for path, body in result.files.items()
        if path.startswith("items/") and isinstance(body, dict)
    }
    for path in sorted(p for p in result.files if p.startswith("attachables/")):
        body = result.files[path]
        if not isinstance(body, dict):
            continue
        description = (body.get("minecraft:attachable") or {}).get("description") or {}
        texture = (description.get("textures") or {}).get("default")
        geometry = (description.get("geometry") or {}).get("default")
        if description.get("identifier") not in items:
            why = f"dropped with its item {description.get('identifier')}, which did not convert"
        elif isinstance(texture, str) and f"{texture}.png" not in result.files:
            why = f"dropped: its texture {texture} did not convert (see that texture's own residue entry)"
        else:
            continue
        del result.files[path]
        if isinstance(geometry, str) and geometry.startswith("geometry.humanoid.armor."):
            # A worn armor look (armor.attachable): its layer texture goes too
            # once no other attachable wears it.
            worn = {((((b.get("minecraft:attachable") or {}).get("description") or {}).get("textures") or {})
                     .get("default")) for p, b in result.files.items()
                    if p.startswith("attachables/") and isinstance(b, dict)}
            if isinstance(texture, str) and texture not in worn and f"{texture}.png" in result.files:
                del result.files[f"{texture}.png"]
            result.notes.append(f"{path}: worn armor look {why}")
            continue
        geo = f"models/entity/{Path(path).stem}.held.geo.json"
        if isinstance(geometry, str) and geo in result.files:
            del result.files[geo]
        result.notes.append(f"{path}: held model {why}")

    if borrowed:
        index = dict(result.files.get("textures/item_texture.json") or {
            "resource_pack_name": namespace,
            "texture_name": "atlas.items",
        })
        index["texture_data"] = {**atlas, **borrowed}
        result.files["textures/item_texture.json"] = index


@dataclass
class PipelineResult:
    tree: Path
    namespace: str
    report: ValidationReport
    unhandled: list[Unhandled]
    file_count: int
    meta: ModMetadata = field(default_factory=ModMetadata)
    addon: Path | None = None
    # Every namespace converted, primary first, with how many files each produced.
    namespaces: dict[str, int] = field(default_factory=dict)

    # Reductions recorded by converters: something shipped, with a detail
    # Bedrock cannot carry.
    reductions: list[str] = field(default_factory=list)

    # What the residue agent did, when one ran (``convert(..., agent=...)``).
    agent: "ResidueRun | None" = None

    # The user's mod config settings (``convert(..., config=...)``), one record
    # per flag set; empty for a run at the cited defaults.
    config: list[dict] = field(default_factory=list)

    # Station runtimes (#177): recipe type -> recipes in its data table and
    # recipes left as station_recipe residue, with the table's path.
    stations: dict[str, dict] = field(default_factory=dict)

    # "explained-empty" when nothing converts and the jar's facts say why
    # (#279); the reason classes are portkit.codeonly.reason_classes output.
    outcome: str | None = None
    reason_classes: list[dict] = field(default_factory=list)

    @property
    def notes(self) -> list[str]:
        """Things worth saying about the mod itself, not about its files.

        Kept out of the residue list on purpose: residue is source files an
        agent can work on, and coverage arithmetic counts files. A guessed
        version is neither, and neither is a block that shipped without its
        random variety, but neither can go unsaid.
        """
        return [*self.meta.notes, *self.reductions]

    @property
    def residue_count(self) -> int:
        """Source files the residue stands for, not the number of entries."""
        return sum(u.count for u in self.unhandled)

    @property
    def coverage(self) -> float:
        total = self.file_count + self.residue_count
        return (self.file_count / total * 100) if total else 100.0

    def summary(self) -> dict:
        return {
            "namespace": self.namespace,
            "namespaces": self.namespaces or {self.namespace: self.file_count},
            "files": self.file_count,
            "valid": self.report.ok,
            "errors": len(self.report.errors),
            "unhandled": len(self.unhandled),
            "unhandled_files": self.residue_count,
            "coverage": round(self.coverage, 1),
            "mod": {
                "name": self.meta.name,
                "id": self.meta.mod_id,
                "version": ".".join(str(n) for n in self.meta.version),
                "loader": self.meta.loader,
            },
            "notes": self.notes,
            "mcaddon": self.addon.name if self.addon else None,
            **({"config": config_record(self.config)} if self.config else {}),
            **({"stations": self.stations} if self.stations else {}),
            **({"outcome": self.outcome, "reason_classes": [r["class"] for r in self.reason_classes]}
               if self.outcome else {}),
            **({"agent": self.agent.summary()} if self.agent else {}),
        }


def convert(
    source: Path,
    out_dir: Path,
    namespace: str | None = None,
    emit_addon: bool = True,
    agent: "ResidueAgent | None" = None,
    config: "list[ConfigRequest] | None" = None,
    experiments: "list[str] | None" = None,
    libraries: "list[Path] | None" = None,
) -> PipelineResult:
    """Convert a mod directory or .jar into a Bedrock pack tree under out_dir.

    Unless ``emit_addon`` is off, the packaged <mod>.mcaddon lands next to the
    tree, since that single file is the thing a player can actually install.

    With an ``agent``, the residue goes through it after the deterministic pass,
    while the staged source is still on disk. Validation and the addon both run
    on the tree as the agent left it; residue the agent resolved drops out of
    ``unhandled`` and its files count as converted.

    ``config`` holds the user's mod config settings (``--config``), the
    conversion-time stand-in for editing the mod's config file in Java: each is
    resolved against the flags this jar knows (an unknown one raises
    :class:`portkit.conditions.ConfigError` before anything is written), and
    replaces that flag's cited default. The settings are recorded in the notes
    and in ``config-overrides.json`` next to the tree, which ``--config-file``
    reads back to reproduce the run. Without settings the output is the
    default-config conversion.

    ``experiments`` (``--experiment``) are Bedrock experiments the user's
    world runs; content that needs one ships only when it is named (see
    ``portkit.converters.blocks.EXPERIMENTS``). An unknown name raises
    ValueError before anything is written. Each is recorded in the notes.

    ``libraries`` (``--library``) are dependency jars read for their classes
    only (#280, :mod:`portkit.libraries`): a block subclassing a library's
    base class or registered by a library's constructor is read as far as
    vanilla; nothing of a library is converted or shipped. Each is noted.
    """
    out_dir = Path(out_dir)
    chosen = frozenset(experiments or ())
    unknown = sorted(chosen - set(EXPERIMENTS))
    if unknown:
        raise ValueError(f"unknown Bedrock experiment(s) {', '.join(unknown)}; known: {', '.join(EXPERIMENTS)}")
    # A run narrowed to one namespace (--namespace) speaks for that namespace
    # only, so it never decides the whole mod is explained-empty (#279).
    narrowed = namespace is not None
    with tempfile.TemporaryDirectory(prefix="portkit-ingest-") as staging:
        staged = ingest(Path(source), Path(staging))
        # An explicit namespace narrows the run to that one; otherwise every
        # namespace the mod ships is converted into the same pack.
        selected = [namespace] if namespace else list(staged.namespaces)
        namespace = selected[0] if selected else _code_only_namespace(staged, Path(source))
        meta = parse_metadata(staged.metadata, namespace)
        # Namespaces come off disk alphabetically, which would make a compat
        # namespace the pack's identity. The mod's own id decides instead.
        if meta.mod_id in selected and meta.mod_id != namespace:
            selected.remove(meta.mod_id)
            selected.insert(0, meta.mod_id)
            namespace = meta.mod_id

        # Forge SRG / Fabric intermediary jars: read their code in Mojang's
        # names (#235), or say why the readers can't.
        mapping_note = attach_mappings(staged.classes, meta.loader, meta.minecraft)
        if mapping_note:
            meta.notes.append(mapping_note)
        # Vanilla Blocks field -> id for the declared game version (#280).
        attach_vanilla_blocks(staged.classes, meta.minecraft or meta.loader_minecraft)
        if libraries:
            meta.notes.extend(attach_libraries(staged.classes, libraries))

        overrides, records = {}, []
        if config:
            known = known_flags(staged.root, meta.mods, selected)
            overrides, records = resolve_config(list(config), known, known_values(meta.mods, selected))
            meta.notes.append(config_note(records))
        if chosen:
            meta.notes.append("Converted for a world running the Bedrock experiment(s) "
                              + ", ".join(sorted(chosen)) + " (--experiment): the pack needs them on.")
        per_namespace = {
            ns: convert_all(SourceMod.from_metadata(staged.root, ns, meta, classes=staged.classes),
                            overrides=overrides or None, experiments=chosen)
            for ns in selected
        }
        result = merge_namespaces(per_namespace)
        vanilla_entries(result, namespace)
        drop_untextured(result, namespace)
        # Last, once every namespace's blocks and items are final: a recipe
        # naming one the pack doesn't ship would be refused by Bedrock (#261).
        drop_unshipped_recipes(result)
        # Then the smithing recipes left: each namespace's bases get the
        # durability its mod's code gives them, and a recipe whose base Bedrock
        # still won't take as armor or a tool (none could be read, or a block)
        # goes back to the residue (#268).
        for ns in selected:
            equipped = equip_smithing_bases(
                SourceMod.from_metadata(staged.root, ns, meta, classes=staged.classes), result.files)
            result.files.update(equipped.files)
            result.notes.extend(equipped.notes)
        withdraw_unequipped_smithing(result)
        # And a trim recipe whose base is the pack's own item that isn't armor
        # carrying minecraft:trimmable_armors (#272).
        withdraw_unacceptable_trims(result)
        # The pack's blocks are final: the ores the jar's Forge/NeoForge biome
        # modifiers add become Bedrock ore features and feature rules (#281).
        # And the ores its Fabric code adds to biomes (BiomeModifications),
        # read from the bytecode (#281 pick 5a).
        code_ores = []
        if staged.classes is not None and len(staged.classes):
            reading = biomecode.read(staged.classes, staged.metadata)
            result.notes.extend(reading.notes)
            if reading.attachments:
                gates = LoadContext(SourceMod.from_metadata(staged.root, namespace, meta),
                                    overrides=overrides or None)
                code_ores = biomecode.decide(reading, staged.root, set(selected), gates,
                                             worldgen_ref.convention_biome_tags(meta.loader, meta.minecraft),
                                             {k for k in worldgen_ref.BIOME_TAGS})
                if gates.note():
                    result.notes.append(gates.note())
        ores = features.convert(staged.root, result.files, set(selected), code=code_ores)
        result.files.update(ores.files)
        result.consumed |= ores.consumed
        result.unhandled.extend(ores.unhandled)
        result.notes.extend(ores.notes)
        # The pack's blocks are final: Java's tool and tier block tags become
        # Bedrock's vanilla block tags on them (#293).
        claimed, tag_notes = datatags.tool_tags(staged.root, result.files, getattr(meta, "loader", None))
        result.consumed |= claimed
        result.notes.extend(tag_notes)
        # Now that the pack's blocks, items and entities are final, its .lang
        # keeps only the lines naming one of them (#277 lang).
        lang.settle(result, selected)
        renames = shorten_paths(result)
        counts = {ns: len(r.files) for ns, r in per_namespace.items()}
        icon, icon_source, icon_note = resolve_icon(staged.icons, namespace)
        if icon_note:
            meta.notes.append(icon_note)
        if icon_source and icon_source.startswith(("assets/", "data/")):
            # A logo kept under assets/ (Fabric's usual place) is a staged file
            # like any other; it shipped, so it is no longer unowned residue.
            result.consumed.add(icon_source)
        unhandled = (
            staged.residue()
            + result.unhandled
            + unowned(staged.root, result.consumed)
        )
        # Nothing shipped: decide from the jar's facts whether that is the
        # whole story (#279). An explained-empty mod gets no pack, its reason
        # classes in explained-empty.json, and its lang/asset leftovers filed
        # as code_only residue.
        outcome, reasons = None, []
        if not result.files and not narrowed:
            facts = codeonly.facts(Path(source), classes=staged.classes)
            explained, _ = codeonly.decide(result.files, unhandled, facts, staged.root, staged.namespaces)
            if explained:
                reasons = codeonly.reason_classes(facts)
                unhandled = codeonly.explain_leftovers(unhandled, reasons, staged.root, staged.namespaces)
                outcome = codeonly.OUTCOME
                codeonly.write_report(out_dir, codeonly.report(meta, reasons, unhandled, facts))
        if outcome is None:
            # A shipping mod's leftover models and textures: the jar's own
            # references say whether residue owns them or only Java code
            # draws them (#277 unowned).
            shipped = {i for i in (_declared(b) for b in result.files.values()) if i}
            unhandled = ownership.refine(unhandled, staged.root, result.consumed, shipped)
            # A refused block loot table whose block is residue goes with the
            # block (#299).
            blocks_shipped = {_declared(b) for b in result.files.values()
                              if isinstance(b, dict) and "minecraft:block" in b} - {None}
            unhandled = loot.refine_owned(unhandled, blocks_shipped)
            # And a recipe withdrawn for naming items that are residue of
            # their own goes with them (#302).
            unhandled = recipes.refine_owned(unhandled, result.unshipped_names)
            # And its leftover data tags: what reads them, and whether their
            # members shipped (#293).
            unhandled = datatags.refine(unhandled, staged.root, result.consumed, shipped,
                                        datatags.jar_namespaces(staged.root), getattr(meta, "loader", None),
                                        set(result.files))
            # And its leftover worldgen, structure templates and other mods'
            # data the jar explains (#277; PR #316 picks 1a 2a 3a).
            unhandled = worldgen.refine(unhandled, staged.root, result.consumed,
                                        datatags.jar_namespaces(staged.root), staged.classes)
            # And its leftover advancements: recipe advancements go with their
            # residue recipes, the rest Bedrock has no place for (#340).
            unhandled = advancements.refine(
                unhandled, staged.root, result.consumed,
                advancements.recipe_bodies(result.files, result.recipe_sources, renames))
        if outcome is None and (out_dir / codeonly.REPORT_NAME).is_file():
            # An earlier run's report would make this tree read as explained-empty.
            (out_dir / codeonly.REPORT_NAME).unlink()

        tree = write_tree(result, namespace, out_dir, meta, icon=icon)
        file_count = len(result.files)
        agent_run = None
        if agent is not None and unhandled:
            # The agent's guards decide config-gated items with the same
            # settings the converters used (cited defaults + --config), so it
            # can't write back an item the converters left out (#187).
            context = LoadContext(SourceMod.from_metadata(staged.root, namespace, meta),
                                  overrides=overrides or None)
            agent_run = agent.run(staged.root, tree, unhandled, namespace, meta, context=context)
            unhandled = agent_run.remaining
            file_count += agent_run.files_written
        report = validate_tree(tree)

        addon = None
        # A tree that fails the oracle is not something to hand a player as an
        # installable file, so the addon is only written for a valid one.
        if emit_addon and report.ok and outcome is None:
            addon = write_mcaddon(tree, out_dir / addon_name(namespace, meta))
        if unhandled:
            (out_dir / "unhandled.json").write_text(
                json.dumps([u.__dict__ for u in unhandled], indent=2) + "\n"
            )
        if records:
            # Next to unhandled.json, outside the packs: a --config-file that
            # reproduces this run, plus what each setting replaced.
            (out_dir / CONFIG_RECORD).write_text(json.dumps(
                {**config_record(records), "_settings": records}, indent=2) + "\n")
        elif (out_dir / CONFIG_RECORD).is_file():
            # A record left by an earlier run into the same folder would make
            # this default-config tree read as overridden.
            (out_dir / CONFIG_RECORD).unlink()
        return PipelineResult(
            tree,
            namespace,
            report,
            unhandled,
            file_count,
            meta,
            addon,
            counts,
            reductions=result.notes,
            agent=agent_run,
            config=records,
            stations=result.stations,
            outcome=outcome,
            reason_classes=reasons,
        )


def _code_only_namespace(staged, source: Path) -> str:
    """The pack identity of a mod with no resource namespace (#279): its
    declared mod id, else the jar's file name, as a namespace."""
    declared = parse_metadata(staged.metadata, "").mod_id or ""
    raw = declared or source.stem
    return re.sub(r"[^a-z0-9_]+", "_", raw.lower()).strip("_") or "mod"
