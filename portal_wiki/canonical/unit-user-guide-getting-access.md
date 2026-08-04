---
id: unit-user-guide-getting-access
kind: what
title: "USER_GUIDE \u2014 Getting Access"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: scripts/openwebui_init.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5134752
updated_at: 1784946220.5134752
---

Using Portal 5 requires an account. Open WebUI runs with `WEBUI_AUTH=true`, so
the interface always demands authentication, and `ENABLE_SIGNUP` defaults to true
so a login page is available for new signups. New accounts land in the `pending`
role because `DEFAULT_USER_ROLE` defaults to `pending`; an administrator must
promote the account to `user` (Admin Panel → Users) before it can chat. Until
then the account shows a pending status. An admin account is created on first
launch by `scripts/openwebui_init.py`.

## Why

Access behaviour is not a policy of this repository's docs but a consequence of
the Open WebUI environment and the bootstrap script. Anchoring these claims to
`WEBUI_AUTH`, `ENABLE_SIGNUP`, and `DEFAULT_USER_ROLE` means the unit stays true
if an operator changes the signup or approval defaults, and it documents where
the approval flow actually lives.
