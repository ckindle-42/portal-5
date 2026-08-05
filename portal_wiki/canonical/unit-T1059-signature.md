---
id: unit-T1059-signature
kind: mixed
title: "T1059 \u2014 Command execution detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1059
- type: code
  path: portal/modules/security/core/exec_chain.py
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- T1059
- signature
- technique
- verified-v1
created_at: 1785503864.922167
updated_at: 1785503864.922167
---

# T1059 — Command execution detection signature

## What This Detection Sees

Command execution on Linux is seen at the syscall layer: auditd EXECVE records for sh, bash, the Python interpreter, or perl are the payload's arrival. The primary SPL groups by host, executable, and first argument, while a Windows variant detects the same behavior through 4688 process creation for cmd, powershell, python, wscript, and cscript.

## SPL Detection

```spl
index=portal5_lab sourcetype="linux:auditd" type=EXECVE (exe=/bin/sh OR exe=/bin/bash OR exe=/usr/bin/python* OR exe=/usr/bin/perl) | stats count by host, exe, a0
```

## Expected Signal

Shell or interpreter execve events from attack payloads, plus process creation for the corresponding Windows scripting hosts — the interpreter invocation is the observable of the technique.

## Exercised By Scenarios

- `web_ssti`
- `meta3_linux_privesc`
- `meta3_elasticsearch_rce`
- `meta3_full_chain`
- `meta3_tomcat_manager`

## Why

The parent technique is deliberately broad, so the unit leans on the executable SPL to fix the exact interpreter set across two source types. Pinning the auditd executable list and the 4688 process names prevents drift between what the documentation claims and what the lab actually queries, and the scenario anchors show how many attack chains terminate in a shell.
