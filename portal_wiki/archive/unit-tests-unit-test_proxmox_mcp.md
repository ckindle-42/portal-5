---
id: unit-tests-unit-test_proxmox_mcp
kind: mixed
title: "Unit tests \u2014 test_proxmox_mcp"
sources:
- type: code
  path: tests/unit/test_proxmox_mcp.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892308
updated_at: 1785800468.892308
---

Unit tests for test_proxmox_mcp.

## Why

The Proxmox MCP's config and auth are verified with no network, pinning the server contract. A config or auth regression would make every Proxmox operation fail against the real host, so the logic is pinned before any live call.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
