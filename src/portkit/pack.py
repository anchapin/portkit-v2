"""Assemble converted files into a Bedrock pack tree (and an .mcaddon)."""
from __future__ import annotations

import json
import uuid
import zipfile
from pathlib import Path

from .icon import ICON_NAME, default_icon
from .meta import ModMetadata
from .model import ConversionResult

# Deterministic UUIDs: same mod in, same manifest out, so fixture diffs are
# clean. The seed includes the pack's header name, not just the namespace,
# because Bedrock keys an installed pack by UUID alone: two packs sharing a
# namespace (the axis probe and the rotation probe both used "probe") hashed to
# the same UUID pair, so importing the second collided with the first instead
# of installing beside it.
_NS = uuid.UUID("6f0a7f1e-0a4a-4f2e-9a1b-6a5f0d1c2b3e")

_BEHAVIOR_DIRS = ("recipes/", "entities/", "functions/", "loot_tables/", "blocks/", "items/", "scripts/")

# A behavior pack that ships this file gets a script module running it, and a
# dependency on the Script API version the station runtimes are written
# against (#177; see portkit.converters.stations). Kept literal here so the
# pack writer doesn't import the converters.
SCRIPT_ENTRY = "scripts/portkit/main.js"
SCRIPT_DEPENDENCY = {"module_name": "@minecraft/server", "version": "2.0.0"}
# @minecraft/server 2.0.0 shipped with Bedrock 1.21.90 (minecraft.net,
# "Minecraft 1.21.90 Bedrock Changelog").
SCRIPT_ENGINE = (1, 21, 90)
# A runtime that shows forms (the waystone menu, #178) imports
# @minecraft/server-ui; the pack then declares it too. 2.0.0 is the stable
# release published with @minecraft/server 2.0.0 for Bedrock 1.21.90 (npm
# @minecraft/server-ui 2.0.0, 2025-06-17, depends on @minecraft/server ^2.0.0),
# so the engine floor stays where the station scripts put it.
SCRIPT_UI_DEPENDENCY = {"module_name": "@minecraft/server-ui", "version": "2.0.0"}
SCRIPT_UI_IMPORT = 'from "@minecraft/server-ui"'


def _uuid(*parts: str) -> str:
    return str(uuid.uuid5(_NS, "/".join(parts)))


def manifest(
    namespace: str,
    kind: str,
    meta: ModMetadata | None = None,
    depends_on: tuple[str, ...] = (),
    min_engine: tuple[int, int, int] = (1, 20, 20),
    script_entry: str | None = None,
    script_ui: bool = False,
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
    if script_entry:
        # learn.microsoft.com, Pack Manifest (modules: type "script", language
        # "javascript"; dependencies: module_name for built-in script modules).
        data["modules"].append({
            "type": "script",
            "language": "javascript",
            "uuid": _uuid(namespace, meta.header_name(namespace, kind), kind, "script"),
            "version": list(version),
            "entry": script_entry,
        })
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
    if script_entry:
        data.setdefault("dependencies", []).append(dict(SCRIPT_DEPENDENCY))
        if script_ui:
            data["dependencies"].append(dict(SCRIPT_UI_DEPENDENCY))
    return data


def uses_script_ui(files: dict) -> bool:
    """Whether a shipped script imports @minecraft/server-ui."""
    return any(path.startswith("scripts/") and isinstance(body, str) and SCRIPT_UI_IMPORT in body
               for path, body in files.items())


ENGINE_FLOOR = (1, 20, 20)


def engine_floor(files: dict) -> tuple[int, int, int]:
    """The oldest engine that loads every block and item in this pack.

    The floor stays at ENGINE_FLOOR unless a block, a block geometry or an
    item was written at a newer format because it needs a newer feature (an
    item's ``minecraft:hand_equipped`` needs 1.20.30, ``minecraft:tags`` 1.20.50),
    so a mod with only simple blocks and items still loads on older versions.
    """
    floor = ENGINE_FLOOR
    if SCRIPT_ENTRY in files:
        floor = max(floor, SCRIPT_ENGINE)
    for relpath, content in files.items():
        is_block = relpath.startswith("blocks/")
        is_item = relpath.startswith("items/")
        is_geometry = relpath.startswith(("models/blocks/", "models/entity/")) and relpath.endswith(".geo.json")
        if not ((is_block or is_item or is_geometry) and isinstance(content, dict)):
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


# File names Minecraft Creator Tools (mct 0.20.0, cli/index.mjs, the json
# item-type switch on ``baseName``) reads as JavaScript tooling files wherever
# they sit: a pack with scripts and a file named package.json anywhere fails
# its SCRIPTMODULE check ("Could not find an package.json registration for
# @minecraft/server"). Bedrock finds block and item definitions by folder,
# not by file name, so such a definition is written as ``_<name>.json``.
_TOOLING_NAMES = {"package", "package.lock", "tsconfig", "jsconfig", "jsdoc", "docfx", ".prettierrc"}


def _written_as(relpath: str, files: dict) -> str:
    """The path a definition is written at (see _TOOLING_NAMES)."""
    folder, _, leaf = relpath.rpartition("/")
    if folder not in ("blocks", "items") or not leaf.endswith(".json") or leaf[:-5] not in _TOOLING_NAMES:
        return relpath
    renamed = f"{folder}/_{leaf}"
    return relpath if renamed in files else renamed


def write_tree(
    result: ConversionResult,
    namespace: str,
    out_dir: Path,
    meta: ModMetadata | None = None,
    icon: bytes | None = None,
) -> Path:
    """Write behavior_pack/ and resource_pack/ under out_dir. Returns out_dir.

    Each pack gets ``icon`` as its pack_icon.png, or a generated one when none
    is given (#115): Bedrock shows a placeholder without it, and Mojang's
    validator rejects the pack.
    """
    icon = icon if icon is not None else default_icon(namespace)
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
        entry = SCRIPT_ENTRY if kind == "behavior" and SCRIPT_ENTRY in files else None
        (base / "manifest.json").write_text(
            json.dumps(manifest(namespace, kind, meta, depends_on, floor, entry,
                                script_ui=bool(entry) and uses_script_ui(files)), indent=2) + "\n"
        )
        (base / ICON_NAME).write_bytes(icon)
        for relpath, content in files.items():
            target = base / _written_as(relpath, files)
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
