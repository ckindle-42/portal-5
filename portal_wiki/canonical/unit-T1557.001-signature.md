---
id: unit-T1557.001-signature
kind: mixed
title: "T1557.001 \u2014 LLMNR/NBT-NS poisoning detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1557.001
- type: code
  path: portal/modules/security/core/exec_chain.py
last_generated_commit: 0a5fcb6eea38bf284a96ceea702849491ba4d1c7
claims: []
confidence: high
tags:
- T1557.001
- signature
- technique
- verified-v1
created_at: 1785503864.931202
updated_at: 1785503864.931202
---

# T1557.001 — LLMNR/NBT-NS poisoning detection signature

## What This Detection Sees

Name-resolution poisoning is seen on both sides of the attack. The SPL matches Windows events that reference LLMNR or the Responder tool (including service-installation 4697 events) and adds Linux auditd execve for a responder binary, grouping by host and sourcetype so the poisoner and the poisoned are both in view.

## SPL Detection

```spl
index=portal5_lab (sourcetype="windows:security" (EventCode=4697 OR Message="*LLMNR*" OR Message="*responder*") OR (sourcetype="linux:auditd" exe="*responder*")) | stats count by host, sourcetype
```

## Expected Signal

LLMNR or NBT-NS poison activity or Responder execution on the network — the sourcetype split is deliberate because the tool runs on the attacker box while the effects show up on Windows.

## Exercised By Scenarios

- `relay_to_shell`

## Why

Grounded in the executable SPL because poisoning has two vantage points — the tool's own execution and the victim events it produces — and the query keeps both arms. Pinning that dual-sourcetype shape preserves the unit's ability to see the poisoner even when no victim event fires.
