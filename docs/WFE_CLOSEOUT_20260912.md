# WFE Closeout — 2026-09-12

Terminates every open model question left by `wfe_full_20260911`. Companion to
`docs/WFE_FITNESS_REPORT_wfe_full_20260911.md` (the campaign) and
`docs/MODEL_FLEET_CLOSEOUT_20260906.tasks.json` (the register, updated here).

**Result: 0 items in the register carry an unterminated stop rule.** Fleet 83 → 78
models, 852 GB → 817 GB. Both corrupted lanes were re-run on the fixed harness
the same day rather than deferred, and one fold was vacated as a result.

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

Six clean completions where there were zero. The existing 22 were discarded and
the full suite re-run on the fixed harness the same day — see §5b.

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
expensive kind of fold to get wrong. Weights re-pulled and the arm restored.

**Outcome: RETAINED, not re-folded** — a second, independent fault surfaced when
the re-run was set up. Its recorded question is *"does GPT-OSS add reasoning
**diversity** over DeepSeek-R1-0528 + Qwen3.6-35B"*, and **no run has ever made
that comparison**; the WFE arm tested it as a compliance judge against
Qwen3.8-27B, which is a different job — the same mis-specified-venue error
caught for command-r in §5. And the fact the removal missed entirely:
`gpt-oss:20b` is registered in **three live backend pools** (general, coding,
reasoning), reachable from **25 production workspaces**, and named in
auto-coding's own description as *Fallback 2*. That is a wired production role,
not a bench seat. Its clean numbers (18/30 = 0.60 home, 7/9 = 0.78 discovery) do
not bear on it, because neither lane is the job it holds. Retained as a pool
fallback; **its diversity stop rule remains UNEVALUATED** and needs the recorded
head-to-head, not another compliance-lane number.

The other three folds survive this check on their own evidence. command-r ran
`think=default` and emitted **zero** reasoning chars, so the defect never
touched it — and its fold rests on the real-tool test in §5 regardless. Both
gemma4 arms ran in `tools-specialist`, which leaves `think` unset: `default` is
that lane's intended behaviour, not a dropped instruction.

---

## 5b. The re-runs, and what they settled

Both corrupted lanes were re-run on the fixed harness the same day, rather than
left as plan items.

**Creative (`wfe_creative_20260912`) — the lane the defect destroyed.**

| arm | before | after |
|---|---|---|
| Huihui-Qwen3.6-35B (incumbent) | 4 gradeable, 5 truncated | **9/9**, 65 s |
| huihui_ai/Qwen3.6-abliterated:27b | 9 gradeable | **9/9**, 295 s |
| orcarouter/Qwen3.8-27B-Uncensored | **0 gradeable**, 9 truncated | **9/9**, 642 s |
| qwen36-fable-fusion-711 | 9 gradeable | **9/9**, 250 s |

22 biased responses → **36 complete ones**, zero truncated, zero refused. The
blind queue is rebuilt and awaiting operator scores.

**auto-compliance (`wfe_think_rerun_20260912`), 117 rows + a 30-row comparator.**

| arm | lane | corrupted | fixed |
|---|---|---|---|
| Qwen3.8-27B-ctx32k (incumbent) | compliance_agentic | 25/30 = 0.83 | 24/30 = 0.80 [0.63–0.91] |
| granite4.2:30b | compliance_agentic | 18/30 = 0.60 | 18/30 = 0.60 [0.42–0.75] |
| gpt-oss:20b | compliance_agentic | 16/30 = 0.53 | 18/30 = 0.60 [0.42–0.75] |
| **granite4.1:30b-ctx16k** (comparator) | compliance_agentic | never run | **18/30 = 0.60** |
| Qwen3.8-27B / granite4.2 / gpt-oss | research | 1.00 / 1.00 / 0.67 | 1.00 / 1.00 / 0.78 |

Honest read: **the defect barely moved auto-compliance.** It destroyed the
creative lane, where a 4096-token budget could not absorb 10k+ chars of
reasoning, but compliance had enough headroom that the ordering held. The
incumbent is confirmed on clean evidence.

<a name="granite42"></a>**granite4.2:30b — FOLDED.** Its stop rule is *"no
analyst-lane advantage over 4.1:30b in real use → REMOVED (council reject stands
regardless)"*, and `granite4.1:30b` had **never been run as an arm**, so the rule
had been unevaluable since it was written — the disposition was sitting on a
permanent hold for want of one 30-row comparator. Run it, and the two are **dead
even at 0.60**. A tie is no advantage: the rule fires. It also loses to the
seated incumbent (0.80) and holds no live config reference. The council reject
stands independently (Y29).

---

## 6. Plan of action — what is deliberately not closed

Two items remain, each with a named owner-action. Everything else is terminal.

1. **Score the 36 creative responses.** They are generated, blind and complete;
   what is missing is operator judgement, which no instrument can supply.
   Scoring sheet: the `Creative Lane Blind Review` artifact. It unblocks the two
   RETAINED dispositions that rest on creative fit — `qwen36-fable-fusion-711`
   and `huihui_ai/Qwen3.6-abliterated:27b-ctx8k`. Discard the old 22.

2. **gpt-oss:20b's diversity stop rule is still unevaluated.** It asks for a
   head-to-head against DeepSeek-R1-0528 + Qwen3.6-35B on reasoning diversity.
   That comparison has never been run, and neither compliance nor research
   measures it. The model is RETAINED on its wired pool role in the meantime,
   so nothing is blocked — but the rule should not be reported as satisfied.

**Structural, not per-model:** the campaign still runs on proxy tools
(`tool_surface_proxy: true` on every row) because the sweep runs with the MCP
fleet down. The command-r test in §5 shows the real-tool version is
straightforward when the fleet is up, and that it can change a verdict. Read
dimension 4 as "can it use *a* tool", not "can it use *its* tool", until that is
addressed.

Coverage caveat from the fitness report still stands: dimensions 2, 6–19 and
23–26 remain unexercised, so every disposition here is provisional against them
in the sense defined by `TASK_WORKSPACE_FITNESS_EVAL_V1.md`.

---

## 7. What this unblocks — the compliance module

The module paused on 2026-09-06 at **27 PASS / 1 FAIL / 2 PENDING** of 30,
waiting on seat decisions it could not make itself. Those are now terminal, and
the continuation task is written:
**`coding_task/v9_compliance/TASK_COMPLIANCE_CLOSEOUT_RESUME_V1.md`**.

The substantive unblock is **S0**. Y25 (`prose-cip-07` must reach rank 1) fails
because the answer lives in CIP-002 Attachment 1 — a **table rendered as a
text-less page image**. The reranker already ranks that chunk highest (rr 0.519)
but fusion cannot lift it without text, and the fix is to turn on S0 table
transcription for the compliance composition. S0's transcriber seat was
provisional while the Ollama OCR arms were unresolved; folding all four confirmed
`qwen3-vl:4b-instruct-q4_K_M` (0.956 EXACT @ 7.9 s/page), so the fix can now be
applied against a seat that will not move underneath it.

Also settled for that module: the council roster is final (Y29 passes, 3 seats),
`granite4.2:30b` — its only live challenger — is folded, and the long-open
**phi4 4th-seat question is decided: not seated**. F2 0.802 sits at the floor
rather than above it, 4.5 tps is disqualifying for a seat the council queries on
every question, and a 4th seat moves quorum from `ceil(0.66x3) = 2 of 3` to
`ceil(0.66x4) = 3 of 4` — raising the agreement bar while slowing every question,
using the weakest judge. Recorded in `Y25_ISSUE_AND_REMAINING.md`.

That leaves Y25, Y21 (adjudication of debug data already on disk) and Y23
(prompt sensitivity, now runnable because the roster is final) between the module
and 30/30.

**A caveat worth carrying into Y23:** three parameters in this stack were
accepted and silently discarded — `think` on `/v1`, runtime `options.num_ctx` on
`/v1`, and the campaign CLI's `--workspace`. Y23 sends a *changed prompt* and
reads a *changed number*; confirm the variant reached the model on the wire
before trusting its F2. An ignored parameter looks exactly like one with no
effect.

---

## Ledger

| | before | after |
|---|---|---|
| models on disk | 83 | 78 |
| model store | 852 GB | 817 GB |
| register items with an open stop rule | 12 | **0** |
| REMOVED_CLOSED / INTEGRATED / RETAINED | 105 / 78 / 5 | 100 / 81 / 7 |

**Removed:** `deepseek-ocr:latest`, `glm-ocr:Q8_0`,
`hf.co/ggml-org/dots.ocr-GGUF:Q8_0`,
`hf.co/mradermacher/Nanonets-OCR2-3B-GGUF:Q4_K_M`,
`hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M`,
`command-r:35b-08-2024-q4_K_M`, `granite4.2:30b-q4_K_M`.

**Restored:** `gpt-oss:20b` — folded on invalid evidence, re-pulled, and kept.

Each removal was cross-checked against live `config/portal.yaml`,
`config/personas/`, `config/backends.yaml` and — after the gpt-oss lesson — the
backend **pool** membership lists, immediately before deletion, then verified
absent.

### Re-runs executed

| campaign | scope | result |
|---|---|---|
| `wfe_creative_20260912` | 4 arms × 3 tasks × 3 repeats | 36/36 gradeable, 0 truncated (was 22 of 36, biased) |
| `wfe_think_rerun_20260912` | auto-compliance, 3 arms + 1 comparator | 147 rows; incumbent confirmed 0.80; granite4.2 folded on a 0.60/0.60 tie |

### Instrument defects found and fixed

| defect | effect | fix |
|---|---|---|
| `think` dropped by Ollama `/v1` | 12 workspaces reasoned against config; 189 campaign rows; 1 wrong fold | `reasoning_effort:"none"` in 3 call sites |
| `OLLAMA_URL=host.docker.internal` inherited by host-native services | `explore_repository` dead since it was wired | rewrite to loopback in the launcher |
| `.claude/worktrees` searchable by GREP/GLOB | explorer cited stale repo copies | skip-set + `.venv` |
| `--workspace` declared but never used | scoped re-runs silently widened to the whole plan | wired into `expand_matrix` |

Four parameters in this stack have now been found accepted-and-discarded:
`think` and `--workspace` (fixed here), runtime `options.num_ctx` on `/v1`
(documented earlier at `validation.py`), and `chat_template_kwargs` /
`/no_think` on `/v1` (measured here). The pattern is worth a standing check:
**a parameter that is ignored is indistinguishable from one that had no effect.**

### Also fixed

`bench-nex-n25-mini-uncensored` routed to `general` while its model is registered
only in the `security` group — a latent `STRICT_HINT_VALIDATION` crash on any
pipeline restart, and the only such mismatch across all 46 workspaces.
