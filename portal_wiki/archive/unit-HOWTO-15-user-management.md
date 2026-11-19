---
id: unit-HOWTO-15-user-management
historical: true
kind: what
title: HOWTO -- 15. User Management
sources:
- type: doc
  path: docs/HOWTO.md
  commit: 455ec2f6
  section: 15. User Management
claims: []
confidence: high
tags:
- docs
- HOWTO

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
