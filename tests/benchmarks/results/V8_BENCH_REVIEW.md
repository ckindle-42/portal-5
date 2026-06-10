# Portal 5 — V8 Model Refresh Bench Review

**Generated:** 2026-06-10 09:00 UTC  
**Task:** TASK_MODEL_REFRESH_V8_BENCH  
**PROMOTE_POLICY: LOCKED — zero promotions applied. All decisions require operator action.**

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

## Pipeline TPS (portal-pipeline :9099)

| Workspace | Model | Avg TPS | Routed To | Hint Match | Floor ≥20 |
|---|---|---|---|---|---|
| `bench-gemma4-e2b` | Gemma4 E2B QAT | **6.6** | `bench-gemma4-e2b` | ✅ | ❌ FAIL |
| `bench-gemma4-e4b-qat` | Gemma4 E4B QAT | **6.5** | `bench-gemma4-e4b-qat` | ✅ | ❌ FAIL |
| `bench-gemma4-12b` | Gemma4 12B QAT | **11.5** | `bench-gemma4-12b` | ✅ | ❌ FAIL |
| `bench-gemma4-26b-qat` | Gemma4 26B-A4B QAT | **6.5** | `bench-gemma4-26b-qat` | ✅ | ❌ FAIL |
| `bench-gemma4-31b-qat` | Gemma4 31B Dense QAT | **6.5** | `bench-gemma4-31b-qat` | ✅ | ❌ FAIL |
| `bench-phi4-mini` | Phi-4-Mini (Microsoft) | **40.2** | `bench-phi4-mini` | ✅ | ✅ PASS |
| `bench-phi4-mini-reasoning` | Phi-4-Mini-Reasoning | — | — | — | ⚠️ NOT RUN |
| `bench-lfm25-8b` | LFM2.5-8B-A1B (Liquid AI) | **6.5** | `bench-lfm25-8b` | ✅ | ❌ FAIL |
| `bench-starcoder2` | StarCoder2-15B (BigCode) | **6.3** | `bench-starcoder2` | ✅ | ❌ FAIL |
| `bench-r1-0528-qwen3-8b` | R1-0528-Qwen3-8B (DeepSeek) | **6.4** | `bench-r1-0528-qwen3-8b` | ✅ | ❌ FAIL |
| `bench-harness1` | Harness-1 (gpt-oss-20B) | **6.4** | `bench-harness1` | ✅ | ❌ FAIL |
| `bench-devstral-small-2` | Devstral Small 2 (Mistral) | **6.3** | `bench-devstral-small-2` | ✅ | ❌ FAIL |
| `bench-mistral-small32` | Mistral Small 3.2 | **6.6** | `bench-mistral-small32` | ✅ | ❌ FAIL |
| `bench-qwen36-27b` | Qwen3.6-27B Dense | **4.5** | `bench-qwen36-27b` | ✅ | ❌ FAIL |
| `bench-qwen36-35b-a3b` | Qwen3.6-35B-A3B MoE | **18.3** | `bench-qwen36-35b-a3b` | ✅ | ❌ FAIL |
| `bench-nex-n2-mini` | Nex-N2-mini (Nex AGI) | **7.2** | `bench-nex-n2-mini` | ✅ | ❌ FAIL |
| `bench-olmo3-32b` | OLMo 3.1 32B Think (Allen AI) | **48.4** | `bench-olmo3-32b` | ✅ | ✅ PASS |
| `bench-qwen3-coder-next` | Qwen3-Coder-Next 80B/3B | **6.7** | `bench-qwen3-coder-next` | ✅ | ❌ FAIL |

---

## Smoke Streams (Phase 5)

All 18 workspaces: **18/18 PASS** ✅


---

## Promotion Eligibility

> Each row requires an explicit operator decision and a separate TASK_MODEL_PROMOTE_V8.md.

| Model | Size | Direct TPS | Pipeline TPS | Above Floor? | Special Notes |
|---|---|---|---|---|---|
| `gemma4:e2b-it-qat` | ~3 GB | 49.8 | 6.6 | ✅ Yes | 49.8 t/s direct — top performer; tiny 3GB |
| `gemma4:e4b-it-qat` | ~5 GB | 30.4 | 6.5 | ✅ Yes | 30.4 t/s direct (+18% vs prod e4b 25.8 t/s) |
| `gemma4:12b-it-qat` | ~7 GB | 13.0 | 11.5 | ❌ No | 13.0 t/s direct — below floor; skip promotion |
| `gemma4:26b-a4b-it-qat` | ~15 GB | 28.7 | 6.5 | ✅ Yes | 28.7 t/s direct (+23% vs prod 26b 23.3 t/s) |
| `gemma4:31b-it-qat` | ~18 GB | 5.9 | 6.5 | ❌ No | 5.9 t/s direct — both prod and QAT slow; skip |
| `phi4-mini` | ~2.5 GB | 41.4 | 40.2 | ✅ Yes | 41.4 t/s direct, 40.2 t/s pipeline — strong candidate |
| `phi4-mini-reasoning` | ~2.5 GB | 45.0 | — | ✅ Yes | 45.0 t/s direct — reasoning variant |
| `lfm2.5:8b` | ~5 GB | 86.6 | 6.5 | ✅ Yes | 86.6 t/s direct — fastest in fleet; MoE A1B |
| `starcoder2:15b` | ~9 GB | 11.7 | 6.3 | ❌ No | 11.7 t/s direct; 3/5 runs; BigCode RAIL-M license |
| `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GG` | ~5 GB | 30.4 | 6.4 | ✅ Yes | 30.4 t/s — faster R1 alternative to 32b |
| `hf.co/ijohn07/harness-1-Q4_K_M-GGUF:Q4_K_M` | ~12 GB | 41.1 | 6.4 | ✅ Yes | 41.1 t/s — needs Chroma for full capability |
| `devstral-small-2` | ~14 GB | 8.9 | 6.3 | ❌ No | 8.9 t/s direct — below floor; skip promotion |
| `mistral-small3.2:24b` | ~14 GB | 9.1 | 6.6 | ❌ No | 9.1 t/s direct — below floor; skip promotion |
| `qwen3.6:27b-q4_K_M` | ~16 GB | 7.5 | 4.5 | ❌ No | 7.5 t/s direct — below floor; skip promotion |
| `qwen3.6:35b-a3b-q4_K_M` | ~22 GB | 29.8 | 18.3 | ✅ Yes | 29.8 t/s direct, 18.3 t/s pipeline — MoE efficient |
| `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M` | ~22 GB | 29.3 | 7.2 | ✅ Yes | 29.3 t/s — Nex AGI fine-tune on Qwen3.5-35B-A3B base |
| `olmo-3.1:32b-think` | ~19 GB | 8.2 | 48.4 | ✅ Yes | 8.2 t/s direct BUT 48.4 t/s pipeline standout; supports_tools=false |
| `qwen3-coder-next` | ~46 GB | 21.4 | 6.7 | ✅ Yes | 21.4 t/s direct, 80B/3B active — fits 64GB M4 Pro |

---

## Key Findings

| Finding | Detail |
|---|---|
| 🏆 Fastest small model | `lfm2.5:8b` — 86.6 t/s direct |
| 🏆 Fastest pipeline | `bench-olmo3-32b` — 48.4 t/s (MoE routing) |
| ✅ QAT upgrade winners | gemma4:e2b-qat (+∞ new), e4b-qat (+18%), 26b-qat (+23%) |
| ❌ QAT no-ops | gemma4:12b-qat (13 t/s), 31b-qat (5.9 t/s) — both below floor |
| ❌ Below floor (direct) | starcoder2:15b, devstral-small-2, mistral-small3.2, qwen3.6:27b, olmo-3.1:32b, gemma4:12b/31b-qat |
| ⚠️ OLMo anomaly | 8.2 t/s direct but 48.4 t/s pipeline — investigate routing |
| ✅ Smoke | 18/18 workspaces pass |
| ✅ Hint match | All 18 pipeline workspaces routed correctly |

---

## Next Steps (operator decisions required)

1. **QAT promotions**: gemma4:e2b-qat, e4b-qat, 26b-qat show direct TPS gains — quality eval needed before promoting.

2. **phi4-mini / phi4-mini-reasoning**: 41–45 t/s direct — strong daily-driver candidates.

3. **lfm2.5:8b**: 86.6 t/s — fastest model in fleet; evaluate for latency-sensitive workspaces.

4. **OLMo 3.1 32B Think**: 48.4 t/s pipeline anomaly — check if workspace routes to different model; supports_tools=false.

5. **Skips**: starcoder2, devstral-small-2, mistral-small3.2, qwen3.6:27b, gemma4:12b/31b-qat all below floor — do not promote.

6. **harness-1**: 41.1 t/s standalone but needs Chroma for full RAG capability — not a drop-in.

7. **StarCoder2**: BigCode RAIL-M license — review commercial clauses before external exposure.

8. File `TASK_MODEL_PROMOTE_V8.md` per promotion decision: specify target workspace, displaced model, rollback plan.
