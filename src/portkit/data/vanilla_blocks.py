"""Vanilla ``Blocks`` field -> block registry id, derived from Mojang's client jar on demand (#280).

A mod that builds a variant from a vanilla block (``new VerticalSlabBlock(Blocks.OAK_SLAB, ..)``
named from the parent's registry key, ``getKey(Blocks.OAK_SLAB)``) can only be named when
the reader knows which registry id the field ``Blocks.OAK_SLAB`` holds. The field's
lower-cased name is not that id for every field (``POTTED_AZALEA`` is
``potted_azalea_bush`` in every version below), so it is read, not guessed (#87).

Where it comes from, per game version (:data:`SETS`):

* Mojang's client jar for that version (piston-data.mojang.com, pinned by the sha1
  Mojang's version manifest gives), class ``net.minecraft.world.level.block.Blocks``:
  its static initializer assigns every block field from one call of a ``Blocks``
  registration helper whose first argument is the id, either a string constant
  (``register("oak_planks", ..)``) or a ``ResourceKey`` constant of another class whose
  own initializer is ``createKey("pumpkin")`` (1.21+ ``net.minecraft.references.Blocks``);
* Mojang's ``client.txt`` for that version (the same file and pin
  :mod:`portkit.data.mappings` uses) to name the obfuscated class and fields.

:func:`derive` reads the initializer with :mod:`portkit.bytecode`: the instructions
between two ``putstatic`` of a ``Blocks`` field must start with the id (an ``ldc`` of a
string, or a ``getstatic`` of such a key) and end with an ``invokestatic`` of a ``Blocks``
method whose first parameter is a ``String`` or a ``ResourceKey``, immediately before the
``putstatic``. A block field assigned any other way is listed under ``unmatched`` and left
out, not guessed. Each id is also checked against the same jar's
``assets/minecraft/blockstates/<id>.json`` (ids without one are listed under
``no_blockstate``; they are still the registry id). Nothing else from the jar is kept.

Like the joined mappings table, the result carries Mojang's names, so it is never
vendored in the repository or the wheel: ``portkit reference fetch`` downloads both
inputs, checks them against their sha1 pins, derives the table, checks the table's
sha256 and caches it. Without it a variant of a vanilla block stays unread, as before.
Only the exact game version a mod declares is used (a field can be renamed between
patch releases: 1.20.3 renamed ``GRASS`` to ``SHORT_GRASS``).

``PORTKIT_VANILLA_BLOCKS`` names a directory of derived tables (``<set id>.json``) to
use instead, unverified: it is how the tests run offline.

``python -m portkit.data.vanilla_blocks --pin`` downloads every set and prints the sha256s.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import FETCH_COMMAND, ReferenceDataError, _USER_AGENT, cache_dir
from .mappings import _MOJANG, _parse_mojang

_ENV_DIR = "PORTKIT_VANILLA_BLOCKS"
_JAR = "https://piston-data.mojang.com/v1/objects/{sha1}/client.jar"

BLOCKS = "net/minecraft/world/level/block/Blocks"
_BLOCK = "net/minecraft/world/level/block/Block"
_RESOURCE_KEY = "net/minecraft/resources/ResourceKey"


@dataclass(frozen=True)
class BlockIdSet:
    id: str
    minecraft: str
    jar_sha1: str          # client.jar sha1 (Mojang version manifest)
    mojang_sha1: str       # client.txt sha1 (Mojang version manifest)
    sha256: str            # sha256 of the derived table

    @property
    def jar_url(self) -> str:
        return _JAR.format(sha1=self.jar_sha1)

    @property
    def mojang_url(self) -> str:
        return _MOJANG.format(sha1=self.mojang_sha1)

    @property
    def label(self) -> str:
        return f"vanilla Blocks field -> id, Minecraft {self.minecraft}: Mojang client.jar + client.txt"


# The game versions the pinned name mappings cover (mappings.SETS). sha256 of each
# derived table: `python -m portkit.data.vanilla_blocks --pin` prints them.
SETS: tuple[BlockIdSet, ...] = (
    BlockIdSet("vanilla-blocks-1.21.8", "1.21.8", "a19d9badbea944a4369fd0059e53bf7286597576",
               "bdeb624c3aefba11d9d40f34bc96176350b549b6",
               "6b87ee750b2c247b458ca3d2998c0e09e9d18478e949f950d7e2350ecc34fcfb"),
    BlockIdSet("vanilla-blocks-1.21.1", "1.21.1", "30c73b1c5da787909b2f73340419fdf13b9def88",
               "2244b6f072256667bcd9a73df124d6c58de77992",
               "ea685223dd387bc7fbd01fd3f6cc62c3dfa81d3ba371025791136ebb8fc07cf8"),
    BlockIdSet("vanilla-blocks-1.21", "1.21", "0e9a07b9bb3390602f977073aa12884a4ce12431",
               "0530a206839eb1e9b35ec86acbbe394b07a2d9fb",
               "45439151443a30a5ab2f9a40e0426b672d0fef0d169222daf3ca877e07a07b2f"),
    BlockIdSet("vanilla-blocks-1.20.1", "1.20.1", "0c3ec587af28e5a785c0b4a7b8a30f9a8f78f838",
               "6c48521eed01fe2e8ecdadbd5ae348415f3c47da",
               "a141be7e155a911062a3ad7dd4d1ea81d0477b8531ecf7139f42cb86411fea6f"),
    BlockIdSet("vanilla-blocks-1.20", "1.20", "e575a48efda46cf88111ba05b624ef90c520eef1",
               "a4cd9a97400f7ecfe4dba23e427549ebc5815d66",
               "e7de4e7dbdf18a774a45f41274c1ad401c72dfc248bf3c0e96a4534e39238c89"),
    BlockIdSet("vanilla-blocks-1.19.2", "1.19.2", "055b30d860ead928cba3849ba920c88b6950b654",
               "8e8c9be5dc27802caba47053d4fdea328f7f89bd",
               "3cbedd9e21e24110612f049bb5141a4662b62bed5c17e42b3b1947b789c53478"),
)


def select(minecraft: str | None) -> BlockIdSet | None:
    """The set for exactly the game version a mod declares, or None."""
    if not minecraft:
        return None
    if minecraft.endswith(".0"):  # "1.21.0" is 1.21
        minecraft = minecraft[:-2]
    for s in SETS:
        if s.minecraft == minecraft:
            return s
    return None


# --- deriving a table -------------------------------------------------------

def _desc_params(desc: str) -> list[str]:
    out, i = [], 1
    while desc[i] != ")":
        j = i
        while desc[j] == "[":
            j += 1
        if desc[j] == "L":
            j = desc.index(";", j)
        out.append(desc[i:j + 1])
        i = j + 1
    return out


def _segments(cf, owner: str):
    """(putstatic field, instructions since the previous putstatic of ``owner``) in order."""
    from .. import bytecode

    method = cf.method("<clinit>")
    if method is None or method.code is None:
        return
    seg = []
    for insn in bytecode.instructions(cf, method.code):
        if insn.name == "putstatic" and insn.arg.owner == owner:
            yield insn.arg.name, seg
            seg = []
        else:
            seg.append(insn)


def derive(mapping: BlockIdSet, jar: bytes, mojang: bytes) -> bytes:
    """client.jar + client.txt -> {"blocks": {Mojang field name: id}, "unmatched", "no_blockstate"}."""
    from .. import bytecode

    classes, _methods, fields = _parse_mojang(mojang.decode("utf-8"))
    obf_blocks, obf_block, obf_key = classes[BLOCKS], classes[_BLOCK], classes[_RESOURCE_KEY]
    names = {(owner, obf): name for owner, name, obf in fields}
    with zipfile.ZipFile(io.BytesIO(jar)) as zf:
        jar_names = set(zf.namelist())

        def parse(cls: str):
            return bytecode.parse(zf.read(cls + ".class"))

        blocks_cf = parse(obf_blocks)
        block_like = {obf_block}

        def is_block_desc(desc: str) -> bool:
            if not (desc.startswith("L") and desc.endswith(";")):
                return False
            cls, seen = desc[1:-1], set()
            while cls and cls not in seen:  # Block or a vanilla subclass of it
                if cls in block_like:
                    return True
                seen.add(cls)
                if cls + ".class" not in jar_names:
                    return False
                cls = parse(cls).super_name
            return False

        keys: dict[tuple[str, str], str | None] = {}

        def key_id(owner: str, field: str) -> str | None:
            """The id of a ResourceKey constant ``ldc id; invokestatic (String)ResourceKey; putstatic``."""
            if (owner, field) not in keys:
                found = None
                if owner + ".class" in jar_names:
                    for name, seg in _segments(parse(owner), owner):
                        if name == field and len(seg) == 2 and seg[0].name in ("ldc", "ldc_w") \
                                and isinstance(seg[0].arg, str) and seg[1].name == "invokestatic" \
                                and seg[1].arg.desc == f"(Ljava/lang/String;)L{obf_key};":
                            found = seg[0].arg
                keys[(owner, field)] = found
            return keys[(owner, field)]

        blocks: dict[str, str] = {}
        unmatched: list[str] = []
        for obf_field, seg in _segments(blocks_cf, obf_blocks):
            desc = blocks_cf.fields.get(obf_field, "")
            if not is_block_desc(desc):
                continue  # predicates and other non-block statics
            field = names.get((obf_blocks, obf_field), obf_field)
            first, last = (seg[0], seg[-1]) if seg else (None, None)
            ok = last is not None and last.name == "invokestatic" and last.arg.owner == obf_blocks
            params = _desc_params(last.arg.desc) if ok else []
            value = None
            if ok and params and params[0] == "Ljava/lang/String;" and first.name in ("ldc", "ldc_w") \
                    and isinstance(first.arg, str):
                value = first.arg
            elif ok and params and params[0] == f"L{obf_key};" and first.name == "getstatic":
                value = key_id(first.arg.owner, first.arg.name)
            if value is None or field in blocks:
                unmatched.append(field)
                continue
            blocks[field] = value
        no_blockstate = sorted(v for v in blocks.values()
                               if f"assets/minecraft/blockstates/{v}.json" not in jar_names)
    if len(set(blocks.values())) != len(blocks):
        raise ValueError("two Blocks fields read with the same id")
    out = {
        "set": mapping.id,
        "minecraft": mapping.minecraft,
        "label": mapping.label,
        "sources": [mapping.jar_url, mapping.mojang_url],
        "method": "net.minecraft.world.level.block.Blocks#<clinit>: each block field's putstatic "
                  "follows an invokestatic of a Blocks method whose first argument is the id "
                  "(a string constant, or a ResourceKey constant built from one); see "
                  "portkit.data.vanilla_blocks.derive",
        "notice": "Derived from Mojang's client jar and mappings ((c) Microsoft); fetched by "
                  "`portkit reference fetch`, never vendored.",
        "blocks": dict(sorted(blocks.items())),
        "unmatched": sorted(unmatched),
        "no_blockstate": no_blockstate,
    }
    return (json.dumps(out, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


# --- fetch and cache --------------------------------------------------------

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def set_path(mapping: BlockIdSet, cache: Path | None = None) -> Path:
    return Path(cache or cache_dir()) / f"{mapping.id}-{mapping.sha256[:12]}.json"


def cached(mapping: BlockIdSet, cache: Path | None = None) -> Path | None:
    """The verified cached table, or None when it is missing or doesn't match the pin."""
    path = set_path(mapping, cache)
    return path if path.is_file() and _sha256(path.read_bytes()) == mapping.sha256 else None


def _get(url: str, opener) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with opener(request, timeout=300) as response:
        return response.read()


def download(mapping: BlockIdSet, opener=urllib.request.urlopen) -> bytes:
    """The derived table from upstream; each input is checked against its sha1 pin."""
    try:
        jar = _get(mapping.jar_url, opener)
        mojang = _get(mapping.mojang_url, opener)
    except (OSError, ValueError, AttributeError) as exc:
        raise ReferenceDataError(f"{mapping.id}: download failed: {exc}") from exc
    if hashlib.sha1(jar).hexdigest() != mapping.jar_sha1:
        raise ReferenceDataError(f"{mapping.id}: sha1 mismatch for {mapping.jar_url}")
    if hashlib.sha1(mojang).hexdigest() != mapping.mojang_sha1:
        raise ReferenceDataError(f"{mapping.id}: sha1 mismatch for {mapping.mojang_url}")
    try:
        return derive(mapping, jar, mojang)
    except (ValueError, KeyError, IndexError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
        raise ReferenceDataError(f"{mapping.id}: can't derive the table: {exc}") from exc


def fetch(mapping: BlockIdSet, cache: Path | None = None,
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


@lru_cache(maxsize=4)
def _read(path: str, mtime_ns: int, size: int, expected: str | None) -> dict[str, str] | None:
    data = Path(path).read_bytes()
    if expected is not None and _sha256(data) != expected:
        return None
    try:
        blocks = json.loads(data).get("blocks")
    except (ValueError, AttributeError):
        return None
    if not isinstance(blocks, dict):
        return None
    return {k: v for k, v in blocks.items() if isinstance(k, str) and isinstance(v, str)}


def table(mapping: BlockIdSet) -> dict[str, str] | None:
    """Field name -> id for ``mapping``, or None when it isn't cached (run ``portkit reference fetch``)."""
    override = os.environ.get(_ENV_DIR)
    path = Path(override).expanduser() / f"{mapping.id}.json" if override else set_path(mapping)
    try:
        stat = path.stat()
    except OSError:
        return None
    return _read(str(path), stat.st_mtime_ns, stat.st_size, None if override else mapping.sha256)


def attach(classes, minecraft: str | None) -> None:
    """Give ``classes`` (a :class:`portkit.bytecode.ClassIndex`) the table of the
    game version its mod declares, when one is pinned and cached."""
    mapping = select(minecraft)
    if mapping is None or classes is None:
        return
    found = table(mapping)
    if found is not None:
        classes.vanilla_blocks = found


if __name__ == "__main__":  # pragma: no cover - maintenance helper
    if sys.argv[1:] == ["--pin"]:
        for s in SETS:
            data = download(s)
            digest = _sha256(data)
            t = json.loads(data)
            print(f"{s.id} {digest} {'ok' if digest == s.sha256 else 'CHANGED'} "
                  f"blocks={len(t['blocks'])} unmatched={len(t['unmatched'])} "
                  f"no_blockstate={len(t['no_blockstate'])}")
        sys.exit(0)
    print(f"usage: python -m portkit.data.vanilla_blocks --pin   (fetch with `{FETCH_COMMAND}`)")
    sys.exit(2)
