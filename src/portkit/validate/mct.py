"""A second oracle: Mojang's Minecraft Creator Tools (#113).

Everything else in portkit asks our own validator whether a pack is good. If
the validator has a blind spot, the converter can ship that bug forever and
every gate stays green, because both were written from the same reading of the
Bedrock docs. ``mct validate`` is Mojang's own rule set (``@minecraft/creator-tools``
on npm, MIT, Node 22+), so running it over the same output is a differential
check: what it flags and we don't is a validator gap or a converter bug we
can't currently see.

It is optional and report-only. Nothing here imports Node or fails a gate:
``run`` returns ``None`` when ``mct`` isn't on PATH, and the summary is
numbers for a person (or a later ratchet) to read.

Two details of how mct reads a folder shape ``run``:

* It validates every file under the folder it's given, so our sidecars
  (``unhandled.json`` and friends) would show up as "Unknown JSON file found",
  and an ``.mcaddon`` next to the packs is unzipped and validated a second time.
  So it runs on a staging folder holding symlinks to just the two packs.
* It writes report files (csv, html, json) to ``-o`` or ``./out``, so the
  output folder and working directory are a temp dir.

Accepting Mojang's EULA is the caller's decision, not this module's: CI runs
``mct eula --accept`` once (see ``.github/workflows/real-mods.yml``).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# mct item types that are findings, most severe first. The rest ("info",
# "testPass", "testFail", "featureAggregate", "unknown") are bookkeeping:
# testFail only restates the count of the errors that follow it.
SEVERITIES = ("error", "warning", "recommendation")
PACK_DIRS = ("behavior_pack", "resource_pack")
DEFAULT_TIMEOUT = 600  # seconds per tree; the largest corpus mod takes ~30s
_ENV_EXE = "PORTKIT_MCT"  # point at a specific mct binary instead of PATH


class MctError(RuntimeError):
    """mct ran but gave us nothing we can read."""


def find_mct() -> str | None:
    """The mct executable, from ``$PORTKIT_MCT`` or PATH, or None."""
    explicit = os.environ.get(_ENV_EXE)
    if explicit:
        return shutil.which(explicit) or (explicit if Path(explicit).is_file() else None)
    return shutil.which("mct")


@dataclass(frozen=True)
class MctFinding:
    severity: str
    rule: str  # mct's generatorId, e.g. CPACKICON, UNLINK, JSON
    message: str
    path: str | None = None
    data: object = None


@dataclass
class MctSummary:
    """Counts by severity and by rule, plus the most common messages."""

    findings: list[MctFinding] = field(default_factory=list)

    @property
    def by_severity(self) -> dict[str, int]:
        counts = Counter(f.severity for f in self.findings)
        return {s: counts.get(s, 0) for s in SEVERITIES}

    @property
    def by_rule(self) -> dict[str, dict[str, int]]:
        """{severity: {rule: count}}, each sorted by count, largest first."""
        out: dict[str, dict[str, int]] = {}
        for severity in SEVERITIES:
            counts = Counter(f.rule for f in self.findings if f.severity == severity)
            out[severity] = dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
        return out

    def top(self, n: int = 10) -> list[dict]:
        """The n most frequent (severity, rule, message) kinds."""
        counts = Counter((f.severity, f.rule, _shape(f)) for f in self.findings)
        rank = {s: i for i, s in enumerate(SEVERITIES)}
        ordered = sorted(counts.items(), key=lambda kv: (rank[kv[0][0]], -kv[1], kv[0][1], kv[0][2]))
        return [
            {"severity": s, "rule": r, "message": m, "count": c}
            for (s, r, m), c in ordered[:n]
        ]

    def to_dict(self, top: int = 10) -> dict:
        return {
            "counts": self.by_severity,
            "by_rule": self.by_rule,
            "top": self.top(top),
        }


def _shape(finding: MctFinding) -> str:
    """A finding's message with its specifics blanked, so like groups with like.

    Version numbers become N. A schema finding's message is just "Structure
    issue" and the substance is in its data, so that comes along with the
    quoted JSON path and the offending value blanked.
    """
    text = re.sub(r"\d+(?:\.\d+)+", "N", finding.message).strip()
    if finding.rule == "JSON" and isinstance(finding.data, str):
        detail = re.sub(r'"[^"]*"', '"…"', finding.data)
        detail = re.sub(r":\s*\S+ - ", ": … - ", detail)
        text = f"{text}: {detail.strip()}"
    return text


def parse(payload: dict | str) -> MctSummary:
    """Findings from ``mct validate --json`` output.

    Items inside an archive (``foo.mcaddon#/behavior_pack/...``) are dropped:
    they repeat the loose packs finding for finding.
    """
    if isinstance(payload, str):
        payload = _decode(payload)
    if not isinstance(payload, dict) or not isinstance(payload.get("projects"), list):
        raise MctError("mct output has no 'projects' list")
    summary = MctSummary()
    for project in payload["projects"]:
        for item in (project or {}).get("items") or ():
            if not isinstance(item, dict) or item.get("type") not in SEVERITIES:
                continue
            path = item.get("path")
            if isinstance(path, str) and "#" in path:
                continue
            summary.findings.append(
                MctFinding(
                    severity=item["type"],
                    rule=str(item.get("generatorId") or "?"),
                    message=str(item.get("message") or ""),
                    path=path if isinstance(path, str) else None,
                    data=item.get("data"),
                )
            )
    return summary


def _decode(text: str) -> dict:
    """The JSON document in mct's stdout, tolerating log lines before it."""
    start = text.find("{")
    if start < 0:
        raise MctError("mct printed no JSON")
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError as exc:
        raise MctError(f"mct printed unreadable JSON: {exc}") from exc


def run(
    tree: Path,
    *,
    exe: str | None = None,
    suite: str = "main",
    timeout: float = DEFAULT_TIMEOUT,
) -> MctSummary | None:
    """``mct validate`` over a converted tree's packs. None when mct is absent.

    mct exits non-zero whenever it finds an error, so the exit code says
    nothing about whether it ran; the JSON on stdout does. Raises MctError
    when there is none.
    """
    exe = exe or find_mct()
    if exe is None:
        return None
    tree = Path(tree)
    with tempfile.TemporaryDirectory(prefix="portkit-mct-") as tmp:
        stage = Path(tmp) / "project"
        stage.mkdir()
        for name in PACK_DIRS:
            if (tree / name).is_dir():
                (stage / name).symlink_to((tree / name).resolve(), target_is_directory=True)
        cmd = [exe, "validate", suite, "-i", str(stage), "-o", str(Path(tmp) / "out"),
               "--json", "--offline"]
        try:
            proc = subprocess.run(
                cmd, cwd=tmp, capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise MctError(f"mct validate timed out after {timeout:g}s") from exc
        except OSError as exc:
            raise MctError(f"cannot run {exe}: {exc}") from exc
    try:
        return parse(proc.stdout)
    except MctError as exc:
        tail = (proc.stderr or "").strip().splitlines()[-3:]
        detail = f" (exit {proc.returncode}: {' / '.join(tail)})" if tail else f" (exit {proc.returncode})"
        raise MctError(f"{exc}{detail}") from exc


def aggregate(summaries: dict[str, MctSummary]) -> MctSummary:
    """Every mod's findings in one summary, for the corpus totals."""
    total = MctSummary()
    for summary in summaries.values():
        total.findings.extend(summary.findings)
    return total


def render(summaries: dict[str, MctSummary], *, top: int = 10) -> str:
    """A per-mod table and the corpus-wide top findings, as plain text."""
    if not summaries:
        return ""
    width = max(len(n) for n in summaries)
    lines = [f"{'mct validate'.ljust(width)}  errors  warnings  recommendations"]
    for name, summary in summaries.items():
        c = summary.by_severity
        lines.append(
            f"{name.ljust(width)}  {c['error']:6d}  {c['warning']:8d}  {c['recommendation']:15d}"
        )
    total = aggregate(summaries)
    lines.append("top mct findings across all trees:")
    for row in total.top(top):
        lines.append(f"  {row['count']:6d}  {row['severity']:<14} [{row['rule']}] {row['message']}")
    return "\n".join(lines)
