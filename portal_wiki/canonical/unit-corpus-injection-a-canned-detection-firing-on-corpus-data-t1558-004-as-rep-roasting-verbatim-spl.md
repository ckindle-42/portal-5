---
id: unit-corpus-injection-a-canned-detection-firing-on-corpus-data-t1558-004-as-rep-roasting-verbatim-spl
kind: what
title: "corpus_injection \u2014 a canned detection firing on corpus data (T1558.004\
  \ AS-REP roasting, verbatim SPL)"
sources:
- type: doc
  path: docs/security/corpus_injection.md
  commit: 05e42ec2
  section: a canned detection firing on corpus data (T1558.004 AS-REP roasting, verbatim
    SPL)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.585215
updated_at: 1784946220.585215
---

index=portal5_lab sourcetype="windows:security" EventCode=4768 PreAuthType=0
  evidence_origin=corpus:* earliest=0 | stats count by Account
