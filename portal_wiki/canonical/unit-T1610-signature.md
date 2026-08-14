---
id: unit-T1610-signature
kind: mixed
title: "T1610 \u2014 Container deploy detection signature"
sources:
- type: code
  path: portal/modules/security/core/siem/spl_detections.yaml
- type: mitre
  path: ATT&CK:T1610
claims: []
confidence: high
tags:
- T1610
- signature
- technique
- verified-v1
created_at: 1785503864.922878
updated_at: 1785503864.922878
---

# T1610 — Container deploy detection signature

## What This Detection Sees

Container deployment is observed at the daemon: Docker daemon events for container creation or start are the deploy signal. The SPL groups by host and `container_name`, so an attacker standing up an auxiliary container is visible as a distinct deployment event rather than an inferred workload.

## SPL Detection

```spl
index=portal5_lab sourcetype="docker:daemon" (create OR start) | stats count by host, container_name
```

## Expected Signal

Container creation or start events from attack activity — daemon-side events are the observability the workload itself cannot provide.

## Why

Grounded in the executable SPL because container deployment has no file artifact the host would see, so the daemon event stream is the only honest source. The unit documents that choice by pinning the create-or-start filter that the lab actually queries.
