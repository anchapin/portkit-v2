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


@dataclass
class PipelineResult:
    tree: Path
    namespace: str
    report: ValidationReport
    unhandled: list[Unhandled]
    file_count: int

    def summary(self) -> dict:
        return {
            "namespace": self.namespace,
            "files": self.file_count,
            "valid": self.report.ok,
            "errors": len(self.report.errors),
            "unhandled": len(self.unhandled),
        }


def convert(source: Path, out_dir: Path, namespace: str | None = None) -> PipelineResult:
    """Convert a mod directory or .jar into a Bedrock pack tree under out_dir."""
    out_dir = Path(out_dir)
    with tempfile.TemporaryDirectory(prefix="portkit-ingest-") as staging:
        staged = ingest(Path(source), Path(staging))
        namespace = namespace or staged.namespace
        mod = SourceMod(root=staged.root, namespace=namespace)
        result = convert_all(mod)
        unhandled = staged.residue() + result.unhandled

        tree = write_tree(result, namespace, out_dir)
        report = validate_tree(tree)
        if unhandled:
            (out_dir / "unhandled.json").write_text(
                json.dumps([u.__dict__ for u in unhandled], indent=2) + "\n"
            )
        return PipelineResult(tree, namespace, report, unhandled, len(result.files))
