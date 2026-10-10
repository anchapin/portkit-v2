from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

from .ingest import IngestError
from .pipeline import convert
from .validate import validate_tree

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _print_findings(report) -> None:
    for f in report.findings:
        mark = "ERROR" if f.severity == "error" else "warn "
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


def cmd_convert(args) -> int:
    repeat = getattr(args, "repeat", 1) or 1
    if repeat < 1:
        print("--repeat must be at least 1", file=sys.stderr)
        return 2
    if repeat == 1:
        code, _ = _convert_once(args)
        return code
    if not (args.agent or args.agent_replay):
        print("--repeat only makes sense with --agent", file=sys.stderr)
        return 2

    rows: list[dict] = []
    worst = 0
    for run in range(1, repeat + 1):
        run_args = argparse.Namespace(**vars(args))
        run_args.out = str(Path(args.out) / f"run-{run}")
        if args.agent_record:
            run_args.agent_record = _numbered(args.agent_record, run)
        print(f"\n=== run {run} of {repeat} -> {run_args.out} ===")
        code, result = _convert_once(run_args)
        if code == 2 and result is None:
            return 2  # could not start at all: repeating will not help
        worst = max(worst, code)
        if result is not None and result.agent is not None:
            rows.append(_run_row(run, result))
    summary = _repeat_summary(rows)
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
        "statuses": {o.key: o.status for o in agent.outcomes},
        "steps": agent.spend.steps,
        "tokens": agent.spend.tokens,
        "cost_usd": None if agent.spend.cost is None else round(agent.spend.cost, 6),
        "ok": result.report.ok,
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
    for r in rows:
        for key, status in r["statuses"].items():
            per_group[key] = per_group.get(key, 0) + (status == "resolved")
    return {
        "runs": len(rows),
        "resolved": _stats([r["resolved"] for r in rows]),
        "steps": _stats([r["steps"] for r in rows]),
        "tokens": _stats([r["tokens"] for r in rows]),
        "cost_usd": _stats(costs) if len(costs) == len(rows) else None,
        "group_resolved_in": per_group,
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
    for key, hits in summary["group_resolved_in"].items():
        lines.append(f"  {key}: resolved in {hits} of {n}")
    return "\n".join(lines)


def _convert_once(args):
    """One conversion. Returns (exit code, result or None if it never ran)."""
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
        )
    except IngestError as exc:
        print(f"cannot read {args.source}: {exc}", file=sys.stderr)
        return 2, None
    print(json.dumps(result.summary(), indent=2))
    if result.agent:
        print(
            f"\nagent resolved {len(result.agent.resolved)} of "
            f"{len(result.agent.outcomes)} residue group(s):"
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
    from .agent.matrix import agent_fixtures, render, run_matrix
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
            provider, _, model = spec.partition(":")
            label = spec if provider else f"(env):{model}"

            try:  # a missing key or unknown provider is a setup error, not a score
                make_client(provider or None, model or None)
            except Exception as exc:
                print(f"{label}: {exc}", file=sys.stderr)
                return 2

            def factory(name, provider=provider or None, model=model or None):
                return make_client(provider, model)
            targets.append((label, factory))
        cases = agent_fixtures(root, args.fixture or ())

    if not cases:
        print(f"no agent fixtures under {root}", file=sys.stderr)
        return 1
    rows = run_matrix(targets, cases, budget)
    print(f"fixtures: {', '.join(c.name for c in cases)}")
    print(render(rows))
    if args.json:
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

    root = Path(args.fixtures or FIXTURES)
    cases = sorted(p for p in root.iterdir() if (p / "input").is_dir())
    if not cases:
        print(f"no fixtures under {root}")
        return 1

    rows, measured, failures = [], [], 0
    for case in cases:
        with tempfile.TemporaryDirectory() as tmp:
            result = convert(case / "input", Path(tmp) / "out")
            ok = result.report.ok
            failures += 0 if ok else 1
            rows.append(
                (case.name, result.file_count, result.residue_count, result.coverage, ok)
            )
            measured.append(
                bl.Measured(case.name, result.file_count, result.residue_count, result.coverage)
            )

    width = max(len(r[0]) for r in rows)
    print(f"{'fixture'.ljust(width)}  files  residue  coverage  valid")
    for name, handled, residue, coverage, ok in rows:
        print(f"{name.ljust(width)}  {handled:5d}  {residue:7d}  {coverage:7.1f}%  {'yes' if ok else 'NO'}")

    baseline_path = Path(args.baseline) if args.baseline else root / bl.BASELINE_NAME

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
    a = p.add_argument_group(
        "agent matrix",
        "with --agent, run the fixture residue through each provider/model instead and print "
        "one row per target: pass/fail/unscored, pass rate, steps, tool calls per success, "
        "format failures, tokens, stop reasons",
    )
    a.add_argument("--agent", action="store_true", help="run the agent eval matrix")
    a.add_argument("--target", action="append", metavar="PROVIDER:MODEL",
                   help="a provider and model to evaluate (repeatable)")
    a.add_argument("--provider", help="shorthand for one --target")
    a.add_argument("--model", help="shorthand for one --target")
    a.add_argument("--fixture", action="append", metavar="NAME",
                   help="limit to these fixtures (default: every fixture with residue)")
    a.add_argument("--agent-replay", metavar="PATH",
                   help="replay a transcript (one fixture) or a directory of <fixture>.jsonl; no network")
    a.add_argument("--agent-max-steps", type=int, default=12, metavar="N", help="step budget per group (default 12)")
    a.add_argument("--agent-max-tokens", type=int, metavar="N", help="token ceiling per target run, per fixture")
    a.add_argument("--agent-max-cost", type=float, metavar="USD", help="dollar ceiling per target run, per fixture")
    a.add_argument("--json", metavar="PATH", help="also write the rows, with per-task scores, as JSON")
    p.set_defaults(func=cmd_eval)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
