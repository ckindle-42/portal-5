---
id: unit-security-trajectory-score
kind: what
title: Trajectory-grounded engagement verdict scoring
sources:
- type: code
  path: portal/modules/security/core/trajectory_score.py
last_generated_commit: baca992c674a3cbb36a619e8f62e7e88b8fccfff
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5
updated_at: 1784946220.5
---

`trajectory_score.py` composes a single final verdict for an entire engagement out of the per-step records each landed action produced. The dataclasses `StepRecord` and `TrajectoryVerdict` carry the inputs and the result, and `score_trajectory()` applies an ordering that keeps honesty first: no landed steps yields `UNAVAILABLE`, a reached objective with any synthetic step yields `INDETERMINATE`, a clean reach is `PROVEN`, and everything else is `FAILED`. Whether the objective state was genuinely reached is delegated to `_objective_reached()`, which resolves the objective class through `OBJECTIVE_CLASS_ORACLE` and then calls the matching entry in `ORACLES`. No model judgement enters this path, so identical inputs always produce the same verdict.

## Why

A single step verdict is not enough to trust an engagement: a run that reached the goal only because some intermediate step was synthetic must never be reported as proven. Lifting the per-run rule of `episode.py` to the trajectory keeps that invariant at the level an operator actually reads, and doing it deterministically means the outcome is repeatable and auditable rather than dependent on which model happened to be serving the request.
