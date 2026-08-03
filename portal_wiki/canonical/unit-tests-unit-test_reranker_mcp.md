---
id: unit-tests-unit-test_reranker_mcp
kind: mixed
title: "Unit tests \u2014 test_reranker_mcp"
sources:
- type: code
  path: tests/unit/test_reranker_mcp.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.89232
updated_at: 1785800468.89232
---

Unit tests for test_reranker_mcp.

## Why

The reranker is the retrieval-rerank surface, and its tests verify the service contract. A rerank regression would reorder retrieval results wrongly, degrading every two-stage retrieval answer.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
