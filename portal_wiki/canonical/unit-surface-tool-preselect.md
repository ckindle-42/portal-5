---
id: unit-surface-tool-preselect
kind: mixed
title: "Tool preselect \u2014 narrows the tool set before the primary call"
sources:
- type: code
  path: portal/platform/inference/tool_preselect/*.py
- type: code
  path: portal/platform/inference/tool_preselect/tests/*.py
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
- tool-preselect
created_at: 1785885400.0
updated_at: 1785885400.0
---

The tool preselector narrows the tool set before the primary call: a small
ranker model reads the user turn and keeps only the tools the query plausibly
needs, so prefill cost scales with relevance. Activation is strictly opt-in.

## Why

Preselection trades a little ranker latency for a large prefill saving, but it
changes what the model may see, so the two-level gate is a safety mechanism:
the global flag disables the feature everywhere, the per-workspace block is
explicit consent, and miss-driven auto-disable reverts a workspace the ranker
cannot serve. The never-raises contract is what makes it safe to run — the
worst case is a no-op.

## Interfaces

`config` resolves the two-level opt-in into `WorkspacePreselectConfig`;
`build_prompt` assembles the ranker prompt; `preselect` runs the ranking pass
and returns a subset with `PreselectOutcome`; `parse_ranked_indices` converts
the noisy output into validated numbers that `indices_to_tool_names` maps onto
the ordered list; `record_outcome` drives per-workspace auto-disable in `state`;
`record_preselect_call` exposes the outcome labels as Prometheus counters;
`cli_probe` replays one user turn against a live ranker; the tests pin every
fallback branch.

## Gotchas

The prompt numbers tools 1-based, so the parser's conversion to 0-based is a
silent off-by-one hazard; the k-plus-slack instruction lets the ranker
over-nominate, so more numbers than the target must be tolerated. `k` and the
confidence floor are per workspace; the probe calls real Ollama — a debugging
tool, not a benchmark.
