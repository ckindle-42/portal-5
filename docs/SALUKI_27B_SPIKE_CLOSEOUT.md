# Saluki 27B spike — closeout (TASK_SALUKI_27B_SPIKE_V1)

**Ran:** 2026-10-11 → 2026-10-12 on the live M4 Pro host, base `ff254ebc` (one `reports/` chore above the drafting base `a23173df`; nothing touching WFE, prove_then_scale, portal.yaml or the model tags — no reconciliation needed). **Executor:** frontier coding agent, unattended between operator checkpoints. Raw data: `tests/benchmarks/results/saluki_spike/`. This document and that receipts directory are the spike's whole record; the task file itself stays untracked in `coding_task/`.

## The question

`ConwayResearch/Underdog-Saluki-27B-1.0` is Qwen3.8-27B compressed to a 7.89 GB GGUF (`Underdog-Saluki-27B-1.0-IQ2-mix.gguf`, a ~2-bit i-quant built on ISTA-DASLab's GSQ-RCO quant, Apache 2.0), tuned to keep tool calling. The operator's interest: Qwen3.8-27B is the strongest model this 64 GB M4 Pro runs, and its footprint is why it isn't resident more often. Could a model this small stay loaded alongside General · Fast and the router, and still do General · Deep's job? This was a model evaluation, not a seat decision: `PROMOTE_POLICY=confirm` held throughout, no production seat changed.

## Arms, tags, and provenance

| Arm | Tag / endpoint | Weights provenance |
|---|---|---|
| Challenger | `portal5/underdog-saluki-27b:iq2-mix` (+ `-ctx32k`, `-ctx96k`, `-vision-ctx32k`) | GGUF sha256 `4a673518b11b…`, HF revision `4f60eba09f4b`; imported from the incumbent's Modelfile with only FROM/num_ctx changed; mmproj `2e0b88b680a4…` (629 MB, vision tag only) |
| Incumbent control | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` / `-ctx96k` | UD-Q4_K_M blob `322e194ff797` (the 2026-10-11 production refresh), revision `4ca72078` |
| oMLX General · Deep | `Qwen3.8-27B-oQ4e-mtp` on `:8085` | production pack |
| Card-fidelity | Homebrew `llama-server` 9950 (`961e4b26a`), `--jinja`, `-c 98304`, alias `saluki` | same GGUF file |

Template parity (P1): Saluki's embedded `tokenizer.chat_template` is byte-identical to the official Qwen3.8 template (`c3cf9e34abf4`, 8,952 chars); the refreshed incumbent's is Unsloth's current one (`12827f24b742`, 9,993 chars), which the review had already verified token-identical to the official render. Both Ollama tags passed the 5-shape render check `all_match: true` (30/19/59/282/333 tokens — the same counts as the official render). Per the task's own warning, the Modelfile diff cannot see templates: `/api/show` hashes differ (`e6cd775a…` incumbent vs `514d5304…` Saluki) — recorded, and P3/P4 gaps were read with that in mind (the Rule-5 diagnostic below then settled attribution on both engines). oMLX's `convert_tools_for_template` adds `"description": ""` to every tool parameter (+5 tokens on the two tool shapes only) — reproduced with oMLX's own code, recorded, not patched.

GGUF inspection: both `qwen35`; Saluki is dominated by IQ2_XXS (2.37 GB of 7.89) with an IQ1_S/IQ1_M tail; no `nextn`/MTP tensors (the incumbent carries `blk.64.nextn.*`, which is why its oMLX pack decodes ~24 tok/s).

Engines (live at run time): Ollama 0.40.0 (`OLLAMA_NUM_PARALLEL=1`, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`, `OLLAMA_MAX_LOADED_MODELS=5`), oMLX 0.7.0, `iogpu.wired_limit_mb=57344`. No engine was upgraded (rule).

## Pre-registered criteria (verbatim from the task) and how each landed

1. **Residency:** *in the P2b co-residency scenario it stays resident next to General · Fast and the router with no swap growth over 2048 MB, where the Q4 does not, or does so with clearly more free memory.* — **Holds in its comparative clause.** See P2b below.
2. **General-deep WFE:** *its PASS count is no more than 2 below the Q4 incumbent's (of 27).* — **Undecided, currently failing:** 14 vs 18 on as-decided rows, with 9 blinded-review rows pending on EACH arm (the creative lane's review queue). Saluki needs ≥4 of its 9 reviews while the incumbent gains none.
3. **Bonsai instrument:** *at least 28/42 with no more than 6 turn-cap loops*; the incumbent re-run as live control; *if the live incumbent lands outside 30–36/42, criterion 3 becomes relative: Saluki within 5 PASS of the live incumbent and no more than 3 loops above it.* — **Fails decisively.** The live incumbent landed at 27/42 (outside the band, so the relative form applies): Saluki 10/42 is 17 PASS below with 32 turn-cap loops (vs the incumbent's 8). **Amendment:** the loop count is a property of the think-off + format-clause + tool-offer condition on this 2-bit reasoning model (see Rule-5, re-verified 2026-10-12), not evidence of a general instruction-following collapse. The auto-compliance WFE suite also serves a persona prompt whose tool references do not match the harness tool surface, which affects every seat measured on it (the incumbent included: 8 of its 42 rows exhausted, mostly map/register hunting); absolute PASS rates on that suite are understated, while the like-for-like comparison stands.
4. **Tools:** *`bench_tool_use_probe` 4/4, parallel ≥ 8/10 clean at the seat setting.* — **Passes.** Both arms 4/4; parallel 20/20 clean on Saluki (card and seat sampling), the incumbent, oMLX Deep, and Saluki-on-llama.cpp. The card's "about a fifth of parallel-call replies have small formatting slips" did not reproduce anywhere (0 slips in 80 card-setting calls across arms).
5. **Speed:** *decode at least 1.3× the Q4 on Ollama at 96K.* — **Fails:** 14.48 vs 12.36 tok/s = **1.17×**.

**Verdict per role, one line each:**

- **Operator gate: REJECTED** (2026-10-12), on the corrected Rule-5 grounds above.
- **Resident Deep-lite candidate: NOT A CANDIDATE.** It does stay resident cheaply (12.27 GB at 96K, keeps the router company, zero swap growth — genuinely better than the Q4's 20.59 GB, which evicted the router), but it fails the speed bar (1.17×, not 1.3×) and fails the agentic instrument by a wide margin.
- **Auto-compliance drop-in: NO.** 10/42 vs the live incumbent's 27/42, with 32 of 33 home runs ending in the 16-turn cap.
- **Compliance reader: at the tie line, not above it.** §A2 reads 4/6 — exactly the threshold that kept gemma4 — with both failures in conflict-detection; today's qwen38 reference reads 6/6 under identical conditions.
- **Vision: functional.** 2/2 colour cases on both the Ollama path (projector tag) and stock llama.cpp (`--mmproj`); incumbent tag also 2/2. Toy probes only.

## P2 — footprint, speed, co-residency

Speed (P2a; all rows `valid: true`, 0 invalid size rows; Ollama decode from `eval_count/eval_duration`, oMLX/llama.cpp wall-derived from streamed tokens):

| Arm | Decode tok/s (median) | Prefill 2K / 16K / 32K / 64K (tok/s) | Resident at 96K |
|---|---|---|---|
| Saluki on Ollama (96K) | **14.48** | 96.1 / 103.2 / 96.0 / 76.9 | **12.27 GB** |
| Q4 on Ollama (96K) | 12.36 | 112.3 / 104.4 / 92.8 / 75.1 | 20.59 GB |
| oMLX MTP Deep | 24.43 | 115.9 / 110.4 / 105.5 / 91.3 | (oMLX-managed) |
| Saluki on llama.cpp | 13.51 | 104.2 / 102.1 / 95.5 / 76.9 | — |

Prefill is ~flat across engines and compressions (75–116 tok/s), reproducing the Bonsai-era finding: compression does not buy time-to-first-token. The 2-bit quant is also *dequant-heavy on Metal*: 8× smaller than the Q4 yet only 1.17× faster to decode.

Co-residency (P2b; each scenario = router pinned `keep_alive -1` → load C at 32K → load General · Fast at 16K → return to C at 2K; snapshots s0/s1/s2):

| Scenario | C resident at s1/s2 | Reload paid on return | Router kept | Swap growth | Free at s1 | General · Fast co-load |
|---|---|---|---|---|---|---|
| C = Saluki 96K | yes | no (0.06 s) | **yes** | 0 MB | 68 % | **BLOCKED** — oMLX admission: Fast needs 21.16 GB, dynamic ceiling 18.80 GB |
| C = Q4 96K | yes | no (0.02 s) | **NO — evicted** | 0 MB | 63 % | **BLOCKED** — ceiling 15.85 GB |
| C = oMLX Deep | yes (warm TTFT) | no | yes | 0 MB | 51 % | **OK** (68.96 tok/s) |

The honest headline for the operator's actual question: **neither Ollama arm achieved the full "C + Fast + router" triangle** — Fast's 21.16 GB admission estimate never fit under oMLX's dynamic ceiling with either C resident. Saluki nonetheless holds the router plus itself comfortably and leaves ~3 GB more oMLX headroom than the Q4, which pushes the router out of memory entirely. (An unconfirmed single observation: Ollama 0.40.0's runner appeared to wedge once on a ~95K-token needle prompt against the 98304 window — a `memory_seq_rm [77312, end)` during prefill, which may be a prompt-cache rollback rather than a context shift. One model, one occurrence; the Q4 90K row was never run, so this is not a reproduced engine fault. Receipt `p5c_needle_90k_ollama_engine_fault.json`.)

## P3 — tool calling

Single-tool `bench_tool_use_probe` (no `think` key, thinking-on for both — read relative to the incumbent): Saluki 4/4 (quality 1.0, 14.5 tok/s), incumbent 4/4 (12.4 tok/s). Parallel probe, n=10 per setting: **clean 10/10 at the card setting and 10/10 at the seat setting** on Saluki-96K, Q4-96K, oMLX Deep, and Saluki-on-llama.cpp; zero content leaks, zero malformed argument sets. Criterion 4 passes fully.

## P4 — multi-turn agentic (WFE, direct Ollama arms, n=3, 16-turn cap)

| Arm | Workload | PASS | Turn-cap loops | Median wall/task-run | Notes |
|---|---|---|---|---|---|
| Q4-32K (live control) | auto-compliance home 33 + research 9 | **27/42** | 8 | 23.1 s | 5 FAIL; 2 HARNESS_ERROR = contaminated instrument rows (task `comp-p6j-09` repeats 1–2 leaked the answer key into a tool result — checker refused to score; not model results) |
| Saluki-32K | same | **10/42** | **32** | 131.0 s | 0 FAIL — it doesn't answer wrong, it doesn't answer |
| Q4-96K | general-deep 27 | **18** (+9 pending review) | 0 | 36.5 s | 0 exhaustions |
| Saluki-96K | general-deep 27 | **14** (+9 pending review) | 3 | 24.9 s | 1 FAIL, 3 exhaustions |

Context rows from the Bonsai table (2026-09-24): incumbent-historical 33/42 with 3 loops; Bonsai-2 PQ2 21/42 with 12 loops. The live incumbent's 27/42 sits below the historical 33 (refreshed weights + the persona-less-prompt fix + Ollama 0.34→0.40), which is exactly why the task pre-registered the relative fallback — and Saluki fails that too.

**Saluki's named loop** (the analogue of Bonsai's `packet.json` re-read): repeated `repo_search` over `portal/modules/compliance/data/nerc_cip_map.json` and `nerc_cip_register.json` with pattern variants, and repeated `file_read` of the same map, until the cap — 160/160 tool calls executed without error; the transcripts show it deriving the strings it later hunts from material it just read.

**Rule-5 attribution — AMENDED 2026-10-12 (re-verify, `p4_rule5_reverify.json`, script `scripts/saluki_rule5_reverify.py`).** The original claim ("a 2-bit instruction-following collapse; hallucinated filenames; the model, not the harness") is **withdrawn as stated**. What the original proof got wrong: a same-template cross-engine repro clears the *engine*, not the *template or settings*; there was no incumbent arm in the diagnostic; the no-clause control ran only on llama.cpp, never on Ollama (the production engine); and think-on was never tested. The "hallucinated" filenames were a hunt for material the WFE prompt tells the model to fetch with tools the harness does not offer.

Re-verified minimal loop (file_read → answer, 6-turn cap; WFE system/user text verbatim; n=5 for S1–S3, n=3 for the rest). Step-0 delivery audit: the engine's prompt token count matches the official render within the trailing-newline artifact (Ollama's chat path drops the render's final `\n\n`; the stripped render matches exactly), and the think-on render has no empty think block. Cells:

| Cell | Setting | Result |
|---|---|---|
| S1 | lane sampling, think off, JSON clause | loop 5/5 |
| S2 | lane, repeat 1.0, think off, clause | loop 5/5 |
| S3 | card sampling, think off, clause | loop 3/5 |
| S4 | card sampling, **think on**, clause | answered-JSON 3/3 |
| S5 | lane, think off, **no clause** | answered 3/3 |
| S6 | lane, think off, clause, system prompt with the tool-referencing tail removed | loop 3/3 |
| I1 | incumbent Q4, lane, think off, clause | answered-JSON 3/3 |
| I2 | incumbent Q4, lane, think off, no clause | answered 3/3 |

Verdict: the loop is **think-off + the output-format clause + tool offers on a 2-bit reasoning model**. It is not the template (S6 rules out the prompt/tool-surface mismatch as the driver) and not the repeat penalty (S2). The incumbent answers at the same settings, so the instrument is valid. Saluki needs thinking to do this lane, at roughly 3× the tokens on the deep lane, which defeats its purpose as a fast resident seat. Tool-argument logging was added after the runs, so the diagnostic cells record tool names only. The WFE confirmation (S4 settings, 1 repeat, direct engine): comp-p6j-01 FAIL (answered, 3 tool calls), comp-p6j-03 PASS (4 calls), comp-p6j-05 not scored (stopped by operator decision mid-request). No pipeline arm was run.

## P5 — what the 2-bit compression costs

- **Deep lane (thinking on, each arm at its own card):** incumbent (Qwen thinking card, 1.0/0.95/20) **18/18**, Σ 11,149 completion tokens, 927 s. Saluki (its card, 0.6/0.95/20) **17/18**, Σ **35,917 tokens (3.2×)**, 2,618 s (2.8×) — the one miss is a 24,576-token `length` finish (a ~30-minute reasoning loop, no answer). The card's "with thinking on, it often reasons at length" is measured fact. This set is saturated, as pre-registered; the token/wall figures are the finding.
- **§A2 six-case read-test** (ALL cells through the pipeline `:9099` — qwen38 via `auto-compliance`, Saluki via the operator-authorized bench-only workspace `bench-saluki-27b`, trace-verified serving; fixed body `d2ee11a25e00`, baseline instruction): **Saluki 4/6**, failures `choice` (the documented conjunction class — dismissed the operator policy's joined list as bullet formatting and said all NERC latitude is in use) and `parent` (declared "no identified compliance gaps" over material containing that planted narrowing). **qwen38 reference 6/6 today** (its historical 4/6 predates the current fixed body). Bar: ≥ 4/6 → Saluki sits exactly at the tie line that kept gemma4, two conflict-detection cases below today's reference. No local rubric copy existed, so both seats were judged side by side under the instrument's own documented failure classes (single reader, not blinded; outcomes-only committed, answers stay operator-local).
- **Long-context needle** (3 distractors at 10/50/90 % depth): Saluki 6/6, Q4 6/6 (32K+64K rows; 0 distractor hits anywhere), oMLX Deep 9/9 including the 90K row. The 90112 row on the Ollama Saluki arm is an **unexplained cell** (the unconfirmed single observation above), not a model result; it is not a confirmed engine fault. Needle recall shows **no** long-context cost from the 2-bit compression at these sizes.
- **Vision (P6):** Saluki-with-projector 2/2 on Ollama and 2/2 on llama.cpp; incumbent (which ships a projector) 2/2.

## Mid-run operator corrections, and how they were honored

1. *"All tests via the pipeline, never direct; direct is only to validate it works."* Then: *"You're doing too much, just run the file as it is written."* Resolution: the campaign ran as the task file was written (its own exemption: raw model/engine probes, not seat decisions), while every genuinely product-facing instrument stayed pipeline-mediated — the §A2 read-test refused direct calls by design and was run entirely through the pipeline; the WFE plan header records the direct-arms basis; P1/P3 probes are the "validate it works" class.
2. *"You aren't to promote anything, but you can't complete the test without making the changes needed to do so."* → The §A2 unblock was done additively and bench-only: `bench-saluki-27b` (eval module) + the tag in `backends.yaml` + MODEL_CATALOG + bench prompt-map entries; `sync-config`; pipeline rebuild; one live request verified from the trace (backend `ollama-general`, served model = the tag). No production workspace hints the tag; nothing was promoted. The bench seat was registered for §A2 only and removed after the re-verify (teardown commit `chore(bench): remove Saluki spike bench registration`).
3. *"When complete, do not promote anything, only write the report."* → This document plus the receipts; no seating, no config beyond the bench registration above.

## What would reopen it

- **A mid-bit quant that keeps the residency story:** an IQ3_XS/IQ3_S build (~10–11 GB) is the natural retest — the 2-bit tail (IQ1_S/IQ1_M) is where the agentic and format-instruction behavior collapses, while needle recall was already fine.
- **The 18 pending blinded-review rows** (9 per general-deep arm): if Saluki takes ≥4 of its 9 while the incumbent takes none, criterion 2 flips to PASS — the only criterion still open.
- **Closed (2026-10-12):** the "harness-side mitigation" path (drop the JSON clause when tools are offered) is not a route to a seat: the loop is conditional on think-off + clause + tools, and the deep-lane fix (think on) costs ~3× tokens. Any future Saluki attempt must be a think-on evaluation with a token budget, which the operator has not requested.
- **Ollama > 0.40** only if the ~95K observation is first reproduced (it is unconfirmed); the no-tooling-upgrades rule stood.
- **Closed (2026-10-12):** the 18 pending blinded-review rows and the criterion-2 path are not pursued; gate is REJECTED.
