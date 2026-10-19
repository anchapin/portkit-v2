"""Loader entry classes in the closed world (#280, portkit.entrypoints and
portkit.blockcode's census).

The class files under tests/data/entrycode are javac 21 output (build.sh): an
example mod (Quark's shape: its @Mod class holds a hub in a static final) over
an example library (Zeta's shape: each hub builds its own variant registry,
and a module's register method gets the registry from the event it is
handed). The library has two entry classes: one that makes no hub of its own
(the shared case) and one that builds a second hub in its constructor
(ZetaModForge's shape, the separate case). Which of them is an entry class is
only what the loader metadata given to the index says.
"""
from __future__ import annotations

import json
from pathlib import Path

from portkit import blockcode, entrypoints
from portkit.bytecode import ClassIndex, parse

DATA = Path(__file__).parent / "data" / "entrycode"
HUB = "com/example/elib/Hub"
VARIANTS = "com/example/elib/Variants"


def _entries(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix()[:-6]: p.read_bytes() for p in root.rglob("*.class")}


def _toml(*ids: str) -> bytes:
    return ("modLoader = \"javafml\"\n" + "".join(f"[[mods]]\nmodId = \"{i}\"\n" for i in ids)).encode()


def _index(lib_meta: dict | None = None, reflect: bool = False) -> ClassIndex:
    lib = _entries(DATA / "library")
    if reflect:
        lib.update(_entries(DATA / "reflect"))
    index = ClassIndex(_entries(DATA / "classes"), lib)
    index.entry_meta = [{"META-INF/neoforge.mods.toml": _toml("emod")}]
    if lib_meta is not None:
        index.entry_meta.append(lib_meta)
    return index


SHARED = {"META-INF/neoforge.mods.toml": _toml("elib_shared")}
SEPARATE = {"META-INF/neoforge.mods.toml": _toml("elib_separate")}


def _read(index: ClassIndex, names=("stone_vertical_slab",)):
    return blockcode._registered(index, list(names))


def test_mod_annotations_are_parsed():
    cf = parse((DATA / "classes/com/example/emod/EMod.class").read_bytes())
    assert cf.annotations == {"Lnet/neoforged/fml/common/Mod;": {"value": "emod"}}


def test_entry_classes_come_from_the_metadata_and_the_mod_annotation():
    found = entrypoints.entry_classes(_index(SEPARATE).entry_meta, _index(SEPARATE))
    assert [(e.name, e.once) for e in found] == [
        ("com/example/elib/SeparateLibMod", True), ("com/example/emod/EMod", True)]
    # SharedLibMod's mod id isn't declared: it is no entry class.
    assert "com/example/elib/SharedLibMod" not in {e.name for e in found}


def test_shared_registry_one_hub_in_the_closed_world_is_read():
    machine, reg = _read(_index(SHARED))
    assert machine.census_entries == {"com/example/emod/EMod", "com/example/elib/SharedLibMod"}
    assert machine.closed_why(VARIANTS) == ""
    hub = machine.statics[("com/example/emod/EMod", "HUB")]
    assert machine.sole_instance(VARIANTS) is hub.fields["variants"]
    objs, _why = reg["stone_vertical_slab"]
    assert [o.cls for o in objs] == ["com/example/elib/VerticalBlock"]


def test_separate_registries_a_second_hub_built_by_a_library_entry_class_stays_unread():
    machine, reg = _read(_index(SEPARATE))
    assert "com/example/elib/SeparateLibMod" in machine.census_entries
    # Both hubs are known objects with their own registry: not one object.
    assert machine.closed_why(VARIANTS) == ""
    assert sum(o.cls == VARIANTS for o in machine.census) == 2
    assert machine.sole_instance(VARIANTS) is None
    assert reg["stone_vertical_slab"][0] == []
    # Nor is the second hub's own name made up.
    _m, reg2 = _read(_index(SEPARATE), ["stone_upright_slab"])
    assert reg2["stone_upright_slab"][0] == []


def test_an_entry_class_constructed_on_one_side_only_is_not_run_and_leaves_the_census_open():
    client = {"fabric.mod.json": json.dumps(
        {"entrypoints": {"client": ["com.example.elib.SeparateLibMod"]}}).encode()}
    machine, reg = _read(_index(client))
    assert "com/example/elib/SeparateLibMod" not in machine.census_entries
    assert "the loader may construct com.example.elib.SeparateLibMod" in machine.closed_why(VARIANTS)
    assert reg["stone_vertical_slab"][0] == []


def test_a_class_nothing_constructs_has_no_objects():
    # SeparateLibMod isn't declared and nothing does new SeparateLibMod():
    # its constructor's hub is never made, so the one hub is still the only one.
    machine, _reg = _read(_index(None))
    assert machine.closed_why("com/example/elib/SeparateLibMod") == ""
    assert machine.sole_instance(VARIANTS) is not None


def test_reflective_instantiation_anywhere_leaves_every_class_open():
    machine, reg = _read(_index(SHARED, reflect=True))
    assert "makes objects of a class it is handed" in machine.closed_why(VARIANTS)
    assert reg["stone_vertical_slab"][0] == []


def test_without_loader_metadata_nothing_is_constructed():
    index = _index(SHARED)
    index.entry_meta = []
    machine, reg = _read(index)
    assert machine.census_entries == frozenset()
    assert reg["stone_vertical_slab"][0] == []


def test_a_class_made_by_a_method_the_game_may_call_any_number_of_times_is_open():
    machine, _reg = _read(_index(SHARED))
    assert "nothing bounds how often" in machine.closed_why("com/example/elib/HubEvent")


def test_fabric_entrypoints_count_one_instance_per_reference():
    meta = {"fabric.mod.json": json.dumps({"entrypoints": {
        "main": ["com.example.elib.SharedLibMod", {"adapter": "kotlin", "value": "com.example.K"}],
        "client": ["com.example.elib.SeparateLibMod", "com.example.elib.SharedLibMod"],
        "server": ["com.example.elib.Registrar::register"],
    }}).encode()}
    found = {e.name: e.once for e in entrypoints.entry_classes([meta], _index())}
    # SharedLibMod is referenced twice (main and client): two instances on a client.
    assert found == {"com/example/elib/SharedLibMod": False, "com/example/elib/SeparateLibMod": False}


def test_quilt_init_and_a_one_side_mod_annotation():
    meta = {"quilt.mod.json": json.dumps({"quilt_loader": {"entrypoints": {
        "init": "com.example.elib.SharedLibMod"}}}).encode()}
    assert [(e.name, e.once) for e in entrypoints.entry_classes([meta], _index())] == [
        ("com/example/elib/SharedLibMod", True)]
    assert entrypoints._both_sides(None)
    assert entrypoints._both_sides((("Lnet/neoforged/api/distmarker/Dist;", "CLIENT"),
                                    ("Lnet/neoforged/api/distmarker/Dist;", "DEDICATED_SERVER")))
    assert not entrypoints._both_sides((("Lnet/neoforged/api/distmarker/Dist;", "CLIENT"),))
