---
id: unit-corpus-injection-rollback
kind: what
title: "corpus_injection \u2014 Rollback"
sources:
- type: doc
  path: docs/security/corpus_injection.md
  commit: 05e42ec2
  section: Rollback
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5859468
updated_at: 1784946220.5859468
---

Because every event is tagged and backdated, removal is surgical and never
touches bench data:

```
index=portal5_lab evidence_origin=corpus:* | delete
```

`| delete` requires the `can_delete` role, which is **not** part of `admin` by
default. Grant it once:

```bash
curl -ks -u "$LAB_SPLUNK_USER:$LAB_SPLUNK_PASSWORD" \
  -X POST "$LAB_SPLUNK_URL/services/authorization/roles/admin" \
  -d imported_roles=power -d imported_roles=user -d imported_roles=can_delete
```

Confirm the scope before deleting — this splits the index into what would go and
what would stay:

```
index=portal5_lab earliest=0
  | eval grp=if(like(evidence_origin,"corpus:%"),"CORPUS","BENCH") | stats count by grp
```
