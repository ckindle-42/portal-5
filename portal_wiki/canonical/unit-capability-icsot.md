---
id: unit-capability-icsot
kind: mixed
title: "ICS/OT MCP — passive industrial-protocol dissection & ATT&CK-for-ICS"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/icsot/tools/icsot_mcp.py
- type: code
  path: portal/modules/icsot/tests/test_icsot_mcp.py
- type: code
  path: scripts/native-mcp-service.sh
claims:
- probe: modules.enabled
  contains: icsot
confidence: high
tags:
- capability
- mcp
- security
- ics
- ot
---

# ICS/OT MCP — passive industrial-protocol dissection & ATT&CK-for-ICS

## What

The ICS/OT MCP (`portal/modules/icsot/tools/icsot_mcp.py`, port 8936) is a
read-only, passive server, pipeline- and IDE-exposed, backing the
`auto-security` and `auto-spl` workspaces. It is host-native (stdlib + lazy
`scapy`) and launched by `scripts/native-mcp-service.sh` / `scripts/lib/util.sh`
alongside the other host-native security MCPs.

## How it's used

`list_ics_protocols` returns the recognized ICS ports and dissection tier.
`dissect_pcap` passively parses a capture — Modbus/TCP gets structured
dissection (`scapy.contrib.modbus`), and the function-code breakdown is tagged
to ATT&CK for ICS: writes (FC 5/15) -> `T1692.001` Command Message, register
writes (FC 6/16) -> `T0836` Modify Parameter, reads (FC 1-4) -> `T0801` Monitor
Process State; DNP3/S7comm traffic is tagged from port identification.
`asset_inventory` infers hosts, protocols, and HMI-vs-device roles from the
conversation directions. `correlate_advisories` calls the `vulnintel` module's
`ics_advisories` in-process to tie an observed vendor to recent CISA ICSA
advisories.

## Why it exists

The OT half of the security surface had no tooling. This server is passive by
design — it never transmits an ICS frame or touches a live PLC — because an
active write can disturb a running process. It ships with an honest capability
split: only Modbus is `full` tier; DNP3/S7comm/EtherNet-IP/BACnet are
`identify` tier with an extension hook. The same task completed `mitre_mcp`'s
ATT&CK-for-ICS matrix (`matrix: "ics"`) so the tags this server
emits are resolvable through the MITRE MCP.

## Value

An analyst can turn a plant capture into a protocol/asset picture and a
technique-tagged behavior list without a Wireshark session, and detection
engineers get ICS ATT&CK coverage in the same MITRE MCP they already use for
Enterprise. Active ICS capability (live polling, register writes, protocol
replay) is deliberately excluded — a separate operator `[GATE]`.
