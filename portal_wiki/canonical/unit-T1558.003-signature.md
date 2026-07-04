---
id: unit-T1558.003-signature
kind: mixed
title: "T1558.003 \u2014 Kerberoasting \u2014 Windows Security Event 4769 with RC4\
  \ encryption"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1558.003
- type: mitre
  path: ATT&CK:T1558.003
- type: scenario
  path: exec_chain.py#kerberoast_to_da
- type: scenario
  path: exec_chain.py#ad_full_compromise
last_generated_commit: ''
confidence: high
tags:
- T1558.003
- technique
- signature
created_at: 1783201357.6881468
updated_at: 1783201357.6881468
---

# T1558.003 — Kerberoasting — Windows Security Event 4769 with RC4 encryption

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="windows:security" EventCode=4769 TicketEncryptionType=0x17 | stats count by ServiceName, Account
```

## Exercised By Scenarios

- `kerberoast_to_da` — target: 10.10.11.21
- `ad_full_compromise` — target: None

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| windows:security | Event 4769 with TicketEncryptionType=0x17 (RC4) — Kerberoasting indicator |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*
