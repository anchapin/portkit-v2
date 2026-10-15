"""Forge SRG and Fabric intermediary name mappings for the bytecode readers (#235).

The readers' fixtures (tests/data/blockcode, tests/data/entitycode) are javac
output with Mojang names. Here they are renamed the way a Forge 1.20.1 build
(SRG member names) and a Fabric build (intermediary class and member names)
of the same code would be, by rewriting the class files' UTF8 constants, and
the readers must give the same facts on the renamed build, read through a
remapper, as on the Mojang-named one. Without the remapper the renamed build
reads nothing.

The tables themselves are derived from Mojang's client.txt and MCPConfig's
joined.tsrg / FabricMC's intermediary .tiny; ``derive`` is checked here on
small hand-written inputs in those formats.
"""
from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import re
import struct
import zipfile
from pathlib import Path

import pytest

from portkit import blockcode, entities
from portkit.bytecode import ClassIndex, Ref, instructions, parse
from portkit.data import ReferenceDataError, mappings

DATA = Path(__file__).parent / "data"
BLOCKS = DATA / "blockcode" / "classes"
MOBS = DATA / "entitycode" / "classes"


# --- renaming a class file the way SRG / intermediary builds do ---------------

def _rewrite_utf8(data: bytes, fn) -> bytes:
    """``data`` with every CONSTANT_Utf8 replaced by ``fn(text)``; the rest of
    the file only refers to the pool by index, so it is copied as is."""
    out = bytearray(data[:10])
    (count,) = struct.unpack_from(">H", data, 8)
    pos, i = 10, 1
    sizes = {3: 4, 4: 4, 5: 8, 6: 8, 7: 2, 8: 2, 16: 2, 19: 2, 20: 2,
             9: 4, 10: 4, 11: 4, 12: 4, 17: 4, 18: 4, 15: 3}
    while i < count:
        tag = data[pos]
        if tag == 1:
            (n,) = struct.unpack_from(">H", data, pos + 1)
            text = data[pos + 3:pos + 3 + n].decode("utf-8")
            new = fn(text).encode("utf-8")
            out += bytes([1]) + struct.pack(">H", len(new)) + new
            pos += 3 + n
        else:
            size = sizes[tag]
            out += data[pos:pos + 1 + size]
            pos += 1 + size
            if tag in (5, 6):
                i += 1
        i += 1
    out += data[pos:]
    return bytes(out)


def _load(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix()[:-6]: p.read_bytes() for p in root.rglob("*.class")}


def _names(raw: dict[str, bytes]) -> tuple[set[str], set[str], set[str]]:
    """(Minecraft member names referenced or overridden, net/minecraft class
    names, every String constant) across ``raw``."""
    members, classes, strings = set(), set(), set()
    for data in raw.values():
        cf = parse(data)
        for entry in cf.pool:
            if entry is not None and entry[0] == 8:
                strings.add(cf.pool[entry[1]][1])
        for k, entry in enumerate(cf.pool):
            if entry is None:
                continue
            value = cf.constant(k) if entry[0] in (9, 10, 11) else None
            if isinstance(value, Ref) and value.owner.startswith("net/minecraft/"):
                if not value.name.startswith("<"):
                    members.add(value.name)
        for m in cf.methods:
            if not m.name.startswith(("<", "lambda$")):
                members.add(m.name)
        for entry in cf.pool:
            if entry is not None and entry[0] == 1:
                classes.update(re.findall(r"net/minecraft/[\w/$]+", entry[1]))
    return members - strings, classes, strings


class _Scheme:
    """A fake SRG or intermediary renaming: forward for building the renamed
    jar, ``table`` (renamed -> Mojang) for the remapper."""

    def __init__(self, raw: dict[str, bytes], scheme: str):
        members, classes, _strings = _names(raw)
        self.members = {n: (f"m_{1000 + k}_" if scheme == "srg" else f"method_{1000 + k}")
                        for k, n in enumerate(sorted(members))}
        self.classes: dict[str, str] = {}
        if scheme == "intermediary":
            outer: dict[str, str] = {}
            for k, name in enumerate(sorted(classes)):
                head, *inner = name.split("$")
                outer.setdefault(head, f"net/minecraft/class_{5000 + len(outer)}")
                self.classes[name] = "$".join([outer[head], *(f"class_{7000 + 10 * k + j}"
                                                              for j, _ in enumerate(inner))])
            for head, renamed in outer.items():
                self.classes.setdefault(head, renamed)

    def rename(self, text: str) -> str:
        if text in self.members:
            return self.members[text]
        if self.classes and "net/minecraft/" in text:
            return re.sub(r"net/minecraft/[\w/$]+", lambda m: self.classes.get(m.group(0), m.group(0)), text)
        return text

    def remapper(self) -> mappings.Remapper:
        return mappings.Remapper("test", {v: k for k, v in self.classes.items()},
                                 {v: k for k, v in self.members.items()})


def _index(raw: dict[str, bytes], scheme: _Scheme | None, remap: bool) -> ClassIndex:
    if scheme is None:
        return ClassIndex(dict(raw))
    index = ClassIndex({k: _rewrite_utf8(v, scheme.rename) for k, v in raw.items()})
    if remap:
        index.set_remapper(scheme.remapper())
    return index


def _plain(readings: dict) -> dict:
    return {k: dataclasses.asdict(v) for k, v in readings.items()}


BLOCK_NAMES = ["lamp", "statue", "vase", "odd", "fan", "ghost", "crate", "box", "toaster", "oven",
               "smoker", "vault", "hamper", "chesty", "bin", "glow", "night_lamp", "toggle", "copy",
               "copy_set", "world_lit", "too_bright", "plain", "renamed", "discarded", "door",
               "shared_lit", "shared_plain"]
BOOLS = {"toggle_lamp": ("lit",), "flip_box": ("open",), "item_flip": ("open",),
         "powered_lamp": ("on", "powered"), "gate_block": ("open",)}


def _block_facts(index: ClassIndex) -> dict:
    return {
        "blocks": _plain(blockcode.read_blocks(index, BLOCK_NAMES)),
        "light": _plain(blockcode.read_light(index, BLOCK_NAMES, {"toggle": {"lit"}})),
        "states": _plain(blockcode.read_state_blocks(index, BOOLS)),
        "containers": _plain(blockcode.read_containers(index, BLOCK_NAMES)),
    }


@pytest.fixture(scope="module")
def block_raw():
    return _load(BLOCKS)


@pytest.fixture(scope="module")
def mojang_facts(block_raw):
    return _block_facts(_index(block_raw, None, False))


@pytest.mark.parametrize("scheme", ["srg", "intermediary"])
def test_renamed_build_reads_the_same_facts_through_the_remapper(block_raw, mojang_facts, scheme):
    renaming = _Scheme(block_raw, scheme)
    assert renaming.members  # the fixture really is renamed
    renamed = _index(block_raw, renaming, False)
    # Sanity: the renamed build no longer spells getStateForPlacement.
    lamp = renamed.get("com/example/deco/LampBlock")
    assert lamp.method("getStateForPlacement") is None
    assert _block_facts(_index(block_raw, renaming, True)) == mojang_facts
    # The facts are real ones: placements, boxes, lights and slots were read.
    assert mojang_facts["blocks"]["lamp"]["placement"] is not None
    assert any(r["slots"] for r in mojang_facts["containers"].values())
    assert any(r["value"] for r in mojang_facts["light"].values())


@pytest.mark.parametrize("scheme", ["srg", "intermediary"])
def test_renamed_build_without_the_remapper_reads_nothing(block_raw, scheme):
    facts = _block_facts(_index(block_raw, _Scheme(block_raw, scheme), False))
    assert all(r["placement"] is None for r in facts["blocks"].values())
    assert all(r["slots"] is None for r in facts["containers"].values())


@pytest.mark.parametrize("scheme", ["srg", "intermediary"])
def test_entity_reader_through_the_remapper(scheme):
    raw = _load(MOBS)
    want = entities.read(ClassIndex(dict(raw)))
    got = entities.read(_index(raw, _Scheme(raw, scheme), True))
    assert got == want
    assert want.entities and want.eggs


def test_a_mojang_named_class_parses_identically_through_a_remapper(block_raw):
    # A real table's remapper only touches renamed-looking names, so a jar
    # that holds Mojang names already reads exactly as without it.
    remapper = mappings.Remapper("t", {"net/minecraft/class_1": "net/minecraft/X"},
                                 {"m_1_": "foo", "method_1": "bar", "field_2": "baz"})
    for name, data in block_raw.items():
        a, b = parse(data), parse(data, remapper)
        assert (a.name, a.super_name, a.interfaces, a.fields) == (b.name, b.super_name, b.interfaces, b.fields)
        assert [(m.name, m.desc) for m in a.methods] == [(m.name, m.desc) for m in b.methods]
        for m in a.methods:
            if m.code:
                assert instructions(a, m.code) == instructions(b, m.code)


def test_strings_keep_their_text_when_a_name_shares_their_constant():
    # A String constant spelling a renamed name shares its UTF8 entry with a
    # method reference of that name: the reference is renamed, the string isn't.
    raw = _load(BLOCKS)
    name, data = next((n, d) for n, d in sorted(raw.items())
                      if any(e is not None and e[0] == 8 for e in parse(d).pool))
    cf = parse(data)
    text = next(cf.pool[e[1]][1] for e in cf.pool if e is not None and e[0] == 8)
    called = next(cf.constant(k).name for k, e in enumerate(cf.pool)
                  if e is not None and e[0] == 10 and not cf.constant(k).name.startswith("<"))
    hacked = _rewrite_utf8(data, lambda t: "m_5_" if t in (text, called) else t)
    got = parse(hacked, mappings.Remapper("t", {}, {"m_5_": called}))
    strings = [got.pool[e[1]][1] for e in got.pool if e is not None and e[0] == 8]
    assert "m_5_" in strings and text not in strings
    refs = {got.constant(k).name for k, e in enumerate(got.pool) if e is not None and e[0] == 10}
    assert called in refs and "m_5_" not in refs


# --- choosing and deriving a table ------------------------------------------------

@pytest.mark.parametrize("loader,mc,want", [
    ("forge", "1.20.1", "mappings-srg-1.20.1"),
    ("forge", "1.19.2", "mappings-srg-1.19.2"),
    ("neoforge", "1.20.1", "mappings-srg-1.20.1"),
    ("neoforge", "1.21.1", None),           # Mojang names at runtime
    ("fabric", "1.21.1", "mappings-intermediary-1.21.1"),
    ("quilt", "1.20.1", "mappings-intermediary-1.20.1"),
    ("fabric", "26.1", None),               # 26.1 is not obfuscated
    ("forge", "1.16.5", None),              # MCP-era names: not pinned
    (None, "1.20.1", None),
])
def test_select(loader, mc, want):
    got = mappings.select(loader, mc)
    assert (got.id if got else None) == want


_CLIENT = """# (c) 2020 Microsoft Corporation. test header
net.minecraft.world.level.block.Block -> cpn:
    net.minecraft.world.level.block.state.properties.DirectionProperty FACING -> a
    12:13:net.minecraft.world.level.block.state.BlockState getStateForPlacement(net.minecraft.world.item.context.BlockPlaceContext) -> a
    void tick(int[],boolean) -> b
    void other() -> c
net.minecraft.world.item.context.BlockPlaceContext -> cdh:
    void foo() -> a
net.minecraft.world.level.block.state.BlockState -> dcb:
net.minecraft.world.level.block.Block$Inner -> cpn$a:
    void bar() -> a
"""


def _tsrg_zip() -> bytes:
    body = ("tsrg2 obf srg id\n"
            "cpn net/minecraft/world/level/block/Block 1\n"
            "\ta f_54117_ 54117\n"
            "\ta (Lcdh;)Ldcb; m_5573_ 5573\n"
            "\t\t0 o p_1_ 1\n"
            "\tb ([IZ)V m_7000_ 7000\n"
            "\tc ()V m_7000_ 7000\n"
            "cdh net/minecraft/world/item/context/BlockPlaceContext 2\n"
            "\ta ()V m_9000_ 9000\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("config/joined.tsrg", body)
    return buf.getvalue()


_TINY = ("v1\tofficial\tintermediary\n"
         "CLASS\tcpn\tnet/minecraft/class_2248\n"
         "CLASS\tcdh\tnet/minecraft/class_1750\n"
         "CLASS\tdcb\tnet/minecraft/class_2680\n"
         "CLASS\tcpn$a\tnet/minecraft/class_2248$class_9\n"
         "FIELD\tcpn\tLx;\ta\tfield_11177\n"
         "METHOD\tcpn\t(Lcdh;)Ldcb;\ta\tmethod_9605\n"
         "METHOD\tcpn$a\t()V\ta\tmethod_77\n")


def test_derive_srg_joins_on_obfuscated_names_and_drops_ambiguous_ids():
    s = mappings.select("forge", "1.20.1")
    table = json.loads(mappings.derive(s, _CLIENT.encode(), _tsrg_zip()))
    assert table["classes"] == {}
    # m_7000_ would map to both tick and other: left unmapped, listed.
    assert table["members"] == {"f_54117_": "FACING", "m_5573_": "getStateForPlacement", "m_9000_": "foo"}
    assert table["ambiguous"] == ["m_7000_"]
    assert table["sources"][0].endswith(f"{s.mojang_sha1}/client.txt")


def test_derive_intermediary_maps_classes_too():
    s = mappings.select("fabric", "1.21.1")
    table = json.loads(mappings.derive(s, _CLIENT.encode(), _TINY.encode()))
    assert table["classes"] == {
        "net/minecraft/class_1750": "net/minecraft/world/item/context/BlockPlaceContext",
        "net/minecraft/class_2248": "net/minecraft/world/level/block/Block",
        "net/minecraft/class_2248$class_9": "net/minecraft/world/level/block/Block$Inner",
        "net/minecraft/class_2680": "net/minecraft/world/level/block/state/BlockState",
    }
    assert table["members"] == {"field_11177": "FACING", "method_77": "bar",
                                "method_9605": "getStateForPlacement"}
    r = mappings.Remapper(s.id, table["classes"], table["members"])
    assert r.desc("(Lnet/minecraft/class_1750;)Lnet/minecraft/class_2680;") == (
        "(Lnet/minecraft/world/item/context/BlockPlaceContext;)"
        "Lnet/minecraft/world/level/block/state/BlockState;")
    assert r.cls("[Lnet/minecraft/class_2248;") == "[Lnet/minecraft/world/level/block/Block;"
    assert r.member("method_9605") == "getStateForPlacement"
    assert r.member("method_1") == "method_1"      # unknown id: unchanged
    assert r.member("getShape") == "getShape"      # not a renamed name


# --- fetching ---------------------------------------------------------------

class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(files: dict[str, bytes]):
    def open_(request, timeout=0):
        return _Resp(files[request.full_url])
    return open_


def test_fetch_checks_every_pin(tmp_path, monkeypatch):
    client, other = _CLIENT.encode(), _TINY.encode()
    base = mappings.select("fabric", "1.21.1")
    derived = mappings.derive(dataclasses.replace(base, mojang_sha1=hashlib.sha1(client).hexdigest()),
                              client, other)
    pinned = dataclasses.replace(base, mojang_sha1=hashlib.sha1(client).hexdigest(),
                                 other_sha256=hashlib.sha256(other).hexdigest(),
                                 sha256=hashlib.sha256(derived).hexdigest())
    files = {pinned.mojang_url: client, pinned.other_url: other}
    path, downloaded = mappings.fetch(pinned, tmp_path, opener=_opener(files))
    assert downloaded and path.read_bytes() == derived
    assert mappings.fetch(pinned, tmp_path, opener=_opener({}))[1] is False  # cached
    bad = dataclasses.replace(pinned, other_sha256="0" * 64)
    with pytest.raises(ReferenceDataError, match="sha256 mismatch"):
        mappings.download(bad, opener=_opener(files))
    bad = dataclasses.replace(pinned, sha256="0" * 64)
    with pytest.raises(ReferenceDataError, match="re-pin"):
        mappings.fetch(bad, tmp_path / "other", opener=_opener(files))
    # A cached table is read back and verified against its pin.
    monkeypatch.setattr(mappings, "cache_dir", lambda: tmp_path)
    monkeypatch.delenv("PORTKIT_MAPPINGS", raising=False)
    assert mappings.remapper(pinned).member("method_9605") == "getStateForPlacement"


def test_attach_notes_a_renamed_jar_without_its_table(block_raw, tmp_path, monkeypatch):
    monkeypatch.setenv("PORTKIT_MAPPINGS", str(tmp_path))  # an empty table dir
    renamed = _index(block_raw, _Scheme(block_raw, "srg"), False)
    note = mappings.attach(renamed, "forge", "1.20.1")
    assert note and "Forge SRG" in note and "portkit reference fetch" in note
    assert renamed.remapper is None
    # A Mojang-named jar needs nothing, and gets no note.
    assert mappings.attach(ClassIndex(dict(block_raw)), "forge", "1.20.1") is None
    assert mappings.attach(ClassIndex(dict(block_raw)), "neoforge", "1.21.1") is None


def test_attach_uses_the_table_from_the_override_dir(block_raw, tmp_path, monkeypatch):
    renaming = _Scheme(block_raw, "srg")
    r = renaming.remapper()
    (tmp_path / "mappings-srg-1.20.1.json").write_text(json.dumps(
        {"set": "mappings-srg-1.20.1", "classes": r.classes, "members": r.members}))
    monkeypatch.setenv("PORTKIT_MAPPINGS", str(tmp_path))
    renamed = _index(block_raw, renaming, False)
    assert mappings.attach(renamed, "forge", "1.20.1") is None
    assert renamed.remapper is not None
    assert renamed.get("com/example/deco/LampBlock").method("getStateForPlacement") is not None
    # Names as compiled stay reachable.
    assert renamed.get("com/example/deco/LampBlock", remap=False).method("getStateForPlacement") is None
