from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path

from .agent import Budget, Pricing, make_client  # noqa: F401  (re-exported for tests)
from .agent.residue import ResidueAgent
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


def cmd_eval(args) -> int:
    """Dispatch between the coverage matrix and the agent eval matrix (#77).

    ``portkit eval`` prints the deterministic coverage table (the ratchet from
    ``coverage-baseline.json``). ``portkit eval --agent --target provider:model``
    runs the residue agent on each fixture, once per target, and prints the
    per-provider pass rate / step count / format-failure matrix.
    """
    if getattr(args, "agent", False):
        return _cmd_eval_agent(args)
    return _cmd_eval_coverage(args)


def _cmd_eval_coverage(args) -> int:
    """The deterministic coverage matrix. ``portkit eval`` without ``--agent``."""
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


# --- agent eval matrix (issue #77) -------------------------------------------
#
# ``portkit eval --agent --target provider:model`` runs every fixture's residue
# through the agent loop, once per target, and prints a row per (fixture,
# target). Tasks are scored on three outcomes, not two:
#
#   pass     validator clean and the residue cleared
#   fail     validator rejected what was written, or the agent gave up
#   unscored provider error, crash in the loop, or the validator never ran
#
# Unscored tasks are reported separately and excluded from the pass rate, so
# a provider outage does not look like a worse model. Format failures (tool
# names or arguments the model got wrong) are counted per provider: a model
# that speaks the wrong wire format looks different from a model that just
# cannot solve the task.

_AGENT_OUTCOME_PASS = "pass"
_AGENT_OUTCOME_FAIL = "fail"
_AGENT_OUTCOME_UNSCORED = "unscored"


def _score_residue_outcomes(outcomes) -> tuple[int, int, int]:
    """(pass, fail, unscored) counts across one fixture's residue groups.

    A group's outcome maps to:
      pass     status == "resolved" (or "partial" whose writes validate, but
               we keep it simple: only resolved counts as a pass)
      unscore  status == "skipped" (deterministic refusal kind) or
               status == "error" (provider failure during the session)
      fail     everything else: "unresolved", "rolled_back", "partial"
    """
    passes = fails = unscored = 0
    for o in outcomes:
        if o.status == "resolved":
            passes += 1
        elif o.status in ("skipped", "error"):
            unscored += 1
        else:
            fails += 1
    return passes, fails, unscored


def _parse_target(spec: str) -> tuple[str, str, str | None]:
    """``anthropic:claude-haiku-4.5`` -> (``anthropic``, ``claude-haiku-4.5``, ``None``).

    ``openai:anthropic/claude-haiku-4.5@https://openrouter.ai/api/v1`` adds an
    optional ``base_url`` after ``@`` so the same run can hit the OpenAI path
    on OpenRouter and the gemini_native path on Google's endpoint without a
    separate shell-level config. The factory's own DEFAULT_BASE_URLS still
    kicks in when no base_url is given.

    Raises ValueError with a useful message if the form is wrong. ``openai`` /
    ``anthropic`` / ``gemini`` / ``gemini_native`` are the provider names the
    factory knows; anything else is a typo before the colon.
    """
    if ":" not in spec:
        raise ValueError(
            f"--target {spec!r} must be provider:model "
            "(e.g. anthropic:claude-haiku-4.5, gemini_native:gemini-flash-latest, "
            "openai:anthropic/claude-haiku-4.5@https://openrouter.ai/api/v1)"
        )
    head, _, base_url = spec.partition("@")
    provider, model = head.split(":", 1)
    provider = provider.strip()
    model = model.strip()
    base_url = base_url.strip() or None
    if not provider or not model:
        raise ValueError(f"--target {spec!r} must be provider:model with both parts non-empty")
    return provider, model, base_url


def _resolve_agent_out_tree(root: Path, fixture: str, target: str, run: int) -> Path:
    """Where this (fixture, target) writes its converted tree on disk.

    Used as the parent dir for a fresh TemporaryDirectory so the agent's
    output survives long enough for the validator to score it.
    """
    slug = target.replace(":", "_").replace("/", "_")
    return root / f".eval-agent-{fixture}-{slug}-run{run}"


def _run_target_against_fixture(case: Path, provider: str, model: str, base_url: str | None, args) -> dict:
    """Convert one fixture with one (provider, model) and return the row data.

    Catches every error mode the issue lists: provider failure, loop crash,
    validator never ran. Each becomes ``unscored`` rather than ``fail`` so
    a model that breaks the harness does not get punished as a weaker one.
    """
    import tempfile

    fixture_name = case.name
    # Reset the env-driven factory: --target wins over the shell. Pricing
    # is only required for dollar ceilings; both are off by default.
    saved_env = {k: os.environ.get(k) for k in (
        "PORTKIT_LLM_PROVIDER", "PORTKIT_LLM_MODEL",
        "PORTKIT_LLM_BASE_URL", "PORTKIT_LLM_INPUT_PRICE",
        "PORTKIT_LLM_OUTPUT_PRICE", "PORTKIT_LLM_TEMPERATURE",
    )}
    try:
        os.environ["PORTKIT_LLM_PROVIDER"] = provider
        os.environ["PORTKIT_LLM_MODEL"] = model
        if base_url is not None:
            os.environ["PORTKIT_LLM_BASE_URL"] = base_url
        elif provider == "openai":
            # If the user did not pin a base_url, let the factory fall back
            # to OpenAI's default endpoint (``api.openai.com``). Without this
            # ``PORTKIT_LLM_BASE_URL`` set by the shell would survive the
            # ``try`` and reach into a target whose provider never asked for
            # it (issue #77: matrix rows must be self-contained).
            os.environ.pop("PORTKIT_LLM_BASE_URL", None)
        # ``base_url`` is left alone on purpose for non-openai providers: a
        # user pointed at OpenRouter for anthropic (via provider=openai)
        # keeps that route, and the native Gemini endpoint stays native for
        # provider=gemini_native. The factory falls back to
        # DEFAULT_BASE_URLS only when nothing is set.

        pricing = Pricing.from_env()
        budget = Budget(
            max_steps=args.agent_max_steps,
            max_tokens=args.agent_max_tokens,
            max_cost=args.agent_max_cost,
            pricing=pricing,
        )

        try:
            client = make_client()
        except Exception as exc:
            return {
                "fixture": fixture_name,
                "provider": provider,
                "model": model,
                "outcome": _AGENT_OUTCOME_UNSCORED,
                "pass": 0, "fail": 0, "unscored": 0,
                "groups": 0, "steps": 0, "tokens": 0,
                "cost_usd": None, "stopped_by": None,
                "format_failures": 0,
                "reason": f"cannot build client: {type(exc).__name__}: {exc}",
            }

        agent = ResidueAgent(client, budget=budget)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            try:
                result = convert(case / "input", out, agent=agent)
            except Exception as exc:
                return {
                    "fixture": fixture_name,
                    "provider": provider,
                    "model": model,
                    "outcome": _AGENT_OUTCOME_UNSCORED,
                    "pass": 0, "fail": 0, "unscored": 0,
                    "groups": 0, "steps": 0, "tokens": 0,
                    "cost_usd": None, "stopped_by": None,
                    "format_failures": 0,
                    "reason": f"convert crashed: {type(exc).__name__}: {exc}",
                }

        agent_run = result.agent
        if agent_run is None:
            return {
                "fixture": fixture_name,
                "provider": provider,
                "model": model,
                "outcome": _AGENT_OUTCOME_PASS,
                "pass": 0, "fail": 0, "unscored": 0,
                "groups": 0, "steps": 0, "tokens": 0,
                "cost_usd": None, "stopped_by": None,
                "format_failures": 0,
                "reason": "no residue",
            }
        p, f, u = _score_residue_outcomes(agent_run.outcomes)
        if u and not p and not f:
            outcome = _AGENT_OUTCOME_UNSCORED
        elif f and not p:
            outcome = _AGENT_OUTCOME_FAIL
        else:
            outcome = _AGENT_OUTCOME_PASS
        return {
            "fixture": fixture_name,
            "provider": provider,
            "model": model,
            "outcome": outcome,
            "pass": p, "fail": f, "unscored": u,
            "groups": len(agent_run.outcomes),
            "steps": agent_run.spend.steps,
            "tokens": agent_run.spend.tokens,
            "cost_usd": None if agent_run.spend.cost is None else round(agent_run.spend.cost, 6),
            "stopped_by": agent_run.limit,
            "format_failures": agent_run.format_failures,
        }
    finally:
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _format_eval_matrix(rows: list[dict]) -> str:
    """The human-readable matrix: one row per (fixture, target)."""
    lines = []
    cols = ("fixture", "provider:model", "pass/fail/unscored", "groups",
            "steps", "tokens", "$", "stopped_by", "fmt_fail", "outcome")
    header = "  ".join(c.ljust(14) for c in cols[:9]) + "  outcome"
    lines.append(header)
    lines.append("-" * len(header))
    for r in rows:
        target = f"{r['provider']}:{r['model']}"
        score = f"{r['pass']}/{r['fail']}/{r['unscored']}"
        lines.append(
            "  ".join([
                r["fixture"].ljust(14),
                target.ljust(22),
                score.ljust(16),
                str(r["groups"]).ljust(6),
                str(r["steps"]).ljust(5),
                str(r["tokens"]).ljust(6),
                ("" if r["cost_usd"] is None else f"${r['cost_usd']:.4f}").ljust(7),
                (r["stopped_by"] or "-").ljust(10),
                str(r["format_failures"]).ljust(8),
                r["outcome"],
            ])
        )
    return "\n".join(lines)


def _per_target_totals(rows: list[dict]) -> list[dict]:
    """One row per target with aggregated counts. Pass rate excludes unscored."""
    by_target: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        by_target.setdefault((r["provider"], r["model"]), []).append(r)
    out = []
    for (provider, model), group in sorted(by_target.items()):
        total_pass = sum(r["pass"] for r in group)
        total_fail = sum(r["fail"] for r in group)
        total_unscored = sum(r["unscored"] for r in group)
        steps = sum(r["steps"] for r in group)
        tokens = sum(r["tokens"] for r in group)
        fmt = sum(r["format_failures"] for r in group)
        out.append({
            "provider": provider, "model": model,
            "pass": total_pass, "fail": total_fail, "unscored": total_unscored,
            "pass_rate": (
                total_pass / (total_pass + total_fail)
                if (total_pass + total_fail) else None
            ),
            "steps": steps, "tokens": tokens,
            "format_failures": fmt,
            "fixtures": len(group),
        })
    return out


def _format_target_totals(totals: list[dict]) -> str:
    lines = [f"{'provider:model':<32} {'pass':>4} {'fail':>4} {'unscored':>8}  {'pass rate':>9}  {'steps':>5}  {'tokens':>7}  fmt_fail"]
    for t in totals:
        target = f"{t['provider']}:{t['model']}"
        rate = "n/a" if t["pass_rate"] is None else f"{t['pass_rate']*100:5.1f}%"
        lines.append(
            f"{target:<32} {t['pass']:>4} {t['fail']:>4} {t['unscored']:>8}  {rate:>9}  "
            f"{t['steps']:>5}  {t['tokens']:>7}  {t['format_failures']}"
        )
    return "\n".join(lines)


def _cmd_eval_agent(args) -> int:
    """The per-provider pass rate / steps / format-failure matrix from #77."""
    if not args.target:
        print("--agent requires at least one --target provider:model", file=sys.stderr)
        return 2
    try:
        targets = [_parse_target(t) for t in args.target]
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    root = Path(args.fixtures or FIXTURES)
    if args.agent_fixture:
        cases = [root / args.agent_fixture]
        if not cases[0].is_dir() or not (cases[0] / "input").is_dir():
            print(f"fixture {cases[0]} has no input/", file=sys.stderr)
            return 2
    else:
        cases = sorted(p for p in root.iterdir() if (p / "input").is_dir())

    if not cases:
        print(f"no fixtures under {root}", file=sys.stderr)
        return 1

    print(
        f"agent eval: {len(cases)} fixture(s) x {len(targets)} target(s)\n"
        f"  budgets: max_steps={args.agent_max_steps} "
        f"max_tokens={args.agent_max_tokens or '-'} "
        f"max_cost={args.agent_max_cost or '-'}\n"
    )

    rows: list[dict] = []
    for case in cases:
        for provider, model, base_url in targets:
            target = f"{provider}:{model}" + (f"@{base_url}" if base_url else "")
            print(f"--> {case.name} via {target}", file=sys.stderr)
            row = _run_target_against_fixture(case, provider, model, base_url, args)
            rows.append(row)

    print("\nper (fixture, target):")
    print(_format_eval_matrix(rows))
    print("\nper target:")
    print(_format_target_totals(_per_target_totals(rows)))

    if args.matrix_out:
        out = Path(args.matrix_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "rows": rows,
            "totals": _per_target_totals(rows),
        }, indent=2) + "\n")
        print(f"\nmatrix written: {out}")
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

    p = sub.add_parser(
        "eval",
        help=(
            "run the whole fixture corpus (coverage matrix by default; "
            "with --agent, the per-provider residue-agent matrix from #77)"
        ),
    )
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
    # Agent mode (#77): run the agent loop on every fixture's residue, once
    # per --target provider:model. Scores pass/fail/unscored separately and
    # counts tool-call format failures per provider.
    p.add_argument(
        "--agent", action="store_true",
        help="run the residue agent against each fixture and print the per-provider matrix",
    )
    p.add_argument(
        "--target", action="append", metavar="PROVIDER:MODEL", default=[],
        help=(
            "provider:model pair to test (repeatable). Required with --agent. "
            "Providers: openai, anthropic, gemini, gemini_native."
        ),
    )
    p.add_argument(
        "--agent-fixture", metavar="NAME",
        help="with --agent, only run this fixture (otherwise every fixture under --fixtures)",
    )
    p.add_argument(
        "--agent-max-steps", type=int, default=12, metavar="N",
        help="step budget per residue group (default 12, same as convert --agent)",
    )
    p.add_argument(
        "--agent-max-tokens", type=int, metavar="N",
        help="token ceiling for the whole agent run (input + output), shared across fixtures",
    )
    p.add_argument(
        "--agent-max-cost", type=float, metavar="USD",
        help=(
            "dollar ceiling for the whole agent run; needs "
            "PORTKIT_LLM_INPUT_PRICE and PORTKIT_LLM_OUTPUT_PRICE"
        ),
    )
    p.add_argument(
        "--matrix-out", metavar="PATH",
        help="with --agent, write the JSON matrix to this path",
    )
    p.set_defaults(func=cmd_eval)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
