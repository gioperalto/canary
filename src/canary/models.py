"""Data models for canary validation results."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class Status(Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass
class CheckpointResult:
    """Result of a single validation checkpoint."""

    number: int
    name: str
    status: Status
    details: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def passed(self) -> bool:
        return self.status is Status.PASS


@dataclass
class ChickReport:
    """Aggregated results for one target chick."""

    name: str
    path: Path
    checkpoints: list[CheckpointResult] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checkpoints if c.passed)

    @property
    def failed_count(self) -> int:
        return len(self.checkpoints) - self.passed_count

    @property
    def overall(self) -> Status:
        return Status.PASS if self.failed_count == 0 else Status.FAIL


@dataclass
class OtelHealthSummary:
    """Health summary from the OTel observer."""

    backend: str = "Unreachable"
    telemetry_enabled: bool = False
    reachable: bool = False
    agents: list[dict] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)
    total_spans: int = 0
    error_spans: int = 0
    timeout_spans: int = 0
    dashboard_url: Optional[str] = None


@dataclass
class CanaryReport:
    """Top-level canary report combining all results."""

    run_date: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    targets: list[str] = field(default_factory=list)
    chick_reports: list[ChickReport] = field(default_factory=list)
    otel_summary: Optional[OtelHealthSummary] = None

    @property
    def overall(self) -> Status:
        if not self.chick_reports:
            return Status.FAIL
        return (
            Status.PASS
            if all(r.overall is Status.PASS for r in self.chick_reports)
            else Status.FAIL
        )
