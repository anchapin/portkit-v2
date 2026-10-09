"""The coverage ratchet: `portkit eval` fails when a fixture drops below its baseline."""
import json
import shutil

from portkit import baseline as bl
from portkit.cli import main


def _m(name, files, residue):
    total = files + residue
    return bl.Measured(name, files, residue, files / total * 100 if total else 100.0)


def test_equal_to_baseline_passes():
    rows = [_m("a", 9, 4)]
    regressions, notes = bl.compare(rows, json.loads(bl.dump(rows))["fixtures"])
    assert regressions == [] and notes == []


def test_coverage_drop_names_fixture_and_delta():
    base = {"a": {"coverage": 100.0, "files": 7, "residue": 0}}
    regressions, _ = bl.compare([_m("a", 7, 1)], base)
    assert len(regressions) == 1
    assert regressions[0].fixture == "a"
    assert "100.0% -> 87.5% (-12.5 pts)" in regressions[0].message


def test_silently_dropped_file_fails_even_at_full_coverage():
    """A converter that stops emitting a file without recording residue keeps 100%."""
    base = {"a": {"coverage": 100.0, "files": 7, "residue": 0}}
    regressions, _ = bl.compare([_m("a", 6, 0)], base)
    assert [r.message for r in regressions] == ["converted files 7 -> 6 (-1)"]


def test_improvement_is_a_note_not_a_failure():
    base = {"a": {"coverage": 50.0, "files": 2, "residue": 2}}
    regressions, notes = bl.compare([_m("a", 3, 1)], base)
    assert regressions == []
    assert notes and "update-baseline" in notes[0].message


def test_new_fixture_is_a_note_and_vanished_fixture_fails():
    base = {"gone": {"coverage": 100.0, "files": 1, "residue": 0}}
    regressions, notes = bl.compare([_m("new", 1, 0)], base)
    assert [n.fixture for n in notes] == ["new"]
    assert [r.fixture for r in regressions] == ["gone"]


def test_committed_baseline_covers_the_whole_corpus(fixtures_dir):
    recorded = set(bl.load(fixtures_dir / bl.BASELINE_NAME))
    corpus = {p.name for p in fixtures_dir.iterdir() if (p / "input").is_dir()}
    assert recorded == corpus


def test_eval_fails_on_regression_end_to_end(fixtures_dir, tmp_path, capsys):
    root = tmp_path / "fixtures"
    shutil.copytree(fixtures_dir / "simple_block_mod", root / "simple_block_mod")
    assert main(["eval", "--fixtures", str(root), "--update-baseline"]) == 0
    assert main(["eval", "--fixtures", str(root)]) == 0

    # Pretend the baseline was recorded when the converter emitted one more file.
    path = root / bl.BASELINE_NAME
    data = json.loads(path.read_text())
    data["fixtures"]["simple_block_mod"]["files"] += 1
    path.write_text(json.dumps(data))
    capsys.readouterr()

    assert main(["eval", "--fixtures", str(root)]) == 1
    out = capsys.readouterr().out
    assert "REGRESSION simple_block_mod: converted files" in out
    assert "(-1)" in out
