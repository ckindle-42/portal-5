---
id: unit-wiki-adapter-seed-security
kind: mixed
title: "Wiki security seeder \u2014 technique-signature units"
sources:
- type: code
  path: portal/platform/wiki/adapters/seed_security.py
  commit: 66aa9fda
last_generated_commit: 66aa9fda
claims: []
confidence: high
tags:
- authored-v1
- wiki
- adapter
created_at: 1785797596.483605
updated_at: 1785797596.483605
---

The security seeder generates technique-signature units from the SPL
detection library: one `unit-T<id>-signature` per technique, each citing the
detection library and documenting the technique's telemetry signature. It
also seeds the DCSync unit specifically.

## Why

The technique signatures are the security module's knowledge backbone — a
detection library is only as discoverable as the units that index it. The
seeder turns the SPL library's coverage into wiki units so an agent can look
up a technique and find its signature, data sources, and detection, cited to
the library. Seeding one unit per technique (rather than one aggregate) is
what makes each signature individually searchable and individually stale-able.

## Interfaces

`seed_technique_signatures(dry_run)` returns the signature units;
`seed_dcsync_specifically(dry_run)` returns the enriched DCSync unit.

## Gotchas

The signature ids match the machine-seeded pattern that the quality gate's
calibration excludes — these are derived, not authored, so they are not
counted as authorship.
