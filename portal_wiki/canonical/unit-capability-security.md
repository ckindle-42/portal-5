---
id: unit-capability-security
kind: mixed
title: "Security MCP \u2014 vulnerability classification and lab perception"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/security/tools/security_mcp.py
claims: []
confidence: high
tags:
- capability
- mcp
- security
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# Security MCP — vulnerability classification and lab perception

## What

The Security MCP (`portal/modules/security/tools/security_mcp.py`, port 8919)
is the security module's central tool server, pipeline- and IDE-exposed and
backing the `auto-security` workspace and its variants.

## How it's used

`classify_vulnerability` maps a CVE or vulnerability description to a severity
label (low/medium/high/critical) with confidence, using a local classifier
model. `lab_perception` is a bounded live-state enumerator for the lab: it
accepts a set of hosts and returns what services are reachable, guarding so
that any host outside the lab scope is rejected before a probe leaves the box.

## Why it exists

The security surface splits cleanly into an analytical axis — severity
classification that must be local and deterministic — and an operational axis —
probing the lab, which must be strictly scoped. Keeping both behind one MCP
with a manifest-defined tool list is what lets the workspace grant them
together and lets the guard run first, always, before any network activity.

## Value

An analyst gets severity with a numeric confidence instead of a prose guess,
and lab reconnaissance is a bounded, guard-enforced operation that cannot
wander outside the authorized subnet. The two tools cover the module's most
common first questions: how bad is this, and what is the lab actually running.
