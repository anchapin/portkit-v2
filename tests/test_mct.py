"""Mojang's mct validate as a second, report-only oracle (#113).

None of this needs Node: the parser runs on a captured ``mct validate --json``
(tests/data/mct_validate_sample.json, mct 0.20.0 on the simple_block_mod
fixture's output, .mcaddon included), and ``run`` is exercised against a fake
``mct`` that prints that capture.
"""
import json
import shutil
import stat
import sys
from pathlib import Path

import pytest

from portkit import cli
from portkit.validate import mct

DATA = Path(__file__).parent / "data" / "mct_validate_sample.json"


def _sample() -> str:
    return DATA.read_text()


def test_parse_keeps_findings_and_drops_bookkeeping():
    summary = mct.parse(_sample())
    assert summary.by_severity == {"error": 4, "warning": 3, "recommendation": 3}
    assert summary.by_rule["error"] == {"CPACKICON": 4}
    assert summary.by_rule["warning"] == {"JSON": 2, "UNLINK": 1}
    assert summary.by_rule["recommendation"] == {"MINENGINEVER": 2, "FORMATVER": 1}
    # info / testPass / testFail / featureAggregate / unknown are not findings
    assert {f.severity for f in summary.findings} <= set(mct.SEVERITIES)


def test_parse_drops_findings_inside_an_archive():
    raw = json.loads(_sample())
    in_archive = [
        i for p in raw["projects"] for i in p["items"]
        if i["type"] in mct.SEVERITIES and "#" in (i.get("path") or "")
    ]
    assert in_archive  # the capture has the .mcaddon's duplicates in it
    paths = [f.path for f in mct.parse(raw).findings if f.path]
    assert paths and not any("#" in p for p in paths)


def test_top_groups_messages_that_differ_only_in_specifics():
    top = mct.parse(_sample()).top()
    assert top[0]["severity"] == "error"  # errors first, whatever their count
    json_rows = [r for r in top if r["rule"] == "JSON"]
    assert len(json_rows) == 1 and json_rows[0]["count"] == 2
    assert "string value found, but a array is required" in json_rows[0]["message"]
    assert "copper" not in json_rows[0]["message"]
    assert all("1.20" not in r["message"] for r in top)


def test_parse_tolerates_log_lines_before_the_json():
    summary = mct.parse("Minecraft Creator Tools v0.20.0\nloading...\n" + _sample())
    assert summary.by_severity["error"] == 4


@pytest.mark.parametrize("text", ["", "no json here", "{not json", '{"command": "validate"}'])
def test_parse_refuses_what_is_not_a_validate_report(text):
    with pytest.raises(mct.MctError):
        mct.parse(text)


def test_render_and_aggregate():
    one = mct.parse(_sample())
    text = mct.render({"a": one, "b": one})
    assert "a" in text and "b" in text and "[CPACKICON]" in text
    assert mct.aggregate({"a": one, "b": one}).by_severity["error"] == 8
    assert mct.render({}) == ""


def test_run_is_none_when_mct_is_absent(monkeypatch, tmp_path):
    monkeypatch.delenv("PORTKIT_MCT", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))  # nothing called mct here
    assert mct.find_mct() is None
    assert mct.run(tmp_path) is None


def _fake_mct(tmp_path: Path, exit_code: int = 4, stdout: str | None = None) -> Path:
    """A stand-in mct: records its argv and what -i holds, prints the capture."""
    capture = tmp_path / "capture.json"
    capture.write_text(_sample() if stdout is None else stdout)
    log = tmp_path / "fake-mct.log"
    script = tmp_path / "bin" / "mct"
    script.parent.mkdir()
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        "stage = args[args.index('-i') + 1]\n"
        f"open({str(log)!r}, 'w').write(json.dumps({{'argv': args, 'stage': sorted(os.listdir(stage))}}))\n"
        f"sys.stdout.write(open({str(capture)!r}).read())\n"
        f"sys.exit({exit_code})\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return script


def _tree(tmp_path: Path) -> Path:
    tree = tmp_path / "out"
    for name in ("behavior_pack", "resource_pack"):
        (tree / name).mkdir(parents=True)
        (tree / name / "manifest.json").write_text("{}")
    (tree / "unhandled.json").write_text("[]")
    (tree / "mod.mcaddon").write_bytes(b"PK")
    return tree


def test_run_validates_only_the_packs_and_reads_past_the_exit_code(tmp_path):
    exe = _fake_mct(tmp_path)
    summary = mct.run(_tree(tmp_path), exe=str(exe))
    assert summary.by_severity["error"] == 4  # exit 4 is "found errors", not a crash
    log = json.loads((tmp_path / "fake-mct.log").read_text())
    assert log["stage"] == ["behavior_pack", "resource_pack"]  # no sidecars, no .mcaddon
    assert log["argv"][:2] == ["validate", "main"]
    assert "--json" in log["argv"] and "--offline" in log["argv"]


def test_run_names_a_crash(tmp_path):
    exe = _fake_mct(tmp_path, exit_code=1, stdout="")
    with pytest.raises(mct.MctError, match="exit 1"):
        mct.run(_tree(tmp_path), exe=str(exe))


def _one_fixture(tmp_path: Path, fixtures_dir: Path) -> Path:
    root = tmp_path / "fixtures"
    shutil.copytree(fixtures_dir / "simple_block_mod", root / "simple_block_mod")
    return root


def test_eval_mct_skips_with_a_note_when_mct_is_absent(tmp_path, fixtures_dir, monkeypatch, capsys):
    monkeypatch.delenv("PORTKIT_MCT", raising=False)
    monkeypatch.setattr(mct, "find_mct", lambda: None)
    root = _one_fixture(tmp_path, fixtures_dir)
    out = tmp_path / "eval.json"
    code = cli.main(["eval", "--fixtures", str(root), "--no-baseline", "--mct", "--json", str(out)])
    assert code == 0
    assert "`mct` is not on PATH" in capsys.readouterr().out
    data = json.loads(out.read_text())
    assert data["mct"]["available"] is False and data["mct"]["trees"] == {}
    assert data["rows"][0]["name"] == "simple_block_mod"


def test_eval_mct_reports_but_never_fails_the_run(tmp_path, fixtures_dir, monkeypatch, capsys):
    exe = _fake_mct(tmp_path)
    monkeypatch.setenv("PORTKIT_MCT", str(exe))
    root = _one_fixture(tmp_path, fixtures_dir)
    out = tmp_path / "eval.json"
    code = cli.main(["eval", "--fixtures", str(root), "--no-baseline", "--mct", "--json", str(out)])
    assert code == 0  # 4 mct errors, still green: report-only
    printed = capsys.readouterr().out
    assert "[CPACKICON]" in printed and "report-only" in printed
    block = json.loads(out.read_text())["mct"]
    assert block["available"] and block["report_only"]
    assert block["trees"]["simple_block_mod"]["counts"]["error"] == 4
    assert block["total"]["by_rule"]["error"] == {"CPACKICON": 4}


def test_eval_without_mct_never_looks_for_it(tmp_path, fixtures_dir, monkeypatch):
    def boom():
        raise AssertionError("looked for mct without --mct")
    monkeypatch.setattr(mct, "find_mct", boom)
    root = _one_fixture(tmp_path, fixtures_dir)
    assert cli.main(["eval", "--fixtures", str(root), "--no-baseline"]) == 0
