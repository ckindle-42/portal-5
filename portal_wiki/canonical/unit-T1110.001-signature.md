---
id: unit-T1110.001-signature
kind: mixed
title: "T1110.001 \u2014 Password guessing \u2014 repeated authentication failures\
  \ against one account [DISTINGUISH: T1110.001 = many passwords against one account;\
  \ T1110.003 = one password across many accounts] [KEY: Many attempts against one\
  \ account]"
sources:
- type: spl
  path: portal/modules/security/core/siem/spl_detections.yaml#T1110.001
- type: mitre
  path: ATT&CK:T1110.001
last_generated_commit: ''
confidence: high
tags:
- T1110.001
- technique
- signature
created_at: 1785503864.925159
updated_at: 1785503864.925159
---

# T1110.001 — Password guessing — repeated authentication failures against one account [DISTINGUISH: T1110.001 = many passwords against one account; T1110.003 = one password across many accounts] [KEY: Many attempts against one account]

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="windows:security" (EventCode=4625 OR EventCode=4771) | stats count as attempt_count by Account, IpAddress | where attempt_count > 10
```

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1110.001 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*
