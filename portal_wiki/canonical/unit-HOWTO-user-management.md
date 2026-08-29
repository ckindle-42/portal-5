---
id: unit-HOWTO-user-management
kind: why
title: "HOWTO \u2014 15. User Management"
sources:
- type: code
  path: .env.example
- type: code
  path: scripts/lib/users.sh
- type: code
  path: launch.sh
claims: []
confidence: high
tags:
- HOWTO
- docs
---

**What:** Control who can sign into Open WebUI: self-registration, an approval gate, and operator-provisioned accounts.

**How:** Self-registration arrives with the `pending` role because `DEFAULT_USER_ROLE=pending` in `.env.example` is the shipped default, and a pending account has no access until an admin promotes it. Two promotion paths exist. The web path is Open WebUI's Admin Panel > Users: locate the pending account and change its role to `user`. The CLI path is `./launch.sh add-user <email> [name] [role]` with an explicit `pending` role, whose role values `scripts/lib/users.sh` documents as `user | admin | pending`. `ENABLE_SIGNUP=true` toggles whether self-registration exists at all.

## Why

Pending-by-default is the deliberate team-deployment posture: nobody gains access silently on a shared box, and every account is either approved or created by an operator. Both registration paths share the same role vocabulary, so the approval gate stays consistent whether a user self-signs or is provisioned from the shell.
