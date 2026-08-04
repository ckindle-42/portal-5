---
id: unit-T1003.001-signature
kind: mixed
title: "T1003.001 \u2014 LSASS dump detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1003.001
- type: code
  path: portal/modules/security/core/exec_chain.py
last_generated_commit: 0a5fcb6eea38bf284a96ceea702849491ba4d1c7
claims: []
confidence: high
tags:
- T1003.001
- signature
- technique
- verified-v1
created_at: 1785503864.9292989
updated_at: 1785503864.9292989
---

# T1003.001 — LSASS dump detection signature

## What This Detection Sees

Credential dumping of the Local Security Authority process shows up on Windows Security telemetry as either a dumper process being created or a handle request targeting the lsass process object. Event 4688 flags process creation where the image path matches `lsass`, `procdump`, or `comsvcs`, and event 10 fires when a process opens a handle to the lsass image. Aggregating by `NewProcessName` and `Account` lets an analyst attribute the dump to the identity that launched the tool.

## SPL Detection

```spl
index=portal5_lab sourcetype="windows:security" (EventCode=4688 (NewProcessName="*lsass*" OR NewProcessName="*procdump*" OR NewProcessName="*comsvcs*") OR EventCode=10 (TargetImage="*lsass*")) | stats count by NewProcessName, Account
```

## Expected Signal

The detection declares process access to lsass.exe for credential dumping — a handle request or dumper process rather than routine system access to the LSA process.

## Distinguishing From Siblings

This is the local memory-access sibling in the credential-dump family. T1003.003 covers NTDS.dit extraction and T1003.006 covers remote Active Directory replication, so an analyst should not conflate an on-host dumper with file or replication-based theft.

## Exercised By Scenarios

- `ad_full_compromise`

## Why

The signature is pinned to the executable SPL because the distinguishing power lives in the event-code pairing: 4688 for the dumper process and 10 for the handle request. Restating "credential dump" without those fields would lose the ability to separate a legitimate LSA access from a tool like `procdump`, which is the entire point of a signature unit. The scenario anchor in `exec_chain.py` shows where the lab exercises the technique.
