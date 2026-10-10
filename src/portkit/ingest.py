"""Turn whatever the user hands us into a plain directory of mod resources.

A Java mod ships as a .jar, which is a zip of compiled classes plus the
resource tree the converters actually care about (assets/ and data/). This
module stages that tree onto disk and is honest about everything it drops.

Nothing here guesses. Compiled code and jar-in-jar dependencies are reported as
residue rather than silently ignored.
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .icon import declared_paths
from .model import Unhandled

RESOURCE_LANES = ("assets/", "data/")

# Loader metadata, read by meta.parse(). MANIFEST.MF is here because Forge lets
# version be "${file.jarVersion}", a placeholder only the jar manifest resolves.
METADATA_NAMES = (
    "fabric.mod.json",
    "quilt.mod.json",
    "META-INF/mods.toml",
    "META-INF/neoforge.mods.toml",
    "META-INF/MANIFEST.MF",
    "mcmod.info",
    "pack.mcmeta",
)

_MAX_MEMBERS = 50_000
_MAX_TOTAL_BYTES = 512 * 1024 * 1024
_MAX_ICON_BYTES = 8 * 1024 * 1024


class IngestError(Exception):
    """The source could not be read at all."""


@dataclass
class Ingested:
    """A staged mod, ready for the converters."""

    root: Path
    namespaces: list[str] = field(default_factory=list)
    metadata: dict[str, bytes] = field(default_factory=dict)
    class_count: int = 0
    nested_jars: list[str] = field(default_factory=list)
    # Icon files the mod declares (see icon.declared_paths) that it actually
    # ships, path -> bytes, in declaration order. Most live outside assets/, so
    # they are read here rather than staged.
    icons: dict[str, bytes] = field(default_factory=dict)

    @property
    def namespace(self) -> str:
        if not self.namespaces:
            raise IngestError(f"no mod namespace found under {self.root}")
        return self.namespaces[0]

    def residue(self) -> list[Unhandled]:
        """Residue that ingestion itself can see, before any converter runs."""
        items: list[Unhandled] = []
        if self.class_count:
            items.append(
                Unhandled(
                    source=f"{self.class_count} compiled class file(s)",
                    kind="java_code",
                    reason=(
                        "mod behavior lives in JVM bytecode; there is no deterministic "
                        "mapping to the Bedrock scripting API"
                    ),
                    count=self.class_count,
                )
            )
        for name in self.nested_jars:
            items.append(
                Unhandled(
                    source=name,
                    kind="nested_jar",
                    reason="jar-in-jar dependency not unpacked; its resources are not converted",
                )
            )
        return items


def _safe_member(name: str) -> bool:
    """Reject absolute paths and anything climbing out of the staging dir."""
    if name.startswith("/") or name.startswith("\\") or ":" in name.split("/")[0][1:]:
        return False
    return ".." not in Path(name).parts


def _namespaces(root: Path) -> list[str]:
    found: list[str] = []
    for lane in ("assets", "data"):
        base = root / lane
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if child.is_dir() and child.name != "minecraft" and child.name not in found:
                found.append(child.name)
    return found


def from_directory(root: Path) -> Ingested:
    root = Path(root)
    if not root.is_dir():
        raise IngestError(f"{root} is not a directory")
    metadata = {}
    for name in METADATA_NAMES:
        candidate = root / name
        if candidate.is_file():
            metadata[name] = candidate.read_bytes()
    icons = {}
    for rel in declared_paths(metadata):
        candidate = root / rel
        if (
            _safe_member(rel)
            and candidate.is_file()
            and candidate.stat().st_size <= _MAX_ICON_BYTES
        ):
            icons[rel] = candidate.read_bytes()
    return Ingested(
        root=root,
        namespaces=_namespaces(root),
        metadata=metadata,
        class_count=sum(1 for _ in root.rglob("*.class")),
        icons=icons,
    )


def from_jar(jar_path: Path, workdir: Path) -> Ingested:
    """Extract the resource lanes of a mod jar into workdir."""
    jar_path = Path(jar_path)
    if not jar_path.is_file():
        raise IngestError(f"{jar_path} is not a file")
    if not zipfile.is_zipfile(jar_path):
        raise IngestError(f"{jar_path} is not a jar (zip) archive")

    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    metadata: dict[str, bytes] = {}
    class_count = 0
    nested: list[str] = []
    total = 0

    with zipfile.ZipFile(jar_path) as zf:
        members = zf.infolist()
        if len(members) > _MAX_MEMBERS:
            raise IngestError(f"{jar_path} has {len(members)} members; refusing to unpack")
        for info in members:
            name = info.filename
            if info.is_dir() or not _safe_member(name):
                continue
            total += info.file_size
            if total > _MAX_TOTAL_BYTES:
                raise IngestError(f"{jar_path} expands past {_MAX_TOTAL_BYTES} bytes; refusing")
            if name.endswith(".class"):
                class_count += 1
                continue
            if name.endswith(".jar"):
                nested.append(name)
                continue
            if name in METADATA_NAMES:
                metadata[name] = zf.read(info)
                continue
            if not name.startswith(RESOURCE_LANES):
                continue
            target = workdir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                dst.write(src.read())

        icons = {}
        names = {info.filename: info for info in members}
        for rel in declared_paths(metadata):
            info = names.get(rel)
            if info is not None and _safe_member(rel) and info.file_size <= _MAX_ICON_BYTES:
                icons[rel] = zf.read(info)

    found = _namespaces(workdir)
    if not found:
        raise IngestError(
            f"{jar_path.name} has no assets/<namespace> or data/<namespace> tree; "
            "nothing to convert"
        )
    return Ingested(
        root=workdir,
        namespaces=found,
        metadata=metadata,
        class_count=class_count,
        nested_jars=nested,
        icons=icons,
    )


def ingest(source: Path, workdir: Path) -> Ingested:
    """Accept a directory or a .jar and stage it the same way."""
    source = Path(source)
    if source.is_dir():
        return from_directory(source)
    return from_jar(source, workdir)
