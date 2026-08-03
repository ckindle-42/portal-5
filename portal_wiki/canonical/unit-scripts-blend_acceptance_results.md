---
id: unit-scripts-blend_acceptance_results
kind: mixed
title: "Script \u2014 blend_acceptance_results"
sources:
- type: code
  path: scripts/blend_acceptance_results.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799458.24798
updated_at: 1785799458.24798
---

Blends multiple acceptance runs into one coherent result set, merging the baseline run with targeted reruns by section, so a partial rerun can repair a full run's failed sections.

## Why

A full acceptance run fails in a few sections; re-running the whole suite for those sections wastes hours. The blender merges a baseline run with targeted reruns (which sections belong to which source commit) so the final result set reflects the best evidence per section. The priority order (baseline for untouched sections, rerun for repaired ones) is the contract that makes the blend deterministic.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
