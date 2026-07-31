---
id: unit-known-limitations-rbp-benign-corpus-alert-fatigue
kind: what
title: "KNOWN_LIMITATIONS — RBP benign-corpus breadth and alert fatigue"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 1f216f09
  section: "RBP Benign-Corpus Breadth and Alert Fatigue"
- type: code
  path: portal/modules/security/core/benign_corpus_bench.py
- type: code
  path: portal/modules/security/core/blue_orchestrate.py
- type: code
  path: portal/modules/security/core/corpus_replay_bench.py
- type: code
  path: portal/modules/security/core/siem/spl_detections.py
- type: code
  path: portal/modules/security/tests/test_benign_corpus_bench.py
- type: code
  path: portal/modules/security/tests/test_blue_orchestrate_toolleg.py
- type: code
  path: portal/modules/security/tests/test_corpus_replay_bench.py
- type: code
  path: portal/modules/security/tests/test_spl_variants.py
- type: doc
  path: reports/RBP_BENIGN_CORPUS_20260730.md
- type: doc
  path: reports/RBP_ATTACK_GROUNDING_REGRESSION_20260730.md
last_generated_commit: 1f216f09
confidence: high
tags:
- docs
- security
- resolved
created_at: 1785067200.0
updated_at: 1785500996
---

- **ID**: P5-SEC-BENIGN-CORPUS-001
- **Status**: RESOLVED 2026-07-30 for the representative corpus.
- **Former issue**: The 2026-07-26 six-cell closeout stayed silent on only 2/6
  benign cases and emitted four `ANOMALOUS_UNCLASSIFIED` notifications:
  notification precision 33.3% and false-flag rate 66.7%.
- **Expansion**: The live negative corpus now contains twelve cells, balanced
  at four each for `windows:security`, `web:access`, and `linux:auditd`.
  Added cases cover approved scheduled-task maintenance, SCCM/WMI inventory,
  QA link checking, mTLS deployment automation, change-ticketed service
  restart, and Kubernetes CSI `nsenter`/mount reconciliation. They use the same
  HEC/index/sourcetype/provenance shape as attack corpus records, while the
  benign answer key remains outside model-visible telemetry.
- **Root cause**: Before grounding, the expanded run scored 8/12 correct
  silences, two honest anomaly false flags, and two confident wrong confirms.
  All four misses treated the mere occurrence of a dual-use ATT&CK-shaped
  primitive as malicious while ignoring explicit operational context in the
  cited record.
- **Resolution**: Shared Hunter, Expert, merged-role, and barrier-tool verdict
  contracts now require evidence of adversarial or unauthorized use in
  addition to a dual-use primitive. Change tickets, known automation/service
  identities, vendor paths, mTLS, purpose-specific agents, and coherent
  completion sequences are material counter-evidence. They are not automatic
  allow rules: an unexplained deviation or contradiction still escalates.
- **Measured proof**: The final live checkpoint produced 12/12
  `RULED_OUT`, notification precision 100%, false-flag rate 0%, zero anomaly
  flags, and zero confident wrong confirms. The full pre-grounding checkpoint
  is retained byte-for-byte for comparison.
- **Attack regression**: A fresh strong-arm replay notified on 4/5 previously
  model-visible attack cells. The non-notify was T1557 evidence containing only
  EventCode 4624 counts; its old notification depended on an invented
  EventCode 4738 and an incorrect technique description. This exposes the
  threshold-only T1557 SPL as weak evidence for the later Windows-aware SPL
  item rather than justifying a hallucinated alert.
- **T1557 follow-through (2026-07-31)**: The threshold-only rule is retired.
  The Windows rule now requires correlated NTLM network logons and privileged
  ADMIN$/C$ share access from the same source/account across more than one
  target. The old 4624-only cell is removed from the curated attack corpus,
  and the blue evidence mapper no longer treats one generic 4624 marker as
  sufficient T1557 coverage.
- **Boundary**: Twelve plausibly confusable cells remain a representative
  subset, not an exhaustive estimate of normal enterprise behavior. Broader
  hosts, identities, time windows, applications, and routine workflows remain
  unmeasured; any future NOTIFY on benign activity remains a false flag.
