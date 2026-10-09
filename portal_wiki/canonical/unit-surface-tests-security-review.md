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
updated_at: 1791552192.0
---

`tests/security/review/` and `tests/security/review_eval/` hold focused tests
for the review product and scorer plane. Product tests cover the truth wall,
intake, knowledge, calibrated funnel, verdict replay and null-slice isolation,
defense response mapping, service, and Splunk/embedder adapters with fake I/O.
Scorer tests cover capture-validator known answers, answer-key drops
and product event IDs, leave-one-family-out leakage, stage traces, report
validation, and pre-registered decision rules.

## Why

These tests pin the conditions that make offline evaluation trustworthy: empty
truth cannot imply success, novel items skip retrieval, ties select the earliest
loss, incomplete entity matches receive a drop receipt, an admitted capture
must match its recorded hash, seeded fold leakage fails, and invalid or premature
decision records are rejected. Temporary repositories and fake transports keep
adapter checks isolated from live state.

## Boundaries

These tests are hermetic. They do not contact Splunk, Ollama, the lab, or an
emulation controller and they do not create new replay data.
