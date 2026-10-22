"""#368 (part of #277): the jar-in-jar libraries a Forge/NeoForge mod lists in
META-INF/jarjar/metadata.json are attached to the class index as library
classes, with their META-INF/services files, so the readers can follow calls
into bundled library code and ServiceLoader sees the providers they declare.

The synthetic jars wrap the javac 21 output under tests/data/libcode (see
test_libraries.py): the example mod's classes in the mod jar, the example
library's in a nested jar.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from portkit import blockcode, libraries, nested_jars
from portkit.blockcode import UNKNOWN, ClassLit, Machine, Obj
from portkit.bytecode import ClassIndex
from portkit.ingest import from_directory, from_jar

DATA = Path(__file__).parent / "data" / "libcode"
NAMES = ["lib_stone_plate", "lib_lamp", "lib_players_plate"]
LOAD = ("java/util/ServiceLoader", "load", "(Ljava/lang/Class;)Ljava/util/ServiceLoader;")
MODS_TOML = b'modLoader="javafml"\nloaderVersion="[47,)"\nlicense="MIT"\n[[mods]]\nmodId="libmod"\nversion="1.0"\n'


def _entries(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix()[:-6]: p.read_bytes() for p in root.rglob("*.class")}


def _inner_jar(classes: dict[str, bytes], services: dict[str, str] | None = None,
               extra: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, raw in classes.items():
            zf.writestr(name + ".class", raw)
        for service, text in (services or {}).items():
            zf.writestr(f"META-INF/services/{service}", text)
        for name, raw in (extra or {}).items():
            zf.writestr(name, raw)
    return buf.getvalue()


def _metadata(*paths: str) -> str:
    # MinecraftForge JarJar Metadata: {"jars": [ContainedJarMetadata...]}
    return json.dumps({"jars": [
        {"identifier": {"group": "com.example", "artifact": p.rsplit("/", 1)[-1][:-4]},
         "version": {"range": "[1.0,)", "artifactVersion": "1.0"}, "path": p, "isObfuscated": False}
        for p in paths]})


def _mod_jar(path: Path, own: dict[str, bytes], nested: dict[str, bytes], listed: list[str] | None,
             services: dict[str, str] | None = None) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("META-INF/mods.toml", MODS_TOML)
        zf.writestr("assets/libmod/lang/en_us.json", "{}")
        for name, raw in own.items():
            zf.writestr(name + ".class", raw)
        for service, text in (services or {}).items():
            zf.writestr(f"META-INF/services/{service}", text)
        for name, raw in nested.items():
            zf.writestr(name, raw)
        if listed is not None:
            zf.writestr(nested_jars.JARJAR_METADATA, _metadata(*listed))
    return path


@pytest.fixture()
def own():
    return _entries(DATA / "classes")


@pytest.fixture()
def lib():
    return _entries(DATA / "library")


# --- the metadata file ----------------------------------------------------------

def test_metadata_lists_paths_in_order_once():
    raw = _metadata("META-INF/jarjar/a.jar", "META-INF/jarjar/b.jar", "META-INF/jarjar/a.jar").encode()
    assert nested_jars.jarjar_paths(raw) == ["META-INF/jarjar/a.jar", "META-INF/jarjar/b.jar"]


@pytest.mark.parametrize("raw", [None, b"", b"not json", b"[]", b'{"jars": {}}', b'{"jars": [{"path": 3}]}',
                                 b'{"jars": [{"path": "../evil.jar"}]}', b"\xff\xfe"])
def test_a_missing_or_odd_metadata_file_lists_nothing(raw):
    assert nested_jars.jarjar_paths(raw) == []


# --- ingest ------------------------------------------------------------------

def test_a_listed_jarjar_library_is_attached_as_library_classes(tmp_path, own, lib):
    jar = _mod_jar(tmp_path / "libmod.jar", own, {"META-INF/jarjar/examplelib-1.0.jar": _inner_jar(lib)},
                   ["META-INF/jarjar/examplelib-1.0.jar"])
    staged = from_jar(jar, tmp_path / "staging")
    index = staged.classes
    assert len(index) == len(own) and index.names() == sorted(own)
    assert index.library_count() == len(lib)
    assert index.is_library("com/example/lib/LibPlateBlock")
    assert index.raw("com/example/lib/LibPlateBlock") is None  # never scanned as the mod's own
    assert staged.class_count == len(own)
    # The nested jar is still nested_jar residue (its resources aren't staged).
    assert [u.kind for u in staged.residue() if u.source == "META-INF/jarjar/examplelib-1.0.jar"] == ["nested_jar"]
    assert staged.bundled == {"META-INF/jarjar/examplelib-1.0.jar": len(lib)}
    assert "examplelib-1.0.jar (4 classes)" in staged.bundled_note()


def test_the_reader_follows_registrations_into_a_jarjar_library(tmp_path, own, lib):
    alone = _mod_jar(tmp_path / "alone.jar", own, {}, None)
    _, reg = blockcode._registered(from_jar(alone, tmp_path / "a").classes, NAMES)
    assert all(objs == [] for objs, _ in reg.values())
    jar = _mod_jar(tmp_path / "libmod.jar", own, {"META-INF/jarjar/examplelib-1.0.jar": _inner_jar(lib)},
                   ["META-INF/jarjar/examplelib-1.0.jar"])
    machine, reg = blockcode._registered(from_jar(jar, tmp_path / "b").classes, NAMES)
    assert {n: [o.cls for o in objs] for n, (objs, _) in reg.items()} == {
        "lib_stone_plate": ["com/example/lib/LibPlateBlock"],
        "lib_lamp": ["com/example/lib/LibBlock"],
        "lib_players_plate": ["com/example/libmod/PlayersPlateBlock"],
    }
    assert machine.vanilla_base("com/example/libmod/PlayersPlateBlock") == \
        "net/minecraft/world/level/block/PressurePlateBlock"


def test_an_unlisted_or_unreadable_jarjar_jar_is_not_read(tmp_path, own, lib):
    nested = {"META-INF/jarjar/examplelib-1.0.jar": _inner_jar(lib), "META-INF/jarjar/broken.jar": b"PK\x03\x04no"}
    unlisted = from_jar(_mod_jar(tmp_path / "u.jar", own, nested, None), tmp_path / "u")
    assert unlisted.classes.library_count() == 0 and unlisted.bundled == {} and unlisted.bundled_note() is None
    broken = from_jar(_mod_jar(tmp_path / "b.jar", own, nested, ["META-INF/jarjar/broken.jar",
                                                                  "META-INF/jarjar/gone.jar"]), tmp_path / "b")
    assert broken.classes.library_count() == 0 and broken.bundled == {}


def test_the_mods_own_class_wins_over_a_bundled_copy(tmp_path, own, lib):
    clash = {"com/example/libmod/PlateModule": lib["com/example/lib/LibModule"]}
    jar = _mod_jar(tmp_path / "libmod.jar", own, {"META-INF/jarjar/x.jar": _inner_jar(clash)},
                   ["META-INF/jarjar/x.jar"])
    staged = from_jar(jar, tmp_path / "s")
    assert staged.classes.library_count() == 0 and staged.bundled == {"META-INF/jarjar/x.jar": 0}
    assert staged.classes.get("com/example/libmod/PlateModule").name == "com/example/libmod/PlateModule"


def test_bundled_loader_metadata_follows_the_mods_own(tmp_path, own, lib):
    inner = _inner_jar(lib, extra={"META-INF/mods.toml": b'[[mods]]\nmodId="examplelib"\n'})
    jar = _mod_jar(tmp_path / "libmod.jar", own, {"META-INF/jarjar/l.jar": inner}, ["META-INF/jarjar/l.jar"])
    meta = from_jar(jar, tmp_path / "s").classes.entry_meta
    assert meta[0]["META-INF/mods.toml"] == MODS_TOML
    assert meta[1] == {"META-INF/mods.toml": b'[[mods]]\nmodId="examplelib"\n'}


def test_an_unpacked_mod_directory_attaches_its_jarjar_libraries(tmp_path, lib):
    root = tmp_path / "unpacked"
    (root / "META-INF/jarjar").mkdir(parents=True)
    (root / "assets/libmod/lang").mkdir(parents=True)
    (root / "assets/libmod/lang/en_us.json").write_text("{}")
    (root / "META-INF/jarjar/examplelib-1.0.jar").write_bytes(_inner_jar(lib))
    (root / nested_jars.JARJAR_METADATA).write_text(_metadata("META-INF/jarjar/examplelib-1.0.jar"))
    staged = from_directory(root)
    assert staged.classes.library_count() == len(lib) and len(staged.classes) == 0
    assert staged.bundled == {"META-INF/jarjar/examplelib-1.0.jar": len(lib)}


# --- services --------------------------------------------------------------------

def test_service_loader_finds_providers_a_bundled_library_declares(tmp_path):
    own = {"a/Service": b"\xca\xfe\xba\xbe", "a/OwnImpl": b"\xca\xfe\xba\xbe"}
    inner = _inner_jar({"b/LibImpl": b"\xca\xfe\xba\xbe"}, {"a.Service": "b.LibImpl\na.OwnImpl\n"})
    jar = _mod_jar(tmp_path / "m.jar", own, {"META-INF/jarjar/b.jar": inner}, ["META-INF/jarjar/b.jar"],
                   services={"a.Service": "a.OwnImpl\n"})
    index = from_jar(jar, tmp_path / "s").classes
    # The mod's own file first, then the library's; a provider once.
    assert index.services["a.Service"] == ["a/OwnImpl", "b/LibImpl"]
    got = Machine(index)._service_call(*LOAD, None, [ClassLit("a/Service")], True)
    assert len(got) == 1 and isinstance(got[0], Obj) and got[0].cls == "__services"
    assert got[0].fields["providers"] == ("a/OwnImpl", "b/LibImpl")


def test_a_bundled_librarys_own_service_stays_unknown(tmp_path):
    # Another jar on the game's class path may provide a library's service, so
    # the "mod's own service" rule doesn't widen to bundled libraries.
    inner = _inner_jar({"x/Service": b"\xca\xfe\xba\xbe", "x/Impl": b"\xca\xfe\xba\xbe"}, {"x.Service": "x.Impl\n"})
    jar = _mod_jar(tmp_path / "m.jar", {"a/A": b"\xca\xfe\xba\xbe"}, {"META-INF/jarjar/x.jar": inner},
                   ["META-INF/jarjar/x.jar"])
    index = from_jar(jar, tmp_path / "s").classes
    assert index.services["x.Service"] == ["x/Impl"]
    assert Machine(index)._service_call(*LOAD, None, [ClassLit("x/Service")], True) == [UNKNOWN]


# --- pinned library jars ------------------------------------------------------------

def test_a_library_jars_jarjar_jars_and_services_are_read(tmp_path, lib):
    first = dict(list(lib.items())[:2])
    rest = dict(list(lib.items())[2:])
    with zipfile.ZipFile(tmp_path / "lib.jar", "w") as zf:
        for name, raw in first.items():
            zf.writestr(name + ".class", raw)
        zf.writestr("META-INF/services/a.Service", "com.example.lib.LibBlock\n")
        zf.writestr("META-INF/jarjar/inner.jar", _inner_jar(rest, {"a.Service": "com.example.lib.LibPlateBlock\n"}))
        zf.writestr("META-INF/jarjar/unlisted.jar", _inner_jar({"z/Z": b"\xca\xfe\xba\xbe"}))
        zf.writestr(nested_jars.JARJAR_METADATA, _metadata("META-INF/jarjar/inner.jar"))
    assert libraries.classes(tmp_path / "lib.jar") == lib
    index = ClassIndex({"a/Service": b"\xca\xfe\xba\xbe"})
    index.add_services({"META-INF/services/a.Service": b"a.Own\n"})
    libraries.attach(index, [tmp_path / "lib.jar"])
    assert index.library_count() == 4 and index.get("z/Z") is None
    assert index.services["a.Service"] == ["a/Own", "com/example/lib/LibBlock", "com/example/lib/LibPlateBlock"]


def test_a_nested_jar_over_the_member_bound_is_skipped(tmp_path, monkeypatch, own, lib):
    jar = _mod_jar(tmp_path / "m.jar", own, {"META-INF/jarjar/l.jar": _inner_jar(lib)}, ["META-INF/jarjar/l.jar"])
    monkeypatch.setattr(nested_jars, "MAX_MEMBERS", 2)
    assert from_jar(jar, tmp_path / "s").classes.library_count() == 0
