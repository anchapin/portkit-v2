"""Assemble converted files into a Bedrock pack tree (and an .mcaddon)."""
from __future__ import annotations

import json
import uuid
import zipfile
from pathlib import Path

from .model import ConversionResult

# Deterministic UUIDs: same mod in, same manifest out, so fixture diffs are clean.
_NS = uuid.UUID("6f0a7f1e-0a4a-4f2e-9a1b-6a5f0d1c2b3e")

_BEHAVIOR_DIRS = ("recipes/", "entities/", "functions/", "loot_tables/")


def _uuid(*parts: str) -> str:
    return str(uuid.uuid5(_NS, "/".join(parts)))


def manifest(namespace: str, kind: str, version=(0, 1, 0)) -> dict:
    module_type = "data" if kind == "behavior" else "resources"
    return {
        "format_version": 2,
        "header": {
            "name": f"{namespace} ({kind})",
            "description": f"Converted from Java by portkit",
            "uuid": _uuid(namespace, kind, "header"),
            "version": list(version),
            "min_engine_version": [1, 20, 10],
        },
        "modules": [
            {
                "type": module_type,
                "uuid": _uuid(namespace, kind, "module"),
                "version": list(version),
            }
        ],
    }


def _is_behavior(relpath: str) -> bool:
    return relpath.startswith(_BEHAVIOR_DIRS)


def write_tree(result: ConversionResult, namespace: str, out_dir: Path) -> Path:
    """Write behavior_pack/ and resource_pack/ under out_dir. Returns out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    buckets = {"behavior": {}, "resource": {}}
    for relpath, content in result.files.items():
        buckets["behavior" if _is_behavior(relpath) else "resource"][relpath] = content

    for kind, files in buckets.items():
        if not files:
            continue
        base = out_dir / f"{kind}_pack"
        base.mkdir(parents=True, exist_ok=True)
        (base / "manifest.json").write_text(
            json.dumps(manifest(namespace, kind), indent=2) + "\n"
        )
        for relpath, content in files.items():
            target = base / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                target.write_bytes(content)
            else:
                target.write_text(json.dumps(content, indent=2) + "\n")
    return out_dir


def write_mcaddon(tree: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(tree.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(tree))
    return destination
