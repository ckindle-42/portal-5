---
id: unit-readme-network-exposure
kind: what
title: "README \u2014 Network Exposure"
sources:
- type: doc
  path: README.md
  commit: 05e42ec2
  section: Network Exposure
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.690359
updated_at: 1784946220.690359
---

By default, the Portal Pipeline binds to all interfaces (`0.0.0.0:9099`) to allow LAN access from other applications. This is intentional for multi-device setups.

**Security Considerations**:
- The pipeline is protected by `PIPELINE_API_KEY` authentication
- Ensure your LAN is trusted or use firewall rules to restrict access
- For local-only deployments, set in `.env`: `PIPELINE_LISTEN_ADDR=127.0.0.1`

---
