---
name: surface-recon
description: Legacy prompt bridge for the Phase 5 surface-recon module. Use the capability manifest and /module commands for deterministic DNS, HTTP, and TLS discovery.
license: Proprietary
compatibility: Agent Skills baseline with Claude-compatible extensions
allowed-tools:
  - bash
  - list_dir
  - read_file
metadata:
  category: security
  risk_level: medium
  mode: workflow
user-invocable: true
disable-model-invocation: true
workflow-profile: surface-recon
---

# Surface Recon

This is the legacy prompt bridge for the Phase 5 `surface-recon` module.
The target runtime contract lives in
`src/capabilities/surface-recon/capability.json`.

## Goals

- Turn a hostname or URL into deterministic reconnaissance steps.
- Keep scope control in runtime code rather than prompt instructions.
- Execute through the Phase 5 module runtime and the Phase 4 scope/risk gate.

## Workflow

1. Use `/module run surface-recon <target> [json_overrides]` for advanced/debug runs.
2. Use an active redteam session for persistent context, or run one-shot without creating a persistent session.
3. Provide optional JSON overrides such as `{"include_dns": false}` when needed.

Legacy operation-bound `/skill plan surface-recon <operation_id>` and
`/skill apply surface-recon <operation_id>` flows are retained only for
migration/debug references. They are not the Phase 5 target module flow.

## Outputs

- `dns_lookup` for hostnames when enabled
- derived `http_probe` jobs
- an optional `tls_inspect` job

## Safety

- This legacy skill is not the target module runtime.
- Scope, protocol, port, and confirmation enforcement stay in the Phase 4 execution gate.
