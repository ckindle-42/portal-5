---
id: unit-compliance-fallback-policy-out-of-scope
kind: what
title: "COMPLIANCE_FALLBACK_POLICY \u2014 Out of scope"
sources:
- type: code
  path: portal/modules/eval/persona_matrix/_common.py
- type: code
  path: portal/modules/compliance/config/__init__.py
- type: code
  path: portal/modules/eval/persona_matrix/cli.py
- type: code
  path: config/portal.yaml
last_generated_commit: fb9979b75eb4d70f331e849b80fc7326e8e61847
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.566437
updated_at: 1784946220.566437
---

The compliance fallback policy is scoped to `auto-compliance` only, and the mechanical boundary is the registry. In `WORKSPACE_REGISTRY`, `auto-compliance` is the single entry bound to `tests.lib.compliance_assertions` and `tests.lib.compliance_fixtures`; `auto-coding` binds to its own assertion and fixture modules, and the bench workspaces bind to a shootout harness. On the config side, `portal.modules.compliance.config` exposes exactly one id, `auto-compliance`, through `COMPLIANCE_WORKSPACE_IDS`, and `config/portal.yaml` maps the compliance module to that one workspace. The driver itself is workspace-parameterizable — `--workspace` accepts any registry key — but the fixture YAML, assertion library and threshold document are per-workspace, so extending the policy to `auto-coding`, `auto-research`, `auto-data` or `auto-security` means authoring those inputs, not changing the driver.

## Why

"Out of scope" is an architectural property, not a preference: the registry couples each workspace to its own assertion and fixture modules, so a compliance policy written for one chain cannot silently govern another. Stating which surfaces would need to be authored — fixtures, assertions, threshold document — converts the source document's future-work note into a concrete extension path grounded in the registry structure and the module's workspace list.
