---
id: unit-HOWTO-15-user-management
kind: what
title: HOWTO -- 15. User Management
sources:
- type: doc
  path: docs/HOWTO.md
  commit: ddb1cc61
  section: 15. User Management
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- HOWTO
created_at: 1784944767.909774
updated_at: 1784944767.909774
---

## Approve Pending Users
1. Admin Panel > Users
2. Find users with "pending" role
3. Click the user > set role to "user"

## Create Users via CLI
```bash
./launch.sh add-user alice@team.local "Alice Smith"
./launch.sh add-user bob@team.local "Bob Jones" admin
./launch.sh list-users
```

## User Roles
- `pending` -- cannot use the system, waiting for approval
- `user` -- standard access to workspaces, tools, chat
- `admin` -- full access including user management and all settings
