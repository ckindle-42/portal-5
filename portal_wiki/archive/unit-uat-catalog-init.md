---
id: unit-uat-catalog-init
kind: mixed
title: "UAT catalog \u2014 assembled test-catalog package"
sources:
- type: code
  path: tests/uat_catalog/__init__.py
  commit: 832db546
last_generated_commit: 832db546
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat-catalog
created_at: 1785799949.716344
updated_at: 1785799949.716344
---

The uat_catalog package is the assembled UAT test catalog: each `g_<group>.py`
module exports a `TESTS` list for one catalog group, and the package
concatenates them in the original catalog order to expose the combined
`TEST_CATALOG`. It was split from the 11k-line inline catalog in the driver.

## Why

The catalog was a single 11k-line inline structure inside the UAT driver, and
editing it meant opening that monolith. The split makes each group a module
with a `TESTS` list, so adding a workspace's tests is creating one
`g_<workspace>.py` and appending its import — no edits to the driver. The
catalog order is significant: it is the stable pre-sort order the runner's
`sort_tests_cascade` consumes before cascade reordering, so the import order
here is a contract, not an accident.

## Interfaces

The package concatenates the group `TESTS` lists into `TEST_CATALOG` in the
import order. Adding a group means creating the module and appending its
import at the correct position.

## Gotchas

The import order equals the catalog order — a group imported in the wrong
position would silently change the pre-sort order the runner depends on.
