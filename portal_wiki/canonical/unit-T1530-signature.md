---
id: unit-T1530-signature
kind: mixed
title: "T1530 \u2014 Data from Cloud Storage \u2014 read or copy of data held in cloud\
  \ object storage [KEY: CloudTrail S3/SecretsManager read or export API]"
sources:
- type: spl
  path: portal/modules/security/core/siem/spl_detections.yaml#T1530
- type: mitre
  path: ATT&CK:T1530
claims: []
confidence: high
tags:
- T1530
- technique
- signature
created_at: 1788236495.099267
updated_at: 1788236495.099267
---

# T1530 — Data from Cloud Storage — read or copy of data held in cloud object storage [KEY: CloudTrail S3/SecretsManager read or export API]

## Telemetry Signatures

### SPL Detection (siem/spl_detections.yaml)
```spl
index=portal5_lab sourcetype="aws:cloudtrail" (eventName="GetObject" OR eventName="ListBucket" OR eventName="GetSecretValue" OR eventName="StartExportTask") | stats count by eventName, eventSource, userIdentity.arn, sourceIPAddress
```

## Per-Source Expected Signatures

| Source | Expected Signal |
|--------|----------------|
| (generic) | Activity consistent with T1530 |

---
*Unit auto-generated from spl_detections.yaml + SCENARIOS.*
