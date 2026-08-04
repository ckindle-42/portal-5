---
id: unit-corpus-injection-a-canned-detection-firing-on-corpus-data-t1558-004-as-rep-roasting-verbatim-spl
kind: what
title: "corpus_injection \u2014 a canned detection firing on corpus data (T1558.004\
  \ AS-REP roasting, verbatim SPL)"
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
created_at: 1784946220.585215
updated_at: 1784946220.585215
---

T1558.004 (AS-REP roasting) is one of the canned detections the injection lane
is built to feed. The detection in `spl_detections.yaml` fires on
`sourcetype="windows:security"` events that carry `EventCode=4768` and
`PreAuthType=0`. For a corpus event to match it, the loader must render the
Windows event id as a flat `EventCode=` field: `scripts/corpus_ingest.py` does
that in `windows_kv`, which flattens EVTX and Mordor JSON envelopes (where the
id lives nested at `Event.System.EventID`) into `EventCode=... Field=value`
text before shipping. A corpus event that keeps its original JSON envelope
indexes fine but matches this detection zero times.

```spl
index=portal5_lab sourcetype="windows:security" EventCode=4768 PreAuthType=0
  evidence_origin=corpus:* earliest=0 | stats count by Account
```

The trailing `evidence_origin=corpus:*` restricts the count to injected events,
and `stats ... by Account` lists the accounts the corpus proves the detection
sees — the direct evidence that Lane B lit up an existing detection without any
rule change.

## Why

The query only proves something if the loader shaped the data the way the SPL
library expects. Windows event ids arrive nested in a JSON envelope, so the
loader flattens them to `EventCode=` text rather than trusting Splunk's default
extraction — otherwise the canned detection matches zero corpus events despite
a full index. Verification is therefore not about volume but about shape.
