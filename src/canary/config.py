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

    # Auto-detect chick directories (supports one level of grouping, e.g. nest/internal/chick)
    if nest_root.is_dir():
        results = []
        for d in sorted(nest_root.iterdir()):
            if not d.is_dir():
                continue
            if (d / "harnest.yaml").exists():
                results.append((d.name, d))
            else:
                # Check one level deeper (group directory)
                for sub in sorted(d.iterdir()):
                    if sub.is_dir() and (sub / "harnest.yaml").exists():
                        results.append((f"{d.name}/{sub.name}", sub))
        return results

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
            # Walk path components to find the chick directory (first one with harnest.yaml)
            for depth in range(1, len(parts)):
                candidate = nest_root.joinpath(*parts[:depth])
                if (candidate / "harnest.yaml").exists():
                    chick_names.add("/".join(parts[:depth]))
                    break

    return sorted(chick_names)
