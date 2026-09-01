---
id: unit-capability-compliance
kind: mixed
title: "Compliance MCP — authoritative control catalogs & CIP-007 R2 evidence"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/compliance/tools/compliance_mcp.py
- type: code
  path: portal/modules/compliance/tests/test_compliance_mcp.py
- type: code
  path: scripts/native-mcp-service.sh
claims:
- probe: modules.enabled
  contains: compliance
confidence: high
tags:
- capability
- mcp
- compliance
---

# Compliance MCP — authoritative control catalogs & CIP-007 R2 evidence

## What

The Compliance MCP (`portal/modules/compliance/tools/compliance_mcp.py`, port
8937) is a read-only server, pipeline- and IDE-exposed, backing the
`auto-compliance` workspace. It is host-native (stdlib only) and launched by
`scripts/native-mcp-service.sh` / `scripts/lib/util.sh`. It adds tooling to the
existing `compliance` module — no new module.

## How it's used

`lookup_control` and `search_controls` read compact distillations of the
official OSCAL catalogs — NIST SP 800-53 Rev5 and NIST CSF 2.0, from
`usnistgov/oscal-content` — so every answer is `{id, title, statement, source}`
the analyst can cite. `nerc_cip_requirement` returns a CIP-002..CIP-014
requirement's paraphrased title and its related 800-53 controls.
`map_frameworks` resolves a CSF 2.0 subcategory to 800-53 (and the reverse)
through a bundled OLIR-style crosswalk seed, tagged `coverage: partial-seed`.
`patch_evidence` calls the `vulnintel` module's `triage_cve` in-process and
formats a CIP-007-6 R2 patch-evaluation record — source identified,
applicability placeholder, SSVC decision, and the two 35-calendar-day clocks.
`refresh_catalogs` re-pulls and re-distils the OSCAL sources
(`scripts/refresh_compliance_catalogs.py` is the CLI path) — it reports
`BLOCKED` on failure and never writes fabricated control text.

## Why it exists

`auto-compliance` is a serious workspace (NERC CIP, NIST 800-53/CSF, PCI-DSS,
ISO 27001, CMMC) whose entire toolset was `create_word_document`, `read_pdf`,
`kb_search`, `kb_list`, `web_search` — it recited controls from model memory.
The ~5MB source OSCAL catalogs are never vendored; only the ~380KB / ~85KB
distillations the server actually reads.

## Value

Control work becomes grounded and citable instead of paraphrased, and the
CIP-007 R2 bridge turns a CVE into a defensible, dated patch-evaluation record
in one call. The crosswalk seed is deliberately marked partial rather than
presented as the authoritative OLIR — honest capability tiers over
overclaiming in a compliance tool.
