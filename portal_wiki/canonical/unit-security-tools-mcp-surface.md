---
id: unit-security-tools-mcp-surface
kind: mixed
title: "Security tools \u2014 MCP server namespace"
sources:
- type: code
  path: portal/modules/security/tools/__init__.py
  commit: b0aa6770
last_generated_commit: b0aa6770
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tools
created_at: 1785795029.118413
updated_at: 1785795029.118413
---

The security module's MCP tool surface names its three standalone server
processes — `detections_mcp`, `mitre_mcp`, and `security_mcp` — each launched
as its own MCP server (see the launch scripts and docker-compose). The
detection-knowledge content they serve lives in
`portal.modules.security.knowledge`; this package is the marker for the tool
servers, not the content.

## Why

The three servers are independent services per the MCP independence rule, so
their import discipline matters: they serve detection knowledge but must not
each embed a copy of it. The `__init__` docstring records the rule — import
content from `knowledge`, not here — so a future tool server added to this
package inherits the dependency direction instead of duplicating the SPL
library.

## Interfaces

No callable surface in `__init__` itself. The package groups the three tool
server modules; each is launched independently and serves the knowledge
content via the re-export boundary.
