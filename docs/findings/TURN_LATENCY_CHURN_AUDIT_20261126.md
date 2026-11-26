# Turn-latency & model-churn audit — QAT release_1_0_20261126T140220Z (2026-11-26)

Whole-system breakdown of where turn time went during the QAT run at git `cfe67a16e`, from the
pipeline container log, `~/.omlx/logs/server.log*`, `/opt/homebrew/var/log/ollama.log*`, and the
run's `results.jsonl` + screenshot anchors. No inference requests were sent; all numbers are
read from logs of the live run.

**Run window analysed:** 2026-11-26 08:02:20–08:42:31 CST (14:02:20–14:42:31Z), the first 52
rows (stages p0 → s2-p1 → s5). The run continued afterwards (s5-compliance-multiframework FAIL
449.3 s, s2-p2-auto-research WARN "slow seat: 302s", then the pipeline container was restarted
at 09:12:50 CST and the remaining 180 rows are BLOCKED "blocked by inter-phase gate failure").
The pipeline's docker log for the analysed window was captured before that restart; the
load_guard/routing facts quoted here are preserved verbatim in
`coding_task/TURN_LATENCY_AUDIT_EVIDENCE/PIPELINE_LOG_FACTS.md`.

**Clock note:** engine logs are local (CST, UTC−6); pipeline log is UTC. Local times are used below.

---

## Q1 — Where turn time goes (per row)

Method: scenario windows reconstructed from `results.jsonl` order + `duration_s`, anchored on
screenshot mtimes (18 anchors, all consistent with the chain). Components attributed from:
oMLX `Chat completion:` lines (prompt tokens, `stream_model_ttft`, tokens, tok/s — model named),
Ollama `slot print_timing` blocks paired to `[GIN] POST /api/chat` durations and attributed to
models via pipeline routing-line timestamps, load_guard `waiting for engine activity` spans and
`cold load admitted … waited_s`, oMLX `Loading model:`→`Loaded model:` and Ollama
`loading model via llama-server`→`loaded runners` pairs, and task-router (Layer-1 LLM
classifier) `Non-stream routing`→`Backend … succeeded` spans. **Residual** = row duration minus
the components: OWUI browser/UI time, tool execution (sandbox, MCP, media engines), harness
grading, and stream post-processing — it is not one number and cannot be split further from
these logs.

| scenario | status | dur s | router s | queue s | load s | prefill s (tok) | decode s (tok) | LLM calls | residual s |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| p0-execute-preflight | PASS | 0.4 | 0.0 | 0.0 | 0.0 | 2.4 (1881) | 0.4 (22) | 1 | -2.4 |
| p0-exposure-gap | PASS | 0.3 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 0.0 (0) | 0 | 0.3 |
| p0-lab-ready | PASS | 3.1 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 0.0 (0) | 0 | 3.1 |
| p0-load-guard | PASS | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 0.0 (0) | 0 | 0.0 |
| p0-portal-trace | WARN | 7.2 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 0.0 (0) | 0 | 7.2 |
| p0-retired-aliases | PASS | 0.3 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 0.0 (0) | 0 | 0.3 |
| p0-routing-baseline | PASS | 4.7 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 0.0 (0) | 0 | 4.7 |
| p0-sweep-freshness | PASS | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 0.0 (0) | 0 | 0.0 |
| s1-hardening | PASS | 0.2 | 0.0 | 0.0 | 0.0 | 0.0 (0) | 0.0 (0) | 0 | 0.2 |
| s5-route-kubernetes-rbac | FAIL | 313.1 | 7.5 | 0.0 | 6.2 | 103.9 (23023.0) | 221.1 (5649) | 3 | -25.7 |
| s5-route-tls-firewall | PASS | 84.6 | 34.3 | 26.2 | 14.8 | 5.8 (4335.0) | 5.0 (243) | 2 | -1.5 |
| s5-route-math-integral | PASS | 89.9 | 8.5 | 0.0 | 13.1 | 1.2 (706.0) | 53.8 (2413) | 3 | 13.3 |
| s5-daily-out-of-lane | PASS | 75.4 | 6.9 | 0.0 | 17.1 | 12.1 (8567.0) | 22.6 (1215) | 2 | 16.8 |
| s5-daily-everyday-no-suggestion | PASS | 30.2 | 2.6 | 0.0 | 0.0 | 5.5 (4278.0) | 8.0 (442) | 2 | 14.1 |
| s5-persona-clarify-agentorchestrator | PASS | 35.1 | 2.7 | 0.0 | 8.1 | 1.5 (11379.0) | 9.8 (267) | 2 | 13.0 |
| s5-persona-destructive-agentorchestrator | FAIL | 77.0 | 3.2 | 0.0 | 0.0 | 1.2 (11579.0) | 59.8 (1387) | 2 | 12.8 |
| s5-sandbox-python-bash-network-isolation | PASS | 72.2 | 7.5 | 0.0 | 7.2 | 17.0 (5166.0) | 25.2 (889) | 5 | 15.4 |
| s5-documents-office-content | PASS | 38.0 | 2.8 | 0.0 | 10.3 | 1.7 (3554.0) | 7.7 (453) | 3 | 15.5 |
| s2-p1-auto | PASS | 30.5 | 0.0 | 0.0 | 19.1 | 5.0 (3845.0) | 2.7 (151) | 1 | 3.6 |
| s2-p1-ui-roster | PASS | 41.7 | 2.4 | 0.0 | 0.0 | 6.3 (4408.0) | 11.2 (621) | 5 | 21.8 |
| s2-p1-auto-audio | PASS | 20.4 | 0.0 | 0.0 | 5.0 | 2.3 (627.0) | 11.1 (326) | 1 | 2.0 |
| s2-p1-auto-audio::image | PASS | 8.3 | 0.0 | 0.0 | 3.5 | 2.7 (902.0) | 1.1 (43) | 1 | 1.0 |
| s2-p1-auto-audio::music | PASS | 6.3 | 0.0 | 0.0 | 3.5 | 1.0 (1723.0) | 1.0 (147) | 1 | 0.8 |
| s2-p1-auto-audio::video | PASS | 6.3 | 0.0 | 0.0 | 0.8 | 2.1 (707.0) | 1.4 (50) | 1 | 2.0 |
| s2-p1-auto-coding | PASS | 18.4 | 0.0 | 0.0 | 7.4 | 6.2 (10846) | 4.4 (102) | 1 | 0.4 |
| s2-p1-auto-coding::bigfix | FAIL | 127.5 | 0.0 | 0.0 | 6.2 | 1.3 (981) | 118.1 (8192) | 1 | 1.9 |
| s2-p1-auto-coding::cad | PASS | 52.7 | 0.0 | 0.0 | 1.2 | 17.8 (37790) | 24.7 (1393) | 4 | 9.0 |
| s2-p1-auto-compliance | PASS | 70.8 | 0.0 | 0.0 | 7.4 | 58.3 (7132) | 3.6 (133) | 1 | 1.5 |
| s2-p1-auto-compliance::reading | PASS | 10.3 | 0.0 | 0.0 | 8.1 | 0.0 (0) | 0.0 (0) | 0 | 2.2 |
| s2-p1-auto-daily | PASS | 34.6 | 0.0 | 0.0 | 20.6 | 5.8 (8291.0) | 4.3 (239) | 2 | 3.8 |
| s2-p1-auto-daily::deep | PASS | 18.5 | 0.0 | 0.0 | 8.7 | 2.3 (3298) | 3.8 (121) | 1 | 3.7 |
| s2-p1-auto-daily::fast | PASS | 28.6 | 0.0 | 0.0 | 11.7 | 14.2 (13164) | 0.5 (27) | 1 | 2.2 |
| s2-p1-auto-daily::inkling | PASS | 26.6 | 0.0 | 0.0 | 0.8 | 1.0 (1108.0) | 0.4 (24) | 1 | 24.5 |
| s2-p1-auto-daily::nemotron | PASS | 28.6 | 0.0 | 0.0 | 21.7 | 2.5 (1783.0) | 1.0 (55) | 1 | 3.5 |
| s2-p1-auto-documents | PASS | 12.4 | 0.0 | 0.0 | 8.8 | 0.0 (0) | 0.0 (0) | 0 | 3.6 |
| s5-documents-upload-readback-rag | PASS | 45.0 | 6.6 | 0.0 | 8.0 | 5.3 (8989.0) | 5.7 (369) | 7 | 19.3 |
| s2-p1-auto-general-uncensored | PASS | 18.4 | 0.0 | 0.0 | 7.9 | 0.2 (1541) | 7.0 (235) | 1 | 3.3 |
| s2-p1-auto-reasoning | PASS | 22.5 | 0.0 | 0.0 | 18.4 | 0.2 (60.0) | 0.6 (28) | 1 | 3.2 |
| s2-p1-auto-reasoning::math | PASS | 32.6 | 0.0 | 0.0 | 16.4 | 0.3 (167.0) | 12.3 (631) | 1 | 3.5 |
| s2-p1-auto-research | PASS | 34.6 | 0.0 | 0.0 | 17.4 | 3.1 (2378.0) | 11.4 (613) | 3 | 2.7 |
| s2-p1-auto-security | PASS | 22.5 | 0.0 | 0.0 | 8.8 | 7.8 (3782) | 4.5 (133) | 1 | 1.3 |
| s2-p1-auto-spl | PASS | 50.8 | 0.0 | 0.0 | 9.0 | 37.3 (4541) | 1.0 (22) | 1 | 3.5 |
| s2-p1-auto-vision | PASS | 69.0 | 0.0 | 0.0 | 22.2 | 26.8 (2202.0) | 18.1 (196) | 1 | 1.9 |
| s2-p1-security-reviewer | PASS | 10.3 | 0.0 | 0.0 | 3.5 | 5.6 (1807.0) | 0.7 (26) | 1 | 0.4 |
| s5-media-image-quality | PASS | 65.7 | 27.7 | 0.0 | 2.3 | 6.4 (3003.0) | 13.9 (301) | 5 | 15.4 |
| s5-media-video-duration | PASS | 127.7 | 22.1 | 0.0 | 0.0 | 10.3 (2452.0) | 37.3 (553) | 10 | 57.9 |
| s5-media-music-audio | FAIL | 59.9 | 4.5 | 0.0 | 3.8 | 1.2 (1911.0) | 14.7 (1058) | 4 | 35.7 |
| s5-media-tts-speech | PASS | 99.2 | 6.0 | 0.0 | 0.0 | 2.1 (2193.0) | 29.1 (2112) | 5 | 62.0 |
| s5-media-voice-clone | PASS | 75.9 | 4.0 | 0.0 | 0.0 | 1.8 (1405.0) | 24.3 (1946) | 4 | 45.8 |
| s5-media-stt-accuracy | WARN | 61.0 | 3.0 | 0.0 | 6.3 | 6.1 (1693.0) | 20.4 (507) | 3 | 25.2 |
| s5-memory-cross-session | PASS | 92.3 | 7.5 | 0.0 | 22.6 | 6.1 (4123.0) | 29.1 (1620) | 5 | 26.9 |
| s5-security-hunt-workflow | FAIL | 98.1 | 0.0 | 0.0 | 14.3 | 12.3 (5112.0) | 25.0 (878) | 16 | 46.4 |
| **TOTAL (52 rows)** | | **2359** | **160** | **26** | **372** | **414 (218432)** | **858 (35832)** | | **529** |

Run totals (52 rows, 2 359 s wall; every engine event counted exactly once, attributed by start time):

| component | seconds | share of run wall | notes |
|---|---:|---:|---|
| decode (generation) | 858 | 36 % | 35 832 generated tokens on main-model calls |
| prefill (prompt eval) | 414 | 18 % | 218 432 prompt tokens — **6.1 prompt tokens per generated token** |
| model loads | 372 (attributed) / 416 (engine-measured: 20 oMLX loads 143.7 s + 50 Ollama loads 272.8 s) | 16–18 % | 70 cold loads in 40 minutes |
| Layer-1 classifier | 160 | 7 % | 59 in-window calls, median 1.6 s, all on gemma-4-E4B-ctx2k (its own prefill+decode included) |
| headroom/queue wait | 26 | 1 % | one 25.5 s span (see Q2); smaller guard `waited_s` (≤2.5 s) are inside the load column |
| residual (UI, tools, media, grading) | 529 | 22 % | media rows' real render time lives here |

Table footnotes: `LLM calls` = main-model completions (tool-loop hops + 1). The
kubernetes-rbac row carries its orphaned turn 2 (started 08:07:09, finished server-side at
08:08:46, 57 s *after* the row timed out) — hence its negative residual. `router s` counts only
in-window classifier calls; a row whose turn was still streaming when the row ended keeps that
time (start-time attribution).

Dominant component **per seat**:

- **Qwen3.8-27B-oQ4e-mtp (oMLX; auto-coding, compliance, spl, persona, daily::deep):** prefill.
  12 completions, 76 168 prompt tokens, 226.8 s total TTFT vs 326.8 s decode. Its cold prefill
  rate is ~126–155 tok/s (dense 27B; consistent since 11-19, see Q4), so the ~10.1k-token
  63-tool schema alone costs **65–80 s of TTFT on every cold first turn**. Decode 26 tok/s.
- **Nemotron-3.5-Lightning-30B-A3B GGUF (Ollama; auto-daily):** load + per-hop prefill.
  13.1 s per cold load (6 in-run), prefill 722 tok/s — but llama.cpp logs
  `forcing full prompt re-processing due to lack of cache data (… hybrid/recurrent memory)`:
  the prompt cache never engages, so **every tool hop re-prefills the whole ~4k prompt** (~4–5 s/hop).
- **granite4.1:8b / lfm2.5:8b (media lanes):** decode + the media engine itself (residual).
  granite prefill is oddly slow at 359 tok/s for an 8B (vs ~1 100 for gemma-E4B) — worth a
  separate look; it is the hunt-workflow and image/video router seat (35 in-window calls).
- **qwen3-vl:32b-ctx16k (auto-vision):** worst prefill in the run — 2 202 prompt tokens in
  26.8 s (82 tok/s, includes vision encoding); the row spent 69 s.

### The 313 s FAIL, corrected against the brief's lead

`s5-route-kubernetes-rbac` (FAIL, TimeoutError at 313.1 s) was **not** "Qwen3.8 cold-loaded for
each turn". The oMLX log shows exactly **one** load (08:03:10, 4.7 s) serving **two** turns:

```
08:03:30 Reserved prefill capacity for 10913 tokens
08:04:41 MTP path activated (primed=10913)          → cold prefill ≈ 71–87 s @ ~126 tok/s
08:07:01 Chat completion: 3651 tokens in 226.89s (26.0 tok/s), prompt: 10913, ttft 86.7s
08:07:09 Prefix cache restore: cached=10240 suffix=1869 → turn 2 prefill only ~17 s
08:07:49 row budget (313 s) expired → harness marked FAIL and moved on
08:08:46 turn 2 still finished server-side: 1974 tokens in 97.27s
```

The row died from **cold prefill of a 10.9k-token prompt (63 exposed tool schemas for a no-tool
question) + a 3 651-token answer at 26 tok/s**, then the harness timeout fired mid-turn-2. The
following row (`tls-firewall`) then spent 08:08:22→08:08:47 (25.5 s) in load_guard
`waiting for engine activity` — correct behaviour: it waited for the orphaned turn 2 to drain
before evicting Qwen3.8 (14:08:47Z `evicted Qwen3.8-27B-oQ4e-mtp … reason=idle LRU`, logged 3×
by 3 workers — one eviction) and cold-loading Nemotron (13.1 s).

---

## Q2 — Churn

In-run counts (07:58–08:43):

| seat | cold loads | load seconds | who unloaded it |
|---|---:|---:|---|
| Qwen3.8-27B-oQ4e-mtp (oMLX) | 7 | ~50 | 1× load_guard idle-LRU (08:08:47, to admit Nemotron), 6× QAT harness `_evict_on_primary_change` (admin unload at scenario boundaries) |
| gemma-4-E4B-OBLITERATED ctx2k (Ollama, classifier) | 13 admits | ~17 | harness evicts every Ollama resident on primary change; reloaded by the next classifier call |
| Nemotron ctx32k (Ollama) | 6 | ~79 | harness primary changes |
| gemma-4-26b-a4b-it-QAT-4bit (oMLX) | 3 (+1 mlx-community copy) | ~32 | harness |
| granite4.1:8b-ctx16k (Ollama) | 5 admits | ~20 | harness; **plus 1 load_guard job-reclaim eviction at 08:31:27 — see defect below** |
| Qwen3-Coder-30B-A3B (oMLX) | 2 | 7.4 | harness |
| Qwen3.6-35B-UD, Inkling-2-Mini ×2, gemma4:12b, lfm2.5, glm-4.7, K2, Nex-N2, qwen3-vl, gemma4:e4b-qat | 1–2 each | ~90 | harness |
| **total** | **20 oMLX + 50 Ollama** | **416 s** | |

**Avoidable churn (evicted then reloaded within 5 min):** every Qwen3.8 reload qualifies by the
letter of the metric (gaps: 4.3 min, 13 s, 2.6 min, 3.0 min, 50 s, 4.8 min). But the split
matters:

1. **Harness-driven (by design):** 6 of 7 Qwen3.8 unloads and most Ollama unloads are the QAT
   runner's `_evict_on_primary_change` (tests/qat/runner.py:845) forcing cold starts when the
   scenario's declared primary changes. Not a product defect; it is what the QAT measures.
2. **Capacity-forced (product reality, not a code defect):** the 08:08:47 eviction. Nemotron
   needs 23.8 GiB; headroom was 17.8 GiB with Qwen3.8 (16.6) resident. No eviction order makes
   both seats coexist on this 64 GiB host — the operator already adjudicated this trade on
   2026-11-20 (`preferred_residents: []`, config/backends.yaml:1064-1070). A real user
   alternating coding↔daily chat will ping-pong these two seats (~7 s load + ~65–80 s cold
   schema prefill per switch) **until either the daily or the coding seat gets smaller**;
   that is a seating/A-B decision, not something this lane may change.
3. **Product defect (fixed in this commit):** at 08:31:27 a background job's
   `POST /admin/reclaim-idle` (from 192.168.65.1, shortage **0.04 GiB** — logged
   `shortage_gib=0.0`) evicted `granite4.1:8b-ctx16k` **0.24 s after it finished a tool-loop hop
   for the in-flight s5-media-image-quality row**; the next hop re-admitted it 0.11 s later
   (`cold load admitted … need_gib=6.3 headroom_gib=23.6`). Two code faults combined:
   - **Job reclaim has no recency shield.** `reclaim_idle_memory` reused the cold-load eviction
     path; between tool hops a seat holds no lock, so "idle" included "served 0.24 s ago".
   - **"idle LRU" was not LRU across workers.** Recency (`_last_access`) is per-process; the
     pipeline runs 4 uvicorn workers. The worker serving `/admin/reclaim-idle` had never seen
     granite's request, so its LRU order was arbitrary (dict order), and it could pick the
     freshest seat over a stale one. The same per-worker blindness applied to Ollama eviction
     ordering on the chat-admission path.

**Fix (this commit, `portal/platform/inference/load_guard.py`):** the per-model cross-worker
activity lock file now carries the last-use timestamp (stamped at request begin *and* end, so a
long stream is protected from its start); `_free_ollama`'s victim order reads that shared stamp
(true cross-worker LRU); and `reclaim_idle_memory` passes a `_JOB_RECLAIM_RECENT_S = 120 s`
shield through `_free_idle_memory`/`_free_omlx`/`_free_ollama`, so a background job never evicts
a seat any worker served within 2 minutes — it gets an empty unload list and its existing
wait/retry loop in `portal/modules/orchestration/jobs.py:_prepare_step_memory` re-probes later.
Chat-admission eviction is untouched (shield defaults to 0): a chat load that genuinely needs
the memory may still evict the hot seat, as at 08:08:47.
Regression tests: `tests/unit/test_load_guard.py::test_reclaim_idle_memory_spares_a_seat_a_sibling_worker_just_served`,
`…_spares_a_recently_served_omlx_seat`, `…_ollama_idle_lru_orders_by_cross_worker_recency`
(all 3 fail on the pre-fix code; verified).

Also noted, not fixed (out of scope): 3 workers each ran the same eviction pass and logged it
(08:08:47 ×3) — idempotent but noisy; and the harness phase-gate unload at 08:02:38 aborted one
in-flight leftover request (`Aborted 1 requests … is being unloaded`).

---

## Q3 — Prompt bloat (tool schemas)

54 in-window turns carried merged tool schemas; 889 tool-exposures total, **9 turns with ≥32
tools** (auto-coding 63/64 ×5, auto-daily::fast 71, auto-compliance 46, auto-spl 32).
Empirical schema size from the two cleanest points — auto-daily (16 tools, first-turn prompt
4 002 tok) and auto-coding (63 tools, first-turn prompt 10 913 tok) — is **≈147–175 tokens per
tool** plus ~1.6k base, cross-checked by auto-daily::fast (71 tools → 13 164-token prompt on
Qwen3.6-35B).

Run-wide impact: estimated schema tokens ≈ **131–142 k = 60–65 % of the 218.4 k main-model prompt
tokens** (classifier prompts excluded). Pro-rated over the measured 414 s of main-model
prefill/TTFT, **≈250–270 s of the run (~11 %) is prefill of tool schemas** — concentrated on
Qwen3.8's cold turns (65–80 s each), where it directly caused the kubernetes-rbac timeout, and
on Nemotron, where the hybrid-model prompt-cache miss re-charges the 16-tool schema on every hop.
The pipeline already drops 39 OWUI `portal_*` mirror schemas per tool turn
(`Tool-merge: dropped 39 OWUI portal_* mirror schema(s)`); the remaining 63-tool merge for
`persona=auto` on a no-tool question is the source-level problem.

**Ownership:** lane `tool-exposure-scope` owns the source fix; its branch has **not landed**
(`lane/tool-exposure-scope` is even with origin/main at `cfe67a16e` — no commits to read). This
lane therefore quantifies only and changes no tool-merge behaviour.

---

## Q4 — Engine speed: regression check

oMLX logs rotate daily and only survive from **11-19**; 10-29…10-31 oMLX data does not exist on
this host (checked `~/.omlx/logs/`). Ollama's rotated logs (`/opt/homebrew/var/log/ollama.log.5.gz`)
reach back to 10-29 but its `print_timing` lines carry no model name, so per-seat Ollama history
is not attributable without the (already-rotated) pipeline logs. Per-day medians from the oMLX
log (prefill = prompt/ttft for requests with ttft > 2 s and prompt ≥ 1500, i.e. real cold
prefills — cache-hit turns excluded; decode = reported tok/s, generations ≥ 50 tokens):

| seat | metric | 11-19 | 11-20 | 11-21 | 11-22 | 11-23 | 11-24 | 11-25 | 11-26 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Qwen3.8-27B-oQ4e-mtp | decode med | 33.5 | 26.9 | 30.1 | 30.6 | 33.7 | 31.2 | 28.5 | 31.2 |
| Qwen3.8-27B-oQ4e-mtp | cold prefill med (n) | 131 (17) | 212 (60) | 257 (25) | 573 (85) | 1600* (85) | 482 (134) | 325 (17) | 611* (123) |
| Qwen3-Coder-30B-A3B | decode med | — | 50.8 | 56.3 | 57.0 | 59.7 | 55.2 | 57.4 | 56.9 |
| gemma-4-26b-a4b-it-QAT | decode med | 10.7 | 21.3 | 13.7 | 57.0 | 15.3 | 16.0 | 39.7 | 57.5 |
| unsloth Qwen3.6-35B-A3B-UD | decode med | 71.7 | 67.5 | 67.8 | 67.1 | 66.0 | 67.4 | 39.9 | 62.6 |

\* medians over a mix of true-cold and SSD-prefix-cache-restored turns (restores report
2 000–4 300 tok/s); the true-cold floor is stable at ~126–212 tok/s all week.

**Answer: no engine-speed regression.** Qwen3.8 decode has sat at 27–34 tok/s all week
(26.0 tok/s in this run), Qwen3-Coder decode is flat at 51–60 tok/s (its *loop-rate* spike
11→18 is a generation-behaviour question owned by lane `coder-loop-forensics`, not tok/s),
gemma-QAT decode improved. The kubernetes-rbac 86.7 s TTFT is the run's *normal* cold-prefill
physics (10.9k tokens @ ~126 tok/s) applied to an abnormal prompt size (Q3), not a slowed engine.
Full per-model daily table: `coding_task/TURN_LATENCY_AUDIT_EVIDENCE/daily_omlx.txt`.

---

## Top 3 root causes, ranked by seconds lost across the run

1. **Tool-schema prompt bloat — ≈250–270 s prefill + the 313 s timeout FAIL it directly caused.**
   60–66 % of all main-model prompt tokens are merged tool schemas (≈147–175 tok/tool; up to 71
   tools exposed). On Qwen3.8's ~130 tok/s cold prefill this is 65–80 s of TTFT before the first
   answer token, and on hybrid llama.cpp seats it re-charges every hop. Source fix belongs to
   lane `tool-exposure-scope` (not landed); evidence above sizes the prize.
2. **Cold-load churn — 416 s of engine load time (70 loads in 40 min) + the cold-prefill penalty
   each reload re-incurs (the bulk of cause 1's 250–270 s).** Mostly harness cold-start design and
   the 23.8 + 16.6 GiB coding/daily seat pair that cannot coexist on 64 GiB — a seating decision
   (needs an A/B, operator-owned), not a code fix. The genuinely defective slice — a background
   job reclaim evicting a seat 0.24 s out of a tool hop, plus per-worker-blind "LRU" victim
   order — is fixed in this commit.
3. **Layer-1 classifier tax — 160 s (59 calls, ~2.7 s avg) ≈ 7 % of run wall,** plus 13 cold
   reloads of its gemma-E4B-ctx2k seat because harness/guard evictions sweep it between calls.
   This is the designed routing mechanism (measured median call 1.6 s); flagged for the
   orchestrator as a systemic per-turn cost, not fixed here (changing routing design is out of
   this brief's scope).

Not in the top 3 but noted: decode volume (858 s) is the largest single component and is mostly
legitimate work; the wasteful tail (3 651-token answer to an RBAC question; bigfix's degenerate
repetition loop, 122 s) is model-quality (rows already FAILed as MODEL_QUALITY_GAP).
Headroom waiting worked as designed (25.5 s, once, correctly waiting out an orphaned stream).

## What was committed

- `portal/platform/inference/load_guard.py` — cross-worker last-use stamps in the activity lock
  files; `_shared_last_access`/`_recently_served` helpers; true cross-worker LRU order in
  `_free_ollama`; `_JOB_RECLAIM_RECENT_S = 120` recency shield applied **only** to
  `reclaim_idle_memory` (chat admission unchanged).
- `tests/unit/test_load_guard.py` — 3 regression tests (fail pre-fix, pass post-fix).

No QAT budgets raised, no graders changed, no scenarios special-cased, no seating/config changed.

## Live check for the orchestrator (after the QAT finishes)

The pipeline image bakes `portal/`, so: `./launch.sh rebuild && ./launch.sh up`. Then, with any
chat seat resident and *just used* (send one chat turn through the pipeline, wait for it to
complete, act within 2 minutes):

```bash
source .env
curl -s http://localhost:11434/api/ps | jq '.models[].name'   # note the resident
curl -s -X POST http://localhost:9099/admin/reclaim-idle \
  -H "Authorization: Bearer $PORTAL5_ADMIN_KEY" -H 'Content-Type: application/json' \
  -d '{"need_gib": 0.05}' | jq '.unloads'
curl -s http://localhost:11434/api/ps | jq '.models[].name'   # unchanged
```

**Worked:** `unloads` is `[]` and the just-used resident is still in `/api/ps` (pre-fix it was
evicted — that is exactly the 08:31:27 granite incident). **Did not work:** the resident
disappears from `/api/ps` after the reclaim call. Second check (ordering): with two Ollama
residents where the alphabetically-first one was used more recently, a
`{"need_gib": <size-of-one>}` reclaim must evict the *older* one (watch
`docker logs portal5-pipeline | grep "evicted"`). A stale resident (>2 min unused) is still
reclaimable — a reclaim after 2 minutes idle must evict it, otherwise the shield is too broad.
