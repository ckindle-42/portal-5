---
id: unit-capability-netforensics
kind: mixed
title: "Network Forensics MCP — tshark PCAP analysis + gated lab recon"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/netforensics/tools/netforensics_mcp.py
- type: code
  path: portal/modules/netforensics/tests/test_netforensics_mcp.py
- type: code
  path: scripts/native-mcp-service.sh
claims:
- probe: modules.enabled
  contains: netforensics
confidence: high
tags:
- capability
- mcp
- security
- pcap
---

# Network Forensics MCP — tshark PCAP analysis + gated lab recon

## What

The Network Forensics MCP (`portal/modules/netforensics/tools/netforensics_mcp.py`,
port 8941) is a read-only server, pipeline- and IDE-exposed, backing the
`auto-security` blueteam variant and `auto-spl`. It is host-native and shells
out to `tshark` (installed via `./launch.sh install-netforensics`); every tool
degrades with a descriptive error when `tshark` is absent.

## How it's used

`protocol_hierarchy` runs `tshark -qz io,phs` and additionally reports which
ICS ports appear, so an analyst is handed off to `icsot.dissect_pcap` for
protocol-level ICS work instead of this server re-implementing it.
`extract_fields` is `tshark -Y <filter> -T fields -e ...` for targeted
extraction; `conversations` is `tshark -qz conv,<kind>`. `recon_scan` is the
one active capability: it returns a refusal unless
`NETFORENSICS_RECON_ENABLED=1` AND every target resolves inside the security
module's `perception.LAB_CIDR` — the guard runs first, always, and is the
same predicate the rest of the security surface uses.

## Why it exists

The fleet had no live packet dissection and recon ran unstructured through
`execute_bash`. PCAP analysis here is passive and file-based (confined to
`NETFORENSICS_ROOT`); it is the IT/IR complement to the `icsot` module's ICS
dissection and defers ICS payloads to it.

## Value

An analyst turns a capture into a protocol/host/field picture with a few
structured calls, and any active scan is off by default and cannot leave the
authorized lab CIDR — `recon_scan` in a workspace is a deliberate operator
`[GATE]`.
