---
id: unit-capability-detections
kind: mixed
title: "Detections MCP \u2014 queryable SPL detection library"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/security/tools/detections_mcp.py
claims: []
confidence: high
tags:
- capability
- mcp
- security
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# Detections MCP — queryable SPL detection library

## What

The Detections MCP (`portal/modules/security/tools/detections_mcp.py`, port
8932) serves a curated SPL detection library as structured, queryable data. It
is a host-native service (`detections-mcp` launchd label) and is both
pipeline- and IDE-exposed.

## How it's used

The surface is `spl_search_library` (keyword or ATT&CK-id search over the
library), `spl_validate_syntax` (local SPL syntax check with no live Splunk),
`spl_explain_detection` (logic, mappings, and expected signal for one
technique), `spl_techniques_covered` (every technique id that has a detection),
and `spl_diff_hypothesis` (compare a detection's expected signal against what
was observed).

## Why it exists

Detections are lookups, not retrieval — an analyst asks "which rule covers
this technique" or "is this SPL valid" and needs a deterministic answer, not an
embedding search over prose. Structuring the library as data rather than as a
RAG index keeps every query exact, and validating SPL locally means a rule can
be checked before it ever touches a live Splunk instance.

The `detection` module's `detection_mcp` (`unit-capability-detection`, port
8938) is the complementary half: this MCP is the read-only SPL *library*;
`detection_mcp` adds Sigma/YARA *conversion* and the promoted live SIEM
*execution* tools. They are unified by design, not duplicated.

## Value

The library is mechanically diffable against an analyst's hypothesis, so
coverage gaps surface as precise answers ("no detection covers this signal")
instead of vague retrieval. It pairs with the MITRE MCP for technique data and
with the lab's capture tooling for replay verification.
