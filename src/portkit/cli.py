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


def cmd_convert(args) -> int:
    try:
        result = convert(
            Path(args.source), Path(args.out), args.namespace, emit_addon=not args.no_addon
        )
    except IngestError as exc:
        print(f"cannot read {args.source}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result.summary(), indent=2))
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


def cmd_eval(args) -> int:
    """Run every fixture and print the coverage table. This is the number that matters."""
    import tempfile

    root = Path(args.fixtures or FIXTURES)
    cases = sorted(p for p in root.iterdir() if (p / "input").is_dir())
    if not cases:
        print(f"no fixtures under {root}")
        return 1

    rows, failures = [], 0
    for case in cases:
        with tempfile.TemporaryDirectory() as tmp:
            result = convert(case / "input", Path(tmp) / "out")
            ok = result.report.ok
            failures += 0 if ok else 1
            rows.append(
                (case.name, result.file_count, result.residue_count, result.coverage, ok)
            )

    width = max(len(r[0]) for r in rows)
    print(f"{'fixture'.ljust(width)}  files  residue  coverage  valid")
    for name, handled, residue, coverage, ok in rows:
        print(f"{name.ljust(width)}  {handled:5d}  {residue:7d}  {coverage:7.1f}%  {'yes' if ok else 'NO'}")
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
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("validate", help="validate a converted tree")
    p.add_argument("tree")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("eval", help="run the whole fixture corpus")
    p.add_argument("--fixtures")
    p.set_defaults(func=cmd_eval)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
