---
id: unit-known-limitations-tool-preselection-candidate-1b-models-cannot-rank-tools
kind: what
title: "KNOWN_LIMITATIONS \u2014 Tool Preselection \u2014 Candidate 1B Models Cannot\
  \ Rank Tools"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: "Tool Preselection \u2014 Candidate 1B Models Cannot Rank Tools"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6670668
updated_at: 1784946220.6670668
---

- **ID**: P5-TOOLPRESELECT-001
- **Status**: BUILT NOT DEPLOYED — exhausted, closed (TASK_BUILD_TOOL_PRESELECT_V1 Phase 2 gate, 2026-07-12; extended diagnostic pass same day before final halt)
- **Description**: `portal/platform/inference/tool_preselect/` implements query-level tool-schema preselection — a small fast model ranks a workspace's tools by relevance to the user's turn so only the top-K schemas are sent to the primary model. The module, config surface, parser, and metrics are built and unit-tested (54 tests, 90% coverage), shipped feature-flagged off (`PORTAL5_TOOL_PRESELECT=0`, default).
- **Evidence — initial pass (2 candidates × 2 techniques):** `hf.co/openbmb/MiniCPM5-1B-GGUF:Q4_K_M` (base) and `hf.co/ewinregirgojr/MiniCPM5-1B-Agentic-Tooluse-GGUF:Q4_K_M` (tool-tuned fine-tune). Natural-language ranking prompt: both models spent their entire token budget on unrequested reasoning and never emitted a ranking. Grammar-constrained JSON output (the same technique the production LLM workspace router uses successfully — `router/routing.py::_route_with_llm`): both produced syntactically valid but semantically nonsensical rankings (sequential counting, out-of-range indices).
- **Evidence — extended pass, before concluding the initial result was final** (5 additional theories, all on the MiniCPM5 candidates plus a third, differently-lineaged model):
  1. *System-prompt framing* ("you are a ranking function, do not reason") — MiniCPM5 ignored it and kept reasoning in its `thinking` channel regardless; still never converged within any reasonable token budget (tested to 300 tokens of pure thinking, no answer).
  2. *`think: false`* (Ollama's native reasoning-suppression option) — produces an instant answer, but a content-empty one: reordering the tool list so the correct answer moved from position 1 to position 8 still returned "1" — proof the model wasn't reading the tool list at all in this mode, just emitting a positional default.
  3. *Single-choice simplification* (pick the one best tool, not a ranked list) — same positional-default failure under `think: false`.
  4. *Few-shot in-context examples* — broke the pure positional default (stopped always answering "1") but still picked wrong answers; some genuine but unreliable engagement.
  5. *Different model lineage* — `qwen2.5:1.5b` (this project's own proven compact performer for a structurally similar task, the LLM workspace router — see `docs/ADMIN_GUIDE.md`'s Router Configuration section) scored 3/5 on trivial single-choice cases (real signal, not positional bias) but **1/5 on the actual multi-item top-K ranking task** — at or below random chance for a 3-of-10 selection. The easier single-choice framing didn't generalize to the real task.
- **Conclusion**: 3 distinct models, 7 distinct elicitation techniques, all converge on the same result — no model tested at ~1-2B scale can perform this specific ranking task reliably, regardless of prompt framing, output-format constraint, or reasoning-mode control. This is a genuine capability gap at this scale for this task, not a fixable prompting/format artifact.
- **Impact**: None on production — the feature has never been enabled on any workspace and the fallback invariant (`preselected == effective_tools` on any failure) means even a hypothetical accidental enable would degrade to a no-op, not a broken tool call.
- **Resolution path**: Revisit only with a materially larger (3B+) or purpose-built tool-ranking model — sub-2B is now empirically ruled out across three attempts, not just theorized. The built Phase 1+2 code (config, prompt builder, resilient parser, Ollama-call integration, metrics, self-healing auto-disable state) is reusable as-is — only `PORTAL5_TOOL_PRESELECT_MODEL` needs to point at a model that actually passes the ranking task.
- **Do not** re-attempt promotion without first re-running `cli_probe.py` against the new candidate and confirming a plausible top-K ranking (e.g. `web_search` ranking above `execute_bash` for an information-lookup query) on at least 5 varied scenarios, not a single spot-check.

---
