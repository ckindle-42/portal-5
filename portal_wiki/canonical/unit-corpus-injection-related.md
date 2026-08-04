---
id: unit-corpus-injection-related
kind: what
title: "corpus_injection \u2014 Related"
sources:
- type: code
  path: scripts/lab_bots_install.py
- type: code
  path: scripts/lab_splunkbase_install.py
- type: code
  path: scripts/corpus_ingest.py
- type: code
  path: scripts/caldera_emulate.py
- type: code
  path: portal/modules/security/core/siem/hec_ship.py
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.587966
updated_at: 1784946220.587966
---

The injection lanes are glued from one shared transport and one shared
detection library:

- `scripts/lab_bots_install.py` — Lane A installer (pre-indexed BOTS buckets)
- `scripts/lab_splunkbase_install.py` — Lane A field-extraction add-ons
- `scripts/corpus_ingest.py` — Lane B loader (HEC re-ship)
- `scripts/caldera_emulate.py` — Lane C driver (live emulation)
- `portal/modules/security/core/siem/hec_ship.py` — the shared `ship_batch` primitive both HEC lanes use
- `portal/modules/security/core/siem/spl_detections.yaml` — the detections these lanes feed

## Why

These are the six files that define the corpus story, and they split cleanly:
three scripts own the three lanes, one transport primitive is shared by lanes B
and C, and one detection library defines the target shape all injected data
must match. Holding the whole mechanism to six files is what keeps the
injection reversible — nothing about it lives in git beyond these.
