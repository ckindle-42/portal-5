---
id: unit-ADMIN_GUIDE-security-notes
kind: why
title: "ADMIN_GUIDE \u2014 Security Notes"
sources:
- type: design
  path: docs/ADMIN_GUIDE.md
  section: Security Notes
last_generated_commit: ''
confidence: high
tags:
- docs
- ADMIN_GUIDE
created_at: 1783195000.813386
updated_at: 1783195000.813386
---


- Generated secrets are in `.env` — never commit this file
- PIPELINE_API_KEY protects the routing API — rotate if compromised
- WEBUI_SECRET_KEY secures user sessions — rotation requires all users to re-login
- To rotate secrets: edit `.env`, restart stack
