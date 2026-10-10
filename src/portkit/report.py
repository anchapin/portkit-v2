"""The conversion report: what converted, what did not, and specifically why.

`convert` prints a summary dict, which is fine for a pipeline and useless to a
modder looking at a pack with a missing block. This produces Markdown they can
read top to bottom, or paste into an issue, and know every gap without opening
the source.

It reads what the conversion already left on disk: the two pack trees, the
manifests, and unhandled.json. Nothing is recomputed from the jar, so a report
always describes the tree in front of you rather than a fresh guess at it.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from .validate import validate_tree
from .validate.report import Finding

# What each directory in a pack actually holds, in the words a modder uses.
_CONTENT_TYPES = {
    "blocks": "blocks",
    "items": "items",
    "recipes": "recipes",
    "loot_tables": "loot tables",
    "entities": "entities",
    "functions": "functions",
    "models": "models",
    "textures": "textures",
    "texts": "translations",
    "sounds": "sounds",
}
_SEVERITY_ORDER = {"error": 0, "warning": 1}


@dataclass
class Residue:
    kind: str
    source: str
    reason: str
    count: int = 1

    @classmethod
    def load(cls, tree: Path) -> list["Residue"]:
        """Read the residue the conversion recorded next to the tree."""
        path = tree / "unhandled.json"
        if not path.is_file():
            return []
        try:
            entries = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return []
        out = []
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, dict):
                out.append(
                    cls(
                        kind=str(entry.get("kind", "unknown")),
                        source=str(entry.get("source", "?")),
                        reason=str(entry.get("reason", "no reason recorded")),
                        count=int(entry.get("count", 1) or 1),
                    )
                )
        return out


def _content_type(relpath: str) -> str:
    head = relpath.split("/", 1)[0]
    return _CONTENT_TYPES.get(head, head)


def _converted(tree: Path) -> Counter:
    """Files that made it, counted by content type."""
    counts: Counter = Counter()
    for pack in ("behavior_pack", "resource_pack"):
        root = tree / pack
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.name in ("manifest.json", "pack_icon.png"):
                continue
            counts[_content_type(path.relative_to(root).as_posix())] += 1
    return counts


def _mod_name(tree: Path) -> str:
    for pack in ("behavior_pack", "resource_pack"):
        manifest = tree / pack / "manifest.json"
        if manifest.is_file():
            try:
                header = json.loads(manifest.read_text()).get("header") or {}
            except (OSError, json.JSONDecodeError):
                continue
            name = header.get("name")
            if isinstance(name, str) and name:
                return name.removesuffix(" (behavior)").removesuffix(" (resources)")
    return tree.name


def _table(rows: list[tuple[str, ...]], headers: tuple[str, ...]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(" --- " for _ in headers) + "|")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return lines


def _findings_section(findings: list[Finding]) -> list[str]:
    if not findings:
        return ["The validator found nothing to report.", ""]
    lines = []
    grouped: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        grouped[finding.severity].append(finding)
    for severity in sorted(grouped, key=lambda s: _SEVERITY_ORDER.get(s, 9)):
        items = grouped[severity]
        label = "Errors" if severity == "error" else "Warnings"
        lines.append(f"### {label} ({len(items)})")
        lines.append("")
        for finding in items:
            lines.append(f"- `{finding.path}` **{finding.rule}**: {finding.message}")
        lines.append("")
    return lines


def render(tree: Path) -> str:
    """Markdown for one converted tree."""
    converted = _converted(tree)
    residue = Residue.load(tree)
    report = validate_tree(tree)

    converted_total = sum(converted.values())
    residue_total = sum(r.count for r in residue)
    denominator = converted_total + residue_total
    coverage = (converted_total / denominator * 100) if denominator else 100.0

    lines = [
        f"# Conversion report: {_mod_name(tree)}",
        "",
        f"- **Coverage:** {coverage:.1f}% ({converted_total} of {denominator} files)",
        f"- **Left unconverted:** {residue_total} file(s) in {len(residue)} item(s)",
        f"- **Validator:** {'passed' if report.ok else 'failed'}, "
        f"{len(report.errors)} error(s), "
        f"{len(report.findings) - len(report.errors)} warning(s)",
        "",
        "## What converted",
        "",
    ]
    if converted:
        lines += _table(
            [(name, str(count)) for name, count in sorted(converted.items())],
            ("Content", "Files"),
        )
    else:
        lines.append("Nothing. The tree holds no pack files.")
    lines.append("")

    lines += ["## What did not, and why", ""]
    if not residue:
        lines += ["Everything in the source was converted.", ""]
    else:
        by_kind: dict[str, list[Residue]] = defaultdict(list)
        for item in residue:
            by_kind[item.kind].append(item)
        for kind in sorted(by_kind):
            items = by_kind[kind]
            files = sum(i.count for i in items)
            lines.append(f"### {kind} ({files} file(s))")
            lines.append("")
            for item in sorted(items, key=lambda i: i.source):
                suffix = f" ({item.count} files)" if item.count > 1 else ""
                lines.append(f"- `{item.source}`{suffix}: {item.reason}")
            lines.append("")

    lines += ["## Validator findings", ""]
    lines += _findings_section(report.findings)

    lines += [
        "## What to do with this",
        "",
        "Every line above names a source file and a reason. A reason that reads "
        "like a refusal is deliberate: the converter would rather leave a file "
        "out than emit something that loads and behaves wrongly. Paste this "
        "report into an issue and the gap is reproducible without the jar.",
        "",
    ]
    return "\n".join(lines)
