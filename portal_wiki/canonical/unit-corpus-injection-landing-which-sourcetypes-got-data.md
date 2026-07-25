---
id: unit-corpus-injection-landing-which-sourcetypes-got-data
kind: what
title: "corpus_injection \u2014 landing + which sourcetypes got data"
sources:
- type: doc
  path: docs/security/corpus_injection.md
  commit: 05e42ec2
  section: landing + which sourcetypes got data
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5844648
updated_at: 1784946220.5844648
---

index=portal5_lab evidence_origin=corpus:* earliest=0 | stats count by sourcetype
