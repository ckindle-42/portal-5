# Follow-up: everything still open after the reasoning-group overhaul

**Date:** 2026-08-31 · **For:** offline review + planning · **Owner:** operator

This consolidates the "Remaining" / "Still open" / "Deferred" items scattered
across the four task docs plus two newly-scoped code repairs. Nothing here is
started. The 22 commits ahead of `origin/main` (see `git log origin/main..HEAD`)
are the *done* portion; this doc is the *not-done* portion.

Parent docs (context, do not duplicate):
`TASK_REASONING_GROUP_OVERHAUL_V1.md`, `TASK_OMLX_REASONING_POOL_REPAIR_V1.md`,
`TASK_ROUTER_POSTURE_GATE_V1.md`, `TASK_WEB_SEARCH_RESILIENCE_V1.md`,
`BENCH_REWIRE_PLAN_V1.md`, `PROPOSED_REASONING_OVERHAUL_V3.md`.

---

## Part A — Code work (can land before UAT resumes, except A1 which needs live verify)

### A1. Repair `portal-browser` MCP — BLOCKED, needs Docker rebuild + live smoke
`portal/modules/research/tools/browser_mcp.py` + `Dockerfile.mcp`. Currently
non-functional end to end. Three independent breaks:

1. **JSON-RPC framing.** `PlaywrightStdioClient.request()` (line ~231) writes
   `{"jsonrpc":"2.0","id":N,"method":<tool_name>,"params":<args>}` straight to
   `@playwright/mcp` stdin. The MCP stdio contract requires:
   - an `initialize` request + `notifications/initialized` notification handshake
     once per process, before any tool call;
   - tool calls wrapped as `{"method":"tools/call","params":{"name":<tool>,
     "arguments":<args>}}`;
   - response read loop that skips server log / notification lines and matches on
     `id`; tool output is in `result.content[].text` (often JSON-in-string), not
     a bare `result` dict. `_execute_tool` line ~334 (`result.get("result", result)`)
     needs to unwrap the content envelope.
2. **No Chromium in the image.** `@playwright/mcp@latest` (0.0.79+) expects
   `/ms-playwright/chromium-<rev>/chrome-linux/chrome`. `Dockerfile.mcp` never
   runs `npx playwright install --with-deps chromium` (or switch that stage to a
   `mcr.microsoft.com/playwright` base). Pin the `@playwright/mcp` version while
   here — `@latest` is why the tool names drifted.
3. **Stale tool names / arg shapes.** Current `@playwright/mcp`:
   `browser_screenshot` → `browser_take_screenshot`; `browser_fill` → `browser_type`
   (single field) or `browser_fill_form` (batch); `browser_click` takes
   `element` (human description) + `ref` (from snapshot), not `element_ref`.
   Update `TOOLS_MANIFEST` (`config/inference/tools_manifest_browser_mcp`), the
   `@mcp.tool()` wrappers, `_redact_args`, and the `browser_fill` sensitive-field
   gate in `_execute_tool`.

**Deliverables:** protocol layer rewrite + handshake; version-pinned Chromium in
`Dockerfile.mcp`; tool-name/arg map; unit tests for the framing (mock the stdio
proc, assert `initialize` precedes `tools/call`, assert content-envelope unwrap);
then `./launch.sh rebuild` + a live `curl :8923/tools/browser_navigate` and
`browser_snapshot` against a real page. **Not commit-before-UAT** — unit mocks
cannot catch the `@playwright/mcp` contract (CLAUDE.md streaming/dependency rule).

### A2. `web_fetch` → browser fallback  (`TASK_WEB_SEARCH_RESILIENCE_V1` step 1, ~1 hr, highest ROI)
Depends on A1. In `web_search_mcp.py` (or wherever `web_fetch` lives): on a
4xx / bot-challenge / empty-body response, retry the fetch via
`browser_navigate` + `browser_snapshot` against the `portal-browser` MCP
(`:8923`). Reading a known URL is the legitimate browser use case (vs. scraping
a SERP). Trigger on the challenge response, not unconditionally.

### A3. `web_search` → browser-driven search tier  (step 2, ~2–3 hr)
Depends on A1. Add a final fallback tier below Brave+SearXNG: run the query in a
persistent `portal-browser` profile (real Chrome, JS, cookies, human-ish
timing), scrape the result list from the rendered DOM. Only fires when both API
tiers return weak/empty (`_results_are_weak` already exists).

### A4. `reasoning_effort` control on `auto-reasoning?variant=deep`
`TASK_REASONING_GROUP_OVERHAUL_V1` §1. The deep variant (Qwen3.8-27B) currently
has a fixed `predict_limit`/`think:true`. Add a `reasoning_effort`
(low/medium/high) request param that maps to `predict_limit` + (for oMLX)
`chat_template_kwargs`. Plumb through `_resolve_workspace_variant` →
`_inject_ollama_options` / `_inject_omlx_options`. Small, self-contained,
unit-testable — safe to land pre-UAT.

### A5. `auto-math` / non-`auto` standard-posture harmful-intent coverage
`TASK_ROUTER_POSTURE_GATE_V1` §4 (C3). The harmful-intent gate only fires for
`workspace_id == "auto"`. A user directly selecting `auto-math` (phi4-mini,
weak on safety) bypasses it — observed producing a covert exam-cheating scheme.
**Design decision required** (do not just build): either
  (a) a lightweight refusal-posture system-prompt prefix on standard-posture
      non-`auto` spaces, or
  (b) a pre-dispatch `detect_harmful_intent()` check that runs regardless of
      selected workspace.
Risk of (b): keyword false positives break legitimate direct security-lane work.
Lean toward (a) for `auto-math`/`auto-council`/`auto-documents`; leave explicit
security lanes alone.

### A6. SearXNG hardening  (`TASK_WEB_SEARCH_RESILIENCE_V1` optional)
`config/searxng/settings.yml`: add non-blocking engines (`mojeek`, `marginalia`,
`wikipedia` direct, `wikidata`) with a custom User-Agent; raise
`search.max_request_timeout` + add a small inter-request delay so bursts look
less scraper-like. Low priority now that Brave is primary.

### A7. `auto-compliance` primary-source navigation  (step 4, workspace-level)
Give `auto-compliance` a curated authoritative-source tool, or a system-prompt
directive to `browser_navigate` the standard-body site directly
(nerc.com, hhs.gov, gdpr-info.eu, eur-lex, pcisecuritystandards.org) instead of
fuzzy search. Depends on A1. Separate from the MCP change.

---

## Part B — oMLX reasoning pool: finish the conversions  (`TASK_OMLX_REASONING_POOL_REPAIR_V1` §2)

**Root cause confirmed:** 6 model dirs under `/Volumes/data01/omlx-models/` are
0 bytes — the conversions were never completed. Health-check code fix already
shipped (`Backend.live_models`), so hollow groups now fall through to Ollama
honestly instead of black-holing; but the speed path is still missing.

Convert (or pull an existing MLX build) into each dir, tool-audit via
`/v1/chat/completions` before `supports_tools: true`, then reconcile the
`omlx-{reasoning,general,security}` `models:`/`aliases:` lists + comment blocks
in `backends.yaml` to what `:8085/v1/models` actually serves:

| Model | Serves | Priority |
|---|---|---|
| `DeepSeek-R1-0528-Qwen3-8B-4bit` | `auto-reasoning` shadow-shift | high — but no oMLX 0.6.4 tool parser for its format; may stay Ollama-only (already RETIRED from `omlx-reasoning` alias). Re-check on next oMLX release. |
| `granite-4.1-8b-mxfp8` | `auto-compliance` / `auto-documents` / blueteam | high |
| `Qwen3.6-35B-A3B-*-4bit` | `auto-creative` / pentest / (decide: `auto-data` alias?) | high |
| `VulnLLM-R-7B-4bit` | `auto-security` | medium |
| `granite-4.1-30b-4bit` | fallback tier only | low — convert only if still wanted |
| `Tongyi-DeepResearch-30B-A3B-abliterated-4bit` | fallback tier only | low |

Re-pin the DeepSeek-R1 tokenizer/tool-parser patches (`backends.yaml:~743`) in a
setup script so `brew upgrade omlx` can't silently drop them.

**Verify:** `curl :8085/v1/models` lists every `omlx-*`-aliased model; an
`auto-*` reasoning request's `x-portal-route` trace resolves to `omlx-reasoning`
not the Ollama fallback; `_update_omlx_live_models` WARN no longer fires.

---

## Part C — Bench / model-selection (deferred, sequential runs only)

### C1. `auto-reasoning` primary — diversity-weighted bench (B3)
Bench `qwen3.6:35b-a3b` vs incumbent `DeepSeek-R1-0528-Qwen3-8B` on the
reasoning persona-matrix **with model-diversity as an explicit scored
criterion**. Only promote if quality delta clearly outweighs losing the
DeepSeek lineage + the dedicated thinking specialist. Otherwise record and close
B3 for this slot. (Leaning: keep DeepSeek — it never thrashed.)

### C2. Declines + disk reclaim (~150 GB)
`scripts/model_cleanup_audit.py` → record DROPPED verdicts in
`config/PENDING_MODEL_VERDICTS.md` → `ollama rm`. **Name exact tags first:**
`granite4.1:30b-ctx16k` is live in `auto-council` (evidence reviewer) + blueteam
`reasoning_model` — do NOT sweep it with a `granite4.1:30b` decline line.
`olmo-3.1:32b-think` stays a Tier-2 bench candidate, not a decline.

### C3. cascade-2 challenger re-bench — **SUPERSEDED / do not run**
`TASK_REASONING_GROUP_OVERHAUL_V1` §2 mentioned re-checking cascade-2 with
search working. Operator decision 2026-08-31: cascade-2 fully DROPPED (worst
fabrication — invented PCI-SSC verbatim quotes + fake URLs). Model, backends
entries, `bench-cascade2-compliance` workspace, and Ollama tag all removed.
Closed.

---

## Part D — UAT / verification (after A + B land; sequential; single-user load only)

| Item | Source | Rows | Notes |
|---|---|---|---|
| Deferred-compliance baseline run on Qwen3.8-27B | REASONING §2 / AI-12 | 33 (8 spaces) | v9 baseline, **not** model selection — probes already settled it |
| A2 memory-thrash empty-capture rerun | FINDINGS_FIXLIST §A2 / AI-11 | ~26 | under the new (MoE ctx32k) config |
| v9 re-baseline | AI-26 | 8 compliance + data-class research spaces | so UAT evidence and shipped config agree |
| pentest lab-exec run | thinking-mode memory | — | confirm tool-first ("call execute_bash first") + 5-phase structure hold with `think:true` + ctx24k |
| Adaptive UAT assessment pass | AI-4 / AI-20 | — | `tests/uat_adaptive/ACTION_ITEMS.md` |
| Deep-lane co-resident eviction test | REASONING §1 | — | when `auto-reasoning?variant=deep` loads, tier-1 (`qwen3.6:35b-a3b`) must evict first; oMLX EnginePool behavior under memory pressure — needs a co-resident probe |
| Keyword-gate top-up | POSTURE_GATE §1/§2 | — | periodic refresh of `routing_harmful_intent_keywords.json` from real C1/C2 corpus rows the router-timeout window misses |
| `workspace_model: auto` persona boundary re-grade | POSTURE_GATE §3 | 12 | re-grade against the *resolved* model now that the gate + persona HARD CONSTRAINTS are in |

---

## Suggested sequencing

1. **A4** (`reasoning_effort`) + **A5 decision** — small, pre-UAT, no deps.
2. **A1** (browser MCP repair) — its own focused session with the rebuild+smoke
   round. Unblocks A2, A3, A7.
3. **Part B** (oMLX conversions) — long, mostly `mlx_lm.convert` + tool-audit;
   independent of A.
4. **A2 → A3 → A7** once A1 is verified live.
5. **Part C** benches, then **Part D** UAT, sequential, under the shipped config.
6. Push happens continuously; UAT resumes after step 4.

## Push status
22 commits on `main` ahead of `origin/main` as of this doc. Push includes all
reasoning-overhaul work + web_search cache + oMLX alias parity tests + this doc.
