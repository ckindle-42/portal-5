---
id: unit-p5-roadmap-future-considerations-not-yet-implemented
kind: what
title: "P5_ROADMAP \u2014 Future Considerations (Not Yet Implemented)"
sources:
- type: doc
  path: P5_ROADMAP.md
  commit: 05e42ec2
  section: Future Considerations (Not Yet Implemented)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.589484
updated_at: 1784946220.589484
---

This table contains only genuinely open work. Completed, canceled, and retired
items remain available through git history and their dedicated canonical units;
they are not kept in the active queue.

| ID | Priority | Title | Status | Next decision or action |
|----|----------|-------|--------|-------------------------|
| P5-FUT-PROMPT-GUARD-INLINE | P3 | Input-side prompt-injection guardrail | OPEN | Scope an input filter under `portal/platform/inference/router/`; coordinate it with the model-layer security controls. |
| P5-FUT-WS-FROM-MODULE | P3 | Derive served workspace from `module` | DECISION NEEDED | Choose a module-level disambiguator or formally retain `workspace_model` as the canonical selector. |
| P5-FUT-MODEL-CHAINWALK | P2 | Live `preferred_models` chain-walk | OPEN | Add cached Ollama availability, bounded chain resolution, and a served-chain-position metric. |
| P5-FUT-RBP-MCP-SECURITY | P2 | MCP Security Assessment challenge class | DESIGN NEEDED | Define malicious/instrumented MCP lab fixtures and scoring for tool-layer compromise. |
| P5-FUT-RBP-LLM-SECURITY-EXPAND | P2 | Expand OWASP LLM Top 10 coverage | DESIGN NEEDED | Extend `portal/modules/security/core/llm_redteam.py` beyond the current thin probe set and replace substring-only grading. |
| P5-FUT-DISK-CLEANUP-001 | P2 | Delete confirmed-unused Ollama models | VERIFY THEN EXECUTE | Reconcile `config/UNUSED_MODELS_20260721.md` against the live loaded set before deletion. |
| P5-FUT-ABLATION-CAPTURE-PERSIST | P2 | Persist Expert/Hunter handoffs in the corpus driver | OPEN | Save each handoff beside the existing raw verdict so future model-swap studies do not require a full rerun. |
