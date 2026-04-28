---
name: web-enum
description: Legacy prompt bridge for the Phase 5 web-enum module. Use the capability manifest and /module commands for deterministic HTTP path probes and optional TLS inspection.
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
workflow-profile: web-enum
---

# Web Enum

This is the legacy prompt bridge for the Phase 5 `web-enum` module.
The target runtime contract lives in
`src/capabilities/web-enum/capability.json`.

## Goals

- Turn a hostname or URL into a deterministic web enumeration plan.
- Keep the workflow declarative at the skill layer and enforced in runtime code.
- Execute through the Phase 5 module runtime and the Phase 4 scope/risk gate.

## Workflow

1. Use `/module run web-enum <target> [json_overrides]` for advanced/debug runs.
2. Use an active redteam session for persistent context, or run one-shot without creating a persistent session.
3. Provide optional JSON overrides such as `{"paths": ["/robots.txt"]}` when needed.

Legacy operation-bound `/skill plan web-enum <operation_id>` and
`/skill apply web-enum <operation_id>` flows are retained only for
migration/debug references. They are not the Phase 5 target module flow.

## Outputs

- `http_probe` for the base URL
- `http_probe` for `robots.txt`
- `http_probe` for `/.well-known/security.txt`
- an optional `tls_inspect` job for HTTPS targets

## Safety

- This legacy skill is not the target module runtime.
- Scope, protocol, port, and confirmation enforcement stay in the Phase 4 execution gate.
