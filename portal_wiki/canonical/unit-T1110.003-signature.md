---
id: unit-T1110.003-signature
kind: mixed
title: "T1110.003 \u2014 Password spray detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1110.003
- type: code
  path: portal/modules/security/core/exec_chain.py
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- T1110.003
- signature
- technique
- verified-v1
created_at: 1785503864.924791
updated_at: 1785503864.924791
---

# T1110.003 — Password spray detection signature

## What This Detection Sees

A password spray keeps the password constant and varies the identity, so the SPL counts distinct accounts rather than attempts. Failed logon and pre-auth events are grouped by source IP, and any IP that touched more than three distinct accounts is retained — the multi-identity signature that a spray leaves behind.

## SPL Detection

```spl
index=portal5_lab sourcetype="windows:security" (EventCode=4625 OR EventCode=4771) | stats dc(Account) as distinct_accounts by IpAddress | where distinct_accounts > 3
```

## Expected Signal

Multiple failed auth events from a single IP across many accounts — the distinct-account count is the discriminator, not the raw failure volume.

## Distinguishing From Siblings

The guessing sibling T1110.001 counts attempts against one account; this unit counts accounts per source, which is how the spray's one-password-many-identities shape is preserved.

## Exercised By Scenarios

- `asrep_to_lateral`
- `meta3_winrm_weakpass`
- `meta3_ssh_brute`

## Why

The unit is pinned to the executable SPL because the distinct-count aggregate is what encodes the spray semantics — no description of "one password, many users" is as precise as the `dc(Account)` operator. Keeping the greater-than-three threshold visible lets an operator reason about tuning the detection to their environment's noise floor.
