"""Name mappings for Forge SRG and Fabric intermediary jars, fetched on demand (#235).

The bytecode readers (:mod:`portkit.blockcode`, :mod:`portkit.entities`)
recognise Minecraft's classes and methods by their Mojang (official) names:
``getStateForPlacement``, ``net/minecraft/world/level/block/Block``. That is
what a NeoForge 1.20.5+ jar (and a 26.1+ jar, which Mojang no longer
obfuscates) holds. The rest of the corpus doesn't:

* a Forge 1.17-1.20.x jar (and NeoForge 1.20.1) keeps Mojang's class names but
  calls members by SRG names: ``m_5573_`` for ``getStateForPlacement``,
  ``f_54117_`` for ``HorizontalDirectionalBlock.FACING``;
* a Fabric (or Quilt) jar uses intermediary names for everything:
  ``net/minecraft/class_2248`` for ``Block``, ``method_9605`` for
  ``getStateForPlacement``, ``field_11177`` for ``FACING``, ``comp_N`` for
  record components.

Both id schemes number a member once for its whole override family, so one
flat table per scheme and game version (SRG or intermediary name -> Mojang
name, plus intermediary class -> Mojang class) is enough to put a jar's
references back into Mojang's names before the readers run
(:meth:`portkit.bytecode.ClassIndex.set_remapper`).

The table is joined from two upstream files on the obfuscated names they share:

* Mojang's ``client.txt`` for the game version (official -> obfuscated), from
  piston-data.mojang.com, pinned by the sha1 Mojang's version manifest gives.
  Its header: "(c) 2020 Microsoft Corporation. ... You may copy and use the
  mappings for development purposes, but you may not redistribute the
  mappings complete and unmodified."
* MCPConfig's ``config/joined.tsrg`` (obfuscated -> SRG), from the Forge maven
  zip, licence: (c) 2018 Forge Development LLC, zlib-style ("may ...
  redistribute it freely", altered versions plainly marked); or FabricMC's
  ``mappings/<version>.tiny`` (obfuscated -> intermediary), CC0 1.0.

Because the joined table carries Mojang's names, it is treated like Mojang's
file: never vendored in the repository or the wheel. ``portkit reference
fetch`` downloads the inputs, checks each against its pin (Mojang's sha1, a
sha256 for the others), derives the table, checks the table's sha256 and
caches it beside the other reference data. Without it, a renamed jar reads as
before (the readers say its names can't be matched) and the conversion notes
say to run the fetch.

A name that maps to more than one Mojang name is left unmapped rather than
guessed and listed under ``ambiguous`` in the table (none in the SRG sets; 8-10
intermediary ids per version, e.g. ``field_28859``).

``PORTKIT_MAPPINGS`` names a directory of derived tables
(``<set id>.json``) to use instead, unverified: it is how the tests run
offline against tiny tables of their own.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import FETCH_COMMAND, ReferenceDataError, _USER_AGENT, cache_dir

_ENV_DIR = "PORTKIT_MAPPINGS"
INTERMEDIARY_COMMIT = "916868752f6935dda70c4490404641a701335d81"
_MOJANG = "https://piston-data.mojang.com/v1/objects/{sha1}/client.txt"
_MCP = ("https://maven.minecraftforge.net/de/oceanlabs/mcp/mcp_config/{v}/"
        "mcp_config-{v}.zip")
_INTERMEDIARY = ("https://raw.githubusercontent.com/FabricMC/intermediary/"
                 f"{INTERMEDIARY_COMMIT}/mappings/{{v}}.tiny")

# Every name a renamed jar can hold for a Minecraft member or class.
OBFUSCATED_MEMBER = re.compile(r"^(?:m_\d+_|f_\d+_|method_\d+|field_\d+|comp_\d+)$")
_INTERMEDIARY_CLASS = re.compile(r"net/minecraft/class_\d+(?:\$class_\d+)*")


@dataclass(frozen=True)
class MappingSet:
    id: str
    scheme: str            # "srg" or "intermediary"
    minecraft: str
    mojang_sha1: str       # Mojang's sha1 of client.txt (version manifest)
    other: str             # MCPConfig version, or the intermediary file's game version
    other_sha256: str      # sha256 of the MCPConfig zip / intermediary .tiny
    sha256: str            # sha256 of the derived table

    @property
    def mojang_url(self) -> str:
        return _MOJANG.format(sha1=self.mojang_sha1)

    @property
    def other_url(self) -> str:
        return (_MCP if self.scheme == "srg" else _INTERMEDIARY).format(v=self.other)

    @property
    def label(self) -> str:
        what = (f"MCPConfig {self.other} (Forge Development LLC)" if self.scheme == "srg"
                else f"FabricMC/intermediary@{INTERMEDIARY_COMMIT[:12]} (CC0)")
        return f"{self.scheme} -> Mojang names, Minecraft {self.minecraft}: {what} + Mojang client.txt"


# sha256 of each derived table: `python -m portkit.data.mappings --pin` prints them.
SETS: tuple[MappingSet, ...] = (
    MappingSet("mappings-srg-1.20.1", "srg", "1.20.1", "6c48521eed01fe2e8ecdadbd5ae348415f3c47da",
               "1.20.1-20230612.114412",
               "f46d1050d8bed9046886b90a0d2fb80b4c6b5120fc35d32e5d37498dbe0a6d2a", "a82a1e9ba3d8a6c8231c7c0c20d9a4cd5b8648912e3d9583cd0a864ee9b22ccd"),
    MappingSet("mappings-srg-1.20", "srg", "1.20", "a4cd9a97400f7ecfe4dba23e427549ebc5815d66",
               "1.20-20230608.053357",
               "e96f9123bfe7676ca6f1917d81ef48ff94317397f19cf648fe369997c25ee7ba", "f9f3c62ae5cb75ea0cb688b838f9439fa05fc7d02d93544de98ae8620419d519"),
    MappingSet("mappings-srg-1.19.2", "srg", "1.19.2", "8e8c9be5dc27802caba47053d4fdea328f7f89bd",
               "1.19.2-20220805.130853",
               "fd4cf084b96492de87499b49d1ae5896ef14a3f85b5462d2842d7b193fba9135", "d3bbd2d1eadf518a3b03658dc839077b6b82f0e192c96cb61cbde598a0528596"),
    MappingSet("mappings-intermediary-1.21.8", "intermediary", "1.21.8",
               "bdeb624c3aefba11d9d40f34bc96176350b549b6", "1.21.8",
               "663b86b08908d1f1c58cf6632a5765e2ae3d2f4396146456feb1aba728bf5875", "3d98ff44261b658b1b04e7f1a4fc4693a6e1088f5d65fea885134b774a47c68a"),
    MappingSet("mappings-intermediary-1.21.1", "intermediary", "1.21.1",
               "2244b6f072256667bcd9a73df124d6c58de77992", "1.21.1",
               "83071b5b17866658463255f5f21430ade2a49ce2dd089dc3c14de1e93b99211c", "f09946a23536d92111cad2773d4962307c3b2cca4d8e4238e7e08399ed04064a"),
    MappingSet("mappings-intermediary-1.21", "intermediary", "1.21",
               "0530a206839eb1e9b35ec86acbbe394b07a2d9fb", "1.21",
               "0f7e4a5a2677b5bcbb1185ebdcfc62645ad01d8e547a7857052d0b1d48d0dff4", "a5218458c30868375c2285f87a94817905fc9e8950bc24cbf23667b52667471d"),
    MappingSet("mappings-intermediary-1.20.1", "intermediary", "1.20.1",
               "6c48521eed01fe2e8ecdadbd5ae348415f3c47da", "1.20.1",
               "5a808bd1ebc4a9ee7d1c5900dbd2bf391586b536c3d86fbf2f972047faa2d165", "47b10d0d38564c976b0ca55a51a4c6106c03d1055b2e119ca610c4e018e2ff2e"),
    MappingSet("mappings-intermediary-1.20", "intermediary", "1.20",
               "a4cd9a97400f7ecfe4dba23e427549ebc5815d66", "1.20",
               "818b0eec9b4efd95dd07c6b9462ec49e1df89b49e0cb882ee079f70da65f142d", "74f7bebaf7dfddb006da77dc396b5f615c91d6ebac060cd8b9a9a036e13475ab"),
    MappingSet("mappings-intermediary-1.19.2", "intermediary", "1.19.2",
               "8e8c9be5dc27802caba47053d4fdea328f7f89bd", "1.19.2",
               "e6ffae7d65077b1b73fa95e5c06c9e1d32445bb43504d672559088a8b0706ca2", "8b2f19b154fa7e0db456367e06f8d14b3c705bdff22f1928b9f2e900df08f92f"),
)
_BY_ID = {s.id: s for s in SETS}


def select(loader: str | None, minecraft: str | None) -> MappingSet | None:
    """The set a mod built for ``loader`` and ``minecraft`` needs, or None when
    its jar holds Mojang names already (NeoForge 1.20.5+, 26.1+) or no set is
    pinned for its version. NeoForge 1.20.1 is Forge's fork and still SRG.

    ``minecraft`` is the version the mod declares (the lower bound of a
    range, see :func:`portkit.meta._mc_version`), and only that exact
    version's table is used: SRG and intermediary ids name a member for good,
    so the table of a range's lower bound also names what a later patch
    release of the same game kept."""
    if not loader or not minecraft:
        return None
    if minecraft.endswith(".0"):  # "1.21.0" is 1.21
        minecraft = minecraft[:-2]
    scheme = {"forge": "srg", "fabric": "intermediary", "quilt": "intermediary"}.get(loader)
    if loader == "neoforge" and minecraft == "1.20.1":
        scheme = "srg"
    for s in SETS:
        if s.scheme == scheme and s.minecraft == minecraft:
            return s
    return None


# --- deriving a table -------------------------------------------------------

_PRIMITIVE = {"byte": "B", "char": "C", "double": "D", "float": "F", "int": "I",
              "long": "J", "short": "S", "boolean": "Z", "void": "V"}


def _parse_mojang(text: str):
    """client.txt -> (classes official->obf, methods [(obf owner, official name,
    official return, official args, obf name)], fields [(obf owner, official, obf)])."""
    classes: dict[str, str] = {}
    methods, fields = [], []
    owner = None
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        if not line.startswith(" "):
            official, _, obf = line.rstrip(":").partition(" -> ")
            owner = obf.replace(".", "/")
            classes[official.replace(".", "/")] = owner
            continue
        member, _, obf = line.strip().partition(" -> ")
        if "(" in member:
            sig = member.split(":")[-1]  # drop the line numbers
            ret, _, rest = sig.partition(" ")
            name, _, args = rest.partition("(")
            args = args.rstrip(")")
            methods.append((owner, name, ret, args.split(",") if args else [], obf))
        else:
            _type, _, name = member.partition(" ")
            fields.append((owner, name, obf))
    return classes, methods, fields


def _obf_desc(ret: str, args: list[str], classes: dict[str, str]) -> str:
    def one(t: str) -> str:
        dims = t.count("[]")
        base = t.replace("[]", "")
        if base in _PRIMITIVE:
            code = _PRIMITIVE[base]
        else:
            path = base.replace(".", "/")
            code = f"L{classes.get(path, path)};"
        return "[" * dims + code
    return "(" + "".join(one(a) for a in args) + ")" + one(ret)


def _parse_tsrg(text: str):
    """MCPConfig joined.tsrg (tsrg2 obf srg id) -> (methods {(obf owner, obf
    name, obf desc): srg}, fields {(obf owner, obf name): srg})."""
    methods, fields = {}, {}
    owner = None
    for line in text.splitlines()[1:]:
        if not line.strip():
            continue
        if not line.startswith("\t"):
            owner = line.split(" ")[0]
            continue
        if line.startswith("\t\t"):
            continue  # parameters and the static marker
        parts = line[1:].split(" ")
        if len(parts) == 4:          # method: obf desc srg id
            methods[(owner, parts[0], parts[1])] = parts[2]
        elif len(parts) == 3:        # field: obf srg id
            fields[(owner, parts[0])] = parts[1]
    return methods, fields


def _parse_tiny(text: str):
    """Fabric intermediary tiny v1 -> (classes {obf: inter}, methods
    {(obf owner, obf name, obf desc): inter}, fields {(obf owner, obf name): inter})."""
    classes, methods, fields = {}, {}, {}
    for line in text.splitlines()[1:]:
        parts = line.split("\t")
        if parts[0] == "CLASS" and len(parts) >= 3:
            classes[parts[1]] = parts[2]
        elif parts[0] == "METHOD" and len(parts) >= 5:
            methods[(parts[1], parts[3], parts[2])] = parts[4]
        elif parts[0] == "FIELD" and len(parts) >= 5:
            fields[(parts[1], parts[3])] = parts[4]
    return classes, methods, fields


def derive(mapping: MappingSet, mojang: bytes, other: bytes) -> bytes:
    """Join Mojang's client.txt with the MCPConfig zip or the intermediary
    .tiny into {"classes", "members", "ambiguous"} (renamed -> Mojang)."""
    classes_o2m, m_methods, m_fields = _parse_mojang(mojang.decode("utf-8"))
    if mapping.scheme == "srg":
        with zipfile.ZipFile(io.BytesIO(other)) as zf:
            tsrg = zf.read("config/joined.tsrg").decode("utf-8")
        o_methods, o_fields = _parse_tsrg(tsrg)
        o_classes: dict[str, str] = {}
    else:
        o_classes, o_methods, o_fields = _parse_tiny(other.decode("utf-8"))

    members: dict[str, str] = {}
    ambiguous: set[str] = set()

    def add(renamed: str | None, official: str) -> None:
        if not renamed or renamed == official or not OBFUSCATED_MEMBER.match(renamed):
            return
        if members.get(renamed, official) != official:
            ambiguous.add(renamed)
        members[renamed] = official

    for owner, name, ret, args, obf in m_methods:
        add(o_methods.get((owner, obf, _obf_desc(ret, args, classes_o2m))), name)
    for owner, name, obf in m_fields:
        add(o_fields.get((owner, obf)), name)
    for name in ambiguous:
        members.pop(name, None)
    classes = {}
    for official, obf in classes_o2m.items():
        inter = o_classes.get(obf)
        if inter and inter != official and _INTERMEDIARY_CLASS.fullmatch(inter):
            classes[inter] = official
    out = {
        "set": mapping.id,
        "label": mapping.label,
        "sources": [mapping.mojang_url, mapping.other_url],
        "notice": "Derived from Mojang's mappings ((c) Microsoft, not for redistribution "
                  "complete and unmodified); fetched by `portkit reference fetch`, never vendored.",
        "classes": dict(sorted(classes.items())),
        "members": dict(sorted(members.items())),
        "ambiguous": sorted(ambiguous),
    }
    return (json.dumps(out, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


# --- fetch and cache --------------------------------------------------------

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def set_path(mapping: MappingSet, cache: Path | None = None) -> Path:
    return Path(cache or cache_dir()) / f"{mapping.id}-{mapping.sha256[:12]}.json"


def cached(mapping: MappingSet, cache: Path | None = None) -> Path | None:
    """The verified cached table, or None when it is missing or doesn't match the pin."""
    path = set_path(mapping, cache)
    return path if path.is_file() and _sha256(path.read_bytes()) == mapping.sha256 else None


def _get(url: str, opener) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with opener(request, timeout=300) as response:
        return response.read()


def download(mapping: MappingSet, opener=urllib.request.urlopen) -> bytes:
    """The derived table from upstream; each input is checked against its pin."""
    try:
        mojang = _get(mapping.mojang_url, opener)
        other = _get(mapping.other_url, opener)
    except (OSError, ValueError, AttributeError) as exc:
        raise ReferenceDataError(f"{mapping.id}: download failed: {exc}") from exc
    if hashlib.sha1(mojang).hexdigest() != mapping.mojang_sha1:
        raise ReferenceDataError(f"{mapping.id}: sha1 mismatch for {mapping.mojang_url}")
    if _sha256(other) != mapping.other_sha256:
        raise ReferenceDataError(f"{mapping.id}: sha256 mismatch for {mapping.other_url}; "
                                 "re-pin it on purpose")
    try:
        return derive(mapping, mojang, other)
    except (ValueError, KeyError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
        raise ReferenceDataError(f"{mapping.id}: can't derive the table: {exc}") from exc


def fetch(mapping: MappingSet, cache: Path | None = None,
          opener=urllib.request.urlopen) -> tuple[Path, bool]:
    """Return (cached path, downloaded?). Raises ReferenceDataError on failure or a hash mismatch."""
    cache = Path(cache or cache_dir())
    hit = cached(mapping, cache)
    if hit:
        return hit, False
    data = download(mapping, opener)
    digest = _sha256(data)
    if digest != mapping.sha256:
        raise ReferenceDataError(
            f"{mapping.id}: derived table sha256 {digest[:16]}... isn't the pinned "
            f"{mapping.sha256[:16]}...; re-pin it on purpose")
    cache.mkdir(parents=True, exist_ok=True)
    target = set_path(mapping, cache)
    partial = target.with_suffix(".part")
    partial.write_bytes(data)
    partial.replace(target)
    _read.cache_clear()
    return target, True


# --- the remapper -----------------------------------------------------------

class Remapper:
    """Renamed -> Mojang names for one table. Names it doesn't know (the
    mod's own, Java's, an unmapped id) come back unchanged."""

    def __init__(self, set_id: str, classes: dict[str, str], members: dict[str, str]):
        self.set_id = set_id
        self.classes = classes
        self.members = members

    def member(self, name: str) -> str:
        return self.members.get(name, name) if OBFUSCATED_MEMBER.match(name) else name

    def cls(self, name: str) -> str:
        if name.startswith("["):
            return self.desc(name)
        return self.classes.get(name, name) if self.classes else name

    def desc(self, desc: str) -> str:
        if not self.classes or "class_" not in desc:
            return desc
        return _INTERMEDIARY_CLASS.sub(lambda m: self.classes.get(m.group(0), m.group(0)), desc)


@lru_cache(maxsize=4)
def _read(path: str, mtime_ns: int, size: int, expected: str | None) -> Remapper | None:
    data = Path(path).read_bytes()
    if expected is not None and _sha256(data) != expected:
        return None
    try:
        table = json.loads(data)
        return Remapper(table.get("set", ""), dict(table.get("classes") or {}),
                        dict(table.get("members") or {}))
    except (ValueError, AttributeError, TypeError):
        return None


def remapper(mapping: MappingSet) -> Remapper | None:
    """The table for ``mapping``, or None when it isn't cached (run ``portkit reference fetch``)."""
    override = os.environ.get(_ENV_DIR)
    path = Path(override).expanduser() / f"{mapping.id}.json" if override else set_path(mapping)
    try:
        stat = path.stat()
    except OSError:
        return None
    return _read(str(path), stat.st_mtime_ns, stat.st_size, None if override else mapping.sha256)


def renamed_scheme(classes) -> str | None:
    """"srg" or "intermediary" when the jar's own classes declare or call
    members by those names, else None (Mojang-named, or no code)."""
    for name in classes.names():
        cf = classes.get(name, remap=False)
        if cf is None:
            continue
        for m in cf.methods:
            if m.name.startswith("m_") and OBFUSCATED_MEMBER.match(m.name):
                return "srg"
            if m.name.startswith("method_") and OBFUSCATED_MEMBER.match(m.name):
                return "intermediary"
    return None


def attach(classes, loader: str | None, minecraft: str | None) -> str | None:
    """Give ``classes`` (a :class:`portkit.bytecode.ClassIndex`) the remapper
    its loader and game version need. Returns a conversion note when the jar
    is renamed but its table can't be had, else None."""
    mapping = select(loader, minecraft)
    if mapping is None or classes is None or not len(classes):
        return None
    found = remapper(mapping)
    if found is not None:
        classes.set_remapper(found)
        return None
    if renamed_scheme(classes) is None:
        return None
    kind = "Forge SRG" if mapping.scheme == "srg" else "Fabric intermediary"
    return (f"This jar's code uses {kind} names and the {mapping.id} table isn't cached, so the "
            f"bytecode readers can't match Minecraft's methods in it; run `{FETCH_COMMAND}`.")


if __name__ == "__main__":  # pragma: no cover - maintenance helper
    if sys.argv[1:] == ["--pin"]:
        for s in SETS:
            data = download(s)
            digest = _sha256(data)
            table = json.loads(data)
            print(f"{s.id} {digest} {'ok' if digest == s.sha256 else 'CHANGED'} "
                  f"classes={len(table['classes'])} members={len(table['members'])} "
                  f"ambiguous={len(table['ambiguous'])}")
        sys.exit(0)
    print(f"usage: python -m portkit.data.mappings --pin   (fetch with `{FETCH_COMMAND}`)")
    sys.exit(2)
