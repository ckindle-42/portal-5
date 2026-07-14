---
id: unit-T1003.006-signature
kind: mixed
title: "T1003.006 \u2014 DCSync detection signature (enriched)"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1003.006
- type: mitre
  path: ATT&CK:T1003.006
- type: design
  path: coding_task/F1/DESIGN_SEC_UNIFIED_RBP_FRAMEWORK_V3.md#R3
last_generated_commit: ''
confidence: high
tags:
- T1003.006
- DCSync
- credential-access
- enriched
created_at: 1784055842.295736
updated_at: 1784055842.295736
---

# T1003.006 — DCSync Detection Signature

## What DCSync Looks Like

DCSync uses the Directory Replication Service (DRS) to request credential
data from a domain controller. The attacker impersonates a domain controller
and calls `DRSGetNCChanges` / `DRSReplicaSync`.

## Windows Security Event 4662 — Distinguishing GUIDs

The key distinguishing feature is **Event 4662** with specific replication
access rights:

| Access Right GUID | Meaning | DCSync Indicator |
|---|---|---|
| `1131f6aa-9c07-11d1-f79f-00c04fc2dcd2` | DS-Replication-Get-Changes | **Yes** |
| `1131f6ad-9c07-11d1-f79f-00c04fc2dcd2` | DS-Replication-Get-Changes-All | **Yes** |
| `89e95b76-444d-4c62-991a-0facbeda640c` | DS-Replication-Get-Changes-In-Filtered-Set | Partial |

**Both** Get-Changes AND Get-Changes-All must be present on the same
object for a high-confidence DCSync indicator.

## SPL Detection

```spl
index=portal5_lab sourcetype="windows:security" EventCode=4662 Properties="*Replication*" | stats count by Account, Properties
```

## Common False Positives

- Domain controllers performing legitimate replication (check source is a DC)
- Azure AD Connect sync (check account name is AAD_*)
- Backup software with AD integration

## Distinguishing from Kerberoasting (T1558.003)

Kerberoasting → Event 4769 (TGS request) with RC4 encryption
DCSync → Event 4662 (directory service access) with replication GUIDs

These are fundamentally different event types and should never be confused.
