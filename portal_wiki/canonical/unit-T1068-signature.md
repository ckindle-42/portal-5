---
id: unit-T1068-signature
kind: mixed
title: "T1068 \u2014 Exploitation for privilege escalation detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1068
claims: []
confidence: high
tags:
- T1068
- signature
- technique
- verified-v1
created_at: 1785503864.927048
updated_at: 1785503864.927048
---

# T1068 — Exploitation for privilege escalation detection signature

## What This Detection Sees

Exploitation for privilege escalation is caught by the artifact it leaves behind: an auditd EXECVE whose executable path names `exploit` or `privesc`, or whose first argument references a CVE. The query groups by host and executable. A Windows variant detects the post-exploitation recon that commonly follows, flagging `whoami` with the `/priv` switch, `systeminfo`, or CVE mentions on the process command line.

## SPL Detection

```spl
index=portal5_lab sourcetype="linux:auditd" type=EXECVE (exe="*/exploit" OR exe="*/privesc" OR a1="*CVE*") | stats count by host, exe
```

## Expected Signal

Exploit binary execution on the target host, plus privilege-escalation recon commands on Windows — the exploit artifact is the observable, not the kernel bug itself.

## Why

This unit is pinned to the executable SPL because the technique has no single canonical event — the signal is the exploit binary. Anchoring to the execve literals and the 4688 recon filters keeps the signature honest about what the lab can actually see, rather than promising kernel-level coverage the telemetry cannot support.
