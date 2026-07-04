---
id: unit-HOWTO-user-roles
kind: why
title: "HOWTO \u2014 User roles"
sources:
- type: design
  path: docs/HOWTO.md
  section: User roles
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.855187
updated_at: 1783195000.855187
---


| Role | Permissions |
|------|-------------|
| `pending` | Cannot use the system, waiting for approval |
| `user` | Standard access to workspaces, tools, chat |
| `admin` | Full access including user management and all settings |

**Configure default role:** Set `DEFAULT_USER_ROLE=user` in `.env` to auto-approve new signups.

---
