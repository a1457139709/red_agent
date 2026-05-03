# Control Center Phase 0 Foundation Alignment

## 1. Purpose

This document records the Phase 0 foundation alignment for the CTF Control Center platform. It maps the current repository baseline to the platform design in:

- `docs/SPEC2.md`
- `docs/design/control-center-platform-design.md`
- `docs/development/control-center-platform-development.md`

Phase 0 deliberately does not implement the FastAPI server, Tauri desktop client, scanner adapters, terminal runtime, or the CTF persistence tables. Its role is to freeze the module boundary so later phases do not push CTF platform behavior into the existing CLI entrypoint or overload the current session runtime with incompatible product concepts.

## 2. Current Baseline

The current implementation already has reusable foundations:

- `src/app/` contains application services for sessions, jobs, artifacts, findings, reports, dashboards, scope policy, execution, and interaction orchestration.
- `src/web/` contains transport-neutral DTO and serialization contracts that can inform later HTTP/WebSocket DTO work.
- `src/storage/` contains SQLite storage, repository-local schema initialization, schema guard behavior, checkpoint storage, and session-scoped filesystem path helpers.
- `src/orchestration/` and `src/runtime/` contain admission, scheduling, planner runtime, execution events, foreground runner, leases, and timeout behavior.
- `src/main.py` remains the CLI entrypoint and must not become the App Server entrypoint.

These modules are useful implementation references, but the CTF Control Center introduces product concepts that deserve explicit names and ownership.

## 3. Boundary Decisions

The following Phase 0 boundaries are now reserved under `src/app/`:

- `ProjectService`
- `TargetSessionService`
- `AttackPathService`
- `ScannerService`
- `TerminalService`
- `WriteupService`

The service classes are intentionally lightweight in Phase 0. They are importable and constructible with `Settings`, which gives later phases stable module names without pretending that Phase 2+ business behavior exists.

Existing concepts should be reused by behavior, not by forcing names:

- Current `Session` remains the existing CLI/redteam session model. CTF `TargetSession` will be project-scoped and implemented separately in Phase 2.
- Current `Job` is a useful reference for task status, leases, retries, logs, and cancellation. CTF `Task` will be implemented as its own persisted platform record in Phase 2.
- Current `Artifact` overlaps with CTF `Evidence`, but Phase 2 should create the CTF evidence table and link it to raw artifact files explicitly.
- Current `Finding` and `Report` are useful references for field shape and services. CTF findings/reports should include `project_id` and project/session scoped file references.
- Current web DTOs are stable adapter contracts for the existing conversation layer. The Control Center API and WebSocket envelopes should be introduced under `src/server/` and CTF-specific DTO modules in later phases.

## 4. Persistence and Migration Direction

The current repository style is repository-local SQLite initialization using `CREATE TABLE IF NOT EXISTS`, plus focused migration or clean-reset guards where older development schemas are incompatible.

Phase 2 should keep that style for new CTF tables:

- Add new repositories for `projects`, `target_sessions`, `tasks`, `events`, `evidence`, `findings`, `attack_path_nodes`, `command_runs`, `flags`, and `reports`.
- Initialize new tables and indexes from repository-owned schema strings.
- Prefer forward-only table/index creation for Phase 2.
- Do not build compatibility paths for obsolete development data.
- If incompatible development data is detected, use a clear clean-reset error through `storage.schema_guard` rather than long-lived dual writes or lossy compatibility code.

This matches the project rule that the current codebase is still in development and may rebuild local databases when necessary.

## 5. Filesystem Layout

Phase 0 reserves the project workspace root:

```text
.red-code/
  projects/
    <project_id>/
      project.json
      sessions/
        <session_id>/
          artifacts/
          reports/
          scripts/
          notes/
      reports/
```

The new `Settings.projects_dir` property points to `.red-code/projects`.

The new `storage.project_paths` helpers define canonical paths for:

- project root
- project manifest
- project reports
- target session root
- target session artifacts
- target session reports
- target session scripts
- target session notes

Project and session identifiers must be single path segments. Relative path resolvers reject absolute paths and `..` escapes so later artifact, report, script, and note writers can share one path-safety rule.

## 6. Phase 0 Acceptance

Phase 0 is complete when:

- The six Control Center service boundaries can be imported and constructed.
- `.red-code/projects/` has a single canonical Settings property and path helper module.
- Path helper tests prove the expected layout and reject path escape attempts.
- Existing CLI and session runtime entrypoints are unchanged.
- No runtime code depends on Tauri or frontend packages.
