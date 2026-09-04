---
id: unit-T1098-signature
kind: mixed
title: "T1098 \u2014 Account Manipulation \u2014 creation of credentials, users, roles,\
  \ or policies in a cloud account [KEY: CloudTrail account-manipulation API (CreateAccessKey/CreateUser/CreateRole/\u2026\
  )]"
sources:
- type: spl
  path: portal/modules/security/core/siem/spl_detections.yaml#T1098
- type: mitre
  path: ATT&CK:T1098
claims: []
confidence: high
tags:
- T1098
- technique
- signature
created_at: 1788561801.1574988
updated_at: 1788561801.1574988
---

# T1098 — Account Manipulation — creation of credentials, users, roles, or policies in a cloud account [KEY: CloudTrail account-manipulation API (CreateAccessKey/CreateUser/CreateRole/…)]

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="aws:cloudtrail" (eventName="CreateAccessKey" OR eventName="CreateUser" OR eventName="CreateLoginProfile" OR eventName="AttachUserPolicy" OR eventName="CreateRole" OR eventName="AttachRolePolicy") | stats count by eventName, userIdentity.arn, awsRegion
```

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1098 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*
