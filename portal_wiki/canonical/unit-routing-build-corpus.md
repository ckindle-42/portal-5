---
id: unit-routing-build-corpus
kind: mixed
title: "Routing corpus builder \u2014 stable before/after router measurement"
sources:
- type: code
  path: tests/routing/build_corpus.py
  commit: dfa74e2e
last_generated_commit: dfa74e2e
claims: []
confidence: high
tags:
- authored-v1
- tests
- routing
created_at: 1785795502.531222
updated_at: 1785795502.531222
---

`build_corpus.py` assembles the routing-integrity corpus that measures the
keyword-layer router before and after the workspace collapse. It merges the
canonical routing examples (all 44, verified byte-identical across the
collapse), per-discipline TPS prompts, the prompts the regression script
already curated, and fold-coverage additions authored from the pre-collapse
routing descriptions so every folded lane has at least one unambiguous prompt
that reflects what that lane was actually for.

## Why

The corpus exists to answer a before/after question: did the collapse change
which workspace a given message routes to? For that measurement to mean
anything, the corpus must be *stable* across the two checkouts being compared
— which is why the pre-collapse examples are asserted byte-identical at
`45edb25` and HEAD, and why the fold-coverage prompts are written from the
*pre-collapse* descriptions: a prompt authored from today's config would bake
the collapse's answer into the question. The `expected_workspace` field is
optional because the corpus measures observed routing, not asserted routing —
the intent is to compare, not to pre-judge.

## Interfaces

`build()` assembles the record list and writes `tests/routing/corpus.json`
as a flat list of `{id, message, source, expected_workspace?}` entries.
`REPO_ROOT` is derived from the script location so it runs from any checkout.

## Gotchas

The corpus is a versioned artifact deliberately *not* rebuilt per measurement:
`measure.py` reads the current tree's `corpus.json` even when executing from a
pre-collapse worktree, so the same questions are asked of both code states.
