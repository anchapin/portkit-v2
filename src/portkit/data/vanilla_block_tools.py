"""Which vanilla blocks need the correct tool for drops, read from Mojang's client jar (#280).

Java rolls a block's loot table only when the player breaking it may harvest it:
``ServerPlayerGameMode#destroyBlock`` calls ``Block#playerDestroy`` (which drops the
loot) only when ``Player#hasCorrectToolForDrops(state)`` holds (NeoForge routes it
through ``IBlockStateExtension#canHarvestBlock`` and ``EventHooks#doPlayerHarvestCheck``,
which start from the same check). That check is
``!state.requiresCorrectToolForDrops() || mainHand.isCorrectToolForDrops(state)``: a
block whose ``BlockBehaviour.Properties`` called ``requiresCorrectToolForDrops()``
(stone, ores, obsidian, cobweb...) gives nothing, its loot modifiers included, to a
wrong tool or a bare hand. Glass and the stained glasses don't (minecraft.wiki/w/Glass,
minecraft.wiki/w/Stained_Glass: "Tool: Any tool"), and this reading agrees.

Where it comes from, per game version (:data:`SETS`, the same pinned client.jar and
client.txt as :mod:`portkit.data.vanilla_blocks`, whose ``Blocks`` field -> id table
names each block):

* the flag field: ``BlockBehaviour$Properties.requiresCorrectToolForDrops`` (named from
  client.txt). Each ``Properties`` method is classified from its own bytecode, not
  from its name: it **sets** the flag (``iconst_1; putfield flag``, i.e.
  ``requiresCorrectToolForDrops()``), **copies** it (``getfield flag; putfield flag``,
  ``ofLegacyCopy``/``ofFullCopy``/1.20's ``copy``), touches it some other way
  (unread), or leaves it alone; a method that calls another ``Properties`` method
  takes that one's class.
* each block field's registration in ``Blocks#<clinit>`` (the instructions between
  two ``putstatic`` of a ``Blocks`` field, as :func:`vanilla_blocks.derive` reads
  them): the flag is set when a method that sets it is called there, or a copy is
  taken of a block already read as needing a tool (``getstatic Blocks.X`` right
  before the copy). A ``Blocks`` helper called there (``stainedGlass(DyeColor)``,
  ``leaves(..)``) is read the same way through its own body.

A block is left **unread** (listed under ``unread``, never guessed, #87) when a copy's
source isn't a block field read before it (``legacyStair(Block)`` copies its
parameter), a ``Properties`` method touches the flag another way, a ``Properties``
value comes from anywhere but ``Properties``/``Blocks`` methods, or a ``Blocks``
helper is unread. Callers treat unread as "may need a tool".

Like the Blocks table it carries Mojang's names, so it is never vendored:
``portkit reference fetch`` downloads both inputs (sha1-pinned), derives the table,
checks its sha256 and caches it. ``PORTKIT_VANILLA_BLOCK_TOOLS`` names a directory of
derived tables (``<set id>.json``) to use instead, unverified (the tests' way).

``python -m portkit.data.vanilla_block_tools --pin`` downloads every set and prints the sha256s.
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

_ENV_DIR = "PORTKIT_VANILLA_BLOCK_TOOLS"
PROPERTIES = "net/minecraft/world/level/block/state/BlockBehaviour$Properties"
FLAG = "requiresCorrectToolForDrops"


@dataclass(frozen=True)
class ToolSet:
    id: str
    blocks: BlockIdSet     # the Blocks field -> id set read from the same jar
    sha256: str            # sha256 of the derived table

    @property
    def minecraft(self) -> str:
        return self.blocks.minecraft

    @property
    def label(self) -> str:
        return (f"vanilla Properties#requiresCorrectToolForDrops, Minecraft {self.minecraft}: "
                "Mojang client.jar + client.txt")


def _set(version: str, sha256: str) -> ToolSet:
    blocks = vanilla_blocks.select(version)
    assert blocks is not None and blocks.minecraft == version
    return ToolSet(f"vanilla-block-tools-{version}", blocks, sha256)


# One per vanilla Blocks set. sha256 of each derived table:
# `python -m portkit.data.vanilla_block_tools --pin` prints them.
SETS: tuple[ToolSet, ...] = (
    _set("1.21.8", "cd19e8b673006249ca2f201cf2155c72e6213f79d7e5c2b987def259489fdcf3"),
    _set("1.21.1", "c363d2d071f762187acb1280649a85655125b27eac5c90f372ded82c5df7c4d6"),
    _set("1.21", "60f292d131cd9bd41215ce01fb7fd3883215ceed856e202a51c6c84958cacb27"),
    _set("1.20.1", "2d3939efb2bd05094fc2392fa460293187e670e5458783f7f6165b940b58794b"),
    _set("1.20", "c414595d40d73b9f905130ab3ce8527db045048114b23f1a6b6fffd59dfa63f4"),
    _set("1.19.2", "c47c71b0b8f03fe8f74c85a33ba1b7eae9be2da3b2872fee2b5230bd877c5730"),
)


def select(minecraft: str | None) -> ToolSet | None:
    """The set for exactly the game version a mod declares, or None."""
    blocks = vanilla_blocks.select(minecraft)
    if blocks is None:
        return None
    for s in SETS:
        if s.blocks == blocks:
            return s
    return None


# --- deriving a table -------------------------------------------------------

_SETS, _COPIES, _NONE, _UNREAD = "sets", "copies", "none", "unread"


def derive(mapping: ToolSet, jar: bytes, mojang: bytes) -> bytes:
    """client.jar + client.txt -> {"requires_correct_tool": {id: bool}, "unread": [ids]}."""
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

    kinds: dict[tuple[str, str], str] = {}

    def kind(name: str, desc: str, stack: tuple = ()) -> str:
        """What a Properties method does to the flag, from its own bytecode."""
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
        seen = set()
        for i, insn in enumerate(insns):
            if insn.name == "putfield" and insn.arg.owner == obf_props and insn.arg.name == flag:
                before = insns[i - 1] if i else None
                if before is not None and before.name == "iconst_1":
                    seen.add(_SETS)
                elif before is not None and before.name == "getfield" and before.arg.name == flag \
                        and before.arg.owner == obf_props:
                    seen.add(_COPIES)
                else:
                    seen.add(_UNREAD)
            elif insn.name.startswith("invoke") and insn.name != "invokedynamic" and insn.arg.owner == obf_props:
                seen.add(kind(insn.arg.name, insn.arg.desc, stack + (key,)))
        seen.discard(_NONE)
        got = _UNREAD if _UNREAD in seen or len(seen) > 1 else (seen.pop() if seen else _NONE)
        kinds[key] = got
        return got

    helpers: dict[tuple[str, str], bool | None] = {}
    known: dict[str, bool | None] = {}  # obf Blocks field -> flag, as read so far

    def walk(insns, stack: tuple) -> bool | None:
        needs = False
        for i, insn in enumerate(insns):
            if insn.name == "getstatic" and insn.arg.desc == props_desc:
                return None
            if not insn.name.startswith("invoke") or insn.name == "invokedynamic":
                continue
            owner = insn.arg.owner
            if owner == obf_props:
                k = kind(insn.arg.name, insn.arg.desc)
                if k == _UNREAD:
                    return None
                if k == _SETS:
                    needs = True
                elif k == _COPIES:
                    before = insns[i - 1] if i else None
                    if before is None or before.name != "getstatic" or before.arg.owner != obf_blocks:
                        return None
                    source = known.get(before.arg.name)
                    if source is None:
                        return None
                    needs = needs or source
            elif owner == obf_blocks:
                got = helper(insn.arg.name, insn.arg.desc, stack)
                if got is None:
                    return None
                needs = needs or got
            elif insn.arg.desc.endswith(props_desc):
                return None  # a Properties value from somewhere this reader doesn't follow
        return needs

    def helper(name: str, desc: str, stack: tuple) -> bool | None:
        key = (name, desc)
        if key in helpers:
            return helpers[key]
        if key in stack or name == "<clinit>":
            return None
        method = blocks_cf.method(name, desc)
        if method is None or method.code is None:
            return None
        got = walk(bytecode.instructions(blocks_cf, method.code), stack + (key,))
        helpers[key] = got
        return got

    needs_tool: dict[str, bool] = {}
    unread: list[str] = []
    for obf_field, seg in _segments(blocks_cf, obf_blocks):
        field = names.get((obf_blocks, obf_field), obf_field)
        if field not in ids:
            continue  # not a block field the Blocks table reads
        got = walk(seg, ())
        known[obf_field] = got
        if got is None:
            unread.append(ids[field])
        else:
            needs_tool[ids[field]] = got
    if not needs_tool:
        raise ValueError("no block's flag was read")
    out = {
        "set": mapping.id,
        "minecraft": mapping.minecraft,
        "label": mapping.label,
        "sources": [mapping.blocks.jar_url, mapping.blocks.mojang_url],
        "method": "net.minecraft.world.level.block.Blocks#<clinit>: per block field, whether its "
                  "BlockBehaviour$Properties called a Properties method that sets "
                  "requiresCorrectToolForDrops (classified from the method's bytecode) or copied a "
                  "block read as needing one; see portkit.data.vanilla_block_tools.derive",
        "notice": "Derived from Mojang's client jar and mappings ((c) Microsoft); fetched by "
                  "`portkit reference fetch`, never vendored.",
        "requires_correct_tool": dict(sorted(needs_tool.items())),
        "unread": sorted(unread),
    }
    return (json.dumps(out, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


# --- fetch and cache --------------------------------------------------------

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def set_path(mapping: ToolSet, cache: Path | None = None) -> Path:
    return Path(cache or cache_dir()) / f"{mapping.id}-{mapping.sha256[:12]}.json"


def cached(mapping: ToolSet, cache: Path | None = None) -> Path | None:
    """The verified cached table, or None when it is missing or doesn't match the pin."""
    path = set_path(mapping, cache)
    return path if path.is_file() and _sha256(path.read_bytes()) == mapping.sha256 else None


def download(mapping: ToolSet, opener=urllib.request.urlopen) -> bytes:
    """The derived table from upstream; each input is checked against its sha1 pin."""
    jar, mojang = vanilla_blocks.inputs(mapping.blocks, opener, keep=True)
    vanilla_blocks._last_inputs.clear()
    try:
        return derive(mapping, jar, mojang)
    except (ValueError, KeyError, IndexError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
        raise ReferenceDataError(f"{mapping.id}: can't derive the table: {exc}") from exc


def fetch(mapping: ToolSet, cache: Path | None = None,
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
    flags = body.get("requires_correct_tool") if isinstance(body, dict) else None
    if not isinstance(flags, dict):
        return None
    return {k: v for k, v in flags.items() if isinstance(k, str) and isinstance(v, bool)}


def table(mapping: ToolSet) -> dict[str, bool] | None:
    """Block id (no namespace) -> needs the correct tool, for ``mapping``; None when it
    isn't cached (run ``portkit reference fetch``)."""
    override = os.environ.get(_ENV_DIR)
    path = Path(override).expanduser() / f"{mapping.id}.json" if override else set_path(mapping)
    try:
        stat = path.stat()
    except OSError:
        return None
    return _read(str(path), stat.st_mtime_ns, stat.st_size, None if override else mapping.sha256)


def needs_correct_tool(minecraft: str | None, java_block: str) -> tuple[bool | None, str]:
    """Whether vanilla ``java_block`` (``minecraft:<name>``) needs the correct tool for
    drops in the game version ``minecraft``, or (None, why it can't be read)."""
    mapping = select(minecraft)
    if mapping is None:
        return None, (f"no vanilla block table is pinned for Minecraft {minecraft}" if minecraft
                      else "the mod declares no Minecraft version")
    flags = table(mapping)
    if flags is None:
        return None, f"{mapping.id} isn't cached (run `{FETCH_COMMAND}`)"
    namespace, _, name = java_block.partition(":")
    if namespace != "minecraft" or name not in flags:
        return None, (f"{java_block}'s registration in Minecraft {mapping.minecraft}'s Blocks "
                      "isn't read (see portkit.data.vanilla_block_tools)")
    return flags[name], ""


if __name__ == "__main__":  # pragma: no cover - maintenance helper
    if sys.argv[1:] == ["--pin"]:
        for s in SETS:
            data = download(s)
            digest = _sha256(data)
            t = json.loads(data)
            needs = sum(t["requires_correct_tool"].values())
            print(f"{s.id} {digest} {'ok' if digest == s.sha256 else 'CHANGED'} "
                  f"read={len(t['requires_correct_tool'])} needs_tool={needs} unread={len(t['unread'])}")
        sys.exit(0)
    print(f"usage: python -m portkit.data.vanilla_block_tools --pin   (fetch with `{FETCH_COMMAND}`)")
    sys.exit(2)
