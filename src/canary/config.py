"""Parse harnest.yaml configuration files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> dict[str, Any]:
    """Load and return a YAML file, or empty dict on failure."""
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return {}


def resolve_targets(
    config: dict[str, Any],
    nest_root: Path,
    explicit_targets: list[str] | None = None,
) -> list[tuple[str, Path]]:
    """Return (name, path) pairs for each target chick to validate.

    Priority:
    1. Explicit CLI targets (--targets)
    2. targets list in harnest.yaml
    3. Auto-detect: every subdirectory of nest_root containing harnest.yaml
    """
    if explicit_targets:
        return [(t, nest_root / t) for t in explicit_targets]

    configured = config.get("targets", [])
    if configured:
        return [(t, nest_root / t) for t in configured]

    # Auto-detect chick directories
    if nest_root.is_dir():
        return [
            (d.name, d)
            for d in sorted(nest_root.iterdir())
            if d.is_dir() and (d / "harnest.yaml").exists()
        ]

    return []


def discover_changed_chicks(
    nest_root: Path, base_ref: str = "origin/main"
) -> list[str]:
    """Detect chick directories with changes relative to base_ref.

    Used by CI to scope validation to only the chicks touched in a PR.
    Returns chick directory names (not full paths).
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", base_ref, "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=nest_root.parent if nest_root.exists() else Path.cwd(),
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    nest_prefix = nest_root.name + "/"
    chick_names: set[str] = set()
    for line in result.stdout.strip().splitlines():
        if line.startswith(nest_prefix):
            parts = line[len(nest_prefix) :].split("/")
            if parts:
                chick_names.add(parts[0])

    return sorted(chick_names)
