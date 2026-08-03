---
id: unit-tests-quality-signals
kind: mixed
title: "Tests quality-signals \u2014 per-category response quality score"
sources:
- type: code
  path: tests/quality_signals.py
  commit: 4900007a
last_generated_commit: 4900007a
claims: []
confidence: high
tags:
- authored-v1
- tests
created_at: 1785798818.650997
updated_at: 1785798818.650997
---

`quality_signals.py` computes a quality score in [0.0, 1.0] for a response
as `signals_found / signals_expected`, going beyond raw TPS or keyword
presence to judge response quality per category.

## Why

TPS measures speed and keyword-presence measures bluntly; neither tells an
operator whether a response is actually good for its category. The quality
signal is the middle ground — per-category checks (coding responses contain
runnable code, reasoning responses show the reasoning) summed into a score.
The signals are explicitly tuned to the bench prompt library, and the
docstring's warning is the contract: if a category's prompt changes, its
signals must be updated too, or the quality score measures the wrong thing.

## Interfaces

`quality_score(category, response_text)` returns the score; the per-category
verifiers implement the signal checks.

## Gotchas

The signal-to-prompt coupling is deliberate and documented — the quality
score is only meaningful when the prompts it was tuned to are the prompts
being run.
