---
id: unit-tests-recall-scorer
kind: mixed
title: "Tests recall scorer \u2014 LCS line-alignment reproduction score"
sources:
- type: code
  path: tests/recall_scorer.py
  commit: 4900007a
last_generated_commit: 4900007a
claims: []
confidence: high
tags:
- authored-v1
- tests
created_at: 1785798822.155159
updated_at: 1785798822.155159
---

`recall_scorer.py` scores verbatim function-body reproduction by
longest-common-subsequence line alignment, reporting matched, missing,
hallucinated, and bonus lines with per-function pass/fail and a per-line
classification for rendering. It is pure stdlib with no external
dependencies and is designed to be unit-tested deterministically without any
LLM.

## Why

The recall test asks a model to reproduce a function body verbatim, and
scoring that needs more than exact-match (a single changed line should not
zero the whole function). The LCS line alignment is the answer: it aligns
the produced lines against the expected ones and classifies each as matched,
missing, hallucinated (present but not expected), or bonus, so the score
reflects *how* the reproduction diverged, not just whether it matched. Being
pure stdlib is what makes the scorer deterministic and unit-testable without
an LLM — the scoring logic is verified in isolation from model behaviour.

## Interfaces

`score_function_recall`, `classify_lines`, `_normalize_lines`, `_lcs_match`,
and `render_diff_ansi`.

## Gotchas

The LCS approach scores line-level alignment, not semantics — a
function that reproduces the same behaviour with different line structure
would score lower despite being functionally correct, which is the accepted
strictness of a verbatim-reproduction test.
