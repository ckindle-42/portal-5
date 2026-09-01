---
id: unit-module-vulnintel
kind: mixed
title: "Vulnerability & Threat Intelligence Module — live CVE/EPSS/KEV/OSV/ICSA + clearnet threat intel"
sources:
- type: code
  path: portal/modules/vulnintel/tools/vulnintel_mcp.py
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: config/portal.yaml
claims:
- probe: modules.enabled
  contains: vulnintel
confidence: high
tags:
- vulnintel
- module
- security
- compliance
- verified-v1
---

# Vulnerability & Threat Intelligence Module

## Tools

`vulnintel_mcp` (:8934) — a read-only, outbound-HTTPS-only intelligence MCP.
Exposes `lookup_cve` (NVD), `get_epss` (FIRST EPSS), `check_kev` (CISA KEV),
`scan_dependencies` (OSV.dev), `ics_advisories` (CISA ICSA/ICSMA — the
OT-specific source the generic IT-CVE tooling misses), `lookup_ioc` (clearnet
IOC enrichment via abuse.ch ThreatFox + GreyNoise, private/reserved IPs
rejected before any lookup), and `triage_cve` (one-call composite risk with a
CISA-KEV hard override + SSVC-style decision, audited for NERC CIP-007-6 R2
patch-evaluation evidence).

## Workspaces

- `auto-security` — vulnerability analysis
- `auto-compliance` — CIP-007 R2 patch-evaluation evidence
- `auto-spl` — detection-engineering context

## Module State

```yaml
enabled: true
```

## Why

Fronts live authoritative vulnerability sources through one read-only MCP so
the fleet stops reasoning about CVEs from stale training data. Every API key
is optional — a zero-key install still yields NVD, EPSS, KEV, OSV, and CISA
ICS advisories. The composite score clamps a KEV-listed CVE to CRITICAL
(≥ 76) regardless of CVSS/EPSS. The audit log is append-only JSONL and never
records keys or response bodies. Tor `.onion` active access and dark-web
scraping are deliberately excluded — a separate gated operator decision, never
a default. The module gates the `vulnintel` fleet id and its workspaces, both
derived from their `module: vulnintel` tag in `config/portal.yaml`.
