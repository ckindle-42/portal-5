---
id: unit-known-limitations-v5-model-visible-corpus-retrieval-coverage
kind: what
title: "KNOWN_LIMITATIONS — V5 Model-visible Corpus Retrieval Coverage"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: d31da27a
  section: "V5 Model-visible Corpus Retrieval Coverage"
last_generated_commit: d31da27a
confidence: high
tags:
- docs
- security
created_at: 1785000000.0
updated_at: 1785000000.0
---

- **ID**: P5-SEC-CORPUS-VISIBLE-001
- **Description**: V5 attribution against the 2026-07-25 51-cell corpus replay
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
- **Operator action**: Keep production routing unchanged. For `T1611`,
  `T1558.003`, `T1053.005`, `T1550.002`, `T1047`, and `T1189`, compare the
  SPL-selected episode raw lines with the exact retriever text shown to the
  Hunter. Apply the same audit to `T1190`, `T1552.005`, `T1558.004`,
  `T1110.003`, `T1078`, and `T1557.001`, whose evidence-absent outcomes were
  honest anomalies. Cross-reference `P5-SEC-META3-001` before creating new
  scenarios or SPL variants.
