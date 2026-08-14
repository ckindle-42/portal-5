---
id: unit-known-limitations-v5-model-visible-corpus-retrieval-coverage
kind: what
title: "KNOWN_LIMITATIONS \u2014 V5 Model-visible Corpus Retrieval Coverage"
sources:
- type: code
  path: portal/modules/security/core/blue_orchestrate.py
- type: code
  path: portal/modules/security/core/corpus_replay_bench.py
- type: code
  path: portal/modules/security/tests/test_blue_orchestrate_toolleg.py
- type: code
  path: portal/modules/security/tests/test_corpus_replay_bench.py
claims: []
confidence: high
tags:
- docs
- resolved
- security
- verified-v1
created_at: 1785000000.0
updated_at: 1785460800
---

- **ID**: P5-SEC-CORPUS-VISIBLE-001
- **Status**: RESOLVED 2026-07-30.
- **Former issue**: Attribution against a large corpus replay found that most strong-arm non-confirms did not receive their expected technique discriminator in the persisted retriever text — the verdicts were honest (`RULED_OUT` or I8-preserving `ANOMALOUS_UNCLASSIFIED`), but the discriminating evidence never reached the model. This is a model-visible coverage finding, not proof that the underlying Splunk corpus lacks the raw event.
- **Boundary**: `corpus_replay_bench` selects each episode through the expected technique's SPL, but later retrieval could return only event-count summaries or targeted-query misses. `T1110.003` was the distinct case: `distinct_accounts` exists only in the detection's `stats dc(Account)` result, which episode construction discarded.
- **Resolution**: `_broad_retrieval_preview` in `portal/modules/security/core/blue_orchestrate.py` now returns the compact facet summary plus a bounded four-record representative preview, and targeted miss notices activate broad fallback. Correlation SPL aggregate fields are preserved alongside raw rows (see `corpus_replay_bench.py`'s aggregate-search path), so `T1110.003` carries `distinct_accounts` to the model. The corpus scenario is opaque (`corpus_replay`) so the expected technique ID is not visible in the production trigger.
- **Impact**: Confirm-only recall cannot be interpreted as a pure reasoning metric; prompting the model to confirm absent visible evidence would manufacture recall and violate invariant I8.
- **Regression proof**: A live Retriever probe against the Splunk-backed episodes returned PRESENT for every declared discriminator, and the focused retrieval/corpus/attribution tests pass.

## Why

Retrieval is the layer between raw telemetry and the reasoning model, and evidence lost there looks exactly like a reasoning failure. The audit separated raw-event presence from retriever loss so the fix could target the real gap, and the resolution keeps summaries bounded so the model gets discriminating fields without unbounded context. Preserving correlation aggregate rows closes the one case where the evidence only ever existed as a derived count.
