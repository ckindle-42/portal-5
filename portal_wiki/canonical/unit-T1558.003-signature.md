---
id: unit-T1558.003-signature
kind: mixed
title: "T1558.003 \u2014 Kerberoasting \u2014 Windows Security Event 4769 with RC4\
  \ encryption (TicketEncryptionType 0x17)"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1558.003
- type: code
  path: portal/modules/security/core/exec_chain.py
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- T1558.003
- signature
- technique
- verified-v1
created_at: 1785503864.9237142
updated_at: 1785503864.9237142
---

# T1558.003 — Kerberoasting detection signature

## What This Detection Sees

Kerberoasting is a single Windows event filtered on encryption type. The SPL takes ticket-service requests (4769) and keeps only those with RC4 encryption, `TicketEncryptionType` 0x17, grouping by `ServiceName` and `Account` — the offline-crackable ticket is the technique's tell.

## SPL Detection

```spl
index=portal5_lab sourcetype="windows:security" EventCode=4769 TicketEncryptionType=0x17 | stats count by ServiceName, Account
```

## Expected Signal

Kerberos service ticket requests with RC4 encryption — the encryption-type filter is the entire signature, not the ticket request itself.

## Distinguishing From Siblings

The AS-REP sibling T1558.004 uses 4768 with no pre-authentication; kerberoasting is a TGS-REQ (4769) with RC4, and conflating the two event codes is the classic miss.

## Exercised By Scenarios

- `kerberoast_to_da`
- `ad_full_compromise`
- `mission_ad_enumerate_exploit`

## Why

Pinned to the executable SPL because the encryption field is the technique in one token: an RC4 service ticket is the crackable artifact, and any prose about "service account attacks" loses that precision. The unit keeps the 0x17 encryption literal verbatim for exactly that reason.
