---
id: unit-T1047-signature
kind: mixed
title: "T1047 \u2014 WMI execution detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1047
- type: code
  path: portal/modules/security/core/exec_chain.py
claims: []
confidence: high
tags:
- T1047
- signature
- technique
- verified-v1
created_at: 1785503864.929932
updated_at: 1785503864.929932
---

# T1047 — WMI execution detection signature

## What This Detection Sees

Windows Management Instrumentation execution is tracked through the process trail it leaves on the target. The SPL flags 4688 process creation for `wmic` or the WMI provider host `WmiPrvSE`, and adds 5861 for permanent event consumer subscriptions, so both one-shot remote commands and persistent WMI weaponization are covered. Grouping by `NewProcessName` and `Account` attributes the WMI activity to an identity.

## SPL Detection

```spl
index=portal5_lab sourcetype="windows:security" (EventCode=4688 (NewProcessName="*wmic*" OR NewProcessName="*WmiPrvSE*") OR EventCode=5861) | stats count by NewProcessName, Account
```

## Expected Signal

WMI process creation or permanent WMI event subscription — the 5861 arm is what makes the query more than a process-name watch.

## Exercised By Scenarios

- `ad_full_compromise`

## Why

Pinned to the executable SPL because WMI has two distinct telemetry faces — ad-hoc command execution and persistent subscriptions — and the query encodes both as separate OR arms. Losing either arm would silently drop half the technique, so the unit mirrors the exact 4688 and 5861 shape rather than paraphrasing it.
