---
id: unit-uat-notify
kind: mixed
title: "UAT notify \u2014 completion notifications"
sources:
- type: code
  path: tests/uat/notify.py
  commit: 85bb65bd
last_generated_commit: 85bb65bd
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat
created_at: 1785799329.934061
updated_at: 1785799329.934061
---

The UAT completion notifications (the `_git_sha` helper lives here because the notify functions are its only callers).

## Why

A long UAT run completes while the operator is away, and the notify module sends the completion signal. The `_git_sha` co-location is a deliberate placement — it has exactly one caller family, so it lives with them rather than in a general util module.

## Interfaces

The notification functions and `_git_sha`.

## Gotchas

The git sha is what ties a notification to the code state that ran — a notification without it cannot be audited.
