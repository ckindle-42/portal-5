---
id: unit-compliance-fallback-policy-compliance-fallback-policy
kind: what
title: "COMPLIANCE_FALLBACK_POLICY \u2014 Compliance Fallback Policy"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: config/backends.yaml
- type: code
  path: portal/modules/eval/persona_matrix/_common.py
- type: code
  path: portal/modules/compliance/config/__init__.py
last_generated_commit: 1896bb7da29dd96ff280b8ffb495519d507070ee
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5634382
updated_at: 1784946220.5634382
---

The compliance fallback policy governs which models may serve requests behind the `auto-compliance` workspace and what happens when a fallback falls below expectations. Its operational shape is fixed by three config surfaces. `config/portal.yaml` declares the workspace: `module: compliance`, `model_hint: granite4.1:8b-ctx16k`, the temperature and context knobs, the tool list, and the owui system prompt. `config/backends.yaml` declares the routing chain in `workspace_routing` (`auto-compliance` routes through the reasoning group and then the general group) and lists the model pools those groups draw from. The registry entry in `WORKSPACE_REGISTRY` binds the workspace to its assertion library `tests.lib.compliance_assertions`, its fixture loader `tests.lib.compliance_fixtures`, and its per-workspace `threshold_doc`. The compliance module surface (`portal.modules.compliance.config`) exposes exactly one workspace id, `auto-compliance`, via `COMPLIANCE_WORKSPACE_IDS`.

## Why

The source document's status and last-reviewed lines were hand-edited stamps that no tooling writes, which is exactly the kind of unverifiable claim re-grounding removes. The policy itself is real, but its truth lives in the files the router and the sweep actually read: the workspace entry, the routing chain, and the registry binding are each machine-checkable, so this unit can be verified against HEAD instead of trusted from a dated stamp.
