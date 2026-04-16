# Phase 5 Finalization: Skill and Module Unification

## Purpose

This document closes the design loop for **Phase 5: Skill and Module Unification**.

It converts the Phase 5 planning guidance into a fixed implementation baseline. After this document, Phase 5 should be treated as **implementation-ready** unless product goals change.

This document freezes:

- the target capability contract
- the `skill` / `module` vocabulary split
- the decision not to continue the current `SKILL.md` workflow model as the target design
- the canonical manifest direction
- the module execution boundary
- the relationship to Phase 4 risk policy
- the removal of operation-id-based module invocation before Phase 6
- the rejection of unnecessary extension-system designs

It should be read together with:

- [SPEC](D:\Project\Python\Agent\docs\SPEC.md)
- [Session Target Architecture](D:\Project\Python\Agent\docs\architecture\session-target-architecture.md)
- [Session Refactor Development Plan](D:\Project\Python\Agent\docs\development\session-refactor-development-plan.en.md)
- [Phase 4 Finalization](D:\Project\Python\Agent\docs\development\session-phase-4-finalization.en.md)
- [Phase 5 Implementation Checklist](D:\Project\Python\Agent\docs\development\session-phase-5-implementation-checklist.en.md)
- [Current Skill System Standard](D:\Project\Python\Agent\docs\architecture\skill-system-standard.md)

## Phase 5 Status

Phase 5 is now **architecturally converged**.

This means:

- the target skill/module contract is settled
- the manifest direction is settled
- the module execution boundary is settled
- current operation-id workflow skills are rewrite targets
- coding can begin without reopening the extension model

## Replacement Position of Phase 5

Phase 5 is the point where the current `SKILL.md` workflow model is replaced in **capability architecture terms**.

After Phase 5:

- modules no longer require `operation_id`
- red-team modules are session-aware
- module execution goes through `ExecutionService`
- risk metadata is routed through the Phase 4 confirmation policy
- current `/skill plan <name> <operation_id>` and `/skill apply <name> <operation_id>` flows are no longer target UX paths

Phase 5 does not own the full physical merge of `task` and `operation`; Phase 6 starts that work after operation-id-based module dependencies are removed.

## Final Decisions

## 1. Shared Capability Contract

Final decision:

- Phase 5 introduces one shared capability contract for both skills and modules

User-facing labels:

- `skill`
- `module`

Runtime goal:

- do not maintain two unrelated extension systems

Not allowed:

- building a separate red-team module registry that cannot share discovery, validation, risk, and execution metadata with general skills

## 2. Current `SKILL.md` Is Not the Target Contract

Final decision:

- current `SKILL.md` is implementation history and migration input, not the Phase 5 target contract

Reusable:

- local description files
- `allowed-tools` narrowing
- `references/` and `scripts/` directories
- prompt body for prompt-assist skills

Not reusable as target:

- slash-command-first activation
- task-bound skill profiles
- operation-id-based workflow skills
- prompt-body-only red-team module semantics
- `/skill plan <name> <operation_id>`
- `/skill apply <name> <operation_id>`

## 3. Canonical Manifest File

Final decision:

- the target structured manifest file is `capability.json`

Recommended locations:

- `src/capabilities/<name>/capability.json`
- `.red-code/capabilities/<name>/capability.json`

Reason:

- red-team modules need nested structured metadata for parameters, risk, tools, execution style, and session support
- the current `SKILL.md` frontmatter parser is not a good target for this shape
- JSON can be validated with the standard library without adding parser dependencies

Existing `SKILL.md` files may remain during migration, but new target module semantics should not be added to `SKILL.md` frontmatter.

## 4. Capability Kinds

Final decision:

- Phase 5 supports exactly two capability kinds

Kinds:

- `skill`
- `module`

Meaning:

- `skill` is a general-purpose agent capability, usually prompt-assist oriented.
- `module` is a red-team capability that can run one-shot or inside a red-team session.

Do not add a third public capability kind in Phase 5.

## 5. Execution Styles

Final decision:

- Phase 5 supports three execution styles

Execution styles:

- `prompt_assist`
- `typed_tool`
- `workflow`

Meaning:

- `prompt_assist` injects assistant guidance and may narrow visible tools.
- `typed_tool` maps to one typed security tool or safe built-in tool.
- `workflow` maps to deterministic multi-step execution through `ExecutionService`.

Not allowed:

- arbitrary script execution as the default red-team module path
- shell-first module execution
- model-generated shell commands as a substitute for typed tools

## 6. Manifest Fields

Final decision:

The minimum target manifest fields are:

- `version`
- `name`
- `kind`
- `display_name`
- `description`
- `modes`
- `parameters`
- `tools`
- `risk`
- `execution`
- `session`

Required behaviors:

- `kind` must be `skill` or `module`
- `modes` must constrain where the capability may run
- `parameters` must be validated before execution
- `risk` must use the Phase 4 risk vocabulary
- `execution` must map to a supported execution style
- `session` must declare one-shot and persistent-session support

## 7. Risk Policy Integration

Final decision:

- module manifest risk metadata is an input to Phase 4 confirmation policy, not the final authority

Meaning:

- manifest risk metadata identifies action hints and default risk
- `ConfirmationPolicyService` remains the final risk decision authority
- manifest risk cannot override policy config
- manifest risk cannot override scope denial

Not allowed:

- letting a module mark itself safe and bypass confirmation policy
- expressing risk only in prompt body text

## 8. Execution Service Boundary

Final decision:

- red-team module execution routes through `ExecutionService`

Module execution may:

- prepare a one-shot invocation
- attach to a persistent red-team session
- emit foreground progress
- request confirmation through the Phase 4 policy path

Module execution may not:

- call raw worker or scheduler primitives as the product-facing path
- require `operation_id`
- run shell commands as the default security execution path

## 9. Session Integration

Final decision:

- modules must be session-aware but may also support one-shot execution

Required metadata:

- `supports_one_shot`
- `supports_persistent`
- `result_layers`

Rules:

- a module that supports persistent execution must accept a session context
- a module that supports one-shot execution must not require persistent session storage
- a module must declare where results should eventually land, even if the final storage split happens in Phase 6

## 10. Operation-ID Dependency Removal

Final decision:

- Phase 5 must remove operation-id-based module invocation as a target dependency

Affected old flows:

- `/skill plan <name> <operation_id>`
- `/skill apply <name> <operation_id>`

New target:

- module invocation is expressed through controller/session/module requests

This is a prerequisite for Phase 6 because Phase 6 starts the physical merge of `task` / `operation` ownership into `session`.

## 11. Capability Service Boundary

Final decision:

- shared capability behavior lives in an application-layer service

Recommended location:

- `src/app/capability_service.py`

Responsibilities:

- list capabilities
- list skills
- list modules
- require capability by name
- validate parameters
- prepare prompt-assist runtime config
- prepare module invocation metadata

## 12. Module Service Boundary

Final decision:

- red-team module-specific behavior lives behind a module service facade

Recommended location:

- `src/app/module_service.py`

Responsibilities:

- require `kind == module`
- validate mode compatibility
- validate one-shot vs persistent support
- build execution requests
- attach risk action IDs
- avoid `operation_id`

## 13. Existing Built-In Migration

Final decision:

Existing built-ins are migration inputs and should be classified as follows:

| Current Built-In | Target Kind | Target Execution Style |
| --- | --- | --- |
| `development-default` | `skill` | `prompt_assist` |
| `git-auto-commit` | `skill` | `prompt_assist` |
| `security-audit` | `skill` | `prompt_assist` |
| `weather-query-example` | `skill` | `prompt_assist` |
| `surface-recon` | `module` | `workflow` |
| `web-enum` | `module` | `workflow` |

Required migration:

- `surface-recon` and `web-enum` must stop requiring `operation_id`
- workflow profile names may be reused as execution profiles
- prompt bodies may remain as human-readable guidance, but structured module semantics must move to `capability.json`

## 14. Legacy Skill Service Boundary

Final decision:

- current `SkillService` may remain during migration, but it is not the target module runtime

Allowed:

- keep existing prompt-assist skills working
- keep legacy tests while new capability tests are added
- bridge current `SkillService` into `CapabilityService` where useful

Not allowed:

- adding new red-team module semantics to current `SKILL.md` frontmatter as the long-term solution
- making task-bound skill profiles part of the new module contract
- making slash commands the primary module invocation path

## 15. Rejected Designs

The following designs are explicitly rejected and should be discarded.

### Rejected: Extend Current `SKILL.md` Frontmatter Forever

Reason:

- target modules need nested structured metadata that current frontmatter parsing does not support cleanly

### Rejected: Separate Skill and Module Runtime Systems

Reason:

- the target product needs one capability model with two user-facing labels

### Rejected: Operation-ID-Based Module Invocation

Reason:

- it preserves the old `operation` top-level model and blocks Phase 6 merge work

### Rejected: Prompt-Only Module Semantics

Reason:

- parameters, risk, execution style, and result ownership must be machine-readable

### Rejected: Shell-First Module Runtime

Reason:

- red-team execution must go through typed tools, risk policy, scope validation, and execution services

### Rejected: Phase 5 as Storage Merge

Reason:

- Phase 5 removes module dependencies on `operation`; Phase 6 owns physical storage ownership changes

## Final Module Plan for Phase 5

New Phase 5 modules:

- `src/models/capability.py`
- `src/capabilities/loader.py`
- `src/capabilities/registry.py`
- `src/app/capability_service.py`
- `src/app/module_service.py`

Expected touched files:

- `src/app/skill_service.py`
- `src/controller/agent_controller.py`
- `src/controller/contracts.py`
- `src/main.py`
- optionally `src/cli/ui.py`
- current skill command handlers
- built-in capability folders under `src/capabilities/`
- relevant docs under `docs/`

Internal modules to integrate:

- `src/app/execution_service.py`
- `src/app/confirmation_policy_service.py`
- `src/app/tool_access_policy_service.py`
- `src/tools/policy.py`
- `src/tools/security/`

## Final Implementation Order

Phase 5 coding order is fixed as:

1. implement capability models
2. implement capability loader
3. implement capability registry
4. implement capability service
5. implement module service
6. integrate module invocation with `ExecutionService`
7. integrate risk metadata with the Phase 4 confirmation policy path
8. bridge current `SkillService` as legacy/compatibility only
9. migrate built-in skill/module manifests
10. demote operation-id-based `/skill plan` and `/skill apply`

Do not invert this order unless a concrete implementation blocker is discovered.

## Final Testing Plan for Phase 5

Recommended new test files:

- `tests/test_capability_manifest.py`
- `tests/test_capability_loader.py`
- `tests/test_capability_registry.py`
- `tests/test_capability_service.py`
- `tests/test_module_service.py`
- optionally `tests/test_skill_module_migration.py`

Required test areas:

### Manifest Loading

- valid `capability.json` loads
- invalid enum values fail
- invalid parameter schemas fail
- local overrides built-in capability with the same name

### Capability Classification

- skills and modules are listed separately
- mode filtering works
- prompt-assist skills do not require module execution metadata
- modules require execution and session metadata

### Module Invocation

- one-shot module invocation works without `operation_id`
- persistent red-team session module invocation works with session context
- module invocation produces execution requests
- operation-id-based invocation is not the primary path

### Risk Integration

- manifest risk metadata is propagated
- Phase 4 confirmation policy remains the final authority
- module risk cannot override scope denial

### Migration

- existing built-ins are classified into target kinds
- `surface-recon` and `web-enum` become module rewrite targets
- current `SKILL.md` files are not required for target module loading

## Final Legacy Boundary

Allowed during migration:

- existing `SkillService`
- existing `SKILL.md` prompt-assist skills
- current skill tests while new capability tests are added
- advanced/debug slash commands that inspect legacy skills

Not allowed:

- treating current `SKILL.md` workflow semantics as the Phase 5 target contract
- keeping operation-id-based module invocation as target UX
- making Phase 6 storage merge depend on operation-id-based modules
- using prompt body as the only source of module parameters, risk, or execution semantics

## Phase 5 Ready-to-Implement Checklist

Phase 5 is now considered fully converged if the team accepts the following locked decisions:

- target manifest is `capability.json`
- capability kinds are exactly `skill` and `module`
- execution styles are `prompt_assist`, `typed_tool`, and `workflow`
- current `SKILL.md` workflow design is not the target architecture
- current `SKILL.md` files may remain only as migration inputs or prompt-assist skill support
- module invocation does not require `operation_id`
- module execution routes through `ExecutionService`
- module risk metadata flows through Phase 4 confirmation policy
- `surface-recon` and `web-enum` are rewrite targets, not target examples as-is
- Phase 6 is unblocked to start `task` / `operation` physical merge

This checklist is now the Phase 5 baseline.
