# BENCH_REWIRE_PLAN_V1 — reasoning-group overhaul (evidence-final)

Companion to `PROPOSED_REASONING_OVERHAUL_V3.md`. This doc is the execution plan: what we bench,
against what evidence, with what acceptance criteria. All speed numbers marked (measured) come from
this machine's own bench results; quality numbers are cited to their source.

## Research findings (Aug 2026, verified)

### Candidates validated
| Model | Speed on this M4 Pro | Quality evidence (source) | Verdict |
|---|---|---|---|
| `qwen3.6:35b-a3b` | **54.2 t/s (measured)**, installed | Lineage beats Cascade-2 on GPQA (84.2 v 76.1), τ²-Bench (81.2 v 58.9), SWE (69.2 v 50.2) per NVIDIA's own comparison table | **Tier-1 primary, stock slots. Zero new download.** |
| `nemotron-cascade-2:30b` | unmeasured here; A3B class ⇒ expect 45-60 | IFBench 82.9 / ArenaHard 83.5 class leaders (NVIDIA card); AA Intelligence Index 18 vs median 9 (#34/14018); runs correctly on llama.cpp Q4_K_M per independent RTX-5090 rig (MMLU 74.4, GSM8K 87.1, HumanEval 79.3). Text-only, 1M ctx native | **Compliance challenger — bench-gated** |
| `qwen3.8:27b` | 6.8 t/s (measured Aug 14) — **support landed Ollama v0.33.0 (~Aug 21); re-bench on v0.33.2+ before accepting** | GPQA 89.2 / HLE 30.8 / LCB v6 90.3 / IFBench 79.5 + full VL (MathVision 90.0, OSWorld 84.3) (Qwen card); repo bench quality_score 1.0. Hybrid DeltaNet+Attention arch | **Tier-2 deep lane entry** |
| `gemma4:12b` | **26.4 t/s (measured) — above floor, dense** | GPQA 78.8 beats Cascade-2's 76.1 (Google card); but fleet's own gemma4-26b-A4B (GPQA 82.3 @ 55 t/s measured) dominates it | Not for reasoning group; watchlist for encoder-free unified vision/audio slots |
| `gpt-oss:20b` | 50.7 t/s (measured), installed | repo q=1.0; OpenAI reasoning MoE | **Tier-1 fast tier, keep** |
| `huihui_ai/tongyi-deepresearch-abliterated` | 49.2 t/s (measured), installed | Deep-research intent fit; unc posture | **Unc slot primary, keep (retire -ctx64k variant)** |
| `granite4.1:8b` | 21.4 t/s (measured) | tool-capable small | keep |
| `olmo-3.1:32b-think` | 8.3 t/s (measured) | GPQA 57.5 / IFBench 68.1 (Ai2 card) — weaker AND slower than qwen3.8:27b | **DISQUALIFIED for tier-2** |
| `empero-ai/Qwen3.8-9B-Distill` | unbenched | community distill, no quality evidence yet | watchlist only — bench before any use |

### Key research conclusions
1. **Dense sweet-spot zone is ≤12B on this hardware** (12B dense = 26.4 t/s; 27B+ dense = 4-12 t/s).
   Above 12B, only MoE clears the floor — except the deliberate deep lane.
2. **qwen3.8:27b's 6.8 t/s is kernel immaturity, not physics**: Qwen3.8 support landed in Ollama
   v0.33.0 ten days before the bench; llama.cpp DeltaNet-hybrid kernels are actively landing
   (v0.33.1 "MLX and llama.cpp update"). Re-bench each Ollama release; MLX build exists as fallback
   reference.
3. **Cascade-2 is the one acquisition worth benching**: independent rig confirms llama.cpp
   compatibility; IFBench/ArenaHard leadership matches the compliance slot's exact need
   (structured, instruction-following document work). Text-only is acceptable for compliance.

## Bench matrix (post-UAT execution, in order)

| # | Bench | Models | Pass criteria | Action on pass |
|---|---|---|---|---|
| B1 | t/s @ 8K/32K ctx + persona-matrix (compliance prompts) | cascade-2:30b vs qwen3.6:35b-a3b | cascade ≥30 t/s AND beats qwen3.6-35b on matrix quality | promote → `auto-compliance` primary |
| B2 | t/s @ 32K (deep-lane sim: tier-1 evicted) | qwen3.8:27b on Ollama v0.33.2+ | document actual t/s (no floor — tier-2) | wire as deep lane, record t/s in backends.yaml |
| B3 | none (reorder) | qwen3.6:35b-a3b → `auto-data`/`auto-reasoning`/`auto-math` primaries | already measured 54.2 t/s | wire immediately on operator approval |
| B4 | persona-matrix (optional) | gemma4-26b-a4b vs qwen3.6:35b-a3b for stock slots | only if B1 loser needs a second challenger | decide from matrix |
| B5 | t/s probe (per Ollama release) | qwen3.8:27b | track kernel-maturity curve | update deep-lane expected t/s |

## Declines (fold into model_cleanup_audit)

granite4.1:30b ×3 · deepseek-r1:32b q4+q8 · GLM-Z1-Rumination-32B ×2 · qwen3.6:27b q8+q4 ·
Qwopus3.6-27B-v2-MTP · supergemma4-26b-uncensored ×2 · Magistral-Small Q8-ctx64k ·
olmo-3.1:32b-think · olmo-3-32b MLX variants. ~150GB+ reclaim.

## Wiring order (post-approval)

1. B3 reorder (no downloads) → re-run deferred compliance + heavy research persona rows
2. B1 cascade-2 bench → promote if passed
3. B2 deep-lane wire + B5 tracking
4. A1/A2 rerun queue under new config
5. v9 re-baseline of affected spaces
