import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pytest


@pytest.fixture
def fixtures_dir():
    return ROOT / "fixtures"


@pytest.fixture(autouse=True)
def _offline_vanilla_sounds(request, monkeypatch):
    """Point every test at a tiny vanilla sound list of our own (#124).

    The real list is Mojang's and is fetched on demand into the user's cache;
    tests must neither need the network nor change with what that cache holds.
    Corpus tests (``-m realmods``) measure against the real cache instead.
    """
    if request.node.get_closest_marker("realmods"):
        return
    monkeypatch.setenv("PORTKIT_VANILLA_SOUNDS", str(ROOT / "tests" / "data" / "vanilla_sounds.txt"))
    monkeypatch.setenv("PORTKIT_REFERENCE_CACHE", str(request.getfixturevalue("tmp_path_factory").mktemp("reference")))
