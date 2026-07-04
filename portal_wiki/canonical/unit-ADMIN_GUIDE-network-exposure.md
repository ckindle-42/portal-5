---
id: unit-ADMIN_GUIDE-network-exposure
kind: why
title: "ADMIN_GUIDE \u2014 Network Exposure"
sources:
- type: design
  path: docs/ADMIN_GUIDE.md
  section: Network Exposure
last_generated_commit: ''
confidence: high
tags:
- docs
- ADMIN_GUIDE
created_at: 1783195000.8136199
updated_at: 1783195000.8136199
---


Portal 5 is designed for single-machine local use. Open WebUI binds to `127.0.0.1` by default and is only reachable from `localhost`. All MCP servers (8910–8923) are always 127.0.0.1-bound and never reach the network directly.
