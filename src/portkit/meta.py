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
    # The Minecraft version the mod declares it runs on (the lower bound of a
    # range, the newest of a list), as written; None when it doesn't say (#160).
    minecraft: str | None = None
    # A NeoForge jar that declares no minecraft dependency: the game version
    # its required ``neoforge`` dependency's lower bound names under NeoForge's
    # versioning (see :func:`_neoforge_minecraft`), else None. Only the vanilla
    # Blocks table reads it (#280); ``minecraft`` stays as declared.
    loader_minecraft: str | None = None
    notes: list[str] = field(default_factory=list)
    # Every mod the file declares (id -> version as written), and the mods it
    # declares as required dependencies; None when no metadata was read (#183).
    mods: dict[str, str] | None = None
    requires: list[str] | None = None

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


def load_json(blob: bytes):
    """Parse a jar's JSON metadata the way the loaders themselves do.

    Fabric's own parser accepts raw newlines and other control characters
    inside strings, and real mods ship them: betterend's description is a
    multi-line string written straight into fabric.mod.json. The standard
    library rejects that, so every JSON metadata reader (fabric.mod.json,
    quilt.mod.json, mcmod.info, here and in icon.py) goes through this one
    tolerant parse instead: the encoding is detected as json.loads(bytes)
    would (UTF-8 with or without a BOM, UTF-16/32), undecodable bytes are
    replaced rather than raised, and control characters inside strings are
    kept (strict=False). Raises json.JSONDecodeError for anything still broken.
    """
    text = blob.decode(json.detect_encoding(blob), "replace")
    return json.loads(text, strict=False)


_MC_VERSION = re.compile(r"\d+\.\d+(?:\.\d+)?")


def _mc_version(value) -> str | None:
    """A Minecraft version out of a declared range or list.

    ``[1.20.1,1.21)`` and ``>=1.21`` give their lower bound, ``~26.1`` the
    version itself, and a list (``["1.21.6", "1.21.8"]``) its newest entry.
    """
    if isinstance(value, list):
        found = [v for v in (_mc_version(x) for x in value) if v]
        return max(found, key=lambda v: tuple(int(p) for p in v.split(".")), default=None)
    if not isinstance(value, str):
        return None
    match = _MC_VERSION.search(value)
    return match.group(0) if match else None


def _toml_minecraft(data: dict) -> str | None:
    """The minecraft dependency's versionRange in mods.toml / neoforge.mods.toml."""
    deps = data.get("dependencies")
    groups = deps.values() if isinstance(deps, dict) else []
    for group in groups:
        for dep in group if isinstance(group, list) else []:
            if isinstance(dep, dict) and dep.get("modId") == "minecraft":
                return _mc_version(dep.get("versionRange"))
    return None


_NEOFORGE_VERSION = re.compile(r"^\s*[\[(]?\s*(\d+)\.(\d+)\.")


def _neoforge_minecraft(data: dict) -> str | None:
    """The Minecraft version a ``neoforge`` dependency's versionRange lower bound
    is built for, when the file names no ``minecraft`` dependency of its own.

    NeoForge's versioning (docs.neoforged.net, Getting Started > Versioning):
    "The major version is Minecraft's minor version, the minor version is
    Minecraft's patch version ... NeoForge 20.2.59 is the 60th version ... for
    Minecraft 1.20.2". Only majors 20-25 are read that way (NeoForge 1.20.1 was
    Forge's 47.x line, and 26.1+ spells the full version)."""
    if _toml_minecraft(data) is not None:
        return None
    deps = data.get("dependencies")
    for group in deps.values() if isinstance(deps, dict) else []:
        for dep in group if isinstance(group, list) else []:
            if isinstance(dep, dict) and dep.get("modId") == "neoforge" \
                    and isinstance(dep.get("versionRange"), str):
                match = _NEOFORGE_VERSION.match(dep["versionRange"])
                if match and 20 <= int(match.group(1)) <= 25:
                    major, minor = int(match.group(1)), int(match.group(2))
                    return f"1.{major}" if minor == 0 else f"1.{major}.{minor}"
                return None
    return None


def _text(value) -> str | None:
    """A free-text field, trimmed; None when empty or not a string."""
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _fabric(blob: bytes, notes: list[str]) -> ModMetadata:
    data = load_json(blob)
    return ModMetadata(
        mod_id=data.get("id"),
        name=data.get("name"),
        description=_text(data.get("description")),
        version_raw=data.get("version"),
        loader="fabric",
        minecraft=_mc_version((data.get("depends") or {}).get("minecraft")),
        notes=notes,
        mods=_declared({data.get("id"): data.get("version"), **_provides(data.get("provides"), data.get("version"))}),
        requires=sorted(k for k in (data.get("depends") or {}) if isinstance(k, str)),
    )


def _quilt(blob: bytes, notes: list[str]) -> ModMetadata:
    loader = load_json(blob).get("quilt_loader") or {}
    meta = loader.get("metadata") or {}
    return ModMetadata(
        mod_id=loader.get("id"),
        name=meta.get("name"),
        description=_text(meta.get("description")),
        version_raw=loader.get("version"),
        loader="quilt",
        minecraft=_quilt_minecraft(loader.get("depends")),
        notes=notes,
        mods=_declared({loader.get("id"): loader.get("version"),
                        **_provides(loader.get("provides"), loader.get("version"))}),
        requires=sorted(_quilt_depends(loader.get("depends"))),
    )


def _declared(pairs: dict) -> dict[str, str]:
    return {k: str(v) for k, v in pairs.items() if isinstance(k, str) and k}


def _provides(provides, version) -> dict:
    """Fabric/Quilt ``provides``: other ids this mod answers to, at its version."""
    out = {}
    for entry in provides if isinstance(provides, list) else []:
        ident = entry.get("id") if isinstance(entry, dict) else entry
        if isinstance(ident, str):
            out[ident] = (entry.get("version") if isinstance(entry, dict) else None) or version
    return out


def _quilt_depends(depends) -> list[str]:
    out = []
    for dep in depends if isinstance(depends, list) else []:
        ident = dep if isinstance(dep, str) else dep.get("id") if isinstance(dep, dict) else None
        if isinstance(ident, str) and not (isinstance(dep, dict) and dep.get("optional")):
            out.append(ident)
    return out


def _toml_requires(data: dict) -> list[str]:
    """Mandatory dependencies in mods.toml (mandatory=true) or neoforge.mods.toml (type="required")."""
    deps = data.get("dependencies")
    found: set[str] = set()
    for group in deps.values() if isinstance(deps, dict) else []:
        for dep in group if isinstance(group, list) else []:
            if not isinstance(dep, dict) or not isinstance(dep.get("modId"), str):
                continue
            kind = str(dep.get("type", "")).lower()
            if dep.get("mandatory") is True or kind == "required":
                found.add(dep["modId"])
    return sorted(found)


def _quilt_minecraft(depends) -> str | None:
    for dep in depends if isinstance(depends, list) else []:
        if isinstance(dep, dict) and dep.get("id") == "minecraft":
            versions = dep.get("versions")
            if isinstance(versions, dict):  # {"any": [...]} / {"all": [...]}
                versions = next(iter(versions.values()), None)
            return _mc_version(versions)
    return None


def _toml(blob: bytes, loader: str, notes: list[str]) -> ModMetadata:
    data = tomllib.loads(blob.decode("utf-8", "replace"))
    mods = data.get("mods") or []
    if not mods:
        notes.append(f"{loader} metadata declares no [[mods]] entry")
        return ModMetadata(loader=loader, minecraft=_toml_minecraft(data), notes=notes,
                           mods={}, requires=_toml_requires(data),
                           loader_minecraft=_neoforge_minecraft(data) if loader == "neoforge" else None)
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
        minecraft=_toml_minecraft(data),
        loader_minecraft=_neoforge_minecraft(data) if loader == "neoforge" else None,
        notes=notes,
        mods=_declared({m.get("modId"): m.get("version") for m in mods if isinstance(m, dict)}),
        requires=_toml_requires(data),
    )


def _mcmod_info(blob: bytes, notes: list[str]) -> ModMetadata:
    data = load_json(blob)
    entries = data.get("modList") if isinstance(data, dict) else data
    if not entries:
        notes.append("mcmod.info has no mod entries")
        return ModMetadata(loader="forge-legacy", notes=notes)
    first = entries[0]
    return ModMetadata(
        mod_id=first.get("modid"),
        name=first.get("name"),
        description=_text(first.get("description")),
        version_raw=first.get("version"),
        loader="forge-legacy",
        minecraft=_mc_version(first.get("mcversion")),
        notes=notes,
        mods=_declared({e.get("modid"): e.get("version") for e in entries if isinstance(e, dict)}),
        requires=sorted({d for e in entries if isinstance(e, dict)
                         for d in (e.get("requiredMods") or []) if isinstance(d, str)}),
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
                if meta.mods is not None:
                    meta.mods = {k: (resolved if v == raw else v) for k, v in meta.mods.items()}
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
