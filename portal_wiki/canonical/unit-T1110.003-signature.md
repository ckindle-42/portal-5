---
id: unit-T1110.003-signature
kind: mixed
title: "T1110.003 \u2014 Password spray \u2014 multiple 4625/4771 events from single\
  \ source [DISTINGUISH: T1110.003 = one password across many accounts; T1110.001\
  \ = many passwords against one account] [KEY: Many accounts, few attempts per account,\
  \ single source IP]"
sources:
- type: spl
  path: siem/spl_detections.yaml#T1110.003
- type: mitre
  path: ATT&CK:T1110.003
- type: scenario
  path: exec_chain.py#asrep_to_lateral
- type: scenario
  path: exec_chain.py#meta3_winrm_weakpass
- type: scenario
  path: exec_chain.py#meta3_ssh_brute
last_generated_commit: ''
confidence: high
tags:
- T1110.003
- technique
- signature
created_at: 1784058424.85748
updated_at: 1784058424.85748
---

# T1110.003 — Password spray — multiple 4625/4771 events from single source [DISTINGUISH: T1110.003 = one password across many accounts; T1110.001 = many passwords against one account] [KEY: Many accounts, few attempts per account, single source IP]

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="windows:security" (EventCode=4625 OR EventCode=4771) | stats dc(Account) as distinct_accounts by IpAddress | where distinct_accounts > 3
```

## Exercised By Scenarios

- `asrep_to_lateral` — target: 10.10.11.21
- `meta3_winrm_weakpass` — target: 10.10.11.10
- `meta3_ssh_brute` — target: 10.10.11.10

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| windows:security | Multiple 4625/4771 events from single source in short window |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*
