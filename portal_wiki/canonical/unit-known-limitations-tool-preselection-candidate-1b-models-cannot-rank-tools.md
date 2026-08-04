---
id: unit-known-limitations-tool-preselection-candidate-1b-models-cannot-rank-tools
kind: what
title: "KNOWN_LIMITATIONS \u2014 Tool Preselection \u2014 Candidate 1B Models Cannot\
  \ Rank Tools"
sources:
- type: code
  path: portal/platform/inference/tool_preselect/config.py
- type: code
  path: portal/platform/inference/tool_preselect/preselector.py
- type: code
  path: portal/platform/inference/tool_preselect/cli_probe.py
- type: code
  path: portal/platform/inference/tool_preselect/prompts.py
- type: code
  path: portal/platform/inference/tool_preselect/tests/test_preselector.py
- type: code
  path: portal/platform/inference/tool_preselect/tests/test_parser.py
last_generated_commit: 0a5fcb6eea38bf284a96ceea702849491ba4d1c7
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6670668
updated_at: 1784946220.6670668
---

- **ID**: P5-TOOLPRESELECT-001
- **Status**: BUILT NOT DEPLOYED — exhausted, closed.
- **Description**: `portal/platform/inference/tool_preselect/` implements query-level tool-schema preselection — a small fast model ranks a workspace's tools by relevance to the user's turn so only the top-K schemas are sent to the primary model. The module, config surface, parser, and metrics are built and unit-tested, shipped feature-flagged off (`PORTAL5_TOOL_PRESELECT=0`, default, per `config.py`; `PORTAL5_TOOL_PRESELECT_MODEL` defaults to `hf.co/openbmb/MiniCPM5-1B-GGUF:Q4_K_M`).
- **Evidence**: The candidate 1B-scale models could not rank tools reliably. Natural-language ranking prompts produced endless unrequested reasoning with no ranking; grammar-constrained JSON produced syntactically valid but semantically nonsensical rankings. Additional elicitation attempts (system-prompt framing, `think: false`, single-choice simplification, few-shot examples, and a different model lineage) all converged on the same failure — positional defaults or unreliable picks, not genuine ranking.
- **Conclusion**: No model tested at ~1-2B scale can perform this specific ranking task reliably, regardless of prompt framing, output-format constraint, or reasoning-mode control — a genuine capability gap at this scale, not a fixable prompting artifact.
- **Impact**: None on production — the feature has never been enabled on any workspace, and `preselector.py`'s fallback invariant (`subset == effective_tools` on any failure, "never raises") means even an accidental enable would degrade to a no-op, not a broken tool call.
- **Resolution path**: Revisit only with a materially larger (3B+) or purpose-built tool-ranking model. The built code is reusable as-is — only `PORTAL5_TOOL_PRESELECT_MODEL` needs to point at a model that passes the ranking task.
- **Do not** re-attempt promotion without first re-running `portal/platform/inference/tool_preselect/cli_probe.py` against the new candidate and confirming a plausible top-K ranking on multiple varied scenarios, not a single spot-check.

## Why

The whole point of preselection is a cheap model deciding which schemas the expensive model sees, so the capability gap is disqualifying at the source: a ranker that cannot rank buys nothing and risks hiding tools the primary model needs. The fallback-to-full-set invariant is what lets the feature ship disabled safely — failure degrades to the pre-feature behavior, so the module can stay built and tested until a capable candidate exists.
