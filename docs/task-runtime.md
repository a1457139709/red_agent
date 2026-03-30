# Task Runtime

## Summary

The current codebase supports a persisted local task workflow.

Tasks are useful for:

- long-running work
- pause/resume
- checkpoints
- run logs
- failure recovery

Tasks are not only for a future web or UI layer. They are a first-class part of the CLI workflow.

## Task Identity Model

Tasks now use two identifiers:

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

In normal CLI usage, `<task_id>` should now be the public task ID.

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
- task skill binding does not overwrite the shell’s active session skill outside the task lifecycle

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

- task public IDs are currently generated locally and sequentially
- there is no task search by title yet
- tasks are still manually completed with `/task complete`
- there is no autonomous background runner yet
- task UX can still be improved further

## Next Direction

The next task-related goals should focus on ergonomics beyond identity:

1. better task selection and filtering
2. possible title-based or recent-task shortcuts
3. richer task/run inspection
4. eventual task-centric CLI flows for long-running work
