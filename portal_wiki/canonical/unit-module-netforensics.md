---
id: unit-module-netforensics
kind: mixed
title: "Network Forensics Module — tshark/Zeek PCAP analysis + gated lab recon"
sources:
- type: code
  path: portal/modules/netforensics/tools/netforensics_mcp.py
- type: code
  path: portal/modules/security/core/perception.py
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: config/portal.yaml
claims:
- probe: modules.enabled
  contains: netforensics
confidence: high
tags:
- netforensics
- pcap
- tshark
- security
- module
- verified-v1
---

# Network Forensics Module

## Tools

`netforensics_mcp` (:8941) — passive, file-based PCAP analysis via `tshark`.
`protocol_hierarchy` returns the tshark protocol tree and flags any ICS ports
present, pointing the caller at `icsot.dissect_pcap` rather than duplicating
ICS logic. `extract_fields` pulls chosen tshark fields under a display filter
(DNS names, HTTP hosts, TLS SNI, ...). `conversations` gives top-talker
statistics. `recon_scan` is a `[GATE]`d structured nmap surface: off by
default (`NETFORENSICS_RECON_ENABLED`), and even when enabled every target is
checked against the authorized lab CIDR — reusing the security module's
`perception.LAB_CIDR` guard, not a divergent copy — before nmap runs.

## Workspaces

- `auto-security` (blueteam) — IR / forensics PCAP analysis
- `auto-spl` — detection-engineering PCAP context

## Module State

```yaml
enabled: true
```

## Why

PCAP was referenced only as capture recipes / evidence in the security core —
there was no live packet dissection anywhere in the fleet, and recon ran
unstructured through `execute_bash` inside Kali. This is the general IT/IR
complement to the `icsot` module's ICS-specific dissection: analysis is
passive and confined to `NETFORENSICS_ROOT`; active recon is a separate
operator `[GATE]`, lab-scoped, and off by default.
