"""The gap leaderboard (#234): which residue reasons block the most mods.

The corpus (#21) measures ~20 hand-picked mods, so gains show up where we
already looked. This module runs a *sample* of popular mods (a manifest in the
corpus format, ``fixtures/sample/mods.toml``, built by ``portkit.sample``) and
ranks the residue reasons across them:

1. ``run_shard`` converts one shard of the sample, each mod in its own child
   process with a timeout (a crash or hang costs that mod, not the run), and
   records per mod its coverage numbers and its residue grouped by
   *normalized* reason (``normalize``: ids, paths, quoted names and numbers
   blanked, so "ingredient a:b is not converted" and "ingredient c:d is not
   converted" are one gap).
2. ``leaderboard`` merges the shard files into one ranked list: for each
   reason, how many mods it blocks and how many entries and source files it
   covers, with a trend against the previous leaderboard when one is given.
3. ``render_markdown`` turns that into the page a person reads.

Nothing here changes a conversion; it only reads the residue ``convert``
returns (the same entries it writes to ``unhandled.json``).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
DEFAULT_TIMEOUT = 900.0  # seconds per mod conversion (child process)
_EXAMPLES = 3  # raw examples kept per reason
_MOD_LIST = 25  # mod names kept per reason in the leaderboard

# Kinds whose reason text is generic and whose *source directory* is the
# signal: "222 file(s) no converter claims yet" says nothing until you know it
# was data/<ns>/advancement/.
_SOURCE_KEYED = {"unowned"}

# The order matters: the e.g. lists and quoted names go first, so an id or a
# path inside them is not blanked twice into something unreadable.
_RULES: list[tuple[re.Pattern, str]] = [
    # "(e.g. a, b, c" lists, sometimes cut short without the closing paren
    (re.compile(r"\(e\.g\.[^)]*\)?"), "(e.g. …)"),
    # quoted names; an apostrophe inside a word (isn't, vanilla's) is not a quote
    (re.compile(r"(?<!\w)'[^']*'(?!\w)|\"[^\"]*\"|`[^`]*`"), "'…'"),
    # Java classes: vectorwing.farmersdelight.common.block.RopeFenceGateBlock
    (re.compile(r"\b(?:[a-z_]\w*\.){2,}[A-Z]\w*(?:\$\w+)*"), "<class>"),
    # blockstate lists: (age=0, age=1, age=2) or (facing=east,part=foot, ...)
    (re.compile(r"\((?:\w+=[\w.-]+[ ,]*)+\)"), "(<states>)"),
    # content hashes: tags-1.21.4-summary@7cffbcdad5fa
    (re.compile(r"@[0-9a-f]{7,}\b"), "@<hash>"),
    # lang: "N key(s) present in de_de but not in en_us went untranslated"
    (re.compile(r"\bpresent in \w+ but not in \w+"), "present in <locale> but not in <locale>"),
    # load conditions: "compat for create: loads only when create is installed"
    (re.compile(r"\bcompat for [\w.-]+:"), "compat for <mod>:"),
    (re.compile(r"\bwhen [\w.-]+ is installed\b"), "when <mod> is installed"),
    # namespaced ids: minecraft:stone, farmersdelight:block/stove, c:ingots/iron
    (re.compile(r"(?<![\w<])#?[a-z0-9_.-]+:[a-z0-9_./-]*[a-z0-9_]"), "<id>"),
    # paths: assets/x/models/y.json, data/ns/recipe/
    (re.compile(r"(?<![\w<])(?:[\w.-]+/)+[\w.-]*"), "<path>"),
    # a condition's arguments after its id: "(<id> immersiveengineering)"
    (re.compile(r"\(<id>(?: [\w.:<>-]+)+\)"), "(<id> …)"),
    (re.compile(r"(?<![\w<])\d+(?:\.\d+)*(?![\w>])"), "N"),
]


def normalize(reason: str) -> str:
    """A residue reason with its specifics blanked, so like groups with like."""
    text = str(reason)
    for pattern, repl in _RULES:
        text = pattern.sub(repl, text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:240]


def _source_shape(source: str) -> str:
    """data/farmersdelight/advancement/ -> data/<ns>/advancement/."""
    parts = source.split("/")
    if len(parts) > 2 and parts[0] in ("assets", "data"):
        parts[1] = "<ns>"
    return "/".join(parts)


def reason_key(kind: str, reason: str, source: str = "") -> str:
    """The leaderboard key: kind, normalized reason, and for source-keyed
    kinds the shape of the source directory."""
    key = f"{kind}: {normalize(reason)}"
    if kind in _SOURCE_KEYED and source:
        key += f" [{_source_shape(source)}]"
    return key


def group_residue(entries) -> dict[str, dict]:
    """Residue entries (report.Residue or dicts) -> {key: totals + examples}."""
    out: dict[str, dict] = {}
    for e in entries:
        kind = getattr(e, "kind", None) or (e.get("kind") if isinstance(e, dict) else None) or "unknown"
        reason = getattr(e, "reason", None) or (e.get("reason") if isinstance(e, dict) else "") or ""
        source = getattr(e, "source", None) or (e.get("source") if isinstance(e, dict) else "") or ""
        count = getattr(e, "count", None) or (e.get("count") if isinstance(e, dict) else 1) or 1
        key = reason_key(kind, reason, source)
        slot = out.setdefault(key, {"kind": kind, "reason": key.split(": ", 1)[1],
                                    "entries": 0, "files": 0, "examples": []})
        slot["entries"] += 1
        slot["files"] += int(count)
        if len(slot["examples"]) < _EXAMPLES:
            slot["examples"].append({"source": source, "reason": reason[:300]})
    return out


# --- running a shard -------------------------------------------------------

def parse_shard(text: str | None) -> tuple[int, int]:
    """"2/4" -> (2, 4); None -> (1, 1)."""
    if not text:
        return 1, 1
    m = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", text)
    if not m or not (1 <= int(m.group(1)) <= int(m.group(2))):
        raise ValueError(f"shard must look like 1/4, got {text!r}")
    return int(m.group(1)), int(m.group(2))


def shard_of(mods: list, index: int, total: int) -> list:
    """Round-robin over the manifest order, so each shard gets a spread of
    download ranks rather than all the biggest mods."""
    return [m for i, m in enumerate(mods) if i % total == index - 1]


def _child_cmd(jar: Path, out: Path, result: Path) -> list[str]:
    return [sys.executable, "-m", "portkit.gaps", "child", str(jar), str(out), str(result)]


def convert_one(jar: Path, workdir: Path, timeout: float = DEFAULT_TIMEOUT, runner=subprocess.run) -> dict:
    """Convert one jar in a child process. Returns the mod's record (without
    the manifest fields); the tree is left at workdir/out for mct."""
    out, result = workdir / "out", workdir / "result.json"
    started = time.monotonic()
    try:
        proc = runner(_child_cmd(jar, out, result), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "seconds": round(time.monotonic() - started, 1),
                "detail": f"conversion took longer than {timeout:g}s"}
    seconds = round(time.monotonic() - started, 1)
    if proc.returncode != 0 or not result.is_file():
        tail = (proc.stderr or "").strip().splitlines()
        last = tail[-1] if tail else f"exit {proc.returncode}"
        return {"status": "crashed", "seconds": seconds, "detail": last[:300],
                "exit": proc.returncode}
    record = json.loads(result.read_text())
    record["status"] = "ok"
    record["seconds"] = seconds
    return record


def _child(jar: str, out: str, result: str) -> int:
    """The child process: one conversion, numbers written to ``result``."""
    from .pipeline import convert

    res = convert(Path(jar), Path(out), emit_addon=False)
    data = {
        "namespace": res.namespace,
        "files": res.file_count,
        "residue": res.residue_count,
        "coverage": round(res.coverage, 2),
        "valid": res.report.ok,
        "errors": len(res.report.errors),
        "reasons": group_residue(res.unhandled),
    }
    Path(result).write_text(json.dumps(data))
    return 0


def run_shard(mods, *, shard: str | None = None, manifest: str = "", fetch=None,
              timeout: float = DEFAULT_TIMEOUT, mct_exe: str | None = None,
              convert=convert_one, log=print) -> dict:
    """Fetch and convert one shard of the sample; returns the shard document.

    ``fetch(mod) -> Path`` raises on failure (corpus.CorpusError); a mod that
    can't be fetched is recorded as ``fetch_failed``, not dropped.
    """
    index, total = parse_shard(shard)
    chosen = shard_of(list(mods), index, total)
    doc = {"schema": SCHEMA, "kind": "gap-shard", "manifest": manifest,
           "shard": f"{index}/{total}", "generated": _now(), "mods": {}}
    for mod in chosen:
        meta = {"project": mod.project, "version": mod.version, "loader": mod.loader,
                "minecraft": mod.minecraft, "license": mod.license}
        try:
            jar = fetch(mod)
        except Exception as exc:  # noqa: BLE001 - a fetch failure is a row, not a crash
            doc["mods"][mod.name] = {**meta, "status": "fetch_failed", "detail": str(exc)[:300]}
            log(f"{mod.name}: fetch failed: {exc}")
            continue
        work = Path(tempfile.mkdtemp(prefix="portkit-gaps-"))
        try:
            record = convert(Path(jar), work, timeout)
            if record.get("status") == "ok" and mct_exe:
                record["mct"] = _mct_counts(mct_exe, work / "out")
        finally:
            shutil.rmtree(work, ignore_errors=True)
        doc["mods"][mod.name] = {**meta, **record}
        log(_one_line(mod.name, record))
    return doc


def _mct_counts(exe: str, tree: Path) -> dict:
    from .validate import mct

    try:
        summary = mct.run(tree, exe=exe)
    except mct.MctError as exc:
        return {"failed": str(exc)[:200]}
    return summary.by_severity if summary is not None else {}


def _one_line(name: str, record: dict) -> str:
    if record.get("status") != "ok":
        return f"{name}: {record.get('status')} ({record.get('detail', '')})"
    return (f"{name}: {record['coverage']:.1f}% coverage, {record['residue']} residue file(s), "
            f"{len(record.get('reasons', {}))} reason(s), {record['seconds']}s")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# --- the leaderboard -------------------------------------------------------

def _status_reason(record: dict) -> tuple[str, str] | None:
    """A mod that never produced residue still has a gap: the conversion
    itself. Crash details are normalized like any other reason."""
    status = record.get("status")
    if status == "crashed":
        return "conversion", f"conversion crashed: {normalize(record.get('detail', ''))}"
    if status == "timeout":
        return "conversion", "conversion timed out"
    return None


def leaderboard(shards: list[dict], previous: dict | None = None) -> dict:
    """Merge shard documents into the ranked leaderboard."""
    mods: dict[str, dict] = {}
    manifests = set()
    for doc in shards:
        if doc.get("kind") != "gap-shard":
            raise ValueError("not a gap shard document")
        manifests.add(doc.get("manifest", ""))
        for name, record in doc.get("mods", {}).items():
            if name in mods:
                raise ValueError(f"mod {name!r} appears in two shards")
            mods[name] = record

    reasons: dict[str, dict] = {}
    for name in sorted(mods):
        record = mods[name]
        items = dict(record.get("reasons") or {})
        status = _status_reason(record)
        if status:
            kind, reason = status
            items[f"{kind}: {reason}"] = {"kind": kind, "reason": reason, "entries": 1,
                                          "files": 0, "examples": [{"source": name, "reason": record.get("detail", "")}]}
        for key, slot in items.items():
            agg = reasons.setdefault(key, {"key": key, "kind": slot["kind"], "reason": slot["reason"],
                                           "mods": 0, "entries": 0, "files": 0,
                                           "mod_names": [], "examples": []})
            agg["mods"] += 1
            agg["entries"] += slot["entries"]
            agg["files"] += slot["files"]
            agg["mod_names"].append(name)
            for ex in slot.get("examples", []):
                if len(agg["examples"]) < _EXAMPLES:
                    agg["examples"].append({"mod": name, **ex})

    ranked = sorted(reasons.values(), key=lambda r: (-r["mods"], -r["files"], r["key"]))
    prev = {r["key"]: r for r in (previous or {}).get("reasons", [])}
    for rank, r in enumerate(ranked, 1):
        r["rank"] = rank
        r["mod_names"] = r["mod_names"][:_MOD_LIST]
        if previous is not None:
            old = prev.get(r["key"])
            r["trend"] = ({"new": True} if old is None else
                          {"mods": r["mods"] - old["mods"], "files": r["files"] - old["files"],
                           "rank": old["rank"] - rank})

    statuses = Counter(rec.get("status", "?") for rec in mods.values())
    ok = [rec for rec in mods.values() if rec.get("status") == "ok"]
    board = {
        "schema": SCHEMA,
        "kind": "gap-leaderboard",
        "generated": _now(),
        "manifest": sorted(manifests)[0] if len(manifests) == 1 else sorted(manifests),
        "mods_total": len(mods),
        "statuses": dict(sorted(statuses.items())),
        "mean_coverage": round(sum(r["coverage"] for r in ok) / len(ok), 2) if ok else None,
        "reasons": ranked,
        "mods": [
            {"name": name, "status": rec.get("status"), "project": rec.get("project"),
             "loader": rec.get("loader"), "minecraft": rec.get("minecraft"),
             "license": rec.get("license"), "coverage": rec.get("coverage"),
             "files": rec.get("files"), "residue": rec.get("residue"),
             "errors": rec.get("errors"), "mct": rec.get("mct"),
             "seconds": rec.get("seconds"), "detail": rec.get("detail")}
            for name, rec in sorted(mods.items())
        ],
    }
    if previous is not None:
        now_keys = set(reasons)
        board["previous"] = {
            "generated": previous.get("generated"),
            "mods_total": previous.get("mods_total"),
            "mean_coverage": previous.get("mean_coverage"),
            "gone": sorted((k for k in prev if k not in now_keys),
                           key=lambda k: (-prev[k]["mods"], k)),
        }
        old_cov = {m["name"]: m.get("coverage") for m in previous.get("mods", [])}
        for m in board["mods"]:
            before = old_cov.get(m["name"])
            if before is not None and m["coverage"] is not None:
                m["coverage_delta"] = round(m["coverage"] - before, 2)
    return board


def _md_cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _trend_cell(r: dict) -> str:
    t = r.get("trend")
    if t is None:
        return ""
    if t.get("new"):
        return "new"
    return f"{t['mods']:+d} mods, {t['files']:+d} files"


def render_markdown(board: dict, top: int = 50) -> str:
    """The leaderboard as a page: summary, ranked reasons, then per mod."""
    lines = ["# Gap leaderboard", ""]
    st = ", ".join(f"{k} {v}" for k, v in board["statuses"].items())
    lines.append(f"Generated {board['generated']} from `{board['manifest']}`: "
                 f"{board['mods_total']} mods ({st}); mean coverage of converted mods "
                 f"{board['mean_coverage']}%.")
    prev = board.get("previous")
    if prev:
        lines.append(f"Trend against the run of {prev.get('generated')} "
                     f"({prev.get('mods_total')} mods, mean coverage {prev.get('mean_coverage')}%).")
    lines += ["", "Ranked by mods blocked, then source files covered. A reason is a residue "
              "reason with ids, paths, quoted names and numbers blanked (see docs/gap-leaderboard.md).",
              "", f"## Top {min(top, len(board['reasons']))} reasons", ""]
    has_trend = prev is not None
    head = "| # | mods | files | entries | kind | reason | e.g. |" + (" trend |" if has_trend else "")
    lines += [head, "|---:|---:|---:|---:|---|---|---|" + ("---|" if has_trend else "")]
    for r in board["reasons"][:top]:
        ex = r["mod_names"][0] if r["mod_names"] else ""
        row = (f"| {r['rank']} | {r['mods']} | {r['files']} | {r['entries']} | {_md_cell(r['kind'])} "
               f"| {_md_cell(r['reason'])} | {_md_cell(ex)} |")
        if has_trend:
            row += f" {_trend_cell(r)} |"
        lines.append(row)
    if prev and prev.get("gone"):
        lines += ["", f"## Gone since the previous run ({len(prev['gone'])})", ""]
        lines += [f"- {_md_cell(k)}" for k in prev["gone"][:top]]
    lines += ["", "## Mods", "", "| mod | status | loader | Minecraft | license | coverage | residue | seconds |",
              "|---|---|---|---|---|---:|---:|---:|"]
    for m in board["mods"]:
        cov = "" if m["coverage"] is None else f"{m['coverage']:.1f}%"
        if m.get("coverage_delta"):
            cov += f" ({m['coverage_delta']:+.1f})"
        status = m["status"] if m["status"] == "ok" else f"{m['status']}: {_md_cell(m.get('detail') or '')[:80]}"
        lines.append(f"| {m['name']} | {status} | {m.get('loader') or ''} | {m.get('minecraft') or ''} "
                     f"| {_md_cell(m.get('license') or '')} | {cov} | {m.get('residue') if m.get('residue') is not None else ''} "
                     f"| {m.get('seconds') if m.get('seconds') is not None else ''} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":  # the child process of convert_one
    if len(sys.argv) == 5 and sys.argv[1] == "child":
        sys.exit(_child(*sys.argv[2:]))
    print("usage: python -m portkit.gaps child JAR OUT RESULT", file=sys.stderr)
    sys.exit(2)
