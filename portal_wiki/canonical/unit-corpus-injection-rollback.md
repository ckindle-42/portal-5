---
id: unit-corpus-injection-rollback
kind: what
title: "corpus_injection \u2014 Rollback"
sources:
- type: code
  path: scripts/corpus_ingest.py
- type: code
  path: portal/modules/security/core/siem/hec_ship.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5859468
updated_at: 1784946220.5859468
---

Because every injected event is tagged `evidence_origin=corpus:<src>:<label>`
and backdated, removal is surgical and never touches bench data. The loader's
own docstring documents the exact rollback search:

```
index=portal5_lab evidence_origin=corpus:* | delete
```

`| delete` requires the `can_delete` role, which the loader's docstring names
as a requirement for the rollback path. Confirm the scope before deleting —
this splits the index into what would go and what would stay:

```
index=portal5_lab earliest=0
  | eval grp=if(like(evidence_origin,"corpus:%"),"CORPUS","BENCH") | stats count by grp
```

The role grant itself is Splunk-side configuration done through the management
API with imported_roles form fields; it is not part of the loader's code.

## Why

Rollback by tag is only possible because the injection contract was set from
the start: every corpus event carries a single `evidence_origin=corpus:*`
marker and no `episode_id`, so one delete removes the whole injection while
leaving bench episodes intact. A loader that shipped untagged or episode-scoped
events would make the "rollback" a dangerous full-index delete.
