"""OTel observer — checks backend reachability and queries trace data.

This is the software equivalent of the observer agent: it detects whether
Jaeger or Datadog is available, queries for trace summaries, and builds
a structured health summary for the canary report.
"""

from __future__ import annotations

import os
from typing import Any

import requests

from canary.models import OtelHealthSummary

# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

_DEFAULT_JAEGER_UI = "http://localhost:16686"
_DEFAULT_JAEGER_OTLP = "http://localhost:4318"


def _detect_backend() -> tuple[str, str]:
    """Return (backend_type, base_url).

    backend_type is one of: 'jaeger', 'datadog', 'none'.
    """
    dd_key = os.environ.get("DD_API_KEY")
    if dd_key:
        site = os.environ.get("DD_SITE", "datadoghq.com")
        return "datadog", f"https://api.{site}"

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", _DEFAULT_JAEGER_OTLP)
    # If a custom endpoint is set but isn't Jaeger-like, still treat as jaeger-style
    return "jaeger", endpoint


# ---------------------------------------------------------------------------
# Reachability checks
# ---------------------------------------------------------------------------


def _check_jaeger(timeout: float = 5.0) -> tuple[bool, str, str | None]:
    """Check Jaeger reachability. Returns (reachable, label, dashboard_url)."""
    ui_url = os.environ.get("JAEGER_UI_URL", _DEFAULT_JAEGER_UI)
    try:
        resp = requests.get(f"{ui_url}/api/services", timeout=timeout)
        if resp.ok:
            dashboard = f"{ui_url}/search?service=claude-code&limit=50"
            return True, f"Jaeger at {ui_url}", dashboard
    except requests.RequestException:
        pass
    return False, f"Jaeger at {ui_url} (unreachable)", None


def _check_datadog(base_url: str, timeout: float = 5.0) -> tuple[bool, str, str | None]:
    """Check Datadog reachability. Returns (reachable, label, dashboard_url)."""
    dd_key = os.environ.get("DD_API_KEY", "")
    try:
        resp = requests.get(
            f"{base_url}/api/v1/validate",
            headers={"DD-API-KEY": dd_key},
            timeout=timeout,
        )
        if resp.status_code == 200:
            site = os.environ.get("DD_SITE", "datadoghq.com")
            dashboard = f"https://app.{site}/apm/traces"
            return True, f"Datadog at {base_url}", dashboard
    except requests.RequestException:
        pass
    return False, f"Datadog at {base_url} (unreachable)", None


# ---------------------------------------------------------------------------
# Trace querying (Jaeger only — Datadog traces are best viewed in-app)
# ---------------------------------------------------------------------------


def _query_jaeger_traces(
    service: str = "claude-code", limit: int = 50, timeout: float = 10.0
) -> dict[str, Any]:
    """Query Jaeger for recent traces of a service."""
    ui_url = os.environ.get("JAEGER_UI_URL", _DEFAULT_JAEGER_UI)
    try:
        resp = requests.get(
            f"{ui_url}/api/traces",
            params={"service": service, "limit": str(limit)},
            timeout=timeout,
        )
        if resp.ok:
            return resp.json()
    except requests.RequestException:
        pass
    return {}


def _summarize_traces(trace_data: dict[str, Any]) -> tuple[int, int, int]:
    """Extract span counts from Jaeger trace response.

    Returns (total_spans, error_spans, timeout_spans).
    """
    total = 0
    errors = 0
    timeouts = 0
    for trace in trace_data.get("data", []):
        for span in trace.get("spans", []):
            total += 1
            tags = {t["key"]: t.get("value") for t in span.get("tags", [])}
            if tags.get("error") == True or tags.get("otel.status_code") == "ERROR":  # noqa: E712
                errors += 1
            duration_us = span.get("duration", 0)
            if duration_us > 5 * 60 * 1_000_000:  # 5 minutes
                timeouts += 1
    return total, errors, timeouts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def observe(skip_traces: bool = False) -> OtelHealthSummary:
    """Run the observer pipeline and return a health summary.

    1. Detect backend (Jaeger vs Datadog)
    2. Check reachability
    3. Query traces (Jaeger only, unless skipped)
    4. Build summary
    """
    telemetry_enabled = os.environ.get("CLAUDE_CODE_ENABLE_TELEMETRY") == "1"
    backend_type, base_url = _detect_backend()

    summary = OtelHealthSummary(telemetry_enabled=telemetry_enabled)

    if backend_type == "datadog":
        reachable, label, dashboard = _check_datadog(base_url)
    else:
        reachable, label, dashboard = _check_jaeger()

    summary.backend = label
    summary.reachable = reachable
    summary.dashboard_url = dashboard

    if reachable and backend_type == "jaeger" and not skip_traces:
        trace_data = _query_jaeger_traces()
        total, errors, timeouts = _summarize_traces(trace_data)
        summary.total_spans = total
        summary.error_spans = errors
        summary.timeout_spans = timeouts

    return summary
