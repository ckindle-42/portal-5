---
id: unit-ADMIN_GUIDE-user-roles
kind: why
title: "ADMIN_GUIDE \u2014 User Roles"
sources:
- type: code
  path: .env.example
- type: code
  path: scripts/lib/users.sh
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1783195000.8126779
updated_at: 1783195000.8126779
---

Accounts carry one of three roles. `pending` — no access until approved; this is the default for self-registration via `DEFAULT_USER_ROLE=pending` in `.env.example`. `user` — standard access to workspaces, tools, and chat. `admin` — full access including user management and settings. The CLI accepts exactly these values: `./launch.sh add-user <email> [name] [role]`, with role options `user | admin | pending` documented in scripts/lib/users.sh. `./launch.sh list-users` prints the role column per account.

## Why

Roles are the boundary between a single-operator home box and a team deployment, and pending-by-default keeps the approval gate on unless an operator explicitly relaxes it. The CLI and the signup default agree on the same three values, so a provisioned account can never silently carry a higher privilege than the operator intended.
