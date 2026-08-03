---
id: unit-tests-unit-test_rag
kind: mixed
title: "Unit tests \u2014 test_rag"
sources:
- type: code
  path: tests/unit/test_rag.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892313
updated_at: 1785800468.892313
---

Unit tests for test_rag.

## Why

The RAG MCP is the knowledge-retrieval surface, and its tests verify the reading and retrieval without a live index. A read or retrieval regression would silently degrade every grounded answer, so the path is pinned hermetically.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
