---
id: unit-capability-browser
kind: mixed
title: "Browser MCP \u2014 Obscura web automation"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/research/tools/browser_mcp.py
- type: code
  path: config/inference/tools_manifest_browser_mcp.json
claims: []
confidence: high
tags:
- capability
- mcp
- research
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# Browser MCP — Obscura web automation

## What

The Browser MCP (`portal/modules/research/tools/browser_mcp.py`, port 8923)
drives a real browser via Obscura (a Rust
headless engine; no Node/Chromium) with built-in stealth. It is IDE-exposed
(`expose_to_pipeline: false`, `expose_to_ide: true`), so it is an operator's
web-automation surface rather than a persona-triggerable one.

## How it's used

`browser_navigate` opens a page and returns its accessibility tree;
`browser_snapshot` returns the current tree; `browser_click`, `browser_fill`,
and `browser_screenshot` interact with it; `browser_evaluate` runs JavaScript
in the page context; `browser_close` releases a session; `browser_list_profiles`
names the available persistent profiles.

## Why it exists

Some tasks need a real rendered page — clicking through a form, capturing a
screenshot, exercising a web UI — which a static fetch cannot provide.
Keeping the automation lane IDE-only follows the same trust boundary as the
vendored base tools: an agent that can drive a browser is effectively running
arbitrary code with network access, which is an operator capability, not a
routed persona's.

## Value

An operator agent can automate a web flow end to end — navigate, verify the
tree, fill, submit, screenshot the evidence — while the pipeline's personas
stay restricted to the bounded search/fetch surface. The profile mechanism
preserves logins and session state across calls.
