# Portal 5 — V8 Model Refresh Bench Review

**Generated:** 2026-06-10 15:00 UTC  
**Task:** TASK_MODEL_REFRESH_V8_BENCH  
**PROMOTE_POLICY: LOCKED — zero promotions applied. All decisions require operator action.**

> **Note:** Pipeline results were re-run (v8b) after pipeline container was rebuilt with V8 catalog.
> Original v8 pipeline bench was invalid — container started before the V8 catalog commit (477280b).

---

## Direct TPS (Ollama :11434 — raw inference)

| Model | Category | Est Size | Avg TPS | Min | Max | Runs | Floor ≥20 |
|---|---|---|---|---|---|---|---|
| `gemma4:e2b-it-qat` | Gemma4 E2B QAT | ~3 GB | **49.8** | 44.7 | 56.1 | 5/5 | ✅ PASS |
| `gemma4:e4b-it-qat` | Gemma4 E4B QAT | ~5 GB | **30.4** | 27.2 | 33.6 | 5/5 | ✅ PASS |
| `gemma4:12b-it-qat` | Gemma4 12B QAT | ~7 GB | **13.0** | 11.7 | 14.1 | 5/5 | ❌ FAIL |
| `gemma4:26b-a4b-it-qat` | Gemma4 26B-A4B QAT | ~15 GB | **28.7** | 27.0 | 30.0 | 5/5 | ✅ PASS |
| `gemma4:31b-it-qat` | Gemma4 31B Dense QAT | ~18 GB | **5.9** | 5.7 | 6.3 | 5/5 | ❌ FAIL |
| `phi4-mini` | Phi-4-Mini (Microsoft) | ~2.5 GB | **41.4** | 33.3 | 48.6 | 5/5 | ✅ PASS |
| `phi4-mini-reasoning` | Phi-4-Mini-Reasoning | ~2.5 GB | **45.0** | 41.4 | 48.1 | 5/5 | ✅ PASS |
| `lfm2.5:8b` | LFM2.5-8B-A1B (Liquid AI) | ~5 GB | **86.6** | 80.4 | 93.7 | 5/5 | ✅ PASS |
| `starcoder2:15b` | StarCoder2-15B (BigCode) | ~9 GB | **11.7** | 9.7 | 13.5 | 3/5 | ❌ FAIL |
| `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:` | R1-0528-Qwen3-8B (DeepSeek) | ~5 GB | **30.4** | 28.2 | 31.3 | 5/5 | ✅ PASS |
| `hf.co/ijohn07/harness-1-Q4_K_M-GGUF:Q4_K_M` | Harness-1 (gpt-oss-20B) | ~12 GB | **41.1** | 25.2 | 47.4 | 5/5 | ✅ PASS |
| `devstral-small-2` | Devstral Small 2 (Mistral) | ~14 GB | **8.9** | 8.4 | 9.4 | 5/5 | ❌ FAIL |
| `mistral-small3.2:24b` | Mistral Small 3.2 | ~14 GB | **9.1** | 8.3 | 9.7 | 5/5 | ❌ FAIL |
| `qwen3.6:27b-q4_K_M` | Qwen3.6-27B Dense | ~16 GB | **7.5** | 6.9 | 8.6 | 5/5 | ❌ FAIL |
| `qwen3.6:35b-a3b-q4_K_M` | Qwen3.6-35B-A3B MoE | ~22 GB | **29.8** | 27.3 | 32.3 | 5/5 | ✅ PASS |
| `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M` | Nex-N2-mini (Nex AGI) | ~22 GB | **29.3** | 27.4 | 31.8 | 5/5 | ✅ PASS |
| `olmo-3.1:32b-think` | OLMo 3.1 32B Think (Allen AI) | ~19 GB | **8.2** | 7.7 | 8.5 | 5/5 | ❌ FAIL |
| `qwen3-coder-next` | Qwen3-Coder-Next 80B/3B | ~46 GB | **21.4** | 19.9 | 23.1 | 5/5 | ✅ PASS |

---

## Pipeline TPS (portal-pipeline :9099) — v8b re-run after container rebuild

| Workspace | Model | Avg TPS | Min | Max | Runs | Routed To | Hint Match | Floor ≥20 |
|---|---|---|---|---|---|---|---|---|
| `bench-gemma4-e2b` | Gemma4 E2B QAT | **41.4** | 39.1 | 43.8 | 5/5 | `bench-gemma4-e2b` | ✅ | ✅ PASS |
| `bench-gemma4-e4b-qat` | Gemma4 E4B QAT | **26.5** | 24.2 | 28.6 | 5/5 | `bench-gemma4-e4b-qat` | ✅ | ✅ PASS |
| `bench-gemma4-12b` | Gemma4 12B QAT | **12.6** | 12.2 | 13.7 | 5/5 | `bench-gemma4-12b` | ✅ | ❌ FAIL |
| `bench-gemma4-26b-qat` | Gemma4 26B-A4B QAT | **26.7** | 25.4 | 27.8 | 5/5 | `bench-gemma4-26b-qat` | ✅ | ✅ PASS |
| `bench-gemma4-31b-qat` | Gemma4 31B Dense QAT | **5.6** | 5.2 | 6.3 | 5/5 | `bench-gemma4-31b-qat` | ✅ | ❌ FAIL |
| `bench-phi4-mini` | Phi-4-Mini (Microsoft) | **43.1** | 36.0 | 51.3 | 5/5 | `bench-phi4-mini` | ✅ | ✅ PASS |
| `bench-phi4-mini-reasoning` | Phi-4-Mini-Reasoning | **41.8** | 40.6 | 43.0 | 5/5 | `bench-phi4-mini-reasoning` | ✅ | ✅ PASS |
| `bench-lfm25-8b` | LFM2.5-8B-A1B (Liquid AI) | **86.1** | 82.1 | 89.6 | 5/5 | `bench-lfm25-8b` | ✅ | ✅ PASS |
| `bench-starcoder2` | StarCoder2-15B (BigCode) | **14.4** | 12.3 | 17.3 | 4/5 | `bench-starcoder2` | ✅ | ❌ FAIL |
| `bench-r1-0528-qwen3-8b` | R1-0528-Qwen3-8B (DeepSeek) | **31.3** | 28.0 | 33.7 | 5/5 | `bench-r1-0528-qwen3-8b` | ✅ | ✅ PASS |
| `bench-harness1` | Harness-1 (gpt-oss-20B) | **34.0** | 27.7 | 40.2 | 5/5 | `bench-harness1` | ✅ | ✅ PASS |
| `bench-devstral-small-2` | Devstral Small 2 (Mistral) | **8.2** | 7.5 | 9.7 | 5/5 | `bench-devstral-small-2` | ✅ | ❌ FAIL |
| `bench-mistral-small32` | Mistral Small 3.2 | **8.5** | 7.4 | 10.3 | 5/5 | `bench-mistral-small32` | ✅ | ❌ FAIL |
| `bench-qwen36-27b` | Qwen3.6-27B Dense | **8.7** | 5.2 | 10.0 | 5/5 | `bench-qwen36-27b` | ✅ | ❌ FAIL |
| `bench-qwen36-35b-a3b` | Qwen3.6-35B-A3B MoE | **29.2** | 26.6 | 32.2 | 5/5 | `bench-qwen36-35b-a3b` | ✅ | ✅ PASS |
| `bench-nex-n2-mini` | Nex-N2-mini (Nex AGI) | **26.5** | 23.2 | 28.6 | 5/5 | `bench-nex-n2-mini` | ✅ | ✅ PASS |
| `bench-olmo3-32b` | OLMo 3.1 32B Think (Allen AI) | **8.3** | 8.0 | 8.6 | 5/5 | `bench-olmo3-32b` | ✅ | ❌ FAIL |
| `bench-qwen3-coder-next` | Qwen3-Coder-Next 80B/3B | **20.6** | 17.9 | 23.7 | 5/5 | `bench-qwen3-coder-next` | ✅ | ✅ PASS |

---

## Smoke Streams (Phase 5)

All 18 workspaces: **18/18 PASS** ✅

---

## Promotion Eligibility

> Each row requires an explicit operator decision and a separate TASK_MODEL_PROMOTE_V8.md.
> Floor ≥20 t/s is a guideline, not a hard gate — operator may promote below-floor models for specific use cases.

| Model | Size | Direct TPS | Pipeline TPS | Floor ≥20? | QS | Special Notes |
|---|---|---|---|---|---|---|
| `gemma4:e2b-it-qat` | ~3 GB | 49.8 | 41.4 | ✅ Yes | 1.00 | Top-2 direct + pipeline — 3GB tiny |
| `gemma4:e4b-it-qat` | ~5 GB | 30.4 | 26.5 | ✅ Yes | 1.00 | +18% vs prod e4b (25.8 t/s) |
| `gemma4:12b-it-qat` | ~7 GB | 13.0 | 12.6 | ❌ No | 1.00 | 13.0 t/s direct — below floor |
| `gemma4:26b-a4b-it-qat` | ~15 GB | 28.7 | 26.7 | ✅ Yes | 1.00 | +23% vs prod 26b (23.3 t/s) |
| `gemma4:31b-it-qat` | ~18 GB | 5.9 | 5.6 | ❌ No | 1.00 | Dense 31B too slow on this hardware |
| `phi4-mini` | ~2.5 GB | 41.4 | 43.1 | ✅ Yes | 0.86 | Strong daily-driver candidate; QS slightly off |
| `phi4-mini-reasoning` | ~2.5 GB | 45.0 | 41.8 | ✅ Yes | 1.00 | Reasoning variant; consistent quality |
| `lfm2.5:8b` | ~5 GB | 86.6 | 86.1 | ✅ Yes | 1.00 | Fastest in fleet; pipeline TPS matches direct |
| `starcoder2:15b` | ~9 GB | 11.7 | 14.4 | ❌ No | 0.00 | 4/5 runs; 0.00 QS; BigCode RAIL-M license |
| `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GG` | ~5 GB | 30.4 | 31.3 | ✅ Yes | 1.00 | Faster R1 alternative; pipeline ≈ direct |
| `hf.co/ijohn07/harness-1-Q4_K_M-GGUF:Q4_K_M` | ~12 GB | 41.1 | 34.0 | ✅ Yes | 1.00 | Needs Chroma for full RAG capability |
| `devstral-small-2` | ~14 GB | 8.9 | 8.2 | ❌ No | 1.00 | 9 t/s — not competitive for 14GB |
| `mistral-small3.2:24b` | ~14 GB | 9.1 | 8.5 | ❌ No | 1.00 | 9 t/s — not competitive for 14GB |
| `qwen3.6:27b-q4_K_M` | ~16 GB | 7.5 | 8.7 | ❌ No | 0.67 | Dense 27B too slow; partial quality |
| `qwen3.6:35b-a3b-q4_K_M` | ~22 GB | 29.8 | 29.2 | ✅ Yes | 0.67 | MoE efficient; QS needs investigation |
| `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M` | ~22 GB | 29.3 | 26.5 | ✅ Yes | 1.00 | Qwen3.5-35B-A3B fine-tune; good quality |
| `olmo-3.1:32b-think` | ~19 GB | 8.2 | 8.3 | ❌ No | 1.00 | 8 t/s both paths; supports_tools=false |
| `qwen3-coder-next` | ~46 GB | 21.4 | 20.6 | ✅ Yes | 0.83 | 80B/3B MoE — fits 64GB M4 Pro; partial QS |

---

## Key Findings

| Finding | Detail |
|---|---|
| 🏆 Fastest overall | `lfm2.5:8b` — 86.6 t/s direct, 86.1 t/s pipeline (near-zero overhead) |
| 🏆 Best pipeline throughput | `bench-lfm25-8b` 86.1 t/s, `bench-phi4-mini` 43.1 t/s, `bench-phi4-mini-reasoning` 41.8 t/s |
| ✅ QAT upgrade winners | gemma4:e2b-qat (+∞ new), e4b-qat (+18%), 26b-qat (+23%) |
| ❌ QAT no-ops | gemma4:12b-qat (13 t/s), 31b-qat (5.9 t/s) |
| ⚠️ OLMo resolved | Previous 48.4 t/s pipeline was wrong model (stale container); real OLMo = 8.3 t/s |
| ⚠️ StarCoder2 | 4/5 pipeline runs, 0.00 QS (BigCode RAIL-M license also applies) |
| ⚠️ QS <1.0 | phi4-mini (0.86), qwen36-27b (0.67), qwen36-35b-a3b (0.67), qwen3-coder-next (0.83) |
| ✅ Smoke | 18/18 workspaces pass |
| ✅ Hint match | All 18 pipeline workspaces routed correctly (verified on rebuilt container) |

---

## Next Steps (operator decisions required)

1. **QAT promotions**: gemma4:e2b-qat, e4b-qat, 26b-qat show direct + pipeline TPS gains — quality eval needed before promoting.

2. **phi4-mini / phi4-mini-reasoning**: 41–45 t/s both paths — strong daily-driver candidates; phi4-mini QS=0.86 warrants a quality spot-check.

3. **lfm2.5:8b**: 86.6 t/s — fastest model in fleet; pipeline TPS matches direct (near-zero routing overhead). Evaluate for latency-sensitive workspaces.

4. **R1-0528-Qwen3-8B**: 30–31 t/s both paths — faster R1-class option; evaluate quality vs current reasoning model.

5. **harness-1**: 41.1 t/s direct, 34.0 t/s pipeline — needs Chroma RAG stack for full capability; not a drop-in.

6. **qwen3.6:35b-a3b / nex-n2-mini**: 26–29 t/s both paths; QS investigation needed on 35b-a3b (0.67).

7. **Below-floor notes**: starcoder2, devstral-small-2, mistral-small3.2, qwen3.6:27b, gemma4:12b/31b-qat, olmo-3.1:32b all under 20 t/s — evaluate use-case fit before promoting.

8. **OLMo**: supports_tools=false — not usable as a general assistant workspace without tool support.

9. **StarCoder2**: BigCode RAIL-M license — review commercial clauses before external exposure.

10. File `TASK_MODEL_PROMOTE_V8.md` per promotion decision: specify target workspace, displaced model, rollback plan.
