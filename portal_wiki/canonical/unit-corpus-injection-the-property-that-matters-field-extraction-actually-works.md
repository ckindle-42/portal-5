---
id: unit-corpus-injection-the-property-that-matters-field-extraction-actually-works
kind: what
title: "corpus_injection \u2014 the property that matters: field extraction actually\
  \ works"
sources:
- type: code
  path: scripts/corpus_ingest.py
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.584824
updated_at: 1784946220.584824
---

The property that makes an injected corpus huntable is not that events landed,
but that the canned SPL library can extract the fields it filters on.
`spl_detections.yaml` matches on flat `EventCode=` fields (for example
`EventCode=4768` for AS-REP roasting), so a corpus event is only useful if the
loader flattened its Windows envelope into `EventCode=... Field=value` text via
`windows_kv`. Non-Windows JSON keeps its structure, which Splunk's own
extraction handles.

```spl
index=portal5_lab evidence_origin=corpus:* earliest=0
  | stats count(EventCode) as with_eventcode, count as total
```

If the two figures are close, the Windows portion of the corpus presents
identically to bench telemetry; a wide gap means the JSON-envelope trap is
still in effect and the canned detections will match nothing.

## Why

This is the acceptance check for the whole lane: the loader's job is to make
public corpus data present to Splunk the same way live bench telemetry does,
because the SPL library has exactly one expected shape. Counting events with an
extractable `EventCode` catches silent failure — events that indexed fine but
will never fire a detection — which is the failure mode a raw event count would
miss entirely.
