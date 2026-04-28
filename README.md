# red-code

`red-code` is a local Python CLI coding agent built around:

- a controller-first natural-language entry flow
- a LangChain tool-calling loop
- persisted session runtime state
- an explicit `SKILL.md` skill system
- a controlled local execution boundary
- a session-first red-team runtime

The project is intended for local single-user development work. It is not a SaaS agent platform or a multi-user service.

The repository now centers on a session-first runtime:

- `Session` / `Run` for the interactive coding-agent workflow
- `Session` / `Job` foundations plus scope-aware admission and a scheduler/worker runtime for the red-team-oriented runtime

## Current Capabilities

- interactive local CLI
- Rich-based CLI presentation layer
- hierarchical help output with topic drill-down
- built-in and user-local `SKILL.md` prompt-assist skills
- Phase 5 `capability.json` contracts for skills and modules
- explicit skill activation and one-shot skill invocation
- bounded module execution for `surface-recon` and `web-enum` through the session risk/scope gate
- file tools: read, write, edit, list, search, delete
- web tools: `web_fetch` and `web_search`
- shell command execution with safety checks
- capability-tier tool safety
- session state and context compression
- persisted sessions, runs, checkpoints, and session logs
- session-scoped safety audit logging
- blob-backed checkpoint storage with metadata-only SQLite indexing
- persisted redteam sessions, scope policies, session-owned jobs, artifacts, findings, reports, and memory entries
- persisted session-level admission and execution events
- scope-aware target validation for the v2 red-team runtime
- a durable scheduler/worker runtime with job queueing, leases, heartbeats, retries, and cooperative cancellation
- pure-Python typed security tools for DNS, HTTP, TLS, banner grabbing, and TCP port scans
- session runtime exposure of typed security tools via LangChain-compatible adapters
- structured typed-tool results with artifact and finding candidates
- automatic persistence of typed-tool artifact payloads, finding records, and indexed reports
- artifact-to-finding traceability links for structured review and report generation
- JSON report generation for session summaries, findings, and artifact indexes
- Phase 6 red-team CLI coverage for sessions, jobs, findings, artifacts, reports, and dashboards
- Phase 7 command-first query entry contracts for session-scoped history, step, artifact, finding, report, and explanation requests
- Phase 7 session-owned record retrieval views with traceable finding explanations
- Phase 7 report-flow orchestration with report reuse and Markdown operator reports
- Phase 8 shared `ConversationContext` and `SessionInteractionService` extraction above the controller and execution services
- Phase 8 Web-ready DTO, serialization, conversation store, and transport-neutral interaction adapter contracts
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
- `/redteam on`
- `Scan example.com for open services`
- `What did you already do?`

Plain-language requests now default to the normal agent flow. Use `/redteam on` to switch subsequent plain-language requests into redteam mode, and `/redteam off` to return to normal mode.
`/report session_summary`, `/report findings_summary`, and `/report operator_report` now reuse the most recent session report when possible and generate a new report only when needed.

Use slash commands for skill, module, and shell-level control. Legacy `/operation` command families are no longer part of the default user-facing flow.

- `/help`
- `/help query`
- `/help skill`
- `/redteam [on|off|toggle|current]`
- `/help module`
- `/module list`
- `/module show <name>`
- `/module run <name> <target> [json_overrides]`
- `/redteam [on|off|toggle|current]`
- `/clear`
- `/status [current|latest|S0001]`
- `/history [current|latest|S0001]`
- `/steps [current|latest|S0001]`
- `/artifacts [current|latest|S0001]`
- `/findings [current|latest|S0001]`
- `/reports [current|latest|S0001]`
- `/show <public_id> [current|latest|S0001]`
- `/why <finding_public_id> [current|latest|S0001]`
- `/report <session_summary|findings_summary|operator_report> [current|latest|S0001]`
- `/skill list`
- `/skill show <name>`
- `/skill use <name>`
- `/skill reload`
- `/skill clear`
- `/skill current`
- `/skill help`
- `/skill-name <prompt>`

`/help` now leads with natural-language examples and keeps command groups in advanced help topics.
Use `/help query` for session-aware retrieval/report commands, `/help skill` for skill command help, and `/help module` for module workflows.
`/clear` resets only the in-memory context and clears the screen while preserving active session binding and active shell skill.

## Red-Team Runtime Status

Phase 2 through Phase 7 currently deliver:

- `Session`, `ScopePolicy`, `Job`, `Artifact`, `Finding`, `Report`, and `MemoryEntry` domain models
- SQLite-backed repositories and services for the v2 red-team runtime
- atomic redteam session plus scope-policy creation
- session-level admission and execution event persistence
- scope-aware target, protocol, port, rate-limit, and confirmation checks
- confirmation-gated executions are re-admitted before execution to re-check rate and concurrency limits
- a v2-only scoped execution service that hard-blocks out-of-scope work before execution
- a job orchestration layer that queues dependency-ready jobs, recovers stale leases, blocks failed dependency chains, and applies cooperative cancellation
- a worker runtime with atomic job leasing, heartbeat refresh, retry backoff, timeout handling, and `drain()` support for sequential background-style execution
- a dedicated typed-security tool registry for session/job execution, plus session-facing adapter tools in the runtime registry
- pure-Python typed security tools: `dns_lookup`, `http_probe`, `tls_inspect`, `banner_grab`, and `port_scan`
- session-facing typed security tools accept native port arrays, single-port values, comma-separated strings, and JSON-style list strings such as `"[80,443]"`; recoverable validation errors are rendered as failed steps instead of successful completions
- `dns_lookup` validates both the resolver egress target and the queried logical name against scope
- `http_probe` captures only the first HTTP response and does not auto-follow redirects
- structured typed-tool outputs that expose normalized payloads plus artifact and finding candidates
- isolated subprocess execution for typed security tools so timed-out or cancelled jobs do not continue uncontrolled in the background
- automatic persistence of successful typed-job artifacts into `.red-code/sessions/<session_id>/artifacts/`
- automatic persistence of finding candidates plus finding-to-artifact traceability links
- indexed report generation under `.red-code/sessions/<session_id>/reports/`
- atomic report creation that rolls back metadata and output files on failure
- structured report-creation errors with user-facing messages plus AI-ready prompt/context fields
- CLI inspection and lifecycle flows for `/finding`, `/artifact`, `/report`, and `/dashboard`
- persisted planner plans and proposal application flows for `/planner`
- planner write-back of newly derived stable facts into structured memory
- foreground execution closure for session-first requests via `ExecutionService` and `ForegroundRunner`
- structured execution progress events for in-session rendering (`execution_started`, step events, terminal events)
- explicit `/redteam` mode switching for foreground redteam execution in the current session (no manual secondary run stage)
- deterministic risk policy loading from `.red-code/config/risk-policy.json` with built-in defaults
- structured confirmation events (`confirmation_required`, `confirmation_approved`, `confirmation_denied`) and execution blocking on denied confirmations
- adapter-neutral conversation binding through `ConversationContext` instead of CLI-only shell state
- shared interaction orchestration through `SessionInteractionService`, with CLI and Web-style adapters on the same controller path
- explicit Web serialization contracts under `src/web/` for conversation snapshots, interactive stream events, session resources, reports, and dashboards

The current runtime still intentionally does not yet deliver:

- natural-language retrieval over persisted artifacts/findings/reports
- planner-driven use of the structured artifact and finding store

Phase 5 now also delivers:

- a unified `capability.json` contract for prompt-assist skills and executable modules
- manifest discovery from `src/capabilities/` with local `.red-code/capabilities/` overrides
- `CapabilityService` and `ModuleService` validation for kind, mode, parameters, risk hints, and session support
- explicit `/module` advanced/debug commands for listing, inspecting, and running modules
- built-in `surface-recon` and `web-enum` modules that execute typed-tool workflows without requiring `operation_id`

## Session Storage Layout

Successful v2 typed security jobs now write structured session-owned runtime records under:

```text
.red-code/
  sessions/
    <session_id>/
      memory/
        checkpoints/
          YYYY/
            MM/
              chk_<checkpoint_id>.json.gz
      artifacts/
        ...
      findings/
      reports/
        ...
```

Each artifact payload is stored on disk under the owning session, while SQLite keeps only structured metadata and link tables. Report generation now persists indexed `Report` rows plus report-to-artifact and report-to-finding links. `ReportService.create_report(...)` validates linked records before commit and rolls back both database writes and output files if creation fails. The failure path exposes a user-facing error message together with AI-ready prompt/context fields for future assistant-driven remediation. Session-first export/report generation now lives under `SessionReportExportService`, which writes `session_summary`, `findings`, and `artifact_index` outputs under the owning session.

Internal persisted session storage now uses the raw `session.id` directory name. Public IDs remain for user-facing commands and displays only. Checkpoint blobs are written under the owning session directory, and on startup the checkpoint runtime repairs older mistaken `.red-code/memory/checkpoints/...` and `.red-code/sessions/<session_public_id>/memory/checkpoints/...` blob paths by migrating them into `.red-code/sessions/<session_id>/memory/checkpoints/...` before checkpoint access continues.

Artifact public IDs now use the Phase 6 `A0001` format. During repository initialization, historical `Exxxx` artifact rows are renumbered into a stable, continuous `Axxxx` sequence before artifact reads and writes continue.

`SessionRecordLocator.get_layer_summary(...)` now returns exact per-layer counts backed by repository `COUNT(*)` queries. It is intended for accurate session health and retrieval summaries, while the separate `list_*` helpers remain available for preview-style record inspection.

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

## Capability Locations

Built-in Phase 5 capability manifests live under:

- `src/capabilities/`

User-local capability manifests live under:

- `.red-code/capabilities/`

Example:

```text
.red-code/
  capabilities/
    my-module/
      capability.json
```

If a local capability has the same name as a built-in capability, the local capability overrides it after the capability registry is reloaded.

## Current Architecture

Core source areas:

- `src/main.py`
- `src/agent/`
- `src/app/`
- `src/web/`
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

`surface-recon` and `web-enum` are Phase 5 modules. Their legacy `SKILL.md` files remain only as migration/debug prompt bridges; the target execution path is `/module run <name> <target> [json_overrides]`.

## Tests

```powershell
# Windows
.venv\Scripts\python -m pytest
```

```bash
# macOS / Linux
.venv/bin/python -m pytest
```
