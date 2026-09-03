---
id: unit-known-limitations-auto-rag-silent-miss
kind: what
title: "KNOWN_LIMITATIONS — Auto-RAG context injection never ran, and failed as a cache miss"
sources:
- type: code
  path: portal/platform/inference/router/context_inject.py
- type: code
  path: config/portal.yaml
  section: workspaces
- type: code
  path: tests/unit/test_rag_tool_contract.py
claims: []
confidence: high
tags:
- docs
- verified-v1
---

### Auto-RAG context injection never ran, and failed as a cache miss (RESOLVED)

- **ID**: SEAM-V1-AUTORAG-001
- **Status**: RESOLVED 2026-09-02 (TASK_RAG_COMPOSITION_SEAM_V1 P1). The feature
  is now OFF by default and the silent-failure hole is closed; re-enabling it is
  a deliberate gated choice, not a bug fix.
- **Description**: `inject_retrieved_context` dispatched `kb_search` with
  `{"query": …, "k": _TOP_K}` — **no `kb_id`**, and `k` where the tool contract
  says `top_k`. `_search` returned `{"error": "kb_id and query required"}` with
  HTTP 400. `_extract_snippets` returns `[]` for any dict containing `"error"`,
  and that branch short-circuited **before** the `ValueError`-on-unparseable
  safety net that the function's own docstring promised. So the metric recorded
  `_auto_context_inject_total{source="rag", outcome="miss"}` — indistinguishable
  from "the KB genuinely had nothing". `_AUTO_RAG_ENABLED` defaulted `true` and
  one production workspace (`auto-daily`) had `auto_rag: true`, so the capability
  was wired live and had **never once worked** — for as long as the workspace
  flag existed.
- **Why it stayed hidden**: same class as the paraphrased-traceback lesson —
  the observable signal (`outcome="miss"`) was a plausible normal state, so a
  dashboard showing all-misses looked like an empty KB, not a broken contract.
  Nothing distinguished a 400 from a legitimate zero-result search.
- **Fixes landed**:
  1. `_dispatch_outcome()` classifies an `{"error": …}` auto-context dispatch as
     a distinct `outcome="error"` with a WARNING log, for both memory and RAG
     injection — a contract mismatch is now visible, not silent.
  2. `_AUTO_RAG_ENABLED` defaults **false** (`AUTO_RAG_ENABLED=true` to opt in);
     `auto_rag` removed from `auto-daily`. This is P1 `[GATE]` option (c) — the
     honest representation of today's behaviour, since which KB a workspace
     should draw from is not settled and turning it on is a real ~52 s/turn
     latency change.
  3. The call shape is corrected (`top_k`, optional `kb_id` from a workspace
     `auto_rag_kb_id`) so it is ready when the gate is answered.
  4. `tests/unit/test_rag_tool_contract.py` locks the tool response shapes and
     asserts the injector never reintroduces the `k` / missing-`kb_id` drift.
- **Residual**: auto-RAG is a capability that has still never run in production.
  Enabling it needs the P1 `[GATE]` answered — a per-workspace `auto_rag_kb_id`
  or a deliberate route to `kb_search_all` (which carries cross-corpus exposure
  between, e.g., a security workspace and compliance content).

## Why

The failure was invisible for the same reason a paraphrased traceback was: the
signal it produced — `outcome="miss"` — is a legitimate normal state, so nothing
distinguished a broken 400 from an empty KB. Recording it here keeps the lesson
(a best-effort feature must still make a contract mismatch *visible*, and a
capability wired live is not the same as a capability that runs) attached to the
fix, and documents that "off by default" is the current honest state rather than
a regression.
