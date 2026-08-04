---
id: unit-comfyui-setup-view-logs
kind: what
title: "COMFYUI_SETUP \u2014 View logs"
sources:
- type: code
  path: scripts/lib/services.sh
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5602078
updated_at: 1784946220.5602078
---

Engine logs live under the home portal directory because the installer's launchd
plist redirects standard output and standard error to those files. `tail -f`
follows the output stream in real time, which is the practical way to watch a
generation in progress or catch a startup failure the agent swallowed. The
installer creates the log directory when it writes the plist, so the paths exist
as soon as the agent is registered. A separate error file receives the
exception stream.

## Why

A host-native agent has no container log driver to capture output, so the plist
explicitly redirects both streams to files under the portal state directory.
Naming those exact paths in the unit keeps the diagnostic step unambiguous —
watching a live stream versus reading the error file are distinct operations.
