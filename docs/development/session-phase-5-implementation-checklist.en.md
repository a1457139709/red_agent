# RETIRED DOCUMENT

# Phase 5 Implementation Checklist: Skill and Module Unification

## Purpose

This document breaks down **Phase 5: Skill and Module Unification** into implementation-ready engineering tasks.

It should be read together with:

- [SPEC](D:\Project\Python\Agent\docs\SPEC.md)
- [Session Target Architecture](D:\Project\Python\Agent\docs\architecture\session-target-architecture.md)
- [Session Refactor Development Plan](D:\Project\Python\Agent\docs\development\session-refactor-development-plan.en.md)
- [Phase 4 Finalization](D:\Project\Python\Agent\docs\development\session-phase-4-finalization.en.md)
- [Current Skill System Standard](D:\Project\Python\Agent\docs\architecture\skill-system-standard.md)

This checklist assumes Phase 1 through Phase 4 have already established:

- `session` as the target top-level work unit
- the Agent Controller boundary
- foreground-first execution
- risk-based confirmation policy

## Phase Goal

Provide one extensible capability system that supports both:

- general-purpose `skills`
- red-team `modules`

The user may still see two words:

- `skill` for general agent assistance
- `module` for red-team capabilities

But the runtime should not need two unrelated extension systems.

## Scope

Phase 5 covers:

- a shared capability manifest contract
- the user-facing skill/module vocabulary split
- module parameter schema
- risk metadata propagation into the Phase 4 confirmation policy
- execution style metadata
- session-aware module invocation
- one-shot module invocation
- migration planning for current `SKILL.md` files
- removal of operation-id-based module invocation from the target flow

Phase 5 does not require:

- final `memory/` / `artifacts/` / `findings/` / `reports/` storage split
- full physical `task` / `operation` merge
- Web UI implementation
- distributed module execution
- arbitrary third-party script execution as a default module path

## Non-Goals

Do not do the following in Phase 5:

- continue the current `SKILL.md` workflow model as the target design
- keep `/skill plan <name> <operation_id>` as the primary module flow
- keep `/skill apply <name> <operation_id>` as the primary module flow
- make red-team modules depend on `operation_id`
- encode module risk and execution semantics only in prompt body text
- bypass `ExecutionService` for red-team module execution
- bypass Phase 4 risk policy for module actions
- perform the full Phase 6 storage ownership migration

## Rewrite Policy

### REWRITE REQUIRED

The current `SKILL.md` system does **not** match the target architecture as-is.

Current design traits:

- prompt-body injection
- `allowed-tools` tool visibility narrowing
- explicit `/skill` activation
- task-bound skill profiles
- operation-id-based workflow skills
- workflow semantics stored in loosely structured frontmatter and prompt text

Target design:

- one structured capability contract
- two user-facing labels: `skill` and `module`
- parameter schema
- risk metadata
- execution style
- session integration
- execution-service routing
- adapter-neutral invocation contracts

Reusable from current design:

- local capability description files
- `allowed-tools` as a tool visibility narrowing mechanism
- `references/` and `scripts/` directory conventions
- prompt body as optional assistant guidance for prompt-assist skills

Not reusable as target design:

- slash-command-first skill activation
- task-bound skill profiles
- operation-id-based workflow skills
- prompt-body-only red-team module semantics
- direct `/skill plan` and `/skill apply` as the primary module lifecycle

## Target Outcomes

By the end of Phase 5:

1. A shared capability manifest model exists.
2. Capabilities can be rendered as user-facing `skills` or `modules`.
3. Red-team modules can declare parameters, risk metadata, execution style, and session support.
4. Module invocation no longer requires `operation_id`.
5. Module execution routes through `ExecutionService`.
6. Module risk metadata is checked through the Phase 4 confirmation policy.
7. Existing built-in skills are classified as migrate, rewrite, or retire.
8. Phase 6 can start `task` / `operation` physical merge without being blocked by operation-id-based modules.

## Target Manifest Direction

Phase 5 should introduce a new structured manifest as the target contract.

Recommended canonical file:

- `capability.json`

Recommended locations:

- `src/capabilities/<name>/capability.json`
- `.red-code/capabilities/<name>/capability.json`

Existing `SKILL.md` files may remain during migration, but they are not the target contract.

Minimum manifest shape:

```json
{
  "version": 1,
  "name": "surface-recon",
  "kind": "module",
  "display_name": "Surface Recon",
  "description": "Run bounded DNS, HTTP, and TLS reconnaissance for an in-scope target.",
  "modes": ["redteam"],
  "parameters": [
    {
      "name": "target",
      "type": "string",
      "required": true,
      "description": "Domain, host, IP, or URL to inspect."
    }
  ],
  "tools": {
    "allowed": ["dns_lookup", "http_probe", "tls_inspect"]
  },
  "risk": {
    "default": "safe",
    "actions": ["dns_lookup", "http_probe", "tls_inspect"]
  },
  "execution": {
    "style": "workflow",
    "profile": "surface_recon"
  },
  "session": {
    "supports_one_shot": true,
    "supports_persistent": true,
    "result_layers": ["artifacts"]
  }
}
```

This JSON shape is intentionally structured because the current frontmatter parser does not support nested schemas well enough for the target module contract.

## Capability Kinds

Phase 5 should support exactly these target kinds:

- `skill`
- `module`

Meaning:

- `skill` is a general-purpose agent capability, usually prompt-assist oriented.
- `module` is a red-team capability that can run one-shot or inside a red-team session.

Do not create a third public label in Phase 5 unless the product direction changes.

## Execution Styles

Phase 5 should support these execution styles:

- `prompt_assist`
- `typed_tool`
- `workflow`

Meaning:

- `prompt_assist` injects assistant guidance and may narrow visible tools.
- `typed_tool` maps to one typed security tool or safe built-in tool.
- `workflow` maps to deterministic multi-step execution through `ExecutionService`.

Not target for Phase 5:

- arbitrary script execution as the default red-team module path
- shell-first module execution
- model-generated shell commands as a substitute for typed tools

## Module Strategy

## Modules to Introduce

### `src/models/capability.py`

Responsibilities:

- define capability kind
- define execution style
- define parameter schema
- define tool visibility metadata
- define risk metadata
- define session support metadata
- define loaded capability model

Completion check:

- tests can validate a module manifest without importing CLI code

### `src/capabilities/loader.py`

Responsibilities:

- load `capability.json`
- validate required fields
- validate enum values
- preserve `references/` and `scripts/` paths as metadata
- reject unsupported nested or malformed data with clear errors

Completion check:

- valid capability manifests load deterministically and invalid manifests fail fast

### `src/capabilities/registry.py`

Responsibilities:

- discover built-in capabilities
- discover local capabilities
- apply local-over-built-in precedence
- list capabilities by kind and mode
- avoid requiring `SKILL.md` for target capabilities

Completion check:

- capability discovery works for both `skill` and `module`

### `src/app/capability_service.py`

Responsibilities:

- expose capability lookup
- expose skill/module filtered lists
- validate capability parameters
- build prompt-assist runtime configs for `skill`
- prepare module invocation requests for `ExecutionService`

Completion check:

- higher-level code can work with skills and modules through one service

### `src/app/module_service.py`

Responsibilities:

- provide red-team module-specific facade over `CapabilityService`
- validate module session compatibility
- validate one-shot vs persistent invocation
- translate module invocation into execution requests
- attach risk action metadata for confirmation policy

Completion check:

- red-team modules can be invoked without `operation_id`

## Existing Modules to Rewrite or Integrate

### REWRITE REQUIRED: Current Skill Manifest Model

Affected files:

- `src/models/skill.py`
- `src/skills/loader.py`
- `src/skills/registry.py`
- `src/app/skill_service.py`

Action:

- keep current skill runtime only as a migration path
- introduce the new capability manifest model
- avoid extending current `SKILL.md` frontmatter as the long-term module contract

### REWRITE REQUIRED: Workflow Skills

Affected built-ins:

- `src/skills/surface-recon/SKILL.md`
- `src/skills/web-enum/SKILL.md`

Action:

- migrate to `kind: module`
- remove `operation_id` from user-facing invocation
- use parameter schema for `target` and options
- route through `ModuleService` and `ExecutionService`

### INTEGRATE: Risk Policy

Affected files:

- `src/app/confirmation_policy_service.py`
- `src/app/module_service.py`
- `src/models/capability.py`

Action:

- module manifest risk metadata should provide action hints
- Phase 4 confirmation policy remains the final risk decision authority
- module manifest risk must not override scope denial

### INTEGRATE: Controller

Affected files:

- `src/controller/agent_controller.py`
- `src/controller/contracts.py`

Action:

- add module invocation request handling
- route natural language module requests through controller
- keep slash commands as advanced/debug access only

## File-Level Checklist

## 1. Add Capability Models

Files:

- `src/models/capability.py`

Checklist:

- define `CapabilityKind`
- define `CapabilityExecutionStyle`
- define `CapabilityParameter`
- define `CapabilityToolPolicy`
- define `CapabilityRiskMetadata`
- define `CapabilitySessionSupport`
- define `CapabilityManifest`
- define `LoadedCapability`

## 2. Add Capability Loader

Files:

- `src/capabilities/loader.py`
- `src/capabilities/__init__.py`

Checklist:

- read `capability.json`
- validate `version`
- validate `name`, `kind`, `description`, `modes`
- validate parameter schema
- validate execution style
- validate risk level values against Phase 4 risk vocabulary
- expose clear load errors

## 3. Add Capability Registry

Files:

- `src/capabilities/registry.py`

Checklist:

- discover built-in capabilities
- discover local `.red-code/capabilities`
- apply local override precedence
- filter by `kind`
- filter by mode
- support reload

## 4. Add Capability Service

Files:

- `src/app/capability_service.py`

Checklist:

- list capabilities
- list skills
- list modules
- require capability by name
- validate parameters
- prepare prompt-assist config
- prepare module invocation metadata

## 5. Add Module Service

Files:

- `src/app/module_service.py`

Checklist:

- require `kind == module`
- validate mode compatibility
- validate one-shot vs persistent session compatibility
- build execution request
- attach action IDs for risk policy
- avoid `operation_id`

## 6. Bridge Existing Skill Service

Files:

- `src/app/skill_service.py`
- optionally `src/models/skill.py`

Checklist:

- keep current `SkillService` working where still needed
- mark it as legacy or compatibility during Phase 5
- do not add new red-team module semantics to current `SKILL.md`
- route new module behavior through `CapabilityService` / `ModuleService`

## 7. Migrate Built-In Capabilities

Files:

- new files under `src/capabilities/`
- existing `src/skills/*/SKILL.md` migration notes

Checklist:

- migrate `development-default` as `kind: skill`, `execution.style: prompt_assist`
- migrate `git-auto-commit` as `kind: skill`, `execution.style: prompt_assist`
- migrate `security-audit` as `kind: skill`, `execution.style: prompt_assist`
- migrate `weather-query-example` as `kind: skill`, `execution.style: prompt_assist`
- migrate `surface-recon` as `kind: module`, `execution.style: workflow`
- migrate `web-enum` as `kind: module`, `execution.style: workflow`

## 8. Integrate Controller and CLI

Files:

- `src/controller/agent_controller.py`
- `src/controller/contracts.py`
- `src/main.py`
- optionally `src/cli/ui.py`

Checklist:

- add module invocation outputs
- add skill/module listing outputs
- keep slash command listing as advanced/debug
- keep natural language as the primary entry
- avoid operation-id-based module prompts

## 9. Demote Operation-ID Workflow Commands

Files:

- current skill command handlers
- docs and help output

Checklist:

- stop documenting `/skill plan <name> <operation_id>` as a target flow
- stop documenting `/skill apply <name> <operation_id>` as a target flow
- keep any old commands as legacy/debug only if needed temporarily
- ensure Phase 6 can start storage merge without module flows depending on operation IDs

## Migration Sequence

Work should be performed in this order:

1. Freeze the target capability manifest shape.
2. Add capability models.
3. Add capability loader and registry.
4. Add capability service.
5. Add module service.
6. Wire module invocation to `ExecutionService`.
7. Integrate Phase 4 risk policy metadata.
8. Bridge current `SkillService` as legacy/compatibility only.
9. Migrate built-in skills/modules into capability manifests.
10. Demote operation-id-based `/skill plan` and `/skill apply`.

## Testing Checklist

Recommended new test files:

- `tests/test_capability_manifest.py`
- `tests/test_capability_loader.py`
- `tests/test_capability_registry.py`
- `tests/test_capability_service.py`
- `tests/test_module_service.py`
- optionally `tests/test_skill_module_migration.py`

Required test areas:

- valid capability manifest loading
- invalid capability manifest failure paths
- local override precedence
- listing by `skill` vs `module`
- listing by mode
- parameter validation
- risk metadata propagation
- module invocation without `operation_id`
- module invocation inside a persistent red-team session
- one-shot module invocation
- legacy `SKILL.md` is not required for target modules
- operation-id-based workflow commands are not the primary path

## Phase 5 Exit Review

Phase 5 is complete only if all questions below can be answered with "yes".

1. Is there a shared capability manifest contract?
2. Can capabilities be listed as either `skill` or `module`?
3. Can red-team modules declare parameters, risk metadata, and execution style?
4. Can a module be invoked without `operation_id`?
5. Does module execution route through `ExecutionService`?
6. Does module risk metadata flow through the Phase 4 confirmation policy?
7. Are current operation-id workflow skills classified as rewrite targets?
8. Are slash-command skill workflows demoted from the target module UX?
9. Is Phase 6 unblocked from starting the `task` / `operation` physical merge?

## Recommended Deliverable Set

The minimum acceptable deliverables for Phase 5 are:

- `src/models/capability.py`
- `src/capabilities/loader.py`
- `src/capabilities/registry.py`
- `src/app/capability_service.py`
- `src/app/module_service.py`
- capability manifests for built-in skills and modules
- controller integration for module invocation
- risk metadata integration with Phase 4 policy
- migration notes for current `SKILL.md` files
- docs marking operation-id-based skill workflows as legacy/debug only

If any of these are missing, Phase 5 is not yet complete as an architecture step.
