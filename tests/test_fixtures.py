"""Golden-fixture parity harness. Every fixture directory becomes a test."""
import tomllib
from pathlib import Path

import pytest

from portkit.pipeline import convert

ROOT = Path(__file__).resolve().parents[1]
CASES = sorted(p for p in (ROOT / "fixtures").iterdir() if (p / "case.toml").is_file())


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_fixture(case, tmp_path):
    spec = tomllib.loads((case / "case.toml").read_text())
    result = convert(case / "input", tmp_path / "out")

    assert result.namespace == spec["namespace"]
    assert result.report.ok == spec["expect_valid"], [
        f"{f.path}: {f.message}" for f in result.report.errors
    ]
    assert len(result.unhandled) == spec["expect_unhandled"], [
        u.reason for u in result.unhandled
    ]

    expected = case / "expected"
    if not expected.is_dir():
        pytest.skip("no expected/ tree recorded for this case yet")

    produced = {
        str(p.relative_to(tmp_path / "out")): p.read_bytes()
        for p in (tmp_path / "out").rglob("*")
        if p.is_file() and p.name != "unhandled.json"
    }
    golden = {
        str(p.relative_to(expected)): p.read_bytes()
        for p in expected.rglob("*")
        if p.is_file()
    }
    assert sorted(produced) == sorted(golden)
    for relpath, content in golden.items():
        assert produced[relpath] == content, f"{relpath} differs from golden"
