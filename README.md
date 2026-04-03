# red-code

`red-code` is a local Python CLI coding agent built around:

- a LangChain tool-calling loop
- a persisted task runtime
- an explicit `SKILL.md` skill system
- a controlled local execution boundary

The project is intended for local single-user development work. It is not a SaaS agent platform or a multi-user service.

The repository now contains two parallel runtime families:

- v1 `Task` / `Run` for the existing coding-agent workflow
- v2 `Operation` / `Job` foundations for the red-team-oriented runtime

## Current Capabilities

- interactive local CLI
- Rich-based CLI presentation layer
- hierarchical help output with topic drill-down
- built-in and user-local `SKILL.md` skills
- explicit skill activation and one-shot skill invocation
- file tools: read, write, edit, list, search, delete
- web tools: `web_fetch` and `web_search`
- shell command execution with safety checks
- capability-tier tool safety
- session state and context compression
- persisted tasks, runs, checkpoints, and task logs
- task-scoped safety audit logging
- blob-backed checkpoint storage with metadata-only SQLite indexing
- persisted operations, scope policies, jobs, evidence, findings, and memory entries
- minimal red-team CLI inspection for operations and jobs

## Run

```powershell
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python src/main.py
```

## Current CLI Commands

- `/help`
- `/help operation`
- `/help job`
- `/help task`
- `/help skill`
- `/clear`
- `/operation create`
- `/operation list [status] [limit]`
- `/operation show <operation_id>`
- `/job create <operation_id>`
- `/job list <operation_id> [status] [limit]`
- `/job show <job_id>`
- `/task create`
- `/task list [status] [limit]`
- `/task recent [limit]`
- `/task find <query> [limit]`
- `/task show <task_id>`
- `/task status <task_id>`
- `/task checkpoints <task_id> [limit]`
- `/task checkpoint <checkpoint_id>`
- `/task runs <task_id> [limit]`
- `/task run <run_id>`
- `/task logs <task_id> [limit]`
- `/task resume <task_id>`
- `/task detach`
- `/task complete`
- `/task help`

Use `latest` or `last` in task-facing commands to target the most recently updated task.

- `/skill list`
- `/skill show <name>`
- `/skill use <name>`
- `/skill reload`
- `/skill clear`
- `/skill current`
- `/skill help`
- `/skill-name <prompt>`

`/help` now shows only top-level topics.
Use `/help operation`, `/help job`, `/help task`, and `/help skill` for detailed command help.
`/clear` resets only the in-memory context and clears the screen while preserving any active task binding or active shell skill.

## Red-Team Phase 1 Scope

Phase 1 currently delivers:

- `Operation`, `ScopePolicy`, `Job`, `Evidence`, `Finding`, and `MemoryEntry` domain models
- SQLite-backed repositories and services for the v2 red-team runtime
- atomic operation plus scope-policy creation
- minimal `/operation` and `/job` CLI inspection flows

Phase 1 intentionally does not yet deliver:

- runtime scope enforcement
- typed security tool execution
- a background scheduler or worker runtime
- managed evidence artifact export
- automatic finding generation

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

The docs index is at `docs/README.md`.

## Built-In Skills

The current built-in skills are:

- `development-default`
- `security-audit`
- `weather-query-example`

## Tests

```powershell
.venv\Scripts\python -m pytest
```
