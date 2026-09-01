---
id: unit-T1526-signature
kind: mixed
title: "T1526 \u2014 Cloud Service Discovery \u2014 enumeration of cloud resources\
  \ via Describe/List APIs [KEY: CloudTrail Describe/List enumeration API]"
sources:
- type: spl
  path: portal/modules/security/core/siem/spl_detections.yaml#T1526
- type: mitre
  path: ATT&CK:T1526
claims: []
confidence: high
tags:
- T1526
- technique
- signature
created_at: 1788236495.0995688
updated_at: 1788236495.0995688
---

# T1526 — Cloud Service Discovery — enumeration of cloud resources via Describe/List APIs [KEY: CloudTrail Describe/List enumeration API]

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="aws:cloudtrail" (eventName="DescribeInstances" OR eventName="ListBuckets" OR eventName="DescribeVpcs" OR eventName="DescribeSecurityGroups" OR eventName="ListUsers" OR eventName="GetCallerIdentity" OR eventName="DescribeDBInstances") | stats count by eventName, userIdentity.arn, sourceIPAddress, awsRegion
```

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1526 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*
