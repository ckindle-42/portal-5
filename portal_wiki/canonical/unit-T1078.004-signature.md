---
id: unit-T1078.004-signature
kind: mixed
title: "T1078.004 \u2014 Valid Accounts: Cloud Accounts \u2014 interactive or non-interactive\
  \ sign-in to an AWS account [KEY: CloudTrail ConsoleLogin record]"
sources:
- type: spl
  path: portal/modules/security/core/siem/spl_detections.yaml#T1078.004
- type: mitre
  path: ATT&CK:T1078.004
- type: scenario
  path: exec_chain.py#cloud_breach
claims: []
confidence: high
tags:
- T1078.004
- technique
- signature
created_at: 1788236495.098591
updated_at: 1788236495.098591
---

# T1078.004 — Valid Accounts: Cloud Accounts — interactive or non-interactive sign-in to an AWS account [KEY: CloudTrail ConsoleLogin record]

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="aws:cloudtrail" eventName="ConsoleLogin" (responseElements.ConsentLevel="fullControl" OR responseElements="" ) | stats count by userIdentity.arn, sourceIPAddress, awsRegion
```

## Exercised By Scenarios

- `cloud_breach`

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| cloud:audit | Cloud account authentication from unusual source |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*
