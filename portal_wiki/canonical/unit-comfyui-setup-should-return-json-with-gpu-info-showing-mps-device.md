---
id: unit-comfyui-setup-should-return-json-with-gpu-info-showing-mps-device
kind: what
title: "COMFYUI_SETUP \u2014 Should return JSON with GPU info showing MPS device"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: portal/modules/media/tools/_admission.py
last_generated_commit: f28832a459fb834ed6696f953f9955694b962483
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.562077
updated_at: 1784946220.562077
---

The system statistics endpoint answers with JSON. `curl http://localhost:8188/system_stats`
returns a document that on Apple Silicon reports the MPS accelerator in the
devices array and current memory availability. Two consumers depend on that
shape: the compose health check requests the endpoint directly, and the admission
gate parses the free-RAM field out of the same response to size pre-flight
checks. Because the engine is host-native, this endpoint is the one place a
Docker-side process can read true host memory rather than its own cgroup view.

## Why

The endpoint doubles as the health probe and the admission input because it is
host truth: a containerized consumer sees real host RAM here, unlike its own
container limits. Standardizing both on one endpoint keeps the two checks in
agreement about what "free" means.
