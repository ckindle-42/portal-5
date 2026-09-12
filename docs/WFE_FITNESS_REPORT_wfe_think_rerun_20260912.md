# WFE Fitness Report — `wfe_think_rerun_20260912`

Generated 2026-09-12T13:12:34.971224+00:00
Environment: git `f7e51269` · Ollama `0.33.2` · fingerprint `87791b227a72`

## 1. Instrument health

Every run by outcome. Rows marked *(excluded)* are instrument failures —
the harness, not the model — and are removed from every rate below.

| Outcome | Count |
|---|---|
| FAIL | 37 |
| PASS | 103 |
| REFUSED | 7 |

0 of 147 run(s) excluded as instrument failures.

Preflight notes (informational — did not block the arm):

- `granite4.2:30b-q4_K_M` — format:json returns empty content — not predicted by the card — card ground truth owed (WFE-0.6); this model cannot serve strict-JSON tasks (the campaign runs none). Observed: ''
- `gpt-oss:20b` — card records format_json_safe: false but format:json returned clean JSON ('{"ok": true}') — card may be stale, re-verify

## 2. Fitness matrix

Rates count only model-attributable outcomes. Brackets are Wilson 95% intervals.

| Workspace | Lane | Arm | Role | Persona | Rate | Excluded | Med tok | Med s |
|---|---|---|---|---|---|---|---|---|
| auto-compliance | home:compliance_agentic | `gpt-oss:20b` | challenger | cippolicywriter | 18/30 = 0.60 [0.42–0.75] | 0 | 4789 | 11.5 |
| auto-compliance | home:compliance_agentic | `granite4.1:30b-ctx16k` | challenger | cippolicywriter | 18/30 = 0.60 [0.42–0.75] | 0 | 3254 | 10.6 |
| auto-compliance | home:compliance_agentic | `granite4.2:30b-q4_K_M` | challenger | cippolicywriter | 18/30 = 0.60 [0.42–0.75] | 0 | 3719 | 13.1 |
| auto-compliance | home:compliance_agentic | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` | incumbent | cippolicywriter | 24/30 = 0.80 [0.63–0.91] | 0 | 5847 | 22.7 |
| auto-compliance | disc:research | `gpt-oss:20b` | challenger | cippolicywriter | 7/9 = 0.78 [0.45–0.94] | 0 | 3307 | 16.1 |
| auto-compliance | disc:research | `granite4.2:30b-q4_K_M` | challenger | cippolicywriter | 9/9 = 1.00 [0.70–1.00] | 0 | 3759 | 22.8 |
| auto-compliance | disc:research | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` | incumbent | cippolicywriter | 9/9 = 1.00 [0.70–1.00] | 0 | 5687 | 33.4 |

## 3. Incumbent vs challenger

| Workspace | Lane | Challenger | Challenger rate | Incumbent rate | Verdict |
|---|---|---|---|---|---|
| auto-compliance | home:compliance_agentic | `gpt-oss:20b` | 18/30 = 0.60 [0.42–0.75] | 24/30 = 0.80 [0.63–0.91] | **NOT SEPARATED (n insufficient)** |
| auto-compliance | home:compliance_agentic | `granite4.1:30b-ctx16k` | 18/30 = 0.60 [0.42–0.75] | 24/30 = 0.80 [0.63–0.91] | **NOT SEPARATED (n insufficient)** |
| auto-compliance | home:compliance_agentic | `granite4.2:30b-q4_K_M` | 18/30 = 0.60 [0.42–0.75] | 24/30 = 0.80 [0.63–0.91] | **NOT SEPARATED (n insufficient)** |
| auto-compliance | discovery:research | `gpt-oss:20b` | 7/9 = 0.78 [0.45–0.94] | 9/9 = 1.00 [0.70–1.00] | **NOT SEPARATED (n insufficient)** |
| auto-compliance | discovery:research | `granite4.2:30b-q4_K_M` | 9/9 = 1.00 [0.70–1.00] | 9/9 = 1.00 [0.70–1.00] | **NOT SEPARATED (n insufficient)** |

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
- **Prior disposition:** RETAINED_FOR_PURPOSE
- **Status:** EVIDENCE PRESENT — OPERATOR GATE
  - auto-compliance / home:compliance_agentic — 18/30 = 0.60 [0.42–0.75] (excluded 0, med 3719 tok / 13.1 s)
  - auto-compliance / discovery:research — 9/9 = 1.00 [0.70–1.00] (excluded 0, med 3759 tok / 22.8 s)
  - vs incumbent `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` on compliance_agentic: **NOT SEPARATED (n insufficient)**
  - vs incumbent `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` on research: **NOT SEPARATED (n insufficient)**

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
- **Prior disposition:** INTEGRATED
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
- **Status:** EVIDENCE PRESENT — OPERATOR GATE
  - auto-compliance / home:compliance_agentic — 18/30 = 0.60 [0.42–0.75] (excluded 0, med 4789 tok / 11.5 s)
  - auto-compliance / discovery:research — 7/9 = 0.78 [0.45–0.94] (excluded 0, med 3307 tok / 16.1 s)
  - vs incumbent `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` on compliance_agentic: **NOT SEPARATED (n insufficient)**
  - vs incumbent `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` on research: **NOT SEPARATED (n insufficient)**

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
- **Status:** EVIDENCE PRESENT — OPERATOR GATE
  - auto-compliance / home:compliance_agentic — 18/30 = 0.60 [0.42–0.75] (excluded 0, med 3719 tok / 13.1 s)
  - auto-compliance / discovery:research — 9/9 = 1.00 [0.70–1.00] (excluded 0, med 3759 tok / 22.8 s)
  - vs incumbent `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` on compliance_agentic: **NOT SEPARATED (n insufficient)**
  - vs incumbent `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` on research: **NOT SEPARATED (n insufficient)**

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
