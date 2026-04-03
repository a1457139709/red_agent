# Documentation Index

This folder contains the maintained project documentation for the current Python implementation.

## Structure

### `architecture/`

Architecture docs describe how the current runtime works.

1. `architecture/architecture.md`
   Current system topology, runtime boundaries, storage layout, and execution flow.
2. `architecture/task-runtime.md`
   Persisted task model, run lifecycle, checkpoints, public IDs, and bound-task behavior.
3. `architecture/prompt-runtime-contract.md`
   Contract for the base prompt, skill prompt, and context-summary layers.
4. `architecture/skill-system-standard.md`
   Current `SKILL.md` parsing, discovery, activation, and safety integration rules.
5. `architecture/checkpoint-storage-evolution.md`
   Checkpoint storage design: SQLite metadata plus filesystem blobs.

### `development/`

Development docs describe planning, review, and iteration guidance.

1. `development/engineering-development-plan.en.md`
   Roadmap, completed phases, and the next development focus.
2. `development/architecture-review.md`
   Current project assessment, maturity snapshot, and comparison notes.
3. `development/red-team-agent-srs.md`
   Product requirements for evolving the local agent into an authorized security assessment and red-team workflow runtime.
4. `development/red-team-agent-roadmap.md`
   Phased implementation roadmap mapped onto the current repository modules and runtime boundaries.

## Read These First

If you are new to the codebase, start with:

1. `architecture/architecture.md`
2. `architecture/task-runtime.md`
3. `development/engineering-development-plan.en.md`

## Maintenance Rules

- `docs/` should describe the current codebase, not historical experiments.
- Architecture docs should explain implemented behavior first and future work second.
- Development docs should stay separate from runtime contracts and system topology.
- If a document becomes stale, rewrite it or remove it.
- When code and docs disagree, update the docs after confirming the code path.
