---
name: web-enum
description: Generate a bounded web enumeration job plan for a hostname or URL using the v2 security runtime. Use when you want deterministic HTTP path probes and optional TLS inspection inside an operation scope.
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
shell: powershell
workflow-profile: web-enum
---

# Web Enum

Work as a bounded red-team workflow skill.

## Goals

- Turn a hostname or URL into a deterministic web enumeration plan.
- Keep the workflow declarative at the skill layer and enforced in runtime code.
- Preview the generated jobs before creating them.

## Workflow

1. Use `/skill plan web-enum <operation_id>` to preview the generated jobs.
2. Use `/skill apply web-enum <operation_id>` to create the approved jobs.
3. Provide a primary target and optional JSON overrides when prompted.

## Outputs

- `http_probe` for the base URL
- `http_probe` for `robots.txt`
- `http_probe` for `/.well-known/security.txt`
- an optional `tls_inspect` job for HTTPS targets

## Safety

- This skill is workflow-only and does not support freeform model invocation.
- Scope, protocol, port, and confirmation enforcement stay in the v2 runtime.
