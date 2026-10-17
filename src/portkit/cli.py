from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path

from .conditions import ConfigError, load_config_file, parse_config_arg
from .ingest import IngestError
from .converters.blocks import EXPERIMENTS
from .pipeline import convert
from .validate import validate_tree

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _print_findings(report) -> None:
    for f in report.findings:
        mark = {"error": "ERROR", "info": "info "}.get(f.severity, "warn ")
        print(f"  {mark} {f.path}: [{f.rule}] {f.message}")


def _residue_agent(args):
    """The agent for ``convert --agent``.

    The provider comes from the environment, unless ``--agent-replay`` names a
    transcript, which needs no provider, key or network. ``--agent-record``
    writes every completion of the run to a transcript.
    """
    from .agent import Budget, Pricing, make_client
    from .agent.residue import ResidueAgent
    from .agent.transcript import RecordingClient, ReplayClient

    budget = Budget(
        max_steps=args.agent_max_steps,
        max_tokens=args.agent_max_tokens,
        max_cost=args.agent_max_cost,
        pricing=Pricing.from_env(),
    )
    if args.agent_replay:
        client = ReplayClient(Path(args.agent_replay))
    else:
        client = make_client()
    if args.agent_record:
        client = RecordingClient(client, Path(args.agent_record))
    return ResidueAgent(client, budget=budget)


def _numbered(path: str, run: int) -> str:
    """``rec.jsonl`` -> ``rec-2.jsonl``: one transcript per repeated run."""
    p = Path(path)
    suffix = p.suffix or ".jsonl"
    return str(p.with_name(f"{p.stem if p.suffix else p.name}-{run}{suffix}"))


def _run_cost_cap(per_run: float | None, remaining: float | None) -> float | None:
    """The dollar ceiling for one run: its own, tightened to what the sweep has left."""
    caps = [c for c in (per_run, remaining) if c is not None]
    return min(caps) if caps else None


def cmd_convert(args) -> int:
    repeat = getattr(args, "repeat", 1) or 1
    total_cap = getattr(args, "agent_max_total_cost", None)
    if repeat < 1:
        print("--repeat must be at least 1", file=sys.stderr)
        return 2
    if total_cap is not None and total_cap <= 0:
        print("--agent-max-total-cost must be more than 0", file=sys.stderr)
        return 2
    if repeat == 1:
        if total_cap is not None:
            args = argparse.Namespace(**vars(args))
            args.agent_max_cost = _run_cost_cap(args.agent_max_cost, total_cap)
        code, _ = _convert_once(args)
        return code
    if not (args.agent or args.agent_replay):
        print("--repeat only makes sense with --agent", file=sys.stderr)
        return 2

    rows: list[dict] = []
    skipped: list[int] = []
    spent = 0.0
    worst = 0
    for run in range(1, repeat + 1):
        # The sweep cap (#143): each run's dollar ceiling is tightened to what
        # is left, and once nothing is, the remaining runs never start.
        remaining = None if total_cap is None else round(total_cap - spent, 9)
        if remaining is not None and remaining <= 0:
            skipped = list(range(run, repeat + 1))
            print(
                f"\nthe sweep's ${total_cap:g} total-cost ceiling is reached "
                f"(${spent:.4f} spent); skipping run(s) {run}..{repeat}"
            )
            break
        run_args = argparse.Namespace(**vars(args))
        run_args.out = str(Path(args.out) / f"run-{run}")
        run_args.agent_max_cost = _run_cost_cap(args.agent_max_cost, remaining)
        if args.agent_record:
            run_args.agent_record = _numbered(args.agent_record, run)
        print(f"\n=== run {run} of {repeat} -> {run_args.out} ===")
        code, result = _convert_once(run_args)
        if code == 2 and result is None:
            return 2  # could not start at all: repeating will not help
        worst = max(worst, code)
        if result is not None and result.agent is not None:
            rows.append(_run_row(run, result))
            spent += result.agent.spend.cost or 0.0
    summary = _repeat_summary(rows)
    if total_cap is not None:
        summary["max_total_cost_usd"] = total_cap
        summary["total_cost_usd"] = round(spent, 6)
        summary["runs_requested"] = repeat
        summary["skipped_runs"] = [
            {"run": run, "status": "skipped", "reason": f"the ${total_cap:g} total-cost ceiling was reached"}
            for run in skipped
        ]
    print("\n" + _format_repeat(summary))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "repeat-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return worst


def _run_row(run: int, result) -> dict:
    agent = result.agent
    return {
        "run": run,
        "groups": len(agent.outcomes),
        "resolved": len(agent.resolved),
        "declined": len(agent.declined),
        # How much of the agent's work landed, and separately whether the pack
        # validates. One "ok" used to stand for the second and read like the
        # first: a run with every group rolled back said ok: true (#86).
        "agent_status": agent.status,
        "statuses": {o.key: o.status for o in agent.outcomes},
        "steps": agent.spend.steps,
        "tokens": agent.spend.tokens,
        "cost_usd": None if agent.spend.cost is None else round(agent.spend.cost, 6),
        "valid": result.report.ok,
    }


def _stats(values: list[float]) -> dict:
    if not values:
        return {"mean": None, "stdev": None, "min": None, "max": None}
    return {
        "mean": round(statistics.fmean(values), 6),
        "stdev": round(statistics.stdev(values), 6) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def _repeat_summary(rows: list[dict]) -> dict:
    """Mean and sample stdev across runs, plus how often each group resolved."""
    costs = [r["cost_usd"] for r in rows if r["cost_usd"] is not None]
    per_group: dict[str, int] = {}
    declined_in: dict[str, int] = {}
    agent_status: dict[str, int] = {}
    for r in rows:
        for key, status in r["statuses"].items():
            per_group[key] = per_group.get(key, 0) + (status == "resolved")
            declined_in[key] = declined_in.get(key, 0) + (status == "declined")
        agent_status[r["agent_status"]] = agent_status.get(r["agent_status"], 0) + 1
    return {
        "runs": len(rows),
        "agent_status": dict(sorted(agent_status.items())),
        "resolved": _stats([r["resolved"] for r in rows]),
        "declined": _stats([r["declined"] for r in rows]),
        "steps": _stats([r["steps"] for r in rows]),
        "tokens": _stats([r["tokens"] for r in rows]),
        "cost_usd": _stats(costs) if len(costs) == len(rows) else None,
        "group_resolved_in": per_group,
        "group_declined_in": declined_in,
        "per_run": rows,
    }


def _format_repeat(summary: dict) -> str:
    n = summary["runs"]
    lines = [f"across {n} run(s), mean ± stdev [min..max]:"]
    for name in ("resolved", "steps", "tokens", "cost_usd"):
        s = summary[name]
        if s is None or s["mean"] is None:
            continue
        lines.append(f"  {name:<9} {s['mean']:g} ± {s['stdev']:g} [{s['min']:g}..{s['max']:g}]")
    if summary.get("skipped_runs"):
        lines.append(
            f"  skipped: {len(summary['skipped_runs'])} of {summary['runs_requested']} run(s), "
            f"the ${summary['max_total_cost_usd']:g} total-cost ceiling "
            f"(spent ${summary['total_cost_usd']:.4f})"
        )
    if summary["agent_status"]:
        statuses = ", ".join(f"{s} {c}" for s, c in summary["agent_status"].items())
        lines.append(f"  agent runs: {statuses}")
    declined_in = summary.get("group_declined_in", {})
    for key, hits in summary["group_resolved_in"].items():
        declined = declined_in.get(key, 0)
        tail = f", declined in {declined}" if declined else ""
        lines.append(f"  {key}: resolved in {hits} of {n}{tail}")
    return "\n".join(lines)


def _config_requests(args):
    """The --config-file settings, then --config ones (later settings win)."""
    requests = []
    if getattr(args, "config_file", None):
        requests += load_config_file(args.config_file)
    for text in getattr(args, "config", None) or []:
        requests.append(parse_config_arg(text))
    return requests


def _convert_once(args):
    """One conversion. Returns (exit code, result or None if it never ran)."""
    try:
        config = _config_requests(args)
    except ConfigError as exc:
        print(f"bad mod config: {exc}", file=sys.stderr)
        return 2, None
    agent = None
    if args.agent or args.agent_replay:
        try:
            agent = _residue_agent(args)
        except (OSError, ValueError) as exc:
            print(f"cannot start the residue agent: {exc}", file=sys.stderr)
            return 2, None
    try:
        result = convert(
            Path(args.source),
            Path(args.out),
            args.namespace,
            emit_addon=not args.no_addon,
            agent=agent,
            config=config or None,
            experiments=getattr(args, "experiment", None) or None,
        )
    except IngestError as exc:
        print(f"cannot read {args.source}: {exc}", file=sys.stderr)
        return 2, None
    except ConfigError as exc:
        print(f"bad mod config: {exc}", file=sys.stderr)
        return 2, None
    print(json.dumps(result.summary(), indent=2))
    if result.agent:
        declined = len(result.agent.declined)
        print(
            f"\nagent {result.agent.status}: resolved {len(result.agent.resolved)} of "
            f"{len(result.agent.outcomes)} residue group(s)"
            + (f", declined {declined}" if declined else "")
            + ":"
        )
        for outcome in result.agent.outcomes:
            detail = f" ({outcome.note})" if outcome.note else ""
            print(f"  {outcome.status}: {outcome.key} [{outcome.spend.describe()}]{detail}")
        print(f"spent: {result.agent.spend.describe()}")
        if result.agent.limit:
            kept = result.agent.partial_files
            tail = f"; {kept} partial file(s) kept" if kept else ""
            print(f"stopped at the run's {result.agent.limit} ceiling{tail}")
    if result.unhandled:
        print(
            f"\n{len(result.unhandled)} item(s) covering "
            f"{result.residue_count} file(s) left for the agent:"
        )
        for item in result.unhandled:
            print(f"  {item.kind}: {item.source} ({item.reason})")
    if result.addon:
        size = result.addon.stat().st_size
        print(f"\ninstallable addon: {result.addon} ({size:,} bytes)")
    if not result.report.ok:
        print("\nvalidation failed:")
        _print_findings(result.report)
        return 1, result
    return 0, result


def cmd_validate(args) -> int:
    report = validate_tree(Path(args.tree))
    if report.ok:
        print(f"ok, {len(report.findings)} warning(s)")
        _print_findings(report)
        return 0
    print(f"{len(report.errors)} error(s):")
    _print_findings(report)
    return 1


def cmd_probe(args) -> int:
    """Build the axis probe pack: one asymmetric model converted both ways."""
    from .harness import axis_probe
    from .meta import ModMetadata
    from .model import ConversionResult
    from .pack import addon_name, write_mcaddon, write_tree

    out = Path(args.out)
    texture = Path(args.texture)
    try:
        if args.kind == "rotation":
            files = axis_probe.rotation_pack_files(
                Path(args.models), texture, args.namespace
            )
        elif args.kind == "face":
            files = axis_probe.face_pack_files(args.namespace)
        elif args.kind == "turn":
            files = axis_probe.turn_pack_files(args.namespace)
        elif args.kind == "sideturn":
            files = axis_probe.side_turn_pack_files(args.namespace)
        elif args.kind == "pivot":
            files = axis_probe.pivot_pack_files(
                Path(args.model), texture, args.namespace
            )
        else:
            files = axis_probe.pack_files(Path(args.model), texture, args.namespace)
    except (OSError, ValueError) as exc:
        print(f"cannot build the probe: {exc}", file=sys.stderr)
        return 2

    label = {
        "axis": ("axis_probe", "Axis Probe"),
        "rotation": ("rotation_probe", "Rotation Probe"),
        "pivot": ("pivot_probe", "Pivot Probe"),
        "face": ("face_probe", "Face Probe"),
        "turn": ("turn_probe", "Turn Probe"),
        "sideturn": ("side_turn_probe", "Side Turn Probe"),
    }
    mod_id, title = label[args.kind]
    meta = ModMetadata(mod_id=mod_id, name=title)
    tree = write_tree(ConversionResult(files=files), args.namespace, out, meta)
    addon = write_mcaddon(tree, out / addon_name(args.namespace, meta))
    print(f"probe tree:  {tree}")
    print(f"install:     {addon} ({addon.stat().st_size:,} bytes)")
    if args.kind == "sideturn":
        print(
            "\nPlace C, A and B in a row. Each side has its own colour.\n"
            "  Looking straight at a side: which of A or B has its arrow a quarter\n"
            "  turn CLOCKWISE from C's? Check every colour; say if one differs.\n"
            "Also say if any arrow looks mirrored (red corner on the wrong side).\n"
        )
        return 0
    if args.kind == "turn":
        print(
            "\nPlace C, A and B in a row on a ledge you can stand under.\n"
            "  From above: which of A or B has its arrow a quarter turn CLOCKWISE from C?\n"
            "  From below: which of A or B has its arrow a quarter turn ANTICLOCKWISE from C?\n"
            "Also say if any arrow looks mirrored (red corner on the wrong side).\n"
        )
        return 0
    if args.kind == "face":
        print(
            "\nTwo blocks, one question. Each is a thin slab on one edge, textured "
            "on one side only.\n"
            "  A face mirrored    -> uv key follows the X mirror (west -> east)\n"
            "  B face as written  -> uv key keeps the Java face name\n"
            f"Java renders {axis_probe.FACE_EXPECTED}. Walk around both; the one "
            "that matches is the keying."
        )
    elif args.kind == "pivot":
        print(
            "\nTwo blocks, one question. Both turn the same cube +45 about Z "
            "around an origin\neight blocks west of centre, and differ only in "
            "where that pivot lands:\n"
            "  A pivot mirrored    -> pivot.x = 8 - origin.x\n"
            "  B pivot as written  -> pivot.x = origin.x - 8\n"
            f"Java renders the cube {axis_probe.PIVOT_EXPECTED}. Whichever block "
            "matches is the mapping."
        )
    elif args.kind == "rotation":
        print(
            "\nSix blocks, one question per axis: which sign leans the way Java does?\n"
            "  X as written / X negated   (Java rotates +22.5 about X)\n"
            "  Y as written / Y negated\n"
            "  Z as written / Z negated\n"
            "Every bar turns about the block centre, so the sign is the only "
            "thing they disagree about."
        )
    else:
        print(
            "\nPlace both blocks, face north, and note which one matches the Java render:\n"
            "  Probe A (axes agree)  -> origin.x = from.x - 8\n"
            "  Probe B (X flipped)   -> origin.x = 8 - to.x"
        )
    return 0


def cmd_report(args) -> int:
    """Markdown a modder can read, or paste into an issue, without the jar."""
    from .report import render

    tree = Path(args.tree)
    if not tree.is_dir():
        print(f"{tree} is not a directory", file=sys.stderr)
        return 2
    text = render(tree)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
        print(f"report: {out} ({len(text):,} bytes)")
    else:
        print(text)
    return 0


def cmd_eval_agent(args) -> int:
    """``portkit eval --agent``: the per-provider eval matrix (#77)."""
    import json as _json

    from .agent import Budget, Pricing, make_client
    from .agent.matrix import agent_fixtures, parse_target, render, run_matrix, target_label
    from .agent.transcript import ReplayClient

    root = Path(args.fixtures or FIXTURES)
    budget = Budget(
        max_steps=args.agent_max_steps,
        max_tokens=args.agent_max_tokens,
        max_cost=args.agent_max_cost,
        pricing=Pricing.from_env(),
    )
    specs = list(args.target or [])
    if args.provider or args.model:
        specs.append(f"{args.provider or ''}:{args.model or ''}")

    if args.agent_replay:
        if specs:
            print("--agent-replay runs on its own; drop --target/--provider/--model", file=sys.stderr)
            return 2
        replay = Path(args.agent_replay)
        cases = agent_fixtures(root, args.fixture or ())
        if replay.is_dir():
            # One transcript per fixture, named <fixture>.jsonl.
            cases = [c for c in cases if (replay / f"{c.name}.jsonl").is_file()]

            def factory(name):
                return ReplayClient(replay / f"{name}.jsonl")
        else:
            if len(cases) != 1:
                print("a single transcript replays one fixture: add --fixture NAME", file=sys.stderr)
                return 2

            def factory(name):
                return ReplayClient(replay)
        targets = [(f"replay:{replay.name}", factory)]
    else:
        if not specs:
            print("eval --agent needs --target PROVIDER:MODEL (repeatable), "
                  "--provider/--model, or --agent-replay", file=sys.stderr)
            return 2
        targets = []
        for spec in specs:
            provider, model, base_url = parse_target(spec)
            label = target_label(provider, model, base_url)
            config = {"base_url": base_url} if base_url else None

            try:  # a missing key or unknown provider is a setup error, not a score
                make_client(provider, model, config=config)
            except Exception as exc:
                print(f"{label}: {exc}", file=sys.stderr)
                return 2

            def factory(name, provider=provider, model=model, config=config):
                return make_client(provider, model, config=config)
            targets.append((label, factory))
        cases = agent_fixtures(root, args.fixture or ())

    if not cases:
        print(f"no agent fixtures under {root}", file=sys.stderr)
        return 1
    rows = run_matrix(targets, cases, budget)
    print(f"fixtures: {', '.join(c.name for c in cases)}")
    print(render(rows))
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(_json.dumps([r.to_dict() for r in rows], indent=2) + "\n")
    # A replay that comes back unscored drifted from its transcript; fail CI on it.
    if args.agent_replay and any(r.unscored for r in rows):
        print("\nreplay drifted: a task came back unscored", file=sys.stderr)
        return 1
    return 0


def cmd_eval(args) -> int:
    """Run every fixture and print the coverage table. This is the number that matters.

    With a baseline (``fixtures/coverage-baseline.json`` by default, or
    ``--baseline``), any fixture whose coverage or converted file count drops
    below it fails the run, naming the fixture and the delta.
    """
    import os
    import tempfile

    from . import baseline as bl

    if getattr(args, "agent", False) or getattr(args, "agent_replay", None):
        return cmd_eval_agent(args)

    corpus_mode = getattr(args, "corpus", False)
    if corpus_mode:
        loaded = _corpus_cases(args)
        if isinstance(loaded, int):
            return loaded
        root, cases = loaded
    else:
        root = Path(args.fixtures or FIXTURES)
        cases = [(p.name, p / "input") for p in sorted(root.iterdir()) if (p / "input").is_dir()]
    if not cases:
        print(f"no fixtures under {root}")
        return 1

    mct_exe, mct_runs, mct_failed = _mct_setup(args)

    rows, measured, failures, error_counts = [], [], 0, {}
    for name, source in cases:
        with tempfile.TemporaryDirectory() as tmp:
            result = convert(source, Path(tmp) / "out", emit_addon=not corpus_mode)
            if mct_exe:
                _mct_one(mct_exe, name, Path(tmp) / "out", mct_runs, mct_failed)
            ok = result.report.ok
            failures += 0 if ok else 1
            error_counts[name] = len(result.report.errors)
            rows.append(
                (name, result.file_count, result.residue_count, result.coverage, ok)
            )
            measured.append(
                bl.Measured(name, result.file_count, result.residue_count, result.coverage)
            )

    width = max(len(r[0]) for r in rows)
    print(f"{'fixture'.ljust(width)}  files  residue  coverage  valid")
    for name, handled, residue, coverage, ok in rows:
        print(f"{name.ljust(width)}  {handled:5d}  {residue:7d}  {coverage:7.1f}%  {'yes' if ok else 'NO'}")

    if mct_runs or mct_failed:
        from .validate import mct

        print()
        if mct_runs:
            print(mct.render(mct_runs))
        for name, err in mct_failed.items():
            print(f"note: {name}: mct validate failed: {err}")
        print("(mct findings are report-only: they do not fail the gate)")
    if getattr(args, "json", None):
        _write_eval_json(Path(args.json), corpus_mode, rows, error_counts,
                         mct_exe, mct_runs, mct_failed, getattr(args, "mct", False))

    baseline_path = Path(args.baseline) if args.baseline else root / bl.BASELINE_NAME

    if corpus_mode:
        return _corpus_verdict(args, baseline_path, measured, error_counts)

    if args.update_baseline:
        baseline_path.write_text(bl.dump(measured))
        print(f"\nbaseline written: {baseline_path}")
        return 1 if failures else 0

    if args.no_baseline:
        return 1 if failures else 0
    if not baseline_path.is_file():
        if args.baseline:
            print(f"\nbaseline not found: {baseline_path}", file=sys.stderr)
            return 2
        return 1 if failures else 0

    try:
        regressions, notes = bl.compare(measured, bl.load(baseline_path))
    except (OSError, ValueError) as exc:
        print(f"\ncannot read baseline: {exc}", file=sys.stderr)
        return 2

    annotate = os.environ.get("GITHUB_ACTIONS") == "true"
    for note in notes:
        print(f"note: {note.fixture}: {note.message}")
        if annotate:
            print(f"::notice title=coverage baseline::{note.fixture}: {note.message}")
    if regressions:
        print(f"\ncoverage regressed against {baseline_path}:")
        for reg in regressions:
            print(f"  REGRESSION {reg.fixture}: {reg.message}")
            if annotate:
                print(f"::error title=coverage regression::{reg.fixture}: {reg.message}")
        return 1
    print(f"\ncoverage at or above baseline for all {len(measured)} fixtures")
    return 1 if failures else 0


def _mct_setup(args):
    """(mct executable or None, results by tree, failures by tree) for ``--mct``."""
    if not getattr(args, "mct", False):
        return None, {}, {}
    from .validate import mct

    exe = mct.find_mct()
    if exe is None:
        print("note: --mct asked for, but `mct` is not on PATH; skipping Mojang's validator "
              "(npm install -g @minecraft/creator-tools, Node 22+)")
    return exe, {}, {}


def _mct_one(exe, name, tree, runs, failed) -> None:
    """Run mct over one converted tree; a failure is a note, never a verdict."""
    from .validate import mct

    try:
        summary = mct.run(tree, exe=exe)
    except mct.MctError as exc:
        failed[name] = str(exc)
        return
    if summary is not None:
        runs[name] = summary


def _write_eval_json(path: Path, corpus_mode, rows, error_counts, mct_exe, mct_runs,
                     mct_failed, mct_asked) -> None:
    """The eval as JSON: one row per fixture or mod, plus the mct block when asked."""
    from .validate import mct

    data: dict = {
        "mode": "corpus" if corpus_mode else "fixtures",
        "rows": [
            {"name": name, "files": files, "residue": residue,
             "coverage": round(coverage, 2), "valid": ok, "errors": error_counts.get(name, 0)}
            for name, files, residue, coverage, ok in rows
        ],
    }
    if mct_asked:
        data["mct"] = {
            "available": mct_exe is not None,
            "report_only": True,
            "trees": {name: s.to_dict() for name, s in mct_runs.items()},
            "failed": dict(mct_failed),
            "total": mct.aggregate(mct_runs).to_dict(top=20) if mct_runs else None,
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"eval written: {path}")


def _corpus_cases(args):
    """(root, [(name, jar)]) for ``eval --corpus``, or an exit code."""
    from . import corpus

    manifest = Path(args.manifest) if args.manifest else corpus.MANIFEST
    try:
        mods = corpus.load(manifest)
    except (OSError, corpus.CorpusError) as exc:
        print(f"cannot read corpus manifest: {exc}", file=sys.stderr)
        return 2
    try:
        mods = corpus.select(mods, args.fixture or (), getattr(args, "include_optional", False))
    except corpus.CorpusError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    cases, missing = [], []
    for mod in mods:
        try:
            jar = corpus.fetch(mod)[0] if args.fetch else corpus.cached(mod)
        except corpus.CorpusError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if jar is None:
            missing.append(mod.name)
        else:
            cases.append((mod.name, jar))
    if missing:
        print(f"not in the corpus cache: {', '.join(missing)}; run `portkit corpus fetch` "
              "or add --fetch", file=sys.stderr)
        return 2
    from . import data

    from .data import tags as tag_data

    from .data import models as model_data
    from .data import java_items, vanilla_items

    if args.fetch:
        try:
            data.fetch_sounds()
            model_data.fetch()
            vanilla_items.fetch()
            java_items.fetch()
            for tag_set in tag_data.SETS:
                tag_data.fetch(tag_set)
        except data.ReferenceDataError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    missing_tags = [s.id for s in tag_data.SETS if tag_data.load(s) is None]
    if missing_tags:
        # The corpus baseline is measured with the loader and vanilla tag data;
        # without it shared tags stay residue (#160), which can move the numbers.
        message = (f"tag reference data isn't cached ({', '.join(missing_tags)}), so loader and "
                   f"vanilla tags stay residue and the numbers may differ from the baseline; "
                   f"run `{data.FETCH_COMMAND}` or add --fetch")
        print(f"warning: {message}", file=sys.stderr)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::warning title=tag reference::{message}")
    if model_data.templates() is None:
        # The corpus baseline is measured with the vanilla model templates;
        # without them stairs, slabs, walls and turned pillars stay residue.
        message = (f"the vanilla block model templates aren't cached, so stairs, slabs, walls "
                   f"and turned pillars stay residue and the numbers may differ from the "
                   f"baseline; run `{data.FETCH_COMMAND}` or add --fetch")
        print(f"warning: {message}", file=sys.stderr)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::warning title=model templates::{message}")
    if vanilla_items.ids() is None:
        # Recipe unlocks name a vanilla item only when Bedrock has it (#260).
        message = (f"the Bedrock vanilla item list isn't cached, so recipe unlocks leave out "
                   f"vanilla items and the numbers may differ from the baseline; run "
                   f"`{data.FETCH_COMMAND}` or add --fetch")
        print(f"warning: {message}", file=sys.stderr)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::warning title=vanilla items::{message}")
    if java_items.table() is None:
        # Recipes name Java vanilla ids; Bedrock spells many differently (#261).
        message = (f"the Java -> Bedrock item table isn't cached, so recipes keep Java's vanilla "
                   f"item ids and the numbers may differ from the baseline; run "
                   f"`{data.FETCH_COMMAND}` or add --fetch")
        print(f"warning: {message}", file=sys.stderr)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::warning title=java items::{message}")
    if data.bedrock_vanilla_sounds() is None:
        # The corpus baseline is measured with the list; without it vanilla
        # sound references are dropped, which can move the numbers.
        message = (f"the Bedrock vanilla sound list isn't cached, so vanilla sound references "
                   f"are dropped and the numbers may differ from the baseline; run "
                   f"`{data.FETCH_COMMAND}` or add --fetch")
        print(f"warning: {message}", file=sys.stderr)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::warning title=vanilla sounds::{message}")
    return manifest.parent, cases


def _corpus_verdict(args, baseline_path: Path, measured, error_counts: dict[str, int]) -> int:
    """The corpus ratchet: coverage and file counts as for fixtures, plus the
    validator error count per mod, which may not rise. A real mod is allowed to
    be invalid today; it is not allowed to get worse unnoticed."""
    import json as _json
    import os

    from . import baseline as bl

    if args.update_baseline:
        if args.fixture:
            print("--update-baseline rewrites every mod; drop --fixture", file=sys.stderr)
            return 2
        data = _json.loads(bl.dump(measured))
        for name, entry in data["fixtures"].items():
            entry["errors"] = error_counts[name]
        # Optional mods this run skipped keep their entries; mods no longer in
        # the manifest drop out.
        for name, entry in _skipped_baseline(args, baseline_path, error_counts).items():
            data["fixtures"][name] = entry
        data["fixtures"] = dict(sorted(data["fixtures"].items()))
        baseline_path.write_text(_json.dumps(data, indent=2) + "\n")
        print(f"\nbaseline written: {baseline_path}")
        return 0
    if args.no_baseline or not baseline_path.is_file():
        if args.baseline and not baseline_path.is_file():
            print(f"\nbaseline not found: {baseline_path}", file=sys.stderr)
            return 2
        return 0
    try:
        base = bl.load(baseline_path)
        regressions, notes = bl.compare(measured, base)
    except (OSError, ValueError) as exc:
        print(f"\ncannot read baseline: {exc}", file=sys.stderr)
        return 2
    if args.fixture:  # a subset run: mods left out are not "dropped"
        regressions = [r for r in regressions if r.fixture in error_counts]
    else:  # optional mods this run skipped are not "dropped" either
        skipped = set(_skipped_baseline(args, baseline_path, error_counts, base))
        regressions = [r for r in regressions if r.fixture not in skipped]
    for name, count in sorted(error_counts.items()):
        before = (base.get(name) or {}).get("errors")
        if before is not None and count > int(before):
            regressions.append(bl.Delta(name, f"validator errors {before} -> {count}"))
        elif before is not None and count < int(before):
            notes.append(bl.Delta(name, f"validator errors {before} -> {count}; bank it with --update-baseline"))
    annotate = os.environ.get("GITHUB_ACTIONS") == "true"
    for note in notes:
        print(f"note: {note.fixture}: {note.message}")
        if annotate:
            print(f"::notice title=corpus baseline::{note.fixture}: {note.message}")
    if regressions:
        print(f"\ncorpus regressed against {baseline_path}:")
        for reg in regressions:
            print(f"  REGRESSION {reg.fixture}: {reg.message}")
            if annotate:
                print(f"::error title=corpus regression::{reg.fixture}: {reg.message}")
        return 1
    print(f"\ncorpus at or above baseline for all {len(measured)} mods")
    return 0


def _skipped_baseline(args, baseline_path: Path, ran, base=None) -> dict:
    """Baseline entries for the manifest's optional mods this run left out:
    kept on --update-baseline, never counted as missing."""
    import json as _json

    from . import corpus

    manifest = Path(args.manifest) if args.manifest else corpus.MANIFEST
    try:
        optional = {m.name for m in corpus.load(manifest) if m.optional}
        if base is None:
            base = _json.loads(baseline_path.read_text())["fixtures"] if baseline_path.is_file() else {}
    except (OSError, ValueError, KeyError, corpus.CorpusError):
        return {}
    return {name: entry for name, entry in base.items() if name in optional and name not in ran}


def cmd_corpus(args) -> int:
    """``portkit corpus fetch|list``: the pinned real-mod jars (#21)."""
    from . import corpus

    manifest = Path(args.manifest) if args.manifest else corpus.MANIFEST
    try:
        mods = corpus.load(manifest)
    except (OSError, corpus.CorpusError) as exc:
        print(f"cannot read corpus manifest: {exc}", file=sys.stderr)
        return 2
    cache = corpus.cache_dir()
    try:
        chosen = corpus.select(mods, args.fixture or (), args.include_optional)
    except corpus.CorpusError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    hidden = [m.name for m in mods if m.optional and m not in chosen]
    if args.action == "list":
        for mod in chosen:
            state = "cached" if corpus.cached(mod, cache) else "missing"
            flag = "optional" if mod.optional else "default"
            print(f"{mod.name:28} {mod.loader:9} {mod.minecraft:8} {mod.license:6} {flag:8} {state}")
        if hidden and not args.fixture:
            print(f"({len(hidden)} optional, not shown: {', '.join(hidden)}; add --include-optional)")
        return 0
    failed = 0
    for mod in chosen:
        try:
            path, downloaded = corpus.fetch(mod, cache)
        except corpus.CorpusError as exc:
            print(f"FAILED {exc}", file=sys.stderr)
            failed += 1
            continue
        print(f"{'fetched' if downloaded else 'cached ':7} {mod.name} -> {path}")
    if hidden and not args.fixture:
        print(f"skipped {len(hidden)} optional: {', '.join(hidden)} (add --include-optional)")
    return 1 if failed else 0


SAMPLE_MANIFEST = Path(__file__).resolve().parents[2] / "fixtures" / "sample" / "mods.toml"


def cmd_sample(args) -> int:
    """``portkit sample build``: the random-sample manifest from Modrinth (#234)."""
    from datetime import date

    from . import sample

    try:
        entries, skipped = sample.build(args.count, args.licences)
    except sample.SampleError as exc:
        print(f"cannot build the sample: {exc}", file=sys.stderr)
        return 1
    today = date.today().isoformat()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sample.render(entries, args.count, args.licences, today))
    for note in skipped:
        print(f"skipped {note}")
    print(f"sample written: {out} ({len(entries)} mods)")
    return 0


def cmd_gaps(args) -> int:
    """``portkit gaps run|board``: the gap leaderboard over the sample (#234)."""
    from . import corpus, gaps

    if args.action == "run":
        manifest = Path(args.manifest) if args.manifest else SAMPLE_MANIFEST
        try:
            mods = corpus.select(corpus.load(manifest), args.fixture or (), include_optional=True)
            gaps.parse_shard(args.shard)
        except (OSError, ValueError, corpus.CorpusError) as exc:
            print(f"cannot read the sample: {exc}", file=sys.stderr)
            return 2
        mct_exe = None
        if args.mct:
            from .validate import mct

            mct_exe = mct.find_mct()
            if mct_exe is None:
                print("note: --mct asked for, but `mct` is not on PATH; skipping it")
        where = manifest.resolve()
        label = str(where.relative_to(gaps_root())) if where.is_relative_to(gaps_root()) else str(manifest)
        doc = gaps.run_shard(
            mods, shard=args.shard, manifest=label,
            fetch=lambda mod: corpus.fetch(mod)[0], timeout=args.timeout, mct_exe=mct_exe,
        )
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, indent=1) + "\n")
        print(f"shard written: {out} ({len(doc['mods'])} mods)")
        return 0

    shards = []
    for path in args.shards:
        try:
            shards.append(json.loads(Path(path).read_text()))
        except (OSError, ValueError) as exc:
            print(f"cannot read shard {path}: {exc}", file=sys.stderr)
            return 2
    previous = None
    if args.previous:
        prev_path = Path(args.previous)
        if prev_path.is_file():
            try:
                previous = json.loads(prev_path.read_text())
            except ValueError as exc:
                print(f"note: previous leaderboard unreadable, no trend: {exc}")
        else:
            print(f"note: no previous leaderboard at {prev_path}; no trend this run")
    try:
        board = gaps.leaderboard(shards, previous)
    except ValueError as exc:
        print(f"cannot build the leaderboard: {exc}", file=sys.stderr)
        return 2
    Path(args.json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json).write_text(json.dumps(board, indent=1) + "\n")
    md = gaps.render_markdown(board, top=args.top)
    if args.md:
        Path(args.md).write_text(md)
    print(md if not args.md else f"leaderboard written: {args.json}, {args.md}")
    return 0


def cmd_gauntlet(args) -> int:
    """``portkit gauntlet pin|run|board``: the top-50 gauntlet (#277, #278)."""
    from datetime import date

    from . import corpus, gaps, gauntlet

    manifest = Path(args.manifest) if args.manifest else gauntlet.MANIFEST
    if args.action == "pin":
        entries = gauntlet.pin()
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(gauntlet.render_manifest(entries, date.today().isoformat()))
        bad = [e["name"] for e in entries if e.get("unfetchable")]
        print(f"gauntlet written: {manifest} ({len(entries)} mods, {len(bad)} unfetchable)")
        return 0
    if args.action == "run":
        try:
            mods = corpus.select(corpus.load(manifest), args.fixture or (), include_optional=True)
            gaps.parse_shard(args.shard)
        except (OSError, ValueError, corpus.CorpusError) as exc:
            print(f"cannot read the gauntlet: {exc}", file=sys.stderr)
            return 2
        mct_exe = None
        if args.mct:
            from .validate import mct

            mct_exe = mct.find_mct()
            if mct_exe is None:
                print("note: --mct asked for, but `mct` is not on PATH; skipping it")
        where = manifest.resolve()
        label = str(where.relative_to(gaps_root())) if where.is_relative_to(gaps_root()) else str(manifest)
        # CurseForge-only mods: fetched only through the official API with
        # CURSEFORGE_API_KEY and only when allowModDistribution is true
        # (#278 pick 2), into a temporary directory that is deleted after the
        # run, never into the corpus cache (which CI caches).
        for jar in gauntlet.purge_curseforge(mods, corpus.cache_dir()):
            print(f"removed a CurseForge jar from the corpus cache: {jar.name}")
        index, total = gaps.parse_shard(args.shard)
        here = {m.name for m in gaps.shard_of(mods, index, total)}
        gated, allow = gauntlet.gate_curseforge([m for m in mods if m.name in here])
        gated = {m.name: m for m in gated}
        mods = [gated.get(m.name, m) for m in mods]
        import tempfile

        with tempfile.TemporaryDirectory(prefix="portkit-curseforge-") as fresh:
            def fetch(mod):
                return corpus.fetch(mod, Path(fresh) if mod.host == "curseforge" else None)[0]

            doc = gaps.run_shard(mods, shard=args.shard, manifest=label, fetch=fetch, timeout=args.timeout,
                                 mct_exe=mct_exe, profile=gauntlet.profile_and_classify)
        if allow:  # what the official API said, per CurseForge mod in this shard
            doc["curseforge_allow_mod_distribution"] = allow
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, indent=1) + "\n")
        print(f"shard written: {out} ({len(doc['mods'])} mods)")
        return 0

    shards = []
    for path in args.shards:
        try:
            shards.append(json.loads(Path(path).read_text()))
        except (OSError, ValueError) as exc:
            print(f"cannot read shard {path}: {exc}", file=sys.stderr)
            return 2

    def _optional_json(path, what):
        if not path:
            return None
        p = Path(path)
        if not p.is_file():
            print(f"note: no {what} at {p}")
            return None
        try:
            return json.loads(p.read_text())
        except ValueError as exc:
            print(f"note: {what} unreadable: {exc}")
            return None

    previous = _optional_json(args.previous, "previous board")
    baseline = _optional_json(args.baseline or gauntlet.BASELINE, "gauntlet baseline")
    try:
        listed = corpus.load(manifest) if manifest.is_file() else None
        result = gauntlet.board(shards, previous, baseline, listed)
    except (ValueError, corpus.CorpusError) as exc:
        print(f"cannot build the gauntlet board: {exc}", file=sys.stderr)
        return 2
    Path(args.json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json).write_text(json.dumps(result, indent=1) + "\n")
    md = gauntlet.render_markdown(result, top=args.top)
    if args.md:
        Path(args.md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md).write_text(md)
    if args.bank:
        Path(args.bank).write_text(json.dumps(gauntlet.baseline_of(result), indent=1) + "\n")
        print(f"baseline banked: {args.bank}")
    print(md if not args.md else f"gauntlet board written: {args.json}, {args.md}")
    return 0


def gaps_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _reference_sets(args):
    """The tag sets ``reference fetch|list`` works on: every pinned one, or the
    ones a given mod's loader and game version select (#160)."""
    from .data import tags

    if not getattr(args, "mod", None):
        return list(tags.SETS), None
    from .ingest import ingest
    from .meta import parse as parse_metadata
    import tempfile

    with tempfile.TemporaryDirectory(prefix="portkit-ref-") as staging:
        staged = ingest(Path(args.mod), Path(staging))
        meta = parse_metadata(staged.metadata, staged.namespace)
    return tags.select(meta.loader, meta.minecraft), meta


def cmd_reference(args) -> int:
    """``portkit reference fetch|list``: reference data fetched on demand: Mojang's
    vanilla sound list (#124), the loaders' and vanilla's item tags (#160),
    the vanilla block model templates stairs, slabs and walls are built from,
    vanilla's campfire recipes the Farmer's Delight stove cooks (#177),
    Bedrock's vanilla texture atlases (short names and file paths only) and the
    SRG / intermediary -> Mojang name tables the bytecode readers use (#235)."""
    from . import data
    from .data import tags

    cache = data.cache_dir()
    sets, meta = _reference_sets(args)
    if meta is not None:
        chosen = ", ".join(s.id for s in sets) or "none"
        print(f"{args.mod}: loader {meta.loader or '?'}, minecraft {meta.minecraft or '?'} -> tag data: {chosen}")
    from .data import models as model_data
    from .data import recipes as recipe_data
    from .data import java_items, vanilla_items
    from .data import vanilla_textures

    from .data import mappings as mapping_data

    # Name mappings (#235): every pinned set, or the one this mod's loader and
    # game version need (none for a Mojang-named jar).
    if meta is None:
        mapping_sets = list(mapping_data.SETS)
    else:
        chosen_map = mapping_data.select(meta.loader, meta.minecraft)
        mapping_sets = [chosen_map] if chosen_map else []
        print(f"{args.mod}: name mappings: {chosen_map.id if chosen_map else 'none needed'}")
    if args.action == "list":
        for mapping in mapping_sets:
            state = "cached" if mapping_data.cached(mapping, cache) else "missing"
            print(f"{mapping.id:28} {mapping.label} {state}")
        state = "cached" if data.cached_sounds(cache) else "missing"
        print(f"{'vanilla-sounds':28} {data.REPO}@{data.COMMIT[:12]} {state}")
        state = "cached" if model_data.cached(cache) else "missing"
        print(f"{model_data.SET_ID:28} {model_data.LABEL} {state}")
        state = "cached" if vanilla_textures.cached(cache) else "missing"
        print(f"{vanilla_textures.SET_ID:28} {vanilla_textures.LABEL} {state}")
        state = "cached" if vanilla_items.cached(cache) else "missing"
        print(f"{vanilla_items.SET_ID:28} {vanilla_items.LABEL} {state}")
        state = "cached" if java_items.cached(cache) else "missing"
        print(f"{java_items.SET_ID:28} {java_items.LABEL} {state}")
        for recipe_set in recipe_data.SETS:
            state = "cached" if recipe_data.cached(recipe_set, cache) else "missing"
            print(f"{recipe_set.id:28} {recipe_set.label} {state}")
        for tag_set in sets:
            state = "cached" if tags.cached(tag_set, cache) else "missing"
            print(f"{'tags-' + tag_set.id:28} {tag_set.label} {state}")
        return 0
    failed = 0
    try:
        path, downloaded = data.fetch_sounds(cache)
        print(f"{'fetched' if downloaded else 'cached ':7} vanilla-sounds -> {path}")
    except data.ReferenceDataError as exc:
        print(f"FAILED {exc}", file=sys.stderr)
        failed += 1
    try:
        path, downloaded = model_data.fetch(cache)
        print(f"{'fetched' if downloaded else 'cached ':7} {model_data.SET_ID} -> {path}")
    except data.ReferenceDataError as exc:
        print(f"FAILED {exc}", file=sys.stderr)
        failed += 1
    try:
        path, downloaded = vanilla_textures.fetch(cache)
        print(f"{'fetched' if downloaded else 'cached ':7} {vanilla_textures.SET_ID} -> {path}")
    except data.ReferenceDataError as exc:
        print(f"FAILED {exc}", file=sys.stderr)
        failed += 1
    try:
        path, downloaded = vanilla_items.fetch(cache)
        print(f"{'fetched' if downloaded else 'cached ':7} {vanilla_items.SET_ID} -> {path}")
    except data.ReferenceDataError as exc:
        print(f"FAILED {exc}", file=sys.stderr)
        failed += 1
    try:
        path, downloaded = java_items.fetch(cache)
        print(f"{'fetched' if downloaded else 'cached ':7} {java_items.SET_ID} -> {path}")
    except data.ReferenceDataError as exc:
        print(f"FAILED {exc}", file=sys.stderr)
        failed += 1
    for recipe_set in recipe_data.SETS:
        try:
            path, downloaded = recipe_data.fetch(recipe_set, cache)
        except data.ReferenceDataError as exc:
            print(f"FAILED {exc}", file=sys.stderr)
            failed += 1
            continue
        print(f"{'fetched' if downloaded else 'cached ':7} {recipe_set.id} -> {path}")
    for mapping in mapping_sets:
        try:
            path, downloaded = mapping_data.fetch(mapping, cache)
        except data.ReferenceDataError as exc:
            print(f"FAILED {exc}", file=sys.stderr)
            failed += 1
            continue
        print(f"{'fetched' if downloaded else 'cached ':7} {mapping.id} -> {path}")
    for tag_set in sets:
        try:
            path, downloaded = tags.fetch(tag_set, cache)
        except data.ReferenceDataError as exc:
            print(f"FAILED {exc}", file=sys.stderr)
            failed += 1
            continue
        print(f"{'fetched' if downloaded else 'cached ':7} tags-{tag_set.id} -> {path}")
    return 1 if failed else 0


def cmd_ingame(args) -> int:
    """``portkit ingame fetch-server|pack|run``: in-game checks on a Bedrock Dedicated Server (#238)."""
    from .ingame import server, testpack

    if args.action == "fetch-server":
        try:
            server.fetch(Path(args.dir), args.accept_eula)
        except (server.EulaNotAccepted, ValueError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"bedrock-server {server.BDS_VERSION} -> {args.dir}")
        return 0
    if not args.tree or not (Path(args.tree) / "behavior_pack").is_dir():
        print(f"{args.action} needs --tree, a converted tree with behavior_pack/", file=sys.stderr)
        return 2
    tree = Path(args.tree)
    name = args.name or tree.name
    if args.action == "pack":
        checks = testpack.write_test_pack(tree / "behavior_pack", Path(args.out), name)
        print(
            f"check pack -> {args.out}: {len(checks.blocks)} blocks, {len(checks.items)} items, "
            f"{len(checks.containers)} containers, {len(checks.connections)} connection blocks, "
            f"{len(checks.drops)} drops, {len(checks.tool_drops)} tool drops"
        )
        return 0
    if not args.server:
        print("run needs --server DIR (portkit ingame fetch-server)", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    prepared = server.prepare(Path(args.server), Path(args.work or out / "server"), tree, name)
    if args.experiment:
        server.enable_experiments(prepared.root, args.experiment)
    result = server.run(prepared.root, f"{server.TAG} DONE", args.timeout, out / "server.log")
    report = server.parse(result.lines)
    report.update(
        name=name, bds_version=server.BDS_VERSION, experiments=args.experiment or [],
        exit_code=result.exit_code, timed_out=result.timed_out, seconds=result.seconds,
    )
    report["content_logs"] = [p.name for p in server.collect_logs(prepared.root, out / "content-log")]
    why = server.verdict(report)
    report["verdict"] = why or ["pass"]
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    summary = report.get("summary") or {}
    print(f"{name}: {json.dumps(summary.get('checks', {}))}")
    for row in report["failures"][:50]:
        print(f"  FAIL {row.get('check')} {row.get('id')}: {row.get('detail')}")
    for row in report["content_errors"][:50]:
        print(f"  CONTENT-LOG {row}")
    print(f"{name}: {'; '.join(why) if why else 'pass'} ({result.seconds}s)")
    if not args.keep_server:
        import shutil
        shutil.rmtree(prepared.root, ignore_errors=True)
    return 1 if why else 0


def cmd_schemas(args) -> int:
    """``portkit schemas check|refresh`` (#155): is the stable npm release of
    each vendored Bedrock schema snapshot out, and re-vendor a snapshot from it.
    check exits 1 when a refresh is due, 2 when the registry can't be read."""
    from .validate import schema_upstream as up

    try:
        packument = up.fetch_packument()
    except up.SchemaUpstreamError as exc:
        print(f"FAILED {exc}", file=sys.stderr)
        return 2
    if args.action == "check":
        try:
            statuses = up.check(packument)
        except up.SchemaUpstreamError as exc:
            print(f"FAILED {exc}", file=sys.stderr)
            return 2
        for st in statuses:
            print(st.message())
        return 1 if any(st.action_needed for st in statuses) else 0
    snapshot = args.snapshot or up.pins()[-1].snapshot
    tarball = Path(args.tarball).read_bytes() if args.tarball else None
    try:
        result = up.refresh_from_registry(
            snapshot, args.version, packument, allow_prerelease=args.allow_prerelease,
            tarball=tarball, dry_run=args.dry_run,
        )
    except up.SchemaUpstreamError as exc:
        print(f"FAILED {exc}", file=sys.stderr)
        return 2
    for line in result.lines():
        print(line)
    if not args.dry_run:
        print("next: python scripts/build_bedrock_reference.py (agent reference topics come from the "
              "schema), pytest -q, portkit eval --corpus --mct; see src/portkit/validate/schemas/SOURCE.md")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="portkit")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("convert", help="convert a Java mod to a Bedrock pack tree")
    p.add_argument("source", help="a mod .jar, or an unpacked directory containing assets/ and data/")
    p.add_argument("out")
    p.add_argument("--namespace")
    p.add_argument(
        "--no-addon", action="store_true", help="write the pack tree only, no .mcaddon"
    )
    p.add_argument(
        "--config", action="append", metavar="MOD.FLAG=true|false",
        help=(
            "set a mod config flag for this conversion, as a Java player would in the "
            "mod's config file (repeatable), e.g. mythicmetals.enableDusts=true. FLAG is "
            "the flag as the mod's load conditions name it or the option's own config "
            "key; it replaces the default cited from the mod's source, both ways. A cited "
            "number option takes a number in the range the mod accepts, e.g. "
            "farmersdelight.cuttingBoardFortuneBonus=0.25. An unknown mod or flag, or a "
            "number out of range, is an error listing the valid ones"
        ),
    )
    p.add_argument(
        "--config-file", metavar="PATH",
        help=(
            "read mod config flags and number options from a JSON or TOML file "
            "({\"mod\": {\"flag\": true}} "
            "or {\"mod.flag\": true}); --config settings win over it. Every run with "
            "settings writes OUT/config-overrides.json, which reproduces it"
        ),
    )
    p.add_argument(
        "--experiment", action="append", metavar="NAME", choices=list(EXPERIMENTS),
        help=(
            "convert for a world that runs this Bedrock experiment (repeatable). "
            "upcoming_creator_features ships blocks that hold items behind a menu in "
            "Java as Bedrock containers (minecraft:block_entity container, block "
            "format 1.26.50); the pack then needs the world's Upcoming Creator "
            "Features experiment on. Without it they stay decoration only"
        ),
    )
    p.add_argument(
        "--agent", action="store_true",
        help=(
            "send the residue through the agent loop, one session per group "
            "(provider from PORTKIT_LLM_PROVIDER / PORTKIT_LLM_MODEL)"
        ),
    )
    p.add_argument(
        "--agent-max-steps", type=int, default=12, metavar="N",
        help="step budget per residue group (default 12)",
    )
    p.add_argument(
        "--agent-max-tokens", type=int, metavar="N",
        help="token ceiling for the whole agent run, input plus output",
    )
    p.add_argument(
        "--agent-max-cost", type=float, metavar="USD",
        help=(
            "dollar ceiling for the whole agent run; needs PORTKIT_LLM_INPUT_PRICE "
            "and PORTKIT_LLM_OUTPUT_PRICE (USD per million tokens)"
        ),
    )
    p.add_argument(
        "--agent-max-total-cost", type=float, metavar="USD",
        help=(
            "dollar ceiling across all --repeat runs: each run's ceiling is tightened "
            "to what is left, and once it is spent no further run starts (they are "
            "listed as skipped in repeat-summary.json); needs the same prices"
        ),
    )
    p.add_argument(
        "--agent-record", metavar="PATH",
        help="write every agent completion of this run to a JSONL transcript",
    )
    p.add_argument(
        "--agent-replay", metavar="PATH",
        help=(
            "run the agent from a recorded transcript instead of a provider "
            "(implies --agent; no API key or network)"
        ),
    )
    p.add_argument(
        "--repeat", type=int, default=1, metavar="N",
        help=(
            "run the agent conversion N times (default 1) into OUT/run-1..N, "
            "recording PATH-1..N.jsonl with --agent-record, and print the mean "
            "and stdev of resolved groups, steps, tokens and cost "
            "(also written to OUT/repeat-summary.json). "
            "Set PORTKIT_LLM_TEMPERATURE to fix sampling across runs"
        ),
    )
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("validate", help="validate a converted tree")
    p.add_argument("tree")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("report", help="Markdown report for a converted tree")
    p.add_argument("tree")
    p.add_argument("-o", "--out", help="write to a file instead of stdout")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("probe", help="build a verification probe pack (dev harness)")
    p.add_argument("out")
    p.add_argument(
        "--kind", choices=("axis", "rotation", "pivot", "face", "turn", "sideturn"), default="axis",
        help=(
            "axis: is Bedrock's X flipped. rotation: which way a rotation leans. "
            "pivot: where an off-centre rotation origin lands. "
            "face: which uv key a one-sided face needs after the mirror."
        ),
    )
    p.add_argument(
        "--models",
        default=str(FIXTURES / "rotated_model_mod/input/assets/examplemod/models/block"),
        help="directory holding rot_x.json, rot_y.json, rot_z.json (rotation probe)",
    )
    p.add_argument(
        "--model",
        default=str(FIXTURES / "asymmetric_model_mod/input/assets/examplemod/models/block/probe.json"),
    )
    p.add_argument(
        "--texture",
        default=str(FIXTURES / "asymmetric_model_mod/input/assets/examplemod/textures/block/probe.png"),
    )
    p.add_argument("--namespace", default="examplemod")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("eval", help="run the whole fixture corpus")
    p.add_argument("--fixtures")
    p.add_argument(
        "--baseline",
        help="per-fixture coverage baseline to enforce (default: <fixtures>/coverage-baseline.json if present)",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--update-baseline", action="store_true",
        help="rewrite the baseline from this run instead of checking against it",
    )
    g.add_argument("--no-baseline", action="store_true", help="skip the baseline check")
    c = p.add_argument_group(
        "real-mod corpus",
        "with --corpus, run the pinned real mods from fixtures/real/mods.toml instead of "
        "the hand-built fixtures; jars come from the local cache (portkit corpus fetch)",
    )
    c.add_argument("--corpus", action="store_true", help="evaluate the real-mod corpus")
    c.add_argument("--manifest", metavar="PATH", help="corpus manifest (default fixtures/real/mods.toml)")
    c.add_argument("--fetch", action="store_true",
                   help="with --corpus, download missing jars and the vanilla sound list first")
    c.add_argument("--include-optional", action="store_true",
                   help="with --corpus, also run the mods marked optional in the manifest "
                        "(skipped by default; --fixture NAME runs any one mod)")
    c.add_argument(
        "--mct", action="store_true",
        help="also run Mojang's `mct validate` (@minecraft/creator-tools) on each converted tree "
             "and report its findings by severity and rule; report-only, never fails the run, "
             "skipped with a note when mct is not on PATH (#113)",
    )
    a = p.add_argument_group(
        "agent matrix",
        "with --agent, run the fixture residue through each provider/model instead and print "
        "one row per target: pass/fail/unscored, pass rate, steps, tool calls per success, "
        "format failures, tokens, stop reasons",
    )
    a.add_argument("--agent", action="store_true", help="run the agent eval matrix")
    a.add_argument("--target", action="append", metavar="PROVIDER:MODEL[@BASE_URL]",
                   help="a provider and model to evaluate (repeatable); an optional @BASE_URL "
                        "points that row at its own endpoint, e.g. "
                        "openai:anthropic/claude-haiku-4.5@https://openrouter.ai/api/v1")
    a.add_argument("--provider", help="shorthand for one --target")
    a.add_argument("--model", help="shorthand for one --target")
    a.add_argument("--fixture", "--agent-fixture", action="append", metavar="NAME",
                   help="limit to these fixtures, or with --corpus these mods "
                        "(default: every fixture with residue, or every mod)")
    a.add_argument("--agent-replay", metavar="PATH",
                   help="replay a transcript (one fixture) or a directory of <fixture>.jsonl; no network")
    a.add_argument("--agent-max-steps", type=int, default=12, metavar="N", help="step budget per group (default 12)")
    a.add_argument("--agent-max-tokens", type=int, metavar="N", help="token ceiling per target run, per fixture")
    a.add_argument("--agent-max-cost", type=float, metavar="USD", help="dollar ceiling per target run, per fixture")
    a.add_argument("--json", "--matrix-out", dest="json", metavar="PATH",
                   help="also write the rows, with per-fixture and per-task scores, as JSON "
                        "(without --agent: the coverage rows, plus the mct block with --mct)")
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("corpus", help="fetch or list the pinned real-mod jars (#21)")
    p.add_argument("action", choices=["fetch", "list"])
    p.add_argument("--manifest", metavar="PATH", help="corpus manifest (default fixtures/real/mods.toml)")
    p.add_argument("--include-optional", action="store_true",
                   help="also the mods marked optional in the manifest (skipped by default)")
    p.add_argument("--fixture", action="append", metavar="NAME",
                   help="only these mods, optional or not (repeatable)")
    p.set_defaults(func=cmd_corpus)

    p = sub.add_parser("sample", help="build the random-sample manifest from Modrinth's most-downloaded mods (#234)")
    p.add_argument("action", choices=["build"])
    p.add_argument("--count", type=int, default=50, help="how many content mods to pin (default 50)")
    p.add_argument("--licences", choices=["all", "open"], default="all",
                   help="all: every licence (default, as the corpus); open: SPDX ids only, "
                        "no LicenseRef-* (All Rights Reserved, custom)")
    p.add_argument("--out", default=str(SAMPLE_MANIFEST), metavar="PATH",
                   help="manifest to write (default fixtures/sample/mods.toml)")
    p.set_defaults(func=cmd_sample)

    p = sub.add_parser("gaps", help="convert the sample and rank residue reasons across it (#234)")
    p.add_argument("action", choices=["run", "board"])
    p.add_argument("shards", nargs="*", metavar="SHARD_JSON", help="board: the shard files to merge")
    p.add_argument("--manifest", metavar="PATH", help="run: sample manifest (default fixtures/sample/mods.toml)")
    p.add_argument("--shard", metavar="I/N", help="run: only every N-th mod starting at I (default 1/1)")
    p.add_argument("--fixture", action="append", metavar="NAME", help="run: only these mods (repeatable)")
    p.add_argument("--timeout", type=float, default=900.0, metavar="S",
                   help="run: seconds per mod conversion before it counts as timed out (default 900)")
    p.add_argument("--mct", action="store_true", help="run: also count mct findings per mod (report-only)")
    p.add_argument("--out", default="gap-shard.json", metavar="PATH", help="run: shard file to write")
    p.add_argument("--previous", metavar="PATH", help="board: the previous leaderboard JSON, for the trend")
    p.add_argument("--json", default="gap-leaderboard.json", metavar="PATH", help="board: leaderboard JSON")
    p.add_argument("--md", metavar="PATH", help="board: leaderboard markdown (default: print it)")
    p.add_argument("--top", type=int, default=50, help="board: reasons shown in the markdown (default 50)")
    p.set_defaults(func=cmd_gaps)

    p = sub.add_parser("gauntlet", help="the top-50 gauntlet (#277): pin the 50 jars, run them, build docs/gauntlet.md (#278)")
    p.add_argument("action", choices=["pin", "run", "board"])
    p.add_argument("shards", nargs="*", metavar="SHARD_JSON", help="board: the shard files to merge")
    p.add_argument("--manifest", metavar="PATH", help="gauntlet manifest (default fixtures/real/gauntlet.toml)")
    p.add_argument("--shard", metavar="I/N", help="run: only every N-th mod starting at I (default 1/1)")
    p.add_argument("--fixture", action="append", metavar="NAME", help="run: only these mods (repeatable)")
    p.add_argument("--timeout", type=float, default=900.0, metavar="S",
                   help="run: seconds per mod conversion before it counts as timed out (default 900)")
    p.add_argument("--mct", action="store_true", help="run: also count mct findings per mod (report-only)")
    p.add_argument("--out", default="gauntlet-shard.json", metavar="PATH", help="run: shard file to write")
    p.add_argument("--previous", metavar="PATH", help="board: the previous board JSON, for the trend")
    p.add_argument("--baseline", metavar="PATH",
                   help="board: banked baseline to compare coverage with (default fixtures/real/gauntlet-baseline.json)")
    p.add_argument("--bank", metavar="PATH", help="board: also write this board as the baseline to PATH")
    p.add_argument("--json", default="gauntlet-board.json", metavar="PATH", help="board: board JSON")
    p.add_argument("--md", metavar="PATH", help="board: board markdown, e.g. docs/gauntlet.md (default: print it)")
    p.add_argument("--top", type=int, default=25, help="board: reason classes shown (default 25)")
    p.set_defaults(func=cmd_gauntlet)

    p = sub.add_parser(
        "reference",
        help="fetch or list reference data: the Bedrock vanilla sound list (#124), "
             "loader/vanilla item tag membership (#160) and the vanilla block model "
             "templates stairs, slabs and walls are built from, and the Forge SRG / "
             "Fabric intermediary -> Mojang name tables (#235)",
    )
    p.add_argument("action", choices=["fetch", "list"])
    p.add_argument("--mod", metavar="JAR",
                   help="only the tag data this mod's loader and game version need "
                        "(default: every pinned set)")
    p.set_defaults(func=cmd_reference)

    p = sub.add_parser(
        "ingame",
        help="in-game checks on a Bedrock Dedicated Server (#238): fetch the pinned server "
             "(--accept-eula), write a converted tree's check pack, or run it headlessly",
    )
    p.add_argument("action", choices=["fetch-server", "pack", "run"])
    p.add_argument("--dir", default="bds", help="fetch-server: where to unpack the server")
    p.add_argument("--accept-eula", action="store_true",
                   help="fetch-server: agree to the Minecraft EULA (minecraft.net/eula) and the "
                        "Microsoft Privacy Statement, which downloading the server means")
    p.add_argument("--tree", help="pack/run: a converted tree (behavior_pack/, resource_pack/)")
    p.add_argument("--name", help="pack/run: a name for the run (default: the tree's directory name)")
    p.add_argument("--out", default="ingame-out", help="pack: the check pack; run: the report directory")
    p.add_argument("--server", help="run: an unpacked server (fetch-server --dir)")
    p.add_argument("--work", help="run: the server copy to run in (default OUT/server)")
    p.add_argument("--experiment", action="append", metavar="NAME",
                   help="run: toggle this experiment on in the world's level.dat (repeatable)")
    p.add_argument("--timeout", type=float, default=900, help="run: seconds before the run is stopped")
    p.add_argument("--keep-server", action="store_true", help="run: keep the server copy afterwards")
    p.set_defaults(func=cmd_ingame)

    p = sub.add_parser(
        "schemas",
        help="check whether the stable @minecraft/bedrock-schemas release of each vendored "
             "snapshot is out, or re-vendor a snapshot from it (#155)",
    )
    p.add_argument("action", choices=["check", "refresh"])
    p.add_argument("--snapshot", metavar="VERSION",
                   help="refresh: the snapshot directory (default: the newest in SOURCE.md)")
    p.add_argument("--version", metavar="PKG_VERSION",
                   help="refresh: the package version (default: the snapshot's stable release)")
    p.add_argument("--allow-prerelease", action="store_true",
                   help="refresh: allow a -beta package version")
    p.add_argument("--tarball", metavar="PATH",
                   help="refresh: use this downloaded .tgz (still checked against the registry hash)")
    p.add_argument("--dry-run", action="store_true", help="refresh: report the diff, write nothing")
    p.set_defaults(func=cmd_schemas)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
