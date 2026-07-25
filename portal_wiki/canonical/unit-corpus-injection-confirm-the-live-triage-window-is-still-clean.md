---
id: unit-corpus-injection-confirm-the-live-triage-window-is-still-clean
kind: what
title: "corpus_injection \u2014 confirm the live triage window is still clean"
sources:
- type: doc
  path: docs/security/corpus_injection.md
  commit: 05e42ec2
  section: confirm the live triage window is still clean
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.58561
updated_at: 1784946220.58561
---

index=portal5_lab earliest=-60m evidence_origin=corpus:* | stats count
```
