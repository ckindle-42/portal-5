---
id: unit-surface-tests-bully
kind: mixed
title: "Retained Defensive Bully integration tests"
sources:
- type: code
  path: tests/security/bully/*.py
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- bully
- tests
created_at: 1786751207.0
updated_at: 1786751207.0
---

`tests/security/bully/` contains integration and contract tests for retained Bully corpus, intake, discovery, and data-plane behavior. Tests for the removed hunt orchestrator and multi-agent investigation path have been deleted; module-focused tests remain alongside the security modules.

## Why

This directory is a test surface only and contains no runtime entry points. Its tests check interactions among retained Bully modules and keep their supported behavior distinct from retired hunt and training phases.

## Interfaces

The tests exercise retained modules through their Python interfaces. Current filenames describe the module or behavior under test rather than a historical phase number.

## Gotchas

Hermetic tests use temporary paths and mocked transports where applicable. Live lab, Splunk, and model behavior requires its own operator-invoked evidence.
