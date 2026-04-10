# Phase 4 Finalization: Risk Policy and Confirmation System

## Purpose

This document closes the design loop for **Phase 4: Risk Policy and Confirmation System**.

It converts the Phase 4 planning guidance into a fixed implementation baseline. After this document, Phase 4 should be treated as **implementation-ready** unless product goals change.

This document freezes:

- the risk level vocabulary
- the deterministic confirmation policy boundary
- the default action-to-risk mapping
- the policy configuration path
- the normal/red-team base tool access boundary
- the controller/execution confirmation flow
- the relationship between risk policy and scope validation
- the rejection of unnecessary policy designs

It should be read together with:

- [SPEC](D:\Project\Python\Agent\docs\SPEC.md)
- [Session Target Architecture](D:\Project\Python\Agent\docs\architecture\session-target-architecture.md)
- [Session Refactor Development Plan](D:\Project\Python\Agent\docs\development\session-refactor-development-plan.en.md)
- [Phase 3 Finalization](D:\Project\Python\Agent\docs\development\session-phase-3-finalization.en.md)
- [Phase 4 Implementation Checklist](D:\Project\Python\Agent\docs\development\session-phase-4-implementation-checklist.en.md)

## Phase 4 Status

Phase 4 is now **architecturally converged**.

This means:

- the risk policy vocabulary is settled
- the confirmation service boundary is settled
- the default policy source is settled
- the normal/red-team tool access direction is settled
- coding can begin without reopening the confirmation model

## Replacement Position of Phase 4

Phase 4 is the point where the old low-level policy setup is replaced in **product safety terms**.

After Phase 4:

- users no longer need to configure ports, protocols, tool categories, rate limits, or confirmation actions during normal session creation
- risk decisions are centralized in the confirmation policy service
- elevated and dangerous actions pause through structured execution events
- the CLI renders confirmation but does not define policy

This phase does not delete all old internal policy machinery. It does, however, remove the old operation-level policy setup from the target user-facing path.

It also does not complete the physical merge or deletion of legacy `task` and `operation` implementations. Their overlap is real, but full cleanup is outside Phase 4.

## Final Decisions

## 1. Risk Level Vocabulary

Final decision:

- Phase 4 uses exactly three risk levels

Risk levels:

- `safe`
- `elevated`
- `dangerous`

Meaning:

- `safe` actions may auto-run when they pass scope validation.
- `elevated` actions require explicit user confirmation.
- `dangerous` actions require explicit user confirmation and stronger audit detail.

Not allowed:

- introducing extra public risk levels in Phase 4
- using numeric severity as the product-facing risk model

## 2. Deterministic Policy, Not AI-Model Risk Guessing

Final decision:

- risk classification is controlled by code and config, not by an AI model

Reason:

- confirmation behavior must be deterministic
- confirmation behavior must be testable
- confirmation behavior must be auditable
- CLI and future Web UI must share the same policy result

The Agent Controller may derive user intent, but the final risk classification must come from the confirmation policy service.

## 3. Policy Configuration Path

Final decision:

- project policy override file lives at `.red-code/config/risk-policy.json`

Recommended settings additions:

- `Settings.config_dir`
- `Settings.risk_policy_path`

Missing config behavior:

- use built-in defaults

Invalid config behavior:

- fail closed for red-team risk-gated execution
- return a clear configuration error
- do not silently allow dangerous actions

## 4. Default Action Mapping

Final decision:

Phase 4 ships with this default mapping.

| Action | Risk | Behavior |
| --- | --- | --- |
| `dns_lookup` | `safe` | Auto-run inside scope |
| `http_probe` | `safe` | Auto-run inside scope |
| `tls_inspect` | `safe` | Auto-run inside scope |
| `banner_grab` | `safe` | Auto-run inside scope |
| `port_scan_small` | `safe` | Auto-run inside scope and configured size limits |
| `batch_safe_probe` | `safe` | Auto-run when all child actions are safe and target count stays under policy limits |
| `port_scan_large` | `elevated` | Requires confirmation |
| `directory_scan_large` | `elevated` | Requires confirmation |
| `poc_execute` | `dangerous` | Requires confirmation and stronger audit |
| unknown red-team action | `elevated` | Requires confirmation |

Default small-scan limits:

- `small_port_scan_max_ports_per_target`: `100`
- `small_port_scan_max_targets`: `10`
- `safe_batch_max_targets`: `25`

These limits are defaults. They must be configurable through the risk policy file.

## 5. Confirmation Policy Service Boundary

Final decision:

- confirmation decisions are owned by an application-layer service

Recommended location:

- `src/app/confirmation_policy_service.py`

Responsibilities:

- load built-in defaults
- load `.red-code/config/risk-policy.json`
- validate policy config
- classify actions
- apply action overrides
- reserve module override support for Phase 5
- return structured confirmation decisions
- provide adapter-neutral confirmation prompt payloads

Not allowed:

- hardcoding risk decisions in `src/main.py`
- hardcoding risk decisions in CLI rendering code
- asking the model to make the final risk classification in prose

## 6. Risk Policy Model Boundary

Final decision:

- risk policy data structures live in the model layer

Recommended location:

- `src/models/risk_policy.py`

Minimum model concepts:

- `RiskLevel`
- confirmation mode
- action policy
- policy limits
- loaded policy config
- confirmation decision

These models must be importable by services and tests without pulling in CLI code.

## 7. Tool Access Policy by Mode

Final decision:

- both normal and red-team agents may use base file tools, but red-team mode has stricter policy boundaries

Recommended location:

- `src/app/tool_access_policy_service.py`

Normal mode:

- may use base read, write, execute, and destructive tools under the existing runtime safety policy
- continues to require confirmation for sensitive writes, destructive operations, and risky shell commands

Red-team mode:

- may read and search workspace/session files
- may write and edit session-owned generated files
- must confirm writes outside the session-owned output area
- must confirm destructive file operations
- must not use generic shell commands as the default security execution path

Important distinction:

- base file tools are allowed for agent work
- typed security tools remain required for red-team security execution

## 8. Security Execution Boundary

Final decision:

- red-team security execution goes through the execution service and typed security tool path

Relevant internal modules:

- `src/app/execution_service.py`
- `src/app/security_tool_execution_service.py`
- `src/app/scoped_execution_service.py`
- `src/orchestration/scope_validator.py`
- `src/tools/security/`

Not allowed:

- implementing red-team scanning primarily through raw `bash`
- using file tools to bypass artifact/finding/result persistence
- treating risk policy as a replacement for scope validation

## 9. Relationship to Scope Validation

Final decision:

- risk policy and scope validation are separate checks

Risk policy answers:

- "Does this type of action need confirmation?"

Scope validation answers:

- "Is this target allowed?"

Execution may proceed only when all checks pass:

- the action is auto-allowed or confirmed
- the target is in scope
- runtime capability policy permits the needed tool

Not allowed:

- allowing a `safe` action against an out-of-scope target
- using user confirmation to override a scope denial

## 10. Controller Integration Policy

Final decision:

- the Agent Controller routes confirmation requests, but does not own risk policy

The controller may:

- receive confirmation-required results
- ask the adapter to render a confirmation request
- pass approve/deny decisions back to execution
- summarize why execution paused

The controller may not:

- hardcode action risk mapping
- turn model narration into the final policy source
- call raw shell tools to avoid the confirmation service

## 11. Execution Integration Policy

Final decision:

- the execution service gates risked steps before running them

Minimum behavior:

- `safe` actions continue automatically after scope validation
- `elevated` actions emit confirmation-required and pause
- `dangerous` actions emit confirmation-required and pause with stronger audit metadata
- denied actions return structured blocked outcomes
- approved actions resume execution and record approval

Recommended event additions or equivalents:

- `confirmation_required`
- `confirmation_approved`
- `confirmation_denied`

These events should be adapter-neutral and usable by CLI now and Web UI later.

## 12. CLI Role During Confirmation

Final decision:

- the CLI renders confirmation requests but does not define the policy

The CLI may:

- show risk level
- show action name
- show target summary
- ask for approve or deny
- send the user's decision back to the controller or execution service

The CLI may not:

- own the action-to-risk map
- decide that a POC is safe
- silently auto-approve elevated or dangerous actions

## 13. Legacy Policy Boundary

### REWRITE REQUIRED

The primary session path must not depend on users manually filling:

- ports
- protocols
- tool categories
- rate limits
- confirmation action lists

Existing operation/scope policy fields may remain temporarily for internal migration or legacy tests, but they are not the target user-facing policy model.

Do not build a long-lived compatibility layer that re-exposes operation policy fields under new session labels.

## 14. Legacy `task` / `operation` Cleanup Boundary

Final decision:

- Phase 4 does not own the full physical cleanup of overlapping legacy `task` and `operation` containers

Rationale:

- `task` and `operation` both overlap with `session` as old top-level work containers
- `task` cleanup touches checkpoints, task runs, task skill binding, and ordinary agent history
- `operation` cleanup touches scope policy, jobs, evidence, findings, operation events, and red-team runtime storage
- those concerns are broader than risk policy and confirmation

Allowed in Phase 4:

- demote operation-level confirmation fields from the primary session path
- route new confirmation policy through `session` and `ExecutionService`
- reuse legacy operation-backed internals temporarily where needed for scoped execution
- add guardrail tests that prevent user-facing session confirmation from requiring operation policy fields

Not allowed in Phase 4:

- making `TaskService` deletion a Phase 4 exit criterion
- making `OperationService` deletion a Phase 4 exit criterion
- rewriting task checkpoint storage as part of risk policy work
- rewriting operation/job/evidence/finding storage as part of risk policy work
- treating legacy top-level model cleanup as a prerequisite for confirmation policy implementation

Merge timing:

- Phase 4 records the overlap but does not perform the physical merge.
- Phase 5 removes operation-id-based skill/module workflow dependencies so modules no longer require `operation` as a top-level container.
- Phase 6 starts the physical merge because the storage split is where task checkpoints, operation jobs, evidence, findings, artifacts, and reports can be re-owned by `session`.
- Phase 7 must not depend on `TaskService` or `OperationService` for the primary record retrieval and report flows.
- The final architecture must still remove `task` and `operation` as top-level concepts rather than keeping them indefinitely.

## 15. Rejected Designs

The following designs are explicitly rejected and should be discarded.

### Rejected: Manual Low-Level Session Policy Wizard

Reason:

- it preserves the complexity this phase is meant to remove

### Rejected: CLI-Only Confirmation Rules

Reason:

- policy must be shared by CLI and future Web UI

### Rejected: AI-Model-Only Risk Judgment

Reason:

- safety behavior must be deterministic and testable

### Rejected: Shell-First Red-Team Execution

Reason:

- typed tools and scope validation are the safety boundary for security actions

### Rejected: All File Tools Disabled in Red-Team Mode

Reason:

- the red-team agent still needs basic file read/write capability for notes, artifacts, findings, and reports

### Rejected: Unrestricted File and Shell Tools in Red-Team Mode

Reason:

- it would allow bypassing typed execution, policy checks, and structured persistence

### Rejected: Scope Confirmation Override

Reason:

- user confirmation should not override an out-of-scope target

### Rejected: Phase 4 as Full Legacy Container Cleanup

Reason:

- it would turn a risk policy phase into a cross-cutting persistence/runtime migration
- it would make confirmation policy depend on unrelated checkpoint, job, evidence, and finding cleanup

## Final Module Plan for Phase 4

New Phase 4 modules:

- `src/models/risk_policy.py`
- `src/app/confirmation_policy_service.py`
- `src/app/tool_access_policy_service.py`

Expected touched files:

- `src/agent/settings.py`
- `src/app/execution_service.py`
- `src/runtime/foreground_runner.py`
- `src/runtime/execution_events.py`
- `src/controller/agent_controller.py`
- `src/controller/contracts.py`
- `src/main.py`
- optionally `src/cli/ui.py`
- optionally `src/cli/adapter.py`
- relevant docs under `docs/`

Internal modules to reuse:

- `src/tools/policy.py`
- `src/tools/executor.py`
- `src/app/scoped_execution_service.py`
- `src/app/security_tool_execution_service.py`
- `src/orchestration/scope_validator.py`
- `src/tools/security/`

## Final Implementation Order

Phase 4 coding order is fixed as:

1. implement risk policy models
2. implement built-in defaults and config loading
3. implement the confirmation policy service
4. implement the tool access policy service
5. integrate the execution service confirmation gate
6. integrate controller confirmation outputs
7. integrate CLI confirmation rendering
8. record confirmation audit events
9. demote legacy low-level operation policy inputs from the primary session flow
10. record remaining `task` / `operation` overlap as Phase 6 merge work without making it a Phase 4 blocker

Do not invert this order unless a concrete implementation blocker is discovered.

## Final Testing Plan for Phase 4

Recommended new test files:

- `tests/test_risk_policy.py`
- `tests/test_confirmation_policy_service.py`
- `tests/test_tool_access_policy_service.py`
- optionally `tests/test_execution_confirmation_policy.py`

Required test areas:

### Risk Mapping

- DNS, HTTP, TLS, and banner actions classify as `safe`
- small port scans classify as `safe` within configured limits
- large port scans classify as `elevated`
- large directory scans classify as `elevated`
- POC execution classifies as `dangerous`
- unknown red-team actions require confirmation

### Config Loading

- missing config uses built-in defaults
- invalid config fails closed
- action overrides are applied
- scan and batch limits are configurable

### Confirmation Flow

- safe actions auto-allow after scope validation
- elevated actions pause for confirmation
- dangerous actions pause for confirmation
- denied actions are blocked and recorded
- approved actions resume execution and are recorded

### Tool Access Policy

- normal mode can use base file tools under existing safety policy
- red-team mode can read/search session files
- red-team mode can write session-owned output files
- red-team mode requires confirmation for writes outside session output area
- red-team mode does not use raw shell as the default security execution path

### Scope Interaction

- out-of-scope targets are denied even when action risk is `safe`
- user approval does not override scope denial

## Final Legacy Boundary

### REWRITE REQUIRED

The primary session path must not require users to configure operation-style low-level policy fields.

### Allowed Temporary Boundary

Allowed during migration:

- internal reuse of `ScopePolicy`
- internal reuse of scoped execution services
- legacy tests that still cover operation policy behavior
- advanced/debug slash commands that inspect old policy data

Not allowed:

- documenting operation policy fields as the new session policy model
- making session creation fail because the user did not provide ports, protocols, tool categories, rate limits, or confirmation action lists
- leaving POC execution dependent on CLI-only hardcoded prompts
- requiring complete `TaskService` or `OperationService` deletion before Phase 4 can complete

## Phase 4 Ready-to-Implement Checklist

Phase 4 is now considered fully converged if the team accepts the following locked decisions:

- risk levels are exactly `safe`, `elevated`, and `dangerous`
- risk classification is deterministic and config-driven
- `.red-code/config/risk-policy.json` is the project override path
- missing config uses built-in defaults
- invalid config fails closed
- low-risk scoped actions auto-run
- elevated and dangerous actions require confirmation
- confirmation events are structured and auditable
- normal and red-team agents can both use base file tools under explicit mode policy
- red-team security execution goes through typed tools and scope validation
- low-level operation policy setup is discarded from the main user flow
- full `task` / `operation` physical cleanup is explicitly deferred beyond Phase 4
- physical merge timing is fixed for Phase 6, after Phase 5 removes operation-id-based module dependencies

This checklist is now the Phase 4 baseline.
