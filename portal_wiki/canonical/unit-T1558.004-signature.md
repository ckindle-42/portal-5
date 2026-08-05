---
id: unit-T1558.004-signature
kind: mixed
title: "T1558.004 \u2014 AS-REP roasting \u2014 Windows Security Event 4768 with pre-auth\
  \ disabled (PreAuthType 0)"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1558.004
- type: code
  path: portal/modules/security/core/exec_chain.py
last_generated_commit: 1c013743834d850604632980a093809f65c3c3ed
claims: []
confidence: high
tags:
- T1558.004
- signature
- technique
- verified-v1
created_at: 1785503864.9240892
updated_at: 1785503864.9240892
---

# T1558.004 — AS-REP roasting detection signature

## What This Detection Sees

AS-REP roasting is detected by the absence rather than the presence of a field: Kerberos authentication requests (4768) that arrive with pre-authentication disabled, `PreAuthType` 0. The SPL filters those events and groups by `Account`, flagging accounts that hand out encryptable responses without the timestamp proof.

## SPL Detection

```spl
index=portal5_lab sourcetype="windows:security" EventCode=4768 PreAuthType=0 | stats count by Account
```

## Expected Signal

Kerberos authentication without pre-authentication — the zero preauth type is the vulnerability made visible in the event stream.

## Distinguishing From Siblings

The kerberoasting sibling T1558.003 filters 4769 tickets by RC4; this unit watches 4768 requests for `PreAuthType` 0, so the event-code difference is the discriminator.

## Exercised By Scenarios

- `asrep_to_lateral`

## Why

Grounded in the executable SPL because this detection is an absence-based filter — `PreAuthType` 0 is a negative condition that prose would inevitably soften. Keeping the exact field and value preserves the precise condition the lab enforces, and the 4768-versus-4769 contrast documents how the sibling pair stays distinct.
