# red-code

`red-code` is a local Python CLI coding agent built around:

- a controller-first natural-language entry flow
- a LangChain tool-calling loop
- a persisted task runtime
- an explicit `SKILL.md` skill system
- a controlled local execution boundary

The project is intended for local single-user development work. It is not a SaaS agent platform or a multi-user service.

The repository now contains two parallel runtime families:

- v1 `Task` / `Run` for the existing coding-agent workflow
- v2 `Operation` / `Job` foundations plus scope-aware admission and a scheduler/worker runtime for the red-team-oriented runtime

## Current Capabilities

- interactive local CLI
- Rich-based CLI presentation layer
- hierarchical help output with topic drill-down
- built-in and user-local `SKILL.md` skills
- explicit skill activation and one-shot skill invocation
- bounded skill-driven workflow planning for v2 security jobs
- file tools: read, write, edit, list, search, delete
- web tools: `web_fetch` and `web_search`
- shell command execution with safety checks
- capability-tier tool safety
- session state and context compression
- persisted tasks, runs, checkpoints, and task logs
- task-scoped safety audit logging
- blob-backed checkpoint storage with metadata-only SQLite indexing
- persisted operations, scope policies, jobs, evidence, findings, and memory entries
- persisted operation-level admission and execution events
- scope-aware target validation for the v2 red-team runtime
- a durable scheduler/worker runtime with job queueing, leases, heartbeats, retries, and cooperative cancellation
- pure-Python typed security tools for DNS, HTTP, TLS, banner grabbing, and TCP port scans
- session runtime exposure of typed security tools via LangChain-compatible adapters
- structured typed-tool results with evidence and finding candidates
- automatic persistence of typed-tool evidence artifacts and finding records
- evidence-to-finding traceability links for structured review and export
- JSON export generation for operation summaries, findings, and evidence indexes
- Phase 7 red-team CLI coverage for operations, jobs, findings, evidence, and dashboards
- isolated subprocess execution for typed security tools so timed-out or cancelled jobs can be terminated cleanly

## Run

```powershell
# Windows
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python src/main.py
```

```bash
# macOS / Linux
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python src/main.py
```

## Current CLI Commands

Describe what you want in plain language first. Examples:

- `Summarize this repository structure`
- `Start a recon session for example.com`
- `What did you already do?`

`Start a recon session for example.com` now starts (or reuses) a redteam session and immediately executes in the current interactive flow with progress visibility.

Use slash commands for skill and shell-level control. Legacy `/task` and `/operation` command families are no longer part of the default user-facing flow.

- `/help`
- `/help skill`
- `/clear`
- `/skill list`
- `/skill show <name>`
- `/skill use <name>`
- `/skill reload`
- `/skill clear`
- `/skill current`
- `/skill help`
- `/skill-name <prompt>`

`/help` now leads with natural-language examples and keeps command groups in advanced help topics.
Use `/help skill` for detailed command help.
`/clear` resets only the in-memory context and clears the screen while preserving active session binding and active shell skill.

## Red-Team Runtime Status

Phase 2 through Phase 7 currently deliver:

- `Operation`, `ScopePolicy`, `Job`, `Evidence`, `Finding`, and `MemoryEntry` domain models
- SQLite-backed repositories and services for the v2 red-team runtime
- atomic operation plus scope-policy creation
- minimal `/operation` and `/job` CLI inspection flows
- operation-level admission and execution event persistence
- scope-aware target, protocol, port, rate-limit, and confirmation checks
- confirmation-gated executions are re-admitted before execution to re-check rate and concurrency limits
- a v2-only scoped execution service that hard-blocks out-of-scope work before execution
- a job orchestration layer that queues dependency-ready jobs, recovers stale leases, blocks failed dependency chains, and applies cooperative cancellation
- a worker runtime with atomic job leasing, heartbeat refresh, retry backoff, timeout handling, and `drain()` support for sequential background-style execution
- a dedicated typed-security tool registry for operation/job execution, plus session-facing adapter tools in the runtime registry
- pure-Python typed security tools: `dns_lookup`, `http_probe`, `tls_inspect`, `banner_grab`, and `port_scan`
- `dns_lookup` validates both the resolver egress target and the queried logical name against scope
- `http_probe` captures only the first HTTP response and does not auto-follow redirects
- structured typed-tool outputs that expose normalized payloads plus evidence and finding candidates
- isolated subprocess execution for typed security tools so timed-out or cancelled jobs do not continue uncontrolled in the background
- automatic persistence of successful typed-job evidence into `.red-code/operations/<operation_public_id>/evidence/`
- automatic persistence of finding candidates plus finding-to-evidence traceability links
- JSON export generation under `.red-code/operations/<operation_public_id>/exports/<export_name>/`
- CLI inspection and lifecycle flows for `/operation`, `/job`, `/finding`, `/evidence`, and `/dashboard`
- persisted planner plans and proposal application flows for `/planner`
- `/operation resume` context summaries built from structured state rather than transcript replay
- planner write-back of newly derived stable facts into structured memory
- foreground execution closure for session-first requests via `ExecutionService` and `ForegroundRunner`
- structured execution progress events for in-session rendering (`execution_started`, step events, terminal events)
- redteam requests that execute in the current session by default (no manual secondary run stage)
- deterministic risk policy loading from `.red-code/config/risk-policy.json` with built-in defaults
- structured confirmation events (`confirmation_required`, `confirmation_approved`, `confirmation_denied`) and execution blocking on denied confirmations

The current runtime still intentionally does not yet deliver:

- CLI-triggered export flows
- planner-driven use of the structured evidence and finding store

Phase 6 now also delivers:

- per-skill runtime activation of `model`, `effort`, `shell`, `user-invocable`, and `disable-model-invocation`
- explicit shell selection for the `bash` tool when a skill declares `shell`; otherwise the runtime uses the host default shell
- workflow-only skills that generate bounded v2 job plans instead of freeform prompt execution
- built-in `surface-recon` and `web-enum` workflow skills

## Evidence and Export Layout

Successful v2 typed security jobs now write structured evidence artifacts and metadata under:

```text
.red-code/
  operations/
    <operation_public_id>/
      evidence/
        <job_public_id>-<ordinal>-<evidence_type>.json
      exports/
        <export_name>/
          operation-summary.json
          findings.json
          evidence-index.json
```

Each evidence artifact is stored as a JSON envelope with metadata plus the normalized tool payload. The persisted `Evidence` row keeps the relative artifact path, a SHA-256 digest, and `application/json` as the stored artifact content type.

Programmatic export is available through `reporting.evidence_export.EvidenceExportService.generate_operation_export(...)`. Phase 5 intentionally stops short of adding new CLI commands for export or finding review.

## Skill Locations

Built-in skills live under:

- `src/skills/`

User-local skills live under:

- `.red-code/skills/`

Example:

```text
.red-code/
  skills/
    my-skill/
      SKILL.md
```

If a local skill has the same name as a built-in skill, the local skill overrides it after `/skill reload`.

## Current Architecture

Core source areas:

- `src/main.py`
- `src/agent/`
- `src/app/`
- `src/runtime/`
- `src/models/`
- `src/skills/`
- `src/storage/`
- `src/tools/`
- `src/utils/`

## Documentation

Current docs:

- `docs/architecture/architecture.md`
- `docs/architecture/task-runtime.md`
- `docs/architecture/prompt-runtime-contract.md`
- `docs/architecture/skill-system-standard.md`
- `docs/architecture/checkpoint-storage-evolution.md`
- `docs/development/engineering-development-plan.en.md`
- `docs/development/red-team-agent-srs.md`
- `docs/development/red-team-agent-roadmap.md`

The docs index is at `docs/README.md`.

## Built-In Skills

The current built-in skills are:

- `development-default`
- `git-auto-commit`
- `security-audit`
- `surface-recon`
- `weather-query-example`
- `web-enum`

## Tests

```powershell
# Windows
.venv\Scripts\python -m pytest
```

```bash
# macOS / Linux
.venv/bin/python -m pytest
```
