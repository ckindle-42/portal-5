---
id: unit-tests-unit-test_config_ollama_url
kind: mixed
title: "Unit tests \u2014 test_config_ollama_url"
sources:
- type: code
  path: tests/unit/test_config_ollama_url.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.8922482
updated_at: 1785800468.8922482
---

Unit tests for test_config_ollama_url.

## Why

A non-canonical Ollama URL would break every backend call the pipeline makes, and the tests pin the canonicalisation rules. The URL forms the pipeline must accept — localhost, host.docker.internal, and the canonical forms — are exactly what these tests lock down.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
