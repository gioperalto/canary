# Canary

Canary is a composable QA validator for [harnest](https://github.com/gioperalto/harnest) chicks. It runs a 6-checkpoint validation suite against any chick directory — checking file structure, YAML schema, agent frontmatter, documentation sections, naming conventions, and cross-references — then generates a pass/fail report. An optional OTel observer checks Jaeger or Datadog for telemetry health alongside the structural validation.

Canary was built as a harnest chick itself (validator + observer agent team), then extracted into a standalone Python CLI and reusable GitHub Action so it can run automatically on pull requests to any repository that hosts harnest chicks.

## How it works

Canary runs 6 checkpoints against each target chick:

| # | Checkpoint | What it checks |
|---|-----------|----------------|
| 1 | **File Presence** | `harnest.yaml`, `CLAUDE.md`, `README.md`, `.claude/settings.json`, agent files |
| 2 | **YAML Schema** | `team`, `agents`, `workflow` sections; required fields; agent file references |
| 3 | **Agent Frontmatter** | YAML frontmatter in each `.claude/agents/*.md` — required fields, valid values |
| 4 | **CLAUDE.md Sections** | Title, Configuration, Team Structure, Workflow, Important Notes — present and ordered |
| 5 | **Naming Conventions** | `snake_case` keys, `kebab-case` file names, `branch_prefix` ends with `/` |
| 6 | **Cross-References** | Agent files exist, MCP server configs present in `settings.json` |

If OTel is enabled, canary also checks backend reachability (Jaeger or Datadog), queries trace data, and includes a health summary in the report.

## Installation

### From source

```bash
git clone https://github.com/gioperalto/canary.git
cd canary
pip install -e .
```

### With OTel support

```bash
pip install -e ".[otel]"
```

## CLI Usage

```bash
# Validate all chicks in nest/
canary

# Validate specific targets
canary --targets webpage brainstorm

# Only validate chicks changed in a PR (CI mode)
canary --changed-only --base-ref origin/main

# Skip OTel observer
canary --no-otel

# Fail with exit code 1 if any checkpoint fails
canary --exit-code

# Output compact PR comment to stdout
canary --pr-comment

# Custom report path
canary --report-path ./my-report.md

# Point at a different nest directory
canary --nest-root /path/to/chicks
```

The full report is written to `.harnest/canary-report.md` by default.

## Integrate with your GitHub project

### Option 1: Reusable GitHub Action (recommended)

Add canary to any repository in one step. Create `.github/workflows/canary.yml`:

```yaml
name: Canary
on:
  pull_request:
    paths: ["nest/**"]

permissions:
  contents: read
  pull-requests: write

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: gioperalto/canary@main
```

That's it. On every PR that touches a chick directory, canary will:

1. Auto-detect which chicks changed
2. Run all 6 checkpoints
3. Post a pass/fail report as a PR comment
4. Fail the check if any checkpoint fails

#### Action inputs

| Input | Default | Description |
|-------|---------|-------------|
| `targets` | *(auto-detect)* | Comma-separated chick names to validate |
| `nest-root` | `nest` | Path to directory containing chick subdirectories |
| `base-ref` | *(from PR)* | Git ref to diff against for change detection |
| `enable-otel` | `false` | Enable OTel observer (needs Jaeger sidecar or `DD_API_KEY`) |
| `post-comment` | `true` | Post canary report as a PR comment |
| `fail-on-error` | `true` | Fail the workflow if any checkpoint fails |

#### Action outputs

| Output | Description |
|--------|-------------|
| `result` | `PASS` or `FAIL` |
| `report-path` | Path to the generated report file |

#### With OTel / Datadog

To enable telemetry observation, add your Datadog API key as a repository secret:

```yaml
      - uses: gioperalto/canary@main
        env:
          DD_API_KEY: ${{ secrets.DD_API_KEY }}
          DD_SITE: ${{ secrets.DD_SITE }}
        with:
          enable-otel: true
```

Or use a Jaeger sidecar:

```yaml
jobs:
  validate:
    runs-on: ubuntu-latest
    services:
      jaeger:
        image: jaegertracing/all-in-one:latest
        ports:
          - 16686:16686
          - 4318:4318
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: gioperalto/canary@main
        env:
          CLAUDE_CODE_ENABLE_TELEMETRY: "1"
        with:
          enable-otel: true
```

### Option 2: Copy the workflow

If you prefer not to use the reusable action, copy `.github/workflows/canary.yml` from this repo into your project and adjust paths as needed. The workflow installs canary from source and runs the CLI directly.

### Option 3: Run locally

```bash
# Install
pip install git+https://github.com/gioperalto/canary.git

# Validate chicks in the current repo
canary --nest-root ./nest --no-otel --exit-code
```

## OTel observability

Canary's observer module checks for a telemetry backend and includes health data in the report.

### Jaeger (local development)

```bash
# Start Jaeger
docker run -d --name jaeger \
  -p 16686:16686 -p 4317:4317 -p 4318:4318 \
  jaegertracing/all-in-one:latest

# Run canary with telemetry
CLAUDE_CODE_ENABLE_TELEMETRY=1 canary
```

### Datadog (production)

```bash
export DD_API_KEY=your-key-here
export DD_SITE=datadoghq.com
canary
```

The observer auto-detects which backend to use based on environment variables. If neither is reachable, the report notes it and validation proceeds normally.

## Project structure

```
canary/
├── src/canary/
│   ├── cli.py           # CLI entry point
│   ├── config.py        # harnest.yaml parsing, target resolution
│   ├── checkpoints.py   # 6-checkpoint validation suite
│   ├── observer.py      # OTel backend detection + trace querying
│   ├── report.py        # Markdown report + PR comment rendering
│   └── models.py        # CheckpointResult, ChickReport, CanaryReport
├── .claude/agents/
│   ├── validator.md     # Validator agent definition (for team mode)
│   └── observer.md      # Observer agent definition (for team mode)
├── .github/workflows/
│   └── canary.yml       # Self-contained workflow (for this repo)
├── action.yml           # Reusable GitHub Action definition
├── harnest.yaml         # Canary's own harnest config
├── pyproject.toml       # Python package config
└── CLAUDE.md            # Agent team bootstrap instructions
```

Canary can run in two modes:
- **CLI mode** — `canary` command, used in CI and local development
- **Team mode** — spawned as a Claude Code agent team (validator + observer), used for interactive dogfooding sessions

## Adding a new checkpoint

Checkpoints live in `src/canary/checkpoints.py`. Each checkpoint is a function with the signature:

```python
def _cpN_name(chick_root: Path) -> tuple[Status, list[str]]:
    """Return (PASS/FAIL, list of error details)."""
```

Wrap it with `_timed(N, "Name", fn)` and append to `ALL_CHECKPOINTS`.

## License

[MIT](LICENSE)
