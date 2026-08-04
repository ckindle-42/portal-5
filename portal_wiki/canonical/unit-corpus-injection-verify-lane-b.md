---
id: unit-corpus-injection-verify-lane-b
kind: what
title: "corpus_injection \u2014 Verify Lane B"
sources:
- type: code
  path: scripts/corpus_ingest.py
- type: code
  path: portal/modules/security/core/siem/hec_ship.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.584086
updated_at: 1784946220.584086
---

Verifying a Lane B ship is a three-query ritual, all scoped by the
`evidence_origin=corpus:*` tag the loader stamps on every event via
`ship_batch`. First confirm the injection landed and see its sourcetype
distribution:

```spl
index=portal5_lab evidence_origin=corpus:* earliest=0 | stats count by sourcetype
```

Then confirm the field-extraction property holds — events must carry a flat
`EventCode` for the canned SPL to match:

```spl
index=portal5_lab evidence_origin=corpus:* earliest=0
  | stats count(EventCode) as with_eventcode, count as total
```

Finally, run one canned detection that the corpus should light up, such as the
T1558.004 AS-REP roasting query in `spl_detections.yaml`, and confirm it
returns results by `Account`.

## Why

Verification exists to distinguish "events indexed" from "events huntable".
Because the loader maps onto detection sourcetypes and flattens Windows
envelopes, the same three queries prove each link in that chain — landing,
extraction, and a real detection firing. A raw volume check alone would bless
an injection whose events no SPL can match.
