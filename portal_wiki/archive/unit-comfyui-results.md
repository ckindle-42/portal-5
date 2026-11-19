---
id: unit-comfyui-results
historical: true
kind: mixed
title: "ComfyUI acceptance results \u2014 run summary writer"
sources:
- type: code
  path: tests/comfyui/results.py
  commit: ee3590ba
claims: []
confidence: high
tags:
- authored-v1
- tests
- comfyui

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
