---
id: unit-ADMIN_GUIDE-create-users-via-cli
kind: why
title: "ADMIN_GUIDE \u2014 Create Users via CLI"
sources:
- type: code
  path: scripts/lib/users.sh
- type: code
  path: scripts/lib/util.sh
- type: code
  path: launch.sh
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1783195000.812448
updated_at: 1783195000.812448
---

`./launch.sh add-user <email> [name] [role]` invokes `_launch_add_user` in scripts/lib/users.sh, which signs in as the admin via `get_admin_token` (scripts/lib/util.sh), POSTs to Open WebUI's `/api/v1/auths/add`, and prints the generated temporary password once. Roles are `user` (default), `admin`, and `pending`. `./launch.sh list-users` calls `_launch_list_users`, GETs `/api/v1/users/`, and prints `[role] name <email>` per account. Both commands fail loudly when the stack is down.

```bash
./launch.sh add-user alice@team.local "Alice Smith"
./launch.sh add-user bob@team.local "Bob Jones" admin
./launch.sh list-users
```

## Why

The CLI exists so an operator can provision accounts without walking someone through the admin UI or sharing the admin password. Because a fresh temporary password is generated and printed per user, the invite path hands out per-account credentials rather than a single reused secret.
