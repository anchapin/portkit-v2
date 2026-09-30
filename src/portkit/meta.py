"""Loader metadata: who this mod says it is.

Namespace detection by directory scan tells us where the files live, not what
the mod is called. Every loader ships a declaration file with the real id, name,
version and description, in four different shapes:

    fabric.mod.json          Fabric, flat JSON
    quilt.mod.json           Quilt, nested under quilt_loader
    META-INF/mods.toml       Forge, TOML with a [[mods]] array
    META-INF/neoforge.mods.toml  NeoForge, same shape
    mcmod.info               Pre-1.13 Forge, a JSON list

We read whichever is present, in that order, and fall back to the directory
scan with a note when a mod ships none of them. Nothing here raises: bad
metadata costs us a good manifest header, not the conversion.
"""
from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field

# Forge lets the version be a placeholder the build resolves from the jar's own
# MANIFEST.MF, so version="${file.jarVersion}" is extremely common in the wild.
_PLACEHOLDER = re.compile(r"^\$\{.*\}$")
_VERSION_PART = re.compile(r"\d+")


@dataclass
class ModMetadata:
    """What the mod declares about itself."""

    mod_id: str | None = None
    name: str | None = None
    description: str | None = None
    version: tuple[int, int, int] = (0, 1, 0)
    version_raw: str | None = None
    loader: str | None = None
    notes: list[str] = field(default_factory=list)

    def header_name(self, namespace: str, kind: str) -> str:
        return f"{self.name or self.mod_id or namespace} ({kind})"

    def header_description(self) -> str:
        return self.description or "Converted from Java by portkit"


def parse_version(raw: str | None, notes: list[str]) -> tuple[int, int, int]:
    """Best-effort semver out of whatever the loader declared.

    Bedrock manifests need three integers. Java versions are free text:
    '5.0.2+fabric', '1.20.4-0.3', '2.0.0-beta.4'. Take the leading numbers and
    say so when the result is a guess, because a wrong version silently breaks
    pack updates for anyone who already installed the add-on.
    """
    if not raw:
        return (0, 1, 0)
    if _PLACEHOLDER.match(raw.strip()):
        notes.append(f"version {raw!r} is a build placeholder that was never resolved")
        return (0, 1, 0)

    lead = raw.split("+")[0]
    numbers = [int(n) for n in _VERSION_PART.findall(lead)[:3]]
    if not numbers:
        notes.append(f"version {raw!r} has no numbers in it; using 0.1.0")
        return (0, 1, 0)
    while len(numbers) < 3:
        numbers.append(0)
    if len(_VERSION_PART.findall(lead)) > 3:
        notes.append(f"version {raw!r} has more than three parts; kept the first three")
    return (numbers[0], numbers[1], numbers[2])


def _manifest_version(blob: bytes | None) -> str | None:
    """Implementation-Version out of a jar MANIFEST.MF, for ${file.jarVersion}."""
    if not blob:
        return None
    for line in blob.decode("utf-8", "replace").splitlines():
        key, _, value = line.partition(":")
        if key.strip() == "Implementation-Version" and value.strip():
            return value.strip()
    return None


def _fabric(blob: bytes, notes: list[str]) -> ModMetadata:
    data = json.loads(blob)
    return ModMetadata(
        mod_id=data.get("id"),
        name=data.get("name"),
        description=data.get("description"),
        version_raw=data.get("version"),
        loader="fabric",
        notes=notes,
    )


def _quilt(blob: bytes, notes: list[str]) -> ModMetadata:
    loader = json.loads(blob).get("quilt_loader") or {}
    meta = loader.get("metadata") or {}
    return ModMetadata(
        mod_id=loader.get("id"),
        name=meta.get("name"),
        description=meta.get("description"),
        version_raw=loader.get("version"),
        loader="quilt",
        notes=notes,
    )


def _toml(blob: bytes, loader: str, notes: list[str]) -> ModMetadata:
    data = tomllib.loads(blob.decode("utf-8", "replace"))
    mods = data.get("mods") or []
    if not mods:
        notes.append(f"{loader} metadata declares no [[mods]] entry")
        return ModMetadata(loader=loader, notes=notes)
    if len(mods) > 1:
        ids = ", ".join(str(m.get("modId")) for m in mods)
        notes.append(f"{loader} metadata declares {len(mods)} mods ({ids}); using the first")
    first = mods[0]
    return ModMetadata(
        mod_id=first.get("modId"),
        name=first.get("displayName"),
        description=(first.get("description") or "").strip() or None,
        version_raw=first.get("version"),
        loader=loader,
        notes=notes,
    )


def _mcmod_info(blob: bytes, notes: list[str]) -> ModMetadata:
    data = json.loads(blob)
    entries = data.get("modList") if isinstance(data, dict) else data
    if not entries:
        notes.append("mcmod.info has no mod entries")
        return ModMetadata(loader="forge-legacy", notes=notes)
    first = entries[0]
    return ModMetadata(
        mod_id=first.get("modid"),
        name=first.get("name"),
        description=(first.get("description") or "").strip() or None,
        version_raw=first.get("version"),
        loader="forge-legacy",
        notes=notes,
    )


_READERS = (
    ("fabric.mod.json", _fabric),
    ("quilt.mod.json", _quilt),
    ("META-INF/neoforge.mods.toml", lambda b, n: _toml(b, "neoforge", n)),
    ("META-INF/mods.toml", lambda b, n: _toml(b, "forge", n)),
    ("mcmod.info", _mcmod_info),
)


def parse(metadata: dict[str, bytes], namespace: str) -> ModMetadata:
    """Read the first loader declaration present. Never raises."""
    notes: list[str] = []
    for name, reader in _READERS:
        blob = metadata.get(name)
        if blob is None:
            continue
        try:
            meta = reader(blob, notes)
        except (json.JSONDecodeError, tomllib.TOMLDecodeError, AttributeError, TypeError) as exc:
            notes.append(f"{name} could not be read ({exc}); falling back to the directory scan")
            continue

        raw = meta.version_raw
        if raw and _PLACEHOLDER.match(str(raw).strip()):
            resolved = _manifest_version(metadata.get("META-INF/MANIFEST.MF"))
            if resolved:
                meta.version_raw = resolved
                notes.append(f"resolved {raw} from the jar manifest as {resolved}")
        meta.version = parse_version(meta.version_raw, notes)

        if meta.mod_id and meta.mod_id != namespace:
            notes.append(
                f"declared mod id {meta.mod_id!r} does not match the resource namespace "
                f"{namespace!r}; namespace wins for file paths"
            )
        return meta

    notes.append(
        "no loader metadata found (fabric.mod.json, mods.toml, mcmod.info); "
        f"falling back to the directory scan, so the pack is named after {namespace!r}"
    )
    return ModMetadata(notes=notes)
