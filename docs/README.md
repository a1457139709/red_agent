# Documentation Index

This folder contains the maintained project documentation for the current Python implementation.

## Structure

### Root

1. `SPEC.md`
   Target product specification for the next-stage refactor: natural-language-first interaction,
   unified `session` model, red-team mode, execution closure, and safety confirmation policy.

### `architecture/`

Architecture docs describe how the current runtime works and, where explicitly labeled, the target
runtime shape for planned refactors.

1. `architecture/architecture.md`
   Current system topology, runtime boundaries, storage layout, and execution flow.
2. `architecture/task-runtime.md`
   Persisted task model, run lifecycle, checkpoints, public IDs, and bound-task behavior.
3. `architecture/prompt-runtime-contract.md`
   Contract for the base prompt, skill prompt, and context-summary layers.
4. `architecture/skill-system-standard.md`
   Current `SKILL.md` parsing, discovery, activation, and safety integration rules. This is a
   current-runtime reference, not the target Phase 5 skill/module architecture.
5. `architecture/checkpoint-storage-evolution.md`
   Checkpoint storage design: SQLite metadata plus filesystem blobs.
6. `architecture/session-target-architecture.md`
   Target architecture for the planned `session`-centric refactor, including mode split,
   layered boundaries, execution closure, memory/artifact separation, and migration direction.

### `development/`

Development docs describe planning, review, and iteration guidance.

1. `development/engineering-development-plan.en.md`
   Retired task-centric development plan retained for historical context only.
2. `development/architecture-review.md`
   Current project assessment, maturity snapshot, and comparison notes.
3. `development/red-team-agent-srs.md`
   Retired requirements document retained for historical context only.
4. `development/red-team-agent-roadmap.md`
   Retired red-team implementation roadmap retained for historical context only.
5. `development/session-refactor-development-plan.en.md`
   Rewrite-first phased development plan for the `session`-centric target architecture, with
   explicit no-compatibility guidance for replacing the old `task` and `operation` product model.
6. `development/session-phase-1-implementation-checklist.en.md`
   Implementation-ready checklist for Phase 1, including module targets, file-level tasks,
   migration order, and explicit rewrite boundaries for the `session` domain reset.
7. `development/session-phase-1-domain-and-service-contract.en.md`
   Detailed Phase 1 contract draft for the new `Session` domain model, repository shape,
   service interface, state transitions, and legacy boundary rules.
8. `development/session-phase-1-finalization.en.md`
   Finalized Phase 1 baseline that freezes the `Session` model, statuses, persistence direction,
   repository and service boundaries, and the no-compatibility rule for `task` and `operation`.
9. `development/session-phase-2-implementation-checklist.en.md`
   Implementation-ready checklist for Phase 2, covering the Agent Controller layer, CLI adapter
   split, intent routing, clarification flow, and the demotion of slash commands from the primary UX.
10. `development/session-phase-2-finalization.en.md`
   Finalized Phase 2 baseline that freezes the controller boundary, intent model, clarification
   policy, CLI role, and the rewrite requirement for `src/main.py`.
11. `development/session-phase-3-implementation-checklist.en.md`
   Implementation-ready checklist for Phase 3, covering foreground execution closure, execution
   services, progress events, controller integration, and the rejection of manual multi-step execution UX.
12. `development/session-phase-3-finalization.en.md`
   Finalized Phase 3 baseline that freezes the foreground-first execution model, execution service
   boundary, progress event model, and the demotion of worker-facing execution from the main product path.
13. `development/session-phase-4-implementation-checklist.en.md`
   Implementation-ready checklist for Phase 4, covering risk policy, confirmation configuration,
   mode-specific base tool access, execution gating, audit events, and the rejection of CLI-owned safety rules.
14. `development/session-phase-4-finalization.en.md`
   Finalized Phase 4 baseline that freezes the three-level risk model, `.red-code/config/risk-policy.json`
   override path, confirmation service boundary, and the policy/scope/tool-access separation.

## Read These First

If you are new to the codebase, start with:

1. `SPEC.md`
2. `architecture/session-target-architecture.md`
3. `development/session-refactor-development-plan.en.md`

For the currently implemented runtime shape, then read:

1. `architecture/architecture.md`
2. `architecture/task-runtime.md`

For historical context on the pre-session planning track, only read documents that are explicitly marked `RETIRED DOCUMENT`.

## Maintenance Rules

- `docs/` should describe the current codebase, not historical experiments.
- Historical documents may remain only when they are explicitly marked `RETIRED DOCUMENT` and link to the current source of truth.
- Architecture docs should explain implemented behavior first and future work second unless a
  document is explicitly marked as a target design for an approved refactor.
- Development docs should stay separate from runtime contracts and system topology.
- If a document becomes stale, rewrite it or remove it.
- When code and docs disagree, update the docs after confirming the code path.
