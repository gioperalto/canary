"""CLI entry point for the canary validator.

Usage:
    # Validate all chicks found in nest/
    canary

    # Validate specific targets
    canary --targets webpage brainstorm

    # Auto-detect changed chicks in a PR (CI mode)
    canary --changed-only --base-ref origin/main

    # Skip OTel observer
    canary --no-otel

    # Output report to custom path
    canary --report-path ./my-report.md

    # Exit with non-zero code on failure (for CI gating)
    canary --exit-code

    # Output PR comment body to stdout
    canary --pr-comment
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from canary.checkpoints import validate_chick
from canary.config import discover_changed_chicks, load_yaml, resolve_targets
from canary.models import CanaryReport, ChickReport
from canary.observer import observe
from canary.report import render_pr_comment, render_report, write_report


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="canary",
        description="Harnest Canary — validate harnest chick structure and conventions.",
    )
    p.add_argument(
        "--targets",
        nargs="*",
        help="Chick directory names to validate (default: auto-detect from harnest.yaml or nest/).",
    )
    p.add_argument(
        "--nest-root",
        type=Path,
        default=None,
        help="Path to the nest directory containing chick subdirectories (default: ./nest).",
    )
    p.add_argument(
        "--changed-only",
        action="store_true",
        help="Only validate chicks with changes relative to --base-ref (for CI).",
    )
    p.add_argument(
        "--base-ref",
        default="origin/main",
        help="Git ref to diff against when using --changed-only (default: origin/main).",
    )
    p.add_argument(
        "--no-otel",
        action="store_true",
        help="Skip OTel observer (no backend check, no trace queries).",
    )
    p.add_argument(
        "--report-path",
        type=Path,
        default=Path(".harnest/canary-report.md"),
        help="Path to write the full report (default: .harnest/canary-report.md).",
    )
    p.add_argument(
        "--exit-code",
        action="store_true",
        help="Exit with code 1 if any checkpoint fails (useful for CI gating).",
    )
    p.add_argument(
        "--pr-comment",
        action="store_true",
        help="Print a compact PR comment to stdout instead of writing the full report.",
    )
    p.add_argument(
        "--config",
        type=Path,
        default=Path("harnest.yaml"),
        help="Path to the canary harnest.yaml config (default: ./harnest.yaml).",
    )
    return p


def run(args: argparse.Namespace) -> CanaryReport:
    """Execute the canary validation pipeline and return the report."""
    config = load_yaml(args.config)

    # Determine nest root
    nest_root = args.nest_root or Path.cwd() / "nest"

    # Resolve targets
    if args.changed_only:
        changed = discover_changed_chicks(nest_root, args.base_ref)
        if not changed:
            print("No chick directories changed — nothing to validate.", file=sys.stderr)
            return CanaryReport(targets=[], chick_reports=[])
        target_pairs = [(name, nest_root / name) for name in changed]
    else:
        target_pairs = resolve_targets(config, nest_root, args.targets)

    if not target_pairs:
        print("No target chicks found. Check --targets, harnest.yaml, or nest/ directory.", file=sys.stderr)
        return CanaryReport(targets=[], chick_reports=[])

    target_names = [name for name, _ in target_pairs]
    print(f"Canary validating: {', '.join(target_names)}", file=sys.stderr)

    # Run checkpoints for each target
    chick_reports: list[ChickReport] = []
    for name, path in target_pairs:
        print(f"  [{name}] running 6 checkpoints...", file=sys.stderr)
        results = validate_chick(path)
        cr = ChickReport(name=name, path=path, checkpoints=results)
        passed = cr.passed_count
        failed = cr.failed_count
        print(f"  [{name}] {passed} passed, {failed} failed", file=sys.stderr)
        chick_reports.append(cr)

    # OTel observer
    otel_summary = None
    if not args.no_otel:
        print("  [otel] checking backend...", file=sys.stderr)
        otel_summary = observe()
        status = "reachable" if otel_summary.reachable else "unreachable"
        print(f"  [otel] {otel_summary.backend} — {status}", file=sys.stderr)

    return CanaryReport(
        targets=target_names,
        chick_reports=chick_reports,
        otel_summary=otel_summary,
    )


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    report = run(args)

    if args.pr_comment:
        print(render_pr_comment(report))
    else:
        out = write_report(report, args.report_path)
        print(f"Report written to {out}", file=sys.stderr)
        # Also print to stdout for piping
        print(render_report(report))

    if args.exit_code and report.overall.value == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
