# WFE Fitness Report — `s8_fast_baseline_20261029d`

Generated 2026-10-29T06:17:21.327425+00:00
Environment: git `9b22e5d6` · Ollama `0.40.12` · fingerprint `63a0745597ea`

## 1. Instrument health

Every run by outcome. Rows marked *(excluded)* are instrument failures —
the harness, not the model — and are removed from every rate below.

| Outcome | Count |
|---|---|
| PASS | 12 |

0 of 12 run(s) excluded as instrument failures.

## 2. Fitness matrix

## 2a. Speed by arm

Decode tok/s and TTFT are the primary speed measures. Answer tok/s includes only rows with at least 32 answer tokens; n is the number of observations in each median, and p90 uses nearest-rank percentile.

| Workspace | Lane | Arm | Decode tok/s med (n) | Decode tok/s p90 | TTFT s med (n) | TTFT s p90 | Answer tok/s med (n, >=32 tokens) | Answer tok/s p90 | Total s med (n) | Total s p90 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| tools-specialist::fast | home:tools_specialist_production | `gemma4:e4b-it-qat-ctx8k` | 12.37 (n=12) | 18.77 | 0.94 (n=12) | 0.98 | — (n=0) | — | 10.49 (n=12) | 11.52 |

Rates count only model-attributable outcomes. Brackets are Wilson 95% intervals.

| Workspace | Lane | Arm | Role | Persona | Rate | Excluded | Med tok | Med s |
|---|---|---|---|---|---|---|---|---|
| tools-specialist::fast | home:tools_specialist_production | `gemma4:e4b-it-qat-ctx8k` | incumbent | — | 12/12 = 1.00 [0.76–1.00] | 0 | 1282 | 12.0 |

## 3. Incumbent vs challenger

_No challenger produced a comparable result._

_NOT SEPARATED means the intervals overlap: the evidence does not order the two arms. It is not a tie and must not be read as one._

## 4. Creative lane (blinded review)

0 responses queued; 0 scored. Unscored items are excluded from every rate above.

## 5. Decision packets

Stop rules quoted verbatim from the closeout register. Dispositions are operator gates.

### `command-r:35b-08-2024-q4_K_M`

- **Question:** Where does this model ACTUALLY belong in real use?
- **Recorded test:** auto-documents/documents-MCP grounded RAG with citations (its card's design purpose) vs granite4.1:8b-ctx16k incumbent on real corpora
- **Stop rule:** grounded-citation quality > incumbent on real documents -> INTEGRATE as RAG seat; else REMOVED
- **Prior disposition:** REMOVED_CLOSED
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `deepseek-ocr:latest`

- **Question:** Where does this model ACTUALLY belong in real use?
- **Recorded test:** documents-MCP real OCR comparison: deepseek-ocr vs MLX PaddleOCR-VL/dots.ocr on 10 real document images
- **Stop rule:** MLX stack >= Ollama OCR on real docs -> REMOVED
- **Prior disposition:** REMOVED_CLOSED
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `gemma4:e2b-it-qat`

- **Question:** Where does this model ACTUALLY belong in real use?
- **Recorded test:** same fast-utility discovery at 2B (lowest-latency tier)
- **Stop rule:** no niche -> REMOVED
- **Prior disposition:** REMOVED_CLOSED
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `gemma4:e4b-it-q4_K_M`

- **Question:** Where does this model ACTUALLY belong in real use?
- **Recorded test:** same fast-utility discovery (non-QAT quant comparison arm)
- **Stop rule:** no niche -> REMOVED
- **Prior disposition:** REMOVED_CLOSED
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `gemma4:e4b-it-qat`

- **Question:** Where does this model ACTUALLY belong in real use?
- **Recorded test:** fast sub-agent lane discovery: router-assist/drafting/classifier assist tasks vs E4B-OBLITERATED (its family holds the router default)
- **Stop rule:** no utility niche vs router default + daily driver -> REMOVED
- **Prior disposition:** INTEGRATED
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `glm-4.7-flash:Q4_K_M`

- **Question:** Does unpruned GLM-4.7-flash beat REAP-23B on coding/tool-flow tasks?
- **Recorded test:** glm_coder eval tool-flow subset, head-to-head
- **Stop rule:** <= REAP-23B -> remove; REAP stays the lane
- **Prior disposition:** INTEGRATED
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `glm-ocr:Q8_0`

- **Question:** Where does this model ACTUALLY belong in real use?
- **Recorded test:** same OCR comparison (GLM lineage arm)
- **Stop rule:** same as deepseek-ocr
- **Prior disposition:** REMOVED_CLOSED
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `granite4.2:30b-q4_K_M`

- **Question:** Where does this model ACTUALLY belong in real use?
- **Recorded test:** analyst personas (dashboardarchitect/dataanalyst) real long-document analysis at proper context; its judgment gap was measured on 500-token packets
- **Stop rule:** no analyst-lane advantage over 4.1:30b in real use -> REMOVED (council reject stands regardless)
- **Prior disposition:** REMOVED_CLOSED
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `hf.co/ggml-org/dots.ocr-GGUF:Q8_0`

- **Question:** Where does this model ACTUALLY belong in real use?
- **Recorded test:** same OCR comparison (dots.ocr lineage arm)
- **Stop rule:** same as deepseek-ocr
- **Prior disposition:** REMOVED_CLOSED
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `hf.co/mradermacher/Nanonets-OCR2-3B-GGUF:Q4_K_M`

- **Question:** Where does this model ACTUALLY belong in real use?
- **Recorded test:** same OCR comparison (Nanonets lineage arm; MLX Nanonets-8bit already owned)
- **Stop rule:** same as deepseek-ocr
- **Prior disposition:** REMOVED_CLOSED
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `kat-coder-v2.5-dev:Q4_K_M`

- **Question:** Where does this model ACTUALLY belong in real use?
- **Recorded test:** auto-coding/splunkdetectionauthor-style real tasks in the IDE flow WITH tools (read->explore->edit->verify), 10+ real repo tasks
- **Stop rule:** completes real tool-loop tasks >= incumbent lane -> INTEGRATE as fast-repair lane; else REMOVED
- **Prior disposition:** INTEGRATED
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `orcarouter/Qwen3.8-27B-Uncensored:Q4_K_M`

- **Question:** Does Qwen3.8-uncensored beat the incumbent on refusal-preservation AND utility?
- **Recorded test:** refusal probe + 10-problem coding subset
- **Stop rule:** no win on either -> remove
- **Prior disposition:** REMOVED_CLOSED
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `qwen36-fable-fusion-711:Q4_K_M`

- **Question:** Where does this model ACTUALLY belong in real use?
- **Recorded test:** auto-creative/creativewriter real sessions (multi-turn story work, style adherence, persona prompt) — no synthetic probe exists for creative fit
- **Stop rule:** operator-judged creative parity or better vs seated creative seats -> RETAIN as creative seat; else REMOVED
- **Prior disposition:** RETAINED_FOR_PURPOSE
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M`

- **Question:** Does FastContext-4B produce useful cited repo exploration for the IDE path?
- **Recorded test:** pull tag; run pipeline_mcp explore_repository on this repo; review citations/turns
- **Stop rule:** poor citations or broken tool flow after pull -> REMOVED_CLOSED for good
- **Prior disposition:** REMOVED_CLOSED
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `gpt-oss:20b`

- **Question:** Does GPT-OSS 20B add reasoning diversity over DeepSeek-R1-0528 + Qwen3.6-35B incumbents?
- **Recorded test:** 30-case judgment run + diversity delta vs both incumbents
- **Stop rule:** F2 < 0.80 OR no measurable diversity gain -> remove without further tests
- **Prior disposition:** contender_test_plan
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `glm-4.7-flash:Q4_K_M`

- **Question:** Does unpruned GLM-4.7-flash beat REAP-23B on coding/tool-flow tasks?
- **Recorded test:** glm_coder eval tool-flow subset, head-to-head
- **Stop rule:** <= REAP-23B -> remove; REAP stays the lane
- **Prior disposition:** contender_test_plan
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:Q4_K_M`

- **Question:** Does abliterated-35B materially beat the 27B incumbent on uncensored general quality?
- **Recorded test:** refusal-preservation probe + 30-case judgment at ctx8k
- **Stop rule:** no quality gain worth +12 GiB residency -> remove
- **Prior disposition:** contender_test_plan
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M`

- **Question:** Does N2-mini beat Aquila-mini on research/agent tasks?
- **Recorded test:** research probe set head-to-head (Aug-13 attempt exists but no comparative data)
- **Stop rule:** below Aquila -> remove
- **Prior disposition:** contender_test_plan
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `orcarouter/Qwen3.8-27B-Uncensored:Q4_K_M`

- **Question:** Does Qwen3.8-uncensored beat the incumbent on refusal-preservation AND utility?
- **Recorded test:** refusal probe + 10-problem coding subset
- **Stop rule:** no win on either -> remove
- **Prior disposition:** contender_test_plan
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `kat-coder-v2.5-dev:Q4_K_M`

- **Question:** Does kat-coder-v2.5 beat the MoE-trio baseline on the same coding exam?
- **Recorded test:** 10-problem exam, same harness as BENCH_REPAIR_MOE_CODERS_20260826
- **Stop rule:** < 43/50 one-shot -> remove
- **Prior disposition:** contender_test_plan
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `portal5/fara1.5-27b:Q4_K_M`

- **Question:** Does fara1.5-27b beat the daily driver on judgment + daily tasks?
- **Recorded test:** 30-case judgment + daily task probe
- **Stop rule:** <= 0.80 exact (incumbent cluster floor) -> remove
- **Prior disposition:** contender_test_plan
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `qwen36-fable-fusion-711:Q4_K_M`

- **Question:** Does the merge beat its own parent quant?
- **Recorded test:** 30-case judgment vs library qwen3.6:27b quant
- **Stop rule:** <= parent -> remove (merge adds nothing)
- **Prior disposition:** contender_test_plan
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M`

- **Question:** Is the bartowski conversion distinguishable from the library quant?
- **Recorded test:** provenance check + 10-case judgment subset equivalence
- **Stop rule:** statistically indistinguishable -> remove as duplicate quant
- **Prior disposition:** contender_test_plan
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `granite4.2:30b-q4_K_M`

- **Question:** Does newer granite4.2-30b beat 4.1-30b on analyst (non-council) tasks?
- **Recorded test:** analyst/compliance mixed set head-to-head
- **Stop rule:** <= 4.1 -> remove; council reject stands regardless
- **Prior disposition:** contender_test_plan
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `granite4.2:8b-q8_0`

- **Question:** Does 4.2-8b beat 4.1-8b with a corrected template?
- **Recorded test:** tools/blueteam probe with template fix
- **Stop rule:** <= 4.1 OR template still dishonored -> remove
- **Prior disposition:** contender_test_plan
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `granite4.1:8b-q8_0`

- **Question:** Does Q8 measurably beat the seated Q4 quant?
- **Recorded test:** tools/compliance probe Q8 vs Q4
- **Stop rule:** within noise -> remove (Q4 seat stays)
- **Prior disposition:** contender_test_plan
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

### `qwen3-vl:8b-instruct-q4_K_M`

- **Question:** Is 8B close enough to 32B for the vision personas at 5.7 GiB vs 23.7?
- **Recorded test:** vision probe set head-to-head
- **Stop rule:** materially below 32b -> remove
- **Prior disposition:** contender_test_plan
- **Status:** NO WFE EVIDENCE

  `[GATE] operator disposition: ______________  reason: ______________`

## 6. Coverage and provisionality

_A disposition that depends on a dimension this campaign did not exercise is provisional until that dimension's instrument exists and has run for the models in question. This is what "proper testing before fold/purpose/removed" means operationally._

**Exercised by this campaign:**

- 1. Settings/design/intent audit
- 3. Think/stream/endpoint/tool-contract fidelity
- 4. Real-work tool loops in-lane — _Every row runs against one fixed generic sandbox (file_read/file_list/repo_search/pytest_run/file_write/http_get) — tool_surface_proxy=true on all 513 wfe_full_20260911 rows, confirmed 2026-09-12. No workspace's actually-declared tools (auto-research's web_search/web_fetch/news_search, auto-documents' create_word_document/read_*, tools-specialist's execute_python/remember/recall) are wired in, because the harness deliberately runs with the live MCP fleet down (no contention for Ollama/memory during a sweep). Coding-lane tasks approximate this reasonably; research/documents/compliance tool-loop rates should be read as 'can it use A tool', not 'can it use its real tool'._
- 5. Cross-lane discovery
- 20. Checker soundness (unit tests FOR checkers)
- 21. Suite calibration & statistical power
- 22. Environment fingerprint gate
- 24. Token economics (cost per completed task)
- 27. Checker gameability (adversarial fixtures)
- 28. Harness determinism (persona/seed/sampling pinned)

**NOT exercised — every disposition above is provisional against these:**

- 2. Card ground truth (sampling/ctx/tools/template)
- 6. Lineage diversity
- 7. Memory co-residency / live swap
- 8. Production-sampling fitness (n>=3 at lane temp)
- 9. Effective context (graded needle fills)
- 10. Prompt-eval latency at fill (TTFT)
- 11. Multi-turn accumulation (10-20 turns)
- 12. Memory/RAG tool fidelity (remember->recall)
- 13. Tool-error recovery injection
- 14. Tool discipline / no confabulated success
- 15. Truncation & schema conformance
- 16. Fake-citation detection (fetch-grounded) — _check_cited_answer exists but no suite task calls it as of 2026-09-12 — the two tasks that did (res-granite-ctx, res-ollama-ctx) required guessing a live URL from memory with no search primitive in the sandbox; both hardcoded URLs had gone dead, so this was measuring URL-memorization, not model quality, for every arm that ran them (14 arms). Converted to hermetic file_read-seeded fixtures (answer_contains) to remove the failure mode; live fetch-grounded citation testing is unbuilt again until a self-contained way to test it (without standing up the real search stack) exists._
- 17. Prompt-injection robustness
- 18. Over-compliance placement risk
- 19. Contamination control (private task bank)
- 23. Standing canary suite post-swap
- 25. Cold-start & concurrency under real loading
- 26. Multimodal through the pipeline
- 29. Compliance reading closure completeness — _The compliance reading contract checker is present and the suite carries a receipt task; live campaign evidence is still required._
- 30. Compliance citation resolution — _The checker rejects unresolved citations, while citation recall/precision remains the offline evaluation instrument._
- 31. Compliance unsupported-absence rate — _The checker requires zero unsupported absence claims; the live reading arm must still be run._
- 32. Compliance tool-selection validity — _The suite requires compliance_requirement as the first tool; measured live selection is not yet a promotion decision._
