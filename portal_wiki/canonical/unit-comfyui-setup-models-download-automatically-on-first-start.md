---
id: unit-comfyui-setup-models-download-automatically-on-first-start
kind: what
title: "COMFYUI_SETUP \u2014 Models download automatically on first start"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: scripts/lib/services.sh
last_generated_commit: f28832a459fb834ed6696f953f9955694b962483
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5613089
updated_at: 1784946220.5613089
---

The "automatic first-start download" claim is no longer true and must not be
relied on. The compose file still defines a one-shot `comfyui-model-init`
service whose command runs a model downloader, but that script was deleted and
the container would fail at launch. The working model-fetch path is the explicit
family commands `pull-qwen-image` and `pull-wan22` implemented in
`scripts/lib/services.sh`. The init service and its volume mount remain in the
compose definition as stale scaffolding, so an operator who enables the
`docker-comfyui` profile should expect to pull models manually rather than wait
for an automatic step.

## Why

The downloader was removed because one script could not track checkpoint sources
across model families, but the compose service that invoked it was not updated at
the same time — the two files drifted. Recording that drift as a known-limitation
grounded in the actual files prevents an operator from trusting a documented
first-start promise that the code can no longer deliver.
