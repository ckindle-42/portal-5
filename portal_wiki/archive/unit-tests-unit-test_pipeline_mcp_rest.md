---
id: unit-tests-unit-test_pipeline_mcp_rest
kind: mixed
title: "Unit tests \u2014 test_pipeline_mcp_rest"
sources:
- type: code
  path: tests/unit/test_pipeline_mcp_rest.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892291
updated_at: 1785800468.892291
---

Unit tests for test_pipeline_mcp_rest.

## Why

The pipeline MCP is the coding tools' introspection surface, and its REST contract is what the tools compile against. A contract drift would break Claude Code and opencode against the pipeline silently, so the REST shape is pinned.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
