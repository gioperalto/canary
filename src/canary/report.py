"""Generate the canary report as Markdown."""

from __future__ import annotations

from pathlib import Path

from canary.models import CanaryReport, OtelHealthSummary, Status


def render_report(report: CanaryReport) -> str:
    """Render a CanaryReport to Markdown."""
    lines: list[str] = []
    _w = lines.append

    _w("# Canary Report")
    _w("")
    _w(f"**Run date:** {report.run_date}")
    _w(f"**Targets:** {', '.join(report.targets)}")
    _w(f"**Overall:** {report.overall.value}")
    _w("")

    # ── Summary table ──
    _w("## Summary")
    _w("")
    _w("| Chick | Passed | Failed | Overall |")
    _w("|-------|--------|--------|---------|")
    for cr in report.chick_reports:
        _w(f"| {cr.name} | {cr.passed_count}/6 | {cr.failed_count}/6 | {cr.overall.value} |")
    _w("")

    # ── Per-chick details ──
    _w("## Validation Results")
    _w("")
    for cr in report.chick_reports:
        _w(f"### {cr.name}")
        _w("")
        for cp in cr.checkpoints:
            _w(f"#### Checkpoint {cp.number}: {cp.name}")
            _w(f"**Result:** {cp.status.value}")
            if cp.details:
                _w("")
                for d in cp.details:
                    _w(f"- {d}")
            _w("")

    # ── OTel health summary ──
    _w("## OTel Health Summary")
    _w("")
    otel = report.otel_summary
    if otel is None:
        _w("*Observer was not run.*")
    elif not otel.reachable:
        _w(f"**Backend:** {otel.backend}")
        _w(f"**Telemetry enabled:** {'Yes' if otel.telemetry_enabled else 'No'}")
        _w("")
        _w("OTel backend was unreachable — telemetry data not available for this run.")
        _w("")
        _w("To enable OTel monitoring, start Jaeger locally:")
        _w("```bash")
        _w(
            "docker run -d --name jaeger -p 16686:16686 -p 4317:4317 "
            "-p 4318:4318 jaegertracing/all-in-one:latest"
        )
        _w("```")
        _w("Then re-run canary with `CLAUDE_CODE_ENABLE_TELEMETRY=1`.")
        _w("")
        _w("**Dashboard:** Not available")
    else:
        _w(f"**Backend:** {otel.backend}")
        _w(f"**Telemetry enabled:** {'Yes' if otel.telemetry_enabled else 'No'}")
        _w("")
        _w("### Span Summary")
        _w("")
        _w(f"- Total spans: {otel.total_spans}")
        error_pct = (
            f" ({otel.error_spans / otel.total_spans * 100:.1f}%)"
            if otel.total_spans > 0
            else ""
        )
        _w(f"- Error spans: {otel.error_spans}{error_pct}")
        _w(f"- Timeout spans (>5m): {otel.timeout_spans}")
        _w("")
        if otel.anomalies:
            _w("### Anomalies Detected")
            _w("")
            for a in otel.anomalies:
                _w(f"- {a}")
            _w("")
        else:
            _w("### Anomalies Detected")
            _w("")
            _w("None detected.")
            _w("")
        _w(f"**Dashboard:** {otel.dashboard_url or 'Not available'}")
    _w("")

    # ── Diagnostics ──
    failures = [
        (cr.name, cp)
        for cr in report.chick_reports
        for cp in cr.checkpoints
        if cp.status is Status.FAIL
    ]
    _w("## Diagnostics")
    _w("")
    if not failures:
        _w("All checkpoints passed. No issues to report.")
    else:
        _w(f"{len(failures)} checkpoint(s) failed across {len(report.chick_reports)} target(s).")
        _w("")
        for chick_name, cp in failures:
            _w(f"- **{chick_name}** — Checkpoint {cp.number} ({cp.name})")
            for d in cp.details:
                _w(f"  - {d}")
    _w("")
    return "\n".join(lines)


def write_report(report: CanaryReport, output_path: Path) -> Path:
    """Render and write the canary report to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = render_report(report)
    output_path.write_text(content)
    return output_path


def render_pr_comment(report: CanaryReport) -> str:
    """Render a compact PR comment version of the report.

    Suitable for posting as a GitHub PR comment via `gh pr comment`.
    """
    lines: list[str] = []
    _w = lines.append

    icon = "white_check_mark" if report.overall is Status.PASS else "x"
    _w(f"## :{icon}: Canary Report")
    _w("")

    _w("| Chick | Passed | Failed | Overall |")
    _w("|-------|--------|--------|---------|")
    for cr in report.chick_reports:
        status_icon = ":white_check_mark:" if cr.overall is Status.PASS else ":x:"
        _w(f"| {cr.name} | {cr.passed_count}/6 | {cr.failed_count}/6 | {status_icon} |")
    _w("")

    # Compact failure details
    failures = [
        (cr.name, cp)
        for cr in report.chick_reports
        for cp in cr.checkpoints
        if cp.status is Status.FAIL
    ]
    if failures:
        _w("<details>")
        _w("<summary>Failure details</summary>")
        _w("")
        for chick_name, cp in failures:
            _w(f"**{chick_name}** — Checkpoint {cp.number}: {cp.name}")
            for d in cp.details:
                _w(f"- {d}")
            _w("")
        _w("</details>")
        _w("")

    # OTel one-liner
    _w(f"*OTel: {report.otel_summary.backend if report.otel_summary else 'not run'}*")
    _w("")
    return "\n".join(lines)
