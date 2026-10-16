import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
# The Farmer's Delight test helpers (tests/adapters/farmersdelight/test_stations.py,
# test_cooking_pot.py) are imported by core tests too (#245 pick 7a moved them).
sys.path.insert(0, str(ROOT / "tests" / "adapters" / "farmersdelight"))

import pytest


@pytest.fixture
def fixtures_dir():
    return ROOT / "fixtures"


@pytest.fixture(autouse=True)
def _offline_vanilla_sounds(request, monkeypatch):
    """Point every test at a tiny vanilla sound list of our own (#124), and an
    empty reference cache, so no fetched tag data either (#160).

    The real list is Mojang's and is fetched on demand into the user's cache;
    tests must neither need the network nor change with what that cache holds.
    Corpus tests (``-m realmods``) measure against the real cache instead.
    """
    if request.node.get_closest_marker("realmods"):
        return
    monkeypatch.setenv("PORTKIT_VANILLA_SOUNDS", str(ROOT / "tests" / "data" / "vanilla_sounds.txt"))
    monkeypatch.setenv("PORTKIT_REFERENCE_CACHE", str(request.getfixturevalue("tmp_path_factory").mktemp("reference")))
    # Loader and vanilla tag data (#160): none unless a test points at its own.
    monkeypatch.delenv("PORTKIT_TAG_REFERENCE", raising=False)
    # Vanilla campfire recipes (the stove, #177): none unless a test points at its own.
    monkeypatch.delenv("PORTKIT_RECIPE_REFERENCE", raising=False)
    # Bedrock's vanilla texture atlases: none unless a test points at its own.
    monkeypatch.delenv("PORTKIT_VANILLA_TEXTURES", raising=False)
    # Bedrock's vanilla item ids (recipe unlocks, #260): none unless a test points at its own.
    monkeypatch.delenv("PORTKIT_VANILLA_ITEMS", raising=False)
    # Java -> Bedrock vanilla item ids (#261): none unless a test points at its own.
    monkeypatch.delenv("PORTKIT_JAVA_ITEMS", raising=False)


@pytest.fixture(autouse=True)
def _no_llm_retries(monkeypatch):
    """Provider clients retry transient failures with backoff (#137). Tests
    that script a failure expect to see it, at once; the retry tests pass
    their own RetryPolicy."""
    monkeypatch.setenv("PORTKIT_LLM_MAX_RETRIES", "0")
