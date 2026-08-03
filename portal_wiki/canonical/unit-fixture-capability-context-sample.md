---
id: unit-fixture-capability-context-sample
kind: mixed
title: "Capability-context fixture \u2014 D4 probe sample module"
sources:
- type: code
  path: tests/fixtures/capability_context/sample_module.py
  commit: c23c27d9
last_generated_commit: c23c27d9
claims: []
confidence: high
tags:
- authored-v1
- tests
- fixture
created_at: 1785795224.869256
updated_at: 1785795224.869256
---

This fixture module is the long-context comprehension probe's sample: the
D4 probe embeds the file ahead of the prompt and the model under test must add
one new function without disturbing the existing code. It is deliberately a
small, realistic module rather than a toy — a dataclass plus a handful of
pure functions over a user list.

## Why

A comprehension probe needs a target with enough real structure that "add a
function that fits" is a meaningful test, but small enough that the whole file
fits in the prompt window comfortably. The functions deliberately tolerate
both dict and object inputs (`isinstance(u, dict)` branches), which exercises
whether the model notices the dual-shape convention when extending the module.
The probe's scoring depends on the fixture staying stable, so it is committed
fixture data, not generated.

## Interfaces

`User` is the dataclass with name, status, and a defaulted role.
`normalize_name`, `filter_by_role`, `count_roles`, `active_names`,
`get_status_counts`, `sort_by_name`, `batch_filter`, and `create_user_batch`
are the pure functions the probe expects the model to extend.
