---
id: unit-surface-tests-security-review
kind: mixed
title: "Security review program tests"
sources:
- type: code
  path: tests/security/review/*.py
- type: code
  path: tests/security/review_eval/*.py
claims: []
confidence: high
tags:
- authored-v1
- security
- review
- tests
created_at: 1791527057.0
updated_at: 1791527057.0
---

`tests/security/review/` and `tests/security/review_eval/` hold focused tests
for the review program's derived-state renderer, truth ledger, and pre-registered
decision validation. The cases use temporary repositories and in-memory traces
to verify deterministic output, invalid records, and stage attribution.

## Why

These tests pin the conditions that make offline evaluation trustworthy: empty
truth cannot imply success, novel items skip retrieval, ties select the earliest
loss, and invalid or premature decision records are rejected. Temporary repos
keep renderer checks isolated from live state.

## Boundaries

These tests are hermetic. They do not contact Splunk, Ollama, the lab, or an
emulation controller and they do not create new replay data.
