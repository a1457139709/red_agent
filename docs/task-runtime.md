# Task Runtime

## Summary

The current codebase supports a persisted local task workflow.

Tasks are useful for:

- long-running work
- pause/resume
- checkpoints
- run logs
- safety audit logs
- failure recovery

Tasks are not only for a future web or UI layer. They are a first-class part of the CLI workflow.

## Task Identity Model

Tasks use two identifiers:

- internal ID: UUID for storage and relations
- public ID: CLI-friendly identifier such as `T0001`

CLI-facing task operations should use the public ID first.
The internal UUID is still shown for debugging and remains valid for compatibility.

Current lookup behavior:

- exact public ID lookup is supported
- exact UUID lookup is supported
- unique UUID prefix lookup is still tolerated for compatibility

## CLI Commands

### General Commands

- `/help`
- `/help task`
- `/help skill`
- `/reset`
- `/exit`
- `/quit`

### Task Commands

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

In normal CLI usage, `<task_id>` should now be the public task ID.
Use `latest` or `last` in task-facing commands to target the most recently updated task.

Current help behavior:

- `/help` shows compact top-level topics
- `/help task` shows task plus run/checkpoint commands
- `/help skill` shows detailed skill commands
- `/task help` is an alias for `/help task`

## Shell Binding Model

Only one task can be bound to one interactive shell session at a time.

When a task is bound:

- the prompt changes to `task:<public_id> >`
- prompts execute through the task runtime
- `/reset`, `/exit`, and `/quit` pause and detach the task first

## Task States

The current task states are:

- `pending`
- `running`
- `paused`
- `failed`
- `completed`
- `cancelled`

Current behavior:

- a new task starts as `pending`
- `/task resume` moves a resumable task to `running`
- `/task detach` moves the active task to `paused`
- `/task complete` moves the active task to `completed`
- runtime exceptions during a bound run move the task to `failed`
- `completed` and `cancelled` tasks cannot be resumed

## Skill Relationship

Tasks may bind an optional `skill_profile`.

Current behavior:

- a blank skill at task creation means no task skill
- an explicit task skill is resolved only while that task is bound
- tasks with no `skill_profile` run in base mode
- task skill binding does not overwrite the shell's active session skill outside the task lifecycle

## Safety Relationship

Each bound run executes through the capability-tier safety boundary.

Current behavior:

- base-mode tasks use the base safety policy
- skill-bound tasks use a narrowed safety policy derived from the skill's allowed tools
- risky operations may be confirmed or blocked before tool execution
- task runs persist high-signal safety events into `task_logs`

Current capability tiers are:

- `read`
- `write`
- `execute`
- `destructive`

## Runtime Flow for a Bound Prompt

When the user sends a normal prompt while a task is bound:

1. `TaskRunner` verifies the task can run.
2. The runtime resolves the task skill if one is explicitly bound.
3. `RunService` creates a `Run` row.
4. A task log entry is written.
5. The effective visible tools and safety policy are derived.
6. The model/tool loop executes.
7. The returned messages are applied to `SessionState`.
8. Context compression may run.
9. A checkpoint is saved through `CheckpointService`.
10. The task is updated with the latest checkpoint and status.
11. The run is marked `completed` or `failed`.

## Persisted Entities

### Task

Stored in the `tasks` table.

Used for:

- internal UUID
- public task ID
- title and goal
- status
- workspace
- `skill_profile`
- current checkpoint pointer
- last error

### Run

Stored in the `runs` table.

Used for:

- public run ID
- one bound prompt execution
- start and finish timestamps
- duration
- step count
- effective skill
- effective tools
- failure kind
- last usage
- last error

### Checkpoint

Checkpoint storage is split across:

- SQLite metadata in the `checkpoints` table
- gzip-compressed session blobs under `.mini-claude-code/checkpoints/`

Checkpoint inspection currently exposes metadata only:

- checkpoint ID
- created time
- storage kind
- payload size
- history message count
- history text bytes
- compressed summary presence

Checkpoint lifecycle currently supports:

- save
- restore
- list
- inspect
- delete
- prune

### TaskLogEntry

Stored in the `task_logs` table.

Used for:

- task lifecycle events
- run lifecycle events
- checkpoint-related events
- failure diagnostics
- safety audit events
- tool event summaries

## Checkpoint Contents

The current checkpoint blob serializes `SessionState`:

- `history`
- `compressed_summary`
- `last_usage`

Supported message types:

- `HumanMessage`
- `AIMessage`
- `ToolMessage`
- `SystemMessage`

The current blob format is:

- versioned
- gzip-compressed JSON
- validated by digest before restore

## Current Limitations

- task public IDs are generated locally and sequentially
- tasks are still manually completed with `/task complete`
- there is no autonomous background runner yet
- checkpoint IDs are still raw UUIDs
- pruning/deletion does not automatically protect a task's currently referenced `last_checkpoint`

## Next Direction

The next task-related goals should focus on deeper diagnostics and exportability:

1. export-friendly diagnostics
2. richer checkpoint retention workflows
3. safer cybersecurity-oriented task flows
