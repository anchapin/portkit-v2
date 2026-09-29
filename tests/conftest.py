import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pytest


@pytest.fixture
def fixtures_dir():
    return ROOT / "fixtures"
