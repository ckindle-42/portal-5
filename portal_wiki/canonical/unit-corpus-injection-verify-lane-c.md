---
id: unit-corpus-injection-verify-lane-c
kind: what
title: "corpus_injection \u2014 Verify Lane C"
sources:
- type: doc
  path: docs/security/corpus_injection.md
  commit: 05e42ec2
  section: Verify Lane C
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.587049
updated_at: 1784946220.587049
---

```
index=portal5_lab evidence_origin=live:caldera:* earliest=0
  | stats count by sourcetype, host, episode_id
```

and the same events must come back from
`SplunkBackend.query_episode(<operation_id>)`.
