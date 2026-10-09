"""Top-level: source mod in, validated tree out, residue listed."""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .converters import convert_all
from .ingest import ingest
from .meta import ModMetadata, parse as parse_metadata
from .model import ConversionResult, SourceMod, Unhandled
from .pack import addon_name, write_mcaddon, write_tree
from .validate import ValidationReport, validate_tree

if TYPE_CHECKING:
    from .agent.residue import ResidueAgent, ResidueRun


# How deep a leftover path is grouped before reporting. assets/<ns>/models/block/x.json
# groups as assets/<ns>/models, which keeps a 300-model mod to one line.
_GROUP_DEPTH = 3


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
            **({"agent": self.agent.summary()} if self.agent else {}),
        }


def convert(
    source: Path,
    out_dir: Path,
    namespace: str | None = None,
    emit_addon: bool = True,
    agent: "ResidueAgent | None" = None,
) -> PipelineResult:
    """Convert a mod directory or .jar into a Bedrock pack tree under out_dir.

    Unless ``emit_addon`` is off, the packaged <mod>.mcaddon lands next to the
    tree, since that single file is the thing a player can actually install.

    With an ``agent``, the residue goes through it after the deterministic pass,
    while the staged source is still on disk. Validation and the addon both run
    on the tree as the agent left it; residue the agent resolved drops out of
    ``unhandled`` and its files count as converted.
    """
    out_dir = Path(out_dir)
    with tempfile.TemporaryDirectory(prefix="portkit-ingest-") as staging:
        staged = ingest(Path(source), Path(staging))
        # An explicit namespace narrows the run to that one; otherwise every
        # namespace the mod ships is converted into the same pack.
        selected = [namespace] if namespace else list(staged.namespaces)
        namespace = selected[0] if selected else staged.namespace
        meta = parse_metadata(staged.metadata, namespace)
        # Namespaces come off disk alphabetically, which would make a compat
        # namespace the pack's identity. The mod's own id decides instead.
        if meta.mod_id in selected and meta.mod_id != namespace:
            selected.remove(meta.mod_id)
            selected.insert(0, meta.mod_id)
            namespace = meta.mod_id

        per_namespace = {
            ns: convert_all(SourceMod(root=staged.root, namespace=ns)) for ns in selected
        }
        result = merge_namespaces(per_namespace)
        counts = {ns: len(r.files) for ns, r in per_namespace.items()}
        unhandled = (
            staged.residue()
            + result.unhandled
            + unowned(staged.root, result.consumed)
        )

        tree = write_tree(result, namespace, out_dir, meta)
        file_count = len(result.files)
        agent_run = None
        if agent is not None and unhandled:
            agent_run = agent.run(staged.root, tree, unhandled, namespace, meta)
            unhandled = agent_run.remaining
            file_count += agent_run.files_written
        report = validate_tree(tree)

        addon = None
        # A tree that fails the oracle is not something to hand a player as an
        # installable file, so the addon is only written for a valid one.
        if emit_addon and report.ok:
            addon = write_mcaddon(tree, out_dir / addon_name(namespace, meta))
        if unhandled:
            (out_dir / "unhandled.json").write_text(
                json.dumps([u.__dict__ for u in unhandled], indent=2) + "\n"
            )
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
        )
