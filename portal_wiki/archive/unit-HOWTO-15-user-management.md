---
id: unit-HOWTO-15-user-management
kind: what
title: HOWTO -- 15. User Management
sources:
- type: doc
  path: docs/HOWTO.md
  commit: 455ec2f6
  section: 15. User Management
last_generated_commit: e4e79f1d894d33cf7c3dfb9340dde71bd401a6cb
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
