---
id: unit-known-limitations-rbp-benign-corpus-alert-fatigue
kind: what
title: "KNOWN_LIMITATIONS \u2014 RBP benign-corpus breadth and alert fatigue"
sources:
- type: code
  path: portal/modules/security/core/benign_corpus_bench.py
- type: code
  path: portal/modules/security/core/blue_orchestrate.py
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: code
  path: portal/modules/security/tests/test_benign_corpus_bench.py
- type: code
  path: portal/modules/security/tests/test_blue_orchestrate_toolleg.py
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- docs
- resolved
- security
- verified-v1
created_at: 1785067200.0
updated_at: 1785500996
---

- **ID**: P5-SEC-BENIGN-CORPUS-001
- **Status**: RESOLVED 2026-07-30 for the representative corpus.
- **Former issue**: An early benign-corpus closeout stayed silent on only part of the benign cases and emitted `ANOMALOUS_UNCLASSIFIED` notifications for the rest, producing a notification-precision and false-flag problem. The evaluation scaffolding lives in `portal/modules/security/core/benign_corpus_bench.py`, which generates live benign negatives and scores alert fatigue against a retained attack corpus.
- **Expansion**: The live negative corpus now contains twelve cells, balanced across `windows:security`, `web:access`, and `linux:auditd`. Added cases cover approved scheduled-task maintenance, SCCM/WMI inventory, QA link checking, mTLS deployment automation, change-ticketed service restart, and Kubernetes CSI `nsenter`/mount reconciliation (all visible in `benign_corpus_bench.py`'s record patterns). They use the same HEC/index/sourcetype/provenance shape as attack corpus records, while the benign answer key stays outside model-visible telemetry.
- **Root cause**: Misses treated the mere occurrence of a dual-use ATT&CK-shaped primitive as malicious while ignoring explicit operational context in the cited record.
- **Resolution**: The shared verdict contracts in `portal/modules/security/core/blue_orchestrate.py` now require evidence of adversarial or unauthorized use in addition to a dual-use primitive. Change tickets, known automation/service identities, vendor paths, mTLS, purpose-specific agents, and coherent completion sequences are material counter-evidence — not automatic allow rules: an unexplained deviation still escalates.
- **Measured proof**: The final live checkpoint produced `RULED_OUT` for every benign cell with zero anomaly flags. The pre-grounding checkpoint is retained byte-for-byte for comparison.
- **T1557 follow-through**: The threshold-only T1557 rule is retired in `portal/modules/security/core/siem/spl_detections.yaml`; the Windows rule now requires correlated NTLM network logons and privileged ADMIN$/C$ share access from the same source/account across more than one target.
- **Boundary**: Twelve plausibly confusable cells remain a representative subset, not an exhaustive estimate of normal enterprise behavior. Broader hosts, identities, time windows, applications, and routine workflows remain unmeasured; any future NOTIFY on benign activity remains a false flag.

## Why

Alert-fatigue evaluation must use plausibly confusable benign telemetry, not obviously-safe records, or it overstates precision. The corpus generator reuses the attack record's transport shape so the only difference from an attack is the operational context the verdict contract must weigh; the resolution hardening — requiring adversarial evidence, not just a dual-use primitive — is what makes a benign case a true negative instead of an anomaly.
