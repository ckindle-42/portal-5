---
id: unit-surface-sec-tests
kind: mixed
title: "Security test suite \u2014 hermetic bench, orchestration, and scoring contracts"
sources:
- type: code
  path: portal/modules/security/tests/*.py
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785882000.0
updated_at: 1785882000.0
---

The security test suite pins the contract of the bench-and-lab harness that
measures red and blue model behaviour against a Proxmox lab. A score must be
earned from real evidence and real lab output, never from a model's
narration. Every member is hermetic, so the whole tree runs in CI without a
live lab.

## Why

A benchmark is only as credible as the evidence its scores rest on, so every
decision here serves one rule: verification must be earned. No path may emit
a verified verdict without real evidence, and the predicted observation
delta must never leak into observations — raw lab output is ground truth,
and `verify_finding` alone produces oracle results. The red transcript is an
audit plane, not sensor evidence; capture recipes need a positive and a
request-only negative control; coverage is granted only on genuine output.
Each decision keeps the model honest against the lab.

## Interfaces

The bench foundation pins the lab reachability gate and raw-output capture
around `lab_dispatch`. Blue orchestration pins a deterministic section
pipeline with a cite-or-drop grounding control. Investigation and consensus
pin the evidence record and the council quorum; scoring pins the
exact/parent/tactic tiers, the similar/variant/novel verdict axis, and the
unknown-defense invariants. The capability graph's `build_index` enforces the
no-orphan invariant; sweeps pin checkpoint safety and the bootstrap
confidence interval; the loop pins escalation and notification-to-resume
wiring; the `field_journal` pins the only-observed-facts rule; and the red
side pins `validate_capture_signals`.

## Gotchas

The suite must pass with no live lab, no Docker, and no live Splunk, and
several members are the only proof that gates such as the scope guard hold
before the lab exists. Some members write through real runtime paths — the
committed `field_journal` and the `results/checkpoints` directory — leaving
artifacts that demand the documented git-status cleanup before staging.
