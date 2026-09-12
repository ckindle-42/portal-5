# WFE Closeout — 2026-09-12

Terminates every open model question left by `wfe_full_20260911`. Companion to
`docs/WFE_FITNESS_REPORT_wfe_full_20260911.md` (the campaign) and
`docs/MODEL_FLEET_CLOSEOUT_20260906.tasks.json` (the register, updated here).

**Result: 0 items in the register carry an unterminated stop rule.** Fleet 83 → 78
models, 852 GB → 820 GB.

The three things that were open on 2026-09-11 — command-r held-not-wired, 11
models with "NO WFE EVIDENCE", and 22 unscored creative responses — are all
resolved below. Two of the three turned out to be instrument problems rather
than model problems, so the instrument findings come first.

---

## 1. The blocking defect: `think: false` never reached any Ollama model

### What was wrong

`router/validation.py` injected the thinking toggle as a top-level `think` bool,
and `Backend.chat_url` dispatches to `/v1/chat/completions`. **Ollama's
OpenAI-compat endpoint silently drops that field.** Measured on Ollama 0.33.2
against three models — `huihui_ai/qwen3.5-abliterated:9b-ctx8k`,
`orcarouter/Qwen3.8-27B-Uncensored:Q4_K_M`,
`hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF`:

| request over `/v1/chat/completions` | content | reasoning | finish |
|---|---|---|---|
| no think param (baseline) | 0 chars | 2251 | length |
| **top-level `think:false`** ← what production sent | 0 chars | 2151 | length |
| `chat_template_kwargs.enable_thinking:false` | 0 chars | 2225 | length |
| `options.think:false` | 0 chars | 2337 | length |
| bare `enable_thinking:false` | 0 chars | 2295 | length |
| `/no_think` token, system or user message | 0 chars | 1816–2327 | length |
| **`reasoning_effort:"none"`** | **1373 chars** | **0** | **stop** |
| `/api/chat` + `think:false` (native knob) | 1457 chars | 0 | stop |

Every suppression mechanism except `reasoning_effort:"none"` is a no-op on the
endpoint that carries all production traffic. Twelve workspaces declared
`think: false` on a thinking-family hint — `auto`, `auto-compliance`,
`auto-council`, `auto-creative`, `auto-data`, `auto-general-uncensored`, plus 6
bench stanzas — and every one had been reasoning anyway.

`warn_unset_thinking_mode()` could not catch this: it only fires when `think` is
*unset*, never when it is set-but-ineffective.

### Why `reasoning_effort` and only in one direction

`reasoning_effort:"medium"` returns **HTTP 400 `"<model>" does not support
thinking`** on a model without the thinking capability (verified on
`granite4.1:8b-ctx16k`, `gemma-4-E4B-it-OBLITERATED`, `command-r:35b`). Injecting
the enabling direction would break every `think: true` workspace seated on a
non-thinking model. `"none"` is safe on all of them, and thinking is already the
template default where it works — so only the suppressing direction is sent.

The wire key is free at that point: the inbound-API meaning of `reasoning_effort`
(a `max_tokens` tier) is popped by `_apply_reasoning_effort` earlier in the same
function, so this never overwrites a caller's value.

### Fixed in three places

| File | Change |
|---|---|
| `portal/platform/inference/router/validation.py` | `think:false` → also emit `reasoning_effort:"none"` |
| `portal/platform/mcp_host/pipeline_mcp.py` | explorer subagent call site |
| `tests/wfe/runner.py` | the campaign harness, so a re-run is valid |

Verified end-to-end through the rebuilt pipeline: `auto-general-uncensored`
returns 1580 chars / 0 reasoning, `auto-compliance` 914 chars / 0 reasoning —
both previously burned the whole budget on invisible reasoning.

Regression guards: 4 new tests in `tests/unit/test_reasoning_effort.py`.

### Scope of the damage

189 of 513 `wfe_full_20260911` rows were sent `think:false` over `/v1`.

- **auto-compliance (117 rows)** — all arms got identical treatment, and because
  production carried the same defect these rates are a fair picture of *how the
  stack actually behaved*. They are not a picture of the *intended* config —
  **and one fold did rest on them.** See §5a.
- **auto-general-uncensored / creative (72 rows)** — destroyed outright, see §3.

---

## 2. Two more instrument defects, found while testing FastContext

Both had silently disabled `explore_repository` since it was wired.

1. **Host-native services got a Docker-only hostname.** `.env:41` sets
   `OLLAMA_URL=http://host.docker.internal:11434` for the containers.
   `scripts/native-mcp-service.sh` sources `.env` *before* its own `localhost`
   default, so every host-native MCP inherited a name that does not resolve
   outside Docker. The symptom is a bare `[Errno 8] nodename nor servname
   provided`, which reads like a dead service rather than a misaddressed one.
   Fixed by rewriting that alias to loopback on the host side; a genuinely
   remote `OLLAMA_URL` is left untouched.

2. **`.claude/worktrees/` was searchable.** `GLOB`/`GREP` excluded `.git`,
   `__pycache__`, `.mypy_cache`, `node_modules`, `.ruff_cache` — but not
   `.claude`, which holds full worktree *copies* of the repo. Because `.claude`
   sorts first, an explorer spent its entire 40-result budget citing stale
   duplicates before reaching real source. `.claude` and `.venv` now excluded.

---

## 3. Creative lane — the 22 responses were never scoreable

The blind-review queue was a biased survivor sample, not a lane measurement.

| arm | PENDING_REVIEW | TRUNCATED | reported rate |
|---|---|---|---|
| `orcarouter/Qwen3.8-27B-Uncensored` | 0 | **9** | `0/9 = 0.00` |
| `Huihui-Qwen3.6-35B-A3B` (incumbent) | 4 | **5** | `0/5 = 0.00` |
| `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` | 9 | 0 | n/a (0 gradeable) |
| `qwen36-fable-fusion-711` | 9 | 0 | n/a (0 gradeable) |

Every TRUNCATED row is `finish_reason=length`, `content=""`, with 6,217–15,368
chars of reasoning. **Those 14 zeros contain no human judgement at all** — they
are the think defect, scored as model failures and then compared in §3 of the
fitness report as though they were quality measurements ("NOT SEPARATED").

The one arm that looked healthy, `qwen36-fable-fusion-711` (median 366 reasoning
chars), looked healthy because it is the only non-thinking model in the group.

**Post-fix re-measurement** of the two broken arms, same suite, same seed:

| arm | before | after |
|---|---|---|
| `orcarouter/Qwen3.8-27B-Uncensored` | 9/9 truncated, 0 words, 328s median | 3/3 `finish=stop`, 192–474 words, 22–62s |
| `Huihui-Qwen3.6-35B-A3B` | 5/9 truncated | 3/3 `finish=stop`, 210–465 words, 6–27s |

Six clean completions where there were zero. **Do not score the existing 22** —
re-run the creative suite on the fixed harness first. See §6.

---

## 4. The 11 "zero WFE evidence" models

"No WFE evidence" was not the same as "no evidence" — WFE is one instrument among
several, and 10 of the 11 were already decidable.

### Folded (5)

| Model | Evidence |
|---|---|
| `deepseek-ocr:latest` | 0.800 EXACT vs MLX PaddleOCR-VL-8bit 0.978. Fastest tested (3.2s/page) but accuracy-dominated. |
| `glm-ocr:Q8_0` | Ties at 0.956 EXACT but repeats **37.7% of its lines** on its own native `Text Recognition:` contract, vs qwen3-vl:4b's 0.6%. Duplicate lines dilute the chunk embedding that is the entire product of S0. |
| `dots.ocr-GGUF:Q8_0` | **0.000 EXACT** — worst of the 16 benched. MLX dots.ocr-4bit (0.422) strictly dominates. |
| `Nanonets-OCR2-3B-GGUF:Q4_K_M` | Stop rule fires literally: the already-owned **MLX build of the same model** scores 1.000 norm @ 8.5s/page vs this GGUF's 1.000 @ 9.8s. |
| `FastContext-1.0-4B-SFT` | See below — tested on a repaired harness, still confabulated. |

OCR source: `reports/runtime/HARDENING_V2_P4_MEASUREMENTS.md` — 16-model,
5-round bake-off on ground-truth fact recall (45 facts over 9 figure pages),
run *after* three harness defects were found and corrected. Two caveats, both of
which strengthen the fold: the MLX round used a generic prompt so MLX is
*understated*, and the corpus is synthetic figures rather than the register's
"10 real document images" — but the margins on deepseek-ocr and dots.ocr are far
too large to flip, and glm-ocr and Nanonets lose on secondary criteria, not
recall. The production transcribe seat (`qwen3-vl:4b-instruct-q4_K_M`, 0.956
EXACT @ 7.9s) is untouched and verified still present.

<a name="fastcontext"></a>**FastContext** was pulled and tested only after the
two §2 defects and the §1 defect were fixed — three instrument bugs that had
masked it. On the repaired harness it still failed to emit a `final_answer` on
2 of 3 queries, and **fabricated the citations it did return**:
`src/workspace/routing.py` and `src/workspace/utils.py`, in a repo with no
`src/` directory at all. Stop rule ("poor citations → REMOVED_CLOSED for good")
fires on clean evidence.

`explore_repository` is repointed to `qwen3-coder:30b-a3b-q4_K_M-ctx16k`, which
on the identical prompt returns real paths with real line ranges and useful
notes (`cluster_backends.py:365-370`, `router/preinject.py:163-203`,
`router/workspaces.py:42`). Overridable via `PIPELINE_MCP_EXPLORER_MODEL`.

### Kept, already terminal on non-WFE evidence (3)

| Model | Disposition | Evidence |
|---|---|---|
| `glm-4.7-flash:Q4_K_M` | INTEGRATED | Repair exam 82%/90% ≥ REAP-23B 80%/90%, closed 2026-09-07. Its `-ctx64k` production tag *did* run WFE (8/9 auto-coding home). |
| `Nex-N2-mini:UD-Q4_K_M` | INTEGRATED | Won the research probe twice (factuality 0.9/0.8 vs Aquila 0.3). Its `-ctx16k` tag ran WFE as the auto-research **incumbent and won separated**, 24/30 vs command-r 13/30. |
| `qwen3-vl:8b-instruct-q4_K_M` | RETAINED | VQA parity 4/4 with the 32b at 5.7 vs 23.7 GiB. Now corroborated by the bake-off: 0.956 EXACT, tying the 4b exactly, at 12.9s/page vs 7.9s. |

### Already executed before this pass (3)

`hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M`, `granite4.2:8b-q8_0`,
`granite4.1:8b-q8_0` — REMOVED_CLOSED on executed-test evidence and confirmed
absent from disk.

### Unchanged (1)

`portal5/fara1.5-27b:Q4_K_M` — RETAINED. CUA preflight PASS; it is the only
CUA-capable model and there is no production CUA lane to displace. Manual-only.

---

## 5. command-r — folded

<a name="command-r"></a>Its recorded test was **mis-specified against the current
architecture**: `auto-documents` has no `kb_search` and does no grounded RAG at
all — it builds Office files with `granite4.1:8b-ctx16k` — and the live RAG MCP
holds only a `smoketest` KB. The reason it was held ("MCP fleet down during
sweeps") was also not a real constraint: `portal5-mcp-documents` was up and
answering on :8913 throughout.

Tested on that lane's **actual** job, with the real documents-MCP tool schemas:

| | command-r:35b | granite4.1:8b-ctx16k (incumbent) |
|---|---|---|
| correct tool selection | 4/4 | 4/4 |
| latency | 34s / 18s / 13s / 8s | 8s / 5s / 1s / 1s |
| residency | 19 GB | 5.3 GB |
| grounded citation, fabricated refs | 0 | 0 |

Its stop rule requires grounded-citation quality **>** the incumbent. It is at
parity on correctness and on citation discipline, while costing 3.6× the
residency and 4–8× the latency — and WFE separately had it *losing separated* to
Nex-N2-mini on compliance_agentic. `else REMOVED` fires.

---

## 5a. gpt-oss:20b — fold VACATED, model re-pulled

<a name="gpt-oss"></a>gpt-oss:20b was removed in `a90d11da` on a 16/30 = 0.53
auto-compliance rate, against a stop rule of "F2 < 0.80 → remove without further
tests". **That evidence is invalid.** Checked per-row on 2026-09-12:

| arm | workspace | harness `think` | endpoint | median reasoning chars | verdict |
|---|---|---|---|---|---|
| **gpt-oss:20b** | auto-compliance | **false** | **v1** | **1661** | **corrupted** |
| command-r:35b | auto-documents / auto-research | default | v1 | 0 | clean |
| gemma4:e2b-it-qat | tools-specialist | default | v1 | 8563 | clean |
| gemma4:e4b-it-q4_K_M | tools-specialist | default | v1 | 3171 | clean |

All 39 of gpt-oss's rows ran at `think=false` over `/v1` — precisely the
combination proven that day to drop the suppression silently — and it reasoned
through every one of them. The number it was removed on was measured with
thinking forced on against its own workspace config.

It is also the register's **lineage-diversity seat** (§1 census), which is the
expensive kind of fold to get wrong. Weights re-pulled, arm restored to
`tests/wfe/workloads.yaml`, disposition moved back to RETAINED_FOR_PURPOSE and
HELD pending `wfe_think_rerun_20260912`. The stop rule is unchanged and will be
applied to the new numbers.

The other three folds survive this check on their own evidence. command-r ran
`think=default` and emitted **zero** reasoning chars, so the defect never
touched it — and its fold rests on the real-tool test in §5 regardless. Both
gemma4 arms ran in `tools-specialist`, which leaves `think` unset: `default` is
that lane's intended behaviour, not a dropped instruction.

---

## 6. Plan of action — what is deliberately not closed

Three items remain open **by design**, each with a named next step. None blocks
the register.

1. **Creative-lane blind review (2 dispositions depend on it).**
   `qwen36-fable-fusion-711` and `huihui_ai/Qwen3.6-abliterated:27b-ctx8k` are
   RETAINED_FOR_PURPOSE pending an operator creative judgement that no synthetic
   instrument can make. **Next step:** re-run the creative suite on the fixed
   harness (all 4 arms × 3 tasks × 3 repeats — now that all four complete, this
   yields 36 gradeable responses instead of 22 biased ones), then score the
   blind queue. Discard the existing 22.

2. **Re-run auto-compliance and auto-general-uncensored under the fixed
   harness.** Their 189 rows measured the stack as it really behaved, not as
   configured. Now that config and behaviour agree, the rates should be
   re-established before anyone cites them as model quality. `granite4.2:30b` is
   the one RETAINED disposition resting mostly on those rows.

3. **The campaign still runs on proxy tools.** `tool_surface_proxy: true` on all
   513 rows — no workspace's real tools were wired, because the sweep runs with
   the MCP fleet down. The command-r test in §5 shows the real-tool version is
   straightforward when the fleet is up, and that it can change a verdict.
   Dimension 4 of the coverage matrix should be re-read as "can it use *a* tool",
   not "can it use *its* tool", until that is addressed.

Coverage caveat from the fitness report still stands: dimensions 2, 6–19 and
23–26 remain unexercised, so every disposition here is provisional against them
in the sense defined by `TASK_WORKSPACE_FITNESS_EVAL_V1.md`.

---

## Ledger

| | before | after |
|---|---|---|
| models on disk | 83 | 78 |
| model store | 852 GB | 820 GB |
| register items with an open stop rule | 12 | **0** |
| REMOVED_CLOSED / INTEGRATED / RETAINED | 105 / 78 / 5 | 100 / 81 / 7 |

Removed this pass: `deepseek-ocr:latest`, `glm-ocr:Q8_0`,
`hf.co/ggml-org/dots.ocr-GGUF:Q8_0`,
`hf.co/mradermacher/Nanonets-OCR2-3B-GGUF:Q4_K_M`,
`hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M`,
`command-r:35b-08-2024-q4_K_M`. Each cross-checked against live
`config/portal.yaml`, `config/personas/` and `config/backends.yaml` for zero
production references immediately before deletion, then verified absent.

Also fixed in passing: `bench-nex-n25-mini-uncensored` routed to `general` while
its model is registered only in the `security` group — a latent
`STRICT_HINT_VALIDATION` failure that would crash the pipeline on any restart.
It was the only such mismatch across all 46 workspaces.
