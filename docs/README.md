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
   Retired `SKILL.md` runtime reference retained only for migration history. The current runtime
   uses capability directories plus `capability.json` and `prompt.md`.
5. `architecture/checkpoint-storage-evolution.md`
   Checkpoint storage design: SQLite metadata plus filesystem blobs.
6. `architecture/session-target-architecture.md`
   Target architecture for the planned `session`-centric refactor, including mode split,
   layered boundaries, execution closure, memory/artifact separation, and migration direction.
7. `architecture/control-center-target-architecture.zh.md`
   Target architecture for evolving `red-code` into a control-center product with a desktop client,
   Python App Server, realtime WebSocket interaction, dashboard views, and remote/local single-user deployment.

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
15. `development/session-phase-5-implementation-checklist.en.md`
   Implementation-ready checklist for Phase 5, covering the shared capability manifest, skill/module
   vocabulary split, module invocation without `operation_id`, and migration away from current `SKILL.md` workflows.
16. `development/session-phase-5-finalization.en.md`
   Finalized Phase 5 baseline that freezes `capability.json` as the target manifest direction,
   the `skill`/`module` capability contract, execution styles, and operation-id workflow rejection.
17. `development/session-phase-6-implementation-checklist.en.md`
   Implementation-ready checklist for Phase 6, covering the session-owned storage split, record ownership
   migration, session record locator, and the beginning of the physical `task` / `operation` merge.
18. `development/session-phase-6-finalization.en.md`
   Finalized Phase 6 baseline that freezes the four-layer session storage model, persistence ownership,
   session-owned execution records, and the legacy naming boundary for the storage refactor.
19. `development/session-phase-7-implementation-checklist.en.md`
   Implementation-ready checklist for Phase 7, covering command-first record retrieval, query contracts,
   finding explanation traces, and controller-facing report orchestration.
20. `development/session-phase-7-finalization.en.md`
   Finalized Phase 7 baseline that freezes the retrieval model, query and report-flow contracts,
   explanation-trace requirements, and the demotion of legacy top-level retrieval paths.
21. `development/session-phase-8-implementation-checklist.en.md`
   Implementation-ready checklist for Phase 8, covering Web adapter readiness, shared interaction
   orchestration, transport-neutral conversation state, Web DTOs, and stream/confirmation contracts.
22. `development/session-phase-8-finalization.en.md`
   Finalized Phase 8 design baseline for Web adapter readiness. As of April 25, 2026, this should be
   read as an architecture contract; the repository may still have only partial Phase 8 implementation
   such as Web-facing interface work rather than a complete Web adapter delivery.
23. `development/control-center-migration-plan.zh.md`
   Detailed migration plan for turning the current session-centric agent into a desktop control center
   with an App Server, realtime interaction channel, detached/background execution, and GUI-oriented APIs.
24. `development/control-center-platform-development.md`
   Development plan for the CTF Control Center platform phases, from foundation alignment through
   desktop packaging.
25. `development/control-center-phase-0-foundation-alignment.md`
   Phase 0 implementation baseline for CTF Control Center service boundaries, `.red-code/projects/`
   filesystem layout, and persistence migration direction.

### `design/`

Design docs describe approved target product and subsystem structure that is not necessarily fully
implemented yet.

1. `design/control-center-platform-design.md`
   Target design for the CTF Control Center platform, including desktop client, App Server,
   domain model, scanner adapter layer, external command-result capture, persistence, and reporting flow.

## Read These First

If you are new to the codebase, start with:

1. `SPEC.md`
2. `architecture/session-target-architecture.md`
3. `development/session-refactor-development-plan.en.md`

For the currently implemented runtime shape, then read:

1. `architecture/architecture.md`
2. `architecture/task-runtime.md`

For historical context on pre-capability or pre-session planning, only read documents that are explicitly marked `RETIRED DOCUMENT`.

## Maintenance Rules

- `docs/` should describe the current codebase, not historical experiments.
- Historical documents may remain only when they are explicitly marked `RETIRED DOCUMENT` and link to the current source of truth.
- Architecture docs should explain implemented behavior first and future work second unless a
  document is explicitly marked as a target design for an approved refactor.
- Development docs should stay separate from runtime contracts and system topology.
- If a document becomes stale, rewrite it or remove it.
- When code and docs disagree, update the docs after confirming the code path.
