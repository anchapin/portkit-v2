"""The generic station kit (#245): namespace-free runtime helpers shipped beside
every station runtime, and the guard that every relative import a shipped
script makes is shipped too (portkit.converters.station_kit)."""
import re
from importlib import resources

import pytest

from portkit.converters import station_kit, stations
from portkit.converters.station_kit import FORMS, KIT_FILES, unresolved_imports
from portkit.pipeline import convert

from test_cooking_pot import _pot_mod, reference  # noqa: F401  (fixture)

RUNTIME = resources.files("portkit.runtime")
# Adapter runtimes (adapters/<name>/runtime/, #245 pick 6a) ship in the same
# scripts/portkit/ directory as the core runtime, so one name space for both.
ADAPTER_RUNTIMES = [resources.files(f"portkit.adapters.{name}").joinpath("runtime")
                    for name in ("farmersdelight", "waystones")]
_IMPORT = re.compile(r'from\s+"\./([^"]+)"')


def _runtime_file(name: str):
    for root in (RUNTIME, *ADAPTER_RUNTIMES):
        if root.joinpath(name).is_file():
            return root.joinpath(name)
    raise FileNotFoundError(name)


def _imports(name: str) -> set[str]:
    return set(_IMPORT.findall(_runtime_file(name).read_text(encoding="utf-8")))


def _closure(names) -> set[str]:
    seen, todo = set(), list(names)
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        todo.extend(_imports(name))
    return seen


# What each converter ships together (the station converters + KIT_FILES,
# waystones.py + FORMS, books.py + FORMS, blocks.py's toggle runtime alone).
SHIPPED_SETS = {
    "cutting board": {"cutting_board.js", "cutting_board_core.js", *KIT_FILES},
    "cooking pot": {"cooking_pot.js", "cooking_pot_core.js", *KIT_FILES},
    "stove": {"stove.js", "stove_core.js", *KIT_FILES},
    "skillet": {"skillet.js", "skillet_core.js", *KIT_FILES},
    "feasts": {"feast.js", "feast_core.js", *KIT_FILES},
    "waystones": {"waystone.js", "waystone_core.js", FORMS, *KIT_FILES},
    "books": {"book.js", "book_core.js", FORMS},
    "toggle": {"toggle.js"},
}


@pytest.mark.parametrize("label", sorted(SHIPPED_SETS))
def test_each_shipped_set_satisfies_its_own_imports(label):
    shipped = SHIPPED_SETS[label]
    assert _closure(shipped) == shipped


def test_kit_files_import_nothing_relative_but_each_other():
    assert _imports("station_core.js") == set()
    assert _imports("station_storage.js") == set()
    assert _imports(FORMS) == set()


def test_unresolved_imports_names_each_missing_target():
    files = {
        "scripts/portkit/main.js": 'import { a } from "./a.js";\nimport "./side.js";\nimport x from "./data/t.js";\n',
        "scripts/portkit/a.js": 'import { world } from "@minecraft/server";\nimport { b } from "./b.js";\n',
        "scripts/portkit/data/t.js": "export default {};\n",
        "blocks/x.json": {"format_version": "1.21.90"},
        "texts/en_US.lang": 'import { nope } from "./nope.js";',
    }
    assert unresolved_imports(files) == [
        "scripts/portkit/a.js -> scripts/portkit/b.js",
        "scripts/portkit/main.js -> scripts/portkit/side.js",
    ]
    files["scripts/portkit/b.js"] = "export const b = 1;\n"
    files["scripts/portkit/side.js"] = ""
    assert unresolved_imports(files) == []


def test_unresolved_imports_follows_parent_paths():
    files = {"scripts/portkit/data/t.js": 'import { k } from "../kit.js";\n'}
    assert unresolved_imports(files) == []  # "../" is not a "./" import: not checked
    files = {"scripts/portkit/sub/t.js": 'import { k } from "./../kit.js";\n'}
    assert unresolved_imports(files) == ["scripts/portkit/sub/t.js -> scripts/portkit/kit.js"]


def test_stations_reexports_the_kit():
    for name in ("FacingBlock", "Overlay", "DerivedTexture", "SCRIPT_FORMAT", "ENTRY", "runtime_source"):
        assert getattr(stations, name) is getattr(station_kit, name)
    assert stations._js_module is station_kit.js_module


def test_conversion_ships_the_kit_beside_a_station(tmp_path, reference):  # noqa: F811
    result = convert(_pot_mod(tmp_path), tmp_path / "out", emit_addon=False)
    scripts = tmp_path / "out/behavior_pack/scripts/portkit"
    for name in KIT_FILES:
        assert (scripts / name).read_text() == station_kit.runtime_source(name)
    assert not (scripts / FORMS).exists()  # no runtime here shows a form
    assert result.report.ok, result.report.errors


def test_conversion_fails_when_a_shipped_script_lacks_an_import(tmp_path, reference, monkeypatch):  # noqa: F811
    monkeypatch.setattr(stations, "KIT_FILES", ("station_storage.js",))
    with pytest.raises(RuntimeError, match=r"station_core\.js"):
        convert(_pot_mod(tmp_path), tmp_path / "out", emit_addon=False)
