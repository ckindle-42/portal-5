---
id: unit-HOWTO-user-roles
historical: true
kind: why
title: "HOWTO \u2014 User roles"
sources:
- type: design
  path: docs/HOWTO.md
  section: User roles
confidence: high
tags:
- docs
- HOWTO

---


| Role | Permissions |
|------|-------------|
| `pending` | Cannot use the system, waiting for approval |
| `user` | Standard access to workspaces, tools, chat |
| `admin` | Full access including user management and all settings |

**Configure default role:** Set `DEFAULT_USER_ROLE=user` in `.env` to auto-approve new signups.

---
