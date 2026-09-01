---
id: unit-capability-mitre
kind: mixed
title: "MITRE MCP \u2014 deterministic ATT&CK lookup"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/security/tools/mitre_mcp.py
- type: code
  path: portal/modules/security/core/siem/mitre_ics_techniques.json
claims: []
confidence: high
tags:
- capability
- mcp
- security
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# MITRE MCP — deterministic ATT&CK lookup

## What

The MITRE MCP (`portal/modules/security/tools/mitre_mcp.py`, port 8929) is a
host-native service serving deterministic MITRE ATT&CK, D3FEND, and CWE
lookups. It is pipeline- and IDE-exposed, sharing the same launchd wrapper
(`mitre-mcp`) that hosts the detections service.

## How it's used

`mitre_technique_lookup` returns a technique's name, tactic, platforms,
`matrix` (`enterprise` | `ics`), and detection availability;
`mitre_data_sources_for_technique` maps a technique to the telemetry sources
and event ids needed to detect it (Enterprise from the curated Event-ID map,
ICS straight from the STIX bundle); `mitre_detections_for_technique` joins a
technique id to the local SPL library; `mitre_techniques_list` enumerates
techniques, optionally filtered by tactic (matching Enterprise and ICS
tactic names).

The index carries both matrices: ATT&CK for Enterprise (bench SPL library +
embedded subset) and the full ATT&CK-for-ICS technique set from MITRE's official
`ics-attack` STIX bundle, distilled to
`portal/modules/security/core/siem/mitre_ics_techniques.json` and regenerated
by `scripts/refresh_mitre_ics_catalog.py`. ICS is loaded eagerly — the catalog
is small, so there is no lazy-on-first-`T0xxx` path.

## Why it exists

Technique data is a constant-index problem: every query is a lookup against a
stable, versioned body of knowledge, and an exact id must return an exact
answer. Shipping the index inside the MCP removes the need for an agent to
re-derive mappings by memory and keeps the technique-to-detection join local
rather than hand-reasoned per question.

## Value

A security agent gets a precise, deterministic technique graph — including the
data sources its detection would need — instead of a language-model guess about
what T-code a behavior maps to. The D3FEND and CWE axes extend the same
determinism to defense and weakness taxonomies.
