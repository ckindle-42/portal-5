---
id: unit-T1557-signature
kind: mixed
title: "T1557 \u2014 Adversary-in-the-middle detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1557
last_generated_commit: 0a5fcb6eea38bf284a96ceea702849491ba4d1c7
claims: []
confidence: high
tags:
- T1557
- signature
- technique
- verified-v1
created_at: 1785503864.92867
updated_at: 1785503864.92867
---

# T1557 — Adversary-in-the-middle detection signature

## What This Detection Sees

Adversary-in-the-middle relay is a cross-event correlation on Windows telemetry. The SPL collects NTLM network logons (4624, `LogonType` 3) and privileged-share access (5140 on `ADMIN$` or `C$`), then evaluates them into `relay_ip` and `relay_account` aliases so the two event types share one identity axis. Only source-account pairs that produced both signal classes across more than one target host are retained.

## SPL Detection

```spl
index=portal5_lab sourcetype="windows:security" ((EventCode=4624 LogonType=3 AuthenticationPackageName="NTLM") OR (EventCode=5140 (ShareName="*\\ADMIN$" OR ShareName="*\\C$"))) | eval relay_account=coalesce(Account, SubjectUserName), relay_ip=coalesce(IpAddress, SourceAddress) | stats count(eval(EventCode=4624)) as network_logons count(eval(EventCode=5140)) as privileged_share_access dc(host) as target_count values(ShareName) as shares by relay_ip, relay_account | where network_logons>0 AND privileged_share_access>0 AND target_count>1
```

## Expected Signal

The same source and account producing NTLM network logons and privileged-share access across multiple Windows targets — the multi-target clause is what separates relay from a one-off logon.

## Distinguishing From Siblings

The poisoning sibling T1557.001 requires Responder or name-resolution evidence, and T1550.002 is NTLM authentication without the relay correlation; this unit's multi-target, two-signal requirement is its differentiator.

## Why

The unit is pinned to the executable SPL because relay is a correlation, not an event — the eval aliases that unify Account with SubjectUserName and IpAddress with SourceAddress are the load-bearing design, and the multi-target clause is what keeps it from firing on ordinary NTLM logons.
