---
id: unit-uat-routing
historical: true
kind: mixed
title: "UAT routing \u2014 slug->workspace mapping"
sources:
- type: code
  path: tests/uat/routing.py
  commit: d7dcc96a
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat

---

The persona-slug to workspace mapping and routed-model validation for the UAT driver.

## Why

The driver sends a request for a persona slug and needs to know which workspace should have served it — the mapping is the ground truth for the routing checks, kept here so the driver and the acceptance routing checks agree on how a slug resolves.

## Interfaces

`_map_slug_to_workspace` and the routed-model validation.

## Gotchas

A slug with no mapping falls back to itself — the resolution must not crash on an unknown slug.
