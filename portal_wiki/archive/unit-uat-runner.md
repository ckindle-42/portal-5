---
id: unit-uat-runner
kind: mixed
title: "UAT runner \u2014 section orchestration"
sources:
- type: code
  path: tests/uat/runner.py
  commit: 85bb65bd
last_generated_commit: 85bb65bd
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat
created_at: 1785799308.3771038
updated_at: 1785799308.3771038
---

The UAT run orchestrator that drives the sections, collects results, and reports the outcome.

## Why

The runner is the largest module and the sequencing heart: it walks the UAT sections in order, applies the skip rules, drives each through dispatch, grades the response, and records the result. Keeping the orchestration in one module is what makes a UAT run's ordering deterministic and its result collection complete.

## Interfaces

The section loop, skip handling, grading integration, and result recording.

## Gotchas

The runner drives real Open WebUI — it is a live acceptance run, not a unit test.
