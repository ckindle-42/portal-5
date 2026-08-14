---
id: unit-T1003.003-signature
kind: mixed
title: "T1003.003 \u2014 NTDS dump detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1003.003
- type: code
  path: portal/modules/security/core/exec_chain.py
claims: []
confidence: high
tags:
- T1003.003
- signature
- technique
- verified-v1
created_at: 1785503864.929618
updated_at: 1785503864.929618
---

# T1003.003 — NTDS dump detection signature

## What This Detection Sees

Domain credential theft from the Active Directory database file is detected through Windows Security events that fire when an attacker reaches for ntds.dit. The SPL combines process creation of `ntdsutil` (4688) with the generic 4661 handle-request event and any message that names ntds.dit, which together cover extraction via `ntdsutil` and via Volume Shadow Copy. Grouping by `Account` and `NewProcessName` ties the file grab to the account that ran the tool.

## SPL Detection

```spl
index=portal5_lab sourcetype="windows:security" (EventCode=4688 (NewProcessName="*ntdsutil*") OR EventCode=4661 OR Message="*ntds.dit*") | stats count by Account, NewProcessName
```

## Expected Signal

NTDS.dit extraction via ntdsutil or Volume Shadow Copy — the detection does not rely on a single canonical event, so the three-way OR is what keeps coverage honest.

## Distinguishing From Siblings

Within the credential-dump family this unit is the file-extraction sibling: T1003.001 reads LSASS memory locally and T1003.006 replays replication rights remotely, while this signature watches the database file itself.

## Exercised By Scenarios

- `relay_to_shell`

## Why

Kept against the executable SPL because the query deliberately widens beyond `ntdsutil` to catch ntds.dit mentions anywhere in the event message, which is how shadow-copy dumps land in the lab logs. Pinning the exact 4688 and 4661 arms keeps the unit faithful to what actually runs rather than a tool-name approximation that would miss the volume-shadow-copy path.
