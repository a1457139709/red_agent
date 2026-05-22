# RETIRED DOCUMENT

# Phase 4 Implementation Checklist: Risk Policy and Confirmation System

## Purpose

This document breaks down **Phase 4: Risk Policy and Confirmation System** into implementation-ready engineering tasks.

It should be read together with:

- [SPEC](D:\Project\Python\Agent\docs\SPEC.md)
- [Session Target Architecture](D:\Project\Python\Agent\docs\architecture\session-target-architecture.md)
- [Session Refactor Development Plan](D:\Project\Python\Agent\docs\development\session-refactor-development-plan.en.md)
- [Phase 3 Finalization](D:\Project\Python\Agent\docs\development\session-phase-3-finalization.en.md)

This checklist assumes Phase 1 through Phase 3 have already established the `session` domain, the Agent Controller boundary, and foreground-first execution.

## Phase Goal

Replace manual low-level setup with a deterministic, configurable, risk-based confirmation model.

The user should no longer need to provide these fields during normal session creation:

- ports
- protocols
- tool categories
- rate limits
- confirmation action lists

Instead, the system should apply defaults, classify the action, validate scope, auto-run low-risk actions, pause for elevated or dangerous actions, and record every required, approved, or denied confirmation.

## Scope

Phase 4 covers:

- risk level definitions
- default action-to-risk mapping
- policy config loading from `.red-code/config/risk-policy.json`
- confirmation decision service
- controller and execution service integration
- normal/red-team base tool access policy
- confirmation audit events
- demotion of operation-level policy fields from the primary user flow

Phase 4 does not require:

- final skill/module unification
- final `memory/` / `artifacts/` / `findings/` / `reports/` storage split
- Web UI implementation
- planner mode
- AI-model-based risk classification
- full physical merge or deletion of legacy `TaskService` and `OperationService`

## Non-Goals

Do not do the following in Phase 4:

- ask users to fill low-level scan policy fields during normal session creation
- hardcode confirmation prompts in the CLI as the source of policy truth
- rely on model prose to decide whether an action is dangerous
- let red-team security execution bypass typed tools through raw shell commands
- remove scope validation under the assumption that risk policy is enough
- build a long-lived compatibility layer around the old `task` / `operation` policy model
- expand Phase 4 into a full cleanup of overlapping legacy `task` and `operation` containers

## Rewrite Policy

### REWRITE REQUIRED

Phase 4 is a **policy boundary rewrite** for red-team execution.

Prefer:

- deterministic policy service decisions
- built-in safe defaults
- project-level policy overrides
- structured confirmation decisions
- audit events independent of CLI rendering

Avoid:

- adding more prompts to the old operation creation flow
- keeping `confirmation_required_actions` as the main product-facing policy mechanism
- scattering risk checks across CLI, controller, and tool code

## Rejected Designs

### Rejected: Manual Policy Setup at Session Creation

Users should not need to enter ports, protocols, tool categories, rate limits, or action confirmation lists before a session can be useful.

### Rejected: CLI-Owned Confirmation Policy

The CLI may render confirmation, but it must not own the action-to-risk map.

### Rejected: Prompt-Only Safety

Risk classification must be deterministic, testable, and auditable. The model can help derive intent, but it must not be the final policy authority.

### Rejected: Shell-Based Security Execution Bypass

Red-team security actions must go through execution services, typed tools, and scope validation rather than generic `bash`.

### Rejected: All-or-Nothing Red-Team Tool Access

Both normal and red-team agents may use basic file tools, but red-team mode must apply stricter boundaries around paths, destructive operations, and shell execution.

### Rejected: Long-Lived Operation Policy Compatibility

Operation-level policy fields may remain temporarily for internal migration or tests, but they must not become the new session policy surface.

### Rejected: Full `task` / `operation` Physical Cleanup Inside Phase 4

`task` and `operation` overlap as legacy top-level containers, but Phase 4 should not become the phase that fully merges or deletes both implementations.

Reason:

- Phase 4 is scoped to risk policy and confirmation.
- Full legacy container cleanup cuts across task checkpoints, operation scope policy, jobs, evidence, findings, and storage.
- That cleanup should be planned as a separate legacy model cleanup step after the session execution and policy path is stable.

## Target Outcomes

By the end of Phase 4:

1. Risk levels are stable domain concepts.
2. Default red-team actions map to `safe`, `elevated`, or `dangerous`.
3. Missing policy config falls back to built-in defaults.
4. Invalid policy config fails closed for red-team risk-gated execution.
5. Low-risk scoped actions can execute automatically.
6. Elevated and dangerous actions pause for confirmation.
7. Confirmed and denied actions are recorded as structured events.
8. Normal and red-team base tool access boundaries are explicit.
9. Scope validation remains separate from risk confirmation.

## Risk Model

Phase 4 must define exactly these risk levels:

- `safe`
- `elevated`
- `dangerous`

Recommended semantics:

- `safe` may run automatically when scope validation passes.
- `elevated` requires explicit user confirmation.
- `dangerous` requires explicit user confirmation and stronger audit detail.

Do not add extra public risk levels in Phase 4 unless the product goals change.

## Default Action Mapping

| Action | Default Risk | Default Behavior |
| --- | --- | --- |
| `dns_lookup` | `safe` | Auto-run inside target scope |
| `http_probe` | `safe` | Auto-run inside target scope |
| `tls_inspect` | `safe` | Auto-run inside target scope |
| `banner_grab` | `safe` | Auto-run inside target scope |
| `port_scan_small` | `safe` | Auto-run inside target scope and configured size limits |
| `batch_safe_probe` | `safe` | Auto-run when every child action is safe and target count stays under the configured batch limit |
| `port_scan_large` | `elevated` | Pause for confirmation |
| `directory_scan_large` | `elevated` | Pause for confirmation |
| `poc_execute` | `dangerous` | Pause for confirmation with stronger audit detail |
| unknown red-team action | `elevated` | Pause for confirmation |

Default limits should live in policy config, not CLI prompts:

- `small_port_scan_max_ports_per_target`: `100`
- `small_port_scan_max_targets`: `10`
- `safe_batch_max_targets`: `25`

## Policy Configuration

Recommended project policy path:

- `.red-code/config/risk-policy.json`

Recommended settings additions:

- `Settings.config_dir`
- `Settings.risk_policy_path`

Missing config behavior:

- use built-in defaults

Invalid config behavior:

- fail closed for red-team risk-gated execution
- return a clear configuration error
- do not silently downgrade to allow-all behavior

Minimum JSON shape:

```json
{
  "version": 1,
  "confirmation": {
    "safe": "auto",
    "elevated": "confirm",
    "dangerous": "confirm"
  },
  "limits": {
    "small_port_scan_max_ports_per_target": 100,
    "small_port_scan_max_targets": 10,
    "safe_batch_max_targets": 25
  },
  "actions": {
    "dns_lookup": { "risk": "safe" },
    "http_probe": { "risk": "safe" },
    "tls_inspect": { "risk": "safe" },
    "banner_grab": { "risk": "safe" },
    "port_scan_small": { "risk": "safe" },
    "port_scan_large": { "risk": "elevated" },
    "directory_scan_large": { "risk": "elevated" },
    "poc_execute": { "risk": "dangerous" }
  },
  "overrides": {
    "actions": {},
    "modules": {}
  }
}
```

## Modules to Introduce

### `src/models/risk_policy.py`

Responsibilities:

- define `RiskLevel`
- define confirmation mode values
- define action policy records
- define policy limits
- define loaded policy config
- define structured confirmation decisions

Completion check:

- tests can classify an action without importing CLI code

### `src/app/confirmation_policy_service.py`

Responsibilities:

- load built-in defaults
- load project overrides from `.red-code/config/risk-policy.json`
- validate config version and enum values
- classify action requests
- support action overrides
- reserve module override support for Phase 5
- return adapter-neutral confirmation prompt payloads

Completion check:

- elevated and dangerous actions return structured confirmation decisions

### `src/app/tool_access_policy_service.py`

Responsibilities:

- derive mode-specific base tool policy
- keep normal and red-team file access behavior explicit
- prevent red-team security execution from using raw file or shell tools as a bypass

Completion check:

- both normal and red-team agents can use basic file tools without giving red-team execution a shell bypass

## Existing Modules to Reuse

Reuse these internally:

- `src/tools/policy.py`
- `src/tools/executor.py`
- `src/app/scoped_execution_service.py`
- `src/app/security_tool_execution_service.py`
- `src/app/execution_service.py`
- `src/runtime/execution_events.py`
- `src/orchestration/scope_validator.py`

Boundary rules:

- `RuntimeSafetyPolicy` and `CapabilityTier` remain base tool capability controls.
- Risk policy is an additional red-team action confirmation layer.
- Scope validation remains the target boundary layer.

## Integration Checklist

## 1. Add Risk Policy Models

Files:

- `src/models/risk_policy.py`

Checklist:

- define the three risk levels
- define confirmation mode values
- define action policy and limits models
- define `ConfirmationDecision`
- make models independent from CLI and storage

## 2. Add Default Policy and Config Loading

Files:

- `src/app/confirmation_policy_service.py`
- `src/agent/settings.py`

Checklist:

- define built-in action mappings
- define built-in confirmation behavior
- define scan and batch limits
- load `.red-code/config/risk-policy.json` when present
- fail closed for invalid config

## 3. Add Confirmation Policy Service

Files:

- `src/app/confirmation_policy_service.py`

Checklist:

- expose action classification
- expose confirmation decision creation
- expose adapter-neutral prompt payloads
- handle unknown red-team actions as confirmation-required
- support action overrides now and module overrides later

## 4. Add Tool Access Policy Service

Files:

- `src/app/tool_access_policy_service.py`
- optionally `src/tools/policy.py`

Checklist:

- define normal mode base tool behavior
- define red-team mode base file behavior
- separate file capability safety from red-team action risk
- require typed execution for security actions that affect external targets

## 5. Integrate Execution Service

Files:

- `src/app/execution_service.py`
- `src/runtime/foreground_runner.py`
- `src/runtime/execution_events.py`

Checklist:

- call confirmation policy before executing a risk-gated step
- emit `confirmation_required`
- handle approval and denial
- keep execution paused until the adapter provides a decision
- return structured blocked outcomes for denied actions

## 6. Integrate Controller and CLI

Files:

- `src/controller/agent_controller.py`
- `src/controller/contracts.py`
- `src/main.py`
- `src/cli/ui.py`
- optionally `src/cli/adapter.py`

Checklist:

- add confirmation request outputs to controller contracts
- route user approval or denial back to execution
- render risk level, action name, target summary, and reason
- keep wording and rendering outside policy decisions
- avoid model-only risk decisions

## 7. Record Confirmation Audit Events

Files:

- `src/runtime/execution_events.py`
- `src/app/execution_service.py`
- optionally existing operation/session event services during migration

Checklist:

- record confirmation-required events
- record confirmation-approved events
- record confirmation-denied events
- include risk level, action name, target summary, and reason
- ensure denial is retrievable later

## 8. Demote Legacy Low-Level Inputs

Files:

- session creation flow files
- operation creation flow files still exposed by slash commands
- docs and help output

Checklist:

- stop requiring ports/protocols/tool categories/rate limits in the primary session flow
- mark low-level slash-command access as advanced/debug only
- do not document operation-level confirmation fields as the new policy model

## Legacy `task` / `operation` Cleanup Boundary

`task` and `operation` have overlapping top-level container responsibilities, including:

- public identifiers
- title or objective fields
- workspace
- status
- timestamps
- last error tracking

Phase 4 should only do the minimum work needed to keep risk policy and confirmation on the new session path.

Allowed in Phase 4:

- demote operation-level confirmation fields from the primary user flow
- route new confirmation logic through `session` and `ExecutionService`
- reuse `ScopePolicy`, scoped execution, or operation-backed internals temporarily when needed
- add tests that prevent new session confirmation behavior from depending on user-facing operation policy fields

Not allowed in Phase 4:

- making full `TaskService` deletion a Phase 4 exit criterion
- making full `OperationService` deletion a Phase 4 exit criterion
- rewriting all task checkpoint storage as part of risk policy work
- rewriting all operation/job/evidence/finding storage as part of risk policy work
- treating legacy model cleanup as a prerequisite for policy implementation

Merge timing:

- Phase 4 records the overlap but does not perform the physical merge.
- Phase 5 removes operation-id-based skill/module workflow dependencies so modules no longer require `operation` as a top-level container.
- Phase 6 starts the physical merge because the storage split is where task checkpoints, operation jobs, evidence, findings, artifacts, and reports can be re-owned by `session`.
- Phase 7 must not depend on `TaskService` or `OperationService` for the primary record retrieval and report flows.
- The final state should still remove `task` and `operation` as top-level concepts rather than preserving them indefinitely.

## Tool Access Policy by Mode

### Normal Mode

Normal mode may use base tools for ordinary agent work:

- `list_dir`
- `read_file`
- `search`
- `write_file`
- `edit_file`
- `bash`
- `delete_file`

Existing safety behavior still applies:

- sensitive write confirmation
- destructive operation confirmation
- shell danger detection
- runtime capability narrowing from skills

### Red-Team Mode

Red-team mode may also use basic file tools, but with stricter intent boundaries.

Allowed by default:

- read and search workspace/session files
- write session-owned notes, artifacts, findings, and reports when those paths exist
- edit session-owned generated files

Requires confirmation:

- write or edit outside the session-owned output area
- destructive file operations
- shell commands that could affect external targets or bypass typed red-team tools

Not allowed as the default path:

- using `bash` to perform security scanning that should be handled by typed tools
- using file writes to bypass structured artifact and finding storage

## Confirmation Decision Flow

The recommended flow is:

1. Controller derives an action request from user intent or execution plan.
2. Execution service prepares a session-aware execution step.
3. Confirmation policy service classifies the action.
4. Scope validation checks whether the target is allowed.
5. If risk is `safe`, the action runs automatically.
6. If risk is `elevated` or `dangerous`, execution emits a confirmation-required event.
7. The adapter renders the confirmation request.
8. If approved, execution continues and records approval.
9. If denied, execution stops or skips the step and records denial.

Policy and scope checks are complementary:

- risk policy answers whether this kind of action needs confirmation
- scope validation answers whether this target is allowed

## Migration Sequence

Work should be performed in this order:

1. Freeze the risk vocabulary and config path.
2. Add risk policy models.
3. Add built-in defaults and config loading.
4. Add the confirmation policy service.
5. Add the tool access policy service.
6. Integrate the execution service confirmation gate.
7. Integrate controller and CLI confirmation flow.
8. Record confirmation audit events.
9. Demote legacy operation policy inputs from the primary session flow.
10. Record remaining `task` / `operation` overlap as Phase 6 merge work, without making it a Phase 4 blocker.

## Testing Checklist

Recommended new test files:

- `tests/test_risk_policy.py`
- `tests/test_confirmation_policy_service.py`
- `tests/test_tool_access_policy_service.py`
- optionally `tests/test_execution_confirmation_policy.py`

Required test areas:

- default action risk mapping
- unknown action fallback
- missing config uses defaults
- invalid config fails closed
- safe action auto-allow decision
- elevated action confirmation-required decision
- dangerous action confirmation-required decision
- normal mode base file tool access
- red-team mode path and capability restrictions
- execution service pauses for elevated actions
- execution service blocks denied actions
- approval resumes execution
- confirmation audit events are emitted
- scope-denied target remains denied even if action risk is `safe`

## Phase 4 Exit Review

Phase 4 is complete only if all questions below can be answered with "yes".

1. Can a low-risk scoped red-team action auto-run from a session?
2. Does a large scan pause for confirmation?
3. Does POC execution pause for confirmation?
4. Is the policy loaded from built-in defaults or `.red-code/config/risk-policy.json`?
5. Does invalid policy config fail closed?
6. Are confirmation-required, approved, and denied events recorded?
7. Does the CLI render confirmation without owning policy logic?
8. Can both normal and red-team agents use base file tools under explicit mode policy?
9. Is security execution still routed through typed tools and scope validation?
10. Are low-level operation policy fields demoted from the main user flow?
11. Is full `task` / `operation` physical cleanup explicitly deferred beyond Phase 4?

## Recommended Deliverable Set

The minimum acceptable deliverables for Phase 4 are:

- `src/models/risk_policy.py`
- `src/app/confirmation_policy_service.py`
- `src/app/tool_access_policy_service.py`
- settings additions for `.red-code/config/risk-policy.json`
- execution-service confirmation gate
- controller confirmation output contracts
- CLI confirmation rendering integration
- tests for risk mapping, config loading, confirmation handling, and tool access policy
- updated docs showing risk-based confirmation as the default policy model

If any of these are missing, Phase 4 is not yet complete as an architecture step.
