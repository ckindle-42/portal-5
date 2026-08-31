# PROPOSED_REASONING_OVERHAUL_V3 — two-tier reasoning group

**Supersedes V2.** V2 over-applied the 20 t/s floor as absolute; the operator's correction stands,
with evidence: dense CAN win quality by enough to justify slowness — but only wired as a deliberate
deep tier, never as the churn default. V3 encodes that as a two-tier design with a formal
exception gate. (V1 was sizes-only and missed the on-disk bench data; V2 corrected speed but
excluded dense; V3 is the synthesis.)

## The evidence trail (what changed the design)

**Speed (measured on this M4 Pro, repo bench results):**
- Dense 27-32B: qwen3.8:27b **6.8**, gemma4:31b 5.5, granite4.1:30b 7.2, r1:32b 11.6, GLM-Z1-32B 6.9-8.5,
  olmo-3.1:32b-think 8.3 t/s → all far below the 20 t/s floor.
- MoE A3B/A4B: qwen3-coder-30b 61.7, gemma4-26b-qat 55.0, **qwen3.6:35b-a3b 54.2**, gpt-oss:20b 50.7,
  tongyi-deepresearch-abliterated 49.2 t/s → all comfortably above it.

**Quality — dense wins that warrant the cost (published + repo-internal):**
| Benchmark | Qwen3.8-27B (dense) | Cascade-2-30B-A3B (MoE) | Qwen3.5-35B-A3B (MoE) |
|---|---|---|---|
| GPQA Diamond | **89.2** | 76.1 | 84.2 |
| HLE | **30.8** | 17.7 | 22.4 |
| LiveCodeBench v6 | **90.3** | 87.2 | 74.6 |
| IFBench | 79.5 | **82.9** | 70.2 |
| TerminalBench 2.1 | **73.0** | 21.1 | 40.5 |
| VL (MathVision / OSWorld) | **90.0 / 84.3** | — (text-only) | — |
| Repo bench quality_score (coding prompt) | **1.0** @ 6.8 t/s | unbenched | 0.67-1.0 @ 42-54 t/s |

Qwen3.8-27B beats both MoEs on scientific reasoning and frontier knowledge by wide margins. That is
the operator's "sweet spot": a dense model whose quality delta purchases its speed cost **in the
right lane**. Note: 6.8 t/s is partly llama.cpp kernel immaturity on its hybrid DeltaNet+Attention
arch (64L, 16:1) — re-bench on newer Ollama before accepting the number as final; an MLX build
exists if the Ollama path stays slow.

## Design: two-tier reasoning group

**Tier 1 — default lane (churn; ≥20 t/s floor enforced):**
- Stock slots (`auto-data`, `auto-compliance`, `auto-reasoning`, `auto-math`):
  `qwen3.6:35b-a3b-q4_K_M` primary (installed, 54.2 t/s measured, thinking, tools).
  Challenger: `nemotron-cascade-2:30b` (24GB; Ollama official / bartowski GGUF) — bench-gated; its
  published IFBench 82.9 / ArenaHard 83.5 lead the class → compliance-lane candidate specifically.
- Unc slot (`auto-research`): keep `huihui_ai/tongyi-deepresearch-abliterated` (49.2 t/s; retire its
  -ctx64k variant). Bench challenger: `mradermacher/...Cascade-2-30B-A3B-heretic` (unc MoE).

**Tier 2 — deep lane (quality-exception; slow by design, invoked on demand):**
- `qwen3.8:27b` — wired deliberately as the deep lane for hard analysis / compliance deep-reviews /
  math proofs, with `reasoning_effort` control. NOT the default. Router/intent selects it; evict
  tier-1 weights while it runs (24GB resident at 32K fits once alone — the 55GB failure mode was a
  64K-ctx dense model co-resident with churn, not this pattern).
- Exception gate (a dense model enters tier 2 only with all three):
  1. published OR benched quality win on slot-relevant benchmarks (qwen3.8:27b: GPQA/HLE/LCB table above);
  2. intent is depth-on-demand, not throughput;
  3. accepted t/s documented in backends.yaml next to the model.

**Discovery bench list — "others we have not discovered" (candidates for tier 2 or tier-1 upgrades):**
| Candidate | t/s (measured, if any) | Why interesting |
|---|---|---|
| `olmo-3.1:32b-think` | 8.3 (repo q=1.0) | AI2 thinking dense; GPQA/HLE-class quality unknown → bench |
| `phi4-reasoning:plus` (14B) | 14.8 | closest dense to the floor; math-reasoning pedigree |
| `gemma4:12b` | **26.4 (above floor)** | thinking+tools+vision at floor-compliant speed; quality bench pending |
| `empero-ai/Qwen3.8-9B-Distill` | unbenched | 3.8 lineage quality distilled into MoE-class speed — the best-of-both bet |
| `empero-ai/Qwen3.8-4B/2B-Distill` | unbenched | fast-tier candidates |
| `deepseek-r1:32b-q8_0` | 4.8 (repo q=1.0) | quality real, speed disqualifying — declines |

## Declines (unchanged from V2, now including V1/V2 dense errors handled correctly)

`granite4.1:30b` ×3 (55GB thrash) · `deepseek-r1:32b-q4_k_m`+`q8_0` · `GLM-Z1-Rumination-32B` ×2 ·
`qwen3.6:27b-q8_0`/`q4` · `Qwopus3.6-27B-v2-MTP` · `supergemma4-26b-uncensored` ×2 ·
`Magistral-Small Q8-ctx64k` · `olmo-3.1:32b-think` stays ON the bench list (tier-2 candidate), NOT
declined. ~150GB reclaim.

## Gate

Tier-1 promotes: bench harness (t/s ≥20 + persona-matrix) as always. Tier-2 entries: the three-part
exception gate above, recorded in backends.yaml. Nothing changes mid-UAT; post-UAT sequence:
bench cascade-2 + deep-lane re-bench of qwen3.8:27b on current Ollama → operator approves → rewire →
re-run affected persona rows → v9 re-baseline.
