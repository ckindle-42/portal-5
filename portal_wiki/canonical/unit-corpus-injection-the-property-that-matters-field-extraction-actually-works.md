---
id: unit-corpus-injection-the-property-that-matters-field-extraction-actually-works
kind: what
title: "corpus_injection \u2014 the property that matters: field extraction actually\
  \ works"
sources:
- type: doc
  path: docs/security/corpus_injection.md
  commit: 05e42ec2
  section: 'the property that matters: field extraction actually works'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.584824
updated_at: 1784946220.584824
---

index=portal5_lab evidence_origin=corpus:* earliest=0
  | stats count(EventCode) as with_eventcode, count as total
