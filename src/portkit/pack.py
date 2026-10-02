"""Assemble converted files into a Bedrock pack tree (and an .mcaddon)."""
from __future__ import annotations

import json
import uuid
import zipfile
from pathlib import Path

from .meta import ModMetadata
from .model import ConversionResult

# Deterministic UUIDs: same mod in, same manifest out, so fixture diffs are
# clean. The seed includes the pack's header name, not just the namespace,
# because Bedrock keys an installed pack by UUID alone: two packs sharing a
# namespace (the axis probe and the rotation probe both used "probe") hashed to
# the same UUID pair, so importing the second collided with the first instead
# of installing beside it.
_NS = uuid.UUID("6f0a7f1e-0a4a-4f2e-9a1b-6a5f0d1c2b3e")

_BEHAVIOR_DIRS = ("recipes/", "entities/", "functions/", "loot_tables/", "blocks/", "items/")


def _uuid(*parts: str) -> str:
    return str(uuid.uuid5(_NS, "/".join(parts)))


def manifest(
    namespace: str,
    kind: str,
    meta: ModMetadata | None = None,
    depends_on: tuple[str, ...] = (),
    min_engine: tuple[int, int, int] = (1, 20, 20),
) -> dict:
    """One Bedrock pack manifest.

    ``depends_on`` names the other pack kinds this one requires. Bedrock treats
    a behavior pack and a resource pack as separate installs unless the
    behavior pack names the resource pack by UUID, so a two-pack addon without
    this block imports as two halves the player has to enable by hand.
    """
    meta = meta or ModMetadata()
    version = meta.version
    module_type = "data" if kind == "behavior" else "resources"
    data = {
        "format_version": 2,
        "header": {
            "name": meta.header_name(namespace, kind),
            "description": meta.header_description(),
            "uuid": _uuid(namespace, meta.header_name(namespace, kind), kind, "header"),
            "version": list(version),
            # 1.20.20 is the first engine with custom block states and the placement
            # traits that set them, which the axis pillars rely on. A pack that
            # uses something newer (palisades need 1.26.0) rises to match.
            "min_engine_version": list(min_engine),
        },
        "modules": [
            {
                "type": module_type,
                "uuid": _uuid(namespace, meta.header_name(namespace, kind), kind, "module"),
                "version": list(version),
            }
        ],
    }
    if depends_on:
        data["dependencies"] = [
            {
                "uuid": _uuid(
                    namespace, meta.header_name(namespace, other), other, "header"
                ),
                "version": list(version),
            }
            for other in depends_on
        ]
    return data


ENGINE_FLOOR = (1, 20, 20)


def engine_floor(files: dict) -> tuple[int, int, int]:
    """The oldest engine that loads every block in this pack.

    The floor stays at ENGINE_FLOOR unless a block or a block geometry was
    written at a newer format because it needs a newer feature, so a mod with only simple blocks
    still loads on older versions.
    """
    floor = ENGINE_FLOOR
    for relpath, content in files.items():
        is_block = relpath.startswith("blocks/")
        is_geometry = relpath.startswith("models/blocks/") and relpath.endswith(".geo.json")
        if not ((is_block or is_geometry) and isinstance(content, dict)):
            continue
        version = str(content.get("format_version", ""))
        try:
            parts = tuple(int(v) for v in version.split("."))
        except ValueError:
            continue
        parts = (parts + (0, 0, 0))[:3]
        floor = max(floor, parts)
    return floor


def _is_behavior(relpath: str) -> bool:
    return relpath.startswith(_BEHAVIOR_DIRS)


def write_tree(
    result: ConversionResult,
    namespace: str,
    out_dir: Path,
    meta: ModMetadata | None = None,
) -> Path:
    """Write behavior_pack/ and resource_pack/ under out_dir. Returns out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    buckets = {"behavior": {}, "resource": {}}
    for relpath, content in result.files.items():
        buckets["behavior" if _is_behavior(relpath) else "resource"][relpath] = content

    # The behavior pack points at the resource pack, never the other way round:
    # Bedrock rejects a circular dependency, and the behavior pack is the half
    # that carries the mod's actual content.
    has_resource = bool(buckets["resource"])
    floor = engine_floor(result.files)
    for kind, files in buckets.items():
        if not files:
            continue
        base = out_dir / f"{kind}_pack"
        base.mkdir(parents=True, exist_ok=True)
        depends_on = ("resource",) if kind == "behavior" and has_resource else ()
        (base / "manifest.json").write_text(
            json.dumps(manifest(namespace, kind, meta, depends_on, floor), indent=2) + "\n"
        )
        for relpath, content in files.items():
            target = base / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                target.write_bytes(content)
            elif isinstance(content, str):
                # .lang files are plain text. Encoding them as JSON wraps the
                # whole file in quotes with literal \\n, which Bedrock reads as
                # one garbage line, so every name shows as its raw key.
                target.write_text(content, encoding="utf-8")
            else:
                target.write_text(json.dumps(content, indent=2) + "\n")
    return out_dir


def addon_name(namespace: str, meta: ModMetadata | None = None) -> str:
    """A filename the player will recognise in their downloads folder."""
    stem = (meta.mod_id if meta and meta.mod_id else namespace) or namespace
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in stem).strip("_")
    return f"{safe or namespace}.mcaddon"


def write_mcaddon(tree: Path, destination: Path) -> Path:
    """Zip the pack folders into one installable file.

    Only behavior_pack/ and resource_pack/ go in. The addon is written next to
    the tree, so zipping everything under it would put the addon's own
    neighbours (unhandled.json, a previous addon) inside the download.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zf:
        for pack in ("behavior_pack", "resource_pack"):
            base = tree / pack
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(tree))
    return destination
