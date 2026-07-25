---
id: unit-corpus-injection-related
kind: what
title: "corpus_injection \u2014 Related"
sources:
- type: doc
  path: docs/security/corpus_injection.md
  commit: 05e42ec2
  section: Related
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.587966
updated_at: 1784946220.587966
---

- `scripts/lab_bots_install.py` — Lane A installer
- `scripts/lab_splunkbase_install.py` — Lane A field-extraction add-ons
- `scripts/corpus_ingest.py` — Lane B loader
- `scripts/caldera_emulate.py` — Lane C driver
- `portal/modules/security/core/siem/hec_ship.py` — the shared `ship_batch` primitive
- `portal/modules/security/core/siem/spl_detections.yaml` — the detections these lanes feed
- `docs/LAB_SETUP.md` — lab topology and target inventory
