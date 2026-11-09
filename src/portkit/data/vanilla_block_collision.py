"""Whether each vanilla block's Properties collide, read from Mojang's client jar (#296).

A mod block built on a copy of a vanilla block's Properties
(``Properties.ofFullCopy(Blocks.WHEAT)``) takes that block's ``hasCollision`` with
the copy: ``ofLegacyCopy`` copies the field, and ``ofFullCopy`` (1.20's ``copy``)
copies through it. ``BlockBehaviour#getCollisionShape`` gives ``Shapes.empty()`` when
``hasCollision`` is false and the block's shape when it is true, so a mod block that
doesn't override it collides exactly when the copied Properties do (unless the mod
then calls ``noCollission``). Without this table such a block's collision stays a
labelled DEFAULT.

Where it comes from, per game version (:data:`SETS`, the same pinned client.jar and
client.txt as :mod:`portkit.data.vanilla_blocks`, whose ``Blocks`` field -> id table
names each block):

* the flag field: ``BlockBehaviour$Properties.hasCollision`` (named from client.txt).
  Each ``Properties`` method is classified from its own bytecode, not from its name,
  by what it leaves in the flag, in instruction order: it **sets** it
  (``iconst_1; putfield flag``: the constructor's ``hasCollision = true``), **clears**
  it (``iconst_0; putfield flag``: ``noCollission()``), **copies** it (``getfield
  flag; putfield flag``: ``ofLegacyCopy``, and ``ofFullCopy`` through it), touches it
  some other way (unread), or leaves it alone; a method that calls another
  ``Properties`` method takes that one's effect at that point. A method with a branch
  that touches the flag is unread (which way it went isn't followed).
* each block field's registration in ``Blocks#<clinit>`` (the instructions between
  two ``putstatic`` of a ``Blocks`` field, as :func:`vanilla_blocks.derive` reads
  them), in order: ``Properties.of()`` sets the flag, ``noCollission()`` clears it, a
  copy takes the value of the block it copies (``getstatic Blocks.X`` right before
  the copy, a block already read). A ``Blocks`` helper called there
  (``leaves(..)``, ``flowerPot(..)``) is read the same way through its own body.

A block is left **unread** (listed under ``unread``, never guessed, #87) when a copy's
source isn't a block field read before it (``legacyStair(Block)`` copies its
parameter), a ``Properties`` method touches the flag another way, a ``Properties``
value comes from anywhere but ``Properties``/``Blocks`` methods, a ``Blocks`` helper
is unread, or no ``Properties`` is made there at all.

This reads only the Properties: a vanilla block class's own ``getCollisionShape``
override isn't copied with them and isn't part of the table.

Like the Blocks table it carries Mojang's names, so it is never vendored:
``portkit reference fetch`` downloads both inputs (sha1-pinned), derives the table,
checks its sha256 and caches it. ``PORTKIT_VANILLA_BLOCK_COLLISION`` names a
directory of derived tables (``<set id>.json``) to use instead, unverified (the
tests' way).

``python -m portkit.data.vanilla_block_collision --pin`` downloads every set and
prints the sha256s.
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

from . import FETCH_COMMAND, ReferenceDataError, cache_dir
from . import vanilla_blocks
from .mappings import _parse_mojang
from .vanilla_blocks import BLOCKS, BlockIdSet, _segments

_ENV_DIR = "PORTKIT_VANILLA_BLOCK_COLLISION"
PROPERTIES = "net/minecraft/world/level/block/state/BlockBehaviour$Properties"
FLAG = "hasCollision"


@dataclass(frozen=True)
class CollisionSet:
    id: str
    blocks: BlockIdSet     # the Blocks field -> id set read from the same jar
    sha256: str            # sha256 of the derived table

    @property
    def minecraft(self) -> str:
        return self.blocks.minecraft

    @property
    def label(self) -> str:
        return (f"vanilla Properties#hasCollision, Minecraft {self.minecraft}: "
                "Mojang client.jar + client.txt")


def _set(version: str, sha256: str) -> CollisionSet:
    blocks = vanilla_blocks.select(version)
    assert blocks is not None and blocks.minecraft == version
    return CollisionSet(f"vanilla-block-collision-{version}", blocks, sha256)


# One per vanilla Blocks set. sha256 of each derived table:
# `python -m portkit.data.vanilla_block_collision --pin` prints them.
SETS: tuple[CollisionSet, ...] = (
    _set("1.21.8", "7c26190952edbf9c11fc38e1372db0809b99d4d810fc7e1d33bde4ceb1d155dd"),
    _set("1.21.1", "9a9d633897950553c72ec7579f6a98aa91c25037275bb31b119c6965050777e8"),
    _set("1.21", "d1d6606710511f42677adcf2d1698928d8c203c55f6437d463d36f96c73ecc38"),
    _set("1.20.1", "c40bd8ad3dc40d7fb4e9876b8980b7f9331dccd88c7dc833c328168de893f73e"),
    _set("1.20", "d087cbdd3555429657a07501737de5099dbb2b50f2d40b5eee76df99b4466551"),
    _set("1.19.2", "3ab37de62e190701539b4d47a09d58b9b71b99d909aa7fe2d0067295a7c6338a"),
)


def select(minecraft: str | None) -> CollisionSet | None:
    """The set for exactly the game version a mod declares, or None."""
    blocks = vanilla_blocks.select(minecraft)
    if blocks is None:
        return None
    for s in SETS:
        if s.blocks == blocks:
            return s
    return None


# --- deriving a table -------------------------------------------------------

# A method's effect on the flag: True (sets it), False (clears it), _COPIES, _NONE
# (leaves it alone) or _UNREAD.
_COPIES, _NONE, _UNREAD = "copies", "none", "unread"
_BRANCHES = frozenset({
    "ifeq", "ifne", "iflt", "ifge", "ifgt", "ifle", "if_icmpeq", "if_icmpne", "if_icmplt",
    "if_icmpge", "if_icmpgt", "if_icmple", "if_acmpeq", "if_acmpne", "ifnull", "ifnonnull",
    "goto", "goto_w", "tableswitch", "lookupswitch", "jsr", "jsr_w"})


def derive(mapping: CollisionSet, jar: bytes, mojang: bytes) -> bytes:
    """client.jar + client.txt -> {"has_collision": {id: bool}, "unread": [ids]}."""
    from .. import bytecode

    ids = json.loads(vanilla_blocks.derive(mapping.blocks, jar, mojang))["blocks"]
    classes, _methods, fields = _parse_mojang(mojang.decode("utf-8"))
    obf_props, obf_blocks = classes[PROPERTIES], classes[BLOCKS]
    flag = [obf for owner, name, obf in fields if owner == obf_props and name == FLAG]
    if len(flag) != 1:
        raise ValueError(f"{PROPERTIES}.{FLAG} isn't one field in client.txt")
    flag = flag[0]
    props_desc = f"L{obf_props};"
    names = {(owner, obf): name for owner, name, obf in fields}
    with zipfile.ZipFile(io.BytesIO(jar)) as zf:
        props_cf = bytecode.parse(zf.read(obf_props + ".class"))
        blocks_cf = bytecode.parse(zf.read(obf_blocks + ".class"))

    kinds: dict[tuple[str, str], object] = {}

    def kind(name: str, desc: str, stack: tuple = ()) -> object:
        """What a Properties method leaves in the flag, from its own bytecode."""
        key = (name, desc)
        if key in kinds:
            return kinds[key]
        if key in stack:
            return _UNREAD
        method = props_cf.method(name, desc)
        if method is None or method.code is None:
            kinds[key] = _UNREAD
            return _UNREAD
        insns = bytecode.instructions(props_cf, method.code)
        got: object = _NONE
        for i, insn in enumerate(insns):
            step: object = _NONE
            if insn.name == "putfield" and insn.arg.owner == obf_props and insn.arg.name == flag:
                before = insns[i - 1] if i else None
                if before is not None and before.name in ("iconst_0", "iconst_1"):
                    step = before.name == "iconst_1"
                elif before is not None and before.name == "getfield" and before.arg.name == flag \
                        and before.arg.owner == obf_props:
                    step = _COPIES
                else:
                    step = _UNREAD
            elif insn.name.startswith("invoke") and insn.name != "invokedynamic" and insn.arg.owner == obf_props:
                step = kind(insn.arg.name, insn.arg.desc, stack + (key,))
            if step == _UNREAD:
                got = _UNREAD
                break
            if step is not _NONE:
                got = step
        if got is not _NONE and got != _UNREAD and any(x.name in _BRANCHES for x in insns):
            got = _UNREAD  # which way a branch went isn't followed
        kinds[key] = got
        return got

    helpers: dict[tuple[str, str], object] = {}
    known: dict[str, bool | None] = {}  # obf Blocks field -> flag, as read so far

    def walk(insns, stack: tuple) -> object:
        """The flag's value after these instructions: True, False, _NONE (no
        Properties made or changed here) or _UNREAD."""
        value: object = _NONE
        for i, insn in enumerate(insns):
            if insn.name == "getstatic" and insn.arg.desc == props_desc:
                return _UNREAD
            if not insn.name.startswith("invoke") or insn.name == "invokedynamic":
                continue
            owner = insn.arg.owner
            if owner == obf_props:
                k = kind(insn.arg.name, insn.arg.desc)
                if k == _UNREAD:
                    return _UNREAD
                if k == _COPIES:
                    before = insns[i - 1] if i else None
                    if before is None or before.name != "getstatic" or before.arg.owner != obf_blocks:
                        return _UNREAD
                    source = known.get(before.arg.name)
                    if source is None:
                        return _UNREAD
                    value = source
                elif k is not _NONE:
                    value = k
            elif owner == obf_blocks:
                got = helper(insn.arg.name, insn.arg.desc, stack)
                if got == _UNREAD:
                    return _UNREAD
                if got is not _NONE:
                    value = got
            elif insn.arg.desc.endswith(props_desc):
                return _UNREAD  # a Properties value from somewhere this reader doesn't follow
        return value

    def helper(name: str, desc: str, stack: tuple) -> object:
        key = (name, desc)
        if key in helpers:
            return helpers[key]
        if key in stack or name == "<clinit>":
            return _UNREAD
        method = blocks_cf.method(name, desc)
        if method is None or method.code is None:
            return _UNREAD
        insns = bytecode.instructions(blocks_cf, method.code)
        got = walk(insns, stack + (key,))
        if got is not _NONE and got != _UNREAD and any(x.name in _BRANCHES for x in insns):
            got = _UNREAD  # which way a branch went isn't followed
        helpers[key] = got
        return got

    collides: dict[str, bool] = {}
    unread: list[str] = []
    for obf_field, seg in _segments(blocks_cf, obf_blocks):
        field = names.get((obf_blocks, obf_field), obf_field)
        if field not in ids:
            continue  # not a block field the Blocks table reads
        got = walk(seg, ())
        if isinstance(got, bool):
            known[obf_field] = got
            collides[ids[field]] = got
        else:
            known[obf_field] = None
            unread.append(ids[field])
    if not collides:
        raise ValueError("no block's flag was read")
    out = {
        "set": mapping.id,
        "minecraft": mapping.minecraft,
        "label": mapping.label,
        "sources": [mapping.blocks.jar_url, mapping.blocks.mojang_url],
        "method": "net.minecraft.world.level.block.Blocks#<clinit>: per block field, the value its "
                  "BlockBehaviour$Properties#hasCollision is left with, in order (Properties methods "
                  "classified from their bytecode: set, cleared by noCollission, or copied from a "
                  "block read before); see portkit.data.vanilla_block_collision.derive",
        "notice": "Derived from Mojang's client jar and mappings ((c) Microsoft); fetched by "
                  "`portkit reference fetch`, never vendored.",
        "has_collision": dict(sorted(collides.items())),
        "unread": sorted(unread),
    }
    return (json.dumps(out, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


# --- fetch and cache --------------------------------------------------------

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def set_path(mapping: CollisionSet, cache: Path | None = None) -> Path:
    return Path(cache or cache_dir()) / f"{mapping.id}-{mapping.sha256[:12]}.json"


def cached(mapping: CollisionSet, cache: Path | None = None) -> Path | None:
    """The verified cached table, or None when it is missing or doesn't match the pin."""
    path = set_path(mapping, cache)
    return path if path.is_file() and _sha256(path.read_bytes()) == mapping.sha256 else None


def download(mapping: CollisionSet, opener=urllib.request.urlopen) -> bytes:
    """The derived table from upstream; each input is checked against its sha1 pin."""
    jar, mojang = vanilla_blocks.inputs(mapping.blocks, opener, keep=True)
    try:
        return derive(mapping, jar, mojang)
    except (ValueError, KeyError, IndexError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
        raise ReferenceDataError(f"{mapping.id}: can't derive the table: {exc}") from exc


def fetch(mapping: CollisionSet, cache: Path | None = None,
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
def _read(path: str, mtime_ns: int, size: int, expected: str | None) -> dict | None:
    data = Path(path).read_bytes()
    if expected is not None and _sha256(data) != expected:
        return None
    try:
        body = json.loads(data)
    except ValueError:
        return None
    flags = body.get("has_collision") if isinstance(body, dict) else None
    if not isinstance(flags, dict):
        return None
    return {k: v for k, v in flags.items() if isinstance(k, str) and isinstance(v, bool)}


def table(mapping: CollisionSet) -> dict[str, bool] | None:
    """Block id (no namespace) -> its Properties collide, for ``mapping``; None when
    it isn't cached (run ``portkit reference fetch``)."""
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
        classes.vanilla_collision = found


if __name__ == "__main__":  # pragma: no cover - maintenance helper
    if sys.argv[1:2] == ["--pin"]:
        only = sys.argv[2:]
        for s in SETS:
            if only and s.minecraft not in only:
                continue
            data = download(s)
            vanilla_blocks._last_inputs.clear()
            digest = _sha256(data)
            t = json.loads(data)
            off = sum(not v for v in t["has_collision"].values())
            print(f"{s.id} {digest} {'ok' if digest == s.sha256 else 'CHANGED'} "
                  f"read={len(t['has_collision'])} no_collision={off} unread={len(t['unread'])}")
        sys.exit(0)
    print(f"usage: python -m portkit.data.vanilla_block_collision --pin [version ...]   "
          f"(fetch with `{FETCH_COMMAND}`)")
    sys.exit(2)
