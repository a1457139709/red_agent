# Documentation Index

This folder contains the current maintained documentation for the Python codebase.

## Read These First

1. `architecture.md`
   Current runtime architecture, module boundaries, execution flow, and safety layer.
2. `task-runtime.md`
   Persisted task model, run lifecycle, checkpoints, public task IDs, and current safety-aware task flow.
3. `engineering-development-plan.en.md`
   Current roadmap, completed phases, and the next implementation phase.
4. `skill-system-standard.md`
   Current `SKILL.md` runtime model, built-in plus local skill discovery rules, and compatibility notes.

## Current Status

The docs now reflect the current implementation, including:

- explicit skill activation
- user-local skill support
- public task IDs
- capability-tier execution safety
- task-scoped safety audit logging

## Maintenance Rules

- `docs/` should describe the current Python implementation, not historical experiments.
- If a document becomes stale, rewrite it or remove it.
- Do not keep imported design notes from other projects unless they are clearly marked as historical and still useful.
- When code and docs disagree, update the docs immediately after confirming the code path.
