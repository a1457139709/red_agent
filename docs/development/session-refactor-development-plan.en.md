# Session Refactor Development Plan

## Purpose

This document is the phased engineering plan for rebuilding `red-code` around the target product direction defined in:

- [SPEC](D:\Project\Python\Agent\docs\SPEC.md)
- [Session Target Architecture](D:\Project\Python\Agent\docs\architecture\session-target-architecture.md)

The plan is written for implementation, not for historical record. It is intentionally opinionated and favors a clean rewrite of the product-facing architecture over compatibility with the current `task` and `operation` split.

## Product Direction Summary

The target product is:

- a local-first single-user agent
- natural-language-first
- CLI-first today, Web-ready later
- split into `normal` and `redteam` modes
- centered on one top-level user concept: `session`
- capable of foreground execution closure for red-team workflows

The target product is not:

- a slash-command-first operator shell
- a dual-model system where both `task` and `operation` remain user-visible
- a compatibility-heavy migration that preserves obsolete concepts

## Non-Negotiable Decisions

The following decisions are fixed and should not be reopened during implementation unless the product goals change.

### 1. `session` Replaces `task` and `operation`

`session` is the only top-level user-facing work unit.

`task` and `operation` must be removed from the user model.

### 2. Natural Language Is the Primary Entry Point

The main user flow must start from natural language.

Slash commands remain available only for:

- debugging
- advanced operator controls
- internal inspection

### 3. Red-Team Execution Must Be Foreground-First

The user must be able to start a red-team workflow and watch it progress in the current session.

Background-capable internals may remain, but they must not be required for the basic product loop.

### 4. No Compatibility Layer for the Old Top-Level Model

This refactor must not preserve the old `task` / `operation` split through a long-lived compatibility layer.

Temporary migration code is acceptable only inside internal implementation phases. It must not become part of the new runtime contract.

## Engineering Principles

### 1. Rewrite Product Boundaries, Reuse Low-Level Safety

Rewrite:

- top-level workflow model
- user-facing commands
- runtime entry flow
- presentation model

Reuse when practical:

- scope validation
- typed security tools
- evidence generation
- worker, scheduler, and job primitives

### 2. Separate Intent, Orchestration, and Execution

The implementation must clearly separate:

- UI adapters
- agent/controller logic
- application services
- execution engine
- persistence

### 3. Remove Obsolete Paths Early

If a path is known to be obsolete in the target design, prefer deleting it or isolating it early rather than extending it.

### 4. Do Not Stretch Legacy Concepts

Do not force:

- `task` to behave like `session`
- `operation` to behave like `session`
- old slash commands to become the permanent red-team API

That would preserve exactly the architecture this rewrite is intended to remove.

## Rewrite Hotspots

The following areas are expected to require major rewrites rather than incremental extension.

### REWRITE REQUIRED: Top-Level Runtime Model

Current problem:

- `task` and `operation` represent overlapping user concepts

Target:

- a single `session` domain model

No compatibility goal:

- do not preserve parallel top-level models in the final design

### REWRITE REQUIRED: `src/main.py`

Current problem:

- `src/main.py` mixes CLI routing, domain creation, workflow invocation, prompt execution, and user interaction

Target:

- thin adapter logic only

No compatibility goal:

- do not keep `src/main.py` as the permanent composition center for product logic

### REWRITE REQUIRED: CLI Command Model

Current problem:

- workflow is command-driven and ID-driven

Target:

- natural-language-first controller-driven interaction

No compatibility goal:

- do not keep slash commands as the primary product surface

### REWRITE REQUIRED: Session Persistence Structure

Current problem:

- memory, evidence, findings, and reports are not organized around the target `session` model

Target:

- explicit `memory/`, `artifacts/`, `findings/`, and `reports/` layers

No compatibility goal:

- do not preserve the old storage mental model if it conflicts with the target structure

### REWRITE REQUIRED: Current `SKILL.md` Workflow Model

Current problem:

- the existing skill runtime is centered on prompt-body injection, `allowed-tools`, explicit `/skill` activation, task binding, and some operation-id-based workflow skills

Target:

- a unified skill/module capability contract that can run one-shot or inside a `session`, carry parameters and risk metadata, integrate with the controller, and execute through the execution service

No compatibility goal:

- do not treat the current `SKILL.md` workflow design as the target Phase 5 architecture
- do not preserve `/skill plan <name> <operation_id>` or `/skill apply <name> <operation_id>` as the primary red-team module flow

## Replacement Milestone for `task` and `operation`

The replacement of `task` and `operation` happens in stages.

### Phase 1: Architecture Replacement

In Phase 1:

- `session` replaces `task` and `operation` as the target top-level product concept
- `TaskService` and `OperationService` become legacy services
- new top-level contracts must be written against `session`, not against legacy models

This is the point where the old top-level model is replaced in architecture terms.

### Phase 2: Product Entry Replacement

In Phase 2:

- the primary runtime entry path moves to natural language plus the Agent Controller
- `/task` and `/operation` are demoted to advanced or debug-only paths
- the main product workflow no longer depends on legacy top-level commands

This is the point where the old top-level model is replaced in product UX terms.

### Phase 3 and Later: Physical Cleanup

From Phase 3 onward:

- once the new runtime path is stable, legacy top-level code paths should be removed physically
- deletion may proceed only after the controller-first and foreground-execution paths are established

This is the point where the old top-level model should disappear from the codebase, not just from the target design.

### Phase 4 Boundary: Do Not Complete Full Legacy Container Cleanup Here

In Phase 4:

- `task` and `operation` overlap is acknowledged as real
- operation-level confirmation fields are demoted from the primary session path
- new confirmation behavior should route through `session` and `ExecutionService`

But Phase 4 does not own:

- full `TaskService` deletion
- full `OperationService` deletion
- task checkpoint storage rewrite
- operation/job/evidence/finding storage rewrite

Fixed merge timing:

- Phase 4 records the overlap but does not perform the physical merge.
- Phase 5 removes operation-id-based skill/module workflow dependencies so modules no longer require `operation` as a top-level container.
- Phase 6 starts the physical merge because the storage split is where task checkpoints, operation jobs, evidence, findings, artifacts, and reports can be re-owned by `session`.
- Phase 7 must not depend on `TaskService` or `OperationService` for the primary record retrieval and report flows.

## Phase Overview

Implementation should follow this order:

1. Phase 0: Refactor Contract and Runtime Freeze
2. Phase 1: Session Domain Reset
3. Phase 2: Controller-First CLI and Intent Flow
4. Phase 3: Foreground Execution Closure
5. Phase 4: Risk Policy and Confirmation System
6. Phase 5: Skill and Module Unification
7. Phase 6: Session Storage Split
8. Phase 7: Record Retrieval and Report Flows
9. Phase 8: Web Adapter Readiness

## Phase 0: Refactor Contract and Runtime Freeze

### Goal

Freeze the target direction and prevent further investment in obsolete product-facing paths.

### Why This Phase Exists

The repository already contains multiple runtime families. Without an explicit freeze, implementation work can easily drift back into extending `task`, `operation`, or slash-command-first UX.

### Work Items

1. Mark the target documents as the source of truth for the next product direction.
2. Identify all product-facing references to:
   - `task`
   - `operation`
   - slash-first workflows
3. Classify current modules into:
   - keep and reuse
   - keep but hide internally
   - rewrite
   - delete
4. Define the initial `session` vocabulary for code, docs, CLI labels, and tests.
5. Define a short-term rule: no new feature may deepen the old `task` / `operation` split.

### Deliverables

- this development plan
- a rewrite inventory
- a clear source-of-truth statement in docs

### Exit Criteria

- the team can name which modules are stable internals and which are rewrite targets
- no new development work is planned on obsolete top-level flows

## Phase 1: Session Domain Reset

### Goal

Introduce `session` as the only top-level user-facing work unit.

### REWRITE REQUIRED

This phase is a domain rewrite. It must not preserve both `task` and `operation` as permanent user-facing concepts.

### Work Items

1. Define the `session` domain model:
   - mode
   - goal
   - targets
   - persistence mode
   - status
   - title or label
   - timestamps
2. Define session categories:
   - `normal`
   - `redteam`
3. Design the session repository and service interfaces.
4. Design the session status lifecycle.
5. Decide which internal execution primitives remain separate from `session`:
   - jobs
   - findings
   - artifacts
   - memory
6. Replace user-facing references to `task` and `operation` in documentation contracts.
7. Plan deletion of legacy top-level models from user paths.

### Engineering Notes

- Internal UUIDs may remain.
- User-facing labels should shift toward human-readable session summaries.
- Temporary database coexistence is acceptable only if it does not leak into the new product contract.

### Deliverables

- session model definition
- session service interface
- migration notes for internal persistence

### Exit Criteria

- the product has one top-level work unit
- `task` and `operation` are no longer part of the target UX model

### Test Focus

- session creation and retrieval
- session status transitions
- target metadata serialization
- human-readable session labeling

## Phase 2: Controller-First CLI and Intent Flow

### Goal

Move from command-driven routing to controller-driven, natural-language-first interaction.

### REWRITE REQUIRED

This phase requires a redesign of the CLI entry model and a major split of responsibilities now concentrated in `src/main.py`.

### Work Items

1. Introduce an Agent Controller layer responsible for:
   - mode routing
   - clarification flow
   - execution requests
   - record lookup requests
2. Redesign the CLI adapter so it only handles:
   - user input
   - output rendering
   - optional advanced command passthrough
3. Define how the controller decides between:
   - normal session
   - redteam session
4. Define clarification rules for common inputs such as:
   - a domain
   - an IP
   - a request for temporary probing
   - a request for a long-running red-team session
5. Reduce slash commands to advanced or debug-only flows.
6. Redesign help content around natural-language-first usage.

### Engineering Notes

- The controller should be a runtime boundary, not a prompt trick.
- The CLI should not create domain objects directly.
- Natural language must become the default path, not a secondary convenience feature.

### Deliverables

- controller interface
- CLI adapter contract
- clarification decision rules
- updated UX documentation

### Exit Criteria

- a user can start the primary flow without knowing slash commands
- the CLI no longer owns domain workflow logic

### Test Focus

- intent classification
- clarification branching
- controller-to-service integration
- command fallback behavior for advanced users

## Phase 3: Foreground Execution Closure

### Goal

Make red-team workflows execute and report progress in the current interactive session.

### REWRITE REQUIRED

This phase changes the basic runtime experience. The current "create now, run elsewhere" behavior must not survive as the default red-team flow.

### Work Items

1. Introduce a foreground execution runner for red-team sessions.
2. Define a step reporting model visible to the user:
   - what is running
   - what finished
   - what failed
   - what needs confirmation
3. Reuse internal job primitives where valuable, but hide them behind execution services.
4. Ensure red-team workflows can:
   - create internal execution units
   - run them in the current session
   - stream progress summaries
   - produce session-level results
5. Preserve the ability to retrieve execution records later.
6. Define when and how execution should pause for confirmation.

### Engineering Notes

- Foreground-first does not forbid background-capable internals.
- The user must not need to manually invoke worker-specific machinery for standard workflows.
- The execution service should become the public runtime contract, not the raw worker runtime.

### Deliverables

- foreground runner design
- execution progress model
- execution service contract

### Exit Criteria

- a red-team session can execute end-to-end from the current interactive flow
- progress reporting is visible and understandable
- execution records remain available after the run

### Test Focus

- foreground execution success paths
- foreground execution failure paths
- interrupted execution paths
- progress update rendering
- record persistence after execution

## Phase 4: Risk Policy and Confirmation System

### Goal

Replace manual low-level session setup with a configurable risk-based confirmation model.

### Work Items

1. Define risk levels:
   - `safe`
   - `elevated`
   - `dangerous`
2. Define the default action mapping for:
   - DNS
   - HTTP probing
   - TLS inspection
   - banner grabbing
   - port scanning
   - large-scale scanning
   - POC execution
3. Introduce configuration for confirmation policy.
4. Define override rules for specific modules or actions.
5. Connect confirmation policy to the controller and execution service.
6. Preserve auditability for all confirmed and denied actions.

### Engineering Notes

- This phase must simplify the user experience without weakening scope control.
- The system should ask for less setup and still enforce boundaries.
- This phase should not expand into a full physical merge or deletion of `TaskService` and `OperationService`.
- `task` / `operation` overlap should be documented as follow-up legacy cleanup, while Phase 4 only removes operation-level policy fields from the primary session path.

### Deliverables

- confirmation policy schema
- risk classification rules
- execution integration contract

### Exit Criteria

- low-risk actions can execute automatically
- elevated and dangerous actions pause for confirmation
- confirmation rules are configurable rather than hardcoded into CLI prompts
- Phase 4 can complete even if legacy `TaskService` and `OperationService` still exist internally, as long as the new session confirmation path does not expose them

### Test Focus

- risk mapping
- configuration parsing
- confirmation-required action handling
- denied action recording
- regression coverage that session confirmation does not require user-facing operation policy fields

## Phase 5: Skill and Module Unification

### Goal

Provide one extensible capability system that supports both general-purpose skills and red-team modules.

### REWRITE REQUIRED

The current `SKILL.md` system does **not** match the target architecture as-is.

Reusable pieces:

- local capability description files
- `allowed-tools` as a tool visibility narrowing mechanism
- `references/` and `scripts/` directory conventions

Not reusable as the target design:

- slash-command-first skill activation
- task-bound skill profiles
- operation-id-based workflow skills
- prompt-body-only module semantics
- `/skill plan <name> <operation_id>` and `/skill apply <name> <operation_id>` as the primary red-team module flow

### Work Items

1. Define the shared manifest model for:
   - metadata
   - parameters
   - visible tools
   - risk level
   - execution style
2. Preserve the user-facing vocabulary split:
   - `skill` for general-purpose features
   - `module` for red-team capabilities
3. Support:
   - one-shot execution
   - execution inside a persistent red-team session
4. Define how modules interact with the session controller and execution service.
5. Retire workflow distinctions that only exist because of the current architecture split.
6. Define the migration from current `SKILL.md` files to the new skill/module contract.
7. Explicitly mark current operation-id-based workflow skills as legacy or rewrite targets.
8. Remove operation-id-based module invocation as a prerequisite for the Phase 6 `task` / `operation` merge.

### Engineering Notes

- The user can see two labels.
- The runtime should not need two separate extension systems.
- Current `SKILL.md` behavior should be treated as implementation history, not as the Phase 5 target contract.
- The new module contract must express risk level, parameter schema, execution style, and session result ownership outside free-form prompt text.

### Deliverables

- unified extension contract
- skill/module vocabulary mapping
- execution integration rules
- migration and rewrite notes for existing `SKILL.md` files

### Exit Criteria

- a module can run once or inside a session
- skills and modules share a coherent runtime contract
- the target design no longer depends on operation-id-based skill workflow commands

### Test Focus

- manifest loading
- parameter validation
- tool visibility narrowing
- risk-level propagation
- migration behavior for existing built-in skills

## Phase 6: Session Storage Split

### Goal

Organize persistent red-team results into the target four-layer structure.

### REWRITE REQUIRED

This phase is a storage model rewrite for the persistent red-team product. Do not preserve a mixed or transcript-first storage design if it conflicts with the target shape.

### Work Items

1. Define persistent session storage layout for:
   - `memory/`
   - `artifacts/`
   - `findings/`
   - `reports/`
2. Define metadata models for each layer.
3. Separate AI harness memory from execution outputs.
4. Define linking rules:
   - artifact to session
   - finding to artifact
   - report to findings and artifacts
5. Define retention and retrieval rules.
6. Ensure session-level record lookup can locate all four layers.
7. Start the physical merge of overlapping legacy top-level containers:
   - re-own task checkpoints and run records under `session`
   - re-own operation jobs, events, evidence, and findings under `session`
   - convert remaining `TaskService` and `OperationService` usage into migration-only or read-only adapters where deletion is not immediately safe
   - delete legacy services once no primary runtime path depends on them

### Engineering Notes

- `memory/` is for AI reasoning support.
- Execution results must not be collapsed into a single undifferentiated memory file.
- Phase 6 is the first phase where full physical `task` / `operation` merge is in scope.
- Phase 6 should not preserve `task` and `operation` as parallel top-level containers after their data ownership has moved to `session`.

### Deliverables

- storage layout contract
- metadata contracts
- linking rules

### Exit Criteria

- persistent red-team sessions store data in four distinct layers
- AI memory and analyst-facing outputs are cleanly separated
- primary runtime storage ownership moves to `session`, not `task` or `operation`
- remaining `TaskService` and `OperationService` usage is migration-only, read-only, or removed

### Test Focus

- storage path generation
- metadata round-trip behavior
- cross-layer linking
- retrieval by session
- migration or deletion coverage for legacy task and operation storage ownership

## Phase 7: Record Retrieval and Report Flows

### Goal

Make execution records, findings, and reports accessible through the natural-language interface.

### Work Items

1. Define record retrieval services for:
   - session history summary
   - execution step logs
   - artifacts
   - findings
   - reports
2. Define AI-facing retrieval patterns such as:
   - "What did you already do?"
   - "Show me the last scan result."
   - "Why did you raise this finding?"
3. Define report generation flows:
   - session summary
   - findings summary
   - operator-readable output
4. Make reports automatically available when requested through the controller.
5. Avoid forcing the user to query raw IDs for normal flows.

### Deliverables

- retrieval service contract
- report generation contract
- user-facing query patterns

### Exit Criteria

- a user can ask the agent for prior records without raw internal knowledge
- reports can be generated automatically from structured session data

### Test Focus

- record lookup correctness
- report composition
- explanation traceability from finding to artifact

## Phase 8: Web Adapter Readiness

### Goal

Prepare the runtime for a future Web UI without changing the core product logic again.

### Work Items

1. Ensure the controller and application services are transport-agnostic.
2. Define DTOs for:
   - session summaries
   - execution progress
   - artifacts
   - findings
   - reports
3. Separate CLI-specific rendering from data preparation.
4. Define Web-ready events or polling contracts for foreground progress.
5. Verify that all required behavior is reachable without CLI-specific assumptions.

### Deliverables

- transport-neutral service boundaries
- adapter-facing DTOs
- progress reporting contract

### Exit Criteria

- a future Web adapter can reuse the same controller and services
- CLI concerns are not embedded in core business logic

### Test Focus

- DTO mapping
- adapter-independent service behavior
- progress model serialization

## Cross-Phase Testing Strategy

Testing should evolve by layer, not just by feature.

### 1. Domain and Persistence Tests

Focus on:

- session model integrity
- metadata serialization
- storage linking

### 2. Controller and Flow Tests

Focus on:

- intent routing
- clarification
- execution orchestration
- confirmation pauses

### 3. Execution Tests

Focus on:

- typed tool execution
- foreground progress
- record creation
- retry and failure visibility

### 4. End-to-End Product Tests

Focus on:

- natural-language red-team startup
- persistent red-team session creation
- temporary one-shot probing
- report retrieval

## Deletion Plan

The following concepts should be planned for removal from the final product-facing architecture:

- `/task` as a primary user workflow
- `/operation` as a primary user workflow
- the assumption that a red-team run must be started by manual operator command sequences
- ID-first interaction for common user flows
- operation-id-based `/skill plan` and `/skill apply` as the primary red-team module workflow

Deletion should happen deliberately and early enough to prevent duplicate architecture from surviving.

Do not use Phase 4 as the full deletion phase for `task` and `operation`. Phase 4 should only remove their policy-related leakage from the new session flow. Phase 5 removes operation-id-based module dependencies, and Phase 6 is the fixed phase where physical storage ownership and service cleanup begin. Phase 7 record retrieval must not depend on `TaskService` or `OperationService` as primary runtime services.

## Recommended First Implementation Milestone

The first meaningful milestone should deliver the smallest coherent slice of the target product:

1. a `session` top-level model
2. a controller-driven CLI flow
3. a foreground red-team execution path
4. risk-based confirmation
5. a minimal persistent split between `memory/` and execution outputs

This milestone matters more than broad feature count because it proves the architecture reset is real.

## Success Criteria for the Full Plan

The plan is complete when all of the following are true:

1. Users interact primarily through natural language.
2. `session` is the only top-level user-facing work unit.
3. Red-team workflows execute in the current session by default.
4. Confirmation is driven by configurable risk policy.
5. Skills and modules share one extensible runtime contract.
6. Persistent red-team data is split into `memory/`, `artifacts/`, `findings/`, and `reports/`.
7. Execution records are retrievable through the agent.
8. CLI and future Web UI share the same core controller and service layers.
