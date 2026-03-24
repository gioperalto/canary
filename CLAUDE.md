<!-- harnest:begin -->
# Harnest — Canary QA / Dogfooding Chick (canary)

This chick tests other harnest chicks end-to-end — validating their structure, schema, naming conventions, and workflow completeness, while monitoring operational health via OpenTelemetry. A validator runs structural checkpoints against each target chick. An observer monitors OTel telemetry in parallel, detecting anomalies that checkpoint-based tests would miss. Together they produce a structured pass/fail report with a link to the OTel trace dashboard.

## Configuration

All team settings live in `harnest.yaml` at the project root. Read it at the start of every session — it is the source of truth for agent roles, models, workflow rules, and target chick configuration.

## Team Structure

| Role      | Model  | Count | Purpose                                                                        |
|-----------|--------|-------|--------------------------------------------------------------------------------|
| Validator | sonnet | 1     | Orchestrates validation: structure, schema, naming, cross-references, workflow |
| Observer  | haiku  | 1     | Monitors OTel telemetry, detects anomalies, produces health summary            |

## Workflow: How to Bootstrap a Team

### Step 1 — Read Configuration
```
Read harnest.yaml
```
Parse team settings, agent definitions, and the list of target chicks to validate.

### Step 2 — Create Team
```
TeamCreate(team_name: "canary", description: "Canary QA team")
```

### Step 3 — Spawn Observer First

Spawn the observer before validation begins. The observer:
1. Configures the OTel export environment (`CLAUDE_CODE_ENABLE_TELEMETRY=1`, OTLP endpoint)
2. Verifies the OTel backend is reachable (Jaeger on localhost:16686, or Datadog if `DD_API_KEY` is set)
3. Waits for the validator's "test starting" signal before monitoring begins

**The observer must be running before the validator starts test execution.**

### Step 4 — Spawn Validator

After the observer is ready, spawn the validator. The validator:
1. Signals the observer that testing is about to begin
2. Runs the 6-checkpoint validation checklist for each target chick:
   - **Checkpoint 1**: Setup — file presence (harnest.yaml, CLAUDE.md, README.md, settings.json, agent files)
   - **Checkpoint 2**: Structure — YAML schema (team, agents, workflow sections; required fields)
   - **Checkpoint 3**: Structure — agent frontmatter (name, description, model, tools, permissionMode, maxTurns)
   - **Checkpoint 4**: Structure — CLAUDE.md section order (title, Configuration, Team Structure, Workflow, Important Notes)
   - **Checkpoint 5**: Convention — naming (snake_case keys, kebab-case file names, branch_prefix format)
   - **Checkpoint 6**: Completeness — cross-references (agent files exist, MCP server configs present)
3. Signals the observer when all checkpoints are complete
4. Collects the observer's health summary
5. Writes `.harnest/canary-report.md`

### Step 5 — Observer Produces Health Summary

After receiving the validator's "testing complete" signal, the observer:
1. Queries the OTel backend for trace summaries
2. Produces a structured health summary (agent lifecycle table, anomaly list, span counts)
3. Sends the health summary to the validator via `SendMessage`

### Step 6 — Validator Writes Report

The validator merges all results into `.harnest/canary-report.md`:
- Per-chick checkpoint table (PASS/FAIL for each of the 6 checkpoints)
- Observer health summary
- Dashboard URL for trace drill-down
- Diagnostics and remediation notes for any failures

### Step 7 — Cleanup

When the validator writes the report:
1. Send `shutdown_request` to all teammates
2. Wait for confirmations
3. Call `TeamDelete` to clean up

The report is available at `.harnest/canary-report.md`.

## Branch Naming Convention

If git branching is used during canary runs:
```
canary/<chick-name>-<timestamp>
```

## Important Notes

- **OTel telemetry**: Set `CLAUDE_CODE_ENABLE_TELEMETRY=1` before running. Without it, the observer cannot collect telemetry but functional validation still runs.
- **Jaeger (local default)**: Start with Docker before running canary:
  ```bash
  docker run -d --name jaeger -p 16686:16686 -p 4317:4317 -p 4318:4318 jaegertracing/all-in-one:latest
  ```
- **Datadog backend**: Pass `DD_API_KEY` and optionally `DD_SITE` as shell env vars — never store in settings files:
  ```bash
  export DD_API_KEY=your-key-here
  export DD_SITE=datadoghq.com
  ```
- **Teams feature**: Requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` (set in `.claude/settings.json`).
- **No worktrees**: Both agents share the project directory. The validator reads from `nest/` and writes to `.harnest/`. The observer reads telemetry and writes its health summary via messaging.
- **Session persistence**: Teams exist only within a single Claude Code session. They are not persisted across sessions.
- **Adding test targets**: To add a new chick to the test suite, add it to the target list in `harnest.yaml` (or instruct the validator directly at session start).

<!-- harnest:end -->
