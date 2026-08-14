---
id: unit-portal-mcp-namespace
kind: mixed
title: "portal_mcp \u2014 vendored MCP assets namespace"
sources:
- type: code
  path: portal_mcp/__init__.py
  commit: b0aa6770
claims: []
confidence: high
tags:
- authored-v1
- mcp
created_at: 1785795040.43541
updated_at: 1785795040.43541
---

`portal_mcp` is the packaging namespace for Portal 5's vendored MCP service
assets. It carries the version string for the vendored server suite and no
other behavior — the individual servers live in sibling modules under this
package.

## Why

The namespace exists so the vendored MCP assets have a stable import home and
a single place the suite version is recorded. Keeping the version here means
a tool server can report which vendor revision it wraps without each module
maintaining its own copy of the number.

## Interfaces

The module exposes `__version__` only. There are no callable functions; the
package's real content is the vendored server modules beneath it.
