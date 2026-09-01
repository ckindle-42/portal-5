---
id: unit-capability-vulnintel
kind: mixed
title: "Vulnintel MCP — live vulnerability & threat intelligence"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/vulnintel/tools/vulnintel_mcp.py
- type: code
  path: portal/modules/vulnintel/tests/test_vulnintel_mcp.py
- type: code
  path: scripts/native-mcp-service.sh
claims:
- probe: modules.enabled
  contains: vulnintel
confidence: high
tags:
- capability
- mcp
- security
- compliance
---

# Vulnintel MCP — live vulnerability & threat intelligence

## What

The Vulnintel MCP (`portal/modules/vulnintel/tools/vulnintel_mcp.py`, port 8934)
is a read-only, outbound-HTTPS-only intelligence server, pipeline- and
IDE-exposed, backing the `auto-security`, `auto-compliance`, and `auto-spl`
workspaces. It is host-native (stdlib + lazy `httpx` only) and launched by
`scripts/native-mcp-service.sh` / `scripts/lib/util.sh` alongside the other
host-native security MCPs.

## How it's used

Seven tools: `lookup_cve` (NVD record — CVSS, CWEs, references, timeline),
`get_epss` (FIRST EPSS exploitation probability + percentile), `check_kev`
(CISA Known Exploited Vulnerabilities membership, cached hourly),
`scan_dependencies` (OSV.dev scan of an ecosystem's `{name: version}` map),
`ics_advisories` (recent CISA ICSA/ICSMA advisories with an optional vendor
filter — the OT-specific source generic IT-CVE tooling misses), `lookup_ioc`
(clearnet IOC enrichment via abuse.ch ThreatFox + GreyNoise, with
private/reserved IPs rejected before any lookup), and `triage_cve` (one call
fans out to NVD + EPSS + KEV and returns a composite `risk_score` / `label`
plus, at `depth: deep`, an SSVC-style `Act` / `Attend` / `Track` decision).

## Why it exists

Before this, everything vulnerability-facing was a local classifier
(`classify_vulnerability`) or model recall — nothing could answer whether a CVE
is KEV-listed, what its EPSS is, or whether a dependency set is affected.
Compliance and security workspaces reasoned from stale training data. The
composite score applies a CISA-KEV hard override: a KEV-listed CVE is never
labeled below CRITICAL and clamps to `risk_score >= 76` regardless of CVSS or
EPSS. Every fan-out call is written to an append-only JSONL audit log
(`{ts, tool, params_redacted, duration_ms, cache_hit, status}` — keys and
response bodies are never recorded), sized for NERC CIP-007-6 R2
patch-evaluation evidence.

## Value

An analyst gets exploitation-in-the-wild signal (KEV, EPSS) and an explainable
SSVC decision in one call instead of a prose guess, and a compliance reviewer
gets a defensible, timestamped evidence trail for the apply-or-mitigate
decision. Every API key (`NVD_API_KEY`, `GREYNOISE_API_KEY`, `ABUSECH_AUTH_KEY`)
is optional — a zero-key install still yields NVD, EPSS, KEV, OSV, and CISA ICS
advisories. Tor `.onion` active access and dark-web scraping are deliberately
excluded — a separate gated operator decision, never a default.
