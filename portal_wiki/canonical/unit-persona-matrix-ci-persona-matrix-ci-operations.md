---
id: unit-persona-matrix-ci-persona-matrix-ci-operations
kind: what
title: "PERSONA_MATRIX_CI \u2014 Persona Matrix CI Operations"
sources:
- type: code
  path: portal/modules/eval/persona_matrix/_common.py
- type: code
  path: .github/workflows/persona_matrix_nightly.yml
last_generated_commit: 9623f6b25b3e922bd0cf4b3885a926a4728b26a1
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.567051
updated_at: 1784946220.567051
---

This unit is the operations surface of the persona-matrix CI: how a sweep is configured, triggered, and consumed by an operator. Configuration is registry-driven — `WORKSPACE_REGISTRY` in `_common.py` maps each sweepable workspace to its assertion module, fixture module, persona categories, and an optional `threshold_doc`. The `auto-compliance` entry binds to `tests.lib.compliance_assertions`, `tests.lib.compliance_fixtures`, the compliance category, and `docs/COMPLIANCE_FALLBACK_POLICY.md`; `auto-coding` binds to the coding assertion and fixture libraries and carries no `threshold_doc` (the coding fallback-policy doc it once named does not exist, so the dead reference was dropped). The workflow supports three operator flows: baseline creation (run locally, inspect, commit the workspace-scoped JSON), manual dispatch (pick a workspace and the `ollama` backend from the workflow inputs), and artifact retrieval (the `persona_matrix-*` upload with 30-day retention).

CI differs from the fallback-policy docs in an important way: the workflow is policy-free. It only compares a fresh run against the committed baseline through `--baseline-compare`; deciding what behavior is acceptable is delegated to the `threshold_doc` files the registry references, which the gate never reads. Operations are therefore split between the mechanical diff and the human-owned acceptability policy.

## Why

The original unit was pure cross-reference — it described a doc's relationship to another doc, which cannot be verified once the generated source is gone. What is real and checkable is the registry binding that names the compliance fallback policy as a workspace's threshold reference and the workflow triggers that define how an operator drives a run. Rewriting the unit around those concrete surfaces keeps it useful as an operations map instead of a memory of a file.
