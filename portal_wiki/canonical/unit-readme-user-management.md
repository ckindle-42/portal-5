---
id: unit-readme-user-management
kind: what
title: "README \u2014 User management"
sources:
- type: code
  path: scripts/lib/users.sh
- type: code
  path: launch.sh
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.682415
updated_at: 1784946220.682415
---

```bash
./launch.sh add-user alice@example.com "Alice Smith"
./launch.sh list-users
```

Both commands are implemented in `scripts/lib/users.sh` and wrap the Open WebUI
admin API. `add-user` calls `POST /api/v1/auths/add` on `OPENWEBUI_URL` (default
`http://localhost:8080`) with an admin bearer token from `get_admin_token`,
generates a temporary password, and prints the credentials for the new account
(email, password, role). The role defaults to `user` and accepts `admin` or
`pending`. `list-users` calls `GET /api/v1/users/` and prints each account with
its role, name and email. Both require the stack to be running and an admin
token to be resolvable.

## Why

User accounts are owned by Open WebUI, so the CLI does not invent its own user
store — it shells out to the same admin endpoints the UI uses, which keeps roles
and password handling consistent. Wrapping them in `launch.sh` gives an operator a
scriptable path to provision accounts without clicking through the admin panel.
