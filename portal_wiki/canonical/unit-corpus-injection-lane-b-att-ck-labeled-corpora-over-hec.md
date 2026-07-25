---
id: unit-corpus-injection-lane-b-att-ck-labeled-corpora-over-hec
kind: what
title: "corpus_injection \u2014 Lane B \u2014 ATT&CK-labeled corpora over HEC"
sources:
- type: doc
  path: docs/security/corpus_injection.md
  commit: 05e42ec2
  section: "Lane B \u2014 ATT&CK-labeled corpora over HEC"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.58291
updated_at: 1784946220.58291
---

`scripts/corpus_ingest.py` reuses the existing `ship_batch` primitive — no new
HEC code — and maps events onto the four sourcetypes `spl_detections.yaml`
actually fires on, so the existing SPL library lights up with zero rule changes.

```bash
