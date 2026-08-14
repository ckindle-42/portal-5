---
id: unit-corpus-injection-verify-lane-c
kind: what
title: "corpus_injection \u2014 Verify Lane C"
sources:
- type: code
  path: scripts/caldera_emulate.py
- type: code
  path: portal/modules/security/core/siem/spl_backend.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.587049
updated_at: 1784946220.587049
---

Verifying a Lane C run confirms both that the telemetry shipped and that it is
episode-scoped the way bench telemetry is. The events carry
`evidence_origin=live:caldera:<profile>` and the Caldera operation id as
`episode_id`, so they are findable two ways:

```spl
index=portal5_lab evidence_origin=live:caldera:* earliest=0
  | stats count by sourcetype, host, episode_id
```

and through the bench's own episode API — `SplunkBackend.query_episode` filters
on the indexed `episode_id` field, so the same events must come back from
`SplunkBackend.query_episode(<operation_id>)`. `scripts/caldera_emulate.py`
prints the operation id and the exact verification search at the end of a run.

## Why

Lane C events carrying an `episode_id` is a deliberate contract difference from
lanes A and B: it is what makes live emulation consumable by the same
blue/purple episode-scoped paths the bench uses. Verifying through
`query_episode` proves that contract held — that the shipped telemetry is
genuinely episode-scoped, not just indexed somewhere the bench would never
look.
