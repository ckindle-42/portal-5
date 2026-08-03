---
id: unit-scripts-caldera_emulate
kind: mixed
title: "Script \u2014 caldera_emulate"
sources:
- type: code
  path: scripts/caldera_emulate.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799461.841791
updated_at: 1785799461.841791
---

The live threat lane: unlike the pre-labeled corpora, Caldera generates fresh unlabeled activity on demand against owned lab targets — the only lane that produces genuine novel-threat telemetry.

## Why

Pre-labeled corpora carry the answer in every event, so they cannot validate detection against *unexpected* behaviour. Caldera's on-demand generation is the complement: fresh, unlabeled activity that a detection must classify without the answer being known in advance. It is the difference between regression-testing a detector and challenging it.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
