# Task Runtime

## Summary

The current codebase supports a persisted local task workflow.

Tasks are useful for:

- long-running work
- pause/resume
- checkpoints
- run logs
- failure recovery

Tasks are **not** only a future web/UI concern.
They are still valuable in the CLI, but the current task identity model is not CLI-friendly enough.

## Current Task Identity Problem

Today, tasks are primarily identified by UUID.

This is acceptable for storage, but awkward for CLI interaction because:

- full UUIDs are long
- task lists usually show shortened IDs
- `/task show <id>` and `/task resume <id>` are inconvenient when the real key is a UUID

The corrected direction is:

- keep UUID as the internal storage identifier
- add a CLI-friendly public/display ID for human interaction

## CLI Commands

### General Commands

- `/help`
- `/reset`
- `/exit`
- `/quit`

### Task Commands

- `/task create`
- `/task list`
- `/task show <task_id>`
- `/task logs <task_id> [limit]`
- `/task resume <task_id>`
- `/task detach`
- `/task complete`

Current note:

`<task_id>` is still inconvenient because it maps to UUID-oriented lookup today.
This is a roadmap item to improve.

## Shell Binding Model

Only one task can be bound to one interactive shell session at a time.

When a task is bound:

- the prompt changes to `task:<short_id> >`
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

Tasks may bind a `skill_profile`.

Current implementation status:

- task-bound skill behavior exists in code
- this supports persisted, skill-aware task execution

Target direction:

- task-bound skills remain explicit
- ad-hoc chat should move toward base mode with no implicit default skill
- task skills should stay visible and predictable

## Runtime Flow for a Bound Prompt

When the user sends a normal prompt while a task is bound:

1. `TaskRunner` verifies the task can run.
2. The runtime resolves the task skill if one is explicitly bound.
3. `RunService` creates a `Run` row.
4. A task log entry is written.
5. The model/tool loop executes.
6. The returned messages are applied to `SessionState`.
7. Context compression may run.
8. A checkpoint is saved.
9. The task is updated with the latest checkpoint and status.
10. The run is marked `completed` or `failed`.

## Persisted Entities

### Task

Stored in the `tasks` table.

Used for:

- task identity
- goal and metadata
- current status
- `skill_profile`
- current checkpoint pointer
- last error

### Run

Stored in the `runs` table.

Used for:

- one bound prompt execution
- start and finish timestamps
- step count
- last usage
- last error

### Checkpoint

Stored in the `checkpoints` table.

Used for:

- serialized `SessionState` snapshots
- restore of conversation context on `/task resume`

### TaskLogEntry

Stored in the `task_logs` table.

Used for:

- task lifecycle events
- run lifecycle events
- checkpoint-related events
- failure diagnostics

## Checkpoint Contents

The current checkpoint payload serializes `SessionState`:

- `history`
- `compressed_summary`
- `last_usage`

Supported message types:

- `HumanMessage`
- `AIMessage`
- `ToolMessage`
- `SystemMessage`

## Current Limitations

- tasks still rely on UUID-oriented interaction
- there is no CLI-friendly public task ID yet
- tasks are still manually completed with `/task complete`
- there is no autonomous background runner yet
- task UX in the CLI needs improvement

## Next Direction

The next task-related development goals should be:

1. add CLI-friendly task public IDs
2. support public ID lookup in task commands
3. keep UUID as the internal storage key
4. improve task list and task selection ergonomics
