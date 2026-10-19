"""Dependency jars read with a mod (#280, portkit.libraries).

The class files under tests/data/libcode are javac 21 output (build.sh): an
example library (lib/: a module base class, a registry, a plate and a block
whose constructors register themselves by name, Zeta's shape) and an example
mod (src/: a module building its blocks in an instance ``register(event)``
method, and its own plate overriding what presses it, Quark's shape).
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from portkit import blockcode, libraries
from portkit.bytecode import ClassIndex
from portkit.converters import doors
from portkit.corpus import CorpusError

DATA = Path(__file__).parent / "data" / "libcode"
NAMES = ["lib_stone_plate", "lib_lamp", "lib_players_plate"]


def _entries(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix()[:-6]: p.read_bytes() for p in root.rglob("*.class")}


def _jar(path: Path, entries: dict[str, bytes], nested: dict[str, dict] | None = None) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name + ".class", data)
        for jar_name, inner in (nested or {}).items():
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as iz:
                for name, data in inner.items():
                    iz.writestr(name + ".class", data)
            zf.writestr(f"META-INF/jars/{jar_name}", buf.getvalue())
    return path


@pytest.fixture()
def own():
    return _entries(DATA / "classes")


@pytest.fixture()
def lib():
    return _entries(DATA / "library")


# --- the class index -----------------------------------------------------------

def test_library_classes_are_found_by_name_but_never_listed(own, lib):
    index = ClassIndex(own, lib)
    assert len(index) == len(own) == 2
    assert index.names() == sorted(own)
    assert index.library_count() == 4
    assert index.get("com/example/lib/LibPlateBlock") is not None
    assert index.raw("com/example/lib/LibPlateBlock") is None
    assert index.is_library("com/example/lib/LibPlateBlock")
    assert not index.is_library("com/example/libmod/PlateModule")


def test_the_mods_own_class_wins_over_a_librarys(own, lib):
    index = ClassIndex(own)
    clash = {"com/example/libmod/PlateModule": lib["com/example/lib/LibModule"], **lib}
    assert index.add_libraries(clash) == 4
    assert not index.is_library("com/example/libmod/PlateModule")
    assert index.get("com/example/libmod/PlateModule").name == "com/example/libmod/PlateModule"


def test_library_jar_and_its_nested_jars_are_read(tmp_path, lib):
    first = dict(list(lib.items())[:2])
    rest = dict(list(lib.items())[2:])
    jar = _jar(tmp_path / "lib.jar", first, {"inner.jar": rest})
    assert libraries.classes(jar) == lib
    index = ClassIndex({})
    notes = libraries.attach(index, [jar])
    assert index.library_count() == 4 and "lib.jar (4 classes" in notes[0]
    with pytest.raises(libraries.LibraryError):
        libraries.classes(tmp_path / "missing.jar")


# --- registrations ----------------------------------------------------------------

def test_without_the_library_the_blocks_are_unread(own):
    _, reg = blockcode._registered(ClassIndex(own), NAMES)
    assert all(objs == [] for objs, _ in reg.values())
    assert "no registration of this block was found" in reg["lib_stone_plate"][1]


def test_with_the_library_a_self_registering_constructor_is_read(own, lib):
    machine, reg = blockcode._registered(ClassIndex(own, lib), NAMES)
    assert {n: [o.cls for o in objs] for n, (objs, _) in reg.items()} == {
        "lib_stone_plate": ["com/example/lib/LibPlateBlock"],
        "lib_lamp": ["com/example/lib/LibBlock"],
        "lib_players_plate": ["com/example/libmod/PlayersPlateBlock"],
    }
    assert machine.vanilla_base("com/example/libmod/PlayersPlateBlock") == \
        "net/minecraft/world/level/block/PressurePlateBlock"


def test_a_library_plate_reads_as_vanilla_and_the_mods_own_is_refused(own, lib):
    got = doors.read_code(ClassIndex(own, lib), ["lib_stone_plate", "lib_players_plate"], "plate")
    plate, players = got["lib_stone_plate"], got["lib_players_plate"]
    assert plate.verdict == "vanilla" and plate.door == ("MOBS", "STONE")
    assert plate.door_from == "BlockSetType.STONE"
    assert players.verdict == "refused"
    assert "PlayersPlateBlock#getSignalStrength" in players.why


def test_a_library_blocks_properties_are_read(own, lib):
    light = blockcode.read_light(ClassIndex(own, lib), ["lib_lamp"])
    assert light["lib_lamp"].value == 12


# --- the manifest ---------------------------------------------------------------

def test_the_repo_manifest_pins_zeta_for_quark():
    pinned = libraries.load()
    zeta = [lib for lib in pinned if lib.name == "zeta"]
    assert zeta and zeta[0].used_by == ("quark",) and len(zeta[0].sha512) == 128
    assert libraries.for_mod("quark", pinned) == zeta
    # BetterEnd gets exactly its three BCLib-family jars, and none of Quark's
    better = libraries.for_mod("betterend", pinned)
    assert sorted(lib.name for lib in better) == ["bclib", "worldweaver", "wunderlib"]
    assert all(lib.used_by == ("betterend",) and len(lib.sha512) == 128 for lib in better)
    assert libraries.for_mod("comforts", pinned) == []


def test_manifest_errors(tmp_path):
    assert libraries.load(tmp_path / "none.toml") == []
    bad = tmp_path / "bad.toml"
    bad.write_text('[[library]]\nname = "x"\n')
    with pytest.raises(CorpusError, match="lacks"):
        libraries.load(bad)
    entry = ('[[library]]\nname = "x"\nfor = "m"\nproject = "x"\nversion_id = "v"\nversion = "1"\n'
             'url = "https://e/x.jar"\nlicense = "MIT"\nsha512 = "' + "a" * 128 + '"\n')
    ok = tmp_path / "ok.toml"
    ok.write_text(entry)
    assert libraries.load(ok)[0].used_by == ("m",)
    ok.write_text(entry + entry)
    with pytest.raises(CorpusError, match="twice"):
        libraries.load(ok)


# --- the gauntlet / sample harness --------------------------------------------------

def test_run_shard_reads_a_mods_libraries_and_names_them():
    from portkit import corpus, gaps

    def mod(name):
        return corpus.Mod(name=name, project=name, version_id="v", url="https://e/x.jar",
                          sha512="a" * 128, license="MIT")

    seen = {}

    def convert(jar, work, timeout, libraries=None):
        seen[jar.stem] = libraries
        return {"status": "ok", "namespace": "x", "files": 1, "residue": 0, "coverage": 100.0,
                "valid": True, "errors": 0, "seconds": 0.1, "reasons": {}}

    def libs(m):
        if m.name == "broken":
            raise corpus.CorpusError("lib: sha512 mismatch")
        return [("lib", Path("/jars/lib.jar"))] if m.name == "withlib" else []

    doc = gaps.run_shard([mod("withlib"), mod("plain"), mod("broken")], shard="1/1", manifest="m",
                         fetch=lambda m: Path(f"/jars/{m.name}.jar"), convert=convert,
                         log=lambda *_: None, libraries=libs)
    assert seen == {"withlib": [Path("/jars/lib.jar")], "plain": None}
    assert doc["mods"]["withlib"]["libraries"] == ["lib"]
    assert "libraries" not in doc["mods"]["plain"]
    assert doc["mods"]["broken"]["status"] == "fetch_failed"
    assert "library" in doc["mods"]["broken"]["detail"]


def test_the_child_command_passes_library_jars():
    from portkit import gaps

    cmd = gaps._child_cmd(Path("m.jar"), Path("out"), Path("r.json"), [Path("a.jar"), Path("b.jar")])
    assert cmd[-5:] == ["m.jar", "out", "r.json", "a.jar", "b.jar"]
