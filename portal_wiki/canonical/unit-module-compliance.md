---
id: unit-module-compliance
kind: mixed
title: "Compliance Module \u2014 multi-framework compliance mapping + control-catalog MCP"
sources:
- type: code
  path: portal/modules/security/core/compliance_report.py
- type: code
  path: portal/modules/compliance/tools/compliance_mcp.py
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: config/portal.yaml
claims:
- probe: modules.enabled
  contains: compliance
confidence: high
tags:
- compliance
- module
- verified-v1
created_at: 1783821386.790902
updated_at: 1783821386.790902
---

# Compliance Module — multi-framework compliance mapping (config-only)

## Tools

`compliance_mcp` (:8937) — authoritative control-catalog lookup and evidence
scaffolding. `lookup_control` / `search_controls` return citable ids over
distilled OSCAL catalogs (the NIST SP 800-53 Rev5 control set and NIST CSF 2.0)
so the analyst cites `NIST SP 800-53 AC-2` rather than paraphrasing from model
memory. `nerc_cip_requirement` looks up a CIP-002..CIP-014 requirement with its
related 800-53 controls. `map_frameworks` uses a bundled OLIR-style crosswalk
seed (partial — a refresh path is documented). `patch_evidence` calls the
`vulnintel` module's `triage_cve` in-process and formats a CIP-007-6 R2
patch-evaluation record (source identified, applicability, apply-or-mitigate,
the 35-day clock). `refresh_catalogs` re-pulls and re-distils the OSCAL
sources — `honest-BLOCKED` on failure, never fabricated control text.

Compliance analysis also still reuses the security module's
`compliance_report.py` for report generation.

## Workspaces

- `auto-compliance` — compliance mapping workspace, routed by its
  `module: compliance` tag in `config/portal.yaml`.

## Module State

```yaml
enabled: true
```

## Why

The compliance module is config-only: it owns a workspace but no MCP
server, so toggling it affects routing (`auto-compliance`) and nothing in
the fleet. That is exactly why this unit is live config rather than a
description — `portal/platform/wiki/adapters/modules.py` reads the fenced
`enabled:` field to gate the workspace, and the module's actual analysis
capability lives in the security module it depends on. Keeping the unit
sourced to the adapter plus `config/portal.yaml` makes the toggle's real
blast radius visible.
