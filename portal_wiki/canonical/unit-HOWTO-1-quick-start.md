---
id: unit-HOWTO-1-quick-start
kind: why
title: "HOWTO \u2014 1. Quick Start"
sources:
- type: design
  path: docs/HOWTO.md
  section: 1. Quick Start
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.838752
updated_at: 1783195000.838752
---


**What:** Launch the entire platform with one command.

```bash
git clone https://github.com/ckindle-42/portal-5.git
cd portal-5
./launch.sh up
```

**First run pulls ~16 GB and takes 10–45 minutes.** When ready:

```
[portal-5] ✅ Stack is ready
[portal-5] Web UI:     http://localhost:8080
[portal-5] Grafana:    http://localhost:3000
```

**Verify:**
```bash
./launch.sh status
