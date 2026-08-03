---
id: unit-sec-tests-test_capability_graph
kind: mixed
title: "Security tests \u2014 test_capability_graph"
sources:
- type: code
  path: portal/modules/security/tests/test_capability_graph.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.98631
updated_at: 1785800599.98631
---

Unit tests for the security module's test_capability_graph surface.

## Why

Tests for the capability graph and gap engine: stable-id entities and the coverage summary. The stable-id property is what makes the graph's coverage answers durable across runs.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
