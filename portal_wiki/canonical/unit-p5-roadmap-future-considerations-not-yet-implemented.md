---
id: unit-p5-roadmap-future-considerations-not-yet-implemented
kind: what
title: "P5_ROADMAP \u2014 Future Considerations (Not Yet Implemented)"
sources:
- type: code
  path: portal/platform/inference/config.py
- type: code
  path: scripts/persona_intent_audit.py
- type: code
  path: portal/modules/security/core/llm_redteam.py
- type: code
  path: config/challenge_classes.yaml
- type: code
  path: portal/modules/security/core/corpus_replay_bench.py
last_generated_commit: ca0f99d64c0644df1d5fc30674b6c476fceb1a42
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.589484
updated_at: 1784946220.589484
---

This queue lists open roadmap items. Two of them are grounded in current code:
`P5-FUT-WS-FROM-MODULE` and `P5-FUT-MODEL-CHAINWALK` both hinge on
`workspace_model` in `config/personas/*.yaml` being the canonical served-model
selector that `portal/platform/inference/config.py` reads in the serving path,
while `preferred_models` is advisory metadata that is NOT consumed —
`scripts/persona_intent_audit.py` documents it as dead metadata — so a live
chain-walk over `preferred_models` does not exist.

The security rows have code anchors for their current state but no implementing
feature. `P5-FUT-RBP-LLM-SECURITY-EXPAND` would extend the OWASP LLM Top 10 probe
set in `portal/modules/security/core/llm_redteam.py`. `P5-FUT-RBP-MCP-SECURITY`
would add an MCP-compromise challenge class; `config/challenge_classes.yaml`
still marks classes `status: aspirational`. `P5-FUT-ABLATION-CAPTURE-PERSIST`
touches the corpus driver `portal/modules/security/core/corpus_replay_bench.py`,
which records verdicts but not Expert/Hunter handoffs. `P5-FUT-PROMPT-GUARD-INLINE`
has no code footprint: no input-side prompt-injection filter exists in
`portal/platform/inference/router/`.

Completed, canceled, and retired items are kept out of this queue; they live in
the referenced code and in git history.

## Why

A roadmap queue is only useful when each entry points at the code that either
absorbs it or currently stands in for it. `config.py` and `persona_intent_audit.py`
decide that `workspace_model` is canonical and `preferred_models` is dead, so
those two items are grounded; the security and prompt-guard rows have no
implementing code, so their bodies only assert the existing surface that planned
work would extend, leaving the aspirational status explicit.
