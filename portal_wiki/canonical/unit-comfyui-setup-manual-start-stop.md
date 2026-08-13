---
id: unit-comfyui-setup-manual-start-stop
kind: what
title: "COMFYUI_SETUP \u2014 Manual Start / Stop"
sources:
- type: code
  path: scripts/lib/services.sh
last_generated_commit: 75c5054f791636f367b62a1776bcc9f631794766
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5588071
updated_at: 1784946220.5588071
---

Manual start and stop are a fallback beside the auto-start agent. The generated
`~/ComfyUI/start.sh` launches the venv interpreter on the main entrypoint bound
to all interfaces on the reserved port, which is also the exact command the
launchd plist runs. Stopping manually uses the agent label, and since the plist
declares KeepAlive, the service is expected to come back after a stop; fully
unloading the agent is the way to keep it down. The installer pre-creates the
model and output folders both paths rely on.

## Why

ComfyUI runs as a host process outside the Docker lifecycle, so a foreground
script and a launchd agent are two faces of the same invocation. Manual control
exists for debugging — running `start.sh` in a terminal surfaces errors the
agent swallows into its log files — while the agent provides the login-time
resilience production needs.
