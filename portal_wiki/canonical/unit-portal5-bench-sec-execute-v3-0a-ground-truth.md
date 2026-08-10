---
id: unit-portal5-bench-sec-execute-v3-0a-ground-truth
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 0a. Ground truth"
sources:
- type: code
  path: scripts/execute_preflight.py
- type: code
  path: config/portal.yaml
last_generated_commit: 0fec84d46a8898b1b5baf0508af1e25634b099af
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.7053828
updated_at: 1784946220.7053828
---

Run `python3 scripts/execute_preflight.py` before every session.
`scripts/execute_preflight.py` reads `config/portal.yaml` at runtime, collects
every `variants:` sub-key of the `auto-security` workspace into a
`security_variants` list, and prints them under "Security canonical variants
(sec-bench --workspaces targets)". It returns exit 0 with the line "No retired
aliases present. Surface is canonical. OK to run." when `check_no_retired_aliases`
finds none of `RETIRED_ALIASES` in the workspace table, and exit 1 otherwise.
Use the printed list, verbatim, as the `--workspaces` targets for the security
bench. If a variant you expect is missing, confirm against `config/portal.yaml`
`workspaces.auto-security.variants` before assuming a bug — the variant set is
config-driven and the preflight is its ground truth.

## Why

The doc's table drifted because variants are defined in exactly one place —
`config/portal.yaml` — and echoed everywhere else. The preflight exists to
print reality at run time: workspace counts, the canonical variant list, the
model-pin personas, and any retired-alias leak, so an execute agent benches
against live config rather than a baked table that has already gone stale.
