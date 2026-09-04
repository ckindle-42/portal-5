---
id: unit-T1557-signature
kind: mixed
title: "T1557 \u2014 Adversary-in-the-middle \u2014 correlated NTLM network logon\
  \ and privileged-share access across multiple Windows targets [DISTINGUISH: T1557\
  \ requires multi-target correlation with privileged-share access; T1557.001 requires\
  \ name-resolution poison/Responder evidence; T1550.002 is NTLM authentication without\
  \ the relay correlation] [KEY: NTLM LogonType 3 plus ADMIN$/C$ access from the same\
  \ source/account across more than one target]"
sources:
- type: spl
  path: portal/modules/security/core/siem/spl_detections.yaml#T1557
- type: mitre
  path: ATT&CK:T1557
claims: []
confidence: high
tags:
- T1557
- technique
- signature
created_at: 1788561801.1525419
updated_at: 1788561801.1525419
---

# T1557 — Adversary-in-the-middle — correlated NTLM network logon and privileged-share access across multiple Windows targets [DISTINGUISH: T1557 requires multi-target correlation with privileged-share access; T1557.001 requires name-resolution poison/Responder evidence; T1550.002 is NTLM authentication without the relay correlation] [KEY: NTLM LogonType 3 plus ADMIN$/C$ access from the same source/account across more than one target]

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="windows:security" ((EventCode=4624 LogonType=3 AuthenticationPackageName="NTLM") OR (EventCode=5140 (ShareName="*\\ADMIN$" OR ShareName="*\\C$"))) | eval relay_account=coalesce(Account, SubjectUserName), relay_ip=coalesce(IpAddress, SourceAddress) | stats count(eval(EventCode=4624)) as network_logons count(eval(EventCode=5140)) as privileged_share_access dc(host) as target_count values(ShareName) as shares by relay_ip, relay_account | where network_logons>0 AND privileged_share_access>0 AND target_count>1
```

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1557 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*
