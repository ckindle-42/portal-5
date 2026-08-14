---
id: unit-corpus-injection-landing-which-sourcetypes-got-data
kind: what
title: "corpus_injection \u2014 landing + which sourcetypes got data"
sources:
- type: code
  path: scripts/corpus_ingest.py
- type: code
  path: portal/modules/security/core/siem/hec_ship.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5844648
updated_at: 1784946220.5844648
---

Because every injected event is tagged at ship time, one search tells you the
whole injection landed and how it is distributed. The loader stamps each event
`evidence_origin=corpus:<src>:<label>` and a `host=corpus-<src>` via
`ship_batch`, and maps each event onto a sourcetype in `resolve_sourcetype` —
one of the four detection sourcetypes (`windows:security`, `linux:auditd`,
`web:access`, `docker:daemon`) or a descriptive fallback.

```spl
index=portal5_lab evidence_origin=corpus:* earliest=0 | stats count by sourcetype
```

The `sourcetype` breakdown is the first thing to check after a ship: detection
sourcetypes should dominate when the source data maps well, and the tail of
descriptive fallbacks shows which corpora landed huntable-but-unmatched.

## Why

Landing is the whole game for this lane. An event that indexes under the wrong
sourcetype is invisible to the canned SPL library no matter how good the
underlying data is, so the loader's sourcetype mapping — not volume — is what
makes corpus data huntable. The breakdown query turns that property into a
visible distribution instead of a hope.
