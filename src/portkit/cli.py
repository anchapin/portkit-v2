from __future__ import annotations

import argparse
import json
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
    """The agent for ``convert --agent``, with the provider from the environment."""
    from .agent import Budget, Pricing, make_client
    from .agent.residue import ResidueAgent

    budget = Budget(
        max_steps=args.agent_max_steps,
        max_tokens=args.agent_max_tokens,
        max_cost=args.agent_max_cost,
        pricing=Pricing.from_env(),
    )
    return ResidueAgent(make_client(), budget=budget)


def cmd_convert(args) -> int:
    agent = None
    if args.agent:
        try:
            agent = _residue_agent(args)
        except ValueError as exc:
            print(f"cannot start the residue agent: {exc}", file=sys.stderr)
            return 2
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
        return 2
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
        return 1
    return 0


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


def cmd_eval(args) -> int:
    """Run every fixture and print the coverage table. This is the number that matters.

    With a baseline (``fixtures/coverage-baseline.json`` by default, or
    ``--baseline``), any fixture whose coverage or converted file count drops
    below it fails the run, naming the fixture and the delta.
    """
    import os
    import tempfile

    from . import baseline as bl

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
    p.set_defaults(func=cmd_eval)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
