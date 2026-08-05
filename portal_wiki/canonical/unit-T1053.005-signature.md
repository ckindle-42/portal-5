---
id: unit-T1053.005-signature
kind: mixed
title: "T1053.005 \u2014 Scheduled task persistence \u2014 Windows Security Event\
  \ 4698 task creation"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1053.005
- type: code
  path: portal/modules/security/core/exec_chain.py
last_generated_commit: 1c013743834d850604632980a093809f65c3c3ed
claims: []
confidence: high
tags:
- T1053.005
- signature
- technique
- verified-v1
created_at: 1785503864.925473
updated_at: 1785503864.925473
---

# T1053.005 — Scheduled task persistence detection signature

## What This Detection Sees

Scheduled task persistence is a single-event detection: the Windows Security log records the creation of a new task with 4698, and the SPL simply aggregates those events by `TaskName` and `Account`. Because the event itself is the signal, the query carries no payload matching — the interesting analysis happens downstream, identifying which account registered an unusual task.

## SPL Detection

```spl
index=portal5_lab sourcetype="windows:security" EventCode=4698 | stats count by TaskName, Account
```

## Expected Signal

New scheduled task creation events, aggregated by task name and registering account — 4698 is the entire observable.

## Exercised By Scenarios

- `kerberoast_to_da`
- `asrep_to_lateral`

## Why

This unit is pinned to the executable SPL because the technique's signature reduces to a single well-known event ID, and re-describing 4698 in prose would add nothing the query does not already carry. Keeping the aggregation fields visible shows the operator exactly how to pivot from a suspicious task to the account that planted it.
