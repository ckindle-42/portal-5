---
id: unit-ADMIN_GUIDE-security-notes
kind: why
title: "ADMIN_GUIDE \u2014 Security Notes"
sources:
- type: code
  path: .env.example
- type: code
  path: scripts/lib/util.sh
- type: code
  path: .gitignore
last_generated_commit: 863d7aa3152e7562e2d09344959c464b20eec0de
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1783195000.813386
updated_at: 1783195000.813386
---

Secrets live in `.env`, which `.gitignore` excludes and `bootstrap_secrets` in scripts/lib/util.sh populates by replacing every `CHANGEME` placeholder on first run. `PIPELINE_API_KEY` authenticates callers of the pipeline API; `WEBUI_SECRET_KEY` encrypts Open WebUI session and tool state — rotating it invalidates stored OAuth tokens and forces re-login, per the `.env.example` note. `GRAFANA_PASSWORD` and `SEARXNG_SECRET_KEY` are generated the same way. Rotation is edit `.env`, then restart the stack; `./launch.sh up` auto-repairs any secret that reverted to a placeholder. Never commit `.env`.

## Why

Secret hygiene is automated here because a shared default is the realistic failure: every secret starts as `CHANGEME` and is replaced at first run, so the residual risk is operator error — committing `.env` or hand-setting a weak value — which the gitignore and the placeholder-repair loop directly counter. Knowing which key guards what matters when a rotation is needed.
