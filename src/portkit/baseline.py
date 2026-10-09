"""The coverage ratchet: a per-fixture baseline `portkit eval` must not fall below.

`portkit eval` prints how much of each fixture converts. On its own that number
can drift down unnoticed, because nothing fails until the validator does. The
baseline records, per fixture, the coverage and the number of files converted
the last time someone deliberately moved it. A run that drops either one, for
any fixture, is a regression and fails, naming the fixture and the delta.

Both numbers are checked because either can hide the other: a converter that
starts refusing a file shows up as lost coverage, but one that silently stops
emitting a file it used to handle (no residue recorded) can leave coverage at
100% while the converted file count falls.

Improvements never fail. They are reported so the author can bank them with
`portkit eval --update-baseline`. That rewrites the file from the current run,
so a deliberate step down is possible but always shows up as a diff to the
baseline in review rather than slipping through.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

BASELINE_NAME = "coverage-baseline.json"


@dataclass(frozen=True)
class Measured:
    name: str
    files: int
    residue: int
    coverage: float  # percent

    @property
    def rounded(self) -> float:
        return round(self.coverage, 1)


@dataclass(frozen=True)
class Delta:
    fixture: str
    message: str


def load(path: Path) -> dict[str, dict]:
    data = json.loads(path.read_text())
    fixtures = data.get("fixtures") if isinstance(data, dict) else None
    if not isinstance(fixtures, dict):
        raise ValueError(f"{path}: expected an object with a 'fixtures' map")
    return fixtures


def dump(rows: list[Measured]) -> str:
    fixtures = {
        r.name: {"coverage": r.rounded, "files": r.files, "residue": r.residue}
        for r in sorted(rows, key=lambda r: r.name)
    }
    return json.dumps({"fixtures": fixtures}, indent=2) + "\n"


def compare(rows: list[Measured], baseline: dict[str, dict]) -> tuple[list[Delta], list[Delta]]:
    """Return (regressions, notes). Any regression fails the build."""
    regressions: list[Delta] = []
    notes: list[Delta] = []
    seen = set()
    for row in rows:
        seen.add(row.name)
        base = baseline.get(row.name)
        if base is None:
            notes.append(Delta(row.name, "not in the baseline yet; run `portkit eval --update-baseline`"))
            continue
        base_cov = float(base.get("coverage", 0.0))
        base_files = int(base.get("files", 0))
        cov_delta = round(row.rounded - base_cov, 1)
        file_delta = row.files - base_files
        if cov_delta < 0:
            regressions.append(
                Delta(row.name, f"coverage {base_cov:.1f}% -> {row.rounded:.1f}% ({cov_delta:+.1f} pts)")
            )
        if file_delta < 0:
            regressions.append(
                Delta(row.name, f"converted files {base_files} -> {row.files} ({file_delta:+d})")
            )
        if cov_delta > 0 or file_delta > 0:
            notes.append(
                Delta(
                    row.name,
                    f"improved (coverage {cov_delta:+.1f} pts, files {file_delta:+d}); "
                    "bank it with `portkit eval --update-baseline`",
                )
            )
    for name in sorted(set(baseline) - seen):
        regressions.append(
            Delta(name, "in the baseline but missing from the corpus; remove it from the baseline if intended")
        )
    return regressions, notes
