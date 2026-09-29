"""Top-level: source mod in, validated tree out, residue listed."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .converters import convert_all
from .model import SourceMod, Unhandled
from .pack import write_tree
from .validate import ValidationReport, validate_tree


def detect_namespace(root: Path) -> str:
    for lane in ("assets", "data"):
        base = root / lane
        if base.is_dir():
            for child in sorted(base.iterdir()):
                if child.is_dir() and child.name != "minecraft":
                    return child.name
    raise ValueError(f"cannot detect mod namespace under {root}")


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
    namespace = namespace or detect_namespace(source)
    mod = SourceMod(root=source, namespace=namespace)
    result = convert_all(mod)
    tree = write_tree(result, namespace, out_dir)
    report = validate_tree(tree)
    if result.unhandled:
        (out_dir / "unhandled.json").write_text(
            json.dumps([u.__dict__ for u in result.unhandled], indent=2) + "\n"
        )
    return PipelineResult(tree, namespace, report, result.unhandled, len(result.files))
