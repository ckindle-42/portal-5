---
id: unit-tests-unit-test_document_mcp
kind: mixed
title: "Unit tests \u2014 test_document_mcp"
sources:
- type: code
  path: tests/unit/test_document_mcp.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.89226
updated_at: 1785800468.89226
---

Unit tests for test_document_mcp.

## Why

The document read tools are the file-access surface, and their tests verify reading without a real document service. A read tool that returned the wrong content or crashed on a valid file would break every document persona, so the tools are pinned.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
