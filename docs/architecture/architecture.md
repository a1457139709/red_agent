# Architecture Overview

## Summary

`red-code` is a local, single-user Python CLI coding agent. The runtime is organized around four always-on concerns:

- interactive shell workflows
- explicit skill overlays
- persisted task execution
- safety-gated local tool access

The repository also contains a parallel v2 red-team runtime layer centered on persisted operations, jobs, scope-aware admission, and operation-level audit events.

The implementation is local-first. State lives under `.red-code/`, the agent talks to an OpenAI-compatible chat model through LangChain, and there is still no server or daemon in the current design. The v2 runtime now includes an in-process scheduler/worker foundation for durable job execution.

One naming detail is worth calling out: the product is branded as `red-code`, but the Python package name in `pyproject.toml` is still `mini-claude-code`.

## Code Map

```text
src/
  main.py                # shell loop, slash commands, prompt routing, active task/skill state
  cli/ui.py              # Rich presenter for help, task, run, checkpoint, and skill output
  agent/                 # model provider, prompt assembly, session state, context compression
  app/                   # task, run, checkpoint, skill, and v2 execution services
  orchestration/         # v2 scope validation, admission, scheduling, and job orchestration
  runtime/               # bound-task runner plus v2 lease, timeout, and worker helpers
  models/                # domain entities and serialization helpers
  skills/                # built-in SKILL.md files, parser, and registry
  storage/               # SQLite repositories and schema management
  tools/                 # registered tools, executor, and runtime safety policy
  utils/                 # confirmation, truncation, and path/shell safety helpers
```

## Runtime Boundaries

### 1. Shell and Presentation

`src/main.py` is the composition root. It builds settings, services, the tool executor, and the interactive loop.

The shell owns three pieces of session-local routing state:

- `active_task_id`
- `active_task_public_id`
- `active_skill_name`

`run_interactive_shell(...)` dispatches:

- session commands such as `/clear`, `/reset`, `/exit`, and `/quit`
- task commands under `/task ...`
- skill commands under `/skill ...`
- one-shot skill shorthand such as `/security-audit <prompt>`
- normal prompts in either base mode, active-skill mode, or bound-task mode

All human-facing structured output is rendered by `src/cli/ui.py` rather than being assembled ad hoc in the shell loop.

### 2. Prompt and Model Runtime

`src/agent/` owns one-turn agent execution:

- `provider.py` creates a `ChatOpenAI` model using environment-backed settings.
- `prompt.py` assembles the final system prompt from `SYSTEM_PROMPT.md`, an optional skill body, and an optional compressed context summary.
- `loop.py` runs the LangChain tool-calling loop until the model returns a final answer or the step limit is reached.
- `state.py` stores in-memory conversation history, compressed summary text, and last usage metadata.
- `context.py` decides when to compress history and uses the model to build a structured summary for future turns.

The agent loop itself is stateless across turns; persisted continuity comes from `SessionState` and task checkpoints.

### 3. Skill Runtime

Skills are explicit overlays, not the default runtime identity.

`src/skills/loader.py` parses `SKILL.md` frontmatter plus body into a normalized manifest.  
`src/skills/registry.py` discovers skills from:

- built-in: `src/skills/*/SKILL.md`
- local: `.red-code/skills/*/SKILL.md`

`SkillService` converts a resolved skill into a runtime config containing:

- the assembled system prompt
- the visible tool list
- the narrowed safety policy

If a local skill has the same name as a built-in skill, the local definition wins. The current built-in skill directories are:

- `development-default`
- `security-audit`
- `weather-query-example`

### 4. Tool Execution and Safety

The callable tool set exposed by `src/tools/__init__.py` is currently:

- `list_dir`
- `read_file`
- `search`
- `web_fetch`
- `web_search`
- `write_file`
- `edit_file`
- `bash`
- `delete_file`

`ToolExecutor` in `src/tools/executor.py` is the enforcement boundary between the model and the local machine. It is responsible for:

- filtering tool visibility for the current runtime
- applying the effective safety policy
- path resolution and workspace confinement
- confirmation gates for sensitive writes and destructive actions
- shell command danger classification
- bounded shell execution with explicit timeout and non-zero exit reporting
- UTF-8-first shell output decoding with Windows fallback codecs to avoid mojibake
- task-scoped audit and tool-event callbacks
- unknown tool requests normalized into audited tool errors

`src/tools/policy.py` maps tools into capability tiers:

- `read`
- `write`
- `execute`
- `destructive`

Skills may narrow tool visibility and therefore narrow the effective capability set, but they do not bypass the executor and do not expand base permissions.

### 5. V2 Operation Admission Runtime

The v2 red-team runtime does not reuse `ToolExecutor` as its primary network safety boundary.

Instead it uses:

- `ScopeValidator` to normalize targets and enforce host/domain/CIDR/protocol/port/tool-category rules
- `OperationAdmissionService` to load `Operation`, `ScopePolicy`, and optional `Job` context and persist admission denials
- `ScopedExecutionService` to handle confirmation and emit operation-level execution events
- `JobOrchestrationService` to own queueing, leasing, retries, cancellation, and terminal job transitions
- `Scheduler` to reclaim stale leases, cancel queued work, block failed dependency chains, and enqueue ready jobs
- `WorkerRuntime` to atomically lease queued jobs and resolve typed-tool attempts into durable job states
- `OperationEventService` to persist admission, confirmation, and execution facts to SQLite

This split keeps the legacy task runtime stable while making future typed security tools pass through an explicit scope-aware boundary.

### 6. V2 Job Runtime

The Phase 4 runtime is intentionally single-process and local-first.

`src/orchestration/job_service.py` owns durable job-state transitions for the v2 runtime:

- queue dependency-ready pending jobs
- persist cancellation requests
- cancel queued or pending jobs
- recover stale running leases
- apply retry backoff and retry exhaustion
- block dependents when an upstream job fails, times out, is blocked, or is cancelled

`src/runtime/worker.py` provides `WorkerRuntime.run_once()` and `WorkerRuntime.drain()`:

- `run_once()` atomically claims one queued job through a lease token
- heartbeats refresh the lease before and after an attempt
- typed-tool execution runs through the existing scoped admission boundary
- final job state is resolved by the worker, not by the scoped execution layer

`src/runtime/leases.py` contains lease-token and lease-deadline helpers.  
`src/runtime/timeouts.py` contains the bounded execution helper used to translate long-running typed-tool attempts into timeout outcomes.

### 7. Task Runtime

`src/runtime/task_runner.py` is the orchestration layer for persisted work. It turns one bound user prompt into one persisted `Run`.

Its responsibilities are:

- verifying task resumability
- restoring `SessionState` from the latest checkpoint
- resolving the task's explicit skill, if any
- starting and finalizing runs
- saving checkpoints after successful bound turns
- updating task status on resume, detach, completion, and failure
- writing task logs for lifecycle, safety, and tool events

The task runtime is only active when a shell has resumed a task with `/task resume <id>`.

### 8. Persistence

Persistence is split between SQLite metadata and filesystem blobs.

SQLite lives at:

- `.red-code/agent.db`

Checkpoint blobs live under:

- `.red-code/checkpoints/YYYY/MM/chk_<checkpoint_id>.json.gz`

Local user-defined skills live under:

- `.red-code/skills/<skill-name>/SKILL.md`

Repository ownership is split as follows:

- `storage/tasks.py` manages the `tasks` table and public task IDs such as `T0001`.
- `storage/runs.py` manages `runs`, `task_logs`, and public run IDs such as `R0001`.
- `storage/checkpoints.py` manages checkpoint metadata and schema-version validation.
- `storage/repositories/operation_events.py` manages v2 admission and execution audit rows.
- `app/checkpoint_service.py` owns blob serialization, digest validation, restore, delete, and prune behavior.

## Data Model

### Task

`Task` is the long-lived unit of work. It stores:

- internal UUID
- public ID
- title and goal
- workspace path
- lifecycle status
- optional `skill_profile`
- last checkpoint pointer
- last error
- free-form metadata

The supported statuses are:

- `pending`
- `running`
- `paused`
- `failed`
- `completed`
- `cancelled`

### Run

`Run` represents one bound prompt executed through `TaskRunner.run_prompt(...)`.

Each run stores:

- internal UUID and public ID
- owning task ID
- status and timestamps
- duration
- step count
- last token usage
- effective skill name
- effective visible tools
- failure kind
- last error

### Checkpoint

Checkpoint persistence is split into three shapes:

- `StoredCheckpoint`: full metadata row stored in SQLite
- `CheckpointRecord`: internal restore-oriented view
- `CheckpointSummary`: CLI-safe inspection view

The serialized payload is a versioned gzip-compressed JSON snapshot of `SessionState`, including:

- `history`
- `compressed_summary`
- `last_usage`

Checkpoint blobs are always serialized as UTF-8 JSON before gzip compression so non-ASCII user content can round-trip without data loss.

### TaskLogEntry

`TaskLogEntry` is the runtime event stream for a task. It is used for:

- task lifecycle events
- run lifecycle events
- checkpoint events
- safety audit events
- tool invoked/completed/failed events
- failure diagnostics

### OperationEvent

`OperationEvent` is the runtime audit stream for v2 red-team execution. It records:

- admission requests and denials
- confirmation-required, approved, and denied events
- execution started, succeeded, and failed events
- tool, category, target, reason code, and payload details

## Main Execution Flows

### Base Prompt Flow

1. The shell receives a normal prompt and no task is bound.
2. `SkillService.build_base_runtime_config(...)` assembles the base prompt and full tool set.
3. `run_prompt_with_runtime(...)` restricts the executor to the visible tools and applies the base safety policy.
4. `agent_loop(...)` runs the model/tool cycle.
5. `apply_result_to_session(...)` appends the new messages to `SessionState`.
6. If token usage crosses the configured threshold, the history is compressed and replaced by a structured summary.

### Active Skill Flow

1. The user activates a shell skill with `/skill use <name>` or calls a one-shot shorthand.
2. `SkillService.build_skill_runtime_config(...)` resolves the skill manifest.
3. The skill body is appended to the system prompt.
4. The visible tool set is filtered by `allowed-tools`.
5. The safety policy is recomputed from the filtered tools.
6. The result is written back into the same in-memory `SessionState`.

### Bound Task Flow

1. `/task resume <id>` restores the latest checkpoint into memory and binds the task to the shell.
2. Each normal prompt is routed to `TaskRunner.run_prompt(...)`.
3. `RunService.start_run(...)` creates a persisted run record.
4. `TaskRunner` resolves base mode or the task's explicit `skill_profile`.
5. The executor is wrapped with runtime safety, task-scoped audit logging, and tool-event logging.
6. `agent_loop(...)` executes the turn.
7. The updated `SessionState` is checkpointed through `CheckpointService`.
8. Task status, run status, and task logs are updated.
9. The task remains bound until detach, complete, reset, exit, or quit.

### Scoped V2 Execution Flow

1. A v2 caller builds an `AdmissionRequest` for an operation, optional job, tool name, tool category, and target.
2. `OperationAdmissionService` loads the operation context and writes `admission_requested`.
3. `ScopeValidator` normalizes the target and enforces scope policy rules.
4. Concurrency and per-minute execution limits are checked against persisted state.
5. If confirmation is required, `ScopedExecutionService` records the confirmation events, waits for approval, and then re-runs admission with confirmation disabled to re-check scope, concurrency, and rate limits.
6. If still admitted, `execution_started` is written and the injected callable executes.
7. `ScopedExecutionService` returns a structured attempt outcome and writes matching execution events.
8. `WorkerRuntime` and `JobOrchestrationService` resolve the durable job state, retry behavior, cancellation precedence, and lease cleanup.

## Architectural Rules

The current codebase follows these rules:

- `main.py` owns shell interaction and route selection.
- `SkillService` builds runtime configs; it does not execute tools.
- `TaskRunner` owns persisted task orchestration; it does not define storage schemas.
- `CheckpointService` owns checkpoint serialization and restore behavior.
- repositories own SQLite reads and writes.
- `ToolExecutor` is the only place where model-issued tool calls cross into local execution.
- the v2 red-team runtime uses `ScopedExecutionService` rather than `ToolExecutor` for scope-aware execution admission.
- the v2 worker runtime, not `ScopedExecutionService`, owns durable `Job` state transitions.
- skills specialize prompts and visible tools, but never bypass the safety boundary.

## Current Constraints

The architecture intentionally does not implement:

- multi-user or network service deployment
- a long-lived daemon or distributed worker pool
- remote checkpoint storage
- plugin/MCP-style external tool protocols
- sub-agent orchestration
- git-native review or PR workflows as first-class runtime features

Those are possible future directions, but they are not part of the current runtime contract.
