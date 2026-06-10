# Fleet Refresh V2 — Phase 6 Bench Report

**Date**: 2026-06-09  
**Task**: TASK_MODEL_FLEET_REFRESH_V2  
**Results file**: `bench_fleet_refresh_v2.json`  
**Stack**: Ollama 0.30.7 (MLX Metal), M4 Pro 64 GB, MAX_LOADED_MODELS=2  
**Floor**: 20 TPS (workhorse); quality-lane q8 results are informational only — no floor verdict applies.

---

## Tier 1 — Quality Lanes (informational, q8 baseline)

| Workspace | Model | Avg TPS | Range | CV | Runs | Notes |
|---|---|---|---|---|---|---|
| auto-data | deepseek-r1:32b-q8_0 | **5.2** | 5.1–5.3 | 0.019 | 3/3 | Quality lane — q8 by design |
| auto-mistral | Magistral-Small-2509 Q8_0 | **5.9** | 5.6–6.2 | 0.053 | 3/3 | Quality lane — q8 by design |

Both lanes are consistent and within expected range for 32B/24B q8 on this hardware. No action.

---

## Tier 2 — Workhorse Candidates + MTP A/B

### MTP A/B Pair

| Workspace | Model | Avg TPS | Range | CV | Runs | TTFT | Decision |
|---|---|---|---|---|---|---|---|
| bench-qwen36-27b | qwen3.6:27b-q8_0 (29 GB) | **4.2** | 3.3–5.0 | 0.205 | 3/3 | 0.84 s | **HOLD** |
| bench-qwen36-27b-mtp | portal5/qwen3.6-27b-mtp:q8_0-drafted (46 GB) | **5.1** | 4.3–6.3 | 0.212 | 3/3 | 1.26 s | **HOLD** |

**MTP delta**: +0.9 TPS / +21% — speculative decoding is functional and measurable on Ollama 0.30.7.  
**Verdict**: Neither promotes. Absolute TPS (4–5) is too far below the 20 TPS workhorse floor. The 46 GB MTP footprint (q8 base + q4_K_M draft) consumes 72% of system RAM, compressing the inference pool to near-zero. Dense 27B q8 is a quality-lane pattern, not a workhorse.

**MTP takeaway for next pass**: Draft quantization is the right lever — a q4_K_XL base with a q2 or 1.5B draft would shrink total footprint to ~18–20 GB while preserving the speculative delta. Revisit when Unsloth publishes an MTP-bundled UD quant for the 27B. The +21% architecture result is banked.

---

### Phase 4 Candidates

| Workspace | Model | Approx GB | Avg TPS | Range | CV | Runs | TTFT | QS | Decision |
|---|---|---|---|---|---|---|---|---|---|
| bench-qwen36-35b-a3b-ud | hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL | ~22 GB | **23.0** | 21.6–24.0 | 0.055 | 3/3 | 0.35 s | 0.67 | **PROMOTE** |
| bench-qwen36-abl-27b | huihui_ai/Qwen3.6-abliterated:27b | ~17 GB | **6.3** | 6.1–6.7 | 0.051 | 3/3 | 0.72 s | 1.0 | **PRUNE** |
| bench-qwen36-hauhaucs | fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4 | ~22 GB | **26.6** | 24.9–27.7 | 0.055 | 3/3 | 0.31 s | 1.0 | **PROMOTE** |
| bench-gptoss | (existing fleet model) | — | **34.5** | 32.0–38.2 | 0.095 | 3/3 | 0.39 s | 0.67 | **RETAIN** |

**bench-qwen36-35b-a3b-ud** (23.0 TPS): Passes floor with 3 TPS margin. Tight CV (0.055). MoE 3B-active pays for itself — 35B parameter density at 22 GB. QS 0.67 reflects partial coding output (expected for a non-coder general model, not a quality defect). Candidate for `auto-general` or uncensored creative workspace.

**bench-qwen36-abl-27b** (6.3 TPS): Dense 27B Q4 at 17 GB still only reaches 6.3 TPS — this confirms the dense-27B-is-slow result from the A/B pair. Tight CV (0.051) means the result is reliable, not a measurement artifact. **Prune bench slot** — the model can remain in backends.yaml catalog for targeted use but should not hold a workhorse workspace.

**bench-qwen36-hauhaucs** (26.6 TPS): Passes floor comfortably, 6+ TPS above threshold. Perfect QS (1.0) on coding bench. MoE efficiency matches the UD variant. HauhauCS abliteration profile (0/465 refusals, low KL-divergence) makes this the best candidate for `auto-creative`/music workspace. **Promote.**

**bench-gptoss** (34.5 TPS): Highest throughput in the Tier 2 field. Already in fleet. Retain.

---

## Tier 3 — Coding Shootout

C1 candidate (bench-qwen36-35b-a3b-ud) covered in Tier 2.  
Gen-1 Devstral vs existing fleet coding tier:

| Workspace | Model | Avg TPS | Range | CV | Runs | TTFT | QS | Decision |
|---|---|---|---|---|---|---|---|---|
| bench-devstral | Devstral-22B (gen-1) | **8.5** | 8.3–8.8 | 0.029 | 3/3 | 0.57 s | 0.83 | **PRUNE** |
| bench-laguna | Laguna-XS.2 (existing) | **24.8** | 24.2–25.1 | 0.021 | 3/3 | 0.71 s | 1.0 | **RETAIN** |
| bench-glm | GLM-4 Flash (existing) | **27.2** | 24.3–29.2 | 0.094 | 3/3 | 0.32 s | 0.67 | **RETAIN** |
| bench-qwen3-coder-30b | qwen3-coder:30b (candidate) | **30.9** | 28.7–33.5 | 0.079 | 3/3 | 0.22 s | 0.83 | **PROMOTE** |

**bench-devstral** (8.5 TPS): Below floor. Tight CV (0.029) confirms the measurement is accurate — this is a genuine throughput limitation, not noise. At 8.5 TPS on the coding bench with QS 0.83, gen-1 Devstral is capable but 2.4× too slow to serve as a default coding model. Prune bench slot. Note: Mistral will likely ship a faster Devstral 2; re-bench when available.

**bench-laguna** (24.8 TPS, CV **0.021**): Lowest variance of any model in the shootout — exceptionally steady. Highest avg token count (317) suggests verbose, structured responses. Strong QS (1.0). Retains its position as the reliable coding baseline.

**bench-glm** (27.2 TPS): Above floor, wider variance (CV 0.094 — likely temperature interaction or context-length variance run-to-run). QS 0.67. Retains.

**bench-qwen3-coder-30b** (30.9 TPS, TTFT **0.22 s**): Fastest coder in the fleet, fastest TTFT of any model tested. QS 0.83. **Promote to `auto-coding` primary** — the sub-quarter-second first token makes it the clear winner for interactive coding use. 30B MoE active-parameter efficiency is working as expected.

---

## Summary — Operator Decision Table

| Bench Workspace | Model | TPS | Recommendation | Target Lane |
|---|---|---|---|---|
| bench-qwen36-27b | qwen3.6:27b-q8_0 | 4.2 | **HOLD** — quality-lane behavior only | — |
| bench-qwen36-27b-mtp | portal5/qwen3.6-27b-mtp:q8_0-drafted | 5.1 | **HOLD** — MTP +21% confirmed; footprint too large | revisit with UD q4 base |
| bench-qwen36-35b-a3b-ud | unsloth UD-Q4_K_XL | 23.0 | **PROMOTE** ✓ | auto-general or uncensored |
| bench-qwen36-abl-27b | huihui_ai abliterated 27B Q4 | 6.3 | **PRUNE bench slot** | catalog-only |
| bench-qwen36-hauhaucs | HauhauCS Q4 MoE | 26.6 | **PROMOTE** ✓ | auto-creative / music |
| bench-gptoss | (existing) | 34.5 | **RETAIN** | existing lane |
| bench-devstral | Devstral 22B gen-1 | 8.5 | **PRUNE bench slot** | — |
| bench-laguna | Laguna-XS.2 | 24.8 | **RETAIN** | auto-coding |
| bench-glm | GLM-4 Flash | 27.2 | **RETAIN** | auto-coding |
| bench-qwen3-coder-30b | qwen3-coder:30b | 30.9 | **PROMOTE** ✓ | auto-coding primary |

**Operator decides on all promotions before any hint or routing changes.**

---

## Flagged for Next Pass

- **phi4-successor research**: phi4-mini and phi4-reasoning have not been benchmarked. Phi4-mini at ~3.8B should reach 60+ TPS on M4 Pro — candidate for fast-lane or router-adjacent use. Schedule a dedicated bench pass.
- **MTP round 2**: Obtain or build a UD-Q4_K_XL + q2 draft combination for bench-qwen36-27b-mtp. Target footprint ≤ 22 GB total to fit alongside inference pool. The +21% delta on the q8 pair makes this worth pursuing.
- **Devstral gen-2**: When Mistral releases the next Devstral variant, re-bench against the current coding tier (laguna / qwen3-coder:30b).
- **tools audit**: bench-qwen36-hauhaucs and bench-qwen36-35b-a3b-ud are marked `supports_tools: true` in backends.yaml but were not verified with `--audit-tools` before bench. Run before promotion to active routing.

---

*Report generated from `bench_fleet_refresh_v2.json` — 12 workspaces, 36 runs, 0 failures.*
