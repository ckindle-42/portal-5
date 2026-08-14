---
id: unit-tests-integration-wiki-cycle
kind: mixed
title: "Integration test \u2014 wiki self-improving cycle proof"
sources:
- type: code
  path: tests/integration/test_wiki_self_improving_cycle.py
  commit: '96146826'
claims: []
confidence: high
tags:
- authored-v1
- tests
- integration
- wiki
created_at: 1785795634.517728
updated_at: 1785795634.517728
---

This integration test is the feature-complete proof of the wiki's
self-improving cycle: a capability gap, detected by the growth loop, gets a
proposed detection, which is proven, confirmed, and written back as a cited
wiki unit — so the wiki has more cited units after the cycle than before.
Each step is asserted.

## Why

The self-improving loop is the project's strongest claim — the security
library grows its own detection knowledge and the wiki records it — and a
claim that nothing verifies is a claim the next refactor silently breaks.
This test is deliberately an *integration* test, not a unit test: the proof
needs the real capability graph, the real growth loop's propose path, the
real writeback store, and the real wiki store wired together, because the
failure modes live in the seams (a proposed unit that cannot be confirmed, a
writeback that misses a citation) rather than in any one function. Using
`tmp_path` keeps the store writes off the real canonical tree.

## Interfaces

The test drives `propose_draft` / `_writeback_proven_detection` from the
growth loop, `build_gap` from the capability graph, and `list_proposed` /
`confirm_unit` from the wiki writeback layer, asserting the count of cited
units grows across the cycle.

## Gotchas

`set_proposed_dir` / `reset_proposed_dir` redirect the proposal store into
`tmp_path` so the test never writes into the real proposed-units directory,
and `set_canonical_dir` does the same for the canonical tree.
