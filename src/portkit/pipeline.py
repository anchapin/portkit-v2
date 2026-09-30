"""Top-level: source mod in, validated tree out, residue listed."""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .converters import convert_all
from .ingest import ingest
from .model import SourceMod, Unhandled
from .pack import write_tree
from .validate import ValidationReport, validate_tree


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


@dataclass
class PipelineResult:
    tree: Path
    namespace: str
    report: ValidationReport
    unhandled: list[Unhandled]
    file_count: int

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
            "files": self.file_count,
            "valid": self.report.ok,
            "errors": len(self.report.errors),
            "unhandled": len(self.unhandled),
            "unhandled_files": self.residue_count,
            "coverage": round(self.coverage, 1),
        }


def convert(source: Path, out_dir: Path, namespace: str | None = None) -> PipelineResult:
    """Convert a mod directory or .jar into a Bedrock pack tree under out_dir."""
    out_dir = Path(out_dir)
    with tempfile.TemporaryDirectory(prefix="portkit-ingest-") as staging:
        staged = ingest(Path(source), Path(staging))
        namespace = namespace or staged.namespace
        mod = SourceMod(root=staged.root, namespace=namespace)
        result = convert_all(mod)
        unhandled = (
            staged.residue()
            + result.unhandled
            + unowned(staged.root, result.consumed)
        )

        tree = write_tree(result, namespace, out_dir)
        report = validate_tree(tree)
        if unhandled:
            (out_dir / "unhandled.json").write_text(
                json.dumps([u.__dict__ for u in unhandled], indent=2) + "\n"
            )
        return PipelineResult(tree, namespace, report, unhandled, len(result.files))
