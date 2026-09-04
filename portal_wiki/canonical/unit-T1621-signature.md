---
id: unit-T1621-signature
kind: mixed
title: "T1621 \u2014 Multi-factor authentication request abuse \u2014 repeated failed\
  \ Okta MFA events [KEY: Okta MFA authentication failures repeated for one actor/source]"
sources:
- type: spl
  path: portal/modules/security/core/siem/spl_detections.yaml#T1621
- type: mitre
  path: ATT&CK:T1621
claims: []
confidence: high
tags:
- T1621
- technique
- signature
created_at: 1788561801.15693
updated_at: 1788561801.15693
---

# T1621 — Multi-factor authentication request abuse — repeated failed Okta MFA events [KEY: Okta MFA authentication failures repeated for one actor/source]

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="OktaIM2:log" eventType="user.authentication.auth_via_mfa" outcome.result="FAILURE" | stats count by actor.alternateId, client.ipAddress | where count >= 3
```

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1621 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*
