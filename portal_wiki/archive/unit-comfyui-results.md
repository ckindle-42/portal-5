---
id: unit-comfyui-results
kind: mixed
title: "ComfyUI acceptance results \u2014 run summary writer"
sources:
- type: code
  path: tests/comfyui/results.py
  commit: 441fd2a1
last_generated_commit: 441fd2a1
claims: []
confidence: high
tags:
- authored-v1
- tests
- comfyui
created_at: 1785798963.4226549
updated_at: 1785798963.4226549
---

`results.py` writes the ComfyUI acceptance results: the elapsed time, the
git sha, and the outcome counts, as the run's summary record.

## Why

Each acceptance run needs a durable result record (what passed, what
failed, how long, against which code) that the dashboard and the operator
read. The writer produces that record in the same shape the other
acceptance packages use.

## Interfaces

`_write_results(elapsed, sha)` writes the summary dict.

## Gotchas

The git sha in the record is what ties a result to the code state that
produced it — a result without a sha cannot be audited.
