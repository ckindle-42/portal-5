---
id: unit-wiki-adapter-writeback-gap
kind: mixed
title: "Wiki gap write-back \u2014 coverage-status updates"
sources:
- type: code
  path: portal/platform/wiki/adapters/writeback_gap.py
  commit: 66aa9fda
last_generated_commit: 66aa9fda
claims: []
confidence: high
tags:
- authored-v1
- wiki
- adapter
created_at: 1785797605.801517
updated_at: 1785797605.801517
---

The gap write-back adapter updates a technique's wiki unit coverage status
when the gap engine resolves a gap — a detection added or a scenario added
flips the unit's coverage state to match.

## Why

The gap engine's whole output is a coverage verdict per technique, and a
verdict that does not reach the wiki is a verdict nobody can cite. Writing
the resolution back updates the technique unit so the gap status lives in the
spine, not in a transient report. The confirm gate keeps a gap claim from
entering canonical without a human or trusted harness sign-off.

## Interfaces

`writeback_gap_resolution(technique_id, gap_summary, episode_id, auto_confirm)`
proposes the coverage update.

## Gotchas

The `gap_summary` value (COVERED, RED_ONLY, and friends) is the gap engine's
own vocabulary, passed through unchanged.
