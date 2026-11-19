---
id: unit-capability-unifi
kind: mixed
title: "UniFi Network MCP — home-gateway control behind a stdio bridge"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/orchestration/mcp/stdio_bridge_mcp.py
- type: code
  path: scripts/native-mcp-service.sh
claims:
- probe: mcp.fleet.ids
  contains: unifi
confidence: high
tags:
- capability
- mcp
- orchestration
---

# UniFi Network MCP — home-gateway control behind a stdio bridge

## What

The UniFi fleet entry (:8949, host-native launchd label
`com.portal5.unifi-mcp`) exposes the operator's existing user-wide UniFi
Network MCP to the Pipeline. The tool implementation stays the sirkirby
`unifi-network-mcp@0.40.0` stdio process launched by
`~/mcp/unifi-network/run.sh` — credentials live outside the repo in
`~/.config/unifi-network-mcp/credentials.env` — and
`portal/modules/orchestration/mcp/stdio_bridge_mcp.py` only relays native
MCP `tools/list` and `tools/call` over streamable HTTP plus a `/health`
route. The bridge never imports the child's code, so the MCP stays an
independent service (CLAUDE.md Rule 3).

## How it's used

`expose_to_pipeline: true` puts the `unifi_*` tools in the Pipeline registry;
the workspaces `auto-daily::fast` and `auto-coding` advertise a curated read
set (`unifi_list_devices`, `unifi_list_clients`, `unifi_list_wlans`, …) plus
the lazy meta-tools (`unifi_tool_index`, `unifi_load_tools`,
`unifi_execute`). Every `unifi_` tool name is confirm-gated for Jarvis
(`personal_policy.CONFIRM_TOOL_PREFIXES`), so a personal task waits for the
Telegram confirm before any call. The sirkirby server itself registers
mutations behind its own permission mode (default confirm) on top of
Jarvis's gate.

## Why it exists

Jarvis personal tasks ("read the unifi device list") previously had no fleet
path to the home network: the operator's UniFi MCP was reachable only from
user-scope IDE registration. Bridging rather than reimplementing keeps the
operator's known-good tool (including its documented controller-API limits)
as the single implementation.

## Value

A confirm-gated home-network read surface for the personal agent, with zero
third-party API reimplementation, and a service that reports health like
every other Portal MCP so the `up` gate can supervise it.

`default_enabled: false` keeps fleet-health quiet on machines without
`~/mcp/unifi-network`; wherever the launcher exists, `up` installs the
launchd service and health-gates it (module_services `skip_reason`).
