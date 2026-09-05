---
id: unit-known-limitations-compliance-engine-had-no-route
kind: what
title: "KNOWN_LIMITATIONS — an engine with no route is an engine that does not exist"
sources:
- type: code
  path: portal/modules/compliance/tools/compliance_mcp.py
- type: code
  path: portal/modules/compliance/tools/compliance_retrieval.py
- type: code
  path: config/portal.yaml
claims:
- probe: compliance.workspace_tools
  contains: "all_reachable:19"
confidence: high
tags:
- docs
- verified-v1
---
### An engine with no route is an engine that does not exist (RESOLVED)

- **ID**: T5-COMPLIANCE-LANDING-001
- **Status**: RESOLVED `TASK_COMPLIANCE_ENGINE_LANDING_V1`. Six prior tasks
  (T1–T4 plus the completeness correction) improved `coverage.py`,
  `mapping_store.py`, `applicability.py`, `tiers.py`, and `engine.py` while
  none of them had a route or a tool. `engine.route()` had never dispatched at
  HEAD, and the `⚖ Portal Compliance Analyst` workspace's `tools:` list
  contained none of the compliance-specific tools — not `compliance_ingest`,
  not `compliance_search`, not even the pre-existing `nerc_cip_currency`.
- **Description**: Every green number up to this task came from tests calling
  the library directly (`Register.load()`, `coverage_matrix()`,
  `make_proposer()` over the planted corpus). No test exercised the MCP
  surface a model actually sees, so no test caught the gap — the module was
  correct and completely unreachable at the same time. `compliance_mcp.py`
  now carries 8 new `@mcp.tool()` functions (`compliance_gaps`,
  `compliance_orphans`, `compliance_change_impact`, `compliance_mappings`,
  `compliance_scope`, `compliance_route`, `compliance_review_list`,
  `compliance_review_decide`), plus `compliance_ingest`/`compliance_search`
  (pre-existing custom routes, previously absent from the discovery manifest
  entirely — reachable by direct POST but invisible to the tool-registry's
  `GET /tools` discovery, so no model could ever have called them). All are
  in `config/inference/tools_manifest_compliance_mcp.json`, `_DISPATCH`, AND
  the workspace's `tools:` list — being reachable at the REST surface is
  necessary but not sufficient; the workspace's `tools:` list is what the
  model sees.
- **Guard**: `compliance.workspace_tools` (`portal/platform/wiki/claims.py`)
  cross-checks all three — the workspace list, the discovery manifest, and
  `_DISPATCH` — for every `compliance_*`/`nerc_cip*` tool name, and reports
  `unreachable:<name>` the moment any one of the three drops it. Verified to
  actually fail: removing one dispatch entry flips the probe from
  `all_reachable:12` to `unreachable:compliance_scope`.

## Why

A probe that only checks a tool exists somewhere in the codebase would have
passed for six tasks straight while the workspace's model never saw it — that
is the exact failure this task exists to fix, so the guard has to bind all
three layers (manifest, dispatch, workspace list) at once, not just one of
them. Recording it here — with the negative-test evidence that the probe
actually flips red — is what keeps a future refactor from quietly re-severing
one of the three links and having every existing test stay green.
