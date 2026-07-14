---
id: unit-T1558.003-signature
kind: mixed
title: "T1558.003 \u2014 Kerberoasting \u2014 Windows Security Event 4769 with RC4\
  \ encryption [DISTINGUISH: T1558.003 uses EventCode=4769 (TGS-REQ) with RC4; T1558.004\
  \ uses EventCode=4768 (AS-REQ) with no preauth] [KEY: TicketEncryptionType=0x17\
  \ in 4769 events]"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1558.003
- type: mitre
  path: ATT&CK:T1558.003
- type: scenario
  path: exec_chain.py#kerberoast_to_da
- type: scenario
  path: exec_chain.py#ad_full_compromise
- type: scenario
  path: exec_chain.py#mission_ad_enumerate_exploit
last_generated_commit: ''
confidence: high
tags:
- T1558.003
- technique
- signature
created_at: 1784058424.8564181
updated_at: 1784058424.8564181
---

# T1558.003 — Kerberoasting — Windows Security Event 4769 with RC4 encryption [DISTINGUISH: T1558.003 uses EventCode=4769 (TGS-REQ) with RC4; T1558.004 uses EventCode=4768 (AS-REQ) with no preauth] [KEY: TicketEncryptionType=0x17 in 4769 events]

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="windows:security" EventCode=4769 TicketEncryptionType=0x17 | stats count by ServiceName, Account
```

## Exercised By Scenarios

- `kerberoast_to_da` — target: 10.10.11.21
- `ad_full_compromise` — target: None
- `mission_ad_enumerate_exploit` — target: 10.10.11.21

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| windows:security | Event 4769 with TicketEncryptionType=0x17 (RC4) — Kerberoasting indicator |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*
