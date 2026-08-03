---
id: unit-acceptance-s60_tool_calling
kind: mixed
title: "S60 \u2014 Tool calling"
sources:
- type: code
  path: tests/acceptance/s60_tool_calling.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799831.368244
updated_at: 1785799831.368244
---

This is the acceptance section s60_tool_calling. S60 — Tool calling

## Why

It proves the tool-calling path dispatches real tools mid-response, the multi-hop loop that the streaming tool loop implements. Tool calling is the difference between a chatbot and an agent, and a dispatch regression that breaks mid-stream is invisible to a non-streaming test.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
