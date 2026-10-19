"""A small, read-only reader for compiled Java class files.

Some of what a Java block does lives only in its compiled code: which way its
``facing`` points when a player places it, and the shape it collides with.
This module reads exactly enough of the class-file format (JVM Specification,
Java SE 21, chapter 4 "The class File Format") to let a converter find those
answers by matching plain, well-known bytecode patterns. It never runs code
and never guesses: a caller that can't match a pattern gets nothing back and
must say so.

Names are read as compiled. NeoForge 1.20.5+ ships Mojang's official names at
runtime, so ``getStateForPlacement`` and ``HorizontalDirectionalBlock`` are
spelled as in the source; Forge (SRG) and Fabric (intermediary) jars use other
names. A :class:`ClassIndex` given a remapper (:mod:`portkit.data.mappings`,
#235) puts those back into Mojang's names as each class is parsed: class
names, member names and descriptors in the constant pool and the class's own
declarations. Strings are never touched, and a jar without renamed names
parses byte-for-byte as before.
"""
from __future__ import annotations

import struct
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

_MAGIC = 0xCAFEBABE
# Constant pool tags (JVMS 4.4, table 4.4-B).
_UTF8, _INTEGER, _FLOAT, _LONG, _DOUBLE = 1, 3, 4, 5, 6
_CLASS, _STRING, _FIELDREF, _METHODREF, _IMETHODREF = 7, 8, 9, 10, 11
_NAME_AND_TYPE, _METHOD_HANDLE, _METHOD_TYPE, _DYNAMIC, _INVOKE_DYNAMIC = 12, 15, 16, 17, 18
_MODULE, _PACKAGE = 19, 20

_MAX_CLASS_BYTES = 4 * 1024 * 1024


class ClassFormatError(Exception):
    """The bytes are not a class file this reader understands."""


@dataclass(frozen=True)
class Ref:
    """A field or method reference from the constant pool."""

    owner: str
    name: str
    desc: str


@dataclass(frozen=True)
class Handle:
    """A CONSTANT_MethodHandle (JVMS 4.4.8): kind 5-9 call a method, 8 is
    REF_newInvokeSpecial (a constructor reference, ``Foo::new``)."""

    kind: int
    ref: Ref


@dataclass(frozen=True)
class Indy:
    """An invokedynamic call site: its bootstrap method and static arguments."""

    name: str
    desc: str
    bootstrap: Handle | None
    args: tuple


@dataclass
class Method:
    name: str
    desc: str
    access: int
    code: bytes | None


@dataclass
class ClassFile:
    name: str
    super_name: str | None
    interfaces: tuple[str, ...]
    fields: dict[str, str]
    methods: list[Method]
    pool: list
    bootstrap: list = field(default_factory=list)
    # The class's access flags (JVMS 4.1): 0x0200 interface, 0x0400 abstract,
    # 0x2000 annotation, 0x4000 enum.
    access: int = 0
    # Each field's access flags (JVMS 4.5), with 0x10000 added when it
    # carries a ConstantValue attribute (a compile-time constant).
    field_access: dict = field(default_factory=dict)
    # The class's RuntimeVisibleAnnotations (JVMS 4.7.16): annotation type
    # descriptor -> {element name: value}, a value a str (String, or a
    # class descriptor for a class literal), int/float, ``(enum type,
    # constant)`` or a tuple of values; a nested annotation reads as None.
    annotations: dict = field(default_factory=dict)

    def method(self, name: str, desc: str | None = None) -> Method | None:
        for m in self.methods:
            if m.name == name and (desc is None or m.desc == desc):
                return m
        return None

    def constant(self, index: int):
        """A resolved loadable constant: str for String, int/float, Ref,
        Handle, Indy, or ("class", name) for a class literal."""
        return _resolve(self, index)


def _resolve(cf: ClassFile, index: int):
    entry = cf.pool[index]
    if entry is None:
        return None
    tag = entry[0]
    if tag == _UTF8:
        return entry[1]
    if tag in (_INTEGER, _FLOAT, _LONG, _DOUBLE):
        return entry[1]
    if tag == _CLASS:
        return ("class", cf.pool[entry[1]][1])
    if tag == _STRING:
        return cf.pool[entry[1]][1]
    if tag in (_FIELDREF, _METHODREF, _IMETHODREF):
        owner = cf.pool[cf.pool[entry[1]][1]][1]
        nat = cf.pool[entry[2]]
        return Ref(owner, cf.pool[nat[1]][1], cf.pool[nat[2]][1])
    if tag == _METHOD_HANDLE:
        return Handle(entry[1], _resolve(cf, entry[2]))
    if tag == _METHOD_TYPE:
        return ("methodtype", cf.pool[entry[1]][1])
    if tag in (_INVOKE_DYNAMIC, _DYNAMIC):
        nat = cf.pool[entry[2]]
        bsm = cf.bootstrap[entry[1]] if entry[1] < len(cf.bootstrap) else None
        handle, args = (None, ()) if bsm is None else (
            _resolve(cf, bsm[0]), tuple(_resolve(cf, a) for a in bsm[1]))
        return Indy(cf.pool[nat[1]][1], cf.pool[nat[2]][1], handle, args)
    return None


def _modified_utf8(raw: bytes) -> str:
    # JVMS 4.4.7: NUL is 0xC0 0x80 and supplementary characters are surrogate
    # pairs; Python's surrogatepass decoder reads both once NUL is restored.
    return raw.replace(b"\xc0\x80", b"\x00").decode("utf-8", "surrogatepass")


def parse(data: bytes, remapper=None) -> ClassFile:
    """Parse one class file, or raise :class:`ClassFormatError`. With a
    ``remapper`` (``cls``/``member``/``desc`` methods, see
    :class:`portkit.data.mappings.Remapper`) renamed Minecraft names come
    back as Mojang's."""
    try:
        return _parse(data, remapper)
    except (struct.error, IndexError, UnicodeDecodeError, TypeError) as exc:
        raise ClassFormatError(str(exc)) from exc


def _remap_pool(pool: list, remapper) -> None:
    """Point the pool's class, member-name and descriptor entries at Mojang's
    names. A changed name gets a new UTF8 entry appended (the old one may be
    shared with a String constant, which must keep its text); everything that
    refers to the pool by index stays valid."""
    added: dict[str, int] = {}

    def utf_index(old: int, fn) -> int:
        text = pool[old][1]
        new = fn(text)
        if new == text:
            return old
        if new not in added:
            added[new] = len(pool)
            pool.append((_UTF8, new))
        return added[new]

    for i in range(len(pool)):
        entry = pool[i]
        if entry is None:
            continue
        tag = entry[0]
        if tag == _CLASS:
            pool[i] = (tag, utf_index(entry[1], remapper.cls))
        elif tag == _NAME_AND_TYPE:
            pool[i] = (tag, utf_index(entry[1], remapper.member), utf_index(entry[2], remapper.desc))
        elif tag == _METHOD_TYPE:
            pool[i] = (tag, utf_index(entry[1], remapper.desc))


def _parse(data: bytes, remapper=None) -> ClassFile:
    if len(data) < 10 or struct.unpack_from(">I", data, 0)[0] != _MAGIC:
        raise ClassFormatError("not a class file")
    pos = 8
    (count,) = struct.unpack_from(">H", data, pos)
    pos += 2
    pool: list = [None] * count
    i = 1
    while i < count:
        tag = data[pos]
        pos += 1
        if tag == _UTF8:
            (n,) = struct.unpack_from(">H", data, pos)
            pool[i] = (tag, _modified_utf8(data[pos + 2:pos + 2 + n]))
            pos += 2 + n
        elif tag == _INTEGER:
            pool[i] = (tag, struct.unpack_from(">i", data, pos)[0])
            pos += 4
        elif tag == _FLOAT:
            pool[i] = (tag, struct.unpack_from(">f", data, pos)[0])
            pos += 4
        elif tag == _LONG:
            pool[i] = (tag, struct.unpack_from(">q", data, pos)[0])
            pos += 8
            i += 1
        elif tag == _DOUBLE:
            pool[i] = (tag, struct.unpack_from(">d", data, pos)[0])
            pos += 8
            i += 1
        elif tag in (_CLASS, _STRING, _METHOD_TYPE, _MODULE, _PACKAGE):
            pool[i] = (tag, struct.unpack_from(">H", data, pos)[0])
            pos += 2
        elif tag in (_FIELDREF, _METHODREF, _IMETHODREF, _NAME_AND_TYPE, _DYNAMIC, _INVOKE_DYNAMIC):
            pool[i] = (tag, *struct.unpack_from(">HH", data, pos))
            pos += 4
        elif tag == _METHOD_HANDLE:
            pool[i] = (tag, data[pos], struct.unpack_from(">H", data, pos + 1)[0])
            pos += 3
        else:
            raise ClassFormatError(f"unknown constant pool tag {tag}")
        i += 1
    if remapper is not None:
        _remap_pool(pool, remapper)
    member = remapper.member if remapper is not None else (lambda n: n)
    desc_of = remapper.desc if remapper is not None else (lambda d: d)

    def utf(idx: int) -> str:
        return pool[idx][1]

    def cls(idx: int) -> str | None:
        return utf(pool[idx][1]) if idx else None

    access, this, sup = struct.unpack_from(">HHH", data, pos)
    pos += 6
    (n,) = struct.unpack_from(">H", data, pos)
    pos += 2
    interfaces = tuple(cls(struct.unpack_from(">H", data, pos + 2 * k)[0]) for k in range(n))
    pos += 2 * n

    def attributes(pos: int) -> tuple[int, list[tuple[str, bytes]]]:
        (n,) = struct.unpack_from(">H", data, pos)
        pos += 2
        out = []
        for _ in range(n):
            name, length = struct.unpack_from(">HI", data, pos)
            pos += 6
            out.append((utf(name), data[pos:pos + length]))
            pos += length
        return pos, out

    fields: dict[str, str] = {}
    field_access: dict[str, int] = {}
    (n,) = struct.unpack_from(">H", data, pos)
    pos += 2
    for _ in range(n):
        faccess, name, desc = struct.unpack_from(">HHH", data, pos)
        pos, fattrs = attributes(pos + 6)
        fields[member(utf(name))] = desc_of(utf(desc))
        field_access[member(utf(name))] = faccess | (0x10000 if any(a == "ConstantValue" for a, _ in fattrs) else 0)

    methods: list[Method] = []
    (n,) = struct.unpack_from(">H", data, pos)
    pos += 2
    for _ in range(n):
        # (A method's own flags: the class's ``access`` is kept for the
        # ClassFile; it was overwritten here before #280 slice 3.)
        maccess, name, desc = struct.unpack_from(">HHH", data, pos)
        pos, attrs = attributes(pos + 6)
        code = None
        for aname, body in attrs:
            if aname == "Code":
                (length,) = struct.unpack_from(">I", body, 4)
                code = body[8:8 + length]
        methods.append(Method(member(utf(name)), desc_of(utf(desc)), maccess, code))

    pos, attrs = attributes(pos)
    bootstrap = []
    for aname, body in attrs:
        if aname == "BootstrapMethods":
            (n,) = struct.unpack_from(">H", body, 0)
            p = 2
            for _ in range(n):
                ref, nargs = struct.unpack_from(">HH", body, p)
                p += 4
                args = struct.unpack_from(f">{nargs}H", body, p)
                p += 2 * nargs
                bootstrap.append((ref, args))
    annotations: dict = {}
    for aname, body in attrs:
        if aname == "RuntimeVisibleAnnotations":
            try:
                annotations = _annotations(body, pool)
            except (struct.error, IndexError, TypeError):
                annotations = {}  # a malformed table names no annotation
    return ClassFile(cls(this), cls(sup), interfaces, fields, methods, pool, bootstrap, access, field_access,
                     annotations)


def _annotations(body: bytes, pool: list) -> dict:
    """A RuntimeVisibleAnnotations attribute's annotations (JVMS 4.7.16)."""
    def utf(idx: int):
        return pool[idx][1]

    def value(pos: int):
        tag = chr(body[pos])
        pos += 1
        if tag in "BCDFIJSZs":
            (idx,) = struct.unpack_from(">H", body, pos)
            return pool[idx][1], pos + 2
        if tag == "e":
            t, c = struct.unpack_from(">HH", body, pos)
            return (utf(t), utf(c)), pos + 4
        if tag == "c":
            (idx,) = struct.unpack_from(">H", body, pos)
            return utf(idx), pos + 2
        if tag == "@":
            _t, pos = annotation(pos)
            return None, pos
        if tag == "[":
            (n,) = struct.unpack_from(">H", body, pos)
            pos += 2
            out = []
            for _ in range(n):
                v, pos = value(pos)
                out.append(v)
            return tuple(out), pos
        raise IndexError(f"unknown element value tag {tag!r}")

    def annotation(pos: int):
        t, n = struct.unpack_from(">HH", body, pos)
        pos += 4
        elems = {}
        for _ in range(n):
            (name,) = struct.unpack_from(">H", body, pos)
            v, pos = value(pos + 2)
            elems[utf(name)] = v
        return (utf(t), elems), pos

    (n,) = struct.unpack_from(">H", body, 0)
    pos = 2
    out = {}
    for _ in range(n):
        (t, elems), pos = annotation(pos)
        out[t] = elems
    return out


# --- Instructions -----------------------------------------------------------

# Operand byte counts for fixed-length opcodes (JVMS chapter 6); the variable
# ones (tableswitch 0xAA, lookupswitch 0xAB, wide 0xC4) are decoded below.
_OPERANDS = [0] * 256
for _op in (0x10, 0x12, 0x15, 0x16, 0x17, 0x18, 0x19, 0x36, 0x37, 0x38, 0x39, 0x3A, 0xA9, 0xBC):
    _OPERANDS[_op] = 1
for _op in (0x11, 0x13, 0x14, 0x84, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xBB, 0xBD,
            0xC0, 0xC1, 0xC6, 0xC7, *range(0x99, 0xA9)):
    _OPERANDS[_op] = 2
for _op in (0xC5,):
    _OPERANDS[_op] = 3
for _op in (0xB9, 0xBA, 0xC8, 0xC9):
    _OPERANDS[_op] = 4

NAMES = {
    0x00: "nop", 0x01: "aconst_null", 0x02: "iconst_m1", 0x03: "iconst_0", 0x04: "iconst_1",
    0x05: "iconst_2", 0x06: "iconst_3", 0x07: "iconst_4", 0x08: "iconst_5", 0x09: "lconst_0",
    0x0A: "lconst_1", 0x0B: "fconst_0", 0x0C: "fconst_1", 0x0D: "fconst_2", 0x0E: "dconst_0",
    0x0F: "dconst_1", 0x10: "bipush", 0x11: "sipush", 0x12: "ldc", 0x13: "ldc_w", 0x14: "ldc2_w",
    0x15: "iload", 0x19: "aload", 0x1A: "iload_0", 0x1B: "iload_1", 0x1C: "iload_2",
    0x1D: "iload_3", 0x2A: "aload_0", 0x2B: "aload_1", 0x2C: "aload_2", 0x2D: "aload_3",
    0x2E: "iaload", 0x32: "aaload", 0x36: "istore", 0x3A: "astore", 0x3B: "istore_0",
    0x3C: "istore_1", 0x3D: "istore_2", 0x3E: "istore_3", 0x4B: "astore_0", 0x4C: "astore_1",
    0x4D: "astore_2", 0x4E: "astore_3", 0x4F: "iastore", 0x53: "aastore", 0x57: "pop",
    0x59: "dup", 0x5A: "dup_x1", 0x5F: "swap", 0x63: "dadd", 0x6B: "dmul", 0x77: "dneg",
    0x99: "ifeq", 0x9A: "ifne", 0x9F: "if_icmpeq", 0xA0: "if_icmpne", 0xA5: "if_acmpeq",
    0xA6: "if_acmpne", 0xA7: "goto", 0xAA: "tableswitch", 0xAB: "lookupswitch",
    0xAC: "ireturn", 0xB0: "areturn", 0xB1: "return", 0xB2: "getstatic", 0xB3: "putstatic",
    0xB4: "getfield", 0xB5: "putfield", 0xB6: "invokevirtual", 0xB7: "invokespecial",
    0xB8: "invokestatic", 0xB9: "invokeinterface", 0xBA: "invokedynamic", 0xBB: "new",
    0xBD: "anewarray", 0xBF: "athrow", 0xC0: "checkcast", 0xC1: "instanceof",
    0xC6: "ifnull", 0xC7: "ifnonnull",
}


@dataclass(frozen=True)
class Insn:
    """One decoded instruction. ``arg`` is the resolved constant for pool
    operands (Ref, Indy, str, number, ("class", name)), the immediate for
    bipush/sipush/local-variable opcodes, a branch target for jumps, or
    (default, {key: target}) for a switch."""

    offset: int
    op: int
    arg: object = None

    @property
    def name(self) -> str:
        return NAMES.get(self.op, f"op_{self.op:02x}")


def instructions(cf: ClassFile, code: bytes) -> list[Insn]:
    """Decode ``code`` (a method's Code bytes) into instructions."""
    out: list[Insn] = []
    pos = 0
    n = len(code)
    while pos < n:
        op = code[pos]
        start = pos
        pos += 1
        if op == 0xAA:  # tableswitch
            pos += (-pos) % 4
            default, low, high = struct.unpack_from(">iii", code, pos)
            pos += 12
            count = high - low + 1
            targets = struct.unpack_from(f">{count}i", code, pos)
            pos += 4 * count
            out.append(Insn(start, op, (start + default, {low + k: start + t for k, t in enumerate(targets)})))
            continue
        if op == 0xAB:  # lookupswitch
            pos += (-pos) % 4
            default, npairs = struct.unpack_from(">ii", code, pos)
            pos += 8
            pairs = {}
            for _ in range(npairs):
                key, target = struct.unpack_from(">ii", code, pos)
                pos += 8
                pairs[key] = start + target
            out.append(Insn(start, op, (start + default, pairs)))
            continue
        if op == 0xC4:  # wide
            inner = code[pos]
            pos += 5 if inner == 0x84 else 3
            index = struct.unpack_from(">H", code, start + 2)[0]
            if inner == 0x84:
                out.append(Insn(start, inner, (index, struct.unpack_from(">h", code, start + 4)[0])))
            else:
                out.append(Insn(start, inner, index))
            continue
        width = _OPERANDS[op]
        raw = code[pos:pos + width]
        pos += width
        arg = None
        if op in (0x12,):
            arg = cf.constant(raw[0])
        elif op in (0x13, 0x14, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xBB, 0xBD, 0xC0, 0xC1):
            arg = cf.constant(struct.unpack_from(">H", raw)[0])
        elif op in (0xB9, 0xBA):
            arg = cf.constant(struct.unpack_from(">H", raw)[0])
        elif op == 0x10:
            arg = struct.unpack_from(">b", raw)[0]
        elif op == 0x11:
            arg = struct.unpack_from(">h", raw)[0]
        elif op in (*range(0x99, 0xA9), 0xC6, 0xC7):
            arg = start + struct.unpack_from(">h", raw)[0]
        elif op == 0xC8:
            arg = start + struct.unpack_from(">i", raw)[0]
        elif op == 0x84:
            arg = (raw[0], struct.unpack_from(">b", raw, 1)[0])
        elif width == 1:
            arg = raw[0]
        out.append(Insn(start, op, arg))
    return out


class ClassIndex:
    """The class files of one mod (a jar or an unpacked directory), parsed on
    demand by internal name (``com/example/FooBlock``)."""

    def __init__(self, entries: dict[str, bytes], libraries: dict[str, bytes] | None = None):
        self._raw = entries
        # Classes of the mod's declared dependency jars (#280), read-only: a
        # lookup by name finds them (a block class subclassing a library's
        # base, a library constructor that registers its block), but they are
        # never listed, counted or scanned as the mod's own (``names``,
        # ``raw``, ``len``), so nothing of a library is converted or shipped.
        self._lib: dict[str, bytes] = {k: v for k, v in (libraries or {}).items() if k not in entries}
        self._parsed: dict[str, ClassFile | None] = {}
        self.remapper = None
        # Vanilla ``Blocks`` field name -> block registry id for the game
        # version the mod declares (:mod:`portkit.data.vanilla_blocks`, #280),
        # or None when that table isn't pinned or cached.
        self.vanilla_blocks: dict[str, str] | None = None
        # The loader metadata files of the mod's jar and of each library jar
        # (one {path: bytes} per jar, the mod's first): which classes the
        # loader constructs itself (:mod:`portkit.entrypoints`, #280).
        self.entry_meta: list[dict[str, bytes]] = []

    def add_libraries(self, entries: dict[str, bytes]) -> int:
        """Make ``entries`` (a dependency jar's classes) visible to lookups;
        a name the mod or an earlier library already has is kept. Returns how
        many classes were added."""
        added = 0
        for k, v in entries.items():
            if k not in self._raw and k not in self._lib:
                self._lib[k] = v
                self._parsed.pop(k, None)
                added += 1
        return added

    def nest(self, name: str) -> list[str]:
        """The classes, the mod's or a library's, compiled from the same
        top-level class as ``name`` (``Outer`` and ``Outer$...``): the only
        classes that may write a private field of ``name`` (JVMS 5.4.4,
        nestmates)."""
        top = name.split("$", 1)[0]
        return sorted({k for src in (self._raw, self._lib) for k in src
                       if k == top or k.startswith(top + "$")})

    def mentions(self, needle: bytes) -> bool:
        """Whether any class file, the mod's or a library's, holds the bytes
        ``needle`` (a constant pool name, as compiled)."""
        return any(needle in raw for src in (self._raw, self._lib) for raw in src.values())

    def is_library(self, name: str) -> bool:
        """Whether ``name`` is a dependency jar's class rather than the mod's."""
        return name in self._lib and name not in self._raw

    def library_count(self) -> int:
        return len(self._lib)

    def set_remapper(self, remapper) -> None:
        """Read every class through ``remapper`` from now on (#235): a Forge SRG
        or Fabric intermediary jar's Minecraft names come back as Mojang's.
        ``None`` reads names as compiled again."""
        self.remapper = remapper
        self._parsed.clear()

    @classmethod
    def from_source(cls, source: Path | None) -> "ClassIndex":
        entries: dict[str, bytes] = {}
        if source is None:
            return cls(entries)
        source = Path(source)
        if source.is_file() and zipfile.is_zipfile(source):
            with zipfile.ZipFile(source) as zf:
                for info in zf.infolist():
                    name = info.filename
                    if name.endswith(".class") and not name.startswith("META-INF/") \
                            and info.file_size <= _MAX_CLASS_BYTES:
                        entries[name[:-6]] = zf.read(info)
        elif source.is_dir():
            for path in source.rglob("*.class"):
                rel = path.relative_to(source).as_posix()
                if not rel.startswith("META-INF/") and path.stat().st_size <= _MAX_CLASS_BYTES:
                    entries[rel[:-6]] = path.read_bytes()
        return cls(entries)

    def __len__(self) -> int:
        return len(self._raw)

    def names(self) -> list[str]:
        return sorted(self._raw)

    def raw(self, name: str) -> bytes | None:
        """The class file's bytes as compiled (not remapped), for cheap scans."""
        return self._raw.get(name)

    def get(self, name: str, remap: bool = True) -> ClassFile | None:
        """The parsed class, through the remapper unless ``remap`` is False
        (names as compiled, not cached)."""
        if not remap and self.remapper is not None:
            raw = self._raw.get(name, self._lib.get(name))
            try:
                return parse(raw) if raw is not None else None
            except ClassFormatError:
                return None
        if name not in self._parsed:
            raw = self._raw.get(name)
            if raw is None:
                raw = self._lib.get(name)
            try:
                self._parsed[name] = parse(raw, self.remapper) if raw is not None else None
            except ClassFormatError:
                self._parsed[name] = None
        return self._parsed[name]
