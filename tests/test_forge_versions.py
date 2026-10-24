"""A Forge jar that declares no minecraft dependency takes the game version its
forge dependency's lower bound is built for, read from Forge's own release
list (#364)."""
from __future__ import annotations

import io
import json

import pytest

from portkit.data import forge_versions
from portkit.meta import parse as parse_metadata

_METADATA = b"""<?xml version="1.0" encoding="UTF-8"?>
<metadata><groupId>net.minecraftforge</groupId><artifactId>forge</artifactId><versioning><versions>
<version>1.20.1-47.1.3</version><version>1.20.1-47.4.10</version>
<version>1.20-46.0.14</version><version>1.20.3-49.0.2</version><version>1.20.4-49.2.13</version>
<version>1.12.2-14.23.5.2860</version><version>1.21.1-52.1.0</version><version>26.4-67.0.1</version>
</versions></versioning></metadata>"""


def test_derive_keeps_majors_that_name_one_game_version():
    table = json.loads(forge_versions.derive(_METADATA))
    assert table["majors"] == {"46": "1.20", "47": "1.20.1", "52": "1.21.1"}
    assert table["ambiguous"] == {"49": ["1.20.3", "1.20.4"]}  # never picked
    assert table["source"] == forge_versions.URL  # 14 (before 25) and 67 (after LAST_MAJOR) are out


def test_derive_refuses_a_file_with_no_releases():
    with pytest.raises(ValueError):
        forge_versions.derive(b"<metadata/>")


@pytest.fixture
def table(tmp_path, monkeypatch):
    path = tmp_path / "forge.json"
    path.write_bytes(forge_versions.derive(_METADATA))
    monkeypatch.setenv("PORTKIT_FORGE_VERSIONS", str(path))
    return path


@pytest.mark.parametrize("range_, expected", [
    ("[47.1.3,)", "1.20.1"),
    ("[47,)", "1.20.1"),
    ("47.1.3", "1.20.1"),
    ("[46.0.1,47)", "1.20"),
    ("[49.0.2,)", None),        # 49 spans 1.20.3 and 1.20.4
    ("[48,)", None),            # not in the table
    ("(,48)", None),            # no lower bound
    ("*", None),
    ("(47.1,)", None),          # an exclusive bound isn't read
])
def test_minecraft_for(table, range_, expected):
    assert forge_versions.minecraft_for(range_) == expected


def _forge(deps: str) -> bytes:
    return f'modLoader="javafml"\nloaderVersion="[47,)"\n[[mods]]\nmodId="x"\nversion="1"\n{deps}'.encode()


def test_forge_dependency_names_the_game_version_as_a_noted_default(table):
    meta = parse_metadata({"META-INF/mods.toml": _forge(
        '[[dependencies.x]]\nmodId="forge"\nmandatory=true\nversionRange="[47.1.3,)"\n')}, "")
    assert meta.minecraft is None  # stays as declared
    assert meta.loader_minecraft == "1.20.1"
    assert any("DEFAULT inferred from its forge dependency '[47.1.3,)'" in n for n in meta.notes)


def test_a_declared_minecraft_dependency_wins_for_forge(table):
    meta = parse_metadata({"META-INF/mods.toml": _forge(
        '[[dependencies.x]]\nmodId="forge"\nversionRange="[47.1.3,)"\n'
        '[[dependencies.x]]\nmodId="minecraft"\nversionRange="[1.20,1.21)"\n')}, "")
    assert meta.minecraft == "1.20"
    assert meta.loader_minecraft is None
    assert not any("DEFAULT" in n for n in meta.notes)


def test_no_table_no_guess(monkeypatch):
    monkeypatch.delenv("PORTKIT_FORGE_VERSIONS", raising=False)
    meta = parse_metadata({"META-INF/mods.toml": _forge(
        '[[dependencies.x]]\nmodId="forge"\nversionRange="[47.1.3,)"\n')}, "")
    assert meta.loader_minecraft is None
    assert any("Forge release table isn't cached" in n for n in meta.notes)


def test_a_major_spanning_two_versions_is_not_guessed(table):
    meta = parse_metadata({"META-INF/mods.toml": _forge(
        '[[dependencies.x]]\nmodId="forge"\nversionRange="[49.0.2,)"\n')}, "")
    assert meta.loader_minecraft is None
    assert not any("DEFAULT" in n for n in meta.notes)


def test_fetch_checks_the_pin(tmp_path, monkeypatch):
    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    opener = lambda request, timeout: _Resp(_METADATA)  # noqa: E731
    with pytest.raises(forge_versions.ReferenceDataError, match="re-pin"):
        forge_versions.fetch(tmp_path, opener=opener)
    monkeypatch.setattr(forge_versions, "SHA256", forge_versions._sha256(forge_versions.derive(_METADATA)))
    path, downloaded = forge_versions.fetch(tmp_path, opener=opener)
    assert downloaded and forge_versions.cached(tmp_path) == path
    assert forge_versions.fetch(tmp_path, opener=opener) == (path, False)
