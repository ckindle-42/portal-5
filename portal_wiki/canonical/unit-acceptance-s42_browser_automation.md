---
id: unit-acceptance-s42_browser_automation
kind: mixed
title: "S42 \u2014 Browser automation"
sources:
- type: code
  path: tests/acceptance/s42_browser_automation.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799823.9086661
updated_at: 1785799823.9086661
---

This is the acceptance section s42_browser_automation. S42 — Browser automation

## Why

It proves the browser MCP drives a real browser end to end, exercising the guarded web-automation surface. Browser automation is the SSRF-capable surface, so this section verifies both that it works and that its admission controls are present.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
