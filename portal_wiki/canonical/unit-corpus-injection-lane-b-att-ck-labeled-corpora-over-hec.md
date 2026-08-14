---
id: unit-corpus-injection-lane-b-att-ck-labeled-corpora-over-hec
kind: what
title: "corpus_injection \u2014 Lane B \u2014 ATT&CK-labeled corpora over HEC"
sources:
- type: code
  path: scripts/corpus_ingest.py
- type: code
  path: portal/modules/security/core/siem/hec_ship.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.58291
updated_at: 1784946220.58291
---

`scripts/corpus_ingest.py` is the Lane B loader. It reuses the existing
`ship_batch` primitive from `hec_ship.py` — no new HEC code — and maps each
event onto one of the four sourcetypes `spl_detections.yaml` actually fires on
(`windows:security`, `linux:auditd`, `web:access`, `docker:daemon`) whenever
the source data supports it, so the existing SPL library lights up with zero
rule changes. Sourcetype resolution in `resolve_sourcetype` consults the corpus
manifest's declared sourcetype and source first (via `load_manifests`, for the
`data.yml` that splunk/attack_data ships beside each dataset), then the event's
Windows channel, then its field shape, and only last the file name. Everything
else keeps a descriptive sourcetype and stays huntable free-form.

```bash
python3 scripts/corpus_ingest.py --src attack_data --root /path/attack_data/datasets --ship
```

## Why

Reusing `ship_batch` instead of writing a second transport keeps Lane B
byte-compatible with bench telemetry: both go through the same HEC envelope,
the same `evidence_origin` and `episode_id` fields, and the same index. And
mapping onto the detections' own sourcetypes is what makes the canned library
fire without edits — the loader's job is to reshape public corpora into the
shape the SPL already expects, not to extend the SPL to the corpora.
