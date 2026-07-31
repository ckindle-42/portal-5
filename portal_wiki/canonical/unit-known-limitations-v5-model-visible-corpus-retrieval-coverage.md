---
id: unit-known-limitations-v5-model-visible-corpus-retrieval-coverage
kind: what
title: "KNOWN_LIMITATIONS — V5 Model-visible Corpus Retrieval Coverage"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: d31da27a
  section: "V5 Model-visible Corpus Retrieval Coverage"
- type: code
  path: portal/modules/security/core/blue_orchestrate.py
- type: code
  path: portal/modules/security/core/corpus_replay_bench.py
- type: code
  path: portal/modules/security/tests/test_blue_orchestrate_toolleg.py
- type: code
  path: portal/modules/security/tests/test_corpus_replay_bench.py
- type: doc
  path: reports/BLUE_CORPUS_VISIBILITY_CLOSEOUT_20260730.md
last_generated_commit: d31da27a
confidence: high
tags:
- docs
- security
- resolved
created_at: 1785000000.0
updated_at: 1785460800
---

- **ID**: P5-SEC-CORPUS-VISIBLE-001
- **Status**: RESOLVED 2026-07-30.
- **Former issue**: V5 attribution against the 2026-07-25 51-cell corpus replay
  found that 12 of 14 strong-arm non-confirms did not receive the expected
  technique discriminator in their persisted retriever text. Six were honest
  RULED_OUT verdicts and six were I8-preserving ANOMALOUS_UNCLASSIFIED
  verdicts. Only two non-confirms (`T1083`, `T1552`) had their expected
  discriminator in model-visible telemetry.
- **Boundary**: This is a model-visible coverage finding, not proof that the
  underlying Splunk corpus lacks the raw event. `corpus_replay_bench` selects
  each episode through the expected technique's SPL, but later retrieval can
  return only event-count summaries or targeted-query misses. A raw-event
  versus retriever-loss audit is required before deciding whether to add corpus
  injections or fix evidence presentation.
- **Impact**: Overall confirm-only recall cannot be interpreted as a pure
  reasoning metric. Prompting the model to confirm absent visible evidence
  would manufacture recall and violate discovery invariant I8.
- **Audit result**: Eleven of the twelve affected techniques had their declared
  discriminator in raw episode rows; it was lost only at retrieval. Broad calls
  emitted count summaries, and targeted misses emitted a non-empty
  `No matching ...` notice that suppressed broadening. `T1110.003` was the
  distinct twelfth case: `distinct_accounts` exists only in the detection's
  `stats dc(Account)` result, which episode construction discarded.
- **Resolution**: Broad retrieval now returns its compact summary plus a
  four-record/4,000-character representative preview. Targeted miss notices
  activate broad fallback. Correlation SPL aggregate fields are preserved
  alongside raw rows, so `T1110.003` carries `distinct_accounts` to the model.
  The corpus scenario was also made opaque (`corpus_replay`) to remove the
  expected technique ID from the production model's trigger.
- **Regression proof**: A live `granite4.1:8b` Retriever probe against all
  twelve Splunk-backed episodes returned PRESENT for all twelve declared
  discriminators. Focused retrieval/corpus/attribution tests pass, including
  label-blindness and bounded-preview checks.
