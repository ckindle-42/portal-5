---
id: unit-ADMIN_GUIDE-first-login
kind: why
title: "ADMIN_GUIDE \u2014 First Login"
sources:
- type: code
  path: scripts/lib/util.sh
- type: code
  path: launch.sh
- type: code
  path: .env.example
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1783195000.811955
updated_at: 1783195000.811955
---

`./launch.sh up` creates `.env` from `.env.example` if absent, then `bootstrap_secrets` in scripts/lib/util.sh replaces every `CHANGEME` placeholder, printing a credentials box with the admin email and the generated `OPENWEBUI_ADMIN_PASSWORD` to the console. The account is `OPENWEBUI_ADMIN_EMAIL` (default `admin@portal.local`) and the password is written into `.env` for later retrieval. Log in at `http://localhost:8080`, or at the hostname printed when `ENABLE_REMOTE_ACCESS=true`.

## Why

First run has no UI to show credentials, so printing the generated password during bootstrap is the only channel that works before the stack is usable. Persisting the same value into `.env` means the operator can recover it later instead of losing it to scrollback, and the placeholder-repair loop regenerates any secret that was hand-broken or left at `CHANGEME`.
