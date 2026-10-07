---
id: unit-known-limitations-compliance-mcp-protocol-calls-not-cancelled
kind: what
title: Compliance Tool Calls Over the MCP Protocol Are Not Cancelled on Disconnect
sources:
- type: code
  path: portal/modules/compliance/tools/compliance_mcp.py
- type: code
  path: portal/modules/compliance/core/cancellation.py
- type: code
  path: reports/host_memory_safety/W3.md
claims: []
confidence: high
tags:
- known-limitations
- compliance
- memory-safety
---

- **ID**: HOST-MEMORY-SAFETY-W3-MCP
- **Status**: OPEN. The production path is covered; the direct MCP-protocol path is not.
- **Description**: Client-disconnect cancellation (`TASK_HOST_MEMORY_SAFETY_V1` W3) lives in the compliance MCP's REST route `/tools/{tool_name}` (`invoke_tool`). The pipeline's tool registry and the acceptance harnesses call that route, so their abandoned calls stop within seconds. A client that speaks the MCP protocol itself (streamable HTTP, for example Claude Code's `portal-compliance` tools) goes through the MCP SDK's request handling, which does not bind the cancel token, so a long tool call it abandons runs to completion server-side.
- **Mitigation**: The model calls such a run makes still pass through the pipeline's load guard, so a cold load cannot exceed host memory; the abandoned work only holds its model busy until it finishes.
- **Revisit trigger**: a long compliance tool (`compliance_ask`, sweeps) becomes routinely called over the MCP protocol, or the SDK exposes a per-request cancellation hook the tool runner can bind to the same token.

## Why

The cancel token is bound where the tool is dispatched. The REST route is the one Portal code owns end to end, and it carries the production traffic. Binding it inside the MCP SDK's own dispatch would mean patching or wrapping the SDK's request loop, for clients that today are operator tools rather than production callers.
