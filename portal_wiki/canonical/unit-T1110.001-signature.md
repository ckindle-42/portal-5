---
id: unit-T1110.001-signature
kind: mixed
title: "T1110.001 \u2014 Password guessing detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1110.001
last_generated_commit: 0a5fcb6eea38bf284a96ceea702849491ba4d1c7
claims: []
confidence: high
tags:
- T1110.001
- signature
- technique
- verified-v1
created_at: 1785503864.925159
updated_at: 1785503864.925159
---

# T1110.001 — Password guessing detection signature

## What This Detection Sees

Password guessing against a single account is a counting problem. The SPL takes failed-logon events (4625) and failed pre-authentication events (4771), groups by `Account` and source IP, and keeps only account-IP pairs with more than ten failures. The threshold turns a handful of typos into a deliberate guessing run.

## SPL Detection

```spl
index=portal5_lab sourcetype="windows:security" (EventCode=4625 OR EventCode=4771) | stats count as attempt_count by Account, IpAddress | where attempt_count > 10
```

## Expected Signal

Many failed authentication attempts against one account — the `where` clause is the actual rule, not the event codes themselves.

## Distinguishing From Siblings

The spray sibling T1110.003 inverts the aggregation: it counts distinct accounts per source IP to catch one password tried across many identities, whereas this unit counts attempts per account and source pair.

## Why

Grounded in the executable SPL because the threshold and the aggregation axis are the entire signature — guessing is defined by volume against one identity. Pinning the attempt-count filter and the Account/IpAddress grouping makes the unit exact about what separates a brute force from ordinary lockout noise.
