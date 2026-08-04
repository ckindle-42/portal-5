---
id: unit-sec-core-field_journal
kind: mixed
title: "Field journal \u2014 observed-fact engagement memory"
sources:
- type: code
  path: portal/modules/security/core/field_journal.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.394165
updated_at: 1785800269.394165
---

After each engagement, records the observed execution chain, pitfalls, and reusable patterns — only observed facts — so the loop recalls relevant prior engagements before acting.

## Why

The journal is the loop's institutional memory, but it must only record *observed* facts — an inference presented as an observation would contaminate every future decision. The recall-before-act and write-back-after pattern is what makes the loop learn from experience without learning from fantasy.

## Interfaces

After each engagement, records the observed execution chain, pitfalls, and reusable patterns — only observed facts — so the loop recalls relevant prior engagements before acting lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
