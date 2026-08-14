---
id: unit-security-config-reserved
kind: mixed
title: "Security config \u2014 reserved, reads shared portal.yaml"
sources:
- type: code
  path: portal/modules/security/config/__init__.py
  commit: b0aa6770
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- config
created_at: 1785795012.121069
updated_at: 1785795012.121069
---

The security module's config surface is reserved but intentionally not
populated: there is no existing isolated Python config-loader to re-export.
Security-relevant configuration — seat models, workspace routing, and
`PROMOTE_POLICY` — lives inline in the shared `config/portal.yaml` and
`config/backends.yaml`, loaded by `portal.platform.inference.config` and
`cluster_backends` alongside every other module's config, not as a
standalone security-only unit.

## Why

Building a dedicated security config loader here would be new code, not a
relocation — exactly what the structure-only slice is meant to avoid. The
config is already module-tagged in the shared files (that is how
`sync-config` routes workspaces per module), so an isolated loader would
duplicate parsing of the same YAML for no behavioral gain. The empty package
marks where a loader *would* live if security ever gained module-specific
configuration that the shared pipeline config does not already cover.

## Interfaces

No callable surface. The package exists as the documented home for a future
security config surface; today the security module's configuration is read
through the shared inference config path.
