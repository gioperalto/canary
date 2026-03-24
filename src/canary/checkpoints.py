"""Six-checkpoint validation suite for harnest chicks.

Each checkpoint function takes a chick root Path and returns a CheckpointResult.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Callable

import yaml

from canary.models import CheckpointResult, Status

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SNAKE_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
KEBAB_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*\.md$")

RECOGNIZED_FRONTMATTER_FIELDS = {
    "name",
    "description",
    "model",
    "tools",
    "permissionMode",
    "maxTurns",
    "mcpServers",
}

VALID_PERMISSION_MODES = {"default", "acceptEdits", "bypassPermissions", "dontAsk", "auto", "plan"}


def _timed(
    number: int, name: str, fn: Callable[[Path], tuple[Status, list[str]]]
) -> Callable[[Path], CheckpointResult]:
    """Wrap a checkpoint function to capture timing."""

    def wrapper(chick_root: Path) -> CheckpointResult:
        t0 = time.monotonic()
        status, details = fn(chick_root)
        elapsed = (time.monotonic() - t0) * 1000
        return CheckpointResult(
            number=number, name=name, status=status, details=details, duration_ms=elapsed
        )

    return wrapper


def _load_yaml(path: Path) -> dict[str, Any] | None:
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return None


def _parse_frontmatter(path: Path) -> dict[str, Any] | None:
    """Extract YAML frontmatter from a markdown file."""
    try:
        text = path.read_text()
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("---", 3)
    if end == -1:
        return None
    try:
        return yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError:
        return None


# ---------------------------------------------------------------------------
# Checkpoint 1: File Presence
# ---------------------------------------------------------------------------

REQUIRED_FILES = [
    "harnest.yaml",
    "CLAUDE.md",
    "README.md",
]

REQUIRED_DIRS = [
    ".claude/settings.json",
    ".claude/agents",
]


def _cp1_file_presence(chick_root: Path) -> tuple[Status, list[str]]:
    errors: list[str] = []

    if not chick_root.is_dir():
        return Status.FAIL, [f"Directory does not exist: {chick_root}"]

    for f in REQUIRED_FILES:
        if not (chick_root / f).is_file():
            errors.append(f"Missing file: {f}")

    settings = chick_root / ".claude" / "settings.json"
    if not settings.is_file():
        errors.append("Missing file: .claude/settings.json")

    agents_dir = chick_root / ".claude" / "agents"
    if not agents_dir.is_dir():
        errors.append("Missing directory: .claude/agents/")
    else:
        agent_files = list(agents_dir.glob("*.md"))
        if not agent_files:
            errors.append("No agent .md files in .claude/agents/")

    return (Status.FAIL if errors else Status.PASS), errors


# ---------------------------------------------------------------------------
# Checkpoint 2: YAML Schema
# ---------------------------------------------------------------------------


def _cp2_yaml_schema(chick_root: Path) -> tuple[Status, list[str]]:
    errors: list[str] = []
    cfg = _load_yaml(chick_root / "harnest.yaml")

    if cfg is None:
        return Status.FAIL, ["Cannot parse harnest.yaml"]

    # team section
    team = cfg.get("team", {})
    if not isinstance(team, dict):
        errors.append("team: must be a mapping")
    else:
        for key in ("name", "description"):
            if key not in team:
                errors.append(f"team.{key}: missing")

    # agents section
    agents = cfg.get("agents", {})
    if not isinstance(agents, dict) or len(agents) == 0:
        errors.append("agents: must contain at least one agent")
    else:
        for name, agent in agents.items():
            if not isinstance(agent, dict):
                errors.append(f"agents.{name}: must be a mapping")
                continue
            for key in ("model", "count", "agent_file", "description"):
                if key not in agent:
                    errors.append(f"agents.{name}.{key}: missing")

            # Verify agent_file exists
            af = agent.get("agent_file")
            if af:
                agent_path = chick_root / ".claude" / "agents" / af
                if not agent_path.is_file():
                    errors.append(
                        f"agents.{name}.agent_file: '{af}' not found in .claude/agents/"
                    )

    # workflow section
    workflow = cfg.get("workflow", {})
    if not isinstance(workflow, dict):
        errors.append("workflow: must be a mapping")
    else:
        for key in ("use_worktrees", "branch_prefix"):
            if key not in workflow:
                errors.append(f"workflow.{key}: missing")

    return (Status.FAIL if errors else Status.PASS), errors


# ---------------------------------------------------------------------------
# Checkpoint 3: Agent Frontmatter
# ---------------------------------------------------------------------------

REQUIRED_FRONTMATTER = {"name", "description", "model", "tools"}


def _cp3_agent_frontmatter(chick_root: Path) -> tuple[Status, list[str]]:
    errors: list[str] = []
    agents_dir = chick_root / ".claude" / "agents"

    if not agents_dir.is_dir():
        return Status.FAIL, ["agents directory missing — skipped"]

    for md_file in sorted(agents_dir.glob("*.md")):
        fm = _parse_frontmatter(md_file)
        if fm is None:
            errors.append(f"{md_file.name}: missing or invalid YAML frontmatter")
            continue

        for key in REQUIRED_FRONTMATTER:
            if key not in fm:
                errors.append(f"{md_file.name}: missing field '{key}'")

        pm = fm.get("permissionMode")
        if pm is not None and pm not in VALID_PERMISSION_MODES:
            errors.append(f"{md_file.name}: unrecognized permissionMode '{pm}'")

        mt = fm.get("maxTurns")
        if mt is not None and (not isinstance(mt, int) or mt <= 0):
            errors.append(f"{md_file.name}: maxTurns must be a positive integer, got '{mt}'")

        extra = set(fm.keys()) - RECOGNIZED_FRONTMATTER_FIELDS
        if extra:
            errors.append(f"{md_file.name}: unrecognized fields: {sorted(extra)}")

    return (Status.FAIL if errors else Status.PASS), errors


# ---------------------------------------------------------------------------
# Checkpoint 4: CLAUDE.md Section Order
# ---------------------------------------------------------------------------

EXPECTED_SECTIONS = [
    r"^#\s+Harnest\s*—",
    r"^##\s+Configuration",
    r"^##\s+Team Structure",
    r"^##\s+Workflow",
    r"^##\s+Important Notes",
]


def _cp4_claude_md_sections(chick_root: Path) -> tuple[Status, list[str]]:
    errors: list[str] = []
    claude_md = chick_root / "CLAUDE.md"

    try:
        text = claude_md.read_text()
    except OSError:
        return Status.FAIL, ["CLAUDE.md not found or unreadable"]

    lines = text.splitlines()

    last_pos = -1
    for pattern in EXPECTED_SECTIONS:
        found_pos = None
        for i, line in enumerate(lines):
            if re.match(pattern, line):
                found_pos = i
                break
        if found_pos is None:
            errors.append(f"Missing section matching: {pattern}")
        elif found_pos <= last_pos:
            errors.append(f"Section '{pattern}' appears out of order (line {found_pos + 1})")
        else:
            last_pos = found_pos

    return (Status.FAIL if errors else Status.PASS), errors


# ---------------------------------------------------------------------------
# Checkpoint 5: Naming Conventions
# ---------------------------------------------------------------------------


def _cp5_naming_conventions(chick_root: Path) -> tuple[Status, list[str]]:
    errors: list[str] = []

    # Agent role keys in harnest.yaml must be snake_case
    cfg = _load_yaml(chick_root / "harnest.yaml")
    if cfg:
        for key in cfg.get("agents", {}).keys():
            if not SNAKE_RE.match(key):
                errors.append(f"Agent key '{key}' is not snake_case")

    # Agent file names must be kebab-case
    agents_dir = chick_root / ".claude" / "agents"
    if agents_dir.is_dir():
        for md_file in agents_dir.glob("*.md"):
            if not KEBAB_RE.match(md_file.name):
                errors.append(f"Agent file '{md_file.name}' is not kebab-case")

    # branch_prefix must end with /
    if cfg:
        bp = cfg.get("workflow", {}).get("branch_prefix", "")
        if bp and not bp.endswith("/"):
            errors.append(f"branch_prefix '{bp}' does not end with '/'")

    return (Status.FAIL if errors else Status.PASS), errors


# ---------------------------------------------------------------------------
# Checkpoint 6: Cross-References
# ---------------------------------------------------------------------------


def _cp6_cross_references(chick_root: Path) -> tuple[Status, list[str]]:
    errors: list[str] = []
    cfg = _load_yaml(chick_root / "harnest.yaml")

    if not cfg:
        return Status.FAIL, ["Cannot parse harnest.yaml for cross-reference check"]

    agents_dir = chick_root / ".claude" / "agents"

    # Every agent_file in harnest.yaml must exist
    for name, agent in cfg.get("agents", {}).items():
        af = agent.get("agent_file") if isinstance(agent, dict) else None
        if af and not (agents_dir / af).is_file():
            errors.append(f"agents.{name}.agent_file '{af}' does not exist")

    # MCP servers referenced in agent frontmatter must exist in settings.json
    settings_path = chick_root / ".claude" / "settings.json"
    settings: dict[str, Any] = {}
    if settings_path.is_file():
        try:
            import json

            settings = json.loads(settings_path.read_text())
        except (OSError, json.JSONDecodeError):
            pass

    configured_mcp = set(settings.get("mcpServers", {}).keys())

    if agents_dir.is_dir():
        for md_file in sorted(agents_dir.glob("*.md")):
            fm = _parse_frontmatter(md_file)
            if not fm:
                continue
            mcp_refs = fm.get("mcpServers")
            if isinstance(mcp_refs, list):
                for ref in mcp_refs:
                    if ref not in configured_mcp:
                        errors.append(
                            f"{md_file.name}: mcpServers '{ref}' not in .claude/settings.json"
                        )

    return (Status.FAIL if errors else Status.PASS), errors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

ALL_CHECKPOINTS: list[Callable[[Path], CheckpointResult]] = [
    _timed(1, "Setup — File Presence", _cp1_file_presence),
    _timed(2, "Structure — YAML Schema", _cp2_yaml_schema),
    _timed(3, "Structure — Agent Frontmatter", _cp3_agent_frontmatter),
    _timed(4, "Structure — CLAUDE.md Section Order", _cp4_claude_md_sections),
    _timed(5, "Convention — Naming Conventions", _cp5_naming_conventions),
    _timed(6, "Completeness — Cross-References", _cp6_cross_references),
]


def validate_chick(chick_root: Path) -> list[CheckpointResult]:
    """Run all 6 checkpoints against a chick and return results."""
    if not chick_root.is_dir():
        return [
            CheckpointResult(
                number=i,
                name=name,
                status=Status.FAIL,
                details=[f"Chick directory does not exist: {chick_root}"],
            )
            for i, name in enumerate(
                [
                    "Setup — File Presence",
                    "Structure — YAML Schema",
                    "Structure — Agent Frontmatter",
                    "Structure — CLAUDE.md Section Order",
                    "Convention — Naming Conventions",
                    "Completeness — Cross-References",
                ],
                start=1,
            )
        ]
    return [cp(chick_root) for cp in ALL_CHECKPOINTS]
