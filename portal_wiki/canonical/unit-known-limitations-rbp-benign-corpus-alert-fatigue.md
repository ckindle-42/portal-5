---
id: unit-known-limitations-rbp-benign-corpus-alert-fatigue
kind: what
title: "KNOWN_LIMITATIONS — RBP benign-corpus breadth and alert fatigue"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 1f216f09
  section: "RBP Benign-Corpus Breadth and Alert Fatigue"
last_generated_commit: 1f216f09
confidence: high
tags:
- docs
- security
created_at: 1785067200.0
updated_at: 1785067200.0
---

- **ID**: P5-SEC-BENIGN-CORPUS-001
- **Description**: The 2026-07-26 closeout added six live, backdated benign
  cells (two each for `windows:security`, `web:access`, and `linux:auditd`)
  through the same HEC/index/provenance path as attack corpus data. The strong
  V4 arm correctly stayed silent on 2/6 and emitted four
  `ANOMALOUS_UNCLASSIFIED` notifications: measured notification precision
  33.3% and false-flag rate 66.7%. There were no confident wrong
  `CONFIRMED` verdicts.
- **Impact**: The scoreboard's previously blank alert-fatigue axis is now
  measured, but the result is not production-trustworthy on this negative
  subset. Honest anomaly escalation is safer than a false confirmation, yet
  each notification still consumes analyst attention.
- **Boundary**: Six plausibly confusable cells are a representative closeout
  subset, not an exhaustive sample of normal enterprise behavior. The 33.3%
  precision estimate must not be extrapolated beyond these fixtures; broader
  hosts, identities, time windows, applications, and routine administrative
  workflows remain unmeasured.
- **Resolution path**: Expand the benign corpus before changing verdict
  behavior, then use the typed false-flag breakdown to tune evidence and
  discriminator quality. Preserve the rule that any NOTIFY on benign activity
  remains a false flag, even when the verdict is an honest anomaly.
